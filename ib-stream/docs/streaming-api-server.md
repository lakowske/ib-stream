# IB Stream API Server Technical Specification

## Overview

This document specifies the design and implementation of a FastAPI-based HTTP server that provides real-time streaming market data from Interactive Brokers TWS via Server-Sent Events (SSE). The server builds upon the existing `ib-stream` CLI tool to provide web-accessible market data streaming.

## Goals

- **Web Integration**: Provide HTTP/SSE endpoints for web applications and trading systems
- **Real-time Streaming**: Low-latency tick-by-tick market data delivery
- **Multiple Clients**: Support concurrent connections from multiple clients
- **Reliability**: Graceful handling of TWS disconnections and automatic reconnection
- **Simplicity**: Focus on SSE for broad client compatibility
- **Compatibility**: Preserve all functionality from the CLI tool

## Architecture

### High-Level Design

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Clients   │    │  HTTP Clients   │    │  API Consumers  │
│   (Browsers)    │    │   (curl, etc)   │    │  (Trading Apps) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │ HTTP/SSE
                                 ▼
                    ┌─────────────────────────────┐
                    │     FastAPI Server          │
                    │   - SSE Streaming           │
                    │   - Stream Management       │
                    │   - Connection Pooling      │
                    └─────────────────────────────┘
                                 │ TWS API
                                 ▼
                    ┌─────────────────────────────┐
                    │   Interactive Brokers       │
                    │      TWS/Gateway            │
                    └─────────────────────────────┘
```

### Core Components

1. **StreamManager**: Manages multiple concurrent streams and client subscriptions
2. **SSEStreamingResponse**: Handles Server-Sent Events formatting and delivery
3. **StreamingApp**: Enhanced version of existing CLI streaming application
4. **ConnectionManager**: TWS connection lifecycle and client ID management

## API Endpoints

### Core Endpoints

#### Root Information
- **GET /** - API information and available endpoints
- **GET /health** - Health check with TWS connection status
- **GET /stream/info** - Available tick types and streaming capabilities

#### Streaming Endpoints
- **GET /stream/{contract_id}** - Stream market data with query parameters
- **GET /stream/{contract_id}/{tick_type}** - Stream specific tick type data

#### Management Endpoints
- **GET /stream/active** - List currently active streams
- **DELETE /stream/{contract_id}** - Stop specific stream for all clients
- **DELETE /stream/all** - Stop all active streams

### Query Parameters

Map CLI options to HTTP query parameters:

| Parameter | Type | Default | Description | CLI Equivalent |
|-----------|------|---------|-------------|----------------|
| `limit` | integer | unlimited | Number of ticks before auto-stop | `--number` |
| `tick_type` | enum | "Last" | Data type to stream | `--type` |
| `timeout` | integer | 300 | Stream timeout in seconds | N/A |
| `format` | enum | "sse" | Response format (sse only for now) | `--json` |

#### Tick Types
- `Last` - Regular trades during market hours
- `AllLast` - All trades including pre/post market
- `BidAsk` - Real-time bid and ask quotes
- `MidPoint` - Calculated midpoint between bid and ask

## Server-Sent Events (SSE)

### Protocol Choice

SSE chosen as the primary streaming protocol because:
- ✅ Native browser support with `EventSource` API
- ✅ Automatic reconnection handling
- ✅ Simple HTTP-based protocol
- ✅ Works through firewalls and proxies
- ✅ Standard `text/event-stream` MIME type

### SSE Event Format

```
data: {"type": "tick", "contract_id": 265598, "data": {...}}

data: {"type": "error", "contract_id": 265598, "error": "Contract not found"}

data: {"type": "complete", "contract_id": 265598, "reason": "limit_reached", "total_ticks": 100}
```

### Event Types

| Event Type | Description |
|------------|-------------|
| `tick` | Market data tick (bid/ask, trade, midpoint) |
| `error` | Stream error (invalid contract, TWS disconnect) |
| `complete` | Stream completion (limit reached, manual stop) |
| `info` | Stream metadata (contract details, start notification) |

## Configuration

### Server Startup Configuration

Configuration via environment variables and command-line arguments:

```bash
# Environment Variables
export IB_STREAM_CLIENT_ID=2           # TWS client ID (default: 2)
export IB_STREAM_HOST=127.0.0.1        # TWS host (default: 127.0.0.1)
export IB_STREAM_PORTS=7497,7496,4002,4001  # TWS ports to try
export IB_STREAM_MAX_STREAMS=50        # Max concurrent streams
export IB_STREAM_STREAM_TIMEOUT=300    # Default stream timeout seconds

# Start Server
uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8000
```

### Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `client_id` | 2 | TWS client ID (not user-configurable via API) |
| `max_concurrent_streams` | 50 | Maximum simultaneous streams |
| `default_timeout` | 300 | Default stream timeout (5 minutes) |
| `reconnect_attempts` | 3 | TWS reconnection attempts |
| `buffer_size` | 100 | Internal tick buffer size |

## Data Formats

### Request Examples

```bash
# Stream bid/ask data for Apple stock
curl -N "http://localhost:8000/stream/265598?tick_type=BidAsk&limit=100"

# Stream unlimited trades with 5-minute timeout
curl -N "http://localhost:8000/stream/265598?tick_type=Last&timeout=300"

# Stream 50 midpoint calculations
curl -N "http://localhost:8000/stream/265598?tick_type=MidPoint&limit=50"
```

### Response Format

#### Tick Event Data
```json
{
  "type": "tick",
  "contract_id": 265598,
  "timestamp": "2025-01-15T10:30:00.123Z",
  "data": {
    "type": "bid_ask",
    "timestamp": "2025-01-15 10:30:00",
    "unix_time": 1705319400,
    "bid_price": 175.25,
    "ask_price": 175.26,
    "bid_size": 100.0,
    "ask_size": 200.0,
    "bid_past_low": false,
    "ask_past_high": false
  }
}
```

#### Error Event Data
```json
{
  "type": "error",
  "contract_id": 265598,
  "timestamp": "2025-01-15T10:30:00.123Z",
  "error": {
    "code": "CONTRACT_NOT_FOUND",
    "message": "Could not find contract with ID 265598",
    "details": "Verify contract ID using the contract lookup API"
  }
}
```

## Error Handling

### HTTP Status Codes

| Code | Scenario |
|------|----------|
| 200 | Stream started successfully |
| 400 | Invalid parameters (bad contract_id, invalid tick_type) |
| 404 | Contract not found |
| 429 | Too many concurrent streams |
| 503 | TWS connection unavailable |
| 500 | Internal server error |

### Error Scenarios

1. **Contract Not Found**: Invalid contract_id
2. **TWS Disconnection**: Lost connection to TWS/Gateway
3. **Rate Limiting**: Too many concurrent streams
4. **Invalid Parameters**: Bad tick_type or limit values
5. **Timeout**: Stream exceeded timeout duration

### Error Recovery

- **Automatic Reconnection**: Attempt to reconnect to TWS on disconnection
- **Graceful Degradation**: Return errors via SSE events, not HTTP errors
- **Client Notification**: Inform clients of connection issues via error events

## Connection Management

### Stream Lifecycle

1. **Start**: Client requests stream via GET endpoint
2. **Subscribe**: Server creates/joins existing stream for contract
3. **Stream**: Real-time data delivered via SSE
4. **Stop**: Stream ends due to limit, timeout, or manual termination
5. **Cleanup**: Server removes inactive streams and connections

### Multiple Client Support

- Multiple clients can subscribe to the same contract stream
- Server maintains single TWS subscription per contract
- Data broadcast to all subscribed clients
- Individual client disconnections don't affect other clients

### Automatic Cleanup

- Streams auto-terminate after timeout period
- Inactive connections removed from subscription lists
- TWS subscriptions cancelled when no clients remain
- Memory cleanup for completed streams

## Performance Considerations

### Scalability

- **Connection Pooling**: Reuse TWS connections across streams
- **Event Broadcasting**: Single TWS subscription serves multiple clients
- **Memory Management**: Bounded buffers and automatic cleanup
- **Rate Limiting**: Prevent resource exhaustion

### Limits

- Maximum 50 concurrent streams (configurable)
- 5-minute default timeout per stream
- 100-tick buffer per stream
- Client connection timeout handling

## Security Considerations

### Authentication

- No authentication required for initial implementation
- Future: API key authentication for production deployment
- Rate limiting by IP address to prevent abuse

### Network Security

- Bind to localhost by default
- CORS headers for browser access
- Input validation on all parameters
- Sanitized error messages

## Deployment

### Development

```bash
cd ib-stream/
pip install -e .[dev]
uvicorn ib_stream.api_server:app --reload --host 127.0.0.1 --port 8000
```

### Production

```bash
# Docker deployment
docker build -t ib-stream-api .
docker run -p 8000:8000 -e IB_STREAM_CLIENT_ID=2 ib-stream-api

# Direct deployment
uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8000 --workers 1
```

### Health Monitoring

- Health check endpoint: `GET /health`
- Metrics: Active streams, TWS connection status, error rates
- Logging: Structured JSON logs with request tracing

## Implementation Phases

### Phase 1: Core SSE Streaming
- Basic SSE endpoint implementation
- Single contract streaming
- Essential error handling

### Phase 2: Stream Management
- Multiple client support
- Stream lifecycle management
- Health and management endpoints

### Phase 3: Production Readiness
- Performance optimization
- Comprehensive error handling
- Monitoring and observability

## Examples

### JavaScript Client (Browser)

```javascript
const eventSource = new EventSource('http://localhost:8000/stream/265598?tick_type=BidAsk&limit=100');

eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    if (data.type === 'tick') {
        console.log('Bid:', data.data.bid_price, 'Ask:', data.data.ask_price);
    } else if (data.type === 'error') {
        console.error('Stream error:', data.error.message);
    } else if (data.type === 'complete') {
        console.log('Stream completed:', data.reason);
        eventSource.close();
    }
};

eventSource.onerror = function(event) {
    console.error('Connection error:', event);
};
```

### Python Client

```python
import requests
import json

url = "http://localhost:8000/stream/265598"
params = {"tick_type": "BidAsk", "limit": 100}

with requests.get(url, params=params, stream=True) as response:
    for line in response.iter_lines():
        if line.startswith(b'data: '):
            data = json.loads(line[6:])  # Remove 'data: ' prefix
            if data['type'] == 'tick':
                print(f"Bid: {data['data']['bid_price']}, Ask: {data['data']['ask_price']}")
            elif data['type'] == 'error':
                print(f"Error: {data['error']['message']}")
                break
            elif data['type'] == 'complete':
                print(f"Stream completed: {data['reason']}")
                break
```

This specification provides a comprehensive blueprint for implementing a production-ready streaming market data API server using SSE as the primary delivery mechanism.