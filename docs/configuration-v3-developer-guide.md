# Configuration v3 Developer Guide

## Table of Contents
1. [Quick Start](#quick-start)
2. [Basic Usage](#basic-usage)
3. [Category Theory Features](#category-theory-features)
4. [Advanced Usage](#advanced-usage)
5. [Development Workflow](#development-workflow)
6. [Extending the System](#extending-the-system)
7. [Troubleshooting](#troubleshooting)

## Quick Start

### Installation & Setup
```bash
# Configuration v3 is already installed with ib-util
cd /home/seth/Software/dev/ib-stream-1

# Set environment for development
export IB_ENVIRONMENT=development
export IB_CONFIG_ROOT=$(pwd)/config

# Validate configuration
python -c "from ib_util.config_v3 import load_config; print('✅ Config v3 working!')"
```

### Your First Configuration
```python
from ib_util.config_v3 import load_config

# Load typed, validated configuration
config = load_config('ib-stream')

# Access configuration with full IDE support
print(f"Client ID: {config.service.client.id}")           # int, validated 1-999999
print(f"Gateway: {config.gateway.host}:{config.gateway.ports}")  # List[int], validated ports
print(f"Log Level: {config.logging.level}")               # str, validated enum
print(f"Environment: {config.project.environment}")        # Environment enum
```

### Standalone Debugging
```bash
# Debug without supervisor - your new best friend!
python ib-stream/debug.py --validate-only    # Just validate config
python ib-stream/debug.py --show-config      # Show loaded config  
python ib-stream/debug.py --run             # Run service standalone
```

## Basic Usage

### Configuration Loading

#### Standard Loading (Recommended)
```python
from ib_util.config_v3 import load_config

# Automatic environment detection from IB_ENVIRONMENT
config = load_config('ib-stream')

# Override config directory
config = load_config('ib-stream', config_root='/custom/config')
```

#### Validation Only
```python
from ib_util.config_v3 import validate_config

# Validate without loading (faster for CI/tests)
is_valid = validate_config('ib-stream')
print(f"Configuration valid: {is_valid}")
```

#### Direct Class Usage
```python
from ib_util.config_v3 import ConfigLoader

loader = ConfigLoader('config')
config = loader.load_service_config('ib-stream')
```

### Configuration Structure Access

Configuration v3 provides full type safety and IDE autocomplete:

```python
config = load_config('ib-stream')

# Project metadata
config.project.name           # str: "ib-stream"
config.project.version        # str: "3.0.0" 
config.project.environment    # Environment: Environment.DEVELOPMENT

# Gateway configuration
config.gateway.host           # str: "192.168.0.60"
config.gateway.ports          # List[int]: [4002, 4001]
config.gateway.connection_timeout  # int: 10

# Service configuration
config.service.name           # str: "ib-stream"
config.service.client.id      # int: 101 (validated range)
config.service.server.port    # int: 8851 (validated range)
config.service.server.host    # str: "0.0.0.0"

# Storage configuration
config.storage.enabled        # bool: True
config.storage.base_path      # str: "storage-dev"  
config.storage.formats.v3_json      # bool: True
config.storage.formats.v3_protobuf  # bool: True

# Logging configuration  
config.logging.level          # str: "DEBUG" (validated enum)
config.logging.format         # str: "detailed"

# Performance settings
config.performance.max_concurrent_streams  # int: 10

# Optional service-specific sections
if config.service.streaming:
    config.service.streaming.enable_background_streaming  # bool
    config.service.streaming.tracked_contracts           # List[TrackedContractConfig]
    
if config.service.cache:
    config.service.cache.duration_days       # int: 1
    config.service.cache.memory_cache_size   # int: 1000
```

### Working with Environments

```python
from ib_util.config_v3 import load_config
import os

# Environment automatically detected
os.environ['IB_ENVIRONMENT'] = 'development'
dev_config = load_config('ib-stream')
print(dev_config.project.environment)  # Environment.DEVELOPMENT

os.environ['IB_ENVIRONMENT'] = 'production'  
prod_config = load_config('ib-stream')
print(prod_config.project.environment)  # Environment.PRODUCTION

# Environment-specific differences
print(f"Dev client ID: {dev_config.service.client.id}")    # 101
print(f"Prod client ID: {prod_config.service.client.id}")  # 851
```

## Category Theory Features

Configuration v3 includes optional Category Theory structures for advanced use cases. These provide mathematical guarantees about configuration operations.

### Monadic Error Handling

Replace exception-based error handling with composable monadic operations:

```python
from ib_util.config_v3_categorical import load_config_categorical

# Monadic loading - no exceptions thrown
result = load_config_categorical('ib-stream')

if result.is_success():
    config = result.unwrap()
    print(f"✅ Config loaded: {config['service']['client']['id']}")
else:
    error_msg = result.error()  
    print(f"❌ Config failed: {error_msg}")
    # Handle error gracefully - no exception bubbling
```

#### Composing Configuration Operations

```python
from ib_util.config_v3_categorical import load_config_categorical
from ib_util.config_transformations import ConfigTransformations

# Monadic composition - operations chain safely
result = (load_config_categorical('ib-stream')
          .bind(lambda cfg: ConfigTransformations.validate_and_transform(cfg))
          .map(lambda cfg: ConfigTransformations.normalize_strings(cfg)))

if result.is_success():
    final_config = result.unwrap()
    print("✅ Configuration loaded, validated, and normalized")
else:
    print(f"❌ Pipeline failed: {result.error()}")
```

### Categorical Validation

Use mathematical constraints for validation:

```python
from ib_util.config_v3_categorical import (
    validate_port, validate_client_id, validate_environment
)

# Port validation (1024-65535 range)
port_result = validate_port(8080)
if port_result.is_success():
    print(f"✅ Valid port: {port_result.unwrap()}")
else:
    print(f"❌ Invalid port: {port_result.error()}")

# Client ID validation (1-999999 range)
client_result = validate_client_id(101)

# Environment validation (development/production only)
env_result = validate_environment('development')

# Compose validations
from ib_util.categorical import sequence_results

all_valid = sequence_results([port_result, client_result, env_result])
if all_valid.is_success():
    print("✅ All validations passed")
    port, client_id, environment = all_valid.unwrap()
```

### Configuration Transformations

Functorial transformations preserve structure while transforming values:

```python
from ib_util.config_transformations import ConfigTransformations

config_dict = {
    'gateway': {'host': '  LOCALHOST  '},
    'logging': {'level': '  debug  '}
}

# String normalization (functional transformation)
normalized = ConfigTransformations.normalize_strings(config_dict)
print(normalized)  # {'gateway': {'host': 'localhost'}, 'logging': {'level': 'debug'}}

# Convert to environment variables (natural transformation)
env_vars = ConfigTransformations.to_environment_vars(config_dict)
print(env_vars)    # {'IB_GATEWAY_HOST': 'localhost', 'IB_LOGGING_LEVEL': 'debug'}

# Monadic validation pipeline
validation = ConfigTransformations.validate_and_transform(config_dict)
```

### Configuration Lenses

Compositional access and modification:

```python
from ib_util.config_transformations import CLIENT_ID_LENS, GATEWAY_HOST_LENS

config = {'service': {'client': {'id': 101}}, 'gateway': {'host': 'localhost'}}

# Focus on client ID
current_id = CLIENT_ID_LENS.get(config)     # 101
modified = CLIENT_ID_LENS.modify(config, lambda x: x + 100)  # Immutable update
new_id = CLIENT_ID_LENS.get(modified)       # 201

# Compose lenses
composite_lens = CLIENT_ID_LENS.compose(GATEWAY_HOST_LENS)  # Advanced composition
```

## Advanced Usage

### Custom Validation

Add your own categorical constraints:

```python
from ib_util.categorical import RangeConstraint, BoundedConstraint

# Custom constraint for your domain
CUSTOM_PORT_RANGE = RangeConstraint(8000, 9000, inclusive=True)
VALID_SYMBOLS = BoundedConstraint(['AAPL', 'GOOGL', 'MSFT'], "stock symbols")

# Validate with custom constraints
port_result = CUSTOM_PORT_RANGE.check(8080)
symbol_result = VALID_SYMBOLS.check('AAPL')

# Compose constraints
combined = CUSTOM_PORT_RANGE.and_then(lambda p: Success(f"port-{p}"))
```

### Configuration Monoids

Merge configurations with mathematical guarantees:

```python
from ib_util.categorical import DictMonoid

monoid = DictMonoid()

base_config = {'gateway': {'host': 'localhost', 'ports': [4002]}}
override_config = {'gateway': {'ports': [4001, 4002]}, 'new_section': {}}

# Associative merge with identity properties
merged = monoid.combine(base_config, override_config)
print(merged)  # Deep merge with override semantics

# Fold multiple configurations
configs = [base_config, override_config, another_config]
result = monoid.fold(configs)  # Equivalent to sequential combines
```

### Custom Configuration Models

Extend the configuration system for your services:

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from ib_util.config_v3 import ConfigLoader

class CustomServiceConfig(BaseModel):
    """Custom service configuration"""
    name: str
    custom_setting: str = "default"
    custom_list: List[str] = Field(default_factory=list)
    optional_section: Optional[dict] = None

class CustomAppConfig(BaseModel):
    """Custom application configuration"""
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig) 
    custom_service: CustomServiceConfig

# Load with custom model
loader = ConfigLoader('config')
raw_config = loader.load_service_config('my-custom-service')
custom_config = CustomAppConfig(**raw_config.dict())
```

### Configuration Factories

Create configuration programmatically:

```python
from ib_util.config_v3 import (
    AppConfig, ProjectConfig, GatewayConfig, ServiceConfig, 
    ServerConfig, ClientConfig
)

# Factory function for test configurations
def create_test_config(client_id: int = 999) -> AppConfig:
    return AppConfig(
        project=ProjectConfig(name="test-service", environment="development"),
        gateway=GatewayConfig(host="localhost", ports=[4002]),
        service=ServiceConfig(
            name="test-service",
            type="test",
            client=ClientConfig(id=client_id),
            server=ServerConfig(port=8999)
        )
    )

# Use in tests
test_config = create_test_config(client_id=123)
assert test_config.service.client.id == 123
```

## Development Workflow

### Hot Reload Development

Configuration v3 supports hot reloading for rapid development:

```python
# development.py - Your service with hot reload
from ib_util.config_v3 import load_config
import time
from pathlib import Path

def run_with_hot_reload():
    config_root = Path('config')
    last_modified = 0
    config = load_config('ib-stream')
    
    while True:
        # Check for configuration changes
        current_modified = max(
            (config_root / 'base.yaml').stat().st_mtime,
            (config_root / 'development.yaml').stat().st_mtime,
            (config_root / 'services' / 'ib-stream.yaml').stat().st_mtime
        )
        
        if current_modified > last_modified:
            print("🔄 Configuration changed, reloading...")
            config = load_config('ib-stream')
            last_modified = current_modified
            # Restart service components with new config
            
        time.sleep(1)
```

### Debug Workflows

```bash
# Quick validation during development
python -c "from ib_util.config_v3 import validate_config; exit(0 if validate_config('ib-stream') else 1)"

# Show configuration diff between environments
python -c "
from ib_util.config_v3 import load_config
import os
os.environ['IB_ENVIRONMENT'] = 'development'
dev = load_config('ib-stream')
os.environ['IB_ENVIRONMENT'] = 'production' 
prod = load_config('ib-stream')
print(f'Dev Client ID: {dev.service.client.id}')
print(f'Prod Client ID: {prod.service.client.id}')
"

# Validate specific configuration sections
python -c "
from ib_util.config_v3_categorical import validate_port, validate_client_id
print('Port 8080:', validate_port(8080).is_success())
print('Client 101:', validate_client_id(101).is_success())
"
```

### Testing Patterns

#### Unit Testing with Custom Configuration

```python
import pytest
from ib_util.config_v3 import AppConfig, ServiceConfig

def test_service_with_custom_config():
    # Create test configuration
    test_config = AppConfig(
        service=ServiceConfig(name="test", type="test")
    )
    
    # Test your service with known configuration
    result = my_service_function(test_config)
    assert result.service.client.id == expected_value

def test_configuration_validation():
    # Test configuration loading
    config = load_config('ib-stream', config_root='tests/fixtures/config')
    assert config.project.environment == Environment.DEVELOPMENT
```

#### Integration Testing

```python
def test_config_integration():
    # Test that configuration works end-to-end
    config = load_config('ib-stream')
    
    # Verify all required sections are present
    assert config.service.client.id > 0
    assert config.gateway.host
    assert config.gateway.ports
    
    # Verify validation worked
    assert 1 <= config.service.client.id <= 999999
    assert all(1024 <= port <= 65535 for port in config.gateway.ports)
```

## Extending the System

### Adding New Configuration Sections

1. **Define Pydantic Models**:

```python
from pydantic import BaseModel, Field
from typing import List

class MyCustomConfig(BaseModel):
    """Custom configuration section"""
    enabled: bool = True
    custom_parameter: str = "default"
    custom_list: List[str] = Field(default_factory=list)
    
    @field_validator('custom_parameter')
    @classmethod
    def validate_custom_parameter(cls, v):
        # Add custom validation logic
        if not v.startswith('custom_'):
            raise ValueError('Custom parameter must start with custom_')
        return v
```

2. **Extend AppConfig**:

```python
from ib_util.config_v3 import AppConfig

class ExtendedAppConfig(AppConfig):
    """Extended application configuration"""
    my_custom: MyCustomConfig = Field(default_factory=MyCustomConfig)
```

3. **Update YAML Files**:

```yaml
# config/base.yaml
my_custom:
  enabled: true
  custom_parameter: "custom_value"
  custom_list: ["item1", "item2"]
```

### Adding Categorical Constraints

```python
from ib_util.categorical import Constraint, Result, Success, Error

class CustomConstraint(Constraint[str]):
    """Custom categorical constraint"""
    
    def check(self, value: str) -> Result[str, str]:
        if value.startswith('valid_'):
            return Success(value)
        return Error(f"Value must start with 'valid_': {value}")

# Use in validation
CUSTOM_CONSTRAINT = CustomConstraint()
result = CUSTOM_CONSTRAINT.check("valid_example")  # Success
result = CUSTOM_CONSTRAINT.check("invalid")        # Error
```

### Creating Natural Transformations

```python
from ib_util.config_transformations import ConfigTransformations

class MyConfigTransformations(ConfigTransformations):
    @staticmethod
    def to_my_format(config: Dict[str, Any]) -> Dict[str, Any]:
        """Natural transformation to custom format"""
        return {
            'my_client_id': config.get('service', {}).get('client', {}).get('id'),
            'my_host': config.get('gateway', {}).get('host'),
            # ... custom transformation logic
        }
```

## Troubleshooting

### Common Issues

#### Configuration Not Found
```
FileNotFoundError: Configuration directory not found: config
```

**Solution**:
```bash
export IB_CONFIG_ROOT=$(pwd)/config
# Or pass explicitly:
config = load_config('ib-stream', config_root='/absolute/path/to/config')
```

#### Invalid Environment
```
ValueError: Invalid environment: staging. Must be 'development' or 'production'
```

**Solution**:
```bash
export IB_ENVIRONMENT=development  # or production
```

#### Validation Errors
```
ValueError: Configuration validation failed: Invalid port: 80. Must be between 1024 and 65535
```

**Solution**: Check your YAML configuration for invalid values:
```yaml
service:
  server:
    port: 8851  # Must be 1024-65535
```

#### Import Errors with Categorical Features
```
ImportError: attempted relative import with no known parent package
```

**Solution**: Use direct imports for testing:
```python
# Instead of:
from .categorical import Result

# Use:
import sys
import importlib.util
# ... direct module loading as shown in examples
```

### Debugging Configuration Loading

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Configuration loading will show detailed information
config = load_config('ib-stream')
```

View configuration step-by-step:

```python
from ib_util.config_v3 import ConfigLoader

loader = ConfigLoader('config')

# Load individual files to debug hierarchy
base = loader.load_yaml_file(Path('config/base.yaml'))
env = loader.load_yaml_file(Path('config/development.yaml'))  
service = loader.load_yaml_file(Path('config/services/ib-stream.yaml'))

print("Base config:", base)
print("Environment config:", env)
print("Service config:", service)

# Test merging
merged = loader.merge_configs(base, env)
print("After env merge:", merged)
```

### Performance Debugging

Time configuration loading:

```python
import time
from ib_util.config_v3 import load_config

start = time.time()
config = load_config('ib-stream')
duration = time.time() - start
print(f"Configuration loaded in {duration:.3f}s")

# Expected: ~0.050s for full configuration loading
```

Monitor configuration file changes:

```python
from pathlib import Path
import time

config_files = [
    Path('config/base.yaml'),
    Path('config/development.yaml'), 
    Path('config/services/ib-stream.yaml')
]

def check_modifications():
    for file in config_files:
        if file.exists():
            mtime = file.stat().st_mtime
            print(f"{file}: {time.ctime(mtime)}")

check_modifications()
```

### Getting Help

1. **View Configuration Schema**:
   ```python
   from ib_util.config_v3 import AppConfig
   print(AppConfig.model_json_schema())
   ```

2. **Check Categorical Laws** (Advanced):
   ```python
   # Run mathematical property tests
   python -c "exec(open('ib-util/ib_util/categorical.py').read())"
   ```

3. **Configuration Validation Details**:
   ```python
   from ib_util.config_v3 import validate_config
   is_valid = validate_config('ib-stream')
   if not is_valid:
       # Check logs for detailed validation errors
       print("Check configuration files for validation errors")
   ```

This developer guide provides comprehensive coverage of Configuration v3 features, from basic usage to advanced Category Theory concepts. Use it as a reference for both everyday development and advanced configuration manipulation.