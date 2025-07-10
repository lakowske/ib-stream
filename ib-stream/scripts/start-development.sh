#!/bin/bash
# Start development environment

set -e

# Set development environment
export IB_STREAM_ENV=development

# Check if we should load from a template
TEMPLATE=${1:-}
if [ -n "$TEMPLATE" ]; then
    if [ -f "config/templates/$TEMPLATE.env" ]; then
        echo "Loading configuration from config/templates/$TEMPLATE.env"
        # Load template variables
        set -a
        source "config/templates/$TEMPLATE.env"
        set +a
    else
        echo "Template $TEMPLATE not found in config/templates/"
        exit 1
    fi
fi

# Start contract server on development port
cd ../ib-contract
bd start --name ib-contracts-dev -- uvicorn api_server:app --host 0.0.0.0 --port 8100

# Start stream server on development port
cd ../ib-stream  
bd start --name ib-stream-dev -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8101

echo "Development servers started:"
echo "  Contract Server: http://localhost:8100"
echo "  Stream Server: http://localhost:8101"
echo ""
echo "Monitor with:"
echo "  bd logs ib-contracts-dev --follow"
echo "  bd logs ib-stream-dev --follow"