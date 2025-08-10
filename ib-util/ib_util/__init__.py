"""
IB Utilities - Shared utilities for Interactive Brokers API connections

This module provides common functionality for both ib-stream and ib-contracts services:
- Reliable connection handling with proper API handshake
- Environment configuration loading  
- Connection state management
- Error handling and logging
"""

from .connection import IBConnection, ConnectionConfig, create_connection, connect_with_retry
from .config_loader import load_environment_config, load_environment_file, load_environment_file_with_detection
from .error_handler import handle_tws_error, handle_streaming_error, get_error_description, is_informational_error, is_connection_error
from .logging_config import configure_logging, configure_service_logging, configure_cli_logging, get_logger, log_environment_info
from .contract_factory import (
    create_contract_by_id, create_stock_contract, create_futures_contract, create_option_contract,
    create_forex_contract, create_index_contract, create_contract_for_lookup, validate_contract
)
from .trading_hours import (
    TradingHoursParser, MarketStatus, MarketStatusResult, TradingSession,
    check_contract_market_status, get_contract_trading_schedule
)
from .response_formatting import (
    format_timestamp, format_iso_timestamp, format_json_response, create_api_response,
    create_error_response, create_contract_lookup_response, create_health_check_response,
    format_cache_status_response, format_sse_event, format_price, format_size, format_percentage
)
from .base_api_server import BaseAPIServer, create_standardized_health_response, create_standardized_error_response
from .cache_manager import CacheManager

__all__ = [
    'IBConnection', 
    'ConnectionConfig', 
    'create_connection', 
    'connect_with_retry', 
    'load_environment_config',
    'load_environment_file',
    'load_environment_file_with_detection',
    'handle_tws_error',
    'handle_streaming_error', 
    'get_error_description',
    'is_informational_error',
    'is_connection_error',
    'configure_logging',
    'configure_service_logging',
    'configure_cli_logging', 
    'get_logger',
    'log_environment_info',
    'create_contract_by_id',
    'create_stock_contract',
    'create_futures_contract', 
    'create_option_contract',
    'create_forex_contract',
    'create_index_contract',
    'create_contract_for_lookup',
    'validate_contract',
    'format_timestamp',
    'format_iso_timestamp',
    'format_json_response',
    'create_api_response',
    'create_error_response',
    'create_contract_lookup_response',
    'create_health_check_response',
    'format_cache_status_response',
    'format_sse_event',
    'format_price',
    'format_size',
    'format_percentage',
    'BaseAPIServer',
    'create_standardized_health_response',
    'create_standardized_error_response',
    'CacheManager'
]