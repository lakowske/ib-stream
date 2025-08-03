"""
Configuration loading with dotenv support.

Provides secure, type-safe configuration loading that replaces the
dangerous shell-based approach with Python dotenv parsing.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv, find_dotenv
from .base import IBBaseConfig, IBEnvironment
from .orchestration import IBOrchestrationConfig, load_orchestration_config

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Secure configuration loader using dotenv and Pydantic validation.
    
    Eliminates security vulnerabilities from shell-based parsing while
    providing type safety and validation.
    """
    
    def __init__(self, project_root: str):
        """
        Initialize configuration loader.
        
        Args:
            project_root: Root directory of the project
        """
        self.project_root = Path(project_root).absolute()
        self.config_dir = self.project_root / "config"
        
    def load_environment_files(self, environment: IBEnvironment) -> None:
        """
        Load environment files in priority order.
        
        Priority (highest to lowest):
        1. .env.{environment}.local
        2. .env.{environment}
        3. .env.local
        4. .env
        
        Args:
            environment: Target environment
        """
        env_files = [
            self.config_dir / f".env.{environment.value}.local",
            self.config_dir / f".env.{environment.value}",
            self.config_dir / ".env.local",
            self.config_dir / ".env",
        ]
        
        # Also check for legacy .env files in project root
        legacy_files = [
            self.project_root / f".env.{environment.value}.local",
            self.project_root / f".env.{environment.value}",
            self.project_root / ".env.local", 
            self.project_root / ".env",
        ]
        
        all_files = env_files + legacy_files
        
        loaded_files = []
        for env_file in all_files:
            if env_file.exists():
                logger.debug(f"Loading environment file: {env_file}")
                load_dotenv(dotenv_path=env_file, override=False)
                loaded_files.append(str(env_file))
        
        if loaded_files:
            logger.info(f"Loaded environment files: {loaded_files}")
        else:
            logger.warning("No environment files found")
    
    def load_legacy_env_file(self, env_file_path: str) -> None:
        """
        Load legacy .env file format safely.
        
        Converts shell-style variable definitions to Python environment
        variables without shell injection vulnerabilities.
        
        Args:
            env_file_path: Path to legacy .env file
        """
        env_path = Path(env_file_path)
        if not env_path.exists():
            logger.warning(f"Legacy env file not found: {env_path}")
            return
        
        logger.info(f"Loading legacy env file: {env_path}")
        
        try:
            with open(env_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse key=value pairs
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        
                        # Only set if not already set (don't override)
                        if key not in os.environ:
                            os.environ[key] = value
                            logger.debug(f"Set {key}={value}")
                    else:
                        logger.warning(f"Invalid line {line_num} in {env_path}: {line}")
                        
        except Exception as e:
            logger.error(f"Error loading legacy env file {env_path}: {e}")
            raise
    
    def create_service_config(
        self,
        service_name: str,
        environment: IBEnvironment = IBEnvironment.DEVELOPMENT,
        **overrides: Any
    ) -> IBBaseConfig:
        """
        Create configuration for a specific service.
        
        Args:
            service_name: Name of the service
            environment: Target environment
            **overrides: Configuration overrides
            
        Returns:
            Service configuration
        """
        # Load environment files
        self.load_environment_files(environment)
        
        # Load legacy files if they exist
        legacy_files = [
            self.project_root / "ib-stream" / "config" / f"{environment.value}.env",
            self.project_root / "ib-stream" / "config" / "instance.env",
        ]
        
        for legacy_file in legacy_files:
            if legacy_file.exists():
                self.load_legacy_env_file(str(legacy_file))
        
        # Create base configuration with proper service name
        config_data = {
            'service_name': service_name,
            'environment': environment,
            'project_root': str(self.project_root),
            **overrides
        }
        
        try:
            return IBBaseConfig(**config_data)
        except Exception as e:
            logger.error(f"Failed to create configuration for {service_name}: {e}")
            raise
    
    def create_orchestration_config(
        self,
        environment: IBEnvironment = IBEnvironment.DEVELOPMENT
    ) -> IBOrchestrationConfig:
        """
        Create orchestration configuration for multi-service deployment.
        
        Args:
            environment: Target environment
            
        Returns:
            Orchestration configuration
        """
        # Load environment files
        self.load_environment_files(environment)
        
        return load_orchestration_config(str(self.project_root), environment)


def load_config(
    service_name: str,
    project_root: Optional[str] = None,
    environment: Optional[IBEnvironment] = None,
    **overrides: Any
) -> IBBaseConfig:
    """
    Convenience function to load configuration for a service.
    
    Args:
        service_name: Name of the service
        project_root: Project root directory (auto-detected if None)
        environment: Target environment (from IB_ENVIRONMENT if None)
        **overrides: Configuration overrides
        
    Returns:
        Service configuration
    """
    # Auto-detect project root if not provided
    if project_root is None:
        project_root = os.getcwd()
        # Try to find project root by looking for specific files
        current = Path(project_root)
        for parent in [current] + list(current.parents):
            if (parent / "pyproject.toml").exists() or (parent / "setup.py").exists():
                project_root = str(parent)
                break
    
    # Get environment from env var if not provided
    if environment is None:
        env_str = os.getenv("IB_ENVIRONMENT", "development")
        try:
            environment = IBEnvironment(env_str)
        except ValueError:
            logger.warning(f"Invalid environment '{env_str}', using development")
            environment = IBEnvironment.DEVELOPMENT
    
    loader = ConfigLoader(project_root)
    return loader.create_service_config(service_name, environment, **overrides)


def get_config_for_service(service_name: str) -> IBBaseConfig:
    """
    Get configuration for a specific service using environment detection.
    
    This is the main entry point for services to get their configuration.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Service configuration
    """
    return load_config(service_name)


def load_orchestration_for_environment(
    environment: IBEnvironment,
    project_root: Optional[str] = None
) -> IBOrchestrationConfig:
    """
    Load orchestration configuration for a specific environment.
    
    Args:
        environment: Target environment
        project_root: Project root directory (auto-detected if None)
        
    Returns:
        Orchestration configuration
    """
    if project_root is None:
        project_root = os.getcwd()
    
    loader = ConfigLoader(project_root)
    return loader.create_orchestration_config(environment)


def validate_configuration() -> Dict[str, Any]:
    """
    Validate the current configuration setup.
    
    Returns:
        Validation results and recommendations
    """
    results = {
        'valid': True,
        'warnings': [],
        'errors': [],
        'recommendations': []
    }
    
    try:
        # Try to load orchestration config
        config = load_orchestration_for_environment(IBEnvironment.DEVELOPMENT)
        config.validate_no_conflicts()
        
        results['orchestration'] = {
            'ports_in_use': config.get_ports_in_use(),
            'client_ids_in_use': config.get_client_ids_in_use(),
            'services': list(config.services.keys())
        }
        
    except Exception as e:
        results['valid'] = False
        results['errors'].append(f"Configuration validation failed: {e}")
    
    # Check for legacy files that should be migrated
    project_root = Path(os.getcwd())
    legacy_files = [
        project_root / "ib-stream" / "config" / "remote-gateway.env",
        project_root / "ib-stream" / "config" / "production-server.env",
        project_root / "start-production.sh",
    ]
    
    found_legacy = [f for f in legacy_files if f.exists()]
    if found_legacy:
        results['warnings'].append(f"Found legacy configuration files: {[str(f) for f in found_legacy]}")
        results['recommendations'].append("Consider migrating to new configuration format")
    
    return results