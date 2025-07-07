# ib-stream

Interactive Brokers streaming data client for real-time market data

## Features

- Stream real-time time & sales data (tick-by-tick)
- Support for multiple data types: trades, quotes, midpoint
- JSON output for easy integration with other tools
- Limit number of ticks or stream continuously
- Automatic connection to TWS/IB Gateway

## Installation

```bash
pip install -e .[dev]
```

## Prerequisites

1. Interactive Brokers account
2. TWS (Trader Workstation) or IB Gateway running
3. API connections enabled in TWS/Gateway settings

## Usage

### Basic Usage

Stream time & sales data for a contract:

```bash
# Stream trades for Apple stock (contract ID: 265598)
ib-stream 265598

# Stream only 20 ticks then stop
ib-stream 265598 --number 20

# Stream bid/ask quotes instead of trades
ib-stream 265598 --type BidAsk
```

### Available Data Types

- `Last` - Regular trades during market hours (default)
- `AllLast` - All trades including pre/post market
- `BidAsk` - Real-time bid and ask quotes
- `MidPoint` - Calculated midpoint between bid and ask

### JSON Output

Output data as JSON for processing by other tools:

```bash
# Stream as JSON (one object per line)
ib-stream 265598 --json

# Process with jq
ib-stream 265598 --json | jq '.price'

# Save to file
ib-stream 265598 --json > trades.jsonl
```

### Finding Contract IDs

Use the `ib-contract` tool to find contract IDs:

```bash
# Install ib-contract (if not already installed)
pip install ib-contract

# Look up Apple stock
ib-contract AAPL --type STK
```

### Command Line Options

```
ib-stream CONTRACT_ID [OPTIONS]

Options:
  --number, -n NUM      Number of ticks to stream (default: unlimited)
  --type, -t TYPE       Data type: Last, AllLast, BidAsk, MidPoint
  --json, -j            Output as JSON
  --verbose, -v         Enable verbose logging
  --client-id NUM       TWS client ID (default: 2)
  --help, -h            Show help message
```

## Examples

```bash
# Stream S&P 500 futures trades
ib-stream 551601777 --type AllLast

# Get 100 bid/ask quotes for EUR/USD
ib-stream 12087792 --type BidAsk --number 100

# Monitor midpoint prices as JSON
ib-stream 265598 --type MidPoint --json

# Stream with verbose logging for debugging
ib-stream 265598 --verbose
```

## Output Format

### Standard Output
```
2024-01-15 09:30:00 |   175.2500 |        100 |  NASDAQ
2024-01-15 09:30:01 |   175.2600 |        200 |   NYSE
```

### JSON Output
```json
{"type": "time_sales", "timestamp": "2024-01-15 09:30:00", "price": 175.25, "size": 100, "exchange": "NASDAQ"}
```

## Development

This project uses ruff for linting and formatting:

```bash
ruff check .    # Run linting
ruff format .   # Run formatting
pytest          # Run tests
```

## Future Features

- WebSocket server for browser-based streaming
- HTTP API endpoints for REST access
- Multiple contract streaming
- Data recording and replay
- Real-time charting integration