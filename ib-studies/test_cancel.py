#!/usr/bin/env python3
"""Test script to verify signal handling and cancellation."""

import asyncio
import signal
import sys
import subprocess
import time

async def run_command():
    """Run the delta command and test cancellation."""
    print("Starting true-delta command...")
    
    # Start the command
    process = subprocess.Popen([
        sys.executable, "-m", "ib_studies.cli", 
        "true-delta", "--contract", "711280073", 
        "--timeout", "30", "--json"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Let it run for 3 seconds
    print("Letting it run for 3 seconds...")
    await asyncio.sleep(3)
    
    # Send SIGINT (Ctrl+C)
    print("Sending SIGINT...")
    process.send_signal(signal.SIGINT)
    
    # Wait a bit
    await asyncio.sleep(1)
    
    # Check if it's still running
    if process.poll() is None:
        print("Process still running after SIGINT, sending SIGTERM...")
        process.terminate()
        await asyncio.sleep(1)
    
    # Force kill if still running
    if process.poll() is None:
        print("Process still running, force killing...")
        process.kill()
    
    print(f"Process ended with return code: {process.returncode}")

if __name__ == "__main__":
    asyncio.run(run_command())