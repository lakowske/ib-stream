#!/bin/bash
# Portable supervisor startup script with dynamic configuration

# Get the absolute path to the project directory
export PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export USER="$(whoami)"

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
    export IB_STREAM_CLIENT_ID=374
    export IB_CONTRACTS_CLIENT_ID=375
    export IB_STREAM_PORT=8774
    export IB_CONTRACTS_PORT=8784
fi

echo "Starting supervisor with:"
echo "  PROJECT_ROOT: $PROJECT_ROOT"
echo "  USER: $USER"
echo "  IB_STREAM_CLIENT_ID: $IB_STREAM_CLIENT_ID"
echo "  IB_CONTRACTS_CLIENT_ID: $IB_CONTRACTS_CLIENT_ID"
echo "  IB_STREAM_PORT: $IB_STREAM_PORT"
echo "  IB_CONTRACTS_PORT: $IB_CONTRACTS_PORT"

# Create logs directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/logs"

# Install supervisor if not available in venv
if [ ! -f "$PROJECT_ROOT/.venv/bin/supervisord" ]; then
    echo "Installing supervisor in virtual environment..."
    "$PROJECT_ROOT/.venv/bin/pip" install supervisor
fi

# Start supervisord
echo "Starting supervisord..."
"$PROJECT_ROOT/.venv/bin/supervisord" -c "$PROJECT_ROOT/supervisor.conf"

if [ $? -eq 0 ]; then
    echo "✓ Supervisor started successfully"
    echo ""
    echo "Management commands:"
    echo "  $PROJECT_ROOT/.venv/bin/supervisorctl -c $PROJECT_ROOT/supervisor.conf status"
    echo "  $PROJECT_ROOT/.venv/bin/supervisorctl -c $PROJECT_ROOT/supervisor.conf start ib-stream-remote"
    echo "  $PROJECT_ROOT/.venv/bin/supervisorctl -c $PROJECT_ROOT/supervisor.conf tail -f ib-stream-remote"
else
    echo "✗ Failed to start supervisor"
    exit 1
fi