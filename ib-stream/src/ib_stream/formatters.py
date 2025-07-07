"""
Tick data formatters for different types of market data
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Any

from ibapi.common import TickAttribBidAsk, TickAttribLast

from .utils import format_timestamp


class TickFormatter(ABC):
    """Abstract base class for formatting tick data"""

    def __init__(self, timestamp: int):
        self.timestamp = timestamp
        self.formatted_time = format_timestamp(timestamp)

    @abstractmethod
    def to_json(self) -> Dict[str, Any]:
        """Return tick data as a dictionary for JSON output"""
        pass

    @abstractmethod
    def to_console(self) -> str:
        """Return tick data as a formatted string for console output"""
        pass


class TimeSalesFormatter(TickFormatter):
    """Formatter for Last and AllLast tick data (time & sales)"""

    def __init__(
        self,
        tick_type: int,
        timestamp: int,
        price: float,
        size: Decimal,
        exchange: str,
        special_conditions: str,
        tick_attrib: TickAttribLast,
    ):
        super().__init__(timestamp)
        self.tick_type_str = "Last" if tick_type == 1 else "AllLast"
        self.price = price
        self.size = size
        self.exchange = exchange
        self.special_conditions = special_conditions
        self.tick_attrib = tick_attrib

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": "time_sales",
            "tick_type": self.tick_type_str,
            "timestamp": self.formatted_time,
            "unix_time": self.timestamp,
            "price": self.price,
            "size": float(self.size),
            "exchange": self.exchange,
            "conditions": self.special_conditions,
            "past_limit": self.tick_attrib.pastLimit,
            "unreported": self.tick_attrib.unreported,
        }

    def to_console(self) -> str:
        conditions = f" [{self.special_conditions}]" if self.special_conditions else ""
        flags = []
        if self.tick_attrib.pastLimit:
            flags.append("PL")
        if self.tick_attrib.unreported:
            flags.append("UR")
        flag_str = f" ({','.join(flags)})" if flags else ""

        return f"{self.formatted_time} | {self.price:10.4f} | {self.size:10} | {self.exchange:^8} {conditions}{flag_str}"


class BidAskFormatter(TickFormatter):
    """Formatter for BidAsk tick data"""

    def __init__(
        self,
        timestamp: int,
        bid_price: float,
        ask_price: float,
        bid_size: Decimal,
        ask_size: Decimal,
        tick_attrib: TickAttribBidAsk,
    ):
        super().__init__(timestamp)
        self.bid_price = bid_price
        self.ask_price = ask_price
        self.bid_size = bid_size
        self.ask_size = ask_size
        self.tick_attrib = tick_attrib

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": "bid_ask",
            "timestamp": self.formatted_time,
            "unix_time": self.timestamp,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "bid_size": float(self.bid_size),
            "ask_size": float(self.ask_size),
            "bid_past_low": self.tick_attrib.bidPastLow,
            "ask_past_high": self.tick_attrib.askPastHigh,
        }

    def to_console(self) -> str:
        flags = []
        if self.tick_attrib.bidPastLow:
            flags.append("BPL")
        if self.tick_attrib.askPastHigh:
            flags.append("APH")
        flag_str = f" ({','.join(flags)})" if flags else ""

        return f"{self.formatted_time} | Bid: {self.bid_price:10.4f} x {self.bid_size:6} | Ask: {self.ask_price:10.4f} x {self.ask_size:6}{flag_str}"


class MidPointFormatter(TickFormatter):
    """Formatter for MidPoint tick data"""

    def __init__(self, timestamp: int, midpoint: float):
        super().__init__(timestamp)
        self.midpoint = midpoint

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": "midpoint",
            "timestamp": self.formatted_time,
            "unix_time": self.timestamp,
            "midpoint": self.midpoint,
        }

    def to_console(self) -> str:
        return f"{self.formatted_time} | MidPoint: {self.midpoint:10.4f}"
