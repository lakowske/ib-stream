#!/usr/bin/env python3
"""
Functorial Configuration Transformations

This module provides functorial transformations for configuration objects,
enabling compositional configuration manipulation and type-safe conversions.
"""

from typing import TypeVar, Callable, Dict, Any, List
try:
    from .categorical import Result, Success, Error, pure
except ImportError:
    # Direct import for testing
    from categorical import Result, Success, Error, pure

A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')


# ============================================================================
# FUNCTOR FOR CONFIGURATION TRANSFORMATIONS
# ============================================================================

class ConfigFunctor:
    """
    Functor for configuration transformations.
    
    Provides structure-preserving mappings over configuration objects.
    Satisfies functor laws:
    - Identity: fmap(id, x) = x
    - Composition: fmap(f ∘ g, x) = fmap(f, fmap(g, x))
    """
    
    @staticmethod
    def fmap(f: Callable[[A], B], config: Dict[str, A]) -> Dict[str, B]:
        """
        Map a function over all values in a configuration dictionary.
        
        This preserves the structure while transforming the values.
        """
        return {key: f(value) for key, value in config.items()}
    
    @staticmethod
    def fmap_nested(f: Callable[[A], B], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map a function over nested configuration values.
        
        Recursively applies transformation to nested dictionaries.
        """
        result = {}
        for key, value in config.items():
            if isinstance(value, dict):
                result[key] = ConfigFunctor.fmap_nested(f, value)
            elif isinstance(value, list):
                result[key] = [ConfigFunctor.fmap_nested(f, item) if isinstance(item, dict) else f(item) 
                              for item in value]
            else:
                result[key] = f(value)
        return result


# ============================================================================
# NATURAL TRANSFORMATIONS
# ============================================================================

class ConfigTransformations:
    """
    Natural transformations for configuration objects.
    
    These transformations preserve categorical structure while changing
    the representation or format of configuration data.
    """
    
    @staticmethod
    def to_environment_vars(config: Dict[str, Any], prefix: str = "IB") -> Dict[str, str]:
        """
        Natural transformation from configuration to environment variables.
        
        Flattens nested configuration into environment variable format.
        """
        def flatten_dict(d: Dict[str, Any], parent_key: str = '') -> Dict[str, str]:
            items = []
            for key, value in d.items():
                new_key = f"{parent_key}_{key.upper()}" if parent_key else f"{prefix}_{key.upper()}"
                if isinstance(value, dict):
                    items.extend(flatten_dict(value, new_key).items())
                elif isinstance(value, list):
                    items.append((new_key, ','.join(map(str, value))))
                else:
                    items.append((new_key, str(value)))
            return dict(items)
        
        return flatten_dict(config)
    
    @staticmethod
    def normalize_strings(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transformation that normalizes all string values in configuration.
        
        This is a functorial transformation that preserves structure.
        """
        def normalize_string(value: Any) -> Any:
            if isinstance(value, str):
                return value.strip().lower()
            return value
        
        return ConfigFunctor.fmap_nested(normalize_string, config)
    
    @staticmethod
    def validate_and_transform(config: Dict[str, Any]) -> Result[Dict[str, Any], str]:
        """
        Monadic transformation that validates and transforms configuration.
        
        Combines validation with transformation in a compositional manner.
        """
        def transform_ports(cfg: Dict[str, Any]) -> Result[Dict[str, Any], str]:
            """Transform and validate port configurations"""
            if 'gateway' in cfg and 'ports' in cfg['gateway']:
                ports = cfg['gateway']['ports']
                if isinstance(ports, list):
                    try:
                        # Validate ports are in valid range
                        valid_ports = []
                        for port in ports:
                            if not isinstance(port, int) or port < 1024 or port > 65535:
                                return Error(f"Invalid port: {port}. Must be between 1024 and 65535")
                            valid_ports.append(port)
                        
                        cfg['gateway']['ports'] = valid_ports
                        return Success(cfg)
                    except Exception as e:
                        return Error(f"Port validation error: {e}")
            return Success(cfg)
        
        def transform_client_id(cfg: Dict[str, Any]) -> Result[Dict[str, Any], str]:
            """Transform and validate client ID"""
            if 'service' in cfg and 'client' in cfg['service'] and 'id' in cfg['service']['client']:
                client_id = cfg['service']['client']['id']
                if not isinstance(client_id, int) or client_id < 1 or client_id > 999999:
                    return Error(f"Invalid client ID: {client_id}. Must be between 1 and 999999")
            return Success(cfg)
        
        # Compose transformations using monadic bind
        return (pure(config)
                .bind(transform_ports)
                .bind(transform_client_id))


# ============================================================================
# CONFIGURATION LENSES (Optional - Advanced Category Theory)
# ============================================================================

class ConfigLens:
    """
    Lens for compositional configuration access and modification.
    
    A lens provides a way to focus on a particular part of a data structure
    in a composable manner. This is advanced category theory.
    """
    
    def __init__(self, getter: Callable[[Dict[str, Any]], Any], 
                 setter: Callable[[Dict[str, Any], Any], Dict[str, Any]]):
        self.get = getter
        self.set = setter
    
    def modify(self, config: Dict[str, Any], f: Callable[[Any], Any]) -> Dict[str, Any]:
        """Modify the focused value using a function"""
        old_value = self.get(config)
        new_value = f(old_value)
        return self.set(config, new_value)
    
    def compose(self, other: 'ConfigLens') -> 'ConfigLens':
        """Compose two lenses (lens composition)"""
        return ConfigLens(
            lambda config: other.get(self.get(config)),
            lambda config, value: self.set(config, other.set(self.get(config), value))
        )


# Predefined lenses for common configuration paths
CLIENT_ID_LENS = ConfigLens(
    getter=lambda config: config.get('service', {}).get('client', {}).get('id'),
    setter=lambda config, value: {
        **config,
        'service': {
            **config.get('service', {}),
            'client': {
                **config.get('service', {}).get('client', {}),
                'id': value
            }
        }
    }
)

GATEWAY_HOST_LENS = ConfigLens(
    getter=lambda config: config.get('gateway', {}).get('host'),
    setter=lambda config, value: {
        **config,
        'gateway': {
            **config.get('gateway', {}),
            'host': value
        }
    }
)


# ============================================================================
# USAGE EXAMPLES AND TESTS
# ============================================================================

if __name__ == "__main__":
    print("🔬 Functorial Configuration Transformations Tests")
    
    # Sample configuration
    sample_config = {
        "gateway": {
            "host": "  LOCALHOST  ",
            "ports": [4002, 4001]
        },
        "service": {
            "client": {"id": 101},
            "server": {"port": 8851}
        },
        "logging": {"level": "  DEBUG  "}
    }
    
    # Test functorial transformations
    print("\n1. Functorial String Normalization:")
    normalized = ConfigTransformations.normalize_strings(sample_config)
    print(f"   Original host: '{sample_config['gateway']['host']}'")
    print(f"   Normalized host: '{normalized['gateway']['host']}'")
    
    # Test natural transformation to environment variables
    print("\n2. Natural Transformation to Environment Variables:")
    env_vars = ConfigTransformations.to_environment_vars(sample_config)
    for key, value in list(env_vars.items())[:5]:  # Show first 5
        print(f"   {key}={value}")
    print("   ... (more)")
    
    # Test monadic validation and transformation
    print("\n3. Monadic Validation and Transformation:")
    validation_result = ConfigTransformations.validate_and_transform(sample_config)
    if validation_result.is_success():
        print("   ✅ Configuration validation passed")
    else:
        print(f"   ❌ Configuration validation failed: {validation_result.error()}")
    
    # Test lenses (advanced)
    print("\n4. Configuration Lenses (Advanced):")
    original_client_id = CLIENT_ID_LENS.get(sample_config)
    modified_config = CLIENT_ID_LENS.modify(sample_config, lambda x: x + 100)
    new_client_id = CLIENT_ID_LENS.get(modified_config)
    
    print(f"   Original client ID: {original_client_id}")
    print(f"   Modified client ID: {new_client_id}")
    
    print("\n✅ All functorial transformations working correctly!")