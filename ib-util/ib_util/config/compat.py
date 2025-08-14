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


# Legacy ConfigMigrator class has been removed as all services now use v2 configuration system


def create_compatible_config(service_name: str) -> IBBaseConfig:
    """
    Create configuration using the v2 system only.
    
    Legacy fallback has been removed - all services now use the v2 configuration system.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Configuration object
    """
    from .loader import load_config
    
    # Use v2 configuration system directly
    config = load_config(service_name)
    logger.info(f"Service {service_name} using v2 configuration system")
    
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


def validate_v2_config() -> Dict[str, Any]:
    """
    Validate that v2 configuration system is working correctly.
    
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
            config = create_compatible_config(service)
            
            results['services_tested'].append({
                'service': service,
                'status': 'success',
                'config_source': 'v2',
                'host': config.connection.host,
                'client_id': config.connection.client_id,
                'server_port': config.server.port
            })
                
        except Exception as e:
            results['valid'] = False
            results['issues'].append(f"Failed to load v2 config for {service}: {e}")
            results['services_tested'].append({
                'service': service,
                'status': 'failed',
                'error': str(e)
            })
    
    if results['valid']:
        results['recommendations'].append("All services successfully using v2 configuration system")
    
    return results