"""
WebSocket client for IB-Studies to connect to IB Stream v2 WebSocket API.
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
from ib_studies.v2_utils import normalize_tick_type

logger = logging.getLogger(__name__)


class WebSocketStreamClient:
    """WebSocket client for consuming IB-Stream v2 protocol data."""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        """Initialize v2 WebSocket stream client."""
        self.config = config or StreamConfig()
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.message_id = 0
        self.pending_messages: Dict[str, asyncio.Future] = {}
        self.subscriptions: Dict[str, Callable] = {}
        self.stream_callbacks: Dict[str, Callable] = {}  # stream_id -> callback
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
        Connect to v2 WebSocket and subscribe to tick types.
        
        Args:
            contract_id: Contract ID to stream
            tick_types: List of tick types to subscribe to
        """
        try:
            # Use v2 WebSocket endpoint
            ws_url = self._get_ws_url("/v2/ws/stream")
            
            logger.info("Connecting to v2 WebSocket: %s", ws_url)
            self.ws = await websockets.connect(
                ws_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5
            )
            
            self.connected = True
            logger.info("v2 WebSocket connected successfully")
            
            # Start message handler
            self._message_handler_task = asyncio.create_task(self._message_handler())
            
            # Wait for connected message
            await asyncio.sleep(0.1)  # Give server time to send connected message
            
            # Subscribe to tick types using v2 protocol
            await self._subscribe_v2(contract_id, tick_types)
                
        except Exception as e:
            logger.error("Failed to connect to v2 WebSocket: %s", e)
            self.connected = False
            raise
    
    async def _subscribe_v2(self, contract_id: int, tick_types: List[str]) -> List[str]:
        """Subscribe to tick types using v2 protocol."""
        from datetime import datetime
        
        msg_id = f"msg-{self._get_next_message_id()}"
        
        future = asyncio.Future()
        self.pending_messages[msg_id] = future
        
        # Convert tick types to v2 format (snake_case)
        v2_tick_types = [normalize_tick_type(t) for t in tick_types]
        
        config = {}
        if self.config.timeout is not None:
            config["timeout_seconds"] = self.config.timeout
            
        message = {
            "type": "subscribe",
            "id": msg_id,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "data": {
                "contract_id": contract_id,
                "tick_types": v2_tick_types,
                "config": config
            }
        }
        
        await self.ws.send(json.dumps(message))
        logger.debug("Sent v2 subscribe message: %s", message)
        
        # Wait for subscription confirmation
        try:
            stream_ids = await asyncio.wait_for(future, timeout=10.0)
            logger.info("v2 subscribed to %s for contract %d, stream_ids: %s", 
                       v2_tick_types, contract_id, stream_ids)
            return stream_ids
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for v2 subscription confirmation")
            raise
    
    def _get_next_message_id(self) -> int:
        """Get next message ID."""
        self.message_id += 1
        return self.message_id
    
    async def consume(self, callback: Callable[[str, Dict[str, Any], str, str], None]) -> None:
        """
        Consume messages from v2 WebSocket.
        
        Args:
            callback: Function to call for each tick (tick_type, data, stream_id, timestamp)
        """
        if not self.connected:
            raise RuntimeError("Not connected to v2 WebSocket")
        
        # Store the callback for message processing
        self.main_callback = callback
        
        try:
            # Wait until stop event is set
            await self._stop_event.wait()
        except Exception as e:
            logger.error("Error in v2 consume loop: %s", e)
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
        """Process a single v2 WebSocket message."""
        message_type = data.get("type")
        logger.debug("Processing v2 message type: %s", message_type)
        
        if message_type == "connected":
            logger.info("Received v2 connected message: %s", data)
            
        elif message_type == "subscribed":
            # Handle v2 subscription confirmation
            msg_id = data.get("id")
            if msg_id and msg_id in self.pending_messages:
                future = self.pending_messages.pop(msg_id)
                streams = data["data"]["streams"]
                stream_ids = [stream["stream_id"] for stream in streams]
                future.set_result(stream_ids)
                
        elif message_type == "tick":
            # Handle v2 tick data
            await self._handle_v2_tick(data)
            
        elif message_type == "error":
            stream_id = data.get("stream_id", "")
            error_data = data.get("data", {})
            error_code = error_data.get("code", "unknown")
            logger.error("Received v2 error message (stream_id=%s): %s", stream_id, error_data)
            
            # If this is a timeout error, stop the client
            if error_code == "STREAM_TIMEOUT":
                logger.info("Received timeout error - stopping WebSocket client")
                self._stop_event.set()
            
        elif message_type == "complete":
            stream_id = data.get("stream_id", "")
            complete_data = data.get("data", {})
            reason = complete_data.get("reason", "unknown")
            total_ticks = complete_data.get("total_ticks", 0)
            logger.info("v2 Stream %s completed: %s (%d ticks)", stream_id, reason, total_ticks)
            
            # If completed due to timeout, stop the client
            if reason == "timeout":
                logger.info("Stream completed due to timeout - stopping WebSocket client")
                self._stop_event.set()
            
        elif message_type == "pong":
            logger.debug("Received v2 pong: %s", data)
            
        else:
            logger.warning("Unknown v2 message type: %s", message_type)
    
    async def _handle_v2_tick(self, message: Dict[str, Any]) -> None:
        """Handle v2 protocol tick data message."""
        stream_id = message.get("stream_id", "")
        timestamp = message.get("timestamp", "")
        tick_data = message.get("data", {})
        tick_type = tick_data.get("tick_type", "unknown")
        
        logger.debug("Received v2 tick for %s: %s", stream_id, tick_type)
        
        # Convert snake_case to expected format for backward compatibility
        tick_type_map = {
            "bid_ask": "BidAsk",
            "last": "Last",
            "all_last": "AllLast",
            "mid_point": "MidPoint"
        }
        
        mapped_type = tick_type_map.get(tick_type, tick_type)
        
        # Call main callback if available
        if hasattr(self, 'main_callback') and self.main_callback:
            try:
                if asyncio.iscoroutinefunction(self.main_callback):
                    await self.main_callback(mapped_type, tick_data, stream_id, timestamp)
                else:
                    self.main_callback(mapped_type, tick_data, stream_id, timestamp)
            except Exception as e:
                logger.error("Error in v2 main callback: %s", e)
        
        # Call stream-specific callbacks if available
        if stream_id in self.stream_callbacks:
            callback = self.stream_callbacks[stream_id]
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(mapped_type, tick_data, stream_id, timestamp)
                else:
                    callback(mapped_type, tick_data, stream_id, timestamp)
            except Exception as e:
                logger.error("Error in v2 stream callback: %s", e)
    
    def register_callback(self, request_id: str, callback: Callable) -> None:
        """Register a callback for a specific request ID."""
        self.subscriptions[request_id] = callback
    
    async def ping(self) -> None:
        """Send v2 ping to server."""
        if not self.connected:
            return
        
        from datetime import datetime
        msg_id = f"msg-{self._get_next_message_id()}"
        message = {
            "type": "ping",
            "id": msg_id,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        
        await self.ws.send(json.dumps(message))
        logger.debug("Sent v2 ping")
    
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
        
        if self.ws and self.connected:
            try:
                await self.ws.close()
            except Exception as e:
                logger.debug("Error closing WebSocket: %s", e)
        
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
    """Multi-stream v2 WebSocket client for consuming multiple data types simultaneously."""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        """Initialize v2 multi-stream WebSocket client."""
        self.config = config or StreamConfig()
        self.client = WebSocketStreamClient(config)
        self._callbacks: Dict[str, Callable] = {}
        
    async def connect_multiple(self, contract_id: int, tick_types: List[str], 
                              callback: Callable[[str, Dict, str, str], None]) -> None:
        """
        Connect to multiple v2 streams for the same contract.
        
        Args:
            contract_id: Contract ID to stream
            tick_types: List of tick types (BidAsk, Last, AllLast, MidPoint)
            callback: Async function to call for each tick (tick_type, data, stream_id, timestamp)
        """
        # Store the callback
        self._callbacks["main"] = callback
        
        # Connect to v2 WebSocket
        await self.client.connect(contract_id, tick_types)
        
        logger.info("Connected to %d v2 streams for contract %d: %s", 
                   len(tick_types), contract_id, tick_types)
    
    async def _handle_tick(self, tick_type: str, data: Dict[str, Any], stream_id: str, timestamp: str) -> None:
        """Internal v2 tick handler that routes to user callback."""
        callback = self._callbacks.get("main")
        if callback:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(tick_type, data, stream_id, timestamp)
                else:
                    callback(tick_type, data, stream_id, timestamp)
            except Exception as e:
                logger.error("Error in v2 user callback: %s", e)
    
    async def consume(self, callback: Callable[[str, Dict, str, str], None]) -> None:
        """Start consuming v2 messages."""
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