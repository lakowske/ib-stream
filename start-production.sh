#!/bin/bash
# Production server startup script with full storage configuration

# Get the absolute path to the project directory
export PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export USER="$(whoami)"

# Set production environment
export IB_STREAM_ENV="production-server"
export IB_STREAM_CONFIG_TYPE="production"

echo "Starting Production IB Stream Server"
echo "===================================="
echo "Server: 192.168.0.60 (localhost TWS connection)"
echo "Environment: production-server"
echo "Full storage enabled with background streaming"
echo ""

# Generate instance configuration if it doesn't exist or is outdated
echo "Generating instance configuration..."
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/generate_instance_config.py"

# Load instance configuration and export as environment variables
if [ -f "$PROJECT_ROOT/ib-stream/config/instance.env" ]; then
    echo "Loading instance configuration from ib-stream/config/instance.env"
    # Export variables from instance.env
    export $(grep -v '^#' "$PROJECT_ROOT/ib-stream/config/instance.env" | xargs)
else
    echo "Warning: instance.env not found, using defaults"
    export IB_STREAM_CLIENT_ID=100
    export IB_CONTRACTS_CLIENT_ID=101
    export IB_STREAM_PORT=8001
    export IB_CONTRACTS_PORT=8002
fi

# Load production-specific environment variables
if [ -f "$PROJECT_ROOT/ib-stream/config/production-server.env" ]; then
    echo "Loading production configuration from production-server.env"
    # Export variables from production-server.env (but don't override instance-specific ones)
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ $key =~ ^#.*$ || -z $key ]] && continue
        # Skip instance-specific variables that are already set
        case $key in
            IB_STREAM_CLIENT_ID|IB_CONTRACTS_CLIENT_ID|IB_STREAM_PORT|IB_CONTRACTS_PORT)
                continue
                ;;
            *)
                export "$key=$value"
                ;;
        esac
    done < "$PROJECT_ROOT/ib-stream/config/production-server.env"
fi

echo "Production configuration:"
echo "  PROJECT_ROOT: $PROJECT_ROOT"
echo "  USER: $USER"
echo "  IB_STREAM_CLIENT_ID: $IB_STREAM_CLIENT_ID"
echo "  IB_CONTRACTS_CLIENT_ID: $IB_CONTRACTS_CLIENT_ID"
echo "  IB_STREAM_PORT: $IB_STREAM_PORT"
echo "  IB_CONTRACTS_PORT: $IB_CONTRACTS_PORT"
echo "  IB_STREAM_HOST: ${IB_STREAM_HOST:-localhost}"
echo "  IB_STREAM_ENABLE_STORAGE: ${IB_STREAM_ENABLE_STORAGE:-true}"
echo "  IB_STREAM_TRACKED_CONTRACTS: ${IB_STREAM_TRACKED_CONTRACTS:-none}"
echo ""

# Create logs directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/logs"

# Install supervisor if not available in venv
if [ ! -f "$PROJECT_ROOT/.venv/bin/supervisord" ]; then
    echo "Installing supervisor in virtual environment..."
    "$PROJECT_ROOT/.venv/bin/pip" install supervisor
fi

# Stop any existing supervisor
if [ -f "$PROJECT_ROOT/supervisord.pid" ]; then
    echo "Stopping existing supervisor..."
    "$PROJECT_ROOT/.venv/bin/supervisorctl" -c "$PROJECT_ROOT/supervisor.conf" shutdown 2>/dev/null || true
    sleep 2
fi

# Create production environment file for supervisor
cat > "$PROJECT_ROOT/.production-env" << ENVEOF
export IB_STREAM_ENV=production-server
export PROJECT_ROOT=$PROJECT_ROOT
export IB_STREAM_CLIENT_ID=$IB_STREAM_CLIENT_ID
export IB_CONTRACTS_CLIENT_ID=$IB_CONTRACTS_CLIENT_ID
export IB_STREAM_PORT=$IB_STREAM_PORT
export IB_CONTRACTS_PORT=$IB_CONTRACTS_PORT
export IB_STREAM_HOST=localhost
export IB_STREAM_PORTS=4002
export IB_STREAM_ENABLE_STORAGE=true
export IB_STREAM_ENABLE_JSON=true
export IB_STREAM_ENABLE_PROTOBUF=true
export IB_STREAM_ENABLE_POSTGRES=true
export IB_STREAM_ENABLE_METRICS=true
export IB_STREAM_ENABLE_CLIENT_STREAM_STORAGE=true
export IB_STREAM_ENABLE_BACKGROUND_STREAMING=true
export IB_STREAM_TRACKED_CONTRACTS="711280073:MNQ:bid_ask;last:24"
export IB_STREAM_MAX_STREAMS=100
export IB_STREAM_BUFFER_SIZE=1000
export IB_STREAM_ENVIRONMENT=production-server
export IB_STREAM_SERVER_TYPE=production
export PORT=$IB_STREAM_PORT
ENVEOF

# Create production supervisor config dynamically
cat > "$PROJECT_ROOT/supervisor-production.conf" << EOF
[unix_http_server]
file=$PROJECT_ROOT/supervisor.sock

[supervisord]
logfile=$PROJECT_ROOT/logs/supervisord.log
pidfile=$PROJECT_ROOT/supervisord.pid
childlogdir=$PROJECT_ROOT/logs
nodaemon=false

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix://$PROJECT_ROOT/supervisor.sock

[program:ib-stream-production]
command=/bin/bash -c "source $PROJECT_ROOT/.production-env && $PROJECT_ROOT/.venv/bin/uvicorn ib_stream.api_server:app --host 0.0.0.0 --port $IB_STREAM_PORT"
directory=$PROJECT_ROOT/ib-stream
autostart=true
autorestart=true
startretries=3
user=$USER
stdout_logfile=$PROJECT_ROOT/logs/ib-stream-production-stdout.log
stderr_logfile=$PROJECT_ROOT/logs/ib-stream-production-stderr.log
stdout_logfile_maxbytes=10MB
stderr_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile_backups=5

[program:ib-contracts-production]  
command=/bin/bash -c "source $PROJECT_ROOT/.production-env && $PROJECT_ROOT/.venv/bin/uvicorn api_server:app --host 0.0.0.0 --port $IB_CONTRACTS_PORT"
directory=$PROJECT_ROOT/ib-contract
autostart=true
autorestart=true
startretries=3
user=$USER  
stdout_logfile=$PROJECT_ROOT/logs/ib-contracts-production-stdout.log
stderr_logfile=$PROJECT_ROOT/logs/ib-contracts-production-stderr.log
stdout_logfile_maxbytes=10MB
stderr_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile_backups=5
EOF

# Start supervisord with production config
echo "Starting production supervisord..."
"$PROJECT_ROOT/.venv/bin/supervisord" -c "$PROJECT_ROOT/supervisor-production.conf"

if [ $? -eq 0 ]; then
    echo "✓ Production supervisor started successfully"
    echo ""
    echo "Production services:"
    echo "  ib-stream-production: http://localhost:$IB_STREAM_PORT"
    echo "  ib-contracts-production: http://localhost:$IB_CONTRACTS_PORT"
    echo ""
    echo "Management commands:"
    echo "  $PROJECT_ROOT/.venv/bin/supervisorctl -c $PROJECT_ROOT/supervisor-production.conf status"
    echo "  $PROJECT_ROOT/.venv/bin/supervisorctl -c $PROJECT_ROOT/supervisor-production.conf tail -f ib-stream-production"
    echo "  $PROJECT_ROOT/.venv/bin/supervisorctl -c $PROJECT_ROOT/supervisor-production.conf restart ib-stream-production"
    echo ""
    echo "Health checks:"
    echo "  curl http://localhost:$IB_STREAM_PORT/health"
    echo "  curl http://localhost:$IB_CONTRACTS_PORT/health"
else
    echo "✗ Failed to start production supervisor"
    exit 1
fi