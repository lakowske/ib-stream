"""
Protobuf storage implementation for IB Stream.

Provides efficient protobuf storage with length-prefixed messages
and hourly file rotation.
"""

import asyncio
import struct
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, BinaryIO
from pathlib import Path

# Import protobuf generated classes (would be generated from tick_stream.proto)
try:
    from .proto import tick_stream_pb2
except ImportError:
    # For now, create a mock implementation until protobuf files are generated
    logging.warning("Protobuf classes not available, using mock implementation")
    tick_stream_pb2 = None

logger = logging.getLogger(__name__)


class ProtobufStorage:
    """
    Protobuf storage with length-prefixed messages and hourly partitioning.
    
    Stores stream messages as binary protobuf with length prefixes for
    efficient serialization and fast reading.
    """
    
    def __init__(self, storage_path: Path):
        """
        Initialize protobuf storage.
        
        Args:
            storage_path: Base path for protobuf storage files
        """
        self.storage_path = storage_path
        self.file_handles: Dict[str, BinaryIO] = {}
        self.current_files: Dict[str, Path] = {}
        self._rotation_lock = asyncio.Lock()
        
        # Check if protobuf classes are available
        self.protobuf_available = tick_stream_pb2 is not None
        
    async def start(self):
        """Initialize storage system."""
        if not self.protobuf_available:
            logger.warning("Protobuf storage started without generated protobuf classes")
            
        # Create storage directory
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Protobuf storage initialized at {self.storage_path}")
        
    async def stop(self):
        """Stop storage and close all file handles."""
        # Close all open file handles
        for handle in self.file_handles.values():
            if not handle.closed:
                handle.close()
        
        self.file_handles.clear()
        self.current_files.clear()
        logger.info("Protobuf storage stopped")
        
    async def write_messages(self, stream_id: str, messages: List[Dict[str, Any]]):
        """
        Write messages to protobuf storage.
        
        Args:
            stream_id: Stream identifier for file organization
            messages: List of messages to write
        """
        if not messages:
            return
            
        if not self.protobuf_available:
            logger.debug("Skipping protobuf write - protobuf classes not available")
            return
            
        # Get file path for current hour
        file_path = await self._get_current_file(stream_id)
        
        # Convert messages to protobuf and write
        try:
            # Open file in append mode
            with open(file_path, 'ab') as f:
                for message in messages:
                    # Convert JSON message to protobuf
                    proto_message = self._json_to_protobuf(message)
                    if proto_message:
                        # Serialize message
                        serialized = proto_message.SerializeToString()
                        
                        # Write length prefix followed by message
                        length = len(serialized)
                        f.write(struct.pack('<I', length))  # 4-byte little-endian length
                        f.write(serialized)
                        
            logger.debug(f"Wrote {len(messages)} protobuf messages to {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to write protobuf messages to {file_path}: {e}")
            raise
            
    def _json_to_protobuf(self, message: Dict[str, Any]) -> Optional[Any]:
        """
        Convert JSON message to protobuf message.
        
        Args:
            message: JSON message in v2 protocol format
            
        Returns:
            Protobuf StreamMessage or None if conversion fails
        """
        if not self.protobuf_available:
            return None
            
        try:
            # Create StreamMessage
            stream_msg = tick_stream_pb2.StreamMessage()
            
            # Set basic fields
            stream_msg.type = message.get('type', '')
            stream_msg.stream_id = message.get('stream_id', '')
            
            # Set timestamp
            timestamp_str = message.get('timestamp', '')
            if timestamp_str:
                # Parse ISO timestamp
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                stream_msg.timestamp.FromDatetime(dt)
                
            # Set message data based on type
            msg_type = message.get('type')
            data = message.get('data', {})
            
            if msg_type == 'tick':
                self._set_tick_data(stream_msg.tick_data, data)
            elif msg_type == 'error':
                self._set_error_data(stream_msg.error_data, data)
            elif msg_type == 'complete':
                self._set_complete_data(stream_msg.complete_data, data)
            elif msg_type == 'info':
                self._set_info_data(stream_msg.info_data, data)
                
            # Set metadata
            metadata = message.get('metadata', {})
            for key, value in metadata.items():
                stream_msg.metadata[key] = str(value)
                
            return stream_msg
            
        except Exception as e:
            logger.warning(f"Failed to convert message to protobuf: {e}")
            return None
            
    def _set_tick_data(self, tick_data, json_data: Dict[str, Any]):
        """Set tick data fields in protobuf message."""
        tick_data.contract_id = json_data.get('contract_id', 0)
        tick_data.tick_type = json_data.get('tick_type', '')
        
        # Set optional price fields
        if 'price' in json_data:
            tick_data.price = json_data['price']
        if 'size' in json_data:
            tick_data.size = json_data['size']
        if 'bid_price' in json_data:
            tick_data.bid_price = json_data['bid_price']
        if 'bid_size' in json_data:
            tick_data.bid_size = json_data['bid_size']
        if 'ask_price' in json_data:
            tick_data.ask_price = json_data['ask_price']
        if 'ask_size' in json_data:
            tick_data.ask_size = json_data['ask_size']
        if 'mid_price' in json_data:
            tick_data.mid_price = json_data['mid_price']
            
        # Set additional fields
        if 'exchange' in json_data:
            tick_data.exchange = json_data['exchange']
        if 'conditions' in json_data:
            tick_data.conditions.extend(json_data['conditions'])
        if 'sequence' in json_data:
            tick_data.sequence = json_data['sequence']
            
        # Set boolean attributes
        if 'past_limit' in json_data:
            tick_data.past_limit = json_data['past_limit']
        if 'unreported' in json_data:
            tick_data.unreported = json_data['unreported']
        if 'bid_past_low' in json_data:
            tick_data.bid_past_low = json_data['bid_past_low']
        if 'ask_past_high' in json_data:
            tick_data.ask_past_high = json_data['ask_past_high']
            
    def _set_error_data(self, error_data, json_data: Dict[str, Any]):
        """Set error data fields in protobuf message."""
        error_data.code = json_data.get('code', '')
        error_data.message = json_data.get('message', '')
        error_data.recoverable = json_data.get('recoverable', False)
        
        # Set details
        details = json_data.get('details', {})
        for key, value in details.items():
            error_data.details[key] = str(value)
            
    def _set_complete_data(self, complete_data, json_data: Dict[str, Any]):
        """Set completion data fields in protobuf message."""
        complete_data.reason = json_data.get('reason', '')
        complete_data.total_ticks = json_data.get('total_ticks', 0)
        complete_data.duration_seconds = json_data.get('duration_seconds', 0.0)
        
        if 'final_sequence' in json_data:
            complete_data.final_sequence = json_data['final_sequence']
            
    def _set_info_data(self, info_data, json_data: Dict[str, Any]):
        """Set info data fields in protobuf message."""
        info_data.status = json_data.get('status', '')
        
        # Set contract info if present
        contract_info = json_data.get('contract_info')
        if contract_info:
            info_data.contract_info.symbol = contract_info.get('symbol', '')
            info_data.contract_info.exchange = contract_info.get('exchange', '')
            info_data.contract_info.currency = contract_info.get('currency', '')
            info_data.contract_info.contract_type = contract_info.get('contract_type', '')
            
        # Set stream config if present
        stream_config = json_data.get('stream_config')
        if stream_config:
            info_data.stream_config.tick_type = stream_config.get('tick_type', '')
            if 'limit' in stream_config:
                info_data.stream_config.limit = stream_config['limit']
            if 'timeout_seconds' in stream_config:
                info_data.stream_config.timeout_seconds = stream_config['timeout_seconds']
            if 'include_extended' in stream_config:
                info_data.stream_config.include_extended = stream_config['include_extended']
                
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
        # Format: {storage_path}/YYYY/MM/DD/HH/stream_id.pb
        date_path = now.strftime('%Y/%m/%d/%H')
        file_dir = self.storage_path / date_path
        file_path = file_dir / f"{stream_id}.pb"
        
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
                    
                    logger.debug(f"Rotated to new protobuf file: {file_path}")
                    
        return file_path
        
    async def query_range(
        self,
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Query messages from protobuf storage within time range.
        
        Args:
            contract_id: Contract ID to filter
            tick_types: List of tick types to include
            start_time: Start of time range
            end_time: End of time range (None for present)
            
        Returns:
            List of messages in the time range (converted to JSON format)
        """
        if not self.protobuf_available:
            logger.warning("Cannot query protobuf storage - protobuf classes not available")
            return []
            
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
            
            # Add all protobuf files in this hour directory
            if hour_dir.exists():
                for file_path in hour_dir.glob('*.pb'):
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
        Read messages from a single protobuf file within the time range.
        
        Args:
            file_path: Path to protobuf file
            contract_id: Contract ID to filter
            tick_types: List of tick types to include
            start_time: Start of time range
            end_time: End of time range
            
        Returns:
            List of messages from the file (converted to JSON format)
        """
        messages = []
        
        try:
            with open(file_path, 'rb') as f:
                while True:
                    # Read length prefix
                    length_data = f.read(4)
                    if len(length_data) < 4:
                        break  # End of file
                        
                    length = struct.unpack('<I', length_data)[0]
                    
                    # Read message data
                    message_data = f.read(length)
                    if len(message_data) < length:
                        logger.warning(f"Truncated message in {file_path}")
                        break
                        
                    # Parse protobuf message
                    stream_msg = tick_stream_pb2.StreamMessage()
                    stream_msg.ParseFromString(message_data)
                    
                    # Convert to JSON format
                    json_message = self._protobuf_to_json(stream_msg)
                    
                    if json_message and self._message_matches_filter(json_message, contract_id, tick_types):
                        # Check timestamp range
                        msg_time = datetime.fromisoformat(
                            json_message['timestamp'].replace('Z', '+00:00')
                        )
                        
                        if start_time <= msg_time <= end_time:
                            messages.append(json_message)
                            
        except Exception as e:
            logger.error(f"Failed to read protobuf file {file_path}: {e}")
            
        return messages
        
    def _protobuf_to_json(self, stream_msg) -> Optional[Dict[str, Any]]:
        """
        Convert protobuf StreamMessage to JSON format.
        
        Args:
            stream_msg: Protobuf StreamMessage
            
        Returns:
            JSON dictionary or None if conversion fails
        """
        try:
            message = {
                'type': stream_msg.type,
                'stream_id': stream_msg.stream_id,
                'timestamp': stream_msg.timestamp.ToDatetime().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            }
            
            # Convert data based on message type
            if stream_msg.HasField('tick_data'):
                message['data'] = self._tick_data_to_json(stream_msg.tick_data)
            elif stream_msg.HasField('error_data'):
                message['data'] = self._error_data_to_json(stream_msg.error_data)
            elif stream_msg.HasField('complete_data'):
                message['data'] = self._complete_data_to_json(stream_msg.complete_data)
            elif stream_msg.HasField('info_data'):
                message['data'] = self._info_data_to_json(stream_msg.info_data)
                
            # Convert metadata
            if stream_msg.metadata:
                message['metadata'] = dict(stream_msg.metadata)
                
            return message
            
        except Exception as e:
            logger.warning(f"Failed to convert protobuf to JSON: {e}")
            return None
            
    def _tick_data_to_json(self, tick_data) -> Dict[str, Any]:
        """Convert protobuf TickData to JSON."""
        data = {
            'contract_id': tick_data.contract_id,
            'tick_type': tick_data.tick_type,
        }
        
        # Add optional fields if present
        if tick_data.HasField('price'):
            data['price'] = tick_data.price
        if tick_data.HasField('size'):
            data['size'] = tick_data.size
        if tick_data.HasField('bid_price'):
            data['bid_price'] = tick_data.bid_price
        if tick_data.HasField('bid_size'):
            data['bid_size'] = tick_data.bid_size
        if tick_data.HasField('ask_price'):
            data['ask_price'] = tick_data.ask_price
        if tick_data.HasField('ask_size'):
            data['ask_size'] = tick_data.ask_size
        if tick_data.HasField('mid_price'):
            data['mid_price'] = tick_data.mid_price
        if tick_data.HasField('exchange'):
            data['exchange'] = tick_data.exchange
        if tick_data.conditions:
            data['conditions'] = list(tick_data.conditions)
        if tick_data.HasField('sequence'):
            data['sequence'] = tick_data.sequence
            
        return data
        
    def _error_data_to_json(self, error_data) -> Dict[str, Any]:
        """Convert protobuf ErrorData to JSON."""
        return {
            'code': error_data.code,
            'message': error_data.message,
            'recoverable': error_data.recoverable,
            'details': dict(error_data.details) if error_data.details else {}
        }
        
    def _complete_data_to_json(self, complete_data) -> Dict[str, Any]:
        """Convert protobuf CompleteData to JSON."""
        data = {
            'reason': complete_data.reason,
            'total_ticks': complete_data.total_ticks,
            'duration_seconds': complete_data.duration_seconds,
        }
        
        if complete_data.HasField('final_sequence'):
            data['final_sequence'] = complete_data.final_sequence
            
        return data
        
    def _info_data_to_json(self, info_data) -> Dict[str, Any]:
        """Convert protobuf InfoData to JSON."""
        data = {'status': info_data.status}
        
        if info_data.HasField('contract_info'):
            data['contract_info'] = {
                'symbol': info_data.contract_info.symbol,
                'exchange': info_data.contract_info.exchange,
                'currency': info_data.contract_info.currency,
                'contract_type': info_data.contract_info.contract_type,
            }
            
        if info_data.HasField('stream_config'):
            config = {'tick_type': info_data.stream_config.tick_type}
            
            if info_data.stream_config.HasField('limit'):
                config['limit'] = info_data.stream_config.limit
            if info_data.stream_config.HasField('timeout_seconds'):
                config['timeout_seconds'] = info_data.stream_config.timeout_seconds
            if info_data.stream_config.HasField('include_extended'):
                config['include_extended'] = info_data.stream_config.include_extended
                
            data['stream_config'] = config
            
        return data
        
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
        """Get statistics about protobuf storage."""
        total_files = 0
        total_size = 0
        
        # Walk through storage directory
        if self.storage_path.exists():
            for file_path in self.storage_path.rglob('*.pb'):
                total_files += 1
                try:
                    total_size += file_path.stat().st_size
                except OSError:
                    pass
                    
        return {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / 1024 / 1024, 2),
            'active_streams': len(self.current_files),
            'protobuf_available': self.protobuf_available
        }