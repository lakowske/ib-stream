# IB-Studies Architecture Document

## Executive Summary

IB-Studies is a library and CLI tool for performing real-time market data analysis using streaming data from IB-Stream. The project will be developed in phases, starting with a Delta Study that calculates buying and selling pressure based on trades crossing the bid-ask spread. Future phases will add additional studies like VWAP, SMA, and other market microstructure indicators.

## Architecture Overview

### System Context

```
┌─────────────────┐     SSE Stream      ┌─────────────────┐
│   IB Gateway/   │◄────────────────────►│   IB-Stream     │
│      TWS        │                      │   API Server    │
└─────────────────┘                      └────────┬────────┘
                                                  │ SSE Events
                                                  ▼
                                         ┌─────────────────┐
                                         │   IB-Studies    │
                                         │   CLI/Library   │
                                         └────────┬────────┘
                                                  │
                                         ┌────────┴────────┐
                                         ▼                 ▼
                                 ┌──────────────┐  ┌──────────────┐
                                 │ Human Output │  │ JSON Output  │
                                 └──────────────┘  └──────────────┘
```

### Core Components

1. **Stream Consumer**: SSE client that connects to IB-Stream endpoints
2. **Study Engine**: Pluggable architecture for different market studies
3. **Data Pipeline**: Event-driven processing with buffering and windowing
4. **Output Formatters**: Human-readable and JSON output options
5. **CLI Interface**: Command-line tool for running studies

## Phase 1: Delta Study Implementation

### What is Delta?

Delta measures buying and selling pressure by tracking trades relative to the bid-ask spread:
- **Positive Delta**: Trade executed at or above the ask price (buying pressure)
- **Negative Delta**: Trade executed at or below the bid price (selling pressure)
- **Neutral Delta**: Trade executed between bid and ask (no clear direction)

### Delta Calculation Methodology

```python
def calculate_delta(trade_price, bid_price, ask_price, trade_size):
    """
    Calculate delta for a single trade
    
    Returns:
        positive value: buying pressure
        negative value: selling pressure
        zero: neutral/unknown
    """
    if trade_price >= ask_price:
        return trade_size  # Buy at ask or higher
    elif trade_price <= bid_price:
        return -trade_size  # Sell at bid or lower
    else:
        # Trade inside spread - could use more sophisticated logic
        return 0  # or proportional assignment
```

### Technical Design

#### Data Structures

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List

@dataclass
class MarketQuote:
    timestamp: datetime
    bid_price: float
    ask_price: float
    bid_size: float
    ask_size: float

@dataclass
class Trade:
    timestamp: datetime
    price: float
    size: float
    exchange: str
    conditions: List[str]

@dataclass
class DeltaPoint:
    timestamp: datetime
    trade: Trade
    quote: MarketQuote
    delta: float
    cumulative_delta: float
```

#### Stream Processing Pipeline

```python
class DeltaStudy:
    def __init__(self, window_seconds: int = 60):
        self.current_quote: Optional[MarketQuote] = None
        self.delta_buffer: List[DeltaPoint] = []
        self.cumulative_delta: float = 0
        self.window_seconds = window_seconds
    
    def process_bid_ask(self, data: dict):
        """Update current market quote"""
        self.current_quote = MarketQuote(
            timestamp=parse_timestamp(data['timestamp']),
            bid_price=data['bid_price'],
            ask_price=data['ask_price'],
            bid_size=data['bid_size'],
            ask_size=data['ask_size']
        )
    
    def process_trade(self, data: dict):
        """Process trade and calculate delta"""
        if not self.current_quote:
            return  # Need quote data first
        
        trade = Trade(
            timestamp=parse_timestamp(data['timestamp']),
            price=data['price'],
            size=data['size'],
            exchange=data.get('exchange', ''),
            conditions=data.get('conditions', [])
        )
        
        delta = self.calculate_delta(
            trade.price,
            self.current_quote.bid_price,
            self.current_quote.ask_price,
            trade.size
        )
        
        self.cumulative_delta += delta
        
        delta_point = DeltaPoint(
            timestamp=trade.timestamp,
            trade=trade,
            quote=self.current_quote,
            delta=delta,
            cumulative_delta=self.cumulative_delta
        )
        
        self.delta_buffer.append(delta_point)
        self.cleanup_old_data()
```

### CLI Interface Design

#### Basic Usage

```bash
# Stream delta for AAPL (using contract ID)
ib-studies delta --contract 265598

# Stream with custom window
ib-studies delta --contract 265598 --window 300

# Output as JSON
ib-studies delta --contract 265598 --json

# Use both Last and AllLast tick types
ib-studies delta --contract 265598 --tick-types Last,AllLast

# Save to file
ib-studies delta --contract 265598 --output delta_aapl.jsonl
```

#### Output Formats

**Human-Readable Output:**
```
IB-Studies Delta Analysis
Contract: 265598 (AAPL)
Window: 60 seconds

Time         Price    Size   Bid      Ask      Delta    Cumulative
─────────────────────────────────────────────────────────────────
10:30:15     175.26   100    175.25   175.26   +100     +100
10:30:16     175.25   200    175.25   175.26   -200     -100
10:30:17     175.26   150    175.25   175.26   +150     +50
10:30:18     175.255  50     175.25   175.26   0        +50

Summary (last 60s):
  Total Buys:  250 shares
  Total Sells: 200 shares
  Net Delta:   +50 shares
  Buy/Sell Ratio: 1.25
```

**JSON Output:**
```json
{
  "study": "delta",
  "contract_id": 265598,
  "timestamp": "2025-01-08T10:30:18.123Z",
  "window_seconds": 60,
  "data": {
    "current_delta": 0,
    "cumulative_delta": 50,
    "period_stats": {
      "total_buy_volume": 250,
      "total_sell_volume": 200,
      "net_delta": 50,
      "buy_sell_ratio": 1.25,
      "trade_count": 4
    }
  }
}
```

### Implementation Plan

1. **Core Library Structure:**
   ```
   ib-studies/
   ├── ib_studies/
   │   ├── __init__.py
   │   ├── stream_client.py      # SSE consumer
   │   ├── studies/
   │   │   ├── __init__.py
   │   │   ├── base.py          # Base study class
   │   │   └── delta.py         # Delta study implementation
   │   ├── formatters/
   │   │   ├── __init__.py
   │   │   ├── human.py         # Human-readable output
   │   │   └── json.py          # JSON output
   │   └── cli.py               # CLI entry point
   ├── tests/
   ├── setup.py
   └── requirements.txt
   ```

2. **Key Classes:**
   - `StreamClient`: Handles SSE connection and event parsing
   - `BaseStudy`: Abstract base class for all studies
   - `DeltaStudy`: Implements delta calculation logic
   - `OutputFormatter`: Base class for formatters
   - `CLI`: Command-line interface using Click or argparse

3. **Error Handling:**
   - Reconnection logic for SSE disconnects
   - Quote synchronization (handle missing quotes)
   - Data validation and sanitization
   - Graceful shutdown on interrupts

## Future Studies Roadmap

### Phase 2: VWAP (Volume Weighted Average Price)

```python
class VWAPStudy(BaseStudy):
    """
    Calculate VWAP over rolling windows
    VWAP = Σ(Price × Volume) / Σ(Volume)
    """
    def __init__(self, window_seconds: int = 300):
        self.price_volume_sum = 0
        self.volume_sum = 0
        self.data_points = []
```

### Phase 3: SMA (Simple Moving Average)

```python
class SMAStudy(BaseStudy):
    """
    Calculate multiple SMAs simultaneously
    """
    def __init__(self, periods: List[int] = [20, 50, 200]):
        self.periods = periods
        self.price_buffer = deque(maxlen=max(periods))
```

### Phase 4: Advanced Studies

1. **Order Flow Imbalance**
   - Measure bid/ask volume imbalances
   - Identify potential price movements

2. **Cumulative Volume Delta (CVD)**
   - Track cumulative buying vs selling over time
   - Identify trend strength and reversals

3. **Market Profile**
   - Volume distribution by price level
   - Identify high-volume nodes and value areas

4. **Footprint Charts**
   - Detailed bid/ask volume at each price level
   - Visualize order flow within candles

### Phase 5: Composite Studies

1. **Multi-Study Dashboard**
   - Run multiple studies simultaneously
   - Correlate signals across studies

2. **Custom Study Builder**
   - DSL for defining custom studies
   - Combine existing indicators

## API Design

### Study Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseStudy(ABC):
    """Base class for all market studies"""
    
    @abstractmethod
    def process_tick(self, tick_type: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process incoming tick data"""
        pass
    
    @abstractmethod
    def get_summary(self) -> Dict[str, Any]:
        """Get current study summary"""
        pass
    
    @abstractmethod
    def reset(self):
        """Reset study state"""
        pass
    
    @property
    @abstractmethod
    def required_tick_types(self) -> List[str]:
        """List of required tick types for this study"""
        pass
```

### Stream Client Interface

```python
class StreamClient:
    """SSE client for consuming IB-Stream data"""
    
    async def connect(self, contract_id: int, tick_types: List[str]):
        """Connect to stream endpoint"""
        pass
    
    async def consume(self, callback: Callable[[str, Dict], None]):
        """Consume events with callback"""
        pass
    
    async def disconnect(self):
        """Clean disconnect"""
        pass
```

## Testing Strategy

### Unit Tests
- Delta calculation accuracy
- Edge cases (zero spreads, crossed markets)
- Buffer management and windowing
- Output formatting

### Integration Tests
- SSE connection handling
- Stream reconnection
- Multi-study coordination
- Performance under high tick rates

### Mock Data Generator
```python
class MockStreamGenerator:
    """Generate realistic tick data for testing"""
    
    def generate_tick_sequence(self, 
                             base_price: float,
                             volatility: float,
                             tick_rate: int):
        """Generate realistic bid/ask/trade sequence"""
        pass
```

## Performance Considerations

1. **Memory Management**
   - Use circular buffers for time windows
   - Implement data expiration
   - Stream processing without full history

2. **CPU Optimization**
   - Minimize calculations per tick
   - Use numpy for bulk operations
   - Profile hot paths

3. **Scalability**
   - Support multiple concurrent studies
   - Efficient event dispatching
   - Consider process pooling for CPU-intensive studies

## Configuration

### Sample Configuration File
```yaml
# ib-studies.config.yaml
stream:
  base_url: "http://localhost:8001"
  timeout: 30
  reconnect_delay: 5

studies:
  delta:
    default_window: 60
    neutral_zone: 0.01  # % of spread for neutral trades
  
  vwap:
    default_window: 300
    
output:
  decimal_places: 2
  timestamp_format: "%Y-%m-%d %H:%M:%S"
  
logging:
  level: INFO
  file: ib-studies.log
```

## Deployment Considerations

1. **Docker Support**
   ```dockerfile
   FROM python:3.9-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install -r requirements.txt
   COPY . .
   CMD ["ib-studies", "delta", "--contract", "265598"]
   ```

2. **Systemd Service**
   ```ini
   [Unit]
   Description=IB-Studies Delta Monitor
   After=ib-stream.service

   [Service]
   Type=simple
   ExecStart=/usr/local/bin/ib-studies delta --contract 265598
   Restart=always
   
   [Install]
   WantedBy=multi-user.target
   ```

## Next Steps

1. Set up project structure and dependencies
2. Implement SSE stream client
3. Build delta study core logic
4. Create CLI interface
5. Add output formatters
6. Write comprehensive tests
7. Document usage and examples
8. Plan Phase 2 features

This architecture provides a solid foundation for building sophisticated market analysis tools while maintaining flexibility for future enhancements.