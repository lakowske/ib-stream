# VS Code Debug Setup for IB Stream

This directory contains VS Code configuration for debugging IB Stream with Configuration System v3.

## 🚀 Quick Start

1. **Open in VS Code**: Open the project root (`/home/seth/Software/dev/ib-stream-1`) in VS Code
2. **Select Python Interpreter**: Choose `.venv/bin/python` when prompted
3. **Stop Production Services**: Run task "Stop Production Services" (Ctrl+Shift+P → Tasks: Run Task)
4. **Start Debugging**: Press F5 or go to Run and Debug panel → "Debug IB Stream (Standalone)"

## 🐛 Debug Configurations

### Primary Debug Targets

**"Debug IB Stream (Standalone)"** - *Recommended for debugging*
- Uses the standalone `debug_runner.py` 
- No supervisor complexity
- Configuration System v3
- Development port 8774
- Full step-through debugging

**"Debug IB Stream (Development)"** - *Direct API server*
- Launches `api_server.py` directly
- Production port 8851
- Good for API endpoint debugging

### Additional Debug Targets

**"Debug IB Contract Service"**
- Debug the contract lookup service
- Port 8861

**"Debug Config Validation"** 
- Debug configuration loading issues
- Runs `ib.py config validate --verbose`

**"Debug Contract Lookup"**
- Debug contract lookup for AAPL
- Test TWS connection and data retrieval

## 🔧 VS Code Tasks

Access via Ctrl+Shift+P → "Tasks: Run Task":

- **Stop Production Services**: Safely stop running services before debugging
- **Start Production Services**: Restart production services after debugging
- **Validate Configuration**: Test Configuration System v3
- **Run Tests**: Execute the test suite  
- **Format Code**: Format code with ruff

## 📋 Debugging Workflow

### Standard Debugging Session:

1. **Prepare Environment**:
   ```bash
   # Stop production services to avoid port conflicts
   Ctrl+Shift+P → Tasks: Run Task → "Stop Production Services"
   ```

2. **Set Breakpoints**:
   - Configuration loading: `ib-stream/src/ib_stream/config.py:194`
   - Service startup: `ib-stream/src/ib_stream/api_server.py:create_app()`
   - TWS connection: `ib-util/ib_util/connection.py:connect_and_start()`
   - Storage initialization: `ib-stream/src/ib_stream/storage/`

3. **Start Debugging**:
   ```
   F5 or Run → "Debug IB Stream (Standalone)"
   ```

4. **Debug Features Available**:
   - Step through Configuration v3 loading
   - Inspect YAML config hierarchical loading  
   - Debug TWS connection establishment
   - Monitor storage system initialization
   - Test API endpoints with breakpoints

5. **Cleanup**:
   ```bash
   # Restart production services when done
   Ctrl+Shift+P → Tasks: Run Task → "Start Production Services"
   ```

### Common Debug Scenarios:

**Configuration Issues**:
- Set breakpoint in `create_config()` in `ib-stream/src/ib_stream/config.py`
- Inspect the v3 config loading process
- Check YAML file hierarchical merging

**TWS Connection Problems**:
- Set breakpoint in `IBConnection.connect_and_start()` 
- Step through port attempts and handshake process
- Monitor connection state changes

**Storage System Issues**:
- Set breakpoints in storage initialization
- Monitor storage format selection (v2/v3 JSON/Protobuf)
- Check file creation and rotation

**API Endpoint Issues**:
- Set breakpoints in FastAPI route handlers
- Test health endpoints, streaming endpoints
- Monitor request/response flow

## 🔍 Key Debugging Points

### Configuration System v3 Entry Points:
```python
# Main config creation
ib-stream/src/ib_stream/config.py:194 - create_config()

# YAML loading and hierarchy 
ib-util/ib_util/config_v3.py:load_config()

# Configuration validation
ib-util/ib_util/categorical.py - Result monads and validation
```

### Service Startup Sequence:
```python
# 1. FastAPI app creation
ib-stream/src/ib_stream/api_server.py:create_app()

# 2. Configuration loading  
ib-stream/src/ib_stream/config.py:create_config()

# 3. Storage initialization
ib-stream/src/ib_stream/storage/multi_storage_v3.py

# 4. TWS connection (if enabled)
ib-util/ib_util/connection.py:IBConnection.connect_and_start()
```

## ⚙️ Environment Variables

The debug configurations automatically set:
- `PYTHONPATH`: Points to ib-util and ib-stream/src
- `IB_ENVIRONMENT`: Set to "development"  
- `IB_CONFIG_ROOT`: Points to config directory

## 🚨 Important Notes

1. **Port Conflicts**: Always stop production services before debugging to avoid port 8851/8861 conflicts
2. **Configuration**: Debug uses Configuration System v3 with development settings
3. **TWS Connection**: Set up IB Gateway/TWS on 192.168.0.60:4002 for connection testing
4. **Storage**: Debug mode creates storage files in `storage-dev/` directory

## 📚 Additional Resources

- Configuration v3 Architecture: `docs/configuration-v3-architecture.md`
- Migration Guide: `docs/configuration-v3-migration-guide.md` 
- Developer Guide: `docs/configuration-v3-developer-guide.md`