"""
Background Stream Orchestrator - Category Theory Compliant

Composes individual components using categorical principles:
- Composition: Components interact via well-defined morphisms
- Associativity: Component operations compose associatively  
- Identity: No-op operations when components are in desired state
- Functoriality: Preserves structure across component interactions
"""

import asyncio
import logging
from typing import Dict, List, Set, Optional
from datetime import datetime

from ..config import TrackedContract
from ..streaming_app import StreamingApp
from ..models.background_health import BackgroundStreamHealth, ContractHealthStatus

from .connection_manager import ConnectionManager, ConnectionListener
from .stream_lifecycle_manager import StreamLifecycleManager, StreamEventListener
from .health_monitor import HealthMonitor

logger = logging.getLogger(__name__)


class BackgroundStreamOrchestrator(ConnectionListener, StreamEventListener):
    """
    Orchestrates background streaming components using categorical composition.
    
    Mathematical Properties:
    - Composition: f ∘ g where f and g are component operations
    - Associativity: (connection ∘ streams) ∘ health = connection ∘ (streams ∘ health)
    - Identity: Operations preserve component state when no change needed
    - Functoriality: Structure-preserving operations across all components
    """
    
    def __init__(self, tracked_contracts: List[TrackedContract], 
                 reconnect_delay: int = 30,
                 staleness_threshold_minutes: int = 15):
        
        # Convert contracts to immutable lookup
        self.tracked_contracts = {c.contract_id: c for c in tracked_contracts if c.enabled}
        
        # Component composition via dependency injection
        self.connection_manager = ConnectionManager(
            client_id_offset=1000,
            reconnect_delay=reconnect_delay
        )
        
        self.stream_manager = StreamLifecycleManager(
            tracked_contracts=self.tracked_contracts,
            start_request_id=60000
        )
        
        self.health_monitor = HealthMonitor(
            tracked_contracts=self.tracked_contracts,
            staleness_threshold_minutes=staleness_threshold_minutes
        )
        
        # Component wiring (categorical composition)
        self.connection_manager.add_listener(self)
        self.stream_manager.add_listener(self)
        
        # Orchestrator state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start orchestrated background streaming (identity if already running)"""
        if self._running:
            return  # Identity property
        
        self._running = True
        
        # Start components in dependency order
        await self.connection_manager.start()
        
        # Start monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("Background stream orchestrator started with %d tracked contracts", 
                   len(self.tracked_contracts))
    
    async def stop(self) -> None:
        """Stop orchestrated background streaming (identity if not running)"""
        if not self._running:
            return  # Identity property
        
        self._running = False
        
        # Stop monitoring
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        # Stop components in reverse dependency order
        await self.stream_manager.stop_all_streams()
        await self.connection_manager.stop()
        
        logger.info("Background stream orchestrator stopped")
    
    # ConnectionListener implementation (categorical morphisms)
    
    async def on_connection_established(self, tws_app: StreamingApp) -> None:
        """Compose connection establishment with stream initialization"""
        logger.info("Connection established - starting tracked streams")
        
        # Wire connection to stream manager
        self.stream_manager.set_connection(tws_app)
        
        # Start streams for all tracked contracts
        await self._start_all_tracked_streams()
    
    async def on_connection_lost(self) -> None:
        """Compose connection loss with stream cleanup"""
        logger.warning("Connection lost - stopping all streams")
        
        # Unwire connection from stream manager
        self.stream_manager.set_connection(None)
        
        # Stop all streams
        await self.stream_manager.stop_all_streams()
    
    # StreamEventListener implementation (categorical morphisms)
    
    async def on_stream_started(self, contract_id: int, request_id: int) -> None:
        """Compose stream start with health monitoring activation"""
        logger.debug("Stream started for contract %d (request %d)", contract_id, request_id)
        
        # Initialize health monitoring for this contract
        self.health_monitor.update_data_timestamp(contract_id)
    
    async def on_stream_stopped(self, contract_id: int, request_id: int) -> None:
        """Compose stream stop with health monitoring deactivation"""
        logger.debug("Stream stopped for contract %d (request %d)", contract_id, request_id)
    
    async def on_stream_error(self, contract_id: int, error: str) -> None:
        """Compose stream error with health status update"""
        logger.error("Stream error for contract %d: %s", contract_id, error)
    
    # Public interface (functorial operations)
    
    def update_data_timestamp(self, contract_id: int) -> None:
        """Update data timestamp (functorial operation on health state)"""
        self.health_monitor.update_data_timestamp(contract_id)
    
    def is_connected(self) -> bool:
        """Pure function: Check if system is connected"""
        return self.connection_manager.is_connected()
    
    def get_tracked_contract_ids(self) -> Set[int]:
        """Pure function: Get tracked contract IDs"""
        return self.health_monitor.get_tracked_contract_ids()
    
    def is_contract_tracked(self, contract_id: int) -> bool:
        """Pure function: Check if contract is tracked"""
        return self.health_monitor.is_contract_tracked(contract_id)
    
    async def get_comprehensive_health(self) -> BackgroundStreamHealth:
        """Compose health assessment across all components"""
        active_contracts = self.stream_manager.get_active_contract_ids()
        return await self.health_monitor.get_comprehensive_health(active_contracts)
    
    async def get_contract_health(self, contract_id: int) -> Optional[ContractHealthStatus]:
        """Get health for specific contract (composition of stream + health state)"""
        is_streaming = self.stream_manager.is_contract_streaming(contract_id)
        return await self.health_monitor.assess_contract_health(contract_id, is_streaming)
    
    def get_health_summary(self) -> Dict[str, any]:
        """Get health summary (pure composition of component states)"""
        active_contracts = self.stream_manager.get_active_contract_ids()
        health_summary = self.health_monitor.get_health_summary(active_contracts)
        
        # Compose with connection status
        health_summary.update({
            "tws_connected": self.is_connected(),
            "enabled": True,
            "timestamp": datetime.now().isoformat()
        })
        
        return health_summary
    
    def set_staleness_threshold(self, minutes: int) -> None:
        """Set staleness threshold (functorial operation)"""
        self.health_monitor.set_staleness_threshold(minutes)
    
    def get_status(self) -> Dict:
        """Get comprehensive status (composition of all component states)"""
        return {
            "running": self._running,
            "tracked_contracts": len(self.tracked_contracts),
            "connection": self.connection_manager.get_status(),
            "streams": self.stream_manager.get_status(),
            "health": self.health_monitor.get_status()
        }
    
    # Private implementation (internal morphisms)
    
    async def _monitor_loop(self) -> None:
        """Background monitoring loop (compositional behavior)"""
        while self._running:
            try:
                # Compose connection check with stream management
                if self.is_connected():
                    await self._ensure_streams_active()
                
                # Health monitoring happens via event-driven updates
                
                await asyncio.sleep(30)  # Monitor every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in monitoring loop: %s", e)
                await asyncio.sleep(30)
    
    async def _start_all_tracked_streams(self) -> None:
        """Start streams for all tracked contracts (compositional operation)"""
        for contract_id in self.tracked_contracts.keys():
            try:
                success = await self.stream_manager.start_contract_streams(contract_id)
                if success:
                    logger.info("Started streams for contract %d", contract_id)
                else:
                    logger.warning("Failed to start streams for contract %d", contract_id)
            except Exception as e:
                logger.error("Error starting streams for contract %d: %s", contract_id, e)
    
    async def _ensure_streams_active(self) -> None:
        """Ensure all tracked contracts have active streams (idempotent operation)"""
        for contract_id in self.tracked_contracts.keys():
            if not self.stream_manager.is_contract_streaming(contract_id):
                logger.info("Restarting streams for contract %d", contract_id)
                await self.stream_manager.start_contract_streams(contract_id)