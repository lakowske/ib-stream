"""
V3 Protobuf storage backend with optimized binary format.

This storage engine writes TickMessage objects to binary protobuf files using
the optimized schema, achieving 40%+ storage reduction compared to v2.
"""

import asyncio
import logging
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator

from ib_util.storage import TickMessage, V3StorageBase
from .proto.tick_message_v3_pb2 import TickMessage as ProtoTickMessage

logger = logging.getLogger(__name__)


class V3ProtobufStorage(V3StorageBase):
    """
    V3 Protobuf storage engine with optimized binary format.
    
    Features:
    - Direct TickMessage to optimized protobuf serialization
    - Optional fields reduce binary size by omitting None/False values
    - Length-prefixed messages for efficient streaming reads
    - File organization: {contract_id}_{tick_type}_{timestamp}.pb
    """
    
    def __init__(self, storage_path: Path, enable_compression: bool = False):
        """
        Initialize v3 Protobuf storage.
        
        Args:
            storage_path: Base path for protobuf storage files
            enable_compression: Whether to enable compression (future feature)
        """
        super().__init__(storage_path, enable_compression)
        
    def _get_file_extension(self) -> str:
        """Get the file extension for protobuf files."""
        return 'pb'
    
    async def write_tick_message(self, tick_message: TickMessage) -> None:
        """
        Write a single tick message to storage.
        
        Args:
            tick_message: TickMessage to store
        """
        await self.write_tick_messages([tick_message])
    
    async def write_tick_messages(self, tick_messages: List[TickMessage]) -> None:
        """
        Write multiple tick messages to storage efficiently.
        
        Groups messages by file and writes them in batches for optimal I/O performance.
        
        Args:
            tick_messages: List of TickMessage objects to store
        """
        if not tick_messages:
            return
            
        # Group messages by target file
        file_groups: Dict[Path, List[TickMessage]] = {}
        
        for tick_message in tick_messages:
            file_path = self.get_file_path(
                tick_message.cid, 
                tick_message.tt, 
                tick_message.ts
            )
            
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(tick_message)
        
        # Write each group to its respective file
        write_tasks = []
        for file_path, messages in file_groups.items():
            task = self._write_messages_to_file(file_path, messages)
            write_tasks.append(task)
        
        # Execute all writes in parallel
        if write_tasks:
            await asyncio.gather(*write_tasks)
    
    async def _write_messages_to_file(self, file_path: Path, messages: List[TickMessage]) -> None:
        """
        Write messages to a protobuf file with length prefixes.
        
        Each message is prefixed with its length (4 bytes, big-endian) for
        efficient streaming reads.
        
        Args:
            file_path: Target file path
            messages: List of messages to write
        """
        lock = self._get_file_lock(file_path)
        
        async with lock:
            try:
                # Ensure directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Convert messages to protobuf binary format
                binary_data = []
                
                for message in messages:
                    proto_message = self._tick_message_to_proto(message)
                    serialized = proto_message.SerializeToString()
                    
                    # Length-prefix the message (4 bytes, big-endian)
                    length_prefix = struct.pack('>I', len(serialized))
                    binary_data.append(length_prefix + serialized)
                
                # Append to file
                with open(file_path, 'ab') as f:
                    for data in binary_data:
                        f.write(data)
                        
                logger.debug(f"Wrote {len(messages)} protobuf messages to {file_path}")
                
            except Exception as e:
                logger.error(f"Failed to write protobuf messages to {file_path}: {e}")
                raise
    
    def _tick_message_to_proto(self, tick_message: TickMessage) -> ProtoTickMessage:
        """
        Convert TickMessage to protobuf format.
        
        Only sets fields that have meaningful values to minimize binary size.
        
        Args:
            tick_message: TickMessage to convert
            
        Returns:
            ProtoTickMessage ready for serialization
        """
        proto = ProtoTickMessage()
        
        # Core fields (always present)
        proto.ts = tick_message.ts
        proto.st = tick_message.st
        proto.cid = tick_message.cid
        proto.tt = tick_message.tt
        proto.rid = tick_message.rid
        
        # Optional price fields (only set if not None)
        if tick_message.p is not None:
            proto.p = tick_message.p
        if tick_message.s is not None:
            proto.s = tick_message.s
        if tick_message.bp is not None:
            proto.bp = tick_message.bp
        if tick_message.bs is not None:
            proto.bs = tick_message.bs
        if tick_message.ap is not None:
            proto.ap = tick_message.ap
        if tick_message.as_ is not None:
            setattr(proto, 'as', tick_message.as_)
        if tick_message.mp is not None:
            proto.mp = tick_message.mp
        
        # Optional boolean flags (only set if True)
        if tick_message.bpl:
            proto.bpl = True
        if tick_message.aph:
            proto.aph = True
        if tick_message.upt:
            proto.upt = True
        
        return proto
    
    def _proto_to_tick_message(self, proto: ProtoTickMessage) -> TickMessage:
        """
        Convert protobuf message to TickMessage.
        
        Args:
            proto: ProtoTickMessage from file
            
        Returns:
            TickMessage object
        """
        return TickMessage(
            ts=proto.ts,
            st=proto.st,
            cid=proto.cid,
            tt=proto.tt,
            rid=proto.rid,
            p=proto.p if proto.HasField('p') else None,
            s=proto.s if proto.HasField('s') else None,
            bp=proto.bp if proto.HasField('bp') else None,
            bs=proto.bs if proto.HasField('bs') else None,
            ap=proto.ap if proto.HasField('ap') else None,
            as_=getattr(proto, 'as') if proto.HasField('as') else None,
            mp=proto.mp if proto.HasField('mp') else None,
            bpl=proto.bpl if proto.HasField('bpl') else None,
            aph=proto.aph if proto.HasField('aph') else None,
            upt=proto.upt if proto.HasField('upt') else None
        )
    
    async def query_range(
        self,
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[TickMessage]:
        """
        Query tick messages in a time range from protobuf files.
        
        Args:
            contract_id: Contract ID to query
            tick_types: List of tick types to include
            start_time: Start of time range (inclusive)
            end_time: End of time range (exclusive). None for open-ended.
            limit: Maximum number of messages to return
            
        Yields:
            TickMessage objects in chronological order
        """
        # Find relevant files
        relevant_files = self._find_files_in_range(contract_id, tick_types, start_time, end_time)
        
        if not relevant_files:
            logger.debug(f"No protobuf files found for contract {contract_id}, tick_types {tick_types}")
            return
        
        logger.debug(f"Found {len(relevant_files)} protobuf files to search")
        
        # Convert time range to microseconds for filtering
        start_timestamp_us = int(start_time.timestamp() * 1_000_000)
        end_timestamp_us = int(end_time.timestamp() * 1_000_000) if end_time else None
        
        message_count = 0
        
        # Process files in chronological order
        for file_path in relevant_files:
            try:
                async for message in self._read_messages_from_file(file_path):
                    # Filter by time range
                    if message.ts < start_timestamp_us:
                        continue
                    if end_timestamp_us and message.ts >= end_timestamp_us:
                        continue
                    
                    # Filter by contract and tick type
                    if message.cid != contract_id or message.tt not in tick_types:
                        continue
                    
                    yield message
                    message_count += 1
                    
                    # Check limit
                    if limit and message_count >= limit:
                        logger.debug(f"Reached limit of {limit} messages")
                        return
                        
            except Exception as e:
                logger.warning(f"Error reading protobuf file {file_path}: {e}")
                continue
        
        logger.debug(f"Protobuf query returned {message_count} messages")
    
    async def _read_messages_from_file(self, file_path: Path) -> AsyncIterator[TickMessage]:
        """
        Read all TickMessage objects from a protobuf file.
        
        Reads length-prefixed messages efficiently.
        
        Args:
            file_path: Path to the protobuf file
            
        Yields:
            TickMessage objects from the file
        """
        if not file_path.exists():
            return
            
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
                        logger.warning(f"Incomplete message in {file_path}: expected {message_length} bytes, got {len(message_data)}")
                        break
                    
                    try:
                        # Parse protobuf message
                        proto_message = ProtoTickMessage()
                        proto_message.ParseFromString(message_data)
                        
                        # Convert to TickMessage
                        tick_message = self._proto_to_tick_message(proto_message)
                        yield tick_message
                        
                    except Exception as e:
                        logger.warning(f"Invalid protobuf message in {file_path}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to read protobuf file {file_path}: {e}")
            raise
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get detailed storage statistics for v3 protobuf storage.
        
        Returns:
            Dictionary with storage metrics including size comparison estimates
        """
        stats = await super().get_storage_stats()
        
        # Add protobuf-specific stats
        stats.update({
            'format': 'v3_protobuf_optimized',
            'binary_format': True,
            'length_prefixed': True
        })
        
        # Estimate storage savings compared to v2
        if stats['total_size_bytes'] > 0:
            # Rough estimate: v3 protobuf is ~40% smaller than v2 protobuf
            estimated_v2_size = stats['total_size_bytes'] * 1.67  # 1/0.6 
            savings_bytes = estimated_v2_size - stats['total_size_bytes']
            savings_percent = (savings_bytes / estimated_v2_size) * 100
            
            stats.update({
                'estimated_v2_size_mb': round(estimated_v2_size / (1024 * 1024), 2),
                'estimated_savings_mb': round(savings_bytes / (1024 * 1024), 2),
                'estimated_savings_percent': round(savings_percent, 1)
            })
        
        return stats
    
    async def verify_file_integrity(self, file_path: Path) -> Dict[str, Any]:
        """
        Verify the integrity of a protobuf file.
        
        Args:
            file_path: Path to the file to verify
            
        Returns:
            Dictionary with verification results
        """
        results = {
            'file_path': str(file_path),
            'valid': True,
            'total_messages': 0,
            'corrupt_messages': 0,
            'file_size': 0,
            'errors': []
        }
        
        if not file_path.exists():
            results['valid'] = False
            results['errors'].append('File does not exist')
            return results
        
        results['file_size'] = file_path.stat().st_size
        
        try:
            async for message in self._read_messages_from_file(file_path):
                results['total_messages'] += 1
                
                # Basic validation
                if not message.cid or not message.tt or not message.ts:
                    results['corrupt_messages'] += 1
                    results['errors'].append(f'Invalid message at position {results["total_messages"]}')
                    
        except Exception as e:
            results['valid'] = False
            results['errors'].append(f'Read error: {str(e)}')
        
        if results['corrupt_messages'] > 0:
            results['valid'] = False
        
        logger.debug(f"Verified {file_path}: {results}")
        return results