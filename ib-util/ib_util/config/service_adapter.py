#!/usr/bin/env python3
"""
Base service adapter classes to eliminate configuration duplication.

This module provides common base classes for service-specific configuration adapters,
following DRY principles and reducing code duplication across services.
"""

from typing import Dict, Any, List
from .compat import create_compatible_config
from .base import IBBaseConfig


class BaseServiceAdapter:
    """
    Base adapter class for service-specific configuration.
    
    This class provides common functionality shared across all service adapters,
    eliminating duplication between ib-stream and ib-contract configurations.
    """
    
    def __init__(self, service_name: str, base_config: IBBaseConfig = None):
        """
        Initialize the service adapter.
        
        Args:
            service_name: Name of the service (e.g., 'ib-stream', 'ib-contract')
            base_config: Optional base configuration, will be created if not provided
        """
        self._service_name = service_name
        self._base_config = base_config or create_compatible_config(service_name)
    
    # Common properties shared by all services
    
    @property
    def host(self) -> str:
        """IB Gateway/TWS host."""
        return self._base_config.connection.host
    
    @property
    def ports(self) -> List[int]:
        """IB Gateway/TWS ports."""
        return self._base_config.connection.ports
    
    @property
    def client_id(self) -> int:
        """IB client ID."""
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
        """
        Convert to dictionary format for legacy compatibility.
        
        This method provides the common dictionary representation.
        Subclasses can override to add service-specific fields.
        """
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


class BaseStorageConfigAdapter:
    """
    Base adapter for storage configuration.
    
    This adapter provides common storage configuration functionality
    that can be extended by service-specific storage adapters.
    """
    
    def __init__(self, storage_config):
        self._storage_config = storage_config
    
    @property
    def enable_storage(self) -> bool:
        """Whether storage is enabled."""
        return self._storage_config.enable_storage
    
    @property
    def storage_base_path(self) -> str:
        """Base path for storage files."""
        return self._storage_config.storage_path
    
    @property
    def enable_json(self) -> bool:
        """Whether JSON output is enabled."""
        return self._storage_config.enable_json
    
    @property
    def enable_protobuf(self) -> bool:
        """Whether protobuf output is enabled."""
        return self._storage_config.enable_protobuf
    
    @property
    def enable_v3_json(self) -> bool:
        """Whether v3 JSON storage is enabled."""
        return getattr(self._storage_config, 'enable_v3_json', True)
    
    @property
    def enable_v3_protobuf(self) -> bool:
        """Whether v3 protobuf storage is enabled."""
        return getattr(self._storage_config, 'enable_v3_protobuf', True)
    
    @property
    def use_compression(self) -> bool:
        """Whether storage compression is enabled."""
        return self._storage_config.use_compression
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert storage configuration to dictionary."""
        return {
            'enable_storage': self.enable_storage,
            'storage_base_path': self.storage_base_path,
            'enable_json': self.enable_json,
            'enable_protobuf': self.enable_protobuf,
            'enable_v3_json': self.enable_v3_json,
            'enable_v3_protobuf': self.enable_v3_protobuf,
            'use_compression': self.use_compression,
        }


# Keep the old name for backward compatibility
StorageConfigAdapter = BaseStorageConfigAdapter


def create_service_adapter(service_name: str) -> BaseServiceAdapter:
    """
    Factory function to create appropriate service adapter.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Configured service adapter instance
    """
    # Import here to avoid circular imports
    if service_name == "ib-stream":
        from ib_stream.config_v2 import StreamConfig
        return StreamConfig(service_name)
    elif service_name == "ib-contract":
        # Import dynamically to handle path issues
        import sys
        import os
        contract_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ib-contract')
        if contract_path not in sys.path:
            sys.path.insert(0, contract_path)
        
        try:
            import config_v2
            return config_v2.ContractConfig(service_name)
        except ImportError:
            # Fallback to base adapter
            return BaseServiceAdapter(service_name)
    else:
        # Default to base adapter for unknown services
        return BaseServiceAdapter(service_name)