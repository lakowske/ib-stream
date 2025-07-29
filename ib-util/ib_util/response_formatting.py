"""
Response formatting utilities for IB services

This module provides standardized formatting functions for API responses,
JSON output, timestamps, and common data structures across ib-stream,
ib-contract, and other IB services.
"""

import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union


def format_timestamp(unix_timestamp: int, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format Unix timestamp to readable string
    
    Args:
        unix_timestamp: Unix timestamp (seconds since epoch)
        format_str: strftime format string
        
    Returns:
        Formatted timestamp string
    """
    return time.strftime(format_str, time.localtime(unix_timestamp))


def format_iso_timestamp(unix_timestamp: Optional[int] = None) -> str:
    """
    Format timestamp as ISO 8601 string
    
    Args:
        unix_timestamp: Unix timestamp, uses current time if None
        
    Returns:
        ISO 8601 formatted timestamp string
    """
    if unix_timestamp is None:
        return datetime.now(timezone.utc).isoformat()
    else:
        return datetime.fromtimestamp(unix_timestamp, timezone.utc).isoformat()


def format_json_response(
    data: Any,
    indent: int = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False
) -> str:
    """
    Format data structure as JSON string with consistent formatting
    
    Args:
        data: Data to serialize as JSON
        indent: JSON indentation level
        ensure_ascii: Whether to ensure ASCII encoding
        sort_keys: Whether to sort object keys
        
    Returns:
        Formatted JSON string
    """
    class DecimalEncoder(json.JSONEncoder):
        """Custom JSON encoder to handle Decimal objects"""
        def default(self, obj):
            if isinstance(obj, Decimal):
                return float(obj)
            return super().default(obj)
    
    return json.dumps(
        data, 
        indent=indent, 
        ensure_ascii=ensure_ascii,
        sort_keys=sort_keys,
        cls=DecimalEncoder
    )


def create_api_response(
    data: Any = None,
    message: str = "",
    success: bool = True,
    timestamp: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Create standardized API response structure
    
    Args:
        data: Response data payload
        message: Status or error message
        success: Whether the operation was successful
        timestamp: Response timestamp (ISO format), uses current time if None
        **kwargs: Additional response fields
        
    Returns:
        Standardized response dictionary
    """
    response = {
        "success": success,
        "timestamp": timestamp or format_iso_timestamp(),
        "message": message
    }
    
    if data is not None:
        response["data"] = data
    
    # Add any additional fields
    response.update(kwargs)
    
    return response


def create_error_response(
    error_message: str,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create standardized error response
    
    Args:
        error_message: Human-readable error message
        error_code: Machine-readable error code
        details: Additional error details
        timestamp: Error timestamp, uses current time if None
        
    Returns:
        Standardized error response dictionary
    """
    response = create_api_response(
        success=False,
        message=error_message,
        timestamp=timestamp
    )
    
    if error_code:
        response["error_code"] = error_code
    
    if details:
        response["error_details"] = details
    
    return response


def create_contract_lookup_response(
    ticker: str,
    contracts: List[Dict[str, Any]],
    security_types_searched: List[str],
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create standardized contract lookup response
    
    Args:
        ticker: Ticker symbol that was searched
        contracts: List of contract dictionaries
        security_types_searched: List of security types that were searched
        timestamp: Response timestamp, uses current time if None
        
    Returns:
        Standardized contract lookup response
    """
    from collections import defaultdict
    
    # Group contracts by security type
    contracts_by_type = defaultdict(list)
    for contract in contracts:
        contracts_by_type[contract.get("sec_type", "UNKNOWN")].append(contract)
    
    # Build response structure
    response_data = {
        "ticker": ticker.upper(),
        "timestamp": timestamp or format_iso_timestamp(),
        "security_types_searched": security_types_searched,
        "total_contracts": len(contracts),
        "contracts_by_type": {},
        "summary": {}
    }
    
    # Add contracts by type
    for sec_type, type_contracts in contracts_by_type.items():
        response_data["contracts_by_type"][sec_type] = {
            "count": len(type_contracts),
            "contracts": type_contracts
        }
    
    # Add summary counts
    for sec_type in contracts_by_type.keys():
        response_data["summary"][sec_type] = len(contracts_by_type[sec_type])
    
    return create_api_response(data=response_data)


def create_health_check_response(
    service_name: str,
    status: str = "healthy",
    details: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create standardized health check response
    
    Args:
        service_name: Name of the service
        status: Health status ("healthy", "unhealthy", "degraded")
        details: Additional health check details
        timestamp: Health check timestamp, uses current time if None
        
    Returns:
        Standardized health check response
    """
    response_data = {
        "service": service_name,
        "status": status,
        "timestamp": timestamp or format_iso_timestamp()
    }
    
    if details:
        response_data.update(details)
    
    return response_data


def format_cache_status_response(
    memory_cache: Dict[str, Any],
    file_cache: Dict[str, Any],
    cache_duration_days: int,
    cache_directory: str
) -> Dict[str, Any]:
    """
    Create standardized cache status response
    
    Args:
        memory_cache: Memory cache information
        file_cache: File cache information
        cache_duration_days: Cache duration in days
        cache_directory: Cache directory path
        
    Returns:
        Standardized cache status response
    """
    return {
        "memory_cache_entries": len(memory_cache),
        "file_cache_entries": len(file_cache),
        "cache_duration_days": cache_duration_days,
        "cache_directory": cache_directory,
        "memory_cache": memory_cache,
        "file_cache": file_cache
    }


def format_sse_event(
    event_type: str,
    data: Any,
    event_id: Optional[str] = None,
    retry: Optional[int] = None
) -> str:
    """
    Format Server-Sent Events (SSE) response
    
    Args:
        event_type: SSE event type
        data: Event data (will be JSON serialized)
        event_id: Optional event ID
        retry: Optional retry interval in milliseconds
        
    Returns:
        Formatted SSE event string
    """
    lines = []
    
    if event_id:
        lines.append(f"id: {event_id}")
    
    if retry:
        lines.append(f"retry: {retry}")
    
    lines.append(f"event: {event_type}")
    
    # Serialize data as JSON
    if isinstance(data, str):
        data_json = data
    else:
        data_json = format_json_response(data, indent=None)
    
    lines.append(f"data: {data_json}")
    lines.append("")  # Empty line to end event
    
    return "\n".join(lines)


def format_price(price: Union[float, Decimal], decimals: int = 2) -> str:
    """
    Format price with appropriate decimal places
    
    Args:
        price: Price value
        decimals: Number of decimal places
        
    Returns:
        Formatted price string
    """
    if isinstance(price, Decimal):
        price = float(price)
    return f"{price:.{decimals}f}"


def format_size(size: Union[int, float, Decimal]) -> str:
    """
    Format size/volume with appropriate formatting
    
    Args:
        size: Size/volume value
        
    Returns:
        Formatted size string
    """
    if isinstance(size, Decimal):
        size = float(size)
    
    if isinstance(size, float) and size.is_integer():
        return str(int(size))
    else:
        return str(size)


def format_percentage(value: Union[float, Decimal], decimals: int = 2) -> str:
    """
    Format percentage value
    
    Args:
        value: Percentage value (as decimal, e.g., 0.05 for 5%)
        decimals: Number of decimal places
        
    Returns:
        Formatted percentage string with % symbol
    """
    if isinstance(value, Decimal):
        value = float(value)
    return f"{value * 100:.{decimals}f}%"


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate string to maximum length with suffix
    
    Args:
        text: String to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_table_row(values: List[str], widths: List[int], separator: str = " ") -> str:
    """
    Format values as a table row with fixed column widths
    
    Args:
        values: Column values
        widths: Column widths
        separator: Column separator
        
    Returns:
        Formatted table row string
    """
    formatted_cols = []
    for value, width in zip(values, widths):
        formatted_cols.append(value.ljust(width))
    
    return separator.join(formatted_cols)


def safe_get_nested(data: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    """
    Safely get nested dictionary value with default fallback
    
    Args:
        data: Dictionary to search
        keys: List of nested keys
        default: Default value if key path doesn't exist
        
    Returns:
        Value at key path or default
    """
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current