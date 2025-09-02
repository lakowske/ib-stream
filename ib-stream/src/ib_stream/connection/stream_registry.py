"""
Stream registry for tracking all active streams across the unified connection
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class StreamType(Enum):
    """Types of streams in the system"""
    CLIENT = "client"              # Client API requests (1000-59999)
    BACKGROUND = "background"      # Background data collection (60000-69999)


class StreamStatus(Enum):
    """Status of individual streams"""
    ACTIVE = "active"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"


@dataclass
class StreamInfo:
    """Information about a registered stream"""
    request_id: int
    stream_type: StreamType
    contract_id: int
    tick_type: str
    callback: Callable
    created_at: datetime
    status: StreamStatus = StreamStatus.ACTIVE
    last_data_at: Optional[datetime] = None
    error_count: int = 0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class RequestIDAllocator:
    """Manages request ID allocation for different stream types"""
    
    # Request ID ranges - keep existing for compatibility
    RANGES = {
        StreamType.CLIENT: (1000, 59999),
        StreamType.BACKGROUND: (60000, 69999),
    }
    
    def __init__(self):
        self._allocated: Dict[StreamType, Set[int]] = {
            StreamType.CLIENT: set(),
            StreamType.BACKGROUND: set()
        }
        self._next_id = {
            StreamType.CLIENT: self.RANGES[StreamType.CLIENT][0],
            StreamType.BACKGROUND: self.RANGES[StreamType.BACKGROUND][0]
        }
    
    def allocate(self, stream_type: StreamType) -> int:
        """Allocate next available request ID for stream type"""
        min_id, max_id = self.RANGES[stream_type]
        allocated = self._allocated[stream_type]
        
        # Find next available ID
        current_id = self._next_id[stream_type]
        
        # Search from current position
        for request_id in range(current_id, max_id + 1):
            if request_id not in allocated:
                allocated.add(request_id)
                self._next_id[stream_type] = request_id + 1
                return request_id
        
        # Search from beginning if needed
        for request_id in range(min_id, current_id):
            if request_id not in allocated:
                allocated.add(request_id)
                self._next_id[stream_type] = request_id + 1
                return request_id
        
        raise RuntimeError(f"No available request IDs for {stream_type.value} streams")
    
    def release(self, stream_type: StreamType, request_id: int):
        """Release a request ID for reuse"""
        self._allocated[stream_type].discard(request_id)
    
    def is_allocated(self, request_id: int) -> Optional[StreamType]:
        """Check if request ID is allocated and return its type"""
        for stream_type, (min_id, max_id) in self.RANGES.items():
            if min_id <= request_id <= max_id:
                if request_id in self._allocated[stream_type]:
                    return stream_type
        return None


class StreamRegistry:
    """Registry for tracking all active streams"""
    
    def __init__(self):
        self.streams: Dict[int, StreamInfo] = {}
        self.allocator = RequestIDAllocator()
        
        # Stream type indexes for quick lookup
        self._client_streams: Set[int] = set()
        self._background_streams: Set[int] = set()
    
    def register_stream(self, 
                       stream_type: StreamType,
                       contract_id: int,
                       tick_type: str,
                       callback: Callable,
                       request_id: Optional[int] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> int:
        """Register a new stream and return allocated request ID"""
        
        # Allocate request ID if not provided
        if request_id is None:
            request_id = self.allocator.allocate(stream_type)
        else:
            # Verify provided request ID is valid and available
            expected_type = self.allocator.is_allocated(request_id)
            if expected_type is not None:
                raise ValueError(f"Request ID {request_id} already allocated to {expected_type.value}")
            
            # Manually allocate the specific request ID
            min_id, max_id = self.allocator.RANGES[stream_type]
            if not (min_id <= request_id <= max_id):
                raise ValueError(f"Request ID {request_id} not in range for {stream_type.value}")
            
            self.allocator._allocated[stream_type].add(request_id)
        
        # Create stream info
        stream_info = StreamInfo(
            request_id=request_id,
            stream_type=stream_type,
            contract_id=contract_id,
            tick_type=tick_type,
            callback=callback,
            created_at=datetime.now(),
            metadata=metadata or {}
        )
        
        # Register in main registry
        self.streams[request_id] = stream_info
        
        # Add to type-specific indexes
        if stream_type == StreamType.CLIENT:
            self._client_streams.add(request_id)
        elif stream_type == StreamType.BACKGROUND:
            self._background_streams.add(request_id)
        
        logger.debug("Registered %s stream %d for contract %d (%s)", 
                    stream_type.value, request_id, contract_id, tick_type)
        
        return request_id
    
    def unregister_stream(self, request_id: int):
        """Unregister a stream and release its request ID"""
        stream_info = self.streams.pop(request_id, None)
        if stream_info is None:
            logger.warning("Attempted to unregister non-existent stream %d", request_id)
            return
        
        # Release request ID
        self.allocator.release(stream_info.stream_type, request_id)
        
        # Remove from type-specific indexes
        self._client_streams.discard(request_id)
        self._background_streams.discard(request_id)
        
        logger.debug("Unregistered %s stream %d", stream_info.stream_type.value, request_id)
    
    def get_stream(self, request_id: int) -> Optional[StreamInfo]:
        """Get stream info by request ID"""
        return self.streams.get(request_id)
    
    def get_client_streams(self) -> Dict[int, StreamInfo]:
        """Get all client streams"""
        return {req_id: self.streams[req_id] for req_id in self._client_streams}
    
    def get_background_streams(self) -> Dict[int, StreamInfo]:
        """Get all background streams"""
        return {req_id: self.streams[req_id] for req_id in self._background_streams}
    
    def get_all_streams(self) -> Dict[int, StreamInfo]:
        """Get all streams"""
        return self.streams.copy()
    
    def update_stream_status(self, request_id: int, status: StreamStatus):
        """Update stream status"""
        if request_id in self.streams:
            self.streams[request_id].status = status
            logger.debug("Updated stream %d status to %s", request_id, status.value)
    
    def mark_data_received(self, request_id: int):
        """Mark that data was received for a stream"""
        if request_id in self.streams:
            self.streams[request_id].last_data_at = datetime.now()
    
    def increment_error_count(self, request_id: int):
        """Increment error count for a stream"""
        if request_id in self.streams:
            self.streams[request_id].error_count += 1
    
    def clear_error_count(self, request_id: int):
        """Clear error count for a stream"""
        if request_id in self.streams:
            self.streams[request_id].error_count = 0
    
    def get_streams_by_contract(self, contract_id: int) -> Dict[int, StreamInfo]:
        """Get all streams for a specific contract"""
        return {
            req_id: stream_info 
            for req_id, stream_info in self.streams.items() 
            if stream_info.contract_id == contract_id
        }
    
    def get_stale_streams(self, threshold_minutes: int = 15) -> Dict[int, StreamInfo]:
        """Get streams that haven't received data recently"""
        threshold_time = datetime.now()
        # Subtract threshold_minutes from current time
        from datetime import timedelta
        threshold_time = threshold_time - timedelta(minutes=threshold_minutes)
        
        stale_streams = {}
        for req_id, stream_info in self.streams.items():
            if stream_info.last_data_at is None:
                # Stream never received data - consider stale if old enough
                if (datetime.now() - stream_info.created_at).total_seconds() > threshold_minutes * 60:
                    stale_streams[req_id] = stream_info
            elif stream_info.last_data_at < threshold_time:
                stale_streams[req_id] = stream_info
        
        return stale_streams
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        return {
            "total_streams": len(self.streams),
            "client_streams": len(self._client_streams),
            "background_streams": len(self._background_streams),
            "active_streams": len([s for s in self.streams.values() if s.status == StreamStatus.ACTIVE]),
            "failed_streams": len([s for s in self.streams.values() if s.status == StreamStatus.FAILED]),
            "request_id_usage": {
                "client_range": f"{self.allocator.RANGES[StreamType.CLIENT][0]}-{self.allocator.RANGES[StreamType.CLIENT][1]}",
                "background_range": f"{self.allocator.RANGES[StreamType.BACKGROUND][0]}-{self.allocator.RANGES[StreamType.BACKGROUND][1]}",
                "client_allocated": len(self.allocator._allocated[StreamType.CLIENT]),
                "background_allocated": len(self.allocator._allocated[StreamType.BACKGROUND])
            }
        }