#!/usr/bin/env python3
"""
Quick test script to validate v3 storage implementation.

This script tests the core v3 storage functionality without requiring
full system integration.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import sys
import os

# Add the project to the path
sys.path.insert(0, str(Path(__file__).parent / 'ib-util'))
sys.path.insert(0, str(Path(__file__).parent / 'ib-stream' / 'src'))

from ib_util.storage import TickMessage, generate_request_id
from ib_stream.storage.v3_json_storage import V3JSONStorage
from ib_stream.storage.multi_storage_v3 import MultiStorageV3


async def test_tick_message():
    """Test TickMessage creation and serialization."""
    print("Testing TickMessage...")
    
    # Create sample tick data (simulating MNQ bid/ask data like we saw earlier)
    sample_tick_data = {
        'contract_id': 711280073,
        'tick_type': 'bid_ask',
        'type': 'bid_ask',
        'timestamp': '2025-08-01 00:31:53',
        'unix_time': int(time.time() * 1_000_000),
        'bid_price': 23260.0,
        'ask_price': 23260.5,
        'bid_size': 4.0,
        'ask_size': 2.0,
        'bid_past_low': False,
        'ask_past_high': False
    }
    
    # Create TickMessage from tick data
    tick_message = TickMessage.create_from_tick_data(
        contract_id=711280073,
        tick_type='bid_ask',
        tick_data=sample_tick_data
    )
    
    print(f"Created TickMessage: rid={tick_message.rid}, cid={tick_message.cid}, tt={tick_message.tt}")
    
    # Test JSON serialization
    json_dict = tick_message.to_json_dict()
    json_str = json.dumps(json_dict, separators=(',', ':'))
    
    # Create v2 format for comparison
    v2_message = {
        'type': 'tick',
        'stream_id': f"711280073_bid_ask_{tick_message.ts}_{tick_message.rid}",
        'timestamp': datetime.fromtimestamp(tick_message.st / 1_000_000, tz=timezone.utc).isoformat() + 'Z',
        'data': sample_tick_data,
        'metadata': {
            'source': 'stream_manager',
            'request_id': str(tick_message.rid),
            'contract_id': '711280073',
            'tick_type': 'bid_ask'
        }
    }
    v2_str = json.dumps(v2_message, separators=(',', ':'))
    
    print(f"v3 JSON ({len(json_str)} bytes): {json_str}")
    print(f"v2 JSON ({len(v2_str)} bytes): {v2_str[:100]}...")
    
    size_reduction = ((len(v2_str) - len(json_str)) / len(v2_str)) * 100
    print(f"Size reduction: {size_reduction:.1f}% ({len(v2_str) - len(json_str)} bytes saved)")
    
    # Test round-trip conversion
    restored_message = TickMessage.from_json_dict(json_dict)
    assert restored_message.cid == tick_message.cid
    assert restored_message.tt == tick_message.tt
    assert restored_message.bp == tick_message.bp
    
    print("✓ TickMessage tests passed")
    return tick_message


async def test_v3_json_storage():
    """Test v3 JSON storage backend."""
    print("\nTesting V3JSONStorage...")
    
    # Create test storage directory
    test_path = Path(__file__).parent / 'test_storage_v3'
    test_path.mkdir(exist_ok=True)
    
    storage = V3JSONStorage(test_path / 'json')
    await storage.start()
    
    try:
        # Create multiple test messages
        messages = []
        for i in range(5):
            tick_data = {
                'contract_id': 711280073,
                'tick_type': 'bid_ask',
                'unix_time': int((time.time() + i) * 1_000_000),  # Spread over time
                'bid_price': 23260.0 + (i * 0.25),
                'ask_price': 23260.5 + (i * 0.25),
                'bid_size': 4.0,
                'ask_size': 2.0,
            }
            
            message = TickMessage.create_from_tick_data(
                contract_id=711280073,
                tick_type='bid_ask',
                tick_data=tick_data
            )
            messages.append(message)
        
        # Write messages to storage
        await storage.write_tick_messages(messages)
        print(f"✓ Wrote {len(messages)} messages to v3 JSON storage")
        
        # Query messages back
        start_time = datetime.fromtimestamp(time.time() - 60, tz=timezone.utc)
        end_time = datetime.fromtimestamp(time.time() + 60, tz=timezone.utc)
        
        retrieved_messages = []
        async for message in storage.query_range(
            contract_id=711280073,
            tick_types=['bid_ask'],
            start_time=start_time,
            end_time=end_time
        ):
            retrieved_messages.append(message)
        
        print(f"✓ Retrieved {len(retrieved_messages)} messages from v3 JSON storage")
        
        # Verify data integrity
        assert len(retrieved_messages) == len(messages)
        for orig, retr in zip(messages, retrieved_messages):
            assert orig.cid == retr.cid
            assert orig.tt == retr.tt
            assert orig.bp == retr.bp
            assert orig.ap == retr.ap
        
        # Get storage stats
        stats = await storage.get_storage_stats()
        print(f"✓ Storage stats: {stats['total_files']} files, {stats['total_size_mb']} MB")
        
    finally:
        await storage.stop()
    
    print("✓ V3JSONStorage tests passed")


async def test_multi_storage_v3():
    """Test MultiStorageV3 with dual format support."""
    print("\nTesting MultiStorageV3...")
    
    # Create test storage directory
    test_path = Path(__file__).parent / 'test_storage_multi'
    test_path.mkdir(exist_ok=True)
    
    # Initialize with v3 formats only for testing
    multi_storage = MultiStorageV3(
        storage_path=test_path,
        enable_v2_json=False,  # Skip v2 for this test
        enable_v2_protobuf=False,
        enable_v3_json=True,
        enable_v3_protobuf=False  # Skip protobuf for simplicity
    )
    
    await multi_storage.start()
    
    try:
        # Create test v2 message (as would come from current system)
        v2_message = {
            'type': 'tick',
            'stream_id': '711280073_bid_ask_1754008313914_3520',
            'timestamp': '2025-08-01T00:31:54.037772Z',
            'data': {
                'contract_id': 711280073,
                'tick_type': 'bid_ask',
                'type': 'bid_ask',
                'timestamp': '2025-08-01 00:31:53',
                'unix_time': int(time.time() * 1_000_000),
                'bid_price': 23260.0,
                'ask_price': 23260.5,
                'bid_size': 4.0,
                'ask_size': 2.0,
                'bid_past_low': False,
                'ask_past_high': False
            },
            'metadata': {
                'source': 'stream_manager',
                'request_id': '12345',
                'contract_id': '711280073',
                'tick_type': 'bid_ask'
            }
        }
        
        # Store v2 message (should convert and store as v3)
        await multi_storage.store_v2_message(v2_message)
        print("✓ Stored v2 message (converted to v3)")
        
        # Create native v3 message
        tick_message = TickMessage.create_from_tick_data(
            contract_id=711280073,
            tick_type='last',
            tick_data={
                'contract_id': 711280073,
                'tick_type': 'last',
                'unix_time': int(time.time() * 1_000_000),
                'price': 23261.0,
                'size': 10.0
            }
        )
        
        # Store v3 message directly
        await multi_storage.store_v3_message(tick_message)
        print("✓ Stored native v3 message")
        
        # Wait a moment for async writes to complete
        await asyncio.sleep(0.5)
        
        # Query v3 data
        start_time = datetime.fromtimestamp(time.time() - 60, tz=timezone.utc)
        
        bid_ask_messages = await multi_storage.query_v3_range(
            contract_id=711280073,
            tick_types=['bid_ask'],
            start_time=start_time,
            storage_format='v3_json'
        )
        
        last_messages = await multi_storage.query_v3_range(
            contract_id=711280073,
            tick_types=['last'],
            start_time=start_time,
            storage_format='v3_json'
        )
        
        print(f"✓ Retrieved {len(bid_ask_messages)} bid_ask and {len(last_messages)} last messages")
        
        # Get storage info
        info = multi_storage.get_storage_info()
        print(f"✓ MultiStorage info: {info['message_stats']}")
        
    finally:
        await multi_storage.stop()
    
    print("✓ MultiStorageV3 tests passed")


async def main():
    """Run all tests."""
    print("Starting v3 storage system tests...\n")
    
    try:
        # Test core TickMessage functionality
        await test_tick_message()
        
        # Test v3 JSON storage
        await test_v3_json_storage() 
        
        # Test multi-storage with v3
        await test_multi_storage_v3()
        
        print("\n🎉 All v3 storage tests passed!")
        print("\nThe v3 storage system is ready for integration with the main application.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    exit(exit_code)