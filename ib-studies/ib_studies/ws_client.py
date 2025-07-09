"""
WebSocket client for IB-Studies to connect to IB Stream WebSocket API.
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urljoin

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from ib_studies.models import StreamConfig

logger = logging.getLogger(__name__)


class WebSocketStreamClient:
    """WebSocket client for consuming IB-Stream data."""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        """Initialize WebSocket stream client."""
        self.config = config or StreamConfig()
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.message_id = 0
        self.pending_messages: Dict[str, asyncio.Future] = {}
        self.subscriptions: Dict[str, Callable] = {}
        self.connected = False
        self._stop_event = asyncio.Event()
        self._message_handler_task: Optional[asyncio.Task] = None
        
    def _get_ws_url(self, path: str = "") -> str:
        """Convert HTTP URL to WebSocket URL."""
        base_url = self.config.base_url
        if base_url.startswith("http://"):
            ws_url = base_url.replace("http://", "ws://")
        elif base_url.startswith("https://"):
            ws_url = base_url.replace("https://", "wss://")
        else:
            ws_url = base_url
        
        return urljoin(ws_url, path)
    
    async def connect(self, contract_id: int, tick_types: List[str]) -> None:
        """
        Connect to WebSocket and subscribe to tick types.
        
        Args:
            contract_id: Contract ID to stream
            tick_types: List of tick types to subscribe to
        """
        try:
            # Use multi endpoint for multiple streams
            ws_url = self._get_ws_url(f"/ws/stream/{contract_id}/multi")
            
            logger.info("Connecting to WebSocket: %s", ws_url)
            self.ws = await websockets.connect(
                ws_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5
            )
            
            self.connected = True
            logger.info("WebSocket connected successfully")
            
            # Start message handler
            self._message_handler_task = asyncio.create_task(self._message_handler())
            
            # Wait for connected message
            await asyncio.sleep(0.1)  # Give server time to send connected message
            
            # Subscribe to tick types
            if len(tick_types) == 1:
                # Use single subscribe for single tick type
                await self._subscribe_single(contract_id, tick_types[0])
            else:
                # Use multi-subscribe for multiple tick types
                await self._subscribe_multi(contract_id, tick_types)
                
        except Exception as e:
            logger.error("Failed to connect to WebSocket: %s", e)
            self.connected = False
            raise
    
    async def _subscribe_single(self, contract_id: int, tick_type: str) -> str:
        """Subscribe to a single tick type."""
        msg_id = f"msg-{self._get_next_message_id()}"
        
        future = asyncio.Future()
        self.pending_messages[msg_id] = future
        
        params = {}
        if self.config.timeout is not None:
            params["timeout"] = self.config.timeout
            
        message = {
            "type": "subscribe",
            "id": msg_id,
            "data": {
                "contract_id": contract_id,
                "tick_type": tick_type,
                "params": params
            }
        }
        
        await self.ws.send(json.dumps(message))
        logger.debug("Sent subscribe message: %s", message)
        
        # Wait for subscription confirmation
        try:
            request_id = await asyncio.wait_for(future, timeout=10.0)
            logger.info("Subscribed to %s for contract %d, request_id: %s", 
                       tick_type, contract_id, request_id)
            return request_id
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for subscription confirmation")
            raise
    
    async def _subscribe_multi(self, contract_id: int, tick_types: List[str]) -> List[str]:
        """Subscribe to multiple tick types."""
        msg_id = f"msg-{self._get_next_message_id()}"
        
        future = asyncio.Future()
        self.pending_messages[msg_id] = future
        
        params = {}
        if self.config.timeout is not None:
            params["timeout"] = self.config.timeout
            
        message = {
            "type": "multi_subscribe",
            "id": msg_id,
            "data": {
                "contract_id": contract_id,
                "tick_types": tick_types,
                "params": params
            }
        }
        
        await self.ws.send(json.dumps(message))
        logger.debug("Sent multi-subscribe message: %s", message)
        
        # Wait for subscription confirmation
        try:
            result = await asyncio.wait_for(future, timeout=10.0)
            logger.info("Multi-subscribed to %s for contract %d", tick_types, contract_id)
            return result
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for multi-subscription confirmation")
            raise
    
    def _get_next_message_id(self) -> int:
        """Get next message ID."""
        self.message_id += 1
        return self.message_id
    
    async def consume(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Consume messages from WebSocket.
        
        Args:
            callback: Function to call for each tick (tick_type, data)
        """
        if not self.connected:
            raise RuntimeError("Not connected to WebSocket")
        
        try:
            # Wait until stop event is set
            await self._stop_event.wait()
        except Exception as e:
            logger.error("Error in consume loop: %s", e)
            raise
    
    async def _message_handler(self) -> None:
        """Handle incoming WebSocket messages."""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    await self._process_message(data)
                except json.JSONDecodeError as e:
                    logger.error("Failed to parse message as JSON: %s", e)
                except Exception as e:
                    logger.error("Error processing message: %s", e)
                    
                # Check if we should stop
                if self._stop_event.is_set():
                    break
                    
        except ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error("Error in message handler: %s", e)
        finally:
            self.connected = False
    
    async def _process_message(self, data: Dict[str, Any]) -> None:
        """Process a single WebSocket message."""
        message_type = data.get("type")
        logger.debug("Processing message type: %s", message_type)
        
        if message_type == "connected":
            logger.info("Received connected message: %s", data)
            
        elif message_type == "subscribed":
            # Handle single subscription confirmation
            msg_id = data.get("id")
            if msg_id and msg_id in self.pending_messages:
                future = self.pending_messages.pop(msg_id)
                request_id = data["data"]["request_id"]
                future.set_result(request_id)
                
        elif message_type == "multi_subscribed":
            # Handle multi-subscription confirmation
            msg_id = data.get("id")
            if msg_id and msg_id in self.pending_messages:
                future = self.pending_messages.pop(msg_id)
                subscriptions = data["data"]["subscriptions"]
                request_ids = [sub["request_id"] for sub in subscriptions]
                future.set_result(request_ids)
                
        elif message_type == "tick":
            # Handle tick data
            await self._handle_tick(data)
            
        elif message_type == "error":
            logger.error("Received error message: %s", data.get("error", {}))
            
        elif message_type == "complete":
            request_id = data.get("request_id")
            reason = data.get("data", {}).get("reason", "unknown")
            total_ticks = data.get("data", {}).get("total_ticks", 0)
            logger.info("Stream %s completed: %s (%d ticks)", request_id, reason, total_ticks)
            
        elif message_type == "pong":
            logger.debug("Received pong: %s", data)
            
        else:
            logger.warning("Unknown message type: %s", message_type)
    
    async def _handle_tick(self, data: Dict[str, Any]) -> None:
        """Handle tick data message."""
        request_id = data.get("request_id")
        tick_data = data.get("data", {})
        tick_type = tick_data.get("type", "unknown")
        
        logger.debug("Received tick for %s: %s", request_id, tick_type)
        
        # Call registered callbacks
        for callback in self.subscriptions.values():
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(tick_type, tick_data)
                else:
                    callback(tick_type, tick_data)
            except Exception as e:
                logger.error("Error in tick callback: %s", e)
    
    def register_callback(self, request_id: str, callback: Callable) -> None:
        """Register a callback for a specific request ID."""
        self.subscriptions[request_id] = callback
    
    async def ping(self) -> None:
        """Send ping to server."""
        if not self.connected:
            return
        
        msg_id = f"msg-{self._get_next_message_id()}"
        message = {
            "type": "ping",
            "id": msg_id,
            "timestamp": time.time()
        }
        
        await self.ws.send(json.dumps(message))
        logger.debug("Sent ping")
    
    async def stop(self) -> None:
        """Stop the WebSocket client."""
        logger.info("Stopping WebSocket client")
        self._stop_event.set()
    
    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        if self._message_handler_task and not self._message_handler_task.done():
            self._message_handler_task.cancel()
            try:
                await self._message_handler_task
            except asyncio.CancelledError:
                pass
        
        if self.ws and not self.ws.closed:
            await self.ws.close()
        
        self.connected = False
        self.pending_messages.clear()
        self.subscriptions.clear()
        
        logger.info("WebSocket disconnected")
    
    async def check_health(self) -> Dict[str, Any]:
        """Check server health via HTTP."""
        # Fall back to HTTP for health check
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = self.config.base_url.replace("ws://", "http://").replace("wss://", "https://")
                response = await client.get(f"{url}/health")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return {"status": "unhealthy", "error": str(e)}
    
    async def get_stream_info(self) -> Dict[str, Any]:
        """Get server stream info via HTTP."""
        # Fall back to HTTP for stream info
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = self.config.base_url.replace("ws://", "http://").replace("wss://", "https://")
                response = await client.get(f"{url}/stream/info")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Stream info request failed: %s", e)
            return {"error": str(e)}


class WebSocketMultiStreamClient:
    """Multi-stream WebSocket client for consuming multiple data types simultaneously."""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        """Initialize multi-stream WebSocket client."""
        self.config = config or StreamConfig()
        self.client = WebSocketStreamClient(config)
        self._callbacks: Dict[str, Callable] = {}
        
    async def connect_multiple(self, contract_id: int, tick_types: List[str], 
                              callback: Callable[[str, Dict], None]) -> None:
        """
        Connect to multiple streams for the same contract.
        
        Args:
            contract_id: Contract ID to stream
            tick_types: List of tick types (BidAsk, Last, AllLast, MidPoint)
            callback: Async function to call for each tick (tick_type, data)
        """
        # Store the callback
        self._callbacks["main"] = callback
        
        # Register callback with client
        self.client.register_callback("main", self._handle_tick)
        
        # Connect to WebSocket
        await self.client.connect(contract_id, tick_types)
        
        logger.info("Connected to %d streams for contract %d: %s", 
                   len(tick_types), contract_id, tick_types)
    
    async def _handle_tick(self, tick_type: str, data: Dict[str, Any]) -> None:
        """Internal tick handler that routes to user callback."""
        callback = self._callbacks.get("main")
        if callback:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(tick_type, data)
                else:
                    callback(tick_type, data)
            except Exception as e:
                logger.error("Error in user callback: %s", e)
    
    async def consume(self, callback: Callable[[str, Dict], None]) -> None:
        """Start consuming messages."""
        await self.client.consume(callback)
    
    async def stop(self) -> None:
        """Stop all streams."""
        await self.client.stop()
    
    async def disconnect_all(self) -> None:
        """Disconnect from all streams."""
        await self.client.disconnect()
        self._callbacks.clear()
    
    async def check_health(self) -> Dict[str, Any]:
        """Check server health."""
        return await self.client.check_health()
    
    async def get_stream_info(self) -> Dict[str, Any]:
        """Get server stream info."""
        return await self.client.get_stream_info()