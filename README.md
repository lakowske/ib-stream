# ib-stream
A market data streaming server for Interactive Brokers with modern configuration management and shared connection utilities.

## Features

- **Real-time market data streaming** via REST API and WebSocket
- **Contract lookup service** for Interactive Brokers securities  
- **Type-safe configuration management** with Pydantic validation and hot-reload
- **Smart instance allocation** using MD5 path hashing for unique client IDs and ports
- **Shared connection utilities** via ib-util module for reliable TWS/Gateway connections
- **Supervisor process management** with automatic restart and logging
- **Modern CLI tool** for configuration, services, and development workflows
- **Development workflow** with configuration hot-reload and testing tools

## Quick Start

### Prerequisites

1. Interactive Brokers Gateway or TWS running and configured for API access
2. Python 3.8+ installed
3. Make utility installed

### Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd ib-stream

# Build TWS API and setup environment
make setup

# Verify setup with the new CLI tool
python ib.py --help
```

### Using the ib.py CLI Tool

The project now uses a modern CLI tool for all configuration and service management:

```bash
# Configuration Management
python ib.py config validate              # Validate configuration system
python ib.py config show                 # Show current configuration
python ib.py config watch                # Watch for configuration changes
python ib.py config compare ib-stream ib-contract  # Compare configurations

# Service Management  
python ib.py services start              # Start all services
python ib.py services status             # Check service status
python ib.py services logs               # View service logs
python ib.py services stop               # Stop all services

# Testing & Validation
python ib.py test connection             # Test IB Gateway connection
python ib.py test contract AAPL          # Test contract lookup

# Development Tools
python ib.py dev setup                   # Development environment setup
python ib.py dev tools                   # Install development tools
python ib.py dev clean                   # Clean build artifacts
```

### Starting Services

```bash
# Start services with the CLI (recommended)
python ib.py services start

# Or use traditional make command
make start-supervisor

# Check service status (shows your generated ports)
python ib.py services status

# View real-time logs
python ib.py services logs
```

## Architecture

### Core Components

- **ib-stream/**: Market data streaming service (port determined by project path hash)
- **ib-contract/**: Contract lookup service (port determined by project path hash)  
- **ib-util/**: Shared connection utilities and configuration management
- **ib.py**: Modern CLI tool for all operations
- **Configuration v2**: Type-safe configuration with Pydantic validation

### Configuration System (v2)

The project uses a modern type-safe configuration system with automatic fallback:

#### Configuration Architecture
- **Type-safe validation** with Pydantic schemas
- **Environment-specific configurations** (development, production, staging)
- **Automatic instance isolation** with unique client IDs and ports
- **Hot-reload capabilities** for development
- **Backward compatibility** with legacy configuration

#### Configuration Files
- **Production**: `ib-stream/config/production.env`
- **Development**: `ib-stream/config/development.env`
- **Instance Config**: `ib-stream/config/instance.env` (auto-generated)
- **Service-specific**: Environment variables per service

#### Dynamic Value Generation
Instance-specific values are generated automatically using MD5 hash of the project path:
- **Client IDs**: Range 100-999 (unique per service)
- **HTTP Ports**: Range 8000-9000 (unique per service)
- **ib-stream**: Client ID 851, Port 8851
- **ib-contract**: Client ID 852, Port 8861

### Services

#### ib-stream (Market Data)
- **Endpoint**: `http://localhost:8851/` (production server)
- **Health**: `http://localhost:8851/health`
- **WebSocket**: `ws://localhost:8851/ws/control`
- **Features**: Real-time streaming, buffer management, V3 optimized storage

#### ib-contracts (Contract Lookup)
- **Endpoint**: `http://localhost:8861/` (production server)
- **Health**: `http://localhost:8861/health`
- **Features**: Contract lookup, symbol resolution, IB contract details, trading hours, market status, dual storage caching

## CLI Usage Examples

### Configuration Management

```bash
# Validate the entire configuration system
python ib.py config validate

# Show configuration for all services
python ib.py config show

# Show detailed configuration for specific service
python ib.py config show --service ib-stream --format detailed

# Compare configurations between services
python ib.py config compare ib-stream ib-contract

# Watch for configuration changes (development)
python ib.py config watch --service ib-stream
```

### Service Operations

```bash
# Start services in production mode
python ib.py services start --environment production

# Check service status and health
python ib.py services status

# View logs for specific service
python ib.py services logs --service ib-stream-remote

# Stop all services
python ib.py services stop
```

### Testing & Validation

```bash
# Test connection to IB Gateway
python ib.py test connection

# Test contract lookup for specific symbols
python ib.py test contract AAPL
python ib.py test contract MNQ
```

### Development Workflow

```bash
# Set up development environment
python ib.py dev setup

# Install development tools (linting, testing, etc.)
python ib.py dev tools

# Start configuration watcher for hot-reload
python ib.py config watch

# In another terminal, make configuration changes and see live updates
```

## API Usage

### REST Endpoints

```bash
# Check service health (production server)
curl http://localhost:8851/health        # ib-stream health
curl http://localhost:8861/health        # ib-contracts health

# Contract lookups - Multiple methods available
curl http://localhost:8861/lookup/AAPL/STK           # Symbol-based lookup (all contracts for symbol/type)
curl http://localhost:8861/contracts/265598          # Direct contract ID lookup (fast, cached)
curl http://localhost:8861/lookup/MNQ/FUT            # Futures contract lookup

# Trading hours and market status
curl http://localhost:8861/market-status/711280073   # Check if market is currently open
curl http://localhost:8861/trading-hours/711280073   # Get detailed trading hours
curl http://localhost:8861/trading-schedule/711280073 # Get upcoming trading schedule

# Cache management and monitoring  
curl http://localhost:8861/cache/status              # View cache statistics and performance
curl -X POST http://localhost:8861/cache/clear       # Clear all cache entries

# Background stream health monitoring
curl http://localhost:8851/background/health/summary   # Overall background stream health
curl http://localhost:8851/background/health/711280073 # Health for specific contract (MNQ)
curl http://localhost:8851/background/health/detailed  # Detailed health for all contracts

# Stream market data (CLI)
cd ib-stream && python -m ib_stream.stream AAPL --number 10
```

### WebSocket API

```python
import asyncio
import websockets
import json

async def stream_data():
    # Connect to ib-stream WebSocket (production port)
    async with websockets.connect('ws://localhost:8851/ws/control') as ws:
        # Get server status
        status = json.loads(await ws.recv())
        print(f"Server status: {status}")
        
        # Send ping
        await ws.send(json.dumps({"type": "ping"}))
        pong = json.loads(await ws.recv())
        print(f"Pong: {pong}")

asyncio.run(stream_data())
```

## Development

### Project Structure

```
ib-stream/
├── ib-stream/           # Market data streaming service
├── ib-contract/         # Contract lookup service  
├── ib-util/             # Shared utilities and configuration
├── ib.py                # Modern CLI tool for all operations
├── Makefile             # Build automation only
├── supervisor.conf      # Process management configuration
├── config-*.py          # Configuration analysis tools
└── logs/                # Service logs
```

### CLI Command Reference

```bash
# Show all available commands
python ib.py --help

# Show commands for specific group
python ib.py config --help
python ib.py services --help
python ib.py test --help
python ib.py dev --help

# Get version information
python ib.py --version
```

### Makefile (Build Automation Only)

The Makefile now focuses solely on build automation:

```bash
make setup            # Full environment setup
make build-api        # Build TWS API only
make install-packages # Install packages in development mode
make dev-tools        # Install development tools
make clean            # Clean build artifacts
```

**Note**: For service management, configuration, and development workflows, use the `ib.py` CLI tool instead.

### Contract Lookup Architecture

#### Dual Storage Pattern
The ib-contract service uses an advanced dual storage pattern for optimal performance:

**Symbol-Based Cache**: Traditional lookup by symbol and security type
- File format: `YYYYMMDD-contracts_SYMBOL_TYPE.json`
- Example: `20250820-contracts_AAPL_STK.json`
- Contains all contract variants for a symbol

**Contract ID Cache**: Direct lookup by contract ID for maximum speed
- File format: `YYYYMMDD-contract_CONTRACTID.json` 
- Example: `20250820-contract_711280073.json`
- Single contract with full details

#### Cache Architecture
- **Memory Cache**: Fast in-memory storage for active lookups
- **File Cache**: Persistent storage with date-prefixed organization
- **Auto-Expiration**: 24-hour cache duration with automatic cleanup
- **IB Gateway Fallback**: Automatic lookup via IB API when cache misses
- **Cross-Reference**: Symbol lookups populate both caches simultaneously

#### Performance Benefits
- **Contract ID Lookups**: Sub-20ms response times from memory/file cache
- **Symbol Lookups**: ~15ms for cached results, ~110ms for new contracts
- **Cache Persistence**: Survives service restarts with zero data loss
- **Dual Access**: Support both traditional symbol-based and modern ID-based workflows

### Remote Gateway Setup

To connect to IB Gateway running on a remote machine:

1. **Configure in environment file** (`ib-stream/config/production.env`):
   ```bash
   IB_STREAM_HOST=192.168.0.60
   IB_STREAM_PORTS=4002,4001
   ```

2. **Test connection**:
   ```bash
   python ib.py test connection
   ```

### Configuration Hot-Reload (Development)

The new configuration system supports hot-reload for development:

```bash
# Start configuration watcher
python ib.py config watch

# In another terminal, edit configuration files
# Changes are detected and applied automatically
vim ib-stream/config/development.env
```

### Logging

View logs using the CLI tool:

```bash
# View logs for all services
python ib.py services logs

# View logs for specific service
python ib.py services logs --service ib-stream-remote

# Traditional approach (still works)
make supervisor-logs
tail -f /var/log/supervisor/ib-stream-remote-stdout.log
```

## Troubleshooting

### Common Issues

**Configuration Problems**
```bash
# Validate entire configuration system
python ib.py config validate

# Show detailed configuration
python ib.py config show --format detailed

# Compare service configurations for differences
python ib.py config compare ib-stream ib-contract
```

**Connection Issues**
```bash
# Test IB Gateway connection
python ib.py test connection

# Check service status
python ib.py services status

# View service logs for errors
python ib.py services logs
```

**Service Problems**
```bash
# Check if services are running
python ib.py services status

# Restart services
python ib.py services stop
python ib.py services start

# View detailed logs
python ib.py services logs --service ib-stream-remote
```

### Debug Mode

For detailed debugging, you can still run services directly:

```bash
# Debug ib-stream
cd ib-stream && python -m ib_stream.api_server

# Debug ib-contracts  
cd ib-contract && python api_server.py

# Debug configuration
python ib.py config validate --verbose
```

## Recent Updates (v2.0)

### Configuration System v2
- **Complete migration** to type-safe configuration with Pydantic validation
- **Hot-reload capabilities** for development workflow
- **Environment-specific configs** with automatic instance isolation

### Critical Fixes
- **Storage initialization** resolved (MultiStorageV3 Path object conversion)
- **Health endpoint synchronization** fixed to reflect actual system state
- **V3 storage optimization** verified with 59% space reduction vs V2 format
- **Background streaming** for MNQ contract fully functional with real-time data

### Service Orchestration
- **Unified CLI tool** (`ib.py`) replacing legacy wrapper scripts
- **Direct supervisor integration** with proper environment handling
- **Clean service management** with health monitoring and status reporting

### Production Verification
```bash
# All systems verified working:
python ib.py services status    # ✅ Services running
curl localhost:8851/health      # ✅ Health endpoints accurate
find ./ib-stream/storage -type f | wc -l  # ✅ Data files active
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Use the CLI tool for development: `python ib.py dev setup`
4. Make changes following the existing code style
5. Test with: `python ib.py test connection`
6. Update documentation as needed
7. Submit a pull request

## License

[Add license information]