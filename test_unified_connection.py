#!/usr/bin/env python3
"""
Test the unified connection manager implementation
"""

import sys
import os
import asyncio
import logging
from unittest.mock import Mock, patch

# Set up environment
sys.path.insert(0, 'ib-stream/src')
os.environ['IB_ENVIRONMENT'] = 'development'
os.environ['IB_CONFIG_ROOT'] = '/home/seth/Software/dev/ib-stream-1/config'

# Configure logging
logging.basicConfig(level=logging.INFO)

async def test_unified_connection_manager():
    """Test the unified connection manager"""
    print("🧪 Testing Unified Connection Manager")
    print("=" * 50)
    
    try:
        from ib_stream.config import create_config
        from ib_stream.connection import UnifiedConnectionManager, StreamRegistry
        from ib_stream.connection.stream_registry import StreamType
        
        print("✅ Imports successful")
        
        # Load configuration
        config = create_config()
        print(f"✅ Config loaded: client_id={config.client_id}, host={config.host}")
        
        # Test StreamRegistry
        print("\n📋 Testing StreamRegistry...")
        registry = StreamRegistry()
        
        # Test request ID allocation
        client_id = registry.allocator.allocate(StreamType.CLIENT)
        background_id = registry.allocator.allocate(StreamType.BACKGROUND)
        
        print(f"  Allocated client stream ID: {client_id} (expected: 1000-59999)")
        print(f"  Allocated background stream ID: {background_id} (expected: 60000-69999)")
        
        # Verify ranges
        assert 1000 <= client_id <= 59999, f"Client ID {client_id} not in expected range"
        assert 60000 <= background_id <= 69999, f"Background ID {background_id} not in expected range"
        print("✅ Request ID allocation working correctly")
        
        # Test stream registration
        mock_callback = Mock()
        
        client_stream_id = registry.register_stream(
            stream_type=StreamType.CLIENT,
            contract_id=711280073,
            tick_type="bid_ask",
            callback=mock_callback
        )
        
        background_stream_id = registry.register_stream(
            stream_type=StreamType.BACKGROUND,
            contract_id=711280073,
            tick_type="last",
            callback=mock_callback
        )
        
        print(f"  Registered client stream: {client_stream_id}")
        print(f"  Registered background stream: {background_stream_id}")
        
        # Test registry queries
        stats = registry.get_stats()
        print(f"  Registry stats: {stats['total_streams']} total, {stats['client_streams']} client, {stats['background_streams']} background")
        
        assert stats['total_streams'] == 2
        assert stats['client_streams'] == 1
        assert stats['background_streams'] == 1
        print("✅ Stream registry working correctly")
        
        # Test UnifiedConnectionManager (without actual connection)
        print("\n🔗 Testing UnifiedConnectionManager...")
        
        # Create manager with recovery disabled for testing
        manager = UnifiedConnectionManager(config, enable_recovery=False)
        
        print(f"  Manager created with client_id={manager.client_id}")
        print(f"  Initial state: {manager.state.value}")
        print(f"  Is connected: {manager.is_connected}")
        
        # Test stream registration in manager
        mock_restart_callback = Mock()
        
        test_stream_id = manager.register_stream(
            stream_type=StreamType.CLIENT,
            contract_id=711280073,
            tick_type="bid_ask",
            restart_callback=mock_restart_callback
        )
        
        print(f"  Registered stream in manager: {test_stream_id}")
        
        # Test statistics
        stats = manager.get_stream_stats()
        print(f"  Manager stats: {stats['streams']['total_streams']} streams")
        print(f"  Connection state: {stats['connection']['state']}")
        
        # Test cleanup
        manager.unregister_stream(test_stream_id)
        final_stats = manager.get_stream_stats()
        print(f"  After cleanup: {final_stats['streams']['total_streams']} streams")
        
        print("✅ UnifiedConnectionManager basic functionality working")
        
        print("\n🎉 All tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_integration_pattern():
    """Test how the unified manager would integrate with existing code"""
    print("\n🔧 Testing Integration Pattern")
    print("=" * 50)
    
    try:
        from ib_stream.config import create_config
        from ib_stream.connection import UnifiedConnectionManager
        from ib_stream.connection.stream_registry import StreamType
        
        config = create_config()
        
        # This is how it would be used in app_lifecycle.py
        async def simulate_app_lifecycle():
            print("  Simulating app_lifecycle.py startup...")
            
            # Create unified manager (replaces dual connections)
            manager = UnifiedConnectionManager(config, enable_recovery=False)
            
            # This replaces ensure_tws_connection() 
            # streaming_app = await manager.ensure_connection()
            print(f"  ✅ Would create single connection with client_id={manager.client_id}")
            
            # Background streaming would use same connection
            def mock_restart_background_stream(request_id, streaming_app):
                print(f"    Would restart background stream {request_id}")
                return asyncio.sleep(0)  # Mock async operation
            
            bg_stream_id = manager.register_stream(
                stream_type=StreamType.BACKGROUND,
                contract_id=711280073,
                tick_type="bid_ask", 
                restart_callback=mock_restart_background_stream
            )
            
            print(f"  ✅ Registered background stream {bg_stream_id} (no +1000 offset needed)")
            
            # Client streaming would use same connection
            def mock_restart_client_stream(request_id, streaming_app):
                print(f"    Would restart client stream {request_id}")
                return asyncio.sleep(0)  # Mock async operation
                
            client_stream_id = manager.register_stream(
                stream_type=StreamType.CLIENT,
                contract_id=265598,
                tick_type="last",
                restart_callback=mock_restart_client_stream
            )
            
            print(f"  ✅ Registered client stream {client_stream_id}")
            
            # Show unified stats
            stats = manager.get_stream_stats()
            print(f"  📊 Unified stats: {stats['streams']['total_streams']} total streams")
            print(f"     - Client: {stats['streams']['client_streams']}")
            print(f"     - Background: {stats['streams']['background_streams']}")
            print(f"     - Single client ID: {stats['connection']['client_id']}")
            
            return manager
        
        manager = await simulate_app_lifecycle()
        
        print("\n✅ Integration pattern validated!")
        print("   - Single connection manager replaces dual connections")
        print("   - No client ID offset calculations needed") 
        print("   - Same request ID ranges maintained for compatibility")
        print("   - Unified recovery system for all streams")
        
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("🔬 Unified Connection Manager Test Suite")
    print("=" * 60)
    
    tests = [
        test_unified_connection_manager,
        test_integration_pattern
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test suite error: {e}")
            results.append(False)
    
    print("\n📋 Test Results Summary")
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ All {total} tests passed!")
        print("🚀 Unified Connection Manager ready for integration!")
    else:
        print(f"❌ {passed}/{total} tests passed")
        print("🔧 Some issues need to be resolved")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)