"""
Health and status endpoints for the IB Stream API
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..storage import MultiStorage

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_health_endpoints(app, config):
    """Setup health and status endpoints with dependencies"""
    
    @router.get("/health")
    async def health_check():
        """Health check endpoint"""
        from ..app_lifecycle import get_app_state
        
        try:
            app_state = get_app_state()
            storage = app_state['storage']
            background_manager = app_state['background_manager']
            tws_app = app_state['tws_app']
            active_streams = app_state['active_streams']
            stream_lock = app_state['stream_lock']
            
            tws_connected = tws_app is not None and tws_app.is_connected()
            
            # Clear active streams if connection is lost
            with stream_lock:
                if not tws_connected and active_streams:
                    logger.warning("TWS disconnected - clearing %d orphaned active streams", len(active_streams))
                    active_streams.clear()
                active_stream_count = len(active_streams)

            storage_status = None
            if storage:
                storage_info = await storage.get_storage_info()
                storage_status = {
                    "enabled": True,
                    "formats": storage_info.get('enabled_formats', []),
                    "queue_sizes": storage_info.get('queue_sizes', {}),
                    "message_stats": storage_info.get('message_stats', {}),
                    "storage_info": storage_info
                }
            else:
                storage_status = {"enabled": False}

            # Get fresh config from app state
            current_config = app_state['config']
            
            # Add time and storage monitoring to health check
            from ib_util.time_monitoring import get_time_health_status
            from ib_util.storage_monitoring import get_storage_health_status
            
            time_health = get_time_health_status()
            
            # Get storage streaming health (check for active data streaming)
            try:
                storage_health = get_storage_health_status()['storage_streaming']
            except Exception as e:
                logger.warning(f"Storage monitoring failed: {e}")
                storage_health = {"status": "error", "message": str(e)}
            
            # Determine overall status based on all subsystems
            overall_status = "healthy"
            if not tws_connected:
                overall_status = "degraded"
            elif time_health['time_sync']['status'] == "critical":
                overall_status = "degraded"
            elif storage_health.get('status') == "critical":
                overall_status = "degraded"
            elif time_health['time_sync']['status'] == "warning" or storage_health.get('status') == "warning":
                overall_status = "warning"
            
            return {
                "service": f"ib-stream",
                "status": overall_status,
                "timestamp": datetime.now().isoformat(),
                "tws_connected": tws_connected,
                "active_streams": active_stream_count,
                "max_streams": current_config.max_concurrent_streams,
                "client_id": current_config.client_id,
                "connection_ports": current_config.connection_ports,
                "storage": storage_status,
                "storage_streaming": storage_health,
                "time_sync": time_health['time_sync'],
                "background_streaming": {
                    "enabled": background_manager is not None,
                    "tracked_contracts": len(current_config.storage.tracked_contracts) if background_manager else 0,
                    "status": "running" if background_manager else "disabled"
                },
                "features": {
                    "sse_streaming": True,
                    "websocket_streaming": True,
                    "v3_storage": True,
                    "background_tracking": background_manager is not None
                }
            }
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                },
            )

    @router.get("/storage/status")
    async def storage_status():
        """Storage system status and metrics"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        storage = app_state['storage']
        
        if not storage:
            return {
                "enabled": False,
                "message": "Storage system is disabled"
            }
        
        try:
            storage_info = storage.get_storage_info()
            storage_metrics = storage.get_metrics()
            
            return {
                "enabled": True,
                "timestamp": datetime.now().isoformat(),
                "info": storage_info,
                "metrics": storage_metrics,
                "config": {
                    "storage_path": str(config.storage.storage_base_path),
                    "json_enabled": config.storage.enable_json,
                    "protobuf_enabled": config.storage.enable_protobuf,
                    "postgres_enabled": config.storage.enable_postgres_index,
                    "metrics_enabled": config.storage.enable_metrics
                }
            }
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "enabled": True,
                    "error": f"Storage system error: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            )

    @router.get("/background/status")
    async def background_streaming_status():
        """Background streaming status for tracked contracts"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        background_manager = app_state['background_manager']
        
        if not background_manager:
            return {
                "enabled": False,
                "message": "Background streaming is disabled"
            }
        
        try:
            status = background_manager.get_status()
            return {
                "enabled": True,
                "timestamp": datetime.now().isoformat(),
                "status": status,
                "config": {
                    "max_tracked_contracts": config.storage.max_tracked_contracts,
                    "reconnect_delay": config.storage.background_stream_reconnect_delay,
                    "tracked_contracts_count": len(config.storage.tracked_contracts)
                }
            }
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "enabled": True,
                    "error": f"Background streaming error: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            )
    
    @router.get("/background/health")
    async def background_streaming_health():
        """Comprehensive health assessment for background streams with trading hours awareness"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        background_manager = app_state['background_manager']
        
        if not background_manager:
            return JSONResponse(
                status_code=503,
                content={
                    "enabled": False,
                    "message": "Background streaming is disabled",
                    "timestamp": datetime.now().isoformat()
                }
            )
        
        try:
            health = await background_manager.get_comprehensive_health()
            return {
                "enabled": True,
                "timestamp": datetime.now().isoformat(),
                **health.to_dict()
            }
        except Exception as e:
            logger.error("Error getting background stream health: %s", e)
            return JSONResponse(
                status_code=500,
                content={
                    "enabled": True,
                    "error": f"Health assessment error: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            )
    
    @router.get("/background/health/summary")
    async def background_health_summary():
        """Quick summary of background stream health status"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        background_manager = app_state['background_manager']
        
        if not background_manager:
            return {
                "enabled": False,
                "message": "Background streaming is disabled",
                "timestamp": datetime.now().isoformat()
            }
        
        try:
            summary = background_manager.get_health_summary()
            return {
                "enabled": True,
                "timestamp": datetime.now().isoformat(),
                **summary
            }
        except Exception as e:
            logger.error("Error getting background stream health summary: %s", e)
            return JSONResponse(
                status_code=500,
                content={
                    "enabled": True,
                    "error": f"Health summary error: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            )
    
    @router.get("/background/health/{contract_id}")
    async def contract_health(contract_id: int):
        """Health status for a specific background stream contract"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        background_manager = app_state['background_manager']
        
        if not background_manager:
            return JSONResponse(
                status_code=503,
                content={
                    "enabled": False,
                    "message": "Background streaming is disabled",
                    "timestamp": datetime.now().isoformat()
                }
            )
        
        try:
            # Validate contract ID
            if contract_id <= 0:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Invalid contract ID",
                        "contract_id": contract_id,
                        "timestamp": datetime.now().isoformat()
                    }
                )
            
            # Check if contract is tracked
            if not background_manager.is_contract_tracked(contract_id):
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "Contract not tracked",
                        "contract_id": contract_id,
                        "tracked_contracts": list(background_manager.get_tracked_contract_ids()),
                        "timestamp": datetime.now().isoformat()
                    }
                )
            
            # Get contract health
            contract_health = await background_manager.get_contract_health(contract_id)
            
            if contract_health:
                return {
                    "enabled": True,
                    "contract_id": contract_id,
                    "timestamp": datetime.now().isoformat(),
                    **contract_health.to_dict()
                }
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Could not assess contract health",
                        "contract_id": contract_id,
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
        except Exception as e:
            logger.error("Error getting contract health for %d: %s", contract_id, e)
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Contract health assessment error: {str(e)}",
                    "contract_id": contract_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
    
    @router.get("/time/status")
    async def time_status():
        """Check system time drift and synchronization status using ib-util time monitoring"""
        from ib_util.time_monitoring import get_time_health_status
        
        try:
            time_health = get_time_health_status()
            return time_health['time_sync']
        except Exception as e:
            logger.error("Time status check failed: %s", e)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Time monitoring failed: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            )
    
    @router.get("/time/drift/history")
    async def time_drift_history(limit: int = 100):
        """Get recent time drift history from monitoring logs"""
        import json
        from pathlib import Path
        
        log_file = Path("logs/time_drift_data.jsonl")
        if not log_file.exists():
            return {
                "message": "No time drift history available",
                "entries": []
            }
        
        try:
            entries = []
            with open(log_file, 'r') as f:
                lines = f.readlines()
                # Get last N lines
                for line in lines[-limit:]:
                    entries.append(json.loads(line.strip()))
            
            return {
                "message": f"Retrieved {len(entries)} time drift entries",
                "entries": entries
            }
        except Exception as e:
            return {
                "error": f"Failed to read time drift history: {e}",
                "entries": []
            }

    @router.get("/system/health")
    async def system_health():
        """Unified system health endpoint for external monitoring (UptimeRobot)"""
        import aiohttp
        import subprocess
        from datetime import datetime
        
        try:
            # Aggregate health from both services
            services_health = {}
            overall_status = "healthy"
            issues = []
            
            service_urls = {
                'ib-stream': 'http://localhost:8851/health',
                'ib-contract': 'http://localhost:8861/health'
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                for service_name, url in service_urls.items():
                    try:
                        async with session.get(url) as response:
                            if response.status == 200:
                                service_data = await response.json()
                                
                                # Get time sync data using our Chrony-based monitoring
                                time_sync_data = {}
                                try:
                                    from ib_util.time_monitoring import get_time_health_status
                                    time_health = get_time_health_status()
                                    time_sync_data = time_health.get('time_sync', {})
                                except ImportError as e:
                                    time_sync_data = {"status": "error", "message": f"Time monitoring module unavailable: {str(e)}"}
                                except subprocess.SubprocessError as e:
                                    time_sync_data = {"status": "error", "message": f"Chrony process error: {str(e)}"}
                                except Exception as e:
                                    # Log the full error for debugging, but return generic message
                                    import logging
                                    logging.getLogger(__name__).error(f"Time monitoring error for {service_name}: {str(e)}", exc_info=True)
                                    time_sync_data = {"status": "error", "message": "Time monitoring temporarily unavailable"}
                                
                                services_health[service_name] = {
                                    "status": service_data.get('status', 'unknown'),
                                    "tws_connected": service_data.get('tws_connected', False),
                                    "time_sync": time_sync_data
                                }
                                
                                # Check for issues
                                if not service_data.get('tws_connected', False):
                                    issues.append(f"{service_name}: TWS disconnected")
                                
                                # Check time sync status using new Chrony-based format
                                if time_sync_data.get('status') == 'critical':
                                    overall_status = "degraded"
                                    drift_ms = time_sync_data.get('drift_ms', 0)
                                    issues.append(f"{service_name}: Critical time drift ({drift_ms:.1f}ms)")
                                elif time_sync_data.get('status') == 'warning' and overall_status == "healthy":
                                    overall_status = "warning"
                                    drift_ms = time_sync_data.get('drift_ms', 0)
                                    issues.append(f"{service_name}: Time drift warning ({drift_ms:.1f}ms)")
                                elif time_sync_data.get('status') == 'error':
                                    if overall_status == "healthy":
                                        overall_status = "warning"
                                    issues.append(f"{service_name}: Time monitoring error")
                                    
                                if service_data.get('status') not in ['healthy', 'warning']:
                                    overall_status = "degraded"
                                    issues.append(f"{service_name}: Service status {service_data.get('status')}")
                                    
                            else:
                                services_health[service_name] = {"status": "error", "message": f"HTTP {response.status}"}
                                overall_status = "degraded"
                                issues.append(f"{service_name}: HTTP {response.status}")
                                
                    except Exception as e:
                        services_health[service_name] = {"status": "error", "message": str(e)}
                        overall_status = "degraded"
                        issues.append(f"{service_name}: {str(e)}")
            
            # Storage verification - check if recent data exists
            storage_status = "unknown"
            try:
                from pathlib import Path
                import os
                
                storage_path = Path("ib-stream/storage")
                if storage_path.exists():
                    # Check for files modified in last 5 minutes
                    recent_files = []
                    for file_path in storage_path.rglob("*.pb"):
                        if os.path.getmtime(file_path) > (datetime.now().timestamp() - 300):
                            recent_files.append(file_path)
                    
                    if recent_files:
                        storage_status = "active"
                    else:
                        storage_status = "stale"
                        if overall_status == "healthy":
                            overall_status = "warning"
                        issues.append("Storage: No recent data files")
                else:
                    storage_status = "missing"
                    overall_status = "degraded"
                    issues.append("Storage: Directory not found")
                    
            except Exception as e:
                storage_status = "error"
                issues.append(f"Storage check failed: {str(e)}")
            
            # HTTP status code based on overall health
            status_code = 200
            if overall_status == "degraded":
                status_code = 503  # Service Unavailable
            elif overall_status == "warning":
                status_code = 200  # OK but with warnings
            
            response_data = {
                "system_status": overall_status,
                "timestamp": datetime.now().isoformat(),
                "services": services_health,
                "storage": {"status": storage_status},
                "summary": {
                    "healthy_services": sum(1 for s in services_health.values() if s.get('status') in ['healthy', 'warning']),
                    "total_services": len(services_health),
                    "issues": issues
                }
            }
            
            return JSONResponse(
                status_code=status_code,
                content=response_data
            )
            
        except Exception as e:
            logger.error("System health check failed: %s", e)
            return JSONResponse(
                status_code=500,
                content={
                    "system_status": "error",
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                    "message": "System health check failed"
                }
            )
    
    app.include_router(router)