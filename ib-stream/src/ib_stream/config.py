"""
Configuration management for IB Stream API Server.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


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
    """Configuration for storage system"""
    
    # Enable/disable storage backends
    enable_storage: bool = True
    enable_json: bool = True
    enable_protobuf: bool = True
    enable_postgres_index: bool = True
    
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
    
    def __post_init__(self):
        """Initialize derived paths"""
        if self.json_storage_path is None:
            self.json_storage_path = self.storage_base_path / "json"
        if self.protobuf_storage_path is None:
            self.protobuf_storage_path = self.storage_base_path / "protobuf"


@dataclass
class ServerConfig:
    """Configuration for the API server"""

    # TWS Connection
    client_id: int = 2
    host: str = "127.0.0.1"
    ports: List[int] = None

    # Streaming Limits
    max_concurrent_streams: int = 50
    default_timeout_seconds: Optional[int] = None  # No timeout by default
    buffer_size: int = 100

    # Connection Management
    reconnect_attempts: int = 3
    connection_timeout: int = 5
    heartbeat_interval: int = 30

    # Server Settings
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    
    # Storage Configuration
    storage: StorageConfig = None

    def __post_init__(self):
        if self.ports is None:
            # Default ports: Paper TWS, Live TWS, Paper Gateway, Live Gateway
            self.ports = [7497, 7496, 4002, 4001]
        if self.storage is None:
            self.storage = StorageConfig()


def load_storage_config_from_env() -> StorageConfig:
    """Load storage configuration from environment variables"""
    config = StorageConfig()
    
    # Enable/disable features
    config.enable_storage = os.getenv("IB_STREAM_ENABLE_STORAGE", "true").lower() == "true"
    config.enable_json = os.getenv("IB_STREAM_ENABLE_JSON", "true").lower() == "true"
    config.enable_protobuf = os.getenv("IB_STREAM_ENABLE_PROTOBUF", "true").lower() == "true"
    config.enable_postgres_index = os.getenv("IB_STREAM_ENABLE_POSTGRES", "true").lower() == "true"
    config.enable_client_stream_storage = os.getenv("IB_STREAM_ENABLE_CLIENT_STREAM_STORAGE", "true").lower() == "true"
    
    # Storage paths
    storage_base = os.getenv("IB_STREAM_STORAGE_PATH")
    if storage_base:
        config.storage_base_path = Path(storage_base)
        
    json_path = os.getenv("IB_STREAM_JSON_PATH")
    if json_path:
        config.json_storage_path = Path(json_path)
        
    protobuf_path = os.getenv("IB_STREAM_PROTOBUF_PATH")
    if protobuf_path:
        config.protobuf_storage_path = Path(protobuf_path)
    
    # PostgreSQL configuration
    config.postgres_url = os.getenv("IB_STREAM_POSTGRES_URL", config.postgres_url)
    config.postgres_schema = os.getenv("IB_STREAM_POSTGRES_SCHEMA", config.postgres_schema)
    
    # Performance settings
    config.write_batch_size = int(os.getenv("IB_STREAM_BATCH_SIZE", config.write_batch_size))
    config.write_batch_timeout_seconds = float(os.getenv("IB_STREAM_BATCH_TIMEOUT", config.write_batch_timeout_seconds))
    config.max_write_queue_size = int(os.getenv("IB_STREAM_QUEUE_SIZE", config.max_write_queue_size))
    config.max_concurrent_writers = int(os.getenv("IB_STREAM_WRITERS", config.max_concurrent_writers))
    
    # File rotation
    config.rotation_interval_hours = int(os.getenv("IB_STREAM_ROTATION_HOURS", config.rotation_interval_hours))
    config.max_file_size_mb = int(os.getenv("IB_STREAM_MAX_FILE_SIZE", config.max_file_size_mb))
    
    # Retention
    config.json_retention_days = int(os.getenv("IB_STREAM_JSON_RETENTION", config.json_retention_days))
    config.protobuf_retention_days = int(os.getenv("IB_STREAM_PROTOBUF_RETENTION", config.protobuf_retention_days))
    config.health_records_retention_days = int(os.getenv("IB_STREAM_HEALTH_RETENTION", config.health_records_retention_days))
    
    # Metrics
    config.enable_metrics = os.getenv("IB_STREAM_ENABLE_METRICS", "true").lower() == "true"
    config.metrics_window_size = int(os.getenv("IB_STREAM_METRICS_WINDOW", config.metrics_window_size))
    config.health_check_interval_seconds = int(os.getenv("IB_STREAM_HEALTH_INTERVAL", config.health_check_interval_seconds))
    
    # Tracked contracts
    config.max_tracked_contracts = int(os.getenv("IB_STREAM_MAX_TRACKED", config.max_tracked_contracts))
    config.background_stream_reconnect_delay = int(os.getenv("IB_STREAM_RECONNECT_DELAY", config.background_stream_reconnect_delay))
    
    # Parse tracked contracts from environment
    # Format: "contract_id:symbol:tick_types:buffer_hours,contract_id:symbol:tick_types:buffer_hours"
    # Example: "265598:AAPL:bid_ask;last:1,711280073:MNQ:bid_ask;last:2"
    tracked_env = os.getenv("IB_STREAM_TRACKED_CONTRACTS")
    if tracked_env:
        config.tracked_contracts = _parse_tracked_contracts_env(tracked_env)
    
    return config


def _parse_tracked_contracts_env(env_value: str) -> List[TrackedContract]:
    """Parse tracked contracts from environment variable string"""
    contracts = []
    
    try:
        for contract_str in env_value.split(','):
            contract_str = contract_str.strip()
            if not contract_str:
                continue
                
            parts = contract_str.split(':')
            if len(parts) < 2:
                raise ValueError(f"Invalid contract format: {contract_str}. Expected contract_id:symbol[:tick_types[:buffer_hours]]")
            
            contract_id = int(parts[0])
            symbol = parts[1]
            
            # Parse tick types (default: bid_ask,last)
            tick_types = ["bid_ask", "last"]
            if len(parts) > 2 and parts[2]:
                tick_types = [t.strip() for t in parts[2].split(';') if t.strip()]
            
            # Parse buffer hours (default: 1)
            buffer_hours = 1
            if len(parts) > 3 and parts[3]:
                buffer_hours = int(parts[3])
            
            contract = TrackedContract(
                contract_id=contract_id,
                symbol=symbol,
                tick_types=tick_types,
                buffer_hours=buffer_hours
            )
            contracts.append(contract)
            
    except Exception as e:
        raise ValueError(f"Failed to parse tracked contracts from env: {e}")
    
    return contracts


def load_config_from_env() -> ServerConfig:
    """Load configuration from environment variables"""
    config = ServerConfig()

    # TWS Connection
    config.client_id = int(os.getenv("IB_STREAM_CLIENT_ID", config.client_id))
    config.host = os.getenv("IB_STREAM_HOST", config.host)

    # Parse ports from comma-separated string
    ports_env = os.getenv("IB_STREAM_PORTS")
    if ports_env:
        config.ports = [int(p.strip()) for p in ports_env.split(",")]

    # Streaming Limits
    config.max_concurrent_streams = int(os.getenv("IB_STREAM_MAX_STREAMS", config.max_concurrent_streams))
    # Handle timeout - can be None for no timeout
    timeout_env = os.getenv("IB_STREAM_STREAM_TIMEOUT")
    if timeout_env:
        config.default_timeout_seconds = int(timeout_env)
    config.buffer_size = int(os.getenv("IB_STREAM_BUFFER_SIZE", config.buffer_size))

    # Connection Management
    config.reconnect_attempts = int(os.getenv("IB_STREAM_RECONNECT_ATTEMPTS", config.reconnect_attempts))
    config.connection_timeout = int(os.getenv("IB_STREAM_CONNECTION_TIMEOUT", config.connection_timeout))
    config.heartbeat_interval = int(os.getenv("IB_STREAM_HEARTBEAT_INTERVAL", config.heartbeat_interval))

    # Server Settings
    config.server_host = os.getenv("HOST", config.server_host)
    config.server_port = int(os.getenv("PORT", config.server_port))

    # Logging
    config.log_level = os.getenv("IB_STREAM_LOG_LEVEL", config.log_level)
    config.log_format = os.getenv("IB_STREAM_LOG_FORMAT", config.log_format)
    
    # Storage configuration
    config.storage = load_storage_config_from_env()

    return config


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


def load_environment_file(env_file_path: Optional[str] = None) -> None:
    """Load environment variables from a .env file"""
    if env_file_path is None:
        # Try to detect environment from IB_STREAM_ENV or default to production
        env_name = os.getenv("IB_STREAM_ENV", "production")
        env_file_path = f"config/{env_name}.env"
    
    env_path = Path(env_file_path)
    if not env_path.exists():
        # Try relative to script directory
        script_dir = Path(__file__).parent.parent.parent
        env_path = script_dir / env_file_path
    
    if not env_path.exists():
        return  # No environment file found, use existing env vars
    
    try:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Parse KEY=VALUE format
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # Handle variable substitution ${VAR:-default}
                    if value.startswith('${') and ':-' in value and value.endswith('}'):
                        var_expr = value[2:-1]  # Remove ${ and }
                        var_name, default_value = var_expr.split(':-', 1)
                        value = os.getenv(var_name, default_value)
                    
                    # Only set if not already set (env vars take precedence)
                    if key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        print(f"Warning: Failed to load environment file {env_path}: {e}")


def create_config() -> ServerConfig:
    """Create and validate configuration"""
    # Load instance-specific configuration first
    load_environment_file("config/instance.env")
    
    # Load environment file (if present)
    load_environment_file()
    
    config = load_config_from_env()
    validate_config(config)
    return config


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
