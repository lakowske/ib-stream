#!/usr/bin/env python3
"""Demo script showing clean delta calculation."""

import asyncio
import signal
import sys
from ib_studies.models import StreamConfig, StudyConfig
from ib_studies.studies.multi_delta import MultiStreamDeltaStudy
from ib_studies.multi_stream_client import MultiStreamClient

async def run_demo():
    """Run a clean demo of delta calculation."""
    print("🚀 True Delta Analysis Demo")
    print("Contract: 711280073 (MNQ Futures)")
    print("=" * 50)
    
    # Create study and client
    study_config = StudyConfig(window_seconds=60)
    study = MultiStreamDeltaStudy(study_config)
    
    stream_config = StreamConfig(timeout=10)
    client = MultiStreamClient(stream_config)
    
    tick_count = 0
    stop_event = asyncio.Event()
    
    def signal_handler():
        print("\n⏹️  Stopping...")
        stop_event.set()
    
    # Set up signal handler
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, signal_handler)
    else:
        signal.signal(signal.SIGINT, lambda s, f: signal_handler())
    
    async def handle_tick(tick_type, data):
        nonlocal tick_count
        if stop_event.is_set():
            return
            
        result = study.process_tick(tick_type, data)
        if result:
            tick_count += 1
            trade = result['current_trade']
            quote = result['current_quote']
            stats = result['calculation_stats']
            
            print(f"📈 Tick {tick_count:3d}: Price ${trade['price']:8.2f} | "
                  f"Size {trade['size']:3.0f} | Delta {trade['delta']:+4.0f} | "
                  f"Bid ${quote['bid']:8.2f} | Ask ${quote['ask']:8.2f}")
            
            # Show stats every 10 ticks
            if tick_count % 10 == 0:
                print(f"📊 Stats: {stats['bid_hits']} bid hits, {stats['ask_hits']} ask hits, "
                      f"{stats['true_delta_percentage']:.1f}% classified")
                print("-" * 70)
    
    try:
        # Connect to streams
        await client.connect_multiple(711280073, ["BidAsk", "Last"], handle_tick)
        
        # Wait for stop signal or timeout
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30)
        except asyncio.TimeoutError:
            print("\n⏰ Timeout reached")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        print(f"\n✅ Demo complete! Processed {tick_count} ticks.")
        await client.stop()
        await client.disconnect_all()

if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    print("🏁 Done!")