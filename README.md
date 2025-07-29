# ib-stream
A market data streaming server for Interactive Brokers with shared connection utilities and remote gateway support.

## Features

- **Real-time market data streaming** via REST API and WebSocket
- **Contract lookup service** for Interactive Brokers securities
- **Remote gateway support** for connecting to IB Gateway on different machines
- **Smart instance allocation** using MD5 path hashing for unique client IDs (100-999) and ports (8000-9000)
- **Shared connection utilities** via ib-util module for reliable TWS/Gateway connections
- **Supervisor process management** with automatic restart and logging
- **Development workflow** with hot reload support

## Quick Start

### Prerequisites

1. Interactive Brokers Gateway or TWS running and configured for API access
2. Python 3.8+ installed
3. Make utility installed

### Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd ib-stream-1

# Build TWS API and setup environment
make setup

# Test connection to remote gateway (optional)
make test-connection

# Note: Instance-specific configuration is generated automatically when starting services
```

### Starting Services

```bash
# Start supervisor with dynamic configuration
make start-supervisor

# Or manually with the startup script
./start-supervisor.sh

# Check service status (shows your generated ports)
make supervisor-status

# Start/stop individual services
make supervisor-start  # Start ib-stream-remote
make supervisor-stop   # Stop all services

# View real-time logs
make supervisor-logs   # Follow ib-stream-remote logs
```

### Development Mode

```bash
# Start development servers with hot reload
./supervisor-wrapper.sh start ib-stream-dev
./supervisor-wrapper.sh start ib-contracts-dev

# Services will auto-reload on code changes using your generated ports
```

## Architecture

### Core Components

- **ib-stream/**: Market data streaming service (port determined by project path hash)
- **ib-contract/**: Contract lookup service (port determined by project path hash)  
- **ib-util/**: Shared connection utilities and IB API abstractions
- **generate_instance_config.py**: Smart configuration generator using MD5 path hashing

### Configuration

The project uses environment-based configuration with automatic instance-specific value generation:

#### Configuration Files
- **Remote Gateway**: `ib-stream/config/remote-gateway.env`
- **SSH Tunnel**: `ib-stream/config/ssh-tunnel.env` 
- **Query Only**: `ib-stream/config/query-only.env`
- **Instance Config**: `ib-stream/config/instance.env` (auto-generated)

#### Dynamic Value Generation
Instance-specific values are generated automatically using MD5 hash of the project path:
- **Client IDs**: Range 100-999 (stream_id, stream_id + 1 for contracts)
- **HTTP Ports**: Range 8000-9000 (base_port, base_port + 10 for contracts)
- **Configuration Flow**:
  1. `make start-supervisor` runs `generate_instance_config.py`
  2. Creates `ib-stream/config/instance.env` with hashed values
  3. `start-supervisor.sh` loads and exports these as environment variables
  4. `supervisor.conf` uses `%(ENV_VAR)s` substitution for dynamic values

### Services

#### ib-stream (Market Data)
- **Endpoint**: `http://localhost:{STREAM_PORT}/` (determined by path hash)
- **Health**: `http://localhost:{STREAM_PORT}/health`
- **WebSocket**: `ws://localhost:{STREAM_PORT}/ws/control`
- **Streaming**: Real-time market data for subscribed contracts

#### ib-contracts (Contract Lookup)
- **Endpoint**: `http://localhost:{CONTRACTS_PORT}/` (determined by path hash)
- **Health**: `http://localhost:{CONTRACTS_PORT}/health`
- **Lookup**: `http://localhost:{CONTRACTS_PORT}/lookup/{symbol}/{type}`
- **Contract Details**: Full IB contract specifications

## API Usage

### REST Endpoints

```bash
# Check your generated ports first
python generate_instance_config.py

# Use the displayed ports for API calls, or use dynamic discovery:
# Check service health
curl http://localhost:$(python -c "from generate_instance_config import generate_instance_config; print(generate_instance_config()['stream_port'])")/health
curl http://localhost:$(python -c "from generate_instance_config import generate_instance_config; print(generate_instance_config()['contracts_port'])")/health

# Look up contract details  
curl http://localhost:$(python -c "from generate_instance_config import generate_instance_config; print(generate_instance_config()['contracts_port'])")/lookup/AAPL/STK

# Stream market data (CLI)
cd ib-stream && python -m ib_stream.stream AAPL --number 10
```

### WebSocket API

```python
import asyncio
import websockets
import json

async def stream_data():
    # Get your instance's port from configuration
    from generate_instance_config import generate_instance_config
    config = generate_instance_config()
    port = config['stream_port']
    
    async with websockets.connect(f'ws://localhost:{port}/ws/control') as ws:
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
ib-stream-1/
├── ib-stream/           # Market data streaming service
├── ib-contract/         # Contract lookup service  
├── ib-util/             # Shared connection utilities
├── Makefile             # Build and setup automation
├── supervisor.conf      # Process management configuration
├── generate_instance_config.py  # Instance configuration generator
└── logs/                # Service logs
```

### Makefile Targets

```bash
make setup            # Full environment setup
make build-api        # Build TWS API only
make venv            # Create virtual environment
make install         # Install packages
make test-connection # Test remote gateway connection
make dev-server      # Start development server
make clean           # Clean build artifacts

# Supervisor management
make start-supervisor # Start supervisor with dynamic config
make supervisor-status # Check status and show generated ports
make supervisor-start # Start ib-stream-remote service
make supervisor-stop  # Stop all services
make supervisor-logs  # Follow service logs
```

### Remote Gateway Setup

To connect to IB Gateway running on a remote machine:

1. **Configure remote gateway** in `ib-stream/config/remote-gateway.env`:
   ```bash
   IB_STREAM_HOST=192.168.0.60
   IB_STREAM_PORTS=4002
   IB_STREAM_CLIENT_ID=${IB_STREAM_CLIENT_ID:-374}
   ```

2. **Update Gateway settings** on remote machine:
   - Set `TrustedIPs=0.0.0.0` in Gateway configuration
   - Ensure API connections are enabled
   - Use appropriate ports (4002 for Paper Gateway, 4001 for Live)

3. **Test connection**:
   ```bash
   make test-connection
   ```

### Logging

All services use structured logging with timestamps and context:

```bash
# View supervisor logs directly
tail -f /var/log/supervisor/ib-stream-remote-stdout.log
tail -f /var/log/supervisor/ib-contracts-stdout.log

# View via supervisor (with dynamic config loading)
make supervisor-logs                # Follow ib-stream-remote logs
./supervisor-wrapper.sh tail -f ib-contracts
./supervisor-wrapper.sh tail -f ib-stream-remote stderr
```

### Development Workflow

1. **Start services**: `make start-supervisor`
2. **Check status**: `make supervisor-status` (shows your generated ports)
3. **Make code changes** in your editor
4. **Services auto-reload** if running in development mode (`--reload` flag)
5. **Check logs**: `make supervisor-logs` or `./supervisor-wrapper.sh tail -f <service-name>`
6. **Test endpoints** using curl or WebSocket clients with your generated ports
7. **Stop services**: `make supervisor-stop` when done

## Troubleshooting

### Common Issues

**Connection Failed**
- Verify IB Gateway/TWS is running
- Check API settings are enabled  
- Confirm correct host and port configuration
- Verify client ID is not in use by another application

**Port Conflicts**
- Ports are generated per-instance using path hash
- Check `make supervisor-status` for actual port assignments
- Different project locations will get different ports automatically

**Service Won't Start**
- Check supervisor logs: `./supervisor-wrapper.sh tail <service> stderr`
- Verify virtual environment: `which python` should show `.venv/bin/python`
- Ensure TWS API is built: `make build-api`
- Regenerate config: `python generate_instance_config.py`

### Debug Mode

Run services directly for detailed debugging:

```bash
# Debug ib-stream
cd ib-stream && python -m ib_stream.api_server

# Debug ib-contracts  
cd ib-contract && python -m api_server

# Test connection manually
python test_real_ib_connection.py
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes following the existing code style
4. Add tests for new functionality
5. Update documentation as needed
6. Submit a pull request

## License

[Add license information]
