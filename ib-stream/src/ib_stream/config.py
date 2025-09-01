"""
Configuration management for IB Stream API Server - Configuration System v3.

This module uses Configuration System v3 with YAML-based hierarchical configuration
and provides compatibility interfaces for existing code.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
import threading

# Import Configuration System v3
from ib_util import load_config, AppConfig


@dataclass
class TrackedContract:
    """Configuration for a contract that should be automatically tracked at startup"""
    
    contract_id: int
    symbol: str  # For logging and monitoring purposes
    tick_types: List[str] = field(default_factory=lambda: ["bid_ask", "last"])
    buffer_hours: int = 1  # How much historical data to maintain as buffer
    enabled: bool = True
    
    def __post_init__(self):
        """Validate tracked contract configuration"""
        if self.contract_id <= 0:
            raise ValueError(f"Contract ID must be positive, got {self.contract_id}")
        
        if not self.symbol:
            raise ValueError("Symbol is required for tracked contracts")
        
        if self.buffer_hours < 1:
            raise ValueError(f"Buffer hours must be at least 1, got {self.buffer_hours}")
        
        valid_tick_types = ["bid_ask", "last", "all_last", "mid_point"]
        for tick_type in self.tick_types:
            if tick_type not in valid_tick_types:
                raise ValueError(f"Invalid tick type '{tick_type}'. Valid types: {valid_tick_types}")


@dataclass
class StorageConfig:
    """Configuration for storage system - mirrors Configuration v3 StorageConfig"""
    
    # Enable/disable storage backends
    enable_storage: bool = True
    
    # v2 storage formats (legacy)
    enable_json: bool = True
    enable_protobuf: bool = True
    
    # v3 storage formats (optimized, 50%+ space reduction)
    enable_v3_json: bool = True
    enable_v3_protobuf: bool = True
    
    # Other storage backends
    enable_postgres_index: bool = False  # Default to disabled
    
    # Control whether client-requested streams are stored to disk
    # Background streams always store regardless of this setting
    enable_client_stream_storage: bool = True
    
    # Storage paths
    storage_base_path: Path = Path("storage")
    json_storage_path: Optional[Path] = None
    protobuf_storage_path: Optional[Path] = None
    
    # PostgreSQL index configuration
    postgres_url: str = "postgresql://localhost:5432/ib_stream"
    postgres_schema: str = "ib_stream_storage"
    
    # Performance settings
    write_batch_size: int = 100
    write_batch_timeout_seconds: float = 1.0
    max_write_queue_size: int = 10000
    max_concurrent_writers: int = 4
    
    # File rotation settings
    rotation_interval_hours: int = 1
    max_file_size_mb: int = 100
    
    # Retention settings
    json_retention_days: int = 7
    protobuf_retention_days: int = 365
    health_records_retention_days: int = 7
    
    # Metrics and monitoring
    enable_metrics: bool = True
    metrics_window_size: int = 100
    health_check_interval_seconds: int = 60
    
    # Tracked contracts for background streaming
    tracked_contracts: List[TrackedContract] = field(default_factory=list)
    max_tracked_contracts: int = 10
    background_stream_reconnect_delay: int = 3  # seconds
    
    # Health monitoring configuration
    health_staleness_threshold_minutes: int = 15  # Minutes before data is considered stale
    health_check_interval_seconds: int = 300  # How often to perform health checks (5 minutes)
    trading_hours_cache_ttl_hours: int = 24  # How long to cache trading hours data
    
    def __post_init__(self):
        """Initialize derived paths"""
        if self.json_storage_path is None:
            self.json_storage_path = self.storage_base_path / "json"
        if self.protobuf_storage_path is None:
            self.protobuf_storage_path = self.storage_base_path / "protobuf"


@dataclass
class ServerConfig:
    """Configuration for the API server - created from Configuration v3"""

    # TWS Connection
    client_id: int = 101
    host: str = "192.168.0.60"
    ports: List[int] = field(default_factory=lambda: [4002, 4001])

    # Streaming Limits  
    max_concurrent_streams: int = 10
    default_timeout_seconds: Optional[int] = None  # No timeout by default
    buffer_size: int = 100

    # Connection Management
    reconnect_attempts: int = 5
    connection_timeout: int = 10
    heartbeat_interval: int = 30

    # Server Settings
    server_host: str = "0.0.0.0"
    server_port: int = 8851

    # Logging
    log_level: str = "DEBUG"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    
    # Storage Configuration
    storage: StorageConfig = field(default_factory=StorageConfig)


def convert_v3_to_legacy_storage(v3_config: AppConfig) -> StorageConfig:
    """Convert Configuration v3 storage config to legacy StorageConfig format"""
    # Extract tracked contracts if they exist
    tracked_contracts = []
    if (v3_config.service.streaming and 
        hasattr(v3_config.service.streaming, 'tracked_contracts')):
        for contract_config in v3_config.service.streaming.tracked_contracts:
            tracked_contract = TrackedContract(
                contract_id=contract_config.contract_id,
                symbol=contract_config.symbol,
                tick_types=contract_config.tick_types,
                buffer_hours=contract_config.buffer_hours
            )
            tracked_contracts.append(tracked_contract)
    
    return StorageConfig(
        enable_storage=v3_config.storage.enabled,
        enable_json=v3_config.storage.formats.v2_json,
        enable_protobuf=v3_config.storage.formats.v2_protobuf,
        enable_v3_json=v3_config.storage.formats.v3_json,
        enable_v3_protobuf=v3_config.storage.formats.v3_protobuf,
        enable_postgres_index=v3_config.storage.enable_postgres,
        enable_metrics=v3_config.storage.enable_metrics,
        storage_base_path=Path(v3_config.storage.base_path),
        write_batch_size=v3_config.storage.buffer_size,
        max_file_size_mb=v3_config.storage.max_file_size_mb,
        tracked_contracts=tracked_contracts
    )


def convert_v3_to_legacy_server(v3_config: AppConfig) -> ServerConfig:
    """Convert Configuration v3 to legacy ServerConfig format"""
    storage_config = convert_v3_to_legacy_storage(v3_config)
    
    return ServerConfig(
        client_id=v3_config.service.client.id,
        host=v3_config.gateway.host,
        ports=v3_config.gateway.ports,
        max_concurrent_streams=v3_config.performance.max_concurrent_streams,
        default_timeout_seconds=v3_config.performance.default_timeout_seconds,
        buffer_size=v3_config.storage.buffer_size,
        reconnect_attempts=v3_config.gateway.reconnect_attempts,
        connection_timeout=v3_config.gateway.connection_timeout,
        server_host=v3_config.service.server.host,
        server_port=v3_config.service.server.port,
        log_level=v3_config.logging.level,
        storage=storage_config
    )


# Configuration cache to avoid repeated expensive loading
_config_cache: Optional[ServerConfig] = None
_cache_lock = threading.Lock()

def create_config() -> ServerConfig:
    """Create and validate configuration using Configuration System v3 with caching"""
    import logging
    logger = logging.getLogger(__name__)
    
    global _config_cache
    
    # Check cache first
    if _config_cache is not None:
        logger.debug("Using cached configuration")
        return _config_cache
    
    # Thread-safe cache population
    with _cache_lock:
        # Double-check pattern
        if _config_cache is not None:
            logger.debug("Using cached configuration (double-check)")
            return _config_cache
        
        logger.info("Loading Configuration System v3...")
        
        # Load configuration using v3 system
        v3_config = load_config('ib-stream')
        
        # Convert to legacy format for backward compatibility
        legacy_config = convert_v3_to_legacy_server(v3_config)
        
        # Validate the converted configuration
        validate_config(legacy_config)
        
        # Cache the result
        _config_cache = legacy_config
        
        logger.info("Configuration System v3 loaded and cached successfully")
        
        return legacy_config


def clear_config_cache():
    """Clear the configuration cache - useful for testing or hot-reload scenarios"""
    global _config_cache
    with _cache_lock:
        _config_cache = None


def validate_config(config: ServerConfig) -> None:
    """Validate configuration values"""
    if config.client_id < 0:
        raise ValueError("Client ID must be non-negative")

    if config.max_concurrent_streams < 1:
        raise ValueError("Maximum concurrent streams must be at least 1")

    if config.default_timeout_seconds is not None and config.default_timeout_seconds < 1:
        raise ValueError("Default timeout must be at least 1 second")

    if config.buffer_size < 1:
        raise ValueError("Buffer size must be at least 1")

    if config.reconnect_attempts < 0:
        raise ValueError("Reconnect attempts must be non-negative")

    if config.connection_timeout < 1:
        raise ValueError("Connection timeout must be at least 1 second")

    if config.heartbeat_interval < 1:
        raise ValueError("Heartbeat interval must be at least 1 second")

    if config.server_port < 1 or config.server_port > 65535:
        raise ValueError("Server port must be between 1 and 65535")

    if not config.ports:
        raise ValueError("At least one TWS port must be specified")

    for port in config.ports:
        if port < 1 or port > 65535:
            raise ValueError(f"TWS port {port} must be between 1 and 65535")

    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.log_level.upper() not in valid_log_levels:
        raise ValueError(f"Log level must be one of: {', '.join(valid_log_levels)}")
    
    # Validate tracked contracts
    if len(config.storage.tracked_contracts) > config.storage.max_tracked_contracts:
        raise ValueError(f"Too many tracked contracts ({len(config.storage.tracked_contracts)}). Maximum: {config.storage.max_tracked_contracts}")
    
    # Check for duplicate contract IDs
    contract_ids = [c.contract_id for c in config.storage.tracked_contracts]
    if len(contract_ids) != len(set(contract_ids)):
        raise ValueError("Duplicate contract IDs found in tracked contracts")
    
    if config.storage.max_tracked_contracts < 0:
        raise ValueError("Max tracked contracts must be non-negative")
    
    if config.storage.background_stream_reconnect_delay < 1:
        raise ValueError("Background stream reconnect delay must be at least 1 second")


# Legacy compatibility functions
def get_tick_types() -> List[str]:
    """Get list of valid tick types"""
    return ["Last", "AllLast", "BidAsk", "MidPoint"]


def is_valid_tick_type(tick_type: str) -> bool:
    """Check if tick type is valid"""
    return tick_type in get_tick_types()


def get_default_tick_type() -> str:
    """Get default tick type"""
    return "Last"


def convert_v2_tick_type_to_tws_api(v2_tick_type: str) -> str:
    """Convert v2 protocol tick type (snake_case) to TWS API format (PascalCase)"""
    conversion_map = {
        "bid_ask": "BidAsk",
        "last": "Last", 
        "all_last": "AllLast",
        "mid_point": "MidPoint"
    }
    
    # Return converted value if found, otherwise return original (for backward compatibility)
    return conversion_map.get(v2_tick_type, v2_tick_type)


def get_max_limit() -> int:
    """Get maximum allowed limit for ticks"""
    return 10000  # Reasonable limit to prevent abuse


def get_min_timeout() -> int:
    """Get minimum allowed timeout"""
    return 5  # 5 seconds minimum


def get_max_timeout() -> int:
    """Get maximum allowed timeout"""
    return 3600  # 1 hour maximum


def create_connection_config(config: ServerConfig) -> dict:
    """Create connection configuration dictionary"""
    return {
        "client_id": config.client_id,
        "host": config.host,
        "ports": config.ports,
        "reconnect_attempts": config.reconnect_attempts,
        "connection_timeout": config.connection_timeout,
    }


def create_streaming_config(config: ServerConfig) -> dict:
    """Create streaming configuration dictionary"""
    return {
        "max_concurrent_streams": config.max_concurrent_streams,
        "default_timeout_seconds": config.default_timeout_seconds,
        "buffer_size": config.buffer_size,
        "heartbeat_interval": config.heartbeat_interval,
    }