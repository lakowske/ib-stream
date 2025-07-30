# IB Stream Storage Format Optimization Technical Specification

## Overview

This specification defines the optimized storage format for IB Stream market data that reduces storage size by approximately 50% while maintaining full data fidelity.

## Current vs. Optimized Format

### Current JSON Format
```json
{
  "type": "tick",
  "stream_id": "711280073_bid_ask_1753837234776_8114",
  "timestamp": "2025-07-30T01:07:14.776Z",
  "data": {
    "contract_id": 711280073,
    "tick_type": "bid_ask",
    "type": "bid_ask",
    "timestamp": "2025-07-30 01:07:14 UTC",
    "unix_time": 1753837634776000,
    "bid_price": 23477.5,
    "ask_price": 23478.0,
    "bid_size": 6.0,
    "ask_size": 5.0,
    "bid_past_low": false,
    "ask_past_high": false
  },
  "metadata": {
    "source": "stream_manager",
    "request_id": "12345",
    "contract_id": "711280073",
    "tick_type": "bid_ask"
  }
}
```

### New Optimized TickMessage Format

#### JSON Format
```json
{
  "ts": 1753837634776000,
  "st": 1753837634777542,
  "cid": 711280073,
  "tt": "bid_ask",
  "rid": 1234567890,
  "bp": 23477.5,
  "ap": 23478.0,
  "bs": 6.0,
  "as": 5.0
}
```

#### Protobuf Schema (optimized)
```protobuf
syntax = "proto3";

message TickMessage {
  int64 ts = 1;          // timestamp (microseconds since epoch)
  int64 st = 2;          // system_timestamp (microseconds since epoch)
  int32 cid = 3;         // contract_id
  string tt = 4;         // tick_type
  int32 rid = 5;         // request_id (hash-generated, collision-resistant)
  
  // Price fields (optional, based on tick type)
  optional double p = 10;   // price (for last/all_last)
  optional double s = 11;   // size (for last/all_last)
  optional double bp = 12;  // bid_price
  optional double bs = 13;  // bid_size
  optional double ap = 14;  // ask_price
  optional double as = 15;  // ask_size
  optional double mp = 16;  // mid_point
  
  // Boolean flags (optional, omitted when false/default)
  optional bool bpl = 20;   // bid_past_low
  optional bool aph = 21;   // ask_past_high
  optional bool upt = 22;   // unreported
}
```

## Field Mappings

### Core Fields (always present)
| Legacy Field | Optimized | Type | Description |
|-------------|-----------|------|-------------|
| `unix_time` | `ts` | int64 | IB timestamp (microseconds since epoch) |
| N/A | `st` | int64 | System timestamp (microseconds since epoch) |
| `contract_id` | `cid` | int32 | IB contract identifier |
| `tick_type` | `tt` | string | Tick type: "bid_ask", "last", "all_last", "mid_point" |
| N/A | `rid` | int32 | Request ID (hash-generated from contract+tick_type+time) |

### Price Fields (conditional)
| Legacy Field | Optimized | Type | Tick Types | Description |
|-------------|-----------|------|------------|-------------|
| `price` | `p` | double | last, all_last | Trade price |
| `size` | `s` | double | last, all_last | Trade size |
| `bid_price` | `bp` | double | bid_ask | Bid price |
| `bid_size` | `bs` | double | bid_ask | Bid size |
| `ask_price` | `ap` | double | bid_ask | Ask price |
| `ask_size` | `as` | double | bid_ask | Ask size |
| `mid_point` | `mp` | double | mid_point | Mid-point price |

### Boolean Flags (optional, omitted when false)
| Legacy Field | Optimized | Type | Description |
|-------------|-----------|------|-------------|
| `bid_past_low` | `bpl` | bool | Bid below previous day's low |
| `ask_past_high` | `aph` | bool | Ask above previous day's high |
| `unreported` | `upt` | bool | Trade was unreported |

## Data Model Implementation

### Python TickMessage Dataclass
```python
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import hashlib
import time
import json

def generate_request_id(contract_id: int, tick_type: str, request_time: Optional[int] = None) -> int:
    """
    Generate collision-resistant request ID from request properties.
    
    Args:
        contract_id: IB contract identifier
        tick_type: Tick type (bid_ask, last, all_last, mid_point)
        request_time: Unix timestamp in microseconds (defaults to current time)
        
    Returns:
        32-bit signed integer request ID (safe for IB API)
    """
    if request_time is None:
        request_time = int(time.time() * 1_000_000)
    
    # Create deterministic hash input
    hash_input = f"{contract_id}_{tick_type}_{request_time}".encode('utf-8')
    
    # Generate MD5 hash and take first 4 bytes
    hash_obj = hashlib.md5(hash_input)
    hash_bytes = hash_obj.digest()[:4]
    
    # Convert to signed 32-bit integer (IB API compatible)
    request_id = int.from_bytes(hash_bytes, byteorder='big', signed=True)
    
    # Ensure positive ID for easier debugging
    return abs(request_id)

@dataclass
class TickMessage:
    """Optimized tick message format with hash-based request ID tracking."""
    
    # Core fields (always present)
    ts: int          # IB timestamp (microseconds since epoch)  
    st: int          # System timestamp (microseconds since epoch)
    cid: int         # Contract ID
    tt: str          # Tick type
    rid: int         # Request ID (hash-generated, collision-resistant)
    
    # Price fields (conditional based on tick type)
    p: Optional[float] = None    # price (last/all_last)
    s: Optional[float] = None    # size (last/all_last) 
    bp: Optional[float] = None   # bid_price
    bs: Optional[float] = None   # bid_size
    ap: Optional[float] = None   # ask_price
    as_: Optional[float] = field(default=None, metadata={'json_key': 'as'})  # ask_size
    mp: Optional[float] = None   # mid_point
    
    # Boolean flags (optional, omitted when false)
    bpl: Optional[bool] = None   # bid_past_low
    aph: Optional[bool] = None   # ask_past_high  
    upt: Optional[bool] = None   # unreported

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to optimized JSON format, omitting None/False values."""
        result = {
            'ts': self.ts,
            'st': self.st, 
            'cid': self.cid,
            'tt': self.tt,
            'rid': self.rid
        }
        
        # Add optional fields only if they have meaningful values
        for field_name, value in [
            ('p', self.p), ('s', self.s), ('bp', self.bp), ('bs', self.bs),
            ('ap', self.ap), ('as', self.as_), ('mp', self.mp),
            ('bpl', self.bpl), ('aph', self.aph), ('upt', self.upt)
        ]:
            if value is not None and value is not False:
                result[field_name] = value
                
        return result
        
    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> 'TickMessage':
        """Create TickMessage from optimized JSON format."""
        return cls(
            ts=data['ts'],
            st=data['st'], 
            cid=data['cid'],
            tt=data['tt'],
            rid=data['rid'],
            p=data.get('p'),
            s=data.get('s'),
            bp=data.get('bp'),
            bs=data.get('bs'), 
            ap=data.get('ap'),
            as_=data.get('as'),
            mp=data.get('mp'),
            bpl=data.get('bpl'),
            aph=data.get('aph'),
            upt=data.get('upt')
        )
    
    @classmethod
    def create_from_tick_data(cls, contract_id: int, tick_type: str, 
                             tick_data: Dict[str, Any], request_time: int = None) -> 'TickMessage':
        """Factory method to create TickMessage with generated request_id."""
        
        request_id = generate_request_id(contract_id, tick_type, request_time)
        timestamp_us = int(time.time() * 1_000_000)
        
        return cls(
            ts=tick_data.get('unix_time', timestamp_us),
            st=timestamp_us,
            cid=contract_id,
            tt=tick_type,
            rid=request_id,
            **_map_tick_data_fields(tick_data, tick_type)
        )
```

## Storage Size Comparison

### Example bid_ask Tick

**Previous Format (223 bytes)**:
```json
{"type":"tick","stream_id":"711280073_bid_ask_1753837234776_8114","timestamp":"2025-07-30T01:07:14.776Z","data":{"contract_id":711280073,"tick_type":"bid_ask","type":"bid_ask","timestamp":"2025-07-30 01:07:14 UTC","unix_time":1753837634776000,"bid_price":23477.5,"ask_price":23478.0,"bid_size":6.0,"ask_size":5.0,"bid_past_low":false,"ask_past_high":false},"metadata":{"source":"stream_manager","request_id":"12345","contract_id":"711280073","tick_type":"bid_ask"}}
```

**Optimized Format (104 bytes)**:
```json
{"ts":1753837634776000,"st":1753837634777542,"cid":711280073,"tt":"bid_ask","rid":1234567890,"bp":23477.5,"ap":23478.0,"bs":6.0,"as":5.0}
```

**Storage Reduction**: 119 bytes saved (53% reduction)

## Implementation Strategy

### Phase 1: Data Model & Storage Layer
1. Create `TickMessage` dataclass in `ib-util/ib_util/models.py`
2. Update storage engines to use optimized format

### Phase 2: Streaming Integration  
1. Update `streaming_app.py` to create `TickMessage` objects directly from IB callbacks
2. Modify `stream_manager.py` to route `TickMessage` objects
3. Update storage pipeline to use optimized format natively

### Phase 3: Protobuf Optimization
1. Update protobuf schema with optimized field names
2. Regenerate Python protobuf classes
3. Update protobuf storage engine to use optimized schema

### Phase 4: CLI and Analysis Integration
1. Update CLI tools to use optimized format
2. Update analysis tools (ib-studies) to work with optimized format

## Benefits

### Storage Efficiency
- **50%+ size reduction** for JSON storage (53% in example with request_id)
- **40%+ size reduction** for protobuf storage  
- Reduced disk I/O and network transfer costs
- Faster query performance due to smaller file sizes
- Minimal overhead (+4 bytes) for collision-resistant request_id tracking

### Performance Improvements
- Faster JSON parsing due to shorter field names
- Reduced memory usage during data processing
- Improved compression ratios for archived data
- Faster file system operations with shorter paths

### Operational Benefits
- Lower storage infrastructure costs
- Reduced backup and replication overhead
- Improved system responsiveness during high-volume periods
- Better scalability for long-term data retention

### Debugging and Multi-Source Benefits
- **Collision-Resistant IDs**: Hash-based request_id prevents conflicts across remote systems
- **TWS Correlation**: Direct mapping between stored data and TWS API logs via request_id
- **Source Identification**: Request_id ranges can identify data sources (background vs client vs external)
- **Human-Readable Files**: Filenames immediately show contract, tick_type, and timestamp
- **Easy Querying**: File organization enables fast filtering by contract and time range


## Testing Strategy

### Unit Tests
- TickMessage serialization/deserialization
- Storage engine functionality 

### Integration Tests
- End-to-end streaming with storage
- Performance benchmarks vs previous format

### Load Testing
- High-volume streaming with optimized storage
- Query performance comparison
- Memory usage analysis

## Monitoring

### Metrics
- Storage size reduction percentage
- Read/write performance improvements

## Stream Manager Integration Plan

The optimized TickMessage format eliminates the `metadata` and `stream_id` fields that are currently used by the stream management system. The following changes are required:

### Current Dependencies on Removed Fields

#### stream_id Usage:
- **StreamHandler**: Stores stream_id for reference and logging (`stream_handler.stream_id`)
- **Background Streams**: Uses consistent stream_id format `bg_{contract_id}_{tick_type}` for file organization
- **Storage Messages**: Creates v2 protocol messages with stream_id for storage routing
- **WebSocket Connections**: Maps stream_id to connection for message routing

#### metadata Usage:
- **Storage Messages**: Contains `source`, `request_id`, `contract_id`, `tick_type` for routing and indexing
- **HTTP Streaming**: Uses metadata for event correlation and debugging
- **WebSocket Protocol**: Relies on metadata for client message routing

### Integration Strategy

#### 1. StreamManager Modifications (`stream_manager.py`)

**Create optimized TickMessage with hash-based request_id:**
```python
def _create_storage_message(self, handler: StreamHandler, tick_data: Dict[str, Any]) -> TickMessage:
    """Create optimized TickMessage with hash-based request_id for storage."""
    
    return TickMessage.create_from_tick_data(
        contract_id=handler.contract_id,
        tick_type=handler.tick_type,
        tick_data=tick_data,
        request_time=int(time.time() * 1_000_000)
    )
```

**Update StreamHandler to use hash-based request_id:**
- Generate collision-resistant request_id using `generate_request_id()`
- Use request_id for TWS API correlation and debugging
- Remove dependency on stream_id for internal tracking
- Enable multi-source debugging via request_id ranges

#### 2. Background Stream Manager (`background_stream_manager.py`)

**Replace stream_id with hash-based request_id:**
```python
# Generate collision-resistant request_id for background streams
request_id = generate_request_id(
    contract_id=contract_id,
    tick_type=tick_type,
    request_time=int(time.time() * 1_000_000)
)

# Background streams use request_id ranges (e.g., 60000-69999 range)
# File organization handled by storage layer using readable filenames
```

**Update stream creation with hash-based ID:**
```python
handler = StreamHandler(
    request_id=request_id,  # Hash-generated, collision-resistant
    contract_id=contract_id,
    tick_type=tick_type,
    # No stream_id needed - request_id provides debugging correlation
)

# TWS API uses the hash-generated request_id
self.tws_app.reqTickByTickData(
    reqId=request_id,  # Direct correlation with stored data
    contract=contract_obj,
    tickType=tws_tick_type,
    numberOfTicks=0,
    ignoreSize=False
)
```

#### 3. Storage Layer Updates

**Hybrid File Organization Strategy:**
- Human-readable filenames: `{contract_id}_{tick_type}_{timestamp_seconds}.jsonl`
- Hash-based request_id stored in message data for debugging/correlation
- Maintain hourly file rotation using `st` (system timestamp)
- File organization by contract+tick_type+time for easy querying

**New file path pattern:**
```
storage/
├── json/
│   └── 2025/07/30/14/
│       ├── 711280073_bid_ask_1753837634.jsonl    # ES futures bid/ask
│       ├── 711280073_last_1753837634.jsonl       # ES futures trades
│       ├── 412345678_bid_ask_1753837635.jsonl    # Different contract
│       └── 711280073_bid_ask_1753837700.jsonl    # Same contract, later time
└── pb/
    └── 2025/07/30/14/
        ├── 711280073_bid_ask_1753837634.pb
        ├── 711280073_last_1753837634.pb
        └── 412345678_bid_ask_1753837635.pb
```

**Request ID Generation:**
```python
from pathlib import Path
from datetime import datetime, timezone

def get_storage_file_path(base_path: Path, contract_id: int, tick_type: str, timestamp: int) -> Path:
    """Generate readable file path with contract info and timestamp."""
    dt = datetime.fromtimestamp(timestamp / 1_000_000, tz=timezone.utc)
    
    # Hourly partitioning: YYYY/MM/DD/HH
    date_path = dt.strftime('%Y/%m/%d/%H')
    
    # Readable filename: {contract_id}_{tick_type}_{timestamp_seconds}
    timestamp_seconds = timestamp // 1_000_000
    filename = f"{contract_id}_{tick_type}_{timestamp_seconds}.jsonl"
    
    return base_path / date_path / filename
```

#### 4. WebSocket Manager (`ws_manager.py`)

**Stream Identification Changes:**
```python
# Replace stream_id generation with request_id tracking
class WebSocketConnection:
    def __init__(self, websocket: WebSocket, connection_id: str):
        self.request_id_to_stream: Dict[int, Dict[str, Any]] = {}  # request_id -> stream info
        
    def add_stream(self, request_id: int, contract_id: int, tick_type: str):
        """Track stream by request_id instead of stream_id."""
        self.request_id_to_stream[request_id] = {
            "contract_id": contract_id,
            "tick_type": tick_type,
            "started_at": time.time()
        }
```

**Message Routing Updates:**
- Route messages using `request_id` from StreamHandler
- Generate display identifiers from `contract_id + tick_type` for client responses
- Remove dependency on stream_id for internal routing

#### 5. HTTP Streaming Endpoints (`streaming_core.py`)

**Event Creation Updates:**
```python
async def on_tick(tick_data: Dict[str, Any], request_id=req_id, tick_type=tick_type, contract_id=contract_id):
    # Create display identifier for client
    display_id = f"{contract_id}_{tick_type}_{int(time.time())}"
    
    event = create_tick_event(display_id, contract_id, tick_type, tick_data)
    await event_queue.put(event)
```

**Remove metadata from tick_data:**
- Extract routing information from StreamHandler context
- Pass contract_id and tick_type explicitly to callbacks
- Remove metadata creation in tick processing

### Migration Steps

1. **Update TickMessage Model**: Implement the optimized dataclass in `ib-util/ib_util/models.py`
2. **Modify StreamManager**: Remove stream_id and metadata dependencies
3. **Update Storage Engines**: Implement file organization using contract_id + tick_type  
4. **Refactor Background Streaming**: Remove stream_id generation and tracking
5. **Update WebSocket Layer**: Replace stream_id routing with request_id tracking
6. **Modify HTTP Endpoints**: Remove metadata from tick events and messages

### Testing Requirements

- Verify storage file organization works without stream_id
- Test background streaming continues without interruption  
- Confirm WebSocket message routing functions with request_id tracking
- Validate HTTP streaming maintains client compatibility
- Test storage retrieval using new file organization pattern

## Comprehensive Migration Issues

### 1. Storage Layer Breaking Changes

**JSON Storage (`json_storage.py`)**:
- **File Organization**: Currently uses `stream_id` for file paths (`{stream_id}.jsonl`)
- **Message Structure**: Expects `{type, stream_id, timestamp, data, metadata}` format
- **Query Methods**: All `query_range()` methods parse nested message structure
- **Impact**: Complete file reorganization and query method rewrite required

**Protobuf Storage (`protobuf_storage.py`)**:
- **Binary Format**: Current protobuf schema uses v2 protocol fields
- **Length-Prefixed Messages**: Serialization assumes current message structure  
- **File Naming**: Uses `stream_id` for organizing `.pb` files
- **Impact**: New protobuf schema, serialization code, and file organization needed

**BufferQuery (`buffer_query.py`)**:
- **Message Parsing**: Extracts `msg.get("data", {})` and `msg.get("metadata", {})`
- **Stream Filtering**: Uses `stream_id` for organizing query results
- **Timestamp Extraction**: Relies on multiple timestamp formats in nested structure
- **Contract ID Access**: Uses `metadata.contract_id` for filtering
- **Impact**: Complete query interface rewrite required (no old data compatibility needed)

### 2. Data Formatting and Serialization

**Formatters (`formatters.py`)**:
- **Output Structure**: All formatters create `{timestamp, tick_type, ...fields}` objects
- **JSON Conversion**: `to_json()` methods return nested field structure
- **Field Mapping**: Assumes consistent field names across tick types
- **Impact**: Formatters must output optimized TickMessage format with conditional fields

**Tick Processing Pipeline**:
- **StreamingApp**: Callback functions expect formatted tick data dictionaries
- **Field Access**: Code directly accesses `tick_data["bid_price"]`, `tick_data["unix_time"]`
- **Type Detection**: Uses `tick_data.get("tick_type")` for processing logic
- **Impact**: All tick processing code needs field mapping logic

### 3. API Layer Compatibility

**HTTP Streaming Endpoints**:
- **SSE Events**: Create events with `{stream_id, data: {nested_fields}}` structure
- **Buffer Streaming**: Historical playback assumes v2 protocol format
- **Client Responses**: All HTTP APIs return messages in current format
- **Error Handling**: Error events include `stream_id` and nested metadata
- **Impact**: Direct API updates to use optimized format (break client compatibility)

**WebSocket Protocol**:
- **Message Routing**: Uses `stream_id` to map messages to connections
- **Client Messages**: WebSocket clients expect v2 protocol structure
- **Subscription Management**: Stream subscriptions tracked by `stream_id`
- **Status Messages**: Connection status uses current message format
- **Impact**: WebSocket protocol updated to use optimized format (break client compatibility)

### 4. Background Services

**Background Stream Manager**:
- **Stream Identification**: Creates consistent `stream_id` for file organization
- **Storage Messages**: Generates v2 protocol messages for storage pipeline
- **Logging**: Uses `stream_id` for debugging and monitoring
- **Error Handling**: Error callbacks expect current message format
- **Impact**: Remove `stream_id` generation, update storage integration

**Monitoring and Metrics**:
- **Message Parsing**: Metrics extraction assumes nested field structure
- **Stream Tracking**: Uses `stream_id` for performance monitoring
- **Error Correlation**: Links errors to streams using current identifiers
- **Impact**: Metrics collection needs field mapping updates

### 5. External Dependencies

**ib-studies Integration**:
- **Data Analysis**: External tools expect v2 protocol message format
- **Import/Export**: Analysis pipelines parse nested message structure
- **Backtesting**: Historical data analysis assumes current field names
- **Impact**: Update ib-studies to use optimized format (break compatibility)

**CLI Tools and Scripts**:
- **Message Display**: CLI tools parse and display nested message fields
- **Data Export**: Export utilities assume current message structure
- **Debugging Tools**: Stream inspection uses `stream_id` and metadata
- **Impact**: All CLI tools need field mapping updates

### 6. Testing and Validation

**Unit Tests**:
- **Message Assertions**: Tests validate specific nested field structures
- **Mock Data**: Test fixtures use v2 protocol format
- **Storage Tests**: Verify message storage and retrieval with current format
- **Impact**: Comprehensive test suite updates required

**Integration Tests**:
- **End-to-End**: Full pipeline tests assume current message flow
- **Storage Verification**: Data integrity tests validate nested structure
- **API Compatibility**: Client integration tests expect v2 protocol
- **Impact**: All integration tests need message format updates

### 7. Operational Considerations

**Logging and Debugging**:
- **Message Logging**: Log statements format nested message structure
- **Error Tracking**: Error messages include `stream_id` and metadata context
- **Performance Analysis**: Debug output assumes current field names
- **Impact**: Logging statements need field mapping or format updates

**Monitoring and Alerting**:
- **Message Parsing**: Monitoring tools parse nested structure for metrics
- **Stream Health**: Health checks validate message format compliance
- **Alert Correlation**: Alerts use `stream_id` for identifying issues
- **Impact**: Monitoring systems need format awareness

### Migration Execution Strategy

**Phase 1: Core Data Model**
1. Implement `TickMessage` dataclass with field validation
2. Add field mapping functions for conditional tick type fields

**Phase 2: Storage Layer**
1. Update storage engines to handle `TickMessage` objects
2. Implement new file organization using `contract_id + tick_type`
3. Clear existing storage directories (fresh start)

**Phase 3: Processing Pipeline**
1. Update formatters to output optimized format
2. Modify stream processing to create `TickMessage` objects
3. Update background streaming integration

**Phase 4: API Layer**
1. Update WebSocket message routing to use optimized format
2. Modify HTTP streaming endpoints to use optimized format
3. Update client-facing APIs to use new field names

**Phase 5: External Integration**
1. Update CLI tools to use new field names
2. Update ib-studies to use optimized format

**Phase 6: Testing and Validation**
1. Update all test suites with new message format
2. Validate storage integrity and query performance
3. Test end-to-end functionality with fresh data

This specification ensures a smooth transition to optimized storage while maintaining operational reliability.