"""Utilities for working with IB-Stream v2 protocol."""

import re
from datetime import datetime
from typing import Dict, Optional, Tuple


def parse_stream_id(stream_id: str) -> Dict[str, str]:
    """
    Parse a v2 protocol stream ID into its components.
    
    Stream ID format: {contract_id}_{tick_type}_{timestamp}_{random}
    Example: "265598_bid_ask_2025-01-08T15:30:00.123Z_abc123"
    
    Args:
        stream_id: The stream ID to parse
        
    Returns:
        Dict with keys: contract_id, tick_type, timestamp, random
    """
    if not stream_id:
        return {"contract_id": "", "tick_type": "", "timestamp": "", "random": ""}
    
    # Split by underscore, but be careful with timestamp which contains colons
    parts = stream_id.split('_')
    if len(parts) < 4:
        return {"contract_id": "", "tick_type": "", "timestamp": "", "random": ""}
    
    contract_id = parts[0]
    tick_type = parts[1]
    # Timestamp might contain underscores in some formats, so rejoin middle parts
    timestamp = '_'.join(parts[2:-1])
    random = parts[-1]
    
    return {
        "contract_id": contract_id,
        "tick_type": tick_type,
        "timestamp": timestamp,
        "random": random
    }


def extract_contract_id_from_stream_id(stream_id: str) -> Optional[int]:
    """
    Extract contract ID from stream ID.
    
    Args:
        stream_id: The stream ID
        
    Returns:
        Contract ID as integer, or None if not found
    """
    parsed = parse_stream_id(stream_id)
    contract_id_str = parsed.get("contract_id", "")
    
    try:
        return int(contract_id_str)
    except (ValueError, TypeError):
        return None


def extract_tick_type_from_stream_id(stream_id: str) -> str:
    """
    Extract tick type from stream ID.
    
    Args:
        stream_id: The stream ID
        
    Returns:
        Tick type string (e.g., "bid_ask", "last")
    """
    parsed = parse_stream_id(stream_id)
    return parsed.get("tick_type", "")


def extract_timestamp_from_stream_id(stream_id: str) -> Optional[datetime]:
    """
    Extract timestamp from stream ID.
    
    Args:
        stream_id: The stream ID
        
    Returns:
        Datetime object or None if parsing fails
    """
    parsed = parse_stream_id(stream_id)
    timestamp_str = parsed.get("timestamp", "")
    
    if not timestamp_str:
        return None
    
    try:
        # Handle ISO format with Z suffix
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return None


def normalize_tick_type(tick_type: str) -> str:
    """
    Normalize tick type between v1 and v2 formats.
    
    Args:
        tick_type: Input tick type in any format
        
    Returns:
        Normalized tick type in v2 format (snake_case)
    """
    # Convert to lowercase first
    tick_type = tick_type.lower()
    
    # Common conversions
    conversions = {
        "bidask": "bid_ask",
        "allast": "all_last", 
        "midpoint": "mid_point",
        "timesales": "time_sales",
        "last": "last",
        "bid_ask": "bid_ask",
        "all_last": "all_last",
        "mid_point": "mid_point",
        "time_sales": "time_sales"
    }
    
    return conversions.get(tick_type, tick_type)


def denormalize_tick_type(tick_type: str) -> str:
    """
    Convert v2 tick type back to display format.
    
    Args:
        tick_type: v2 format tick type (snake_case)
        
    Returns:
        Display format tick type (PascalCase)
    """
    conversions = {
        "bid_ask": "BidAsk",
        "last": "Last",
        "all_last": "AllLast",
        "mid_point": "MidPoint",
        "time_sales": "TimeSales"
    }
    
    return conversions.get(tick_type, tick_type)


def parse_v2_timestamp(timestamp: str) -> Optional[datetime]:
    """
    Parse v2 protocol timestamp string.
    
    Args:
        timestamp: ISO format timestamp string
        
    Returns:
        Datetime object or None if parsing fails
    """
    if not timestamp:
        return None
    
    try:
        # Handle ISO format with Z suffix
        if timestamp.endswith('Z'):
            timestamp = timestamp[:-1] + '+00:00'
        return datetime.fromisoformat(timestamp)
    except (ValueError, TypeError):
        return None


def format_v2_timestamp(dt: datetime) -> str:
    """
    Format datetime as v2 protocol timestamp.
    
    Args:
        dt: Datetime object
        
    Returns:
        ISO format timestamp string with Z suffix
    """
    return dt.isoformat() + 'Z'


def validate_v2_message(message: Dict) -> Tuple[bool, str]:
    """
    Validate v2 protocol message structure.
    
    Args:
        message: Message dictionary to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ["type", "timestamp"]
    
    for field in required_fields:
        if field not in message:
            return False, f"Missing required field: {field}"
    
    # Validate message type
    valid_types = ["tick", "error", "complete", "info", "subscribe", "subscribed", "ping", "pong", "connected"]
    if message.get("type") not in valid_types:
        return False, f"Invalid message type: {message.get('type')}"
    
    # Stream messages should have stream_id
    stream_types = ["tick", "error", "complete", "info"]
    if message.get("type") in stream_types and not message.get("stream_id"):
        return False, f"Stream message missing stream_id: {message.get('type')}"
    
    # Validate timestamp format
    timestamp = message.get("timestamp")
    if timestamp and not parse_v2_timestamp(timestamp):
        return False, f"Invalid timestamp format: {timestamp}"
    
    return True, ""


def is_v2_message(message: Dict) -> bool:
    """
    Check if message appears to be v2 protocol format.
    
    Args:
        message: Message dictionary to check
        
    Returns:
        True if message looks like v2 protocol
    """
    # V2 messages have type and timestamp fields
    return isinstance(message, dict) and "type" in message and "timestamp" in message


def extract_tick_data(v2_message: Dict) -> Dict:
    """
    Extract tick data from v2 protocol message.
    
    Args:
        v2_message: v2 protocol message
        
    Returns:
        Tick data dictionary
    """
    if not is_v2_message(v2_message):
        return {}
    
    return v2_message.get("data", {})


def get_message_age_seconds(v2_message: Dict) -> Optional[float]:
    """
    Calculate age of v2 message in seconds.
    
    Args:
        v2_message: v2 protocol message
        
    Returns:
        Age in seconds or None if timestamp unavailable
    """
    timestamp_str = v2_message.get("timestamp")
    if not timestamp_str:
        return None
    
    message_time = parse_v2_timestamp(timestamp_str)
    if not message_time:
        return None
    
    return (datetime.utcnow() - message_time).total_seconds()