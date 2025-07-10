# IB-Stream Management Scripts

This directory contains scripts for managing different environments of the IB-Stream system.

## Environment Management Scripts

### Start Scripts

**Production Environment:**
```bash
./scripts/start-production.sh
```
- Starts contract server on port 8000
- Starts stream server on port 8001  
- Uses production configuration

**Development Environment:**
```bash
./scripts/start-development.sh [template]
```
- Starts contract server on port 8100
- Starts stream server on port 8101
- Uses development configuration
- Optional template parameter for specific configs

Examples:
```bash
./scripts/start-development.sh                    # Default development config
./scripts/start-development.sh development-recording  # With background streaming
./scripts/start-development.sh development-api-only   # API-only mode
./scripts/start-development.sh migration-test         # Migration testing
```

**Staging Environment:**
```bash
./scripts/start-staging.sh
```
- Starts contract server on port 8200
- Starts stream server on port 8201
- Uses staging configuration

### Stop Scripts

**Stop Any Environment:**
```bash
./scripts/stop-environment.sh [environment]
```

Examples:
```bash
./scripts/stop-environment.sh production
./scripts/stop-environment.sh development  
./scripts/stop-environment.sh staging
```

### Migration Script

**Migrate Between Environments:**
```bash
./scripts/migrate-environment.sh [from_env] [to_env] [backup]
```

Examples:
```bash
# Migrate from staging to production with backup
./scripts/migrate-environment.sh staging production true

# Switch to development environment without backup
./scripts/migrate-environment.sh production development false
```

The migration script:
- Stops the source environment safely
- Creates backup of storage data (optional)
- Copies data between storage locations if needed
- Starts the target environment
- Provides verification commands

## Configuration Templates

Located in `config/templates/`:

- `development-recording.env` - Full development with background streaming
- `development-api-only.env` - API development without storage
- `migration-test.env` - Testing migrations with production data (read-only)

## Usage Examples

### Feature Development Workflow

```bash
# Start development environment for API changes
./scripts/start-development.sh development-api-only

# Develop and test...

# Switch to recording mode for integration testing
./scripts/stop-environment.sh development
./scripts/start-development.sh development-recording

# Test complete functionality...

# Deploy to staging for final validation
./scripts/migrate-environment.sh development staging true

# Deploy to production
./scripts/migrate-environment.sh staging production true
```

### Quick Environment Switching

```bash
# Switch from production to development
./scripts/stop-environment.sh production
./scripts/start-development.sh

# Switch back to production
./scripts/stop-environment.sh development  
./scripts/start-production.sh
```

### Safe Production Deployment

```bash
# Test new version in staging
./scripts/start-staging.sh

# Validate staging environment
curl -s http://localhost:8201/health | jq .

# Migrate to production with backup
./scripts/migrate-environment.sh production staging false  # Don't backup to staging
./scripts/migrate-environment.sh staging production true   # Backup production

# Verify production
curl -s http://localhost:8001/health | jq .
```

## Environment Variables

The scripts respect the following environment variables:

- `IB_STREAM_ENV` - Override environment detection
- Configuration from environment files takes precedence
- Command-line environment variables take highest precedence

## Log Monitoring

Monitor logs for each environment:

```bash
# Production
bd logs ib-stream --follow
bd logs ib-contracts --follow

# Development  
bd logs ib-stream-dev --follow
bd logs ib-contracts-dev --follow

# Staging
bd logs ib-stream-staging --follow
bd logs ib-contracts-staging --follow
```

## Troubleshooting

**Port conflicts:**
```bash
netstat -tlnp | grep :8100  # Check if dev ports are in use
./scripts/stop-environment.sh development  # Stop if needed
```

**Storage permission issues:**
```bash
ls -la storage*  # Check permissions
chmod 755 storage-dev  # Fix if needed
```

**Configuration issues:**
```bash
# Validate environment files
grep -v '^#' config/production.env | grep '='  # Check syntax
```