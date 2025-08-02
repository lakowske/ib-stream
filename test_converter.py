#!/usr/bin/env python3
"""
Simple test for the v2 to v3 converter functionality.
"""

import json
import sys
from pathlib import Path

# Add the source directory to path
sys.path.insert(0, str(Path(__file__).parent / 'ib-stream' / 'src'))
sys.path.insert(0, str(Path(__file__).parent / 'ib-util'))

def test_v2_data_reading():
    """Test reading v2 data files."""
    print("Testing V2 data reading...")
    
    # Find some v2 files
    v2_storage = Path('/workspace/storage/v2')
    if not v2_storage.exists():
        print("ERROR: V2 storage path not found")
        return False
    
    json_files = list(v2_storage.rglob('*.jsonl'))
    print(f"Found {len(json_files)} JSON files")
    
    if not json_files:
        print("ERROR: No JSON files found")
        return False
    
    # Read a sample file
    sample_file = json_files[0]
    print(f"Reading sample file: {sample_file}")
    
    try:
        with open(sample_file, 'r') as f:
            lines = f.readlines()[:5]  # Read first 5 lines
            
        print(f"File has {len(lines)} sample lines")
        
        for i, line in enumerate(lines):
            try:
                message = json.loads(line.strip())
                print(f"Line {i+1}: {type(message)} with keys {list(message.keys())}")
                
                # Check v2 format structure
                if 'type' in message and 'data' in message and 'metadata' in message:
                    data = message['data']
                    metadata = message['metadata']
                    print(f"  V2 format confirmed - tick_type: {data.get('tick_type')}, contract_id: {metadata.get('contract_id')}")
                else:
                    print(f"  Unexpected format: {message}")
                
            except json.JSONDecodeError as e:
                print(f"Line {i+1}: JSON decode error - {e}")
        
        return True
        
    except Exception as e:
        print(f"ERROR reading file: {e}")
        return False

def test_tick_message_import():
    """Test importing the TickMessage class."""
    print("\nTesting TickMessage import...")
    
    try:
        from ib_util.storage import TickMessage, create_tick_message_from_v2
        print("✓ Successfully imported TickMessage and create_tick_message_from_v2")
        
        # Test creating a sample tick message
        sample_v2_message = {
            'type': 'tick',
            'stream_id': 'bg_711280073_bid_ask',
            'timestamp': '2025-07-21T15:27:15.896109+00:00',
            'data': {
                'type': 'bid_ask',
                'timestamp': '2025-07-21 10:27:53',
                'unix_time': 1753111673000000,
                'bid_price': 23398.75,
                'ask_price': 23399.25,
                'bid_size': 12.0,
                'ask_size': 9.0,
                'bid_past_low': False,
                'ask_past_high': False
            },
            'metadata': {
                'source': 'stream_manager',
                'request_id': '60014',
                'contract_id': '711280073',
                'tick_type': 'bid_ask'
            }
        }
        
        tick_message = create_tick_message_from_v2(sample_v2_message)
        if tick_message:
            print(f"✓ Successfully converted v2 message to TickMessage")
            print(f"  Contract ID: {tick_message.cid}")
            print(f"  Tick Type: {tick_message.tt}")
            print(f"  Bid Price: {tick_message.bp}")
            print(f"  Ask Price: {tick_message.ap}")
            
            # Test JSON conversion
            json_dict = tick_message.to_json_dict()
            print(f"  V3 JSON: {json_dict}")
            
            return True
        else:
            print("ERROR: Failed to convert v2 message")
            return False
            
    except ImportError as e:
        print(f"ERROR: Could not import required modules - {e}")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error - {e}")
        return False

def main():
    """Run all tests."""
    print("V2 to V3 Converter Test")
    print("=" * 40)
    
    success = True
    
    # Test v2 data reading
    if not test_v2_data_reading():
        success = False
    
    # Test TickMessage functionality
    if not test_tick_message_import():
        success = False
    
    print("\n" + "=" * 40)
    if success:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed!")
        return 1

if __name__ == '__main__':
    sys.exit(main())