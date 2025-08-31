#!/usr/bin/env python3
"""
Configuration System v3 - Clean Slate YAML-Based Configuration

This is a complete rewrite of the configuration system with:
- YAML file-based configuration
- Hierarchical overrides (base -> environment -> service)
- Minimal environment variable dependency
- Clear validation and error reporting
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class Environment(str, Enum):
    """Supported environments"""
    DEVELOPMENT = "development" 
    PRODUCTION = "production"


class ProjectConfig(BaseModel):
    """Project-level configuration"""
    name: str = "ib-stream"
    version: str = "3.0.0"
    environment: Environment = Environment.DEVELOPMENT


class GatewayConfig(BaseModel):
    """IB Gateway connection configuration"""
    host: str = "192.168.0.60"
    ports: List[int] = Field(default_factory=lambda: [4002, 4001])
    connection_timeout: int = 10
    reconnect_attempts: int = 5


class StorageFormatsConfig(BaseModel):
    """Storage format configuration"""
    v2_json: bool = False
    v2_protobuf: bool = False
    v3_json: bool = True
    v3_protobuf: bool = True


class StorageConfig(BaseModel):
    """Storage system configuration"""
    enabled: bool = True
    base_path: str = "storage-dev"
    formats: StorageFormatsConfig = Field(default_factory=StorageFormatsConfig)
    enable_postgres: bool = False
    enable_metrics: bool = True
    buffer_size: int = 100
    max_file_size_mb: int = 100


class LoggingConfig(BaseModel):
    """Logging configuration"""
    level: str = "DEBUG"
    format: str = "detailed"
    file_rotation: str = "daily"
    
    @field_validator('level')
    @classmethod
    def validate_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Invalid log level: {v}. Must be one of {valid_levels}')
        return v.upper()


class PerformanceConfig(BaseModel):
    """Performance and resource configuration"""
    max_concurrent_streams: int = 10
    default_timeout_seconds: Optional[int] = None


class ServerConfig(BaseModel):
    """HTTP server configuration"""
    host: str = "0.0.0.0"
    port: int = 8851
    enable_cors: bool = True
    enable_websockets: bool = True


class ClientConfig(BaseModel):
    """IB client configuration"""
    id: int = 101


class TrackedContractConfig(BaseModel):
    """Configuration for tracked contracts"""
    contract_id: int
    symbol: str
    tick_types: List[str]
    buffer_hours: int = 24


class StreamingConfig(BaseModel):
    """Streaming-specific configuration"""
    enable_background_streaming: bool = False
    tracked_contracts: List[TrackedContractConfig] = Field(default_factory=list)


class CacheConfig(BaseModel):
    """Cache configuration for contract service"""
    duration_days: int = 1
    memory_cache_size: int = 1000
    file_cache_enabled: bool = True


class ServiceConfig(BaseModel):
    """Service-specific configuration"""
    name: str
    type: str
    server: ServerConfig = Field(default_factory=ServerConfig)
    client: ClientConfig = Field(default_factory=ClientConfig)
    streaming: Optional[StreamingConfig] = None
    cache: Optional[CacheConfig] = None


class AppConfig(BaseModel):
    """Complete application configuration"""
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    service: ServiceConfig


class ConfigLoader:
    """YAML-based configuration loader with hierarchical overrides"""
    
    def __init__(self, config_root: Optional[str] = None):
        """
        Initialize configuration loader.
        
        Args:
            config_root: Path to configuration directory. Defaults to ./config
        """
        self.config_root = Path(config_root or "config")
        if not self.config_root.exists():
            raise FileNotFoundError(f"Configuration directory not found: {self.config_root}")
    
    def load_yaml_file(self, filepath: Path) -> Dict[str, Any]:
        """Load YAML file and return parsed data"""
        if not filepath.exists():
            return {}
        
        try:
            with open(filepath, 'r') as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {filepath}: {e}")
        except Exception as e:
            raise IOError(f"Error reading {filepath}: {e}")
    
    def merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two configuration dictionaries"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.merge_configs(result[key], value)
            else:
                result[key] = value
                
        return result
    
    def get_environment(self) -> Environment:
        """Get current environment from environment variable"""
        env_str = os.getenv('IB_ENVIRONMENT', 'development').lower()
        try:
            return Environment(env_str)
        except ValueError:
            raise ValueError(f"Invalid environment: {env_str}. Must be 'development' or 'production'")
    
    def load_service_config(self, service_name: str) -> AppConfig:
        """
        Load complete configuration for a service.
        
        Hierarchy:
        1. config/base.yaml (base configuration)
        2. config/{environment}.yaml (environment overrides)
        3. config/services/{service}.yaml (service-specific config)
        4. Environment variables (final overrides)
        """
        environment = self.get_environment()
        
        # Load base configuration
        base_config = self.load_yaml_file(self.config_root / "base.yaml")
        
        # Load environment overrides
        env_config = self.load_yaml_file(self.config_root / f"{environment.value}.yaml")
        merged_config = self.merge_configs(base_config, env_config)
        
        # Load service-specific configuration
        service_config = self.load_yaml_file(self.config_root / "services" / f"{service_name}.yaml")
        merged_config = self.merge_configs(merged_config, service_config)
        
        # Apply environment-specific service overrides
        if environment.value in service_config:
            env_service_config = service_config[environment.value]
            merged_config = self.merge_configs(merged_config, env_service_config)
        
        # Apply environment variable overrides
        self.apply_environment_overrides(merged_config)
        
        # Ensure we have a service configuration
        if 'service' not in merged_config:
            merged_config['service'] = {'name': service_name, 'type': 'generic'}
        
        try:
            return AppConfig(**merged_config)
        except Exception as e:
            raise ValueError(f"Configuration validation failed for {service_name}: {e}")
    
    def apply_environment_overrides(self, config: Dict[str, Any]):
        """Apply environment variable overrides to configuration"""
        # Gateway overrides
        if os.getenv('IB_GATEWAY_HOST'):
            config.setdefault('gateway', {})['host'] = os.getenv('IB_GATEWAY_HOST')
            
        if os.getenv('IB_GATEWAY_PORTS'):
            config.setdefault('gateway', {})['ports'] = [
                int(p.strip()) for p in os.getenv('IB_GATEWAY_PORTS').split(',')
            ]
            
        # Client ID override
        if os.getenv('IB_CLIENT_ID'):
            config.setdefault('service', {}).setdefault('client', {})['id'] = int(os.getenv('IB_CLIENT_ID'))
            
        # Server port override
        if os.getenv('IB_SERVER_PORT'):
            config.setdefault('service', {}).setdefault('server', {})['port'] = int(os.getenv('IB_SERVER_PORT'))


def load_config(service_name: str, config_root: Optional[str] = None) -> AppConfig:
    """
    Convenience function to load configuration for a service.
    
    Args:
        service_name: Name of the service (e.g., 'ib-stream', 'ib-contract')
        config_root: Optional path to configuration directory
        
    Returns:
        Complete validated configuration for the service
    """
    loader = ConfigLoader(config_root)
    return loader.load_service_config(service_name)


def validate_config(service_name: str, config_root: Optional[str] = None) -> bool:
    """
    Validate configuration for a service without loading it.
    
    Returns:
        True if configuration is valid, False otherwise
    """
    try:
        load_config(service_name, config_root)
        return True
    except Exception as e:
        print(f"Configuration validation failed: {e}")
        return False


if __name__ == "__main__":
    # CLI for testing configuration
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python config_v3.py <service_name>")
        sys.exit(1)
        
    service_name = sys.argv[1]
    
    try:
        config = load_config(service_name)
        print(f"Configuration loaded successfully for {service_name}")
        print(f"Environment: {config.project.environment}")
        print(f"Gateway: {config.gateway.host}:{config.gateway.ports}")
        print(f"Service: {config.service.name} on port {config.service.server.port}")
        print(f"Client ID: {config.service.client.id}")
        print(f"Storage: {config.storage.base_path} (enabled: {config.storage.enabled})")
        
    except Exception as e:
        print(f"Configuration error: {e}")
        sys.exit(1)