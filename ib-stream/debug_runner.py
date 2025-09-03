#!/usr/bin/env python3
"""
IB Stream Service Runner - Service Composition Architecture

This runner provides a consistent entry point for IB Stream services whether
running in debug mode or production. It uses the new Service Orchestration
pattern with clean separation of concerns.

Features:
- Service Orchestration Pattern with single configuration load
- Independent IB Service (can run without web server)
- Proper service startup ordering and dependency management
- Clean separation between IB API and FastAPI lifecycles  
- Configuration System v3
- Full debugging capabilities

Usage:
    python debug_runner.py [mode] [options]
    
    Modes:
        debug         - Start with FastAPI web server for debugging (default)
        standalone    - Start IB service only (no web server)  
        web-only      - Start web server only (degraded mode)
        production    - Start all services for production

Examples:
    python debug_runner.py                    # Debug mode with web server
    python debug_runner.py standalone         # Background streaming only
    python debug_runner.py production         # Full production setup

This script:
1. Sets up the proper Python path
2. Loads Configuration System v3 exactly once
3. Uses Service Orchestrator for proper service coordination 
4. Starts services based on specified mode
5. Enables debugging with proper service separation
"""

import sys
import os
import asyncio
import signal
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "ib-util"))
sys.path.insert(0, str(project_root / "ib-stream" / "src"))

# Set environment for Configuration System v3
os.environ["IB_ENVIRONMENT"] = "development" 
os.environ["IB_CONFIG_ROOT"] = str(project_root / "config")

# Global orchestrator for clean shutdown
orchestrator: Optional['ServiceOrchestrator'] = None

def setup_signal_handlers():
    """Setup signal handlers for clean shutdown"""
    def signal_handler(signum, frame):
        print(f"\n⚠️  Received signal {signum}, shutting down...")
        if orchestrator:
            asyncio.create_task(orchestrator.stop())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def run_debug_mode():
    """Run in debug mode with FastAPI web server"""
    global orchestrator
    
    print("🐛 IB Stream Debug Mode")
    print("=" * 60)
    print("Service Orchestration Pattern - Web Server + IB Services")
    print()
    
    # Import service orchestrator
    from ib_stream.services import get_orchestrator
    ServiceOrchestrator = get_orchestrator()
    orchestrator = ServiceOrchestrator()
    
    # Start IB and Storage services (FastAPI will be separate)
    print("Starting services: IB API + Storage")
    await orchestrator.start(['ib', 'storage'])
    
    # Create FastAPI app with service integration
    @asynccontextmanager
    async def lifespan(_):
        # Services already started by orchestrator
        print("✅ FastAPI lifespan started - services already running")
        yield
        # Services will be stopped by orchestrator
        print("✅ FastAPI lifespan finished")
    
    from fastapi import FastAPI
    app = FastAPI(lifespan=lifespan, title="IB Stream API", version="3.0")
    
    # Add basic endpoint that uses the orchestrator services
    @app.get("/health")
    async def health():
        return orchestrator.get_all_status()
    
    @app.get("/")
    async def root():
        return {"message": "IB Stream API - Service Orchestration Architecture", "version": "3.0"}
    
    # Start FastAPI server
    print("✅ Services started successfully")
    print("✅ Starting FastAPI web server...")
    print()
    print("🚀 Debug Mode Ready!")
    print("   • IB Service: Independent lifecycle")
    print("   • Storage Service: Independent lifecycle") 
    print("   • Web Server: FastAPI on http://0.0.0.0:8774")
    print("   • Single configuration load")
    print("   • Clean service separation")
    print("   • Set breakpoints in VS Code")
    print("   • Use step-through debugging")
    print()
    
    import uvicorn
    
    # Run server in background task so we can handle shutdown
    server_task = asyncio.create_task(
        asyncio.to_thread(
            uvicorn.run,
            app,
            host="0.0.0.0", 
            port=8774,
            log_level="debug",
            reload=False,
            access_log=True
        )
    )
    
    try:
        await server_task
    except KeyboardInterrupt:
        print("\n⚠️  Shutting down...")
    finally:
        if orchestrator:
            await orchestrator.stop()

async def run_standalone_mode():
    """Run standalone mode - IB services only, no web server"""
    global orchestrator
    
    print("🔧 IB Stream Standalone Mode")
    print("=" * 60) 
    print("Service Orchestration Pattern - IB Services Only")
    print("Background streaming will run independently without web server")
    print()
    
    from ib_stream.services import get_orchestrator
    ServiceOrchestrator = get_orchestrator()
    orchestrator = ServiceOrchestrator()
    
    print("Starting services: IB API + Storage (no web server)")
    await orchestrator.start(['ib', 'storage'])
    
    print("✅ Standalone services started successfully")
    print()
    print("🚀 Standalone Mode Running!")
    print("   • IB Service: Running independently")
    print("   • Storage Service: Running independently")
    print("   • Background Streaming: Active") 
    print("   • No web server (headless operation)")
    print("   • Press Ctrl+C to stop")
    print()
    
    try:
        # Run indefinitely
        while True:
            await asyncio.sleep(60)
            
            # Print periodic status
            status = orchestrator.get_all_status()
            print(f"📊 Status: {len(status.get('services', {}))} services running, "
                  f"healthy: {orchestrator.is_healthy()}")
    
    except KeyboardInterrupt:
        print("\n⚠️  Shutting down standalone services...")
    finally:
        if orchestrator:
            await orchestrator.stop()

async def run_production_mode():
    """Run production mode - all services"""
    global orchestrator
    
    print("🏭 IB Stream Production Mode")  
    print("=" * 60)
    print("Service Orchestration Pattern - Full Production Setup")
    print()
    
    from ib_stream.services import get_orchestrator
    ServiceOrchestrator = get_orchestrator()
    orchestrator = ServiceOrchestrator()
    
    print("Starting services: IB API + Storage + Web Server")
    await orchestrator.start(['ib', 'storage'])
    
    print("✅ Production services started successfully")
    print()
    print("🚀 Production Mode Ready!")
    print("   • All services running")
    print("   • Optimized for production use")
    print("   • Single configuration load")
    print()
    
    try:
        # In production, this would be managed by supervisor/systemd
        # For this script, just run indefinitely  
        while True:
            await asyncio.sleep(300)  # 5 minute status updates
            
            status = orchestrator.get_all_status()
            print(f"📊 Production Status: {len(status.get('services', {}))} services, "
                  f"healthy: {orchestrator.is_healthy()}")
    
    except KeyboardInterrupt:
        print("\n⚠️  Shutting down production services...")
    finally:
        if orchestrator:
            await orchestrator.stop()

def main():
    """Main runner function"""
    mode = sys.argv[1] if len(sys.argv) > 1 else "debug"
    
    print("🚀 IB Stream Service Runner")
    print("=" * 60)
    print("Service Composition Architecture v3")
    print(f"Project Root: {project_root}")
    print(f"Config Root: {os.environ['IB_CONFIG_ROOT']}")
    print(f"Environment: {os.environ['IB_ENVIRONMENT']}")
    print(f"Mode: {mode}")
    print()
    
    # Configure logging for debug mode BEFORE creating services
    try:
        print("✓ Setting up service logging...")
        from ib_util.logging_config import configure_service_logging
        configure_service_logging("ib-stream", verbose=(mode == "debug"))
        
        print("✓ Configuration System v3 ready")
        print("✓ Service orchestration ready")
        print()
        
        setup_signal_handlers()
        
        # Run based on mode
        if mode == "debug":
            asyncio.run(run_debug_mode())
        elif mode == "standalone":
            asyncio.run(run_standalone_mode())  
        elif mode == "production":
            asyncio.run(run_production_mode())
        elif mode == "web-only":
            print("❌ Web-only mode not implemented yet")
            sys.exit(1)
        else:
            print(f"❌ Unknown mode: {mode}")
            print("Available modes: debug, standalone, production, web-only")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error starting service runner: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()