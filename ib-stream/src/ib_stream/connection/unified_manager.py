"""
Unified connection manager for IB Stream - single connection for all streaming needs
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Optional, List, Callable, Dict, Any
from contextlib import asynccontextmanager

from ib_util import IBConnection
from ib_util.connection import ConnectionConfig
from ..streaming_app import StreamingApp
from .stream_registry import StreamRegistry, StreamType, StreamStatus

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECOVERING = "recovering"
    FAILED = "failed"


class UnifiedConnectionManager:
    """
    Single connection manager for all IB streaming needs
    
    Replaces the dual-connection architecture with a shared connection
    that handles both client requests and background streaming.
    """
    
    def __init__(self, config, enable_recovery: bool = True):
        self.config = config
        self.enable_recovery = enable_recovery
        
        # Core connection management
        self.connection: Optional[IBConnection] = None
        self.streaming_app: Optional[StreamingApp] = None
        self.state = ConnectionState.DISCONNECTED
        
        # Stream management
        self.stream_registry = StreamRegistry()
        
        # Recovery and monitoring
        self._recovery_task: Optional[asyncio.Task] = None
        self._connection_callbacks: List[Callable[[ConnectionState], None]] = []
        self._last_connection_attempt = None
        self._connection_failures = 0
        self._max_connection_failures = 10
        
        # Statistics
        self._stats = {
            "connection_attempts": 0,
            "successful_connections": 0,
            "recovery_cycles": 0,
            "streams_restarted": 0
        }
    
    @property
    def is_connected(self) -> bool:
        """Check if connection is active"""
        return (self.connection is not None and 
                self.connection.is_connected() and
                self.state == ConnectionState.CONNECTED)
    
    @property
    def client_id(self) -> int:
        """Get client ID from config"""
        return self.config.client_id
    
    async def start(self):
        """Start the connection manager"""
        logger.info("Starting unified connection manager with client ID %d", self.client_id)
        
        # Establish initial connection
        await self.ensure_connection()
        
        # Start recovery monitoring if enabled
        if self.enable_recovery and self._recovery_task is None:
            self._recovery_task = asyncio.create_task(self._recovery_monitor())
            logger.info("Recovery monitoring started")
    
    async def stop(self):
        """Stop the connection manager and clean up"""
        logger.info("Stopping unified connection manager")
        
        # Stop recovery task
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
            self._recovery_task = None
        
        # Cancel all active streams
        await self._cancel_all_streams()
        
        # Disconnect
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception as e:
                logger.warning("Error during disconnect: %s", e)
            self.connection = None
            self.streaming_app = None
        
        self.state = ConnectionState.DISCONNECTED
        self._notify_state_change()
        
        logger.info("Unified connection manager stopped")
    
    async def ensure_connection(self) -> StreamingApp:
        """
        Ensure connection is established and return StreamingApp instance
        
        This is the main interface for getting a connection - replaces
        the old ensure_tws_connection() pattern.
        """
        if self.is_connected:
            return self.streaming_app
        
        await self._establish_connection()
        return self.streaming_app
    
    async def _establish_connection(self):
        """Establish connection to IB Gateway"""
        self.state = ConnectionState.CONNECTING
        self._notify_state_change()
        self._last_connection_attempt = datetime.now()
        self._stats["connection_attempts"] += 1
        
        try:
            logger.info("Establishing connection to %s:%s with client ID %d",
                       self.config.host, self.config.ports, self.config.client_id)
            
            # Clean up existing connection
            if self.connection:
                try:
                    self.connection.disconnect()
                except Exception as e:
                    logger.debug("Error disconnecting old connection: %s", e)
                self.connection = None
                self.streaming_app = None
            
            # Create new connection using existing configuration
            connection_config = ConnectionConfig(
                host=self.config.host,
                ports=self.config.ports,
                client_id=self.config.client_id,
                connection_timeout=self.config.connection_timeout
            )
            
            # Create IBConnection
            self.connection = IBConnection(connection_config)
            
            # Create StreamingApp that uses the connection
            self.streaming_app = StreamingApp(
                json_output=True,
                config=self.config
            )
            
            # Replace StreamingApp's connection with ours (composition pattern)
            self.streaming_app._ib_connection = self.connection
            
            # Connect to IB Gateway
            if not self.streaming_app.connect_and_start():
                raise RuntimeError("Failed to connect to IB Gateway")
            
            self.state = ConnectionState.CONNECTED
            self._connection_failures = 0
            self._stats["successful_connections"] += 1
            
            logger.info("✅ Unified connection established successfully")
            
            # Restart all registered streams
            await self._restart_all_streams()
            
        except Exception as e:
            self._connection_failures += 1
            self.state = ConnectionState.FAILED
            logger.error("Failed to establish connection (attempt %d): %s", 
                        self._connection_failures, e)
            raise
        finally:
            self._notify_state_change()
    
    async def _restart_all_streams(self):
        """Restart all registered streams after connection"""
        if not self.is_connected:
            logger.warning("Cannot restart streams - not connected")
            return
        
        streams_to_restart = self.stream_registry.get_all_streams()
        if not streams_to_restart:
            logger.debug("No streams to restart")
            return
        
        logger.info("Restarting %d streams after connection", len(streams_to_restart))
        
        restart_count = 0
        for request_id, stream_info in streams_to_restart.items():
            try:
                # Call the stream's restart callback
                await stream_info.callback(request_id, self.streaming_app)
                self.stream_registry.update_stream_status(request_id, StreamStatus.ACTIVE)
                self.stream_registry.clear_error_count(request_id)
                restart_count += 1
                
            except Exception as e:
                logger.error("Failed to restart stream %d: %s", request_id, e)
                self.stream_registry.update_stream_status(request_id, StreamStatus.FAILED)
                self.stream_registry.increment_error_count(request_id)
        
        self._stats["streams_restarted"] += restart_count
        logger.info("✅ Restarted %d/%d streams successfully", 
                   restart_count, len(streams_to_restart))
    
    async def _cancel_all_streams(self):
        """Cancel all active streams"""
        streams = self.stream_registry.get_all_streams()
        if not streams:
            return
        
        logger.info("Cancelling %d active streams", len(streams))
        
        for request_id, stream_info in streams.items():
            try:
                if self.streaming_app and self.streaming_app.isConnected():
                    self.streaming_app.cancelTickByTickData(request_id)
            except Exception as e:
                logger.debug("Error cancelling stream %d: %s", request_id, e)
        
        logger.info("All streams cancelled")
    
    async def _recovery_monitor(self):
        """Background task to monitor connection and recover if needed"""
        logger.info("Recovery monitor started")
        
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if not self.is_connected and self.state != ConnectionState.CONNECTING:
                    if self._connection_failures < self._max_connection_failures:
                        logger.info("Connection lost - attempting recovery...")
                        self.state = ConnectionState.RECOVERING
                        self._notify_state_change()
                        self._stats["recovery_cycles"] += 1
                        
                        try:
                            await self._establish_connection()
                        except Exception as e:
                            logger.error("Recovery attempt failed: %s", e)
                            # Will retry on next cycle
                    else:
                        logger.error("Maximum connection failures reached (%d) - giving up recovery",
                                   self._max_connection_failures)
                        break
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Recovery monitor error: %s", e)
                await asyncio.sleep(60)  # Wait longer on error
        
        logger.info("Recovery monitor stopped")
    
    def register_connection_callback(self, callback: Callable[[ConnectionState], None]):
        """Register callback for connection state changes"""
        self._connection_callbacks.append(callback)
    
    def _notify_state_change(self):
        """Notify all callbacks of connection state change"""
        for callback in self._connection_callbacks:
            try:
                callback(self.state)
            except Exception as e:
                logger.error("Error in connection callback: %s", e)
    
    # Stream management methods
    
    def register_stream(self, stream_type: StreamType, contract_id: int, 
                       tick_type: str, restart_callback: Callable) -> int:
        """
        Register a stream for management and recovery
        
        Args:
            stream_type: Type of stream (client or background)
            contract_id: Contract ID being streamed
            tick_type: Type of tick data
            restart_callback: Async function to call to restart the stream
        
        Returns:
            Allocated request ID for the stream
        """
        return self.stream_registry.register_stream(
            stream_type=stream_type,
            contract_id=contract_id,
            tick_type=tick_type,
            callback=restart_callback
        )
    
    def unregister_stream(self, request_id: int):
        """Unregister a stream"""
        self.stream_registry.unregister_stream(request_id)
    
    def mark_stream_data_received(self, request_id: int):
        """Mark that a stream received data (for health monitoring)"""
        self.stream_registry.mark_data_received(request_id)
    
    def get_stream_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        registry_stats = self.stream_registry.get_stats()
        
        return {
            "connection": {
                "state": self.state.value,
                "client_id": self.client_id,
                "is_connected": self.is_connected,
                "connection_failures": self._connection_failures,
                "last_attempt": self._last_connection_attempt.isoformat() if self._last_connection_attempt else None
            },
            "streams": registry_stats,
            "performance": self._stats
        }
    
    # Context manager support for easy cleanup
    
    @asynccontextmanager
    async def connection_context(self):
        """Context manager for automatic connection management"""
        await self.start()
        try:
            yield self
        finally:
            await self.stop()
            
    # Legacy compatibility methods
    
    def connect_and_start(self) -> bool:
        """Legacy compatibility method"""
        # This is synchronous in the old API, but our new API is async
        # For now, return True if already connected, False otherwise
        return self.is_connected
    
    def disconnect(self):
        """Legacy compatibility method"""
        if self.connection:
            self.connection.disconnect()
    
    def isConnected(self) -> bool:
        """Legacy compatibility method"""
        return self.is_connected