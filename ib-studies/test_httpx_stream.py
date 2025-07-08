#!/usr/bin/env python3
"""Test httpx streaming directly."""

import asyncio
import json
import httpx


async def test_httpx_stream():
    """Test httpx streaming directly."""
    url = "http://localhost:8001/stream/711280073?tick_types=Last&limit=5"
    
    print(f"Connecting to: {url}")
    
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream("GET", url) as response:
                print(f"Response status: {response.status_code}")
                print(f"Response headers: {response.headers}")
                
                line_count = 0
                async for line in response.aiter_lines():
                    line_count += 1
                    print(f"Line {line_count}: {line}")
                    
                    if line_count >= 20:  # Limit output
                        break
                        
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_httpx_stream())