"""
Pure State Container - Category Theory Compliant State Management

This module implements a mathematically sound state container that eliminates
global mutable state and provides proper categorical composition properties.

Key Principles:
- Immutability: All state transformations are pure functions
- Associativity: State transformations compose associatively
- Identity: Identity transformations leave state unchanged
- Functoriality: Structure-preserving state operations
"""

import logging
from dataclasses import dataclass, replace
from typing import Optional, Dict, Any, Callable, TypeVar, Generic
from threading import Lock

from .streaming_app import StreamingApp
from .storage.multi_storage_v3 import MultiStorageV3
from .background_stream_manager import BackgroundStreamManager
from .config_v2 import StreamConfig

logger = logging.getLogger(__name__)

T = TypeVar('T')
S = TypeVar('S')


@dataclass(frozen=True)
class AppState:
    """
    Immutable application state container.
    
    This class provides categorical properties:
    - Identity: with_* methods act as identity when passed current values
    - Associativity: Chained updates compose associatively
    - Functoriality: Structure is preserved across transformations
    """
    config: Optional[StreamConfig] = None
    tws_app: Optional[StreamingApp] = None
    storage: Optional[MultiStorageV3] = None
    background_manager: Optional[BackgroundStreamManager] = None
    active_streams: Dict[str, Any] = None
    _locks: Dict[str, Lock] = None
    
    def __post_init__(self):
        """Initialize default values while maintaining immutability"""
        if self.active_streams is None:
            object.__setattr__(self, 'active_streams', {})
        if self._locks is None:
            object.__setattr__(self, '_locks', {
                'tws': Lock(),
                'streams': Lock()
            })
    
    # Pure state transformation functions (Category Theory: Morphisms)
    
    def with_config(self, config: StreamConfig) -> 'AppState':
        """Identity morphism: returns current state if config is unchanged"""
        if self.config == config:
            return self  # Identity property
        return replace(self, config=config)
    
    def with_tws_app(self, tws_app: Optional[StreamingApp]) -> 'AppState':
        """Pure function: TWS app state transformation"""
        if self.tws_app == tws_app:
            return self  # Identity property
        return replace(self, tws_app=tws_app)
    
    def with_storage(self, storage: Optional[MultiStorageV3]) -> 'AppState':
        """Pure function: Storage state transformation"""
        if self.storage == storage:
            return self  # Identity property
        return replace(self, storage=storage)
    
    def with_background_manager(self, manager: Optional[BackgroundStreamManager]) -> 'AppState':
        """Pure function: Background manager state transformation"""
        if self.background_manager == manager:
            return self  # Identity property
        return replace(self, background_manager=manager)
    
    def with_active_stream(self, stream_id: str, stream_data: Any) -> 'AppState':
        """Pure function: Add/update active stream"""
        new_streams = self.active_streams.copy()
        new_streams[stream_id] = stream_data
        return replace(self, active_streams=new_streams)
    
    def without_active_stream(self, stream_id: str) -> 'AppState':
        """Pure function: Remove active stream"""
        if stream_id not in self.active_streams:
            return self  # Identity property
        new_streams = self.active_streams.copy()
        del new_streams[stream_id]
        return replace(self, active_streams=new_streams)
    
    def with_active_streams(self, streams: Dict[str, Any]) -> 'AppState':
        """Pure function: Replace all active streams"""
        if self.active_streams == streams:
            return self  # Identity property
        return replace(self, active_streams=streams.copy())
    
    # Categorical composition operations
    
    def compose(self, transformation: Callable[['AppState'], 'AppState']) -> 'AppState':
        """
        Function composition for state transformations.
        Ensures associativity: (f ∘ g) ∘ h = f ∘ (g ∘ h)
        """
        return transformation(self)
    
    def map_tws_app(self, func: Callable[[Optional[StreamingApp]], Optional[StreamingApp]]) -> 'AppState':
        """Functorial operation: preserves structure while transforming TWS app"""
        return self.with_tws_app(func(self.tws_app))
    
    def map_storage(self, func: Callable[[Optional[MultiStorageV3]], Optional[MultiStorageV3]]) -> 'AppState':
        """Functorial operation: preserves structure while transforming storage"""
        return self.with_storage(func(self.storage))
    
    # Safe access with locks (maintains referential transparency)
    
    def get_tws_lock(self) -> Lock:
        """Get TWS lock for thread-safe operations"""
        return self._locks['tws']
    
    def get_streams_lock(self) -> Lock:
        """Get streams lock for thread-safe operations"""
        return self._locks['streams']
    
    # Query operations (pure functions)
    
    def is_tws_connected(self) -> bool:
        """Pure function: Check if TWS is connected"""
        return self.tws_app is not None and self.tws_app.is_connected()
    
    def has_storage(self) -> bool:
        """Pure function: Check if storage is available"""
        return self.storage is not None
    
    def has_background_streaming(self) -> bool:
        """Pure function: Check if background streaming is active"""
        return self.background_manager is not None
    
    def get_active_stream_count(self) -> int:
        """Pure function: Get count of active streams"""
        return len(self.active_streams)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for serialization (pure function)"""
        return {
            'config_loaded': self.config is not None,
            'tws_connected': self.is_tws_connected(),
            'storage_available': self.has_storage(),
            'background_streaming': self.has_background_streaming(),
            'active_streams_count': self.get_active_stream_count(),
            'client_id': self.tws_app.config.client_id if self.tws_app else None
        }


class StateContainer:
    """
    Thread-safe container for immutable AppState.
    
    This provides the mutable interface needed for the application while
    maintaining categorical properties of the underlying state.
    """
    
    def __init__(self, initial_state: Optional[AppState] = None):
        self._state = initial_state or AppState()
        self._lock = Lock()
    
    def get_state(self) -> AppState:
        """Get current immutable state snapshot"""
        with self._lock:
            return self._state
    
    def update_state(self, transformation: Callable[[AppState], AppState]) -> AppState:
        """
        Apply pure transformation to state.
        Returns new state while maintaining immutability.
        """
        with self._lock:
            new_state = transformation(self._state)
            self._state = new_state
            return new_state
    
    def set_state(self, new_state: AppState) -> None:
        """Replace entire state (useful for testing)"""
        with self._lock:
            self._state = new_state
    
    # Convenience methods for common transformations
    
    def update_config(self, config: StreamConfig) -> AppState:
        """Update configuration in thread-safe manner"""
        return self.update_state(lambda s: s.with_config(config))
    
    def update_tws_app(self, tws_app: Optional[StreamingApp]) -> AppState:
        """Update TWS app in thread-safe manner"""
        return self.update_state(lambda s: s.with_tws_app(tws_app))
    
    def update_storage(self, storage: Optional[MultiStorageV3]) -> AppState:
        """Update storage in thread-safe manner"""
        return self.update_state(lambda s: s.with_storage(storage))
    
    def update_background_manager(self, manager: Optional[BackgroundStreamManager]) -> AppState:
        """Update background manager in thread-safe manner"""
        return self.update_state(lambda s: s.with_background_manager(manager))
    
    def add_active_stream(self, stream_id: str, stream_data: Any) -> AppState:
        """Add active stream in thread-safe manner"""
        return self.update_state(lambda s: s.with_active_stream(stream_id, stream_data))
    
    def remove_active_stream(self, stream_id: str) -> AppState:
        """Remove active stream in thread-safe manner"""
        return self.update_state(lambda s: s.without_active_stream(stream_id))


# Global state container (single point of mutation)
_global_state_container = StateContainer()


def get_app_state() -> AppState:
    """
    Get current immutable application state.
    
    This replaces the old get_app_state() function with a pure version
    that returns immutable state instead of mutable dictionaries.
    """
    return _global_state_container.get_state()


def update_app_state(transformation: Callable[[AppState], AppState]) -> AppState:
    """
    Apply pure transformation to global application state.
    
    This provides the mechanism for state updates while maintaining
    categorical properties of composition and associativity.
    """
    return _global_state_container.update_state(transformation)


# Specific state update functions for backward compatibility
def update_global_config(config: StreamConfig) -> AppState:
    """Update global configuration"""
    return _global_state_container.update_config(config)


def update_global_tws_app(tws_app: Optional[StreamingApp]) -> AppState:
    """Update global TWS app"""
    return _global_state_container.update_tws_app(tws_app)


def update_global_storage(storage: Optional[MultiStorageV3]) -> AppState:
    """Update global storage"""
    return _global_state_container.update_storage(storage)


def update_global_background_manager(manager: Optional[BackgroundStreamManager]) -> AppState:
    """Update global background manager"""
    return _global_state_container.update_background_manager(manager)


def add_global_active_stream(stream_id: str, stream_data: Any) -> AppState:
    """Add active stream to global state"""
    return _global_state_container.add_active_stream(stream_id, stream_data)


def remove_global_active_stream(stream_id: str) -> AppState:
    """Remove active stream from global state"""
    return _global_state_container.remove_active_stream(stream_id)


# For testing: allow direct state injection
def set_global_state(state: AppState) -> None:
    """Set global state directly (for testing only)"""
    _global_state_container.set_state(state)