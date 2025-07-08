#!/usr/bin/env python3
"""Test if the unknown error messages are suppressed."""

import asyncio
import sys
import signal
from ib_studies.models import StreamConfig, StudyConfig
from ib_studies.studies.multi_delta import MultiStreamDeltaStudy
from ib_studies.multi_stream_client import MultiStreamClient

async def run_test():
    """Run a short test to check error handling."""
    print("Starting 8-second test...")
    
    # Create study and client
    study_config = StudyConfig(window_seconds=60)
    study = MultiStreamDeltaStudy(study_config)
    
    stream_config = StreamConfig(timeout=5)  # 5 second timeout to trigger completion
    client = MultiStreamClient(stream_config)
    
    tick_count = 0
    
    async def handle_tick(tick_type, data):
        nonlocal tick_count
        result = study.process_tick(tick_type, data)
        if result:
            tick_count += 1
            if tick_count <= 3:  # Only show first few
                print(f"Tick {tick_count}: {result['current_trade']['price']} -> delta {result['current_trade']['delta']}")
    
    try:
        # Connect to streams with short timeout
        await client.connect_multiple(711280073, ["BidAsk", "Last"], handle_tick)
        
        # Wait for 8 seconds then stop
        await asyncio.sleep(8)
        
    except Exception as e:
        print(f"Exception: {e}")
    finally:
        print(f"Test complete. Processed {tick_count} ticks.")
        await client.stop()
        await client.disconnect_all()

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        print("Interrupted!")
    print("Done!")