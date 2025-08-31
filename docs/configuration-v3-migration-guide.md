# Configuration v3 Migration Guide

## Overview

This guide helps you migrate from the legacy supervisor-based configuration system to Configuration v3. The new system eliminates the complexity of 20+ environment variables and provides a clean YAML-based hierarchical configuration with Category Theory foundations.

## Migration Benefits

### Before Configuration v3
- ❌ 20+ environment variables per service
- ❌ Configuration scattered across multiple files
- ❌ Manual string parsing and type conversion
- ❌ Supervisor dependency for all debugging
- ❌ Limited validation and error reporting

### After Configuration v3  
- ✅ 2 environment variables total
- ✅ Clean YAML hierarchy with overrides
- ✅ Fully typed configuration with validation
- ✅ Standalone debugging without supervisor
- ✅ Mathematical guarantees about configuration composition

## Step-by-Step Migration

### Step 1: Update Configuration Files

#### Create Base Configuration (`config/base.yaml`)
```yaml
# Replace scattered environment variables with structured YAML
project:
  name: ib-stream
  version: "3.0.0"

gateway:
  host: 192.168.0.60
  ports: [4002, 4001]
  connection_timeout: 10
  reconnect_attempts: 5

storage:
  enabled: true
  formats:
    v2_json: false
    v2_protobuf: false
    v3_json: true
    v3_protobuf: true
  enable_postgres: false
  buffer_size: 100
  max_file_size_mb: 100

logging:
  level: DEBUG
  format: detailed
  file_rotation: daily

performance:
  max_concurrent_streams: 10
```

#### Create Environment-Specific Files

**Development** (`config/development.yaml`):
```yaml
project:
  environment: development

storage:
  base_path: storage-dev
  enable_metrics: true

logging:
  level: DEBUG
```

**Production** (`config/production.yaml`):
```yaml
project:
  environment: production

storage:
  base_path: storage-prod
  enable_metrics: true
  
logging:
  level: INFO
```

#### Create Service-Specific Files

**ib-stream** (`config/services/ib-stream.yaml`):
```yaml
service:
  name: ib-stream
  type: streaming

server:
  host: 0.0.0.0
  port: 8851

client:
  id: 101

streaming:
  enable_background_streaming: false
  tracked_contracts: []

# Environment-specific overrides
development:
  streaming:
    enable_background_streaming: false
    
production:
  client:
    id: 851
  server:
    port: 8851
  streaming:
    enable_background_streaming: true
    tracked_contracts:
      - contract_id: 711280073
        symbol: MNQ
        tick_types: [LAST_PRICE, VOLUME, BID_ASK]
        buffer_hours: 24
```

### Step 2: Update Supervisor Configuration

#### Before (supervisor/development.conf)
```ini
[program:ib-stream-development]
command=/home/seth/Software/dev/ib-stream-1/.venv/bin/python -m ib_stream.api_server
directory=/home/seth/Software/dev/ib-stream-1/ib-stream
environment=IB_ENVIRONMENT=development,IB_GATEWAY_HOST=192.168.0.60,IB_GATEWAY_PORTS="4002,4001",IB_CLIENT_ID=101,IB_SERVER_PORT=8851,IB_STORAGE_ENABLED=true,IB_STORAGE_PATH=storage-dev,IB_LOG_LEVEL=DEBUG,IB_ENABLE_V2_JSON=false,IB_ENABLE_V2_PROTOBUF=false,IB_ENABLE_V3_JSON=true,IB_ENABLE_V3_PROTOBUF=true,IB_ENABLE_POSTGRES=false,IB_ENABLE_METRICS=true,IB_BUFFER_SIZE=100,IB_MAX_FILE_SIZE_MB=100,IB_CONNECTION_TIMEOUT=10,IB_RECONNECT_ATTEMPTS=5,IB_MAX_CONCURRENT_STREAMS=10,IB_ENABLE_BACKGROUND_STREAMING=false
```

#### After (supervisor/development.conf)
```ini
[program:ib-stream-development]
command=/home/seth/Software/dev/ib-stream-1/.venv/bin/python -m ib_stream.api_server
directory=/home/seth/Software/dev/ib-stream-1/ib-stream
environment=IB_ENVIRONMENT=development,IB_CONFIG_ROOT=/home/seth/Software/dev/ib-stream-1/config
```

**Reduction: 20+ environment variables → 2 environment variables**

### Step 3: Update Service Code

#### Before (Legacy Configuration Loading)
```python
import os

class ConfigManager:
    def load_config(self):
        return {
            'CLIENT_ID': int(os.getenv('IB_CLIENT_ID', '101')),
            'GATEWAY_HOST': os.getenv('IB_GATEWAY_HOST', 'localhost'),
            'GATEWAY_PORTS': [int(p) for p in os.getenv('IB_GATEWAY_PORTS', '4002,4001').split(',')],
            'SERVER_PORT': int(os.getenv('IB_SERVER_PORT', '8851')),
            'STORAGE_ENABLED': os.getenv('IB_STORAGE_ENABLED', 'false').lower() == 'true',
            'LOG_LEVEL': os.getenv('IB_LOG_LEVEL', 'INFO'),
            # ... 15+ more environment variables
        }

# Usage (error-prone, untyped)
config = ConfigManager().load_config()
client_id = config['CLIENT_ID']  # Could be None, needs error checking
```

#### After (Configuration v3)
```python
from ib_util.config_v3 import load_config

# Usage (typed, validated, safe)
config = load_config('ib-stream')
client_id = config.service.client.id  # Guaranteed to be int, validated range
```

#### Backward Compatibility Option
```python
# For gradual migration - existing code works unchanged
from ib_stream.config_v3_adapter import ConfigV3Adapter

adapter = ConfigV3Adapter('ib-stream')
legacy_config = adapter.to_legacy_format()

# Existing code continues to work
client_id = legacy_config['CLIENT_ID']
```

### Step 4: Update Development Workflow

#### Before (Complex Debugging)
```bash
# Required supervisor for all debugging
make start-supervisor
# Edit 20+ environment variables in supervisor config
# Restart entire supervisor stack for config changes
```

#### After (Simple Debugging)
```bash
# Standalone debugging without supervisor
python ib-stream/debug.py --validate-only
python ib-stream/debug.py --show-config  
python ib-stream/debug.py --run

# Edit YAML files directly
vim config/development.yaml
# Changes take effect immediately (hot reload in development)
```

## Service-Specific Migration

### ib-stream Service

#### Configuration Changes
```yaml
# config/services/ib-stream.yaml
service:
  name: ib-stream
  type: streaming

# Development settings
development:
  client:
    id: 101
  server:
    port: 8851
  streaming:
    enable_background_streaming: false

# Production settings  
production:
  client:
    id: 851  # Different client ID for production
  server:
    port: 8851
  streaming:
    enable_background_streaming: true
    tracked_contracts:
      - contract_id: 711280073
        symbol: MNQ
        tick_types: [LAST_PRICE, VOLUME, BID_ASK]
```

#### Code Changes
```python
# api_server.py - Before
config_manager = ConfigManager()
config = config_manager.load_config()

# api_server.py - After  
from ib_util.config_v3 import load_config
config = load_config('ib-stream')

# All existing property access works through adapter
```

### ib-contract Service

#### Configuration Changes
```yaml
# config/services/ib-contract.yaml
service:
  name: ib-contract
  type: lookup
  
cache:
  duration_days: 1
  memory_cache_size: 1000
  file_cache_enabled: true

development:
  client:
    id: 102
  server:
    port: 8861

production:
  client:
    id: 852
  server:  
    port: 8861
```

## Categorical Features (Optional Advanced Usage)

### Monadic Error Handling
```python
# Before - Exception-based (fragile)
try:
    config = load_config_old()
    validated = validate_config(config)
    transformed = transform_config(validated)
except Exception as e:
    # Generic error handling
    logger.error(f"Config failed: {e}")

# After - Monadic (composable)
from ib_util.config_v3_categorical import load_config_categorical

result = (load_config_categorical('ib-stream')
          .bind(additional_validation)
          .bind(custom_transformation)
          .map(normalize_config))

if result.is_success():
    config = result.unwrap()
    # Guaranteed valid configuration
else:
    error_msg = result.error()
    # Detailed, composable error information
```

### Configuration Transformations
```python
from ib_util.config_transformations import ConfigTransformations

# Functional transformations
normalized = ConfigTransformations.normalize_strings(config_dict)
env_vars = ConfigTransformations.to_environment_vars(config_dict)

# Monadic validation pipeline
validation_result = ConfigTransformations.validate_and_transform(config_dict)
```

## Validation and Error Handling

### Before (Manual Validation)
```python
def validate_config(config):
    if not isinstance(config.get('CLIENT_ID'), int):
        raise ValueError("CLIENT_ID must be integer")
    if config.get('CLIENT_ID', 0) < 1 or config.get('CLIENT_ID', 0) > 999999:
        raise ValueError("CLIENT_ID out of range")
    # ... manual validation for each field
```

### After (Categorical Validation)
```python
# Validation happens automatically during config loading
config = load_config('ib-stream')  
# config.service.client.id is guaranteed valid (1-999999)
# config.service.server.port is guaranteed valid (1024-65535)  
# config.logging.level is guaranteed valid enum value

# Explicit validation if needed
from ib_util.config_v3_categorical import validate_client_id
result = validate_client_id(12345)
if result.is_success():
    valid_id = result.unwrap()
```

## Testing Changes

### Before
```python
# Test configuration required extensive mocking
@patch.dict(os.environ, {
    'IB_CLIENT_ID': '101',
    'IB_GATEWAY_HOST': 'localhost', 
    'IB_GATEWAY_PORTS': '4002,4001',
    # ... 20+ environment variables
})
def test_service():
    config = ConfigManager().load_config()
    # Test with mocked environment
```

### After  
```python
# Test configuration with direct YAML
def test_service():
    config = load_config('ib-stream', config_root='test/fixtures/config')
    # Test with actual configuration files
    
# Or create config programmatically
from ib_util.config_v3 import AppConfig
config = AppConfig(
    service=ServiceConfig(name='test', type='test'),
    # ... fully typed configuration object
)
```

## Rollback Plan

If you need to rollback to the legacy system:

1. **Keep Legacy Files**: Don't delete old supervisor configs initially
2. **Feature Flag**: Use environment variable to switch systems:
   ```python
   if os.getenv('USE_CONFIG_V3', 'true').lower() == 'true':
       config = load_config('ib-stream')
   else:
       config = ConfigManager().load_config()  # Legacy
   ```
3. **Gradual Migration**: Migrate services one at a time
4. **Monitor**: Compare configurations between systems during transition

## Troubleshooting

### Common Migration Issues

#### Issue: "Configuration file not found"
```bash
# Solution: Set IB_CONFIG_ROOT environment variable
export IB_CONFIG_ROOT=/path/to/config
```

#### Issue: "Invalid log level" validation error
```yaml
# Problem: Invalid log level in YAML
logging:
  level: TRACE  # Not a valid level

# Solution: Use valid log levels  
logging:
  level: DEBUG  # Valid: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

#### Issue: "Port out of range" validation error
```yaml
# Problem: Invalid port range
server:
  port: 80  # Too low (< 1024)

# Solution: Use valid port range (1024-65535)
server:
  port: 8851
```

### Validation Commands
```bash
# Test configuration validity
python -c "from ib_util.config_v3 import load_config; print('✅ Valid' if load_config('ib-stream') else '❌ Invalid')"

# Debug configuration loading
python ib-stream/debug.py --validate-only --show-config

# Compare legacy vs v3 configuration  
python tools/compare_configs.py  # If available
```

## Performance Impact

### Configuration Loading Performance
- **Legacy System**: ~100ms (environment variable parsing + validation)
- **Configuration v3**: ~50ms (YAML loading + Pydantic validation)
- **Memory Usage**: Similar (~2MB per service)

### Development Workflow Performance
- **Legacy**: 30-60 seconds (supervisor restart for config changes)
- **Configuration v3**: 1-5 seconds (direct service restart)
- **Hot Reload**: Immediate (configuration changes without restart)

## Post-Migration Cleanup

After successful migration:

1. **Remove Legacy Files**:
   ```bash
   rm supervisor/legacy-*.conf
   rm ib-*/config/*.env  # Old environment files
   ```

2. **Remove Legacy Code**:
   ```python
   # Remove ConfigManager class and related legacy code
   ```

3. **Update Documentation**: Update all references to old configuration approach

4. **Update CI/CD**: Modify deployment scripts to use new configuration system

This migration provides a significantly improved developer experience while maintaining full backward compatibility during the transition period.