#!/bin/bash
# Wrapper script for supervisor commands that loads instance configuration

# Get the absolute path to the project directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load instance configuration if it exists
if [ -f "$PROJECT_ROOT/ib-stream/config/instance.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/ib-stream/config/instance.env" | xargs)
fi

# Export required environment variables
export PROJECT_ROOT
export USER="$(whoami)"

# Run supervisorctl with the provided arguments
exec "$PROJECT_ROOT/.venv/bin/supervisorctl" -c "$PROJECT_ROOT/supervisor.conf" "$@"