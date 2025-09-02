"""
Background Stream Manager v2 - Unified Connection Architecture

This version uses the UnifiedConnectionManager instead of creating its own
separate IB connection, eliminating the dual-connection complexity.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from .config import TrackedContract
from .connection import UnifiedConnectionManager
from .connection.stream_registry import StreamType
from .stream_manager import StreamHandler
from .services.stream_health_service import StreamHealthService

logger = logging.getLogger(__name__)


@dataclass
class BackgroundStreamInfo:
    """Information about a background stream"""
    contract_id: int
    tick_type: str
    request_id: int
    handler: StreamHandler
    started_at: datetime
    last_data_at: Optional[datetime] = None
    error_count: int = 0


class BackgroundStreamManagerV2:
    """
    Background stream manager using unified connection architecture
    
    Key changes from v1:
    - Uses shared UnifiedConnectionManager instead of separate connection
    - No client ID offset logic (uses same client ID as main service)
    - Simplified connection management
    - Enhanced stream recovery through unified system
    """
    
    def __init__(self, 
                 tracked_contracts: List[TrackedContract],
                 connection_manager: UnifiedConnectionManager,
                 staleness_threshold_minutes: int = 15):
        """
        Initialize background stream manager
        
        Args:
            tracked_contracts: List of contracts to stream
            connection_manager: Shared connection manager
            staleness_threshold_minutes: Threshold for stale data detection
        """
        self.tracked_contracts = {c.contract_id: c for c in tracked_contracts if c.enabled}
        self.connection_manager = connection_manager
        self.staleness_threshold_minutes = staleness_threshold_minutes
        
        # Stream tracking
        self.background_streams: Dict[int, BackgroundStreamInfo] = {}  # request_id -> stream_info
        self.contract_streams: Dict[int, List[int]] = {}  # contract_id -> [request_ids]
        
        # Health monitoring
        self.health_service = StreamHealthService(staleness_threshold_minutes)
        
        # State management
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        logger.info("BackgroundStreamManager v2 initialized with %d contracts", 
                   len(self.tracked_contracts))
    
    async def start(self):
        """Start background streaming"""
        if self._running:
            logger.warning("Background streaming already running")
            return
        
        logger.info("Starting background streaming for %d contracts", 
                   len(self.tracked_contracts))
        
        self._running = True
        
        try:
            # Ensure connection is established
            streaming_app = await self.connection_manager.ensure_connection()
            
            # Start streams for all tracked contracts
            await self._start_all_streams(streaming_app)
            
            # Start health monitoring
            self._monitor_task = asyncio.create_task(self._health_monitor())
            
            logger.info("✅ Background streaming started successfully")
            
        except Exception as e:
            logger.error("Failed to start background streaming: %s", e)
            self._running = False
            raise
    
    async def stop(self):
        """Stop background streaming"""
        if not self._running:
            return
        
        logger.info("Stopping background streaming")
        self._running = False
        
        # Stop health monitoring
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        
        # Stop all streams
        await self._stop_all_streams()
        
        logger.info("Background streaming stopped")
    
    async def _start_all_streams(self, streaming_app):
        """Start streams for all tracked contracts"""
        for contract in self.tracked_contracts.values():
            try:
                await self._start_contract_streams(contract, streaming_app)
            except Exception as e:
                logger.error("Failed to start streams for contract %d: %s", 
                           contract.contract_id, e)
    
    async def _start_contract_streams(self, contract: TrackedContract, streaming_app):
        """Start streams for a specific contract"""
        contract_id = contract.contract_id
        
        logger.info("Starting streams for contract %d (%s): %s", 
                   contract_id, contract.symbol, contract.tick_types)
        
        request_ids = []
        
        for tick_type in contract.tick_types:
            try:
                # Create restart callback for this stream
                async def restart_callback(request_id, streaming_app, 
                                         contract=contract, tick_type=tick_type):
                    return await self._restart_stream(contract, tick_type, 
                                                    request_id, streaming_app)
                
                # Register stream with unified manager
                request_id = self.connection_manager.register_stream(
                    stream_type=StreamType.BACKGROUND,
                    contract_id=contract_id,
                    tick_type=tick_type,
                    restart_callback=restart_callback
                )
                
                # Create stream handler
                handler = StreamHandler(
                    request_id=request_id,
                    contract_id=contract_id,
                    tick_type=tick_type,
                    limit=None,  # Unlimited for background streams
                    timeout=None,  # Fixed: use 'timeout' not 'timeout_seconds'
                    tick_callback=self._handle_tick_data,
                    error_callback=self._handle_stream_error,
                    complete_callback=None  # Background streams don't complete
                )
                
                # Start the actual stream
                await self._start_stream(contract, tick_type, request_id, 
                                       handler, streaming_app)
                
                request_ids.append(request_id)
                
                logger.debug("Started background stream %d for %d (%s)", 
                           request_id, contract_id, tick_type)
                
            except Exception as e:
                logger.error("Failed to start %s stream for contract %d: %s", 
                           tick_type, contract_id, e)
        
        if request_ids:
            self.contract_streams[contract_id] = request_ids
            logger.info("✅ Started %d streams for contract %d", 
                       len(request_ids), contract_id)
    
    async def _start_stream(self, contract: TrackedContract, tick_type: str,
                          request_id: int, handler: StreamHandler, streaming_app):
        """Start an individual stream"""
        
        # Create contract object for IB API
        from ibapi.contract import Contract
        ib_contract = Contract()
        ib_contract.conId = contract.contract_id
        ib_contract.symbol = contract.symbol
        ib_contract.secType = "FUT"  # Assume futures for now
        ib_contract.exchange = "CME"
        
        # Register stream info
        stream_info = BackgroundStreamInfo(
            contract_id=contract.contract_id,
            tick_type=tick_type,
            request_id=request_id,
            handler=handler,
            started_at=datetime.now()
        )
        
        self.background_streams[request_id] = stream_info
        
        # Convert tick type to IB API format
        from .config import convert_v2_tick_type_to_tws_api
        tws_tick_type = convert_v2_tick_type_to_tws_api(tick_type)
        
        # Start tick-by-tick data stream
        streaming_app.reqTickByTickData(
            reqId=request_id,
            contract=ib_contract,
            tickType=tws_tick_type,  # Use converted tick type
            numberOfTicks=0,  # Unlimited
            ignoreSize=False
        )
        
        logger.debug("Requested tick-by-tick data for stream %d", request_id)
    
    async def _restart_stream(self, contract: TrackedContract, tick_type: str,
                            request_id: int, streaming_app):
        """Restart callback for stream recovery"""
        logger.info("Restarting background stream %d (%d:%s)", 
                   request_id, contract.contract_id, tick_type)
        
        try:
            # Get existing handler if available
            stream_info = self.background_streams.get(request_id)
            if stream_info:
                handler = stream_info.handler
            else:
                # Create new handler if needed
                handler = StreamHandler(
                    request_id=request_id,
                    contract_id=contract.contract_id,
                    tick_type=tick_type,
                    limit=None,
                    timeout=None,  # Fixed: use 'timeout' not 'timeout_seconds'
                    tick_callback=self._handle_tick_data,
                    error_callback=self._handle_stream_error,
                    complete_callback=None
                )
            
            # Restart the stream
            await self._start_stream(contract, tick_type, request_id, handler, streaming_app)
            
            logger.debug("✅ Restarted background stream %d", request_id)
            
        except Exception as e:
            logger.error("Failed to restart background stream %d: %s", request_id, e)
            raise
    
    async def _stop_all_streams(self):
        """Stop all background streams"""
        if not self.background_streams:
            return
        
        logger.info("Stopping %d background streams", len(self.background_streams))
        
        # Cancel all streams
        streaming_app = await self.connection_manager.ensure_connection()
        if streaming_app and streaming_app.isConnected():
            for request_id in list(self.background_streams.keys()):
                try:
                    streaming_app.cancelTickByTickData(request_id)
                    self.connection_manager.unregister_stream(request_id)
                except Exception as e:
                    logger.debug("Error canceling stream %d: %s", request_id, e)
        
        # Clear tracking
        self.background_streams.clear()
        self.contract_streams.clear()
        
        logger.info("All background streams stopped")
    
    def _handle_tick_data(self, tick_data):
        """Handle incoming tick data"""
        request_id = tick_data.get('request_id')
        if request_id in self.background_streams:
            stream_info = self.background_streams[request_id]
            stream_info.last_data_at = datetime.now()
            
            # Mark data received in connection manager
            self.connection_manager.mark_stream_data_received(request_id)
            
            # Update health service
            self.health_service.record_tick_data(
                contract_id=stream_info.contract_id,
                tick_type=stream_info.tick_type,
                timestamp=stream_info.last_data_at
            )
            
            logger.debug("Received tick data for stream %d", request_id)
    
    def _handle_stream_error(self, error_code: str, error_msg: str):
        """Handle stream errors"""
        logger.error("Background stream error %s: %s", error_code, error_msg)
        
        # Find affected stream(s) and increment error count
        # Note: Error doesn't include request_id, so we increment all
        for stream_info in self.background_streams.values():
            stream_info.error_count += 1
    
    async def _health_monitor(self):
        """Monitor stream health and trigger recovery if needed"""
        logger.info("Background stream health monitor started")
        
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                if not self.background_streams:
                    continue
                
                current_time = datetime.now()
                stale_threshold = current_time - timedelta(minutes=self.staleness_threshold_minutes)
                
                stale_streams = []
                for request_id, stream_info in self.background_streams.items():
                    if (stream_info.last_data_at is None or 
                        stream_info.last_data_at < stale_threshold):
                        stale_streams.append((request_id, stream_info))
                
                if stale_streams:
                    logger.warning("Found %d stale background streams", len(stale_streams))
                    # The unified connection manager will handle recovery
                    # through its own recovery system
                
                # Log health summary
                total_streams = len(self.background_streams)
                healthy_streams = total_streams - len(stale_streams)
                logger.info("Background stream health: %d/%d healthy", 
                           healthy_streams, total_streams)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health monitor error: %s", e)
                await asyncio.sleep(300)  # Wait 5 minutes on error
        
        logger.info("Background stream health monitor stopped")
    
    # Public interface methods
    
    def get_active_streams(self) -> Dict[int, Dict[str, any]]:
        """Get information about active background streams"""
        result = {}
        
        for request_id, stream_info in self.background_streams.items():
            result[request_id] = {
                "contract_id": stream_info.contract_id,
                "tick_type": stream_info.tick_type,
                "started_at": stream_info.started_at.isoformat(),
                "last_data_at": stream_info.last_data_at.isoformat() if stream_info.last_data_at else None,
                "error_count": stream_info.error_count,
                "is_stale": self._is_stream_stale(stream_info)
            }
        
        return result
    
    def get_health_summary(self) -> Dict[str, any]:
        """Get overall health summary"""
        if not self.background_streams:
            return {
                "status": "no_streams",
                "total_streams": 0,
                "healthy_streams": 0,
                "stale_streams": 0,
                "contracts_tracked": len(self.tracked_contracts)
            }
        
        total = len(self.background_streams)
        stale_count = sum(1 for s in self.background_streams.values() if self._is_stream_stale(s))
        healthy = total - stale_count
        
        return {
            "status": "healthy" if stale_count == 0 else "degraded" if healthy > 0 else "unhealthy",
            "total_streams": total,
            "healthy_streams": healthy,
            "stale_streams": stale_count,
            "contracts_tracked": len(self.tracked_contracts),
            "connection_client_id": self.connection_manager.client_id,
            "connection_state": self.connection_manager.state.value
        }
    
    def get_contract_health(self, contract_id: int) -> Dict[str, any]:
        """Get health information for a specific contract"""
        if contract_id not in self.contract_streams:
            return {"error": "Contract not tracked"}
        
        request_ids = self.contract_streams[contract_id]
        streams = [self.background_streams[req_id] for req_id in request_ids 
                  if req_id in self.background_streams]
        
        if not streams:
            return {"error": "No active streams for contract"}
        
        healthy_count = sum(1 for s in streams if not self._is_stream_stale(s))
        
        return {
            "contract_id": contract_id,
            "total_streams": len(streams),
            "healthy_streams": healthy_count,
            "stale_streams": len(streams) - healthy_count,
            "streams": [
                {
                    "request_id": s.request_id,
                    "tick_type": s.tick_type,
                    "last_data_at": s.last_data_at.isoformat() if s.last_data_at else None,
                    "is_stale": self._is_stream_stale(s),
                    "error_count": s.error_count
                }
                for s in streams
            ]
        }
    
    def _is_stream_stale(self, stream_info: BackgroundStreamInfo) -> bool:
        """Check if a stream is stale"""
        if stream_info.last_data_at is None:
            # No data received yet - stale if running for more than threshold
            runtime = datetime.now() - stream_info.started_at
            return runtime.total_seconds() > (self.staleness_threshold_minutes * 60)
        
        # Has received data - stale if last data is beyond threshold
        time_since_data = datetime.now() - stream_info.last_data_at
        return time_since_data.total_seconds() > (self.staleness_threshold_minutes * 60)