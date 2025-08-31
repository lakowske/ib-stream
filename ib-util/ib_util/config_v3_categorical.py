#!/usr/bin/env python3
"""
Configuration System v3 - Categorical Enhancement

This enhances the config v3 system with proper Category Theory structures:
- Monadic error handling (no exceptions)
- Monoid-based configuration merging  
- Categorical constraints for validation
- Functorial transformations
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum

# Import our categorical abstractions
try:
    from .categorical import (
        Result, Success, Error, pure, sequence_results,
        Monoid, DictMonoid, 
        Constraint, BoundedConstraint, RangeConstraint,
        LogLevel, validate_log_level
    )
except ImportError:
    # Direct import for testing
    from categorical import (
        Result, Success, Error, pure, sequence_results,
        Monoid, DictMonoid, 
        Constraint, BoundedConstraint, RangeConstraint,
        LogLevel, validate_log_level
    )


class Environment(str, Enum):
    """Supported environments"""
    DEVELOPMENT = "development" 
    PRODUCTION = "production"


# ============================================================================
# CATEGORICAL VALIDATION CONSTRAINTS
# ============================================================================

# Environment constraint
ENVIRONMENT_CONSTRAINT = BoundedConstraint(
    list(Environment),
    "environment"
)

# Port range constraint  
PORT_CONSTRAINT = RangeConstraint(1024, 65535, inclusive=True)

# Client ID constraint
CLIENT_ID_CONSTRAINT = RangeConstraint(1, 999999, inclusive=True)


def validate_environment(env_str: str) -> Result[Environment, str]:
    """Validate environment using categorical constraints"""
    try:
        env = Environment(env_str.lower())
        return ENVIRONMENT_CONSTRAINT.check(env)
    except ValueError:
        return Error(f"Invalid environment: {env_str}. Must be 'development' or 'production'")


def validate_port(port: int) -> Result[int, str]:
    """Validate port using categorical constraints"""
    return PORT_CONSTRAINT.check(port)


def validate_client_id(client_id: int) -> Result[int, str]:
    """Validate client ID using categorical constraints"""
    return CLIENT_ID_CONSTRAINT.check(client_id)


# ============================================================================
# CATEGORICAL CONFIGURATION LOADER
# ============================================================================

class CategoricalConfigLoader:
    """
    Configuration loader using Category Theory principles.
    
    - Monadic error handling (no exceptions)
    - Monoid-based merging
    - Compositional validation
    - Functorial transformations
    """
    
    def __init__(self, config_root: Optional[str] = None):
        self.config_root = Path(config_root or "config")
        self.dict_monoid = DictMonoid()
    
    def load_yaml_file(self, filepath: Path) -> Result[Dict[str, Any], str]:
        """Load YAML file with monadic error handling"""
        if not filepath.exists():
            return Success({})  # Empty dict is monoid identity
        
        try:
            with open(filepath, 'r') as f:
                content = yaml.safe_load(f) or {}
                return Success(content)
        except yaml.YAMLError as e:
            return Error(f"Invalid YAML in {filepath}: {e}")
        except Exception as e:
            return Error(f"Error reading {filepath}: {e}")
    
    def get_environment(self) -> Result[Environment, str]:
        """Get environment with categorical validation"""
        env_str = os.getenv('IB_ENVIRONMENT', 'development')
        return validate_environment(env_str)
    
    def merge_configs(self, configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge configurations using monoid structure"""
        return self.dict_monoid.fold(configs)
    
    def load_config_hierarchy(self, service_name: str) -> Result[Dict[str, Any], str]:
        """
        Load configuration hierarchy with monadic composition.
        
        This replaces imperative error handling with monadic bind operations.
        """
        def load_hierarchy(env: Environment) -> Result[Dict[str, Any], str]:
            # Load all configuration files
            base_result = self.load_yaml_file(self.config_root / "base.yaml")
            env_result = self.load_yaml_file(self.config_root / f"{env.value}.yaml")
            service_result = self.load_yaml_file(self.config_root / "services" / f"{service_name}.yaml")
            
            # Sequence all results (fail fast on first error)
            return sequence_results([base_result, env_result, service_result]).map(
                lambda configs: self.merge_configs(configs)
            ).bind(
                lambda merged: self.apply_environment_overrides(merged, env)
            )
        
        return self.get_environment().bind(load_hierarchy)
    
    def apply_environment_overrides(self, config: Dict[str, Any], env: Environment) -> Result[Dict[str, Any], str]:
        """Apply environment variable overrides with validation"""
        result = config.copy()
        
        # Gateway host override
        if os.getenv('IB_GATEWAY_HOST'):
            result.setdefault('gateway', {})['host'] = os.getenv('IB_GATEWAY_HOST')
        
        # Gateway ports override with validation
        if os.getenv('IB_GATEWAY_PORTS'):
            try:
                ports = [int(p.strip()) for p in os.getenv('IB_GATEWAY_PORTS').split(',')]
                # Validate all ports
                port_results = [validate_port(port) for port in ports]
                sequence_result = sequence_results(port_results)
                
                if sequence_result.is_error():
                    return Error(f"Invalid gateway ports: {sequence_result.error()}")
                
                result.setdefault('gateway', {})['ports'] = sequence_result.unwrap()
            except ValueError as e:
                return Error(f"Invalid gateway ports format: {e}")
        
        # Client ID override with validation
        if os.getenv('IB_CLIENT_ID'):
            try:
                client_id = int(os.getenv('IB_CLIENT_ID'))
                client_id_result = validate_client_id(client_id)
                
                if client_id_result.is_error():
                    return Error(f"Invalid client ID: {client_id_result.error()}")
                
                result.setdefault('service', {}).setdefault('client', {})['id'] = client_id_result.unwrap()
            except ValueError as e:
                return Error(f"Invalid client ID format: {e}")
        
        # Server port override with validation
        if os.getenv('IB_SERVER_PORT'):
            try:
                port = int(os.getenv('IB_SERVER_PORT'))
                port_result = validate_port(port)
                
                if port_result.is_error():
                    return Error(f"Invalid server port: {port_result.error()}")
                
                result.setdefault('service', {}).setdefault('server', {})['port'] = port_result.unwrap()
            except ValueError as e:
                return Error(f"Invalid server port format: {e}")
        
        return Success(result)
    
    def validate_configuration(self, config: Dict[str, Any]) -> Result[Dict[str, Any], str]:
        """
        Validate complete configuration using categorical constraints.
        
        Composes multiple validation functions using monadic bind.
        """
        def validate_logging(cfg: Dict[str, Any]) -> Result[Dict[str, Any], str]:
            if 'logging' in cfg and 'level' in cfg['logging']:
                level_result = validate_log_level(cfg['logging']['level'])
                if level_result.is_error():
                    return Error(f"Logging validation failed: {level_result.error()}")
                cfg['logging']['level'] = level_result.unwrap()
            return Success(cfg)
        
        def validate_server_config(cfg: Dict[str, Any]) -> Result[Dict[str, Any], str]:
            if 'service' in cfg and 'server' in cfg['service'] and 'port' in cfg['service']['server']:
                port_result = validate_port(cfg['service']['server']['port'])
                if port_result.is_error():
                    return Error(f"Server port validation failed: {port_result.error()}")
                cfg['service']['server']['port'] = port_result.unwrap()
            return Success(cfg)
        
        def validate_client_config(cfg: Dict[str, Any]) -> Result[Dict[str, Any], str]:
            if 'service' in cfg and 'client' in cfg['service'] and 'id' in cfg['service']['client']:
                client_result = validate_client_id(cfg['service']['client']['id'])
                if client_result.is_error():
                    return Error(f"Client ID validation failed: {client_result.error()}")
                cfg['service']['client']['id'] = client_result.unwrap()
            return Success(cfg)
        
        # Compose validations using monadic bind
        return (pure(config)
                .bind(validate_logging)
                .bind(validate_server_config) 
                .bind(validate_client_config))


def load_config_categorical(service_name: str, config_root: Optional[str] = None) -> Result[Dict[str, Any], str]:
    """
    Load configuration using categorical approach.
    
    This function demonstrates the full categorical pipeline:
    - Monadic error handling
    - Monoid-based merging
    - Compositional validation
    - No exceptions thrown
    """
    loader = CategoricalConfigLoader(config_root)
    
    return (loader.load_config_hierarchy(service_name)
            .bind(loader.validate_configuration))


# ============================================================================
# COMPATIBILITY BRIDGE
# ============================================================================

class CategoricalResult:
    """Bridge between categorical Result and existing code expectations"""
    
    def __init__(self, result: Result[Dict[str, Any], str]):
        self._result = result
    
    def get_or_raise(self) -> Dict[str, Any]:
        """Convert Result back to exception-based interface for compatibility"""
        if self._result.is_success():
            return self._result.unwrap()
        else:
            raise ValueError(self._result.error())
    
    def get_or_default(self, default: Dict[str, Any]) -> Dict[str, Any]:
        """Get value or return default"""
        if self._result.is_success():
            return self._result.unwrap()
        return default
    
    def is_success(self) -> bool:
        return self._result.is_success()
    
    def error_message(self) -> Optional[str]:
        return self._result.error() if self._result.is_error() else None


def load_config_safe(service_name: str, config_root: Optional[str] = None) -> CategoricalResult:
    """
    Safe configuration loading that returns Result instead of raising exceptions.
    
    This provides a bridge between the categorical system and existing code.
    """
    result = load_config_categorical(service_name, config_root)
    return CategoricalResult(result)


# ============================================================================
# TESTING AND EXAMPLES
# ============================================================================

if __name__ == "__main__":
    print("🔬 Categorical Configuration System v3 Tests")
    
    # Test monadic configuration loading
    print("\n1. Monadic Configuration Loading:")
    
    result = load_config_categorical("ib-stream")
    
    if result.is_success():
        config = result.unwrap()
        print("   ✅ Configuration loaded successfully")
        print(f"   Environment: {config.get('project', {}).get('environment', 'unknown')}")
        print(f"   Gateway host: {config.get('gateway', {}).get('host', 'unknown')}")
        print(f"   Client ID: {config.get('service', {}).get('client', {}).get('id', 'unknown')}")
    else:
        print(f"   ❌ Configuration failed: {result.error()}")
    
    # Test categorical validation
    print("\n2. Categorical Validation Tests:")
    
    # Test port validation
    valid_port = validate_port(8080)
    invalid_port = validate_port(70000)
    
    print(f"   Port 8080: {'✅ Valid' if valid_port.is_success() else '❌ ' + valid_port.error()}")
    print(f"   Port 70000: {'✅ Valid' if invalid_port.is_success() else '❌ ' + invalid_port.error()}")
    
    # Test log level validation
    valid_level = validate_log_level("INFO")
    invalid_level = validate_log_level("TRACE")
    
    print(f"   Log level 'INFO': {'✅ Valid' if valid_level.is_success() else '❌ ' + valid_level.error()}")
    print(f"   Log level 'TRACE': {'✅ Valid' if invalid_level.is_success() else '❌ ' + invalid_level.error()}")
    
    print("\n✅ Categorical configuration system working!")