# IB-Stream v2 Refactoring Plan

## Executive Summary

This document outlines the implementation plan for refactoring IB-Stream to align with the v2 protocol specification. The refactoring will be executed in three phases, prioritizing high-impact changes while maintaining backward compatibility.

## Goals

1. **Unify Protocol**: Implement consistent message format across SSE and WebSocket
2. **Standardize Naming**: Adopt snake_case and consistent field names
3. **Improve Developer Experience**: Reduce complexity for client implementations
4. **Maintain Compatibility**: Provide smooth migration path from v1

## Implementation Phases

### Phase 1: High Priority - Core Protocol Standardization (2-3 weeks)

#### 1.1 Unified Stream Identification

**Current State:**
- SSE uses `contract_id` directly
- WebSocket uses `request_id`
- No consistent stream identification

**Changes Required:**

1. **Create Stream ID Generator** (`ib_stream/utils/stream_id.py`):
```python
def generate_stream_id(contract_id: int, tick_type: str) -> str:
    """Generate unique stream identifier."""
    timestamp = int(time.time() * 1000)
    random_suffix = random.randint(1000, 9999)
    return f"{contract_id}_{tick_type}_{timestamp}_{random_suffix}"
```

2. **Update SSE Response Classes** (`ib_stream/sse_response.py`):
- Add `stream_id` to all event classes
- Maintain `contract_id` for v1 compatibility
- Update `format()` method to use new structure

3. **Update WebSocket Schemas** (`ib_stream/ws_schemas.py`):
- Replace `request_id` with `stream_id` in all messages
- Update validation schemas
- Add backward compatibility mapping

#### 1.2 Standardize Error Structure

**Files to Modify:**
- `ib_stream/sse_response.py`: Update `SSEErrorEvent`
- `ib_stream/ws_schemas.py`: Update `ErrorMessage`
- Create `ib_stream/errors.py` for unified error definitions

**New Error Structure:**
```python
class UnifiedError:
    def __init__(self, code: str, message: str, details: dict = None, 
                 recoverable: bool = True):
        self.code = code
        self.message = message
        self.details = details or {}
        self.recoverable = recoverable
```

#### 1.3 Consistent Field Naming

**Snake_case Migration:**
1. Create field mapping dictionary for backward compatibility
2. Update all message classes to use snake_case
3. Add conversion utilities for v1 clients

**Files to Update:**
- All message classes in `sse_response.py` and `ws_schemas.py`
- Stream handlers in `stream_manager.py`
- Client examples and documentation

### Phase 2: Medium Priority - Feature Alignment (2 weeks)

#### 2.1 Multi-Stream Harmonization

**Current Issues:**
- SSE doesn't truly support multi-stream
- WebSocket has complex multi-subscribe protocol

**Implementation:**

1. **SSE Enhancement** (`api_server.py`):
```python
@app.get("/v2/stream/{contract_id}")
async def stream_v2_multi(
    contract_id: int,
    tick_types: str = Query(...),  # comma-separated
    limit: Optional[int] = None,
    timeout: Optional[int] = None
):
    # Parse tick types and create unified stream
    types = tick_types.split(',')
    stream_id = generate_multi_stream_id(contract_id, types)
    # Return multi-type stream with clear type identification
```

2. **WebSocket Simplification**:
- Support both individual and batch subscriptions
- Use consistent stream_id format
- Simplify response structure

#### 2.2 Completion Message Standardization

**Changes:**
- Add duration to SSE completion events
- Nest completion data consistently
- Include final sequence number

**Files:**
- `sse_response.py`: Update `SSECompleteEvent`
- `ws_schemas.py`: Align `CompleteMessage`

#### 2.3 Timestamp Unification

**Implementation:**
- Use single ISO-8601 timestamp field
- Remove redundant timestamp fields
- Add utility for timestamp formatting

### Phase 3: Low Priority - Enhanced Features (1-2 weeks)

#### 3.1 SSE Control Features

**Planned Additions:**
1. **Metadata Endpoint**:
```python
@app.get("/v2/stream/{stream_id}/info")
async def get_stream_info(stream_id: str):
    # Return current stream status and configuration
```

2. **Stream Management**:
- Add DELETE endpoint for stopping specific streams
- Implement stream pause/resume via headers

#### 3.2 Protocol Parity

**Remaining Gaps:**
- Add heartbeat events to SSE
- Implement stream statistics
- Enhanced error recovery

## Code Changes by Module

### 1. Core Message Classes

**Create `ib_stream/protocol/messages.py`:**
```python
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional

class BaseMessage(ABC):
    """Base class for all protocol messages."""
    
    def __init__(self, message_type: str, stream_id: str, 
                 data: Dict[str, Any], metadata: Optional[Dict] = None):
        self.type = message_type
        self.stream_id = stream_id
        self.timestamp = datetime.utcnow().isoformat() + 'Z'
        self.data = data
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        result = {
            "type": self.type,
            "stream_id": self.stream_id,
            "timestamp": self.timestamp,
            "data": self.data
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @abstractmethod
    def to_v1_format(self) -> Dict[str, Any]:
        """Convert to v1 format for backward compatibility."""
        pass
```

### 2. Update Stream Manager

**Modifications to `stream_manager.py`:**
1. Use new message classes
2. Generate stream IDs consistently
3. Add v1/v2 routing logic

### 3. API Versioning

**Create `ib_stream/api/v2/endpoints.py`:**
- New v2 endpoints with consistent behavior
- Version negotiation middleware
- Backward compatibility layer

### 4. WebSocket Manager Updates

**Changes to `ws_manager.py`:**
1. Support v2 message format
2. Add version negotiation in handshake
3. Implement v1 compatibility mode

## Testing Strategy

### 1. Unit Tests

**New Test Files:**
- `tests/test_protocol_messages.py`
- `tests/test_stream_id_generation.py`
- `tests/test_v1_compatibility.py`

**Test Coverage:**
- Message serialization/deserialization
- Field mapping correctness
- Error handling
- Stream ID uniqueness

### 2. Integration Tests

**Test Scenarios:**
1. v1 client → v2 server
2. v2 client → v2 server
3. Mixed v1/v2 clients
4. Multi-stream scenarios
5. Error recovery

### 3. Performance Tests

**Benchmarks:**
- Message throughput comparison
- Memory usage with new structure
- Latency impact of field mapping

## Migration Guide

### 1. Server Deployment

**Deployment Steps:**
1. Deploy v2 code with v1 compatibility
2. Monitor v1 endpoint usage
3. Gradually migrate clients to v2
4. Deprecate v1 after migration period

### 2. Client Migration

**Client Update Path:**
1. Update to v2-compatible client library
2. Test with v1 endpoints
3. Switch to v2 endpoints
4. Remove v1 compatibility code

### 3. Breaking Changes

**Minimal Breaking Changes:**
- Field name changes (handled by compatibility layer)
- Message structure (dual-format support)
- Stream identification (backward compatible)

## Rollback Plan

### 1. Feature Flags

```python
class FeatureFlags:
    USE_V2_PROTOCOL = os.getenv("IB_STREAM_V2_PROTOCOL", "false") == "true"
    V1_COMPATIBILITY = os.getenv("IB_STREAM_V1_COMPAT", "true") == "true"
```

### 2. Gradual Rollout

1. Deploy with v2 disabled
2. Enable v2 for specific clients
3. Monitor metrics and errors
4. Full rollout or rollback

## Monitoring and Metrics

### 1. Key Metrics

- Protocol version usage (v1 vs v2)
- Error rates by version
- Message throughput
- Client compatibility issues

### 2. Logging Updates

```python
logger.info("Stream created", extra={
    "stream_id": stream_id,
    "protocol_version": "v2",
    "transport": "websocket",
    "tick_types": tick_types
})
```

## Timeline and Milestones

### Week 1-2: Phase 1 Core Changes
- [ ] Stream ID implementation
- [ ] Error structure standardization
- [ ] Field naming consistency

### Week 3-4: Phase 1 Testing & Integration
- [ ] Unit test implementation
- [ ] Integration testing
- [ ] v1 compatibility verification

### Week 5-6: Phase 2 Implementation
- [ ] Multi-stream harmonization
- [ ] Completion message updates
- [ ] Timestamp unification

### Week 7: Phase 3 & Polish
- [ ] SSE control features
- [ ] Documentation updates
- [ ] Client library updates

### Week 8: Deployment & Monitoring
- [ ] Staged deployment
- [ ] Monitor metrics
- [ ] Address issues

## Risk Assessment

### Technical Risks

1. **Backward Compatibility**: Mitigated by dual-format support
2. **Performance Impact**: Mitigated by efficient field mapping
3. **Client Confusion**: Mitigated by clear migration guide

### Operational Risks

1. **Deployment Issues**: Mitigated by feature flags
2. **Rollback Complexity**: Mitigated by gradual rollout
3. **Support Burden**: Mitigated by comprehensive documentation

## Success Criteria

1. **Zero v1 Client Breakage**: All existing clients continue working
2. **Improved Developer Experience**: Measured by client feedback
3. **Performance Neutral**: No degradation in latency or throughput
4. **90% v2 Adoption**: Within 3 months of release

## Appendix: File Change Summary

### Files to Create
- `ib_stream/protocol/messages.py`
- `ib_stream/protocol/errors.py`
- `ib_stream/utils/stream_id.py`
- `ib_stream/api/v2/endpoints.py`
- `tests/test_protocol_messages.py`
- `tests/test_v1_compatibility.py`

### Files to Modify
- `ib_stream/sse_response.py`
- `ib_stream/ws_schemas.py`
- `ib_stream/ws_manager.py`
- `ib_stream/stream_manager.py`
- `ib_stream/api_server.py`

### Documentation Updates
- Update API documentation
- Create migration guide
- Update client examples
- Add v2 protocol reference