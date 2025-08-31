#!/usr/bin/env python3
"""
Standalone Debug Runner for IB Stream

This runner allows you to debug ib-stream directly in VS Code without
the complexity of supervisor. It uses Configuration System v3 and
provides the same functionality as the production service.

Usage:
    python debug_runner.py

This script:
1. Sets up the proper Python path
2. Loads Configuration System v3 
3. Starts the ib-stream API server
4. Enables all debugging features
"""

import sys
import os
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "ib-util"))
sys.path.insert(0, str(project_root / "ib-stream" / "src"))

# Set environment for Configuration System v3
os.environ["IB_ENVIRONMENT"] = "development" 
os.environ["IB_CONFIG_ROOT"] = str(project_root / "config")

def main():
    """Main debug runner function"""
    print("🐛 IB Stream Debug Runner")
    print("=" * 50)
    print("Configuration System v3 - Development Mode")
    print(f"Project Root: {project_root}")
    print(f"Config Root: {os.environ['IB_CONFIG_ROOT']}")
    print(f"Environment: {os.environ['IB_ENVIRONMENT']}")
    print()
    
    try:
        # Import and start the API server
        from ib_stream.api_server import create_app
        
        print("✓ Loading Configuration System v3...")
        app = create_app()
        
        print("✓ Configuration loaded successfully")
        print("✓ Starting ib-stream API server...")
        print()
        print("🚀 Ready for debugging!")
        print("   • Set breakpoints in VS Code")
        print("   • Use step-through debugging")
        print("   • Inspect configuration objects")
        print("   • Debug TWS connection issues")
        print()
        
        # Start the server with debug-friendly settings
        import uvicorn
        
        # Get server configuration
        from ib_stream.config import create_config
        config = create_config()
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8774,  # Use development port from instance config
            log_level="debug",
            reload=False,  # Disable reload for debugging
            access_log=True
        )
        
    except Exception as e:
        print(f"❌ Error starting debug runner: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()