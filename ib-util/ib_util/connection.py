"""
Reliable IB API connection handling

This module provides a robust connection class that properly handles the IB API 
connection lifecycle, including the full handshake process.
"""

import logging
import socket
import threading
import time
from typing import Optional, Callable, Any

from ibapi.client import EClient
from ibapi.wrapper import EWrapper

from .config_loader import ConnectionConfig


logger = logging.getLogger(__name__)


class IBConnection(EWrapper, EClient):
    """
    Reliable IB API connection that properly waits for the full handshake
    
    This class extends both EWrapper and EClient to provide a complete
    connection solution that waits for nextValidId callback to confirm
    the connection is fully established.
    """
    
    def __init__(self, config: ConnectionConfig):
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        
        self.config = config
        self.connected = False
        self.connection_time = None
        self.next_valid_id = None
        self.api_thread = None
        self.connection_event = threading.Event()
        
        # Optional callbacks for connection events
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_error: Optional[Callable[[int, int, str], None]] = None
        
    def nextValidId(self, orderId: int):
        """Called when connection is fully established"""
        self.next_valid_id = orderId
        self.connected = True
        self.connection_time = time.time()
        self.connection_event.set()
        
        if self.on_connected:
            self.on_connected()
            
        logger.info(f"✓ Connected to IB Gateway with client ID {self.config.client_id}, next valid order ID: {orderId}")
        
    def connectAck(self):
        """Called when initial connection is acknowledged"""
        logger.debug("Connection acknowledged by server")
        
    def connectionClosed(self):
        """Called when connection is closed"""
        self.connected = False
        self.next_valid_id = None  # Clear this too to ensure is_connected() returns False
        self.connection_event.clear()
        
        logger.warning("TWS connection closed")
        
        if self.on_disconnected:
            self.on_disconnected()
            
        logger.info("Connection closed")
        
    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str = ""):
        """Handle API errors using standardized error handling"""
        # Check for critical connection errors that indicate disconnection
        if errorCode in [504, 1100, 1101, 1102]:  # Not connected, connectivity issues
            logger.warning("Critical connection error %d: %s", errorCode, errorString)
            self.connected = False
            self.next_valid_id = None
            if self.on_disconnected:
                self.on_disconnected()
        
        from .error_handler import handle_tws_error
        handle_tws_error(reqId, errorCode, errorString, logger, self.on_error)
    
    def connect_and_start(self) -> bool:
        """
        Connect to IB Gateway/TWS and wait for full handshake
        
        Returns:
            bool: True if connected successfully, False otherwise
        """
        for port in self.config.ports:
            try:
                logger.info(f"Attempting to connect to {self.config.host}:{port} with client ID {self.config.client_id}")
                
                # Reset connection state
                self.connected = False
                self.connection_event.clear()
                
                # Attempt connection
                super().connect(self.config.host, port, self.config.client_id)
                
                # Start API thread
                self.api_thread = threading.Thread(target=self.run, daemon=True)
                self.api_thread.start()
                
                # Wait for the nextValidId callback (proper connection confirmation)
                if self.connection_event.wait(timeout=self.config.connection_timeout):
                    logger.info(f"✓ Successfully connected to {self.config.host}:{port}")
                    return True
                else:
                    logger.warning(f"Connection timeout after {self.config.connection_timeout}s on port {port}")
                    self.disconnect()
                    
            except Exception as e:
                logger.debug(f"Failed to connect to port {port}: {e}")
                continue
        
        logger.error(f"Failed to connect to {self.config.host} on any port {self.config.ports}")
        return False
    
    def disconnect_and_stop(self):
        """Properly disconnect and clean up"""
        if self.connected:
            self.disconnect()
        
        # Wait for API thread to finish
        if self.api_thread and self.api_thread.is_alive():
            self.api_thread.join(timeout=2)
    
    def is_connected(self) -> bool:
        """Check if properly connected with live socket verification"""
        # First check basic connection state
        if not (self.connected and self.next_valid_id is not None):
            return False
        
        # Verify the underlying socket is still alive using IB API patterns
        try:
            # Check if the socket is still connected
            if hasattr(self, 'conn') and hasattr(self.conn, 'isConnected'):
                socket_alive = self.conn.isConnected()
                if not socket_alive:
                    logger.warning("Socket connection lost (conn.isConnected=False)")
                    self.connected = False
                    self.next_valid_id = None
                    return False
            
            # Additional check: try to get socket state directly
            if hasattr(self, 'conn') and hasattr(self.conn, 'socket') and self.conn.socket:
                try:
                    # Use socket.getpeername() to test if socket is connected
                    # This will raise an exception if socket is not connected
                    self.conn.socket.getpeername()
                except (OSError, socket.error, AttributeError) as e:
                    logger.warning("Socket state check failed: %s", e)
                    self.connected = False
                    self.next_valid_id = None
                    # Trigger connectionClosed callback like IB API does
                    self.connectionClosed()
                    return False
            
            return True
        except Exception as e:
            logger.warning("Connection verification failed: %s", e)
            self.connected = False
            self.next_valid_id = None
            return False
    
    def wait_for_connection(self, timeout: float = None) -> bool:
        """
        Wait for connection to be established
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if connected within timeout
        """
        timeout = timeout or self.config.connection_timeout
        return self.connection_event.wait(timeout)


def create_connection(service_type: str = "stream") -> IBConnection:
    """
    Create a properly configured IB connection
    
    Args:
        service_type: "stream" or "contracts" for service-specific configuration
        
    Returns:
        IBConnection: Configured but not yet connected instance
    """
    from .config_loader import load_environment_config
    
    config = load_environment_config(service_type)
    return IBConnection(config)


def connect_with_retry(service_type: str = "stream", max_retries: int = 3, retry_delay: float = 2.0) -> Optional[IBConnection]:
    """
    Create and connect with retry logic
    
    Args:
        service_type: "stream" or "contracts" 
        max_retries: Maximum number of connection attempts
        retry_delay: Delay between retries in seconds
        
    Returns:
        IBConnection: Connected instance or None if failed
    """
    for attempt in range(max_retries):
        try:
            connection = create_connection(service_type)
            
            if connection.connect_and_start():
                return connection
            else:
                logger.warning(f"Connection attempt {attempt + 1}/{max_retries} failed")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    
        except Exception as e:
            logger.error(f"Connection attempt {attempt + 1}/{max_retries} error: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    return None