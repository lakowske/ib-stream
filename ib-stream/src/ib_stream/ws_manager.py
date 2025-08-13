"""
WebSocket connection manager for IB Stream API v2 protocol.
Handles WebSocket connections, message routing, and integration with StreamManager.
"""

import asyncio
import json
import logging
import random
import time
from typing import Any, Dict, List, Optional, Set
from datetime import datetime
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect
from jsonschema import ValidationError

from .config_v2 import create_config
from .stream_manager import stream_manager, StreamHandler
from .stream_id import generate_stream_id, generate_multi_stream_id, extract_contract_id, extract_tick_type
from .ws_schemas import (
    parse_client_message, validate_client_message,
    create_subscribed_message, create_connected_message, create_pong_message,
    create_tick_message, create_error_message, create_complete_message,
    create_invalid_message_error, create_contract_not_found_error,
    create_rate_limit_error, create_connection_error, create_internal_error,
    WSCloseCode, get_close_code_for_error
)

logger = logging.getLogger(__name__)
config = create_config()


class WebSocketConnection:
    """Represents a single WebSocket connection with its streams."""
    
    def __init__(self, websocket: WebSocket, connection_id: str):
        self.websocket = websocket
        self.connection_id = connection_id
        self.streams: Dict[str, Dict[str, Any]] = {}  # stream_id -> stream info
        self.message_count = 0
        self.connected_at = datetime.now()
        self.last_activity = datetime.now()
        
    async def send_message(self, message: Any) -> bool:
        """Send a message to the WebSocket client."""
        try:
            if hasattr(message, 'to_json'):
                await self.websocket.send_text(message.to_json())
            else:
                await self.websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.error("Failed to send message to connection %s: %s", self.connection_id, e)
            return False
    
    async def close(self, code: int = WSCloseCode.NORMAL_CLOSURE, reason: str = "Normal closure"):
        """Close the WebSocket connection."""
        try:
            await self.websocket.close(code=code, reason=reason)
        except Exception as e:
            logger.warning("Error closing WebSocket %s: %s", self.connection_id, e)
    
    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()
        
    def add_stream(self, stream_id: str, stream_info: Dict[str, Any]):
        """Add a stream to this connection."""
        self.streams[stream_id] = stream_info
        
    def remove_stream(self, stream_id: str) -> bool:
        """Remove a stream from this connection."""
        return self.streams.pop(stream_id, None) is not None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            "connection_id": self.connection_id,
            "connected_at": self.connected_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "message_count": self.message_count,
            "stream_count": len(self.streams),
            "streams": list(self.streams.keys())
        }


class WebSocketManager:
    """Central manager for WebSocket connections and message routing."""
    
    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.stream_id_to_connection: Dict[str, str] = {}  # stream_id -> connection_id
        self.connection_counts: Dict[str, int] = defaultdict(int)  # IP -> count
        self.message_rates: Dict[str, List[float]] = defaultdict(list)  # connection_id -> timestamps
        
    def generate_connection_id(self) -> str:
        """Generate unique connection ID."""
        timestamp = int(time.time() * 1000)
        random_suffix = random.randint(1000, 9999)
        return f"ws_{timestamp}_{random_suffix}"
    
    async def register_connection(self, websocket: WebSocket) -> str:
        """Register a new WebSocket connection."""
        # Check rate limits BEFORE creating connection
        client_ip = websocket.client.host if websocket.client else "unknown"
        if self.connection_counts[client_ip] >= 10:  # Max 10 connections per IP
            # Don't close here - let the caller handle it
            raise ValueError("Rate limit exceeded")
        
        connection_id = self.generate_connection_id()
        connection = WebSocketConnection(websocket, connection_id)
        
        self.connections[connection_id] = connection
        self.connection_counts[client_ip] += 1
        
        logger.info("Registered WebSocket connection %s from %s", connection_id, client_ip)
        
        # Send connected message with v2 protocol
        connected_msg = create_connected_message()
        await connection.send_message(connected_msg)
        
        return connection_id
    
    async def unregister_connection(self, connection_id: str):
        """Unregister and cleanup a WebSocket connection."""
        connection = self.connections.get(connection_id)
        if not connection:
            return
        
        # Unsubscribe all active streams
        for stream_id in list(connection.streams.keys()):
            await self._handle_unsubscribe_internal(connection_id, stream_id)
        
        # Update connection count
        if connection.websocket.client:
            client_ip = connection.websocket.client.host
            self.connection_counts[client_ip] = max(0, self.connection_counts[client_ip] - 1)
        
        # Remove from tracking
        del self.connections[connection_id]
        self.message_rates.pop(connection_id, None)
        
        logger.info("Unregistered WebSocket connection %s", connection_id)
    
    async def handle_message(self, connection_id: str, raw_message: str):
        """Handle incoming message from WebSocket client."""
        connection = self.connections.get(connection_id)
        if not connection:
            logger.warning("Received message for unknown connection %s", connection_id)
            return
        
        connection.update_activity()
        connection.message_count += 1
        
        # Rate limiting check
        current_time = time.time()
        message_times = self.message_rates[connection_id]
        message_times.append(current_time)
        
        # Keep only messages from last second
        message_times[:] = [t for t in message_times if current_time - t < 1.0]
        
        if len(message_times) > 100:  # Max 100 messages per second
            error_msg = create_rate_limit_error("")
            await connection.send_message(error_msg)
            await connection.close(code=WSCloseCode.RATE_LIMIT_EXCEEDED)
            return
        
        try:
            message_data = parse_client_message(raw_message)
            await self._route_message(connection_id, message_data)
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Invalid message from connection %s: %s", connection_id, e)
            error_msg = create_invalid_message_error("", str(e))
            await connection.send_message(error_msg)
            
        except Exception as e:
            logger.error("Error handling message from connection %s: %s", connection_id, e, exc_info=True)
            error_msg = create_internal_error("", str(e))
            await connection.send_message(error_msg)
    
    async def _route_message(self, connection_id: str, message_data: Dict[str, Any]):
        """Route message to appropriate handler based on type."""
        message_type = message_data["type"]
        message_id = message_data.get("id")
        
        if message_type == "subscribe":
            await self._handle_subscribe(connection_id, message_id, message_data["data"])
        elif message_type == "unsubscribe":
            await self._handle_unsubscribe(connection_id, message_id, message_data["data"])
        elif message_type == "ping":
            await self._handle_ping(connection_id, message_id, message_data.get("timestamp"))
        else:
            logger.warning("Unknown message type %s from connection %s", message_type, connection_id)
    
    async def _handle_subscribe(self, connection_id: str, message_id: str, data: Dict[str, Any]):
        """Handle subscribe message with v2 protocol."""
        connection = self.connections.get(connection_id)
        if not connection:
            return
        
        # Check subscription limits
        if len(connection.streams) >= 20:  # Max 20 streams per connection
            error_msg = create_rate_limit_error("")
            await connection.send_message(error_msg)
            return
        
        contract_id = data["contract_id"]
        tick_types = data["tick_types"]
        config_data = data.get("config", {})
        
        # Normalize tick_types to list
        if isinstance(tick_types, str):
            tick_types = [tick_types]
        
        streams_created = []
        
        try:
            # Create streams for each tick type
            for tick_type in tick_types:
                # Generate unique stream ID
                stream_id = generate_stream_id(contract_id, tick_type)
                
                # Create stream info
                stream_info = {
                    "stream_id": stream_id,
                    "contract_id": contract_id,
                    "tick_type": tick_type,
                    "config": config_data,
                    "message_id": message_id
                }
                
                # Start the stream
                await self._start_stream(connection_id, stream_id, stream_info)
                streams_created.append({
                    "stream_id": stream_id,
                    "tick_type": tick_type
                })
            
            # Send subscribed confirmation with all created streams
            subscribed_msg = create_subscribed_message(message_id, streams_created)
            await connection.send_message(subscribed_msg)
            
        except Exception as e:
            logger.error("Error starting streams for connection %s: %s", connection_id, e)
            
            # Cleanup any partial streams
            for stream in streams_created:
                await self._handle_unsubscribe_internal(connection_id, stream["stream_id"])
            
            error_msg = create_internal_error("", f"Failed to start streams: {str(e)}")
            await connection.send_message(error_msg)
    
    async def _handle_unsubscribe(self, connection_id: str, message_id: str, data: Dict[str, Any]):
        """Handle unsubscribe message with v2 protocol."""
        stream_id = data["stream_id"]
        success = await self._handle_unsubscribe_internal(connection_id, stream_id)
        
        if success:
            connection = self.connections.get(connection_id)
            if connection:
                # Send completion message for unsubscribed stream
                complete_msg = create_complete_message(
                    stream_id, 
                    "client_disconnect", 
                    0,  # No ticks since we're unsubscribing
                    0.0  # No duration since we're disconnecting
                )
                await connection.send_message(complete_msg)
        else:
            connection = self.connections.get(connection_id)
            if connection:
                error_msg = create_error_message(stream_id, "INVALID_REQUEST", "Stream not found", recoverable=False)
                await connection.send_message(error_msg)
    
    async def _handle_ping(self, connection_id: str, message_id: str, client_timestamp: Optional[str]):
        """Handle ping message with v2 protocol."""
        connection = self.connections.get(connection_id)
        if connection:
            pong_msg = create_pong_message(message_id, client_timestamp)
            await connection.send_message(pong_msg)
    
    async def _handle_unsubscribe_internal(self, connection_id: str, stream_id: str) -> bool:
        """Internal unsubscribe logic."""
        connection = self.connections.get(connection_id)
        if not connection:
            return False
        
        if stream_id not in connection.streams:
            return False
        
        # Remove from StreamManager - need to find the numeric request ID
        stream_info = connection.streams.get(stream_id)
        if stream_info and "numeric_request_id" in stream_info:
            stream_manager.unregister_stream(stream_info["numeric_request_id"])
        
        # Remove from connection tracking
        connection.remove_stream(stream_id)
        self.stream_id_to_connection.pop(stream_id, None)
        
        logger.info("Unsubscribed stream %s from connection %s", stream_id, connection_id)
        return True
    
    async def _start_stream(self, connection_id: str, stream_id: str, stream_info: Dict[str, Any]):
        """Start a new stream for a subscription."""
        from .api_server import ensure_tws_connection
        
        contract_id = stream_info["contract_id"]
        tick_type = stream_info["tick_type"]
        config_data = stream_info["config"]
        
        # Get TWS connection
        app_instance = ensure_tws_connection()
        
        # Create callback functions that use stream_id
        async def on_tick(tick_data: Dict[str, Any]):
            tick_msg = create_tick_message(stream_id, contract_id, tick_type, tick_data)
            connection = self.connections.get(connection_id)
            if connection:
                await connection.send_message(tick_msg)
        
        async def on_error(error_code: str, message: str):
            error_msg = create_error_message(stream_id, error_code, message)
            connection = self.connections.get(connection_id)
            if connection:
                await connection.send_message(error_msg)
        
        async def on_complete(reason: str, total_ticks: int):
            duration = time.time() - stream_info.get("start_time", time.time())
            complete_msg = create_complete_message(stream_id, reason, total_ticks, duration)
            connection = self.connections.get(connection_id)
            if connection:
                await connection.send_message(complete_msg)
                # Auto-cleanup completed streams
                await self._handle_unsubscribe_internal(connection_id, stream_id)
        
        # Create StreamHandler - use a simple numeric ID for IB API
        numeric_request_id = int(time.time() * 1000) % 100000 + random.randint(1, 999)
        
        stream_handler = StreamHandler(
            request_id=numeric_request_id,
            contract_id=contract_id,
            tick_type=tick_type,
            limit=config_data.get("limit"),
            timeout=config_data.get("timeout_seconds"),
            tick_callback=on_tick,
            error_callback=on_error,
            complete_callback=on_complete,
            stream_id=stream_id
        )
        
        # Register with StreamManager
        stream_manager.register_stream(stream_handler)
        
        # Add to connection tracking
        connection = self.connections[connection_id]
        stream_info["start_time"] = time.time()
        stream_info["numeric_request_id"] = numeric_request_id
        connection.add_stream(stream_id, stream_info)
        self.stream_id_to_connection[stream_id] = connection_id
        
        # Start the actual streaming (convert v2 tick type to TWS API format)
        from .config_v2 import convert_v2_tick_type_to_tws_api
        tws_tick_type = convert_v2_tick_type_to_tws_api(tick_type)
        app_instance.req_id = stream_handler.request_id
        app_instance.stream_contract(contract_id, tws_tick_type)
        
        logger.info("Started stream %s for connection %s", stream_id, connection_id)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics for all connections."""
        total_connections = len(self.connections)
        total_streams = sum(len(conn.streams) for conn in self.connections.values())
        
        return {
            "total_connections": total_connections,
            "total_streams": total_streams,
            "connection_details": [conn.get_stats() for conn in self.connections.values()],
            "connections_by_ip": dict(self.connection_counts)
        }


# Global WebSocket manager instance
ws_manager = WebSocketManager()