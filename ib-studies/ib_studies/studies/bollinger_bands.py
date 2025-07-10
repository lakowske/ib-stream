"""Bollinger Bands study implementation for N-minute price analysis."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ib_studies.models import BollingerPoint, BollingerSummary, StudyConfig, Trade
from ib_studies.statistics_utils import BollingerBandsCalculator
from ib_studies.studies.base import BaseStudy

logger = logging.getLogger(__name__)


class BollingerBandsStudy(BaseStudy):
    """
    Bollinger Bands study calculates Simple Moving Average with upper and lower
    bands based on standard deviation over a specified time period.
    """

    def __init__(self, config: Optional[StudyConfig] = None):
        """Initialize Bollinger Bands study."""
        super().__init__(config)
        self.period_seconds = getattr(config, 'bollinger_period_seconds', 1200) if config else 1200  # 20 minutes
        self.std_dev_multiplier = getattr(config, 'bollinger_std_dev_multiplier', 1.0) if config else 1.0
        self.min_trades = getattr(config, 'bollinger_min_trades', 10) if config else 10

        self.bollinger_calculator = BollingerBandsCalculator(
            window_seconds=self.period_seconds
        )
        self.bollinger_buffer: list[BollingerPoint] = []
        self.band_touches = {"upper": 0, "lower": 0}
        self.last_band_position = "normal"
        self.mean_reversion_signals = 0

    @property
    def required_tick_types(self) -> list[str]:
        """Bollinger Bands study requires trade data."""
        return ["last", "all_last"]

    def process_tick(self, tick_type: str, data: dict[str, Any], stream_id: str = "", timestamp: str = "") -> Optional[dict[str, Any]]:
        """Process incoming v2 protocol tick data."""
        self.increment_tick_count()
        logger.debug("BollingerBandsStudy.process_tick: tick_type=%s, stream_id=%s, timestamp=%s, data=%s",
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
        """Process trade and calculate Bollinger Bands."""
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

            # Add trade to Bollinger Bands calculator
            self.bollinger_calculator.add_trade(trade.timestamp, trade.price, trade.size)

            # Check if we have enough data for calculation
            data_count = self.bollinger_calculator.get_data_count()
            if data_count < self.min_trades:
                logger.debug("Insufficient data for Bollinger Bands calculation: %d < %d",
                           data_count, self.min_trades)
                return None

            # Calculate Bollinger Bands
            sma, upper_band, lower_band = self.bollinger_calculator.get_bands(
                num_std_dev=self.std_dev_multiplier
            )

            # Get standard deviation
            std_dev = self.bollinger_calculator.get_std_dev()

            # Create Bollinger point
            bollinger_point = BollingerPoint(
                timestamp=trade.timestamp,
                trade=trade,
                sma=sma,
                upper_band=upper_band,
                lower_band=lower_band,
                std_dev=std_dev,
                data_count=data_count
            )

            # Track band touches and mean reversion signals
            self._track_band_activity(bollinger_point)

            self.bollinger_buffer.append(bollinger_point)

            # Cleanup old data
            self.bollinger_buffer = self.cleanup_old_data(
                self.bollinger_buffer,
                self.period_seconds
            )

            # Return current state
            return self._create_output(bollinger_point, stream_id, timestamp)

        except (KeyError, ValueError) as e:
            logger.error("Invalid trade data: %s", e)
            return None

    def _track_band_activity(self, bollinger_point: BollingerPoint) -> None:
        """Track when price touches bands and identify mean reversion signals."""
        current_position = bollinger_point.band_position

        # Check for band touches
        if current_position == "above_upper" and self.last_band_position != "above_upper":
            self.band_touches["upper"] += 1
            logger.debug("Upper band touch detected at price %.2f", bollinger_point.trade.price)
        elif current_position == "below_lower" and self.last_band_position != "below_lower":
            self.band_touches["lower"] += 1
            logger.debug("Lower band touch detected at price %.2f", bollinger_point.trade.price)

        # Check for mean reversion signals (price returns to SMA from bands)
        if ((self.last_band_position == "above_upper" and current_position in ["at_sma", "below_sma"]) or
            (self.last_band_position == "below_lower" and current_position in ["at_sma", "above_sma"])):
            self.mean_reversion_signals += 1
            logger.debug("Mean reversion signal detected: %s -> %s",
                        self.last_band_position, current_position)

        self.last_band_position = current_position

    def _create_output(self, bollinger_point: BollingerPoint, stream_id: str = "", timestamp: str = "") -> dict[str, Any]:
        """Create v2 protocol output dictionary for current state."""
        summary = self.get_summary()

        return {
            "study": "bollinger_bands",
            "timestamp": timestamp or datetime.now().isoformat(),
            "stream_id": stream_id,
            "tick_type": "trade",
            "current_trade": {
                "price": bollinger_point.trade.price,
                "size": bollinger_point.trade.size,
                "timestamp": bollinger_point.timestamp.isoformat()
            },
            "bands": {
                "sma": bollinger_point.sma,
                "upper_band": bollinger_point.upper_band,
                "lower_band": bollinger_point.lower_band,
                "std_dev": bollinger_point.std_dev,
                "band_width": bollinger_point.upper_band - bollinger_point.lower_band,
                "band_width_percent": ((bollinger_point.upper_band - bollinger_point.lower_band) / bollinger_point.sma * 100) if bollinger_point.sma != 0 else 0,
                "is_squeeze": bollinger_point.is_squeeze
            },
            "analysis": {
                "percent_b": bollinger_point.percent_b,
                "band_position": bollinger_point.band_position,
                "distance_from_sma": bollinger_point.distance_from_sma,
                "distance_from_upper_band": bollinger_point.distance_from_upper_band,
                "distance_from_lower_band": bollinger_point.distance_from_lower_band
            },
            "summary": summary
        }

    def get_summary(self) -> dict[str, Any]:
        """Get current Bollinger Bands summary statistics."""
        # Get current band values
        sma, upper_band, lower_band = self.bollinger_calculator.get_bands(
            num_std_dev=self.std_dev_multiplier
        )
        std_dev = self.bollinger_calculator.get_std_dev()
        data_count = self.bollinger_calculator.get_data_count()

        summary = BollingerSummary(
            period_seconds=self.period_seconds,
            trade_count=data_count,
            sma=sma,
            upper_band=upper_band,
            lower_band=lower_band,
            std_dev=std_dev,
            band_touches=self.band_touches.copy(),
            mean_reversion_signals=self.mean_reversion_signals
        )

        return {
            "period_seconds": summary.period_seconds,
            "trade_count": summary.trade_count,
            "sma": round(summary.sma, 4),
            "upper_band": round(summary.upper_band, 4),
            "lower_band": round(summary.lower_band, 4),
            "std_dev": round(summary.std_dev, 4),
            "band_width": round(summary.band_width, 4),
            "band_width_percent": round(summary.band_width_percent, 4),
            "band_touches": summary.band_touches,
            "total_band_touches": summary.total_band_touches,
            "mean_reversion_signals": summary.mean_reversion_signals,
            "volatility_regime": summary.volatility_regime
        }

    def reset(self) -> None:
        """Reset study state."""
        self.bollinger_calculator.reset()
        self.bollinger_buffer.clear()
        self.band_touches = {"upper": 0, "lower": 0}
        self.last_band_position = "normal"
        self.mean_reversion_signals = 0
        self._tick_count = 0
        self._start_time = datetime.now()
        logger.info("Bollinger Bands study reset")

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
