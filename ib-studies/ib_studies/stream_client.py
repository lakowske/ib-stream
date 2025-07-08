"""SSE client for consuming IB-Stream data."""

import asyncio
import json
import logging
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin, urlencode

import httpx

from ib_studies.models import StreamConfig

logger = logging.getLogger(__name__)


class StreamClient:
    """SSE client for consuming IB-Stream data."""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        """Initialize stream client."""
        self.config = config or StreamConfig()
        self.client: Optional[httpx.AsyncClient] = None
        self.is_connected = False
        self.reconnect_attempts = 0
        self._stop_event = asyncio.Event()
        self._stream_url: Optional[str] = None
        
    async def connect(self, contract_id: int, tick_types: List[str]) -> None:
        """Connect to stream endpoint."""
        if self.is_connected:
            logger.warning("Already connected to stream")
            return
        
        # Build URL with query parameters
        params = {
            "tick_types": ",".join(tick_types),
            "timeout": self.config.timeout
        }
        
        url = urljoin(self.config.base_url, f"/stream/{contract_id}")
        self._stream_url = f"{url}?{urlencode(params)}"
        
        logger.info("Connecting to stream: %s", self._stream_url)
        
        # Create HTTP client
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=self.config.timeout,
                write=10.0,
                pool=10.0
            )
        )
        
        self.is_connected = True
        self.reconnect_attempts = 0
        logger.info("Connected to stream for contract %d", contract_id)
    
    async def consume(self, callback: Callable[[str, Dict], None]) -> None:
        """
        Consume events with callback.
        
        Args:
            callback: Function to call for each event (tick_type, data)
        """
        if not self.is_connected or not self.client:
            raise RuntimeError("Not connected to stream")
        
        while not self._stop_event.is_set():
            try:
                await self._consume_events(callback)
            except Exception as e:
                logger.error("Stream consumption error: %s", e, exc_info=True)
                
                if self.reconnect_attempts < self.config.max_reconnect_attempts:
                    await self._handle_reconnect()
                else:
                    logger.error("Max reconnection attempts reached")
                    break
    
    async def _consume_events(self, callback: Callable[[str, Dict], None]) -> None:
        """Internal method to consume SSE events."""
        if not self._stream_url:
            raise RuntimeError("Stream URL not set - call connect() first")
        
        logger.info("Starting SSE stream consumption from: %s", self._stream_url)
        
        async with self.client.stream("GET", self._stream_url) as response:
            logger.info("Stream response status: %d, headers: %s", response.status_code, dict(response.headers))
            
            if response.status_code != 200:
                raise RuntimeError(f"Stream request failed with status {response.status_code}")
            
            line_count = 0
            
            async for line in response.aiter_lines():
                line_count += 1
                logger.debug("Raw line %d: %r", line_count, line)
                
                if self._stop_event.is_set():
                    logger.debug("Stop event set, breaking from stream consumption")
                    break
                
                # Process SSE format
                if line.startswith("data: "):
                    data_line = line[6:]  # Remove "data: " prefix
                    logger.debug("Processing data line: %r", data_line)
                    
                    # Process this data immediately - each line is a complete event
                    await self._process_sse_data(data_line, callback)
                    
                elif line.startswith("event: "):
                    # Event type line - can be stored if needed
                    event_type = line[7:]  # Remove "event: " prefix
                    logger.debug("Event type: %s", event_type)
                elif line.startswith("id: "):
                    # Event ID - can be stored if needed
                    event_id = line[4:]  # Remove "id: " prefix
                    logger.debug("Event ID: %s", event_id)
                elif line == "":
                    # Empty line signals end of event - but we already processed above
                    logger.debug("Empty line - event boundary")
                # Ignore other SSE fields like "retry:"
    
    async def _process_sse_data(self, data: str, callback: Callable[[str, Dict], None]) -> None:
        """Process a complete SSE data block."""
        try:
            logger.debug("Processing SSE data: %r", data)
            
            # Parse JSON data
            parsed_data = json.loads(data)
            logger.debug("Parsed JSON data: %s", parsed_data)
            
            # Determine event type
            event_type = parsed_data.get("type", "message")
            logger.debug("Event type from data: %s", event_type)
            
            # Handle different event types
            if event_type == "tick":
                await self._handle_tick_event(parsed_data, callback)
            elif event_type == "error":
                await self._handle_error_event(parsed_data)
            elif event_type == "complete":
                await self._handle_complete_event(parsed_data)
            elif event_type == "heartbeat":
                await self._handle_heartbeat_event(parsed_data)
            else:
                logger.debug("Unknown event type: %s", event_type)
                # Try to handle as tick data anyway
                await self._handle_tick_event(parsed_data, callback)
                        
        except json.JSONDecodeError as e:
            logger.error("Failed to parse SSE data as JSON: %s", e)
            logger.error("Raw data was: %r", data)
        except Exception as e:
            logger.error("Error processing SSE data: %s", e, exc_info=True)
    
    async def _handle_tick_event(self, data: Dict, callback: Callable[[str, Dict], None]) -> None:
        """Handle tick event."""
        tick_data = data.get("data", {})
        tick_type = tick_data.get("type", "unknown")
        
        logger.debug("Processing tick event: tick_type=%s, tick_data=%s", tick_type, tick_data)
        
        # Map tick types to expected format
        tick_type_map = {
            "bid_ask": "BidAsk",
            "time_sales": "Last",  # This is the actual type from ib-stream
            "all_last": "AllLast",
            "midpoint": "MidPoint"
        }
        
        mapped_type = tick_type_map.get(tick_type, tick_type)
        logger.debug("Mapped tick type: %s -> %s", tick_type, mapped_type)
        
        try:
            await callback(mapped_type, tick_data)
            logger.debug("Callback executed successfully for tick type: %s", mapped_type)
        except Exception as e:
            logger.error("Error in tick callback: %s", e, exc_info=True)
    
    async def _handle_error_event(self, data: Dict) -> None:
        """Handle error event."""
        error_code = data.get("error_code", "unknown")
        message = data.get("message", "Unknown error")
        logger.error("Stream error: %s - %s", error_code, message)
    
    async def _handle_complete_event(self, data: Dict) -> None:
        """Handle stream complete event."""
        reason = data.get("reason", "unknown")
        total_ticks = data.get("total_ticks", 0)
        logger.info("Stream completed: %s (total ticks: %d)", reason, total_ticks)
    
    async def _handle_heartbeat_event(self, data: Dict) -> None:
        """Handle heartbeat event."""
        logger.debug("Heartbeat received")
    
    async def _handle_reconnect(self) -> None:
        """Handle reconnection logic."""
        self.reconnect_attempts += 1
        delay = min(self.config.reconnect_delay * self.reconnect_attempts, 60)
        
        logger.info("Reconnecting in %d seconds (attempt %d/%d)", 
                   delay, self.reconnect_attempts, self.config.max_reconnect_attempts)
        
        await asyncio.sleep(delay)
        
        # Close existing client
        if self.client:
            await self.client.aclose()
        
        # Reset connection state
        self.is_connected = False
        
        # Note: The actual reconnection will be handled by the calling code
        # which should call connect() again
    
    async def disconnect(self) -> None:
        """Clean disconnect."""
        logger.info("Disconnecting from stream")
        
        # Signal stop
        self._stop_event.set()
        
        # Close HTTP client
        if self.client:
            await self.client.aclose()
            self.client = None
        
        self.is_connected = False
        self.reconnect_attempts = 0
        
        logger.info("Disconnected from stream")
    
    async def check_health(self) -> Dict:
        """Check stream server health."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=10.0)
        
        try:
            url = urljoin(self.config.base_url, "/health")
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return {"status": "unhealthy", "error": str(e)}
    
    async def get_stream_info(self) -> Dict:
        """Get stream server information."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=10.0)
        
        try:
            url = urljoin(self.config.base_url, "/stream/info")
            response = await self.client.get(url)
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
        if self.is_connected:
            asyncio.run(self.disconnect())
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()