#!/usr/bin/env python3
"""
Test the new configuration settings for background streaming and V3 storage
"""

import sys
import os

# Set up paths
sys.path.insert(0, 'ib-stream/src')
os.environ['IB_ENVIRONMENT'] = 'development'
os.environ['IB_CONFIG_ROOT'] = '/home/seth/Software/dev/ib-stream-1/config'

def test_configuration():
    """Test the updated configuration"""
    print("🧪 Testing Updated Configuration")
    print("=" * 50)
    
    try:
        from ib_stream.config import create_config
        config = create_config()
        
        print("✅ Configuration loaded successfully")
        print(f"  Environment: {os.environ.get('IB_ENVIRONMENT', 'default')}")
        print()
        
        # Test storage configuration
        print("📁 Storage Configuration:")
        print(f"  Base Path: {config.storage.storage_base_path}")
        print(f"  V2 JSON Enabled: {config.storage.enable_json}")
        print(f"  V2 Protobuf Enabled: {config.storage.enable_protobuf}")
        print(f"  V3 JSON Enabled: {config.storage.enable_v3_json}")
        print(f"  V3 Protobuf Enabled: {config.storage.enable_v3_protobuf}")
        print()
        
        # Test background streaming configuration
        print("📊 Background Streaming Configuration:")
        print(f"  Tracked Contracts: {len(config.storage.tracked_contracts)}")
        
        for i, contract in enumerate(config.storage.tracked_contracts):
            print(f"  Contract {i+1}:")
            print(f"    Symbol: {contract.symbol}")
            print(f"    Contract ID: {contract.contract_id}")
            print(f"    Tick Types: {contract.tick_types}")
            print(f"    Buffer Hours: {contract.buffer_hours}")
            print(f"    Enabled: {contract.enabled}")
        print()
        
        # Test storage paths
        print("📂 Storage Paths:")
        if hasattr(config.storage, 'json_storage_path'):
            print(f"  JSON: {config.storage.json_storage_path}")
        if hasattr(config.storage, 'protobuf_storage_path'):
            print(f"  Protobuf: {config.storage.protobuf_storage_path}")
        print()
        
        # Verify storage directory exists
        from pathlib import Path
        storage_path = Path(config.storage.storage_base_path)
        print(f"📁 Storage Directory Status:")
        print(f"  Path: {storage_path.absolute()}")
        print(f"  Exists: {storage_path.exists()}")
        
        if not storage_path.exists():
            print("  Creating storage directory...")
            storage_path.mkdir(parents=True, exist_ok=True)
            print("  ✅ Created successfully")
        
        # Test expected V3 subdirectories
        v3_json_path = storage_path / "v3" / "json"
        v3_protobuf_path = storage_path / "v3" / "protobuf" 
        
        print(f"  V3 JSON path: {v3_json_path} (exists: {v3_json_path.exists()})")
        print(f"  V3 Protobuf path: {v3_protobuf_path} (exists: {v3_protobuf_path.exists()})")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_storage_format_verification():
    """Verify that only V3 formats are enabled"""
    print("\n🔍 Storage Format Verification")
    print("=" * 50)
    
    try:
        from ib_stream.config import create_config
        config = create_config()
        
        # Expected settings
        expected = {
            'V2 JSON': False,
            'V2 Protobuf': False,
            'V3 JSON': True,
            'V3 Protobuf': True
        }
        
        # Actual settings  
        actual = {
            'V2 JSON': config.storage.enable_json,
            'V2 Protobuf': config.storage.enable_protobuf,
            'V3 JSON': config.storage.enable_v3_json,
            'V3 Protobuf': config.storage.enable_v3_protobuf
        }
        
        all_correct = True
        for format_name, expected_value in expected.items():
            actual_value = actual[format_name]
            status = "✅" if actual_value == expected_value else "❌"
            print(f"  {format_name}: {actual_value} {status}")
            
            if actual_value != expected_value:
                all_correct = False
        
        if all_correct:
            print("\n✅ All storage formats configured correctly!")
        else:
            print("\n❌ Some storage formats are incorrectly configured")
            
        return all_correct
        
    except Exception as e:
        print(f"❌ Storage format verification failed: {e}")
        return False

def main():
    """Run all configuration tests"""
    print("🔬 Configuration Testing Suite")
    print("=" * 60)
    
    tests = [
        test_configuration,
        test_storage_format_verification
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
    
    print("\n📋 Test Summary")
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ All {total} tests passed!")
        print("🎉 Configuration is ready for background streaming with V3 storage!")
    else:
        print(f"❌ {passed}/{total} tests passed")
        print("❗ Some configuration issues need to be resolved")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)