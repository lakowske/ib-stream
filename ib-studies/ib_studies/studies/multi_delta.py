"""Multi-stream delta study using both BidAsk and Last streams for true delta calculation."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ib_studies.models import DeltaPoint, DeltaSummary, MarketQuote, StudyConfig, Trade
from ib_studies.studies.base import BaseStudy

logger = logging.getLogger(__name__)


class MultiStreamDeltaStudy(BaseStudy):
    """
    Multi-stream delta study that consumes both BidAsk and Last streams
    to calculate true delta based on trades hitting bid vs ask.
    """
    
    def __init__(self, config: Optional[StudyConfig] = None):
        """Initialize multi-stream delta study."""
        super().__init__(config)
        self.current_quote: Optional[MarketQuote] = None
        self.delta_buffer: List[DeltaPoint] = []
        self.cumulative_delta: float = 0
        self.last_trade_price: Optional[float] = None
        # Track last known bid/ask for when current_quote is None
        self.last_known_quote: Optional[MarketQuote] = None
        
        # Track statistics
        self.bid_hits: int = 0
        self.ask_hits: int = 0
        self.inside_spread: int = 0
        self.no_quote_trades: int = 0
        
    @property
    def required_tick_types(self) -> List[str]:
        """Multi-stream delta study requires both bid/ask quotes and trade data."""
        return ["BidAsk", "Last"]
    
    def process_tick(self, tick_type: str, data: Dict[str, Any], stream_id: str = "", timestamp: str = "") -> Optional[Dict[str, Any]]:
        """Process incoming v2 protocol tick data from multiple streams."""
        self.increment_tick_count()
        logger.debug("MultiStreamDeltaStudy.process_tick: tick_type=%s, stream_id=%s, timestamp=%s, data=%s", 
                    tick_type, stream_id, timestamp, data)
        
        try:
            if tick_type in ["BidAsk", "bid_ask"]:
                logger.debug("Processing BidAsk tick from stream")
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
        """Update current market quote from v2 BidAsk stream."""
        try:
            # Handle bid_ask data format from stream
            bid_price = float(data.get('bid_price', 0))
            ask_price = float(data.get('ask_price', 0))
            bid_size = float(data.get('bid_size', 0))
            ask_size = float(data.get('ask_size', 0))
            
            self.current_quote = MarketQuote(
                timestamp=self._parse_timestamp(data, timestamp),
                bid_price=bid_price,
                ask_price=ask_price,
                bid_size=bid_size,
                ask_size=ask_size
            )
            
            # Store as last known quote if it has valid prices
            if self.current_quote.bid_price > 0 and self.current_quote.ask_price > 0:
                self.last_known_quote = self.current_quote
            
            logger.debug("Updated v2 quote (stream_id=%s): bid=%.2f@%.0f, ask=%.2f@%.0f, spread=%.2f", 
                        stream_id, self.current_quote.bid_price, self.current_quote.bid_size,
                        self.current_quote.ask_price, self.current_quote.ask_size,
                        self.current_quote.spread)
        except (KeyError, ValueError) as e:
            logger.error("Invalid bid/ask data: %s", e)
    
    def _process_trade(self, data: Dict[str, Any], tick_type: str, stream_id: str = "", timestamp: str = "") -> Optional[Dict[str, Any]]:
        """Process trade and calculate true delta using current bid/ask from v2 protocol."""
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
            
            # Calculate delta using current bid/ask if available
            if self.current_quote and self.current_quote.bid_price > 0 and self.current_quote.ask_price > 0:
                logger.debug("Using true bid/ask calculation: bid=%.2f, ask=%.2f", 
                           self.current_quote.bid_price, self.current_quote.ask_price)
                delta = self._calculate_true_delta(trade, self.current_quote)
            else:
                logger.debug("No valid quote available, using uptick/downtick rule")
                delta = self._calculate_delta_from_price_direction(trade)
                self.no_quote_trades += 1
            
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
    
    def _calculate_true_delta(self, trade: Trade, quote: MarketQuote) -> float:
        """
        Calculate true delta using bid/ask spread.
        
        This is the core logic for determining buying vs selling pressure:
        - Trade at ask or higher = buying pressure (positive delta)
        - Trade at bid or lower = selling pressure (negative delta)  
        - Trade inside spread = neutral (zero delta)
        
        Args:
            trade: Trade object
            quote: Current market quote with bid/ask
            
        Returns:
            Delta value: positive for buys, negative for sells, zero for neutral
        """
        # Validate quote data
        if quote.bid_price <= 0 or quote.ask_price <= 0:
            logger.warning("Invalid quote prices: bid=%.2f, ask=%.2f", quote.bid_price, quote.ask_price)
            return 0
        
        # Handle crossed markets (bid >= ask) - this shouldn't happen but let's be safe
        if quote.bid_price >= quote.ask_price:
            logger.warning("Crossed market detected: bid=%.2f >= ask=%.2f", 
                          quote.bid_price, quote.ask_price)
            # Use mid price for crossed markets
            mid_price = (quote.bid_price + quote.ask_price) / 2
            if trade.price >= mid_price:
                return trade.size
            else:
                return -trade.size
        
        # Apply neutral zone if configured
        if self.config.neutral_zone_percent > 0:
            spread = quote.ask_price - quote.bid_price
            neutral_zone = spread * self.config.neutral_zone_percent / 100
            bid_threshold = quote.bid_price + neutral_zone
            ask_threshold = quote.ask_price - neutral_zone
            
            if trade.price >= ask_threshold:
                self.ask_hits += 1
                logger.debug("Ask hit (with neutral zone): %.2f >= %.2f, delta=+%.2f", 
                           trade.price, ask_threshold, trade.size)
                return trade.size  # Buy at ask zone
            elif trade.price <= bid_threshold:
                self.bid_hits += 1
                logger.debug("Bid hit (with neutral zone): %.2f <= %.2f, delta=-%.2f", 
                           trade.price, bid_threshold, trade.size)
                return -trade.size  # Sell at bid zone
            else:
                self.inside_spread += 1
                logger.debug("Inside spread (neutral zone): %.2f between %.2f and %.2f, delta=0", 
                           trade.price, bid_threshold, ask_threshold)
                return 0  # Neutral
        else:
            # Standard calculation without neutral zone
            if trade.price >= quote.ask_price:
                self.ask_hits += 1
                logger.debug("Ask hit: %.2f >= %.2f, delta=+%.2f", 
                           trade.price, quote.ask_price, trade.size)
                return trade.size  # Buy at ask or higher
            elif trade.price <= quote.bid_price:
                self.bid_hits += 1
                logger.debug("Bid hit: %.2f <= %.2f, delta=-%.2f", 
                           trade.price, quote.bid_price, trade.size)
                return -trade.size  # Sell at bid or lower
            else:
                self.inside_spread += 1
                logger.debug("Inside spread: %.2f between %.2f and %.2f, delta=0", 
                           trade.price, quote.bid_price, quote.ask_price)
                return 0  # Inside spread
    
    def _calculate_delta_from_price_direction(self, trade: Trade) -> float:
        """
        Fallback: Calculate delta using uptick/downtick rule when no bid/ask available.
        """
        if self.last_trade_price is None:
            logger.debug("First trade at price %.2f, setting as neutral", trade.price)
            self.last_trade_price = trade.price
            return 0
        
        if trade.price > self.last_trade_price:
            logger.debug("Uptick: %.2f > %.2f, delta=+%.2f", trade.price, self.last_trade_price, trade.size)
            self.last_trade_price = trade.price
            return trade.size
        elif trade.price < self.last_trade_price:
            logger.debug("Downtick: %.2f < %.2f, delta=-%.2f", trade.price, self.last_trade_price, trade.size)
            self.last_trade_price = trade.price
            return -trade.size
        else:
            logger.debug("Same price: %.2f = %.2f, delta=0", trade.price, self.last_trade_price)
            return 0
    
    def _create_output(self, delta_point: DeltaPoint, stream_id: str = "", timestamp: str = "") -> Dict[str, Any]:
        """Create v2 protocol output dictionary for current state."""
        summary = self.get_summary()
        
        return {
            "study": "multi_delta",
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
                "bid_size": delta_point.quote.bid_size if delta_point.quote else None,
                "ask_size": delta_point.quote.ask_size if delta_point.quote else None,
                "spread": delta_point.quote.spread if delta_point.quote else None
            },
            "summary": summary,
            "calculation_stats": {
                "bid_hits": self.bid_hits,
                "ask_hits": self.ask_hits,
                "inside_spread": self.inside_spread,
                "no_quote_trades": self.no_quote_trades,
                "true_delta_percentage": round(
                    ((self.bid_hits + self.ask_hits) / len(self.delta_buffer) * 100) 
                    if self.delta_buffer else 0, 1
                )
            }
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
        self.last_trade_price = None
        self.bid_hits = 0
        self.ask_hits = 0
        self.inside_spread = 0
        self.no_quote_trades = 0
        self._tick_count = 0
        self._start_time = datetime.now()
        logger.info("Multi-stream delta study reset")
    
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