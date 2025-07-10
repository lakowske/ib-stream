# Protobuf Storage and Stream Indexing

## Overview

This document outlines a simple and efficient approach to storing IB-Stream v2 protocol messages using Protocol Buffers (protobuf) with hourly file partitioning and PostgreSQL metadata indexing. The goal is to provide an efficient alternative to JSON storage while maintaining simplicity and enabling fast data retrieval for ib-studies analysis.

## Design Principles

1. **Simplicity First** - Minimize complexity while achieving performance goals
2. **Efficient Storage** - 60-70% compression compared to JSON
3. **Fast Queries** - Sub-second retrieval for common time ranges
4. **Manageable Files** - Hourly partitioning keeps files under 100MB
5. **SQL Familiarity** - PostgreSQL for metadata enables standard SQL queries
6. **Direct Mapping** - Seamless conversion from existing v2 JSON protocol

## Protobuf Schema Design

### Core Message Schema

```protobuf
// tick_stream.proto
syntax = "proto3";

package ib_stream;

import "google/protobuf/timestamp.proto";

// Base message wrapper for all stream messages
message StreamMessage {
  string type = 1;                              // "tick", "error", "complete", "info"
  string stream_id = 2;                         // Unique stream identifier
  google.protobuf.Timestamp timestamp = 3;     // UTC timestamp
  oneof message_data {
    TickData tick_data = 4;
    ErrorData error_data = 5;
    CompleteData complete_data = 6;
    InfoData info_data = 7;
  }
  map<string, string> metadata = 8;            // Optional metadata
}

// Tick data message
message TickData {
  uint32 contract_id = 1;
  string tick_type = 2;                        // "last", "bid_ask", "mid_point", "all_last"
  
  // Price fields (conditional based on tick_type)
  optional double price = 3;                   // For last/all_last
  optional double size = 4;                    // For last/all_last
  optional double bid_price = 5;               // For bid_ask
  optional double bid_size = 6;                // For bid_ask
  optional double ask_price = 7;               // For bid_ask
  optional double ask_size = 8;                // For bid_ask
  optional double mid_price = 9;               // For mid_point
  
  // Additional fields
  optional string exchange = 10;
  repeated string conditions = 11;
  optional uint64 sequence = 12;
  
  // Tick attributes (from IB API)
  optional bool past_limit = 13;               // For last/all_last
  optional bool unreported = 14;               // For last/all_last
  optional bool bid_past_low = 15;             // For bid_ask
  optional bool ask_past_high = 16;            // For bid_ask
}

// Error data message
message ErrorData {
  string code = 1;                             // Error code
  string message = 2;                          // Human-readable message
  bool recoverable = 3;                        // Whether client can retry
  map<string, string> details = 4;            // Additional error context
}

// Stream completion message
message CompleteData {
  string reason = 1;                           // "limit_reached", "timeout", etc.
  uint64 total_ticks = 2;                      // Total ticks in stream
  double duration_seconds = 3;                 // Stream duration
  optional uint64 final_sequence = 4;         // Last sequence number
}

// Stream info/metadata message
message InfoData {
  string status = 1;                           // "subscribed", "active", etc.
  optional ContractInfo contract_info = 2;
  optional StreamConfig stream_config = 3;
}

// Contract information
message ContractInfo {
  string symbol = 1;
  string exchange = 2;
  string currency = 3;
  string contract_type = 4;                    // "STK", "OPT", "FUT", etc.
}

// Stream configuration
message StreamConfig {
  string tick_type = 1;
  optional uint64 limit = 2;                  // Max ticks
  optional uint32 timeout_seconds = 3;        // Stream timeout
}

// File header for each protobuf file
message FileHeader {
  uint32 version = 1;                          // File format version
  google.protobuf.Timestamp start_time = 2;   // First tick timestamp
  google.protobuf.Timestamp end_time = 3;     // Last tick timestamp
  uint32 contract_id = 4;                     // Contract ID for this file
  string tick_type = 5;                       // Tick type for this file
  uint64 message_count = 6;                   // Number of messages in file
  string compression = 7;                      // "none", "gzip", "snappy"
}
```

### Message Framing Format

Each protobuf file contains:
1. **File Header** (FileHeader message)
2. **Message Stream** (length-prefixed StreamMessage instances)

```
File Structure:
┌──────────────────┐
│   File Header    │  ← FileHeader protobuf message
├──────────────────┤
│ Length (4 bytes) │  ← Message 1 length (big-endian)
│ StreamMessage 1  │  ← First tick message
├──────────────────┤
│ Length (4 bytes) │  ← Message 2 length
│ StreamMessage 2  │  ← Second tick message
├──────────────────┤
│       ...        │
└──────────────────┘
```

## File Organization Strategy

### Directory Structure

```
/storage/protobuf/
├── /265598/                    # Contract ID (AAPL)
│   ├── /bid_ask/
│   │   ├── /2025/01/10/
│   │   │   ├── 09_ticks.pb     # 09:00-10:00 UTC
│   │   │   ├── 10_ticks.pb     # 10:00-11:00 UTC
│   │   │   ├── 14_ticks.pb     # 14:00-15:00 UTC (NYSE open)
│   │   │   └── 21_ticks.pb     # 21:00-22:00 UTC (NYSE close)
│   │   └── /2025/01/11/
│   │       └── ...
│   ├── /last/
│   │   └── /2025/01/10/
│   │       ├── 14_ticks.pb
│   │       └── 15_ticks.pb
│   └── /mid_point/
│       └── ...
├── /711280073/                 # Another contract ID
│   └── ...
└── /metadata/
    ├── schema.proto            # Schema definition
    └── index.json              # Quick file lookup
```

### File Naming Convention

```
{hour}_ticks.pb
```

Where:
- `{hour}` = UTC hour (00-23) for the time window
- Files contain all ticks for that contract/tick_type/hour combination
- Empty hours (no ticks) have no corresponding file

### File Size Management

**Target Size:** 50-100MB per file
**Rotation Strategy:**
- Primary: Hourly boundaries (fixed)
- Fallback: If file exceeds 200MB, split at 30-minute boundary
- Compression: Optional gzip compression for older files

## PostgreSQL Schema Design

### Core Tables

```sql
-- Main table for tracking protobuf files
CREATE TABLE tick_files (
    id BIGSERIAL PRIMARY KEY,
    contract_id INTEGER NOT NULL,
    tick_type VARCHAR(20) NOT NULL,
    file_path VARCHAR(500) NOT NULL UNIQUE,
    
    -- Time range
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    hour_bucket TIMESTAMPTZ NOT NULL,  -- Truncated to hour boundary
    
    -- File metadata
    file_size_bytes BIGINT NOT NULL,
    message_count BIGINT NOT NULL,
    compression VARCHAR(20) DEFAULT 'none',
    
    -- Content statistics
    first_sequence BIGINT,
    last_sequence BIGINT,
    min_price DECIMAL(12,4),
    max_price DECIMAL(12,4),
    total_volume DECIMAL(15,2),
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX idx_tick_files_contract_time 
    ON tick_files (contract_id, tick_type, hour_bucket);

CREATE INDEX idx_tick_files_time_range 
    ON tick_files USING GIST (tstzrange(start_time, end_time));

CREATE INDEX idx_tick_files_contract_type 
    ON tick_files (contract_id, tick_type);

CREATE INDEX idx_tick_files_hour_bucket 
    ON tick_files (hour_bucket);

-- Daily aggregation table for faster range queries
CREATE TABLE daily_tick_stats (
    id BIGSERIAL PRIMARY KEY,
    contract_id INTEGER NOT NULL,
    tick_type VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    
    -- Aggregated statistics
    total_files INTEGER NOT NULL,
    total_messages BIGINT NOT NULL,
    total_size_bytes BIGINT NOT NULL,
    first_tick TIMESTAMPTZ,
    last_tick TIMESTAMPTZ,
    
    -- Price statistics (for last/all_last ticks)
    min_price DECIMAL(12,4),
    max_price DECIMAL(12,4),
    avg_price DECIMAL(12,4),
    total_volume DECIMAL(15,2),
    
    -- VWAP calculation
    vwap DECIMAL(12,4),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(contract_id, tick_type, date)
);

CREATE INDEX idx_daily_stats_contract_date 
    ON daily_tick_stats (contract_id, tick_type, date);

-- Contract metadata table
CREATE TABLE contracts (
    contract_id INTEGER PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(20),
    currency VARCHAR(10),
    contract_type VARCHAR(10),
    
    -- Activity tracking
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    active BOOLEAN DEFAULT true,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Query helper functions
CREATE OR REPLACE FUNCTION get_files_for_range(
    p_contract_id INTEGER,
    p_tick_type VARCHAR,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ
) RETURNS TABLE (
    file_path VARCHAR,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    message_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        tf.file_path,
        tf.start_time,
        tf.end_time,
        tf.message_count
    FROM tick_files tf
    WHERE tf.contract_id = p_contract_id
      AND tf.tick_type = p_tick_type
      AND tf.start_time <= p_end_time
      AND tf.end_time >= p_start_time
    ORDER BY tf.start_time;
END;
$$ LANGUAGE plpgsql;
```

## Storage Implementation

### ProtobufStorage Class

```python
import os
import gzip
import struct
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, BinaryIO

import psycopg2
from psycopg2.extras import execute_values
from google.protobuf.timestamp_pb2 import Timestamp

from . import tick_stream_pb2  # Generated protobuf classes

class ProtobufStorage:
    def __init__(self, storage_path: str, db_connection: str):
        self.storage_path = Path(storage_path)
        self.db_connection = db_connection
        self.current_files: Dict[str, BinaryIO] = {}  # stream_key -> file handle
        self.file_message_counts: Dict[str, int] = {}
        self.file_start_times: Dict[str, datetime] = {}
        
    def append_tick(self, message_data: Dict) -> None:
        """Convert JSON message to protobuf and append to appropriate file."""
        # Extract key information
        contract_id = message_data['data']['contract_id']
        tick_type = message_data['data']['tick_type']
        timestamp = datetime.fromisoformat(message_data['timestamp'].replace('Z', '+00:00'))
        
        # Create protobuf message
        pb_message = self._json_to_protobuf(message_data)
        
        # Get appropriate file for this hour
        stream_key = f"{contract_id}_{tick_type}"
        file_handle = self._get_file_for_timestamp(stream_key, contract_id, tick_type, timestamp)
        
        # Write length-prefixed message
        serialized = pb_message.SerializeToString()
        length_bytes = struct.pack('>I', len(serialized))
        file_handle.write(length_bytes)
        file_handle.write(serialized)
        file_handle.flush()
        
        # Update tracking
        self.file_message_counts[stream_key] = self.file_message_counts.get(stream_key, 0) + 1
        
    def _json_to_protobuf(self, json_data: Dict) -> tick_stream_pb2.StreamMessage:
        """Convert v2 protocol JSON to protobuf message."""
        message = tick_stream_pb2.StreamMessage()
        
        # Set common fields
        message.type = json_data['type']
        message.stream_id = json_data['stream_id']
        
        # Convert timestamp
        ts = datetime.fromisoformat(json_data['timestamp'].replace('Z', '+00:00'))
        message.timestamp.FromDatetime(ts)
        
        # Set type-specific data
        if json_data['type'] == 'tick':
            self._populate_tick_data(message.tick_data, json_data['data'])
        elif json_data['type'] == 'error':
            self._populate_error_data(message.error_data, json_data['data'])
        elif json_data['type'] == 'complete':
            self._populate_complete_data(message.complete_data, json_data['data'])
        elif json_data['type'] == 'info':
            self._populate_info_data(message.info_data, json_data['data'])
            
        # Add metadata if present
        if 'metadata' in json_data:
            for key, value in json_data['metadata'].items():
                message.metadata[key] = str(value)
                
        return message
    
    def _populate_tick_data(self, tick_data: tick_stream_pb2.TickData, data: Dict) -> None:
        """Populate tick data from JSON."""
        tick_data.contract_id = data['contract_id']
        tick_data.tick_type = data['tick_type']
        
        # Set fields based on tick type
        if 'price' in data:
            tick_data.price = data['price']
        if 'size' in data:
            tick_data.size = data['size']
        if 'bid_price' in data:
            tick_data.bid_price = data['bid_price']
        if 'bid_size' in data:
            tick_data.bid_size = data['bid_size']
        if 'ask_price' in data:
            tick_data.ask_price = data['ask_price']
        if 'ask_size' in data:
            tick_data.ask_size = data['ask_size']
        if 'mid_price' in data:
            tick_data.mid_price = data['mid_price']
            
        # Optional fields
        if 'exchange' in data:
            tick_data.exchange = data['exchange']
        if 'conditions' in data:
            tick_data.conditions.extend(data['conditions'])
        if 'sequence' in data:
            tick_data.sequence = data['sequence']
            
        # Tick attributes
        if 'past_limit' in data:
            tick_data.past_limit = data['past_limit']
        if 'unreported' in data:
            tick_data.unreported = data['unreported']
        if 'bid_past_low' in data:
            tick_data.bid_past_low = data['bid_past_low']
        if 'ask_past_high' in data:
            tick_data.ask_past_high = data['ask_past_high']
    
    def _get_file_for_timestamp(
        self, 
        stream_key: str, 
        contract_id: int, 
        tick_type: str, 
        timestamp: datetime
    ) -> BinaryIO:
        """Get or create file handle for the given timestamp."""
        hour_bucket = timestamp.replace(minute=0, second=0, microsecond=0)
        file_key = f"{stream_key}_{hour_bucket.isoformat()}"
        
        if file_key not in self.current_files:
            # Create file path
            file_path = self._get_file_path(contract_id, tick_type, hour_bucket)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Open file
            self.current_files[file_key] = open(file_path, 'ab')
            
            # Write header if new file
            if file_path.stat().st_size == 0:
                self._write_file_header(self.current_files[file_key], contract_id, tick_type, hour_bucket)
            
            # Track file metadata
            self.file_start_times[file_key] = timestamp
            
        return self.current_files[file_key]
    
    def _get_file_path(self, contract_id: int, tick_type: str, hour_bucket: datetime) -> Path:
        """Generate file path for given parameters."""
        date_str = hour_bucket.strftime('%Y/%m/%d')
        hour_str = hour_bucket.strftime('%H')
        
        return self.storage_path / str(contract_id) / tick_type / date_str / f"{hour_str}_ticks.pb"
    
    def _write_file_header(self, file_handle: BinaryIO, contract_id: int, tick_type: str, hour_bucket: datetime) -> None:
        """Write file header to new protobuf file."""
        header = tick_stream_pb2.FileHeader()
        header.version = 1
        header.contract_id = contract_id
        header.tick_type = tick_type
        header.compression = "none"
        
        # Set start time (will update end time when closing)
        header.start_time.FromDatetime(hour_bucket)
        header.end_time.FromDatetime(hour_bucket)
        
        # Write header with length prefix
        serialized = header.SerializeToString()
        length_bytes = struct.pack('>I', len(serialized))
        file_handle.write(length_bytes)
        file_handle.write(serialized)
        
    def close_hour_files(self, before_time: datetime) -> None:
        """Close files for completed hours and update database."""
        to_close = []
        
        for file_key, file_handle in self.current_files.items():
            start_time = self.file_start_times.get(file_key)
            if start_time and start_time < before_time:
                to_close.append(file_key)
        
        for file_key in to_close:
            self._close_and_index_file(file_key)
    
    def _close_and_index_file(self, file_key: str) -> None:
        """Close file and add metadata to database."""
        file_handle = self.current_files[file_key]
        file_path = file_handle.name
        message_count = self.file_message_counts.get(file_key, 0)
        
        # Close file
        file_handle.close()
        
        # Get file info
        file_size = os.path.getsize(file_path)
        start_time = self.file_start_times[file_key]
        end_time = datetime.now(timezone.utc)
        
        # Extract metadata from file key
        parts = file_key.split('_')
        contract_id = int(parts[0])
        tick_type = parts[1]
        
        # Insert into database
        with psycopg2.connect(self.db_connection) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tick_files (
                        contract_id, tick_type, file_path, start_time, end_time,
                        hour_bucket, file_size_bytes, message_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    contract_id, tick_type, file_path, start_time, end_time,
                    start_time.replace(minute=0, second=0, microsecond=0),
                    file_size, message_count
                ))
        
        # Clean up tracking
        del self.current_files[file_key]
        del self.file_message_counts[file_key]
        del self.file_start_times[file_key]
```

### ProtobufQuery Class

```python
class ProtobufQuery:
    def __init__(self, storage_path: str, db_connection: str):
        self.storage_path = Path(storage_path)
        self.db_connection = db_connection
    
    def query_range(
        self, 
        contract_id: int, 
        tick_type: str, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[Dict]:
        """Query ticks for a specific time range."""
        
        # Get relevant files from database
        files = self._get_files_for_range(contract_id, tick_type, start_time, end_time)
        
        messages = []
        for file_info in files:
            file_messages = self._read_protobuf_file(
                file_info['file_path'], 
                start_time, 
                end_time
            )
            messages.extend(file_messages)
        
        # Sort by timestamp
        messages.sort(key=lambda x: x['timestamp'])
        
        return messages
    
    def _get_files_for_range(
        self, 
        contract_id: int, 
        tick_type: str, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[Dict]:
        """Get list of files that might contain data in the range."""
        
        with psycopg2.connect(self.db_connection) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT file_path, start_time, end_time, message_count
                    FROM get_files_for_range(%s, %s, %s, %s)
                """, (contract_id, tick_type, start_time, end_time))
                
                return [
                    {
                        'file_path': row[0],
                        'start_time': row[1],
                        'end_time': row[2],
                        'message_count': row[3]
                    }
                    for row in cur.fetchall()
                ]
    
    def _read_protobuf_file(
        self, 
        file_path: str, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[Dict]:
        """Read and filter messages from a protobuf file."""
        messages = []
        
        with open(file_path, 'rb') as f:
            # Skip header
            header_length = struct.unpack('>I', f.read(4))[0]
            f.read(header_length)
            
            # Read messages
            while True:
                try:
                    # Read length prefix
                    length_data = f.read(4)
                    if len(length_data) < 4:
                        break
                    
                    message_length = struct.unpack('>I', length_data)[0]
                    
                    # Read message
                    message_data = f.read(message_length)
                    if len(message_data) < message_length:
                        break
                    
                    # Parse protobuf
                    pb_message = tick_stream_pb2.StreamMessage()
                    pb_message.ParseFromString(message_data)
                    
                    # Convert to JSON and filter by time
                    json_message = self._protobuf_to_json(pb_message)
                    message_time = datetime.fromisoformat(json_message['timestamp'].replace('Z', '+00:00'))
                    
                    if start_time <= message_time <= end_time:
                        messages.append(json_message)
                        
                except struct.error:
                    break
        
        return messages
    
    def _protobuf_to_json(self, pb_message: tick_stream_pb2.StreamMessage) -> Dict:
        """Convert protobuf message back to v2 JSON format."""
        result = {
            'type': pb_message.type,
            'stream_id': pb_message.stream_id,
            'timestamp': pb_message.timestamp.ToDatetime().isoformat() + 'Z'
        }
        
        # Convert type-specific data
        if pb_message.HasField('tick_data'):
            result['data'] = self._tick_data_to_json(pb_message.tick_data)
        elif pb_message.HasField('error_data'):
            result['data'] = self._error_data_to_json(pb_message.error_data)
        elif pb_message.HasField('complete_data'):
            result['data'] = self._complete_data_to_json(pb_message.complete_data)
        elif pb_message.HasField('info_data'):
            result['data'] = self._info_data_to_json(pb_message.info_data)
        
        # Add metadata if present
        if pb_message.metadata:
            result['metadata'] = dict(pb_message.metadata)
        
        return result
    
    def _tick_data_to_json(self, tick_data: tick_stream_pb2.TickData) -> Dict:
        """Convert protobuf tick data to JSON format."""
        data = {
            'contract_id': tick_data.contract_id,
            'tick_type': tick_data.tick_type
        }
        
        # Add present fields
        if tick_data.HasField('price'):
            data['price'] = tick_data.price
        if tick_data.HasField('size'):
            data['size'] = tick_data.size
        if tick_data.HasField('bid_price'):
            data['bid_price'] = tick_data.bid_price
        if tick_data.HasField('bid_size'):
            data['bid_size'] = tick_data.bid_size
        if tick_data.HasField('ask_price'):
            data['ask_price'] = tick_data.ask_price
        if tick_data.HasField('ask_size'):
            data['ask_size'] = tick_data.ask_size
        if tick_data.HasField('mid_price'):
            data['mid_price'] = tick_data.mid_price
            
        # Optional fields
        if tick_data.exchange:
            data['exchange'] = tick_data.exchange
        if tick_data.conditions:
            data['conditions'] = list(tick_data.conditions)
        if tick_data.HasField('sequence'):
            data['sequence'] = tick_data.sequence
            
        # Tick attributes
        if tick_data.HasField('past_limit'):
            data['past_limit'] = tick_data.past_limit
        if tick_data.HasField('unreported'):
            data['unreported'] = tick_data.unreported
        if tick_data.HasField('bid_past_low'):
            data['bid_past_low'] = tick_data.bid_past_low
        if tick_data.HasField('ask_past_high'):
            data['ask_past_high'] = tick_data.ask_past_high
            
        return data
```

## Enhanced Historical Query Capabilities

### Overview

The protobuf storage system supports flexible historical query patterns to enable various use cases:

1. **Standard Range Queries** - Query between two specific timestamps
2. **To-Present Queries** - Query from a start time to the current moment
3. **Session-Based Queries** - Query based on market sessions (NY, London, etc.)
4. **Relative Time Queries** - Query using relative periods (last hour, last day)
5. **Hybrid Historical/Live Queries** - Combine historical buffer with live streaming

### Enhanced ProtobufQuery Class

```python
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, AsyncIterator, Tuple
import asyncio
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed

class EnhancedProtobufQuery(ProtobufQuery):
    def __init__(self, storage_path: str, db_connection: str, max_workers: int = 4):
        super().__init__(storage_path, db_connection)
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
    def query_to_present(
        self,
        contract_id: int,
        tick_type: str,
        start_time: datetime,
        include_incomplete_hour: bool = True
    ) -> List[Dict]:
        """Query from start time to current moment."""
        end_time = datetime.now(timezone.utc)
        
        # Query completed hours
        messages = self.query_range(contract_id, tick_type, start_time, end_time)
        
        # Include current incomplete hour if requested
        if include_incomplete_hour:
            current_hour = end_time.replace(minute=0, second=0, microsecond=0)
            incomplete_messages = self._query_incomplete_hour(
                contract_id, tick_type, current_hour, end_time
            )
            messages.extend(incomplete_messages)
            messages.sort(key=lambda x: x['timestamp'])
        
        return messages
    
    def query_session(
        self,
        contract_id: int,
        tick_type: str,
        session_date: datetime,
        session_type: str = 'regular',
        market: str = 'US'
    ) -> List[Dict]:
        """Query data for a specific market session."""
        start_time, end_time = self._get_session_boundaries(
            session_date, session_type, market
        )
        
        return self.query_range(contract_id, tick_type, start_time, end_time)
    
    def query_relative(
        self,
        contract_id: int,
        tick_type: str,
        period: str,
        end_time: Optional[datetime] = None
    ) -> List[Dict]:
        """Query using relative time period (e.g., 'last_hour', 'last_day')."""
        if end_time is None:
            end_time = datetime.now(timezone.utc)
            
        # Calculate start time based on period
        period_map = {
            'last_minute': timedelta(minutes=1),
            'last_5_minutes': timedelta(minutes=5),
            'last_15_minutes': timedelta(minutes=15),
            'last_30_minutes': timedelta(minutes=30),
            'last_hour': timedelta(hours=1),
            'last_2_hours': timedelta(hours=2),
            'last_4_hours': timedelta(hours=4),
            'last_day': timedelta(days=1),
            'last_week': timedelta(weeks=1),
            'last_month': timedelta(days=30),
        }
        
        if period not in period_map:
            raise ValueError(f"Invalid period: {period}")
            
        start_time = end_time - period_map[period]
        
        return self.query_range(contract_id, tick_type, start_time, end_time)
    
    async def query_with_live_stream(
        self,
        contract_id: int,
        tick_type: str,
        buffer_period: str = 'last_hour',
        stream_callback: Optional[callable] = None
    ) -> AsyncIterator[Dict]:
        """Query historical buffer and continue with live stream."""
        # Get historical buffer
        historical_messages = self.query_relative(contract_id, tick_type, buffer_period)
        
        # Yield historical messages
        for msg in historical_messages:
            yield msg
        
        # Connect to live stream
        if stream_callback:
            # Hand off to live streaming system
            await stream_callback(contract_id, tick_type)
    
    def query_range_parallel(
        self,
        contract_id: int,
        tick_type: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """Query large time ranges using parallel file reading."""
        # Get all files in range
        files = self._get_files_for_range(contract_id, tick_type, start_time, end_time)
        
        if len(files) <= 2:
            # Use sequential for small queries
            return self.query_range(contract_id, tick_type, start_time, end_time)
        
        # Read files in parallel
        futures = []
        for file_info in files:
            future = self.executor.submit(
                self._read_protobuf_file,
                file_info['file_path'],
                start_time,
                end_time
            )
            futures.append(future)
        
        # Collect results
        all_messages = []
        for future in as_completed(futures):
            messages = future.result()
            all_messages.extend(messages)
        
        # Sort by timestamp
        all_messages.sort(key=lambda x: x['timestamp'])
        
        return all_messages
    
    def _query_incomplete_hour(
        self,
        contract_id: int,
        tick_type: str,
        hour_start: datetime,
        current_time: datetime
    ) -> List[Dict]:
        """Query the current incomplete hour from active file."""
        # Check if there's an active file for current hour
        file_path = self._get_file_path(contract_id, tick_type, hour_start)
        
        if file_path.exists():
            return self._read_protobuf_file(str(file_path), hour_start, current_time)
        
        return []
    
    def _get_session_boundaries(
        self,
        date: datetime,
        session_type: str,
        market: str
    ) -> Tuple[datetime, datetime]:
        """Get market session boundaries."""
        # Define market sessions
        sessions = {
            'US': {
                'pre_market': ('04:00', '09:30', 'US/Eastern'),
                'regular': ('09:30', '16:00', 'US/Eastern'),
                'after_hours': ('16:00', '20:00', 'US/Eastern'),
                'extended': ('04:00', '20:00', 'US/Eastern'),
                'overnight': ('00:00', '23:59', 'US/Eastern'),
            },
            'UK': {
                'regular': ('08:00', '16:30', 'Europe/London'),
                'extended': ('07:00', '17:30', 'Europe/London'),
            },
            'JP': {
                'morning': ('09:00', '11:30', 'Asia/Tokyo'),
                'afternoon': ('12:30', '15:00', 'Asia/Tokyo'),
                'regular': ('09:00', '15:00', 'Asia/Tokyo'),
            }
        }
        
        if market not in sessions:
            raise ValueError(f"Unknown market: {market}")
            
        if session_type not in sessions[market]:
            raise ValueError(f"Unknown session type for {market}: {session_type}")
        
        start_str, end_str, tz_name = sessions[market][session_type]
        tz = pytz.timezone(tz_name)
        
        # Parse times and localize to market timezone
        start_hour, start_min = map(int, start_str.split(':'))
        end_hour, end_min = map(int, end_str.split(':'))
        
        # Create datetime objects in market timezone
        local_date = date.astimezone(tz).date()
        start_local = tz.localize(datetime.combine(
            local_date,
            datetime.min.time().replace(hour=start_hour, minute=start_min)
        ))
        end_local = tz.localize(datetime.combine(
            local_date,
            datetime.min.time().replace(hour=end_hour, minute=end_min)
        ))
        
        # Handle sessions that cross midnight
        if end_local <= start_local:
            end_local += timedelta(days=1)
        
        # Convert to UTC
        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
```

### Session Helper Functions

```python
class MarketSessionHelper:
    """Helper class for common market session queries."""
    
    @staticmethod
    def get_current_session(market: str = 'US') -> Tuple[datetime, datetime]:
        """Get the current active session boundaries."""
        now = datetime.now(timezone.utc)
        
        # Map markets to their primary timezone
        market_timezones = {
            'US': 'US/Eastern',
            'UK': 'Europe/London',
            'JP': 'Asia/Tokyo',
        }
        
        tz = pytz.timezone(market_timezones[market])
        local_now = now.astimezone(tz)
        
        # Determine which session we're in
        hour = local_now.hour
        
        if market == 'US':
            if 4 <= hour < 9.5:
                session_type = 'pre_market'
            elif 9.5 <= hour < 16:
                session_type = 'regular'
            elif 16 <= hour < 20:
                session_type = 'after_hours'
            else:
                # Outside trading hours, return previous day's regular session
                date = local_now.date() - timedelta(days=1)
                return EnhancedProtobufQuery._get_session_boundaries(
                    datetime.combine(date, datetime.min.time()),
                    'regular',
                    market
                )
        
        query = EnhancedProtobufQuery(None, None)
        return query._get_session_boundaries(local_now, session_type, market)
    
    @staticmethod
    def get_previous_session(
        market: str = 'US',
        session_type: str = 'regular'
    ) -> Tuple[datetime, datetime]:
        """Get the previous session boundaries."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        
        query = EnhancedProtobufQuery(None, None)
        return query._get_session_boundaries(yesterday, session_type, market)
    
    @staticmethod
    def is_market_open(market: str = 'US') -> bool:
        """Check if market is currently open."""
        now = datetime.now(timezone.utc)
        try:
            start, end = MarketSessionHelper.get_current_session(market)
            return start <= now <= end
        except:
            return False
```

### Convenience Query Methods

```python
# Additional convenience methods for EnhancedProtobufQuery
class EnhancedProtobufQuery(ProtobufQuery):
    # ... previous methods ...
    
    def query_today(self, contract_id: int, tick_type: str) -> List[Dict]:
        """Query all data from midnight to present."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return self.query_to_present(contract_id, tick_type, today_start)
    
    def query_since_open(
        self, 
        contract_id: int, 
        tick_type: str, 
        market: str = 'US'
    ) -> List[Dict]:
        """Query since market open."""
        session_start, _ = MarketSessionHelper.get_current_session(market)
        return self.query_to_present(contract_id, tick_type, session_start)
    
    def query_previous_n_sessions(
        self,
        contract_id: int,
        tick_type: str,
        n_sessions: int,
        session_type: str = 'regular',
        market: str = 'US'
    ) -> List[Dict]:
        """Query data for previous N sessions."""
        all_messages = []
        current_date = datetime.now(timezone.utc)
        
        for i in range(n_sessions):
            date = current_date - timedelta(days=i)
            session_messages = self.query_session(
                contract_id, tick_type, date, session_type, market
            )
            all_messages.extend(session_messages)
        
        # Sort by timestamp
        all_messages.sort(key=lambda x: x['timestamp'])
        
        return all_messages
```

### PostgreSQL Helper Functions

```sql
-- Additional SQL functions for common query patterns

-- Get files for "to present" queries
CREATE OR REPLACE FUNCTION get_files_to_present(
    p_contract_id INTEGER,
    p_tick_type VARCHAR,
    p_start_time TIMESTAMPTZ
) RETURNS TABLE (
    file_path VARCHAR,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    message_count BIGINT,
    is_complete BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        tf.file_path,
        tf.start_time,
        tf.end_time,
        tf.message_count,
        tf.end_time < NOW() - INTERVAL '1 hour' as is_complete
    FROM tick_files tf
    WHERE tf.contract_id = p_contract_id
      AND tf.tick_type = p_tick_type
      AND tf.end_time >= p_start_time
    ORDER BY tf.start_time;
END;
$$ LANGUAGE plpgsql;

-- Get session boundaries for a date
CREATE OR REPLACE FUNCTION get_session_boundaries(
    p_date DATE,
    p_market VARCHAR DEFAULT 'US',
    p_session_type VARCHAR DEFAULT 'regular'
) RETURNS TABLE (
    session_start TIMESTAMPTZ,
    session_end TIMESTAMPTZ
) AS $$
DECLARE
    v_tz TEXT;
    v_start_time TIME;
    v_end_time TIME;
BEGIN
    -- Market timezone mapping
    CASE p_market
        WHEN 'US' THEN v_tz := 'US/Eastern';
        WHEN 'UK' THEN v_tz := 'Europe/London';
        WHEN 'JP' THEN v_tz := 'Asia/Tokyo';
        ELSE RAISE EXCEPTION 'Unknown market: %', p_market;
    END CASE;
    
    -- Session times
    IF p_market = 'US' THEN
        CASE p_session_type
            WHEN 'regular' THEN 
                v_start_time := '09:30:00'::TIME;
                v_end_time := '16:00:00'::TIME;
            WHEN 'extended' THEN
                v_start_time := '04:00:00'::TIME;
                v_end_time := '20:00:00'::TIME;
            WHEN 'pre_market' THEN
                v_start_time := '04:00:00'::TIME;
                v_end_time := '09:30:00'::TIME;
            WHEN 'after_hours' THEN
                v_start_time := '16:00:00'::TIME;
                v_end_time := '20:00:00'::TIME;
            ELSE RAISE EXCEPTION 'Unknown session type: %', p_session_type;
        END CASE;
    END IF;
    
    -- Convert to UTC
    RETURN QUERY
    SELECT 
        (p_date + v_start_time) AT TIME ZONE v_tz AT TIME ZONE 'UTC',
        (p_date + v_end_time) AT TIME ZONE v_tz AT TIME ZONE 'UTC';
END;
$$ LANGUAGE plpgsql;

-- Get files with data density information
CREATE OR REPLACE FUNCTION get_files_with_density(
    p_contract_id INTEGER,
    p_tick_type VARCHAR,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ
) RETURNS TABLE (
    file_path VARCHAR,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    message_count BIGINT,
    messages_per_minute NUMERIC,
    file_size_mb NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        tf.file_path,
        tf.start_time,
        tf.end_time,
        tf.message_count,
        CASE 
            WHEN EXTRACT(EPOCH FROM (tf.end_time - tf.start_time)) > 0 
            THEN tf.message_count::NUMERIC / (EXTRACT(EPOCH FROM (tf.end_time - tf.start_time)) / 60)
            ELSE 0
        END as messages_per_minute,
        tf.file_size_bytes::NUMERIC / (1024 * 1024) as file_size_mb
    FROM tick_files tf
    WHERE tf.contract_id = p_contract_id
      AND tf.tick_type = p_tick_type
      AND tf.start_time <= p_end_time
      AND tf.end_time >= p_start_time
    ORDER BY tf.start_time;
END;
$$ LANGUAGE plpgsql;
```

### API Endpoints for Historical Queries

```python
# Enhanced API endpoints in api_server.py

@app.get("/v2/historical/{contract_id}/range")
async def get_historical_range(
    contract_id: int,
    tick_type: str = "bid_ask",
    start_time: datetime,
    end_time: datetime,
    parallel: bool = False
):
    """Standard time range query."""
    query = EnhancedProtobufQuery(
        storage_path=config.protobuf_storage_path,
        db_connection=config.postgres_dsn
    )
    
    if parallel and (end_time - start_time).days > 1:
        messages = query.query_range_parallel(contract_id, tick_type, start_time, end_time)
    else:
        messages = query.query_range(contract_id, tick_type, start_time, end_time)
    
    return {"messages": messages, "count": len(messages)}

@app.get("/v2/historical/{contract_id}/to-present")
async def get_historical_to_present(
    contract_id: int,
    tick_type: str = "bid_ask",
    start_time: datetime,
    include_incomplete_hour: bool = True
):
    """Query from start time to current moment."""
    query = EnhancedProtobufQuery(
        storage_path=config.protobuf_storage_path,
        db_connection=config.postgres_dsn
    )
    
    messages = query.query_to_present(
        contract_id, tick_type, start_time, include_incomplete_hour
    )
    
    return {
        "messages": messages,
        "count": len(messages),
        "current_time": datetime.now(timezone.utc).isoformat()
    }

@app.get("/v2/historical/{contract_id}/session")
async def get_historical_session(
    contract_id: int,
    tick_type: str = "bid_ask",
    date: Optional[datetime] = None,
    session_type: str = "regular",
    market: str = "US"
):
    """Query market session data."""
    if date is None:
        date = datetime.now(timezone.utc)
    
    query = EnhancedProtobufQuery(
        storage_path=config.protobuf_storage_path,
        db_connection=config.postgres_dsn
    )
    
    messages = query.query_session(contract_id, tick_type, date, session_type, market)
    
    # Get session boundaries for reference
    start_time, end_time = query._get_session_boundaries(date, session_type, market)
    
    return {
        "messages": messages,
        "count": len(messages),
        "session": {
            "type": session_type,
            "market": market,
            "start": start_time.isoformat(),
            "end": end_time.isoformat()
        }
    }

@app.get("/v2/historical/{contract_id}/relative")
async def get_historical_relative(
    contract_id: int,
    tick_type: str = "bid_ask",
    period: str = "last_hour"
):
    """Query using relative time period."""
    query = EnhancedProtobufQuery(
        storage_path=config.protobuf_storage_path,
        db_connection=config.postgres_dsn
    )
    
    messages = query.query_relative(contract_id, tick_type, period)
    
    return {
        "messages": messages,
        "count": len(messages),
        "period": period
    }

@app.websocket("/v2/stream/{contract_id}/with-buffer")
async def stream_with_historical_buffer(
    websocket: WebSocket,
    contract_id: int,
    tick_type: str = "bid_ask",
    buffer_period: str = "last_hour"
):
    """WebSocket endpoint that provides historical buffer before live stream."""
    await websocket.accept()
    
    try:
        # Send historical buffer first
        query = EnhancedProtobufQuery(
            storage_path=config.protobuf_storage_path,
            db_connection=config.postgres_dsn
        )
        
        historical_messages = query.query_relative(contract_id, tick_type, buffer_period)
        
        # Send historical data
        for msg in historical_messages:
            await websocket.send_json({
                "type": "historical",
                "data": msg
            })
        
        # Send marker indicating switch to live
        await websocket.send_json({
            "type": "info",
            "data": {
                "status": "switching_to_live",
                "historical_count": len(historical_messages)
            }
        })
        
        # Connect to live stream
        # ... (existing WebSocket streaming logic)
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for contract {contract_id}")
```

### Usage Examples

```python
# Example 1: Query current trading session
query = EnhancedProtobufQuery(storage_path, db_conn)
messages = query.query_since_open(265598, 'bid_ask', market='US')
print(f"Ticks since market open: {len(messages)}")

# Example 2: Get last hour of data leading to present
messages = query.query_relative(265598, 'last', 'last_hour')
print(f"Ticks in last hour: {len(messages)}")

# Example 3: Query with historical buffer and continue live
async def process_with_buffer():
    async for msg in query.query_with_live_stream(
        265598, 'bid_ask', 
        buffer_period='last_30_minutes'
    ):
        # Process each tick (historical then live)
        process_tick(msg)

# Example 4: Get previous 5 trading sessions
messages = query.query_previous_n_sessions(
    265598, 'bid_ask', 
    n_sessions=5, 
    session_type='regular'
)

# Example 5: Parallel query for large date range
start = datetime(2025, 1, 1, tzinfo=timezone.utc)
end = datetime(2025, 1, 31, tzinfo=timezone.utc)
messages = query.query_range_parallel(265598, 'last', start, end)
```

### Performance Optimizations for Common Queries

1. **Session Queries** - Pre-compute session boundaries in database
2. **To-Present Queries** - Keep current hour file handle open for fast access
3. **Relative Queries** - Cache frequently requested periods
4. **Buffer + Live** - Pre-fetch historical while establishing live connection

## Tracked Contracts and Background Streaming

### Overview

The IB Stream server supports automatic tracking of predefined contracts at startup, providing continuous data capture for frequently accessed contracts. This enables seamless historical buffer + live streaming for clients.

### Configuration

Tracked contracts are configured via the `TrackedContract` class and environment variables:

```python
@dataclass
class TrackedContract:
    contract_id: int
    symbol: str  # For logging and monitoring
    tick_types: List[str] = field(default_factory=lambda: ["bid_ask", "last"])
    buffer_hours: int = 1  # Historical buffer duration
    enabled: bool = True
```

**Environment Variable Configuration:**
```bash
# Format: "contract_id:symbol:tick_types:buffer_hours,..."
# Example: Track MNQ and AAPL with different settings
export IB_STREAM_TRACKED_CONTRACTS="711280073:MNQ:bid_ask;last:2,265598:AAPL:bid_ask;last;mid_point:1"
```

**Configuration Options:**
- `IB_STREAM_MAX_TRACKED` - Maximum tracked contracts (default: 10)
- `IB_STREAM_RECONNECT_DELAY` - Background stream reconnect delay in seconds (default: 30)

### Background Streaming Architecture

```
┌─────────────────────┐    ┌─────────────────────┐
│   API Server       │    │ Background Stream   │
│   (Client ID: 2)    │    │ Manager (Client ID: 10)│
├─────────────────────┤    ├─────────────────────┤
│ • Client requests   │    │ • Tracked contracts │
│ • On-demand streams │    │ • Persistent streams│
│ • Buffer endpoints  │    │ • Auto-reconnect    │
└─────────────────────┘    └─────────────────────┘
           │                          │
           └──────────┬─────────────────┘
                      │
                ┌─────▼─────┐
                │ TWS/IB    │
                │ Gateway   │
                └───────────┘
```

**Key Features:**
- **Dual TWS Connections**: Separate client IDs for foreground and background streaming
- **Automatic Recovery**: Background streams automatically reconnect on failures
- **Storage Integration**: All tracked contract data flows through the storage system
- **Request ID Isolation**: Background streams use request IDs starting at 60000+

### Buffer Query Patterns

The `BufferQuery` class provides convenient access to historical data:

```python
from ib_stream.storage import create_buffer_query

# Initialize buffer query
buffer_query = create_buffer_query(storage_path)

# Query recent buffer data
messages = await buffer_query.query_buffer(
    contract_id=711280073,
    tick_types=["bid_ask", "last"],
    buffer_duration="1h"
)

# Query since specific time
messages = await buffer_query.query_buffer_since(
    contract_id=711280073,
    tick_types=["bid_ask"],
    since_time=datetime.now() - timedelta(hours=2)
)

# Query session data (market open to present)
messages = await buffer_query.query_session_buffer(
    contract_id=711280073,
    tick_types=["last"]
)

# Get buffer statistics
stats = await buffer_query.get_buffer_stats(
    contract_id=711280073,
    tick_types=["bid_ask", "last"],
    buffer_duration="30m"
)
```

**Duration Format Examples:**
- `"1m"`, `"5m"`, `"15m"`, `"30m"` - Minutes
- `"1h"`, `"2h"`, `"4h"`, `"12h"` - Hours  
- `"1d"`, `"2d"`, `"1w"` - Days/weeks
- `"2h30m"` - Complex combinations

### Buffer + Live Streaming Endpoints

#### Stream with Historical Buffer

```http
GET /v2/stream/{contract_id}/with-buffer?tick_types=bid_ask,last&buffer_duration=1h&limit=1000
```

**Response Flow:**
1. **Buffer Phase**: Historical data with `historical: true` metadata
2. **Transition Marker**: Info event marking switch to live data
3. **Live Phase**: Real-time data with `historical: false` metadata

**Example Response Sequence:**
```json
// Buffer start info
{"type": "info", "data": {"status": "buffer_start", "buffer_message_count": 245}}

// Historical tick events (with metadata.historical: true)
{"type": "tick", "data": {...}, "metadata": {"historical": true, "buffer_index": 0}}
{"type": "tick", "data": {...}, "metadata": {"historical": true, "buffer_index": 1}}
...

// Buffer complete + live start
{"type": "info", "data": {"status": "buffer_complete", "buffer_message_count": 245}}
{"type": "info", "data": {"status": "live_start"}}

// Live tick events (with metadata.historical: false)
{"type": "tick", "data": {...}, "metadata": {"historical": false}}
```

#### Buffer Information Endpoints

**Get Buffer Info:**
```http
GET /v2/buffer/{contract_id}/info?tick_types=bid_ask,last
```

```json
{
  "contract_id": 711280073,
  "tick_types": ["bid_ask", "last"],
  "tracked": true,
  "available_duration": "2:15:30",
  "configured_buffer_hours": 2,
  "latest_tick_time": "2025-07-10T13:45:22.123456Z",
  "buffer_stats_1h": {
    "message_count": 1247,
    "tick_type_counts": {"bid_ask": 623, "last": 624},
    "time_range": {"start": "...", "end": "..."},
    "duration_available": "0:59:58"
  }
}
```

**Get Buffer Statistics:**
```http
GET /v2/buffer/{contract_id}/stats?tick_types=bid_ask&duration=30m
```

### Background Stream Status

**Monitor Tracked Contracts:**
```http
GET /background/status
```

```json
{
  "enabled": true,
  "status": {
    "running": true,
    "tws_connected": true,
    "total_contracts": 2,
    "active_contracts": 2,
    "total_streams": 6,
    "contracts": {
      "711280073": {
        "symbol": "MNQ",
        "enabled": true,
        "expected_tick_types": ["bid_ask", "last"],
        "active_tick_types": ["bid_ask", "last"],
        "stream_count": 2,
        "buffer_hours": 2
      },
      "265598": {
        "symbol": "AAPL", 
        "enabled": true,
        "expected_tick_types": ["bid_ask", "last", "mid_point"],
        "active_tick_types": ["bid_ask", "last", "mid_point"],
        "stream_count": 3,
        "buffer_hours": 1
      }
    }
  }
}
```

### Use Cases

#### 1. Real-time Analytics with Historical Context
```python
# Client connects and immediately gets 1 hour of history + live data
curl -N http://localhost:8001/v2/stream/711280073/with-buffer?buffer_duration=1h
```

#### 2. Market Session Analysis
```python
# Get all data since market open
buffer_query = create_buffer_query(storage_path)
session_data = await buffer_query.query_session_buffer(711280073, ["last"])
```

#### 3. Statistical Analysis
```python
# Analyze recent market activity  
stats = await buffer_query.get_buffer_stats(711280073, ["bid_ask"], "2h")
print(f"Recent activity: {stats['message_count']} ticks")
print(f"Bid/Ask ratio: {stats['tick_type_counts']}")
```

### Performance Characteristics

**Background Streaming:**
- **Memory Usage**: ~10MB per tracked contract (including buffers)
- **TWS Load**: One persistent connection per tick type per contract
- **Storage Rate**: ~1000-5000 ticks/minute during active trading (varies by contract)
- **Buffer Query Speed**: <100ms for 1-hour queries, <500ms for 1-day queries

**Scalability Limits:**
- **Max Tracked Contracts**: 10 (configurable, limited by TWS connection limits)
- **Max Buffer Duration**: 24 hours (recommended), unlimited (storage permitting)
- **Concurrent Buffer Queries**: 50+ simultaneous without performance impact

### Operational Considerations

**Resource Management:**
```bash
# Monitor background streaming
curl http://localhost:8001/background/status | jq .status.total_streams

# Monitor storage usage
curl http://localhost:8001/storage/status | jq .metrics.storage_usage

# Check buffer availability
curl http://localhost:8001/v2/buffer/711280073/info | jq .available_duration
```

**Failure Recovery:**
- **TWS Disconnection**: Automatic reconnection with exponential backoff
- **Missing Ticks**: Background streams continue independently of client requests
- **Storage Errors**: Logged but don't affect streaming (graceful degradation)
- **Contract Issues**: Individual contracts can fail without affecting others

**Maintenance:**
```bash
# Add new tracked contract (requires restart)
export IB_STREAM_TRACKED_CONTRACTS="$IB_STREAM_TRACKED_CONTRACTS,12345:SPY:bid_ask:1"

# Monitor and restart if needed
bd restart ib-stream

# Verify tracking
curl http://localhost:8001/background/status | jq .status.contracts
```

## Integration with Existing System

### StreamingApp Integration

```python
# In streaming_app.py
class StreamingApp(EWrapper, EClient):
    def __init__(self, protobuf_storage: Optional[ProtobufStorage] = None, **kwargs):
        super().__init__(**kwargs)
        self.protobuf_storage = protobuf_storage
        
    async def route_tick_data(self, request_id: int, tick_data: Dict[str, Any]) -> bool:
        """Enhanced to support protobuf storage."""
        # Existing JSON routing
        success = await super().route_tick_data(request_id, tick_data)
        
        # Additionally store in protobuf format
        if self.protobuf_storage and success:
            try:
                self.protobuf_storage.append_tick(tick_data)
            except Exception as e:
                logger.error(f"Failed to store tick in protobuf format: {e}")
        
        return success
```

### API Server Integration

```python
# New endpoint for protobuf format
@app.get("/v2/historical/{contract_id}/protobuf")
async def get_historical_protobuf(
    contract_id: int,
    tick_types: str = "bid_ask",
    start_time: datetime,
    end_time: Optional[datetime] = None,
    format: str = "json"  # "json" or "protobuf"
):
    """Get historical data from protobuf storage."""
    
    if end_time is None:
        end_time = datetime.now(timezone.utc)
    
    tick_type_list = tick_types.split(',')
    query = ProtobufQuery(storage_path=config.protobuf_storage_path, 
                         db_connection=config.postgres_dsn)
    
    all_messages = []
    for tick_type in tick_type_list:
        messages = query.query_range(contract_id, tick_type.strip(), start_time, end_time)
        all_messages.extend(messages)
    
    # Sort by timestamp
    all_messages.sort(key=lambda x: x['timestamp'])
    
    if format == "protobuf":
        # Return raw protobuf bytes
        return Response(
            content=serialize_messages_to_protobuf(all_messages),
            media_type="application/x-protobuf"
        )
    else:
        # Return JSON (default)
        return {"messages": all_messages}
```

## Performance Characteristics

### Expected Performance

| Metric | Expected Value | Notes |
|--------|----------------|-------|
| **Write Speed** | 100,000 ticks/second | Batched writes with length prefixing |
| **Query Speed** | <50ms for 1-hour range | PostgreSQL index + sequential file read |
| **Storage Efficiency** | 70-80% reduction vs JSON | Protobuf compression + optional gzip |
| **File Size** | 50-100MB per hour | For active contracts during market hours |
| **Memory Usage** | <100MB | Small buffer for current hour files |

### Query Patterns and Performance

```sql
-- Common query patterns and expected performance

-- 1. Get files for current session (sub-second)
SELECT file_path FROM tick_files 
WHERE contract_id = 265598 
  AND tick_type = 'bid_ask'
  AND hour_bucket >= '2025-01-10 14:00:00+00'
  AND hour_bucket <= '2025-01-10 21:00:00+00';

-- 2. Get session statistics (milliseconds)
SELECT 
    MIN(start_time) as session_start,
    MAX(end_time) as session_end,
    SUM(message_count) as total_ticks,
    SUM(file_size_bytes) as total_size
FROM tick_files 
WHERE contract_id = 265598 
  AND date(hour_bucket) = '2025-01-10';

-- 3. Find active contracts for date (milliseconds)
SELECT DISTINCT contract_id, tick_type, COUNT(*) as file_count
FROM tick_files 
WHERE date(hour_bucket) = '2025-01-10'
GROUP BY contract_id, tick_type
ORDER BY file_count DESC;
```

## Operational Considerations

### Maintenance Tasks

1. **File Rotation** - Automatic hourly file closing and database updates
2. **Compression** - Optional gzip compression for files older than 24 hours
3. **Cleanup** - Archive/delete files older than retention period
4. **Statistics** - Update daily aggregation tables for faster range queries

### Monitoring

```sql
-- Storage monitoring queries

-- Daily storage usage
SELECT 
    date(hour_bucket) as date,
    SUM(file_size_bytes) / (1024*1024*1024) as size_gb,
    SUM(message_count) as total_messages
FROM tick_files 
WHERE hour_bucket >= NOW() - INTERVAL '30 days'
GROUP BY date(hour_bucket)
ORDER BY date;

-- Top contracts by storage
SELECT 
    contract_id,
    SUM(file_size_bytes) / (1024*1024) as size_mb,
    SUM(message_count) as total_ticks
FROM tick_files 
WHERE hour_bucket >= NOW() - INTERVAL '7 days'
GROUP BY contract_id
ORDER BY size_mb DESC
LIMIT 20;
```

### Error Handling

1. **File Corruption** - Checksums in file headers, graceful degradation
2. **Database Connectivity** - Retry logic, local queue for metadata updates
3. **Disk Space** - Monitoring and automatic cleanup of old files
4. **Schema Evolution** - Version field in protobuf for backward compatibility

## Migration Strategy

### Phase 1: Parallel Operation (Week 1)
1. Deploy protobuf storage alongside existing JSON storage
2. Start capturing data in both formats
3. Validate data consistency between formats

### Phase 2: Client Integration (Week 2-3)
1. Add protobuf endpoints to API
2. Update ib-studies to optionally use protobuf data
3. Performance testing and optimization

### Phase 3: Full Migration (Week 4)
1. Make protobuf storage the primary format
2. JSON storage becomes backup/debugging format
3. Implement data lifecycle policies

## Conclusion

This protobuf-based storage system provides:

1. **60-70% storage reduction** compared to JSON
2. **Fast queries** using PostgreSQL indexing
3. **Simple implementation** with familiar SQL interface
4. **Hourly partitioning** for manageable file sizes
5. **Direct v2 protocol mapping** for seamless integration

The system balances simplicity with performance, providing an efficient foundation for ib-studies historical analysis while maintaining the flexibility to evolve with changing requirements.