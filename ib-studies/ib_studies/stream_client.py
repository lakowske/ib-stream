"""SSE client for consuming IB-Stream v2 protocol data."""

import asyncio
import json
import logging
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin, urlencode

import httpx

from ib_studies.models import StreamConfig
from ib_studies.v2_utils import normalize_tick_type

logger = logging.getLogger(__name__)


class StreamClient:
    """SSE client for consuming IB-Stream v2 protocol data."""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        """Initialize stream client."""
        self.config = config or StreamConfig()
        self.client: Optional[httpx.AsyncClient] = None
        self.is_connected = False
        self.reconnect_attempts = 0
        self._stop_event = asyncio.Event()
        self._stream_url: Optional[str] = None
        
    async def connect(self, contract_id: int, tick_types: List[str]) -> None:
        """Connect to v2 stream endpoint."""
        if self.is_connected:
            logger.warning("Already connected to stream")
            return
        
        # Build v2 URL - single tick type or multi-stream
        if len(tick_types) == 1:
            # Single stream endpoint
            tick_type = normalize_tick_type(tick_types[0])
            url = urljoin(self.config.base_url, f"/v2/stream/{contract_id}/{tick_type}")
            params = {}
        else:
            # Multi-stream endpoint
            url = urljoin(self.config.base_url, f"/v2/stream/{contract_id}")
            params = {
                "tick_types": ",".join([normalize_tick_type(t) for t in tick_types])
            }
        
        # Add common parameters
        if self.config.timeout:
            params["timeout"] = self.config.timeout
        
        if params:
            self._stream_url = f"{url}?{urlencode(params)}"
        else:
            self._stream_url = url
        
        logger.info("Connecting to v2 stream: %s", self._stream_url)
        
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
    
    async def stop(self) -> None:
        """Stop the stream client."""
        logger.info("Stopping stream client")
        self._stop_event.set()
    
    async def consume(self, callback: Callable[[str, Dict, str, str], None]) -> None:
        """
        Consume v2 protocol events with callback.
        
        Args:
            callback: Function to call for each event (tick_type, data, stream_id, timestamp)
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
    
    async def _consume_events(self, callback: Callable[[str, Dict, str, str], None]) -> None:
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
    
    async def _process_sse_data(self, data: str, callback: Callable[[str, Dict, str, str], None]) -> None:
        """Process a complete v2 protocol SSE data block."""
        try:
            logger.debug("Processing v2 SSE data: %r", data)
            
            # Parse JSON data - v2 protocol uses full message structure
            message = json.loads(data)
            logger.debug("Parsed v2 message: %s", message)
            
            # Extract v2 protocol fields
            message_type = message.get("type", "unknown")
            stream_id = message.get("stream_id", "")
            timestamp = message.get("timestamp", "")
            
            logger.debug("v2 message: type=%s, stream_id=%s, timestamp=%s", 
                        message_type, stream_id, timestamp)
            
            # Handle different v2 message types
            if message_type == "tick":
                await self._handle_v2_tick_event(message, callback)
            elif message_type == "error":
                await self._handle_v2_error_event(message)
            elif message_type == "complete":
                await self._handle_v2_complete_event(message)
            elif message_type == "info":
                await self._handle_v2_info_event(message)
            else:
                logger.warning("Unknown v2 message type: %s", message_type)
                        
        except json.JSONDecodeError as e:
            logger.error("Failed to parse v2 SSE data as JSON: %s", e)
            logger.error("Raw data was: %r", data)
        except Exception as e:
            logger.error("Error processing v2 SSE data: %s", e, exc_info=True)
    
    async def _handle_v2_tick_event(self, message: Dict, callback: Callable[[str, Dict, str, str], None]) -> None:
        """Handle v2 protocol tick event."""
        stream_id = message.get("stream_id", "")
        timestamp = message.get("timestamp", "")
        tick_data = message.get("data", {})
        tick_type = tick_data.get("tick_type", "unknown")
        
        logger.debug("Processing v2 tick event: stream_id=%s, tick_type=%s", stream_id, tick_type)
        
        # Convert snake_case to expected format for backward compatibility
        tick_type_map = {
            "bid_ask": "BidAsk",
            "last": "Last",
            "all_last": "AllLast", 
            "mid_point": "MidPoint"
        }
        
        mapped_type = tick_type_map.get(tick_type, tick_type)
        logger.debug("Mapped v2 tick type: %s -> %s", tick_type, mapped_type)
        
        try:
            await callback(mapped_type, tick_data, stream_id, timestamp)
            logger.debug("v2 callback executed successfully for tick type: %s", mapped_type)
        except Exception as e:
            logger.error("Error in v2 tick callback: %s", e, exc_info=True)
    
    async def _handle_v2_error_event(self, message: Dict) -> None:
        """Handle v2 protocol error event."""
        stream_id = message.get("stream_id", "")
        error_data = message.get("data", {})
        error_code = error_data.get("code", "unknown")
        error_message = error_data.get("message", "Unknown error")
        recoverable = error_data.get("recoverable", False)
        
        logger.error("v2 Stream error (stream_id=%s): %s - %s (recoverable=%s)", 
                    stream_id, error_code, error_message, recoverable)
        
        # If this is a timeout error, stop the client instead of reconnecting
        if error_code == "STREAM_TIMEOUT":
            logger.info("Received timeout error - stopping client")
            self._stop_event.set()
    
    async def _handle_v2_complete_event(self, message: Dict) -> None:
        """Handle v2 protocol stream complete event."""
        stream_id = message.get("stream_id", "")
        complete_data = message.get("data", {})
        reason = complete_data.get("reason", "unknown")
        total_ticks = complete_data.get("total_ticks", 0)
        duration = complete_data.get("duration_seconds", 0)
        
        logger.info("v2 Stream completed (stream_id=%s): %s (total ticks: %d, duration: %.2fs)", 
                   stream_id, reason, total_ticks, duration)
        
        # If stream completed due to timeout, stop the client
        if reason == "timeout":
            logger.info("Stream completed due to timeout - stopping client")
            self._stop_event.set()
    
    async def _handle_v2_info_event(self, message: Dict) -> None:
        """Handle v2 protocol info event."""
        stream_id = message.get("stream_id", "")
        info_data = message.get("data", {})
        status = info_data.get("status", "unknown")
        
        logger.info("v2 Stream info (stream_id=%s): %s", stream_id, status)
    
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
        """Get v2 stream server information."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=10.0)
        
        try:
            url = urljoin(self.config.base_url, "/v2/info")
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("v2 Stream info request failed: %s", e)
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