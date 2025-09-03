"""
Service Orchestrator - Single Configuration and Service Coordination

This orchestrator loads configuration exactly once and coordinates service
startup/shutdown in the proper dependency order.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
import time

from ..config import create_config, ServerConfig
from .event_bus import EventBus, EventType, Event
from .service_registry import ServiceRegistry, ServiceInterface
from .ib_service import IBService
from .storage_service import StorageService

logger = logging.getLogger(__name__)


class ServiceOrchestrator:
    """
    Service Orchestrator for IB Stream Architecture
    
    Responsibilities:
    - Load configuration exactly once 
    - Start/stop services in proper dependency order
    - Coordinate inter-service communication
    - Provide unified service status
    """
    
    def __init__(self):
        self.config: Optional[ServerConfig] = None
        self.event_bus = EventBus()
        self.service_registry = ServiceRegistry()
        self.services: Dict[str, ServiceInterface] = {}
        
        self._logger = logging.getLogger(f"{__name__}.ServiceOrchestrator")
        self._setup_event_logging()
    
    def _setup_event_logging(self):
        """Set up event bus logging for debugging"""
        def log_event(event: Event):
            self._logger.debug(f"Event: {event.event_type.name} from {event.source_service}")
        
        # Subscribe to key events for logging
        for event_type in [EventType.SERVICE_STARTED, EventType.SERVICE_STOPPED, EventType.SERVICE_ERROR]:
            self.event_bus.subscribe(event_type, log_event)
    
    async def start(self, services_to_start: Optional[List[str]] = None) -> None:
        """
        Start specified services or all services
        
        Args:
            services_to_start: List of service names to start, or None for all services
                             Supported: ['storage', 'ib', 'web'] 
        """
        if services_to_start is None:
            services_to_start = ['storage', 'ib']  # Default: no web service (handled by FastAPI)
        
        self._logger.info(f"Starting Service Orchestrator with services: {services_to_start}")
        
        # Load configuration exactly once
        self._logger.info("Loading configuration...")
        self.config = create_config()  # SINGLE CONFIG LOAD!
        self._logger.info(f"✅ Configuration loaded: client_id={self.config.client_id}, host={self.config.host}")
        
        # Start services in dependency order
        try:
            # Phase 1: Independent services (can start in parallel)
            startup_tasks = []
            
            if 'storage' in services_to_start:
                startup_tasks.append(self._start_storage_service())
            
            if 'ib' in services_to_start:
                startup_tasks.append(self._start_ib_service())
            
            # Start independent services concurrently  
            if startup_tasks:
                self._logger.info(f"Starting {len(startup_tasks)} services concurrently...")
                await asyncio.gather(*startup_tasks)
            
            # TODO: Phase 2: Dependent services (web service that depends on ib service)
            # if 'web' in services_to_start:
            #     await self._start_web_service()
            
            self._logger.info("✅ Service Orchestrator startup complete")
            
        except Exception as e:
            self._logger.error(f"Service orchestrator startup failed: {e}")
            await self.stop()  # Cleanup on failure
            raise
    
    async def stop(self) -> None:
        """Stop all services in reverse dependency order"""
        self._logger.info("Stopping Service Orchestrator...")
        
        # Stop services in reverse dependency order
        stop_tasks = []
        
        # Stop all registered services concurrently
        for service_name, service in self.services.items():
            self._logger.info(f"Stopping {service_name}...")
            stop_tasks.append(service.stop())
        
        if stop_tasks:
            try:
                await asyncio.gather(*stop_tasks, return_exceptions=True)
            except Exception as e:
                self._logger.error(f"Error during service shutdown: {e}")
        
        self._logger.info("✅ Service Orchestrator stopped")
    
    async def _start_storage_service(self) -> None:
        """Start storage service"""
        self._logger.info("Starting Storage Service...")
        storage_service = StorageService(config=self.config, event_bus=self.event_bus)
        self.services['storage'] = storage_service
        self.service_registry.register('storage_service', storage_service)
        await storage_service.start()
        self._logger.info("✅ Storage Service started")
    
    async def _start_ib_service(self) -> None:
        """Start IB service"""
        self._logger.info("Starting IB Service...")
        ib_service = IBService(config=self.config, event_bus=self.event_bus)
        self.services['ib'] = ib_service
        self.service_registry.register('ib_service', ib_service)
        await ib_service.start()
        self._logger.info("✅ IB Service started")
    
    def get_service(self, service_name: str) -> Optional[ServiceInterface]:
        """Get a service by name"""
        return self.services.get(service_name)
    
    def get_ib_service(self) -> Optional[IBService]:
        """Get IB service specifically (convenience method)"""
        return self.services.get('ib')
    
    def get_storage_service(self) -> Optional[StorageService]:
        """Get storage service specifically (convenience method)"""
        return self.services.get('storage')
    
    def get_all_status(self) -> Dict[str, Any]:
        """Get status for all services"""
        return {
            'orchestrator': {
                'config_loaded': self.config is not None,
                'services_running': list(self.services.keys()),
                'total_services': len(self.services)
            },
            'services': self.service_registry.get_all_status()
        }
    
    def is_healthy(self) -> bool:
        """Check if orchestrator and all services are healthy"""
        if not self.config:
            return False
        
        for service_name in self.services:
            if not self.service_registry.is_service_healthy(service_name):
                return False
        
        return True