"""
Buffer and storage query endpoints for the IB Stream API
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ..storage import create_buffer_query

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_buffer_endpoints(app, config):
    """Setup buffer and storage query endpoints with dependencies"""
    
    @router.get("/v2/buffer/{contract_id}/info")
    async def buffer_info(
        contract_id: int,
        tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types")
    ):
        """Get buffer information for a contract with stored data"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        storage = app_state['storage']
        background_manager = app_state['background_manager']
        
        # Parse tick types
        tick_type_list = [t.strip() for t in tick_types.split(',')]
        
        # Check if storage is available
        if not storage:
            raise HTTPException(
                status_code=503,
                detail="Storage system not available"
            )
        
        try:
            buffer_query = create_buffer_query(config.storage.storage_base_path)
            
            # Check if contract has stored data
            if not buffer_query.is_contract_tracked(contract_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Contract {contract_id} has no stored data"
                )
            
            # Get buffer information
            available_duration = buffer_query.get_available_buffer_duration(contract_id, tick_type_list)
            latest_tick_time = buffer_query.get_latest_tick_time(contract_id, tick_type_list)
            buffer_stats_1h = await buffer_query.get_buffer_stats(contract_id, tick_type_list, "1h")
            
            # Get configured buffer hours from background manager (if available)
            configured_buffer_hours = None
            if background_manager and background_manager.is_contract_tracked(contract_id):
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

    @router.get("/v2/buffer/{contract_id}/stats")
    async def buffer_stats(
        contract_id: int,
        tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types"),
        duration: str = Query(default="1h", description="Duration to analyze"),
        storage_type: str = Query(default="json", description="Storage type: json, protobuf, or both")
    ):
        """Get detailed buffer statistics for a contract with stored data"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        storage = app_state['storage']
        
        # Parse tick types
        tick_type_list = [t.strip() for t in tick_types.split(',')]
        
        # Check if storage is available
        if not storage:
            raise HTTPException(
                status_code=503,
                detail="Storage system not available"
            )
        
        try:
            buffer_query = create_buffer_query(config.storage.storage_base_path)
            
            # Check if contract has stored data
            if not buffer_query.is_contract_tracked(contract_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Contract {contract_id} has no stored data"
                )
            
            stats = await buffer_query.get_buffer_stats(contract_id, tick_type_list, duration, storage_type)
            
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
    
    app.include_router(router)