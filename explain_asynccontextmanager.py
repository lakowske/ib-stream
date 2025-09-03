#!/usr/bin/env python3
"""
Complete explanation of @asynccontextmanager
Shows how it works in general Python and specifically with FastAPI
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

# Configure logging to see the execution flow
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# PART 1: @asynccontextmanager is a GENERAL PYTHON feature
# =============================================================================

print("🔍 @asynccontextmanager Explanation")
print("=" * 60)

@asynccontextmanager
async def example_resource_manager() -> AsyncIterator[str]:
    """
    This is a general Python async context manager.
    It works with 'async with' statements.
    """
    # STARTUP CODE (before yield)
    logger.info("🚀 STARTUP: Acquiring resource...")
    resource = "My Important Resource"
    
    try:
        # The 'yield' is the key! This is where execution pauses
        # and the context manager "yields control" to the caller
        yield resource  # This value goes to 'async with ... as resource:'
        
    finally:
        # CLEANUP CODE (after yield, always runs)
        logger.info("🧹 CLEANUP: Releasing resource...")

async def demonstrate_basic_usage():
    """Show how @asynccontextmanager works in general Python"""
    print("\n📚 BASIC @asynccontextmanager Usage:")
    
    async with example_resource_manager() as resource:
        logger.info(f"💼 USING: {resource}")
        # Your main code runs here
        await asyncio.sleep(0.1)  # Simulate some work
        logger.info("✅ Work completed")
    
    logger.info("🏁 Context manager finished")

# =============================================================================
# PART 2: How FastAPI uses @asynccontextmanager for "lifespan"
# =============================================================================

@asynccontextmanager
async def app_lifespan_manager(app) -> AsyncIterator[None]:
    """
    This is how we use @asynccontextmanager with FastAPI.
    FastAPI calls this during app startup and shutdown.
    """
    # STARTUP CODE - runs when FastAPI app starts
    logger.info("🏗️  FastAPI STARTUP: Initialize database connections...")
    logger.info("🏗️  FastAPI STARTUP: Start background tasks...")
    logger.info("🏗️  FastAPI STARTUP: Load configuration...")
    
    # Simulate startup work
    await asyncio.sleep(0.1)
    
    try:
        # yield gives control back to FastAPI
        # FastAPI runs your app here (handles HTTP requests)
        yield  # Note: yield None for FastAPI lifespan
        
    finally:
        # SHUTDOWN CODE - runs when FastAPI app shuts down
        logger.info("🛑 FastAPI SHUTDOWN: Close database connections...")
        logger.info("🛑 FastAPI SHUTDOWN: Stop background tasks...")
        logger.info("🛑 FastAPI SHUTDOWN: Cleanup resources...")

def create_example_fastapi_app():
    """Show how FastAPI uses the lifespan context manager"""
    # This is pseudocode - showing the concept
    print("\n🚀 FastAPI Lifespan Usage:")
    print("from fastapi import FastAPI")
    print()
    print("app = FastAPI(lifespan=app_lifespan_manager)")
    print()
    print("# FastAPI automatically:")
    print("# 1. Calls lifespan manager STARTUP code when app starts")
    print("# 2. Runs your app (handles requests)")  
    print("# 3. Calls lifespan manager CLEANUP code when app shuts down")

# =============================================================================
# PART 3: Your IB Stream example
# =============================================================================

@asynccontextmanager
async def ib_stream_lifespan(app) -> AsyncIterator[None]:
    """
    This is from your actual IB Stream code.
    Shows real-world FastAPI + @asynccontextmanager usage.
    """
    # STARTUP - Initialize IB connections, storage, etc.
    logger.info("🔌 IB STARTUP: Create unified connection manager...")
    logger.info("🔌 IB STARTUP: Initialize storage system...")
    logger.info("🔌 IB STARTUP: Start background streaming...")
    
    # Simulate the startup process
    await asyncio.sleep(0.2)
    logger.info("✅ IB Stream ready to handle requests")
    
    try:
        # FastAPI handles HTTP requests here
        yield
        
    finally:
        # SHUTDOWN - Cleanup IB connections, stop streaming, etc.
        logger.info("🔌 IB SHUTDOWN: Stop background streaming...")
        logger.info("🔌 IB SHUTDOWN: Close IB connections...")
        logger.info("🔌 IB SHUTDOWN: Stop storage system...")

# =============================================================================
# PART 4: Key Concepts Explained
# =============================================================================

def explain_key_concepts():
    print("\n🎯 Key Concepts:")
    print("-" * 40)
    print("1. @asynccontextmanager is CORE PYTHON (contextlib module)")
    print("   - Works with any async context (not just FastAPI)")
    print("   - Provides setup/cleanup pattern")
    print()
    print("2. The 'yield' is the magic:")
    print("   - Code BEFORE yield = setup/startup")
    print("   - Code AFTER yield = cleanup/shutdown") 
    print("   - yield value = what 'async with' receives")
    print()
    print("3. FastAPI's lifespan parameter:")
    print("   - FastAPI calls your @asynccontextmanager automatically")
    print("   - Startup code runs when server starts")
    print("   - Shutdown code runs when server stops")
    print()
    print("4. Error handling:")
    print("   - try/finally ensures cleanup always runs")
    print("   - Even if exceptions occur during startup or main execution")

def compare_with_regular_context_manager():
    print("\n🔄 Comparison with Regular Context Manager:")
    print("-" * 50)
    print("SYNC version:")
    print("@contextmanager")
    print("def sync_manager():")
    print("    # setup")
    print("    yield resource")
    print("    # cleanup")
    print()
    print("ASYNC version:")
    print("@asynccontextmanager  # <-- async version")
    print("async def async_manager():  # <-- async function")
    print("    # setup (can use await)")
    print("    yield resource")
    print("    # cleanup (can use await)")

# =============================================================================
# MAIN DEMONSTRATION
# =============================================================================

async def main():
    """Run all demonstrations"""
    
    # Show basic usage
    await demonstrate_basic_usage()
    
    # Show FastAPI concept
    create_example_fastapi_app()
    
    # Show your IB Stream example
    print("\n📊 IB Stream Lifespan Simulation:")
    async with ib_stream_lifespan(None):
        logger.info("📈 IB Stream handling requests...")
        await asyncio.sleep(0.1)
        logger.info("📈 Processing market data...")
    
    # Explain concepts
    explain_key_concepts()
    compare_with_regular_context_manager()
    
    print("\n🎉 Summary:")
    print("✅ @asynccontextmanager = General Python async context manager")
    print("✅ FastAPI uses it for startup/shutdown lifecycle management")
    print("✅ Your IB Stream uses it to initialize/cleanup connections")
    print("✅ The 'yield' separates setup from cleanup code")

if __name__ == "__main__":
    asyncio.run(main())