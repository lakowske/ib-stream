#!/usr/bin/env python3
"""Simple test to verify SSE event reception."""

import asyncio
import json
import httpx
from httpx_sse import aconnect_sse


async def test_sse():
    """Test SSE connection directly."""
    url = "http://localhost:8001/stream/711280073?tick_types=Last&limit=5"
    
    print(f"Connecting to: {url}")
    
    async with httpx.AsyncClient() as client:
        try:
            async with aconnect_sse(client, "GET", url) as event_source:
                print("Connected to SSE stream")
                
                event_count = 0
                async for sse_event in event_source.aiter_sse():
                    event_count += 1
                    event_type = sse_event.event or "message"
                    
                    try:
                        data = json.loads(sse_event.data) if sse_event.data else {}
                        print(f"Event {event_count}: type={event_type}")
                        print(f"  Data: {data}")
                        
                        if event_count >= 10:  # Limit output
                            break
                            
                    except json.JSONDecodeError as e:
                        print(f"JSON error: {e}")
                        print(f"Raw data: {sse_event.data}")
                        
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_sse())