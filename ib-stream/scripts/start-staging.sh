#!/bin/bash
# Start staging environment

set -e

# Set staging environment
export IB_STREAM_ENV=staging

# Start contract server
cd ../ib-contract
bd start --name ib-contracts-staging -- uvicorn api_server:app --host 0.0.0.0 --port 8200

# Start stream server
cd ../ib-stream
bd start --name ib-stream-staging -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8201

echo "Staging servers started:"
echo "  Contract Server: http://localhost:8200"
echo "  Stream Server: http://localhost:8201"
echo ""
echo "Monitor with:"
echo "  bd logs ib-contracts-staging --follow"
echo "  bd logs ib-stream-staging --follow"