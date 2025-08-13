"""
Core streaming logic for the IB Stream API
Contains the main streaming generator functions
"""

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import HTTPException

from .config_v2 import convert_v2_tick_type_to_tws_api
from .storage import create_buffer_query
from .sse_response import (
    SSEEvent,
    create_tick_event,
    create_error_event,
    create_complete_event,
    create_info_event,
    create_stream_started_event as create_v2_stream_started_event,
    create_rate_limit_error_event as create_v2_rate_limit_error_event,
    create_timeout_error_event as create_v2_timeout_error_event,
)
from .stream_id import generate_stream_id
from .stream_manager import stream_manager, StreamHandler

logger = logging.getLogger(__name__)


async def stream_contract_data_v2(
    contract_id: int, 
    tick_types: list, 
    limit: Optional[int] = None,
    timeout: Optional[int] = None,
    config=None,
    ensure_tws_connection=None
) -> AsyncGenerator[SSEEvent, None]:
    """Stream contract data via SSE using v2 protocol with stream IDs"""
    
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


async def stream_contract_with_buffer_data(
    contract_id: int, 
    tick_types: list, 
    buffer_duration: str,
    limit: Optional[int] = None,
    timeout: Optional[int] = None,
    config=None,
    storage=None,
    ensure_tws_connection=None
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
                # Extract the needed fields from the stored message
                stream_id = msg.get("stream_id", "")
                contract_id_from_msg = int(msg.get("metadata", {}).get("contract_id", contract_id))
                tick_type_from_msg = msg.get("metadata", {}).get("tick_type", "unknown")
                tick_data = msg.get("data", {})
                
                tick_event = create_tick_event(stream_id, contract_id_from_msg, tick_type_from_msg, tick_data)
                
                # Add buffer metadata to indicate historical data
                if hasattr(tick_event.message, "data"):
                    if "metadata" not in tick_event.message.data:
                        tick_event.message.data["metadata"] = {}
                    tick_event.message.data["metadata"]["historical"] = True
                    tick_event.message.data["metadata"]["buffer_index"] = i
                    tick_event.message.data["metadata"]["buffer_total"] = buffer_count
                
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
        async for event in stream_contract_data_v2(
            contract_id, tick_types, limit, timeout, config, ensure_tws_connection
        ):
            # Add live metadata
            if hasattr(event, 'data') and isinstance(event.data, dict):
                event.data["metadata"] = event.data.get("metadata", {})
                event.data["metadata"]["historical"] = False
            
            yield event
            
    except Exception as e:
        logger.error("Error in buffer+live stream for contract %d: %s", contract_id, e)
        yield create_error_event("", "STREAM_ERROR", f"Stream error: {str(e)}")