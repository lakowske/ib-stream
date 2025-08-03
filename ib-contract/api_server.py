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
        self.cache = CacheManager(
            cache_dir="./.cache",
            cache_duration=timedelta(days=1),
            prefix="contracts",
            auto_cleanup=True
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
            "description": "Interactive Brokers TWS API contract lookup with file-based caching",
            "endpoints": {
                "/lookup/{ticker}": "Get all contracts for a ticker",
                "/lookup/{ticker}/{sec_type}": "Get contracts for a ticker and security type",
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
                "Connection pooling and retry logic"
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
        else:
            self.logger.warning("Failed to cache data for %s", "/".join(cache_key_parts))
        
        return data
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime
        return datetime.now().isoformat()


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