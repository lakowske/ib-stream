"""
IB-Stream v2 Protocol Message Types and Definitions.
Implements the unified message structure for both SSE and WebSocket transports.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


class V2Message:
    """Base class for v2 protocol messages."""
    
    def __init__(
        self,
        message_type: str,
        stream_id: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.type = message_type
        self.stream_id = stream_id
        self.timestamp = datetime.utcnow().isoformat() + 'Z'
        self.data = data
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to v2 protocol dictionary."""
        result = {
            "type": self.type,
            "stream_id": self.stream_id,
            "timestamp": self.timestamp,
            "data": self.data
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


class TickMessage(V2Message):
    """Market data tick message."""
    
    def __init__(
        self,
        stream_id: str,
        contract_id: int,
        tick_type: str,
        tick_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ):
        data = {
            "contract_id": contract_id,
            "tick_type": tick_type,
            **tick_data
        }
        super().__init__("tick", stream_id, data, metadata)


class ErrorMessage(V2Message):
    """Error notification message."""
    
    def __init__(
        self,
        stream_id: str,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ):
        data = {
            "code": code,
            "message": message,
            "details": details or {},
            "recoverable": recoverable
        }
        super().__init__("error", stream_id, data, metadata)


class CompleteMessage(V2Message):
    """Stream completion message."""
    
    def __init__(
        self,
        stream_id: str,
        reason: str,
        total_ticks: int,
        duration_seconds: float,
        final_sequence: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        data = {
            "reason": reason,
            "total_ticks": total_ticks,
            "duration_seconds": duration_seconds
        }
        if final_sequence is not None:
            data["final_sequence"] = final_sequence
        super().__init__("complete", stream_id, data, metadata)


class InfoMessage(V2Message):
    """Stream information/metadata message."""
    
    def __init__(
        self,
        stream_id: str,
        status: str,
        contract_info: Optional[Dict[str, Any]] = None,
        stream_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        data = {"status": status}
        if contract_info:
            data["contract_info"] = contract_info
        if stream_config:
            data["stream_config"] = stream_config
        super().__init__("info", stream_id, data, metadata)


# WebSocket-specific message types (client to server)

class SubscribeMessage:
    """WebSocket subscribe request message."""
    
    def __init__(
        self,
        message_id: str,
        contract_id: int,
        tick_types: Union[str, List[str]],
        config: Optional[Dict[str, Any]] = None
    ):
        self.type = "subscribe"
        self.id = message_id
        self.timestamp = datetime.utcnow().isoformat() + 'Z'
        
        # Normalize tick_types to list
        if isinstance(tick_types, str):
            tick_types = [tick_types]
            
        self.data = {
            "contract_id": contract_id,
            "tick_types": tick_types
        }
        if config:
            self.data["config"] = config
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "timestamp": self.timestamp,
            "data": self.data
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class UnsubscribeMessage:
    """WebSocket unsubscribe request message."""
    
    def __init__(self, message_id: str, stream_id: str):
        self.type = "unsubscribe"
        self.id = message_id
        self.timestamp = datetime.utcnow().isoformat() + 'Z'
        self.data = {"stream_id": stream_id}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "timestamp": self.timestamp,
            "data": self.data
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class SubscribedMessage(V2Message):
    """WebSocket subscription confirmation message."""
    
    def __init__(
        self,
        message_id: str,
        streams: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None
    ):
        data = {"streams": streams}
        # Use empty stream_id for subscription confirmations
        super().__init__("subscribed", "", data, metadata)
        self.id = message_id
    
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result["id"] = self.id
        # Remove stream_id for subscription messages
        result.pop("stream_id", None)
        return result


class ConnectedMessage:
    """WebSocket connected handshake message."""
    
    def __init__(self, version: str = "2.0.0"):
        self.type = "connected"
        self.timestamp = datetime.utcnow().isoformat() + 'Z'
        self.data = {
            "version": version,
            "capabilities": {
                "max_streams_per_connection": 20,
                "supported_tick_types": ["last", "all_last", "bid_ask", "mid_point"],
                "ping_interval_seconds": 30
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "data": self.data
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class PingMessage:
    """WebSocket ping message."""
    
    def __init__(self, message_id: str):
        self.type = "ping"
        self.id = message_id
        self.timestamp = datetime.utcnow().isoformat() + 'Z'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "timestamp": self.timestamp
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class PongMessage:
    """WebSocket pong response message."""
    
    def __init__(self, message_id: str, client_timestamp: Optional[str] = None):
        self.type = "pong"
        self.id = message_id
        self.timestamp = datetime.utcnow().isoformat() + 'Z'
        self.data = {
            "server_timestamp": self.timestamp
        }
        if client_timestamp:
            self.data["client_timestamp"] = client_timestamp
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "timestamp": self.timestamp,
            "data": self.data
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# Error code constants
class ErrorCode:
    CONTRACT_NOT_FOUND = "CONTRACT_NOT_FOUND"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_TICK_TYPE = "INVALID_TICK_TYPE"
    STREAM_TIMEOUT = "STREAM_TIMEOUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_MESSAGE = "INVALID_MESSAGE"


# Completion reason constants
class CompletionReason:
    LIMIT_REACHED = "limit_reached"
    TIMEOUT = "timeout"
    CLIENT_DISCONNECT = "client_disconnect"
    SERVER_SHUTDOWN = "server_shutdown"
    ERROR = "error"


# Helper functions for creating standard messages

def create_tick_message(
    stream_id: str,
    contract_id: int,
    tick_type: str,
    tick_data: Dict[str, Any]
) -> TickMessage:
    """Create a tick message with standard structure."""
    return TickMessage(stream_id, contract_id, tick_type, tick_data)


def create_error_message(
    stream_id: str,
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    recoverable: bool = True
) -> ErrorMessage:
    """Create an error message with standard structure."""
    return ErrorMessage(stream_id, code, message, details, recoverable)


def create_complete_message(
    stream_id: str,
    reason: str,
    total_ticks: int,
    duration_seconds: float,
    final_sequence: Optional[int] = None
) -> CompleteMessage:
    """Create a completion message with standard structure."""
    return CompleteMessage(stream_id, reason, total_ticks, duration_seconds, final_sequence)


def create_info_message(
    stream_id: str,
    status: str,
    contract_info: Optional[Dict[str, Any]] = None,
    stream_config: Optional[Dict[str, Any]] = None
) -> InfoMessage:
    """Create an info message with standard structure."""
    return InfoMessage(stream_id, status, contract_info, stream_config)