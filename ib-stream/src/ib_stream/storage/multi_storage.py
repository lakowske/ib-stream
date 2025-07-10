"""
Multi-format storage implementation for IB Stream.

Provides parallel storage in JSON and protobuf formats for comparison
and debugging while maintaining fast write performance.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path

from .json_storage import JSONStorage
from .protobuf_storage import ProtobufStorage
from .metrics import StorageMetrics

logger = logging.getLogger(__name__)


class MultiStorage:
    """
    Multi-format storage that writes to JSON and protobuf in parallel.
    
    Provides a unified interface for storing stream messages in multiple
    formats simultaneously, enabling comparison and gradual migration.
    """
    
    def __init__(
        self,
        storage_path: Path,
        enable_json: bool = True,
        enable_protobuf: bool = True,
        enable_metrics: bool = True
    ):
        """
        Initialize multi-format storage.
        
        Args:
            storage_path: Base path for storage files
            enable_json: Whether to enable JSON storage
            enable_protobuf: Whether to enable protobuf storage
            enable_metrics: Whether to enable metrics collection
        """
        self.storage_path = storage_path
        self.enable_json = enable_json
        self.enable_protobuf = enable_protobuf
        
        # Initialize storage backends
        self.storages: Dict[str, Any] = {}
        
        if enable_json:
            self.storages['json'] = JSONStorage(storage_path / 'json')
            
        if enable_protobuf:
            self.storages['protobuf'] = ProtobufStorage(storage_path / 'protobuf')
        
        # Initialize metrics
        self.metrics = StorageMetrics() if enable_metrics else None
        
        # Track active files and write queues
        self._write_queues: Dict[str, asyncio.Queue] = {}
        self._write_tasks: Dict[str, asyncio.Task] = {}
        self._file_handles: Dict[str, Dict[str, Any]] = {}
        
    async def start(self):
        """Start storage system and background tasks."""
        logger.info("Starting MultiStorage system")
        
        # Create storage directories
        for storage_name, storage in self.storages.items():
            await storage.start()
            
        # Start write workers for each storage backend
        for storage_name in self.storages.keys():
            queue = asyncio.Queue(maxsize=10000)  # Buffer up to 10k messages
            self._write_queues[storage_name] = queue
            
            task = asyncio.create_task(
                self._write_worker(storage_name, queue),
                name=f"storage_writer_{storage_name}"
            )
            self._write_tasks[storage_name] = task
            
        logger.info(f"Started MultiStorage with backends: {list(self.storages.keys())}")
        
    async def stop(self):
        """Stop storage system and flush all pending writes."""
        logger.info("Stopping MultiStorage system")
        
        # Signal all write workers to stop
        for queue in self._write_queues.values():
            await queue.put(None)  # Sentinel value
            
        # Wait for all write tasks to complete
        if self._write_tasks:
            await asyncio.gather(*self._write_tasks.values())
            
        # Stop storage backends
        for storage in self.storages.values():
            await storage.stop()
            
        logger.info("MultiStorage system stopped")
        
    async def store_message(self, message: Dict[str, Any]) -> None:
        """
        Store a stream message in all enabled formats.
        
        Args:
            message: Stream message in v2 protocol format
        """
        if self.metrics:
            self.metrics.record_message_received()
            
        # Extract message info for routing
        message_type = message.get('type', 'unknown')
        stream_id = message.get('stream_id', 'unknown')
        
        # Queue message for each storage backend
        for storage_name, queue in self._write_queues.items():
            try:
                queue.put_nowait((message_type, stream_id, message))
                if self.metrics:
                    self.metrics.record_write_queued(storage_name)
            except asyncio.QueueFull:
                logger.warning(f"Write queue full for {storage_name}, dropping message")
                if self.metrics:
                    self.metrics.record_write_dropped(storage_name)
                    
    async def _write_worker(self, storage_name: str, queue: asyncio.Queue):
        """
        Background worker that processes write queue for a storage backend.
        
        Args:
            storage_name: Name of the storage backend
            queue: Queue of messages to write
        """
        storage = self.storages[storage_name]
        batch_size = 100
        batch_timeout = 1.0  # seconds
        
        logger.info(f"Starting write worker for {storage_name}")
        
        try:
            while True:
                batch = []
                
                # Collect batch of messages
                try:
                    # Get first message (blocking)
                    item = await asyncio.wait_for(queue.get(), timeout=batch_timeout)
                    if item is None:  # Sentinel value to stop
                        break
                        
                    batch.append(item)
                    
                    # Get additional messages (non-blocking)
                    while len(batch) < batch_size:
                        try:
                            item = queue.get_nowait()
                            if item is None:  # Sentinel value to stop
                                break
                            batch.append(item)
                        except asyncio.QueueEmpty:
                            break
                            
                except asyncio.TimeoutError:
                    # No messages in timeout period, continue
                    continue
                    
                # Process batch
                if batch:
                    await self._write_batch(storage_name, storage, batch)
                    
        except Exception as e:
            logger.error(f"Write worker {storage_name} failed: {e}")
        finally:
            logger.info(f"Write worker for {storage_name} stopped")
            
    async def _write_batch(self, storage_name: str, storage: Any, batch: List[tuple]):
        """
        Write a batch of messages to storage backend.
        
        Args:
            storage_name: Name of the storage backend
            storage: Storage backend instance
            batch: List of (message_type, stream_id, message) tuples
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            # Group messages by stream_id for efficient writing
            streams: Dict[str, List[Dict[str, Any]]] = {}
            
            for message_type, stream_id, message in batch:
                if stream_id not in streams:
                    streams[stream_id] = []
                streams[stream_id].append(message)
                
            # Write each stream's messages
            for stream_id, messages in streams.items():
                await storage.write_messages(stream_id, messages)
                
            # Record metrics
            if self.metrics:
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                self.metrics.record_batch_written(storage_name, len(batch), duration)
                
        except Exception as e:
            logger.error(f"Failed to write batch to {storage_name}: {e}")
            if self.metrics:
                self.metrics.record_write_error(storage_name)
                
    async def query_range(
        self,
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: Optional[datetime] = None,
        storage_format: str = 'json'
    ) -> List[Dict[str, Any]]:
        """
        Query historical data from storage.
        
        Args:
            contract_id: Contract ID to query
            tick_types: List of tick types to include
            start_time: Start of time range
            end_time: End of time range (None for present)
            storage_format: Which storage format to query ('json' or 'protobuf')
            
        Returns:
            List of messages in the time range
        """
        if storage_format not in self.storages:
            raise ValueError(f"Storage format {storage_format} not enabled")
            
        storage = self.storages[storage_format]
        
        if hasattr(storage, 'query_range'):
            return await storage.query_range(contract_id, tick_types, start_time, end_time)
        else:
            raise NotImplementedError(f"Query not implemented for {storage_format}")
            
    def get_metrics(self) -> Optional[Dict[str, Any]]:
        """Get storage metrics."""
        if self.metrics:
            return self.metrics.get_stats()
        return None
        
    def get_storage_info(self) -> Dict[str, Any]:
        """Get information about enabled storage backends."""
        return {
            'enabled_formats': list(self.storages.keys()),
            'storage_path': str(self.storage_path),
            'queue_sizes': {
                name: queue.qsize() 
                for name, queue in self._write_queues.items()
            }
        }