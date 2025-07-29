"""
Standardized TWS/Gateway error handling for IB services

This module provides common error handling patterns used across ib-stream, ib-contract,
and other IB API services. It centralizes error code interpretation and logging.
"""

import logging
from typing import Optional, Callable, Any


def handle_tws_error(
    req_id: int, 
    error_code: int, 
    error_string: str, 
    logger: logging.Logger,
    error_callback: Optional[Callable[[int, int, str], Any]] = None
) -> None:
    """
    Standardized TWS error handling
    
    Args:
        req_id: Request ID associated with the error
        error_code: TWS error code
        error_string: Error message from TWS
        logger: Logger instance to use for logging
        error_callback: Optional callback function for custom error handling
    """
    try:
        # Handle specific error codes with standardized responses
        if error_code == 502:
            error_msg = "Couldn't connect to TWS. Make sure TWS/Gateway is running."
            logger.error(error_msg)
            if error_callback:
                error_callback(req_id, error_code, error_msg)
                
        elif error_code == 200:
            error_msg = f"No security definition found for request {req_id}"
            logger.warning(error_msg)
            if error_callback:
                error_callback(req_id, error_code, error_msg)
                
        elif error_code == 504:
            error_msg = f"Connection timeout: {error_string}"
            logger.error(error_msg)
            if error_callback:
                error_callback(req_id, error_code, error_msg)
                
        elif error_code in [2104, 2106, 2158]:
            # Market data farm connection messages - informational only
            logger.info(f"Connection status: {error_string}")
            # Don't call error_callback for informational messages
            
        elif error_code in [2100, 2101, 2102, 2103]:
            # API connection status messages - informational
            logger.info(f"API status: {error_string}")
            
        elif error_code in [300, 301, 302, 303]:
            # Data request errors - handle gracefully
            error_msg = f"Data request error {error_code}: {error_string} (ReqId: {req_id})"
            logger.warning(error_msg)
            if error_callback:
                error_callback(req_id, error_code, error_msg)
                
        elif error_code >= 1000 and error_code < 2000:
            # System errors - more serious
            error_msg = f"System error {error_code}: {error_string} (ReqId: {req_id})"
            logger.error(error_msg)
            if error_callback:
                error_callback(req_id, error_code, error_msg)
                
        else:
            # Generic error handling
            error_msg = f"TWS error {error_code}: {error_string} (ReqId: {req_id})"
            logger.warning(error_msg)
            if error_callback:
                error_callback(req_id, error_code, error_msg)
                
    except Exception as e:
        # Error in error handler - log but don't re-raise to avoid infinite loops
        logger.error("Exception in TWS error handler: %s", e)


def handle_streaming_error(
    req_id: int,
    error_code: int, 
    error_string: str,
    logger: logging.Logger,
    error_callback: Optional[Callable[[str, str], Any]] = None
) -> None:
    """
    Specialized error handling for streaming applications
    
    This variant provides error_callback with string error codes for compatibility
    with streaming applications that use categorical error codes.
    
    Args:
        req_id: Request ID associated with the error
        error_code: TWS error code
        error_string: Error message from TWS  
        logger: Logger instance to use for logging
        error_callback: Optional callback with (error_category, error_message) signature
    """
    try:
        if error_code == 502:
            error_msg = "Couldn't connect to TWS. Make sure TWS/Gateway is running."
            logger.error(error_msg)
            if error_callback:
                error_callback("CONNECTION_ERROR", error_msg)
                
        elif error_code == 200:
            error_msg = "No security definition found for contract ID"
            logger.error(error_msg)
            if error_callback:
                error_callback("CONTRACT_NOT_FOUND", error_msg)
                
        elif error_code in [2104, 2106, 2158]:
            # Market data farm connection messages - can ignore
            logger.info(f"Connection status: {error_string}")
            # Don't call error_callback for informational messages
            
        else:
            error_msg = f"Error {error_code}: {error_string} (ReqId: {req_id})"
            logger.error(error_msg)
            if error_callback:
                error_callback(f"TWS_ERROR_{error_code}", error_msg)
                
    except Exception as e:
        import traceback
        logger.error("Exception in streaming error handler: %s\nTraceback:\n%s", e, traceback.format_exc())


def get_error_description(error_code: int) -> str:
    """
    Get human-readable description of TWS error codes
    
    Args:
        error_code: TWS error code
        
    Returns:
        Description of the error code
    """
    error_descriptions = {
        200: "No security definition found",
        502: "Couldn't connect to TWS",
        504: "Connection timeout", 
        1100: "Connectivity between IB and TWS has been lost",
        1101: "Connectivity between IB and TWS has been restored - data lost",
        1102: "Connectivity between IB and TWS has been restored - data maintained",
        2104: "Market data farm connection is OK",
        2106: "HMDS data farm connection is OK", 
        2158: "Sec-def data farm connection is OK",
        # Add more as needed
    }
    
    return error_descriptions.get(error_code, f"Unknown error code {error_code}")


def is_informational_error(error_code: int) -> bool:
    """
    Check if an error code is informational (not a real error)
    
    Args:
        error_code: TWS error code
        
    Returns:
        True if the error is informational only
    """
    informational_codes = [2100, 2101, 2102, 2103, 2104, 2106, 2158]
    return error_code in informational_codes


def is_connection_error(error_code: int) -> bool:
    """
    Check if an error code indicates a connection problem
    
    Args:
        error_code: TWS error code
        
    Returns:
        True if the error indicates connection issues
    """
    connection_error_codes = [502, 504, 1100]
    return error_code in connection_error_codes