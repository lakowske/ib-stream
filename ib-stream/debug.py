#!/usr/bin/env python3
"""
Standalone Development Runner for IB-Stream

This script allows you to run ib-stream directly for debugging without supervisor.
It loads configuration from YAML files and provides a clean development environment.

Usage:
    python debug.py                    # Run with default development config
    python debug.py --port 8080        # Override port
    python debug.py --env production    # Use production config
    python debug.py --config ../config # Use custom config directory
"""

import argparse
import os
import sys
from pathlib import Path

# Add the src and ib-util directories to the path so we can import our modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(project_root / "ib-util"))

def setup_environment():
    """Setup development environment defaults"""
    # Set default environment if not specified
    if not os.getenv('IB_ENVIRONMENT'):
        os.environ['IB_ENVIRONMENT'] = 'development'
    
    # Set config root to project config directory  
    config_root = project_root / "config"
    os.environ.setdefault('IB_CONFIG_ROOT', str(config_root))
    
    print(f"🔧 Development Environment Setup")
    print(f"   Environment: {os.getenv('IB_ENVIRONMENT')}")
    print(f"   Config Root: {os.getenv('IB_CONFIG_ROOT')}")
    print(f"   Project Root: {project_root}")
    print()


def load_config(config_override_path=None):
    """Load configuration using the v3 system"""
    try:
        from ib_util.config_v3 import load_config
        
        config_root = config_override_path or os.getenv('IB_CONFIG_ROOT')
        config = load_config('ib-stream', config_root)
        
        print(f"📋 Configuration Loaded")
        print(f"   Environment: {config.project.environment}")
        print(f"   Server: {config.service.server.host}:{config.service.server.port}")
        print(f"   Gateway: {config.gateway.host}:{config.gateway.ports}")
        print(f"   Client ID: {config.service.client.id}")
        print(f"   Storage: {config.storage.base_path} ({'enabled' if config.storage.enabled else 'disabled'})")
        print(f"   Log Level: {config.logging.level}")
        print()
        
        return config
        
    except Exception as e:
        print(f"❌ Configuration Error: {e}")
        print("\nTroubleshooting:")
        print("- Ensure config files exist in config/ directory")
        print("- Check YAML syntax in configuration files")
        print("- Verify IB_ENVIRONMENT is set correctly")
        sys.exit(1)


def main():
    """Main debug runner"""
    parser = argparse.ArgumentParser(description="Debug runner for ib-stream")
    parser.add_argument('--port', type=int, help='Override server port')
    parser.add_argument('--host', default='0.0.0.0', help='Override server host')
    parser.add_argument('--env', choices=['development', 'production'], 
                       help='Override environment')
    parser.add_argument('--config', help='Override config directory path')
    parser.add_argument('--no-reload', action='store_true', 
                       help='Disable auto-reload for debugging')
    parser.add_argument('--validate-only', action='store_true',
                       help='Only validate configuration, do not start server')
    
    args = parser.parse_args()
    
    # Apply overrides
    if args.env:
        os.environ['IB_ENVIRONMENT'] = args.env
    
    setup_environment()
    config = load_config(args.config)
    
    if args.validate_only:
        print("✅ Configuration validation successful!")
        return
    
    # Apply command line overrides
    server_host = args.host or config.service.server.host
    server_port = args.port or config.service.server.port
    
    print(f"🚀 Starting IB-Stream Debug Server")
    print(f"   Server: http://{server_host}:{server_port}")
    print(f"   Auto-reload: {'disabled' if args.no_reload else 'enabled'}")
    print(f"   Environment: {config.project.environment}")
    print()
    print("💡 Debugging Tips:")
    print("   - Set breakpoints in your IDE and attach to this process")
    print("   - Configuration loaded from YAML files (no supervisor complexity)")
    print("   - Press Ctrl+C to stop the server")
    print()
    
    try:
        import uvicorn
        
        # Set environment variables for the running server
        os.environ['IB_SERVER_PORT'] = str(server_port)
        os.environ['IB_CLIENT_ID'] = str(config.service.client.id)
        
        # Run the server
        uvicorn.run(
            "ib_stream.api_server:app",
            host=server_host,
            port=server_port,
            reload=not args.no_reload,
            log_level=config.logging.level.lower(),
            reload_dirs=["src"] if not args.no_reload else None
        )
        
    except KeyboardInterrupt:
        print("\n👋 Shutting down debug server")
    except ImportError:
        print("❌ Error: uvicorn not found. Install with: pip install uvicorn")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Server Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()