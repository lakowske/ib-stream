"""
Background Stream Manager for Tracked Contracts

This module manages persistent streaming for tracked contracts that should
continuously capture data to storage, even when no clients are connected.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

from ib_util import ConnectionConfig
from .config import TrackedContract, create_config
from .stream_manager import stream_manager, StreamHandler
from .streaming_app import StreamingApp
from .models.background_health import (
    BackgroundStreamHealth, ContractHealthStatus, StreamHealthStatus
)
from .services.stream_health_service import StreamHealthService

logger = logging.getLogger(__name__)


class BackgroundStreamManager:
    """Manages background streaming for tracked contracts"""
    
    def __init__(self, tracked_contracts: List[TrackedContract], 
                 reconnect_delay: int = 30,
                 staleness_threshold_minutes: int = 15):
        self.tracked_contracts = {c.contract_id: c for c in tracked_contracts if c.enabled}
        self.reconnect_delay = reconnect_delay
        
        # Active background streams
        self.active_streams: Dict[int, Dict[str, int]] = {}  # contract_id -> {tick_type: request_id}
        self.stream_handlers: Dict[int, StreamHandler] = {}  # request_id -> handler
        
        # TWS connection for background streaming
        self.tws_app: Optional[StreamingApp] = None
        self.connection_task: Optional[asyncio.Task] = None
        self.monitor_task: Optional[asyncio.Task] = None
        
        # State management
        self.running = False
        self.next_request_id = 60000  # Start background streams at higher request IDs
        
        # Data staleness monitoring
        self.last_data_timestamps: Dict[int, datetime] = {}  # contract_id -> last_data_time
        self.data_staleness_threshold = timedelta(minutes=5)  # Alert if no data for 5+ minutes
        
        # Health monitoring
        self.health_service = StreamHealthService()
        self.staleness_threshold_minutes = staleness_threshold_minutes
        self.last_health_check: Dict[int, datetime] = {}  # contract_id -> last_health_check
        
        # Enhanced connection monitoring
        self.last_connection_check = datetime.now(timezone.utc)
        self.market_data_farm_status: Dict[str, bool] = {}  # farm_name -> is_connected
        self.connection_check_interval = 2  # seconds - very frequent monitoring
        self.market_data_test_interval = 60  # seconds - periodic capability testing
        self.max_reconnect_delay = 30  # max delay between reconnection attempts
        self.connection_failures = 0  # track consecutive failures
        
        logger.info("BackgroundStreamManager initialized with %d tracked contracts", 
                   len(self.tracked_contracts))
    
    async def start(self) -> None:
        """Start background streaming for all tracked contracts"""
        if self.running:
            logger.warning("BackgroundStreamManager already running")
            return
        
        self.running = True
        logger.info("Starting background streaming for tracked contracts...")
        
        # Connect to stream manager for data staleness tracking
        from .stream_manager import stream_manager
        stream_manager.set_background_stream_manager(self)
        
        # Connect to error handler for farm status tracking
        from ib_util.error_handler import set_background_stream_manager
        set_background_stream_manager(self)
        
        # Start connection management task with exception monitoring
        self.connection_task = asyncio.create_task(self._manage_connection())
        self.connection_task.add_done_callback(self._task_exception_handler)
        logger.info("Started connection management task with exception monitoring")
        
        # Start monitoring task with exception monitoring
        self.monitor_task = asyncio.create_task(self._monitor_streams())
        self.monitor_task.add_done_callback(self._task_exception_handler)
        logger.info("Started stream monitoring task with exception monitoring")
        
        logger.info("Background streaming started with comprehensive error handling")
    
    async def stop(self) -> None:
        """Stop all background streaming"""
        if not self.running:
            return
        
        self.running = False
        logger.info("Stopping background streaming...")
        
        # Cancel tasks
        if self.connection_task:
            self.connection_task.cancel()
            try:
                await self.connection_task
            except asyncio.CancelledError:
                pass
        
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        # Stop all active streams
        await self._stop_all_streams()
        
        # Disconnect TWS
        if self.tws_app and self.tws_app.isConnected():
            self.tws_app.disconnect()
            self.tws_app = None
        
        logger.info("Background streaming stopped")
    
    async def _manage_connection(self) -> None:
        """Manage TWS connection and stream lifecycle with persistent reconnection"""
        was_connected = False
        last_connection_log = datetime.now(timezone.utc)
        
        logger.info("Starting connection management loop")
        
        while self.running:
            try:
                current_time = datetime.now(timezone.utc)
                is_connected = self._is_connected()
                
                # Log connection status periodically for monitoring
                if (current_time - last_connection_log).total_seconds() > 60:  # Every minute
                    logger.debug("Connection monitor: connected=%s, failures=%d", 
                                is_connected, self.connection_failures)
                    last_connection_log = current_time
                
                # Detect disconnection
                if was_connected and not is_connected:
                    self.connection_failures += 1
                    logger.error("TWS disconnection detected - failure count: %d, clearing active streams", 
                                self.connection_failures)
                    await self._handle_disconnection()
                elif is_connected and not was_connected:
                    self.connection_failures = 0  # Reset failure counter on successful connection
                    logger.info("TWS connection established successfully")
                
                # ALWAYS try to connect if not connected - this is the key fix
                if not is_connected:
                    # Calculate delay based on failure count (exponential backoff, capped)
                    delay = min(self.max_reconnect_delay, 5 + (self.connection_failures * 2))
                    logger.info("Attempting reconnection in %d seconds (failure count: %d)", 
                               delay, self.connection_failures + 1)
                    
                    await asyncio.sleep(delay)
                    await self._establish_connection()
                    
                    # Check if connection succeeded
                    if self._is_connected():
                        logger.info("TWS reconnected successfully, restarting all tracked streams")
                        self.connection_failures = 0
                        await self._start_tracked_streams()
                    else:
                        self.connection_failures += 1
                        logger.warning("Reconnection attempt failed (failure count: %d)", self.connection_failures)
                
                # Start streams for new/missing contracts if connected
                elif is_connected:
                    await self._start_tracked_streams()
                
                was_connected = is_connected
                
                # Wait before next check - shorter interval for better monitoring
                await asyncio.sleep(self.connection_check_interval)
                
            except asyncio.CancelledError:
                logger.info("🛑 Connection management loop cancelled")
                break
            except Exception as e:
                logger.error("💥 Critical error in connection management: %s", e, exc_info=True)
                # Don't let exceptions break the connection management loop
                await asyncio.sleep(self.connection_check_interval)
    
    async def _monitor_streams(self) -> None:
        """Monitor stream health and restart if needed"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                if not self._is_connected():
                    continue
                
                # Check if all expected streams are active and data is flowing
                for contract_id, contract in self.tracked_contracts.items():
                    if contract_id not in self.active_streams:
                        logger.warning("Missing streams for contract %d (%s), will restart", 
                                     contract_id, contract.symbol)
                        continue
                    
                    active_types = set(self.active_streams[contract_id].keys())
                    expected_types = set(contract.tick_types)
                    
                    if active_types != expected_types:
                        logger.warning("Stream mismatch for contract %d (%s): active=%s, expected=%s", 
                                     contract_id, contract.symbol, active_types, expected_types)
                        # Restart streams for this contract
                        await self._restart_contract_streams(contract_id)
                    
                    # Check data staleness - alert if no data received recently during potential trading hours
                    await self._check_data_staleness(contract_id, contract)
                
                # Log monitoring heartbeat every 10 cycles (10 minutes)
                if hasattr(self, '_monitor_cycle_count'):
                    self._monitor_cycle_count += 1
                else:
                    self._monitor_cycle_count = 1
                    
                if self._monitor_cycle_count % 10 == 0:
                    logger.info("Background stream monitor heartbeat - monitoring %d contracts", 
                              len(self.tracked_contracts))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in stream monitoring: %s", e)
    
    def _is_connected(self) -> bool:
        """Check if TWS connection is active and capable of market data"""
        # Basic socket connection check
        if not (self.tws_app and self.tws_app.is_connected()):
            return False
        
        # Test actual connectivity by attempting a simple request every 10 seconds (more frequent)
        current_time = datetime.now(timezone.utc)
        time_since_last_test = 0
        if hasattr(self, '_last_connection_test'):
            time_since_last_test = (current_time - self._last_connection_test).total_seconds()
        
        if not hasattr(self, '_last_connection_test') or time_since_last_test > 10:
            self._last_connection_test = current_time
            
            # Try to make a simple request to test if connection is actually alive
            # This forces the IB API to try sending data, which will trigger disconnection detection
            try:
                # Access the underlying IBConnection which has the IB API methods
                connection = getattr(self.tws_app, '_ib_connection', None)
                
                if connection and hasattr(connection, 'reqCurrentTime'):
                    # Request current time as a simple connectivity test
                    connection.reqCurrentTime()
                    
                    # Wait briefly to allow error 504 to be processed
                    time.sleep(0.1)
                    
                    # Check if the connection was marked as disconnected by error handler
                    if not connection.is_connected():
                        logger.warning("Connectivity test revealed disconnection")
                        return False
                        
                elif connection and hasattr(connection, 'reqServerVersion'):
                    # Alternative test request  
                    connection.reqServerVersion()
                    
                    # Wait briefly to allow error processing
                    time.sleep(0.1)
                    
                    if not connection.is_connected():
                        logger.warning("Connectivity test revealed disconnection")
                        return False
                        
                else:
                    logger.warning("Cannot send connectivity test - connection unavailable")
                    return False
            except Exception as e:
                logger.warning("Connection test failed: %s", e)
                return False
        
        # Enhanced check: Verify market data capability
        return self._has_market_data_capability()
    
    async def _handle_disconnection(self) -> None:
        """Handle TWS disconnection by cleaning up streams"""
        try:
            # Cancel all active tick requests
            for contract_id, tick_types in self.active_streams.items():
                for tick_type, request_id in tick_types.items():
                    try:
                        if self.tws_app and self.tws_app.isConnected():
                            self.tws_app.cancelTickByTickData(request_id)
                    except Exception as e:
                        logger.debug("Error canceling tick request %d: %s", request_id, e)
                    
                    # Unregister from stream manager
                    stream_manager.unregister_stream(request_id)
            
            # Clear all tracking dictionaries
            self.active_streams.clear()
            self.stream_handlers.clear()
            
            # Also clear the main app state active_streams if accessible
            try:
                from .app_lifecycle import get_app_state
                app_state = get_app_state()
                main_active_streams = app_state.get('active_streams', {})
                stream_lock = app_state.get('stream_lock')
                
                if stream_lock and main_active_streams:
                    with stream_lock:
                        if main_active_streams:
                            logger.info("Clearing %d orphaned main active streams after disconnection", len(main_active_streams))
                            main_active_streams.clear()
            except Exception as e:
                logger.debug("Could not clear main active streams: %s", e)
            
            logger.info("Cleared all active streams after disconnection")
            
        except Exception as e:
            logger.error("Error handling disconnection: %s", e)
    
    async def _establish_connection(self) -> None:
        """Establish TWS connection for background streaming with detailed logging"""
        try:
            logger.debug("Establishing TWS connection for background streaming")
            
            # Clean up existing connection if any
            if self.tws_app:
                try:
                    self.tws_app.disconnect()
                except Exception as e:
                    logger.debug("Error disconnecting old connection: %s", e)
                self.tws_app = None
            
            # Create StreamingApp with background-specific client ID
            # Use the same connection configuration as the main service
            main_config = create_config()
            
            # Use a different client ID for background streaming to avoid conflicts
            background_config = ConnectionConfig(
                host=main_config.host,
                ports=main_config.ports,
                client_id=main_config.client_id + 1000,  # Offset to avoid conflicts
                connection_timeout=main_config.connection_timeout
            )
            
            logger.debug("Attempting connection to %s:%s with client ID %d", 
                        background_config.host, background_config.ports, background_config.client_id)
            
            self.tws_app = StreamingApp(json_output=True, config=background_config)
            
            # Add disconnection callback to immediately detect disconnections
            if hasattr(self.tws_app, 'on_disconnected'):
                self.tws_app.on_disconnected = self._on_connection_lost
            
            connection_success = self.tws_app.connect_and_start()
            
            if not connection_success:
                logger.error("Failed to connect to TWS for background streaming")
                self.tws_app = None
                return
            
            # Connection is already established and verified by connect_and_start()
            logger.info("Background TWS connection established successfully")
            
        except Exception as e:
            logger.error("Failed to establish TWS connection for background streaming: %s", e, exc_info=True)
            self.tws_app = None
    
    def _on_connection_lost(self):
        """Callback when connection is lost"""
        logger.warning("Connection lost callback triggered")
        if self.tws_app:
            self.tws_app = None
    
    
    async def _start_tracked_streams(self) -> None:
        """Start streams for all tracked contracts"""
        for contract_id, contract in self.tracked_contracts.items():
            # Check if all expected streams are active
            needs_restart = False
            
            if contract_id not in self.active_streams:
                needs_restart = True
            else:
                # Verify all tick types are present
                active_types = set(self.active_streams[contract_id].keys())
                expected_types = set(contract.tick_types)
                if active_types != expected_types:
                    logger.info("Stream mismatch for contract %d: active=%s, expected=%s", 
                               contract_id, active_types, expected_types)
                    needs_restart = True
            
            if needs_restart:
                await self._start_contract_streams(contract_id, contract)
    
    async def _start_contract_streams(self, contract_id: int, contract: TrackedContract) -> None:
        """Start streams for a specific contract"""
        try:
            logger.info("Starting background streams for contract %d (%s): %s", 
                       contract_id, contract.symbol, contract.tick_types)
            
            contract_streams = {}
            
            for tick_type in contract.tick_types:
                request_id = self._get_next_request_id()
                
                # Create consistent stream_id for storage file organization
                # Format: bg_{contract_id}_{tick_type} (e.g., bg_711280073_bid_ask)
                stream_id = f"bg_{contract_id}_{tick_type}"
                
                # Create stream handler for this background stream
                handler = StreamHandler(
                    request_id=request_id,
                    contract_id=contract_id,
                    tick_type=tick_type,
                    limit=None,  # No limit for background streams
                    timeout=None,  # No timeout for background streams
                    tick_callback=None,  # No callback needed - storage is handled by StreamManager
                    error_callback=self._handle_stream_error,
                    complete_callback=self._handle_stream_complete,
                    stream_id=stream_id  # Set consistent stream_id for file organization
                )
                
                # Register with stream manager
                stream_manager.register_stream(handler)
                
                # Start TWS stream
                try:
                    # Convert v2 tick type to TWS format
                    from .config import convert_v2_tick_type_to_tws_api
                    tws_tick_type = convert_v2_tick_type_to_tws_api(tick_type)
                    
                    # Start the stream with specific request ID
                    # Note: We need to manually set up the stream since StreamingApp.stream_contract
                    # uses its own request ID management
                    
                    # Get complete contract information from ib-contract service
                    from .contract_client import get_contract_by_id
                    contract = await get_contract_by_id(contract_id)
                    
                    if contract is None:
                        logger.error("Could not get contract details for contract %d from ib-contract service", contract_id)
                        # Unregister failed handler
                        stream_manager.unregister_stream(request_id)
                        continue
                    
                    # Start tick-by-tick data with complete contract information
                    self.tws_app.reqTickByTickData(
                        reqId=request_id,
                        contract=contract,
                        tickType=tws_tick_type,
                        numberOfTicks=0,
                        ignoreSize=False
                    )
                    
                    contract_streams[tick_type] = request_id
                    self.stream_handlers[request_id] = handler
                    
                    logger.info("Started background stream: contract=%d, type=%s, request_id=%d", 
                               contract_id, tick_type, request_id)
                    
                except Exception as e:
                    logger.error("Failed to start stream for contract %d, type %s: %s", 
                               contract_id, tick_type, e)
                    # Unregister failed handler
                    stream_manager.unregister_stream(request_id)
            
            if contract_streams:
                self.active_streams[contract_id] = contract_streams
                logger.info("Background streams started for contract %d (%s): %d streams", 
                           contract_id, contract.symbol, len(contract_streams))
            
        except Exception as e:
            logger.error("Failed to start streams for contract %d (%s): %s", 
                        contract_id, contract.symbol, e)
    
    async def _restart_contract_streams(self, contract_id: int) -> None:
        """Restart streams for a specific contract"""
        logger.info("Restarting streams for contract %d", contract_id)
        
        # Stop existing streams
        if contract_id in self.active_streams:
            await self._stop_contract_streams(contract_id)
        
        # Start new streams
        if contract_id in self.tracked_contracts:
            await self._start_contract_streams(contract_id, self.tracked_contracts[contract_id])
    
    async def _stop_contract_streams(self, contract_id: int) -> None:
        """Stop streams for a specific contract"""
        if contract_id not in self.active_streams:
            return
        
        contract_streams = self.active_streams[contract_id]
        logger.info("Stopping background streams for contract %d: %d streams", 
                   contract_id, len(contract_streams))
        
        for tick_type, request_id in contract_streams.items():
            try:
                # Cancel TWS stream
                if self.tws_app and self.tws_app.isConnected():
                    self.tws_app.cancelTickByTickData(request_id)
                
                # Unregister from stream manager
                stream_manager.unregister_stream(request_id)
                
                # Clean up handler
                if request_id in self.stream_handlers:
                    del self.stream_handlers[request_id]
                
            except Exception as e:
                logger.error("Error stopping stream %d for contract %d: %s", 
                           request_id, contract_id, e)
        
        del self.active_streams[contract_id]
    
    async def _stop_all_streams(self) -> None:
        """Stop all active background streams"""
        contract_ids = list(self.active_streams.keys())
        for contract_id in contract_ids:
            await self._stop_contract_streams(contract_id)
    
    def _get_next_request_id(self) -> int:
        """Get next request ID for background streams"""
        request_id = self.next_request_id
        self.next_request_id += 1
        return request_id
    
    def _task_exception_handler(self, task: asyncio.Task) -> None:
        """Handle exceptions from background tasks"""
        if task.cancelled():
            logger.info("Background task was cancelled: %s", task.get_name())
            return
            
        exception = task.exception()
        if exception is not None:
            logger.error("CRITICAL: Background task failed with exception: %s", exception, exc_info=exception)
            logger.error("Task name: %s", task.get_name())
            
            # Attempt to restart the failed task if we're still running
            if self.running:
                asyncio.create_task(self._restart_failed_task(task))
        else:
            logger.warning("Background task completed unexpectedly without exception: %s", task.get_name())
            
    async def _restart_failed_task(self, failed_task: asyncio.Task) -> None:
        """Restart a failed background task"""
        try:
            task_name = failed_task.get_name()
            logger.info("Attempting to restart failed task: %s", task_name)
            
            # Wait a moment before restarting to avoid rapid restart loops
            await asyncio.sleep(5)
            
            # Restart based on task type
            if self.connection_task and self.connection_task == failed_task:
                logger.info("Restarting connection management task")
                self.connection_task = asyncio.create_task(self._manage_connection())
                self.connection_task.add_done_callback(self._task_exception_handler)
                
            elif self.monitor_task and self.monitor_task == failed_task:
                logger.info("Restarting stream monitoring task")
                self.monitor_task = asyncio.create_task(self._monitor_streams())
                self.monitor_task.add_done_callback(self._task_exception_handler)
                
        except Exception as e:
            logger.error("Failed to restart background task: %s", e)
    
    async def _check_data_staleness(self, contract_id: int, contract: TrackedContract) -> None:
        """Check if data is stale for a contract and log warnings"""
        now = datetime.now(timezone.utc)
        last_data_time = self.last_data_timestamps.get(contract_id)
        
        if last_data_time is None:
            # No data received yet - this might be expected if streams just started
            if contract_id in self.active_streams:
                # Only warn if streams have been active for more than staleness threshold
                logger.debug("No data recorded yet for contract %d (%s)", contract_id, contract.symbol)
            return
            
        time_since_data = now - last_data_time
        
        # Alert if data is stale beyond threshold
        if time_since_data > self.data_staleness_threshold:
            logger.warning("STALE DATA: Contract %d (%s) has not received data for %s (threshold: %s)",
                          contract_id, contract.symbol, time_since_data, self.data_staleness_threshold)
            
            # If data is very stale (30+ minutes), consider restarting streams
            if time_since_data > timedelta(minutes=30):
                logger.error("VERY STALE DATA: Restarting streams for contract %d (%s) - no data for %s",
                           contract_id, contract.symbol, time_since_data)
                await self._restart_contract_streams(contract_id)
    
    def update_data_timestamp(self, contract_id: int) -> None:
        """Update the last data timestamp for a contract"""
        self.last_data_timestamps[contract_id] = datetime.now(timezone.utc)
        logger.debug("Updated data timestamp for contract %d", contract_id)
    
    def _has_market_data_capability(self) -> bool:
        """Check if TWS has market data capability beyond basic socket connection"""
        try:
            # If we have no tracked market data farm status, assume connected for now
            if not self.market_data_farm_status:
                return True
                
            # Check if critical market data farms are connected
            critical_farms = ['usfarm', 'usfuture', 'cashfarm']
            for farm in critical_farms:
                if farm in self.market_data_farm_status:
                    if self.market_data_farm_status[farm]:
                        return True  # At least one critical farm is connected
            
            # If we have farm status but none of the critical ones are connected
            if self.market_data_farm_status:
                logger.warning("No critical market data farms connected: %s", 
                             self.market_data_farm_status)
                return False
                
            # Default to true if we can't determine farm status
            return True
            
        except Exception as e:
            logger.error("Error checking market data capability: %s", e)
            return True  # Fail open - assume connected to avoid false disconnections
    
    def update_market_data_farm_status(self, farm_name: str, is_connected: bool) -> None:
        """Update market data farm connection status"""
        previous_status = self.market_data_farm_status.get(farm_name, None)
        self.market_data_farm_status[farm_name] = is_connected
        
        if previous_status is not None and previous_status != is_connected:
            status_text = "connected" if is_connected else "disconnected"
            logger.info("Market data farm %s status changed: %s", farm_name, status_text)
            
            # If a critical farm disconnected, log as warning
            if not is_connected and farm_name in ['usfarm', 'usfuture', 'cashfarm']:
                logger.warning("CRITICAL: Market data farm %s disconnected", farm_name)
    
    async def _test_market_data_capability(self) -> bool:
        """Periodically test actual market data capability"""
        try:
            # This could be enhanced to make a test market data request
            # For now, we rely on farm status monitoring
            return self._has_market_data_capability()
            
        except Exception as e:
            logger.error("Error testing market data capability: %s", e)
            return False
    
    async def _handle_stream_error(self, error_code: str, error_message: str) -> None:
        """Handle stream errors"""
        logger.warning("Background stream error: %s - %s", error_code, error_message)
    
    async def _handle_stream_complete(self, reason: str, total_ticks: int) -> None:
        """Handle stream completion (should not happen for background streams)"""
        logger.warning("Background stream completed unexpectedly: %s (ticks: %d)", reason, total_ticks)
    
    def get_status(self) -> Dict:
        """Get status of background streaming"""
        contract_status = {}
        for contract_id, contract in self.tracked_contracts.items():
            active_streams = self.active_streams.get(contract_id, {})
            contract_status[contract_id] = {
                "symbol": contract.symbol,
                "enabled": contract.enabled,
                "expected_tick_types": contract.tick_types,
                "active_tick_types": list(active_streams.keys()),
                "stream_count": len(active_streams),
                "buffer_hours": contract.buffer_hours
            }
        
        return {
            "running": self.running,
            "tws_connected": self._is_connected(),
            "total_contracts": len(self.tracked_contracts),
            "active_contracts": len(self.active_streams),
            "total_streams": sum(len(streams) for streams in self.active_streams.values()),
            "contracts": contract_status
        }
    
    def get_tracked_contract_ids(self) -> Set[int]:
        """Get set of tracked contract IDs"""
        return set(self.tracked_contracts.keys())
    
    def is_contract_tracked(self, contract_id: int) -> bool:
        """Check if a contract is being tracked"""
        return contract_id in self.tracked_contracts
    
    def get_contract_buffer_hours(self, contract_id: int) -> Optional[int]:
        """Get buffer hours for a tracked contract"""
        contract = self.tracked_contracts.get(contract_id)
        return contract.buffer_hours if contract else None
    
    async def get_comprehensive_health(self) -> BackgroundStreamHealth:
        """
        Get comprehensive health status for all tracked contracts
        
        Returns:
            BackgroundStreamHealth with detailed per-contract assessments
        """
        try:
            health = BackgroundStreamHealth(
                overall_status=StreamHealthStatus.UNKNOWN,
                contracts={},
                last_updated=datetime.now(timezone.utc)
            )
            
            # Assess health for each tracked contract
            for contract_id, contract in self.tracked_contracts.items():
                try:
                    contract_health = await self.health_service.assess_contract_health(
                        contract_id=contract_id,
                        symbol=contract.symbol,
                        expected_streams=contract.tick_types,
                        active_streams=self.active_streams.get(contract_id, {}),
                        stream_handlers=self.stream_handlers,
                        last_data_timestamps=self.last_data_timestamps,
                        staleness_threshold_minutes=self.staleness_threshold_minutes,
                        buffer_hours=contract.buffer_hours
                    )
                    
                    health.contracts[contract_id] = contract_health
                    self.last_health_check[contract_id] = datetime.now(timezone.utc)
                    
                except Exception as e:
                    logger.error("Error assessing health for contract %d: %s", contract_id, e)
                    # Create minimal health status for failed assessment
                    health.contracts[contract_id] = ContractHealthStatus(
                        contract_id=contract_id,
                        symbol=contract.symbol,
                        status=StreamHealthStatus.UNKNOWN,
                        market_status=await self.health_service.get_contract_market_status(contract_id),
                        connection_issues=[f"Health assessment failed: {str(e)}"]
                    )
            
            # Calculate overall health status
            health.overall_status = health.calculate_overall_status()
            
            logger.debug("Comprehensive health check completed: %s", health.overall_status.value)
            return health
            
        except Exception as e:
            logger.error("Error performing comprehensive health check: %s", e)
            # Return minimal health status
            return BackgroundStreamHealth(
                overall_status=StreamHealthStatus.UNKNOWN,
                contracts={},
                last_updated=datetime.now(timezone.utc)
            )
    
    async def get_contract_health(self, contract_id: int) -> Optional[ContractHealthStatus]:
        """
        Get health status for a specific contract
        
        Args:
            contract_id: IB contract ID
            
        Returns:
            ContractHealthStatus or None if contract not tracked
        """
        if contract_id not in self.tracked_contracts:
            return None
        
        try:
            contract = self.tracked_contracts[contract_id]
            
            contract_health = await self.health_service.assess_contract_health(
                contract_id=contract_id,
                symbol=contract.symbol,
                expected_streams=contract.tick_types,
                active_streams=self.active_streams.get(contract_id, {}),
                stream_handlers=self.stream_handlers,
                last_data_timestamps=self.last_data_timestamps,
                staleness_threshold_minutes=self.staleness_threshold_minutes,
                buffer_hours=contract.buffer_hours
            )
            
            self.last_health_check[contract_id] = datetime.now(timezone.utc)
            
            logger.debug("Health check for contract %d (%s): %s", 
                        contract_id, contract.symbol, contract_health.status.value)
            
            return contract_health
            
        except Exception as e:
            logger.error("Error getting health for contract %d: %s", contract_id, e)
            return None
    
    def set_staleness_threshold(self, minutes: int):
        """Set the staleness threshold for health monitoring"""
        if minutes > 0:
            self.staleness_threshold_minutes = minutes
            logger.info("Staleness threshold updated to %d minutes", minutes)
        else:
            logger.warning("Invalid staleness threshold: %d minutes", minutes)
    
    def get_health_summary(self) -> Dict[str, any]:
        """
        Get a quick summary of stream health status
        
        Returns:
            Dictionary with health summary statistics
        """
        try:
            now = datetime.now(timezone.utc)
            total_contracts = len(self.tracked_contracts)
            active_contracts = len(self.active_streams)
            
            # Check data staleness
            stale_contracts = 0
            for contract_id, last_data_time in self.last_data_timestamps.items():
                if last_data_time:
                    minutes_since_data = (now - last_data_time).total_seconds() / 60
                    if minutes_since_data > self.staleness_threshold_minutes:
                        stale_contracts += 1
            
            return {
                "total_contracts": total_contracts,
                "active_contracts": active_contracts,
                "stale_contracts": stale_contracts,
                "healthy_contracts": active_contracts - stale_contracts,
                "staleness_threshold_minutes": self.staleness_threshold_minutes,
                "tws_connected": self._is_connected(),
                "last_updated": now.isoformat()
            }
            
        except Exception as e:
            logger.error("Error generating health summary: %s", e)
            return {
                "error": str(e),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }


# Global background stream manager instance (initialized in api_server.py)
background_stream_manager: Optional[BackgroundStreamManager] = None