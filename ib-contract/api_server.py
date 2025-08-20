#!/usr/bin/env python3
"""
FastAPI Server for Contract Lookup - Refactored Version
Uses BaseAPIServer and CacheManager for reduced code duplication and improved maintainability.
"""

import asyncio
import time
from datetime import timedelta
from typing import Any, Dict, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from ib_util import BaseAPIServer, CacheManager, create_standardized_health_response, create_standardized_error_response
from contract_lookup import ContractLookupApp


class ContractAPIServer(BaseAPIServer):
    """
    Contract lookup API server using BaseAPIServer and CacheManager
    
    This refactored version eliminates ~200 lines of duplicated code
    while maintaining all original functionality.
    """
    
    def __init__(self):
        super().__init__(
            service_name="ib-contract",
            service_type="contracts",
            title="TWS Contract Lookup API",
            description="Interactive Brokers TWS API contract lookup with file-based caching",
            verbose_logging=True
        )
        
        # Initialize cache manager with 1-day expiration
        # Use absolute path to avoid working directory issues
        from pathlib import Path
        cache_dir = Path(__file__).parent / ".cache"
        self.cache = CacheManager(
            cache_dir=str(cache_dir),
            cache_duration=timedelta(days=1),
            prefix="contracts",
            auto_cleanup=True
        )
        
        # Initialize contract index for fast lookups
        from ib_util import get_contract_index, TradingHoursServiceFactory
        self.contract_index = get_contract_index()
        
        # Initialize trading hours service with SOLID principles
        self.trading_hours_service = TradingHoursServiceFactory.create_service(
            self.contract_index, 
            self.cache
        )
        
        # TWS connection state
        self.tws_app: Optional[ContractLookupApp] = None
        
        # Valid security types
        self.valid_security_types = ["STK", "FUT", "OPT", "CASH", "IND", "CFD", "BOND", "FUND", "CMDTY"]
    
    def setup_endpoints(self):
        """Setup contract-specific endpoints"""
        
        @self.app.get("/lookup/{ticker}")
        async def lookup_ticker(ticker: str):
            """Lookup all contracts for a ticker"""
            try:
                self.logger.info("Looking up all contracts for ticker: %s", ticker)
                data = await self._lookup_contracts(ticker)
                return data
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Error looking up ticker %s: %s", ticker, e)
                raise HTTPException(
                    status_code=500, 
                    detail=f"Internal server error: {str(e)}"
                ) from e
        
        @self.app.get("/lookup/{ticker}/{sec_type}")
        async def lookup_ticker_with_type(ticker: str, sec_type: str):
            """Lookup contracts for a ticker with specific security type"""
            sec_type_upper = sec_type.upper()
            
            if sec_type_upper not in self.valid_security_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid security type: {sec_type}. Valid types: {', '.join(self.valid_security_types)}",
                )
            
            try:
                self.logger.info("Looking up %s contracts for ticker: %s", sec_type_upper, ticker)
                data = await self._lookup_contracts(ticker, sec_type_upper)
                return data
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Error looking up ticker %s with type %s: %s", ticker, sec_type, e)
                raise HTTPException(
                    status_code=500, 
                    detail=f"Internal server error: {str(e)}"
                ) from e
        
        @self.app.get("/contracts/{contract_id}")
        async def get_contract(contract_id: int):
            """Get contract details by contract ID"""
            try:
                # Validate contract ID first
                from ib_util import validate_contract_id, ValidationError
                
                try:
                    contract_id = validate_contract_id(contract_id)
                except ValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                
                # Try contract ID-specific cache first (fast path)
                cached_contract = self.cache.get_contract(contract_id)
                if cached_contract:
                    self.logger.debug(f"Contract cache hit for ID {contract_id}")
                    contract_data = cached_contract["contract_data"]
                else:
                    # Find contract using reliable cache search (symbol-based cache)
                    contract_data = await self._find_contract_by_id_fast(contract_id)
                    if not contract_data:
                        # Try slow path as backup
                        contract_data = self._find_contract_by_id_slow(contract_id)
                    
                    # If found in symbol-based cache, create ID-specific cache entry for faster future access
                    if contract_data:
                        try:
                            self.cache.set_contract(contract_id, contract_data, "symbol_cache")
                            self.logger.debug(f"Created ID-specific cache entry for contract {contract_id}")
                        except Exception as e:
                            self.logger.warning(f"Failed to create ID-specific cache for contract {contract_id}: {e}")
                    
                    if not contract_data:
                        # Contract not in cache - try to fetch from IB Gateway by ID
                        self.logger.info(f"Contract {contract_id} not in cache, attempting IB Gateway lookup...")
                        contract_data = await self._lookup_contract_by_id_from_ib(contract_id)
                        
                        if not contract_data:
                            raise HTTPException(
                                status_code=404,
                                detail=f"Contract ID {contract_id} not found in cache or IB Gateway. Contract may not exist or IB Gateway may be unavailable."
                            )
                
                return {
                    "status": "success",
                    "timestamp": self._get_current_timestamp(),
                    "contract_id": contract_id,
                    **contract_data
                }
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Error getting contract details for ID %d: %s", contract_id, e)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get contract details: {str(e)}"
                ) from e
        
        @self.app.get("/cache/status")
        async def cache_status():
            """Get cache status"""
            try:
                status = self.cache.get_status()
                return {
                    "status": "success",
                    "timestamp": self._get_current_timestamp(),
                    **status
                }
            except Exception as e:
                self.logger.error("Error getting cache status: %s", e)
                return create_standardized_error_response(
                    "Failed to get cache status",
                    error_code="CACHE_STATUS_ERROR",
                    details={"error": str(e)}
                )
        
        @self.app.delete("/cache/clear")
        async def clear_cache():
            """Clear all cache entries"""
            try:
                result = self.cache.clear_all()
                self.logger.info(
                    "Cleared %d memory cache entries and %d file cache entries",
                    result["memory_entries"], result["file_entries"]
                )
                return {
                    "status": "success",
                    "message": f"Cleared {result['memory_entries']} memory cache entries and {result['file_entries']} file cache entries",
                    "timestamp": self._get_current_timestamp(),
                    **result
                }
            except Exception as e:
                self.logger.error("Error clearing cache: %s", e)
                raise HTTPException(
                    status_code=500, 
                    detail=f"Failed to clear cache: {str(e)}"
                ) from e
        
        @self.app.get("/market-status/{contract_id}")
        async def get_market_status(contract_id: int):
            """Check if market is currently open for specific contract ID"""
            try:
                # Validate contract ID first
                from ib_util import validate_contract_id, ValidationError
                
                try:
                    contract_id = validate_contract_id(contract_id)
                except ValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                
                # Find contract using reliable cache search (fallback to slow path)
                contract_data = await self._find_contract_by_id_fast(contract_id)
                if not contract_data:
                    # Try slow path as backup
                    contract_data = self._find_contract_by_id_slow(contract_id)
                
                if not contract_data:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Contract ID {contract_id} not found in cache. Use /lookup endpoints to cache contract first."
                    )
                
                # Check market status using trading hours utilities directly
                from ib_util import check_contract_market_status
                
                market_status = check_contract_market_status(contract_data)
                response_data = market_status.to_dict()
                response_data["contract_info"] = {
                    "symbol": contract_data.get("symbol"),
                    "sec_type": contract_data.get("sec_type"), 
                    "exchange": contract_data.get("exchange"),
                    "currency": contract_data.get("currency")
                }
                
                return {
                    "status": "success",
                    "timestamp": self._get_current_timestamp(),
                    **response_data
                }
                
            except HTTPException:
                raise
            except ValidationError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                self.logger.error("Error getting market status for contract %d: %s", contract_id, e)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get market status: {str(e)}"
                ) from e
        
        @self.app.get("/trading-hours/{contract_id}")
        async def get_trading_hours(contract_id: int):
            """Get detailed trading hours information for specific contract ID"""
            try:
                # Validate contract ID first
                from ib_util import validate_contract_id, ValidationError
                
                try:
                    contract_id = validate_contract_id(contract_id)
                except ValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                
                # Find contract using reliable cache search
                contract_data = await self._find_contract_by_id_fast(contract_id)
                if not contract_data:
                    contract_data = self._find_contract_by_id_slow(contract_id)
                    
                if not contract_data:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Contract ID {contract_id} not found in cache. Use /lookup endpoints to cache contract first."
                    )
                
                return {
                    "status": "success",
                    "timestamp": self._get_current_timestamp(),
                    "contract_id": contract_id,
                    "contract_info": {
                        "symbol": contract_data.get("symbol"),
                        "sec_type": contract_data.get("sec_type"),
                        "exchange": contract_data.get("exchange"),
                        "currency": contract_data.get("currency"),
                        "market_name": contract_data.get("market_name")
                    },
                    "trading_hours_info": {
                        "time_zone_id": contract_data.get("time_zone_id"),
                        "trading_hours": contract_data.get("trading_hours"),
                        "liquid_hours": contract_data.get("liquid_hours"),
                        "retrieved_at": contract_data.get("retrieved_at")
                    }
                }
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Error getting trading hours for contract %d: %s", contract_id, e)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get trading hours: {str(e)}"
                ) from e
        
        @self.app.get("/trading-schedule/{contract_id}")
        async def get_trading_schedule(contract_id: int, days: int = 7):
            """Get upcoming trading schedule for specific contract ID"""
            try:
                # Validate inputs
                from ib_util import validate_contract_id, ValidationError
                
                try:
                    contract_id = validate_contract_id(contract_id)
                except ValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                    
                if days < 1 or days > 30:
                    raise HTTPException(
                        status_code=400,
                        detail="Days parameter must be between 1 and 30"
                    )
                
                # Find contract using reliable cache search
                contract_data = await self._find_contract_by_id_fast(contract_id)
                if not contract_data:
                    contract_data = self._find_contract_by_id_slow(contract_id)
                    
                if not contract_data:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Contract ID {contract_id} not found in cache. Use /lookup endpoints to cache contract first."
                    )
                
                # Get trading schedule
                from ib_util import get_contract_trading_schedule
                schedule = get_contract_trading_schedule(contract_data, days_ahead=days)
                
                return {
                    "status": "success", 
                    "timestamp": self._get_current_timestamp(),
                    "contract_id": contract_id,
                    "contract_info": {
                        "symbol": contract_data.get("symbol"),
                        "sec_type": contract_data.get("sec_type"),
                        "exchange": contract_data.get("exchange"),
                        "currency": contract_data.get("currency")
                    },
                    "days_requested": days,
                    "schedule": schedule
                }
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Error getting trading schedule for contract %d: %s", contract_id, e)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get trading schedule: {str(e)}"
                ) from e
    
    async def startup(self):
        """Service-specific startup logic"""
        self.logger.info("Attempting to establish TWS connection...")
        try:
            self._ensure_tws_connection()
            self.logger.info("TWS connection established successfully")
        except Exception as e:
            self.logger.warning("Failed to establish initial TWS connection: %s", e)
            self.logger.info("Will attempt to connect on first request")
    
    async def shutdown(self):
        """Service-specific shutdown logic"""
        if self.tws_app and self.tws_app.is_connected():
            self.tws_app.disconnect_and_stop()
            self.logger.info("TWS connection closed")
    
    def get_api_info(self) -> Dict[str, Any]:
        """Get contract service API information"""
        return {
            "description": "Interactive Brokers TWS API contract lookup with file-based caching and trading hours support",
            "endpoints": {
                "/lookup/{ticker}": "Get all contracts for a ticker",
                "/lookup/{ticker}/{sec_type}": "Get contracts for a ticker and security type",
                "/contracts/{contract_id}": "Get contract details by contract ID",
                "/market-status/{contract_id}": "Check if market is currently open for contract",
                "/trading-hours/{contract_id}": "Get detailed trading hours information",
                "/trading-schedule/{contract_id}": "Get upcoming trading schedule",
                "/health": "Health check with TWS connection status",
                "/cache/status": "Cache status and statistics",
                "/cache/clear": "Clear all cache entries",
            },
            "security_types": self.valid_security_types,
            "cache_duration_days": self.cache.cache_duration.days,
            "features": [
                "File-based caching with automatic expiration",
                "Memory caching for fast access",
                "Automatic cache cleanup",
                "Comprehensive error handling",
                "Connection pooling and retry logic",
                "Trading hours and market status detection",
                "Multi-timezone support",
                "Trading schedule forecasting"
            ]
        }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get service health status"""
        try:
            tws_connected = self.tws_app is not None and self.tws_app.is_connected()
            cache_status = self.cache.get_status()
            
            # Determine overall health status
            status = "healthy"
            if not tws_connected:
                status = "degraded"  # Can still serve cached data
            
            return create_standardized_health_response(
                service_name=self.service_name,
                status=status,
                details={
                    "tws_connected": tws_connected,
                    "cache_entries": len(self.cache),
                    "cache_directory": str(self.cache.cache_dir),
                    "total_memory_entries": cache_status["total_memory_entries"],
                    "total_file_entries": cache_status["total_file_entries"],
                    "client_id": self.config.client_id,
                    "connection_ports": self.config.ports
                }
            )
        except Exception as e:
            self.logger.error("Health check failed: %s", e)
            response = create_standardized_health_response(
                service_name=self.service_name,
                status="unhealthy",
                details={"error": str(e)}
            )
            return JSONResponse(status_code=503, content=response)
    
    def _ensure_tws_connection(self) -> ContractLookupApp:
        """Ensure TWS connection is active"""
        if self.tws_app is None or not self.tws_app.is_connected():
            self.logger.info("Establishing TWS connection...")
            self.tws_app = ContractLookupApp()
            if not self.tws_app.connect_and_start():
                msg = "Unable to connect to TWS/Gateway. Please ensure it's running with API enabled."
                raise HTTPException(status_code=503, detail=msg)
            self.logger.info("TWS connection established")
        
        return self.tws_app
    
    async def _lookup_contracts(self, ticker: str, sec_type: Optional[str] = None) -> Dict[str, Any]:
        """Lookup contracts using cache-first approach"""
        
        # Create cache key
        cache_key_parts = [ticker.upper()]
        if sec_type:
            cache_key_parts.append(sec_type.upper())
        else:
            cache_key_parts.append("ALL")
        
        # Check cache first
        cached_data = self.cache.get(*cache_key_parts)
        if cached_data:
            self.logger.debug("Cache hit for %s", "/".join(cache_key_parts))
            return cached_data
        
        self.logger.info("Cache miss for %s, fetching from TWS...", "/".join(cache_key_parts))
        
        # Get TWS connection
        app_instance = self._ensure_tws_connection()
        
        # Reset app state for new request
        app_instance.contracts = []
        app_instance.finished_requests = set()
        app_instance.total_requests = 0
        app_instance.ticker = None
        app_instance.requested_types = []
        app_instance.json_output = True
        
        # Request contracts
        sec_types = [sec_type] if sec_type else None
        app_instance.request_contracts(ticker.upper(), sec_types)
        
        # Wait for data with timeout
        timeout = 30
        start_time = time.time()
        
        while not app_instance.is_finished() and (time.time() - start_time) < timeout:
            await asyncio.sleep(0.1)
        
        if not app_instance.is_finished():
            raise HTTPException(
                status_code=408, 
                detail=f"Timeout waiting for contract data for {ticker}"
            )
        
        # Prepare response data
        if not app_instance.contracts:
            data = {
                "ticker": ticker.upper(),
                "timestamp": self._get_current_timestamp(),
                "security_types_searched": app_instance.requested_types,
                "total_contracts": 0,
                "contracts_by_type": {},
                "summary": {},
                "cached": False
            }
        else:
            data = app_instance._prepare_json_data()
            data["cached"] = False  # Mark as fresh data
        
        # Store in cache
        if self.cache.set(data, *cache_key_parts):
            self.logger.debug("Cached data for %s", "/".join(cache_key_parts))
            
            # Update contract index with new contracts
            try:
                cache_key = "/".join(cache_key_parts)
                contracts_added = 0
                
                # Add contracts to index
                contracts_by_type = data.get("contracts_by_type", {})
                for sec_type, type_data in contracts_by_type.items():
                    if isinstance(type_data, dict) and "contracts" in type_data:
                        contracts_list = type_data["contracts"]
                        for contract in contracts_list:
                            if isinstance(contract, dict) and contract.get("con_id"):
                                self.contract_index.add_contract(contract, cache_key)
                                contracts_added += 1
                
                if contracts_added > 0:
                    self.logger.debug(f"Added {contracts_added} contracts to index for {cache_key}")
                    
            except Exception as e:
                self.logger.warning(f"Failed to update contract index: {e}")
        else:
            self.logger.warning("Failed to cache data for %s", "/".join(cache_key_parts))
        
        return data
    
    async def _lookup_contract_by_id_from_ib(self, contract_id: int) -> Optional[Dict]:
        """
        Lookup contract details from IB Gateway using only contract ID
        
        Args:
            contract_id: IB contract ID to lookup
            
        Returns:
            Contract data dictionary if found, None if not found or error
        """
        try:
            # Get TWS connection
            app_instance = self._ensure_tws_connection()
            
            # Reset app state for new request
            app_instance.contracts = []
            app_instance.finished_requests = set()
            app_instance.total_requests = 0
            app_instance.ticker = None
            app_instance.requested_types = []
            app_instance.json_output = True
            
            # Request contract by ID
            app_instance.request_contract_by_id(contract_id)
            
            # Wait for data with timeout
            timeout = 15  # Shorter timeout for ID lookup
            start_time = time.time()
            
            while not app_instance.is_finished() and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)
            
            if not app_instance.is_finished():
                self.logger.warning(f"Timeout waiting for contract ID {contract_id} from IB Gateway")
                return None
            
            if not app_instance.contracts:
                self.logger.info(f"No contract found for ID {contract_id}")
                return None
            
            # Should only have one contract for ID lookup
            contract_data = app_instance.contracts[0]
            
            # Cache using dual storage pattern
            symbol = contract_data.get("symbol", "UNKNOWN")
            sec_type = contract_data.get("sec_type", "UNKNOWN")
            
            # 1. Create and cache symbol-based cache (for /lookup endpoints)
            cache_key_parts = [symbol, sec_type]
            symbol_cache_data = {
                "ticker": symbol,
                "timestamp": self._get_current_timestamp(),
                "security_types_searched": [sec_type],
                "total_contracts": 1,
                "contracts_by_type": {
                    sec_type: {
                        "count": 1,
                        "contracts": [contract_data]
                    }
                },
                "summary": {sec_type: 1},
                "cached": False,
                "source": "id_lookup"
            }
            
            # Cache symbol-based data
            symbol_cache_filename = None
            if self.cache.set(symbol_cache_data, *cache_key_parts):
                cache_key = "_".join(cache_key_parts)
                symbol_cache_filename = f"{self.cache.prefix}_{cache_key}.json" if self.cache.prefix else f"{cache_key}.json"
                self.logger.info(f"Cached contract {contract_id} ({symbol} {sec_type}) in symbol cache")
                
                # Update contract index
                try:
                    self.contract_index.add_contract(contract_data, cache_key)
                    self.logger.debug(f"Added contract {contract_id} to index from ID lookup")
                except Exception as e:
                    self.logger.warning(f"Failed to update contract index after ID lookup: {e}")
            
            # 2. Cache in contract ID-specific cache (for /contracts/{id} endpoints)
            if self.cache.set_contract(contract_id, contract_data, symbol_cache_filename):
                self.logger.info(f"Cached contract {contract_id} in ID-specific cache")
            else:
                self.logger.warning(f"Failed to cache contract {contract_id} in ID-specific cache")
            
            return contract_data
            
        except Exception as e:
            self.logger.error(f"Error looking up contract ID {contract_id} from IB Gateway: {e}")
            return None
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    async def _find_contract_by_id_fast(self, contract_id: int) -> Optional[Dict]:
        """
        Fast contract lookup using index
        
        Args:
            contract_id: IB contract ID to search for
            
        Returns:
            Contract data dictionary or None if not found
        """
        try:
            # Use the contract index for O(1) lookup
            cache_entry = self.contract_index.find_by_contract_id(contract_id)
            
            if cache_entry:
                # Check if entry is still valid (not expired)
                if not cache_entry.is_expired(ttl_hours=24):
                    return cache_entry.contract_data
                else:
                    # Remove expired entry
                    self.contract_index.remove_contract(contract_id)
                    self.logger.debug(f"Removed expired cache entry for contract {contract_id}")
            
            # If not in index, try to rebuild index from cache (maybe it was just added)
            if not hasattr(self, '_index_rebuilt_recently'):
                self.contract_index.rebuild_from_cache_manager(self.cache)
                self._index_rebuilt_recently = True
                
                # Try again after rebuild
                cache_entry = self.contract_index.find_by_contract_id(contract_id)
                if cache_entry and not cache_entry.is_expired(ttl_hours=24):
                    return cache_entry.contract_data
            
            return None
            
        except Exception as e:
            self.logger.error("Error in fast contract lookup for ID %d: %s", contract_id, e)
            # Fallback to slow search if fast lookup fails
            return self._find_contract_by_id_slow(contract_id)
    
    def _find_contract_by_id_slow(self, contract_id: int) -> Optional[Dict]:
        """
        Legacy slow contract search as fallback
        Only used when fast index lookup fails
        """
        try:
            # Search through memory cache
            for key, cached_data in self.cache._memory_cache.items():
                if isinstance(cached_data, dict):
                    contracts_by_type = cached_data.get("contracts_by_type", {})
                    for sec_type, type_data in contracts_by_type.items():
                        if isinstance(type_data, dict) and "contracts" in type_data:
                            contracts_list = type_data["contracts"]
                        else:
                            contracts_list = type_data if isinstance(type_data, list) else []
                        
                        for contract in contracts_list:
                            if isinstance(contract, dict) and contract.get("con_id") == contract_id:
                                # Add to index for future fast access
                                self.contract_index.add_contract(contract, key)
                                return contract
            
            # Search file cache with security checks
            from ib_util import ContractIndex
            import json
            index_helper = ContractIndex()
            cache_files = index_helper._get_safe_cache_files(self.cache.cache_dir, self.cache.prefix)
            
            for cache_file in cache_files:
                try:
                    with open(cache_file, 'r') as f:
                        cached_data = json.load(f)
                    
                    if isinstance(cached_data, dict):
                        contracts_by_type = cached_data.get("contracts_by_type", {})
                        for sec_type, type_data in contracts_by_type.items():
                            if isinstance(type_data, dict) and "contracts" in type_data:
                                contracts_list = type_data["contracts"]
                            else:
                                contracts_list = type_data if isinstance(type_data, list) else []
                            
                            for contract in contracts_list:
                                if isinstance(contract, dict) and contract.get("con_id") == contract_id:
                                    # Add to index for future fast access
                                    cache_key = cache_file.stem
                                    self.contract_index.add_contract(contract, cache_key, cache_file)
                                    return contract
                                    
                except (json.JSONDecodeError, IOError) as e:
                    self.logger.debug(f"Could not read cache file {cache_file}: {e}")
            
            return None
            
        except Exception as e:
            self.logger.error("Error in slow contract search for ID %d: %s", contract_id, e)
            return None


# Factory function for backwards compatibility
def create_app() -> ContractAPIServer:
    """Factory function to create the contract API server"""
    return ContractAPIServer()


# Global app instance for uvicorn
server_instance = create_app()
app = server_instance.app


def main():
    """Main function to run the server"""
    server_instance.run()


if __name__ == "__main__":
    main()