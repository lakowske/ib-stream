"""
IB Service - Independent IB API Management

This service manages all IB API connections and background streaming
independently of the web server.
"""

import logging
import asyncio
from typing import Optional, List
from dataclasses import dataclass, field
import time

from ..config import ServerConfig
from ..connection import UnifiedConnectionManager
from ..background_stream_manager_v2 import BackgroundStreamManagerV2
from ..streaming_app import StreamingApp
from .event_bus import EventBus, EventType
from .service_registry import ServiceStatus, ServiceState

logger = logging.getLogger(__name__)


@dataclass
class IBServiceStatus:
    """IB Service specific status information"""
    connection_healthy: bool = False
    background_streams_running: bool = False
    tracked_contracts_count: int = 0
    last_data_timestamp: Optional[float] = None
    connection_uptime: Optional[float] = None
    auto_recovery_enabled: bool = True


class IBService:
    """
    Independent IB API Service
    
    Manages IB API connections and background streaming without being
    tied to FastAPI lifecycle. Can run standalone or composed with other services.
    """
    
    def __init__(self, config: ServerConfig, event_bus: EventBus):
        self.config = config
        self.event_bus = event_bus
        self.connection_manager: Optional[UnifiedConnectionManager] = None
        self.background_manager: Optional[BackgroundStreamManagerV2] = None
        
        self._state = ServiceState.INITIALIZING
        self._start_time: Optional[float] = None
        self._logger = logging.getLogger(f"{__name__}.IBService")
        
        self._logger.info(f"IBService initialized with client_id={config.client_id}")
    
    async def start(self) -> None:
        """Start IB API connections and background streaming"""
        self._logger.info("Starting IB Service...")
        self._state = ServiceState.STARTING
        self._start_time = time.time()
        
        try:
            # Initialize unified connection manager
            self._logger.info("Initializing unified connection manager...")
            self.connection_manager = UnifiedConnectionManager(
                config=self.config,
                enable_recovery=True
            )
            
            # Start connection
            self._logger.info("Starting unified connection...")
            await self.connection_manager.start()
            
            # Publish connection event
            self.event_bus.publish_simple(
                EventType.IB_CONNECTION_STATUS_CHANGED,
                "ib_service",
                {"connected": True, "client_id": self.config.client_id}
            )
            
            # Start background streaming if configured
            if self.config.storage.tracked_contracts:
                self._logger.info(f"Starting background streaming for {len(self.config.storage.tracked_contracts)} contracts...")
                
                staleness_threshold = getattr(
                    self.config.storage,
                    'health_staleness_threshold_minutes',
                    15
                )
                
                self.background_manager = BackgroundStreamManagerV2(
                    tracked_contracts=self.config.storage.tracked_contracts,
                    connection_manager=self.connection_manager,
                    staleness_threshold_minutes=staleness_threshold
                )
                
                await self.background_manager.start()
                
                self.event_bus.publish_simple(
                    EventType.IB_STREAM_STARTED,
                    "ib_service", 
                    {"contract_count": len(self.config.storage.tracked_contracts)}
                )
                
                self._logger.info("✅ Background streaming started successfully")
            else:
                self._logger.info("No tracked contracts configured - background streaming disabled")
            
            self._state = ServiceState.RUNNING
            self.event_bus.publish_simple(EventType.SERVICE_STARTED, "ib_service")
            self._logger.info("✅ IB Service started successfully")
            
        except Exception as e:
            self._state = ServiceState.ERROR
            self._logger.error(f"Failed to start IB Service: {e}")
            self.event_bus.publish_simple(
                EventType.SERVICE_ERROR,
                "ib_service", 
                {"error": str(e)}
            )
            raise
    
    async def stop(self) -> None:
        """Stop IB API connections and background streaming"""
        self._logger.info("Stopping IB Service...")
        self._state = ServiceState.STOPPING
        
        try:
            # Stop background streaming
            if self.background_manager:
                self._logger.info("Stopping background streaming...")
                await self.background_manager.stop()
                self.event_bus.publish_simple(EventType.IB_STREAM_STOPPED, "ib_service")
            
            # Stop connection manager  
            if self.connection_manager:
                self._logger.info("Stopping unified connection manager...")
                await self.connection_manager.stop()
                self.event_bus.publish_simple(
                    EventType.IB_CONNECTION_STATUS_CHANGED,
                    "ib_service",
                    {"connected": False}
                )
            
            self._state = ServiceState.STOPPED
            self.event_bus.publish_simple(EventType.SERVICE_STOPPED, "ib_service")
            self._logger.info("✅ IB Service stopped successfully")
            
        except Exception as e:
            self._state = ServiceState.ERROR
            self._logger.error(f"Error stopping IB Service: {e}")
            raise
    
    def get_status(self) -> ServiceStatus:
        """Get current service status"""
        health = "healthy"
        error_message = None
        
        # Determine health based on connections
        if self._state != ServiceState.RUNNING:
            health = "unhealthy" if self._state == ServiceState.ERROR else "starting"
        elif not self.is_connection_healthy():
            health = "degraded"
        
        # Get IB-specific status
        ib_status = self.get_ib_status()
        
        uptime = None
        if self._start_time:
            uptime = time.time() - self._start_time
        
        return ServiceStatus(
            service_name="ib_service",
            state=self._state,
            health=health,
            metadata={
                "connection_healthy": ib_status.connection_healthy,
                "background_streams_running": ib_status.background_streams_running,
                "tracked_contracts_count": ib_status.tracked_contracts_count,
                "uptime_seconds": uptime,
                "client_id": self.config.client_id,
                "auto_recovery_enabled": ib_status.auto_recovery_enabled
            },
            error_message=error_message
        )
    
    def get_ib_status(self) -> IBServiceStatus:
        """Get detailed IB service status"""
        connection_healthy = False
        background_streams_running = False
        tracked_contracts_count = 0
        last_data_timestamp = None
        connection_uptime = None
        
        if self.connection_manager:
            connection_healthy = self.connection_manager.is_connected
            if connection_healthy and self._start_time:
                connection_uptime = time.time() - self._start_time
        
        if self.background_manager:
            # TODO: Add method to BackgroundStreamManagerV2 to check if streams are running
            background_streams_running = True  # Simplified for now
            
        if self.config.storage.tracked_contracts:
            tracked_contracts_count = len(self.config.storage.tracked_contracts)
        
        return IBServiceStatus(
            connection_healthy=connection_healthy,
            background_streams_running=background_streams_running,
            tracked_contracts_count=tracked_contracts_count,
            last_data_timestamp=last_data_timestamp,
            connection_uptime=connection_uptime,
            auto_recovery_enabled=True
        )
    
    def get_streaming_app(self) -> Optional[StreamingApp]:
        """Get StreamingApp for client requests (used by web service)"""
        if self.connection_manager and self.connection_manager.is_connected:
            return self.connection_manager.streaming_app
        return None
    
    def is_connection_healthy(self) -> bool:
        """Check if IB connection is healthy"""
        return (self.connection_manager is not None and 
                self.connection_manager.is_connected)
    
    def get_background_status(self) -> dict:
        """Get background streaming status (used by web service health endpoints)"""
        if not self.background_manager:
            return {"enabled": False}
        
        # TODO: Implement detailed background status in BackgroundStreamManagerV2
        return {
            "enabled": True,
            "running": self._state == ServiceState.RUNNING,
            "contract_count": len(self.config.storage.tracked_contracts) if self.config.storage.tracked_contracts else 0
        }