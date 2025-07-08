#!/usr/bin/env python3
"""Simple test of delta without hanging."""

import asyncio
import signal
import sys
from ib_studies.models import StreamConfig, StudyConfig
from ib_studies.studies.multi_delta import MultiStreamDeltaStudy
from ib_studies.multi_stream_client import MultiStreamClient
from ib_studies.formatters.json import JSONFormatter

stop_event = asyncio.Event()

def signal_handler(sig, frame):
    print("\nReceived signal, stopping...")
    stop_event.set()

async def run_test():
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create study and client
    study_config = StudyConfig(window_seconds=60)
    study = MultiStreamDeltaStudy(study_config)
    
    stream_config = StreamConfig(timeout=5)  # 5 second timeout
    client = MultiStreamClient(stream_config)
    
    formatter = JSONFormatter(pretty=False)
    
    tick_count = 0
    
    async def handle_tick(tick_type, data):
        nonlocal tick_count
        result = study.process_tick(tick_type, data)
        if result:
            tick_count += 1
            output = formatter.format_update(result)
            print(output)
            
            # Stop after 10 ticks for testing
            if tick_count >= 10:
                print("\nReceived 10 ticks, stopping...")
                stop_event.set()
    
    try:
        # Connect to streams
        await client.connect_multiple(711280073, ["BidAsk", "Last"], handle_tick)
        
        # Wait for stop or timeout
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=10)
        except asyncio.TimeoutError:
            print("\nTimeout reached, stopping...")
        
    finally:
        print("\nCleaning up...")
        await client.stop()
        await client.disconnect_all()
        print("Done!")

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        print("\nInterrupted!")
    sys.exit(0)