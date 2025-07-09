"""
WebSocket connection manager for IB Stream API.
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

from .config import create_config
from .stream_manager import stream_manager, StreamHandler
from .ws_schemas import (
    parse_client_message, validate_client_message,
    SubscribedMessage, TickMessage, ErrorMessage, CompleteMessage,
    UnsubscribedMessage, PongMessage, ConnectedMessage,
    WSCloseCode, get_close_code_for_error
)

logger = logging.getLogger(__name__)
config = create_config()


class WebSocketConnection:
    """Represents a single WebSocket connection with its subscriptions."""
    
    def __init__(self, websocket: WebSocket, connection_id: str):
        self.websocket = websocket
        self.connection_id = connection_id
        self.subscriptions: Dict[str, Dict[str, Any]] = {}  # request_id -> subscription info
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
        
    def add_subscription(self, request_id: str, subscription_info: Dict[str, Any]):
        """Add a subscription to this connection."""
        self.subscriptions[request_id] = subscription_info
        
    def remove_subscription(self, request_id: str) -> bool:
        """Remove a subscription from this connection."""
        return self.subscriptions.pop(request_id, None) is not None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            "connection_id": self.connection_id,
            "connected_at": self.connected_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "message_count": self.message_count,
            "subscription_count": len(self.subscriptions),
            "subscriptions": list(self.subscriptions.keys())
        }


class WebSocketManager:
    """Central manager for WebSocket connections and message routing."""
    
    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.request_id_to_connection: Dict[str, str] = {}  # request_id -> connection_id
        self.connection_counts: Dict[str, int] = defaultdict(int)  # IP -> count
        self.message_rates: Dict[str, List[float]] = defaultdict(list)  # connection_id -> timestamps
        
    def generate_connection_id(self) -> str:
        """Generate unique connection ID."""
        timestamp = int(time.time() * 1000)
        random_suffix = random.randint(1000, 9999)
        return f"ws_{timestamp}_{random_suffix}"
    
    def generate_request_id(self, contract_id: int, tick_type: str) -> str:
        """Generate unique request ID for a subscription."""
        timestamp = int(time.time() * 1000)
        random_suffix = random.randint(1000, 9999)
        return f"{contract_id}_{tick_type}_{timestamp}_{random_suffix}"
    
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
        
        # Send connected message
        connected_msg = ConnectedMessage(server_info={
            "max_subscriptions_per_connection": 20,
            "max_concurrent_streams": config.max_concurrent_streams
        })
        await connection.send_message(connected_msg)
        
        return connection_id
    
    async def unregister_connection(self, connection_id: str):
        """Unregister and cleanup a WebSocket connection."""
        connection = self.connections.get(connection_id)
        if not connection:
            return
        
        # Unsubscribe all active subscriptions
        for request_id in list(connection.subscriptions.keys()):
            await self._handle_unsubscribe_internal(connection_id, request_id)
        
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
            error_msg = ErrorMessage(None, "RATE_LIMIT_EXCEEDED", 
                                   "Too many messages per second")
            await connection.send_message(error_msg)
            await connection.close(code=WSCloseCode.RATE_LIMIT_EXCEEDED)
            return
        
        try:
            message_data = parse_client_message(raw_message)
            await self._route_message(connection_id, message_data)
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Invalid message from connection %s: %s", connection_id, e)
            error_msg = ErrorMessage(None, "INVALID_MESSAGE", f"Invalid message format: {str(e)}")
            await connection.send_message(error_msg)
            
        except Exception as e:
            logger.error("Error handling message from connection %s: %s", connection_id, e, exc_info=True)
            error_msg = ErrorMessage(None, "INTERNAL_ERROR", "Internal server error")
            await connection.send_message(error_msg)
    
    async def _route_message(self, connection_id: str, message_data: Dict[str, Any]):
        """Route message to appropriate handler based on type."""
        message_type = message_data["type"]
        message_id = message_data.get("id")
        
        if message_type == "subscribe":
            await self._handle_subscribe(connection_id, message_id, message_data["data"])
        elif message_type == "multi_subscribe":
            await self._handle_multi_subscribe(connection_id, message_id, message_data["data"])
        elif message_type == "unsubscribe":
            await self._handle_unsubscribe(connection_id, message_id, message_data["data"])
        elif message_type == "unsubscribe_all":
            await self._handle_unsubscribe_all(connection_id, message_id)
        elif message_type == "ping":
            await self._handle_ping(connection_id, message_id, message_data.get("timestamp"))
        else:
            logger.warning("Unknown message type %s from connection %s", message_type, connection_id)
    
    async def _handle_subscribe(self, connection_id: str, message_id: str, data: Dict[str, Any]):
        """Handle subscribe message."""
        connection = self.connections.get(connection_id)
        if not connection:
            return
        
        # Check subscription limits
        if len(connection.subscriptions) >= 20:  # Max 20 subscriptions per connection
            error_msg = ErrorMessage(None, "RATE_LIMIT_EXCEEDED", 
                                   "Maximum subscriptions per connection exceeded")
            await connection.send_message(error_msg)
            return
        
        contract_id = data["contract_id"]
        tick_type = data["tick_type"]
        params = data.get("params", {})
        
        request_id = self.generate_request_id(contract_id, tick_type)
        
        # Create subscription info
        subscription_info = {
            "request_id": request_id,
            "contract_id": contract_id,
            "tick_type": tick_type,
            "params": params,
            "message_id": message_id
        }
        
        try:
            # Create stream handler and start streaming
            await self._start_stream(connection_id, request_id, subscription_info)
            
            # Send subscribed confirmation
            subscribed_msg = SubscribedMessage(message_id, request_id, contract_id, tick_type)
            await connection.send_message(subscribed_msg)
            
        except Exception as e:
            logger.error("Error starting stream for connection %s: %s", connection_id, e)
            error_msg = ErrorMessage(request_id, "INTERNAL_ERROR", f"Failed to start stream: {str(e)}")
            await connection.send_message(error_msg)
    
    async def _handle_multi_subscribe(self, connection_id: str, message_id: str, data: Dict[str, Any]):
        """Handle multi-subscribe message."""
        connection = self.connections.get(connection_id)
        if not connection:
            return
        
        contract_id = data["contract_id"]
        tick_types = data["tick_types"]
        params = data.get("params", {})
        
        # Check if we can create all subscriptions
        if len(connection.subscriptions) + len(tick_types) > 20:
            error_msg = ErrorMessage(None, "RATE_LIMIT_EXCEEDED", 
                                   "Would exceed maximum subscriptions per connection")
            await connection.send_message(error_msg)
            return
        
        request_ids = []
        
        try:
            # Create subscriptions for each tick type
            for tick_type in tick_types:
                request_id = self.generate_request_id(contract_id, tick_type)
                request_ids.append(request_id)
                
                subscription_info = {
                    "request_id": request_id,
                    "contract_id": contract_id,
                    "tick_type": tick_type,
                    "params": params,
                    "message_id": message_id,
                    "multi_subscribe": True
                }
                
                await self._start_stream(connection_id, request_id, subscription_info)
            
            # Send single confirmation for all subscriptions
            multi_subscribed_msg = {
                "type": "multi_subscribed",
                "id": message_id,
                "data": {
                    "contract_id": contract_id,
                    "subscriptions": [
                        {"request_id": req_id, "tick_type": tick_type}
                        for req_id, tick_type in zip(request_ids, tick_types)
                    ]
                },
                "timestamp": datetime.now().isoformat()
            }
            await connection.send_message(multi_subscribed_msg)
            
        except Exception as e:
            logger.error("Error in multi-subscribe for connection %s: %s", connection_id, e)
            # Cleanup any partial subscriptions
            for request_id in request_ids:
                await self._handle_unsubscribe_internal(connection_id, request_id)
            
            error_msg = ErrorMessage(None, "INTERNAL_ERROR", f"Failed to create multi-subscription: {str(e)}")
            await connection.send_message(error_msg)
    
    async def _handle_unsubscribe(self, connection_id: str, message_id: str, data: Dict[str, Any]):
        """Handle unsubscribe message."""
        request_id = data["request_id"]
        success = await self._handle_unsubscribe_internal(connection_id, request_id)
        
        if success:
            connection = self.connections.get(connection_id)
            if connection:
                unsubscribed_msg = UnsubscribedMessage(message_id, request_id)
                await connection.send_message(unsubscribed_msg)
        else:
            connection = self.connections.get(connection_id)
            if connection:
                error_msg = ErrorMessage(request_id, "INVALID_REQUEST", "Subscription not found")
                await connection.send_message(error_msg)
    
    async def _handle_unsubscribe_all(self, connection_id: str, message_id: str):
        """Handle unsubscribe all message."""
        connection = self.connections.get(connection_id)
        if not connection:
            return
        
        request_ids = list(connection.subscriptions.keys())
        
        for request_id in request_ids:
            await self._handle_unsubscribe_internal(connection_id, request_id)
        
        unsubscribed_all_msg = {
            "type": "unsubscribed_all",
            "id": message_id,
            "data": {
                "unsubscribed_count": len(request_ids)
            },
            "timestamp": datetime.now().isoformat()
        }
        await connection.send_message(unsubscribed_all_msg)
    
    async def _handle_ping(self, connection_id: str, message_id: str, client_timestamp: Optional[str]):
        """Handle ping message."""
        connection = self.connections.get(connection_id)
        if connection:
            pong_msg = PongMessage(message_id, client_timestamp)
            await connection.send_message(pong_msg)
    
    async def _handle_unsubscribe_internal(self, connection_id: str, request_id: str) -> bool:
        """Internal unsubscribe logic."""
        connection = self.connections.get(connection_id)
        if not connection:
            return False
        
        if request_id not in connection.subscriptions:
            return False
        
        # Remove from StreamManager - need to find the numeric request ID
        subscription_info = connection.subscriptions.get(request_id)
        if subscription_info and "numeric_request_id" in subscription_info:
            stream_manager.unregister_stream(subscription_info["numeric_request_id"])
        
        # Remove from connection tracking
        connection.remove_subscription(request_id)
        self.request_id_to_connection.pop(request_id, None)
        
        logger.info("Unsubscribed %s from connection %s", request_id, connection_id)
        return True
    
    async def _start_stream(self, connection_id: str, request_id: str, subscription_info: Dict[str, Any]):
        """Start a new stream for a subscription."""
        from .api_server import ensure_tws_connection
        
        contract_id = subscription_info["contract_id"]
        tick_type = subscription_info["tick_type"]
        params = subscription_info["params"]
        
        # Get TWS connection
        app_instance = ensure_tws_connection()
        
        # Create callback functions
        async def on_tick(tick_data: Dict[str, Any]):
            tick_msg = TickMessage(request_id, tick_data)
            connection = self.connections.get(connection_id)
            if connection:
                await connection.send_message(tick_msg)
        
        async def on_error(error_code: str, message: str):
            error_msg = ErrorMessage(request_id, error_code, message)
            connection = self.connections.get(connection_id)
            if connection:
                await connection.send_message(error_msg)
        
        async def on_complete(reason: str, total_ticks: int):
            duration = time.time() - subscription_info.get("start_time", time.time())
            complete_msg = CompleteMessage(request_id, reason, total_ticks, duration)
            connection = self.connections.get(connection_id)
            if connection:
                await connection.send_message(complete_msg)
                # Auto-cleanup completed subscriptions
                await self._handle_unsubscribe_internal(connection_id, request_id)
        
        # Create StreamHandler - use a simple numeric ID for IB API
        numeric_request_id = int(time.time() * 1000) % 100000 + random.randint(1, 999)
        
        stream_handler = StreamHandler(
            request_id=numeric_request_id,
            contract_id=contract_id,
            tick_type=tick_type,
            limit=params.get("limit"),
            timeout=params.get("timeout"),
            tick_callback=on_tick,
            error_callback=on_error,
            complete_callback=on_complete
        )
        
        # Register with StreamManager
        stream_manager.register_stream(stream_handler)
        
        # Add to connection tracking
        connection = self.connections[connection_id]
        subscription_info["start_time"] = time.time()
        subscription_info["numeric_request_id"] = numeric_request_id
        connection.add_subscription(request_id, subscription_info)
        self.request_id_to_connection[request_id] = connection_id
        
        # Start the actual streaming
        app_instance.req_id = stream_handler.request_id
        app_instance.stream_contract(contract_id, tick_type)
        
        logger.info("Started stream %s for connection %s", request_id, connection_id)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics for all connections."""
        total_connections = len(self.connections)
        total_subscriptions = sum(len(conn.subscriptions) for conn in self.connections.values())
        
        return {
            "total_connections": total_connections,
            "total_subscriptions": total_subscriptions,
            "connection_details": [conn.get_stats() for conn in self.connections.values()],
            "connections_by_ip": dict(self.connection_counts)
        }


# Global WebSocket manager instance
ws_manager = WebSocketManager()