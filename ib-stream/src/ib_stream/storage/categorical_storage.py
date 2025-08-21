"""
Categorical Storage Abstraction - Natural Transformations and Proper Limits

This module implements a mathematically sound storage architecture using category theory:
- Natural transformations between storage formats
- Proper limits/colimits for storage composition
- Functorial operations preserving structure
- Clean abstraction boundaries hiding implementation details
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Protocol, TypeVar, Generic, AsyncIterator, Union
from datetime import datetime
from pathlib import Path

from ib_util.storage import TickMessage

logger = logging.getLogger(__name__)

# Type variables for categorical operations
T = TypeVar('T')  # Source type
U = TypeVar('U')  # Target type
M = TypeVar('M', bound='StorageMessage')  # Message type


@dataclass(frozen=True)
class StorageMessage:
    """
    Immutable storage message container.
    
    This provides the common structure for all storage operations,
    acting as the identity element in the category of storage messages.
    """
    message_id: str
    timestamp: datetime
    contract_id: Optional[int]
    data: Dict[str, Any]
    format_version: str = "v3"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (natural transformation to dict)"""
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "contract_id": self.contract_id,
            "data": self.data,
            "format_version": self.format_version
        }


class StorageBackend(Protocol):
    """
    Storage backend protocol defining categorical interface.
    
    This protocol defines the morphisms in the category of storage backends:
    - store: messages -> stored_messages (natural transformation)
    - query: query_params -> message_stream (natural transformation)
    - Natural transformations preserve structure across all implementations
    """
    
    async def store(self, messages: List[StorageMessage]) -> None:
        """
        Natural transformation: List[StorageMessage] -> Stored
        
        This operation must preserve the structure of messages while
        transforming them into the storage backend's native format.
        """
        ...
    
    async def query(self, query: 'StorageQuery') -> AsyncIterator[StorageMessage]:
        """
        Natural transformation: StorageQuery -> AsyncIterator[StorageMessage]
        
        This operation must preserve the temporal and structural relationships
        of stored messages when retrieving them.
        """
        ...
    
    async def start(self) -> None:
        """Initialize storage backend (idempotent operation)"""
        ...
    
    async def stop(self) -> None:
        """Cleanup storage backend (idempotent operation)"""
        ...
    
    def get_info(self) -> Dict[str, Any]:
        """Get backend information (pure function)"""
        ...


@dataclass(frozen=True)
class StorageQuery:
    """
    Immutable query specification for storage operations.
    
    This acts as a morphism in the category of queries, enabling
    compositional query operations.
    """
    contract_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    message_types: Optional[List[str]] = None
    limit: Optional[int] = None
    
    def compose_with(self, other: 'StorageQuery') -> 'StorageQuery':
        """
        Compose two queries (categorical composition).
        
        This operation satisfies associativity: (q1 ∘ q2) ∘ q3 = q1 ∘ (q2 ∘ q3)
        """
        return StorageQuery(
            contract_id=other.contract_id if other.contract_id is not None else self.contract_id,
            start_time=max(filter(None, [self.start_time, other.start_time]), default=None),
            end_time=min(filter(None, [self.end_time, other.end_time]), default=None),
            message_types=list(set((self.message_types or []) + (other.message_types or []))),
            limit=min(filter(None, [self.limit, other.limit]), default=None)
        )


class MessageTransformer(Protocol, Generic[T, U]):
    """
    Natural transformation between message formats.
    
    This protocol defines functorial operations that preserve structure
    while transforming between different message representations.
    """
    
    def transform(self, source: T) -> U:
        """
        Natural transformation: T -> U
        
        Must satisfy functoriality: 
        - preserve identity: transform(id) = id
        - preserve composition: transform(f ∘ g) = transform(f) ∘ transform(g)
        """
        ...
    
    def can_transform(self, source: T) -> bool:
        """Pure function: check if transformation is possible"""
        ...


class V2ToV3Transformer:
    """Natural transformation from v2 messages to v3 StorageMessage"""
    
    def transform(self, v2_message: Dict[str, Any]) -> Optional[StorageMessage]:
        """Transform v2 dict to v3 StorageMessage (structure-preserving)"""
        try:
            # Extract common fields with proper defaults
            message_id = f"{v2_message.get('stream_id', 'unknown')}_{datetime.now().timestamp()}"
            timestamp = datetime.fromisoformat(v2_message.get('timestamp', datetime.now().isoformat()))
            contract_id = v2_message.get('contract_id')
            
            # Create immutable storage message
            return StorageMessage(
                message_id=message_id,
                timestamp=timestamp,
                contract_id=contract_id,
                data=v2_message,
                format_version="v3"
            )
        except Exception as e:
            logger.error("Failed to transform v2 message to v3: %s", e)
            return None
    
    def can_transform(self, v2_message: Dict[str, Any]) -> bool:
        """Check if v2 message can be transformed to v3"""
        return isinstance(v2_message, dict) and 'timestamp' in v2_message


class TickMessageTransformer:
    """Natural transformation from TickMessage to StorageMessage"""
    
    def transform(self, tick_message: TickMessage) -> StorageMessage:
        """Transform TickMessage to StorageMessage (structure-preserving)"""
        from datetime import datetime
        
        # Extract timestamp and contract_id from TickMessage
        timestamp = datetime.fromtimestamp(tick_message.ts)
        contract_id = tick_message.cid
        
        # Create data dict from TickMessage fields
        data = {
            "ts": tick_message.ts,
            "st": tick_message.st,
            "cid": tick_message.cid,
            "tt": tick_message.tt,
            "rid": tick_message.rid,
            "p": tick_message.p,
            "s": tick_message.s,
            "bp": tick_message.bp,
            "bs": tick_message.bs,
            "ap": tick_message.ap,
            "as_": tick_message.as_,
            "mp": tick_message.mp,
            "bpl": tick_message.bpl,
            "aph": tick_message.aph,
            "upt": tick_message.upt
        }
        
        return StorageMessage(
            message_id=f"tick_{contract_id}_{tick_message.ts}",
            timestamp=timestamp,
            contract_id=contract_id,
            data=data,
            format_version="v3"
        )
    
    def can_transform(self, tick_message: TickMessage) -> bool:
        """Check if TickMessage can be transformed"""
        return isinstance(tick_message, TickMessage)


class StorageBackendAdapter:
    """
    Adapter for legacy storage backends to new categorical interface.
    
    This provides a categorical wrapper around existing storage implementations,
    ensuring they satisfy the natural transformation requirements.
    """
    
    def __init__(self, legacy_backend: Any, format_name: str):
        self.legacy_backend = legacy_backend
        self.format_name = format_name
        self._started = False
    
    async def store(self, messages: List[StorageMessage]) -> None:
        """Adapt legacy store interface to categorical interface"""
        logger.debug(f"StorageBackendAdapter.store called with {len(messages)} messages for backend {self.format_name}")
        
        if not self._started:
            logger.info(f"Backend {self.format_name} not started, starting now")
            await self.start()
        
        # Transform messages to legacy format
        legacy_messages = []
        for i, msg in enumerate(messages):
            logger.debug(f"Processing message {i+1}/{len(messages)}: {msg.message_id}")
            
            if hasattr(self.legacy_backend, 'store_message'):
                # Legacy v2 interface
                logger.debug(f"Using v2 interface (store_message) for {self.format_name}")
                legacy_messages.append(msg.data)
            elif hasattr(self.legacy_backend, 'write_tick_message'):
                # V3 interface expects TickMessage
                logger.debug(f"Using v3 interface (write_tick_message) for {self.format_name}")
                tick_msg = self._to_tick_message(msg)
                if tick_msg:
                    legacy_messages.append(tick_msg)
                    logger.debug(f"Converted to TickMessage: {tick_msg.cid}, {tick_msg.ts}, {tick_msg.tt}")
                else:
                    logger.warning(f"Failed to convert StorageMessage to TickMessage for {self.format_name}")
        
        logger.debug(f"Converted {len(legacy_messages)} messages for {self.format_name} backend")
        
        # Batch store to legacy backend
        if hasattr(self.legacy_backend, 'store_message'):
            # v2 interface - store each message individually
            logger.debug(f"Storing {len(legacy_messages)} messages individually to {self.format_name} via store_message")
            for i, msg in enumerate(legacy_messages):
                try:
                    await self.legacy_backend.store_message(msg)
                    logger.debug(f"Stored message {i+1} to {self.format_name}")
                except Exception as e:
                    logger.error(f"Failed to store message {i+1} to {self.format_name}: {e}")
        elif hasattr(self.legacy_backend, 'write_tick_messages'):
            # v3 interface - batch write all messages
            if legacy_messages:
                logger.debug(f"Batch writing {len(legacy_messages)} TickMessages to {self.format_name} via write_tick_messages")
                try:
                    await self.legacy_backend.write_tick_messages(legacy_messages)
                    logger.debug(f"Successfully batch wrote {len(legacy_messages)} messages to {self.format_name}")
                except Exception as e:
                    logger.error(f"Failed to batch write to {self.format_name}: {e}")
            else:
                logger.warning(f"No messages to write to {self.format_name}")
        elif hasattr(self.legacy_backend, 'write_tick_message'):
            # v3 interface - individual writes
            logger.info(f"Writing {len(legacy_messages)} TickMessages individually to {self.format_name} via write_tick_message")
            for i, msg in enumerate(legacy_messages):
                try:
                    await self.legacy_backend.write_tick_message(msg)
                    logger.debug(f"Wrote TickMessage {i+1} to {self.format_name}")
                except Exception as e:
                    logger.error(f"Failed to write TickMessage {i+1} to {self.format_name}: {e}")
        else:
            logger.error(f"Backend {self.format_name} has no compatible write interface")
    
    async def query(self, query: StorageQuery) -> AsyncIterator[StorageMessage]:
        """Adapt legacy query interface to categorical interface"""
        if not self._started:
            await self.start()
        
        # Transform query to legacy format and execute
        if hasattr(self.legacy_backend, 'query_range'):
            async for legacy_msg in self.legacy_backend.query_range(
                start_time=query.start_time,
                end_time=query.end_time,
                contract_id=query.contract_id,
                limit=query.limit
            ):
                # Transform legacy result back to StorageMessage
                storage_msg = self._from_legacy_message(legacy_msg)
                if storage_msg:
                    yield storage_msg
    
    async def start(self) -> None:
        """Start legacy backend (idempotent)"""
        if self._started:
            return  # Identity property
        
        if hasattr(self.legacy_backend, 'start'):
            await self.legacy_backend.start()
        self._started = True
    
    async def stop(self) -> None:
        """Stop legacy backend (idempotent)"""
        if not self._started:
            return  # Identity property
        
        if hasattr(self.legacy_backend, 'stop'):
            await self.legacy_backend.stop()
        self._started = False
    
    def get_info(self) -> Dict[str, Any]:
        """Get backend info (pure function)"""
        info = {"format": self.format_name, "started": self._started}
        
        if hasattr(self.legacy_backend, 'get_storage_info'):
            legacy_info = self.legacy_backend.get_storage_info()
            info.update(legacy_info)
        
        return info
    
    def _to_tick_message(self, storage_msg: StorageMessage) -> Optional[TickMessage]:
        """Convert StorageMessage to TickMessage for v3 backends"""
        try:
            data = storage_msg.data
            logger.debug(f"Converting StorageMessage to TickMessage. Data keys: {list(data.keys())}")
            
            # Check if it's a nested v2 format with data.data structure
            if 'data' in data and isinstance(data['data'], dict):
                logger.debug(f"Found nested data structure. Inner data keys: {list(data['data'].keys())}")
            
            # Handle TickMessage format (transformed by TickMessageTransformer)
            if 'ts' in data and 'cid' in data and 'tt' in data:
                logger.debug("Using TickMessage format conversion")
                return TickMessage(
                    ts=data['ts'],
                    st=data.get('st', 1),
                    cid=data['cid'],
                    tt=data['tt'],
                    rid=data.get('rid', 0),
                    p=data.get('p', 0.0),
                    s=data.get('s', 0.0),
                    bp=data.get('bp', 0.0),
                    bs=data.get('bs', 0.0),
                    ap=data.get('ap', 0.0),
                    as_=data.get('as_', 0.0),
                    mp=data.get('mp', 0.0),
                    bpl=data.get('bpl', 0.0),
                    aph=data.get('aph', 0.0),
                    upt=data.get('upt', 0.0)
                )
            
            # Handle v2 format (transformed by V2ToV3Transformer) 
            elif 'tick_type' in data and 'price' in data:
                logger.debug("Using v2 format conversion")
                return TickMessage(
                    ts=int(storage_msg.timestamp.timestamp()),
                    st=1,
                    cid=storage_msg.contract_id or 0,
                    tt=data['tick_type'],
                    rid=0,
                    p=data['price'],
                    s=data.get('size', 0.0)
                )
            
            # Handle nested v2 format (new v2 stream format with data.data structure)
            elif 'data' in data and isinstance(data['data'], dict):
                inner_data = data['data']
                logger.debug(f"Using nested v2 format conversion for type: {inner_data.get('type', 'unknown')}")
                
                # Extract contract_id from stream_id (e.g., 'bg_711280073_bid_ask' -> 711280073)
                contract_id = storage_msg.contract_id
                if not contract_id and 'stream_id' in data:
                    try:
                        # Extract contract_id from stream_id pattern
                        parts = data['stream_id'].split('_')
                        if len(parts) >= 2:
                            contract_id = int(parts[1])
                    except (ValueError, IndexError):
                        logger.warning(f"Could not extract contract_id from stream_id: {data.get('stream_id')}")
                        contract_id = 0
                
                # Map nested data to TickMessage based on tick type
                tick_type = inner_data.get('type', 'unknown')
                
                if tick_type == 'bid_ask':
                    # Use the proper factory method that handles timestamp conversion automatically
                    return TickMessage.create_from_tick_data(
                        contract_id=contract_id or 0,
                        tick_type="bid_ask",
                        tick_data=inner_data,
                        request_id=0
                    )
                elif tick_type == 'last':
                    # Use the proper factory method that handles timestamp conversion automatically
                    return TickMessage.create_from_tick_data(
                        contract_id=contract_id or 0,
                        tick_type="last",
                        tick_data=inner_data,
                        request_id=0
                    )
                elif tick_type == 'time_sales':
                    # Use the proper factory method that handles timestamp conversion automatically
                    # Map time_sales to 'last' tick type for compatibility
                    return TickMessage.create_from_tick_data(
                        contract_id=contract_id or 0,
                        tick_type="last",  # time_sales maps to 'last' tick type
                        tick_data=inner_data,
                        request_id=0
                    )
                else:
                    logger.error(f"Unknown nested tick type: {tick_type}. Available types: bid_ask, last, time_sales. Message will be dropped.")
                    # Consider adding metrics for dropped messages
                    return None
            else:
                logger.warning(f"No matching format for StorageMessage. Data keys: {list(data.keys())}")
                
        except Exception as e:
            logger.warning(f"Could not convert StorageMessage to TickMessage: {e}, Data: {data}")
        return None
    
    def _from_legacy_message(self, legacy_msg: Any) -> Optional[StorageMessage]:
        """Convert legacy message to StorageMessage"""
        try:
            if isinstance(legacy_msg, dict):
                return StorageMessage(
                    message_id=f"legacy_{datetime.now().timestamp()}",
                    timestamp=datetime.fromisoformat(legacy_msg.get('timestamp', datetime.now().isoformat())),
                    contract_id=legacy_msg.get('contract_id'),
                    data=legacy_msg,
                    format_version="legacy"
                )
            elif hasattr(legacy_msg, 'to_dict'):
                return StorageMessage(
                    message_id=f"tick_{datetime.now().timestamp()}",
                    timestamp=legacy_msg.timestamp,
                    contract_id=legacy_msg.contract_id,
                    data=legacy_msg.to_dict(),
                    format_version="v3"
                )
        except Exception as e:
            logger.debug("Could not convert legacy message: %s", e)
        return None


class CategoricalStorageOrchestrator:
    """
    Storage orchestrator using categorical composition.
    
    This class implements proper limits/colimits in the category of storage backends:
    - Product: Parallel storage across multiple backends
    - Coproduct: Fallback storage with automatic switching
    - Natural transformations: Format conversions between backends
    """
    
    def __init__(self):
        self.backends: Dict[str, StorageBackend] = {}
        self.transformers: Dict[str, MessageTransformer] = {
            'v2_to_v3': V2ToV3Transformer(),
            'tick_to_storage': TickMessageTransformer()
        }
        self._started = False
    
    def add_backend(self, name: str, backend: StorageBackend) -> None:
        """Add storage backend (categorical composition)"""
        self.backends[name] = backend
        logger.info("Added storage backend: %s", name)
    
    def remove_backend(self, name: str) -> None:
        """Remove storage backend"""
        if name in self.backends:
            del self.backends[name]
            logger.info("Removed storage backend: %s", name)
    
    async def start(self) -> None:
        """Start all backends (idempotent)"""
        if self._started:
            return  # Identity property
        
        for name, backend in self.backends.items():
            try:
                await backend.start()
                logger.info("Started storage backend: %s", name)
            except Exception as e:
                logger.error("Failed to start backend %s: %s", name, e)
        
        self._started = True
        logger.info("Storage orchestrator started with %d backends", len(self.backends))
    
    async def stop(self) -> None:
        """Stop all backends (idempotent)"""
        if not self._started:
            return  # Identity property
        
        for name, backend in self.backends.items():
            try:
                await backend.stop()
                logger.info("Stopped storage backend: %s", name)
            except Exception as e:
                logger.error("Failed to stop backend %s: %s", name, e)
        
        self._started = False
        logger.info("Storage orchestrator stopped")
    
    async def store_v2_message(self, v2_message: Dict[str, Any]) -> None:
        """
        Store v2 message using natural transformations.
        
        This demonstrates categorical composition:
        v2_message -> StorageMessage -> [Backend1, Backend2, ...]
        """
        logger.debug(f"CategoricalStorageOrchestrator.store_v2_message called with message: {v2_message.get('contract_id', 'unknown_contract')}")
        
        # Transform v2 to categorical format
        transformer = self.transformers['v2_to_v3']
        storage_msg = transformer.transform(v2_message)
        
        if storage_msg:
            logger.debug(f"Successfully transformed v2 message to StorageMessage: {storage_msg.message_id}")
            await self.store_messages([storage_msg])
        else:
            logger.error(f"Failed to transform v2 message to StorageMessage")
    
    async def store_tick_message(self, tick_message: TickMessage) -> None:
        """
        Store TickMessage using natural transformations.
        
        TickMessage -> StorageMessage -> [Backend1, Backend2, ...]
        """
        transformer = self.transformers['tick_to_storage']
        storage_msg = transformer.transform(tick_message)
        
        await self.store_messages([storage_msg])
    
    async def store_messages(self, messages: List[StorageMessage]) -> None:
        """
        Store messages to all backends (categorical product).
        
        This implements the product in the category of storage backends:
        messages get stored to all backends in parallel.
        """
        if not messages:
            logger.debug("No messages to store, returning early")
            return  # Identity property
        
        logger.debug(f"CategoricalStorageOrchestrator.store_messages called with {len(messages)} messages to {len(self.backends)} backends")
        
        # Parallel storage across all backends (categorical product)
        store_tasks = []
        for name, backend in self.backends.items():
            logger.debug(f"Creating storage task for backend: {name}")
            task = asyncio.create_task(self._safe_store(name, backend, messages))
            store_tasks.append(task)
        
        # Wait for all storage operations to complete
        if store_tasks:
            logger.debug(f"Executing {len(store_tasks)} storage tasks in parallel")
            await asyncio.gather(*store_tasks, return_exceptions=True)
            logger.info(f"Completed storage to all {len(store_tasks)} backends")
    
    async def query_messages(self, query: StorageQuery, 
                           preferred_backend: Optional[str] = None) -> AsyncIterator[StorageMessage]:
        """
        Query messages with backend preference (categorical coproduct).
        
        This implements fallback behavior as a coproduct: try preferred backend,
        fall back to others if it fails.
        """
        if preferred_backend and preferred_backend in self.backends:
            try:
                async for msg in self.backends[preferred_backend].query(query):
                    yield msg
                return  # Successfully used preferred backend
            except Exception as e:
                logger.warning("Preferred backend %s failed, trying others: %s", preferred_backend, e)
        
        # Fallback to first available backend (coproduct behavior)
        for name, backend in self.backends.items():
            if name == preferred_backend:
                continue  # Already tried
            
            try:
                async for msg in backend.query(query):
                    yield msg
                return  # Successfully used fallback backend
            except Exception as e:
                logger.warning("Backend %s failed: %s", name, e)
        
        logger.error("All storage backends failed for query")
    
    async def _safe_store(self, name: str, backend: StorageBackend, 
                         messages: List[StorageMessage]) -> None:
        """Safely store to backend with error handling"""
        try:
            await backend.store(messages)
            logger.debug("Stored %d messages to %s", len(messages), name)
        except Exception as e:
            logger.error("Failed to store to backend %s: %s", name, e)
    
    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status (pure function)"""
        backend_info = {}
        for name, backend in self.backends.items():
            backend_info[name] = backend.get_info()
        
        return {
            "started": self._started,
            "backend_count": len(self.backends),
            "backends": backend_info,
            "transformers": list(self.transformers.keys())
        }