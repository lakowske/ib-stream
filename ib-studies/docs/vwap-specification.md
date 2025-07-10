# VWAP Study Specification

## Overview

The Volume Weighted Average Price (VWAP) study calculates the average price weighted by volume over a specified time period. This study includes volatility-based bands using realized volatility to provide context for price movements relative to the volume-weighted average.

## Mathematical Definition

### Volume Weighted Average Price (VWAP)

```
VWAP = Σ(Price × Volume) / Σ(Volume)
```

Where:
- `Price` = Trade execution price
- `Volume` = Trade volume
- `Σ` = Sum over all trades in the time period

### Realized Volatility

```
Realized Volatility = sqrt(Σ(log_returns²) / N × Annualization_Factor)
```

Where:
- `log_returns` = ln(P_t / P_{t-1})
- `N` = Number of observations
- `Annualization_Factor` = 252 (trading days per year)

### VWAP Bands

```
Upper Band = VWAP + (3 × Realized Volatility)
Lower Band = VWAP - (3 × Realized Volatility)
```

## Implementation Details

### Data Requirements

**Required Tick Types:**
- `last` - Regular market trades
- `all_last` - All trades including pre/post market (optional)

**Data Fields:**
- `timestamp` - Trade execution time
- `price` - Trade price
- `size` - Trade volume
- `exchange` - Exchange identifier (optional)

### Time Windows

#### Session-Based VWAP (Default)
- Calculates VWAP from market open to current time
- Resets at market open each day
- Most common implementation for institutional trading

#### Custom Time Window
- Rolling window of specified duration (e.g., 1 hour, 30 minutes)
- Continuously updates as new trades arrive
- Useful for intraday analysis

### Calculation Algorithm

1. **Initialize**: Set cumulative price×volume and volume to zero
2. **Process Trade**: For each incoming trade:
   - Add `price × volume` to cumulative price×volume
   - Add `volume` to cumulative volume
   - Calculate current VWAP
3. **Calculate Volatility**: 
   - Compute log returns from recent trades
   - Calculate standard deviation of log returns
   - Annualize volatility
4. **Generate Bands**: Apply 3-sigma bands around VWAP
5. **Output**: Return VWAP, bands, and summary statistics

### Performance Considerations

- **Memory Efficiency**: Use circular buffers for time-windowed calculations
- **Incremental Updates**: Avoid recalculating entire VWAP on each trade
- **Numerical Stability**: Use Welford's algorithm for volatility calculations

## Usage Examples

### CLI Usage

```bash
# Session-based VWAP for contract 711280073
ib-studies vwap --contract 711280073

# 1-hour rolling VWAP
ib-studies vwap --contract 711280073 --window 3600

# Custom volatility bands (2-sigma instead of 3-sigma)
ib-studies vwap --contract 711280073 --std-dev 2.0

# Output to file
ib-studies vwap --contract 711280073 --output vwap_analysis.json

# Specify timezone
ib-studies vwap --contract 711280073 --timezone "US/Eastern"
```

### Output Format

#### Human-Readable Output
```
IB-Studies VWAP Analysis
Contract: 711280073 (MNQ)
Window: Session-based
Started: 2025-01-09 09:30:00 EST

Time         Price    Volume    VWAP     Upper(+3σ)  Lower(-3σ)  Status
──────────────────────────────────────────────────────────────────────
09:30:15     19850.0   25       19850.0   19851.2     19848.8     Normal
09:30:30     19851.5   15       19850.4   19852.1     19848.7     Normal
09:30:45     19849.0   30       19850.1   19851.8     19848.4     Normal
09:31:00     19853.0   20       19850.7   19852.3     19849.1     Upper Touch

Session Summary:
  Total Volume: 90 contracts
  VWAP: 19850.7
  Realized Volatility: 0.15%
  Upper Band: 19852.3
  Lower Band: 19849.1
  Band Touches: 1
```

#### JSON Output
```json
{
  "study": "vwap",
  "contract_id": 711280073,
  "timestamp": "2025-01-09T14:31:00.123Z",
  "window_type": "session",
  "current_trade": {
    "price": 19853.0,
    "volume": 20,
    "timestamp": "2025-01-09T14:31:00.123Z"
  },
  "vwap": {
    "value": 19850.7,
    "upper_band": 19852.3,
    "lower_band": 19849.1,
    "realized_volatility": 0.0015,
    "band_position": "upper_touch"
  },
  "summary": {
    "total_volume": 90,
    "trade_count": 4,
    "session_start": "2025-01-09T14:30:00.000Z",
    "duration_minutes": 1.0,
    "avg_trade_size": 22.5,
    "band_touches": {
      "upper": 1,
      "lower": 0
    }
  }
}
```

## Interpretation and Trading Applications

### VWAP as Benchmark
- **Above VWAP**: Price is trading above volume-weighted average (potential strength)
- **Below VWAP**: Price is trading below volume-weighted average (potential weakness)
- **At VWAP**: Price is fairly valued relative to volume

### Band Analysis
- **Upper Band Touch**: Price extension beyond normal volatility (potential reversal)
- **Lower Band Touch**: Price compression below normal volatility (potential reversal)
- **Band Expansion**: Increasing volatility
- **Band Contraction**: Decreasing volatility

### Institutional Usage
- **Execution Benchmark**: Compare execution quality against VWAP
- **Order Management**: Split large orders around VWAP levels
- **Market Impact**: Assess impact of large trades on VWAP

## Configuration Options

### StudyConfig Parameters
```python
vwap_config = {
    "window_seconds": 0,        # 0 = session-based, >0 = rolling window
    "std_dev_multiplier": 3.0,  # Standard deviation multiplier for bands
    "min_trades": 2,           # Minimum trades for volatility calculation
    "annualization_factor": 252 # Trading days per year
}
```

### Advanced Options
- **Volume Filtering**: Filter trades by minimum volume
- **Price Filtering**: Remove obvious bad prints
- **Exchange Filtering**: Include/exclude specific exchanges
- **Time Filtering**: Include/exclude pre/post market hours

## Error Handling

### Data Validation
- Verify positive prices and volumes
- Handle missing or invalid timestamps
- Manage market close/open transitions

### Edge Cases
- **No Volume**: Return 0 for VWAP when no trades
- **Single Trade**: Use trade price as VWAP, no bands
- **Market Gaps**: Handle overnight gaps in calculation

### Performance Limits
- **Memory Management**: Limit buffer size for long sessions
- **Calculation Frequency**: Throttle updates for high-frequency data
- **Precision**: Handle floating-point precision issues

## Testing Requirements

### Unit Tests
- Mathematical accuracy of VWAP calculation
- Volatility calculation with known data sets
- Band calculation with various scenarios
- Edge case handling

### Integration Tests
- Real-time data processing
- Memory usage under load
- Performance with high-frequency data
- Cross-timezone handling

### Validation Tests
- Compare against known VWAP implementations
- Validate volatility calculations
- Test band accuracy with historical data

## References

1. **VWAP Definition**: CFA Institute Market Structure and Trading
2. **Realized Volatility**: Andersen, Bollerslev, Diebold, Labys (2001)
3. **Institutional Trading**: Kissell, Glantz (2013) - Optimal Trading Strategies
4. **Market Microstructure**: Hasbrouck (2007) - Empirical Market Microstructure