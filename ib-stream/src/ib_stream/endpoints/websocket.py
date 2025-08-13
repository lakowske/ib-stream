"""
WebSocket endpoints for the IB Stream API
"""

import logging

from fastapi import APIRouter, WebSocket

from ..config_v2 import is_valid_tick_type
from ..ws_response import websocket_endpoint, websocket_control_endpoint
from ..ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_websocket_endpoints(app):
    """Setup WebSocket endpoints"""
    
    @router.websocket("/v2/ws/stream")
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

    @router.websocket("/ws/stream/{contract_id}/multi")
    async def websocket_multi_stream(websocket: WebSocket, contract_id: int):
        """WebSocket endpoint for multi-stream subscriptions for a contract."""
        logger.info("Multi-stream WebSocket endpoint called for contract %d", contract_id)
        await websocket_endpoint(websocket)

    @router.websocket("/ws/stream/{contract_id}/{tick_type}")
    async def websocket_single_stream(websocket: WebSocket, contract_id: int, tick_type: str):
        """WebSocket endpoint for streaming specific tick type data for a contract."""
        # Validate tick type
        if not is_valid_tick_type(tick_type):
            await websocket.close(code=4002, reason=f"Invalid tick type: {tick_type}")
            return
        
        await websocket_endpoint(websocket)

    @router.websocket("/ws/control")
    async def websocket_control(websocket: WebSocket):
        """WebSocket control endpoint for management operations."""
        await websocket_control_endpoint(websocket)

    @router.get("/ws/stats")
    async def websocket_stats():
        """Get WebSocket connection statistics."""
        return ws_manager.get_connection_stats()
    
    app.include_router(router)