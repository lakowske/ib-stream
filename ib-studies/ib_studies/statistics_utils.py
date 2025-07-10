"""
Shared statistical utilities for IB-Studies.

This module provides reusable statistical functions and data structures
for time-windowed calculations, following the DRY principle.
"""

import logging
import math
from collections import deque
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class TimeWindow:
    """
    Generic time-based rolling window for efficient statistical calculations.

    Uses circular buffer approach for memory efficiency and supports incremental
    updates without full recalculation.
    """

    def __init__(self, window_seconds: int, max_size: int = 10000):
        """
        Initialize time window.

        Args:
            window_seconds: Time window in seconds
            max_size: Maximum buffer size to prevent memory issues
        """
        self.window_seconds = window_seconds
        self.max_size = max_size
        self.data_points: deque[tuple[datetime, float, float]] = deque(maxlen=max_size)
        # Store (timestamp, price, volume) tuples

    def add_point(self, timestamp: datetime, price: float, volume: float = 1.0) -> None:
        """
        Add a new data point to the window.

        Args:
            timestamp: Point timestamp
            price: Price value
            volume: Volume (default 1.0 for simple price series)
        """
        self.data_points.append((timestamp, price, volume))
        self._cleanup_old_data()

    def _cleanup_old_data(self) -> None:
        """Remove data points older than the window."""
        if not self.data_points:
            return

        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)

        while self.data_points and self.data_points[0][0] < cutoff_time:
            self.data_points.popleft()

    def get_current_data(self) -> list[tuple[datetime, float, float]]:
        """
        Get current data points within the window.

        Returns:
            List of (timestamp, price, volume) tuples
        """
        self._cleanup_old_data()
        return list(self.data_points)

    def is_empty(self) -> bool:
        """Check if window is empty."""
        self._cleanup_old_data()
        return len(self.data_points) == 0

    def size(self) -> int:
        """Get current number of data points."""
        self._cleanup_old_data()
        return len(self.data_points)


class RollingStatistics:
    """
    Efficient rolling statistics calculator using Welford's algorithm.

    Provides numerically stable calculation of mean, variance, and standard deviation
    with incremental updates.
    """

    def __init__(self):
        """Initialize rolling statistics."""
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0  # Sum of squares of deviations

    def update(self, value: float) -> None:
        """
        Update statistics with new value using Welford's algorithm.

        Args:
            value: New value to include
        """
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.m2 += delta * delta2

    def get_variance(self) -> float:
        """
        Get current variance.

        Returns:
            Population variance
        """
        if self.count < 2:
            return 0.0
        return self.m2 / self.count

    def get_sample_variance(self) -> float:
        """
        Get current sample variance.

        Returns:
            Sample variance (Bessel's correction)
        """
        if self.count < 2:
            return 0.0
        return self.m2 / (self.count - 1)

    def get_std_dev(self) -> float:
        """
        Get current standard deviation.

        Returns:
            Population standard deviation
        """
        return math.sqrt(self.get_variance())

    def get_sample_std_dev(self) -> float:
        """
        Get current sample standard deviation.

        Returns:
            Sample standard deviation
        """
        return math.sqrt(self.get_sample_variance())

    def get_mean(self) -> float:
        """Get current mean."""
        return self.mean

    def get_count(self) -> int:
        """Get current count."""
        return self.count

    def reset(self) -> None:
        """Reset statistics."""
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0


def calculate_vwap(data_points: list[tuple[datetime, float, float]]) -> float:
    """
    Calculate Volume Weighted Average Price (VWAP).

    VWAP = Σ(Price × Volume) / Σ(Volume)

    Args:
        data_points: List of (timestamp, price, volume) tuples

    Returns:
        VWAP value or 0.0 if no data
    """
    if not data_points:
        return 0.0

    total_pv = 0.0  # Price × Volume
    total_volume = 0.0

    for _, price, volume in data_points:
        total_pv += price * volume
        total_volume += volume

    if total_volume == 0:
        return 0.0

    return total_pv / total_volume


def calculate_realized_volatility(data_points: list[tuple[datetime, float, float]],
                                  annualization_factor: float = 252.0) -> float:
    """
    Calculate realized volatility from price returns.

    Uses log returns: ln(P_t / P_{t-1})

    Args:
        data_points: List of (timestamp, price, volume) tuples
        annualization_factor: Factor to annualize volatility (default 252 trading days)

    Returns:
        Realized volatility or 0.0 if insufficient data
    """
    if len(data_points) < 2:
        return 0.0

    # Calculate log returns
    log_returns = []
    for i in range(1, len(data_points)):
        prev_price = data_points[i-1][1]
        curr_price = data_points[i][1]

        if prev_price > 0 and curr_price > 0:
            log_return = math.log(curr_price / prev_price)
            log_returns.append(log_return)

    if len(log_returns) < 2:
        return 0.0

    # Calculate standard deviation of log returns
    mean_return = sum(log_returns) / len(log_returns)
    variance = sum((r - mean_return) ** 2 for r in log_returns) / len(log_returns)

    # Annualize volatility
    volatility = math.sqrt(variance * annualization_factor)

    return volatility


def calculate_simple_moving_average(data_points: list[tuple[datetime, float, float]]) -> float:
    """
    Calculate Simple Moving Average (SMA).

    Args:
        data_points: List of (timestamp, price, volume) tuples

    Returns:
        SMA value or 0.0 if no data
    """
    if not data_points:
        return 0.0

    prices = [price for _, price, _ in data_points]
    return sum(prices) / len(prices)


def calculate_standard_deviation(data_points: list[tuple[datetime, float, float]]) -> float:
    """
    Calculate standard deviation of prices.

    Args:
        data_points: List of (timestamp, price, volume) tuples

    Returns:
        Standard deviation or 0.0 if insufficient data
    """
    if len(data_points) < 2:
        return 0.0

    prices = [price for _, price, _ in data_points]
    mean = sum(prices) / len(prices)
    variance = sum((price - mean) ** 2 for price in prices) / len(prices)

    return math.sqrt(variance)


def calculate_bollinger_bands(data_points: list[tuple[datetime, float, float]],
                            num_std_dev: float = 1.0) -> tuple[float, float, float]:
    """
    Calculate Bollinger Bands (SMA, Upper Band, Lower Band).

    Args:
        data_points: List of (timestamp, price, volume) tuples
        num_std_dev: Number of standard deviations for bands

    Returns:
        Tuple of (sma, upper_band, lower_band)
    """
    if not data_points:
        return 0.0, 0.0, 0.0

    sma = calculate_simple_moving_average(data_points)
    std_dev = calculate_standard_deviation(data_points)

    upper_band = sma + (num_std_dev * std_dev)
    lower_band = sma - (num_std_dev * std_dev)

    return sma, upper_band, lower_band


def calculate_vwap_bands(data_points: list[tuple[datetime, float, float]],
                        num_std_dev: float = 3.0) -> tuple[float, float, float]:
    """
    Calculate VWAP with volatility-based bands.

    Args:
        data_points: List of (timestamp, price, volume) tuples
        num_std_dev: Number of standard deviations for bands

    Returns:
        Tuple of (vwap, upper_band, lower_band)
    """
    if not data_points:
        return 0.0, 0.0, 0.0

    vwap = calculate_vwap(data_points)
    volatility = calculate_realized_volatility(data_points)

    # Use realized volatility as band width
    band_width = num_std_dev * volatility
    upper_band = vwap + band_width
    lower_band = vwap - band_width

    return vwap, upper_band, lower_band


class VWAPCalculator:
    """
    Efficient VWAP calculator with incremental updates.

    Tracks cumulative price*volume and volume for efficient VWAP calculation.
    """

    def __init__(self, window_seconds: int = 0):
        """
        Initialize VWAP calculator.

        Args:
            window_seconds: Time window in seconds (0 for session-based)
        """
        self.window_seconds = window_seconds
        self.time_window = TimeWindow(window_seconds) if window_seconds > 0 else None
        self.cumulative_pv = 0.0  # Price × Volume
        self.cumulative_volume = 0.0
        self.start_time = datetime.now(timezone.utc)

    def add_trade(self, timestamp: datetime, price: float, volume: float) -> None:
        """
        Add a trade to the VWAP calculation.

        Args:
            timestamp: Trade timestamp
            price: Trade price
            volume: Trade volume
        """
        if self.time_window:
            self.time_window.add_point(timestamp, price, volume)
        else:
            # Session-based: accumulate since start
            self.cumulative_pv += price * volume
            self.cumulative_volume += volume

    def get_vwap(self) -> float:
        """
        Get current VWAP.

        Returns:
            Current VWAP value
        """
        if self.time_window:
            data_points = self.time_window.get_current_data()
            return calculate_vwap(data_points)
        else:
            if self.cumulative_volume == 0:
                return 0.0
            return self.cumulative_pv / self.cumulative_volume

    def get_vwap_with_bands(self, num_std_dev: float = 3.0) -> tuple[float, float, float]:
        """
        Get VWAP with volatility-based bands.

        Args:
            num_std_dev: Number of standard deviations for bands

        Returns:
            Tuple of (vwap, upper_band, lower_band)
        """
        if self.time_window:
            data_points = self.time_window.get_current_data()
            return calculate_vwap_bands(data_points, num_std_dev)
        else:
            vwap = self.get_vwap()
            # For session-based, we need to track all trades for volatility
            # This is a simplified implementation
            return vwap, vwap, vwap

    def reset(self) -> None:
        """Reset VWAP calculation."""
        if self.time_window:
            self.time_window = TimeWindow(self.window_seconds)
        self.cumulative_pv = 0.0
        self.cumulative_volume = 0.0
        self.start_time = datetime.now(timezone.utc)


class BollingerBandsCalculator:
    """
    Efficient Bollinger Bands calculator with time-based windows.
    """

    def __init__(self, window_seconds: int):
        """
        Initialize Bollinger Bands calculator.

        Args:
            window_seconds: Time window in seconds
        """
        self.window_seconds = window_seconds
        self.time_window = TimeWindow(window_seconds)

    def add_trade(self, timestamp: datetime, price: float, volume: float = 1.0) -> None:
        """
        Add a trade to the calculation.

        Args:
            timestamp: Trade timestamp
            price: Trade price
            volume: Trade volume (optional for simple price series)
        """
        self.time_window.add_point(timestamp, price, volume)

    def get_bands(self, num_std_dev: float = 1.0) -> tuple[float, float, float]:
        """
        Get Bollinger Bands.

        Args:
            num_std_dev: Number of standard deviations for bands

        Returns:
            Tuple of (sma, upper_band, lower_band)
        """
        data_points = self.time_window.get_current_data()
        return calculate_bollinger_bands(data_points, num_std_dev)

    def get_sma(self) -> float:
        """Get Simple Moving Average."""
        data_points = self.time_window.get_current_data()
        return calculate_simple_moving_average(data_points)

    def get_std_dev(self) -> float:
        """Get standard deviation."""
        data_points = self.time_window.get_current_data()
        return calculate_standard_deviation(data_points)

    def get_data_count(self) -> int:
        """Get current number of data points."""
        return self.time_window.size()

    def reset(self) -> None:
        """Reset calculation."""
        self.time_window = TimeWindow(self.window_seconds)
