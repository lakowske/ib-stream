"""
Streaming application for IB tick-by-tick data
"""

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from ibapi.client import EClient
from ibapi.common import TickAttribBidAsk, TickAttribLast
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

from .formatters import (
    BidAskFormatter,
    MidPointFormatter,
    TickFormatter,
    TimeSalesFormatter,
)

logger = logging.getLogger(__name__)


class StreamingApp(EWrapper, EClient):
    """Application for streaming tick-by-tick data from TWS."""

    def __init__(self, max_ticks: Optional[int] = None, json_output: bool = False,
                 tick_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
                 error_callback: Optional[Callable[[str, str], None]] = None,
                 complete_callback: Optional[Callable[[str, int], None]] = None):
        EClient.__init__(self, self)
        self.max_ticks = max_ticks
        self.json_output = json_output
        self.tick_count = 0
        self.req_id = 1000
        self.connected = False
        self.contract_details = None  # Keep for backward compatibility
        self.contract_details_by_req_id = {}  # Store contract details per request ID
        self.streaming_stopped = False

        # Callback functions for API server
        self.tick_callback = tick_callback
        self.error_callback = error_callback
        self.complete_callback = complete_callback

        # Set up signal handler for graceful shutdown only if not in callback mode
        if not self.tick_callback:
            signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, _signum, _frame):
        """Handle Ctrl+C for graceful shutdown."""
        if not self.json_output:
            print("\nShutting down stream...")
        self.cancelTickByTickData(self.req_id)
        self.disconnect()
        sys.exit(0)

    def error(self, reqId, errorCode, errorString, _advancedOrderRejectJson=""):
        """Handle errors from TWS."""
        try:
            if errorCode == 502:
                error_msg = "Couldn't connect to TWS. Make sure TWS/Gateway is running."
                logger.error(error_msg)
                if self.error_callback:
                    self.error_callback("CONNECTION_ERROR", error_msg)
            elif errorCode == 200:
                error_msg = "No security definition found for contract ID"
                logger.error(error_msg)
                if self.error_callback:
                    self.error_callback("CONTRACT_NOT_FOUND", error_msg)
            elif errorCode in [2104, 2106, 2158]:
                # Market data farm connection messages - can ignore
                logger.info(f"Connection status: {errorString}")
            else:
                error_msg = f"Error {errorCode}: {errorString} (ReqId: {reqId})"
                logger.error(error_msg)
                if self.error_callback:
                    self.error_callback(f"TWS_ERROR_{errorCode}", error_msg)
        except Exception as e:
            import traceback
            logger.error("Exception in error handler: %s\nTraceback:\n%s", e, traceback.format_exc())

    def nextValidId(self, orderId):
        """Called when connection is established."""
        self.connected = True
        logger.info(f"Connected. Next valid order ID: {orderId}")

    def contractDetails(self, reqId, contractDetails):
        """Receive contract details."""
        # Store contract details by request ID to avoid race conditions
        self.contract_details_by_req_id[reqId] = contractDetails
        # Keep backward compatibility
        self.contract_details = contractDetails
        contract = contractDetails.contract
        if not self.json_output:
            print(
                f"Streaming {contract.symbol} ({contract.secType}) - {contract.localSymbol}"
            )
            print(f"Exchange: {contract.exchange}, Currency: {contract.currency}")
            print("-" * 80)

    def contractDetailsEnd(self, _reqId):
        """Called when contract details are complete."""
        logger.info("Contract details received")

    def _process_tick(self, reqId: int, formatter: TickFormatter):
        """Central method to process any type of tick data with StreamManager routing"""
        
        # Get tick data as JSON
        tick_json = formatter.to_json()
        
        # First try to route through StreamManager for API server mode
        # Note: Storage is now handled in StreamManager in the async context
        try:
            from .stream_manager import stream_manager
            
            # Create event loop if we're in an async context
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule the async routing as a task
                    asyncio.create_task(stream_manager.route_tick_data(reqId, tick_json))
                    return
                else:
                    # Run the async method
                    asyncio.run(stream_manager.route_tick_data(reqId, tick_json))
                    return
            except RuntimeError:
                # No event loop, try to create one
                try:
                    asyncio.run(stream_manager.route_tick_data(reqId, tick_json))
                    return
                except Exception:
                    # Fall back to legacy mode
                    pass
        except ImportError:
            # StreamManager not available, fall back to legacy mode
            pass
        
        # Legacy mode for CLI usage and fallback
        if self.streaming_stopped:
            return

        self.tick_count += 1

        # Handle callback mode (API server)
        if self.tick_callback:
            self.tick_callback(tick_json)
        else:
            # Handle CLI mode
            if self.json_output:
                print(json.dumps(tick_json))
            else:
                print(formatter.to_console())

        # Check if we've reached the limit
        if self.max_ticks and self.tick_count >= self.max_ticks:
            self.streaming_stopped = True

            # Handle completion callback
            if self.complete_callback:
                self.complete_callback("limit_reached", self.tick_count)
            elif not self.json_output:
                print(f"\nReached limit of {self.max_ticks} ticks")

            self.cancelTickByTickData(reqId)

            # Only disconnect if not in callback mode (API server manages connections)
            if not self.tick_callback:
                # Small delay to allow cancel to process
                time.sleep(0.1)
                self.disconnect()

    def tickByTickAllLast(
        self,
        reqId: int,
        tickType: int,
        time: int,
        price: float,
        size: Decimal,
        tickAttribLast: TickAttribLast,
        exchange: str,
        specialConditions: str,
    ):
        """Handle Last and AllLast tick data (time & sales)."""
        formatter = TimeSalesFormatter(
            tick_type=tickType,
            timestamp=time,
            price=price,
            size=size,
            exchange=exchange,
            special_conditions=specialConditions,
            tick_attrib=tickAttribLast,
        )
        self._process_tick(reqId, formatter)

    def tickByTickBidAsk(
        self,
        reqId: int,
        time: int,
        bidPrice: float,
        askPrice: float,
        bidSize: Decimal,
        askSize: Decimal,
        tickAttribBidAsk: TickAttribBidAsk,
    ):
        """Handle BidAsk tick data."""
        formatter = BidAskFormatter(
            timestamp=time,
            bid_price=bidPrice,
            ask_price=askPrice,
            bid_size=bidSize,
            ask_size=askSize,
            tick_attrib=tickAttribBidAsk,
        )
        self._process_tick(reqId, formatter)

    def tickByTickMidPoint(self, reqId: int, time: int, midPoint: float):
        """Handle MidPoint tick data."""
        formatter = MidPointFormatter(timestamp=time, midpoint=midPoint)
        self._process_tick(reqId, formatter)

    def stream_contract(self, contract_id: int, tick_type: str = "Last"):
        """Start streaming tick-by-tick data for a contract."""
        # Create contract with just the ID
        contract = Contract()
        contract.conId = contract_id

        # Request contract details first
        self.reqContractDetails(self.req_id, contract)

        # Wait for contract details for this specific request ID
        timeout = 5
        start_time = time.time()
        while self.req_id not in self.contract_details_by_req_id and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        if self.req_id not in self.contract_details_by_req_id:
            if not self.json_output:
                print(f"Error: Could not find contract with ID {contract_id}")
            return

        # Get contract details for this specific request ID
        contract_details = self.contract_details_by_req_id[self.req_id]

        # Request tick-by-tick data using the correct contract
        self.reqTickByTickData(
            reqId=self.req_id,
            contract=contract_details.contract,
            tickType=tick_type,
            numberOfTicks=0,  # 0 means unlimited
            ignoreSize=False,
        )

        if not self.json_output:
            print(f"Streaming {tick_type} data... (Press Ctrl+C to stop)")
            if self.max_ticks:
                print(f"Will stop after {self.max_ticks} ticks")
            print()

    def cleanup_request(self, req_id):
        """Clean up data for a specific request ID."""
        if req_id in self.contract_details_by_req_id:
            del self.contract_details_by_req_id[req_id]
