# Interactive Brokers Tick Types Reference

A comprehensive guide to IB's tick types, their characteristics, and usage in the ib-stream system.

## Overview

Interactive Brokers provides several different tick types through their API, each optimized for different use cases. This document covers the tick types supported by ib-stream and their characteristics.

---

## Supported Tick Types

### 1. `bid_ask` (Bid/Ask Quotes)

**Description**: Real-time bid and ask price/size quotes from the market makers.

**Data Fields**:
- `bid_price` (bp) - Current highest bid price
- `bid_size` (bs) - Shares/contracts available at bid
- `ask_price` (ap) - Current lowest ask price  
- `ask_size` (as) - Shares/contracts available at ask
- `bid_past_low` (bpl) - Boolean: Bid below previous day's low
- `ask_past_high` (aph) - Boolean: Ask above previous day's high

**Characteristics**:
- **Frequency**: Very high (100-1000+ updates/minute during active trading)
- **Latency**: Ultra-low (~1-10ms)
- **Source**: Primary exchange + ECNs
- **Use Cases**: Real-time trading, spread analysis, liquidity assessment

**Example JSON**:
```json
{
  "ts": 1755784806394084,
  "st": 1755784806394150,
  "cid": 711280073,
  "tt": "bid_ask",
  "rid": 0,
  "bp": 23199.0,
  "bs": 3.0,
  "ap": 23199.5,
  "as": 2.0
}
```

**Storage Impact**: Highest volume tick type - typically 60-80% of all messages.

---

### 2. `last` (Primary Exchange Trades)

**Description**: Individual trade executions from the primary exchange only.

**Data Fields**:
- `price` (p) - Trade execution price
- `size` (s) - Number of shares/contracts traded
- `unreported` (upt) - Boolean: Trade not reported to consolidated tape

**Characteristics**:
- **Frequency**: Medium (10-100+ trades/minute depending on activity)
- **Latency**: Very low (~1-5ms)
- **Source**: Primary exchange only
- **Precision**: Microsecond timestamps
- **Use Cases**: Real-time price discovery, execution tracking, scalping

**Example JSON**:
```json
{
  "ts": 1755784806394084,
  "st": 1755784806394150,
  "cid": 711280073,
  "tt": "last",
  "rid": 0,
  "p": 23186.5,
  "s": 1.0
}
```

**Storage Impact**: Medium volume - ~10-20% of total messages.

---

### 3. `time_sales` (All Market Trades) → **Mapped to `last`**

**Description**: Consolidated trade data from all exchanges, ECNs, and dark pools.

**Data Fields**: Same as `last` tick type
- `price` (p) - Trade execution price
- `size` (s) - Number of shares/contracts traded
- `unreported` (upt) - Boolean: Off-exchange trade

**Characteristics**:
- **Frequency**: Very high (10x more than `last`)
- **Latency**: Slightly higher (~10-50ms due to consolidation)
- **Source**: All exchanges + ECNs + dark pools + off-exchange
- **Precision**: Often rounded to seconds (batched processing)
- **Use Cases**: Market analysis, volume studies, complete trade picture

**Storage Note**: 
```
⚠️ IMPORTANT: time_sales is mapped to 'last' tick type in storage for efficiency.
This consolidates ~10x more trade data into the same file structure as primary exchange trades.
```

**Volume Comparison**:
- `time_sales`: ~6.9MB/hour (all market activity)
- `last`: ~751KB/hour (primary exchange only)
- **~10x difference** in data volume

---

## Request Configuration

### Background Streaming (Production)

Current production configuration in `config/.env.production`:
```bash
IB_STREAM_TRACKED_CONTRACTS=711280073:MNQ:bid_ask;last:24
```

**Format**: `{contract_id}:{symbol}:{tick_types}:{hours}`

### API Requests

**V2 Streaming**:
```
GET /v2/stream/{contract_id}?tick_types=bid_ask,last
```

**V3 Buffer Query**:
```
GET /v3/buffer/{contract_id}/range?tick_types=bid_ask,last&start_time=2025-08-21T12:00:00Z
```

---

## Storage Architecture

### File Organization

**Pattern**: `{contract_id}_{tick_type}_{hour_timestamp}.{ext}`

**Examples**:
```
711280073_bid_ask_1755781200.jsonl     # Bid/ask quotes
711280073_last_1755781200.jsonl        # All trades (last + time_sales)
711280073_bid_ask_1755781200.pb        # Protobuf format
```

### V3 Optimized Format

**Space Savings**:
- JSON: ~50% smaller than v2 format
- Protobuf: ~35% additional savings over v3 JSON
- **Total**: ~67% space reduction vs v2 format

**Field Mapping**:
```
timestamp → ts (microseconds)
contract_id → cid
tick_type → tt
price → p
size → s
bid_price → bp
ask_price → ap
```

---

## Performance Characteristics

### Message Rates (MNQ Contract)

| Tick Type | Messages/Minute | File Size/Hour | Latency | Primary Use |
|-----------|----------------|----------------|---------|-------------|
| `bid_ask` | 500-1000+ | ~60MB | 1-10ms | Real-time trading |
| `last` | 50-200 | ~751KB | 1-5ms | Price discovery |
| `time_sales`* | 500-2000+ | ~6.9MB | 10-50ms | Market analysis |

*_Mapped to `last` in storage_

### Storage Efficiency

**Hourly Storage (All Formats)**:
- **v3 JSON**: ~65MB total
- **v3 Protobuf**: ~42MB total
- **Combined**: ~107MB/hour for full market data

**Daily Storage Estimate**:
- **24 hours**: ~2.6GB/day
- **Monthly**: ~80GB/month

---

## Data Quality Notes

### Timestamp Precision

- **bid_ask, last**: Microsecond precision IB timestamps
- **time_sales**: Often rounded to second (batched processing)

### Market Hours Impact

- **Regular Hours**: Full data flow
- **Pre/Post Market**: Reduced frequency (~10-50% of regular hours)
- **Closed Market**: Minimal activity, mostly bid/ask updates

### Connection Reliability

- **TWS Connection**: Auto-reconnect with 30s delay
- **Data Gaps**: Background streaming minimizes gaps during reconnections  
- **Health Monitoring**: 5-minute staleness alerts during market hours

---

## Troubleshooting

### Common Issues

**No `time_sales` files**: Expected - data is stored in `last` files for efficiency.

**Large `bid_ask` files**: Normal - highest frequency tick type.

**Timestamp mismatches**: `time_sales` uses rounded timestamps, others use microsecond precision.

### Monitoring Commands

```bash
# Check current data flow
curl -s http://localhost:8851/health | jq .

# Verify file creation
find ./ib-stream/storage -name "*.jsonl" -newermt "5 minutes ago"

# Check storage stats
curl -s http://localhost:8851/v3/storage/stats | jq .
```

---

## Implementation Details

### Categorical Storage Mapping

```python
# time_sales → last mapping for storage efficiency
elif tick_type == 'time_sales':
    return TickMessage.create_from_tick_data(
        contract_id=contract_id or 0,
        tick_type="last",  # Consolidated with primary exchange trades
        tick_data=inner_data,
        request_id=0
    )
```

### Factory Method Usage

The system uses `TickMessage.create_from_tick_data()` for proper timestamp conversion:
```python
# Handles seconds → microseconds conversion automatically
TickMessage.create_from_tick_data(
    contract_id=contract_id,
    tick_type=tick_type,
    tick_data=data,
    request_id=request_id
)
```

---

*Last Updated: August 21, 2025*  
*System Version: ib-stream v2.0 with Categorical Storage*