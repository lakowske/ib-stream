"""
Application lifecycle management for the IB Stream API - Unified Connection Architecture v2

Key changes from v1:
- Uses UnifiedConnectionManager instead of dual connections
- Single client ID (no +1000 offset for background streams)  
- Simplified startup/shutdown with unified recovery
- BackgroundStreamManager v2 integration
"""

import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import HTTPException

from .config import create_config
from .storage import MultiStorage
from .storage.multi_storage_v3 import MultiStorageV3
from .streaming_app import StreamingApp
from .stream_manager import stream_manager
from .background_stream_manager_v2 import BackgroundStreamManagerV2
from .connection import UnifiedConnectionManager

logger = logging.getLogger(__name__)

# Global state - Unified Architecture
config = None  # Configuration loaded in lifespan startup
unified_connection_manager: Optional[UnifiedConnectionManager] = None  # Single connection manager
storage: Optional[MultiStorageV3] = None
background_manager: Optional[BackgroundStreamManagerV2] = None
active_streams = {}
stream_lock = threading.Lock()


def ensure_tws_connection() -> StreamingApp:
    """
    Ensure TWS connection is active - Unified Architecture Version
    
    Returns the StreamingApp instance from the unified connection manager.
    This replaces the old pattern of creating separate connections.
    """
    global unified_connection_manager
    
    if unified_connection_manager is None:
        msg = "Unified connection manager not initialized. Server startup may have failed."
        raise HTTPException(status_code=503, detail=msg)
    
    if not unified_connection_manager.is_connected:
        msg = "TWS connection not available. Please ensure IB Gateway is running with API enabled."
        raise HTTPException(status_code=503, detail=msg)
    
    # Return the shared StreamingApp instance
    return unified_connection_manager.streaming_app


@asynccontextmanager
async def lifespan(_):
    """
    Unified lifespan event handler for startup/shutdown
    
    Key improvements:
    - Single UnifiedConnectionManager replaces dual connections
    - BackgroundStreamManager v2 uses shared connection
    - Simplified connection state management
    - Enhanced recovery system
    """
    # Startup - Load configuration with current environment variables
    global config, unified_connection_manager, storage, background_manager
    
    config = create_config()
    
    logger.info("Starting IB Stream API Server with Unified Connection Architecture...")
    logger.info("Configuration:")
    logger.info("  Client ID: %d", config.client_id)  
    logger.info("  Host: %s", config.host)
    logger.info("  Ports: %s", config.ports)
    logger.info("  Max Streams: %d", config.max_concurrent_streams)
    if config.default_timeout_seconds is not None:
        logger.info("  Default Timeout: %d seconds", config.default_timeout_seconds)
    else:
        logger.info("  Default Timeout: No timeout (unlimited)")
    
    # Initialize unified connection manager
    logger.info("Initializing unified connection manager...")
    unified_connection_manager = UnifiedConnectionManager(
        config=config,
        enable_recovery=True  # Enable automatic recovery
    )
    logger.info("✅ Unified connection manager created with client ID %d", config.client_id)
    
    # Initialize storage system
    if config.storage.enable_storage:
        logger.info("Initializing storage system...")
        logger.info("  Storage path: %s", config.storage.storage_base_path)
        logger.info("  v2 JSON enabled: %s", config.storage.enable_json)
        logger.info("  v2 Protobuf enabled: %s", config.storage.enable_protobuf)
        logger.info("  v3 JSON enabled: %s", config.storage.enable_v3_json)
        logger.info("  v3 Protobuf enabled: %s", config.storage.enable_v3_protobuf)
        logger.info("  PostgreSQL enabled: %s", config.storage.enable_postgres_index)
        
        try:
            storage = MultiStorageV3(
                storage_path=config.storage.storage_base_path,
                enable_v2_json=config.storage.enable_json,
                enable_v2_protobuf=config.storage.enable_protobuf,
                enable_v3_json=config.storage.enable_v3_json,
                enable_v3_protobuf=config.storage.enable_v3_protobuf,
                enable_metrics=config.storage.enable_metrics
            )
            await storage.start()
            logger.info("✅ Storage system initialized successfully")
            
            # Initialize stream_manager with storage and client stream storage config
            stream_manager.storage = storage
            stream_manager.enable_client_stream_storage = config.storage.enable_client_stream_storage
            logger.info("✅ Stream manager configured with storage, client stream storage: %s", 
                       "enabled" if config.storage.enable_client_stream_storage else "disabled")
            
        except Exception as e:
            logger.error("Failed to initialize storage system: %s", e)
            logger.info("Continuing without storage...")
            storage = None
    else:
        logger.info("Storage system disabled")
        # Still configure stream_manager with client stream storage setting
        stream_manager.enable_client_stream_storage = config.storage.enable_client_stream_storage

    # Start unified connection manager
    logger.info("Starting unified connection manager...")
    try:
        await unified_connection_manager.start()
        logger.info("✅ Unified connection established successfully")
    except Exception as e:
        logger.warning("Failed to establish initial connection: %s", e)
        logger.info("Will attempt to connect on first streaming request")
    
    # Initialize background streaming for tracked contracts using unified architecture
    if config.storage.tracked_contracts:
        logger.info("Initializing background streaming for %d tracked contracts...", 
                   len(config.storage.tracked_contracts))
        
        try:
            # Get health staleness threshold with fallback
            staleness_threshold = getattr(
                config.storage, 
                'health_staleness_threshold_minutes', 
                15  # Default to 15 minutes
            )
            
            # Create BackgroundStreamManager v2 with shared connection
            background_manager = BackgroundStreamManagerV2(
                tracked_contracts=config.storage.tracked_contracts,
                connection_manager=unified_connection_manager,  # Use shared connection!
                staleness_threshold_minutes=staleness_threshold
            )
            
            # Start background streaming
            await background_manager.start()
            logger.info("✅ Background streaming started successfully")
            
            # Log tracked contracts
            for contract in config.storage.tracked_contracts:
                logger.info("  📊 Tracking contract %d (%s): %s, buffer=%dh", 
                           contract.contract_id, contract.symbol, 
                           contract.tick_types, contract.buffer_hours)
            
            logger.info("✅ Unified architecture: Single client ID %d serving all streams", 
                       config.client_id)
            
        except Exception as e:
            logger.error("Failed to start background streaming: %s", e)
            background_manager = None
    else:
        logger.info("No tracked contracts configured - background streaming disabled")

    logger.info("🚀 IB Stream API Server startup complete - Unified Architecture Active")
    
    yield

    # Shutdown - Unified Architecture Cleanup
    logger.info("Shutting down IB Stream API Server...")
    
    # Stop background streaming
    if background_manager:
        logger.info("Stopping background streaming...")
        try:
            await background_manager.stop()
            logger.info("✅ Background streaming stopped")
        except Exception as e:
            logger.error("Error stopping background streaming: %s", e)
    
    # Stop storage system
    if storage:
        logger.info("Stopping storage system...")
        try:
            await storage.stop()
            logger.info("✅ Storage system stopped")
        except Exception as e:
            logger.error("Error stopping storage system: %s", e)
    
    # Stop unified connection manager (handles all stream cleanup)
    if unified_connection_manager:
        logger.info("Stopping unified connection manager...")
        try:
            await unified_connection_manager.stop()
            logger.info("✅ Unified connection manager stopped")
            logger.info("✅ All streams cancelled and connection closed")
        except Exception as e:
            logger.error("Error stopping unified connection manager: %s", e)

    logger.info("✅ IB Stream API Server shutdown complete")


def update_global_state(storage_obj=None, background_manager_obj=None, connection_manager_obj=None):
    """
    Update global state variables for health endpoints
    
    Updated for unified architecture - now includes connection_manager
    """
    global storage, background_manager, unified_connection_manager
    
    if storage_obj is not None:
        storage = storage_obj
    if background_manager_obj is not None:
        background_manager = background_manager_obj  
    if connection_manager_obj is not None:
        unified_connection_manager = connection_manager_obj


def get_app_state():
    """
    Get current application state for dependency injection
    
    Updated for unified architecture
    """
    # Ensure config is loaded if not already done
    global config
    if config is None:
        import os
        logger.debug("Loading config (first time)")
        logger.info(f"IB_ENVIRONMENT: {os.getenv('IB_ENVIRONMENT', 'NOT_SET')}")
        logger.info(f"IB_CLIENT_ID: {os.getenv('IB_CLIENT_ID', 'NOT_SET')}")
        logger.info(f"IB_HOST: {os.getenv('IB_HOST', 'NOT_SET')}")
        logger.info(f"IB_STREAM_ENABLE_BACKGROUND_STREAMING: {os.getenv('IB_STREAM_ENABLE_BACKGROUND_STREAMING', 'NOT_SET')}")
        logger.info(f"IB_STREAM_TRACKED_CONTRACTS: {os.getenv('IB_STREAM_TRACKED_CONTRACTS', 'NOT_SET')}")
        
        config = create_config()
        
        logger.debug("Config created")
        logger.info(f"Config client_id: {config.client_id}")
        logger.info(f"Config host: {config.host}")
        logger.info(f"Config storage enabled: {config.storage.enable_storage}")
        logger.info(f"Config background streaming: {getattr(config.storage, 'enable_background_streaming', 'NOT_FOUND')}")
        logger.info(f"Config tracked contracts: {len(getattr(config.storage, 'tracked_contracts', []))}")
        logger.debug("Config loading complete")
    else:
        # Config already exists and cached - use existing config
        logger.debug("Using cached configuration")
    
    # Get StreamingApp from unified connection manager
    streaming_app = None
    if unified_connection_manager and unified_connection_manager.is_connected:
        streaming_app = unified_connection_manager.streaming_app
    
    return {
        'config': config,
        'storage': storage,
        'background_manager': background_manager,
        'unified_connection_manager': unified_connection_manager,  # New: unified manager
        'tws_app': streaming_app,  # Legacy compatibility
        'active_streams': active_streams,
        'stream_lock': stream_lock,
        'ensure_tws_connection': ensure_tws_connection
    }


# Legacy compatibility functions for gradual migration

def get_legacy_tws_app():
    """Legacy compatibility: return StreamingApp from unified manager"""
    if unified_connection_manager and unified_connection_manager.is_connected:
        return unified_connection_manager.streaming_app
    return None


def is_connection_healthy() -> bool:
    """Check if unified connection is healthy"""
    return (unified_connection_manager is not None and 
            unified_connection_manager.is_connected)