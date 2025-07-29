#!/usr/bin/env python3
"""
FastAPI Server for Contract Lookup
Provides HTTP endpoints for contract lookup with file-based caching for performance.
"""

import asyncio
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from contract_lookup import ContractLookupApp

# Configure logging using ib-util standardized logging
from ib_util import configure_service_logging, log_environment_info

logger = configure_service_logging("ib-contract", verbose=True)

# Cache configuration
CACHE_DIR = Path("./.cache")
CACHE_DURATION = timedelta(days=1)  # Cache for 1 day

# Global cache for contract data
contract_cache: Dict[str, Dict[str, Any]] = {}

# Global TWS connection
tws_app: Optional[ContractLookupApp] = None
tws_lock = threading.Lock()


def get_cache_key(ticker: str, sec_type: Optional[str] = None) -> str:
    """Generate cache key for ticker and security type"""
    if sec_type:
        return f"{ticker.upper()}_{sec_type.upper()}"
    return f"{ticker.upper()}_ALL"


def get_cache_filename(ticker: str, sec_type: Optional[str] = None) -> str:
    """Generate cache filename for ticker and security type"""
    today = datetime.now().strftime("%Y%m%d")
    suffix = f"_{sec_type.upper()}" if sec_type else ""
    return f"{today}-{ticker.upper()}{suffix}.json"


def is_cache_valid(cache_filename: str) -> bool:
    """Check if cache file is still valid"""
    cache_path = CACHE_DIR / cache_filename
    if not cache_path.exists():
        return False

    file_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
    age = datetime.now() - file_time
    return age < CACHE_DURATION


def get_from_cache(ticker: str, sec_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get contract data from cache if valid"""
    cache_key = get_cache_key(ticker, sec_type)
    cache_filename = get_cache_filename(ticker, sec_type)

    # Check memory cache first
    if cache_key in contract_cache and is_cache_valid(cache_filename):
        logger.info("Memory cache hit for %s", cache_key)
        return contract_cache[cache_key]

    # Check file cache
    if is_cache_valid(cache_filename):
        cache_path = CACHE_DIR / cache_filename
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            contract_cache[cache_key] = data
            logger.info("File cache hit for %s", cache_key)
            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to load cache file %s: %s", cache_filename, e)
            # Remove corrupted cache file
            cache_path.unlink(missing_ok=True)

    # Remove expired memory cache entry
    if cache_key in contract_cache:
        del contract_cache[cache_key]
        logger.info("Cache expired for %s", cache_key)

    return None


def store_in_cache(ticker: str, sec_type: Optional[str], data: Dict[str, Any]) -> None:
    """Store contract data in both memory and file cache"""
    cache_key = get_cache_key(ticker, sec_type)
    cache_filename = get_cache_filename(ticker, sec_type)

    # Store in memory cache
    contract_cache[cache_key] = data

    # Store in file cache
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        cache_path = CACHE_DIR / cache_filename
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Cached data for %s to %s", cache_key, cache_filename)
    except OSError as e:
        logger.error("Failed to write cache file %s: %s", cache_filename, e)


def ensure_tws_connection() -> ContractLookupApp:
    """Ensure TWS connection is active"""
    global tws_app

    with tws_lock:
        if tws_app is None or not tws_app.is_connected():
            logger.info("Establishing TWS connection...")
            tws_app = ContractLookupApp()
            if not tws_app.connect_and_start():
                msg = (
                    "Unable to connect to TWS/Gateway. Please ensure it's running with API enabled."
                )
                raise HTTPException(status_code=503, detail=msg)
            logger.info("TWS connection established")

    return tws_app


async def lookup_contracts(ticker: str, sec_type: Optional[str] = None) -> Dict[str, Any]:
    """Lookup contracts using existing implementation"""
    # Check cache first
    cached_data = get_from_cache(ticker, sec_type)
    if cached_data:
        return cached_data

    cache_key = get_cache_key(ticker, sec_type)
    logger.info("Cache miss for %s, fetching from TWS...", cache_key)

    # Get TWS connection
    app_instance = ensure_tws_connection()

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
            status_code=408, detail=f"Timeout waiting for contract data for {ticker}"
        )

    # Prepare response data
    if not app_instance.contracts:
        data = {
            "ticker": ticker.upper(),
            "timestamp": datetime.now().isoformat(),
            "security_types_searched": app_instance.requested_types,
            "total_contracts": 0,
            "contracts_by_type": {},
            "summary": {},
        }
    else:
        data = app_instance._prepare_json_data()

    # Store in cache
    store_in_cache(ticker, sec_type, data)

    return data


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Lifespan event handler for startup/shutdown"""
    # Startup
    logger.info("Starting TWS Contract Lookup API...")
    
    # Log environment configuration using standardized logging
    log_environment_info(logger, "ib-contract")
    
    logger.info("Attempting to establish TWS connection...")
    try:
        ensure_tws_connection()
        logger.info("TWS connection established successfully")
    except Exception as e:
        logger.warning("Failed to establish initial TWS connection: %s", e)
        logger.info("Will attempt to connect on first request")

    yield

    # Shutdown
    logger.info("Shutting down TWS Contract Lookup API...")
    global tws_app
    if tws_app and tws_app.is_connected():
        tws_app.disconnect_and_stop()
        logger.info("TWS connection closed")


app = FastAPI(
    title="TWS Contract Lookup API",
    description="Interactive Brokers TWS API contract lookup with file-based caching",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "TWS Contract Lookup API",
        "version": "1.0.0",
        "endpoints": {
            "/lookup/{ticker}": "Get all contracts for a ticker",
            "/lookup/{ticker}/{sec_type}": "Get contracts for a ticker and security type",
            "/health": "Health check",
            "/cache/status": "Cache status",
            "/cache/clear": "Clear cache",
        },
        "security_types": ["STK", "FUT", "OPT", "CASH", "IND", "CFD", "BOND", "FUND", "CMDTY"],
        "cache_duration_days": CACHE_DURATION.days,
    }


@app.get("/health")
async def health_check():
    """Health check endpoint using ib-util standardized formatting"""
    from ib_util import create_health_check_response
    
    try:
        tws_connected = tws_app is not None and tws_app.is_connected()
        return create_health_check_response(
            service_name="ib-contract",
            status="healthy",
            details={
                "tws_connected": tws_connected,
                "cache_entries": len(contract_cache),
            }
        )
    except Exception as e:
        logger.error("Health check failed: %s", e)
        response = create_health_check_response(
            service_name="ib-contract",
            status="unhealthy",
            details={"error": str(e)}
        )
        return JSONResponse(status_code=503, content=response)


@app.get("/cache/status")
async def cache_status():
    """Get cache status using ib-util standardized formatting"""
    from ib_util import format_cache_status_response
    
    cache_info = {}
    file_cache_info = {}

    # Memory cache info
    for key, data in contract_cache.items():
        cache_info[key] = {
            "in_memory": True,
            "contracts_count": len(data.get("contracts_by_type", {})),
        }

    # File cache info
    if CACHE_DIR.exists():
        for cache_file in CACHE_DIR.glob("*.json"):
            file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
            age = datetime.now() - file_time
            file_cache_info[cache_file.name] = {
                "cached_at": file_time.isoformat(),
                "age_seconds": int(age.total_seconds()),
                "valid": age < CACHE_DURATION,
                "file_size": cache_file.stat().st_size,
            }

    return format_cache_status_response(
        memory_cache=cache_info,
        file_cache=file_cache_info,
        cache_duration_days=CACHE_DURATION.days,
        cache_directory=str(CACHE_DIR)
    )


@app.delete("/cache/clear")
async def clear_cache():
    """Clear all cache entries"""
    memory_count = len(contract_cache)
    file_count = 0

    # Clear memory cache
    contract_cache.clear()

    # Clear file cache
    if CACHE_DIR.exists():
        for cache_file in CACHE_DIR.glob("*.json"):
            cache_file.unlink(missing_ok=True)
            file_count += 1

    logger.info(
        "Cleared %d memory cache entries and %d file cache entries", memory_count, file_count
    )

    return {
        "message": f"Cleared {memory_count} memory cache entries and {file_count} file cache entries",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/lookup/{ticker}")
async def lookup_ticker(ticker: str):
    """Lookup all contracts for a ticker"""
    try:
        logger.info("Looking up all contracts for ticker: %s", ticker)
        data = await lookup_contracts(ticker)
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error looking up ticker %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") from e


@app.get("/lookup/{ticker}/{sec_type}")
async def lookup_ticker_with_type(ticker: str, sec_type: str):
    """Lookup contracts for a ticker with specific security type"""
    # Validate security type
    valid_types = ["STK", "FUT", "OPT", "CASH", "IND", "CFD", "BOND", "FUND", "CMDTY"]
    sec_type_upper = sec_type.upper()

    if sec_type_upper not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid security type: {sec_type}. Valid types: {', '.join(valid_types)}",
        )

    try:
        logger.info("Looking up %s contracts for ticker: %s", sec_type_upper, ticker)
        data = await lookup_contracts(ticker, sec_type_upper)
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error looking up ticker %s with type %s: %s", ticker, sec_type, e)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") from e


def main():
    """Main function to run the server"""
    import os
    port = int(os.environ.get("IB_CONTRACTS_PORT", 8000))
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, log_level="info", reload=True)


if __name__ == "__main__":
    main()
