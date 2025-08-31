#!/usr/bin/env python3
"""
Configuration v3 Adapter for IB-Stream

This adapter bridges the new config v3 YAML system with the existing ib-stream
service interfaces, providing backward compatibility while using the clean new system.
"""

import os
from typing import Dict, Any, List, Optional
from pathlib import Path

# Import the new configuration v3 system directly
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "ib-util"))

# Import config_v3 directly without going through ib_util __init__
import importlib.util
config_v3_path = Path(__file__).parent.parent.parent.parent / "ib-util" / "ib_util" / "config_v3.py"
spec = importlib.util.spec_from_file_location("config_v3", config_v3_path)
config_v3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_v3)

load_config = config_v3.load_config
AppConfig = config_v3.AppConfig


class ConfigV3Adapter:
    """
    Adapter that makes config v3 compatible with existing ib-stream service expectations.
    
    This allows us to use the new YAML-based configuration system while maintaining
    compatibility with existing code that expects the old configuration interface.
    """
    
    def __init__(self, service_name: str = "ib-stream"):
        """Initialize adapter with config v3 system"""
        self.service_name = service_name
        self._config_v3 = load_config(service_name)
        
    def to_legacy_format(self) -> Dict[str, Any]:
        """Convert config v3 to legacy format expected by existing code"""
        config = self._config_v3
        
        return {
            # Connection settings (legacy format)
            'client_id': config.service.client.id,
            'host': config.gateway.host,
            'ports': config.gateway.ports,
            'connection_timeout': config.gateway.connection_timeout,
            'reconnect_attempts': config.gateway.reconnect_attempts,
            
            # Server settings
            'server_port': config.service.server.port,
            'server_host': config.service.server.host,
            'enable_cors': config.service.server.enable_cors,
            
            # Storage settings
            'enable_storage': config.storage.enabled,
            'storage_base_path': config.storage.base_path,
            'enable_json': config.storage.formats.v2_json,
            'enable_protobuf': config.storage.formats.v2_protobuf,
            'enable_v3_json': config.storage.formats.v3_json,
            'enable_v3_protobuf': config.storage.formats.v3_protobuf,
            'enable_postgres_index': config.storage.enable_postgres,
            'enable_metrics': config.storage.enable_metrics,
            'buffer_size': config.storage.buffer_size,
            'max_file_size_mb': config.storage.max_file_size_mb,
            
            # Performance settings
            'max_concurrent_streams': config.performance.max_concurrent_streams,
            'default_timeout_seconds': config.performance.default_timeout_seconds,
            
            # Logging
            'log_level': config.logging.level,
            
            # Streaming settings (if available)
            'enable_background_streaming': (
                config.service.streaming.enable_background_streaming 
                if config.service.streaming else False
            ),
            'tracked_contracts': (
                [self._convert_tracked_contract(tc) for tc in config.service.streaming.tracked_contracts]
                if config.service.streaming else []
            ),
            
            # Environment info
            'environment': str(config.project.environment),
            'project_name': config.project.name,
            'version': config.project.version,
        }
    
    def _convert_tracked_contract(self, tc) -> str:
        """Convert tracked contract config to legacy string format"""
        tick_types_str = ";".join(tc.tick_types)
        return f"{tc.contract_id}:{tc.symbol}:{tick_types_str}:{tc.buffer_hours}"
    
    # Legacy property accessors for compatibility
    @property
    def client_id(self) -> int:
        return self._config_v3.service.client.id
    
    @property 
    def host(self) -> str:
        return self._config_v3.gateway.host
    
    @property
    def ports(self) -> List[int]:
        return self._config_v3.gateway.ports
    
    @property
    def server_port(self) -> int:
        return self._config_v3.service.server.port
    
    @property
    def server_host(self) -> str:
        return self._config_v3.service.server.host
    
    @property
    def max_concurrent_streams(self) -> int:
        return self._config_v3.performance.max_concurrent_streams
    
    @property
    def default_timeout_seconds(self) -> Optional[int]:
        return self._config_v3.performance.default_timeout_seconds
    
    @property
    def storage(self):
        """Storage configuration object compatible with legacy code"""
        return self._StorageConfig(self._config_v3.storage)
    
    class _StorageConfig:
        """Storage configuration wrapper for legacy compatibility"""
        def __init__(self, storage_config):
            self._storage_config = storage_config
            
        @property
        def enable_storage(self) -> bool:
            return self._storage_config.enabled
            
        @property
        def storage_base_path(self) -> str:
            return self._storage_config.base_path
            
        @property
        def enable_json(self) -> bool:
            return self._storage_config.formats.v2_json
            
        @property
        def enable_protobuf(self) -> bool:
            return self._storage_config.formats.v2_protobuf
            
        @property
        def enable_v3_json(self) -> bool:
            return self._storage_config.formats.v3_json
            
        @property
        def enable_v3_protobuf(self) -> bool:
            return self._storage_config.formats.v3_protobuf
            
        @property
        def enable_postgres_index(self) -> bool:
            return self._storage_config.enable_postgres
            
        @property
        def enable_metrics(self) -> bool:
            return self._storage_config.enable_metrics


def create_config_v3() -> ConfigV3Adapter:
    """
    Factory function to create config v3 adapter.
    
    This replaces the old create_legacy_compatible_config function
    and provides the same interface while using the new YAML configuration system.
    """
    return ConfigV3Adapter("ib-stream")


def get_config_v3_state() -> Dict[str, Any]:
    """
    Get current application state using config v3.
    
    This replaces the old get_app_state function with config v3.
    """
    try:
        adapter = ConfigV3Adapter("ib-stream")
        return {
            'config': adapter,
            'config_loaded': True,
            'config_source': 'v3_yaml',
            'environment': str(adapter._config_v3.project.environment),
        }
    except Exception as e:
        return {
            'config': None,
            'config_loaded': False,
            'config_source': 'error',
            'config_error': str(e),
        }


if __name__ == "__main__":
    # Test the adapter
    try:
        adapter = ConfigV3Adapter()
        print("✅ Config v3 Adapter Test:")
        print(f"   Client ID: {adapter.client_id}")
        print(f"   Gateway: {adapter.host}:{adapter.ports}")
        print(f"   Server: {adapter.server_host}:{adapter.server_port}")
        print(f"   Storage: {adapter.storage.storage_base_path} ({'enabled' if adapter.storage.enable_storage else 'disabled'})")
        
        legacy_format = adapter.to_legacy_format()
        print(f"\n📋 Legacy Format Keys: {len(legacy_format)}")
        for key in sorted(legacy_format.keys())[:10]:  # Show first 10 keys
            print(f"   - {key}: {legacy_format[key]}")
        print("   ... (and more)")
        
    except Exception as e:
        print(f"❌ Error: {e}")