"""
Configuration management for IB Stream API Server - V2 (New System).

This module provides the new configuration system while maintaining backward
compatibility with the existing config.py module.
"""

import os
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from ib_util.config import create_compatible_config, IBBaseConfig
from ib_util.config.service_adapter import BaseServiceAdapter, BaseStorageConfigAdapter

logger = logging.getLogger(__name__)


class StreamConfig(BaseServiceAdapter):
    """
    Configuration adapter for ib-stream service.
    
    This maintains the same interface as the legacy configuration while using
    the new type-safe configuration system underneath. Now inherits from
    BaseServiceAdapter to eliminate code duplication.
    """
    
    def __init__(self, service_name: str = "ib-stream"):
        """Initialize stream configuration using new system."""
        super().__init__(service_name)
        
        # Log configuration source
        logger.info(f"Stream configuration initialized for {service_name}")
        logger.info(f"Environment: {self._base_config.environment}")
        logger.info(f"TWS Host: {self._base_config.connection.host}")
        logger.info(f"Server Port: {self._base_config.server.port}")
        logger.info(f"Storage Enabled: {self._base_config.storage.enable_storage}")
    
    # Stream-specific properties (common ones inherited from BaseServiceAdapter)
    
    @property
    def max_concurrent_streams(self) -> int:
        """Maximum concurrent streams."""
        return self._base_config.server.max_streams
    
    @property
    def default_timeout_seconds(self) -> Optional[int]:
        """Default timeout for operations."""
        # This is derived from connection timeout
        return self._base_config.connection.connection_timeout if self._base_config.connection.connection_timeout > 0 else None
    
    # Storage configuration
    
    @property
    def storage(self) -> 'StorageConfigAdapter':
        """Storage configuration."""
        return StorageConfigAdapter(self._base_config.storage)
    
    # Access to storage configuration
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for legacy compatibility."""
        # Get base dictionary from parent class
        result = super().to_dict()
        
        # Add stream-specific fields
        result.update({
            'max_concurrent_streams': self.max_concurrent_streams,
            'default_timeout_seconds': self.default_timeout_seconds,
            'storage': self.storage.to_dict(),
        })
        
        return result


class StorageConfigAdapter(BaseStorageConfigAdapter):
    """
    Stream-specific storage configuration adapter.
    
    Extends the base storage adapter with ib-stream specific functionality
    like tracked contracts and background streaming.
    """
    
    # Stream-specific storage properties (common ones inherited from BaseStorageConfigAdapter)
    
    @property
    def enable_postgres_index(self) -> bool:
        return self._storage_config.enable_postgres
    
    @property
    def enable_metrics(self) -> bool:
        return self._storage_config.enable_metrics
    
    @property
    def enable_client_stream_storage(self) -> bool:
        return getattr(self._storage_config, 'enable_client_stream_storage', True)
    
    @property
    def enable_background_streaming(self) -> bool:
        return self._storage_config.enable_background_streaming
    
    @property
    def tracked_contracts(self) -> List['TrackedContractAdapter']:
        """Parse tracked contracts from configuration."""
        contracts_str = self._storage_config.tracked_contracts
        if not contracts_str:
            return []
        
        contracts = []
        try:
            # Parse format: "contract_id:symbol:tick_types:buffer_hours"
            for contract_str in contracts_str.split(','):
                if ':' in contract_str:
                    parts = contract_str.strip().split(':')
                    if len(parts) >= 4:
                        contract_id = int(parts[0])
                        symbol = parts[1]
                        tick_types = parts[2].split(';')
                        buffer_hours = int(parts[3])
                        
                        contracts.append(TrackedContractAdapter(
                            contract_id=contract_id,
                            symbol=symbol,
                            tick_types=tick_types,
                            buffer_hours=buffer_hours
                        ))
        except Exception as e:
            logger.warning(f"Failed to parse tracked contracts '{contracts_str}': {e}")
        
        return contracts
    
    @property
    def background_stream_reconnect_delay(self) -> int:
        return getattr(self._storage_config, 'background_reconnect_delay', 30)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for legacy compatibility."""
        # Start with base storage configuration
        result = super().to_dict()
        
        # Add stream-specific storage fields
        result.update({
            'enable_postgres_index': self.enable_postgres_index,
            'enable_metrics': self.enable_metrics,
            'enable_client_stream_storage': self.enable_client_stream_storage,
            'enable_background_streaming': self.enable_background_streaming,
            'tracked_contracts': [c.to_dict() for c in self.tracked_contracts],
            'background_stream_reconnect_delay': self.background_stream_reconnect_delay,
        })
        
        return result


@dataclass
class TrackedContractAdapter:
    """Adapter for tracked contract configuration."""
    
    contract_id: int
    symbol: str
    tick_types: List[str]
    buffer_hours: int
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'contract_id': self.contract_id,
            'symbol': self.symbol,
            'tick_types': self.tick_types,
            'buffer_hours': self.buffer_hours,
            'enabled': self.enabled,
        }


def create_config() -> StreamConfig:
    """
    Create configuration using the new system.
    
    This is the main entry point for ib-stream configuration.
    It replaces the legacy create_config() function.
    """
    return StreamConfig("ib-stream")


def create_legacy_compatible_config():
    """
    Create a configuration that's compatible with the legacy system.
    
    This can be used as a drop-in replacement for the old configuration
    during the migration period.
    """
    config = create_config()
    
    # Return an object that has all the expected attributes
    class LegacyCompatConfig:
        def __init__(self, stream_config: StreamConfig):
            self._stream_config = stream_config
            
            # Copy all properties to maintain compatibility
            self.host = stream_config.host
            self.ports = stream_config.ports
            self.client_id = stream_config.client_id
            self.server_port = stream_config.server_port
            self.server_host = stream_config.server_host
            self.log_level = stream_config.log_level
            self.max_concurrent_streams = stream_config.max_concurrent_streams
            self.default_timeout_seconds = stream_config.default_timeout_seconds
            self.storage = stream_config.storage
        
        def to_dict(self):
            return self._stream_config.to_dict()
    
    return LegacyCompatConfig(config)


# For backward compatibility, also export the function with the legacy name
def load_config_from_env():
    """Legacy function name - redirects to new system."""
    logger.info("Using legacy load_config_from_env() - consider migrating to create_config()")
    return create_legacy_compatible_config()


if __name__ == "__main__":
    # Test the new configuration system
    import json
    
    config = create_config()
    print("New Configuration System Test:")
    print(f"Service: {config._service_name}")
    print(f"Environment: {config.base_config.environment}")
    print(f"TWS Host: {config.host}")
    print(f"TWS Ports: {config.ports}")
    print(f"Client ID: {config.client_id}")
    print(f"Server Port: {config.server_port}")
    print(f"Storage Enabled: {config.storage.enable_storage}")
    print(f"Tracked Contracts: {len(config.storage.tracked_contracts)}")
    
    print("\nLegacy Compatibility Test:")
    legacy_config = create_legacy_compatible_config()
    print(f"Legacy Host: {legacy_config.host}")
    print(f"Legacy Port: {legacy_config.server_port}")
    print(f"Legacy Storage: {legacy_config.storage.enable_storage}")
    
    print("\nConfiguration Dictionary:")
    print(json.dumps(config.to_dict(), indent=2, default=str))