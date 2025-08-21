"""
Stream Lifecycle Manager Component - Category Theory Compliant

Handles only stream creation, management, and destruction:
- Single responsibility: stream lifecycle only
- Pure functions for stream operations
- Composition via well-defined interfaces
- Identity element: no-op for already managed streams
"""

import asyncio
import logging
from typing import Dict, Optional, Set, List, Protocol
from datetime import datetime

from ..config import TrackedContract
from ..stream_manager import stream_manager, StreamHandler
from ..streaming_app import StreamingApp

logger = logging.getLogger(__name__)


class StreamEventListener(Protocol):
    """Protocol for stream lifecycle event notifications"""
    
    async def on_stream_started(self, contract_id: int, request_id: int) -> None:
        """Called when a stream is successfully started"""
        ...
    
    async def on_stream_stopped(self, contract_id: int, request_id: int) -> None:
        """Called when a stream is stopped"""
        ...
    
    async def on_stream_error(self, contract_id: int, error: str) -> None:
        """Called when a stream encounters an error"""
        ...


class StreamLifecycleManager:
    """
    Pure stream lifecycle management component.
    
    Categorical Properties:
    - Identity: start_stream() for already active stream returns existing stream
    - Composition: stream operations compose via event listeners
    - Single responsibility: only manages stream lifecycle
    """
    
    def __init__(self, tracked_contracts: Dict[int, TrackedContract], start_request_id: int = 60000):
        self.tracked_contracts = tracked_contracts
        self.next_request_id = start_request_id
        
        # Stream state (immutable references)
        self.active_streams: Dict[int, Dict[str, int]] = {}  # contract_id -> {tick_type: request_id}
        self.stream_handlers: Dict[int, StreamHandler] = {}  # request_id -> handler
        self._listeners: List[StreamEventListener] = []
        
        # Connection reference (managed externally)
        self._tws_app: Optional[StreamingApp] = None
    
    def add_listener(self, listener: StreamEventListener) -> None:
        """Add stream event listener (pure composition)"""
        if listener not in self._listeners:
            self._listeners.append(listener)
    
    def remove_listener(self, listener: StreamEventListener) -> None:
        """Remove stream event listener"""
        if listener in self._listeners:
            self._listeners.remove(listener)
    
    def set_connection(self, tws_app: Optional[StreamingApp]) -> None:
        """Set TWS connection for stream operations"""
        self._tws_app = tws_app
    
    def has_connection(self) -> bool:
        """Pure function: Check if connection is available"""
        return self._tws_app is not None and self._tws_app.is_connected()
    
    async def start_contract_streams(self, contract_id: int) -> bool:
        """Start all streams for a contract (identity if already started)"""
        if contract_id in self.active_streams:
            logger.debug("Streams for contract %d already active", contract_id)
            return True  # Identity property
        
        if not self.has_connection():
            logger.warning("Cannot start streams for contract %d: no connection", contract_id)
            return False
        
        contract = self.tracked_contracts.get(contract_id)
        if not contract:
            logger.error("Contract %d not found in tracked contracts", contract_id)
            return False
        
        try:
            # Initialize stream tracking for this contract
            self.active_streams[contract_id] = {}
            
            # Start streams for each requested tick type
            for tick_type in contract.tick_types:
                request_id = self._get_next_request_id()
                
                # Create stream handler
                handler = StreamHandler(
                    contract_id=contract_id,
                    tick_type=tick_type,
                    enable_storage=True,
                    buffer_hours=contract.buffer_hours
                )
                
                # Register handler with stream manager
                stream_manager.handlers[request_id] = handler
                self.stream_handlers[request_id] = handler
                
                # Start the stream
                success = await self._start_individual_stream(
                    contract_id, tick_type, request_id, handler
                )
                
                if success:
                    self.active_streams[contract_id][tick_type] = request_id
                    await self._notify_stream_started(contract_id, request_id)
                    logger.info("Started %s stream for contract %d (request_id: %d)", 
                              tick_type, contract_id, request_id)
                else:
                    # Clean up failed stream
                    stream_manager.handlers.pop(request_id, None)
                    self.stream_handlers.pop(request_id, None)
                    await self._notify_stream_error(contract_id, f"Failed to start {tick_type} stream")
            
            if not self.active_streams[contract_id]:
                # No streams were started successfully
                del self.active_streams[contract_id]
                return False
            
            return True
            
        except Exception as e:
            logger.error("Error starting streams for contract %d: %s", contract_id, e)
            await self._cleanup_contract_streams(contract_id)
            await self._notify_stream_error(contract_id, str(e))
            return False
    
    async def stop_contract_streams(self, contract_id: int) -> None:
        """Stop all streams for a contract (identity if not active)"""
        if contract_id not in self.active_streams:
            return  # Identity property
        
        try:
            contract_streams = self.active_streams[contract_id].copy()
            
            for tick_type, request_id in contract_streams.items():
                await self._stop_individual_stream(contract_id, tick_type, request_id)
                await self._notify_stream_stopped(contract_id, request_id)
            
            await self._cleanup_contract_streams(contract_id)
            logger.info("Stopped all streams for contract %d", contract_id)
            
        except Exception as e:
            logger.error("Error stopping streams for contract %d: %s", contract_id, e)
    
    async def stop_all_streams(self) -> None:
        """Stop all active streams"""
        contract_ids = list(self.active_streams.keys())
        for contract_id in contract_ids:
            await self.stop_contract_streams(contract_id)
    
    async def restart_contract_streams(self, contract_id: int) -> bool:
        """Restart streams for a contract"""
        await self.stop_contract_streams(contract_id)
        return await self.start_contract_streams(contract_id)
    
    def get_active_contract_ids(self) -> Set[int]:
        """Pure function: Get set of contracts with active streams"""
        return set(self.active_streams.keys())
    
    def is_contract_streaming(self, contract_id: int) -> bool:
        """Pure function: Check if contract has active streams"""
        return contract_id in self.active_streams and bool(self.active_streams[contract_id])
    
    def get_contract_stream_count(self, contract_id: int) -> int:
        """Pure function: Get number of active streams for contract"""
        return len(self.active_streams.get(contract_id, {}))
    
    def get_total_stream_count(self) -> int:
        """Pure function: Get total number of active streams"""
        return sum(len(streams) for streams in self.active_streams.values())
    
    async def _start_individual_stream(self, contract_id: int, tick_type: str, 
                                     request_id: int, handler: StreamHandler) -> bool:
        """Start individual stream with TWS"""
        try:
            if not self._tws_app:
                return False
            
            # Request market data from TWS
            success = self._tws_app.request_market_data(
                request_id=request_id,
                contract_id=contract_id,
                tick_types=[tick_type]
            )
            
            if success:
                logger.debug("Started %s stream for contract %d", tick_type, contract_id)
                return True
            else:
                logger.error("Failed to start %s stream for contract %d", tick_type, contract_id)
                return False
                
        except Exception as e:
            logger.error("Error starting %s stream for contract %d: %s", tick_type, contract_id, e)
            return False
    
    async def _stop_individual_stream(self, contract_id: int, tick_type: str, request_id: int) -> None:
        """Stop individual stream with TWS"""
        try:
            if self._tws_app:
                self._tws_app.cancel_market_data(request_id)
            
            # Clean up handler
            stream_manager.handlers.pop(request_id, None)
            self.stream_handlers.pop(request_id, None)
            
            logger.debug("Stopped %s stream for contract %d", tick_type, contract_id)
            
        except Exception as e:
            logger.error("Error stopping %s stream for contract %d: %s", tick_type, contract_id, e)
    
    async def _cleanup_contract_streams(self, contract_id: int) -> None:
        """Clean up all tracking data for contract streams"""
        self.active_streams.pop(contract_id, None)
    
    def _get_next_request_id(self) -> int:
        """Get next available request ID"""
        request_id = self.next_request_id
        self.next_request_id += 1
        return request_id
    
    # Event notification methods
    
    async def _notify_stream_started(self, contract_id: int, request_id: int) -> None:
        """Notify listeners of stream start"""
        for listener in self._listeners:
            try:
                await listener.on_stream_started(contract_id, request_id)
            except Exception as e:
                logger.error("Error notifying stream start listener: %s", e)
    
    async def _notify_stream_stopped(self, contract_id: int, request_id: int) -> None:
        """Notify listeners of stream stop"""
        for listener in self._listeners:
            try:
                await listener.on_stream_stopped(contract_id, request_id)
            except Exception as e:
                logger.error("Error notifying stream stop listener: %s", e)
    
    async def _notify_stream_error(self, contract_id: int, error: str) -> None:
        """Notify listeners of stream error"""
        for listener in self._listeners:
            try:
                await listener.on_stream_error(contract_id, error)
            except Exception as e:
                logger.error("Error notifying stream error listener: %s", e)
    
    def get_status(self) -> dict:
        """Get stream status (pure function)"""
        return {
            "total_streams": self.get_total_stream_count(),
            "active_contracts": len(self.active_streams),
            "stream_details": {
                contract_id: {
                    "stream_count": len(streams),
                    "tick_types": list(streams.keys())
                }
                for contract_id, streams in self.active_streams.items()
            }
        }