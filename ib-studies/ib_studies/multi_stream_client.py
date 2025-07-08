"""Multi-stream SSE client for consuming multiple IB-Stream data types simultaneously."""

import asyncio
import json
import logging
from typing import Callable, Dict, List, Optional, Set
from urllib.parse import urljoin, urlencode

import httpx

from ib_studies.models import StreamConfig

logger = logging.getLogger(__name__)


class MultiStreamClient:
    """SSE client for consuming multiple IB-Stream data types simultaneously."""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        """Initialize multi-stream client."""
        self.config = config or StreamConfig()
        self.clients: Dict[str, httpx.AsyncClient] = {}
        self.active_streams: Set[str] = set()
        self.reconnect_attempts: Dict[str, int] = {}
        self._stop_event = asyncio.Event()
        self._stream_tasks: Dict[str, asyncio.Task] = {}
        
    async def connect_multiple(self, contract_id: int, tick_types: List[str], 
                              callback: Callable[[str, Dict], None]) -> None:
        """
        Connect to multiple stream endpoints simultaneously.
        
        Args:
            contract_id: Contract ID to stream
            tick_types: List of tick types (BidAsk, Last, AllLast, MidPoint)
            callback: Async function to call for each tick (tick_type, data)
        """
        if self.active_streams:
            logger.warning("Already connected to streams: %s", self.active_streams)
            await self.disconnect_all()
        
        logger.info("Connecting to %d streams for contract %d: %s", 
                   len(tick_types), contract_id, tick_types)
        
        # Create tasks for each stream
        for tick_type in tick_types:
            stream_key = f"{contract_id}_{tick_type}"
            
            # Create HTTP client for this stream
            self.clients[stream_key] = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=self.config.timeout,
                    write=10.0,
                    pool=10.0
                )
            )
            
            # Start stream consumption task
            self._stream_tasks[stream_key] = asyncio.create_task(
                self._consume_stream(contract_id, tick_type, callback, stream_key)
            )
            
            self.active_streams.add(stream_key)
            self.reconnect_attempts[stream_key] = 0
        
        logger.info("Started %d concurrent streams", len(self.active_streams))
    
    async def _consume_stream(self, contract_id: int, tick_type: str, 
                             callback: Callable[[str, Dict], None], stream_key: str) -> None:
        """Consume a single stream endpoint."""
        # Build stream URL using the clean API pattern
        url = urljoin(self.config.base_url, f"/stream/{contract_id}/{tick_type}")
        
        # Add query parameters
        params = {}
        if self.config.timeout:
            params["timeout"] = self.config.timeout
        
        if params:
            url = f"{url}?{urlencode(params)}"
        
        logger.info("Starting stream consumption: %s", url)
        
        while not self._stop_event.is_set() and stream_key in self.active_streams:
            try:
                await self._consume_stream_data(url, tick_type, callback, stream_key)
            except asyncio.CancelledError:
                logger.info("Stream %s cancelled", stream_key)
                break
            except Exception as e:
                if self._stop_event.is_set():
                    logger.info("Stream %s stopped during error handling", stream_key)
                    break
                    
                logger.error("Stream %s consumption error: %s", stream_key, e, exc_info=True)
                
                if self.reconnect_attempts[stream_key] < self.config.max_reconnect_attempts:
                    await self._handle_reconnect(stream_key)
                else:
                    logger.error("Max reconnection attempts reached for stream %s", stream_key)
                    break
    
    async def _consume_stream_data(self, url: str, tick_type: str, 
                                  callback: Callable[[str, Dict], None], stream_key: str) -> None:
        """Internal method to consume SSE events from a single stream."""
        client = self.clients[stream_key]
        
        async with client.stream("GET", url) as response:
            logger.info("Stream %s status: %d, headers: %s", 
                       stream_key, response.status_code, dict(response.headers))
            
            if response.status_code != 200:
                raise RuntimeError(f"Stream {stream_key} request failed with status {response.status_code}")
            
            line_count = 0
            
            async for line in response.aiter_lines():
                line_count += 1
                
                # Check for cancellation more frequently
                if self._stop_event.is_set():
                    logger.info("Stop event set, breaking from stream %s", stream_key)
                    break
                    
                # Only log first 10 lines and then every 100th line to reduce noise
                if line_count <= 10 or line_count % 100 == 0:
                    logger.debug("Stream %s line %d: %r", stream_key, line_count, line)
                
                # Process SSE format
                if line.startswith("data: "):
                    data_line = line[6:]  # Remove "data: " prefix
                    logger.debug("Stream %s processing data: %r", stream_key, data_line)
                    
                    # Process this data immediately - each line is a complete event
                    await self._process_sse_data(data_line, tick_type, callback, stream_key)
                    
                elif line.startswith("event: "):
                    # Event type line - can be stored if needed
                    event_type = line[7:]  # Remove "event: " prefix
                    logger.debug("Stream %s event type: %s", stream_key, event_type)
                elif line.startswith("id: "):
                    # Event ID - can be stored if needed
                    event_id = line[4:]  # Remove "id: " prefix
                    logger.debug("Stream %s event ID: %s", stream_key, event_id)
                elif line == "":
                    # Empty line signals end of event - but we already processed above
                    logger.debug("Stream %s empty line - event boundary", stream_key)
                # Ignore other SSE fields like "retry:"
    
    async def _process_sse_data(self, data: str, tick_type: str, 
                               callback: Callable[[str, Dict], None], stream_key: str) -> None:
        """Process a complete SSE data block."""
        try:
            logger.debug("Stream %s processing SSE data: %r", stream_key, data)
            
            # Parse JSON data
            parsed_data = json.loads(data)
            logger.debug("Stream %s parsed JSON: %s", stream_key, parsed_data)
            
            # Determine event type
            event_type = parsed_data.get("type", "message")
            logger.debug("Stream %s event type from data: %s", stream_key, event_type)
            
            # Handle different event types
            if event_type == "tick":
                await self._handle_tick_event(parsed_data, tick_type, callback, stream_key)
            elif event_type == "error":
                await self._handle_error_event(parsed_data, stream_key)
            elif event_type == "complete":
                await self._handle_complete_event(parsed_data, stream_key)
            elif event_type == "info":
                await self._handle_info_event(parsed_data, stream_key)
            else:
                # Check if this might be a complete/timeout event with wrong event type
                if "reason" in parsed_data and parsed_data.get("reason") in ["timeout", "limit_reached", "complete"]:
                    logger.debug("Stream %s treating unknown event as complete: %s", stream_key, parsed_data)
                    await self._handle_complete_event(parsed_data, stream_key)
                elif "error_code" in parsed_data or "error" in parsed_data:
                    logger.debug("Stream %s treating unknown event as error: %s", stream_key, parsed_data)
                    await self._handle_error_event(parsed_data, stream_key)
                else:
                    logger.debug("Stream %s unknown event type: %s, full data: %s", stream_key, event_type, parsed_data)
                    # Don't try to handle unknown events as ticks - this causes errors
                        
        except json.JSONDecodeError as e:
            logger.error("Stream %s failed to parse SSE data as JSON: %s", stream_key, e)
            logger.error("Stream %s raw data was: %r", stream_key, data)
        except Exception as e:
            logger.error("Stream %s error processing SSE data: %s", stream_key, e, exc_info=True)
    
    async def _handle_tick_event(self, data: Dict, tick_type: str, 
                                callback: Callable[[str, Dict], None], stream_key: str) -> None:
        """Handle tick event from a specific stream."""
        tick_data = data.get("data", {})
        actual_tick_type = tick_data.get("type", "unknown")
        
        logger.debug("Stream %s processing tick: tick_type=%s, actual=%s, data=%s", 
                    stream_key, tick_type, actual_tick_type, tick_data)
        
        # Map the server's tick types to our expected format
        tick_type_map = {
            "bid_ask": "BidAsk",
            "time_sales": "Last",  
            "all_last": "AllLast",
            "midpoint": "MidPoint"
        }
        
        # Use the requested tick_type as primary, with fallback to mapped type
        final_tick_type = tick_type
        if actual_tick_type in tick_type_map:
            final_tick_type = tick_type_map[actual_tick_type]
        
        logger.debug("Stream %s mapped tick type: %s -> %s", stream_key, actual_tick_type, final_tick_type)
        
        try:
            await callback(final_tick_type, tick_data)
            logger.debug("Stream %s callback executed successfully for tick type: %s", stream_key, final_tick_type)
        except Exception as e:
            logger.error("Stream %s error in tick callback: %s", stream_key, e, exc_info=True)
    
    async def _handle_error_event(self, data: Dict, stream_key: str) -> None:
        """Handle error event."""
        error_code = data.get("error_code", "unknown")
        message = data.get("message", "Unknown error")
        error_data = data.get("data", {})
        
        # Check if this is actually a timeout/complete event disguised as an error
        if error_code == "unknown" and not error_data and message == "Unknown error":
            logger.debug("Stream %s received likely timeout/complete event (ignoring)", stream_key)
            # Don't treat this as a real error - it's probably just the stream ending
            return
        
        # Only log real errors
        logger.error("Stream %s error: %s - %s", stream_key, error_code, message)
        if error_data:
            logger.error("Stream %s error details: %s", stream_key, error_data)
        logger.debug("Stream %s full error data: %s", stream_key, data)
    
    async def _handle_complete_event(self, data: Dict, stream_key: str) -> None:
        """Handle stream complete event."""
        reason = data.get("reason", "unknown")
        total_ticks = data.get("total_ticks", 0)
        logger.info("Stream %s completed: %s (total ticks: %d)", stream_key, reason, total_ticks)
        
        # For natural completion reasons, don't reconnect
        if reason in ["timeout", "limit_reached", "complete"]:
            logger.debug("Stream %s completed naturally, removing from active streams", stream_key)
            self.active_streams.discard(stream_key)
    
    async def _handle_info_event(self, data: Dict, stream_key: str) -> None:
        """Handle stream info event."""
        logger.debug("Stream %s info: %s", stream_key, data.get("info", {}))
    
    async def _handle_reconnect(self, stream_key: str) -> None:
        """Handle reconnection logic for a specific stream."""
        self.reconnect_attempts[stream_key] += 1
        delay = min(self.config.reconnect_delay * self.reconnect_attempts[stream_key], 60)
        
        logger.info("Reconnecting stream %s in %d seconds (attempt %d/%d)", 
                   stream_key, delay, self.reconnect_attempts[stream_key], 
                   self.config.max_reconnect_attempts)
        
        await asyncio.sleep(delay)
        
        # Close existing client
        if stream_key in self.clients:
            await self.clients[stream_key].aclose()
            
            # Create new client
            self.clients[stream_key] = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=self.config.timeout,
                    write=10.0,
                    pool=10.0
                )
            )
        
        # Note: The actual reconnection will be handled by the calling code
        # which will continue the while loop in _consume_stream
    
    async def wait_for_completion(self) -> None:
        """Wait for all stream tasks to complete or stop event."""
        if not self._stream_tasks:
            return
        
        stop_task = asyncio.create_task(self._stop_event.wait())
        
        # Wait for either all streams to complete or stop signal
        pending_tasks = list(self._stream_tasks.values()) + [stop_task]
        
        try:
            done, pending = await asyncio.wait(
                pending_tasks,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # If stop event was triggered, cancel all stream tasks immediately
            if stop_task in done:
                logger.info("Stop event triggered, cancelling all streams")
                for stream_key, task in self._stream_tasks.items():
                    if not task.done():
                        logger.debug("Cancelling stream %s", stream_key)
                        task.cancel()
            
            # Cancel remaining pending tasks
            for task in pending:
                if not task.done():
                    task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            logger.error("Error waiting for stream completion: %s", e, exc_info=True)
    
    async def stop(self) -> None:
        """Signal all streams to stop."""
        logger.info("Stopping all streams")
        self._stop_event.set()
    
    async def disconnect_all(self) -> None:
        """Clean disconnect from all streams."""
        logger.info("Disconnecting from all streams")
        
        # Signal stop
        self._stop_event.set()
        
        # Cancel all tasks
        for stream_key, task in self._stream_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Close HTTP clients
        for stream_key, client in self.clients.items():
            try:
                await client.aclose()
            except Exception as e:
                logger.warning("Error closing client for stream %s: %s", stream_key, e)
        
        # Clear state
        self.clients.clear()
        self.active_streams.clear()
        self._stream_tasks.clear()
        self.reconnect_attempts.clear()
        
        logger.info("Disconnected from all streams")
    
    async def check_health(self) -> Dict:
        """Check stream server health."""
        # Use a temporary client for health check
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                url = urljoin(self.config.base_url, "/health")
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error("Health check failed: %s", e)
                return {"status": "unhealthy", "error": str(e)}
    
    async def get_stream_info(self) -> Dict:
        """Get stream server information."""
        # Use a temporary client for info request
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                url = urljoin(self.config.base_url, "/stream/info")
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error("Stream info request failed: %s", e)
                return {"error": str(e)}
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.active_streams:
            asyncio.run(self.disconnect_all())
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect_all()