# Project Commands

## ⚠️ CRITICAL WARNING ⚠️

**NEVER stop supervisor services without explicit user permission!**

The production server continuously records live market data to disk. Stopping it unexpectedly will:
- **Lose valuable market data** that cannot be recovered
- **Break historical data continuity** for analysis and backtesting
- **Interrupt critical data collection** during market hours

**Always ask the user before stopping production servers!**

Safe commands to check status:
- `supervisorctl status` - Check which servers are running
- `curl -s http://localhost:$(python -c "from generate_instance_config import generate_instance_config; print(generate_instance_config()['stream_port'])")/health | jq .` - Check streaming server health
- `curl -s http://localhost:$(python -c "from generate_instance_config import generate_instance_config; print(generate_instance_config()['contracts_port'])")/health | jq .` - Check contracts server health
- `find storage -name "*.pb" -newermt "5 minutes ago" | wc -l` - Verify data is being recorded

## Quick Start - Start Both Servers

```bash
# Start supervisor with dynamic configuration:
make start-supervisor

# Or manually with the startup script:
./start-supervisor.sh

# Check both are running (shows your generated ports):
make supervisor-status

# Test health endpoints:
python generate_instance_config.py  # Shows your ports
curl -s http://localhost:$(python -c "from generate_instance_config import generate_instance_config; print(generate_instance_config()['stream_port'])")/health | jq .status
curl -s http://localhost:$(python -c "from generate_instance_config import generate_instance_config; print(generate_instance_config()['contracts_port'])")/health | jq .status
```

## Server Management with Supervisor

This project uses supervisor for managing server processes in the background with automatic logging and process monitoring.

### Start the Servers

```bash
# Start supervisor with dynamic configuration
make start-supervisor

# Start individual services  
make supervisor-start                   # Start ib-stream-remote service
./supervisor-wrapper.sh start ib-contracts  # Start contracts service

# Start development servers with hot reload
./supervisor-wrapper.sh start ib-stream-dev      # Development streaming server with --reload
./supervisor-wrapper.sh start ib-contracts-dev   # Development contracts server with --reload

# Start all services at once
./supervisor-wrapper.sh start all
```

**Important Notes:**
- Supervisor configuration uses `%(ENV_VAR)s` substitution for dynamic values
- **start-supervisor.sh** automatically generates instance config and exports environment variables
- **supervisor-wrapper.sh** loads instance config for all supervisorctl commands
- Ports and client IDs are generated automatically using MD5 hash of project path
- Services are configured to auto-restart on failure
- Uses shared ib-util module for reliable IB Gateway connections

### Server Management

```bash
# Check status of all services (shows generated ports)
make supervisor-status

# Check status of specific service
./supervisor-wrapper.sh status ib-stream-remote

# Stop specific services
make supervisor-stop                     # Stop all services 
./supervisor-wrapper.sh stop ib-stream-remote
./supervisor-wrapper.sh stop ib-contracts

# Restart services
make supervisor-restart                  # Restart ib-stream-remote
./supervisor-wrapper.sh restart ib-contracts

# Stop all running services
./supervisor-wrapper.sh stop all

# Reload supervisor configuration
./supervisor-wrapper.sh reread
./supervisor-wrapper.sh update
```

### Log Management

```bash
# View real-time logs for services
tail -f /var/log/supervisor/ib-stream-remote-stdout.log
tail -f /var/log/supervisor/ib-stream-remote-stderr.log
tail -f /var/log/supervisor/ib-contracts-stdout.log
tail -f /var/log/supervisor/ib-contracts-stderr.log

# View static logs
./supervisor-wrapper.sh tail ib-stream-remote
./supervisor-wrapper.sh tail ib-stream-remote stderr
./supervisor-wrapper.sh tail ib-contracts
./supervisor-wrapper.sh tail ib-contracts stderr

# Follow logs in real-time
make supervisor-logs                            # Follow ib-stream-remote logs
./supervisor-wrapper.sh tail -f ib-stream-remote stderr
```

### Development Workflow

```bash
# Start development servers with hot reload
supervisorctl start ib-stream-dev
supervisorctl start ib-contracts-dev

# Watch logs in another terminal
supervisorctl tail -f ib-stream-dev
supervisorctl tail -f ib-contracts-dev

# Stop development servers when done
supervisorctl stop ib-stream-dev
supervisorctl stop ib-contracts-dev

# Restart development servers (to pick up code changes)
supervisorctl restart ib-stream-dev
supervisorctl restart ib-contracts-dev
```

## Log Files

Supervisor automatically saves logs to:
- `/var/log/supervisor/ib-stream-remote-stdout.log` - streaming server stdout logs
- `/var/log/supervisor/ib-stream-remote-stderr.log` - streaming server stderr logs  
- `/var/log/supervisor/ib-contracts-stdout.log` - contract server stdout logs
- `/var/log/supervisor/ib-contracts-stderr.log` - contract server stderr logs
- `/var/log/supervisor/ib-stream-dev-stdout.log` - development streaming server logs
- `/var/log/supervisor/ib-contracts-dev-stdout.log` - development contracts server logs

## Configuration Files

- `supervisor.conf` - Main supervisor configuration with environment variable support
- `generate_instance_config.py` - Automatic configuration generator (called by start-supervisor.sh)
- `ib-stream/config/remote-gateway.env` - Configuration for connecting to remote IB Gateway
- `ib-stream/config/ssh-tunnel.env` - SSH tunnel configuration for remote connections
- `ib-stream/config/query-only.env` - Environment configuration for query-only mode
- Process IDs and supervisor state are managed automatically by supervisor daemon

## Makefile Commands

The project includes a comprehensive Makefile for environment setup and development workflow:

### Initial Setup
```bash
make setup           # Full environment setup (builds API, creates venv, installs packages)
make build-api       # Build TWS API only
make venv           # Create virtual environment only
make install        # Install Python packages only
```

### Development & Testing  
```bash
make test-connection # Test connection to remote gateway
make dev-server     # Start development server with remote gateway
make clean          # Clean build artifacts and temporary files
```

### Build Process Details
- **TWS API Build**: Automatically builds `contrib/twsapi_macunix.1030.01/IBJts/source/pythonclient/`
- **Virtual Environment**: Creates `.venv/` with proper Python isolation
- **Package Installation**: Installs both ib-stream and ib-util packages in development mode
- **Dynamic Config**: Instance configuration generated automatically during supervisor startup

### Usage Examples
```bash
# Full project setup from scratch
make setup

# Test your remote gateway connection
make test-connection

# Start both services with supervisor
make start-supervisor

# Check status and see your generated ports
make supervisor-status

# View logs
make supervisor-logs

# Stop services when done
make supervisor-stop
```

## Remote Gateway Configuration

### Connecting to Remote IB Gateway

To connect ib-stream to a remote IB Gateway (e.g., running on 192.168.0.60):

#### Quick Setup
```bash
# Full development environment setup
make setup

# Test connection to remote gateway
make test-connection

# Start server with remote gateway
make dev-server
```

#### Manual Configuration
```bash
# Set environment to use remote gateway config
export IB_STREAM_ENV=remote-gateway

# Test CLI with remote gateway
cd ib-stream && python -m ib_stream.stream 265598 --number 5
```

#### Configuration File
Remote gateway settings are in `ib-stream/config/remote-gateway.env`:
- `IB_STREAM_HOST=192.168.0.60` - Remote gateway IP
- `IB_STREAM_PORTS=4002` - Gateway port (4002 for Paper, 4001 for Live)
- `IB_STREAM_CLIENT_ID=${IB_STREAM_CLIENT_ID:-374}` - Instance-specific client ID (generated from path hash)
- `IB_STREAM_PORT=${IB_STREAM_PORT:-8774}` - HTTP server port (generated from path hash)
- `IB_CONTRACTS_PORT=${IB_CONTRACTS_PORT:-8784}` - Contract service port (generated from path hash + 10)

#### Shared Connection Architecture
Both `ib-stream` and `ib-contract` services now use the shared `ib-util` module for consistent connection handling:
- **IBConnection class**: Handles proper IB API handshake and connection events
- **Environment loading**: Automatic configuration loading from .env files
- **Smart client allocation**: Unique client IDs (100-999) and ports (8000-9000) generated using MD5 hash of project path
- **Connection reliability**: Proper `nextValidId` callback handling for connection confirmation

## Architecture Overview

### Service Architecture
The project uses a microservices architecture with shared utilities:

```
ib-stream-1/
├── ib-stream/          # Market data streaming service
│   ├── src/ib_stream/  # Core streaming functionality
│   └── config/         # Environment configurations
├── ib-contract/        # Contract lookup service
│   └── contract_lookup.py  # Contract resolution logic
├── ib-util/            # Shared connection utilities
│   └── ib_util/        # IBConnection and configuration handling
└── supervisor.conf     # Process management
```

### Key Components

#### IBConnection (ib-util/ib_util/connection.py)
Shared base class for reliable IB Gateway connections:
- Handles connection lifecycle and proper handshake
- Waits for `nextValidId` callback before marking connection as ready
- Provides consistent connection status across services
- Supports configuration loading from environment files

#### StreamingApp (ib-stream/src/ib_stream/streaming_app.py)
Market data streaming application using composition pattern:
- Uses IBConnection for reliable connection handling
- Implements EWrapper for market data callbacks
- Delegates connection management to ib-util

#### ContractLookupApp (ib-contract/contract_lookup.py)
Contract lookup service inheriting from IBConnection:
- Direct inheritance for simple contract resolution
- Automatic configuration loading
- Reliable connection status for health endpoints

### Configuration System
- **Environment-based**: Uses .env files for different deployment scenarios
- **Automatic generation**: `start-supervisor.sh` runs `generate_instance_config.py` to create `instance.env`
- **Dynamic loading**: Supervisor loads and exports configuration variables automatically  
- **Instance-aware**: MD5 hash of project path generates unique client IDs (100-999) and ports (8000-9000)
- **Portable**: Works across different machines without hardcoded paths
- **Variable substitution**: `supervisor.conf` uses `%(ENV_VAR)s` for dynamic value injection
- **Collision avoidance**: Allows ~900 concurrent client instances and ~1000 port instances

#### Configuration Flow (Tested & Working)
1. **`make start-supervisor`** calls `start-supervisor.sh`
2. **`start-supervisor.sh`** runs `generate_instance_config.py` 
3. **`generate_instance_config.py`** creates `ib-stream/config/instance.env` with MD5-hashed values
4. **`start-supervisor.sh`** loads `instance.env` and exports variables to environment
5. **`supervisord`** starts with `supervisor.conf` using `%(ENV_VAR)s` substitution
6. **Services start** with correct dynamic ports and client IDs
7. **`supervisor-wrapper.sh`** ensures all subsequent commands use the same environment

### Process Management
- **Supervisor**: Manages services with automatic restart and logging
- **Dynamic startup**: `start-supervisor.sh` generates config and exports environment variables
- **Wrapper scripts**: `supervisor-wrapper.sh` ensures consistent environment for all commands
- **Development mode**: Supports `--reload` for hot code reloading
- **Logging**: Centralized log management with stdout/stderr separation