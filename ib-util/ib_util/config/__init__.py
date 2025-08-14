"""
Shared configuration system for IB projects.

This module provides a centralized, type-safe configuration system that:
- Supports multiple projects (ib-stream, ib-contract, ib-studies)
- Uses Pydantic for validation and type safety
- Supports environment-specific configurations
- Provides orchestration capabilities for multi-service deployments
- Eliminates security vulnerabilities from shell-based parsing
"""

from .base import (
    IBBaseConfig,
    IBConnectionConfig,
    IBStorageConfig,
    IBServerConfig,
    IBEnvironment
)
from .orchestration import (
    IBOrchestrationConfig,
    ServiceConfig,
    load_orchestration_config
)
from .loader import (
    ConfigLoader,
    load_config,
    get_config_for_service,
    load_orchestration_for_environment,
    validate_configuration
)
from .compat import (
    create_compatible_config,
    migrate_legacy_config_object,
    validate_v2_config
)

__all__ = [
    # Base configuration classes
    'IBBaseConfig',
    'IBConnectionConfig', 
    'IBStorageConfig',
    'IBServerConfig',
    'IBEnvironment',
    
    # Orchestration
    'IBOrchestrationConfig',
    'ServiceConfig',
    'load_orchestration_config',
    
    # Loader utilities
    'ConfigLoader',
    'load_config',
    'get_config_for_service',
    'load_orchestration_for_environment',
    'validate_configuration',
    
    # Compatibility layer
    'create_compatible_config',
    'migrate_legacy_config_object',
    'validate_v2_config',
]