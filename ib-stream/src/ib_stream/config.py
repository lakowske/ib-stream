"""
Configuration management for IB Stream API Server.
"""

import os
from dataclasses import dataclass
from typing import List


@dataclass
class ServerConfig:
    """Configuration for the API server"""

    # TWS Connection
    client_id: int = 2
    host: str = "127.0.0.1"
    ports: List[int] = None

    # Streaming Limits
    max_concurrent_streams: int = 50
    default_timeout_seconds: int = 300
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

    def __post_init__(self):
        if self.ports is None:
            # Default ports: Paper TWS, Live TWS, Paper Gateway, Live Gateway
            self.ports = [7497, 7496, 4002, 4001]


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
    config.default_timeout_seconds = int(os.getenv("IB_STREAM_STREAM_TIMEOUT", config.default_timeout_seconds))
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

    return config


def validate_config(config: ServerConfig) -> None:
    """Validate configuration values"""
    if config.client_id < 0:
        raise ValueError("Client ID must be non-negative")

    if config.max_concurrent_streams < 1:
        raise ValueError("Maximum concurrent streams must be at least 1")

    if config.default_timeout_seconds < 1:
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


def create_config() -> ServerConfig:
    """Create and validate configuration"""
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
