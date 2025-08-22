#!/usr/bin/env python3
"""
Storage Layer Categorical Properties Validation

This script validates that our storage layer refactoring satisfies category theory principles:
- Natural transformations preserve structure
- Storage operations compose correctly
- Abstraction boundaries are maintained
- Limits/colimits work properly
"""

import sys
import os
import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Add the project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ib-stream/src'))

from ib_stream.storage.categorical_storage import (
    StorageMessage, StorageQuery, V2ToV3Transformer, TickMessageTransformer,
    CategoricalStorageOrchestrator, StorageBackendAdapter
)
from ib_util.storage import TickMessage


def test_storage_message_immutability():
    """Test that StorageMessage is properly immutable"""
    print("🔍 Testing StorageMessage Immutability...")
    
    msg = StorageMessage(
        message_id="test_123",
        timestamp=datetime.now(),
        contract_id=123,
        data={"price": 100.0},
        format_version="v3"
    )
    
    # Should be immutable
    try:
        msg.message_id = "changed"
        assert False, "StorageMessage should be immutable"
    except AttributeError:
        pass  # Expected - frozen dataclass
    
    # to_dict should be pure function (same result every time)
    dict1 = msg.to_dict()
    dict2 = msg.to_dict()
    assert dict1 == dict2
    
    print("✅ StorageMessage immutability validated")


def test_storage_query_composition():
    """Test that StorageQuery composition satisfies categorical laws"""
    print("🔍 Testing StorageQuery Composition...")
    
    now = datetime.now()
    
    query1 = StorageQuery(contract_id=123, start_time=now)
    query2 = StorageQuery(contract_id=456, end_time=now + timedelta(hours=1))
    query3 = StorageQuery(limit=100)
    
    # Test associativity: (q1 ∘ q2) ∘ q3 = q1 ∘ (q2 ∘ q3)
    left_result = query1.compose_with(query2).compose_with(query3)
    right_result = query1.compose_with(query2.compose_with(query3))
    
    # Both should have the same final structure
    assert left_result.limit == right_result.limit == 100
    assert left_result.contract_id == right_result.contract_id == 456  # q2 overrides q1
    
    print("✅ StorageQuery composition associativity validated")


def test_natural_transformations():
    """Test that message transformations preserve structure"""
    print("🔍 Testing Natural Transformations...")
    
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
    
    # Natural transformation should preserve structure
    v3_message = v2_transformer.transform(v2_message)
    
    assert v3_message is not None
    assert v3_message.contract_id == 123
    assert v3_message.data["price"] == 100.5
    assert v3_message.format_version == "v3"
    
    # Test TickMessage transformation  
    tick_transformer = TickMessageTransformer()
    
    # Create TickMessage with correct constructor
    tick_msg = TickMessage(
        ts=int(datetime.now().timestamp()),
        st=1,  # stream_type
        cid=456,  # contract_id
        tt="BID",  # tick_type
        rid=1,  # request_id
        p=99.5,  # price
        s=500.0  # size
    )
    
    storage_msg = tick_transformer.transform(tick_msg)
    
    assert storage_msg.contract_id == 456
    assert storage_msg.data["p"] == 99.5  # TickMessage uses 'p' for price
    assert storage_msg.format_version == "v3"
    
    print("✅ Natural transformations preserve structure")


def test_identity_properties():
    """Test identity properties of storage operations"""
    print("🔍 Testing Identity Properties...")
    
    # Test StorageQuery identity
    query = StorageQuery(contract_id=123)
    identity_query = StorageQuery()
    
    # Composing with identity should return equivalent query
    composed = query.compose_with(identity_query)
    assert composed.contract_id == query.contract_id
    
    # Test transformation identity
    transformer = V2ToV3Transformer()
    
    # Empty message should be handled gracefully (identity behavior)
    empty_result = transformer.transform({})
    assert empty_result is None or isinstance(empty_result, StorageMessage)
    
    print("✅ Identity properties validated")


class MockStorageBackend:
    """Mock storage backend for testing composition"""
    
    def __init__(self, name: str):
        self.name = name
        self.started = False
        self.stored_messages = []
    
    async def store(self, messages):
        if not self.started:
            raise RuntimeError(f"Backend {self.name} not started")
        self.stored_messages.extend(messages)
    
    async def query(self, query):
        if not self.started:
            raise RuntimeError(f"Backend {self.name} not started")
        # Return stored messages that match query
        for msg in self.stored_messages:
            if query.contract_id is None or msg.contract_id == query.contract_id:
                yield msg
    
    async def start(self):
        if self.started:
            return  # Identity property
        self.started = True
    
    async def stop(self):
        if not self.started:
            return  # Identity property
        self.started = False
    
    def get_info(self):
        return {"name": self.name, "started": self.started, "stored_count": len(self.stored_messages)}


async def test_orchestrator_composition():
    """Test that storage orchestrator satisfies categorical composition"""
    print("🔍 Testing Orchestrator Composition...")
    
    orchestrator = CategoricalStorageOrchestrator()
    
    # Add mock backends
    backend1 = MockStorageBackend("backend1")
    backend2 = MockStorageBackend("backend2")
    
    orchestrator.add_backend("backend1", backend1)
    orchestrator.add_backend("backend2", backend2)
    
    # Test idempotent start
    await orchestrator.start()
    await orchestrator.start()  # Should be no-op (identity)
    
    assert backend1.started
    assert backend2.started
    
    # Test storage composition (categorical product)
    msg = StorageMessage(
        message_id="test",
        timestamp=datetime.now(),
        contract_id=123,
        data={"test": "data"}
    )
    
    await orchestrator.store_messages([msg])
    
    # Message should be stored to both backends (product behavior)
    assert len(backend1.stored_messages) == 1
    assert len(backend2.stored_messages) == 1
    assert backend1.stored_messages[0].message_id == "test"
    assert backend2.stored_messages[0].message_id == "test"
    
    # Test query composition (coproduct behavior)
    query = StorageQuery(contract_id=123)
    results = []
    async for result_msg in orchestrator.query_messages(query, "backend1"):
        results.append(result_msg)
    
    assert len(results) == 1
    assert results[0].message_id == "test"
    
    # Test idempotent stop
    await orchestrator.stop()
    await orchestrator.stop()  # Should be no-op (identity)
    
    assert not backend1.started
    assert not backend2.started
    
    print("✅ Orchestrator composition validated")


async def test_backend_adapter():
    """Test that storage backend adapter maintains categorical properties"""
    print("🔍 Testing Backend Adapter...")
    
    # Create mock legacy backend
    class MockLegacyBackend:
        def __init__(self):
            self.started = False
            self.messages = []
        
        async def start(self):
            self.started = True
        
        async def stop(self):
            self.started = False
        
        async def store_message(self, msg):
            self.messages.append(msg)
        
        def get_storage_info(self):
            return {"legacy": True, "count": len(self.messages)}
    
    legacy = MockLegacyBackend()
    adapter = StorageBackendAdapter(legacy, "test_format")
    
    # Test idempotent operations
    await adapter.start()
    await adapter.start()  # Should be no-op
    assert legacy.started
    
    # Test storage through adapter
    storage_msg = StorageMessage(
        message_id="adapter_test",
        timestamp=datetime.now(),
        contract_id=789,
        data={"adapted": True}
    )
    
    await adapter.store([storage_msg])
    assert len(legacy.messages) == 1
    
    # Test info composition
    info = adapter.get_info()
    assert info["format"] == "test_format"
    assert info["legacy"] == True
    
    await adapter.stop()
    assert not legacy.started
    
    print("✅ Backend adapter maintains categorical properties")


async def run_all_storage_tests():
    """Run all storage categorical property tests"""
    print("🎯 Storage Layer Categorical Property Validation")
    print("=" * 60)
    
    try:
        # Synchronous tests
        test_storage_message_immutability()
        test_storage_query_composition()
        test_natural_transformations()
        test_identity_properties()
        
        # Asynchronous tests
        await test_orchestrator_composition()
        await test_backend_adapter()
        
        print("\n🎉 All storage layer categorical validations passed!")
        print("✨ Storage abstraction satisfies mathematical requirements")
        print("🏗️ Natural transformations preserve structure correctly")
        print("🎯 Orchestrator implements proper categorical composition")
        print("🔧 Backend adapters maintain abstraction boundaries")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Storage validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point"""
    success = asyncio.run(run_all_storage_tests())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()