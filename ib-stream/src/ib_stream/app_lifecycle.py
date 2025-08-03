"""
Application lifecycle management for the IB Stream API
Handles startup, shutdown, and global state management
"""

import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import HTTPException

from .config_v2 import create_legacy_compatible_config
from .storage import MultiStorage
from .storage.multi_storage_v3 import MultiStorageV3
from .streaming_app import StreamingApp
from .stream_manager import stream_manager
from .background_stream_manager import BackgroundStreamManager

logger = logging.getLogger(__name__)

# Global state
config = None  # Will be loaded in lifespan startup
tws_app: Optional[StreamingApp] = None
tws_lock = threading.Lock()
storage: Optional[MultiStorageV3] = None
background_manager: Optional[BackgroundStreamManager] = None
active_streams = {}
stream_lock = threading.Lock()


def ensure_tws_connection() -> StreamingApp:
    """Ensure TWS connection is active"""
    global tws_app

    with tws_lock:
        # Check if we already have a working connection
        if tws_app is not None and tws_app.is_connected():
            logger.debug("Using existing TWS connection")
            return tws_app
            
        logger.info("Establishing TWS connection...")
        tws_app = StreamingApp(json_output=True)
        
        if not tws_app.connect_and_start():
            msg = "Unable to connect to TWS/Gateway. Please ensure it's running with API enabled."
            raise HTTPException(status_code=503, detail=msg)

        logger.info("TWS connection established successfully with client ID %d", tws_app.config.client_id)

    return tws_app


@asynccontextmanager
async def lifespan(_):
    """Lifespan event handler for startup/shutdown"""
    # Startup - Load configuration with current environment variables
    global config
    config = create_legacy_compatible_config()
    
    logger.info("Starting IB Stream API Server...")
    logger.info("Configuration:")
    logger.info("  Client ID: %d", config.client_id)  
    logger.info("  Host: %s", config.host)
    logger.info("  Ports: %s", config.ports)
    logger.info("  Max Streams: %d", config.max_concurrent_streams)
    if config.default_timeout_seconds is not None:
        logger.info("  Default Timeout: %d seconds", config.default_timeout_seconds)
    else:
        logger.info("  Default Timeout: No timeout (unlimited)")
    
    # Initialize storage system
    global storage
    if config.storage.enable_storage:
        logger.info("Initializing storage system...")
        logger.info("  Storage path: %s", config.storage.storage_base_path)
        logger.info("  JSON enabled: %s", config.storage.enable_json)
        logger.info("  Protobuf enabled: %s", config.storage.enable_protobuf)
        logger.info("  PostgreSQL enabled: %s", config.storage.enable_postgres_index)
        
        try:
            storage = MultiStorageV3(
                storage_path=config.storage.storage_base_path,
                enable_v2_json=config.storage.enable_json,
                enable_v2_protobuf=config.storage.enable_protobuf,
                enable_v3_json=True,  # Enable v3 JSON storage by default
                enable_v3_protobuf=True,  # Enable v3 Protobuf storage by default
                enable_metrics=config.storage.enable_metrics
            )
            await storage.start()
            logger.info("Storage system initialized successfully")
            
            # Initialize stream_manager with storage and client stream storage config
            stream_manager.storage = storage
            stream_manager.enable_client_stream_storage = config.storage.enable_client_stream_storage
            logger.info("Stream manager configured with storage, client stream storage: %s", 
                       "enabled" if config.storage.enable_client_stream_storage else "disabled")
            
        except Exception as e:
            logger.error("Failed to initialize storage system: %s", e)
            logger.info("Continuing without storage...")
            storage = None
    else:
        logger.info("Storage system disabled")
        # Still configure stream_manager with client stream storage setting
        stream_manager.enable_client_stream_storage = config.storage.enable_client_stream_storage

    logger.info("Attempting to establish TWS connection...")
    try:
        ensure_tws_connection()
        logger.info("TWS connection established successfully")
    except Exception as e:
        logger.warning("Failed to establish initial TWS connection: %s", e)
        logger.info("Will attempt to connect on first streaming request")
    
    # Initialize background streaming for tracked contracts
    global background_manager
    if config.storage.tracked_contracts:
        logger.info("Initializing background streaming for %d tracked contracts...", 
                   len(config.storage.tracked_contracts))
        
        try:
            background_manager = BackgroundStreamManager(
                tracked_contracts=config.storage.tracked_contracts,
                reconnect_delay=config.storage.background_stream_reconnect_delay
            )
            await background_manager.start()
            logger.info("Background streaming started successfully")
            
            # Log tracked contracts
            for contract in config.storage.tracked_contracts:
                logger.info("  Tracking contract %d (%s): %s, buffer=%dh", 
                           contract.contract_id, contract.symbol, 
                           contract.tick_types, contract.buffer_hours)
            
        except Exception as e:
            logger.error("Failed to start background streaming: %s", e)
            background_manager = None
    else:
        logger.info("No tracked contracts configured - background streaming disabled")

    yield

    # Shutdown
    logger.info("Shutting down IB Stream API Server...")
    global tws_app
    
    # Stop background streaming
    if background_manager:
        logger.info("Stopping background streaming...")
        try:
            await background_manager.stop()
            logger.info("Background streaming stopped")
        except Exception as e:
            logger.error("Error stopping background streaming: %s", e)
    
    # Stop storage system
    if storage:
        logger.info("Stopping storage system...")
        try:
            await storage.stop()
            logger.info("Storage system stopped")
        except Exception as e:
            logger.error("Error stopping storage system: %s", e)
    
    if tws_app and tws_app.is_connected():
        # Stop all active streams
        with stream_lock:
            for stream_id in list(active_streams.keys()):
                try:
                    tws_app.cancelTickByTickData(stream_id)
                except Exception as e:
                    logger.warning("Error cancelling stream %s: %s", stream_id, e)
            active_streams.clear()

        tws_app.disconnect_and_stop()
        logger.info("TWS connection closed")


def update_global_state(storage_obj=None, background_manager_obj=None, tws_app_obj=None):
    """Update global state variables for health endpoints"""
    global storage, background_manager, tws_app
    
    if storage_obj is not None:
        storage = storage_obj
    if background_manager_obj is not None:
        background_manager = background_manager_obj  
    if tws_app_obj is not None:
        tws_app = tws_app_obj


def get_app_state():
    """Get current application state for dependency injection"""
    # Ensure config is loaded if not already done
    global config
    if config is None:
        import os
        logger.info("=== CONFIG DEBUG: Loading config (first time) ===")
        logger.info(f"IB_ENVIRONMENT: {os.getenv('IB_ENVIRONMENT', 'NOT_SET')}")
        logger.info(f"IB_CLIENT_ID: {os.getenv('IB_CLIENT_ID', 'NOT_SET')}")
        logger.info(f"IB_HOST: {os.getenv('IB_HOST', 'NOT_SET')}")
        logger.info(f"IB_STREAM_ENABLE_BACKGROUND_STREAMING: {os.getenv('IB_STREAM_ENABLE_BACKGROUND_STREAMING', 'NOT_SET')}")
        logger.info(f"IB_STREAM_TRACKED_CONTRACTS: {os.getenv('IB_STREAM_TRACKED_CONTRACTS', 'NOT_SET')}")
        
        config = create_legacy_compatible_config()
        
        logger.info(f"=== CONFIG DEBUG: Config created ===")
        logger.info(f"Config client_id: {config.client_id}")
        logger.info(f"Config host: {config.host}")
        logger.info(f"Config storage enabled: {config.storage.enable_storage}")
        logger.info(f"Config background streaming: {getattr(config.storage, 'enable_background_streaming', 'NOT_FOUND')}")
        logger.info(f"Config tracked contracts: {len(getattr(config.storage, 'tracked_contracts', []))}")
        logger.info("=== CONFIG DEBUG: End ===")
    else:
        # Config already exists - let's force reload it to pick up current env vars
        import os
        logger.info("=== CONFIG DEBUG: Reloading existing config ===")
        logger.info(f"Current IB_STREAM_ENABLE_BACKGROUND_STREAMING: {os.getenv('IB_STREAM_ENABLE_BACKGROUND_STREAMING', 'NOT_SET')}")
        logger.info(f"Current config background streaming: {getattr(config.storage, 'enable_background_streaming', 'NOT_FOUND')}")
        
        # Force reload
        config = create_legacy_compatible_config()
        logger.info(f"Reloaded config background streaming: {getattr(config.storage, 'enable_background_streaming', 'NOT_FOUND')}")
        logger.info("=== CONFIG DEBUG: Reload complete ===")
    
    return {
        'config': config,
        'storage': storage,
        'background_manager': background_manager,
        'tws_app': tws_app,
        'active_streams': active_streams,
        'stream_lock': stream_lock,
        'ensure_tws_connection': ensure_tws_connection
    }