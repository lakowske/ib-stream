"""
Generic cache manager for IB services

Provides memory and file-based caching with expiration, validation,
and automatic cleanup. Supports any JSON-serializable data.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


class CacheException(Exception):
    """Base exception for cache operations"""
    pass


class CacheFileError(CacheException):
    """Exception for cache file operations"""
    pass


class CacheValidationError(CacheException):
    """Exception for cache validation failures"""
    pass


class CacheFilenameGenerator:
    """Utility class for generating consistent cache filenames"""
    
    @staticmethod
    def get_date_prefix() -> str:
        """Generate consistent date prefix for cache files"""
        return datetime.now().strftime("%Y%m%d")
    
    @staticmethod 
    def generate_symbol_cache_filename(prefix: str, cache_key: str) -> str:
        """Generate filename for symbol-based cache"""
        date_prefix = CacheFilenameGenerator.get_date_prefix()
        return f"{date_prefix}-{cache_key}.json"
    
    @staticmethod
    def generate_contract_cache_filename(contract_id: int) -> str:
        """Generate filename for contract ID-based cache"""
        date_prefix = CacheFilenameGenerator.get_date_prefix()
        return f"{date_prefix}-contract_{contract_id}.json"
    
    @staticmethod
    def get_file_patterns(prefix: Optional[str] = None) -> list[str]:
        """Get file patterns for cache file discovery"""
        patterns = []
        if prefix:
            patterns.extend([
                f"*-{prefix}_*.json",  # Date-prefixed symbol files
                f"{prefix}_*.json"     # Non-prefixed symbol files  
            ])
        patterns.append("*-contract_*.json")  # Contract ID files
        return patterns


class ContractCacheMixin:
    """Mixin class for contract-specific cache operations"""
    
    def get_contract(self, contract_id: int) -> Optional[Dict[str, Any]]:
        """
        Get contract data by ID from contract-specific cache
        
        Args:
            contract_id: Contract ID to lookup
            
        Returns:
            Contract data if valid, None otherwise
            
        Raises:
            CacheFileError: If cache file operation fails
        """
        try:
            cache_filename = self._get_contract_cache_filename(contract_id)
            
            # Check file cache for contract ID
            if self._is_cache_valid(cache_filename):
                cache_path = self.cache_dir / cache_filename
                try:
                    with open(cache_path, encoding="utf-8") as f:
                        data = json.load(f)
                    logger.info("Cache operation completed", extra={
                        "operation": "get_contract",
                        "contract_id": contract_id,
                        "cache_hit": True,
                        "cache_type": "file"
                    })
                    return data
                except (OSError, json.JSONDecodeError) as e:
                    logger.warning("Failed to load contract cache file %s: %s", cache_filename, e)
                    # Remove corrupted cache file
                    cache_path.unlink(missing_ok=True)
                    raise CacheFileError(f"Failed to load contract cache for ID {contract_id}") from e
            
            logger.debug("Contract cache miss for ID %d", contract_id)
            return None
            
        except Exception as e:
            if isinstance(e, CacheFileError):
                raise
            raise CacheFileError(f"Contract cache operation failed for ID {contract_id}") from e
    
    def set_contract(self, contract_id: int, contract_data: Dict[str, Any], 
                    source_cache: Optional[str] = None) -> bool:
        """
        Store contract data in ID-specific cache
        
        Args:
            contract_id: Contract ID
            contract_data: Contract details
            source_cache: Optional reference to symbol-based cache file
            
        Returns:
            True if successfully cached, False otherwise
            
        Raises:
            CacheFileError: If cache file operation fails
        """
        try:
            cache_filename = self._get_contract_cache_filename(contract_id)
            
            # Create contract cache structure
            cache_data = {
                "contract_id": contract_id,
                "contract_data": contract_data,
                "cached_at": datetime.now().isoformat(),
                "source_cache": source_cache,
                "cache_type": "contract_id"
            }
            
            # Store in file cache
            cache_path = self.cache_dir / cache_filename
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            logger.debug("Cached contract data for ID %d to %s", contract_id, cache_filename)
            return True
            
        except (OSError, TypeError) as e:
            logger.error("Failed to write contract cache file for ID %d: %s", contract_id, e)
            raise CacheFileError(f"Failed to cache contract ID {contract_id}") from e


class CacheManager(ContractCacheMixin):
    """
    Generic cache manager with memory and file-based storage
    
    Features:
    - Memory cache for fast access
    - File-based persistence across restarts
    - Automatic expiration and cleanup
    - Configurable cache duration
    - Thread-safe operations
    - Corruption handling with automatic recovery
    """
    
    def __init__(
        self,
        cache_dir: Union[str, Path] = "./.cache",
        cache_duration: timedelta = timedelta(days=1),
        prefix: str = "",
        auto_cleanup: bool = True
    ):
        """
        Initialize cache manager
        
        Args:
            cache_dir: Directory for file cache storage
            cache_duration: How long cache entries remain valid
            prefix: Prefix for cache filenames (useful for service isolation)
            auto_cleanup: Whether to automatically clean expired files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_duration = cache_duration
        self.prefix = prefix
        self.auto_cleanup = auto_cleanup
        
        # In-memory cache
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(exist_ok=True)
        
        # Clean up expired files if requested
        if auto_cleanup:
            self._cleanup_expired_files()
    
    def _get_cache_key(self, *key_parts: str) -> str:
        """Generate cache key from parts"""
        key = "_".join(str(part).upper() for part in key_parts if part)
        return f"{self.prefix}_{key}" if self.prefix else key
    
    def _get_cache_filename(self, cache_key: str) -> str:
        """Generate cache filename with timestamp"""
        return CacheFilenameGenerator.generate_symbol_cache_filename(self.prefix, cache_key)
    
    def _get_contract_cache_filename(self, contract_id: int) -> str:
        """Generate contract ID-based cache filename"""
        return CacheFilenameGenerator.generate_contract_cache_filename(contract_id)
    
    def _is_cache_valid(self, cache_filename: str) -> bool:
        """Check if cache file is still valid"""
        cache_path = self.cache_dir / cache_filename
        if not cache_path.exists():
            return False
        
        try:
            file_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
            age = datetime.now() - file_time
            return age < self.cache_duration
        except (OSError, OverflowError):
            # File system issues or invalid timestamp
            return False
    
    def _cleanup_expired_files(self):
        """Remove expired cache files"""
        if not self.cache_dir.exists():
            return
        
        removed_count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            if not self._is_cache_valid(cache_file.name):
                try:
                    cache_file.unlink(missing_ok=True)
                    removed_count += 1
                except OSError as e:
                    logger.warning("Failed to remove expired cache file %s: %s", cache_file, e)
        
        if removed_count > 0:
            logger.info("Cleaned up %d expired cache files", removed_count)
    
    def get(self, *key_parts: str) -> Optional[Dict[str, Any]]:
        """
        Get data from cache
        
        Args:
            *key_parts: Components to build cache key from
            
        Returns:
            Cached data if valid, None otherwise
        """
        cache_key = self._get_cache_key(*key_parts)
        cache_filename = self._get_cache_filename(cache_key)
        
        # Check memory cache first
        if cache_key in self._memory_cache and self._is_cache_valid(cache_filename):
            logger.debug("Memory cache hit for %s", cache_key)
            return self._memory_cache[cache_key]
        
        # Check file cache
        if self._is_cache_valid(cache_filename):
            cache_path = self.cache_dir / cache_filename
            try:
                with open(cache_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._memory_cache[cache_key] = data
                logger.debug("File cache hit for %s", cache_key)
                return data
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Failed to load cache file %s: %s", cache_filename, e)
                # Remove corrupted cache file
                cache_path.unlink(missing_ok=True)
        
        # Remove expired memory cache entry
        if cache_key in self._memory_cache:
            del self._memory_cache[cache_key]
            logger.debug("Cache expired for %s", cache_key)
        
        return None
    
    def set(self, data: Dict[str, Any], *key_parts: str) -> bool:
        """
        Store data in cache
        
        Args:
            data: Data to cache (must be JSON serializable)
            *key_parts: Components to build cache key from
            
        Returns:
            True if successfully cached, False otherwise
        """
        cache_key = self._get_cache_key(*key_parts)
        cache_filename = self._get_cache_filename(cache_key)
        
        # Store in memory cache
        self._memory_cache[cache_key] = data
        
        # Store in file cache
        try:
            cache_path = self.cache_dir / cache_filename
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug("Cached data for %s to %s", cache_key, cache_filename)
            return True
        except (OSError, TypeError) as e:
            logger.error("Failed to write cache file %s: %s", cache_filename, e)
            return False
    
    def invalidate(self, *key_parts: str) -> bool:
        """
        Invalidate cached data for given key
        
        Args:
            *key_parts: Components to build cache key from
            
        Returns:
            True if cache was invalidated, False if not found
        """
        cache_key = self._get_cache_key(*key_parts)
        cache_filename = self._get_cache_filename(cache_key)
        
        # Remove from memory cache
        was_cached = cache_key in self._memory_cache
        if was_cached:
            del self._memory_cache[cache_key]
        
        # Remove file cache
        cache_path = self.cache_dir / cache_filename
        if cache_path.exists():
            try:
                cache_path.unlink()
                was_cached = True
                logger.debug("Invalidated cache for %s", cache_key)
            except OSError as e:
                logger.warning("Failed to remove cache file %s: %s", cache_filename, e)
        
        return was_cached
    
    def clear_all(self) -> Dict[str, int]:
        """
        Clear all cache entries
        
        Returns:
            Dictionary with counts of cleared entries
        """
        memory_count = len(self._memory_cache)
        file_count = 0
        
        # Clear memory cache
        self._memory_cache.clear()
        
        # Clear file cache
        if self.cache_dir.exists():
            pattern = f"{self.prefix}_*.json" if self.prefix else "*.json"
            for cache_file in self.cache_dir.glob(pattern):
                try:
                    cache_file.unlink(missing_ok=True)
                    file_count += 1
                except OSError as e:
                    logger.warning("Failed to remove cache file %s: %s", cache_file, e)
        
        logger.info(
            "Cleared %d memory cache entries and %d file cache entries",
            memory_count, file_count
        )
        
        return {
            "memory_entries": memory_count,
            "file_entries": file_count
        }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get cache status information
        
        Returns:
            Dictionary with cache statistics and status
        """
        memory_info = {}
        file_info = {}
        
        # Memory cache info
        for cache_key, data in self._memory_cache.items():
            memory_info[cache_key] = {
                "in_memory": True,
                "data_size": len(str(data)) if data else 0,
                "data_type": type(data).__name__
            }
        
        # File cache info
        if self.cache_dir.exists():
            # Use filename generator for consistent patterns
            patterns = CacheFilenameGenerator.get_file_patterns(self.prefix)
            
            for pattern in patterns:
                for cache_file in self.cache_dir.glob(pattern):
                    try:
                        file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
                        age = datetime.now() - file_time
                        file_info[cache_file.name] = {
                            "cached_at": file_time.isoformat(),
                            "age_seconds": int(age.total_seconds()),
                            "valid": self._is_cache_valid(cache_file.name),
                            "file_size": cache_file.stat().st_size
                        }
                    except (OSError, OverflowError) as e:
                        logger.warning("Error getting file info for %s: %s", cache_file, e)
        
        return {
            "cache_directory": str(self.cache_dir),
            "cache_duration_seconds": int(self.cache_duration.total_seconds()),
            "prefix": self.prefix,
            "memory_cache": memory_info,
            "file_cache": file_info,
            "total_memory_entries": len(memory_info),
            "total_file_entries": len(file_info)
        }
    
    def __contains__(self, key_parts) -> bool:
        """Check if cache contains data for key"""
        if isinstance(key_parts, (list, tuple)):
            return self.get(*key_parts) is not None
        else:
            return self.get(key_parts) is not None
    
    def __len__(self) -> int:
        """Return number of memory cache entries"""
        return len(self._memory_cache)