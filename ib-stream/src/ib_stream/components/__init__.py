"""
Category Theory Compliant Components Package

This package contains decomposed components that follow categorical principles:
- Single responsibility (each component is a proper object in its category)
- Composition via well-defined morphisms
- Identity elements for proper categorical structure
"""

from .connection_manager import ConnectionManager
from .stream_lifecycle_manager import StreamLifecycleManager
from .health_monitor import HealthMonitor
from .background_orchestrator import BackgroundStreamOrchestrator

__all__ = [
    'ConnectionManager',
    'StreamLifecycleManager', 
    'HealthMonitor',
    'BackgroundStreamOrchestrator'
]