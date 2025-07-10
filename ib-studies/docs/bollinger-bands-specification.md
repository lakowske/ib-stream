# Bollinger Bands Study Specification

## Overview

The Bollinger Bands study calculates a Simple Moving Average (SMA) with upper and lower bands based on standard deviation of price movements over a specified time period. This study helps identify overbought/oversold conditions and potential mean reversion opportunities.

## Mathematical Definition

### Simple Moving Average (SMA)

```
SMA = Σ(Price) / N
```

Where:
- `Price` = Trade execution price
- `N` = Number of observations in the time window

### Standard Deviation

```
Standard Deviation = sqrt(Σ(Price - SMA)² / N)
```

### Bollinger Bands

```
Upper Band = SMA + (K × Standard Deviation)
Lower Band = SMA - (K × Standard Deviation)
```

Where:
- `K` = Number of standard deviations (default: 1.0)

## Implementation Details

### Data Requirements

**Required Tick Types:**
- `last` - Regular market trades
- `all_last` - All trades including pre/post market (optional)

**Data Fields:**
- `timestamp` - Trade execution time
- `price` - Trade price
- `size` - Trade volume (for weighting if needed)

### Time Windows

#### N-Minute Rolling Window
- Default: 20 minutes (1200 seconds)
- Continuously updates as new trades arrive
- Maintains only the last N minutes of data

#### Configurable Periods
- 5-minute: Short-term scalping
- 20-minute: Standard intraday analysis
- 60-minute: Longer-term trend analysis
- Custom: Any period specified in seconds

### Calculation Algorithm

1. **Initialize**: Create time window buffer
2. **Process Trade**: For each incoming trade:
   - Add trade price to time window
   - Remove trades older than window period
   - Calculate SMA of current prices
3. **Calculate Standard Deviation**:
   - Compute variance of prices around SMA
   - Take square root for standard deviation
4. **Generate Bands**: Apply K-sigma bands around SMA
5. **Output**: Return SMA, bands, and analysis

### Performance Considerations

- **Memory Efficiency**: Use circular buffers for price data
- **Incremental Updates**: Efficient recalculation when adding/removing prices
- **Numerical Stability**: Handle floating-point precision issues

## Usage Examples

### CLI Usage

```bash
# 20-minute Bollinger Bands for contract 711280073
ib-studies bollinger --contract 711280073

# 5-minute bands with custom period
ib-studies bollinger --contract 711280073 --period 300

# 2-sigma bands instead of 1-sigma
ib-studies bollinger --contract 711280073 --std-dev 2.0

# Output to file
ib-studies bollinger --contract 711280073 --output bollinger_analysis.json

# Specify timezone
ib-studies bollinger --contract 711280073 --timezone "US/Eastern"
```

### Output Format

#### Human-Readable Output
```
IB-Studies Bollinger Bands Analysis
Contract: 711280073 (MNQ)
Period: 20 minutes
Standard Deviations: 1.0

Time         Price    SMA      Upper(+1σ)  Lower(-1σ)  Position     %B
────────────────────────────────────────────────────────────────────────
14:30:15     19850.0  19849.2   19851.5     19846.9     Above SMA    0.35
14:30:30     19851.5  19849.5   19852.1     19846.9     Near Upper   0.89
14:30:45     19849.0  19849.4   19851.8     19847.0     At SMA       0.42
14:31:00     19847.5  19849.2   19851.4     19847.0     Below SMA    0.11
14:31:15     19853.0  19849.8   19852.1     19847.5     Upper Touch  1.22

Period Summary (20 minutes):
  SMA: 19849.8
  Upper Band: 19852.1
  Lower Band: 19847.5
  Band Width: 4.6
  Current %B: 1.22
  Band Touches: Upper=1, Lower=0
  Mean Reversion Signals: 0
```

#### JSON Output
```json
{
  "study": "bollinger_bands",
  "contract_id": 711280073,
  "timestamp": "2025-01-09T19:31:15.123Z",
  "period_seconds": 1200,
  "std_dev_multiplier": 1.0,
  "current_trade": {
    "price": 19853.0,
    "timestamp": "2025-01-09T19:31:15.123Z"
  },
  "bands": {
    "sma": 19849.8,
    "upper_band": 19852.1,
    "lower_band": 19847.5,
    "band_width": 4.6,
    "band_width_pct": 0.023
  },
  "analysis": {
    "price_position": "above_upper",
    "percent_b": 1.22,
    "distance_from_sma": 3.2,
    "distance_from_upper": 0.9,
    "distance_from_lower": 5.5
  },
  "summary": {
    "trade_count": 45,
    "period_start": "2025-01-09T19:11:15.000Z",
    "band_touches": {
      "upper": 1,
      "lower": 0
    },
    "volatility_regime": "normal",
    "mean_reversion_signals": 0
  }
}
```

## Interpretation and Trading Applications

### Band Position Analysis
- **Above Upper Band**: Overbought condition, potential sell signal
- **Below Lower Band**: Oversold condition, potential buy signal
- **Near SMA**: Neutral zone, trend continuation likely
- **Between SMA and Bands**: Normal trading range

### %B Indicator
```
%B = (Price - Lower Band) / (Upper Band - Lower Band)
```

- **%B > 1.0**: Price above upper band (overbought)
- **%B < 0.0**: Price below lower band (oversold)
- **%B = 0.5**: Price at SMA (neutral)

### Band Width Analysis
- **Expanding Bands**: Increasing volatility
- **Contracting Bands**: Decreasing volatility (squeeze)
- **Narrow Bands**: Low volatility, potential breakout
- **Wide Bands**: High volatility, potential reversal

### Trading Strategies

#### Mean Reversion
- **Entry**: Price touches band (overbought/oversold)
- **Exit**: Price returns to SMA
- **Stop**: Price breaks through band with volume

#### Trend Following
- **Uptrend**: Price stays above SMA, upper band acts as support
- **Downtrend**: Price stays below SMA, lower band acts as resistance
- **Breakout**: Price breaks through band with expansion

#### Volatility Trading
- **Squeeze**: Bands contract, prepare for breakout
- **Expansion**: Bands widen, momentum play
- **Reversion**: Bands return to normal width

## Configuration Options

### StudyConfig Parameters
```python
bollinger_config = {
    "period_seconds": 1200,     # 20 minutes default
    "std_dev_multiplier": 1.0,  # Standard deviation multiplier
    "min_trades": 10,          # Minimum trades for calculation
    "band_touch_threshold": 0.1 # Distance considered "touching" band
}
```

### Advanced Options
- **Volume Weighting**: Weight prices by volume
- **Price Filtering**: Remove outliers and bad prints
- **Adaptive Periods**: Adjust period based on volatility
- **Multiple Timeframes**: Different periods simultaneously

## Band Touch Detection

### Touch Criteria
- **Exact Touch**: Price exactly equals band level
- **Threshold Touch**: Price within threshold of band
- **Penetration**: Price breaks through band

### Signal Generation
- **Touch Count**: Number of band touches per period
- **Touch Duration**: Time spent at band levels
- **Touch Strength**: Volume at band touch points

## Error Handling

### Data Validation
- Verify positive prices
- Handle missing timestamps
- Manage data gaps and market closures

### Edge Cases
- **Insufficient Data**: Require minimum number of trades
- **Zero Volatility**: Handle constant price scenarios
- **Extreme Outliers**: Filter or handle price spikes

### Performance Limits
- **Memory Management**: Limit buffer size for long periods
- **Calculation Frequency**: Optimize for high-frequency updates
- **Precision**: Handle floating-point arithmetic issues

## Testing Requirements

### Unit Tests
- SMA calculation accuracy
- Standard deviation calculation
- Band calculation with various scenarios
- %B indicator calculation

### Integration Tests
- Real-time data processing
- Memory usage optimization
- Performance with high-frequency data
- Time window management

### Validation Tests
- Compare against known implementations
- Validate statistical calculations
- Test edge cases and error conditions

## Historical Context

### Original Development
- **Creator**: John Bollinger (1980s)
- **Purpose**: Volatility-based technical analysis
- **Innovation**: Adaptive bands based on standard deviation

### Market Applications
- **Equity Trading**: Most common application
- **Forex**: 4-hour and daily charts
- **Futures**: Intraday mean reversion
- **Options**: Volatility assessment

### Modern Adaptations
- **Algorithmic Trading**: Automated mean reversion systems
- **High-Frequency Trading**: Sub-second band calculations
- **Multi-Asset**: Cross-market analysis
- **Machine Learning**: Feature engineering for models

## References

1. **Original Work**: Bollinger, J. (2001) - Bollinger on Bollinger Bands
2. **Technical Analysis**: Murphy, J. (1999) - Technical Analysis of Financial Markets
3. **Quantitative Trading**: Chan, E. (2008) - Quantitative Trading
4. **Statistical Methods**: Taylor, S. (2005) - Asset Price Dynamics, Volatility, and Prediction