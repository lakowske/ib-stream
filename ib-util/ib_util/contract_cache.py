"""
Efficient Contract Cache Management
Provides fast contract ID lookup and indexing for ib-contract service
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Set
from datetime import datetime, timedelta
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class ContractCacheEntry:
    """Single contract cache entry with metadata"""
    contract_data: Dict
    cache_key: str
    cached_at: datetime
    file_path: Optional[Path] = None
    
    @property
    def contract_id(self) -> int:
        return self.contract_data.get("con_id", 0)
    
    def is_expired(self, ttl_hours: int = 24) -> bool:
        """Check if cache entry is expired"""
        return datetime.now() - self.cached_at > timedelta(hours=ttl_hours)

class ContractIndex:
    """
    Fast contract ID to cache entry mapping
    Thread-safe indexing system for efficient contract lookup
    """
    
    def __init__(self):
        self._contract_to_entry: Dict[int, ContractCacheEntry] = {}
        self._lock = threading.RLock()
        self._last_rebuild = datetime.now()
        
    def add_contract(self, contract_data: Dict, cache_key: str, file_path: Optional[Path] = None):
        """Add or update contract in index"""
        contract_id = contract_data.get("con_id")
        if not contract_id:
            logger.warning("Contract data missing con_id, skipping index")
            return
        
        try:
            with self._lock:
                entry = ContractCacheEntry(
                    contract_data=contract_data,
                    cache_key=cache_key,
                    cached_at=datetime.now(),
                    file_path=file_path
                )
                self._contract_to_entry[contract_id] = entry
                logger.debug(f"Indexed contract {contract_id} with cache key {cache_key}")
        except Exception as e:
            logger.error(f"Failed to index contract {contract_id}: {e}")
    
    def find_by_contract_id(self, contract_id: int) -> Optional[ContractCacheEntry]:
        """Fast lookup of contract by ID"""
        with self._lock:
            return self._contract_to_entry.get(contract_id)
    
    def remove_contract(self, contract_id: int) -> bool:
        """Remove contract from index"""
        with self._lock:
            return self._contract_to_entry.pop(contract_id, None) is not None
    
    def get_all_contract_ids(self) -> Set[int]:
        """Get all indexed contract IDs"""
        with self._lock:
            return set(self._contract_to_entry.keys())
    
    def cleanup_expired(self, ttl_hours: int = 24) -> int:
        """Remove expired entries from index"""
        removed = 0
        with self._lock:
            expired_ids = [
                cid for cid, entry in self._contract_to_entry.items()
                if entry.is_expired(ttl_hours)
            ]
            
            for contract_id in expired_ids:
                del self._contract_to_entry[contract_id]
                removed += 1
        
        if removed > 0:
            logger.info(f"Cleaned up {removed} expired contract cache entries")
        
        return removed
    
    def rebuild_from_cache_manager(self, cache_manager):
        """
        Rebuild index from existing cache manager
        Should be called when cache manager is initialized or periodically
        """
        rebuilt = 0
        try:
            with self._lock:
                # Clear existing index
                self._contract_to_entry.clear()
                
                # Rebuild from memory cache
                for cache_key, cached_data in cache_manager._memory_cache.items():
                    contracts_found = self._extract_contracts_from_cache_data(cached_data, cache_key)
                    rebuilt += contracts_found
                
                # Rebuild from file cache
                cache_dir = cache_manager.cache_dir
                if cache_dir.exists():
                    for cache_file in self._get_safe_cache_files(cache_dir, cache_manager.prefix):
                        try:
                            with open(cache_file, 'r') as f:
                                cached_data = json.load(f)
                            
                            cache_key = cache_file.stem
                            contracts_found = self._extract_contracts_from_cache_data(
                                cached_data, cache_key, cache_file
                            )
                            rebuilt += contracts_found
                            
                        except (json.JSONDecodeError, IOError) as e:
                            logger.debug(f"Could not read cache file {cache_file}: {e}")
                
                self._last_rebuild = datetime.now()
                logger.info(f"Rebuilt contract index with {rebuilt} contracts from {len(self._contract_to_entry)} entries")
        
        except Exception as e:
            logger.error(f"Failed to rebuild contract index: {e}")
        
        return rebuilt
    
    def _get_safe_cache_files(self, cache_dir: Path, prefix: str) -> list:
        """
        Safely get cache files, preventing path traversal attacks
        
        Args:
            cache_dir: Cache directory path
            prefix: Cache file prefix
            
        Returns:
            List of safe cache file paths
        """
        try:
            # Get all matching files - handle date-prefixed names (YYYYMMDD-prefix_*.json)
            pattern_files = list(cache_dir.glob(f"*-{prefix}_*.json"))
            if not pattern_files:
                # Fallback to non-prefixed pattern  
                pattern_files = list(cache_dir.glob(f"{prefix}_*.json"))
            
            # Security check: ensure all files are within cache directory
            safe_files = []
            for file_path in pattern_files:
                # Resolve to absolute path and check if it's within cache_dir
                resolved_path = file_path.resolve()
                resolved_cache_dir = cache_dir.resolve()
                
                if resolved_cache_dir in resolved_path.parents or resolved_path.parent == resolved_cache_dir:
                    if file_path.is_file():  # Additional check
                        safe_files.append(file_path)
                    else:
                        logger.warning(f"Skipping non-file: {file_path}")
                else:
                    logger.warning(f"Potential path traversal attempt detected: {file_path}")
            
            return safe_files
            
        except Exception as e:
            logger.error(f"Error getting safe cache files: {e}")
            return []
    
    def _extract_contracts_from_cache_data(self, cached_data: Dict, cache_key: str, 
                                         file_path: Optional[Path] = None) -> int:
        """Extract contracts from cache data structure and add to index"""
        contracts_added = 0
        
        if not isinstance(cached_data, dict):
            return 0
        
        try:
            # Handle contracts_by_type structure
            contracts_by_type = cached_data.get("contracts_by_type", {})
            for sec_type, type_data in contracts_by_type.items():
                if isinstance(type_data, dict) and "contracts" in type_data:
                    contracts_list = type_data["contracts"]
                elif isinstance(type_data, list):
                    contracts_list = type_data
                else:
                    continue
                
                for contract in contracts_list:
                    if isinstance(contract, dict) and contract.get("con_id"):
                        self.add_contract(contract, cache_key, file_path)
                        contracts_added += 1
            
            # Handle direct contracts list if present
            contracts_list = cached_data.get("contracts", [])
            for contract in contracts_list:
                if isinstance(contract, dict) and contract.get("con_id"):
                    self.add_contract(contract, cache_key, file_path)
                    contracts_added += 1
        
        except Exception as e:
            logger.error(f"Error extracting contracts from cache data: {e}")
        
        return contracts_added
    
    def get_stats(self) -> Dict:
        """Get index statistics for monitoring"""
        with self._lock:
            return {
                "total_contracts": len(self._contract_to_entry),
                "last_rebuild": self._last_rebuild.isoformat(),
                "memory_usage_contracts": len(self._contract_to_entry)
            }

# Global contract index instance
_global_contract_index = None

def get_contract_index() -> ContractIndex:
    """Get or create global contract index instance"""
    global _global_contract_index
    if _global_contract_index is None:
        _global_contract_index = ContractIndex()
    return _global_contract_index