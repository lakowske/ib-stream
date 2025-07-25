"""
V2 streaming endpoints for the IB Stream API
"""

import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query

from ..storage import create_buffer_query
from ..sse_response import SSEEvent, SSEStreamingResponse, create_error_event
from ..streaming_core import stream_contract_data_v2, stream_contract_with_buffer_data

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_streaming_endpoints(app, config):
    """Setup v2 streaming endpoints with dependencies"""
    
    @router.get("/v2/stream/{contract_id}/buffer")
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
        
        # Check if contract has stored data
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        storage = app_state['storage']
        ensure_tws_connection = app_state['ensure_tws_connection']
        
        if not storage:
            raise HTTPException(
                status_code=503,
                detail="Storage system not available"
            )
        
        buffer_query = create_buffer_query(config.storage.storage_base_path)
        if not buffer_query.is_contract_tracked(contract_id):
            raise HTTPException(
                status_code=404,
                detail=f"Contract {contract_id} has no stored data. Only contracts with stored data support buffer streaming."
            )
        
        logger.info("Starting v2 buffer stream for contract %d, types %s, buffer %s, limit %s, timeout %s",
                    contract_id, tick_type_list, buffer_duration, limit, timeout)
        
        # Create buffer + live event generator
        events = stream_contract_with_buffer_data(
            contract_id, tick_type_list, buffer_duration, limit, timeout,
            config, storage, ensure_tws_connection
        )
        
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

    @router.get("/v2/stream/{contract_id}/live/{tick_type}")
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
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        ensure_tws_connection = app_state['ensure_tws_connection']
        
        events = stream_contract_data_v2(
            contract_id, [tick_type], limit, timeout, config, ensure_tws_connection
        )
        
        # Return SSE response with v2 headers
        return SSEStreamingResponse(
            content=async_sse_generator(events),
            media_type="text/event-stream"
        )

    @router.get("/v2/stream/{contract_id}/live")
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
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        ensure_tws_connection = app_state['ensure_tws_connection']
        
        events = stream_contract_data_v2(
            contract_id, tick_type_list, limit, timeout, config, ensure_tws_connection
        )
        
        # Return SSE response with v2 headers
        return SSEStreamingResponse(
            content=async_sse_generator(events),
            media_type="text/event-stream"
        )

    @router.get("/v2/info")
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
    
    app.include_router(router)


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