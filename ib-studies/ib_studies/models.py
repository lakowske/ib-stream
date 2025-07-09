"""Data models for IB-Studies."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

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
    conditions: List[str] = Field(default_factory=list)
    
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


@dataclass
class StudyConfig:
    """Configuration for studies."""
    
    window_seconds: int = 60
    buffer_size: int = 10000
    decimal_places: int = 2
    
    # Delta-specific config
    neutral_zone_percent: float = 0.0  # Percentage of spread for neutral zone