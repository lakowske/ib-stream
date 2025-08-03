#!/usr/bin/env python3
"""
FastAPI Server for IB Stream API - Refactored Version
Uses BaseAPIServer for consistent architecture while maintaining all streaming functionality.
"""

import logging
from typing import Any, Dict

from ib_util import BaseAPIServer, create_standardized_health_response

from .app_lifecycle import get_app_state, ensure_tws_connection
from .endpoints.health import setup_health_endpoints
from .endpoints.buffer import setup_buffer_endpoints
from .endpoints.streaming import setup_streaming_endpoints
from .endpoints.websocket import setup_websocket_endpoints
from .endpoints.management import setup_management_endpoints
from .endpoints.v3 import setup_v3_endpoints


class IBStreamAPIServer(BaseAPIServer):
    """
    IB Stream API server using BaseAPIServer
    
    Maintains all existing streaming functionality while benefiting from
    standardized server setup, configuration, and lifecycle management.
    """
    
    def __init__(self):
        # Get the existing app state and config for compatibility
        self.app_state = get_app_state()
        self.stream_config = self.app_state['config']
        
        super().__init__(
            service_name="ib-stream",
            service_type="stream",
            title="IB Stream API Server",
            description="Real-time streaming market data from Interactive Brokers TWS via Server-Sent Events",
            verbose_logging=True
        )
        
        # Store references to streaming-specific components
        self.storage = None
        self.background_manager = None
        self.tws_app = None
        self.active_streams = {}
        self.stream_lock = None
    
    def setup_endpoints(self):
        """Setup streaming-specific endpoints"""
        # Setup all endpoint modules with the stream config
        setup_health_endpoints(self.app, self.stream_config)
        setup_buffer_endpoints(self.app, self.stream_config)
        setup_streaming_endpoints(self.app, self.stream_config)
        setup_websocket_endpoints(self.app)
        setup_management_endpoints(self.app, self.stream_config)
        setup_v3_endpoints(self.app, self.stream_config)
    
    async def startup(self):
        """Streaming service startup logic"""
        # Import here to avoid circular imports
        from .app_lifecycle import lifespan
        from .storage.multi_storage_v3 import MultiStorageV3
        from .stream_manager import stream_manager
        from .background_stream_manager import BackgroundStreamManager
        
        self.logger.info("Initializing IB Stream API Server...")
        self.logger.info("Configuration:")
        self.logger.info("  Client ID: %d", self.stream_config.client_id)
        self.logger.info("  Host: %s", self.stream_config.host)
        self.logger.info("  Ports: %s", self.stream_config.ports)
        self.logger.info("  Max Streams: %d", self.stream_config.max_concurrent_streams)
        if self.stream_config.default_timeout_seconds is not None:
            self.logger.info("  Default Timeout: %d seconds", self.stream_config.default_timeout_seconds)
        else:
            self.logger.info("  Default Timeout: No timeout (unlimited)")
        
        # Initialize storage system
        if self.stream_config.storage.enable_storage:
            self.logger.info("Initializing storage system...")
            self.logger.info("  Storage path: %s", self.stream_config.storage.storage_base_path)
            self.logger.info("  JSON enabled: %s", self.stream_config.storage.enable_json)
            self.logger.info("  Protobuf enabled: %s", self.stream_config.storage.enable_protobuf)
            self.logger.info("  PostgreSQL enabled: %s", self.stream_config.storage.enable_postgres_index)
            
            try:
                self.storage = MultiStorageV3(
                    storage_path=self.stream_config.storage.storage_base_path,
                    enable_v2_json=self.stream_config.storage.enable_json,
                    enable_v2_protobuf=self.stream_config.storage.enable_protobuf,
                    enable_v3_json=True,
                    enable_v3_protobuf=True,
                    enable_metrics=self.stream_config.storage.enable_metrics
                )
                await self.storage.start()
                self.logger.info("Storage system initialized successfully")
                
                # Initialize stream_manager with storage
                stream_manager.storage = self.storage
                stream_manager.enable_client_stream_storage = self.stream_config.storage.enable_client_stream_storage
                self.logger.info("Stream manager configured with storage, client stream storage: %s", 
                               "enabled" if self.stream_config.storage.enable_client_stream_storage else "disabled")
                
            except Exception as e:
                self.logger.error("Failed to initialize storage system: %s", e)
                self.logger.info("Continuing without storage...")
                self.storage = None
        else:
            self.logger.info("Storage system disabled")
            # Still configure stream_manager with client stream storage setting
            stream_manager.enable_client_stream_storage = self.stream_config.storage.enable_client_stream_storage
        
        # Attempt TWS connection
        self.logger.info("Attempting to establish TWS connection...")
        try:
            self.tws_app = ensure_tws_connection()
            self.logger.info("TWS connection established successfully")
        except Exception as e:
            self.logger.warning("Failed to establish initial TWS connection: %s", e)
            self.logger.info("Will attempt to connect on first streaming request")
        
        # Initialize background streaming for tracked contracts
        if self.stream_config.storage.tracked_contracts:
            self.logger.info("Initializing background streaming for %d tracked contracts...", 
                           len(self.stream_config.storage.tracked_contracts))
            
            try:
                self.background_manager = BackgroundStreamManager(
                    tracked_contracts=self.stream_config.storage.tracked_contracts,
                    reconnect_delay=self.stream_config.storage.background_stream_reconnect_delay
                )
                await self.background_manager.start()
                self.logger.info("Background streaming started successfully")
                
                # Log tracked contracts
                for contract in self.stream_config.storage.tracked_contracts:
                    self.logger.info("  Tracking contract %d (%s): %s, buffer=%dh", 
                                   contract.contract_id, contract.symbol, 
                                   contract.tick_types, contract.buffer_hours)
                
            except Exception as e:
                self.logger.error("Failed to start background streaming: %s", e)
                self.background_manager = None
        else:
            self.logger.info("No tracked contracts configured - background streaming disabled")
        
        # Update app state references
        self.app_state.update({
            'storage': self.storage,
            'background_manager': self.background_manager,
            'tws_app': self.tws_app
        })
    
    async def shutdown(self):
        """Streaming service shutdown logic"""
        self.logger.info("Shutting down IB Stream API Server...")
        
        # Stop background streaming
        if self.background_manager:
            self.logger.info("Stopping background streaming...")
            try:
                await self.background_manager.stop()
                self.logger.info("Background streaming stopped")
            except Exception as e:
                self.logger.error("Error stopping background streaming: %s", e)
        
        # Stop storage system
        if self.storage:
            self.logger.info("Stopping storage system...")
            try:
                await self.storage.stop()
                self.logger.info("Storage system stopped")
            except Exception as e:
                self.logger.error("Error stopping storage system: %s", e)
        
        # Close TWS connection and clean up streams
        if self.tws_app and self.tws_app.is_connected():
            # Get current active streams
            app_state = get_app_state()
            active_streams = app_state.get('active_streams', {})
            stream_lock = app_state.get('stream_lock')
            
            if stream_lock:
                with stream_lock:
                    for stream_id in list(active_streams.keys()):
                        try:
                            self.tws_app.cancelTickByTickData(stream_id)
                        except Exception as e:
                            self.logger.warning("Error cancelling stream %s: %s", stream_id, e)
                    active_streams.clear()
            
            self.tws_app.disconnect_and_stop()
            self.logger.info("TWS connection closed")
    
    def get_api_info(self) -> Dict[str, Any]:
        """Get streaming service API information"""
        return {
            "description": "Real-time streaming market data via Server-Sent Events",
            "documentation": {
                "info": "Visit /stream/info for detailed API usage and examples",
                "health": "Check /health for server and connection status",
                "active": "View /stream/active for currently running streams",
            },
            "endpoints": {
                "/v2/stream/{contract_id}/buffer": "Stream historical buffer + live data (SSE)",
                "/v2/stream/{contract_id}/live/{tick_type}": "Stream specific tick type data (SSE)",
                "/v2/stream/{contract_id}/live": "Stream multiple tick types (SSE)",
                "ws://{host}/v2/ws/stream": "V2 WebSocket streaming endpoint",
                "ws://{host}/ws/stream/{contract_id}/{tick_type}": "WebSocket streaming for specific tick type",
                "ws://{host}/ws/stream/{contract_id}/multi": "WebSocket multi-stream endpoint",
                "ws://{host}/ws/control": "WebSocket control channel",
                "/health": "Health check with TWS connection status",
                "/storage/status": "Storage system status and metrics",
                "/background/status": "Background streaming status",
                "/v2/buffer/{contract_id}/info": "Buffer information for contract",
                "/v2/buffer/{contract_id}/stats": "Buffer statistics for contract",
                "/stream/info": "Available tick types and streaming capabilities",
                "/v2/info": "V2 protocol information",
                "/v3/info": "V3 optimized format information (50%+ storage reduction)",
                "/v3/buffer/{contract_id}/info": "V3 buffer information with optimization stats",
                "/v3/buffer/{contract_id}/query": "Query v3 optimized buffer data",
                "/v3/storage/stats": "V3 storage statistics and v2 comparison",
                "/v3/storage/files/{contract_id}": "List v3 storage files for contract",
                "/stream/active": "List currently active streams",
                "DELETE /stream/{contract_id}": "Stop all streams for a specific contract",
                "DELETE /stream/all": "Stop all active streams",
            },
            "tick_types": ["last", "all_last", "bid_ask", "mid_point"],
            "configuration": {
                "client_id": self.stream_config.client_id,
                "max_concurrent_streams": self.stream_config.max_concurrent_streams,
                "default_timeout_seconds": self.stream_config.default_timeout_seconds,
                "storage": {
                    "enabled": self.stream_config.storage.enable_storage,
                    "formats": {
                        "json": self.stream_config.storage.enable_json,
                        "protobuf": self.stream_config.storage.enable_protobuf,
                        "v3_optimized": True
                    },
                    "tracked_contracts": len(self.stream_config.storage.tracked_contracts) if self.stream_config.storage.tracked_contracts else 0
                }
            },
            "features": [
                "Real-time tick-by-tick streaming",
                "Server-Sent Events (SSE) support",
                "WebSocket streaming",
                "Historical buffer integration",
                "V3 optimized storage (50%+ reduction)",
                "Background contract tracking",
                "Multi-format storage (JSON, Protobuf)",
                "Connection pooling and auto-reconnect"
            ]
        }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get streaming service health status"""
        try:
            app_state = get_app_state()
            storage = app_state.get('storage')
            background_manager = app_state.get('background_manager')
            tws_app = app_state.get('tws_app')
            active_streams = app_state.get('active_streams', {})
            stream_lock = app_state.get('stream_lock')
            
            tws_connected = tws_app is not None and tws_app.is_connected()
            
            # Get active stream count safely
            active_stream_count = 0
            if stream_lock:
                with stream_lock:
                    active_stream_count = len(active_streams)
            
            # Get storage status
            storage_status = {"enabled": False}
            if storage:
                try:
                    storage_info = await storage.get_storage_info()
                    storage_status = {
                        "enabled": True,
                        "formats": storage_info.get('enabled_formats', []),
                        "queue_sizes": storage_info.get('queue_sizes', {}),
                        "message_stats": storage_info.get('message_stats', {}),
                    }
                except Exception as e:
                    self.logger.warning("Failed to get storage info: %s", e)
                    storage_status = {"enabled": True, "error": str(e)}
            
            # Get background streaming status
            background_status = {"enabled": False}
            if background_manager:
                try:
                    background_status = {
                        "enabled": True,
                        "tracked_contracts": len(self.stream_config.storage.tracked_contracts) if self.stream_config.storage.tracked_contracts else 0,
                        "status": "running"
                    }
                except Exception as e:
                    background_status = {"enabled": True, "error": str(e)}
            
            # Determine overall health
            status = "healthy"
            if not tws_connected:
                status = "degraded"  # Can still serve buffered data
            
            return create_standardized_health_response(
                service_name=self.service_name,
                status=status,
                details={
                    "tws_connected": tws_connected,
                    "active_streams": active_stream_count,
                    "max_streams": self.stream_config.max_concurrent_streams,
                    "client_id": self.stream_config.client_id,
                    "connection_ports": self.stream_config.ports,
                    "storage": storage_status,
                    "background_streaming": background_status,
                    "features": {
                        "sse_streaming": True,
                        "websocket_streaming": True,
                        "v3_storage": storage_status.get("enabled", False),
                        "background_tracking": background_status.get("enabled", False)
                    }
                }
            )
        except Exception as e:
            self.logger.error("Health check failed: %s", e)
            return create_standardized_health_response(
                service_name=self.service_name,
                status="unhealthy",
                details={"error": str(e)}
            )


# Factory function and compatibility layer
def create_app() -> IBStreamAPIServer:
    """Factory function to create the IB Stream API server"""
    return IBStreamAPIServer()


# Create lifespan context manager for backward compatibility
def create_lifespan_wrapper(server_instance):
    """Create a lifespan wrapper that integrates with BaseAPIServer"""
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def lifespan(app):
        # Startup is handled by BaseAPIServer
        yield
        # Shutdown is handled by BaseAPIServer
    
    return lifespan


# Global app instance for uvicorn and compatibility
server_instance = create_app()
app = server_instance.app

# Create and set the lifespan for compatibility
app.router.lifespan_context = create_lifespan_wrapper(server_instance)


def main():
    """Main function to run the server"""
    server_instance.run()


if __name__ == "__main__":
    main()