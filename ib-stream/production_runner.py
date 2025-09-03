#!/usr/bin/env python3
"""
IB Stream Production Runner

Consistent entry point for production deployment using Service Orchestration.
This script is designed to be called by supervisor or systemd.

Usage:
    python production_runner.py [mode]
    
    Modes:
        full        - All services (IB + Storage + Web) [default]
        standalone  - IB + Storage services only (no web)
        ib-only     - IB service only
"""

import sys
import os
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "ib-util"))
sys.path.insert(0, str(project_root / "ib-stream" / "src"))

# Use production environment
os.environ["IB_ENVIRONMENT"] = "production" 
os.environ["IB_CONFIG_ROOT"] = str(project_root / "config")

def main():
    """Production main - delegate to debug_runner with production mode"""
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    
    print("🏭 IB Stream Production Deployment")
    print(f"Mode: {mode}")
    print()
    
    # Map production modes to debug_runner modes
    runner_mode_map = {
        "full": "production",
        "standalone": "standalone", 
        "ib-only": "standalone"  # For now, same as standalone
    }
    
    runner_mode = runner_mode_map.get(mode, "production")
    
    # Import and run the service runner
    from debug_runner import main as runner_main
    
    # Override sys.argv for the runner
    original_argv = sys.argv
    sys.argv = ["production_runner.py", runner_mode]
    
    try:
        runner_main()
    finally:
        sys.argv = original_argv

if __name__ == "__main__":
    main()