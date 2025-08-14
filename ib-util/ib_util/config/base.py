"""
Base configuration classes for IB projects.

Provides type-safe, validated configuration classes that can be shared
across ib-stream, ib-contract, ib-studies, and other projects.
"""

import os
from enum import Enum
from typing import List, Optional, Dict, Any
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class IBEnvironment(str, Enum):
    """Supported deployment environments."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    STAGING = "staging"
    TESTING = "testing"


class IBConnectionConfig(BaseSettings):
    """Interactive Brokers connection configuration."""
    
    host: str = Field(default="localhost", description="TWS/Gateway host")
    ports: List[int] = Field(default=[4002], description="TWS/Gateway ports to try")
    client_id: int = Field(description="IB API client ID")
    connection_timeout: int = Field(default=10, description="Connection timeout in seconds")
    reconnect_attempts: int = Field(default=5, description="Number of reconnection attempts")
    
    model_config = SettingsConfigDict(
        env_prefix="IB_",
        # Disable JSON parsing for lists to allow custom parsing
        env_parse_none_str="null"
    )
        
    @field_validator('ports', mode='before')
    @classmethod
    def parse_ports(cls, v):
        """Parse ports from string or list."""
        if isinstance(v, str):
            # Handle comma-separated string like "4002,4001"
            return [int(port.strip()) for port in v.split(',')]
        elif isinstance(v, int):
            # Handle single integer
            return [v]
        elif isinstance(v, list):
            # Handle list (ensure all are integers)
            return [int(port) for port in v]
        return v
    
    @field_validator('ports')
    @classmethod
    def validate_ports(cls, v):
        """Ensure all ports are valid."""
        for port in v:
            if not (1 <= port <= 65535):
                raise ValueError(f"Invalid port: {port}")
        return v
    
    @field_validator('client_id')
    @classmethod
    def validate_client_id(cls, v):
        """Ensure client ID is in valid range."""
        if not (1 <= v <= 32767):
            raise ValueError(f"Client ID must be between 1 and 32767, got: {v}")
        return v


class IBStorageConfig(BaseSettings):
    """Storage configuration for market data."""
    
    enable_storage: bool = Field(default=True, description="Enable data storage")
    storage_path: str = Field(default="storage", description="Base storage directory")
    enable_json: bool = Field(default=True, description="Enable JSON storage")
    enable_protobuf: bool = Field(default=True, description="Enable Protobuf storage") 
    enable_postgres: bool = Field(default=False, description="Enable PostgreSQL indexing")
    enable_metrics: bool = Field(default=True, description="Enable storage metrics")
    enable_v2_storage: bool = Field(default=True, description="Enable v2 legacy storage format")
    enable_v3_storage: bool = Field(default=True, description="Enable v3 optimized storage")
    
    # Background streaming
    enable_background_streaming: bool = Field(default=False, description="Enable background streaming")
    tracked_contracts: str = Field(default="", description="Tracked contracts for background streaming")
    background_reconnect_delay: int = Field(default=30, description="Background streaming reconnect delay")
    
    # Performance settings
    buffer_size: int = Field(default=100, description="Storage buffer size")
    max_file_size_mb: int = Field(default=100, description="Maximum file size in MB")
    
    model_config = SettingsConfigDict(env_prefix="IB_STREAM_")
        
    @field_validator('storage_path')
    @classmethod
    def validate_storage_path(cls, v):
        """Ensure storage path is valid."""
        path = Path(v)
        if path.is_absolute():
            # For absolute paths, check if parent exists
            if not path.parent.exists():
                raise ValueError(f"Parent directory does not exist: {path.parent}")
        return str(path)


class IBServerConfig(BaseSettings):
    """HTTP server configuration."""
    
    host: str = Field(default="0.0.0.0", description="Server bind address")
    port: int = Field(description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")
    max_streams: int = Field(default=50, description="Maximum concurrent streams")
    enable_cors: bool = Field(default=True, description="Enable CORS")
    
    model_config = SettingsConfigDict(env_prefix="IB_STREAM_")
        
    @field_validator('port')
    @classmethod
    def validate_port(cls, v):
        """Ensure port is valid."""
        if not (1 <= v <= 65535):
            raise ValueError(f"Invalid port: {v}")
        return v
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()


class IBBaseConfig(BaseSettings):
    """Base configuration class for all IB services."""
    
    # Environment and service identification
    environment: IBEnvironment = Field(default=IBEnvironment.DEVELOPMENT, description="Deployment environment")
    service_name: str = Field(description="Service name (e.g., 'ib-stream', 'ib-contract')")
    project_root: str = Field(default=".", description="Project root directory")
    
    # Component configurations
    connection: IBConnectionConfig = Field(default_factory=IBConnectionConfig)
    storage: IBStorageConfig = Field(default_factory=IBStorageConfig)
    server: IBServerConfig = Field(default_factory=IBServerConfig)
    
    # Instance identification (for multi-instance deployments)
    instance_id: Optional[str] = Field(default=None, description="Unique instance identifier")
    
    model_config = SettingsConfigDict(arbitrary_types_allowed=True)
    
    @field_validator('project_root')
    @classmethod
    def validate_project_root(cls, v):
        """Ensure project root exists."""
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Project root does not exist: {path}")
        return str(path.absolute())
    
    def get_config_dir(self) -> Path:
        """Get the configuration directory for this service."""
        return Path(self.project_root) / "config"
    
    def get_storage_path(self) -> Path:
        """Get the full storage path."""
        if Path(self.storage.storage_path).is_absolute():
            return Path(self.storage.storage_path)
        return Path(self.project_root) / self.storage.storage_path
    
    def get_instance_suffix(self) -> str:
        """Get suffix for instance-specific resources."""
        if self.instance_id:
            return f"-{self.instance_id}"
        return ""
    
    def to_env_dict(self) -> Dict[str, str]:
        """Convert configuration to environment variables dictionary."""
        env_dict = {}
        
        # Service-level variables
        env_dict["IB_ENVIRONMENT"] = self.environment.value
        env_dict["IB_SERVICE_NAME"] = self.service_name
        env_dict["PROJECT_ROOT"] = self.project_root
        
        # Connection variables
        env_dict["IB_HOST"] = self.connection.host
        env_dict["IB_PORTS"] = ",".join(map(str, self.connection.ports))
        env_dict["IB_CLIENT_ID"] = str(self.connection.client_id)
        env_dict["IB_CONNECTION_TIMEOUT"] = str(self.connection.connection_timeout)
        env_dict["IB_RECONNECT_ATTEMPTS"] = str(self.connection.reconnect_attempts)
        
        # Storage variables
        env_dict["IB_STREAM_ENABLE_STORAGE"] = str(self.storage.enable_storage).lower()
        env_dict["IB_STREAM_STORAGE_PATH"] = self.storage.storage_path
        env_dict["IB_STREAM_ENABLE_JSON"] = str(self.storage.enable_json).lower()
        env_dict["IB_STREAM_ENABLE_PROTOBUF"] = str(self.storage.enable_protobuf).lower()
        env_dict["IB_STREAM_ENABLE_POSTGRES"] = str(self.storage.enable_postgres).lower()
        env_dict["IB_STREAM_ENABLE_METRICS"] = str(self.storage.enable_metrics).lower()
        env_dict["IB_STREAM_ENABLE_V2_STORAGE"] = str(self.storage.enable_v2_storage).lower()
        env_dict["IB_STREAM_ENABLE_V3_STORAGE"] = str(self.storage.enable_v3_storage).lower()
        env_dict["IB_STREAM_ENABLE_BACKGROUND_STREAMING"] = str(self.storage.enable_background_streaming).lower()
        env_dict["IB_STREAM_TRACKED_CONTRACTS"] = self.storage.tracked_contracts
        env_dict["IB_STREAM_BUFFER_SIZE"] = str(self.storage.buffer_size)
        
        # Server variables
        env_dict["IB_STREAM_HOST"] = self.server.host
        env_dict["IB_STREAM_PORT"] = str(self.server.port)
        env_dict["IB_STREAM_LOG_LEVEL"] = self.server.log_level
        env_dict["IB_STREAM_MAX_STREAMS"] = str(self.server.max_streams)
        
        # Instance ID
        if self.instance_id:
            env_dict["IB_INSTANCE_ID"] = self.instance_id
            
        return env_dict