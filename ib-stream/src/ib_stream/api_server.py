#!/usr/bin/env python3
"""
FastAPI Server for IB Stream API
Provides HTTP endpoints for real-time streaming market data via Server-Sent Events.
"""

import asyncio
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from .config import create_config, get_default_tick_type, is_valid_tick_type
from .sse_response import (
    SSECompleteEvent,
    SSEErrorEvent,
    SSETickEvent,
    create_rate_limit_error_event,
    create_sse_response,
    create_stream_started_event,
    create_timeout_error_event,
)
from .streaming_app import StreamingApp
from .utils import connect_to_tws

# Load configuration
config = create_config()

# Configure logging
logging.basicConfig(
    level=config.log_level,
    format=config.log_format,
)
logger = logging.getLogger(__name__)

# Global TWS connection
tws_app: Optional[StreamingApp] = None
tws_lock = threading.Lock()

# Stream management
active_streams = {}
stream_lock = threading.Lock()


def ensure_tws_connection() -> StreamingApp:
    """Ensure TWS connection is active"""
    global tws_app

    with tws_lock:
        if tws_app is None or not tws_app.isConnected():
            logger.info("Establishing TWS connection with client ID %d...", config.client_id)
            tws_app = StreamingApp(json_output=True)

            if not connect_to_tws(tws_app, client_id=config.client_id):
                msg = "Unable to connect to TWS/Gateway. Please ensure it's running with API enabled."
                raise HTTPException(status_code=503, detail=msg)

            # Wait for connection to be ready
            timeout = config.connection_timeout
            start_time = time.time()
            while not tws_app.connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)

            if not tws_app.connected:
                msg = "TWS connection established but not ready"
                raise HTTPException(status_code=503, detail=msg)

            logger.info("TWS connection established successfully")

    return tws_app


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Lifespan event handler for startup/shutdown"""
    # Startup
    logger.info("Starting IB Stream API Server...")
    logger.info("Configuration:")
    logger.info("  Client ID: %d", config.client_id)
    logger.info("  Host: %s", config.host)
    logger.info("  Max Streams: %d", config.max_concurrent_streams)
    logger.info("  Default Timeout: %d seconds", config.default_timeout_seconds)

    logger.info("Attempting to establish TWS connection...")
    try:
        ensure_tws_connection()
        logger.info("TWS connection established successfully")
    except Exception as e:
        logger.warning("Failed to establish initial TWS connection: %s", e)
        logger.info("Will attempt to connect on first streaming request")

    yield

    # Shutdown
    logger.info("Shutting down IB Stream API Server...")
    global tws_app
    if tws_app and tws_app.isConnected():
        # Stop all active streams
        with stream_lock:
            for stream_id in list(active_streams.keys()):
                try:
                    tws_app.cancelTickByTickData(stream_id)
                except Exception as e:
                    logger.warning("Error cancelling stream %s: %s", stream_id, e)
            active_streams.clear()

        tws_app.disconnect()
        logger.info("TWS connection closed")


app = FastAPI(
    title="IB Stream API Server",
    description="Real-time streaming market data from Interactive Brokers TWS via Server-Sent Events",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "IB Stream API Server",
        "version": "1.0.0",
        "description": "Real-time streaming market data via Server-Sent Events",
        "endpoints": {
            "/stream/{contract_id}": "Stream market data for a contract with query parameters",
            "/stream/{contract_id}/{tick_type}": "Stream specific tick type data",
            "/health": "Health check with TWS connection status",
            "/stream/info": "Available tick types and streaming capabilities",
            "/stream/active": "List currently active streams",
            "DELETE /stream/{contract_id}": "Stop all streams for a specific contract",
            "DELETE /stream/all": "Stop all active streams",
        },
        "tick_types": ["Last", "AllLast", "BidAsk", "MidPoint"],
        "configuration": {
            "client_id": config.client_id,
            "max_concurrent_streams": config.max_concurrent_streams,
            "default_timeout_seconds": config.default_timeout_seconds,
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        tws_connected = tws_app is not None and tws_app.isConnected()
        with stream_lock:
            active_stream_count = len(active_streams)

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "tws_connected": tws_connected,
            "active_streams": active_stream_count,
            "max_streams": config.max_concurrent_streams,
            "client_id": config.client_id,
        }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            },
        )


@app.get("/stream/info")
async def stream_info():
    """Information about available streaming capabilities"""
    return {
        "tick_types": {
            "Last": "Regular trades during market hours",
            "AllLast": "All trades including pre/post market",
            "BidAsk": "Real-time bid and ask quotes",
            "MidPoint": "Calculated midpoint between bid and ask",
        },
        "query_parameters": {
            "limit": "Number of ticks before auto-stop (integer, optional)",
            "tick_type": "Data type to stream (enum: Last, AllLast, BidAsk, MidPoint)",
            "timeout": "Stream timeout in seconds (integer, default: 300)",
        },
        "sse_event_types": {
            "tick": "Market data tick",
            "error": "Stream error",
            "complete": "Stream completion",
            "info": "Stream metadata",
        },
        "limits": {
            "max_concurrent_streams": config.max_concurrent_streams,
            "default_timeout_seconds": config.default_timeout_seconds,
        },
    }


async def stream_contract_data(contract_id: int, tick_type: str, limit: Optional[int] = None,
                              timeout: Optional[int] = None) -> AsyncGenerator[Any, None]:
    """Stream contract data via SSE using StreamManager for isolation"""
    from .stream_manager import stream_manager, StreamHandler
    
    if timeout is None:
        timeout = config.default_timeout_seconds

    # Check if we're at max streams
    current_stream_count = stream_manager.get_stream_count()
    if current_stream_count >= config.max_concurrent_streams:
        event = create_rate_limit_error_event(contract_id)
        yield event
        return

    # Generate unique request ID
    import time
    import random
    req_id = int(time.time() * 1000) % 100000 + random.randint(1, 999)
    
    # Create event queue for this stream
    event_queue = asyncio.Queue()
    stream_id = f"{contract_id}_{tick_type}_{id(event_queue)}"
    
    logger.info("Starting stream for contract %d, type %s, limit %s, timeout %s", 
                contract_id, tick_type, limit, timeout)
    logger.info("Starting stream %s for contract %d", stream_id, contract_id)
    logger.info("Using request ID %d for stream %s", req_id, stream_id)

    try:
        # Get TWS connection
        app_instance = ensure_tws_connection()
        
        # Create callback functions for SSE events
        async def on_tick(tick_data: Dict[str, Any]):
            event = SSETickEvent(contract_id, tick_data)
            try:
                await event_queue.put(event)
            except Exception as e:
                logger.warning("Failed to queue tick event for stream %s: %s", stream_id, e)

        async def on_error(error_code: str, message: str):
            event = SSEErrorEvent(contract_id, error_code, message)
            try:
                await event_queue.put(event)
            except Exception as e:
                logger.warning("Failed to queue error event for stream %s: %s", stream_id, e)

        async def on_complete(reason: str, total_ticks: int):
            event = SSECompleteEvent(contract_id, reason, total_ticks)
            try:
                await event_queue.put(event)
            except Exception as e:
                logger.warning("Failed to queue complete event for stream %s: %s", stream_id, e)

        # Create StreamHandler for this stream
        stream_handler = StreamHandler(
            request_id=req_id,
            contract_id=contract_id,
            tick_type=tick_type,
            limit=limit,
            timeout=timeout,
            tick_callback=on_tick,
            error_callback=on_error,
            complete_callback=on_complete
        )
        
        # Set the request ID on the app instance BEFORE registering anything
        app_instance.req_id = req_id
        
        # Register the stream with StreamManager
        stream_manager.register_stream(stream_handler)
        
        # Register stream in active_streams for tracking
        with stream_lock:
            active_streams[stream_id] = {
                "contract_id": contract_id,
                "tick_type": tick_type,
                "start_time": datetime.now(),
                "request_id": req_id,
                "app": app_instance,
                "queue": event_queue
            }

        # Start streaming in background
        async def start_stream():
            try:
                logger.info("Starting TWS stream for request ID %d", req_id)

                # Start streaming - this will route through StreamManager
                app_instance.stream_contract(contract_id, tick_type)

                # Send start event
                start_event = create_stream_started_event(contract_id, tick_type)
                await event_queue.put(start_event)

            except Exception as e:
                import traceback
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                logger.error("Detailed stream start error: %s", error_msg)
                error_event = SSEErrorEvent(contract_id, "STREAM_START_ERROR", str(e))
                await event_queue.put(error_event)

        # Start the stream
        asyncio.create_task(start_stream())

        # Stream events with timeout
        start_time = time.time()
        while True:
            try:
                # Check timeout only if one is set
                if timeout is not None and time.time() - start_time > timeout:
                    timeout_event = create_timeout_error_event(contract_id, timeout)
                    yield timeout_event
                    break

                # Get next event with timeout
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                yield event

                # Check if stream is complete
                if isinstance(event, SSECompleteEvent):
                    break

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                import traceback
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                logger.error("Error in stream %s: %s", stream_id, error_msg)
                error_event = SSEErrorEvent(contract_id, "STREAM_ERROR", str(e))
                yield error_event
                break

    finally:
        # Unregister from StreamManager
        stream_manager.unregister_stream(req_id)
        
        # Clean up
        with stream_lock:
            if stream_id in active_streams:
                try:
                    app_data = active_streams[stream_id]
                    if "app" in app_data and "request_id" in app_data:
                        app_data["app"].cancelTickByTickData(app_data["request_id"])
                        # Clean up request-specific data
                        app_data["app"].cleanup_request(app_data["request_id"])
                except Exception as e:
                    import traceback
                    logger.error("Error cleaning up stream %s: %s\nTraceback:\n%s", stream_id, e, traceback.format_exc())
                del active_streams[stream_id]

        logger.info("Stream %s ended", stream_id)


@app.get("/stream/active")
async def get_active_streams():
    """Get list of currently active streams"""
    with stream_lock:
        streams = []
        for stream_id, stream_data in active_streams.items():
            streams.append({
                "stream_id": stream_id,
                "contract_id": stream_data["contract_id"],
                "tick_type": stream_data["tick_type"],
                "start_time": stream_data["start_time"].isoformat(),
                "duration_seconds": int((datetime.now() - stream_data["start_time"]).total_seconds())
            })

        return {
            "active_streams": streams,
            "total_streams": len(streams),
            "max_streams": config.max_concurrent_streams
        }


@app.get("/stream/{contract_id}/{tick_type}")
async def stream_contract_with_type(
    contract_id: int,
    tick_type: str,
    limit: Optional[int] = Query(default=None, description="Number of ticks before auto-stop"),
    timeout: Optional[int] = Query(default=None, description="Stream timeout in seconds")
):
    """Stream market data for a contract with explicit tick type via Server-Sent Events"""
    
    # Validate tick type
    if not is_valid_tick_type(tick_type):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tick type: {tick_type}. Valid types: {', '.join(['Last', 'AllLast', 'BidAsk', 'MidPoint'])}"
        )
    
    # Validate limit
    if limit is not None and (limit < 1 or limit > 10000):
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 10000"
        )
    
    # Validate timeout
    if timeout is not None and (timeout < 5 or timeout > 3600):
        raise HTTPException(
            status_code=400,
            detail="Timeout must be between 5 and 3600 seconds"
        )
    
    logger.info("Starting stream for contract %d, type %s, limit %s, timeout %s",
                contract_id, tick_type, limit, timeout)
    
    # Create event generator
    events = stream_contract_data(contract_id, tick_type, limit, timeout)
    
    # Return SSE response
    return create_sse_response(events)


@app.get("/stream/{contract_id}")
async def stream_contract(
    contract_id: int,
    tick_type: str = Query(default=get_default_tick_type(), description="Type of tick data to stream"),
    limit: Optional[int] = Query(default=None, description="Number of ticks before auto-stop"),
    timeout: Optional[int] = Query(default=None, description="Stream timeout in seconds")
):
    """Stream market data for a contract via Server-Sent Events"""

    # Validate tick type
    if not is_valid_tick_type(tick_type):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tick type: {tick_type}. Valid types: {', '.join(['Last', 'AllLast', 'BidAsk', 'MidPoint'])}"
        )

    # Validate limit
    if limit is not None and (limit < 1 or limit > 10000):
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 10000"
        )

    # Validate timeout
    if timeout is not None and (timeout < 5 or timeout > 3600):
        raise HTTPException(
            status_code=400,
            detail="Timeout must be between 5 and 3600 seconds"
        )

    logger.info("Starting stream for contract %d, type %s, limit %s, timeout %s",
                contract_id, tick_type, limit, timeout)

    # Create event generator
    events = stream_contract_data(contract_id, tick_type, limit, timeout)

    # Return SSE response
    return create_sse_response(events)


@app.delete("/stream/all")
async def stop_all_streams():
    """Stop all active streams"""
    stopped_streams = []
    
    with stream_lock:
        # Stop all streams
        for stream_id, stream_data in list(active_streams.items()):
            try:
                if "app" in stream_data:
                    stream_data["app"].cancelTickByTickData(stream_data["app"].req_id)
                stopped_streams.append({
                    "stream_id": stream_id,
                    "contract_id": stream_data["contract_id"],
                    "tick_type": stream_data["tick_type"],
                    "duration_seconds": int((datetime.now() - stream_data["start_time"]).total_seconds())
                })
                logger.info("Stopped stream %s", stream_id)
            except Exception as e:
                logger.error("Error stopping stream %s: %s", stream_id, e)
        
        # Clear all active streams
        active_streams.clear()
    
    return {
        "message": f"Stopped {len(stopped_streams)} streams",
        "stopped_streams": stopped_streams,
        "timestamp": datetime.now().isoformat()
    }


@app.delete("/stream/{contract_id}")
async def stop_contract_streams(contract_id: int):
    """Stop all active streams for a specific contract"""
    stopped_streams = []
    
    with stream_lock:
        # Find all streams for this contract
        streams_to_stop = []
        for stream_id, stream_data in active_streams.items():
            if stream_data["contract_id"] == contract_id:
                streams_to_stop.append((stream_id, stream_data))
        
        # Stop each stream
        for stream_id, stream_data in streams_to_stop:
            try:
                if "app" in stream_data:
                    stream_data["app"].cancelTickByTickData(stream_data["app"].req_id)
                stopped_streams.append({
                    "stream_id": stream_id,
                    "contract_id": contract_id,
                    "tick_type": stream_data["tick_type"],
                    "duration_seconds": int((datetime.now() - stream_data["start_time"]).total_seconds())
                })
                del active_streams[stream_id]
                logger.info("Stopped stream %s for contract %d", stream_id, contract_id)
            except Exception as e:
                logger.error("Error stopping stream %s: %s", stream_id, e)
    
    if not stopped_streams:
        raise HTTPException(
            status_code=404,
            detail=f"No active streams found for contract {contract_id}"
        )
    
    return {
        "message": f"Stopped {len(stopped_streams)} streams for contract {contract_id}",
        "stopped_streams": stopped_streams,
        "timestamp": datetime.now().isoformat()
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
