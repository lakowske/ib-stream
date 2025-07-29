# Project Commands

## ⚠️ CRITICAL WARNING ⚠️

**NEVER stop supervisor services without explicit user permission!**

The production server (`ib-stream-tracked` on port 8001) continuously records live market data to disk. Stopping it unexpectedly will:
- **Lose valuable market data** that cannot be recovered
- **Break historical data continuity** for analysis and backtesting
- **Interrupt critical data collection** during market hours

**Always ask the user before stopping production servers!**

Safe commands to check status:
- `supervisorctl status` - Check which servers are running
- `curl -s http://localhost:8001/health | jq .` - Check production server health
- `find storage -name "*.pb" -newermt "5 minutes ago" | wc -l` - Verify data is being recorded

## Quick Start - Start Both Servers

```bash
# Start supervisor daemon if not running:
supervisord -c supervisor.conf

# Start both servers:
supervisorctl start ib-stream
supervisorctl start ib-contracts

# Check both are running:
curl -s http://localhost:8001/health | jq .status
curl -s http://localhost:8000/health | jq .status
```

## Server Management with Supervisor

This project uses supervisor for managing server processes in the background with automatic logging and process monitoring.

### Start the Servers

```bash
# Start supervisor daemon (if not already running)
supervisord -c supervisor.conf

# Start individual services
supervisorctl start ib-stream      # Streaming API server (port 8001)
supervisorctl start ib-contracts   # Contract lookup server (port 8000)

# Start development servers with hot reload
supervisorctl start ib-stream-dev      # Development streaming server with --reload
supervisorctl start ib-contracts-dev   # Development contracts server with --reload

# Start all services at once
supervisorctl start all
```

**Important Notes:**
- Supervisor configuration is defined in `supervisor.conf`
- The ib-stream server module is `ib_stream.api_server` (with underscore)
- The ib-contract server module is just `api_server` (in the root of ib-contract directory)
- Services are configured to auto-restart on failure

### Server Management

```bash
# Check status of all services
supervisorctl status

# Check status of specific service
supervisorctl status ib-stream

# Stop specific services
supervisorctl stop ib-stream
supervisorctl stop ib-contracts

# Restart services
supervisorctl restart ib-stream
supervisorctl restart ib-contracts

# Stop all running services
supervisorctl stop all

# Reload supervisor configuration
supervisorctl reread
supervisorctl update
```

### Log Management

```bash
# View real-time logs for services
tail -f /var/log/supervisor/ib-stream-stdout.log
tail -f /var/log/supervisor/ib-stream-stderr.log
tail -f /var/log/supervisor/ib-contracts-stdout.log
tail -f /var/log/supervisor/ib-contracts-stderr.log

# View static logs
supervisorctl tail ib-stream
supervisorctl tail ib-stream stderr
supervisorctl tail ib-contracts
supervisorctl tail ib-contracts stderr

# Follow logs in real-time
supervisorctl tail -f ib-stream
supervisorctl tail -f ib-stream stderr
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
- `/var/log/supervisor/ib-stream-stdout.log` - streaming server stdout logs
- `/var/log/supervisor/ib-stream-stderr.log` - streaming server stderr logs  
- `/var/log/supervisor/ib-contracts-stdout.log` - contract server stdout logs
- `/var/log/supervisor/ib-contracts-stderr.log` - contract server stderr logs
- `/var/log/supervisor/ib-stream-dev-stdout.log` - development streaming server logs
- `/var/log/supervisor/ib-contracts-dev-stdout.log` - development contracts server logs

## Configuration Files

- `supervisor.conf` - Main supervisor configuration
- `config/query-only.env` - Environment configuration for query-only mode
- `config/remote-gateway.env` - Configuration for connecting to remote IB Gateway
- Process IDs and supervisor state are managed automatically by supervisor daemon

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
- `IB_STREAM_PORTS=4001,4002,7496,7497` - Ports to try (Gateway ports first)
- `IB_STREAM_CLIENT_ID=10` - Client ID for connections

#### Note about Contract Lookup
The `ib-contract` tool still uses hardcoded localhost. To use with remote gateway, manually update the host in `ib-contract/contract_lookup.py` line 426.