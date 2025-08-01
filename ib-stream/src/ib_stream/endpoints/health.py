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
            with stream_lock:
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

            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "tws_connected": tws_connected,
                "active_streams": active_stream_count,
                "storage": storage_status,
                "max_streams": config.max_concurrent_streams,
                "client_id": config.client_id,
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
    
    @router.get("/time/status")
    async def time_status():
        """Check system time drift and synchronization status"""
        import subprocess
        import socket
        import struct
        from datetime import datetime, timezone
        
        async def get_ntp_time(server: str = 'pool.ntp.org') -> dict:
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                client.settimeout(2)
                
                # NTP packet format
                packet = b'\x1b' + 47 * b'\0'
                client.sendto(packet, (server, 123))
                data, _ = client.recvfrom(1024)
                client.close()
                
                # Extract timestamp
                unpacked = struct.unpack('!12I', data)
                timestamp = unpacked[10] + unpacked[11] / 2**32
                unix_timestamp = timestamp - 2208988800
                
                ntp_time = datetime.fromtimestamp(unix_timestamp, timezone.utc)
                system_time = datetime.now(timezone.utc)
                drift = (system_time - ntp_time).total_seconds()
                
                return {
                    "server": server,
                    "ntp_time": ntp_time.isoformat(),
                    "system_time": system_time.isoformat(),
                    "drift_seconds": round(drift, 3),
                    "status": "success"
                }
            except Exception as e:
                return {
                    "server": server,
                    "error": str(e),
                    "status": "error"
                }
        
        # Get NTP status
        ntp_status = await get_ntp_time()
        
        # Get system time sync status
        try:
            timedatectl_result = subprocess.run(
                ['timedatectl', 'status'], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            sync_status = "synchronized" in timedatectl_result.stdout
        except:
            sync_status = False
        
        # Get NTP peer info
        try:
            ntpq_result = subprocess.run(
                ['ntpq', '-p'], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            ntpq_output = ntpq_result.stdout
        except:
            ntpq_output = "NTP query failed"
        
        # Determine overall status
        drift = abs(ntp_status.get('drift_seconds', 999))
        if drift > 30:
            overall_status = "critical"
        elif drift > 5:
            overall_status = "warning"  
        elif drift > 1:
            overall_status = "caution"
        else:
            overall_status = "good"
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status,
            "system_sync": sync_status,
            "ntp_check": ntp_status,
            "ntpq_peers": ntpq_output,
            "message": f"Time drift: {drift:.3f}s ({overall_status})"
        }
    
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
    
    app.include_router(router)