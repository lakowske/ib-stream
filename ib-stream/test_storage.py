#!/usr/bin/env python3
"""
Test script for IB Stream storage system.

Tests the MultiStorage system with JSON and protobuf backends
without requiring PostgreSQL or TWS connection.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from ib_stream.storage import MultiStorage


async def test_storage():
    """Test the storage system with sample data."""
    
    print("🧪 Testing IB Stream Storage System")
    print("=" * 50)
    
    # Create storage directory
    storage_path = Path("./test_storage")
    storage_path.mkdir(exist_ok=True)
    
    # Initialize storage (disable PostgreSQL for this test)
    storage = MultiStorage(
        storage_path=storage_path,
        enable_json=True,
        enable_protobuf=True,
        enable_metrics=True
    )
    
    try:
        # Start storage system
        print("📦 Starting storage system...")
        await storage.start()
        
        # Create sample tick messages
        sample_messages = []
        base_time = datetime.now(timezone.utc)
        
        for i in range(50):
            # Simulate different types of tick data
            tick_types = ["bid_ask", "last", "mid_point"]
            tick_type = tick_types[i % len(tick_types)]
            
            if tick_type == "bid_ask":
                data = {
                    "contract_id": 265598,  # AAPL
                    "tick_type": tick_type,
                    "bid_price": 175.25 + (i * 0.01),
                    "bid_size": 100 + (i * 10),
                    "ask_price": 175.26 + (i * 0.01),
                    "ask_size": 150 + (i * 5),
                    "exchange": "SMART"
                }
            elif tick_type == "last":
                data = {
                    "contract_id": 265598,
                    "tick_type": tick_type,
                    "price": 175.25 + (i * 0.01),
                    "size": 100 + (i * 10),
                    "exchange": "SMART"
                }
            else:  # mid_point
                data = {
                    "contract_id": 265598,
                    "tick_type": tick_type,
                    "mid_price": 175.255 + (i * 0.01),
                    "exchange": "SMART"
                }
            
            # Create v2 protocol message
            message = {
                "type": "tick",
                "stream_id": f"test_stream_{i // 10}",
                "timestamp": base_time.isoformat(),
                "data": data,
                "metadata": {
                    "source": "test_script",
                    "sequence": i
                }
            }
            
            sample_messages.append(message)
        
        # Store messages
        print(f"💾 Storing {len(sample_messages)} sample messages...")
        
        for i, message in enumerate(sample_messages):
            await storage.store_message(message)
            
            # Show progress
            if (i + 1) % 10 == 0:
                print(f"   Stored {i + 1}/{len(sample_messages)} messages...")
        
        # Wait for all writes to complete
        print("⏳ Waiting for writes to complete...")
        await asyncio.sleep(2)
        
        # Get metrics
        metrics = storage.get_metrics()
        if metrics:
            print("\n📊 Storage Metrics:")
            print(f"   Overall messages received: {metrics['overall']['messages_received']}")
            print(f"   Overall messages written: {metrics['overall']['messages_written']}")
            print(f"   Overall write rate: {metrics['overall']['write_rate_per_second']:.2f} msg/sec")
            print(f"   Overall error rate: {metrics['overall']['error_rate']:.4f}")
            
            for backend, stats in metrics['backends'].items():
                print(f"\n   {backend.upper()} Backend:")
                print(f"     Messages written: {stats['messages']['written']}")
                print(f"     Success rate: {stats['messages']['success_rate']:.4f}")
                print(f"     Avg batch time: {stats['performance']['avg_batch_time_ms']:.2f}ms")
                print(f"     Files created: {stats['files']['files_created']}")
                print(f"     MB written: {stats['files']['mb_written']}")
        
        # Get storage info
        info = storage.get_storage_info()
        print(f"\n🗂️  Storage Info:")
        print(f"   Enabled formats: {info['enabled_formats']}")
        print(f"   Storage path: {info['storage_path']}")
        print(f"   Queue sizes: {info['queue_sizes']}")
        
        # Check generated files
        print(f"\n📁 Generated Files:")
        for format_dir in storage_path.iterdir():
            if format_dir.is_dir():
                print(f"   {format_dir.name}/")
                for file_path in format_dir.rglob("*"):
                    if file_path.is_file():
                        size_mb = file_path.stat().st_size / 1024 / 1024
                        rel_path = file_path.relative_to(storage_path)
                        print(f"     {rel_path} ({size_mb:.3f} MB)")
        
        # Test query functionality (JSON only for now)
        print(f"\n🔍 Testing Query Functionality...")
        try:
            results = await storage.query_range(
                contract_id=265598,
                tick_types=["bid_ask", "last"],
                start_time=base_time,
                storage_format="json"
            )
            print(f"   Found {len(results)} messages in query")
            if results:
                print(f"   First message: {results[0]['type']} at {results[0]['timestamp']}")
                print(f"   Last message: {results[-1]['type']} at {results[-1]['timestamp']}")
        except NotImplementedError:
            print("   Query functionality not yet implemented")
        except Exception as e:
            print(f"   Query failed: {e}")
        
        print(f"\n✅ Storage test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Storage test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Stop storage system
        print("\n🛑 Stopping storage system...")
        await storage.stop()


if __name__ == "__main__":
    # Run the test
    asyncio.run(test_storage())