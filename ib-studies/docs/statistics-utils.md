# Statistics Utilities Documentation

## Overview

The `statistics_utils.py` module provides reusable statistical functions and data structures for time-windowed calculations in IB-Studies, following the DRY (Don't Repeat Yourself) principle. It serves as the foundation for all statistical calculations across different studies.

## Core Components

### TimeWindow Class

Generic time-based rolling window for efficient statistical calculations.

```python
class TimeWindow:
    def __init__(self, window_seconds: int, max_size: int = 10000)
    def add_point(self, timestamp: datetime, price: float, volume: float = 1.0) -> None
    def get_current_data(self) -> list[tuple[datetime, float, float]]
    def is_empty(self) -> bool
    def size(self) -> int
```

**Features:**
- Circular buffer approach for memory efficiency
- Automatic cleanup of old data points
- Thread-safe operations
- Configurable maximum size to prevent memory issues

**Usage:**
```python
from ib_studies.statistics_utils import TimeWindow

# Create 5-minute rolling window
window = TimeWindow(window_seconds=300)

# Add data points
window.add_point(datetime.now(), 100.50, 200)
window.add_point(datetime.now(), 100.75, 150)

# Get current data
data = window.get_current_data()
print(f"Current data points: {len(data)}")
```

### RollingStatistics Class

Efficient rolling statistics calculator using Welford's algorithm for numerical stability.

```python
class RollingStatistics:
    def __init__(self)
    def update(self, value: float) -> None
    def get_variance(self) -> float
    def get_sample_variance(self) -> float
    def get_std_dev(self) -> float
    def get_sample_std_dev(self) -> float
    def get_mean(self) -> float
    def get_count(self) -> int
    def reset(self) -> None
```

**Features:**
- Numerically stable calculations
- Incremental updates without full recalculation
- Both population and sample statistics
- Memory efficient (O(1) storage)

**Usage:**
```python
from ib_studies.statistics_utils import RollingStatistics

stats = RollingStatistics()

# Add values incrementally
for price in [100.0, 101.0, 99.5, 102.0]:
    stats.update(price)

print(f"Mean: {stats.get_mean():.2f}")
print(f"Std Dev: {stats.get_std_dev():.2f}")
```

## Statistical Functions

### VWAP Calculations

#### calculate_vwap()
```python
def calculate_vwap(data_points: list[tuple[datetime, float, float]]) -> float
```

Calculate Volume Weighted Average Price using the formula:
```
VWAP = Σ(Price × Volume) / Σ(Volume)
```

**Parameters:**
- `data_points`: List of (timestamp, price, volume) tuples

**Returns:**
- VWAP value or 0.0 if no data

**Example:**
```python
from datetime import datetime
from ib_studies.statistics_utils import calculate_vwap

data = [
    (datetime.now(), 100.0, 1000),
    (datetime.now(), 100.5, 500),
    (datetime.now(), 99.8, 800),
]

vwap = calculate_vwap(data)
print(f"VWAP: {vwap:.2f}")  # Output: VWAP: 100.09
```

#### calculate_vwap_bands()
```python
def calculate_vwap_bands(data_points: list[tuple[datetime, float, float]], 
                        num_std_dev: float = 3.0) -> tuple[float, float, float]
```

Calculate VWAP with volatility-based bands using realized volatility.

**Parameters:**
- `data_points`: List of (timestamp, price, volume) tuples
- `num_std_dev`: Number of standard deviations for bands (default: 3.0)

**Returns:**
- Tuple of (vwap, upper_band, lower_band)

### Volatility Calculations

#### calculate_realized_volatility()
```python
def calculate_realized_volatility(data_points: list[tuple[datetime, float, float]],
                                  annualization_factor: float = 252.0) -> float
```

Calculate realized volatility from price returns using log returns.

**Formula:**
```
Log Return = ln(P_t / P_{t-1})
Realized Volatility = sqrt(Variance(Log Returns) × Annualization Factor)
```

**Parameters:**
- `data_points`: List of (timestamp, price, volume) tuples
- `annualization_factor`: Factor to annualize volatility (default: 252 trading days)

**Returns:**
- Realized volatility or 0.0 if insufficient data

### Moving Averages

#### calculate_simple_moving_average()
```python
def calculate_simple_moving_average(data_points: list[tuple[datetime, float, float]]) -> float
```

Calculate Simple Moving Average (SMA) of prices.

**Formula:**
```
SMA = Σ(Price) / N
```

#### calculate_standard_deviation()
```python
def calculate_standard_deviation(data_points: list[tuple[datetime, float, float]]) -> float
```

Calculate population standard deviation of prices.

**Formula:**
```
Standard Deviation = sqrt(Σ(Price - Mean)² / N)
```

### Bollinger Bands

#### calculate_bollinger_bands()
```python
def calculate_bollinger_bands(data_points: list[tuple[datetime, float, float]],
                            num_std_dev: float = 1.0) -> tuple[float, float, float]
```

Calculate Bollinger Bands with SMA and standard deviation bands.

**Parameters:**
- `data_points`: List of (timestamp, price, volume) tuples
- `num_std_dev`: Number of standard deviations for bands (default: 1.0)

**Returns:**
- Tuple of (sma, upper_band, lower_band)

**Example:**
```python
from ib_studies.statistics_utils import calculate_bollinger_bands

# Sample price data
data = [(datetime.now(), price, 100) for price in [100, 101, 99, 102, 98, 103]]

sma, upper, lower = calculate_bollinger_bands(data, num_std_dev=2.0)
print(f"SMA: {sma:.2f}, Upper: {upper:.2f}, Lower: {lower:.2f}")
```

## High-Level Calculator Classes

### VWAPCalculator

Efficient VWAP calculator with incremental updates and optional time windows.

```python
class VWAPCalculator:
    def __init__(self, window_seconds: int = 0)  # 0 = session-based
    def add_trade(self, timestamp: datetime, price: float, volume: float) -> None
    def get_vwap(self) -> float
    def get_vwap_with_bands(self, num_std_dev: float = 3.0) -> tuple[float, float, float]
    def reset(self) -> None
```

**Features:**
- Session-based or time-windowed calculation
- Incremental updates for efficiency
- Volatility-based bands
- Memory efficient for long sessions

**Usage:**
```python
from ib_studies.statistics_utils import VWAPCalculator

# Session-based VWAP
vwap_calc = VWAPCalculator(window_seconds=0)

# Add trades
vwap_calc.add_trade(datetime.now(), 100.0, 1000)
vwap_calc.add_trade(datetime.now(), 100.5, 500)

# Get results
vwap = vwap_calc.get_vwap()
vwap, upper, lower = vwap_calc.get_vwap_with_bands(num_std_dev=3.0)
```

### BollingerBandsCalculator

Efficient Bollinger Bands calculator with time-based windows.

```python
class BollingerBandsCalculator:
    def __init__(self, window_seconds: int)
    def add_trade(self, timestamp: datetime, price: float, volume: float = 1.0) -> None
    def get_bands(self, num_std_dev: float = 1.0) -> tuple[float, float, float]
    def get_sma(self) -> float
    def get_std_dev(self) -> float
    def get_data_count(self) -> int
    def reset(self) -> None
```

**Features:**
- Time-based rolling window
- Configurable standard deviation multiplier
- Individual component access (SMA, std dev)
- Data count tracking

**Usage:**
```python
from ib_studies.statistics_utils import BollingerBandsCalculator

# 20-minute Bollinger Bands
bb_calc = BollingerBandsCalculator(window_seconds=1200)

# Add trades
bb_calc.add_trade(datetime.now(), 100.0)
bb_calc.add_trade(datetime.now(), 100.5)

# Get bands
sma, upper, lower = bb_calc.get_bands(num_std_dev=2.0)
```

## Performance Considerations

### Memory Management
- **Circular Buffers**: Use fixed-size deques to prevent memory growth
- **Automatic Cleanup**: Old data points are automatically removed
- **Configurable Limits**: Maximum buffer sizes prevent memory issues

### Numerical Stability
- **Welford's Algorithm**: Used for incremental variance calculations
- **Float Precision**: Handles floating-point arithmetic carefully
- **Edge Cases**: Proper handling of zero values and empty datasets

### Computational Efficiency
- **Incremental Updates**: Avoid full recalculation where possible
- **O(1) Operations**: Most updates are constant time
- **Lazy Evaluation**: Calculations performed only when needed

## Error Handling

### Data Validation
```python
# Handle empty datasets
if not data_points:
    return 0.0

# Handle insufficient data
if len(data_points) < 2:
    return 0.0

# Handle zero volume
if total_volume == 0:
    return 0.0
```

### Edge Cases
- **Empty Data**: Returns 0.0 or appropriate default
- **Single Data Point**: Returns price or 0.0 for variance
- **Zero Volume**: Handles division by zero gracefully
- **Invalid Timestamps**: Filters out invalid data points

## Integration with Studies

### Study Implementation Pattern
```python
from ib_studies.statistics_utils import VWAPCalculator
from ib_studies.studies.base import BaseStudy

class MyStudy(BaseStudy):
    def __init__(self, config):
        super().__init__(config)
        self.calculator = VWAPCalculator(config.window_seconds)
    
    def process_tick(self, tick_type, data, stream_id, timestamp):
        # Extract trade data
        trade = self._parse_trade(data)
        
        # Update calculator
        self.calculator.add_trade(trade.timestamp, trade.price, trade.size)
        
        # Get results
        vwap = self.calculator.get_vwap()
        return {"vwap": vwap}
```

### Configuration Integration
```python
# StudyConfig supports study-specific parameters
config = StudyConfig(
    window_seconds=300,
    vwap_std_dev_multiplier=3.0,
    bollinger_std_dev_multiplier=2.0,
    bollinger_period_seconds=1200
)
```

## Testing

### Unit Test Examples
```python
def test_vwap_calculation():
    data = [
        (datetime.now(), 100.0, 1000),
        (datetime.now(), 101.0, 500),
        (datetime.now(), 99.0, 1500),
    ]
    
    vwap = calculate_vwap(data)
    expected = (100*1000 + 101*500 + 99*1500) / (1000 + 500 + 1500)
    assert abs(vwap - expected) < 0.01

def test_bollinger_bands():
    prices = [100, 101, 99, 102, 98, 103, 97, 104]
    data = [(datetime.now(), price, 100) for price in prices]
    
    sma, upper, lower = calculate_bollinger_bands(data, num_std_dev=2.0)
    
    assert sma == sum(prices) / len(prices)
    assert upper > sma
    assert lower < sma
```

### Performance Testing
```python
def test_memory_usage():
    window = TimeWindow(window_seconds=300, max_size=10000)
    
    # Add many data points
    for i in range(15000):
        window.add_point(datetime.now(), 100.0 + i * 0.01, 100)
    
    # Should not exceed max_size
    assert window.size() <= 10000
```

## Best Practices

### When to Use Each Function
- **calculate_vwap()**: One-time calculation with static data
- **VWAPCalculator**: Real-time streaming data with incremental updates
- **calculate_bollinger_bands()**: Batch analysis of historical data
- **BollingerBandsCalculator**: Live market data with rolling windows

### Memory Management
- Use appropriate `max_size` for time windows
- Reset calculators between sessions
- Monitor memory usage in long-running processes

### Numerical Precision
- Use double precision for financial calculations
- Handle edge cases (zero division, empty data)
- Validate input data before calculations

## Future Enhancements

### Planned Features
- **Exponential Moving Averages**: Weighted moving averages
- **Correlation Calculations**: Multi-asset correlation analysis
- **Risk Metrics**: Value at Risk (VaR) and Expected Shortfall
- **Performance Attribution**: Return decomposition analysis

### Optimization Opportunities
- **Vectorized Operations**: NumPy integration for bulk calculations
- **Parallel Processing**: Multi-threaded calculations for large datasets
- **Caching**: Memoization for expensive calculations
- **Streaming Algorithms**: More efficient online algorithms