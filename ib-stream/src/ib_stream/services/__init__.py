"""
IB Stream Services - Service Composition Pattern

This module implements a clean separation of concerns architecture where:
- IBService manages IB API connections and background streaming  
- WebService provides HTTP API endpoints
- StorageService handles data persistence
- ServiceOrchestrator coordinates services with single config loading
"""

# Core infrastructure (no external dependencies)
from .event_bus import EventBus
from .service_registry import ServiceRegistry

# Services (may have external dependencies - import on demand)
def get_ib_service():
    from .ib_service import IBService
    return IBService

def get_storage_service():
    from .storage_service import StorageService
    return StorageService

def get_orchestrator():
    from .orchestrator import ServiceOrchestrator
    return ServiceOrchestrator

__all__ = [
    'EventBus',
    'ServiceRegistry',
    'get_ib_service',
    'get_storage_service', 
    'get_orchestrator'
]