"""
Configuration compatibility layer for gradual migration.

Provides backward compatibility with existing configuration systems
while allowing services to gradually adopt the new type-safe configuration.
"""

import os
import logging
from typing import Any, Dict, Optional, List
from pathlib import Path

from .base import IBBaseConfig, IBEnvironment
from .loader import load_config

logger = logging.getLogger(__name__)


class ConfigMigrator:
    """
    Helps migrate from legacy configuration systems to the new type-safe system.
    
    Provides fallback mechanisms and compatibility helpers for existing services.
    """
    
    def __init__(self, service_name: str, legacy_config_path: Optional[str] = None):
        """
        Initialize configuration migrator.
        
        Args:
            service_name: Name of the service being migrated
            legacy_config_path: Path to legacy configuration (optional)
        """
        self.service_name = service_name
        self.legacy_config_path = legacy_config_path
        self._new_config: Optional[IBBaseConfig] = None
        self._legacy_fallback_used = False
    
    def get_config(self) -> IBBaseConfig:
        """
        Get configuration with automatic fallback to legacy system.
        
        Returns:
            Configuration object
        """
        try:
            # Try new configuration system first
            self._new_config = load_config(self.service_name)
            logger.info(f"Using new configuration system for {self.service_name}")
            return self._new_config
            
        except Exception as e:
            logger.warning(f"New configuration failed for {self.service_name}: {e}")
            logger.info("Falling back to legacy configuration...")
            self._legacy_fallback_used = True
            return self._create_legacy_config()
    
    def _create_legacy_config(self) -> IBBaseConfig:
        """Create configuration from legacy environment variables."""
        
        # Load environment files first (like the legacy system does)
        self._load_legacy_env_files()
        
        # Extract legacy environment variables
        legacy_env = self._extract_legacy_env()
        
        # Map to new configuration format
        config_data = {
            'service_name': self.service_name,
            'environment': IBEnvironment(os.getenv('IB_ENVIRONMENT', 'development')),
            'project_root': os.getenv('PROJECT_ROOT', os.getcwd()),
        }
        
        # Map connection settings (always create, use defaults if not found)
        # Handle service-specific environment variables
        if self.service_name == 'ib-contract':
            client_id_key = 'IB_CONTRACTS_CLIENT_ID'
            host_key = 'IB_CONTRACTS_HOST'
        else:
            client_id_key = 'IB_STREAM_CLIENT_ID'
            host_key = 'IB_STREAM_HOST'
        
        config_data['connection'] = {
            'host': legacy_env.get(host_key, legacy_env.get('IB_STREAM_HOST', legacy_env.get('IB_HOST', 'localhost'))),
            'ports': self._parse_ports(legacy_env.get('IB_STREAM_PORTS', legacy_env.get('IB_PORTS', '4002'))),
            'client_id': int(legacy_env.get(client_id_key, legacy_env.get('IB_STREAM_CLIENT_ID', legacy_env.get('IB_CLIENT_ID', '100')))),
        }
        
        # Map server settings (always create, use defaults if not found)
        # Handle service-specific port variables
        if self.service_name == 'ib-contract':
            port_key = 'IB_CONTRACTS_PORT'
        else:
            port_key = 'IB_STREAM_PORT'
        
        config_data['server'] = {
            'host': legacy_env.get('IB_STREAM_BIND_HOST', legacy_env.get('HOST', '0.0.0.0')),
            'port': int(legacy_env.get(port_key, legacy_env.get('IB_STREAM_PORT', legacy_env.get('PORT', '8001')))),
            'log_level': legacy_env.get('IB_STREAM_LOG_LEVEL', 'INFO'),
            'max_streams': int(legacy_env.get('IB_STREAM_MAX_STREAMS', '50')),
        }
        
        # Map storage settings (always create)
        storage_enabled = legacy_env.get('IB_STREAM_ENABLE_STORAGE', 'false').lower() == 'true'
        config_data['storage'] = {
            'enable_storage': storage_enabled,
            'storage_path': legacy_env.get('IB_STREAM_STORAGE_PATH', 'storage'),
            'enable_json': legacy_env.get('IB_STREAM_ENABLE_JSON', 'true').lower() == 'true',
            'enable_protobuf': legacy_env.get('IB_STREAM_ENABLE_PROTOBUF', 'false').lower() == 'true',
            'enable_postgres': legacy_env.get('IB_STREAM_ENABLE_POSTGRES', 'false').lower() == 'true',
            'enable_v2_storage': legacy_env.get('IB_STREAM_ENABLE_V2_STORAGE', 'true').lower() == 'true',
            'enable_v3_storage': legacy_env.get('IB_STREAM_ENABLE_V3_STORAGE', 'true').lower() == 'true',
            'enable_background_streaming': legacy_env.get('IB_STREAM_ENABLE_BACKGROUND_STREAMING', 'false').lower() == 'true',
            'tracked_contracts': legacy_env.get('IB_STREAM_TRACKED_CONTRACTS', ''),
            'buffer_size': int(legacy_env.get('IB_STREAM_BUFFER_SIZE', '100')),
        }
        
        try:
            return IBBaseConfig(**config_data)
        except Exception as e:
            logger.error(f"Failed to create legacy configuration: {e}")
            # Return minimal working configuration
            return IBBaseConfig(
                service_name=self.service_name,
                project_root=os.getcwd(),
                connection={'host': 'localhost', 'ports': [4002], 'client_id': 100},
                server={'host': '0.0.0.0', 'port': 8001},
                storage={'enable_storage': False}
            )
    
    def _load_legacy_env_files(self) -> None:
        """Load legacy environment files like the original system does."""
        try:
            # Use the same logic as the legacy config system
            from ib_util.config_loader import load_environment_file_with_detection
            from pathlib import Path
            
            # Load instance configuration first
            instance_files = [
                "ib-stream/config/instance.env",
                "../ib-stream/config/instance.env", 
                "../config/instance.env",
                "config/instance.env"
            ]
            
            for path in instance_files:
                if Path(path).exists():
                    load_environment_file_with_detection(path)
                    logger.debug(f"Loaded instance config: {path}")
                    break
            
            # Load environment-specific configuration
            load_environment_file_with_detection()
            
        except Exception as e:
            logger.warning(f"Failed to load legacy environment files: {e}")
    
    def _extract_legacy_env(self) -> Dict[str, str]:
        """Extract legacy environment variables."""
        legacy_prefixes = ['IB_STREAM_', 'IB_', 'PROJECT_ROOT', 'HOST', 'PORT']
        legacy_env = {}
        
        for key, value in os.environ.items():
            if any(key.startswith(prefix) for prefix in legacy_prefixes):
                legacy_env[key] = value
        
        return legacy_env
    
    def _parse_ports(self, ports_str: str) -> List[int]:
        """Parse ports from string format."""
        try:
            if ',' in ports_str:
                return [int(p.strip()) for p in ports_str.split(',')]
            else:
                return [int(ports_str)]
        except (ValueError, AttributeError):
            logger.warning(f"Invalid ports format: {ports_str}, using default")
            return [4002]
    
    def is_using_legacy_fallback(self) -> bool:
        """Check if legacy fallback was used."""
        return self._legacy_fallback_used
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get migration status information."""
        return {
            'service_name': self.service_name,
            'using_new_config': not self._legacy_fallback_used,
            'using_legacy_fallback': self._legacy_fallback_used,
            'config_source': 'new' if not self._legacy_fallback_used else 'legacy',
            'recommendations': self._get_migration_recommendations()
        }
    
    def _get_migration_recommendations(self) -> list[str]:
        """Get recommendations for completing migration."""
        recommendations = []
        
        if self._legacy_fallback_used:
            recommendations.extend([
                "Consider creating .env files in config/ directory",
                "Run: python config-migrate.py to generate new configuration",
                "Update service initialization to use ib_util.config.load_config()",
                "Test new configuration before removing legacy environment variables"
            ])
        else:
            recommendations.extend([
                "Migration successful! Consider removing legacy environment variables",
                "Add configuration validation to service startup",
                "Consider using configuration hot-reloading for development"
            ])
        
        return recommendations


def create_compatible_config(service_name: str) -> IBBaseConfig:
    """
    Create configuration with automatic legacy fallback.
    
    This is the main entry point for services migrating to the new system.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Configuration object
    """
    migrator = ConfigMigrator(service_name)
    config = migrator.get_config()
    
    # Log migration status
    status = migrator.get_migration_status()
    if status['using_legacy_fallback']:
        logger.warning(f"Service {service_name} using legacy configuration fallback")
        for rec in status['recommendations'][:2]:  # Show first 2 recommendations
            logger.info(f"Recommendation: {rec}")
    else:
        logger.info(f"Service {service_name} successfully using new configuration system")
    
    return config


def migrate_legacy_config_object(legacy_config: Any) -> IBBaseConfig:
    """
    Migrate an existing legacy configuration object to new format.
    
    Args:
        legacy_config: Legacy configuration object
        
    Returns:
        New configuration object
    """
    # This would be customized based on the specific legacy config format
    # For now, extract what we can and create a new config
    
    service_name = getattr(legacy_config, 'service_name', 'unknown')
    
    config_data = {
        'service_name': service_name,
        'project_root': getattr(legacy_config, 'project_root', os.getcwd()),
    }
    
    # Extract connection info if available
    if hasattr(legacy_config, 'host'):
        config_data['connection'] = {
            'host': getattr(legacy_config, 'host', 'localhost'),
            'ports': getattr(legacy_config, 'ports', [4002]),
            'client_id': getattr(legacy_config, 'client_id', 100),
        }
    
    # Extract server info if available  
    if hasattr(legacy_config, 'server_port'):
        config_data['server'] = {
            'host': getattr(legacy_config, 'server_host', '0.0.0.0'),
            'port': getattr(legacy_config, 'server_port', 8001),
        }
    
    return IBBaseConfig(**config_data)


def validate_migration() -> Dict[str, Any]:
    """
    Validate that migration is working correctly.
    
    Returns:
        Validation results
    """
    results = {
        'valid': True,
        'services_tested': [],
        'issues': [],
        'recommendations': []
    }
    
    # Test configuration loading for known services
    known_services = ['ib-stream', 'ib-contract']
    
    for service in known_services:
        try:
            migrator = ConfigMigrator(service)
            config = migrator.get_config()
            status = migrator.get_migration_status()
            
            results['services_tested'].append({
                'service': service,
                'status': 'success',
                'using_new_config': status['using_new_config'],
                'config_source': status['config_source']
            })
            
            if status['using_legacy_fallback']:
                results['recommendations'].extend([
                    f"Service {service} is using legacy fallback",
                    f"Consider migrating {service} to new configuration format"
                ])
                
        except Exception as e:
            results['valid'] = False
            results['issues'].append(f"Failed to load config for {service}: {e}")
            results['services_tested'].append({
                'service': service,
                'status': 'failed',
                'error': str(e)
            })
    
    return results