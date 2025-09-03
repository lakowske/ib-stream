# Service Composition Architecture Migration Guide

## Overview

This guide outlines how to migrate from the existing unified architecture to the new **Service Composition Architecture** with single configuration loading and clean service separation.

## Migration Path Summary

### ✅ Phase 1: Foundation (COMPLETED)
- [x] Service Orchestration infrastructure created
- [x] Event bus and service registry implemented  
- [x] Independent IB and Storage services developed
- [x] Service Composition FastAPI integration (app_v3.py)
- [x] Updated debug_runner.py with service orchestration

### 🔄 Phase 2: Integration (IN PROGRESS)
- [x] FastAPI health endpoints connected to ServiceRegistry
- [x] Service Composition lifespan management
- [ ] Migrate existing endpoints to use ServiceRegistry
- [ ] Update production deployment scripts

### 🔄 Phase 3: Full Migration (NEXT STEPS)
- [ ] Replace unified_app.py with app_v3.py in production
- [ ] Update supervisor configurations
- [ ] Migrate existing tests
- [ ] Documentation updates

## Current Architecture Status

### ✅ **Completed Components**

**Core Infrastructure:**
- `ServiceOrchestrator` - Single config load, service coordination
- `EventBus` - Decoupled inter-service communication
- `ServiceRegistry` - Service discovery and status tracking
- `IBService` - Independent IB API and background streaming
- `StorageService` - Independent data persistence

**FastAPI Integration:**
- `app_v3.py` - Service Composition FastAPI app
- Health endpoints using ServiceRegistry instead of global state
- Flexible orchestrator integration (can use existing or create new)

**Entry Points:**
- `debug_runner.py` - Multi-mode service runner (debug/standalone/production)
- `production_runner.py` - Production deployment wrapper

## Usage Examples

### Development & Debugging

```bash
cd ib-stream
source ../.venv/bin/activate

# Background streaming only (no web server)
python debug_runner.py standalone
# ✅ IB Service: Running independently
# ✅ Storage Service: Running independently  
# ✅ Background Streaming: Active
# ✅ No web server (headless operation)

# Debug with web server
python debug_runner.py debug
# ✅ IB Service: Independent lifecycle
# ✅ Storage Service: Independent lifecycle
# ✅ Web Server: FastAPI on http://0.0.0.0:8774
# ✅ Single configuration load
# ✅ Clean service separation

# Production mode
python debug_runner.py production
# ✅ All services running
# ✅ Optimized for production use
```

### Health Monitoring (New Service Registry Pattern)

```bash
# Comprehensive health check
curl -s http://localhost:8774/health | jq .
{
  "status": "healthy",
  "architecture": "service_composition",
  "config_loads": 1,
  "services": {
    "ib_service": {"status": "healthy", "connection_healthy": true},
    "storage_service": {"status": "healthy", "enabled": true},
    "web_service": {"status": "healthy", "endpoints": "active"}
  },
  "service_registry": {
    "registered_services": ["ib_service", "storage_service"],
    "total_services": 2
  }
}

# Detailed service status
curl -s http://localhost:8774/health/detailed | jq .

# Individual service health
curl -s http://localhost:8774/services/ib_service/health | jq .

# All service status
curl -s http://localhost:8774/services/status | jq .
```

## Migration Benefits

### **Configuration Efficiency**

**Before (Multiple Config Loads):**
```python
# app_lifecycle.py
config = create_config()  # Load 1

# get_app_state()
if config is None:
    config = create_config()  # Load 2

# background_stream_manager.py  
if self.config is None:
    config = create_config()  # Load 3

# stream.py
config = create_config()  # Load 4

# ws_manager.py
config = create_config()  # Load 5
```

**After (Single Config Load):**
```python
# ServiceOrchestrator
orchestrator = ServiceOrchestrator()
config = create_config()  # ONLY LOAD!

# All services receive config via dependency injection
ib_service = IBService(config=config, event_bus=event_bus)
storage_service = StorageService(config=config, event_bus=event_bus)
```

### **Service Independence**

**Before:** FastAPI managed IB API lifecycle
```python
@asynccontextmanager
async def lifespan(_):
    # FastAPI creates and manages IB connections
    unified_connection_manager = UnifiedConnectionManager(...)
    await unified_connection_manager.start()
    # Background streaming tied to FastAPI lifecycle
```

**After:** Independent service lifecycles
```python
# IB Service runs independently
orchestrator.start(['ib', 'storage'])  # No web server needed

# FastAPI uses existing services
app = create_service_composition_app(existing_orchestrator=orchestrator)
```

### **Clean Service Communication**

**Before:** Global state and direct coupling
```python
# Global variables shared between components
global config, unified_connection_manager, storage, background_manager

def ensure_tws_connection():
    global unified_connection_manager  # Direct global state access
```

**After:** ServiceRegistry communication  
```python
# Clean service registry queries
orchestrator = app.state.orchestrator
ib_service = orchestrator.get_ib_service()
streaming_app = ib_service.get_streaming_app()
```

## Step-by-Step Migration

### Step 1: Update Entry Points

**Current supervisor config:**
```ini
[program:ib-stream-production]
command=uvicorn ib_stream.unified_app:app --host 0.0.0.0 --port 8851
```

**New supervisor config:**
```ini
[program:ib-stream-production]
command=python production_runner.py full
directory=/path/to/ib-stream-1/ib-stream
```

### Step 2: Migrate Health Endpoints

**Replace old health endpoints** that use global state:
```python
# OLD: app_lifecycle.py global state
def ensure_tws_connection():
    global unified_connection_manager
    if unified_connection_manager is None:
        raise HTTPException(status_code=503, detail=msg)
```

**With new ServiceRegistry queries:**
```python
# NEW: Service Composition pattern
@app.get("/health")
async def health_check():
    orchestrator = app.state.orchestrator
    ib_service = orchestrator.get_ib_service()
    return {"status": "healthy" if ib_service.is_connection_healthy() else "degraded"}
```

### Step 3: Update Streaming Endpoints

**Replace direct StreamingApp access:**
```python  
# OLD: Global state access
def ensure_tws_connection() -> StreamingApp:
    global unified_connection_manager
    return unified_connection_manager.streaming_app
```

**With service registry access:**
```python
# NEW: Service registry access
ib_service = app.state.orchestrator.get_ib_service()
streaming_app = ib_service.get_streaming_app()
```

### Step 4: Production Deployment

**Update deployment scripts to use the new entry points:**

```bash
# Production deployment
cd ib-stream
python production_runner.py full

# Development/debugging  
python debug_runner.py debug

# Background streaming only
python debug_runner.py standalone
```

## Testing Migration

### Test Service Orchestration
```bash
python test_service_orchestration.py
# ✅ All 3 tests passed!
# 🎉 Service Orchestration Pattern is working correctly!
```

### Test FastAPI Integration
```bash
source .venv/bin/activate
python test_service_composition_app.py
# Tests Service Composition FastAPI integration
```

### Test Debug Runner Modes
```bash
cd ib-stream
source ../.venv/bin/activate

# Validate runner setup
python ../validate_debug_runner.py

# Test modes (with dependencies available)
python debug_runner.py standalone  # Background streaming only
python debug_runner.py debug       # Full debug setup
```

## Rollback Plan

If issues arise during migration, you can rollback:

**Revert to unified_app.py:**
```python
# In supervisor or production scripts
# OLD: python production_runner.py full  
# ROLLBACK: uvicorn ib_stream.unified_app:app --host 0.0.0.0 --port 8851
```

**Revert debug_runner.py:**
```bash
# Use git to revert debug_runner.py to previous version if needed
git checkout HEAD~1 -- ib-stream/debug_runner.py
```

## Benefits Summary

### ✅ **Achieved**
- **Single Configuration Load**: Eliminated 5+ redundant `create_config()` calls
- **Service Independence**: Background streaming runs without FastAPI  
- **Clean Separation**: Services have independent lifecycles
- **Ordered Startup**: Proper dependency management
- **Flexible Deployment**: Services can be composed based on needs

### 🎯 **Production Ready**
- Consistent entry points for debug and production
- Comprehensive health monitoring through ServiceRegistry
- Clean service boundaries with event communication
- Horizontal scaling potential (services on different servers)
- Maintenance flexibility (restart services independently)

### 📊 **Performance**
- Reduced configuration loading time
- Eliminated redundant service initialization
- Better resource utilization
- Faster startup times

## Next Actions

1. **Test with Real IB Gateway**: Validate full integration
2. **Update Production Scripts**: Switch supervisor to use `production_runner.py`
3. **Migrate Remaining Endpoints**: Update other endpoints to use ServiceRegistry
4. **Documentation**: Update API documentation with new architecture
5. **Monitoring**: Implement service-level monitoring dashboards

The Service Composition Architecture provides a **solid foundation** for scalable, maintainable, and efficient service deployment while maintaining all existing functionality.