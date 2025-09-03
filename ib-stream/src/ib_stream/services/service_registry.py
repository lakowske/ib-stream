"""
Service Registry for Inter-Service Communication

Provides a central registry for services to find and communicate with each other
without direct coupling.
"""

import logging
from typing import Dict, Any, Optional, Protocol
from dataclasses import dataclass, field
from enum import Enum, auto
import time

logger = logging.getLogger(__name__)


class ServiceState(Enum):
    """Service lifecycle states"""
    INITIALIZING = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()


@dataclass
class ServiceStatus:
    """Service status information"""
    service_name: str
    state: ServiceState
    health: str  # "healthy", "degraded", "unhealthy"
    last_updated: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


class ServiceInterface(Protocol):
    """Protocol for services in the registry"""
    
    async def start(self) -> None:
        """Start the service"""
        ...
    
    async def stop(self) -> None:
        """Stop the service"""
        ...
    
    def get_status(self) -> ServiceStatus:
        """Get current service status"""
        ...


class ServiceRegistry:
    """
    Central registry for service discovery and status tracking
    
    Services register themselves and can query other services through
    this registry without direct coupling.
    """
    
    def __init__(self):
        self._services: Dict[str, ServiceInterface] = {}
        self._status_cache: Dict[str, ServiceStatus] = {}
        self._logger = logging.getLogger(f"{__name__}.ServiceRegistry")
    
    def register(self, service_name: str, service: ServiceInterface):
        """Register a service in the registry"""
        self._services[service_name] = service
        self._status_cache[service_name] = ServiceStatus(
            service_name=service_name,
            state=ServiceState.INITIALIZING,
            health="unknown"
        )
        self._logger.info(f"Registered service: {service_name}")
    
    def get_service(self, service_name: str) -> Optional[ServiceInterface]:
        """Get a service by name"""
        return self._services.get(service_name)
    
    def get_status(self, service_name: str) -> Optional[ServiceStatus]:
        """Get cached status for a service"""
        service = self._services.get(service_name)
        if service:
            try:
                # Refresh status from service
                status = service.get_status()
                self._status_cache[service_name] = status
                return status
            except Exception as e:
                self._logger.error(f"Error getting status for {service_name}: {e}")
                # Return cached status with error
                if service_name in self._status_cache:
                    cached_status = self._status_cache[service_name]
                    cached_status.error_message = str(e)
                    cached_status.health = "unhealthy"
                    return cached_status
        return None
    
    def get_all_status(self) -> Dict[str, ServiceStatus]:
        """Get status for all registered services"""
        status_dict = {}
        for service_name in self._services:
            status = self.get_status(service_name)
            if status:
                status_dict[service_name] = status
        return status_dict
    
    def list_services(self) -> list[str]:
        """List all registered service names"""
        return list(self._services.keys())
    
    def is_service_healthy(self, service_name: str) -> bool:
        """Check if a service is healthy"""
        status = self.get_status(service_name)
        return status and status.health == "healthy" and status.state == ServiceState.RUNNING
    
    def update_status(self, service_name: str, status: ServiceStatus):
        """Update cached status for a service (for performance)"""
        if service_name in self._services:
            self._status_cache[service_name] = status
            self._logger.debug(f"Updated status for {service_name}: {status.health}")