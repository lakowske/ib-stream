#!/usr/bin/env python3
"""
Standalone Debug Runner for IB Stream - UNIFIED ARCHITECTURE

This runner allows you to debug ib-stream directly in VS Code using the
new unified connection architecture. No supervisor complexity!

Features:
- Single UnifiedConnectionManager (no dual connections)
- BackgroundStreamManager v2 with shared connection  
- 50% resource reduction
- Configuration System v3
- Full debugging capabilities

Usage:
    python debug_runner.py

This script:
1. Sets up the proper Python path
2. Loads Configuration System v3 
3. Starts the UNIFIED ARCHITECTURE ib-stream API server
4. Enables all debugging features for single connection system
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
        # Configure logging for debug mode BEFORE creating the app
        print("✓ Setting up debug logging...")
        from ib_util.logging_config import configure_service_logging
        configure_service_logging("ib-stream", verbose=True)
        
        # Import and create the FastAPI app with UNIFIED ARCHITECTURE
        print("✓ Loading Configuration System v3...")
        
        # Import the unified architecture app
        from ib_stream.unified_app import create_unified_app
        app = create_unified_app()
        
        print("✓ Unified Architecture - Single Connection System")
        
        print("✓ Configuration loaded successfully")
        print("✓ FastAPI app created with Unified Architecture")
        print("✓ Starting ib-stream API server...")
        print()
        print("🚀 Ready for debugging UNIFIED ARCHITECTURE!")
        print("   • Set breakpoints in VS Code")
        print("   • Use step-through debugging") 
        print("   • Debug single UnifiedConnectionManager")
        print("   • Debug shared connection for all streams")
        print("   • Observe 50% resource reduction")
        print("   • Server running on http://0.0.0.0:8774")
        print()
        
        # Start the server with debug-friendly settings
        import uvicorn
        
        uvicorn.run(
            app,  # Now passing the actual FastAPI app
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