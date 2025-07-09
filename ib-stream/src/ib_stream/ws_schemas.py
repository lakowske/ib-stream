"""WebSocket message schemas and validation for IB-Stream v2 protocol."""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

import jsonschema
from jsonschema import validate, ValidationError

from .protocol_types import (
    SubscribeMessage,
    UnsubscribeMessage,
    SubscribedMessage,
    ConnectedMessage,
    PingMessage,
    PongMessage,
    TickMessage,
    ErrorMessage,
    CompleteMessage,
    InfoMessage
)

logger = logging.getLogger(__name__)

# Client-to-Server Message Schemas (v2 protocol)

SUBSCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"const": "subscribe"},
        "id": {"type": "string", "minLength": 1},
        "timestamp": {"type": "string", "format": "date-time"},
        "data": {
            "type": "object",
            "properties": {
                "contract_id": {"type": "integer", "minimum": 1},
                "tick_types": {
                    "type": "array",
                    "items": {"enum": ["last", "all_last", "bid_ask", "mid_point"]},
                    "minItems": 1,
                    "maxItems": 4,
                    "uniqueItems": True
                },
                "config": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10000},
                        "timeout_seconds": {"type": "integer", "minimum": 5, "maximum": 3600},
                        "buffer_size": {"type": "integer", "minimum": 1, "maximum": 10000},
                        "include_extended": {"type": "boolean"}
                    },
                    "additionalProperties": False
                }
            },
            "required": ["contract_id", "tick_types"],
            "additionalProperties": False
        }
    },
    "required": ["type", "id", "timestamp", "data"],
    "additionalProperties": False
}

UNSUBSCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"const": "unsubscribe"},
        "id": {"type": "string", "minLength": 1},
        "timestamp": {"type": "string", "format": "date-time"},
        "data": {
            "type": "object",
            "properties": {
                "stream_id": {"type": "string", "minLength": 1}
            },
            "required": ["stream_id"],
            "additionalProperties": False
        }
    },
    "required": ["type", "id", "timestamp", "data"],
    "additionalProperties": False
}

PING_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"const": "ping"},
        "id": {"type": "string", "minLength": 1},
        "timestamp": {"type": "string", "format": "date-time"}
    },
    "required": ["type", "id", "timestamp"],
    "additionalProperties": False
}

# Schema registry for message types
CLIENT_MESSAGE_SCHEMAS = {
    "subscribe": SUBSCRIBE_SCHEMA,
    "unsubscribe": UNSUBSCRIBE_SCHEMA,
    "ping": PING_SCHEMA
}


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


def create_subscribe_message(message_id: str, contract_id: int, tick_types: List[str], config: Optional[Dict[str, Any]] = None) -> SubscribeMessage:
    """Create a subscribe message with v2 protocol structure."""
    return SubscribeMessage(message_id, contract_id, tick_types, config)


def create_unsubscribe_message(message_id: str, stream_id: str) -> UnsubscribeMessage:
    """Create an unsubscribe message with v2 protocol structure."""
    return UnsubscribeMessage(message_id, stream_id)


def create_subscribed_message(message_id: str, streams: List[Dict[str, str]]) -> SubscribedMessage:
    """Create a subscribed confirmation message with v2 protocol structure."""
    return SubscribedMessage(message_id, streams)


def create_connected_message(version: str = "2.0.0") -> ConnectedMessage:
    """Create a connected handshake message with v2 protocol structure."""
    return ConnectedMessage(version)


def create_ping_message(message_id: str) -> PingMessage:
    """Create a ping message with v2 protocol structure."""
    return PingMessage(message_id)


def create_pong_message(message_id: str, client_timestamp: Optional[str] = None) -> PongMessage:
    """Create a pong response message with v2 protocol structure."""
    return PongMessage(message_id, client_timestamp)


def create_tick_message(stream_id: str, contract_id: int, tick_type: str, tick_data: Dict[str, Any]) -> TickMessage:
    """Create a tick message with v2 protocol structure."""
    return TickMessage(stream_id, contract_id, tick_type, tick_data)


def create_error_message(stream_id: str, code: str, message: str, details: Optional[Dict[str, Any]] = None, recoverable: bool = True) -> ErrorMessage:
    """Create an error message with v2 protocol structure."""
    return ErrorMessage(stream_id, code, message, details, recoverable)


def create_complete_message(stream_id: str, reason: str, total_ticks: int, duration_seconds: float, final_sequence: Optional[int] = None) -> CompleteMessage:
    """Create a completion message with v2 protocol structure."""
    return CompleteMessage(stream_id, reason, total_ticks, duration_seconds, final_sequence)


def create_info_message(stream_id: str, status: str, contract_info: Optional[Dict[str, Any]] = None, stream_config: Optional[Dict[str, Any]] = None) -> InfoMessage:
    """Create an info message with v2 protocol structure."""
    return InfoMessage(stream_id, status, contract_info, stream_config)


# WebSocket close codes (same as v1)
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


# Error code mappings for close codes
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


# Helper functions for common error messages

def create_invalid_message_error(stream_id: str, validation_error: str) -> ErrorMessage:
    """Create an invalid message error."""
    return create_error_message(
        stream_id,
        "INVALID_MESSAGE",
        "Invalid message format",
        {"validation_error": validation_error},
        recoverable=False
    )


def create_contract_not_found_error(stream_id: str, contract_id: int) -> ErrorMessage:
    """Create a contract not found error."""
    return create_error_message(
        stream_id,
        "CONTRACT_NOT_FOUND",
        f"Contract ID {contract_id} not found",
        {
            "contract_id": contract_id,
            "suggestion": "Verify contract ID using the contract lookup API"
        },
        recoverable=False
    )


def create_rate_limit_error(stream_id: str) -> ErrorMessage:
    """Create a rate limit exceeded error."""
    return create_error_message(
        stream_id,
        "RATE_LIMIT_EXCEEDED",
        "Too many concurrent streams",
        {"suggestion": "Try again later or reduce concurrent connections"},
        recoverable=True
    )


def create_connection_error(stream_id: str, details: str) -> ErrorMessage:
    """Create a TWS connection error."""
    return create_error_message(
        stream_id,
        "CONNECTION_ERROR",
        "Unable to connect to TWS/Gateway",
        {
            "connection_details": details,
            "suggestion": "Ensure TWS/Gateway is running with API enabled"
        },
        recoverable=True
    )


def create_internal_error(stream_id: str, error_details: str) -> ErrorMessage:
    """Create an internal server error."""
    return create_error_message(
        stream_id,
        "INTERNAL_ERROR",
        "Internal server error occurred",
        {
            "error_details": error_details,
            "suggestion": "Please retry or contact support if problem persists"
        },
        recoverable=True
    )