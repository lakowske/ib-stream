#!/usr/bin/env python3
"""
Unified IB Stream App - Uses the new unified connection architecture
This is the main entry point for the unified architecture implementation.
"""

from fastapi import FastAPI
from .app_lifecycle import lifespan
from .endpoints.health import setup_health_endpoints
from .endpoints.buffer import setup_buffer_endpoints  
from .endpoints.streaming import setup_streaming_endpoints
from .endpoints.websocket import setup_websocket_endpoints
from .endpoints.management import setup_management_endpoints
from .endpoints.v3 import setup_v3_endpoints


def create_unified_app() -> FastAPI:
    """
    Create the FastAPI app with unified connection architecture
    
    This uses the lifespan from app_lifecycle.py which implements:
    - Single UnifiedConnectionManager 
    - BackgroundStreamManager v2 with shared connection
    - Unified recovery system
    - Single client ID for all streams
    """
    app = FastAPI(
        title="IB Stream API - Unified Architecture",
        description="Real-time streaming market data from Interactive Brokers TWS via Server-Sent Events (Unified Architecture)",
        version="3.0.0",
        lifespan=lifespan  # Use the unified lifespan
    )
    
    # Get config for endpoint setup
    from .config import create_config
    config = create_config()
    
    # Setup all endpoints (some need config, some don't)
    setup_health_endpoints(app, config)
    setup_buffer_endpoints(app, config)
    setup_streaming_endpoints(app, config)  
    setup_websocket_endpoints(app)  # No config parameter
    setup_management_endpoints(app, config)
    setup_v3_endpoints(app, config)
    
    @app.get("/")
    async def root():
        """Root endpoint with API information"""
        return {
            "service": "ib-stream",
            "architecture": "unified",
            "description": "Real-time market data streaming with unified connection architecture",
            "version": "3.0.0",
            "features": [
                "Single connection for all streams",
                "Unified recovery system", 
                "50% resource reduction",
                "Enhanced monitoring",
                "Zero breaking changes"
            ],
            "endpoints": {
                "/health": "Health check with unified connection status",
                "/stream/info": "Streaming API documentation",
                "/v2/stream/{contract_id}/buffer": "Stream historical buffer + live data (SSE)",
                "/v2/stream/{contract_id}/live/{tick_type}": "Stream specific tick type data (SSE)", 
                "/background/health/summary": "Background stream health summary",
                "ws://host/v2/ws/stream": "WebSocket streaming endpoint"
            }
        }
        
    return app


# Create the app instance
app = create_unified_app()