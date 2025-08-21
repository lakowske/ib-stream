"""
MultiStorageV4 - Category Theory Compliant Storage

This is a categorical refactoring of MultiStorageV3 that eliminates anti-patterns:
- Proper abstraction boundaries via protocols
- Natural transformations between formats
- Compositional storage architecture
- Clean separation of concerns
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from .categorical_storage import (
    CategoricalStorageOrchestrator, StorageBackendAdapter, StorageMessage, StorageQuery
)
from .json_storage import JSONStorage
from .protobuf_storage import ProtobufStorage
from .v3_json_storage import V3JSONStorage
from .v3_protobuf_storage import V3ProtobufStorage
from .metrics import StorageMetrics
from ib_util.storage import TickMessage

logger = logging.getLogger(__name__)


class MultiStorageV4:
    """
    Category theory compliant multi-format storage.
    
    Key improvements over V3:
    - Clean abstraction boundaries (no leaky implementation details)
    - Natural transformations between message formats  
    - Compositional architecture using categorical principles
    - Proper separation of orchestration from individual backends
    
    This class acts as a facade over the categorical storage orchestrator,
    providing backward compatibility while using mathematically sound architecture.
    """
    
    def __init__(
        self,
        storage_path: Path,
        enable_v2_json: bool = True,
        enable_v2_protobuf: bool = True,
        enable_v3_json: bool = True,
        enable_v3_protobuf: bool = True,
        enable_metrics: bool = True,
        v3_only_mode: bool = False
    ):
        """
        Initialize categorical multi-format storage.
        
        This constructor composes storage backends using categorical principles
        rather than managing them directly.
        """
        self.storage_path = Path(storage_path)
        self.v3_only_mode = v3_only_mode
        self.enable_metrics = enable_metrics
        
        # Categorical orchestrator (composition root)
        self.orchestrator = CategoricalStorageOrchestrator()
        
        # Metrics (optional functor)
        self.metrics = StorageMetrics() if enable_metrics else None
        
        # Message statistics (pure data)
        self._message_stats = {
            'v2_messages': 0,
            'v3_messages': 0,
            'conversion_errors': 0
        }
        
        # Backend configuration (immutable after initialization)
        self._backend_config = {
            'enable_v2_json': enable_v2_json and not v3_only_mode,
            'enable_v2_protobuf': enable_v2_protobuf and not v3_only_mode,
            'enable_v3_json': enable_v3_json,
            'enable_v3_protobuf': enable_v3_protobuf,
        }
        
        # Initialize backends using categorical composition
        self._setup_storage_backends()
    
    def _setup_storage_backends(self) -> None:
        """
        Setup storage backends using categorical composition.
        
        This method demonstrates proper categorical architecture:
        - Each backend is wrapped in an adapter (functorial operation)
        - Backends are composed via the orchestrator (categorical product)
        - No direct coupling between orchestrator and backend implementations
        """
        config = self._backend_config
        
        # V2 backends (legacy format support)
        if config['enable_v2_json']:
            v2_json = JSONStorage(self.storage_path / "v2" / "json")
            adapter = StorageBackendAdapter(v2_json, "v2_json")
            self.orchestrator.add_backend("v2_json", adapter)
        
        if config['enable_v2_protobuf']:
            v2_protobuf = ProtobufStorage(self.storage_path / "v2" / "protobuf")
            adapter = StorageBackendAdapter(v2_protobuf, "v2_protobuf")
            self.orchestrator.add_backend("v2_protobuf", adapter)
        
        # V3 backends (optimized format)
        if config['enable_v3_json']:
            v3_json = V3JSONStorage(self.storage_path / "v3" / "json")
            adapter = StorageBackendAdapter(v3_json, "v3_json")
            self.orchestrator.add_backend("v3_json", adapter)
        
        if config['enable_v3_protobuf']:
            v3_protobuf = V3ProtobufStorage(self.storage_path / "v3" / "protobuf")
            adapter = StorageBackendAdapter(v3_protobuf, "v3_protobuf")
            self.orchestrator.add_backend("v3_protobuf", adapter)
        
        logger.info("Initialized %d storage backends in categorical orchestrator", 
                   len(self.orchestrator.backends))
    
    async def start(self) -> None:
        """
        Start storage system (idempotent via categorical composition).
        
        The orchestrator handles the complexity of starting multiple backends,
        maintaining the identity property for repeated calls.
        """
        try:
            await self.orchestrator.start()
            
            # Note: StorageMetrics doesn't need explicit start() - it's stateless
            
            logger.info("MultiStorageV4 started successfully with categorical orchestration")
            
        except Exception as e:
            logger.error("Failed to start MultiStorageV4: %s", e)
            raise
    
    async def stop(self) -> None:
        """
        Stop storage system (idempotent via categorical composition).
        
        The orchestrator ensures clean shutdown of all backends.
        """
        try:
            await self.orchestrator.stop()
            
            # Note: StorageMetrics doesn't need explicit stop() - it's stateless
            
            logger.info("MultiStorageV4 stopped successfully")
            
        except Exception as e:
            logger.error("Failed to stop MultiStorageV4: %s", e)
    
    # Backward compatibility interface (facade pattern)
    
    async def store_message(self, message: Dict[str, Any]) -> None:
        """
        Backward compatibility method for v2 message storage.
        
        This maintains interface compatibility while using categorical storage
        underneath. The natural transformation from v2 to categorical format
        happens automatically in the orchestrator.
        """
        if self.metrics:
            self.metrics.record_message_received()
        
        self._message_stats['v2_messages'] += 1
        
        try:
            await self.orchestrator.store_v2_message(message)
        except Exception as e:
            logger.error("Failed to store v2 message: %s", e)
            self._message_stats['conversion_errors'] += 1
            raise
    
    async def store_v2_message(self, message: Dict[str, Any]) -> None:
        """Store v2 protocol message using categorical transformations"""
        await self.store_message(message)  # Delegate to main interface
    
    async def store_v3_message(self, tick_message: TickMessage) -> None:
        """
        Store v3 TickMessage using categorical transformations.
        
        This demonstrates natural transformation from TickMessage to the
        categorical storage format, then distributed storage via the orchestrator.
        """
        if self.metrics:
            self.metrics.record_message_received()
        
        self._message_stats['v3_messages'] += 1
        
        try:
            await self.orchestrator.store_tick_message(tick_message)
        except Exception as e:
            logger.error("Failed to store v3 message: %s", e)
            self._message_stats['conversion_errors'] += 1
            raise
    
    # Query interface using categorical composition
    
    async def query_v3_range(
        self,
        contract_id: int,
        start_time: datetime,
        end_time: datetime,
        tick_types: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[TickMessage]:
        """
        Query v3 messages using categorical query composition.
        
        This demonstrates how queries compose categorically while maintaining
        backward compatibility with the existing interface.
        """
        # Compose query using categorical operations
        query = StorageQuery(
            contract_id=contract_id,
            start_time=start_time,
            end_time=end_time,
            message_types=tick_types,
            limit=limit
        )
        
        # Prefer v3 backends for v3 queries (categorical coproduct)
        preferred_backend = "v3_protobuf" if "v3_protobuf" in self.orchestrator.backends else None
        
        results = []
        async for storage_msg in self.orchestrator.query_messages(query, preferred_backend):
            # Transform back to TickMessage for backward compatibility
            tick_msg = self._storage_message_to_tick(storage_msg)
            if tick_msg:
                results.append(tick_msg)
        
        return results
    
    async def query_v2_range(
        self,
        contract_id: int,
        start_time: datetime,
        end_time: datetime,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Query v2 messages using categorical query composition.
        """
        query = StorageQuery(
            contract_id=contract_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        # Prefer v2 backends for v2 queries
        preferred_backend = "v2_json" if "v2_json" in self.orchestrator.backends else None
        
        results = []
        async for storage_msg in self.orchestrator.query_messages(query, preferred_backend):
            # Use the original data for v2 format
            if storage_msg.format_version in ["legacy", "v2"]:
                results.append(storage_msg.data)
        
        return results
    
    # Status and information (pure functions)
    
    async def get_storage_info(self) -> Dict[str, Any]:
        """
        Get storage information using categorical composition.
        
        This composes information from all backends via the orchestrator,
        providing a unified view while maintaining abstraction boundaries.
        """
        orchestrator_status = self.orchestrator.get_status()
        
        # Compose backend information
        enabled_formats = []
        queue_sizes = {}  # Not applicable in categorical architecture
        
        for backend_name, backend_info in orchestrator_status["backends"].items():
            if backend_info.get("started", False):
                enabled_formats.append(backend_name)
        
        return {
            "enabled_formats": enabled_formats,
            "queue_sizes": queue_sizes,  # Empty - no queues in categorical design
            "message_stats": self._message_stats.copy(),
            "backend_count": orchestrator_status["backend_count"],
            "categorical_architecture": True,  # Indicator of new architecture
            "storage_path": str(self.storage_path),
            "v3_only_mode": self.v3_only_mode
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics (pure function when available)"""
        if self.metrics:
            return self.metrics.get_stats()
        return {"metrics_enabled": False}
    
    async def get_storage_comparison(self) -> Dict[str, Any]:
        """
        Get storage format comparison.
        
        In the categorical architecture, this becomes a composition of
        backend status information rather than direct size calculations.
        """
        info = await self.get_storage_info()
        
        # Calculate comparative information from backend status
        backend_info = self.orchestrator.get_status()["backends"]
        
        comparison = {
            "v2_formats": {
                "json": "v2_json" in backend_info,
                "protobuf": "v2_protobuf" in backend_info
            },
            "v3_formats": {
                "json": "v3_json" in backend_info,
                "protobuf": "v3_protobuf" in backend_info
            },
            "categorical_benefits": {
                "clean_abstraction": True,
                "natural_transformations": True,
                "compositional_architecture": True,
                "proper_separation_of_concerns": True
            }
        }
        
        return comparison
    
    async def enable_v3_only_mode(self) -> None:
        """
        Enable v3-only mode by removing v2 backends.
        
        This demonstrates categorical composition - we can dynamically
        modify the orchestrator by removing backends without breaking abstractions.
        """
        if self.v3_only_mode:
            return  # Identity property
        
        # Remove v2 backends from orchestrator
        self.orchestrator.remove_backend("v2_json")
        self.orchestrator.remove_backend("v2_protobuf")
        
        self.v3_only_mode = True
        logger.info("Enabled v3-only mode - removed v2 backends from orchestrator")
    
    # Private helper methods (natural transformations)
    
    def _storage_message_to_tick(self, storage_msg: StorageMessage) -> Optional[TickMessage]:
        """
        Natural transformation: StorageMessage -> TickMessage
        
        This preserves structure when converting between categorical and legacy formats.
        """
        try:
            data = storage_msg.data
            if 'tick_type' in data and 'price' in data:
                return TickMessage(
                    contract_id=storage_msg.contract_id or 0,
                    timestamp=storage_msg.timestamp,
                    tick_type=data['tick_type'],
                    price=data['price'],
                    size=data.get('size', 0)
                )
        except Exception as e:
            logger.debug("Could not convert StorageMessage to TickMessage: %s", e)
        return None