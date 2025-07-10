# Migration and Development Strategy for IB-Stream

## Overview

This document outlines the strategy for running multiple versions of the IB-Stream server simultaneously, enabling safe development while maintaining production data continuity. The approach uses port-based isolation, environment-specific configuration, and careful resource management.

## Architecture Overview

### Port Allocation Strategy

The system uses a consistent port numbering pattern:

- **Production Environment**: 8000-8099
  - Contract Server: Port 8000 (ib-contract)
  - Stream Server: Port 8001 (ib-stream)

- **Development Environment**: 8100-8199
  - Contract Server: Port 8100 (ib-contract-dev)
  - Stream Server: Port 8101 (ib-stream-dev)

- **Staging Environment**: 8200-8299 (optional)
  - Contract Server: Port 8200 (ib-contract-staging)
  - Stream Server: Port 8201 (ib-stream-staging)

### TWS Client ID Management

To avoid conflicts when connecting to TWS/Gateway, each environment uses different client IDs:

- **Production**: 
  - Main client: ID 2
  - Background streams: ID 10
- **Development**: 
  - Main client: ID 12
  - Background streams: ID 20
- **Staging**: 
  - Main client: ID 22
  - Background streams: ID 30

## Environment Configuration

### Environment Files

Create environment-specific configuration files:

#### `config/production.env`
```bash
# Production Environment Configuration
PORT=8001
IB_STREAM_CLIENT_ID=2
IB_STREAM_STORAGE_PATH=storage
IB_STREAM_ENABLE_STORAGE=true
IB_STREAM_TRACKED_CONTRACTS=711280073:MNQ:bid_ask;last:1
```

#### `config/development.env`
```bash
# Development Environment Configuration
PORT=8101
IB_STREAM_CLIENT_ID=12
IB_STREAM_STORAGE_PATH=storage-dev
IB_STREAM_ENABLE_STORAGE=true
IB_STREAM_TRACKED_CONTRACTS=
```

#### `config/staging.env`
```bash
# Staging Environment Configuration
PORT=8201
IB_STREAM_CLIENT_ID=22
IB_STREAM_STORAGE_PATH=storage-staging
IB_STREAM_ENABLE_STORAGE=true
IB_STREAM_TRACKED_CONTRACTS=711280073:MNQ:bid_ask;last:1
```

### Storage Path Isolation

Each environment uses isolated storage paths:

- **Production**: `storage/` (current implementation)
- **Development**: `storage-dev/` or `storage-{version}/`
- **Staging**: `storage-staging/`

This prevents development work from interfering with production data collection.

## Development Modes

### 1. Recording Mode (Full Development)

Run complete background streaming with independent storage:

```bash
# Start development servers with recording
cd ib-stream
env $(cat config/development.env | xargs) bd start --name ib-stream-dev -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8101

cd ib-contract
env $(cat ../config/development.env | xargs) bd start --name ib-contracts-dev -- uvicorn api_server:app --host 0.0.0.0 --port 8100
```

### 2. Passthrough Mode (API Development)

Disable background streaming, rely on production data:

```bash
# Development without background streaming
export IB_STREAM_TRACKED_CONTRACTS=""
export IB_STREAM_ENABLE_STORAGE=false
bd start --name ib-stream-dev -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8101
```

### 3. Isolated Mode (Feature Development)

Independent storage for testing new features:

```bash
# Feature branch development
export IB_STREAM_STORAGE_PATH=storage-feature-xyz
export IB_STREAM_TRACKED_CONTRACTS=711280073:MNQ:bid_ask;last:1
bd start --name ib-stream-feature -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8101
```

### 4. Migration Mode (Production Testing)

Test migrations using production storage (read-only):

```bash
# Test with production data
export IB_STREAM_STORAGE_PATH=storage
export IB_STREAM_ENABLE_STORAGE=false  # Read-only mode
bd start --name ib-stream-migration -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8101
```

## Backdrop Service Management

### Service Naming Convention

- Production: `ib-stream`, `ib-contracts`
- Development: `ib-stream-dev`, `ib-contracts-dev`
- Staging: `ib-stream-staging`, `ib-contracts-staging`

### Common Commands

```bash
# Start production (current)
bd start --name ib-stream -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001
cd ib-contract && bd start --name ib-contracts -- uvicorn api_server:app --host 0.0.0.0 --port 8000

# Start development
bd start --name ib-stream-dev -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8101
cd ib-contract && bd start --name ib-contracts-dev -- uvicorn api_server:app --host 0.0.0.0 --port 8100

# Switch environments
bd stop ib-stream-dev
bd start --name ib-stream-dev -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8101

# Monitor logs
bd logs ib-stream-dev --follow
bd logs ib-contracts-dev --follow
```

## Migration Strategy

### Blue-Green Deployment

1. **Preparation Phase**
   - Start new version on development ports (8100/8101)
   - Validate functionality with test data
   - Verify storage compatibility

2. **Staging Phase**
   - Deploy to staging environment (8200/8201)
   - Run with production-like configuration
   - Perform integration testing

3. **Migration Phase**
   - Graceful shutdown of production services
   - Atomic switch of storage paths (if needed)
   - Start new version on production ports (8000/8001)
   - Validate data continuity

### Storage Migration

#### Symlink Strategy (Atomic Migration)

```bash
# Prepare new storage location
mkdir storage-new
# ... populate with migrated data ...

# Atomic switch (zero downtime)
ln -sfn storage-new storage-active
# Update configuration to use storage-active

# Rollback if needed
ln -sfn storage storage-active
```

#### Backup Strategy

```bash
# Before migration
cp -r storage storage-backup-$(date +%Y%m%d-%H%M%S)

# After successful migration
# Keep backup for rollback period
```

### Data Validation

#### Pre-Migration Checks

```bash
# Check storage format compatibility
python -m ib_stream.tools.validate_storage --path storage

# Verify tracked contracts configuration
python -m ib_stream.tools.validate_config --env config/production.env
```

#### Post-Migration Validation

```bash
# Verify data continuity
python -m ib_stream.tools.validate_migration --old storage-backup-* --new storage

# Check API endpoints
curl -s http://localhost:8001/health | jq .
curl -s http://localhost:8001/background/status | jq .
```

## Development Workflow

### 1. Feature Development

```bash
# Create feature branch
git checkout -b feature/new-endpoint

# Start development environment
export IB_STREAM_STORAGE_PATH=storage-feature-new-endpoint
bd start --name ib-stream-feature -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8101

# Develop and test
# ...

# Stop development environment
bd stop ib-stream-feature
```

### 2. Integration Testing

```bash
# Test with production-like data
export IB_STREAM_STORAGE_PATH=storage-staging
export IB_STREAM_TRACKED_CONTRACTS=711280073:MNQ:bid_ask;last:1
bd start --name ib-stream-staging -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8201

# Run integration tests
# ...
```

### 3. Production Deployment

```bash
# Final validation
bd stop ib-stream
bd start --name ib-stream-new -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001

# Monitor for issues
bd logs ib-stream-new --follow

# If successful, clean up
bd stop ib-stream-new
bd start --name ib-stream -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001
```

## Configuration Management

### Environment Variable Precedence

1. Command-line environment variables (highest priority)
2. Environment file (`config/{env}.env`)
3. Default configuration values (lowest priority)

### Configuration Templates

Create templates for common configurations:

```bash
# config/templates/development-recording.env
PORT=8101
IB_STREAM_CLIENT_ID=12
IB_STREAM_STORAGE_PATH=storage-dev
IB_STREAM_ENABLE_STORAGE=true
IB_STREAM_TRACKED_CONTRACTS=711280073:MNQ:bid_ask;last:1

# config/templates/development-api-only.env
PORT=8101
IB_STREAM_CLIENT_ID=12
IB_STREAM_STORAGE_PATH=storage-dev
IB_STREAM_ENABLE_STORAGE=false
IB_STREAM_TRACKED_CONTRACTS=
```

## Monitoring and Observability

### Health Checks

Each environment provides health endpoints:

```bash
# Production
curl -s http://localhost:8001/health
curl -s http://localhost:8000/health

# Development
curl -s http://localhost:8101/health
curl -s http://localhost:8100/health
```

### Log Management

Backdrop automatically manages logs for each environment:

```bash
# Production logs
bd logs ib-stream
bd logs ib-contracts

# Development logs
bd logs ib-stream-dev
bd logs ib-contracts-dev
```

### Storage Monitoring

```bash
# Monitor storage usage
du -sh storage* | sort -h

# Check storage health
find storage* -name "*.jsonl" -size 0 -delete  # Clean up empty files
```

## Security Considerations

### TWS Connection Security

- Use different client IDs to prevent conflicts
- Ensure only authorized development connects to live TWS
- Use paper trading accounts for development when possible

### Data Access

- Development environments should not access production storage by default
- Use read-only access when testing with production data
- Implement proper backup/restore procedures

### Network Security

- Development ports (8100+) should be firewalled from external access
- Use localhost binding for development environments
- Implement proper authentication for staging environments

## Troubleshooting

### Common Issues

1. **Port Conflicts**
   ```bash
   # Check port usage
   netstat -tlnp | grep :810
   
   # Kill conflicting processes
   bd stop ib-stream-dev
   ```

2. **TWS Client ID Conflicts**
   ```bash
   # Check client IDs in logs
   bd logs ib-stream-dev | grep "client ID"
   
   # Ensure different IDs per environment
   export IB_STREAM_CLIENT_ID=12
   ```

3. **Storage Path Issues**
   ```bash
   # Check storage permissions
   ls -la storage*
   
   # Create missing directories
   mkdir -p storage-dev/{json,protobuf}
   ```

### Recovery Procedures

1. **Rollback Migration**
   ```bash
   # Stop new version
   bd stop ib-stream
   
   # Restore backup
   mv storage storage-failed
   mv storage-backup-YYYYMMDD-HHMMSS storage
   
   # Start old version
   bd start --name ib-stream -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001
   ```

2. **Data Recovery**
   ```bash
   # Check data integrity
   python -m ib_stream.tools.validate_storage --path storage --repair
   
   # Rebuild indices if needed
   python -m ib_stream.tools.rebuild_indices --path storage
   ```

## Future Enhancements

### Planned Improvements

1. **Automated Migration Scripts**
   - Schema migration tools
   - Data format converters
   - Validation automation

2. **Enhanced Monitoring**
   - Metrics collection
   - Alerting systems
   - Performance monitoring

3. **Container Support**
   - Docker configurations
   - Kubernetes deployment
   - Environment isolation

4. **Testing Framework**
   - Automated testing environments
   - Data replay capabilities
   - Performance benchmarks

This migration and development strategy provides a robust foundation for maintaining production stability while enabling rapid development and safe deployments.