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

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.responses import JSONResponse

from .config import create_config, is_valid_tick_type, convert_v2_tick_type_to_tws_api
from .storage import MultiStorage, create_buffer_query
# Legacy v1 imports - will need to add these back for v1 endpoints
# from .sse_response_v1 import (
#     SSECompleteEvent,
#     SSEErrorEvent, 
#     SSETickEvent,
#     create_rate_limit_error_event,
#     create_sse_response,
#     create_stream_started_event,
#     create_timeout_error_event,
# )
# v2 protocol imports
from .sse_response import (
    SSEEvent,
    create_tick_event,
    create_error_event,
    create_complete_event,
    create_info_event,
    create_stream_started_event as create_v2_stream_started_event,
    create_connection_error_event,
    create_contract_not_found_event,
    create_rate_limit_error_event as create_v2_rate_limit_error_event,
    create_timeout_error_event as create_v2_timeout_error_event,
    SSEStreamingResponse
)
from .streaming_app import StreamingApp
from .utils import connect_to_tws
from .ws_response import websocket_endpoint, websocket_control_endpoint
from .ws_manager import ws_manager
from .stream_id import generate_stream_id, generate_multi_stream_id
from .stream_manager import stream_manager
from .background_stream_manager import BackgroundStreamManager, background_stream_manager

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

# Global storage instance
storage: Optional[MultiStorage] = None

# Global background stream manager
background_manager: Optional[BackgroundStreamManager] = None

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
    if config.default_timeout_seconds is not None:
        logger.info("  Default Timeout: %d seconds", config.default_timeout_seconds)
    else:
        logger.info("  Default Timeout: No timeout (unlimited)")
    
    # Initialize storage system
    global storage
    if config.storage.enable_storage:
        logger.info("Initializing storage system...")
        logger.info("  Storage path: %s", config.storage.storage_base_path)
        logger.info("  JSON enabled: %s", config.storage.enable_json)
        logger.info("  Protobuf enabled: %s", config.storage.enable_protobuf)
        logger.info("  PostgreSQL enabled: %s", config.storage.enable_postgres_index)
        
        try:
            storage = MultiStorage(
                storage_path=config.storage.storage_base_path,
                enable_json=config.storage.enable_json,
                enable_protobuf=config.storage.enable_protobuf,
                enable_metrics=config.storage.enable_metrics
            )
            await storage.start()
            logger.info("Storage system initialized successfully")
            
            # Initialize stream_manager with storage
            stream_manager.storage = storage
            logger.info("Stream manager configured with storage")
            
        except Exception as e:
            logger.error("Failed to initialize storage system: %s", e)
            logger.info("Continuing without storage...")
            storage = None
    else:
        logger.info("Storage system disabled")

    logger.info("Attempting to establish TWS connection...")
    try:
        ensure_tws_connection()
        logger.info("TWS connection established successfully")
    except Exception as e:
        logger.warning("Failed to establish initial TWS connection: %s", e)
        logger.info("Will attempt to connect on first streaming request")
    
    # Initialize background streaming for tracked contracts
    global background_manager
    if config.storage.tracked_contracts:
        logger.info("Initializing background streaming for %d tracked contracts...", 
                   len(config.storage.tracked_contracts))
        
        try:
            background_manager = BackgroundStreamManager(
                tracked_contracts=config.storage.tracked_contracts,
                reconnect_delay=config.storage.background_stream_reconnect_delay
            )
            await background_manager.start()
            logger.info("Background streaming started successfully")
            
            # Log tracked contracts
            for contract in config.storage.tracked_contracts:
                logger.info("  Tracking contract %d (%s): %s, buffer=%dh", 
                           contract.contract_id, contract.symbol, 
                           contract.tick_types, contract.buffer_hours)
            
        except Exception as e:
            logger.error("Failed to start background streaming: %s", e)
            background_manager = None
    else:
        logger.info("No tracked contracts configured - background streaming disabled")

    yield

    # Shutdown
    logger.info("Shutting down IB Stream API Server...")
    global tws_app
    
    # Stop background streaming
    if background_manager:
        logger.info("Stopping background streaming...")
        try:
            await background_manager.stop()
            logger.info("Background streaming stopped")
        except Exception as e:
            logger.error("Error stopping background streaming: %s", e)
    
    # Stop storage system
    if storage:
        logger.info("Stopping storage system...")
        try:
            await storage.stop()
            logger.info("Storage system stopped")
        except Exception as e:
            logger.error("Error stopping storage system: %s", e)
    
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
        "documentation": {
            "info": "Visit /stream/info for detailed API usage and examples",
            "health": "Check /health for server and connection status",
            "active": "View /stream/active for currently running streams",
        },
        "endpoints": {
            "/stream/{contract_id}/{tick_type}": "Stream specific tick type data for a contract (SSE)",
            "ws://{host}/ws/stream/{contract_id}/{tick_type}": "WebSocket streaming for specific tick type",
            "ws://{host}/ws/stream/{contract_id}/multi": "WebSocket multi-stream endpoint",
            "ws://{host}/ws/control": "WebSocket control channel",
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

        storage_status = None
        if storage:
            storage_info = storage.get_storage_info()
            storage_metrics = storage.get_metrics()
            storage_status = {
                "enabled": True,
                "formats": storage_info.get('enabled_formats', []),
                "queue_sizes": storage_info.get('queue_sizes', {}),
                "health": storage_metrics.get('health', {}) if storage_metrics else {}
            }
        else:
            storage_status = {"enabled": False}

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "tws_connected": tws_connected,
            "active_streams": active_stream_count,
            "storage": storage_status,
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


@app.get("/storage/status")
async def storage_status():
    """Storage system status and metrics"""
    if not storage:
        return {
            "enabled": False,
            "message": "Storage system is disabled"
        }
    
    try:
        storage_info = storage.get_storage_info()
        storage_metrics = storage.get_metrics()
        
        return {
            "enabled": True,
            "timestamp": datetime.now().isoformat(),
            "info": storage_info,
            "metrics": storage_metrics,
            "config": {
                "storage_path": str(config.storage.storage_base_path),
                "json_enabled": config.storage.enable_json,
                "protobuf_enabled": config.storage.enable_protobuf,
                "postgres_enabled": config.storage.enable_postgres_index,
                "metrics_enabled": config.storage.enable_metrics
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "enabled": True,
                "error": f"Storage system error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )


@app.get("/background/status")
async def background_streaming_status():
    """Background streaming status for tracked contracts"""
    if not background_manager:
        return {
            "enabled": False,
            "message": "Background streaming is disabled"
        }
    
    try:
        status = background_manager.get_status()
        return {
            "enabled": True,
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "config": {
                "max_tracked_contracts": config.storage.max_tracked_contracts,
                "reconnect_delay": config.storage.background_stream_reconnect_delay,
                "tracked_contracts_count": len(config.storage.tracked_contracts)
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "enabled": True,
                "error": f"Background streaming error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )


@app.get("/v2/buffer/{contract_id}/info")
async def buffer_info(
    contract_id: int,
    tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types")
):
    """Get buffer information for a tracked contract"""
    
    # Parse tick types
    tick_type_list = [t.strip() for t in tick_types.split(',')]
    
    # Check if contract is tracked
    if not background_manager or not background_manager.is_contract_tracked(contract_id):
        raise HTTPException(
            status_code=404,
            detail=f"Contract {contract_id} is not tracked"
        )
    
    # Check if storage is available
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Storage system not available"
        )
    
    try:
        buffer_query = create_buffer_query(config.storage.storage_base_path)
        
        # Get buffer information
        available_duration = buffer_query.get_available_buffer_duration(contract_id, tick_type_list)
        latest_tick_time = buffer_query.get_latest_tick_time(contract_id, tick_type_list)
        buffer_stats_1h = await buffer_query.get_buffer_stats(contract_id, tick_type_list, "1h")
        
        # Get configured buffer hours from background manager
        configured_buffer_hours = background_manager.get_contract_buffer_hours(contract_id)
        
        return {
            "contract_id": contract_id,
            "tick_types": tick_type_list,
            "tracked": True,
            "available_duration": str(available_duration) if available_duration else None,
            "configured_buffer_hours": configured_buffer_hours,
            "latest_tick_time": latest_tick_time.isoformat() if latest_tick_time else None,
            "buffer_stats_1h": buffer_stats_1h,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Buffer info error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )


@app.get("/v2/buffer/{contract_id}/stats")
async def buffer_stats(
    contract_id: int,
    tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types"),
    duration: str = Query(default="1h", description="Duration to analyze")
):
    """Get detailed buffer statistics for a tracked contract"""
    
    # Parse tick types
    tick_type_list = [t.strip() for t in tick_types.split(',')]
    
    # Check if contract is tracked
    if not background_manager or not background_manager.is_contract_tracked(contract_id):
        raise HTTPException(
            status_code=404,
            detail=f"Contract {contract_id} is not tracked"
        )
    
    # Check if storage is available
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Storage system not available"
        )
    
    try:
        buffer_query = create_buffer_query(config.storage.storage_base_path)
        stats = await buffer_query.get_buffer_stats(contract_id, tick_type_list, duration)
        
        return {
            "contract_id": contract_id,
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Buffer stats error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )


@app.get("/stream/info")
async def stream_info():
    """Information about available streaming capabilities"""
    return {
        "usage": {
            "endpoint": "/stream/{contract_id}/{tick_type}",
            "description": "Stream market data for a contract with specific tick type",
            "example": "/stream/12345/BidAsk?limit=100&timeout=60",
        },
        "tick_types": {
            "Last": "Regular trades during market hours",
            "AllLast": "All trades including pre/post market",
            "BidAsk": "Real-time bid and ask quotes",
            "MidPoint": "Calculated midpoint between bid and ask",
        },
        "query_parameters": {
            "limit": "Number of ticks before auto-stop (integer, optional, max: 10000)",
            "timeout": "Stream timeout in seconds (integer, optional, range: 5-3600)",
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


# V1 SSE streaming function - commented out for now since we're implementing v2
# async def stream_contract_data(contract_id: int, tick_type: str, limit: Optional[int] = None,
#                               timeout: Optional[int] = None) -> AsyncGenerator[Any, None]:
#     """Stream contract data via SSE using StreamManager for isolation"""
#     from .stream_manager import stream_manager, StreamHandler
#     
#     if timeout is None:
#         timeout = config.default_timeout_seconds
# 
#     # Check if we're at max streams
#     current_stream_count = stream_manager.get_stream_count()
#     if current_stream_count >= config.max_concurrent_streams:
#         event = create_rate_limit_error_event(contract_id)
#         yield event
#         return
# 
#     # Generate unique request ID
#     import time
#     import random
#     req_id = int(time.time() * 1000) % 100000 + random.randint(1, 999)
#     
#     # Create event queue for this stream
#     event_queue = asyncio.Queue()
#     stream_id = f"{contract_id}_{tick_type}_{id(event_queue)}"
#     
#     logger.info("Starting stream for contract %d, type %s, limit %s, timeout %s", 
#                 contract_id, tick_type, limit, timeout)
#     logger.info("Starting stream %s for contract %d", stream_id, contract_id)
#     logger.info("Using request ID %d for stream %s", req_id, stream_id)
# 
#     try:
#         # Get TWS connection
#         app_instance = ensure_tws_connection()
#         
#         # Create callback functions for SSE events
#         async def on_tick(tick_data: Dict[str, Any]):
#             event = SSETickEvent(contract_id, tick_data)
#             try:
#                 await event_queue.put(event)
#             except Exception as e:
#                 logger.warning("Failed to queue tick event for stream %s: %s", stream_id, e)
# 
#         async def on_error(error_code: str, message: str):
#             event = SSEErrorEvent(contract_id, error_code, message)
#             try:
#                 await event_queue.put(event)
#             except Exception as e:
#                 logger.warning("Failed to queue error event for stream %s: %s", stream_id, e)
# 
#         async def on_complete(reason: str, total_ticks: int):
#             event = SSECompleteEvent(contract_id, reason, total_ticks)
#             try:
#                 await event_queue.put(event)
#             except Exception as e:
#                 logger.warning("Failed to queue complete event for stream %s: %s", stream_id, e)
# 
#         # Create StreamHandler for this stream
#         stream_handler = StreamHandler(
#             request_id=req_id,
#             contract_id=contract_id,
#             tick_type=tick_type,
#             limit=limit,
#             timeout=timeout,
#             tick_callback=on_tick,
#             error_callback=on_error,
#             complete_callback=on_complete
#         )
#         
#         # Set the request ID on the app instance BEFORE registering anything
#         app_instance.req_id = req_id
#         
#         # Register the stream with StreamManager
#         stream_manager.register_stream(stream_handler)
#         
#         # Register stream in active_streams for tracking
#         with stream_lock:
#             active_streams[stream_id] = {
#                 "contract_id": contract_id,
#                 "tick_type": tick_type,
#                 "start_time": datetime.now(),
#                 "request_id": req_id,
#                 "app": app_instance,
#                 "queue": event_queue
#             }
# 
#         # Start streaming in background
#         async def start_stream():
#             try:
#                 logger.info("Starting TWS stream for request ID %d", req_id)
# 
#                 # Start streaming - this will route through StreamManager
#                 app_instance.stream_contract(contract_id, tick_type)
# 
#                 # Send start event
#                 start_event = create_stream_started_event(contract_id, tick_type)
#                 await event_queue.put(start_event)
# 
#             except Exception as e:
#                 import traceback
#                 error_msg = f"{str(e)}\n{traceback.format_exc()}"
#                 logger.error("Detailed stream start error: %s", error_msg)
#                 error_event = SSEErrorEvent(contract_id, "STREAM_START_ERROR", str(e))
#                 await event_queue.put(error_event)
# 
#         # Start the stream
#         asyncio.create_task(start_stream())
# 
#         # Stream events with timeout
#         start_time = time.time()
#         while True:
#             try:
#                 # Check timeout only if one is set
#                 if timeout is not None and time.time() - start_time > timeout:
#                     timeout_event = create_timeout_error_event(contract_id, timeout)
#                     yield timeout_event
#                     break
# 
#                 # Get next event with timeout
#                 event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
#                 yield event
# 
#                 # Check if stream is complete
#                 if isinstance(event, SSECompleteEvent):
#                     break
# 
#             except asyncio.TimeoutError:
#                 continue
#             except Exception as e:
#                 import traceback
#                 error_msg = f"{str(e)}\n{traceback.format_exc()}"
#                 logger.error("Error in stream %s: %s", stream_id, error_msg)
#                 error_event = SSEErrorEvent(contract_id, "STREAM_ERROR", str(e))
#                 yield error_event
#                 break
# 
#     finally:
#         # Unregister from StreamManager
#         stream_manager.unregister_stream(req_id)
#         
#         # Clean up
#         with stream_lock:
#             if stream_id in active_streams:
#                 try:
#                     app_data = active_streams[stream_id]
#                     if "app" in app_data and "request_id" in app_data:
#                         app_data["app"].cancelTickByTickData(app_data["request_id"])
#                         # Clean up request-specific data
#                         app_data["app"].cleanup_request(app_data["request_id"])
#                 except Exception as e:
#                     import traceback
#                     logger.error("Error cleaning up stream %s: %s\nTraceback:\n%s", stream_id, e, traceback.format_exc())
#                 del active_streams[stream_id]
# 
#         logger.info("Stream %s ended", stream_id)


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


# V1 SSE endpoint - commented out for now since we're implementing v2 only
# @app.get("/stream/{contract_id}/{tick_type}")
# async def stream_contract_with_type(
#     contract_id: int,
#     tick_type: str,
#     limit: Optional[int] = Query(default=None, description="Number of ticks before auto-stop"),
#     timeout: Optional[int] = Query(default=None, description="Stream timeout in seconds")
# ):
#     """Stream market data for a contract with explicit tick type via Server-Sent Events"""
#     
#     # Validate tick type
#     if not is_valid_tick_type(tick_type):
#         raise HTTPException(
#             status_code=400,
#             detail=f"Invalid tick type: {tick_type}. Valid types: {', '.join(['Last', 'AllLast', 'BidAsk', 'MidPoint'])}"
#         )
#     
#     # Validate limit
#     if limit is not None and (limit < 1 or limit > 10000):
#         raise HTTPException(
#             status_code=400,
#             detail="Limit must be between 1 and 10000"
#         )
#     
#     # Validate timeout
#     if timeout is not None and (timeout < 5 or timeout > 3600):
#         raise HTTPException(
#             status_code=400,
#             detail="Timeout must be between 5 and 3600 seconds"
#         )
#     
#     logger.info("Starting stream for contract %d, type %s, limit %s, timeout %s",
#                 contract_id, tick_type, limit, timeout)
#     
#     # Create event generator
#     events = stream_contract_data(contract_id, tick_type, limit, timeout)
#     
#     # Return SSE response
#     return create_sse_response(events)




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


# V2 Protocol Endpoints

async def stream_contract_data_v2(contract_id: int, tick_types: list, limit: Optional[int] = None,
                                  timeout: Optional[int] = None) -> AsyncGenerator[SSEEvent, None]:
    """Stream contract data via SSE using v2 protocol with stream IDs"""
    from .stream_manager import stream_manager, StreamHandler
    
    if timeout is None:
        timeout = config.default_timeout_seconds

    # Check if we're at max streams
    current_stream_count = stream_manager.get_stream_count()
    if current_stream_count >= config.max_concurrent_streams:
        stream_id = ""  # Empty for connection-level errors
        event = create_v2_rate_limit_error_event(stream_id)
        yield event
        return

    # Normalize tick_types to list
    if isinstance(tick_types, str):
        tick_types = [tick_types]
    
    # Generate stream IDs for each tick type
    if len(tick_types) == 1:
        stream_id = generate_stream_id(contract_id, tick_types[0])
        stream_ids = [stream_id]
    else:
        stream_ids = []
        for tick_type in tick_types:
            stream_id = generate_stream_id(contract_id, tick_type)
            stream_ids.append(stream_id)
    
    logger.info("Starting v2 stream for contract %d, types %s, limit %s, timeout %s", 
                contract_id, tick_types, limit, timeout)
    
    # Create event queue for all streams
    event_queue = asyncio.Queue()
    handlers = []
    
    try:
        # Get TWS connection
        app_instance = ensure_tws_connection()
        
        # Create handlers for each tick type
        for tick_type, stream_id in zip(tick_types, stream_ids):
            # Generate unique request ID for IB API
            import time
            import random
            req_id = int(time.time() * 1000) % 100000 + random.randint(1, 999)
            
            # Create callback functions for v2 protocol
            async def on_tick(tick_data: Dict[str, Any], sid=stream_id, tid=tick_type, cid=contract_id):
                event = create_tick_event(sid, cid, tid, tick_data)
                try:
                    await event_queue.put(event)
                except Exception as e:
                    logger.warning("Failed to queue tick event for stream %s: %s", sid, e)

            async def on_error(error_code: str, message: str, sid=stream_id):
                event = create_error_event(sid, error_code, message)
                try:
                    await event_queue.put(event)
                except Exception as e:
                    logger.warning("Failed to queue error event for stream %s: %s", sid, e)

            async def on_complete(reason: str, total_ticks: int, sid=stream_id):
                duration = time.time() - start_time if 'start_time' in locals() else 0.0
                event = create_complete_event(sid, reason, total_ticks, duration)
                try:
                    await event_queue.put(event)
                except Exception as e:
                    logger.warning("Failed to queue complete event for stream %s: %s", sid, e)

            # Create StreamHandler for this stream
            stream_handler = StreamHandler(
                request_id=req_id,
                contract_id=contract_id,
                tick_type=tick_type,
                limit=limit,
                timeout=timeout,
                tick_callback=on_tick,
                error_callback=on_error,
                complete_callback=on_complete,
                stream_id=stream_id
            )
            
            handlers.append((stream_handler, req_id, stream_id, tick_type))
        
        # Set request ID and register all handlers
        for stream_handler, req_id, stream_id, tick_type in handlers:
            app_instance.req_id = req_id
            stream_manager.register_stream(stream_handler)
            
            # Start streaming for this tick type (convert from v2 to TWS API format)
            tws_tick_type = convert_v2_tick_type_to_tws_api(tick_type)
            app_instance.stream_contract(contract_id, tws_tick_type)
            
            # Send stream started event
            start_event = create_v2_stream_started_event(stream_id, tick_type)
            await event_queue.put(start_event)
        
        # Stream events with timeout
        start_time = time.time()
        while True:
            try:
                # Check timeout only if one is set
                if timeout is not None and time.time() - start_time > timeout:
                    for _, _, stream_id, _ in handlers:
                        timeout_event = create_v2_timeout_error_event(stream_id, timeout)
                        yield timeout_event
                    break

                # Get next event with timeout
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                yield event

                # Check if this is a completion event
                if hasattr(event, 'message') and event.message.type == "complete":
                    # Remove the completed handler
                    completed_stream_id = event.message.stream_id
                    handlers = [(h, r, s, t) for h, r, s, t in handlers if s != completed_stream_id]
                    
                    # If all handlers are complete, break
                    if not handlers:
                        break

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                import traceback
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                logger.error("Error in v2 stream: %s", error_msg)
                for _, _, stream_id, _ in handlers:
                    error_event = create_error_event(stream_id, "STREAM_ERROR", str(e))
                    yield error_event
                break

    finally:
        # Unregister all handlers from StreamManager
        for stream_handler, req_id, stream_id, tick_type in handlers:
            stream_manager.unregister_stream(req_id)
        
        logger.info("V2 streams ended for contract %d", contract_id)


@app.get("/v2/stream/{contract_id}/{tick_type}")
async def stream_contract_v2_single(
    contract_id: int,
    tick_type: str,
    limit: Optional[int] = Query(default=None, description="Number of ticks before auto-stop"),
    timeout: Optional[int] = Query(default=None, description="Stream timeout in seconds")
):
    """Stream market data for a contract with specific tick type via Server-Sent Events (v2 protocol)"""
    
    # Validate tick type (convert to v2 format)
    tick_type_map = {
        'Last': 'last',
        'AllLast': 'all_last', 
        'BidAsk': 'bid_ask',
        'MidPoint': 'mid_point'
    }
    
    if tick_type in tick_type_map:
        tick_type = tick_type_map[tick_type]
    elif tick_type not in ['last', 'all_last', 'bid_ask', 'mid_point']:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tick type: {tick_type}. Valid types: last, all_last, bid_ask, mid_point"
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
    
    logger.info("Starting v2 stream for contract %d, type %s, limit %s, timeout %s",
                contract_id, tick_type, limit, timeout)
    
    # Create event generator
    events = stream_contract_data_v2(contract_id, [tick_type], limit, timeout)
    
    # Return SSE response with v2 headers
    return SSEStreamingResponse(
        content=async_sse_generator(events),
        media_type="text/event-stream"
    )


@app.get("/v2/stream/{contract_id}/with-buffer")
async def stream_contract_with_buffer(
    contract_id: int,
    tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types"),
    buffer_duration: str = Query(default="1h", description="Buffer duration (e.g., '1h', '30m', '2h')"),
    limit: Optional[int] = Query(default=None, description="Number of ticks before auto-stop (excluding buffer)"),
    timeout: Optional[int] = Query(default=None, description="Stream timeout in seconds")
):
    """Stream market data with historical buffer for tracked contracts (v2 protocol)"""
    
    # Parse and validate tick types
    tick_type_list = [t.strip() for t in tick_types.split(',')]
    valid_tick_types = ['last', 'all_last', 'bid_ask', 'mid_point']
    
    for tick_type in tick_type_list:
        if tick_type not in valid_tick_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tick type: {tick_type}. Valid types: {', '.join(valid_tick_types)}"
            )
    
    # Remove duplicates while preserving order
    seen = set()
    tick_type_list = [t for t in tick_type_list if not (t in seen or seen.add(t))]
    
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
    
    # Check if contract is tracked
    if not background_manager or not background_manager.is_contract_tracked(contract_id):
        raise HTTPException(
            status_code=404,
            detail=f"Contract {contract_id} is not tracked. Only tracked contracts support buffer streaming."
        )
    
    logger.info("Starting v2 buffer stream for contract %d, types %s, buffer %s, limit %s, timeout %s",
                contract_id, tick_type_list, buffer_duration, limit, timeout)
    
    # Create buffer + live event generator
    events = stream_contract_with_buffer_data(contract_id, tick_type_list, buffer_duration, limit, timeout)
    
    # Return SSE response with v2 headers
    return SSEStreamingResponse(
        content=async_sse_generator(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Stream-Protocol": "v2",
            "X-Buffer-Enabled": "true",
            "X-Buffer-Duration": buffer_duration
        }
    )


async def stream_contract_with_buffer_data(
    contract_id: int, 
    tick_types: list, 
    buffer_duration: str,
    limit: Optional[int] = None,
    timeout: Optional[int] = None
) -> AsyncGenerator[SSEEvent, None]:
    """Generate events with historical buffer followed by live stream"""
    
    try:
        # Create buffer query
        if not storage:
            raise HTTPException(status_code=503, detail="Storage system not available")
        
        buffer_query = create_buffer_query(config.storage.storage_base_path)
        
        # Phase 1: Send historical buffer
        logger.info("Fetching buffer data for contract %d, duration %s", contract_id, buffer_duration)
        
        try:
            buffer_messages = await buffer_query.query_buffer(contract_id, tick_types, buffer_duration)
            buffer_count = len(buffer_messages)
            
            # Send info event about buffer
            yield create_info_event("", {
                "status": "buffer_start",
                "contract_id": contract_id,
                "tick_types": tick_types,
                "buffer_duration": buffer_duration,
                "buffer_message_count": buffer_count
            })
            
            # Send historical messages
            for i, msg in enumerate(buffer_messages):
                # Create historical tick event
                tick_event = create_tick_event("", msg)
                
                # Add buffer metadata to indicate historical data
                tick_event.data["metadata"] = tick_event.data.get("metadata", {})
                tick_event.data["metadata"]["historical"] = True
                tick_event.data["metadata"]["buffer_index"] = i
                tick_event.data["metadata"]["buffer_total"] = buffer_count
                
                yield tick_event
            
            # Send buffer complete event
            yield create_info_event("", {
                "status": "buffer_complete",
                "contract_id": contract_id,
                "buffer_message_count": buffer_count
            })
            
        except Exception as e:
            logger.error("Error fetching buffer data: %s", e)
            yield create_error_event("", "BUFFER_ERROR", f"Failed to fetch buffer data: {str(e)}")
            return
        
        # Phase 2: Switch to live streaming
        logger.info("Switching to live stream for contract %d", contract_id)
        
        yield create_info_event("", {
            "status": "live_start",
            "contract_id": contract_id,
            "tick_types": tick_types
        })
        
        # Start live stream using existing streaming logic
        async for event in stream_contract_data_v2(contract_id, tick_types, limit, timeout):
            # Add live metadata
            if hasattr(event, 'data') and isinstance(event.data, dict):
                event.data["metadata"] = event.data.get("metadata", {})
                event.data["metadata"]["historical"] = False
            
            yield event
            
    except Exception as e:
        logger.error("Error in buffer+live stream for contract %d: %s", contract_id, e)
        yield create_error_event("", "STREAM_ERROR", f"Stream error: {str(e)}")


@app.get("/v2/stream/{contract_id}")
async def stream_contract_v2_multi(
    contract_id: int,
    tick_types: str = Query(..., description="Comma-separated tick types: last,all_last,bid_ask,mid_point"),
    limit: Optional[int] = Query(default=None, description="Number of ticks before auto-stop"),
    timeout: Optional[int] = Query(default=None, description="Stream timeout in seconds")
):
    """Stream market data for a contract with multiple tick types via Server-Sent Events (v2 protocol)"""
    
    # Parse and validate tick types
    tick_type_list = [t.strip() for t in tick_types.split(',')]
    valid_tick_types = ['last', 'all_last', 'bid_ask', 'mid_point']
    
    for tick_type in tick_type_list:
        if tick_type not in valid_tick_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tick type: {tick_type}. Valid types: {', '.join(valid_tick_types)}"
            )
    
    # Remove duplicates while preserving order
    seen = set()
    tick_type_list = [t for t in tick_type_list if not (t in seen or seen.add(t))]
    
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
    
    logger.info("Starting v2 multi-stream for contract %d, types %s, limit %s, timeout %s",
                contract_id, tick_type_list, limit, timeout)
    
    # Create event generator
    events = stream_contract_data_v2(contract_id, tick_type_list, limit, timeout)
    
    # Return SSE response with v2 headers
    return SSEStreamingResponse(
        content=async_sse_generator(events),
        media_type="text/event-stream"
    )


async def async_sse_generator(events: AsyncGenerator[SSEEvent, None]) -> AsyncGenerator[str, None]:
    """Convert SSE events to formatted strings."""
    try:
        async for event in events:
            yield event.format()
    except Exception as e:
        logger.error("Error in SSE generator: %s", e)
        # Send error event with empty stream_id (connection-level error)
        error_event = create_error_event("", "STREAM_ERROR", f"Stream error: {str(e)}")
        yield error_event.format()


@app.get("/v2/info")
async def stream_info_v2():
    """Information about v2 protocol streaming capabilities"""
    return {
        "version": "2.0.0",
        "protocol": "v2",
        "usage": {
            "single_stream": "/v2/stream/{contract_id}/{tick_type}",
            "multi_stream": "/v2/stream/{contract_id}?tick_types=bid_ask,last",
            "websocket": "ws://{host}/v2/ws/stream",
            "description": "Stream market data using v2 unified protocol",
            "example": "/v2/stream/12345/bid_ask?limit=100&timeout=60",
        },
        "tick_types": {
            "last": "Regular trades during market hours",
            "all_last": "All trades including pre/post market",
            "bid_ask": "Real-time bid and ask quotes",
            "mid_point": "Calculated midpoint between bid and ask",
        },
        "query_parameters": {
            "limit": "Number of ticks before auto-stop (integer, optional, max: 10000)",
            "timeout": "Stream timeout in seconds (integer, optional, range: 5-3600)",
            "tick_types": "Comma-separated tick types for multi-stream (string, required for multi-stream)",
        },
        "message_structure": {
            "type": "Message type (tick, error, complete, info)",
            "stream_id": "Unique stream identifier",
            "timestamp": "ISO-8601 timestamp with milliseconds",
            "data": "Message-specific payload",
            "metadata": "Optional metadata object",
        },
        "stream_id_format": "{contract_id}_{tick_type}_{timestamp}_{random}",
        "limits": {
            "max_concurrent_streams": config.max_concurrent_streams,
            "default_timeout_seconds": config.default_timeout_seconds,
        },
    }


# V2 WebSocket Endpoints

@app.websocket("/v2/ws/stream")
async def websocket_stream_v2(websocket: WebSocket):
    """WebSocket endpoint for v2 protocol streaming with dynamic subscriptions."""
    try:
        await websocket.accept()
        
        # Register connection with WebSocket manager
        connection_id = await ws_manager.register_connection(websocket)
        
        try:
            while True:
                # Receive message from client
                raw_message = await websocket.receive_text()
                
                # Handle message through WebSocket manager
                await ws_manager.handle_message(connection_id, raw_message)
                
        except Exception as e:
            logger.warning("WebSocket connection %s error: %s", connection_id, e)
        finally:
            # Unregister connection
            await ws_manager.unregister_connection(connection_id)
            
    except Exception as e:
        logger.error("WebSocket connection failed: %s", e)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass


# WebSocket Endpoints

@app.websocket("/ws/stream/{contract_id}/multi")
async def websocket_multi_stream(websocket: WebSocket, contract_id: int):
    """WebSocket endpoint for multi-stream subscriptions for a contract."""
    logger.info("Multi-stream WebSocket endpoint called for contract %d", contract_id)
    await websocket_endpoint(websocket)


@app.websocket("/ws/stream/{contract_id}/{tick_type}")
async def websocket_single_stream(websocket: WebSocket, contract_id: int, tick_type: str):
    """WebSocket endpoint for streaming specific tick type data for a contract."""
    # Validate tick type
    if not is_valid_tick_type(tick_type):
        await websocket.close(code=4002, reason=f"Invalid tick type: {tick_type}")
        return
    
    await websocket_endpoint(websocket)


@app.websocket("/ws/control")
async def websocket_control(websocket: WebSocket):
    """WebSocket control endpoint for management operations."""
    await websocket_control_endpoint(websocket)


@app.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection statistics."""
    return ws_manager.get_connection_stats()


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
