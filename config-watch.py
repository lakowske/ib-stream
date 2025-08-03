#!/usr/bin/env python3
"""
Configuration hot-reload testing tool.

Watch configuration files and show changes in real-time.
Useful for development and testing configuration changes.
"""

import sys
import time
import argparse
from pathlib import Path

# Add ib-util to path
sys.path.insert(0, 'ib-util')

try:
    from ib_util.config.hot_reload import create_hot_reloader
    from ib_util.config.base import IBBaseConfig
except ImportError as e:
    print(f"Error importing hot-reload modules: {e}")
    print("Make sure to run: make dev-tools")
    sys.exit(1)


def format_config_summary(config: IBBaseConfig) -> str:
    """Format configuration summary for display."""
    lines = [
        f"Service: {config.service_name}",
        f"Environment: {config.environment}",
        f"Connection:",
        f"  Host: {config.connection.host}",
        f"  Ports: {config.connection.ports}",
        f"  Client ID: {config.connection.client_id}",
        f"Server:",
        f"  Host: {config.server.host}",
        f"  Port: {config.server.port}",
        f"  Log Level: {config.server.log_level}",
        f"Storage:",
        f"  Enabled: {config.storage.enable_storage}",
        f"  Path: {config.storage.storage_path}",
    ]
    return "\n".join(f"  {line}" for line in lines)


def on_config_change(service_name: str, config: IBBaseConfig):
    """Handle configuration changes."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"\n[{timestamp}] Configuration changed for {service_name}:")
    print(format_config_summary(config))
    print("-" * 60)


def main():
    parser = argparse.ArgumentParser(description="Watch configuration files for changes")
    parser.add_argument(
        "--service", 
        choices=["ib-stream", "ib-contract", "ib-studies", "all"],
        default="all",
        help="Service to watch (default: all)"
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root directory (default: current directory)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only show changes, not initial configuration"
    )
    
    args = parser.parse_args()
    
    # Create hot-reloader
    try:
        reloader = create_hot_reloader(args.project_root)
    except Exception as e:
        print(f"Error creating hot-reloader: {e}")
        sys.exit(1)
    
    # Determine services to watch
    if args.service == "all":
        services = ["ib-stream", "ib-contract", "ib-studies"]
    else:
        services = [args.service]
    
    # Register callbacks
    for service in services:
        callback = lambda config, svc=service: on_config_change(svc, config)
        reloader.register_callback(service, callback)
    
    # Show initial configurations
    if not args.quiet:
        print("Initial configuration:")
        print("=" * 60)
        for service in services:
            try:
                # Try to load current configuration
                from ib_util.config.compat import create_compatible_config
                config = create_compatible_config(service)
                print(f"\n{service}:")
                print(format_config_summary(config))
            except Exception as e:
                print(f"\n{service}: Error loading configuration - {e}")
        
        print("\n" + "=" * 60)
        print("Watching for configuration changes...")
        print("Edit .env files in ib-stream/config/ to see changes")
        print("Press Ctrl+C to stop")
        print("=" * 60)
    
    # Start watching
    try:
        reloader.start()
        
        # Keep running
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n\nStopping configuration watcher...")
        reloader.stop()
        print("Configuration watcher stopped.")


if __name__ == "__main__":
    main()