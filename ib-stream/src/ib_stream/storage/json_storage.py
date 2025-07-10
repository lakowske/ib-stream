"""
JSON storage implementation for IB Stream.

Provides efficient JSON Lines storage with hourly file rotation
and fast append operations.
"""

import json
import asyncio
import aiofiles
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, TextIO
from pathlib import Path

logger = logging.getLogger(__name__)


class JSONStorage:
    """
    JSON Lines storage with hourly file partitioning.
    
    Stores stream messages as JSON Lines format with automatic
    file rotation every hour for manageable file sizes.
    """
    
    def __init__(self, storage_path: Path):
        """
        Initialize JSON storage.
        
        Args:
            storage_path: Base path for JSON storage files
        """
        self.storage_path = storage_path
        self.file_handles: Dict[str, TextIO] = {}
        self.current_files: Dict[str, Path] = {}
        self._rotation_lock = asyncio.Lock()
        
    async def start(self):
        """Initialize storage system."""
        # Create storage directory
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"JSON storage initialized at {self.storage_path}")
        
    async def stop(self):
        """Stop storage and close all file handles."""
        # Close all open file handles
        for handle in self.file_handles.values():
            if not handle.closed:
                handle.close()
        
        self.file_handles.clear()
        self.current_files.clear()
        logger.info("JSON storage stopped")
        
    async def write_messages(self, stream_id: str, messages: List[Dict[str, Any]]):
        """
        Write messages to JSON storage.
        
        Args:
            stream_id: Stream identifier for file organization
            messages: List of messages to write
        """
        if not messages:
            return
            
        # Get file path for current hour
        file_path = await self._get_current_file(stream_id)
        
        # Write messages to file
        try:
            async with aiofiles.open(file_path, 'a', encoding='utf-8') as f:
                for message in messages:
                    json_line = json.dumps(message, separators=(',', ':'), ensure_ascii=False)
                    await f.write(json_line + '\n')
                    
            logger.debug(f"Wrote {len(messages)} messages to {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to write messages to {file_path}: {e}")
            raise
            
    async def _get_current_file(self, stream_id: str) -> Path:
        """
        Get the current file path for a stream, creating hourly partitions.
        
        Args:
            stream_id: Stream identifier
            
        Returns:
            Path to current file for the stream
        """
        now = datetime.now(timezone.utc)
        
        # Create file path with hourly partitioning
        # Format: {storage_path}/YYYY/MM/DD/HH/stream_id.jsonl
        date_path = now.strftime('%Y/%m/%d/%H')
        file_dir = self.storage_path / date_path
        file_path = file_dir / f"{stream_id}.jsonl"
        
        # Check if we need to rotate to a new file
        current_file = self.current_files.get(stream_id)
        if current_file != file_path:
            async with self._rotation_lock:
                # Double-check after acquiring lock
                if self.current_files.get(stream_id) != file_path:
                    # Create directory if needed
                    file_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Update current file tracking
                    self.current_files[stream_id] = file_path
                    
                    logger.debug(f"Rotated to new file: {file_path}")
                    
        return file_path
        
    async def query_range(
        self,
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Query messages from JSON storage within time range.
        
        Args:
            contract_id: Contract ID to filter
            tick_types: List of tick types to include
            start_time: Start of time range
            end_time: End of time range (None for present)
            
        Returns:
            List of messages in the time range
        """
        if end_time is None:
            end_time = datetime.now(timezone.utc)
            
        # Find all potential files in the time range
        file_paths = self._get_files_in_range(start_time, end_time)
        
        messages = []
        
        for file_path in file_paths:
            if file_path.exists():
                file_messages = await self._read_file_range(
                    file_path, contract_id, tick_types, start_time, end_time
                )
                messages.extend(file_messages)
                
        # Sort by timestamp
        messages.sort(key=lambda m: m.get('timestamp', ''))
        
        return messages
        
    def _get_files_in_range(self, start_time: datetime, end_time: datetime) -> List[Path]:
        """
        Get all potential file paths that could contain data in the time range.
        
        Args:
            start_time: Start of time range
            end_time: End of time range
            
        Returns:
            List of file paths to check
        """
        file_paths = []
        
        # Generate hourly file paths for the entire range
        current = start_time.replace(minute=0, second=0, microsecond=0)
        
        while current <= end_time:
            date_path = current.strftime('%Y/%m/%d/%H')
            hour_dir = self.storage_path / date_path
            
            # Add all JSON files in this hour directory
            if hour_dir.exists():
                for file_path in hour_dir.glob('*.jsonl'):
                    file_paths.append(file_path)
                    
            current += timedelta(hours=1)
            
        return file_paths
        
    async def _read_file_range(
        self,
        file_path: Path,
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Read messages from a single file within the time range.
        
        Args:
            file_path: Path to JSON file
            contract_id: Contract ID to filter
            tick_types: List of tick types to include
            start_time: Start of time range
            end_time: End of time range
            
        Returns:
            List of messages from the file
        """
        messages = []
        
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                async for line in f:
                    line = line.strip()
                    if not line:
                        continue
                        
                    try:
                        message = json.loads(line)
                        
                        # Filter by contract_id and tick_type
                        if self._message_matches_filter(message, contract_id, tick_types):
                            # Check timestamp range
                            msg_time = datetime.fromisoformat(
                                message['timestamp'].replace('Z', '+00:00')
                            )
                            
                            if start_time <= msg_time <= end_time:
                                messages.append(message)
                                
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Skipping invalid JSON line in {file_path}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            
        return messages
        
    def _message_matches_filter(
        self,
        message: Dict[str, Any],
        contract_id: int,
        tick_types: List[str]
    ) -> bool:
        """
        Check if a message matches the filter criteria.
        
        Args:
            message: Message to check
            contract_id: Required contract ID
            tick_types: List of allowed tick types
            
        Returns:
            True if message matches filter
        """
        # Check message type
        if message.get('type') != 'tick':
            return False
            
        # Check contract_id in tick data
        data = message.get('data', {})
        if data.get('contract_id') != contract_id:
            return False
            
        # Check tick_type
        if tick_types and data.get('tick_type') not in tick_types:
            return False
            
        return True
        
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get statistics about JSON storage."""
        total_files = 0
        total_size = 0
        
        # Walk through storage directory
        if self.storage_path.exists():
            for file_path in self.storage_path.rglob('*.jsonl'):
                total_files += 1
                try:
                    total_size += file_path.stat().st_size
                except OSError:
                    pass
                    
        return {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / 1024 / 1024, 2),
            'active_streams': len(self.current_files)
        }