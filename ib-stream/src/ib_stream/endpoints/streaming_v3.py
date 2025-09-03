"""
V3 Streaming Endpoints - Service Composition Architecture

Migrated streaming endpoints that use ServiceRegistry instead of global state.
This eliminates global state dependencies and uses clean service communication.
"""

import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from ..storage import create_buffer_query
from ..sse_response import SSEEvent, SSEStreamingResponse, create_error_event
from ..streaming_core import stream_contract_data_v2, stream_contract_with_buffer_data
from ..services.event_bus import EventType

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_streaming_endpoints_v3(app):
    """Setup v3 streaming endpoints using Service Composition Architecture"""
    
    @router.get("/v3/stream/{contract_id}/buffer")
    async def stream_contract_with_buffer_v3(
        request: Request,
        contract_id: int,
        tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types"),
        buffer_duration: str = Query(default="1h", description="Buffer duration (e.g., '1h', '30m', '2h')"),
        limit: Optional[int] = Query(default=None, description="Number of ticks before auto-stop (excluding buffer)"),
        timeout: Optional[int] = Query(default=None, description="Stream timeout in seconds")
    ):
        """
        Stream market data with historical buffer using Service Composition Architecture
        
        This endpoint demonstrates the benefits of ServiceRegistry vs global state:
        - Clean service discovery through ServiceRegistry
        - No global state dependencies
        - Proper service lifecycle management
        """
        
        # Get services from ServiceRegistry (no global state!)
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        
        # Get IB service for streaming
        ib_service = orchestrator.get_ib_service()
        if not ib_service or not ib_service.is_connection_healthy():
            raise HTTPException(status_code=503, detail="IB Service not available")
        
        # Get storage service for buffer data
        storage_service = orchestrator.get_storage_service() 
        if not storage_service or not storage_service.config.storage.enable_storage:
            raise HTTPException(status_code=503, detail="Storage service not available")
        
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
        if timeout is not None and (timeout < 1 or timeout > 3600):
            raise HTTPException(
                status_code=400,
                detail="Timeout must be between 1 and 3600 seconds"
            )
        
        # Check if contract has stored data using service
        config = orchestrator.config
        buffer_query = create_buffer_query(config.storage.storage_base_path)
        if not buffer_query.is_contract_tracked(contract_id):
            raise HTTPException(
                status_code=404,
                detail=f"Contract {contract_id} has no stored data. Only contracts with stored data support buffer streaming."
            )
        
        # Get StreamingApp from IB service (no global state!)
        streaming_app = ib_service.get_streaming_app()
        if not streaming_app:
            raise HTTPException(status_code=503, detail="IB connection not available")
        
        logger.info("Starting v3 buffer stream for contract %d, types %s, buffer %s, limit %s, timeout %s",
                    contract_id, tick_type_list, buffer_duration, limit, timeout)
        
        # Publish streaming event for monitoring
        event_bus = orchestrator.event_bus
        event_bus.publish_simple(
            EventType.IB_STREAM_STARTED,
            "streaming_endpoint",
            {
                "contract_id": contract_id,
                "tick_types": tick_type_list,
                "buffer_duration": buffer_duration,
                "endpoint": "v3/stream/buffer",
                "client_ip": request.client.host if request.client else "unknown"
            }
        )
        
        # Helper function to ensure streaming connection (Service Composition pattern)
        def ensure_streaming_connection():
            if not ib_service.is_connection_healthy():
                raise HTTPException(status_code=503, detail="IB connection lost")
            return streaming_app
        
        # Create buffer + live event generator using services
        events = stream_contract_with_buffer_data_v3(
            contract_id, tick_type_list, buffer_duration, limit, timeout,
            config, storage_service.storage, ensure_streaming_connection, event_bus
        )
        
        return SSEStreamingResponse(events, media_type="text/plain")
    
    @router.get("/v3/stream/{contract_id}/live/{tick_type}")
    async def stream_live_data_v3(
        request: Request,
        contract_id: int,
        tick_type: str,
        limit: Optional[int] = Query(default=None, description="Number of ticks before auto-stop"),
        timeout: Optional[int] = Query(default=None, description="Stream timeout in seconds")
    ):
        """
        Stream live market data using Service Composition Architecture
        
        Benefits of ServiceRegistry pattern:
        - No global state dependencies
        - Clean service discovery
        - Proper error handling through service status
        """
        
        # Get services from ServiceRegistry
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        ib_service = orchestrator.get_ib_service()
        
        if not ib_service or not ib_service.is_connection_healthy():
            raise HTTPException(status_code=503, detail="IB Service not available")
        
        # Validate tick type
        valid_tick_types = ['last', 'all_last', 'bid_ask', 'mid_point']
        if tick_type not in valid_tick_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tick type: {tick_type}. Valid types: {', '.join(valid_tick_types)}"
            )
        
        # Validate parameters
        if limit is not None and (limit < 1 or limit > 10000):
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 10000")
        
        if timeout is not None and (timeout < 1 or timeout > 3600):
            raise HTTPException(status_code=400, detail="Timeout must be between 1 and 3600 seconds")
        
        # Get StreamingApp from service
        streaming_app = ib_service.get_streaming_app()
        if not streaming_app:
            raise HTTPException(status_code=503, detail="IB connection not available")
        
        logger.info("Starting v3 live stream for contract %d, type %s, limit %s, timeout %s",
                    contract_id, tick_type, limit, timeout)
        
        # Publish streaming event for monitoring
        event_bus = orchestrator.event_bus
        event_bus.publish_simple(
            EventType.IB_STREAM_STARTED,
            "streaming_endpoint",
            {
                "contract_id": contract_id,
                "tick_type": tick_type,
                "endpoint": "v3/stream/live",
                "client_ip": request.client.host if request.client else "unknown"
            }
        )
        
        # Helper function for service-based connection management
        def ensure_streaming_connection():
            if not ib_service.is_connection_healthy():
                raise HTTPException(status_code=503, detail="IB connection lost")
            return streaming_app
        
        # Create live event generator using services
        events = stream_contract_data_v3(
            contract_id, [tick_type], limit, timeout,
            orchestrator.config, ensure_streaming_connection, event_bus
        )
        
        return SSEStreamingResponse(events, media_type="text/plain")
    
    @router.get("/v3/stream/info")
    async def stream_info_v3(request: Request):
        """Stream API information using Service Composition Architecture"""
        
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        ib_service = orchestrator.get_ib_service()
        storage_service = orchestrator.get_storage_service()
        
        # Get service status
        ib_status = ib_service.get_ib_status() if ib_service else None
        storage_status = storage_service.get_storage_status() if storage_service else None
        
        return {
            "service": "ib-stream",
            "architecture": "service_composition_v3",
            "streaming": {
                "available": ib_service.is_connection_healthy() if ib_service else False,
                "connection_status": ib_status.__dict__ if ib_status else None
            },
            "storage": {
                "enabled": storage_status.storage_enabled if storage_status else False,
                "v3_json": storage_status.v3_json_enabled if storage_status else False,
                "v3_protobuf": storage_status.v3_protobuf_enabled if storage_status else False
            },
            "endpoints": {
                "/v3/stream/{contract_id}/buffer": "Buffer + live streaming with Service Composition",
                "/v3/stream/{contract_id}/live/{tick_type}": "Live streaming with Service Composition",
                "/v3/stream/info": "Stream information with service status"
            },
            "benefits": [
                "No global state dependencies",
                "Clean service discovery through ServiceRegistry",
                "Event-driven monitoring and metrics",
                "Proper service lifecycle management"
            ]
        }
    
    # Register router with app
    app.include_router(router, prefix="", tags=["streaming_v3"])


async def stream_contract_with_buffer_data_v3(
    contract_id: int, tick_types: list, buffer_duration: str, limit: Optional[int], 
    timeout: Optional[int], config, storage, ensure_connection_func, event_bus
) -> AsyncGenerator[SSEEvent, None]:
    """
    Service Composition version of buffer streaming with event monitoring
    
    This demonstrates how the new architecture eliminates global state dependencies
    while adding comprehensive monitoring through the EventBus.
    """
    try:
        # Use the existing buffer streaming logic but with service integration
        async for event in stream_contract_with_buffer_data(
            contract_id, tick_types, buffer_duration, limit, timeout,
            config, storage, ensure_connection_func
        ):
            # Publish data event for monitoring
            if event.event_type == "data":
                event_bus.publish_simple(
                    EventType.IB_DATA_RECEIVED,
                    "streaming_endpoint",
                    {
                        "contract_id": contract_id,
                        "tick_types": tick_types,
                        "data_size": len(event.data) if event.data else 0
                    }
                )
            
            yield event
            
    except Exception as e:
        logger.error(f"Error in v3 buffer streaming for contract {contract_id}: {e}")
        
        # Publish error event for monitoring
        event_bus.publish_simple(
            EventType.SERVICE_ERROR,
            "streaming_endpoint",
            {
                "contract_id": contract_id,
                "error": str(e),
                "endpoint": "v3/stream/buffer"
            }
        )
        
        yield create_error_event(f"Streaming error: {e}")


async def stream_contract_data_v3(
    contract_id: int, tick_types: list, limit: Optional[int], timeout: Optional[int],
    config, ensure_connection_func, event_bus
) -> AsyncGenerator[SSEEvent, None]:
    """
    Service Composition version of live streaming with event monitoring
    """
    try:
        # Use existing streaming logic with service integration
        async for event in stream_contract_data_v2(
            contract_id, tick_types, limit, timeout, config, ensure_connection_func
        ):
            # Publish data event for monitoring  
            if event.event_type == "data":
                event_bus.publish_simple(
                    EventType.IB_DATA_RECEIVED,
                    "streaming_endpoint", 
                    {
                        "contract_id": contract_id,
                        "tick_types": tick_types,
                        "data_size": len(event.data) if event.data else 0
                    }
                )
            
            yield event
            
    except Exception as e:
        logger.error(f"Error in v3 live streaming for contract {contract_id}: {e}")
        
        # Publish error event for monitoring
        event_bus.publish_simple(
            EventType.SERVICE_ERROR,
            "streaming_endpoint",
            {
                "contract_id": contract_id,
                "error": str(e),
                "endpoint": "v3/stream/live"
            }
        )
        
        yield create_error_event(f"Streaming error: {e}")