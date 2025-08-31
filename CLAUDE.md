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

# Selective Service Management (New)
source .venv/bin/activate && source .venv/bin/activate && python ib.py services restart-service contract      # Restart only ib-contract service
source .venv/bin/activate && source .venv/bin/activate && python ib.py services restart-service ib-stream     # Restart only ib-stream service
source .venv/bin/activate && source .venv/bin/activate && python ib.py services stop-service contract         # Stop only ib-contract service
source .venv/bin/activate && source .venv/bin/activate && python ib.py services start-service ib-contract     # Start only ib-contract service
source .venv/bin/activate && source .venv/bin/activate && python ib.py services test-restart contract --test-contract-id 711280073  # Restart ib-contract with health tests

# Testing & Validation
source .venv/bin/activate && source .venv/bin/activate && python ib.py test connection              # Test IB Gateway connection
source .venv/bin/activate && source .venv/bin/activate && python ib.py test contract AAPL           # Test contract lookup

# Background Stream Health Monitoring (New)
curl -s http://localhost:8851/background/health/summary | jq .                    # Overall background stream health summary
curl -s http://localhost:8851/background/health/711280073 | jq .                 # Health for specific contract (MNQ)  
curl -s http://localhost:8851/background/health/detailed | jq .                  # Detailed health for all tracked contracts

# ib-contract Advanced Endpoints (New)
curl -s http://localhost:8861/contracts/711280073 | jq .                         # Direct contract ID lookup (fast)
curl -s http://localhost:8861/market-status/711280073 | jq .                     # Check if market is open for contract
curl -s http://localhost:8861/trading-hours/711280073 | jq .                     # Get detailed trading hours
curl -s http://localhost:8861/cache/status | jq .                                # Cache performance and statistics

# Development Tools
source .venv/bin/activate && source .venv/bin/activate && python ib.py dev setup                    # Setup development environment
source .venv/bin/activate && source .venv/bin/activate && python ib.py dev tools                    # Install development tools
source .venv/bin/activate && source .venv/bin/activate && python ib.py dev clean                    # Clean build artifacts
```

## Configuration System v3 🆕

The project uses Configuration System v3 - a complete rewrite with Category Theory foundations:

### Key Features
- **YAML-based hierarchical configuration** (base → environment → service → env vars)
- **Category Theory structures** (Monads, Functors, Monoids) for mathematical guarantees
- **Type-safe validation** with Pydantic schemas + categorical constraints  
- **Monadic error handling** (no exceptions in configuration pipeline)
- **Standalone debugging** (no supervisor dependency required)
- **Hot-reload capabilities** for development
- **2 environment variables** (vs 20+ in legacy system)
- **Full backward compatibility** with existing services

### Quick Start - Configuration v3

```bash
# Standalone debugging (your new best friend!)
python ib-stream/debug.py --validate-only    # Just validate config
python ib-stream/debug.py --show-config      # Show loaded config
python ib-stream/debug.py --run              # Run service standalone

# Configuration validation
python -c "from ib_util.config_v3 import validate_config; print('✅ Valid' if validate_config('ib-stream') else '❌ Invalid')"

# Load typed configuration in code
python -c "from ib_util.config_v3 import load_config; cfg = load_config('ib-stream'); print(f'Client ID: {cfg.service.client.id}')"

# Categorical features (advanced)  
python -c "from ib_util.config_v3_categorical import validate_port; print('Port 8080:', validate_port(8080).is_success())"
```

### Configuration Files Structure

```
config/
├── base.yaml                 # Shared defaults (all services)
├── development.yaml          # Development environment overrides  
├── production.yaml           # Production environment overrides
└── services/
    ├── ib-stream.yaml        # ib-stream specific configuration
    └── ib-contract.yaml      # ib-contract specific configuration
```

### Environment Variables (Simplified!)

**Required (only 2!):**
- `IB_ENVIRONMENT=development` or `production`
- `IB_CONFIG_ROOT=/path/to/config` (optional, defaults to `./config`)

**Optional overrides (rare use):**
- `IB_GATEWAY_HOST=192.168.0.60` (override gateway host)
- `IB_CLIENT_ID=101` (override client ID)

**Gone are the days of 20+ environment variables!**

### Production Configuration
- **ib-stream**: Client ID 851, Port 8851
- **ib-contract**: Client ID 852, Port 8861
- **Environment**: Production server (192.168.0.60) using localhost connections
- **Storage**: Enabled with background streaming for MNQ contract

### Configuration v3 Documentation

📖 **Complete Documentation Available:**
- [`docs/configuration-v3-architecture.md`](docs/configuration-v3-architecture.md) - Complete architecture and design
- [`docs/configuration-v3-migration-guide.md`](docs/configuration-v3-migration-guide.md) - Migration from legacy system  
- [`docs/configuration-v3-developer-guide.md`](docs/configuration-v3-developer-guide.md) - Developer guide and examples

### Configuration Files (v3 System)
- `config/base.yaml` - Shared defaults for all services
- `config/development.yaml` - Development environment overrides
- `config/production.yaml` - Production environment overrides
- `config/services/ib-stream.yaml` - ib-stream service configuration
- `config/services/ib-contract.yaml` - ib-contract service configuration

### Configuration v3 Features

**Mathematical Foundations:**
- **Result Monads**: Compositional error handling (no exceptions)
- **Configuration Monoids**: Associative merging with identity laws
- **Categorical Constraints**: Type-safe validation (ports: 1024-65535, client IDs: 1-999999)
- **Functorial Transformations**: Structure-preserving config operations

**Developer Experience:**
- **Standalone Debugging**: `python ib-stream/debug.py --run`
- **Hot Reload**: Configuration changes applied immediately (development)
- **Type Safety**: Full IDE support with Pydantic models
- **Clear Validation**: Descriptive error messages with categorical constraints

## Background Stream Health Monitoring

The system now includes comprehensive health monitoring for background streams with trading hours awareness.

### Health Monitoring Features
- **Trading Hours Integration**: Automatically detects market status (OPEN, CLOSED, PRE_MARKET, AFTER_HOURS)
- **Data Staleness Detection**: Configurable threshold (default: 15 minutes) for detecting stale data
- **Contract-Specific Health**: Individual health assessment for each tracked contract
- **Market-Aware Status**: Different health expectations during market hours vs off-hours

### Health Status Classifications
- **HEALTHY**: Stream active and receiving data within expected timeframe during market hours
- **DEGRADED**: Stream active but data is getting stale during market hours  
- **UNHEALTHY**: Stream not receiving expected data during market hours
- **OFF_HOURS**: Market closed, no data expected (normal state)
- **UNKNOWN**: Unable to determine market status or data state

### Health Monitoring Endpoints
- **Summary Health**: `/background/health/summary` - Overall status for all background streams
- **Contract Health**: `/background/health/{contract_id}` - Detailed health for specific contract
- **Detailed Health**: `/background/health/detailed` - Comprehensive health data for all contracts

### Example Usage
```bash
# Check overall background stream health
curl -s http://localhost:8851/background/health/summary | jq .

# Check health for MNQ contract specifically  
curl -s http://localhost:8851/background/health/711280073 | jq .

# Get detailed health information for all tracked contracts
curl -s http://localhost:8851/background/health/detailed | jq .
```

The system tracks contract 711280073 (MNQ) by default and can monitor multiple contracts simultaneously.

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

## Configuration v3 Management 🆕

### Quick Configuration Commands

```bash
# Standalone debugging (fastest way to test config)
python ib-stream/debug.py --validate-only         # Validate configuration only
python ib-stream/debug.py --show-config           # Show loaded configuration
python ib-stream/debug.py --run                   # Run service with config v3

# Configuration validation (new v3 system)
python -c "from ib_util.config_v3 import validate_config; print('✅ Valid' if validate_config('ib-stream') else '❌ Invalid')"
python -c "from ib_util.config_v3 import validate_config; print('✅ Valid' if validate_config('ib-contract') else '❌ Invalid')"

# Load and inspect configuration (type-safe)
python -c "from ib_util.config_v3 import load_config; cfg = load_config('ib-stream'); print(f'Client: {cfg.service.client.id}, Port: {cfg.service.server.port}')"

# Categorical validation (advanced)
python -c "from ib_util.config_v3_categorical import validate_port, validate_client_id; print('Port:', validate_port(8851).is_success()); print('Client:', validate_client_id(101).is_success())"
```

### Legacy Configuration Management (Still Supported)

```bash
# Check entire configuration system health (legacy ib.py)
source .venv/bin/activate && python ib.py config validate

# Show detailed validation results (legacy ib.py)
source .venv/bin/activate && python ib.py config validate --verbose
```

### View Current Configuration (Legacy)

```bash
# Show summary for all services (legacy ib.py)
source .venv/bin/activate && python ib.py config show

# Show detailed configuration for specific service (legacy ib.py)  
source .venv/bin/activate && python ib.py config show --service ib-stream --format detailed

# Show configuration in JSON format (legacy ib.py)
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

## Enhanced Auto-Recovery System

The ib-stream service features a sophisticated auto-recovery system that automatically detects and resolves connection and data flow issues without manual intervention. This system is critical for maintaining continuous market data collection during trading hours.

**📋 For complete documentation, see [AUTO_RECOVERY.md](./AUTO_RECOVERY.md)**

### Key Features
- **Dual-state monitoring**: Socket connection + actual data flow detection
- **Escalating recovery**: Progressive intervention levels (1min → 3min → 5min → 10min)  
- **Zombie connection detection**: Identifies "connected but no data" states
- **Automatic stream restarts**: Self-healing for common issues
- **Production-optimized timing**: Fast detection and recovery for active markets

### Quick Health Check
```bash
# Check overall system health
curl -s http://localhost:8851/health | jq '{status, tws_connected, background_streaming}'

# Check specific contract health  
curl -s http://localhost:8851/background/health/711280073 | jq '{status, data_freshness}'

# Monitor auto-recovery logs
source .venv/bin/activate && python ib.py services logs | grep -E "Monitor cycle|STALE DATA|restart"
```

### Common Auto-Recovery Scenarios
1. **TWS Session Conflicts** - Automatically resolves when competing sessions close
2. **IB Gateway Restarts** - Reconnects and restarts streams within 1-2 minutes  
3. **Network Interruptions** - Continuous retry until connection restored
4. **Data Subscription Issues** - Escalating recovery actions

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

### New CLI Commands (Latest)

| Command | Purpose |
|---------|---------|
| `python ib.py services restart-service [contract\|ib-stream]` | Restart specific service only |
| `python ib.py services stop-service [contract\|ib-stream]` | Stop specific service only |
| `python ib.py services start-service [contract\|ib-stream]` | Start specific service only |
| `python ib.py services test-restart contract --test-contract-id ID` | Restart ib-contract with health tests |

The CLI provides better error handling, help systems, and extensibility compared to the legacy Makefile approach.

## Recent Critical Fixes and New Features (v3.0)

### 🆕 Configuration System v3 ✅ NEW FEATURE
- **Complete configuration system rewrite**: Category Theory foundations with mathematical guarantees
  - **YAML-based hierarchy**: base → environment → service → env vars (2 vars total vs 20+)
  - **Standalone debugging**: `python ib-stream/debug.py --run` (no supervisor dependency)
  - **Category Theory**: Monads, Functors, Monoids for compositional configuration operations
  - **Type Safety**: Full Pydantic validation with categorical constraints
  - **Documentation**: Complete architecture, migration guide, and developer documentation
  - **Result**: Dramatically simplified configuration with mathematical guarantees about composition

### 🏥 Background Stream Health Monitoring ✅ ESTABLISHED FEATURE
- **Comprehensive health monitoring**: Trading hours awareness with market status detection
  - **Endpoints**: `/background/health/summary`, `/background/health/{contract_id}`, `/background/health/detailed`
  - **Classifications**: HEALTHY, DEGRADED, UNHEALTHY, OFF_HOURS, UNKNOWN
  - **Features**: 15-minute data staleness detection, contract-specific health assessment
  - **Result**: Full visibility into background stream health with market-aware expectations

### 🔄 Dual Storage Pattern for Contract Caching ✅ ESTABLISHED FEATURE  
- **Dual storage architecture**: Support both symbol-based and contract ID lookups
  - **Symbol Cache**: `YYYYMMDD-contracts_SYMBOL_TYPE.json` for traditional lookups
  - **Contract ID Cache**: `YYYYMMDD-contract_{ID}.json` for direct ID-based access  
  - **Performance**: Sub-20ms response times for cached contract ID lookups
  - **Result**: Fast contract resolution without requiring prior symbol knowledge

### 🛠️ Selective Service Management ✅ ESTABLISHED FEATURE
- **Granular service control**: Restart individual services without affecting others
  - **Commands**: `restart-service`, `stop-service`, `start-service`, `test-restart`
  - **Service Isolation**: ib-contract can be restarted independently of ib-stream
  - **Health Testing**: Integrated health validation after service operations
  - **Result**: Safe production service management with zero downtime for unaffected services

### Production Verification ✅ CONFIRMED
```bash
# Verify all systems working:
source .venv/bin/activate && python ib.py services status                    # ✅ Services running
curl -s http://localhost:8851/health | jq .     # ✅ Accurate health status
find ./ib-stream/storage -type f | wc -l        # ✅ 8+ data files active
python ib-stream/debug.py --validate-only       # ✅ Config v3 validation
```

These features ensure the system is production-ready with Configuration v3 providing a robust foundation.