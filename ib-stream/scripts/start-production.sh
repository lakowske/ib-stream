#!/bin/bash
# Start production environment

set -e

# Set production environment
export IB_STREAM_ENV=production

# Start contract server
cd ../ib-contract
bd start --name ib-contracts -- uvicorn api_server:app --host 0.0.0.0 --port 8000

# Start stream server  
cd ../ib-stream
bd start --name ib-stream -- uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8001

echo "Production servers started:"
echo "  Contract Server: http://localhost:8000"
echo "  Stream Server: http://localhost:8001"
echo ""
echo "Monitor with:"
echo "  bd logs ib-contracts --follow"
echo "  bd logs ib-stream --follow"