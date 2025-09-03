# IB Stream Architecture v3: Service Composition Pattern

## Overview
This architecture separates the IB API/background streaming services from the FastAPI web server while enabling composition and interaction through well-defined interfaces.

## Core Principles

### 1. Single Configuration Instance
- **One config load per process**: Configuration loaded once and passed to all services
- **Dependency injection pattern**: Services receive config rather than loading it themselves
- **Immutable config**: Configuration becomes read-only after initial load

### 2. Service Independence  
- **IB Service**: Manages IB API connections and background streaming independently
- **Web Service**: Provides HTTP API endpoints without managing IB lifecycle
- **Storage Service**: Handles data persistence as a separate concern
- **Each service can start/stop independently**

### 3. Service Composition
- **Service Registry**: Central registry for inter-service communication
- **Event Bus**: Services communicate through events, not direct coupling
- **Status Interfaces**: Well-defined APIs for health checks and status queries

## Architecture Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     Service Orchestrator                        │
│  - Single config load                                          │
│  - Service lifecycle management                                │  
│  - Event bus coordination                                      │
└─────────────────────────────────────────────────────────────────┘
              │                  │                  │
              │                  │                  │
    ┌─────────▼─────────┐ ┌─────▼─────┐ ┌──────────▼──────────┐
    │   IB Service      │ │Web Service│ │  Storage Service    │
    │                   │ │           │ │                     │
    │ - IB API mgmt     │ │ - FastAPI │ │ - MultiStorageV3    │
    │ - Background      │ │ - HTTP    │ │ - File/DB writes    │
    │   streaming       │ │   endpoints│ │ - Data archival     │
    │ - Auto-recovery   │ │ - Health  │ │                     │
    │ - Connection mgmt │ │   checks  │ │                     │
    └───────────────────┘ └───────────┘ └─────────────────────┘
```

## Service Definitions

### IB Service (`ib_service.py`)
**Responsibility**: Manage all IB API interactions and background streaming
**Independence**: Can run without web server
**Interface**: Status queries, stream management, health monitoring

```python
class IBService:
    def __init__(self, config: ServerConfig, event_bus: EventBus):
        self.config = config  # Injected, not loaded
        self.connection_manager = UnifiedConnectionManager(config)
        self.background_manager = None
        self.event_bus = event_bus
    
    async def start(self) -> None:
        """Start IB connections and background streaming"""
        
    async def stop(self) -> None:
        """Clean shutdown of all IB connections"""
        
    def get_status(self) -> IBServiceStatus:
        """Return current service status (for web API queries)"""
        
    def get_streaming_app(self) -> Optional[StreamingApp]:
        """Provide StreamingApp for client requests"""
```

### Web Service (`web_service.py`)
**Responsibility**: HTTP API endpoints and request routing
**Independence**: Can run without IB service (degraded mode)
**Interface**: HTTP endpoints, service status aggregation

```python
class WebService:
    def __init__(self, config: ServerConfig, service_registry: ServiceRegistry):
        self.config = config  # Injected, not loaded
        self.service_registry = service_registry
        self.app = FastAPI()
    
    async def start(self) -> None:
        """Start FastAPI server"""
        
    async def stop(self) -> None:
        """Shutdown HTTP server"""
        
    def get_ib_service_status(self) -> dict:
        """Query IB service status through registry"""
```

### Storage Service (`storage_service.py`)
**Responsibility**: Data persistence and archival
**Independence**: Can run independently for batch processing
**Interface**: Write operations, storage health

```python
class StorageService:
    def __init__(self, config: ServerConfig, event_bus: EventBus):
        self.config = config  # Injected, not loaded
        self.storage = MultiStorageV3(...)
        self.event_bus = event_bus
    
    async def start(self) -> None:
        """Initialize storage systems"""
        
    async def stop(self) -> None:
        """Flush and close storage"""
```

## Service Orchestrator

**Responsibility**: Single point of configuration loading and service coordination

```python
class ServiceOrchestrator:
    def __init__(self):
        self.config: Optional[ServerConfig] = None
        self.services: Dict[str, Any] = {}
        self.event_bus = EventBus()
        self.service_registry = ServiceRegistry()
    
    async def start(self, services_to_start: List[str] = None):
        """Start specified services or all services"""
        # Load config exactly once
        self.config = create_config()
        
        # Start services in dependency order
        if 'storage' in services_to_start:
            await self._start_storage_service()
        if 'ib' in services_to_start:
            await self._start_ib_service()
        if 'web' in services_to_start:
            await self._start_web_service()
    
    async def stop(self):
        """Stop all services in reverse dependency order"""
```

## Benefits

### 1. Configuration Efficiency
- **Single config load**: `create_config()` called exactly once per process
- **Zero config redundancy**: All services receive injected configuration
- **Faster startup**: No redundant file I/O or environment variable parsing

### 2. Service Independence
- **Background streaming only**: `orchestrator.start(['ib', 'storage'])`
- **Web API only**: `orchestrator.start(['web'])`
- **Full system**: `orchestrator.start(['ib', 'storage', 'web'])`

### 3. Clean Separation
- **IB API lifecycle**: Managed by IB Service, not FastAPI lifespan
- **Storage lifecycle**: Independent service with its own lifecycle  
- **Web server lifecycle**: Only manages HTTP concerns

### 4. Better Testing
- **Unit tests**: Each service can be tested independently
- **Integration tests**: Services can be composed as needed
- **Mock interfaces**: Services communicate through well-defined interfaces

### 5. Production Flexibility
- **Horizontal scaling**: Run IB service on one server, web service on another
- **Maintenance**: Restart web server without affecting data collection
- **Debugging**: Run background streaming standalone for investigation

## Migration Strategy

### Phase 1: Extract IB Service
1. Create `IBService` class with injected config
2. Move `UnifiedConnectionManager` and `BackgroundStreamManager` into `IBService`  
3. Create `ServiceRegistry` for status queries

### Phase 2: Extract Storage Service
1. Create `StorageService` class with injected config
2. Move `MultiStorageV3` lifecycle into `StorageService`
3. Use event bus for data flow from IB Service to Storage Service

### Phase 3: Create Service Orchestrator
1. Create `ServiceOrchestrator` with single config loading
2. Modify existing entry points to use orchestrator
3. Remove config loading from individual services

### Phase 4: Update FastAPI Integration
1. Modify FastAPI lifespan to only start `WebService`
2. Use `ServiceRegistry` for cross-service status queries  
3. Remove IB API lifecycle management from FastAPI

## Entry Points

### Background Streaming Only
```python
# standalone_streaming.py
orchestrator = ServiceOrchestrator()
await orchestrator.start(['storage', 'ib'])
# Runs indefinitely, no web server
```

### Web Server Only (Development)
```python
# web_only.py  
orchestrator = ServiceOrchestrator()
await orchestrator.start(['web'])
# HTTP API available, but IB calls return 503
```

### Full Production System
```python
# production.py
orchestrator = ServiceOrchestrator()
await orchestrator.start(['storage', 'ib', 'web'])
# All services running
```

### FastAPI Integration (Backward Compatible)
```python
@asynccontextmanager
async def lifespan(_):
    orchestrator = ServiceOrchestrator()
    await orchestrator.start(['storage', 'ib'])  # No web service (FastAPI handles that)
    yield
    await orchestrator.stop()

app = FastAPI(lifespan=lifespan)
```

## Configuration Simplification

**Before (Multiple Loads):**
```python
# app_lifecycle.py
config = create_config()  # Load 1

# get_app_state() 
config = create_config()  # Load 2

# background_stream_manager.py
config = create_config()  # Load 3

# stream.py
config = create_config()  # Load 4
```

**After (Single Load):**
```python
# service_orchestrator.py
orchestrator = ServiceOrchestrator()
config = create_config()  # ONLY load

# All services receive config via dependency injection
ib_service = IBService(config=config, event_bus=event_bus)
web_service = WebService(config=config, service_registry=registry)
storage_service = StorageService(config=config, event_bus=event_bus)
```

This architecture achieves the user's goals:
1. ✅ **No multiple config loads** - Single configuration instance
2. ✅ **Ordered startup** - Clear service dependency chains  
3. ✅ **Separation of concerns** - Independent service lifecycles
4. ✅ **Composition** - Services can be mixed and matched
5. ✅ **Independent background streaming** - Can run without FastAPI
6. ✅ **Status query interface** - Web service can query IB service status without tight coupling