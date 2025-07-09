"""
WebSocket message schemas and validation for IB Stream API.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

import jsonschema
from jsonschema import validate, ValidationError

logger = logging.getLogger(__name__)

# Client-to-Server Message Schemas

SUBSCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"const": "subscribe"},
        "id": {"type": "string", "minLength": 1},
        "data": {
            "type": "object",
            "properties": {
                "contract_id": {"type": "integer", "minimum": 1},
                "tick_type": {"enum": ["Last", "AllLast", "BidAsk", "MidPoint"]},
                "params": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10000},
                        "timeout": {"type": "integer", "minimum": 5, "maximum": 3600}
                    },
                    "additionalProperties": False
                }
            },
            "required": ["contract_id", "tick_type"],
            "additionalProperties": False
        }
    },
    "required": ["type", "id", "data"],
    "additionalProperties": False
}

MULTI_SUBSCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"const": "multi_subscribe"},
        "id": {"type": "string", "minLength": 1},
        "data": {
            "type": "object",
            "properties": {
                "contract_id": {"type": "integer", "minimum": 1},
                "tick_types": {
                    "type": "array",
                    "items": {"enum": ["Last", "AllLast", "BidAsk", "MidPoint"]},
                    "minItems": 1,
                    "maxItems": 4,
                    "uniqueItems": True
                },
                "params": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10000},
                        "timeout": {"type": "integer", "minimum": 5, "maximum": 3600}
                    },
                    "additionalProperties": False
                }
            },
            "required": ["contract_id", "tick_types"],
            "additionalProperties": False
        }
    },
    "required": ["type", "id", "data"],
    "additionalProperties": False
}

UNSUBSCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"const": "unsubscribe"},
        "id": {"type": "string", "minLength": 1},
        "data": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "minLength": 1}
            },
            "required": ["request_id"],
            "additionalProperties": False
        }
    },
    "required": ["type", "id", "data"],
    "additionalProperties": False
}

UNSUBSCRIBE_ALL_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"const": "unsubscribe_all"},
        "id": {"type": "string", "minLength": 1}
    },
    "required": ["type", "id"],
    "additionalProperties": False
}

PING_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"const": "ping"},
        "id": {"type": "string", "minLength": 1},
        "timestamp": {"type": "string", "format": "date-time"}
    },
    "required": ["type", "id"],
    "additionalProperties": False
}

# Schema registry for message types
CLIENT_MESSAGE_SCHEMAS = {
    "subscribe": SUBSCRIBE_SCHEMA,
    "multi_subscribe": MULTI_SUBSCRIBE_SCHEMA,
    "unsubscribe": UNSUBSCRIBE_SCHEMA,
    "unsubscribe_all": UNSUBSCRIBE_ALL_SCHEMA,
    "ping": PING_SCHEMA
}


class WebSocketMessage:
    """Base class for WebSocket messages."""
    
    def __init__(self, message_type: str, message_id: Optional[str] = None, 
                 data: Optional[Dict[str, Any]] = None):
        self.type = message_type
        self.id = message_id
        self.data = data or {}
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        message = {
            "type": self.type,
            "timestamp": self.timestamp
        }
        
        if self.id:
            message["id"] = self.id
            
        if self.data:
            message.update(self.data)
            
        return message
    
    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


class SubscribedMessage(WebSocketMessage):
    """Server message confirming subscription."""
    
    def __init__(self, message_id: str, request_id: str, contract_id: int, 
                 tick_type: str, contract_info: Optional[Dict[str, Any]] = None):
        data = {
            "data": {
                "request_id": request_id,
                "contract_id": contract_id,
                "tick_type": tick_type,
                "contract_info": contract_info or {}
            }
        }
        super().__init__("subscribed", message_id, data)


class TickMessage(WebSocketMessage):
    """Server message containing tick data."""
    
    def __init__(self, request_id: str, tick_data: Dict[str, Any]):
        data = {
            "request_id": request_id,
            "data": tick_data
        }
        super().__init__("tick", data=data)


class ErrorMessage(WebSocketMessage):
    """Server message containing error information."""
    
    def __init__(self, request_id: Optional[str], error_code: str, 
                 message: str, details: Optional[Dict[str, Any]] = None):
        data = {
            "error": {
                "code": error_code,
                "message": message,
                "details": details or {}
            }
        }
        if request_id:
            data["request_id"] = request_id
        super().__init__("error", data=data)


class CompleteMessage(WebSocketMessage):
    """Server message indicating stream completion."""
    
    def __init__(self, request_id: str, reason: str, total_ticks: int, 
                 duration_seconds: float):
        data = {
            "request_id": request_id,
            "data": {
                "reason": reason,
                "total_ticks": total_ticks,
                "duration_seconds": duration_seconds
            }
        }
        super().__init__("complete", data=data)


class UnsubscribedMessage(WebSocketMessage):
    """Server message confirming unsubscription."""
    
    def __init__(self, message_id: str, request_id: str):
        data = {
            "data": {
                "request_id": request_id
            }
        }
        super().__init__("unsubscribed", message_id, data)


class PongMessage(WebSocketMessage):
    """Server message responding to ping."""
    
    def __init__(self, message_id: str, client_timestamp: Optional[str] = None):
        data = {
            "data": {
                "client_timestamp": client_timestamp,
                "server_timestamp": datetime.now().isoformat()
            }
        }
        super().__init__("pong", message_id, data)


class ConnectedMessage(WebSocketMessage):
    """Server message sent on connection establishment."""
    
    def __init__(self, version: str = "1.0.0", server_info: Optional[Dict[str, Any]] = None):
        data = {
            "version": version,
            "server_info": server_info or {}
        }
        super().__init__("connected", data=data)


def validate_client_message(message_data: Dict[str, Any]) -> bool:
    """
    Validate a client message against its schema.
    
    Args:
        message_data: The parsed message data
        
    Returns:
        True if valid, False otherwise
        
    Raises:
        ValidationError: If validation fails with details
    """
    message_type = message_data.get("type")
    
    if not message_type:
        raise ValidationError("Message missing 'type' field")
    
    if message_type not in CLIENT_MESSAGE_SCHEMAS:
        raise ValidationError(f"Unknown message type: {message_type}")
    
    schema = CLIENT_MESSAGE_SCHEMAS[message_type]
    
    try:
        validate(instance=message_data, schema=schema)
        return True
    except ValidationError as e:
        logger.warning("Message validation failed for type %s: %s", message_type, e)
        raise


def parse_client_message(raw_message: str) -> Dict[str, Any]:
    """
    Parse and validate a raw client message.
    
    Args:
        raw_message: Raw JSON string from client
        
    Returns:
        Parsed and validated message data
        
    Raises:
        json.JSONDecodeError: If JSON parsing fails
        ValidationError: If validation fails
    """
    try:
        message_data = json.loads(raw_message)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse JSON message: %s", e)
        raise
    
    validate_client_message(message_data)
    return message_data


# WebSocket close codes
class WSCloseCode:
    """WebSocket close codes."""
    NORMAL_CLOSURE = 1000
    GOING_AWAY = 1001
    UNSUPPORTED_DATA = 1003
    POLICY_VIOLATION = 1008
    INTERNAL_ERROR = 1011
    
    # Custom codes (4000-4999 range)
    INVALID_MESSAGE = 4000
    AUTH_REQUIRED = 4001
    INVALID_CONTRACT = 4002
    TWS_CONNECTION_LOST = 4003
    RATE_LIMIT_EXCEEDED = 4004


# Error code mappings
ERROR_CODE_TO_CLOSE_CODE = {
    "INVALID_MESSAGE": WSCloseCode.INVALID_MESSAGE,
    "AUTH_REQUIRED": WSCloseCode.AUTH_REQUIRED,
    "CONTRACT_NOT_FOUND": WSCloseCode.INVALID_CONTRACT,
    "CONNECTION_ERROR": WSCloseCode.TWS_CONNECTION_LOST,
    "RATE_LIMIT_EXCEEDED": WSCloseCode.RATE_LIMIT_EXCEEDED,
    "INTERNAL_ERROR": WSCloseCode.INTERNAL_ERROR
}


def get_close_code_for_error(error_code: str) -> int:
    """Get appropriate WebSocket close code for an error."""
    return ERROR_CODE_TO_CLOSE_CODE.get(error_code, WSCloseCode.INTERNAL_ERROR)