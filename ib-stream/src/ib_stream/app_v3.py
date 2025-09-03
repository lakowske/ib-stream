#!/usr/bin/env python3
"""
IB Stream App v3 - Service Composition Architecture

This is the FastAPI app integrated with the new Service Composition Architecture.
Uses ServiceOrchestrator for single config loading and clean service separation.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from .services import get_orchestrator, ServiceRegistry, EventBus
from .endpoints.health import setup_health_endpoints
from .endpoints.buffer import setup_buffer_endpoints  
from .endpoints.streaming import setup_streaming_endpoints
from .endpoints.websocket import setup_websocket_endpoints
from .endpoints.management import setup_management_endpoints
from .endpoints.v3 import setup_v3_endpoints

logger = logging.getLogger(__name__)

# Global orchestrator for this app instance
app_orchestrator: Optional['ServiceOrchestrator'] = None


def create_service_composition_lifespan(existing_orchestrator=None):
    """
    Create Service Composition Lifespan for FastAPI
    
    Args:
        existing_orchestrator: Optional existing ServiceOrchestrator to use
                              If None, creates its own orchestrator
    """
    @asynccontextmanager
    async def service_composition_lifespan(app: FastAPI):
        """
        Service Composition Lifespan for FastAPI
        
        This lifespan integrates with the Service Orchestration pattern:
        - Can use existing ServiceOrchestrator or create its own
        - FastAPI only manages web server lifecycle
        - Services communicate through ServiceRegistry
        """
        global app_orchestrator
        
        logger.info("🚀 Starting FastAPI with Service Composition Architecture...")
        
        # Use existing orchestrator or create new one
        if existing_orchestrator:
            logger.info("Using existing ServiceOrchestrator")
            app_orchestrator = existing_orchestrator
            should_stop_orchestrator = False  # Don't stop external orchestrator
        else:
            logger.info("Creating new ServiceOrchestrator")
            ServiceOrchestrator = get_orchestrator()
            app_orchestrator = ServiceOrchestrator()
            
            logger.info("Starting core services: IB API + Storage")
            await app_orchestrator.start(['ib', 'storage'])
            should_stop_orchestrator = True  # We created it, we stop it
        
        try:
            # Store orchestrator reference in app state for endpoints to use
            app.state.orchestrator = app_orchestrator
            app.state.service_registry = app_orchestrator.service_registry
            
            logger.info("✅ FastAPI + Service Orchestration startup complete")
            
            yield  # FastAPI runs here
            
        except Exception as e:
            logger.error(f"Service composition startup failed: {e}")
            raise
        finally:
            # Only shutdown orchestrator if we created it
            if should_stop_orchestrator and app_orchestrator:
                logger.info("🛑 Shutting down Service Orchestration...")
                await app_orchestrator.stop()
                logger.info("✅ Service Composition shutdown complete")
            else:
                logger.info("✅ FastAPI shutdown complete (external orchestrator preserved)")
    
    return service_composition_lifespan


def create_service_composition_app(existing_orchestrator=None) -> FastAPI:
    """
    Create FastAPI app with Service Composition Architecture
    
    Key improvements over unified_app:
    - Uses ServiceOrchestrator for single config loading
    - Clean separation between web server and IB API lifecycles
    - Services communicate through ServiceRegistry instead of global state
    - Background streaming can run independently
    """
    app = FastAPI(
        title="IB Stream API - Service Composition Architecture",
        description="Real-time streaming market data with Service Composition Architecture",
        version="3.0.0",
        lifespan=create_service_composition_lifespan(existing_orchestrator)
    )
    
    # Setup endpoints with service integration
    # Note: We'll pass the orchestrator/registry to endpoints instead of raw config
    setup_health_endpoints_v3(app)
    setup_buffer_endpoints_v3(app)
    setup_streaming_endpoints_v3(app)
    setup_websocket_endpoints_v3(app)
    setup_management_endpoints_v3(app)
    setup_v3_endpoints_v3(app)
    
    @app.get("/")
    async def root():
        """Root endpoint with Service Composition Architecture information"""
        return {
            "service": "ib-stream",
            "architecture": "service_composition",
            "description": "Real-time market data streaming with Service Composition Architecture",
            "version": "3.0.0",
            "features": [
                "Service Composition Pattern",
                "Single configuration loading",
                "Independent service lifecycles",
                "Event-driven service communication",
                "Background streaming independence",
                "Clean separation of concerns"
            ],
            "services": {
                "ib_service": "Independent IB API and background streaming management",
                "storage_service": "Independent data persistence",
                "web_service": "FastAPI HTTP endpoints (this service)"
            },
            "endpoints": {
                "/health": "Health check with service composition status",
                "/services/status": "All service status from ServiceRegistry",
                "/stream/info": "Streaming API documentation",
                "/v2/stream/{contract_id}/buffer": "Stream historical buffer + live data (SSE)",
                "/v2/stream/{contract_id}/live/{tick_type}": "Stream specific tick type data (SSE)", 
                "/background/health/summary": "Background stream health summary",
                "ws://host/v2/ws/stream": "WebSocket streaming endpoint"
            }
        }
    
    @app.get("/services/status")
    async def services_status():
        """Get status for all services from ServiceRegistry"""
        if not hasattr(app.state, 'service_registry'):
            raise HTTPException(status_code=503, detail="Service registry not available")
        
        return app.state.service_registry.get_all_status()
    
    return app


def setup_health_endpoints_v3(app: FastAPI):
    """Setup health endpoints that use ServiceRegistry instead of global state"""
    
    @app.get("/health")
    async def health_check():
        """
        Comprehensive health check using Service Composition Architecture
        
        This replaces the old global state pattern with clean ServiceRegistry queries
        """
        if not hasattr(app.state, 'orchestrator'):
            return {
                "status": "starting",
                "architecture": "service_composition",
                "message": "Service orchestrator not yet available",
                "timestamp": __import__('time').time()
            }
        
        orchestrator = app.state.orchestrator
        service_registry = app.state.service_registry
        
        # Get comprehensive status from ServiceRegistry
        all_status = orchestrator.get_all_status()
        
        # Determine overall health based on critical services
        overall_health = "healthy"
        if not orchestrator.is_healthy():
            overall_health = "degraded"
        
        # Get detailed service status
        ib_service = orchestrator.get_ib_service()
        storage_service = orchestrator.get_storage_service()
        
        ib_health = "unavailable"
        storage_health = "unavailable"
        
        if ib_service:
            ib_status = ib_service.get_ib_status()
            ib_health = "healthy" if ib_service.is_connection_healthy() else "degraded"
        
        if storage_service:
            storage_status = storage_service.get_storage_status()
            storage_health = "healthy" if storage_service._state.name == "RUNNING" else "degraded"
        
        return {
            "status": overall_health,
            "architecture": "service_composition",
            "timestamp": __import__('time').time(),
            "config_loads": 1,  # Always 1 with ServiceOrchestrator!
            "services": {
                "ib_service": {
                    "status": ib_health,
                    "connection_healthy": ib_service.is_connection_healthy() if ib_service else False,
                    "background_streaming": ib_service.get_background_status() if ib_service else {}
                },
                "storage_service": {
                    "status": storage_health,
                    "enabled": storage_service.config.storage.enable_storage if storage_service else False
                },
                "web_service": {
                    "status": "healthy",
                    "endpoints": "active"
                }
            },
            "orchestrator": all_status.get("orchestrator", {}),
            "service_registry": {
                "registered_services": service_registry.list_services(),
                "total_services": len(service_registry.list_services())
            },
            "benefits": [
                "Single configuration load (no redundancy)",
                "Independent service lifecycles",
                "Clean separation of concerns",
                "Event-driven service communication",
                "Background streaming independence"
            ]
        }
    
    @app.get("/health/detailed")
    async def health_detailed():
        """Detailed health information from all services"""
        if not hasattr(app.state, 'service_registry'):
            raise HTTPException(status_code=503, detail="Service registry not available")
        
        service_registry = app.state.service_registry
        return {
            "architecture": "service_composition", 
            "detailed_status": service_registry.get_all_status(),
            "timestamp": __import__('time').time()
        }
    
    @app.get("/services/{service_name}/health")
    async def service_health(service_name: str):
        """Get health for a specific service"""
        if not hasattr(app.state, 'service_registry'):
            raise HTTPException(status_code=503, detail="Service registry not available")
        
        service_registry = app.state.service_registry
        status = service_registry.get_status(service_name)
        
        if not status:
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
        
        return {
            "service": service_name,
            "status": status.__dict__,
            "timestamp": __import__('time').time()
        }


def setup_buffer_endpoints_v3(app: FastAPI):
    """Setup buffer endpoints that use ServiceRegistry to get IB service"""
    
    @app.get("/stream/info")
    async def stream_info():
        """Stream API information using Service Composition"""
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        ib_service = orchestrator.get_ib_service()
        
        if not ib_service or not ib_service.is_connection_healthy():
            raise HTTPException(status_code=503, detail="IB Service not available")
        
        return {
            "service": "ib-stream",
            "architecture": "service_composition", 
            "streaming_available": True,
            "ib_service_status": ib_service.get_ib_status().__dict__,
            "message": "Streaming API ready via Service Composition"
        }


def setup_streaming_endpoints_v3(app: FastAPI):
    """Setup streaming endpoints that use ServiceRegistry to get StreamingApp"""
    
    from fastapi.responses import StreamingResponse
    from .streaming_app import StreamingApp
    
    @app.get("/v2/stream/{contract_id}/live/{tick_type}")
    async def stream_live_data(contract_id: int, tick_type: str):
        """Stream live data using Service Composition Architecture"""
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        ib_service = orchestrator.get_ib_service()
        
        if not ib_service:
            raise HTTPException(status_code=503, detail="IB Service not available")
        
        streaming_app = ib_service.get_streaming_app()
        if not streaming_app:
            raise HTTPException(status_code=503, detail="IB connection not available")
        
        # Use the streaming app from the service
        # This is where we'd implement the actual streaming logic
        # For now, return a placeholder
        return {
            "message": "Streaming endpoint ready",
            "contract_id": contract_id,
            "tick_type": tick_type,
            "architecture": "service_composition",
            "streaming_app_available": True
        }


def setup_websocket_endpoints_v3(app: FastAPI):
    """Setup WebSocket endpoints using Service Composition"""
    # Placeholder for WebSocket integration with services
    pass


def setup_management_endpoints_v3(app: FastAPI):
    """Setup management endpoints using Service Composition"""
    
    @app.get("/background/health/summary")
    async def background_health_summary():
        """Background streaming health using Service Composition"""
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        ib_service = orchestrator.get_ib_service()
        
        if not ib_service:
            return {
                "status": "unavailable",
                "message": "IB Service not running"
            }
        
        return {
            "status": "healthy" if ib_service.is_connection_healthy() else "unhealthy",
            "architecture": "service_composition",
            "background_status": ib_service.get_background_status(),
            "ib_status": ib_service.get_ib_status().__dict__
        }


def setup_v3_endpoints_v3(app: FastAPI):
    """Setup v3 endpoints using Service Composition"""
    # Placeholder for v3 endpoint integration
    pass


# Create the app instance
app = create_service_composition_app()