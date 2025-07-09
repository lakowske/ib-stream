# IB-Stream API Inconsistencies Report v1

## Executive Summary

This document identifies and analyzes inconsistencies between the Server-Sent Events (SSE) and WebSocket transport mechanisms in the IB-Stream API. These inconsistencies create unnecessary complexity for client developers and increase the potential for errors when switching between or supporting both transports.

## Key Inconsistencies Overview

### 1. Message Format Differences

**SSE Format:**
```
event: tick
data: {"type": "tick", "contract_id": 265598, "timestamp": "2025-01-15T10:30:00.123Z", "data": {...}}

event: error
data: {"type": "error", "contract_id": 265598, "timestamp": "2025-01-15T10:30:00.123Z", "error": {...}}
```

**WebSocket Format:**
```json
{
  "type": "tick",
  "request_id": "265598_BidAsk_1234567890_1234",
  "data": {...},
  "timestamp": "2025-01-15T10:30:00.123Z"
}
```

**Issues:**
- SSE duplicates the event type in both the SSE event field and JSON data
- WebSocket uses `request_id` while SSE uses `contract_id` directly
- Error structure differs between protocols

### 2. Endpoint Structure Inconsistencies

**SSE Endpoints:**
```
GET /stream/{contract_id}/{tick_type}?limit=100&timeout=60
GET /stream/{contract_id}?tick_types=BidAsk,Last
```

**WebSocket Endpoints:**
```
ws://{host}/ws/stream/{contract_id}/{tick_type}
ws://{host}/ws/stream/{contract_id}/multi
ws://{host}/ws/control
```

**Issues:**
- SSE uses query parameters for configuration, WebSocket uses message protocol
- Multi-stream handling differs: SSE uses comma-separated query param, WebSocket has dedicated endpoint
- No control endpoint equivalent in SSE

### 3. Subscription Management Differences

**SSE Subscription:**
- Fixed at connection time
- No dynamic subscribe/unsubscribe
- Single HTTP request determines entire stream lifecycle

**WebSocket Subscription:**
```json
// Subscribe
{"type": "subscribe", "id": "msg-001", "data": {"contract_id": 711280073, "tick_type": "BidAsk"}}

// Multi-subscribe
{"type": "multi_subscribe", "id": "msg-002", "data": {"contract_id": 711280073, "tick_types": ["BidAsk", "Last"]}}

// Unsubscribe
{"type": "unsubscribe", "id": "msg-003", "data": {"request_id": "req-12345"}}
```

**Issues:**
- WebSocket allows dynamic subscription management
- SSE requires new connection for subscription changes
- Different lifecycle management approaches

### 4. Data Field Naming Inconsistencies

**Tick Type Field:**
- SSE tick data: Uses `type` field (e.g., "bid_ask", "time_sales")
- WebSocket message: Uses `tick_type` in subscription, but `type` in tick data
- Inconsistent casing: "BidAsk" vs "bid_ask"

**Timestamp Fields:**
- SSE: Single `timestamp` in ISO format
- WebSocket tick data: Multiple timestamp fields (`time`, `unix_time`, message `timestamp`)

**Price/Size Fields:**
- Different field names for same data (e.g., `bid_price` vs `bidPrice` in some cases)

### 5. Error Handling Differences

**SSE Errors:**
```json
{
  "type": "error",
  "contract_id": 265598,
  "error": {
    "code": "CONTRACT_NOT_FOUND",
    "message": "Could not find contract with ID 265598",
    "details": "Verify contract ID using the contract lookup API"
  }
}
```

**WebSocket Errors:**
```json
{
  "type": "error",
  "request_id": "req-12345",
  "error": {
    "code": "CONTRACT_NOT_FOUND",
    "message": "Contract ID not found",
    "details": {}
  },
  "timestamp": "2025-07-09T12:00:00Z"
}
```

**Issues:**
- SSE uses `contract_id`, WebSocket uses `request_id`
- Error detail structure differs
- WebSocket includes timestamp at message level

### 6. Stream Completion Handling

**SSE Completion:**
```json
{
  "type": "complete",
  "contract_id": 265598,
  "reason": "limit_reached",
  "total_ticks": 100
}
```

**WebSocket Completion:**
```json
{
  "type": "complete",
  "request_id": "req-12345",
  "data": {
    "reason": "limit_reached",
    "total_ticks": 100,
    "duration_seconds": 45.2
  }
}
```

**Issues:**
- WebSocket nests completion data, SSE flattens it
- WebSocket includes duration, SSE doesn't
- Identifier inconsistency (contract_id vs request_id)

### 7. Multi-Stream Support Differences

**SSE Multi-Stream:**
- Not truly supported - client must parse single stream with multiple tick types
- No clear separation between different tick types in the stream

**WebSocket Multi-Stream:**
- Explicit multi-subscribe message type
- Each tick identifies its source via request_id
- Clear separation and routing of different data types

### 8. Connection Lifecycle Management

**SSE:**
- Simple HTTP connection
- No explicit connection acknowledgment
- Reconnection handled by client

**WebSocket:**
- Handshake protocol
- Explicit "connected" message on establishment
- Built-in ping/pong for keepalive
- Structured close codes

## Detailed Comparison Tables

### Message Types Comparison

| Message Type | SSE Event | WebSocket Type | Key Differences |
|-------------|-----------|----------------|-----------------|
| Market Data | `tick` | `tick` | Field structure, identifiers |
| Error | `error` | `error` | Nesting, detail format |
| Completion | `complete` | `complete` | Data nesting, fields |
| Info/Metadata | `info` | `subscribed` | SSE generic, WS specific |
| Connection | N/A | `connected` | WS only |
| Subscription | N/A | `subscribe` | WS only |
| Unsubscription | N/A | `unsubscribe` | WS only |
| Keepalive | N/A | `ping`/`pong` | WS only |

### Field Naming Comparison

| Data | SSE Field | WebSocket Field | Notes |
|------|-----------|-----------------|-------|
| Stream Identifier | `contract_id` | `request_id` | Fundamental difference |
| Tick Type | `type` | `type` or `tick_type` | Context dependent |
| Error Code | `error.code` | `error.code` | Consistent |
| Timestamp | `timestamp` | `timestamp` + others | WS has multiple |
| Completion Reason | `reason` | `data.reason` | Nesting difference |

## Recommendations for Standardization

### 1. Unified Message Structure
Adopt a consistent message structure across both transports:
```json
{
  "type": "message_type",
  "stream_id": "unique_identifier",
  "data": {
    // All message-specific data here
  },
  "timestamp": "ISO-8601",
  "metadata": {
    // Optional metadata
  }
}
```

### 2. Consistent Field Naming
- Use `stream_id` instead of mixing `contract_id` and `request_id`
- Standardize on camelCase or snake_case (currently mixed)
- Use consistent tick type values across both transports

### 3. Unified Endpoint Pattern
- Consider supporting WebSocket-style subscription via SSE headers
- Or provide SSE-style simple endpoints for WebSocket

### 4. Error Structure Standardization
```json
{
  "type": "error",
  "stream_id": "identifier",
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {},
    "recoverable": true
  },
  "timestamp": "ISO-8601"
}
```

### 5. Multi-Stream Handling
- Provide consistent multi-stream support in both transports
- Use same subscription model where possible

## Migration Considerations

### For SSE Clients Moving to WebSocket
1. Implement message-based protocol handler
2. Add subscription management logic
3. Handle connection lifecycle events
4. Update field mappings

### For WebSocket Clients Supporting SSE
1. Implement SSE parser
2. Handle fixed subscription model
3. Add client-side reconnection logic
4. Map SSE events to WebSocket message types

## Implementation Priority

1. **High Priority:**
   - Standardize stream identifiers (contract_id vs request_id)
   - Unify error message structure
   - Consistent field naming for tick data

2. **Medium Priority:**
   - Align multi-stream handling
   - Standardize completion messages
   - Unified timestamp handling

3. **Low Priority:**
   - Add control features to SSE
   - Full protocol parity

## Conclusion

The current inconsistencies between SSE and WebSocket implementations create unnecessary complexity and potential for errors. By standardizing message formats, field names, and behavioral patterns, we can significantly improve the developer experience and reduce maintenance burden.

These changes should be implemented gradually with careful versioning to maintain backward compatibility while moving toward a more consistent API surface.