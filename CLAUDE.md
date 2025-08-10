# Project Commands

## ⚠️ Code Review Protocol ⚠️

**IMPORTANT**: Before making any significant commits, ask if the user wants a code review.

**When to request code review:**
- New feature implementations (>50 lines of new code)
- API changes or new endpoints  
- Database/cache modifications
- Security-related changes
- Performance-critical code
- Complex algorithms or business logic

**Template question to ask:**
> "I've completed implementing [feature/change]. Would you like me to conduct a code review before committing to identify any issues with code quality, security, performance, or maintainability?"

**Code review command:**
```bash
# Use the Task tool with code-quality-auditor agent
# Focus on: SOLID principles, security, performance, maintainability, production readiness
```

This helps catch critical issues before they reach production in this trading system where reliability is paramount.

## ⚠️ CRITICAL WARNING ⚠️

**NEVER stop supervisor services without explicit user permission!**

The production server continuously records live market data to disk. Stopping it unexpectedly will:
- **Lose valuable market data** that cannot be recovered
- **Break historical data continuity** for analysis and backtesting
- **Interrupt critical data collection** during market hours

**Always ask the user before stopping production servers!**

Safe commands to check status:
- `source .venv/bin/activate && source .venv/bin/activate && python ib.py services status` - Check which services are running
- `source .venv/bin/activate && source .venv/bin/activate && python ib.py test connection` - Test IB Gateway connection health
- `curl -s http://localhost:8851/health | jq .` - Check ib-stream health (production port)
- `curl -s http://localhost:8861/health | jq .` - Check ib-contracts health (production port)
- `find storage -name "*.pb" -newermt "5 minutes ago" | wc -l` - Verify data is being recorded

## 🚀 Modern CLI Tool - ib.py

The project now uses a modern CLI tool (`ib.py`) for all configuration, service management, and development workflows. This replaces most Makefile targets with a cleaner, more maintainable approach.

### Quick Start - CLI Usage

```bash
# Configuration Management
source .venv/bin/activate && source .venv/bin/activate && python ib.py config validate              # Validate configuration system
source .venv/bin/activate && source .venv/bin/activate && python ib.py config show                  # Show current configuration
source .venv/bin/activate && source .venv/bin/activate && python ib.py config watch                 # Watch for configuration changes (hot-reload)
source .venv/bin/activate && source .venv/bin/activate && python ib.py config compare ib-stream ib-contract  # Compare service configurations

# Service Management
source .venv/bin/activate && source .venv/bin/activate && python ib.py services start               # Start all services
source .venv/bin/activate && source .venv/bin/activate && python ib.py services status              # Check service status
source .venv/bin/activate && source .venv/bin/activate && python ib.py services logs                # View service logs
source .venv/bin/activate && source .venv/bin/activate && python ib.py services stop                # Stop all services

# Testing & Validation
source .venv/bin/activate && source .venv/bin/activate && python ib.py test connection              # Test IB Gateway connection
source .venv/bin/activate && source .venv/bin/activate && python ib.py test contract AAPL           # Test contract lookup

# Development Tools
source .venv/bin/activate && source .venv/bin/activate && python ib.py dev setup                    # Setup development environment
source .venv/bin/activate && source .venv/bin/activate && python ib.py dev tools                    # Install development tools
source .venv/bin/activate && source .venv/bin/activate && python ib.py dev clean                    # Clean build artifacts
```

## Configuration System v2

The project uses a modern type-safe configuration system with automatic fallback:

### Key Features
- **Type-safe validation** with Pydantic schemas
- **Environment-specific configurations** (development, production, staging)
- **Hot-reload capabilities** for development
- **Automatic instance isolation** with unique client IDs and ports
- **Backward compatibility** with legacy configuration

### Production Configuration
- **ib-stream**: Client ID 851, Port 8851
- **ib-contract**: Client ID 852, Port 8861
- **Environment**: Production server (192.168.0.60) using localhost connections
- **Storage**: Enabled with background streaming for MNQ contract

### Configuration Files
- `ib-stream/config/production.env` - Production environment settings
- `ib-stream/config/development.env` - Development environment settings  
- `ib-stream/config/instance.env` - Auto-generated instance-specific values
- `ib-stream/config/production-server.env` - Production server specific settings

## Service Management

### Start Services (Recommended CLI Approach)

```bash
# Start services with the modern CLI
source .venv/bin/activate && source .venv/bin/activate && python ib.py services start

# Check status (shows actual ports and client IDs)
source .venv/bin/activate && source .venv/bin/activate && python ib.py services status

# View real-time logs
source .venv/bin/activate && source .venv/bin/activate && python ib.py services logs
```

### Legacy Makefile Approach (Still Supported)

```bash
# Start supervisor with dynamic configuration
make start-supervisor

# Check status (shows generated ports)
make supervisor-status

# View logs
make supervisor-logs
```

### Individual Service Management

```bash
# Using CLI (recommended)
source .venv/bin/activate && source .venv/bin/activate && python ib.py services logs --service ib-stream-remote

# Using traditional supervisor wrapper
./supervisor-wrapper.sh start ib-stream-remote
./supervisor-wrapper.sh start ib-contracts-production
./supervisor-wrapper.sh stop all
```

## Configuration Management

### Validate Configuration System

```bash
# Check entire configuration system health
source .venv/bin/activate && python ib.py config validate

# Show detailed validation results
source .venv/bin/activate && python ib.py config validate --verbose
```

### View Current Configuration

```bash
# Show summary for all services
source .venv/bin/activate && python ib.py config show

# Show detailed configuration for specific service
source .venv/bin/activate && python ib.py config show --service ib-stream --format detailed

# Show configuration in JSON format
source .venv/bin/activate && python ib.py config show --service ib-stream --format json
```

### Compare Service Configurations

```bash
# Compare ib-stream vs ib-contract configurations
source .venv/bin/activate && python ib.py config compare ib-stream ib-contract

# Show configuration summary for all services
python ib.py config summary
```

### Configuration Hot-Reload (Development)

```bash
# Start configuration watcher
source .venv/bin/activate && python ib.py config watch

# Watch specific service only
source .venv/bin/activate && python ib.py config watch --service ib-stream

# In another terminal, edit configuration files
# Changes are detected and applied automatically
vim ib-stream/config/development.env
```

## Testing & Validation

### Connection Testing

```bash
# Test connection to IB Gateway with new configuration
source .venv/bin/activate && python ib.py test connection

# Test contract lookup
source .venv/bin/activate && python ib.py test contract AAPL
source .venv/bin/activate && python ib.py test contract MNQ
```

### Service Health Checks

```bash
# Check if services are running and healthy
source .venv/bin/activate && python ib.py services status

# Test specific endpoints (production ports)
curl -s http://localhost:8851/health | jq .    # ib-stream
curl -s http://localhost:8861/health | jq .    # ib-contracts
```

## Development Workflow

### Setup Development Environment

```bash
# Complete development setup
source .venv/bin/activate && python ib.py dev setup

# Install development tools (linting, testing, hot-reload)
source .venv/bin/activate && python ib.py dev tools

# Clean build artifacts
source .venv/bin/activate && python ib.py dev clean
```

### Hot-Reload Development

```bash
# Start configuration watcher in one terminal
source .venv/bin/activate && python ib.py config watch

# Start services in another terminal
source .venv/bin/activate && python ib.py services start

# Make configuration changes and see live updates
# Edit files in ib-stream/config/ directory
```

### Development Testing

```bash
# Validate configuration changes
source .venv/bin/activate && python ib.py config validate

# Test connections with new configuration
source .venv/bin/activate && python ib.py test connection

# Compare configurations for debugging
source .venv/bin/activate && python ib.py config compare ib-stream ib-contract
```

## Makefile (Build Automation Only)

The Makefile now focuses solely on build automation. For service management, configuration, and development workflows, use the `ib.py` CLI tool.

### Build Automation Commands

```bash
make setup            # Full development environment setup
make build-api        # Build TWS API from contrib/
make install-packages # Install ib-util, ib-stream, ib-contract packages
make dev-tools        # Install development tools (ruff, pytest, click, watchdog)
make clean            # Clean build artifacts and temporary files
```

### Legacy Service Commands (Deprecated)

These Makefile targets still work but are deprecated in favor of the CLI:

```bash
# Deprecated - Use source .venv/bin/activate && python ib.py services start instead
make start-supervisor

# Deprecated - Use source .venv/bin/activate && python ib.py services status instead  
make supervisor-status

# Deprecated - Use source .venv/bin/activate && python ib.py services logs instead
make supervisor-logs

# Deprecated - Use source .venv/bin/activate && python ib.py config validate instead
make config-validate
```

## Log Management

### View Logs with CLI (Recommended)

```bash
# View logs for all services
source .venv/bin/activate && python ib.py services logs

# View logs for specific service
source .venv/bin/activate && python ib.py services logs --service ib-stream-remote
```

### Traditional Log Viewing (Still Supported)

```bash
# View real-time logs directly
tail -f /var/log/supervisor/ib-stream-production-stdout.log
tail -f /var/log/supervisor/ib-contracts-production-stdout.log

# View logs via supervisor wrapper
./supervisor-wrapper.sh tail -f ib-stream-production
./supervisor-wrapper.sh tail -f ib-contracts-production stderr
```

## Production Server Configuration

### Current Production Settings
- **Server**: 192.168.0.60 (localhost connections for security)
- **ib-stream**: Port 8851, Client ID 851
- **ib-contracts**: Port 8861, Client ID 852  
- **Storage**: Enabled with background streaming
- **Tracked Contract**: MNQ (contract ID 711280073)

### Health Monitoring

```bash
# Check service health
source .venv/bin/activate && python ib.py services status

# Test connections
source .venv/bin/activate && python ib.py test connection

# Verify data recording
find storage -name "*.pb" -newermt "5 minutes ago" | wc -l
```

## Troubleshooting

### Configuration Issues

```bash
# Validate entire configuration system
source .venv/bin/activate && python ib.py config validate --verbose

# Show detailed configuration for debugging
source .venv/bin/activate && python ib.py config show --format detailed

# Compare configurations to find differences
source .venv/bin/activate && python ib.py config compare ib-stream ib-contract
```

### Connection Problems

```bash
# Test IB Gateway connection
source .venv/bin/activate && python ib.py test connection

# Check service status
source .venv/bin/activate && python ib.py services status

# View error logs
source .venv/bin/activate && python ib.py services logs
```

### Service Problems

```bash
# Restart services
source .venv/bin/activate && python ib.py services stop
source .venv/bin/activate && python ib.py services start

# Check supervisor status
./supervisor-wrapper.sh status

# View detailed error logs
source .venv/bin/activate && python ib.py services logs --service ib-stream-remote
```

## Migration from Legacy Commands

| Legacy Makefile Command | New CLI Command | Purpose |
|-------------------------|-----------------|---------|
| `make config-validate` | `source .venv/bin/activate && python ib.py config validate` | Validate configuration |
| `make config-show` | `source .venv/bin/activate && python ib.py config show` | Show configuration |
| `make supervisor-status` | `source .venv/bin/activate && python ib.py services status` | Check service status |
| `make supervisor-logs` | `source .venv/bin/activate && python ib.py services logs` | View service logs |
| `make test-connection-v2` | `source .venv/bin/activate && python ib.py test connection` | Test IB connection |
| `make contract-lookup-v2` | `source .venv/bin/activate && python ib.py test contract SYMBOL` | Test contract lookup |
| `make config-watch` | `source .venv/bin/activate && python ib.py config watch` | Configuration hot-reload |

The CLI provides better error handling, help systems, and extensibility compared to the legacy Makefile approach.

## Recent Critical Fixes (v2.0)

### Storage System Issues ✅ RESOLVED
- **Fixed MultiStorageV3 initialization error**: `unsupported operand type(s) for /: 'str' and 'str'`
  - **Solution**: Convert storage_path string to Path object in api_server.py
  - **Result**: All 4 storage formats now working (v2/v3 JSON + Protobuf)

### Health Endpoint Synchronization ✅ RESOLVED  
- **Fixed health endpoints showing incorrect status**: Storage and background streaming showed as disabled despite being active
  - **Root Cause**: Health endpoints used outdated global variables instead of startup-created objects
  - **Solution**: Added update_global_state() function to sync global variables
  - **Result**: Health endpoints now reflect actual running state accurately

### Production Verification ✅ CONFIRMED
```bash
# Verify all systems working:
source .venv/bin/activate && python ib.py services status                    # ✅ Services running
curl -s http://localhost:8851/health | jq .     # ✅ Accurate health status
find ./ib-stream/storage -type f | wc -l        # ✅ 8+ data files active
ls -lh ./ib-stream/storage/v*/protobuf/2025/*/*/ # ✅ V3 59% space reduction
```

These fixes ensure the configuration system v2 is fully functional and production-ready.