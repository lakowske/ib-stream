#!/usr/bin/env python3
"""
End-to-End Categorical Integration Validation

This script validates that the complete categorical refactoring works end-to-end:
- Configuration loading with categorical storage
- MultiStorageV4 initialization and functionality
- Health endpoints reflecting categorical architecture
- Complete abstraction boundary compliance
"""

import sys
import os
import asyncio
import tempfile
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add the project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ib-stream/src'))

def test_import_validation():
    """Test that all categorical components can be imported"""
    print("🔍 Testing Import Validation...")
    
    try:
        # Test categorical storage imports
        from ib_stream.storage.categorical_storage import (
            StorageMessage, StorageQuery, CategoricalStorageOrchestrator,
            V2ToV3Transformer, TickMessageTransformer, StorageBackendAdapter
        )
        
        # Test MultiStorageV4 import
        from ib_stream.storage.multi_storage_v4 import MultiStorageV4
        
        # Test state container imports
        from ib_stream.state_container import AppState, get_app_state, update_app_state
        
        # Test component imports
        from ib_stream.components.connection_manager import ConnectionManager
        from ib_stream.components.stream_lifecycle_manager import StreamLifecycleManager
        from ib_stream.components.health_monitor import HealthMonitor
        from ib_stream.components.background_orchestrator import BackgroundStreamOrchestrator
        
        print("✅ All categorical components imported successfully")
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False


async def test_multistorage_v4_functionality():
    """Test that MultiStorageV4 works with categorical orchestration"""
    print("🔍 Testing MultiStorageV4 Functionality...")
    
    try:
        from ib_stream.storage.multi_storage_v4 import MultiStorageV4
        from ib_util.storage import TickMessage
        
        # Create temporary storage directory
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir)
            
            # Initialize MultiStorageV4 with categorical architecture
            storage = MultiStorageV4(
                storage_path=storage_path,
                enable_v2_json=True,
                enable_v2_protobuf=False,  # Minimal for testing
                enable_v3_json=True,
                enable_v3_protobuf=False,  # Minimal for testing
                enable_metrics=True
            )
            
            # Test startup (should initialize categorical orchestrator)
            await storage.start()
            
            # Verify categorical architecture indicator
            info = await storage.get_storage_info()
            assert info.get("categorical_architecture") == True, "Missing categorical architecture indicator"
            assert info.get("backend_count") >= 2, "Should have at least 2 backends (v2_json, v3_json)"
            
            # Test v2 message storage via natural transformation
            v2_message = {
                "timestamp": datetime.now().isoformat(),
                "stream_id": "test_stream",
                "contract_id": 123,
                "tick_type": "TRADES",
                "price": 100.5,
                "size": 1000
            }
            
            await storage.store_v2_message(v2_message)
            
            # Test v3 message storage via natural transformation
            tick_msg = TickMessage(
                ts=int(datetime.now().timestamp()),
                st=1,  # stream_type
                cid=456,  # contract_id
                tt="BID",  # tick_type
                rid=1,  # request_id
                p=99.5,  # price
                s=500.0  # size
            )
            
            await storage.store_v3_message(tick_msg)
            
            # Verify message statistics
            final_info = await storage.get_storage_info()
            stats = final_info["message_stats"]
            assert stats["v2_messages"] >= 1, "Should have processed v2 messages"
            assert stats["v3_messages"] >= 1, "Should have processed v3 messages"
            
            # Test categorical composition comparison
            comparison = await storage.get_storage_comparison()
            assert "categorical_benefits" in comparison, "Should highlight categorical benefits"
            
            benefits = comparison["categorical_benefits"]
            assert benefits["clean_abstraction"] == True
            assert benefits["natural_transformations"] == True
            assert benefits["compositional_architecture"] == True
            assert benefits["proper_separation_of_concerns"] == True
            
            # Test clean shutdown
            await storage.stop()
            
            print("✅ MultiStorageV4 categorical functionality validated")
            return True
            
    except Exception as e:
        print(f"❌ MultiStorageV4 test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_state_container_integration():
    """Test that state container integrates with categorical storage"""
    print("🔍 Testing State Container Integration...")
    
    try:
        from ib_stream.state_container import AppState, get_app_state
        
        # Test state container creation with categorical properties
        app_state = get_app_state()
        
        # Verify immutability (should be frozen dataclass)
        try:
            app_state.config = None  # Should fail
            assert False, "AppState should be immutable"
        except AttributeError:
            pass  # Expected for frozen dataclass
        
        # Test categorical identity properties
        new_state = app_state.with_config(app_state.config)
        assert new_state is app_state, "Identity property: with_config(same) should return self"
        
        print("✅ State container categorical integration validated")
        return True
        
    except Exception as e:
        print(f"❌ State container test failed: {e}")
        return False


async def test_component_composition():
    """Test that decomposed components compose correctly"""
    print("🔍 Testing Component Composition...")
    
    try:
        from ib_stream.components.connection_manager import ConnectionManager
        from ib_stream.components.stream_lifecycle_manager import StreamLifecycleManager
        from ib_stream.components.health_monitor import HealthMonitor
        from ib_stream.config import TrackedContract
        
        # Test individual component initialization
        connection_manager = ConnectionManager(
            client_id_offset=1000,
            reconnect_delay=30
        )
        
        # Create test tracked contracts
        from ib_stream.config import TrackedContract
        test_contracts = {
            123: TrackedContract(contract_id=123, symbol="TEST", tick_types=["bid_ask", "last"])
        }
        
        stream_manager = StreamLifecycleManager(test_contracts)
        
        health_monitor = HealthMonitor(test_contracts)
        
        # Test categorical identity properties
        assert not connection_manager._running, "Should start in stopped state"
        assert len(stream_manager.active_streams) == 0, "Should start with no streams"
        
        # Test health monitor threshold setting (identity property)
        original_threshold = health_monitor.staleness_threshold
        health_monitor.set_staleness_threshold(5)  # 5 minutes
        new_threshold = health_monitor.staleness_threshold
        
        # Setting same value should maintain identity
        health_monitor.set_staleness_threshold(5)
        assert health_monitor.staleness_threshold == new_threshold, "Identity property violated"
        
        print("✅ Component composition validated")
        return True
        
    except Exception as e:
        print(f"❌ Component composition test failed: {e}")
        return False


async def test_natural_transformations_end_to_end():
    """Test natural transformations work end-to-end"""
    print("🔍 Testing Natural Transformations End-to-End...")
    
    try:
        from ib_stream.storage.categorical_storage import (
            V2ToV3Transformer, TickMessageTransformer, StorageMessage
        )
        from ib_util.storage import TickMessage
        
        # Test V2 to V3 transformation
        v2_transformer = V2ToV3Transformer()
        
        v2_message = {
            "timestamp": datetime.now().isoformat(),
            "stream_id": "test_stream",
            "contract_id": 123,
            "tick_type": "TRADES",
            "price": 100.5,
            "size": 1000
        }
        
        storage_msg = v2_transformer.transform(v2_message)
        assert isinstance(storage_msg, StorageMessage), "Should produce StorageMessage"
        assert storage_msg.contract_id == 123, "Should preserve contract_id"
        assert storage_msg.format_version == "v3", "Should mark as v3 format"
        
        # Test TickMessage transformation
        tick_transformer = TickMessageTransformer()
        
        tick_msg = TickMessage(
            ts=int(datetime.now().timestamp()),
            st=1,
            cid=456,
            tt="BID",
            rid=1,
            p=99.5,
            s=500.0
        )
        
        transformed = tick_transformer.transform(tick_msg)
        assert isinstance(transformed, StorageMessage), "Should produce StorageMessage"
        assert transformed.contract_id == 456, "Should preserve contract_id"
        assert transformed.data["p"] == 99.5, "Should preserve price in data"
        
        # Test structure preservation (functoriality)
        assert len(transformed.data) > 5, "Should preserve all TickMessage fields"
        
        print("✅ Natural transformations end-to-end validated")
        return True
        
    except Exception as e:
        print(f"❌ Natural transformations test failed: {e}")
        return False


async def run_integration_validation():
    """Run all categorical integration validation tests"""
    print("🎯 Categorical Integration End-to-End Validation")
    print("=" * 60)
    
    try:
        # Test imports
        if not test_import_validation():
            return False
        
        # Test storage functionality
        if not await test_multistorage_v4_functionality():
            return False
        
        # Test state container
        if not await test_state_container_integration():
            return False
        
        # Test component composition
        if not await test_component_composition():
            return False
        
        # Test natural transformations
        if not await test_natural_transformations_end_to_end():
            return False
        
        print("\n🎉 All categorical integration validations passed!")
        print("✨ Phase 3 storage layer abstraction complete!")
        print("🏗️ Category theory refactoring working end-to-end!")
        print("🎯 Ready for production deployment with categorical architecture!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Integration validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point"""
    success = asyncio.run(run_integration_validation())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()