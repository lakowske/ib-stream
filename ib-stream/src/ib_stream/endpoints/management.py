"""
Stream management endpoints for the IB Stream API
"""

import logging
import threading
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_management_endpoints(app, config):
    """Setup stream management endpoints with dependencies"""
    
    @router.get("/stream/info")
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

    @router.get("/stream/active")
    async def get_active_streams():
        """Get list of currently active streams"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        active_streams = app_state['active_streams']
        stream_lock = app_state['stream_lock']
        
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

    @router.delete("/stream/all")
    async def stop_all_streams():
        """Stop all active streams"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        active_streams = app_state['active_streams']
        stream_lock = app_state['stream_lock']
        
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

    @router.delete("/stream/{contract_id}")
    async def stop_contract_streams(contract_id: int):
        """Stop all active streams for a specific contract"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        active_streams = app_state['active_streams']
        stream_lock = app_state['stream_lock']
        
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
    
    app.include_router(router)