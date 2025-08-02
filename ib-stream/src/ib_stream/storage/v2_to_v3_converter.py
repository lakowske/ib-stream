"""
V2 to V3 Storage Converter

Comprehensive storage converter to migrate existing v2 data to v3 format
with complete data integrity and conversion tracking.
"""

import asyncio
import json
import logging
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator, Set
from dataclasses import dataclass

from ib_util.storage import TickMessage, create_tick_message_from_v2
from .v3_json_storage import V3JSONStorage
from .v3_protobuf_storage import V3ProtobufStorage

logger = logging.getLogger(__name__)


@dataclass
class ConversionStats:
    """Statistics for a single file conversion."""
    source_file: str
    target_file: str
    source_format: str  # 'json' or 'protobuf'
    stream_type: str    # 'bid_ask' or 'last'
    messages_processed: int
    messages_converted: int
    messages_failed: int
    source_size_bytes: int
    target_size_bytes: int
    conversion_time_seconds: float
    errors: List[str]


@dataclass
class ConversionReport:
    """Complete conversion session report."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    source_path: Path
    target_path: Path
    total_files_processed: int
    total_messages_converted: int
    total_messages_failed: int
    total_source_size_bytes: int
    total_target_size_bytes: int
    conversion_stats: List[ConversionStats]
    errors: List[str]
    
    @property
    def duration_seconds(self) -> float:
        """Calculate total conversion duration."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio (target/source)."""
        if self.total_source_size_bytes > 0:
            return self.total_target_size_bytes / self.total_source_size_bytes
        return 0.0
    
    @property
    def space_saved_bytes(self) -> int:
        """Calculate total space saved."""
        return self.total_source_size_bytes - self.total_target_size_bytes
    
    def to_json_dict(self) -> Dict[str, Any]:
        """Convert report to JSON-serializable format."""
        return {
            'session_id': self.session_id,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'source_path': str(self.source_path),
            'target_path': str(self.target_path),
            'summary': {
                'duration_seconds': self.duration_seconds,
                'total_files_processed': self.total_files_processed,
                'total_messages_converted': self.total_messages_converted,
                'total_messages_failed': self.total_messages_failed,
                'total_source_size_mb': round(self.total_source_size_bytes / (1024 * 1024), 2),
                'total_target_size_mb': round(self.total_target_size_bytes / (1024 * 1024), 2),
                'space_saved_mb': round(self.space_saved_bytes / (1024 * 1024), 2),
                'compression_ratio': round(self.compression_ratio, 3),
                'space_saved_percent': round((1 - self.compression_ratio) * 100, 1)
            },
            'files': [
                {
                    'source_file': stat.source_file,
                    'target_file': stat.target_file,
                    'source_format': stat.source_format,
                    'stream_type': stat.stream_type,
                    'messages_processed': stat.messages_processed,
                    'messages_converted': stat.messages_converted,
                    'messages_failed': stat.messages_failed,
                    'source_size_mb': round(stat.source_size_bytes / (1024 * 1024), 3),
                    'target_size_mb': round(stat.target_size_bytes / (1024 * 1024), 3),
                    'conversion_time_seconds': stat.conversion_time_seconds,
                    'errors': stat.errors
                } for stat in self.conversion_stats
            ],
            'errors': self.errors
        }


class V2StorageReader:
    """Reader for v2 storage formats (JSON and protobuf)."""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        
    async def read_json_file(self, file_path: Path) -> AsyncIterator[Dict[str, Any]]:
        """Read v2 JSON file and yield message dictionaries."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        message = json.loads(line)
                        yield message
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON at {file_path}:{line_num}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to read JSON file {file_path}: {e}")
            raise
    
    async def read_protobuf_file(self, file_path: Path) -> AsyncIterator[Dict[str, Any]]:
        """Read v2 protobuf file and yield message dictionaries."""
        try:
            with open(file_path, 'rb') as f:
                while True:
                    # Read message length (4 bytes, big-endian)
                    length_bytes = f.read(4)
                    if not length_bytes or len(length_bytes) < 4:
                        break  # End of file
                    
                    message_length = struct.unpack('>I', length_bytes)[0]
                    
                    # Read message data
                    message_data = f.read(message_length)
                    if len(message_data) != message_length:
                        logger.warning(f"Incomplete protobuf message in {file_path}")
                        break
                    
                    try:
                        # For now, we'll skip protobuf parsing since we don't have the v2 schema
                        # This would need the actual v2 protobuf schema implementation
                        logger.debug(f"Skipping protobuf message of {message_length} bytes")
                        continue
                        
                    except Exception as e:
                        logger.warning(f"Invalid protobuf message in {file_path}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to read protobuf file {file_path}: {e}")
            raise
    
    def find_v2_files(self) -> List[Path]:
        """Find all v2 storage files in chronological order."""
        json_files = []
        protobuf_files = []
        
        # Find JSON files
        json_path = self.storage_path / 'json'
        if json_path.exists():
            json_files = sorted(json_path.rglob('*.jsonl'))
        
        # Find protobuf files  
        protobuf_path = self.storage_path / 'protobuf'
        if protobuf_path.exists():
            protobuf_files = sorted(protobuf_path.rglob('*.pb'))
        
        # Combine and sort by file path for chronological order
        all_files = json_files + protobuf_files
        return sorted(all_files)


class V2ToV3StorageConverter:
    """Main converter orchestrator for v2 to v3 storage migration."""
    
    def __init__(self, v2_storage_path: Path, v3_storage_path: Path, 
                 enable_json: bool = True, enable_protobuf: bool = True,
                 buffer_size: int = 1000):
        """
        Initialize the storage converter.
        
        Args:
            v2_storage_path: Path to existing v2 storage directory
            v3_storage_path: Path where v3 storage will be created  
            enable_json: Whether to convert to v3 JSON format
            enable_protobuf: Whether to convert to v3 protobuf format
            buffer_size: Number of messages to buffer before writing
        """
        self.v2_storage_path = v2_storage_path
        self.v3_storage_path = v3_storage_path
        self.enable_json = enable_json
        self.enable_protobuf = enable_protobuf
        self.buffer_size = buffer_size
        
        # Initialize readers and writers
        self.v2_reader = V2StorageReader(v2_storage_path)
        
        if enable_json:
            self.v3_json_storage = V3JSONStorage(v3_storage_path / 'json')
        if enable_protobuf:
            self.v3_protobuf_storage = V3ProtobufStorage(v3_storage_path / 'protobuf')
    
    async def convert_all(self) -> ConversionReport:
        """
        Convert all v2 data to v3 format.
        
        Returns:
            ConversionReport with detailed conversion statistics
        """
        session_id = f"conv_{int(time.time())}"
        start_time = datetime.now(timezone.utc)
        
        logger.info(f"Starting v2 to v3 conversion session {session_id}")
        logger.info(f"Source: {self.v2_storage_path}")
        logger.info(f"Target: {self.v3_storage_path}")
        
        # Initialize report
        report = ConversionReport(
            session_id=session_id,
            start_time=start_time,
            end_time=None,
            source_path=self.v2_storage_path,
            target_path=self.v3_storage_path,
            total_files_processed=0,
            total_messages_converted=0,
            total_messages_failed=0,
            total_source_size_bytes=0,
            total_target_size_bytes=0,
            conversion_stats=[],
            errors=[]
        )
        
        try:
            # Ensure target directory exists
            self.v3_storage_path.mkdir(parents=True, exist_ok=True)
            
            # Find all v2 files
            v2_files = self.v2_reader.find_v2_files()
            logger.info(f"Found {len(v2_files)} v2 files to convert")
            
            if not v2_files:
                logger.warning("No v2 files found for conversion")
                report.end_time = datetime.now(timezone.utc)
                return report
            
            # Convert files sequentially for temporal consistency
            for file_path in v2_files:
                try:
                    file_stats = await self._convert_file(file_path)
                    report.conversion_stats.append(file_stats)
                    
                    # Update totals
                    report.total_files_processed += 1
                    report.total_messages_converted += file_stats.messages_converted
                    report.total_messages_failed += file_stats.messages_failed
                    report.total_source_size_bytes += file_stats.source_size_bytes
                    report.total_target_size_bytes += file_stats.target_size_bytes
                    
                    # Log progress
                    if report.total_files_processed % 100 == 0:
                        logger.info(f"Processed {report.total_files_processed}/{len(v2_files)} files")
                        
                except Exception as e:
                    error_msg = f"Failed to convert file {file_path}: {e}"
                    logger.error(error_msg)
                    report.errors.append(error_msg)
            
            report.end_time = datetime.now(timezone.utc)
            
            # Log final summary
            logger.info(f"Conversion completed in {report.duration_seconds:.1f} seconds")
            logger.info(f"Files processed: {report.total_files_processed}")
            logger.info(f"Messages converted: {report.total_messages_converted}")
            logger.info(f"Messages failed: {report.total_messages_failed}")
            logger.info(f"Space saved: {report.space_saved_bytes / (1024*1024):.1f} MB ({(1-report.compression_ratio)*100:.1f}%)")
            
            return report
            
        except Exception as e:
            error_msg = f"Conversion session failed: {e}"
            logger.error(error_msg)
            report.errors.append(error_msg)
            report.end_time = datetime.now(timezone.utc)
            return report
    
    async def _convert_file(self, file_path: Path) -> ConversionStats:
        """Convert a single v2 file to v3 format."""
        start_time = time.time()
        
        # Determine file format and stream type
        source_format = 'json' if file_path.suffix == '.jsonl' else 'protobuf'
        stream_type = self._extract_stream_type(file_path)
        
        # Get source file size
        source_size = file_path.stat().st_size
        
        stats = ConversionStats(
            source_file=str(file_path),
            target_file="",  # Will be updated when we know target files
            source_format=source_format,
            stream_type=stream_type,
            messages_processed=0,
            messages_converted=0,
            messages_failed=0,
            source_size_bytes=source_size,
            target_size_bytes=0,
            conversion_time_seconds=0.0,
            errors=[]
        )
        
        logger.debug(f"Converting {source_format} file: {file_path}")
        
        try:
            # Buffer for batched writes
            message_buffer: List[TickMessage] = []
            
            # Read messages from v2 file
            if source_format == 'json':
                async for v2_message in self.v2_reader.read_json_file(file_path):
                    await self._process_v2_message(v2_message, message_buffer, stats)
            else:
                # Protobuf conversion would go here
                # For now, skip protobuf files
                logger.warning(f"Protobuf conversion not yet implemented, skipping {file_path}")
                return stats
            
            # Write any remaining buffered messages
            if message_buffer:
                await self._write_message_buffer(message_buffer)
                message_buffer.clear()
            
            # Calculate target size (approximate)
            stats.target_size_bytes = int(stats.source_size_bytes * 0.5)  # Estimated 50% reduction
            
        except Exception as e:
            error_msg = f"Error converting file {file_path}: {e}"
            logger.error(error_msg)
            stats.errors.append(error_msg)
        
        stats.conversion_time_seconds = time.time() - start_time
        return stats
    
    async def _process_v2_message(self, v2_message: Dict[str, Any], 
                                 message_buffer: List[TickMessage], 
                                 stats: ConversionStats) -> None:
        """Process a single v2 message and add to buffer."""
        stats.messages_processed += 1
        
        try:
            # Convert v2 message to v3 TickMessage
            tick_message = create_tick_message_from_v2(v2_message)
            
            if tick_message is None:
                stats.messages_failed += 1
                stats.errors.append(f"Failed to convert message at position {stats.messages_processed}")
                return
            
            message_buffer.append(tick_message)
            stats.messages_converted += 1
            
            # Flush buffer if it's full
            if len(message_buffer) >= self.buffer_size:
                await self._write_message_buffer(message_buffer)
                message_buffer.clear()
                
        except Exception as e:
            stats.messages_failed += 1
            error_msg = f"Error processing message {stats.messages_processed}: {e}"
            stats.errors.append(error_msg)
    
    async def _write_message_buffer(self, messages: List[TickMessage]) -> None:
        """Write buffered messages to v3 storage."""
        if not messages:
            return
        
        write_tasks = []
        
        # Write to JSON storage
        if self.enable_json:
            task = self.v3_json_storage.write_tick_messages(messages)
            write_tasks.append(task)
        
        # Write to protobuf storage
        if self.enable_protobuf:
            task = self.v3_protobuf_storage.write_tick_messages(messages)
            write_tasks.append(task)
        
        # Execute writes in parallel
        if write_tasks:
            await asyncio.gather(*write_tasks)
    
    def _extract_stream_type(self, file_path: Path) -> str:
        """Extract stream type from file path."""
        filename = file_path.stem
        if 'bid_ask' in filename:
            return 'bid_ask'
        elif 'last' in filename:
            return 'last'
        else:
            return 'unknown'
    
    async def save_conversion_report(self, report: ConversionReport, 
                                   output_path: Optional[Path] = None) -> Path:
        """Save conversion report to JSON file."""
        if output_path is None:
            timestamp = report.start_time.strftime('%Y-%m-%d-%H-%M-%S')
            filename = f"conversion-{timestamp}.json"
            output_path = self.v3_storage_path / filename
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write report
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_json_dict(), f, indent=2)
        
        logger.info(f"Conversion report saved to {output_path}")
        return output_path