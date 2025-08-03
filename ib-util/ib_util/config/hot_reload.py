"""
Configuration hot-reload functionality.

Provides file watching and automatic configuration reloading for development.
"""

import os
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Set, Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .loader import ConfigLoader
from .base import IBBaseConfig

logger = logging.getLogger(__name__)


class ConfigFileHandler(FileSystemEventHandler):
    """Handle configuration file change events."""
    
    def __init__(self, reload_callback: Callable[[str], None]):
        self.reload_callback = reload_callback
        self.last_reload = {}
        self.debounce_seconds = 1.0
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        file_path = event.src_path
        if not file_path.endswith('.env'):
            return
        
        # Debounce rapid file changes
        now = time.time()
        if file_path in self.last_reload:
            if now - self.last_reload[file_path] < self.debounce_seconds:
                return
        
        self.last_reload[file_path] = now
        
        logger.info(f"Configuration file changed: {file_path}")
        self.reload_callback(file_path)


class ConfigHotReloader:
    """
    Hot-reload configuration files during development.
    
    Watches .env files for changes and automatically reloads configuration
    when files are modified.
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.config_loader = ConfigLoader(str(self.project_root))
        self.observer = None
        self.callbacks: Dict[str, Set[Callable[[IBBaseConfig], None]]] = {}
        self.current_configs: Dict[str, IBBaseConfig] = {}
        self.lock = threading.Lock()
    
    def register_callback(self, service_name: str, callback: Callable[[IBBaseConfig], None]):
        """Register a callback to be called when configuration changes."""
        with self.lock:
            if service_name not in self.callbacks:
                self.callbacks[service_name] = set()
            self.callbacks[service_name].add(callback)
    
    def unregister_callback(self, service_name: str, callback: Callable[[IBBaseConfig], None]):
        """Unregister a configuration change callback."""
        with self.lock:
            if service_name in self.callbacks:
                self.callbacks[service_name].discard(callback)
                if not self.callbacks[service_name]:
                    del self.callbacks[service_name]
    
    def _on_config_change(self, file_path: str):
        """Handle configuration file changes."""
        try:
            # Determine which services might be affected
            affected_services = self._get_affected_services(file_path)
            
            with self.lock:
                for service_name in affected_services:
                    if service_name in self.callbacks:
                        try:
                            # Reload configuration
                            new_config = self.config_loader.create_service_config(service_name)
                            old_config = self.current_configs.get(service_name)
                            
                            # Check if configuration actually changed
                            if old_config is None or self._config_changed(old_config, new_config):
                                self.current_configs[service_name] = new_config
                                
                                # Notify all callbacks
                                for callback in self.callbacks[service_name]:
                                    try:
                                        callback(new_config)
                                    except Exception as e:
                                        logger.error(f"Error in config reload callback for {service_name}: {e}")
                                
                                logger.info(f"Configuration reloaded for service: {service_name}")
                        
                        except Exception as e:
                            logger.error(f"Failed to reload configuration for {service_name}: {e}")
        
        except Exception as e:
            logger.error(f"Error handling configuration change: {e}")
    
    def _get_affected_services(self, file_path: str) -> Set[str]:
        """Determine which services might be affected by a file change."""
        file_name = Path(file_path).name
        
        # Service-specific files
        if 'stream' in file_name or 'ib-stream' in file_name:
            return {'ib-stream'}
        elif 'contract' in file_name or 'ib-contract' in file_name:
            return {'ib-contract'}
        elif 'studies' in file_name or 'ib-studies' in file_name:
            return {'ib-studies'}
        
        # Instance and global files affect all services
        if file_name in ['instance.env', 'production.env', 'development.env', '.env']:
            return {'ib-stream', 'ib-contract', 'ib-studies'}
        
        # Default: might affect all services
        return {'ib-stream', 'ib-contract', 'ib-studies'}
    
    def _config_changed(self, old_config: IBBaseConfig, new_config: IBBaseConfig) -> bool:
        """Check if configuration has meaningfully changed."""
        try:
            # Compare serialized configurations
            old_dict = old_config.dict()
            new_dict = new_config.dict()
            return old_dict != new_dict
        except Exception:
            # If comparison fails, assume it changed
            return True
    
    def start(self, watch_paths: Optional[list] = None):
        """Start watching configuration files for changes."""
        if self.observer is not None:
            logger.warning("Hot reload is already running")
            return
        
        if watch_paths is None:
            watch_paths = [
                self.project_root / "ib-stream" / "config",
                self.project_root / "config",
                self.project_root,  # For root .env files
            ]
        
        # Filter to existing paths
        existing_paths = []
        for path in watch_paths:
            path = Path(path)
            if path.exists():
                existing_paths.append(str(path))
            else:
                logger.debug(f"Watch path does not exist: {path}")
        
        if not existing_paths:
            logger.warning("No configuration directories found to watch")
            return
        
        self.observer = Observer()
        handler = ConfigFileHandler(self._on_config_change)
        
        for path in existing_paths:
            self.observer.schedule(handler, path, recursive=True)
            logger.info(f"Watching configuration directory: {path}")
        
        self.observer.start()
        logger.info("Configuration hot-reload started")
    
    def stop(self):
        """Stop watching configuration files."""
        if self.observer is not None:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logger.info("Configuration hot-reload stopped")
    
    def get_current_config(self, service_name: str) -> Optional[IBBaseConfig]:
        """Get the current configuration for a service."""
        with self.lock:
            return self.current_configs.get(service_name)
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


# Convenience functions for common use cases

def create_hot_reloader(project_root: str = None) -> ConfigHotReloader:
    """Create a configuration hot-reloader for the current project."""
    if project_root is None:
        project_root = os.environ.get('PROJECT_ROOT', os.getcwd())
    
    return ConfigHotReloader(project_root)


def watch_config_changes(service_name: str, callback: Callable[[IBBaseConfig], None], 
                        project_root: str = None) -> ConfigHotReloader:
    """
    Convenience function to start watching configuration changes for a service.
    
    Returns the hot-reloader instance so you can stop it later.
    """
    reloader = create_hot_reloader(project_root)
    reloader.register_callback(service_name, callback)
    reloader.start()
    return reloader


# Example usage
if __name__ == "__main__":
    def on_stream_config_change(config: IBBaseConfig):
        print(f"ib-stream configuration changed:")
        print(f"  Host: {config.connection.host}")
        print(f"  Port: {config.server.port}")
        print(f"  Client ID: {config.connection.client_id}")
    
    # Start watching configuration changes
    reloader = watch_config_changes('ib-stream', on_stream_config_change)
    
    try:
        print("Watching for configuration changes... Press Ctrl+C to stop")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping configuration watcher...")
        reloader.stop()