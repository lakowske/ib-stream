"""
Configuration management for IB Contract Lookup Service - V2 (New System).

This module provides the new configuration system while maintaining backward
compatibility with the existing contract lookup service.
"""

import logging
from typing import Dict, Any

from ib_util.config import create_compatible_config, IBBaseConfig

logger = logging.getLogger(__name__)


class ContractConfig:
    """
    Adapter class that wraps the new IBBaseConfig for ib-contract compatibility.
    
    This maintains the same interface as the legacy configuration while using
    the new type-safe configuration system underneath.
    """
    
    def __init__(self, service_name: str = "ib-contract"):
        """Initialize contract configuration using new system."""
        self._base_config = create_compatible_config(service_name)
        self._service_name = service_name
        
        # Log configuration source
        logger.info(f"Contract configuration initialized for {service_name}")
        logger.info(f"Environment: {self._base_config.environment}")
        logger.info(f"TWS Host: {self._base_config.connection.host}")
        logger.info(f"Client ID: {self._base_config.connection.client_id}")
        logger.info(f"Server Port: {self._base_config.server.port}")
    
    # Properties that maintain backward compatibility with existing code
    
    @property
    def host(self) -> str:
        """TWS connection host."""
        return self._base_config.connection.host
    
    @property
    def ports(self) -> list:
        """TWS connection ports."""
        return self._base_config.connection.ports
    
    @property
    def client_id(self) -> int:
        """TWS client ID."""
        return self._base_config.connection.client_id
    
    @property
    def server_port(self) -> int:
        """HTTP server port."""
        return self._base_config.server.port
    
    @property
    def server_host(self) -> str:
        """HTTP server bind address."""
        return self._base_config.server.host
    
    @property
    def log_level(self) -> str:
        """Logging level."""
        return self._base_config.server.log_level
    
    @property
    def connection_timeout(self) -> int:
        """Connection timeout in seconds."""
        return self._base_config.connection.connection_timeout
    
    # Access to underlying configuration
    
    @property
    def base_config(self) -> IBBaseConfig:
        """Access to the underlying IBBaseConfig."""
        return self._base_config
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for legacy compatibility."""
        return {
            'host': self.host,
            'ports': self.ports,
            'client_id': self.client_id,
            'server_port': self.server_port,
            'server_host': self.server_host,
            'log_level': self.log_level,
            'connection_timeout': self.connection_timeout,
            'environment': str(self._base_config.environment),
            'project_root': self._base_config.project_root,
        }


def create_config() -> ContractConfig:
    """
    Create configuration using the new system.
    
    This is the main entry point for ib-contract configuration.
    It replaces any legacy create_config() function.
    """
    return ContractConfig("ib-contract")


def create_legacy_compatible_config():
    """
    Create a configuration that's compatible with the legacy system.
    
    This can be used as a drop-in replacement for the old configuration
    during the migration period.
    """
    config = create_config()
    
    # Return an object that has all the expected attributes
    class LegacyCompatConfig:
        def __init__(self, contract_config: ContractConfig):
            self._contract_config = contract_config
            
            # Copy all properties to maintain compatibility
            self.host = contract_config.host
            self.ports = contract_config.ports
            self.client_id = contract_config.client_id
            self.server_port = contract_config.server_port
            self.server_host = contract_config.server_host
            self.log_level = contract_config.log_level
            self.connection_timeout = contract_config.connection_timeout
        
        def to_dict(self):
            return self._contract_config.to_dict()
    
    return LegacyCompatConfig(config)


if __name__ == "__main__":
    # Test the new configuration system
    import json
    
    config = create_config()
    print("New Contract Configuration System Test:")
    print(f"Service: {config._service_name}")
    print(f"Environment: {config.base_config.environment}")
    print(f"TWS Host: {config.host}")
    print(f"TWS Ports: {config.ports}")
    print(f"Client ID: {config.client_id}")
    print(f"Server Port: {config.server_port}")
    print(f"Connection Timeout: {config.connection_timeout}")
    
    print("\nLegacy Compatibility Test:")
    legacy_config = create_legacy_compatible_config()
    print(f"Legacy Host: {legacy_config.host}")
    print(f"Legacy Client ID: {legacy_config.client_id}")
    print(f"Legacy Server Port: {legacy_config.server_port}")
    
    print("\nConfiguration Dictionary:")
    print(json.dumps(config.to_dict(), indent=2, default=str))