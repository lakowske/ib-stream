"""
Health and status endpoints for the IB Stream API
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..storage import MultiStorage

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_health_endpoints(app, config):
    """Setup health and status endpoints with dependencies"""
    
    @router.get("/health")
    async def health_check():
        """Health check endpoint"""
        from ..app_lifecycle import get_app_state
        
        try:
            app_state = get_app_state()
            storage = app_state['storage']
            background_manager = app_state['background_manager']
            tws_app = app_state['tws_app']
            active_streams = app_state['active_streams']
            stream_lock = app_state['stream_lock']
            
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

    @router.get("/storage/status")
    async def storage_status():
        """Storage system status and metrics"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        storage = app_state['storage']
        
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

    @router.get("/background/status")
    async def background_streaming_status():
        """Background streaming status for tracked contracts"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        background_manager = app_state['background_manager']
        
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
    
    app.include_router(router)