"""
Streaming application for IB tick-by-tick data
"""

import json
import logging
import signal
import sys
from decimal import Decimal
from typing import Optional

from ibapi.client import EClient
from ibapi.common import TickAttribBidAsk, TickAttribLast
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

from .utils import format_timestamp

logger = logging.getLogger(__name__)


class StreamingApp(EWrapper, EClient):
    """Application for streaming tick-by-tick data from TWS."""

    def __init__(self, max_ticks: Optional[int] = None, json_output: bool = False):
        EClient.__init__(self, self)
        self.max_ticks = max_ticks
        self.json_output = json_output
        self.tick_count = 0
        self.req_id = 1000
        self.connected = False
        self.contract_details = None
        self.streaming_stopped = False

        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C for graceful shutdown."""
        if not self.json_output:
            print("\nShutting down stream...")
        self.cancelTickByTickData(self.req_id)
        self.disconnect()
        sys.exit(0)

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        """Handle errors from TWS."""
        if errorCode == 502:
            logger.error("Couldn't connect to TWS. Make sure TWS/Gateway is running.")
        elif errorCode == 200:
            logger.error("No security definition found for contract ID")
        elif errorCode in [2104, 2106, 2158]:
            # Market data farm connection messages - can ignore
            logger.info(f"Connection status: {errorString}")
        else:
            logger.error(f"Error {errorCode}: {errorString} (ReqId: {reqId})")

    def nextValidId(self, orderId):
        """Called when connection is established."""
        self.connected = True
        logger.info(f"Connected. Next valid order ID: {orderId}")

    def contractDetails(self, reqId, contractDetails):
        """Receive contract details."""
        self.contract_details = contractDetails
        contract = contractDetails.contract
        if not self.json_output:
            print(
                f"Streaming {contract.symbol} ({contract.secType}) - {contract.localSymbol}"
            )
            print(f"Exchange: {contract.exchange}, Currency: {contract.currency}")
            print("-" * 80)

    def contractDetailsEnd(self, reqId):
        """Called when contract details are complete."""
        logger.info("Contract details received")

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
        if self.streaming_stopped:
            return
        self.tick_count += 1

        timestamp = format_timestamp(time)
        tick_type_str = "Last" if tickType == 1 else "AllLast"

        if self.json_output:
            data = {
                "type": "time_sales",
                "tick_type": tick_type_str,
                "timestamp": timestamp,
                "unix_time": time,
                "price": price,
                "size": float(size),
                "exchange": exchange,
                "conditions": specialConditions,
                "past_limit": tickAttribLast.pastLimit,
                "unreported": tickAttribLast.unreported,
            }
            print(json.dumps(data))
        else:
            conditions = f" [{specialConditions}]" if specialConditions else ""
            flags = []
            if tickAttribLast.pastLimit:
                flags.append("PL")
            if tickAttribLast.unreported:
                flags.append("UR")
            flag_str = f" ({','.join(flags)})" if flags else ""

            print(
                f"{timestamp} | {price:10.4f} | {size:10} | {exchange:^8} {conditions}{flag_str}"
            )

        # Check if we've reached the limit
        if self.max_ticks and self.tick_count >= self.max_ticks:
            self.streaming_stopped = True
            if not self.json_output:
                print(f"\nReached limit of {self.max_ticks} ticks")
            self.cancelTickByTickData(reqId)
            # Small delay to allow cancel to process
            import time
            time.sleep(0.1)
            self.disconnect()

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
        if self.streaming_stopped:
            return
        self.tick_count += 1

        timestamp = format_timestamp(time)

        if self.json_output:
            data = {
                "type": "bid_ask",
                "timestamp": timestamp,
                "unix_time": time,
                "bid_price": bidPrice,
                "ask_price": askPrice,
                "bid_size": float(bidSize),
                "ask_size": float(askSize),
                "bid_past_low": tickAttribBidAsk.bidPastLow,
                "ask_past_high": tickAttribBidAsk.askPastHigh,
            }
            print(json.dumps(data))
        else:
            flags = []
            if tickAttribBidAsk.bidPastLow:
                flags.append("BPL")
            if tickAttribBidAsk.askPastHigh:
                flags.append("APH")
            flag_str = f" ({','.join(flags)})" if flags else ""

            print(
                f"{timestamp} | Bid: {bidPrice:10.4f} x {bidSize:6} | Ask: {askPrice:10.4f} x {askSize:6}{flag_str}"
            )

        # Check if we've reached the limit
        if self.max_ticks and self.tick_count >= self.max_ticks:
            self.streaming_stopped = True
            if not self.json_output:
                print(f"\nReached limit of {self.max_ticks} ticks")
            self.cancelTickByTickData(reqId)
            # Small delay to allow cancel to process
            import time
            time.sleep(0.1)
            self.disconnect()

    def tickByTickMidPoint(self, reqId: int, time: int, midPoint: float):
        """Handle MidPoint tick data."""
        if self.streaming_stopped:
            return
        self.tick_count += 1

        timestamp = format_timestamp(time)

        if self.json_output:
            data = {
                "type": "midpoint",
                "timestamp": timestamp,
                "unix_time": time,
                "midpoint": midPoint,
            }
            print(json.dumps(data))
        else:
            print(f"{timestamp} | MidPoint: {midPoint:10.4f}")

        # Check if we've reached the limit
        if self.max_ticks and self.tick_count >= self.max_ticks:
            self.streaming_stopped = True
            if not self.json_output:
                print(f"\nReached limit of {self.max_ticks} ticks")
            self.cancelTickByTickData(reqId)
            # Small delay to allow cancel to process
            import time
            time.sleep(0.1)
            self.disconnect()

    def stream_contract(self, contract_id: int, tick_type: str = "Last"):
        """Start streaming tick-by-tick data for a contract."""
        # Create contract with just the ID
        contract = Contract()
        contract.conId = contract_id

        # Request contract details first
        self.reqContractDetails(self.req_id, contract)

        # Wait for contract details
        import time

        timeout = 5
        start_time = time.time()
        while self.contract_details is None and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        if self.contract_details is None:
            if not self.json_output:
                print(f"Error: Could not find contract with ID {contract_id}")
            return

        # Request tick-by-tick data
        self.reqTickByTickData(
            reqId=self.req_id,
            contract=self.contract_details.contract,
            tickType=tick_type,
            numberOfTicks=0,  # 0 means unlimited
            ignoreSize=False,
        )

        if not self.json_output:
            print(f"Streaming {tick_type} data... (Press Ctrl+C to stop)")
            if self.max_ticks:
                print(f"Will stop after {self.max_ticks} ticks")
            print()
