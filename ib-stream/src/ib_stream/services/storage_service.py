"""
Storage Service - Independent Data Persistence

This service manages data storage independently of other services,
listening for data events through the event bus.
"""

import logging
import asyncio
from typing import Optional
from dataclasses import dataclass
import time

from ..config import ServerConfig
from ..storage.multi_storage_v3 import MultiStorageV3
from .event_bus import EventBus, EventType, Event
from .service_registry import ServiceStatus, ServiceState

logger = logging.getLogger(__name__)


@dataclass 
class StorageServiceStatus:
    """Storage Service specific status information"""
    storage_enabled: bool = False
    v3_json_enabled: bool = False
    v3_protobuf_enabled: bool = False
    storage_path: Optional[str] = None
    files_written_count: int = 0
    last_write_timestamp: Optional[float] = None


class StorageService:
    """
    Independent Storage Service
    
    Manages data persistence independently, listening for data events
    from other services through the event bus.
    """
    
    def __init__(self, config: ServerConfig, event_bus: EventBus):
        self.config = config
        self.event_bus = event_bus
        self.storage: Optional[MultiStorageV3] = None
        
        self._state = ServiceState.INITIALIZING
        self._start_time: Optional[float] = None
        self._files_written = 0
        self._last_write_time: Optional[float] = None
        self._logger = logging.getLogger(f"{__name__}.StorageService")
        
        # Subscribe to data events
        self.event_bus.subscribe(EventType.IB_DATA_RECEIVED, self._handle_data_event)
        
        self._logger.info(f"StorageService initialized, storage_enabled={config.storage.enable_storage}")
    
    async def start(self) -> None:
        """Start storage service"""
        self._logger.info("Starting Storage Service...")
        self._state = ServiceState.STARTING
        self._start_time = time.time()
        
        try:
            if self.config.storage.enable_storage:
                self._logger.info("Initializing storage system...")
                self._logger.info(f"  Storage path: {self.config.storage.storage_base_path}")
                self._logger.info(f"  v2 JSON enabled: {self.config.storage.enable_json}")
                self._logger.info(f"  v2 Protobuf enabled: {self.config.storage.enable_protobuf}")
                self._logger.info(f"  v3 JSON enabled: {self.config.storage.enable_v3_json}")
                self._logger.info(f"  v3 Protobuf enabled: {self.config.storage.enable_v3_protobuf}")
                
                self.storage = MultiStorageV3(
                    storage_path=self.config.storage.storage_base_path,
                    enable_v2_json=self.config.storage.enable_json,
                    enable_v2_protobuf=self.config.storage.enable_protobuf,
                    enable_v3_json=self.config.storage.enable_v3_json,
                    enable_v3_protobuf=self.config.storage.enable_v3_protobuf,
                    enable_metrics=self.config.storage.enable_metrics
                )
                
                await self.storage.start()
                self._logger.info("✅ Storage system initialized successfully")
            else:
                self._logger.info("Storage system disabled")
            
            self._state = ServiceState.RUNNING
            self.event_bus.publish_simple(EventType.SERVICE_STARTED, "storage_service")
            self._logger.info("✅ Storage Service started successfully")
            
        except Exception as e:
            self._state = ServiceState.ERROR
            self._logger.error(f"Failed to start Storage Service: {e}")
            self.event_bus.publish_simple(
                EventType.SERVICE_ERROR,
                "storage_service",
                {"error": str(e)}
            )
            raise
    
    async def stop(self) -> None:
        """Stop storage service"""
        self._logger.info("Stopping Storage Service...")
        self._state = ServiceState.STOPPING
        
        try:
            if self.storage:
                self._logger.info("Stopping storage system...")
                await self.storage.stop()
                self._logger.info("✅ Storage system stopped")
            
            self._state = ServiceState.STOPPED
            self.event_bus.publish_simple(EventType.SERVICE_STOPPED, "storage_service")
            self._logger.info("✅ Storage Service stopped successfully")
            
        except Exception as e:
            self._state = ServiceState.ERROR
            self._logger.error(f"Error stopping Storage Service: {e}")
            raise
    
    def get_status(self) -> ServiceStatus:
        """Get current service status"""
        health = "healthy"
        error_message = None
        
        if self._state != ServiceState.RUNNING:
            health = "unhealthy" if self._state == ServiceState.ERROR else "starting"
        
        # Get storage-specific status
        storage_status = self.get_storage_status()
        
        uptime = None
        if self._start_time:
            uptime = time.time() - self._start_time
        
        return ServiceStatus(
            service_name="storage_service",
            state=self._state,
            health=health,
            metadata={
                "storage_enabled": storage_status.storage_enabled,
                "v3_json_enabled": storage_status.v3_json_enabled,
                "v3_protobuf_enabled": storage_status.v3_protobuf_enabled,
                "storage_path": storage_status.storage_path,
                "files_written": storage_status.files_written_count,
                "uptime_seconds": uptime,
                "last_write_timestamp": storage_status.last_write_timestamp
            },
            error_message=error_message
        )
    
    def get_storage_status(self) -> StorageServiceStatus:
        """Get detailed storage service status"""
        return StorageServiceStatus(
            storage_enabled=self.config.storage.enable_storage,
            v3_json_enabled=self.config.storage.enable_v3_json,
            v3_protobuf_enabled=self.config.storage.enable_v3_protobuf,
            storage_path=self.config.storage.storage_base_path if self.config.storage.enable_storage else None,
            files_written_count=self._files_written,
            last_write_timestamp=self._last_write_time
        )
    
    def _handle_data_event(self, event: Event):
        """Handle data events from other services"""
        if self.storage and self._state == ServiceState.RUNNING:
            try:
                # Process data event for storage
                # This would be expanded based on the specific data format
                self._files_written += 1
                self._last_write_time = time.time()
                
                self.event_bus.publish_simple(
                    EventType.STORAGE_DATA_WRITTEN,
                    "storage_service",
                    {"files_written": self._files_written}
                )
                
            except Exception as e:
                self._logger.error(f"Error handling data event: {e}")
                self.event_bus.publish_simple(
                    EventType.STORAGE_ERROR,
                    "storage_service",
                    {"error": str(e)}
                )