"""
WebSocket response handler for IB Stream API.
Handles WebSocket message formatting and connection management.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

from .ws_manager import ws_manager
from .ws_schemas import ErrorMessage, WSCloseCode

logger = logging.getLogger(__name__)


class WebSocketHandler:
    """Handler for individual WebSocket connections."""
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.connection_id: Optional[str] = None
        
    async def handle_connection(self):
        """Handle the complete lifecycle of a WebSocket connection."""
        try:
            # Accept the WebSocket connection
            await self.websocket.accept()
            
            # Register with WebSocket manager
            try:
                self.connection_id = await ws_manager.register_connection(self.websocket)
            except ValueError as e:
                if "Rate limit exceeded" in str(e):
                    await self.websocket.close(code=WSCloseCode.RATE_LIMIT_EXCEEDED, 
                                            reason="Too many connections from this IP")
                    return
                else:
                    raise
            
            logger.info("WebSocket connection established: %s", self.connection_id)
            
            # Handle messages
            await self._message_loop()
            
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected: %s", self.connection_id)
        except Exception as e:
            logger.error("WebSocket connection error: %s", e, exc_info=True)
            try:
                error_msg = ErrorMessage(None, "INTERNAL_ERROR", "Connection error")
                await self.websocket.send_text(error_msg.to_json())
                await self.websocket.close(code=WSCloseCode.INTERNAL_ERROR)
            except:
                pass  # Connection might already be closed
        finally:
            # Cleanup
            if self.connection_id:
                await ws_manager.unregister_connection(self.connection_id)
    
    async def _message_loop(self):
        """Main message handling loop."""
        while True:
            try:
                # Receive message from client
                raw_message = await self.websocket.receive_text()
                
                # Handle the message
                await ws_manager.handle_message(self.connection_id, raw_message)
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("Error in message loop for %s: %s", self.connection_id, e)
                break


async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint handler."""
    handler = WebSocketHandler(websocket)
    await handler.handle_connection()


async def websocket_control_endpoint(websocket: WebSocket):
    """WebSocket control endpoint for management operations."""
    try:
        await websocket.accept()
        
        # Send initial status
        stats = ws_manager.get_connection_stats()
        await websocket.send_json({
            "type": "status",
            "data": stats
        })
        
        # Simple echo for control messages
        while True:
            try:
                message = await websocket.receive_json()
                
                if message.get("type") == "get_stats":
                    stats = ws_manager.get_connection_stats()
                    await websocket.send_json({
                        "type": "stats",
                        "data": stats
                    })
                elif message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": message.get("timestamp")
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown control message type: {message.get('type')}"
                    })
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("Error in control endpoint: %s", e)
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error: {str(e)}"
                })
                break
                
    except Exception as e:
        logger.error("Control WebSocket error: %s", e)
    finally:
        try:
            await websocket.close()
        except:
            pass


class WebSocketMiddleware:
    """Middleware for WebSocket connection handling."""
    
    def __init__(self):
        self.connection_count = 0
        self.max_connections = 100
    
    async def __call__(self, websocket: WebSocket, call_next):
        """Process WebSocket connection with middleware."""
        # Check connection limits
        if self.connection_count >= self.max_connections:
            await websocket.close(code=WSCloseCode.POLICY_VIOLATION, 
                                reason="Maximum connections exceeded")
            return
        
        # Track connection
        self.connection_count += 1
        
        try:
            # Process the connection
            await call_next(websocket)
        finally:
            # Cleanup
            self.connection_count -= 1


# Global middleware instance
ws_middleware = WebSocketMiddleware()