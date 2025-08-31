"""
IB Utilities v3 - Shared utilities for Interactive Brokers API connections

Configuration System v3 - Clean YAML-based configuration with minimal environment variables.

This module provides common functionality for both ib-stream and ib-contracts services:
- NEW: YAML-based configuration system (config v3)
- Reliable connection handling with proper API handshake
- Connection state management
- Error handling and logging
"""

# Configuration System v3 - Primary import
from .config_v3 import (
    load_config,
    validate_config, 
    AppConfig,
    ConfigLoader,
    Environment
)

from .connection import IBConnection, ConnectionConfig, create_connection, connect_with_retry
from .error_handler import handle_tws_error, handle_streaming_error, get_error_description, is_informational_error, is_connection_error
from .logging_config import configure_logging, configure_service_logging, configure_cli_logging, get_logger, log_environment_info
from .contract_factory import (
    create_contract_by_id, create_stock_contract, create_futures_contract, create_option_contract,
    create_forex_contract, create_index_contract, create_contract_for_lookup, validate_contract
)
from .trading_hours import (
    TradingHoursParser, MarketStatus, MarketStatusResult, TradingSession,
    check_contract_market_status, get_contract_trading_schedule,
    ValidationError, validate_contract_id, validate_timezone, validate_hours_string
)
from .contract_cache import (
    ContractIndex, ContractCacheEntry, get_contract_index
)
from .trading_hours_service import (
    MarketStatusService, TradingHoursServiceFactory, CircuitBreaker, 
    ResilientMarketStatusService, ContractRepository, CachedContractRepository
)
from .response_formatting import (
    format_timestamp, format_iso_timestamp, format_json_response, create_api_response,
    create_error_response, create_contract_lookup_response, create_health_check_response,
    format_cache_status_response, format_sse_event, format_price, format_size, format_percentage
)
from .base_api_server import BaseAPIServer, create_standardized_health_response, create_standardized_error_response
from .cache_manager import CacheManager, CacheException, CacheFileError, CacheValidationError, CacheFilenameGenerator

__all__ = [
    # Configuration v3 - Primary exports
    'load_config',
    'validate_config',
    'AppConfig',
    'ConfigLoader', 
    'Environment',
    
    # Connection management
    'IBConnection', 
    'ConnectionConfig', 
    'create_connection', 
    'connect_with_retry',
    
    # Error handling
    'handle_tws_error',
    'handle_streaming_error', 
    'get_error_description',
    'is_informational_error',
    'is_connection_error',
    
    # Logging
    'configure_logging',
    'configure_service_logging',
    'configure_cli_logging', 
    'get_logger',
    'log_environment_info',
    
    # Contract management
    'create_contract_by_id',
    'create_stock_contract',
    'create_futures_contract', 
    'create_option_contract',
    'create_forex_contract',
    'create_index_contract',
    'create_contract_for_lookup',
    'validate_contract',
    
    # Response formatting
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
    
    # Base API server
    'BaseAPIServer',
    'create_standardized_health_response',
    'create_standardized_error_response',
    
    # Cache management
    'CacheManager'
]