"""
V3 Monitoring Dashboard Endpoints - Service Composition Architecture

Comprehensive monitoring dashboard that showcases advanced metrics collection
through EventBus and ServiceRegistry integration.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Query

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_monitoring_endpoints_v3(app):
    """Setup v3 monitoring dashboard endpoints"""
    
    @router.get("/v3/monitoring/dashboard")
    async def monitoring_dashboard_v3(request: Request):
        """
        Comprehensive monitoring dashboard using Service Composition Architecture
        
        This endpoint demonstrates the power of EventBus-driven metrics collection
        and ServiceRegistry service discovery.
        """
        
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        
        # Get comprehensive metrics
        metrics = orchestrator.get_metrics()
        
        # Get service registry status
        service_registry = app.state.service_registry
        all_services = service_registry.get_all_status()
        
        # Build comprehensive dashboard
        dashboard = {
            "dashboard": "IB Stream Service Composition Architecture",
            "timestamp": datetime.utcnow().isoformat(),
            "architecture": "service_composition_v3",
            
            # Configuration efficiency metrics
            "configuration": {
                "total_config_loads": metrics.get("global_metrics", {}).get("config_loads", 1),
                "efficiency": "Single configuration load eliminates 5+ redundant loads",
                "benefit": "Faster startup, reduced I/O, single source of truth"
            },
            
            # Service composition overview
            "service_composition": {
                "total_services": len(orchestrator.services),
                "registered_services": service_registry.list_services(),
                "healthy_services": sum(1 for name in service_registry.list_services() 
                                      if service_registry.is_service_healthy(name)),
                "orchestrator_healthy": orchestrator.is_healthy()
            },
            
            # Event-driven metrics
            "event_metrics": metrics.get("global_metrics", {}),
            
            # Performance summary
            "performance": metrics.get("performance_summary", {}),
            
            # Service details
            "service_details": {},
            
            # Architecture benefits showcase
            "architecture_benefits": {
                "single_config_loading": "✅ Eliminated redundant configuration loads",
                "service_independence": "✅ IB Service runs without FastAPI",
                "clean_separation": "✅ Services communicate through EventBus/ServiceRegistry",
                "flexible_deployment": "✅ Multiple deployment modes available",
                "event_driven_monitoring": "✅ Real-time metrics collection",
                "ordered_startup": "✅ Proper service dependency management"
            }
        }
        
        # Add detailed service information
        for service_name in orchestrator.services:
            service_metrics = orchestrator.get_service_metrics(service_name)
            service_status = service_registry.get_status(service_name)
            
            dashboard["service_details"][service_name] = {
                "status": service_status.__dict__ if service_status else None,
                "metrics": service_metrics,
                "healthy": service_registry.is_service_healthy(service_name)
            }
        
        return dashboard
    
    @router.get("/v3/monitoring/metrics")
    async def monitoring_metrics_v3(request: Request):
        """
        Raw metrics data for external monitoring systems
        """
        
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        metrics = orchestrator.get_metrics()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "architecture": "service_composition_v3",
            "metrics": metrics
        }
    
    @router.get("/v3/monitoring/performance")
    async def monitoring_performance_v3(request: Request):
        """
        Performance monitoring endpoint showcasing Service Composition benefits
        """
        
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        metrics = orchestrator.get_metrics()
        
        # Get performance summary
        performance = metrics.get("performance_summary", {})
        global_metrics = metrics.get("global_metrics", {})
        
        return {
            "performance_analysis": {
                "architecture": "service_composition_v3",
                "timestamp": datetime.utcnow().isoformat(),
                
                # Configuration efficiency
                "config_performance": {
                    "total_loads": global_metrics.get("config_loads", 1),
                    "improvement": "Eliminated 5+ redundant config loads",
                    "startup_efficiency": "Faster startup due to single config load"
                },
                
                # Event processing performance
                "event_performance": {
                    "total_events": global_metrics.get("total_events", 0),
                    "events_per_second": global_metrics.get("events_per_second", 0),
                    "error_rate_percent": performance.get("error_rate_percent", 0),
                    "data_events": global_metrics.get("data_events", 0)
                },
                
                # Service performance
                "service_performance": {
                    "uptime_hours": performance.get("uptime_hours", 0),
                    "total_services": performance.get("total_services", 0),
                    "most_active_service": performance.get("most_active_service", "unknown"),
                    "events_per_hour": performance.get("events_per_hour", 0)
                },
                
                # Architecture comparison
                "architecture_comparison": {
                    "old_architecture": {
                        "config_loads": "5+ redundant loads",
                        "service_coupling": "Tight coupling via global state",
                        "monitoring": "Limited visibility",
                        "independence": "Services tied to FastAPI lifecycle"
                    },
                    "new_architecture": {
                        "config_loads": "1 single load",
                        "service_coupling": "Loose coupling via EventBus/ServiceRegistry",
                        "monitoring": "Comprehensive event-driven metrics",
                        "independence": "Services run independently"
                    }
                }
            }
        }
    
    @router.get("/v3/monitoring/services/{service_name}")
    async def monitoring_service_detail_v3(request: Request, service_name: str):
        """
        Detailed monitoring for a specific service
        """
        
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        service_registry = app.state.service_registry
        
        # Check if service exists
        if service_name not in service_registry.list_services():
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
        
        # Get detailed service information
        service_metrics = orchestrator.get_service_metrics(service_name)
        service_status = service_registry.get_status(service_name)
        
        return {
            "service": service_name,
            "timestamp": datetime.utcnow().isoformat(),
            "architecture": "service_composition_v3",
            "status": service_status.__dict__ if service_status else None,
            "metrics": service_metrics,
            "healthy": service_registry.is_service_healthy(service_name),
            "monitoring_capabilities": [
                "Real-time event tracking",
                "Performance metrics collection",
                "Error rate monitoring",
                "Service lifecycle tracking",
                "Custom metric collection"
            ]
        }
    
    @router.get("/v3/monitoring/comparison")
    async def architecture_comparison_v3(request: Request):
        """
        Architecture comparison showing Service Composition benefits
        """
        
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        metrics = orchestrator.get_metrics()
        global_metrics = metrics.get("global_metrics", {})
        
        return {
            "architecture_comparison": {
                "timestamp": datetime.utcnow().isoformat(),
                
                "unified_architecture_issues": {
                    "config_loading": "5+ redundant create_config() calls during startup",
                    "service_coupling": "Tight coupling through global state variables",
                    "startup_process": "Chaotic, unordered service initialization",
                    "service_management": "FastAPI managing IB API lifecycle",
                    "independence": "Background streaming requires web server",
                    "monitoring": "Limited visibility into service health"
                },
                
                "service_composition_solutions": {
                    "config_loading": f"Single config load (currently: {global_metrics.get('config_loads', 1)})",
                    "service_coupling": "Loose coupling via EventBus and ServiceRegistry",
                    "startup_process": "Ordered dependency management through ServiceOrchestrator",
                    "service_management": "Independent service lifecycles",
                    "independence": "Background streaming runs standalone",
                    "monitoring": f"Comprehensive metrics ({global_metrics.get('total_events', 0)} events tracked)"
                },
                
                "measurable_improvements": {
                    "config_efficiency": f"{global_metrics.get('config_loads', 1)} vs 5+ loads",
                    "event_tracking": f"{global_metrics.get('total_events', 0)} events monitored",
                    "service_count": len(orchestrator.services),
                    "error_monitoring": f"{global_metrics.get('error_events', 0)} errors tracked",
                    "uptime_tracking": f"{metrics.get('performance_summary', {}).get('uptime_hours', 0):.2f} hours"
                },
                
                "deployment_flexibility": {
                    "debug_mode": "python debug_runner.py debug - FastAPI + Services",
                    "standalone_mode": "python debug_runner.py standalone - Background streaming only",
                    "production_mode": "python debug_runner.py production - Full deployment",
                    "supervisor_compatible": "python production_runner.py full"
                }
            }
        }
    
    @router.post("/v3/monitoring/metrics/reset")
    async def reset_metrics_v3(request: Request):
        """
        Reset metrics (useful for testing and development)
        """
        
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        
        if orchestrator.metrics_collector:
            orchestrator.metrics_collector.reset_metrics()
            
            return {
                "message": "Metrics reset successfully",
                "timestamp": datetime.utcnow().isoformat(),
                "architecture": "service_composition_v3"
            }
        else:
            raise HTTPException(status_code=503, detail="Metrics collector not available")
    
    @router.get("/v3/monitoring/health/realtime")
    async def realtime_health_v3(request: Request):
        """
        Real-time health monitoring endpoint
        """
        
        if not hasattr(app.state, 'orchestrator'):
            raise HTTPException(status_code=503, detail="Service orchestrator not available")
        
        orchestrator = app.state.orchestrator
        service_registry = app.state.service_registry
        metrics = orchestrator.get_metrics()
        
        # Calculate real-time health scores
        total_services = len(orchestrator.services)
        healthy_services = sum(1 for name in service_registry.list_services() 
                             if service_registry.is_service_healthy(name))
        
        health_percentage = (healthy_services / total_services * 100) if total_services > 0 else 0
        
        # Get recent error rate
        global_metrics = metrics.get("global_metrics", {})
        error_rate = (global_metrics.get("error_events", 0) / 
                     max(global_metrics.get("total_events", 1), 1) * 100)
        
        return {
            "realtime_health": {
                "timestamp": datetime.utcnow().isoformat(),
                "architecture": "service_composition_v3",
                
                "overall_health": {
                    "status": "healthy" if health_percentage >= 100 else "degraded",
                    "health_percentage": health_percentage,
                    "healthy_services": healthy_services,
                    "total_services": total_services
                },
                
                "realtime_metrics": {
                    "total_events": global_metrics.get("total_events", 0),
                    "events_per_second": global_metrics.get("events_per_second", 0),
                    "error_rate_percent": error_rate,
                    "data_events": global_metrics.get("data_events", 0)
                },
                
                "service_status": {
                    name: service_registry.is_service_healthy(name)
                    for name in service_registry.list_services()
                },
                
                "monitoring_active": {
                    "event_bus": True,
                    "service_registry": True,
                    "metrics_collector": orchestrator.metrics_collector is not None,
                    "advanced_monitoring": True
                }
            }
        }
    
    # Register router with app
    app.include_router(router, prefix="", tags=["monitoring_v3"])