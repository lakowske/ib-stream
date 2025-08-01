"""
Enhanced MultiStorage with v2+v3 parallel storage support.

Extends the original MultiStorage to support both v2 (legacy) and v3 (optimized)
storage formats running in parallel, enabling safe migration and performance comparison.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

from .json_storage import JSONStorage
from .protobuf_storage import ProtobufStorage
from .v3_json_storage import V3JSONStorage
from .v3_protobuf_storage import V3ProtobufStorage
from .metrics import StorageMetrics
from ib_util.storage import TickMessage, create_tick_message_from_v2

logger = logging.getLogger(__name__)


class MultiStorageV3:
    """
    Enhanced multi-format storage with v2+v3 parallel support.
    
    Supports simultaneous storage in:
    - v2 JSON (legacy format with nested structure)
    - v2 Protobuf (legacy format)
    - v3 JSON (optimized format, 50%+ smaller)
    - v3 Protobuf (optimized format, 40%+ smaller)
    
    Enables safe migration and performance comparison between formats.
    """
    
    def __init__(
        self,
        storage_path: Path,
        enable_v2_json: bool = True,
        enable_v2_protobuf: bool = True,
        enable_v3_json: bool = True,
        enable_v3_protobuf: bool = True,
        enable_metrics: bool = True,
        v3_only_mode: bool = False  # For future migration: only store v3 format
    ):
        """
        Initialize enhanced multi-format storage.
        
        Args:
            storage_path: Base path for storage files
            enable_v2_json: Whether to enable v2 JSON storage
            enable_v2_protobuf: Whether to enable v2 protobuf storage
            enable_v3_json: Whether to enable v3 JSON storage
            enable_v3_protobuf: Whether to enable v3 protobuf storage
            enable_metrics: Whether to enable metrics collection
            v3_only_mode: If True, only store v3 format (for migration)
        """
        self.storage_path = storage_path
        self.v3_only_mode = v3_only_mode
        
        # Initialize storage backends
        self.storages: Dict[str, Any] = {}
        
        # v2 storage backends (legacy)
        if enable_v2_json and not v3_only_mode:
            self.storages['v2_json'] = JSONStorage(storage_path / 'v2' / 'json')
            
        if enable_v2_protobuf and not v3_only_mode:
            self.storages['v2_protobuf'] = ProtobufStorage(storage_path / 'v2' / 'protobuf')
        
        # v3 storage backends (optimized)
        if enable_v3_json:
            self.storages['v3_json'] = V3JSONStorage(storage_path / 'v3' / 'json')
            
        if enable_v3_protobuf:
            self.storages['v3_protobuf'] = V3ProtobufStorage(storage_path / 'v3' / 'protobuf')
        
        # Initialize metrics
        self.metrics = StorageMetrics() if enable_metrics else None
        
        # Track active files and write queues
        self._write_queues: Dict[str, asyncio.Queue] = {}
        self._write_tasks: Dict[str, asyncio.Task] = {}
        self._message_stats = {
            'v2_messages': 0,
            'v3_messages': 0,
            'conversion_errors': 0
        }
        
    async def start(self):
        """Start storage system and background tasks."""
        logger.info("Starting MultiStorageV3 system")
        
        # Create storage directories and start backends
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
            
        enabled_formats = list(self.storages.keys())
        logger.info(f"Started MultiStorageV3 with formats: {enabled_formats}")
        
    async def stop(self):
        """Stop storage system and flush all pending writes."""
        logger.info("Stopping MultiStorageV3 system")
        
        # Signal all write workers to stop
        for queue in self._write_queues.values():
            await queue.put(None)  # Sentinel value
            
        # Wait for all write tasks to complete
        if self._write_tasks:
            await asyncio.gather(*self._write_tasks.values())
            
        # Stop storage backends
        for storage in self.storages.values():
            await storage.stop()
            
        logger.info("MultiStorageV3 system stopped")
        
    async def store_message(self, message: Dict[str, Any]) -> None:
        """
        Backwards compatibility method that delegates to store_v2_message.
        
        This maintains interface compatibility with existing code that expects
        the original MultiStorage.store_message() method.
        
        Args:
            message: Stream message in v2 protocol format
        """
        await self.store_v2_message(message)
    
    async def store_v2_message(self, message: Dict[str, Any]) -> None:
        """
        Store a v2 protocol message to both v2 and v3 storage formats.
        
        This method handles the dual storage logic:
        1. Store original v2 message to v2 storage backends
        2. Convert to TickMessage and store to v3 storage backends
        
        Args:
            message: Stream message in v2 protocol format
        """
        if self.metrics:
            self.metrics.record_message_received()
            
        self._message_stats['v2_messages'] += 1
        
        # Extract message info for routing
        message_type = message.get('type', 'unknown')
        stream_id = message.get('stream_id', 'unknown')
        
        # Queue v2 message for v2 storage backends
        for storage_name, queue in self._write_queues.items():
            if storage_name.startswith('v2_'):
                try:
                    queue.put_nowait(('v2', message_type, stream_id, message))
                    if self.metrics:
                        self.metrics.record_write_queued(storage_name)
                except asyncio.QueueFull:
                    logger.warning(f"Write queue full for {storage_name}, dropping v2 message")
                    if self.metrics:
                        self.metrics.record_write_dropped(storage_name)
        
        # Convert to v3 format and queue for v3 storage backends
        try:
            tick_message = create_tick_message_from_v2(message)
            if tick_message:
                await self.store_v3_message(tick_message)
            else:
                logger.warning("Failed to convert v2 message to v3 format")
                self._message_stats['conversion_errors'] += 1
                
        except Exception as e:
            logger.error(f"Error converting v2 to v3 message: {e}")
            self._message_stats['conversion_errors'] += 1
    
    async def store_v3_message(self, tick_message: TickMessage) -> None:
        """
        Store a v3 TickMessage to v3 storage backends.
        
        Args:
            tick_message: TickMessage in optimized v3 format
        """
        if self.metrics:
            self.metrics.record_message_received()
            
        self._message_stats['v3_messages'] += 1
        
        # Queue TickMessage for v3 storage backends
        for storage_name, queue in self._write_queues.items():
            if storage_name.startswith('v3_'):
                try:
                    queue.put_nowait(('v3', tick_message.cid, tick_message.tt, tick_message))
                    if self.metrics:
                        self.metrics.record_write_queued(storage_name)
                except asyncio.QueueFull:
                    logger.warning(f"Write queue full for {storage_name}, dropping v3 message")
                    if self.metrics:
                        self.metrics.record_write_dropped(storage_name)
    
    async def _write_worker(self, storage_name: str, queue: asyncio.Queue):
        """
        Background worker that processes write queue for a storage backend.
        
        Handles both v2 and v3 message formats based on storage backend type.
        
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
            batch: List of message tuples
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            if storage_name.startswith('v2_'):
                # Handle v2 format messages
                await self._write_v2_batch(storage_name, storage, batch)
            elif storage_name.startswith('v3_'):
                # Handle v3 format messages
                await self._write_v3_batch(storage_name, storage, batch)
            else:
                logger.warning(f"Unknown storage format: {storage_name}")
                
            # Record metrics
            if self.metrics:
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                self.metrics.record_batch_written(storage_name, len(batch), duration)
                
        except Exception as e:
            logger.error(f"Failed to write batch to {storage_name}: {e}")
            if self.metrics:
                self.metrics.record_write_error(storage_name)
    
    async def _write_v2_batch(self, storage_name: str, storage: Any, batch: List[tuple]):
        """Write batch of v2 messages to v2 storage backend."""
        # Group messages by stream_id for efficient writing (v2 format)
        streams: Dict[str, List[Dict[str, Any]]] = {}
        
        for format_type, message_type, stream_id, message in batch:
            if stream_id not in streams:
                streams[stream_id] = []
            streams[stream_id].append(message)
            
        # Write each stream's messages
        for stream_id, messages in streams.items():
            await storage.write_messages(stream_id, messages)
    
    async def _write_v3_batch(self, storage_name: str, storage: Any, batch: List[tuple]):
        """Write batch of v3 TickMessages to v3 storage backend."""
        # Extract TickMessage objects from batch
        tick_messages = []
        
        for format_type, contract_id, tick_type, tick_message in batch:
            tick_messages.append(tick_message)
        
        # Write messages using v3 storage interface
        await storage.write_tick_messages(tick_messages)
    
    async def query_v3_range(
        self,
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: Optional[datetime] = None,
        storage_format: str = 'v3_json',
        limit: Optional[int] = None
    ) -> List[TickMessage]:
        """
        Query historical data from v3 storage.
        
        Args:
            contract_id: Contract ID to query
            tick_types: List of tick types to include
            start_time: Start of time range
            end_time: End of time range (None for present)
            storage_format: Which v3 storage format to query ('v3_json' or 'v3_protobuf')
            limit: Maximum number of messages to return
            
        Returns:
            List of TickMessage objects in the time range
        """
        if storage_format not in self.storages:
            raise ValueError(f"Storage format {storage_format} not enabled")
            
        storage = self.storages[storage_format]
        
        if hasattr(storage, 'query_range'):
            messages = []
            async for message in storage.query_range(contract_id, tick_types, start_time, end_time, limit):
                messages.append(message)
            return messages
        else:
            raise NotImplementedError(f"Query not implemented for {storage_format}")
    
    async def query_v2_range(
        self,
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: Optional[datetime] = None,
        storage_format: str = 'v2_json'
    ) -> List[Dict[str, Any]]:
        """
        Query historical data from v2 storage (legacy format).
        
        Args:
            contract_id: Contract ID to query
            tick_types: List of tick types to include
            start_time: Start of time range
            end_time: End of time range (None for present)
            storage_format: Which v2 storage format to query ('v2_json' or 'v2_protobuf')
            
        Returns:
            List of v2 protocol messages in the time range
        """
        if storage_format not in self.storages:
            raise ValueError(f"Storage format {storage_format} not enabled")
            
        storage = self.storages[storage_format]
        
        if hasattr(storage, 'query_range'):
            return await storage.query_range(contract_id, tick_types, start_time, end_time)
        else:
            raise NotImplementedError(f"Query not implemented for {storage_format}")
    
    async def get_storage_info(self) -> Dict[str, Any]:
        """Get comprehensive information about all storage backends."""
        info = {
            'enabled_formats': list(self.storages.keys()),
            'storage_path': str(self.storage_path),
            'v3_only_mode': self.v3_only_mode,
            'queue_sizes': {
                name: queue.qsize() 
                for name, queue in self._write_queues.items()
            },
            'message_stats': self._message_stats.copy()
        }
        
        # Add per-storage info
        info['storage_details'] = {}
        for name, storage in self.storages.items():
            if hasattr(storage, 'get_storage_stats'):  # v3 storages
                try:
                    info['storage_details'][name] = await storage.get_storage_stats()
                except Exception as e:
                    logger.warning(f"Failed to get stats for {name}: {e}")
                    info['storage_details'][name] = {'error': str(e)}
            else:  # v2 storages
                info['storage_details'][name] = {
                    'type': storage.__class__.__name__,
                    'path': str(getattr(storage, 'storage_path', 'unknown'))
                }
        
        # Add storage comparison
        try:
            comparison = await self.get_storage_comparison()
            info['storage_comparison'] = comparison
        except Exception as e:
            logger.warning(f"Failed to get storage comparison: {e}")
            info['storage_comparison'] = {'error': str(e)}
        
        return info
    
    async def get_storage_comparison(self) -> Dict[str, Any]:
        """
        Get storage size comparison between v2 and v3 formats.
        
        Returns:
            Dictionary with detailed size comparison metrics
        """
        comparison = {
            'v2_total_mb': 0,
            'v3_total_mb': 0,
            'savings_mb': 0,
            'savings_percent': 0,
            'by_format': {}
        }
        
        try:
            # Get stats from all storage backends
            for name, storage in self.storages.items():
                if hasattr(storage, 'get_storage_stats'):
                    stats = await storage.get_storage_stats()
                    size_mb = stats.get('total_size_mb', 0)
                    
                    comparison['by_format'][name] = {
                        'size_mb': size_mb,
                        'files': stats.get('total_files', 0)
                    }
                    
                    if name.startswith('v2_'):
                        comparison['v2_total_mb'] += size_mb
                    elif name.startswith('v3_'):
                        comparison['v3_total_mb'] += size_mb
            
            # Calculate savings
            if comparison['v2_total_mb'] > 0:
                comparison['savings_mb'] = comparison['v2_total_mb'] - comparison['v3_total_mb']
                comparison['savings_percent'] = (comparison['savings_mb'] / comparison['v2_total_mb']) * 100
                
        except Exception as e:
            logger.error(f"Error calculating storage comparison: {e}")
            
        return comparison
    
    async def enable_v3_only_mode(self):
        """
        Enable v3-only mode for final migration phase.
        
        Stops writing to v2 storage backends and only uses v3 optimized storage.
        """
        logger.info("Enabling v3-only mode")
        self.v3_only_mode = True
        
        # Stop v2 write workers
        v2_queues = [name for name in self._write_queues.keys() if name.startswith('v2_')]
        for queue_name in v2_queues:
            queue = self._write_queues[queue_name]
            await queue.put(None)  # Signal stop
            
        # Remove v2 storage backends
        v2_storages = [name for name in self.storages.keys() if name.startswith('v2_')]
        for storage_name in v2_storages:
            storage = self.storages.pop(storage_name)
            await storage.stop()
            
        logger.info(f"v3-only mode enabled. Active formats: {list(self.storages.keys())}")