"""
Background Stream Health Models

Data structures for comprehensive health monitoring of background streaming
with trading hours awareness and data staleness detection.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class StreamHealthStatus(Enum):
    """Health status for background streams"""
    HEALTHY = "HEALTHY"              # Receiving data within threshold during trading hours
    DEGRADED = "DEGRADED"           # Minor delays (>15min, <30min) during trading hours
    UNHEALTHY = "UNHEALTHY"         # No data >30min during trading hours, or connection issues
    OFF_HOURS = "OFF_HOURS"         # Markets closed, minimal/no data expected (healthy state)
    UNKNOWN = "UNKNOWN"             # Unable to determine status


class MarketStatus(Enum):
    """Market trading status"""
    OPEN = "OPEN"                   # Market is open for trading
    CLOSED = "CLOSED"               # Market is closed
    PRE_MARKET = "PRE_MARKET"       # Pre-market trading hours
    AFTER_HOURS = "AFTER_HOURS"     # After-hours trading
    UNKNOWN = "UNKNOWN"             # Unable to determine market status


@dataclass
class DataFreshnessCheck:
    """Data freshness assessment for a stream"""
    last_tick_timestamp: Optional[datetime] = None
    minutes_since_last_tick: Optional[float] = None
    is_stale: bool = False
    threshold_minutes: int = 15
    
    def __post_init__(self):
        """Calculate freshness metrics"""
        if self.last_tick_timestamp:
            now = datetime.now(timezone.utc)
            time_diff = now - self.last_tick_timestamp
            self.minutes_since_last_tick = time_diff.total_seconds() / 60
            self.is_stale = self.minutes_since_last_tick > self.threshold_minutes
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "last_tick": self.last_tick_timestamp.isoformat() if self.last_tick_timestamp else None,
            "minutes_ago": round(self.minutes_since_last_tick, 1) if self.minutes_since_last_tick is not None else None,
            "is_stale": self.is_stale,
            "threshold_minutes": self.threshold_minutes
        }


@dataclass 
class StreamInfo:
    """Information about an individual stream (e.g., bid_ask, last)"""
    tick_type: str
    is_active: bool
    request_id: Optional[int] = None
    last_tick_timestamp: Optional[datetime] = None
    error_count: int = 0
    last_error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "tick_type": self.tick_type,
            "active": self.is_active,
            "request_id": self.request_id,
            "last_tick": self.last_tick_timestamp.isoformat() if self.last_tick_timestamp else None,
            "error_count": self.error_count,
            "last_error": self.last_error_message
        }


@dataclass
class ContractTradingHours:
    """Trading hours information for a contract"""
    timezone: str
    regular_hours: str  # e.g., "09:30-16:00"
    extended_hours: Optional[str] = None  # e.g., "04:00-20:00"
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def is_expired(self, ttl_hours: int = 24) -> bool:
        """Check if trading hours data is expired"""
        now = datetime.now(timezone.utc)
        return (now - self.last_updated) > timedelta(hours=ttl_hours)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "timezone": self.timezone,
            "regular_hours": self.regular_hours,
            "extended_hours": self.extended_hours,
            "last_updated": self.last_updated.isoformat()
        }


@dataclass
class ContractHealthStatus:
    """Health status for a single background stream contract"""
    contract_id: int
    symbol: str
    status: StreamHealthStatus
    market_status: MarketStatus
    trading_hours: Optional[ContractTradingHours] = None
    data_staleness: Optional[DataFreshnessCheck] = None
    streams: Dict[str, StreamInfo] = field(default_factory=dict)
    connection_issues: List[str] = field(default_factory=list)
    last_health_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Additional metrics
    total_streams_expected: int = 0
    total_streams_active: int = 0
    buffer_hours: int = 1
    
    def calculate_overall_status(self, staleness_threshold_minutes: int = 15) -> StreamHealthStatus:
        """Calculate overall health status based on market conditions and data flow"""
        try:
            # If we have connection issues, mark as unhealthy
            if self.connection_issues:
                return StreamHealthStatus.UNHEALTHY
            
            # If market is closed, streams are expected to be quiet
            if self.market_status == MarketStatus.CLOSED:
                return StreamHealthStatus.OFF_HOURS
            
            # Check if all expected streams are active
            if self.total_streams_active < self.total_streams_expected:
                return StreamHealthStatus.DEGRADED
            
            # During trading hours, check data freshness
            if self.market_status == MarketStatus.OPEN:
                if self.data_staleness and self.data_staleness.is_stale:
                    # Severe staleness = unhealthy, minor = degraded
                    if self.data_staleness.minutes_since_last_tick and self.data_staleness.minutes_since_last_tick > 30:
                        return StreamHealthStatus.UNHEALTHY
                    else:
                        return StreamHealthStatus.DEGRADED
                
                return StreamHealthStatus.HEALTHY
            
            # Pre/after market - less strict requirements
            if self.market_status in [MarketStatus.PRE_MARKET, MarketStatus.AFTER_HOURS]:
                # Allow more staleness during extended hours
                if self.data_staleness and self.data_staleness.minutes_since_last_tick and self.data_staleness.minutes_since_last_tick > 60:
                    return StreamHealthStatus.DEGRADED
                return StreamHealthStatus.HEALTHY
            
            return StreamHealthStatus.UNKNOWN
            
        except Exception as e:
            logger.error("Error calculating health status for contract %d: %s", self.contract_id, e)
            return StreamHealthStatus.UNKNOWN
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "contract_id": self.contract_id,
            "symbol": self.symbol,
            "status": self.status.value,
            "market_status": self.market_status.value,
            "trading_hours": self.trading_hours.to_dict() if self.trading_hours else None,
            "data_staleness": self.data_staleness.to_dict() if self.data_staleness else None,
            "streams": {tick_type: stream.to_dict() for tick_type, stream in self.streams.items()},
            "connection_issues": self.connection_issues,
            "last_health_check": self.last_health_check.isoformat(),
            "metrics": {
                "total_streams_expected": self.total_streams_expected,
                "total_streams_active": self.total_streams_active,
                "buffer_hours": self.buffer_hours
            }
        }


@dataclass
class BackgroundStreamHealth:
    """Overall health status for all background streams"""
    overall_status: StreamHealthStatus
    contracts: Dict[int, ContractHealthStatus] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    summary: Dict[str, Any] = field(default_factory=dict)
    
    def calculate_overall_status(self) -> StreamHealthStatus:
        """Calculate overall health based on individual contract statuses"""
        if not self.contracts:
            return StreamHealthStatus.UNKNOWN
        
        statuses = [contract.status for contract in self.contracts.values()]
        
        # If any contracts are unhealthy, overall is unhealthy
        if StreamHealthStatus.UNHEALTHY in statuses:
            return StreamHealthStatus.UNHEALTHY
        
        # If any are degraded, overall is degraded
        if StreamHealthStatus.DEGRADED in statuses:
            return StreamHealthStatus.DEGRADED
        
        # If all are off-hours, overall is off-hours
        if all(status == StreamHealthStatus.OFF_HOURS for status in statuses):
            return StreamHealthStatus.OFF_HOURS
        
        # If we have healthy contracts, overall is healthy
        if StreamHealthStatus.HEALTHY in statuses:
            return StreamHealthStatus.HEALTHY
        
        return StreamHealthStatus.UNKNOWN
    
    def update_summary(self):
        """Update summary statistics"""
        total_contracts = len(self.contracts)
        status_counts = {}
        
        for status in StreamHealthStatus:
            status_counts[status.value.lower()] = sum(
                1 for contract in self.contracts.values() 
                if contract.status == status
            )
        
        self.summary = {
            "total_contracts": total_contracts,
            "status_distribution": status_counts,
            "last_updated": self.last_updated.isoformat()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        self.update_summary()
        
        return {
            "overall_status": self.overall_status.value,
            "contracts": {
                str(contract_id): contract.to_dict() 
                for contract_id, contract in self.contracts.items()
            },
            "summary": self.summary,
            "last_updated": self.last_updated.isoformat()
        }