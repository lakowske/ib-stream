#!/bin/bash
# Portable supervisor startup script

# Get the absolute path to the project directory
export PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export USER="$(whoami)"

echo "Starting supervisor with:"
echo "  PROJECT_ROOT: $PROJECT_ROOT"
echo "  USER: $USER"

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