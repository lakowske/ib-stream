"""VWAP study implementation for volume-weighted average price analysis."""

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from ib_studies.models import StudyConfig, Trade, VWAPPoint, VWAPSummary
from ib_studies.statistics_utils import VWAPCalculator
from ib_studies.studies.base import BaseStudy

logger = logging.getLogger(__name__)


class VWAPStudy(BaseStudy):
    """
    VWAP (Volume Weighted Average Price) study calculates the average price
    weighted by volume over a specified time period, with volatility-based bands.
    """

    def __init__(self, config: Optional[StudyConfig] = None):
        """Initialize VWAP study."""
        super().__init__(config)
        self.vwap_calculator = VWAPCalculator(
            window_seconds=self.config.window_seconds
        )
        self.vwap_buffer: list[VWAPPoint] = []
        self.session_start = datetime.now(timezone.utc)
        self.band_touches = {"upper": 0, "lower": 0}
        self.last_band_position = "normal"

    @property
    def required_tick_types(self) -> list[str]:
        """VWAP study requires trade data."""
        return ["last", "all_last"]

    def process_tick(self, tick_type: str, data: dict[str, Any], stream_id: str = "", timestamp: str = "") -> Optional[dict[str, Any]]:
        """Process incoming v2 protocol tick data."""
        self.increment_tick_count()
        logger.debug("VWAPStudy.process_tick: tick_type=%s, stream_id=%s, timestamp=%s, data=%s",
                    tick_type, stream_id, timestamp, data)

        try:
            if tick_type in ["last", "all_last", "Last", "AllLast", "time_sales"]:
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

    def _process_trade(self, data: dict[str, Any], tick_type: str, stream_id: str = "", timestamp: str = "") -> Optional[dict[str, Any]]:
        """Process trade and calculate VWAP."""
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

            # Add trade to VWAP calculator
            self.vwap_calculator.add_trade(trade.timestamp, trade.price, trade.size)

            # Calculate VWAP with bands
            vwap_value = self.vwap_calculator.get_vwap()

            # For band calculation, use data from our buffer rather than the calculator
            # to handle both windowed and session-based cases properly
            # Include current trade with existing buffer for band calculation
            trade_data = [(p.trade.timestamp, p.trade.price, p.trade.size) for p in self.vwap_buffer]
            trade_data.append((trade.timestamp, trade.price, trade.size))  # Include current trade
            
            if len(trade_data) >= 3:  # Need at least 3 trades for meaningful volatility calculation
                from ib_studies.statistics_utils import calculate_vwap_bands
                
                # For intraday VWAP, use a more appropriate volatility calculation
                # that doesn't over-annualize for short-term trading
                _, upper_band, lower_band = self._calculate_intraday_vwap_bands(
                    trade_data,
                    vwap_value,
                    num_std_dev=self.config.vwap_std_dev_multiplier
                )
                
                # Calculate realized volatility for display (with reduced annualization)
                realized_vol = self._calculate_intraday_volatility(trade_data)
            else:
                # Not enough data for volatility calculation yet
                upper_band = vwap_value
                lower_band = vwap_value
                realized_vol = 0.0

            # Create VWAP point
            vwap_point = VWAPPoint(
                timestamp=trade.timestamp,
                trade=trade,
                vwap=vwap_value,
                upper_band=upper_band,
                lower_band=lower_band,
                realized_volatility=realized_vol,
                cumulative_volume=self.vwap_calculator.cumulative_volume
            )

            # Track band touches
            self._track_band_touches(vwap_point)

            self.vwap_buffer.append(vwap_point)

            # Cleanup old data
            self.vwap_buffer = self.cleanup_old_data(
                self.vwap_buffer,
                self.config.window_seconds if self.config.window_seconds > 0 else 86400  # 24 hours for session
            )

            # Return current state
            return self._create_output(vwap_point, stream_id, timestamp)

        except (KeyError, ValueError) as e:
            logger.error("Invalid trade data: %s", e)
            return None

    def _calculate_intraday_vwap_bands(self, trade_data: list[tuple[datetime, float, float]], 
                                     vwap_value: float, num_std_dev: float) -> tuple[float, float, float]:
        """
        Calculate VWAP bands using intraday volatility appropriate for short-term trading.
        
        Args:
            trade_data: List of (timestamp, price, volume) tuples
            vwap_value: Current VWAP value
            num_std_dev: Number of standard deviations for bands
            
        Returns:
            Tuple of (vwap, upper_band, lower_band)
        """
        if len(trade_data) < 3:
            return vwap_value, vwap_value, vwap_value
            
        # Calculate price standard deviation directly (not log returns)
        prices = [price for _, price, _ in trade_data]
        price_mean = sum(prices) / len(prices)
        price_variance = sum((price - price_mean) ** 2 for price in prices) / len(prices)
        price_std_dev = math.sqrt(price_variance)
        
        # Use price standard deviation for bands (more intuitive for intraday)
        band_width = num_std_dev * price_std_dev
        upper_band = vwap_value + band_width
        lower_band = vwap_value - band_width
        
        return vwap_value, upper_band, lower_band

    def _calculate_intraday_volatility(self, trade_data: list[tuple[datetime, float, float]]) -> float:
        """
        Calculate intraday volatility using log returns with appropriate scaling.
        
        Args:
            trade_data: List of (timestamp, price, volume) tuples
            
        Returns:
            Intraday volatility
        """
        if len(trade_data) < 2:
            return 0.0
            
        # Calculate log returns
        log_returns = []
        for i in range(1, len(trade_data)):
            prev_price = trade_data[i-1][1]
            curr_price = trade_data[i][1]
            
            if prev_price > 0 and curr_price > 0:
                log_return = math.log(curr_price / prev_price)
                log_returns.append(log_return)
        
        if len(log_returns) < 2:
            return 0.0
            
        # Calculate standard deviation of log returns
        mean_return = sum(log_returns) / len(log_returns)
        variance = sum((r - mean_return) ** 2 for r in log_returns) / len(log_returns)
        
        # Use moderate scaling for intraday (much less than 252 annual days)
        # Scale by sqrt of approximate trades per day for this frequency
        intraday_scaling = math.sqrt(len(trade_data) * 2)  # Rough estimate
        volatility = math.sqrt(variance) * intraday_scaling
        
        return volatility

    def _track_band_touches(self, vwap_point: VWAPPoint) -> None:
        """Track when price touches VWAP bands."""
        current_position = vwap_point.band_position

        # Check for band touches
        if current_position == "above_upper" and self.last_band_position != "above_upper":
            self.band_touches["upper"] += 1
            logger.debug("Upper band touch detected at price %.2f", vwap_point.trade.price)
        elif current_position == "below_lower" and self.last_band_position != "below_lower":
            self.band_touches["lower"] += 1
            logger.debug("Lower band touch detected at price %.2f", vwap_point.trade.price)

        self.last_band_position = current_position

    def _create_output(self, vwap_point: VWAPPoint, stream_id: str = "", timestamp: str = "") -> dict[str, Any]:
        """Create v2 protocol output dictionary for current state."""
        summary = self.get_summary()

        return {
            "study": "vwap",
            "timestamp": timestamp or datetime.now().isoformat(),
            "stream_id": stream_id,
            "tick_type": "trade",
            "current_trade": {
                "price": vwap_point.trade.price,
                "size": vwap_point.trade.size,
                "timestamp": vwap_point.timestamp.isoformat()
            },
            "vwap": {
                "value": vwap_point.vwap,
                "upper_band": vwap_point.upper_band,
                "lower_band": vwap_point.lower_band,
                "realized_volatility": vwap_point.realized_volatility,
                "band_position": vwap_point.band_position,
                "distance_from_vwap": vwap_point.distance_from_vwap,
                "distance_from_upper_band": vwap_point.distance_from_upper_band,
                "distance_from_lower_band": vwap_point.distance_from_lower_band
            },
            "summary": summary
        }

    def get_summary(self) -> dict[str, Any]:
        """Get current VWAP summary statistics."""
        total_volume = sum(p.trade.size for p in self.vwap_buffer)
        avg_trade_size = total_volume / len(self.vwap_buffer) if self.vwap_buffer else 0

        # Get current VWAP values
        current_vwap, upper_band, lower_band = self.vwap_calculator.get_vwap_with_bands(
            num_std_dev=self.config.vwap_std_dev_multiplier
        )

        # Calculate realized volatility
        if hasattr(self.vwap_calculator, 'time_window') and self.vwap_calculator.time_window:
            data_points = self.vwap_calculator.time_window.get_current_data()
            if len(data_points) >= 2:
                from ib_studies.statistics_utils import calculate_realized_volatility
                realized_vol = calculate_realized_volatility(data_points)
            else:
                realized_vol = 0.0
        else:
            realized_vol = 0.0

        summary = VWAPSummary(
            window_seconds=self.config.window_seconds,
            trade_count=len(self.vwap_buffer),
            total_volume=total_volume,
            session_start=self.session_start,
            vwap=current_vwap,
            upper_band=upper_band,
            lower_band=lower_band,
            realized_volatility=realized_vol,
            band_touches=self.band_touches.copy(),
            avg_trade_size=avg_trade_size
        )

        return {
            "window_seconds": summary.window_seconds,
            "trade_count": summary.trade_count,
            "total_volume": round(summary.total_volume, 2),
            "session_start": summary.session_start.isoformat(),
            "vwap": round(summary.vwap, 4),
            "upper_band": round(summary.upper_band, 4),
            "lower_band": round(summary.lower_band, 4),
            "band_width": round(summary.band_width, 4),
            "band_width_percent": round(summary.band_width_percent, 4),
            "realized_volatility": round(summary.realized_volatility, 6),
            "avg_trade_size": round(summary.avg_trade_size, 2),
            "band_touches": summary.band_touches,
            "total_band_touches": summary.total_band_touches
        }

    def reset(self) -> None:
        """Reset study state."""
        self.vwap_calculator.reset()
        self.vwap_buffer.clear()
        self.band_touches = {"upper": 0, "lower": 0}
        self.last_band_position = "normal"
        self.session_start = datetime.now(timezone.utc)
        self._tick_count = 0
        self._start_time = datetime.now()
        logger.info("VWAP study reset")

    def _parse_timestamp(self, data: dict[str, Any], v2_timestamp: str = "") -> datetime:
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
            return datetime.fromtimestamp(float(unix_time), tz=timezone.utc)

        # Default to now
        return datetime.now(timezone.utc)
