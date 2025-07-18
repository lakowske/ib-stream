# Project Commands

## ⚠️ CRITICAL WARNING ⚠️

**NEVER use `bd stop-all` without explicit user permission!**

The production server (`ib-stream-tracked` on port 8001) continuously records live market data to disk. Stopping it unexpectedly will:
- **Lose valuable market data** that cannot be recovered
- **Break historical data continuity** for analysis and backtesting
- **Interrupt critical data collection** during market hours

**Always ask the user before stopping production servers!**

Safe commands to check status:
- `bd status` - Check which servers are running
- `curl -s http://localhost:8001/health | jq .` - Check production server health
- `find storage -name "*.pb" -newermt "5 minutes ago" | wc -l` - Verify data is being recorded

## Quick Start - Start Both Servers

```bash
# From the ib-stream directory, start both servers:
bd start --name ib-stream -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001
cd ib-contract && bd start --name ib-contracts -- uvicorn api_server:app --host 0.0.0.0 --port 8000 && cd ..

# Check both are running:
curl -s http://localhost:8001/health | jq .status
curl -s http://localhost:8000/health | jq .status
```

## Server Management with Backdrop

This project uses backdrop (`bd`) for managing server processes in the background with automatic logging.

### Start the Servers

```bash
# Start the streaming API server (port 8001) - from ib-stream directory
bd start --name ib-stream -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001

# Start the contract lookup server (port 8000) - from ib-contract directory
cd ib-contract && bd start --name ib-contracts -- uvicorn api_server:app --host 0.0.0.0 --port 8000

# Start streaming server with hot reload for development
bd start --name ib-stream-dev -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001 --reload

# Start contract server with hot reload for development
cd ib-contract && bd start --name ib-contracts-dev -- uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload

# Start with custom log level
bd start --name ib-stream -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001 --log-level debug
```

**Important Notes:**
- The ib-stream server module is `ib_stream.api_server` (with underscore)
- The ib-contract server module is just `api_server` (in the root of ib-contract directory)
- You must be in the `ib-contract` directory to start the contract server

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
cd ib-contract && bd start --name ib-contracts-dev -- uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload

# Watch logs in another terminal
bd logs ib-stream-dev --follow
cd ib-contract && bd logs ib-contracts-dev --follow

# Stop development servers when done
bd stop ib-stream-dev
cd ib-contract && bd stop ib-contracts-dev
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