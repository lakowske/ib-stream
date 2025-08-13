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

from .config_v2 import TrackedContract
from .stream_manager import stream_manager, StreamHandler
from .streaming_app import StreamingApp

logger = logging.getLogger(__name__)


class BackgroundStreamManager:
    """Manages background streaming for tracked contracts"""
    
    def __init__(self, tracked_contracts: List[TrackedContract], 
                 reconnect_delay: int = 30):
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
        """Manage TWS connection and stream lifecycle"""
        was_connected = False
        
        while self.running:
            try:
                is_connected = self._is_connected()
                
                # Detect disconnection
                if was_connected and not is_connected:
                    logger.warning("TWS disconnection detected, clearing active streams")
                    await self._handle_disconnection()
                
                # Ensure TWS connection
                if not is_connected:
                    await self._establish_connection()
                    # After successful connection, force restart all streams
                    if self._is_connected():
                        logger.info("TWS reconnected, restarting all tracked streams")
                        await self._start_tracked_streams()
                
                # Start streams for new/missing contracts
                elif is_connected:
                    await self._start_tracked_streams()
                
                was_connected = is_connected
                
                # Wait before next check
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in connection management: %s", e)
                await asyncio.sleep(self.reconnect_delay)
    
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
        """Check if TWS connection is active"""
        return self.tws_app is not None and self.tws_app.is_connected()
    
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
            
            logger.info("Cleared all active streams after disconnection")
            
        except Exception as e:
            logger.error("Error handling disconnection: %s", e)
    
    async def _establish_connection(self) -> None:
        """Establish TWS connection for background streaming"""
        try:
            logger.info("Establishing TWS connection for background streaming...")
            
            # Create StreamingApp with background-specific client ID
            from ib_util import ConnectionConfig
            from .config_v2 import create_config
            
            # Use the same connection configuration as the main service
            main_config = create_config()
            
            # Use a different client ID for background streaming to avoid conflicts
            background_config = ConnectionConfig(
                host=main_config.host,
                ports=main_config.ports,
                client_id=main_config.client_id + 1000,  # Offset to avoid conflicts
                connection_timeout=main_config.connection_timeout
            )
            
            self.tws_app = StreamingApp(json_output=True, config=background_config)
            
            if not self.tws_app.connect_and_start():
                logger.error("Failed to connect to TWS for background streaming")
                self.tws_app = None
                return
            
            # Connection is already established and verified by connect_and_start()
            logger.info("Background TWS connection established successfully")
            
        except Exception as e:
            logger.error("Failed to establish TWS connection for background streaming: %s", e)
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
                    from .config_v2 import convert_v2_tick_type_to_tws_api
                    tws_tick_type = convert_v2_tick_type_to_tws_api(tick_type)
                    
                    # Start the stream with specific request ID
                    # Note: We need to manually set up the stream since StreamingApp.stream_contract
                    # uses its own request ID management
                    from ib_util import create_contract_by_id
                    
                    # Create contract using ib-util factory
                    contract = create_contract_by_id(contract_id)
                    
                    # Request contract details first
                    self.tws_app.reqContractDetails(request_id, contract)
                    
                    # Wait briefly for contract details
                    await asyncio.sleep(0.5)
                    
                    # Start tick-by-tick data with our request ID
                    if request_id in self.tws_app.contract_details_by_req_id:
                        contract_details = self.tws_app.contract_details_by_req_id[request_id]
                        self.tws_app.reqTickByTickData(
                            reqId=request_id,
                            contract=contract_details.contract,
                            tickType=tws_tick_type,
                            numberOfTicks=0,
                            ignoreSize=False
                        )
                    else:
                        logger.error("Could not get contract details for contract %d, request_id %d", 
                                   contract_id, request_id)
                        continue
                    
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


# Global background stream manager instance (initialized in api_server.py)
background_stream_manager: Optional[BackgroundStreamManager] = None