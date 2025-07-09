"""Data models for IB-Studies."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class MarketQuote(BaseModel):
    """Represents current bid/ask quote."""

    timestamp: datetime
    bid_price: float = Field(ge=0)
    ask_price: float = Field(ge=0)
    bid_size: float = Field(ge=0)
    ask_size: float = Field(ge=0)

    @property
    def spread(self) -> float:
        """Calculate bid-ask spread."""
        return self.ask_price - self.bid_price

    @property
    def mid_price(self) -> float:
        """Calculate mid price."""
        return (self.bid_price + self.ask_price) / 2


class Trade(BaseModel):
    """Represents a single trade/transaction."""

    timestamp: datetime
    price: float = Field(ge=0)
    size: float = Field(gt=0)
    exchange: str = ""
    conditions: list[str] = Field(default_factory=list)

    @property
    def value(self) -> float:
        """Calculate trade value (price * size)."""
        return self.price * self.size


class DeltaPoint(BaseModel):
    """Represents a single delta calculation point."""

    timestamp: datetime
    trade: Trade
    quote: MarketQuote
    delta: float  # Positive for buys, negative for sells
    cumulative_delta: float

    @property
    def is_buy(self) -> bool:
        """Check if this was a buy order."""
        return self.delta > 0

    @property
    def is_sell(self) -> bool:
        """Check if this was a sell order."""
        return self.delta < 0

    @property
    def is_neutral(self) -> bool:
        """Check if this was neutral (inside spread)."""
        return self.delta == 0


class DeltaSummary(BaseModel):
    """Summary statistics for delta analysis."""

    window_seconds: int
    trade_count: int = 0
    total_buy_volume: float = 0
    total_sell_volume: float = 0
    total_neutral_volume: float = 0
    net_delta: float = 0
    cumulative_delta: float = 0

    @property
    def total_volume(self) -> float:
        """Calculate total volume traded."""
        return self.total_buy_volume + self.total_sell_volume + self.total_neutral_volume

    @property
    def buy_sell_ratio(self) -> Optional[float]:
        """Calculate buy/sell ratio."""
        if self.total_sell_volume == 0:
            return None if self.total_buy_volume == 0 else float('inf')
        return self.total_buy_volume / self.total_sell_volume

    @property
    def buy_percentage(self) -> float:
        """Calculate percentage of volume that was buying."""
        total = self.total_buy_volume + self.total_sell_volume
        if total == 0:
            return 0.0
        return (self.total_buy_volume / total) * 100


@dataclass
class StreamConfig:
    """Configuration for stream client."""

    base_url: str = "http://localhost:8001"
    timeout: Optional[int] = None
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 10
    heartbeat_interval: int = 30
    # Timezone for displaying timestamps in human-readable format
    # Can be a timezone name like "US/Eastern", "Europe/London", "UTC", etc.
    # Defaults to system local timezone if None
    display_timezone: Optional[str] = None


@dataclass
class StudyConfig:
    """Configuration for studies."""

    window_seconds: int = 60
    buffer_size: int = 10000
    decimal_places: int = 2

    # Delta-specific config
    neutral_zone_percent: float = 0.0  # Percentage of spread for neutral zone


# V2 Protocol Message Models

class V2BaseMessage(BaseModel):
    """Base v2 protocol message structure."""

    type: str
    stream_id: Optional[str] = None
    timestamp: str
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: Optional[dict[str, Any]] = None


class V2TickMessage(V2BaseMessage):
    """V2 tick message with tick data."""

    type: str = "tick"
    stream_id: str

    class Config:
        schema_extra = {
            "example": {
                "type": "tick",
                "stream_id": "265598_bid_ask_2025-01-08T15:30:00.123Z_abc123",
                "timestamp": "2025-01-08T15:30:00.123Z",
                "data": {
                    "tick_type": "bid_ask",
                    "bid_price": 175.25,
                    "ask_price": 175.26,
                    "bid_size": 500,
                    "ask_size": 300
                }
            }
        }


class V2ErrorMessage(V2BaseMessage):
    """V2 error message."""

    type: str = "error"

    class Config:
        schema_extra = {
            "example": {
                "type": "error",
                "stream_id": "265598_bid_ask_2025-01-08T15:30:00.123Z_abc123",
                "timestamp": "2025-01-08T15:30:00.123Z",
                "data": {
                    "code": "INVALID_CONTRACT",
                    "message": "Contract not found",
                    "recoverable": False
                }
            }
        }


class V2CompleteMessage(V2BaseMessage):
    """V2 stream complete message."""

    type: str = "complete"

    class Config:
        schema_extra = {
            "example": {
                "type": "complete",
                "stream_id": "265598_bid_ask_2025-01-08T15:30:00.123Z_abc123",
                "timestamp": "2025-01-08T15:30:00.123Z",
                "data": {
                    "reason": "timeout",
                    "total_ticks": 1247,
                    "duration_seconds": 300.45
                }
            }
        }


class V2InfoMessage(V2BaseMessage):
    """V2 info message."""

    type: str = "info"

    class Config:
        schema_extra = {
            "example": {
                "type": "info",
                "stream_id": "265598_bid_ask_2025-01-08T15:30:00.123Z_abc123",
                "timestamp": "2025-01-08T15:30:00.123Z",
                "data": {
                    "status": "active",
                    "tick_count": 125,
                    "uptime_seconds": 45.2
                }
            }
        }


class V2SubscribeMessage(BaseModel):
    """V2 WebSocket subscribe message."""

    type: str = "subscribe"
    id: str
    timestamp: str
    data: dict[str, Any]

    class Config:
        schema_extra = {
            "example": {
                "type": "subscribe",
                "id": "msg-123",
                "timestamp": "2025-01-08T15:30:00.123Z",
                "data": {
                    "contract_id": 265598,
                    "tick_types": ["bid_ask", "last"],
                    "config": {
                        "timeout_seconds": 300
                    }
                }
            }
        }


class V2SubscribedMessage(BaseModel):
    """V2 WebSocket subscribed confirmation message."""

    type: str = "subscribed"
    id: str
    timestamp: str
    data: dict[str, Any]

    class Config:
        schema_extra = {
            "example": {
                "type": "subscribed",
                "id": "msg-123",
                "timestamp": "2025-01-08T15:30:00.123Z",
                "data": {
                    "contract_id": 265598,
                    "streams": [
                        {
                            "tick_type": "bid_ask",
                            "stream_id": "265598_bid_ask_2025-01-08T15:30:00.123Z_abc123"
                        },
                        {
                            "tick_type": "last",
                            "stream_id": "265598_last_2025-01-08T15:30:00.123Z_def456"
                        }
                    ]
                }
            }
        }


class V2PingMessage(BaseModel):
    """V2 WebSocket ping message."""

    type: str = "ping"
    id: str
    timestamp: str

    class Config:
        schema_extra = {
            "example": {
                "type": "ping",
                "id": "msg-124",
                "timestamp": "2025-01-08T15:30:00.123Z"
            }
        }


class V2PongMessage(BaseModel):
    """V2 WebSocket pong message."""

    type: str = "pong"
    id: str
    timestamp: str

    class Config:
        schema_extra = {
            "example": {
                "type": "pong",
                "id": "msg-124",
                "timestamp": "2025-01-08T15:30:00.123Z"
            }
        }


# Union type for all v2 message types
V2Message = Union[
    V2TickMessage,
    V2ErrorMessage,
    V2CompleteMessage,
    V2InfoMessage,
    V2SubscribeMessage,
    V2SubscribedMessage,
    V2PingMessage,
    V2PongMessage
]
