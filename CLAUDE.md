# Project Commands

## Server Management with Backdrop

This project uses backdrop (`bd`) for managing server processes in the background with automatic logging.

### Start the Servers

```bash
# Start the streaming API server (port 8001)
bd start --name ib-stream -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001

# Start the contract lookup server (port 8000)
bd start --name ib-contracts -- uvicorn ib_stream.contract_server:app --host 0.0.0.0 --port 8000

# Start streaming server with hot reload for development
bd start --name ib-stream-dev -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001 --reload

# Start with custom log level
bd start --name ib-stream -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001 --log-level debug
```

### Server Management

```bash
# Check status of all servers
bd status

# Check detailed status with resource usage
bd status --verbose

# Stop the streaming server
bd stop ib-stream

# Stop the contract lookup server
bd stop ib-contracts

# Restart servers
bd restart ib-stream
bd restart ib-contracts

# Stop all running servers
bd stop-all
```

### Log Management

```bash
# View real-time logs for streaming server
bd logs ib-stream --follow

# View real-time logs for contract server
bd logs ib-contracts --follow

# View error logs only
bd logs ib-stream --error
bd logs ib-contracts --error

# View static logs
bd logs ib-stream
bd logs ib-contracts
```

### Development Workflow

```bash
# Start development servers with hot reload
bd start --name ib-stream-dev -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001 --reload
bd start --name ib-contracts-dev -- uvicorn ib_stream.contract_server:app --host 0.0.0.0 --port 8000 --reload

# Watch logs in another terminal
bd logs ib-stream-dev --follow
bd logs ib-contracts-dev --follow

# Stop development servers when done
bd stop ib-stream-dev
bd stop ib-contracts-dev
```

## Log Files

Backdrop automatically saves logs to:
- `./logs/ib-stream.log` - streaming server stdout logs
- `./logs/ib-stream_error.log` - streaming server stderr logs  
- `./logs/ib-contracts.log` - contract server stdout logs
- `./logs/ib-contracts_error.log` - contract server stderr logs

## PID Files

Process IDs are tracked in:
- `./pids/ib-stream.pid` - streaming server (port 8001)
- `./pids/ib-contracts.pid` - contract lookup server (port 8000)