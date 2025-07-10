# IB-Stream Storage and Caching Design

## Executive Summary

This document outlines the design and implementation plan for adding persistent storage and caching capabilities to IB-Stream. The goal is to enable IB-Studies to access historical market data for statistical analysis over various time periods, from minutes to months.

## Requirements

### Functional Requirements

1. **Store streaming market data to disk** for later retrieval
2. **Support flexible time-range queries** including:
   - Current session data (midnight to present)
   - Trading session boundaries (9:30 AM - 4:00 PM ET)
   - Custom ranges for backtesting
   - Rolling windows (last 24 hours, last week, etc.)
3. **Handle large data volumes** efficiently (millions of ticks per day)
4. **Maintain data integrity** during concurrent reads/writes
5. **Support multiple tick types** (last, bid_ask, etc.) per contract
6. **Enable real-time + historical data combination** for continuous analysis

### Non-Functional Requirements

1. **Low latency** for recent data queries (<100ms)
2. **Scalable storage** (handle years of tick data)
3. **Efficient compression** to minimize disk usage
4. **Fast startup** with cache warming
5. **Configurable retention policies**
6. **Minimal impact on streaming performance**

## Storage Format Options

### Option 1: Apache Parquet (Recommended)

**Pros:**
- Columnar format optimized for analytics
- Excellent compression (70-90% reduction)
- Fast queries on specific columns
- Native support for time-series partitioning
- Wide ecosystem support (pandas, arrow, etc.)

**Cons:**
- Not ideal for real-time writes (batch oriented)
- Requires periodic compaction
- Binary format (not human readable)

**Implementation:**
```python
# Example structure
/storage/
  /contracts/
    /265598/  # AAPL
      /2025/01/10/
        bid_ask_00.parquet  # Hour 00
        bid_ask_01.parquet  # Hour 01
        last_09.parquet     # Hour 09
        metadata.json       # Daily metadata
```

### Option 2: Time-Series Database (InfluxDB/TimescaleDB)

**Pros:**
- Purpose-built for time-series data
- Built-in downsampling and retention
- SQL-like query interface
- Real-time aggregations

**Cons:**
- Additional infrastructure dependency
- Higher operational complexity
- Potential single point of failure
- License considerations

### Option 3: JSON Lines with Indexes

**Pros:**
- Human readable
- Simple to implement
- Streaming-friendly (append-only)
- Easy debugging

**Cons:**
- Large file sizes
- Slower queries
- Manual index management
- Limited compression

### Option 4: Protocol Buffers with RocksDB

**Pros:**
- Efficient binary serialization
- Fast key-value lookups
- Built-in compression
- Good for real-time updates

**Cons:**
- Complex schema management
- Requires protobuf definitions
- Less suitable for range queries
- Additional dependencies

## Recommended Architecture

### Hybrid Approach: Parquet + JSON Buffer

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Live Stream    │────▶│  JSON Buffer     │────▶│ Parquet Archive │
│  (Real-time)    │     │  (Recent Data)   │     │ (Historical)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │                          │
                               ▼                          ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │  Memory Cache    │     │  Metadata Index │
                        │  (Hot Data)      │     │  (SQLite)       │
                        └──────────────────┘     └─────────────────┘
```

### Components

#### 1. JSON Buffer (Real-time Layer)
- Stores most recent data (last 1-2 hours)
- Append-only JSON lines format
- Low-latency writes
- Automatic rotation

```python
# storage/buffer.py
class StreamBuffer:
    def __init__(self, buffer_duration_minutes=120):
        self.buffer_path = Path("storage/buffer")
        self.current_file = None
        self.rotation_interval = timedelta(minutes=15)
    
    async def append_tick(self, stream_id: str, tick_data: dict):
        """Append tick to current buffer file."""
        file_path = self._get_current_file(stream_id)
        async with aiofiles.open(file_path, 'a') as f:
            await f.write(json.dumps(tick_data) + '\n')
```

#### 2. Parquet Archive (Historical Layer)
- Hourly partitioned files
- Compressed columnar storage
- Optimized for analytics
- Background compaction

```python
# storage/archive.py
class ParquetArchive:
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.compaction_scheduler = BackgroundScheduler()
    
    async def archive_buffer(self, buffer_file: Path):
        """Convert JSON buffer to Parquet."""
        df = pd.read_json(buffer_file, lines=True)
        
        # Parse and optimize data types
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        # Write to partitioned Parquet
        output_path = self._get_archive_path(df.iloc[0]['timestamp'])
        df.to_parquet(output_path, compression='snappy')
```

#### 3. Metadata Index (SQLite)
- Tracks available data ranges
- Stores file locations
- Enables fast lookups
- Maintains statistics

```sql
-- Schema for metadata index
CREATE TABLE tick_archives (
    id INTEGER PRIMARY KEY,
    contract_id INTEGER NOT NULL,
    tick_type TEXT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    file_path TEXT NOT NULL,
    tick_count INTEGER,
    file_size_bytes INTEGER,
    compression_ratio REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_contract_time (contract_id, tick_type, start_time, end_time)
);

CREATE TABLE data_statistics (
    contract_id INTEGER NOT NULL,
    tick_type TEXT NOT NULL,
    date DATE NOT NULL,
    total_ticks INTEGER,
    unique_prices INTEGER,
    total_volume REAL,
    vwap REAL,
    high_price REAL,
    low_price REAL,
    
    PRIMARY KEY (contract_id, tick_type, date)
);
```

#### 4. Query Interface

```python
# storage/query.py
class StorageQuery:
    def __init__(self, archive: ParquetArchive, buffer: StreamBuffer):
        self.archive = archive
        self.buffer = buffer
        self.cache = LRUCache(maxsize=1000)
    
    async def query_range(
        self, 
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: Optional[datetime] = None,
        resolution: Optional[str] = None  # 'tick', '1s', '1m', etc.
    ) -> pd.DataFrame:
        """Query historical data with optional downsampling."""
        
        # Default to current time
        if end_time is None:
            end_time = datetime.now()
        
        # Check cache first
        cache_key = f"{contract_id}:{tick_types}:{start_time}:{end_time}"
        if cached := self.cache.get(cache_key):
            return cached
        
        # Determine data sources
        sources = self._get_data_sources(start_time, end_time)
        
        # Load and combine data
        dfs = []
        
        # Historical data from Parquet
        if sources.get('archive'):
            archive_df = await self._load_archive_data(
                contract_id, tick_types, sources['archive']
            )
            dfs.append(archive_df)
        
        # Recent data from buffer
        if sources.get('buffer'):
            buffer_df = await self._load_buffer_data(
                contract_id, tick_types, sources['buffer']
            )
            dfs.append(buffer_df)
        
        # Combine and process
        result = pd.concat(dfs, ignore_index=True)
        result = result.sort_values('timestamp')
        
        # Apply resolution if requested
        if resolution:
            result = self._downsample(result, resolution)
        
        # Cache result
        self.cache[cache_key] = result
        
        return result
```

### Session Boundary Helpers

```python
# storage/sessions.py
class MarketSessions:
    """Helper for common market session queries."""
    
    @staticmethod
    def get_session_boundaries(
        date: datetime,
        session_type: str = 'regular',
        timezone: str = 'US/Eastern'
    ) -> Tuple[datetime, datetime]:
        """Get session start and end times."""
        
        tz = pytz.timezone(timezone)
        date_local = date.astimezone(tz).date()
        
        sessions = {
            'regular': (time(9, 30), time(16, 0)),     # 9:30 AM - 4:00 PM
            'extended': (time(4, 0), time(20, 0)),      # 4:00 AM - 8:00 PM
            'overnight': (time(0, 0), time(23, 59)),    # Full day
            'pre_market': (time(4, 0), time(9, 30)),    # 4:00 AM - 9:30 AM
            'after_hours': (time(16, 0), time(20, 0)),  # 4:00 PM - 8:00 PM
        }
        
        start_time, end_time = sessions.get(session_type, sessions['regular'])
        
        start = tz.localize(datetime.combine(date_local, start_time))
        end = tz.localize(datetime.combine(date_local, end_time))
        
        return start.astimezone(pytz.utc), end.astimezone(pytz.utc)
    
    @staticmethod
    def get_current_session() -> Tuple[datetime, datetime]:
        """Get current trading session boundaries."""
        now = datetime.now(pytz.timezone('US/Eastern'))
        
        # If before 9:30 AM, return previous day's session
        if now.time() < time(9, 30):
            date = now - timedelta(days=1)
        else:
            date = now
            
        return MarketSessions.get_session_boundaries(date)
```

## Implementation Plan

### Phase 1: Core Storage (Week 1-2)

1. **Create storage module structure**
   ```
   ib_stream/storage/
     __init__.py
     buffer.py         # JSON buffer implementation
     archive.py        # Parquet archive
     index.py          # SQLite metadata index
     query.py          # Query interface
     sessions.py       # Session helpers
     config.py         # Storage configuration
   ```

2. **Implement JSON buffer**
   - Append-only writes
   - Automatic rotation
   - Concurrent access handling

3. **Add storage hooks to streaming**
   - Intercept tick data in `StreamingApp`
   - Queue for async storage
   - Error handling and retries

### Phase 2: Archival System (Week 3-4)

1. **Implement Parquet archiver**
   - Buffer to Parquet conversion
   - Hourly partitioning
   - Compression optimization

2. **Create metadata index**
   - SQLite schema
   - Index maintenance
   - Statistics tracking

3. **Background tasks**
   - Periodic archival
   - Index updates
   - Old file cleanup

### Phase 3: Query Interface (Week 5-6)

1. **Build query API**
   - Time range queries
   - Multi-source aggregation
   - Caching layer

2. **Add REST endpoints**
   ```
   GET /v2/historical/{contract_id}
     ?tick_types=bid_ask,last
     &start_time=2025-01-10T09:30:00Z
     &end_time=2025-01-10T16:00:00Z
     &resolution=1m
   
   GET /v2/sessions/{contract_id}/current
   GET /v2/sessions/{contract_id}/previous
   ```

3. **Session helpers**
   - Market hours detection
   - Holiday calendar
   - Timezone handling

### Phase 4: Optimization (Week 7-8)

1. **Performance tuning**
   - Query optimization
   - Cache warming
   - Parallel loading

2. **Data management**
   - Retention policies
   - Compaction strategies
   - Storage monitoring

3. **Testing and documentation**
   - Load testing
   - API documentation
   - Usage examples

## Configuration

```python
# config.py additions
class StorageConfig:
    # Buffer settings
    buffer_duration_minutes: int = 120
    buffer_rotation_minutes: int = 15
    buffer_path: Path = Path("storage/buffer")
    
    # Archive settings
    archive_path: Path = Path("storage/archive")
    archive_compression: str = "snappy"
    archive_partition_hours: int = 1
    
    # Index settings
    index_path: Path = Path("storage/index.db")
    index_update_interval_seconds: int = 60
    
    # Retention settings
    buffer_retention_hours: int = 24
    archive_retention_days: int = 365
    
    # Cache settings
    query_cache_size: int = 1000
    query_cache_ttl_seconds: int = 300
    
    # Performance settings
    max_concurrent_writes: int = 10
    batch_size: int = 1000
```

## Usage Examples

### Example 1: Query Current Session
```python
from ib_stream.storage import StorageQuery, MarketSessions

# Initialize query interface
query = StorageQuery()

# Get current session boundaries
start, end = MarketSessions.get_current_session()

# Query all bid/ask data for current session
df = await query.query_range(
    contract_id=265598,  # AAPL
    tick_types=['bid_ask'],
    start_time=start,
    end_time=None  # Up to present
)

# Calculate session VWAP
vwap = (df['price'] * df['size']).sum() / df['size'].sum()
```

### Example 2: Historical Analysis
```python
# Query last week of data with 1-minute bars
end = datetime.now()
start = end - timedelta(days=7)

df = await query.query_range(
    contract_id=265598,
    tick_types=['last', 'bid_ask'],
    start_time=start,
    end_time=end,
    resolution='1m'  # Downsample to 1-minute bars
)

# Analyze price distribution
stats = df.groupby(df['timestamp'].dt.date).agg({
    'price': ['mean', 'std', 'min', 'max'],
    'size': 'sum'
})
```

### Example 3: Multi-Contract Query
```python
# Query multiple contracts for correlation analysis
contracts = [265598, 264598]  # AAPL, MSFT

dfs = []
for contract_id in contracts:
    df = await query.query_range(
        contract_id=contract_id,
        tick_types=['mid_point'],
        start_time=start,
        end_time=end,
        resolution='5m'
    )
    df['contract_id'] = contract_id
    dfs.append(df)

combined = pd.concat(dfs)
correlation = combined.pivot(
    index='timestamp', 
    columns='contract_id', 
    values='price'
).corr()
```

## Performance Considerations

### Write Performance
- Target: 10,000 ticks/second per contract
- Use async I/O for non-blocking writes
- Batch writes to reduce syscalls
- Separate write queues per contract

### Query Performance
- Recent data (buffer): <10ms latency
- Historical data (archive): <100ms for day queries
- Use columnar storage for efficient scans
- Implement query result caching

### Storage Efficiency
- Raw JSON: ~1KB per tick
- Compressed Parquet: ~100-200 bytes per tick
- 80-90% storage reduction
- Daily storage: ~1GB for active contract

### Scalability
- Horizontal partitioning by contract
- Time-based partitioning for archives
- Distributed storage support (future)
- Cloud storage backends (S3, GCS)

## Migration Strategy

### Phase 1: Side-by-side Operation
1. Deploy storage system alongside streaming
2. Start capturing data without affecting existing clients
3. Build up historical data corpus
4. Validate data integrity

### Phase 2: Integration
1. Add historical query endpoints
2. Update IB-Studies to use historical data
3. Implement cache warming
4. Monitor performance

### Phase 3: Full Migration
1. Make storage mandatory
2. Implement data lifecycle policies
3. Add monitoring and alerting
4. Document best practices

## Future Enhancements

### Advanced Features
1. **Real-time aggregations** - Running VWAP, volume profiles
2. **Data replay** - Simulate historical streams
3. **Multi-resolution storage** - Store 1s, 1m, 5m bars
4. **Distributed storage** - Cluster support for scale
5. **Cloud backends** - S3, GCS, Azure Blob

### Analytics Integration
1. **Apache Arrow** - Zero-copy data sharing
2. **DuckDB** - Embedded analytics
3. **Kafka Connect** - Stream to external systems
4. **Prometheus metrics** - Storage monitoring

### Machine Learning Support
1. **Feature engineering** - Pre-computed indicators
2. **Training data export** - ML-ready formats
3. **Model backtesting** - Historical evaluation
4. **Online learning** - Incremental updates

## Conclusion

This storage and caching system will transform IB-Stream from a real-time only system to a comprehensive market data platform. By combining efficient storage formats with flexible querying capabilities, IB-Studies will be able to perform sophisticated analysis over any time period while maintaining low latency for real-time operations.

The modular design allows for incremental implementation and future enhancements without disrupting existing functionality. The recommended Parquet + JSON buffer approach provides the best balance of performance, storage efficiency, and implementation complexity.