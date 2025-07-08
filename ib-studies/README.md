# IB-Studies

Real-time market data analysis using IB-Stream. This project provides tools for analyzing order flow and market microstructure using streaming data from Interactive Brokers.

## Features

- **Delta Study**: Measures buying and selling pressure by tracking trades relative to the bid-ask spread
- Real-time streaming analysis with configurable time windows
- Multiple output formats (human-readable and JSON)
- Robust error handling and automatic reconnection

## Installation

```bash
# Clone the repository
git clone https://github.com/seth/ib-studies.git
cd ib-studies

# Install in development mode
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

## Prerequisites

1. IB-Stream server running on `http://localhost:8001`
2. Interactive Brokers TWS or Gateway with API enabled
3. Python 3.9 or higher

## Usage

### Delta Study

The delta study tracks buying and selling pressure in real-time:

```bash
# Basic usage with contract ID
ib-studies delta --contract 265598

# With custom time window (seconds)
ib-studies delta --contract 265598 --window 300

# JSON output format
ib-studies delta --contract 265598 --json

# Save to file (JSON Lines format)
ib-studies delta --contract 265598 --output delta_data.jsonl

# Use specific tick types
ib-studies delta --contract 265598 --tick-types Last,AllLast
```

### Output Formats

#### Human-Readable Output
```
IB-Studies Delta Analysis
Contract: 265598
Window: 60 seconds

Time         Price    Size   Bid      Ask      Delta    Cumulative
─────────────────────────────────────────────────────────────────
10:30:15     175.26   100    175.25   175.26   +100     +100
10:30:16     175.25   200    175.25   175.26   -200     -100
10:30:17     175.26   150    175.25   175.26   +150     +50

Summary (last 60s):
  Total Buys:  250 shares
  Total Sells: 200 shares
  Net Delta:   +50 shares
  Buy/Sell Ratio: 1.25
```

#### JSON Output
Each line is a JSON object with current state:
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

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ib_studies

# Run specific test file
pytest tests/test_delta.py
```

### Code Quality

```bash
# Format code
black ib_studies tests

# Lint code
ruff check ib_studies tests

# Type checking
mypy ib_studies
```

## Architecture

IB-Studies uses an event-driven architecture to process streaming market data:

1. **StreamClient**: Connects to IB-Stream SSE endpoints
2. **Study Engine**: Processes tick data through pluggable studies
3. **Output Formatters**: Presents results in various formats

See [docs/ib-studies-architecture.md](docs/ib-studies-architecture.md) for detailed architecture documentation.

## License

MIT License - see LICENSE file for details