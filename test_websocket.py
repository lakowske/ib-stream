#!/usr/bin/env python3
"""
Test script for WebSocket implementation in IB-Stream.
"""

import asyncio
import json
import logging
import sys
from typing import Dict, Any

import websockets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_websocket_connection():
    """Test basic WebSocket connection and subscription."""
    uri = "ws://localhost:8001/ws/stream/711280073/multi"
    
    try:
        logger.info("Connecting to WebSocket: %s", uri)
        
        async with websockets.connect(uri) as websocket:
            logger.info("WebSocket connected successfully")
            
            # Wait for connected message
            message = await websocket.recv()
            data = json.loads(message)
            logger.info("Received connected message: %s", data)
            
            # Send multi-subscribe message
            subscribe_msg = {
                "type": "multi_subscribe",
                "id": "test-001",
                "data": {
                    "contract_id": 711280073,
                    "tick_types": ["BidAsk", "Last"],
                    "params": {
                        "timeout": 10
                    }
                }
            }
            
            logger.info("Sending subscription: %s", subscribe_msg)
            await websocket.send(json.dumps(subscribe_msg))
            
            # Listen for messages
            tick_count = 0
            max_ticks = 5
            
            while tick_count < max_ticks:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                    data = json.loads(message)
                    
                    message_type = data.get("type")
                    logger.info("Received message type: %s", message_type)
                    
                    if message_type == "multi_subscribed":
                        logger.info("Multi-subscription confirmed: %s", data["data"])
                    elif message_type == "tick":
                        tick_count += 1
                        tick_data = data.get("data", {})
                        logger.info("Tick %d: %s - %s", tick_count, 
                                  tick_data.get("tick_type", "unknown"),
                                  tick_data.get("time", "no-time"))
                    elif message_type == "error":
                        logger.error("Error message: %s", data.get("error", {}))
                    elif message_type == "complete":
                        logger.info("Stream completed: %s", data)
                        break
                    
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for message")
                    break
                except Exception as e:
                    logger.error("Error receiving message: %s", e)
                    break
            
            logger.info("Test completed. Received %d ticks.", tick_count)
            
    except Exception as e:
        logger.error("WebSocket test failed: %s", e)
        return False
    
    return True


async def test_single_stream():
    """Test single stream WebSocket endpoint."""
    uri = "ws://localhost:8001/ws/stream/711280073/BidAsk"
    
    try:
        logger.info("Testing single stream: %s", uri)
        
        async with websockets.connect(uri) as websocket:
            # Wait for connected message
            message = await websocket.recv()
            data = json.loads(message)
            logger.info("Connected: %s", data.get("type"))
            
            # Send subscribe message
            subscribe_msg = {
                "type": "subscribe",
                "id": "single-001",
                "data": {
                    "contract_id": 711280073,
                    "tick_type": "BidAsk",
                    "params": {
                        "limit": 3
                    }
                }
            }
            
            await websocket.send(json.dumps(subscribe_msg))
            
            # Listen for a few messages
            for _ in range(5):
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    data = json.loads(message)
                    logger.info("Single stream message: %s", data.get("type"))
                    
                    if data.get("type") == "complete":
                        logger.info("Single stream completed")
                        break
                        
                except asyncio.TimeoutError:
                    logger.warning("Single stream timeout")
                    break
                    
        return True
        
    except Exception as e:
        logger.error("Single stream test failed: %s", e)
        return False


async def test_control_endpoint():
    """Test WebSocket control endpoint."""
    uri = "ws://localhost:8001/ws/control"
    
    try:
        logger.info("Testing control endpoint: %s", uri)
        
        async with websockets.connect(uri) as websocket:
            # Should receive initial status
            message = await websocket.recv()
            data = json.loads(message)
            logger.info("Control status: %s connections", 
                       data.get("data", {}).get("total_connections", 0))
            
            # Send get_stats request
            stats_msg = {
                "type": "get_stats"
            }
            
            await websocket.send(json.dumps(stats_msg))
            
            # Receive stats response
            message = await websocket.recv()
            data = json.loads(message)
            logger.info("Stats response: %s", data.get("type"))
            
        return True
        
    except Exception as e:
        logger.error("Control endpoint test failed: %s", e)
        return False


async def main():
    """Run all WebSocket tests."""
    logger.info("Starting WebSocket tests...")
    
    tests = [
        ("Control Endpoint", test_control_endpoint),
        ("Single Stream", test_single_stream),
        ("Multi Stream", test_websocket_connection),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info("\n" + "="*50)
        logger.info("Running test: %s", test_name)
        logger.info("="*50)
        
        try:
            result = await test_func()
            results[test_name] = result
            logger.info("Test %s: %s", test_name, "PASSED" if result else "FAILED")
        except Exception as e:
            logger.error("Test %s failed with exception: %s", test_name, e)
            results[test_name] = False
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("TEST SUMMARY")
    logger.info("="*50)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info("%s: %s", test_name, status)
    
    passed = sum(results.values())
    total = len(results)
    logger.info("\nOverall: %d/%d tests passed", passed, total)
    
    return passed == total


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error("Test runner failed: %s", e)
        sys.exit(1)