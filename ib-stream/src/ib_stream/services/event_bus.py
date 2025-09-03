"""
Event Bus for Service Communication

Simple event bus to enable decoupled communication between services
without direct dependencies.
"""

import logging
from typing import Dict, List, Callable, Any
from dataclasses import dataclass
from enum import Enum, auto

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Event types for inter-service communication"""
    
    # IB Service events
    IB_CONNECTION_STATUS_CHANGED = auto()
    IB_DATA_RECEIVED = auto()
    IB_STREAM_STARTED = auto()
    IB_STREAM_STOPPED = auto()
    
    # Storage Service events  
    STORAGE_DATA_WRITTEN = auto()
    STORAGE_ERROR = auto()
    
    # System events
    SERVICE_STARTED = auto()
    SERVICE_STOPPED = auto()
    SERVICE_ERROR = auto()


@dataclass
class Event:
    """Event data structure"""
    event_type: EventType
    source_service: str
    data: Dict[str, Any] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            import time
            self.timestamp = time.time()


class EventBus:
    """
    Simple event bus for service communication
    
    Services can publish events and subscribe to events from other services
    without direct coupling.
    """
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._logger = logging.getLogger(f"{__name__}.EventBus")
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """Subscribe to an event type"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append(callback)
        self._logger.debug(f"Subscribed to {event_type.name}: {callback.__name__}")
    
    def publish(self, event: Event):
        """Publish an event to all subscribers"""
        self._logger.debug(f"Publishing event: {event.event_type.name} from {event.source_service}")
        
        subscribers = self._subscribers.get(event.event_type, [])
        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                self._logger.error(f"Error in event callback {callback.__name__}: {e}")
    
    def publish_simple(self, event_type: EventType, source_service: str, data: Dict[str, Any] = None):
        """Convenience method to publish a simple event"""
        event = Event(event_type=event_type, source_service=source_service, data=data or {})
        self.publish(event)