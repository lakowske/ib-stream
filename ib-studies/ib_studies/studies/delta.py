"""Delta study implementation for analyzing order flow."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ib_studies.models import DeltaPoint, DeltaSummary, MarketQuote, StudyConfig, Trade
from ib_studies.studies.base import BaseStudy

logger = logging.getLogger(__name__)


class DeltaStudy(BaseStudy):
    """
    Delta study measures buying and selling pressure by tracking trades 
    relative to the bid-ask spread.
    """
    
    def __init__(self, config: Optional[StudyConfig] = None):
        """Initialize delta study."""
        super().__init__(config)
        self.current_quote: Optional[MarketQuote] = None
        self.delta_buffer: List[DeltaPoint] = []
        self.cumulative_delta: float = 0
        self.last_price: Optional[float] = None
        # Track last known bid/ask for when current_quote is None
        self.last_known_quote: Optional[MarketQuote] = None
        
    @property
    def required_tick_types(self) -> List[str]:
        """Delta study requires bid/ask quotes and trade data."""
        return ["BidAsk", "Last", "AllLast"]
    
    def process_tick(self, tick_type: str, data: Dict[str, Any], stream_id: str = "", timestamp: str = "") -> Optional[Dict[str, Any]]:
        """Process incoming v2 protocol tick data."""
        self.increment_tick_count()
        logger.debug("DeltaStudy.process_tick: tick_type=%s, stream_id=%s, timestamp=%s, data=%s", 
                    tick_type, stream_id, timestamp, data)
        
        try:
            if tick_type in ["BidAsk", "bid_ask"]:
                logger.debug("Processing BidAsk tick")
                self._process_bid_ask(data, stream_id, timestamp)
                return None  # No output for quote updates
            elif tick_type in ["Last", "AllLast", "last", "all_last", "time_sales"]:
                logger.debug("Processing trade tick: %s", tick_type)
                result = self._process_trade(data, tick_type, stream_id, timestamp)
                logger.debug("Trade processing result: %s", result)
                return result
            else:
                logger.debug("Ignoring tick type: %s", tick_type)
                return None
        except Exception as e:
            logger.error("Error processing tick: %s", e, exc_info=True)
            return None
    
    def _process_bid_ask(self, data: Dict[str, Any], stream_id: str = "", timestamp: str = "") -> None:
        """Update current market quote from v2 protocol."""
        try:
            self.current_quote = MarketQuote(
                timestamp=self._parse_timestamp(data, timestamp),
                bid_price=float(data.get('bid_price', 0)),
                ask_price=float(data.get('ask_price', 0)),
                bid_size=float(data.get('bid_size', 0)),
                ask_size=float(data.get('ask_size', 0))
            )
            # Store as last known quote if it has valid prices
            if self.current_quote.bid_price > 0 and self.current_quote.ask_price > 0:
                self.last_known_quote = self.current_quote
            logger.debug("Updated v2 quote (stream_id=%s): bid=%.2f, ask=%.2f", 
                        stream_id, self.current_quote.bid_price, 
                        self.current_quote.ask_price)
        except (KeyError, ValueError) as e:
            logger.error("Invalid bid/ask data: %s", e)
    
    def _process_trade(self, data: Dict[str, Any], tick_type: str, stream_id: str = "", timestamp: str = "") -> Optional[Dict[str, Any]]:
        """Process trade and calculate delta from v2 protocol."""
        # For futures without bid/ask data, we can still calculate delta
        # using price direction (uptick/downtick rule)
        
        try:
            # Handle conditions - convert string to list if needed
            conditions = data.get('conditions', [])
            if isinstance(conditions, str):
                conditions = [conditions] if conditions else []
            
            trade = Trade(
                timestamp=self._parse_timestamp(data, timestamp),
                price=float(data.get('price', 0)),
                size=float(data.get('size', 0)),
                exchange=data.get('exchange', ''),
                conditions=conditions
            )
            
            logger.debug("Created trade: price=%.2f, size=%.2f", trade.price, trade.size)
            
            # Calculate delta
            if self.current_quote:
                # Use bid/ask if available
                logger.debug("Using bid/ask calculation: bid=%.2f, ask=%.2f", 
                           self.current_quote.bid_price, self.current_quote.ask_price)
                delta = self._calculate_delta(
                    trade.price,
                    self.current_quote.bid_price,
                    self.current_quote.ask_price,
                    trade.size
                )
            else:
                # Use uptick/downtick rule for futures
                logger.debug("Using uptick/downtick rule, last_price=%s", self.last_price)
                delta = self._calculate_delta_from_price_direction(trade)
            
            logger.debug("Calculated delta: %.2f, cumulative: %.2f", delta, self.cumulative_delta + delta)
            self.cumulative_delta += delta
            
            # Create delta point (use last known quote if current quote not available)
            quote = self.current_quote or self.last_known_quote or MarketQuote(
                timestamp=trade.timestamp,
                bid_price=0.0,
                ask_price=0.0,
                bid_size=0.0,
                ask_size=0.0
            )
            
            delta_point = DeltaPoint(
                timestamp=trade.timestamp,
                trade=trade,
                quote=quote,
                delta=delta,
                cumulative_delta=self.cumulative_delta
            )
            
            self.delta_buffer.append(delta_point)
            
            # Cleanup old data
            self.delta_buffer = self.cleanup_old_data(
                self.delta_buffer, 
                self.config.window_seconds
            )
            
            # Return current state
            return self._create_output(delta_point, stream_id, timestamp)
            
        except (KeyError, ValueError) as e:
            logger.error("Invalid trade data: %s", e)
            return None
    
    def _calculate_delta(self, trade_price: float, bid_price: float, 
                        ask_price: float, trade_size: float) -> float:
        """
        Calculate delta for a single trade.
        
        Returns:
            positive value: buying pressure
            negative value: selling pressure
            zero: neutral/unknown
        """
        # Handle edge cases
        if bid_price <= 0 or ask_price <= 0 or trade_size <= 0:
            return 0
        
        # Handle crossed markets
        if bid_price >= ask_price:
            logger.warning("Crossed market detected: bid=%.2f >= ask=%.2f", 
                          bid_price, ask_price)
            # Use mid price for crossed markets
            mid_price = (bid_price + ask_price) / 2
            if trade_price >= mid_price:
                return trade_size
            else:
                return -trade_size
        
        # Calculate neutral zone if configured
        if self.config.neutral_zone_percent > 0:
            spread = ask_price - bid_price
            neutral_zone = spread * self.config.neutral_zone_percent / 100
            bid_threshold = bid_price + neutral_zone
            ask_threshold = ask_price - neutral_zone
            
            if trade_price >= ask_threshold:
                return trade_size  # Buy
            elif trade_price <= bid_threshold:
                return -trade_size  # Sell
            else:
                return 0  # Neutral
        else:
            # Standard calculation
            if trade_price >= ask_price:
                return trade_size  # Buy at ask or higher
            elif trade_price <= bid_price:
                return -trade_size  # Sell at bid or lower
            else:
                return 0  # Inside spread
    
    def _calculate_delta_from_price_direction(self, trade: Trade) -> float:
        """
        Calculate delta using uptick/downtick rule for futures.
        
        Args:
            trade: Trade object
            
        Returns:
            Delta value based on price direction
        """
        if self.last_price is None:
            # First trade, assume neutral
            logger.debug("First trade at price %.2f, setting as neutral", trade.price)
            self.last_price = trade.price
            return 0
        
        if trade.price > self.last_price:
            # Uptick - buying pressure
            logger.debug("Uptick: %.2f > %.2f, delta=+%.2f", trade.price, self.last_price, trade.size)
            self.last_price = trade.price
            return trade.size
        elif trade.price < self.last_price:
            # Downtick - selling pressure
            logger.debug("Downtick: %.2f < %.2f, delta=-%.2f", trade.price, self.last_price, trade.size)
            self.last_price = trade.price
            return -trade.size
        else:
            # Same price - neutral
            logger.debug("Same price: %.2f = %.2f, delta=0", trade.price, self.last_price)
            return 0
    
    def _create_output(self, delta_point: DeltaPoint, stream_id: str = "", timestamp: str = "") -> Dict[str, Any]:
        """Create v2 protocol output dictionary for current state."""
        summary = self.get_summary()
        
        return {
            "study": "delta",
            "timestamp": timestamp or datetime.now().isoformat(),
            "stream_id": stream_id,
            "tick_type": "trade",
            "current_trade": {
                "price": delta_point.trade.price,
                "size": delta_point.trade.size,
                "delta": delta_point.delta,
                "timestamp": delta_point.timestamp.isoformat()
            },
            "current_quote": {
                "bid": delta_point.quote.bid_price if delta_point.quote else None,
                "ask": delta_point.quote.ask_price if delta_point.quote else None,
                "spread": delta_point.quote.spread if delta_point.quote else None
            },
            "summary": summary
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get current delta summary statistics."""
        # Calculate statistics from buffer
        total_buy_volume = sum(p.trade.size for p in self.delta_buffer if p.is_buy)
        total_sell_volume = sum(abs(p.delta) for p in self.delta_buffer if p.is_sell)
        total_neutral_volume = sum(p.trade.size for p in self.delta_buffer if p.is_neutral)
        
        summary = DeltaSummary(
            window_seconds=self.config.window_seconds,
            trade_count=len(self.delta_buffer),
            total_buy_volume=total_buy_volume,
            total_sell_volume=total_sell_volume,
            total_neutral_volume=total_neutral_volume,
            net_delta=total_buy_volume - total_sell_volume,
            cumulative_delta=self.cumulative_delta
        )
        
        return {
            "window_seconds": summary.window_seconds,
            "trade_count": summary.trade_count,
            "total_buy_volume": round(summary.total_buy_volume, 2),
            "total_sell_volume": round(summary.total_sell_volume, 2),
            "total_neutral_volume": round(summary.total_neutral_volume, 2),
            "net_delta": round(summary.net_delta, 2),
            "cumulative_delta": round(summary.cumulative_delta, 2),
            "buy_sell_ratio": round(summary.buy_sell_ratio, 2) if summary.buy_sell_ratio else None,
            "buy_percentage": round(summary.buy_percentage, 1)
        }
    
    def reset(self) -> None:
        """Reset study state."""
        self.current_quote = None
        self.last_known_quote = None
        self.delta_buffer.clear()
        self.cumulative_delta = 0
        self.last_price = None
        self._tick_count = 0
        self._start_time = datetime.now()
        logger.info("Delta study reset")
    
    def _parse_timestamp(self, data: Dict[str, Any], v2_timestamp: str = "") -> datetime:
        """Parse timestamp from v2 protocol tick data."""
        # Try v2 protocol timestamp first
        if v2_timestamp:
            try:
                # ISO format with Z suffix
                return datetime.fromisoformat(v2_timestamp.replace('Z', '+00:00'))
            except ValueError:
                pass
        
        # Fall back to data timestamp
        timestamp_str = data.get('timestamp', '')
        if timestamp_str:
            try:
                # ISO format
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except ValueError:
                pass
        
        # Unix timestamp
        unix_time = data.get('unix_time')
        if unix_time:
            return datetime.fromtimestamp(float(unix_time))
        
        # Default to now
        return datetime.now()