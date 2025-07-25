#!/usr/bin/env python3
"""
FastAPI Server for IB Stream API
Provides HTTP endpoints for real-time streaming market data via Server-Sent Events.
"""

import logging
import os

from fastapi import FastAPI

from .app_lifecycle import lifespan, get_app_state
from .endpoints.health import setup_health_endpoints
from .endpoints.buffer import setup_buffer_endpoints
from .endpoints.streaming import setup_streaming_endpoints
from .endpoints.websocket import setup_websocket_endpoints
from .endpoints.management import setup_management_endpoints

# Configure logging
app_state = get_app_state()
config = app_state['config']

logging.basicConfig(
    level=config.log_level,
    format=config.log_format,
)
logger = logging.getLogger(__name__)




app = FastAPI(
    title="IB Stream API Server",
    description="Real-time streaming market data from Interactive Brokers TWS via Server-Sent Events",
    version="1.0.0",
    lifespan=lifespan,
)

# Setup all endpoint modules
setup_health_endpoints(app, config)
setup_buffer_endpoints(app, config)
setup_streaming_endpoints(app, config)
setup_websocket_endpoints(app)
setup_management_endpoints(app, config)


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "IB Stream API Server",
        "version": "1.0.0",
        "description": "Real-time streaming market data via Server-Sent Events",
        "documentation": {
            "info": "Visit /stream/info for detailed API usage and examples",
            "health": "Check /health for server and connection status",
            "active": "View /stream/active for currently running streams",
        },
        "endpoints": {
            "/v2/stream/{contract_id}/buffer": "Stream historical buffer + live data (SSE)",
            "/v2/stream/{contract_id}/live/{tick_type}": "Stream specific tick type data (SSE)",
            "/v2/stream/{contract_id}/live": "Stream multiple tick types (SSE)",
            "ws://{host}/v2/ws/stream": "V2 WebSocket streaming endpoint",
            "ws://{host}/ws/stream/{contract_id}/{tick_type}": "WebSocket streaming for specific tick type",
            "ws://{host}/ws/stream/{contract_id}/multi": "WebSocket multi-stream endpoint",
            "ws://{host}/ws/control": "WebSocket control channel",
            "/health": "Health check with TWS connection status",
            "/storage/status": "Storage system status and metrics",
            "/background/status": "Background streaming status",
            "/v2/buffer/{contract_id}/info": "Buffer information for contract",
            "/v2/buffer/{contract_id}/stats": "Buffer statistics for contract",
            "/stream/info": "Available tick types and streaming capabilities",
            "/v2/info": "V2 protocol information",
            "/stream/active": "List currently active streams",
            "DELETE /stream/{contract_id}": "Stop all streams for a specific contract",
            "DELETE /stream/all": "Stop all active streams",
        },
        "tick_types": ["last", "all_last", "bid_ask", "mid_point"],
        "configuration": {
            "client_id": config.client_id,
            "max_concurrent_streams": config.max_concurrent_streams,
            "default_timeout_seconds": config.default_timeout_seconds,
        },
    }





def main():
    """Main function to run the server"""
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info("Starting IB Stream API Server on %s:%d", host, port)
    uvicorn.run(
        "ib_stream.api_server:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
