# Unified Connection Architecture Plan

## 🎯 **Objective**
Simplify IB Stream architecture from multiple connections/client IDs to a single unified connection that handles all streaming needs.

## 📋 **Current State Analysis**

### Current Architecture Issues:
- **Dual Connections**: Main service + Background streaming each create separate IB connections
- **Client ID Complexity**: Main uses 101/851, Background uses 1101/1851 (+1000 offset)
- **Resource Redundancy**: Two `StreamingApp` instances, two `IBConnection` instances
- **Configuration Overhead**: Separate client ID management and offset calculations
- **Recovery Complexity**: Two independent recovery systems

### Current Flow:
```
app_lifecycle.py:
├── ensure_tws_connection() → StreamingApp(client_id=101) → IBConnection
└── BackgroundStreamManager() → StreamingApp(client_id=1101) → IBConnection

Result: 2 connections, 2 client IDs, 2 recovery systems
```

## 🏗️ **Target Architecture**

### Unified Flow:
```
app_lifecycle.py:
├── UnifiedConnectionManager(client_id=101) → Single IBConnection
├── ensure_tws_connection() → Reuse shared connection
└── BackgroundStreamManager() → Reuse shared connection

Result: 1 connection, 1 client ID, 1 recovery system
```

### Key Principles:
1. **Single Source of Truth**: One connection manager owns the IB connection
2. **Request ID Separation**: Keep existing request ID ranges for isolation
3. **Shared Recovery**: Unified reconnection logic restarts all streams
4. **Backward Compatibility**: Existing API endpoints work unchanged

## 📝 **Implementation Phases**

### Phase 1: Core Infrastructure (Foundation)
**Goal**: Create unified connection management without breaking existing functionality

**Tasks:**
1. **Create `UnifiedConnectionManager`**
   - Single `IBConnection` instance
   - Shared across all streaming needs
   - Centralized connection state management
   - Request ID registry for all active streams

2. **Design Stream Registry**
   - Track all active streams (background + client)
   - Map request IDs to stream types and callbacks
   - Enable bulk stream restart on reconnection

### Phase 2: Background Integration (Low Risk)  
**Goal**: Migrate background streaming to use shared connection

**Tasks:**
1. **Modify `BackgroundStreamManager`**
   - Accept `connection_manager` parameter instead of creating own connection
   - Remove client ID offset logic (+1000)
   - Use shared connection for all `reqTickByTickData()` calls
   - Keep existing request ID ranges (60000+)

2. **Update `app_lifecycle.py`**
   - Create `UnifiedConnectionManager` early in startup
   - Pass shared connection to `BackgroundStreamManager`
   - Remove dual connection initialization

### Phase 3: Client Integration (Medium Risk)
**Goal**: Migrate client streaming to use shared connection

**Tasks:**
1. **Update `ensure_tws_connection()`**
   - Return shared connection instead of creating new `StreamingApp`
   - Modify to use `UnifiedConnectionManager`
   - Maintain same interface for backward compatibility

2. **Modify Client Stream Endpoints**
   - Update streaming endpoints to use shared connection
   - Keep existing request ID ranges (1000-59999)
   - Maintain API compatibility

### Phase 4: Enhanced Recovery (Optimization)
**Goal**: Improve recovery system for unified architecture

**Tasks:**
1. **Unified Stream Recovery**
   - Single reconnection handler for all stream types
   - Bulk stream restart on connection loss
   - Enhanced monitoring and health checks

2. **Remove Legacy Code**
   - Delete dual connection logic
   - Remove client ID offset calculations
   - Clean up redundant configuration

### Phase 5: Testing & Validation (Safety)
**Goal**: Ensure stability and performance

**Tasks:**
1. **Comprehensive Testing**
   - Test background streaming continuity
   - Test client streaming functionality  
   - Test connection recovery scenarios
   - Performance benchmarking

## 🔧 **Technical Implementation Details**

### UnifiedConnectionManager Class Design:

```python
class UnifiedConnectionManager:
    """Single connection manager for all IB streaming needs"""
    
    def __init__(self, config):
        self.config = config
        self.connection = None  # IBConnection instance
        self.stream_registry = {}  # request_id -> stream_info
        self.connection_callbacks = []  # Notification callbacks
        self.recovery_state = "healthy"
        
    async def ensure_connection(self) -> IBConnection:
        """Ensure connection is established, create if needed"""
        if self.connection is None or not self.connection.is_connected():
            await self._establish_connection()
        return self.connection
    
    def register_stream(self, request_id: int, stream_type: str, callback: callable):
        """Register a stream for recovery tracking"""
        self.stream_registry[request_id] = {
            "type": stream_type,
            "callback": callback,
            "created_at": datetime.now()
        }
    
    async def recovery_restart_all_streams(self):
        """Restart all registered streams after reconnection"""
        for request_id, stream_info in self.stream_registry.items():
            try:
                await stream_info["callback"](request_id)
            except Exception as e:
                logger.error("Failed to restart stream %d: %s", request_id, e)
```

### Request ID Allocation Strategy:

```python
# UNCHANGED - Keep existing ranges for compatibility
REQUEST_ID_RANGES = {
    "client_streams": (1000, 59999),      # Client API requests
    "background_streams": (60000, 69999), # Background data collection
    "reserved": (70000, 99999)            # Future use
}
```

### Connection State Management:

```python
class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting" 
    CONNECTED = "connected"
    RECOVERING = "recovering"
    FAILED = "failed"
```

## ⚡ **Migration Strategy**

### Step-by-Step Migration:

1. **Create Foundation** (Non-breaking)
   - Implement `UnifiedConnectionManager`
   - Add to existing `app_lifecycle.py` alongside current connections
   - Test in isolation

2. **Migrate Background First** (Lower risk)
   - Background streams are internal-only
   - Less user-facing impact
   - Easier to test and validate

3. **Migrate Client Streams** (Higher impact)
   - User-facing API endpoints
   - Requires careful testing
   - Rollback plan ready

4. **Clean Up Legacy** (Final phase)
   - Remove old connection code
   - Update documentation
   - Performance optimization

### Rollback Strategy:
- Each phase can be independently reverted
- Configuration flags to enable/disable unified mode
- Parallel connection testing during migration

## 📊 **Success Metrics**

### Performance Improvements:
- **Memory Usage**: ~50% reduction (eliminate duplicate connections)
- **Startup Time**: Faster (single connection establishment)
- **Recovery Time**: Improved (unified recovery logic)
- **Resource Utilization**: Lower (fewer threads, sockets)

### Operational Benefits:
- **Simplified Monitoring**: One connection state to track
- **Easier Debugging**: Single connection path
- **Reduced Configuration**: No client ID offset management
- **Better Reliability**: Consolidated recovery logic

### Risk Mitigation:
- **Gradual Migration**: Phase-by-phase approach
- **Extensive Testing**: Each phase thoroughly tested
- **Rollback Capability**: Can revert to dual connections
- **Monitoring**: Enhanced logging during transition

## 🔍 **Testing Strategy**

### Unit Tests:
- `UnifiedConnectionManager` class methods
- Stream registry functionality
- Request ID allocation
- Recovery scenarios

### Integration Tests:
- Background streaming continuity
- Client stream functionality
- Connection recovery
- Multi-contract streaming

### Load Tests:
- Multiple concurrent streams
- Connection stability under load
- Recovery performance
- Memory usage validation

### Production Tests:
- Canary deployment approach
- A/B testing between architectures
- Real market data validation
- Performance monitoring

## 📅 **Timeline Estimate**

### Phase 1 (Foundation): 2-3 days
- Design and implement core classes
- Unit tests and basic validation

### Phase 2 (Background Integration): 1-2 days  
- Modify background streaming
- Integration testing

### Phase 3 (Client Integration): 2-3 days
- Update client endpoints
- API compatibility testing

### Phase 4 (Enhanced Recovery): 1-2 days
- Implement unified recovery
- Recovery scenario testing

### Phase 5 (Testing & Cleanup): 2-3 days
- Comprehensive testing
- Performance validation
- Code cleanup

**Total Estimate: 8-13 days**

## 🚀 **Getting Started**

### Immediate Next Steps:
1. Create `UnifiedConnectionManager` class
2. Implement basic connection management
3. Add stream registry functionality
4. Create unit tests for core functionality
5. Begin background manager integration

### Files to Modify:
- `ib-stream/src/ib_stream/connection/` (new directory)
- `ib-stream/src/ib_stream/app_lifecycle.py`
- `ib-stream/src/ib_stream/background_stream_manager.py`
- `ib-stream/src/ib_stream/api_server.py`
- Configuration files (remove background client ID settings)

This plan provides a systematic approach to simplifying the architecture while maintaining stability and backward compatibility.