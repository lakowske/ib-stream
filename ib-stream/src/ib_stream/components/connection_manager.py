"""
Connection Manager Component - Category Theory Compliant

Handles only TWS connection lifecycle according to categorical principles:
- Single responsibility: TWS connection management only
- Pure functions where possible
- Composition via well-defined interfaces
- Identity element: no-op when already connected
"""

import asyncio
import logging
from typing import Optional, Protocol
from datetime import datetime

from ..streaming_app import StreamingApp
from ..config import create_config

logger = logging.getLogger(__name__)


class ConnectionListener(Protocol):
    """Protocol for connection state change notifications"""
    
    async def on_connection_established(self, tws_app: StreamingApp) -> None:
        """Called when connection is successfully established"""
        ...
    
    async def on_connection_lost(self) -> None:
        """Called when connection is lost"""
        ...


class ConnectionManager:
    """
    Pure connection management component.
    
    Categorical Properties:
    - Identity: connect() when already connected returns current connection
    - Composition: connection state changes compose via listeners
    - Single responsibility: only manages TWS connection
    """
    
    def __init__(self, client_id_offset: int = 1000, reconnect_delay: int = 30):
        self.client_id_offset = client_id_offset
        self.reconnect_delay = reconnect_delay
        
        # Connection state (immutable after creation)
        self._tws_app: Optional[StreamingApp] = None
        self._connection_task: Optional[asyncio.Task] = None
        self._listeners: list[ConnectionListener] = []
        
        # Connection monitoring
        self._running = False
        self._last_connection_attempt: Optional[datetime] = None
    
    def add_listener(self, listener: ConnectionListener) -> None:
        """Add connection state listener (pure composition)"""
        if listener not in self._listeners:
            self._listeners.append(listener)
    
    def remove_listener(self, listener: ConnectionListener) -> None:
        """Remove connection state listener"""
        if listener in self._listeners:
            self._listeners.remove(listener)
    
    async def start(self) -> None:
        """Start connection management"""
        if self._running:
            return  # Identity: no-op if already running
        
        self._running = True
        self._connection_task = asyncio.create_task(self._manage_connection())
        logger.info("Connection manager started")
    
    async def stop(self) -> None:
        """Stop connection management"""
        if not self._running:
            return  # Identity: no-op if not running
        
        self._running = False
        
        if self._connection_task:
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass
        
        await self._disconnect()
        logger.info("Connection manager stopped")
    
    def is_connected(self) -> bool:
        """Pure function: Check connection status"""
        return self._tws_app is not None and self._tws_app.is_connected()
    
    def get_connection(self) -> Optional[StreamingApp]:
        """Pure function: Get current connection if available"""
        return self._tws_app if self.is_connected() else None
    
    async def _manage_connection(self) -> None:
        """Connection lifecycle management loop"""
        while self._running:
            try:
                if not self.is_connected():
                    logger.info("Attempting to establish TWS connection...")
                    await self._establish_connection()
                
                # Wait before next check
                await asyncio.sleep(self.reconnect_delay)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Connection management error: %s", e)
                await asyncio.sleep(self.reconnect_delay)
    
    async def _establish_connection(self) -> None:
        """Establish new TWS connection"""
        self._last_connection_attempt = datetime.now()
        
        try:
            # Disconnect existing connection if any
            await self._disconnect()
            
            # Create configuration with offset client ID for background streaming
            config = create_config()
            bg_client_id = config.client_id + self.client_id_offset
            
            logger.info("Creating background TWS connection with client ID %d", bg_client_id)
            
            # Create new connection
            self._tws_app = StreamingApp(
                json_output=True,
                client_id=bg_client_id,
                host=config.host,
                ports=config.connection_ports
            )
            
            # Attempt connection
            if self._tws_app.connect_and_start():
                logger.info("Background TWS connection established with client ID %d", bg_client_id)
                await self._notify_connection_established()
            else:
                logger.error("Failed to establish TWS connection")
                self._tws_app = None
                
        except Exception as e:
            logger.error("Connection establishment failed: %s", e)
            self._tws_app = None
    
    async def _disconnect(self) -> None:
        """Clean disconnect from TWS"""
        if self._tws_app:
            try:
                logger.info("Disconnecting from TWS...")
                self._tws_app.disconnect_and_stop()
                await self._notify_connection_lost()
            except Exception as e:
                logger.error("Error during TWS disconnect: %s", e)
            finally:
                self._tws_app = None
    
    async def _notify_connection_established(self) -> None:
        """Notify all listeners of connection establishment"""
        if self._tws_app:
            for listener in self._listeners:
                try:
                    await listener.on_connection_established(self._tws_app)
                except Exception as e:
                    logger.error("Error notifying connection listener: %s", e)
    
    async def _notify_connection_lost(self) -> None:
        """Notify all listeners of connection loss"""
        for listener in self._listeners:
            try:
                await listener.on_connection_lost()
            except Exception as e:
                logger.error("Error notifying connection listener: %s", e)
    
    def get_status(self) -> dict:
        """Get connection status (pure function)"""
        return {
            "connected": self.is_connected(),
            "client_id": self._tws_app.config.client_id if self._tws_app else None,
            "last_attempt": self._last_connection_attempt.isoformat() if self._last_connection_attempt else None,
            "running": self._running
        }