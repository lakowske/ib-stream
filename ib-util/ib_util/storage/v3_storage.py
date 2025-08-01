"""
Base storage interface for v3 optimized tick message format.

This module provides the foundation for v3 storage engines with optimized
file organization and query capabilities.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator
from .tick_message import TickMessage

logger = logging.getLogger(__name__)


class V3StorageBase(ABC):
    """
    Abstract base class for v3 storage engines.
    
    Provides the interface for optimized storage with contract-based file organization
    and efficient querying capabilities.
    """
    
    def __init__(self, storage_path: Path, enable_compression: bool = False):
        """
        Initialize v3 storage engine.
        
        Args:
            storage_path: Base path for storage files
            enable_compression: Whether to enable file compression
        """
        self.storage_path = Path(storage_path)
        self.enable_compression = enable_compression
        self._file_handles: Dict[str, Any] = {}
        self._write_locks: Dict[str, asyncio.Lock] = {}
        
    async def start(self):
        """Start the storage engine."""
        logger.info(f"Starting v3 storage engine at {self.storage_path}")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
    async def stop(self):
        """Stop the storage engine and close all file handles."""
        logger.info("Stopping v3 storage engine")
        
        # Close all open file handles
        for file_handle in self._file_handles.values():
            if hasattr(file_handle, 'close'):
                try:
                    file_handle.close()
                except Exception as e:
                    logger.warning(f"Error closing file handle: {e}")
        
        self._file_handles.clear()
        self._write_locks.clear()
        
    @abstractmethod
    async def write_tick_message(self, tick_message: TickMessage) -> None:
        """
        Write a single tick message to storage.
        
        Args:
            tick_message: TickMessage to store
        """
        pass
    
    @abstractmethod
    async def write_tick_messages(self, tick_messages: List[TickMessage]) -> None:
        """
        Write multiple tick messages to storage efficiently.
        
        Args:
            tick_messages: List of TickMessage objects to store
        """
        pass
    
    @abstractmethod
    async def query_range(
        self,
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[TickMessage]:
        """
        Query tick messages in a time range.
        
        Args:
            contract_id: Contract ID to query
            tick_types: List of tick types to include
            start_time: Start of time range (inclusive)
            end_time: End of time range (exclusive). None for open-ended.
            limit: Maximum number of messages to return
            
        Yields:
            TickMessage objects in chronological order
        """
        pass
    
    def get_file_path(self, contract_id: int, tick_type: str, timestamp: int) -> Path:
        """
        Generate optimized file path for a tick message.
        
        Uses human-readable format: {contract_id}_{tick_type}_{timestamp_seconds}.ext
        Organized by hour: YYYY/MM/DD/HH/
        
        Args:
            contract_id: IB contract identifier
            tick_type: Tick type (bid_ask, last, etc.)
            timestamp: Unix timestamp in microseconds
            
        Returns:
            Path object for the storage file
        """
        # Convert microseconds to seconds for filename
        timestamp_seconds = timestamp // 1_000_000
        dt = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
        
        # Hourly partitioning: YYYY/MM/DD/HH
        date_path = dt.strftime('%Y/%m/%d/%H')
        
        # Human-readable filename with extension
        extension = self._get_file_extension()
        filename = f"{contract_id}_{tick_type}_{timestamp_seconds}.{extension}"
        
        return self.storage_path / date_path / filename
    
    @abstractmethod
    def _get_file_extension(self) -> str:
        """Get the file extension for this storage type."""
        pass
    
    def _get_file_lock(self, file_path: Path) -> asyncio.Lock:
        """
        Get or create a file-specific lock for thread-safe writing.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Asyncio lock for the file
        """
        file_key = str(file_path)
        if file_key not in self._write_locks:
            self._write_locks[file_key] = asyncio.Lock()
        return self._write_locks[file_key]
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dictionary with storage metrics
        """
        stats = {
            'storage_path': str(self.storage_path),
            'storage_type': self.__class__.__name__,
            'compression_enabled': self.enable_compression,
            'open_files': len(self._file_handles),
            'active_locks': len(self._write_locks)
        }
        
        # Add storage-specific stats
        try:
            # Count files and calculate total size
            total_files = 0
            total_size = 0
            
            if self.storage_path.exists():
                for file_path in self.storage_path.rglob(f"*.{self._get_file_extension()}"):
                    total_files += 1
                    total_size += file_path.stat().st_size
                    
            stats.update({
                'total_files': total_files,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            })
            
        except Exception as e:
            logger.warning(f"Error calculating storage stats: {e}")
            
        return stats
    
    def _parse_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Parse filename to extract contract_id, tick_type, and timestamp.
        
        Args:
            filename: Filename in format {contract_id}_{tick_type}_{timestamp}.ext
            
        Returns:
            Dictionary with parsed information or None if invalid
        """
        try:
            # Remove extension
            name_part = filename.rsplit('.', 1)[0]
            
            # Split by underscore
            parts = name_part.split('_')
            
            if len(parts) >= 3:
                contract_id = int(parts[0])
                timestamp = int(parts[-1])
                tick_type = '_'.join(parts[1:-1])  # Handle tick types with underscores
                
                return {
                    'contract_id': contract_id,
                    'tick_type': tick_type,
                    'timestamp': timestamp
                }
                
        except (ValueError, IndexError) as e:
            logger.debug(f"Invalid filename format: {filename} - {e}")
            
        return None
    
    def _find_files_in_range(
        self, 
        contract_id: int, 
        tick_types: List[str], 
        start_time: datetime, 
        end_time: Optional[datetime] = None
    ) -> List[Path]:
        """
        Find storage files that might contain data in the specified range.
        
        Args:
            contract_id: Contract ID to search for
            tick_types: List of tick types to include
            start_time: Start of time range
            end_time: End of time range (None for open-ended)
            
        Returns:
            List of file paths that might contain relevant data
        """
        files = []
        
        if not self.storage_path.exists():
            return files
            
        # Calculate time range in seconds
        start_timestamp = int(start_time.timestamp())
        end_timestamp = int(end_time.timestamp()) if end_time else None
        
        # Find all files matching the contract and tick types
        extension = self._get_file_extension()
        
        for tick_type in tick_types:
            pattern = f"{contract_id}_{tick_type}_*.{extension}"
            
            for file_path in self.storage_path.rglob(pattern):
                file_info = self._parse_filename(file_path.name)
                
                if file_info:
                    file_timestamp = file_info['timestamp']
                    
                    # Check if file might contain data in our range
                    # Note: This is approximate since files contain data over time
                    if file_timestamp >= start_timestamp:
                        if end_timestamp is None or file_timestamp <= end_timestamp + 3600:  # +1 hour buffer
                            files.append(file_path)
        
        # Sort by timestamp for chronological processing
        files.sort(key=lambda p: self._parse_filename(p.name)['timestamp'])
        
        return files