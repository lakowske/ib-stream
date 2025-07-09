# IB-Stream v2 Protocol Specification

## Overview

This document defines the unified protocol for IB-Stream v2, supporting both Server-Sent Events (SSE) and WebSocket transports. The protocol is designed to minimize differences between transports while respecting their inherent characteristics.

## Core Principles

1. **Unified Message Structure**: All messages follow the same JSON structure regardless of transport
2. **Consistent Naming**: Snake_case field names throughout
3. **Stream Identity**: Every stream has a unique `stream_id` identifier
4. **Explicit Typing**: All messages include a `type` field
5. **Timestamp Standardization**: ISO-8601 timestamps for all events

## Message Structure

### Base Message Format

All messages MUST follow this structure:

```json
{
  "type": "message_type",
  "stream_id": "unique_stream_identifier",
  "timestamp": "2025-01-15T10:30:00.123Z",
  "data": {
    // Message-specific payload
  },
  "metadata": {
    // Optional metadata
  }
}
```

### Field Definitions

- **type** (string, required): Message type identifier
- **stream_id** (string, required): Unique identifier for the stream
- **timestamp** (string, required): ISO-8601 formatted timestamp
- **data** (object, required): Message-specific payload
- **metadata** (object, optional): Additional context or transport-specific information

## Message Types

### 1. Tick Message

Market data update message.

```json
{
  "type": "tick",
  "stream_id": "265598_bid_ask_1234567890",
  "timestamp": "2025-01-15T10:30:00.123Z",
  "data": {
    "contract_id": 265598,
    "tick_type": "bid_ask",
    "bid_price": 175.25,
    "bid_size": 100,
    "ask_price": 175.26,
    "ask_size": 150,
    "exchange": "SMART",
    "conditions": []
  }
}
```

#### Tick Type Values

- `last`: Last traded price
- `all_last`: All trades including extended hours
- `bid_ask`: Bid and ask quotes
- `mid_point`: Calculated midpoint

### 2. Error Message

Error notification for stream-related issues.

```json
{
  "type": "error",
  "stream_id": "265598_bid_ask_1234567890",
  "timestamp": "2025-01-15T10:30:00.123Z",
  "data": {
    "code": "CONTRACT_NOT_FOUND",
    "message": "Contract ID 265598 not found",
    "details": {
      "contract_id": 265598,
      "suggestion": "Verify contract ID using the contract lookup API"
    },
    "recoverable": false
  }
}
```

#### Standard Error Codes

- `CONTRACT_NOT_FOUND`: Invalid contract ID
- `CONNECTION_ERROR`: TWS/Gateway connection issue
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `INVALID_TICK_TYPE`: Unsupported tick type
- `STREAM_TIMEOUT`: Stream exceeded timeout
- `PERMISSION_DENIED`: Insufficient permissions
- `INTERNAL_ERROR`: Server error

### 3. Complete Message

Stream completion notification.

```json
{
  "type": "complete",
  "stream_id": "265598_bid_ask_1234567890",
  "timestamp": "2025-01-15T10:30:45.123Z",
  "data": {
    "reason": "limit_reached",
    "total_ticks": 100,
    "duration_seconds": 45.2,
    "final_sequence": 100
  }
}
```

#### Completion Reasons

- `limit_reached`: Tick limit reached
- `timeout`: Stream timeout
- `client_disconnect`: Client-initiated
- `server_shutdown`: Server maintenance
- `error`: Unrecoverable error

### 4. Info Message

Stream metadata and status updates.

```json
{
  "type": "info",
  "stream_id": "265598_bid_ask_1234567890",
  "timestamp": "2025-01-15T10:30:00.123Z",
  "data": {
    "status": "subscribed",
    "contract_info": {
      "symbol": "AAPL",
      "exchange": "SMART",
      "currency": "USD",
      "contract_type": "STK"
    },
    "stream_config": {
      "tick_type": "bid_ask",
      "limit": 100,
      "timeout_seconds": 300
    }
  }
}
```

### 5. Subscribe Message (WebSocket Only)

Request to start a new stream.

```json
{
  "type": "subscribe",
  "id": "msg-001",
  "data": {
    "contract_id": 265598,
    "tick_types": ["bid_ask", "last"],
    "config": {
      "limit": 100,
      "timeout_seconds": 300
    }
  }
}
```

### 6. Unsubscribe Message (WebSocket Only)

Request to stop a stream.

```json
{
  "type": "unsubscribe",
  "id": "msg-002",
  "data": {
    "stream_id": "265598_bid_ask_1234567890"
  }
}
```

### 7. Control Messages (WebSocket Only)

#### Ping
```json
{
  "type": "ping",
  "id": "msg-003",
  "timestamp": "2025-01-15T10:30:00.123Z"
}
```

#### Pong
```json
{
  "type": "pong",
  "id": "msg-003",
  "data": {
    "client_timestamp": "2025-01-15T10:30:00.123Z",
    "server_timestamp": "2025-01-15T10:30:00.150Z"
  }
}
```

## Transport-Specific Behavior

### SSE Transport

#### Connection Format
```
GET /v2/stream/{contract_id}/{tick_type}?limit=100&timeout=300
```

#### Message Delivery
```
event: tick
data: {"type":"tick","stream_id":"265598_bid_ask_1234567890",...}

event: error
data: {"type":"error","stream_id":"265598_bid_ask_1234567890",...}

event: complete
data: {"type":"complete","stream_id":"265598_bid_ask_1234567890",...}
```

#### SSE-Specific Characteristics
- Unidirectional: Server to client only
- Fixed subscription at connection time
- No dynamic subscription management
- Client-managed reconnection
- Event field matches message type

### WebSocket Transport

#### Connection Format
```
ws://host:port/v2/ws/stream
```

#### Initial Handshake
Upon connection, server sends:
```json
{
  "type": "connected",
  "timestamp": "2025-01-15T10:30:00.123Z",
  "data": {
    "version": "2.0.0",
    "capabilities": {
      "max_streams_per_connection": 20,
      "supported_tick_types": ["last", "all_last", "bid_ask", "mid_point"],
      "ping_interval_seconds": 30
    }
  }
}
```

#### WebSocket-Specific Characteristics
- Bidirectional communication
- Dynamic subscription management
- Multiple streams per connection
- Built-in ping/pong keepalive
- Structured close codes

## Multi-Stream Support

### SSE Multi-Stream

For SSE, multiple tick types are requested via query parameter:
```
GET /v2/stream/{contract_id}?tick_types=bid_ask,last&limit=100
```

All messages include tick type in the data:
```json
{
  "type": "tick",
  "stream_id": "265598_multi_1234567890",
  "data": {
    "tick_type": "bid_ask",
    // tick-specific fields
  }
}
```

### WebSocket Multi-Stream

WebSocket supports dynamic multi-stream subscriptions:
```json
{
  "type": "subscribe",
  "id": "msg-001",
  "data": {
    "contract_id": 265598,
    "tick_types": ["bid_ask", "last"],
    "config": {
      "limit": 100
    }
  }
}
```

Server responds with individual stream IDs:
```json
{
  "type": "subscribed",
  "id": "msg-001",
  "data": {
    "streams": [
      {
        "stream_id": "265598_bid_ask_1234567890",
        "tick_type": "bid_ask"
      },
      {
        "stream_id": "265598_last_1234567891",
        "tick_type": "last"
      }
    ]
  }
}
```

## Stream Identification

### Stream ID Format

Stream IDs follow the pattern:
```
{contract_id}_{tick_type}_{timestamp}_{random}
```

Examples:
- `265598_bid_ask_1234567890_5678`
- `711280073_last_1234567891_9012`

### Stream ID Usage

- All server-to-client messages include `stream_id`
- WebSocket unsubscribe uses `stream_id`
- Stream IDs are unique per stream instance
- Stream IDs persist for the stream lifetime

## Error Handling

### Error Message Structure

All errors follow the same structure regardless of transport:

```json
{
  "type": "error",
  "stream_id": "stream_identifier",
  "timestamp": "2025-01-15T10:30:00.123Z",
  "data": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": {
      // Context-specific information
    },
    "recoverable": true
  }
}
```

### Recovery Behavior

- **recoverable: true**: Client may retry
- **recoverable: false**: Client should not retry with same parameters

## Versioning

### Version Header

Both transports include version information:

**SSE**: Response header
```
X-IB-Stream-Version: 2.0.0
```

**WebSocket**: In connected message
```json
{
  "type": "connected",
  "data": {
    "version": "2.0.0"
  }
}
```

### Backward Compatibility

- v1 endpoints remain at `/stream/`
- v2 endpoints use `/v2/stream/`
- Version negotiation via Accept header or query parameter

## Security Considerations

### Authentication

Both transports support:
- API key via header: `X-API-Key: <key>`
- JWT token via header: `Authorization: Bearer <token>`
- Query parameter (WebSocket): `?token=<token>`

### Rate Limiting

Consistent rate limits across transports:
- Max streams per client: 50
- Max messages per second (WebSocket): 100
- Max bandwidth per stream: 10 MB/s

### Encryption

- Production deployments MUST use TLS
- SSE: HTTPS required
- WebSocket: WSS required

## Implementation Notes

### Timestamp Precision

- All timestamps MUST include milliseconds
- Format: `YYYY-MM-DDTHH:mm:ss.sssZ`
- Always UTC timezone

### Number Formatting

- Prices: Decimal with appropriate precision
- Sizes: Integer or decimal as appropriate
- No scientific notation

### Field Presence

- Required fields MUST always be present
- Optional fields MAY be omitted
- Null values SHOULD be omitted

## Migration Guide

### From v1 to v2

1. **Update Endpoints**: Add `/v2` prefix
2. **Field Mapping**:
   - `contract_id` → `stream_id` (in messages)
   - `request_id` → `stream_id`
   - Mixed case → snake_case
3. **Message Structure**: Adopt unified format
4. **Error Handling**: Use new error structure

### Client Library Updates

Example migration for tick handler:

**v1 Handler**:
```javascript
function handleTick(data) {
  const contractId = data.contract_id || data.request_id;
  const price = data.bidPrice || data.bid_price;
  // Process tick
}
```

**v2 Handler**:
```javascript
function handleTick(message) {
  const { stream_id, data } = message;
  const { bid_price, tick_type } = data;
  // Process tick
}
```

## Appendix: Complete Field Reference

### Tick Data Fields

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| contract_id | integer | IB contract identifier | Yes |
| tick_type | string | Type of tick data | Yes |
| price | number | Trade price (last/all_last) | Conditional |
| size | number | Trade size | Conditional |
| bid_price | number | Bid price | Conditional |
| bid_size | number | Bid size | Conditional |
| ask_price | number | Ask price | Conditional |
| ask_size | number | Ask size | Conditional |
| mid_price | number | Calculated midpoint | Conditional |
| exchange | string | Execution exchange | No |
| conditions | array | Trade conditions | No |
| sequence | integer | Tick sequence number | No |

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| limit | integer | null | Max ticks before auto-stop |
| timeout_seconds | integer | 300 | Stream timeout in seconds |
| buffer_size | integer | 1000 | Internal buffer size |
| include_extended | boolean | false | Include extended hours |