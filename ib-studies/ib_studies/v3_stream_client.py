"""V3 protocol-aware streaming client for IB-Stream."""

import asyncio
import json
import logging
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin, urlencode

import httpx

from ib_studies.models import StreamConfig
from ib_studies.v2_utils import normalize_tick_type

logger = logging.getLogger(__name__)


class V3StreamClient:
    """
    V3 protocol-aware streaming client.
    
    This client uses the v2 live streaming endpoints but provides v3 message format
    normalization and enhanced features like protocol selection and message conversion.
    """
    
    def __init__(self, config: Optional[StreamConfig] = None):
        """Initialize v3 stream client."""
        self.config = config or StreamConfig()
        self.client: Optional[httpx.AsyncClient] = None
        self.is_connected = False
        self.reconnect_attempts = 0
        self._stop_event = asyncio.Event()
        self._stream_url: Optional[str] = None
        self.protocol_version = "v3"  # Track protocol version
        
    async def connect(self, contract_id: int, tick_types: List[str], 
                     use_buffer: bool = False, buffer_duration: str = "1h") -> None:
        """
        Connect to stream endpoint with v3 protocol support.
        
        Args:
            contract_id: Contract ID to stream
            tick_types: List of tick types to stream  
            use_buffer: Whether to use buffer streaming (historical + live)
            buffer_duration: Buffer duration for historical data
        """
        if self.is_connected:
            logger.warning("Already connected to stream")
            return
        
        # Build URL based on buffer preference
        if use_buffer:
            # Use v2 buffer endpoint for historical + live streaming  
            url = urljoin(self.config.base_url, f"/v2/stream/{contract_id}/buffer")
            params = {
                "tick_types": ",".join([normalize_tick_type(t) for t in tick_types]),
                "buffer_duration": buffer_duration
            }
        elif len(tick_types) == 1:
            # Single stream endpoint
            tick_type = normalize_tick_type(tick_types[0])
            url = urljoin(self.config.base_url, f"/v2/stream/{contract_id}/live/{tick_type}")
            params = {}
        else:
            # Multi-stream endpoint
            url = urljoin(self.config.base_url, f"/v2/stream/{contract_id}/live")
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
        
        logger.info("Connecting to v3-aware stream: %s", self._stream_url)
        
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
        logger.info("Connected to v3-aware stream for contract %d", contract_id)
    
    async def stop(self) -> None:
        """Stop the stream client."""
        logger.info("Stopping v3 stream client")
        self._stop_event.set()
    
    async def consume(self, callback: Callable[[str, Dict, str, str], None]) -> None:
        """
        Consume v3 protocol events with callback.
        
        Args:
            callback: Function to call for each event (tick_type, data, stream_id, timestamp)
        """
        if not self.is_connected or not self.client:
            raise RuntimeError("Not connected to stream")
        
        while not self._stop_event.is_set():
            try:
                await self._consume_events(callback)
            except Exception as e:
                logger.error("V3 stream consumption error: %s", e, exc_info=True)
                
                if self.reconnect_attempts < self.config.max_reconnect_attempts:
                    await self._handle_reconnect()
                else:
                    logger.error("Max reconnection attempts reached")
                    break
    
    async def _consume_events(self, callback: Callable[[str, Dict, str, str], None]) -> None:
        """Internal method to consume SSE events with v3 processing."""
        if not self._stream_url:
            raise RuntimeError("Stream URL not set - call connect() first")
        
        logger.info("Starting v3-aware SSE stream consumption from: %s", self._stream_url)
        
        async with self.client.stream("GET", self._stream_url) as response:
            logger.info("Stream response status: %d, headers: %s", 
                       response.status_code, dict(response.headers))
            
            if response.status_code != 200:
                raise RuntimeError(f"Stream request failed with status {response.status_code}")
            
            # Check if this is a v3-enabled endpoint
            protocol_header = response.headers.get("X-Stream-Protocol", "v2")
            logger.info("Stream protocol detected: %s", protocol_header)
            
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
                    
                    # Process this data with v3 awareness
                    await self._process_v3_sse_data(data_line, callback)
                    
                elif line.startswith("event: "):
                    event_type = line[7:]  # Remove "event: " prefix
                    logger.debug("Event type: %s", event_type)
                elif line.startswith("id: "):
                    event_id = line[4:]  # Remove "id: " prefix
                    logger.debug("Event ID: %s", event_id)
                elif line == "":
                    logger.debug("Empty line - event boundary")
    
    async def _process_v3_sse_data(self, data: str, callback: Callable[[str, Dict, str, str], None]) -> None:
        """Process SSE data with v3 protocol awareness."""
        try:
            logger.debug("Processing v3-aware SSE data: %r", data)
            
            # Parse JSON data
            message = json.loads(data)
            logger.debug("Parsed message: %s", message)
            
            # Extract message fields
            message_type = message.get("type", "unknown")
            stream_id = message.get("stream_id", "")
            timestamp = message.get("timestamp", "")
            
            logger.debug("Message: type=%s, stream_id=%s, timestamp=%s", 
                        message_type, stream_id, timestamp)
            
            # Handle different message types
            if message_type == "tick":
                await self._handle_v3_tick_event(message, callback)
            elif message_type == "error":
                await self._handle_v3_error_event(message)
            elif message_type == "complete":
                await self._handle_v3_complete_event(message)
            elif message_type == "info":
                await self._handle_v3_info_event(message)
            else:
                logger.warning("Unknown message type: %s", message_type)
                        
        except json.JSONDecodeError as e:
            logger.error("Failed to parse SSE data as JSON: %s", e)
            logger.error("Raw data was: %r", data)
        except Exception as e:
            logger.error("Error processing v3 SSE data: %s", e, exc_info=True)
    
    async def _handle_v3_tick_event(self, message: Dict, callback: Callable[[str, Dict, str, str], None]) -> None:
        """Handle tick event with v3 protocol enhancements."""
        stream_id = message.get("stream_id", "")
        timestamp = message.get("timestamp", "")
        tick_data = message.get("data", {})
        
        # Detect if this is raw v3 format or v2 format
        if self._is_v3_raw_format(tick_data):
            # Convert v3 raw format to normalized format
            tick_type = tick_data.get("tt", "unknown")
            normalized_data = self._convert_v3_to_normalized(tick_data)
            logger.debug("Converted v3 raw format: %s -> %s", tick_data, normalized_data)
        else:
            # Standard v2 format processing
            tick_type = tick_data.get("tick_type", "unknown")
            normalized_data = tick_data
        
        # Normalize tick type to expected format
        mapped_type = self._normalize_tick_type_for_callback(tick_type)
        logger.debug("Processing v3 tick event: stream_id=%s, tick_type=%s -> %s", 
                    stream_id, tick_type, mapped_type)
        
        try:
            await callback(mapped_type, normalized_data, stream_id, timestamp)
            logger.debug("V3 callback executed successfully for tick type: %s", mapped_type)
        except Exception as e:
            logger.error("Error in v3 tick callback: %s", e, exc_info=True)
    
    def _is_v3_raw_format(self, tick_data: Dict) -> bool:
        """Detect if tick data is in v3 raw format (shortened field names)."""
        v3_fields = {"ts", "st", "cid", "tt", "rid", "bp", "bs", "ap", "as", "p", "s", "mp"}
        data_fields = set(tick_data.keys())
        
        # If we see v3-specific shortened fields, it's v3 format
        v3_field_count = len(v3_fields.intersection(data_fields))
        return v3_field_count > 0
    
    def _convert_v3_to_normalized(self, v3_data: Dict) -> Dict:
        """Convert v3 raw format to normalized format for studies."""
        normalized = {}
        
        # Map v3 shortened fields to full names
        field_mapping = {
            "ts": "ib_timestamp",
            "st": "system_timestamp", 
            "cid": "contract_id",
            "tt": "tick_type",
            "rid": "request_id",
            "bp": "bid_price",
            "bs": "bid_size",
            "ap": "ask_price", 
            "as": "ask_size",
            "p": "price",
            "s": "size",
            "mp": "mid_point"
        }
        
        for v3_field, full_field in field_mapping.items():
            if v3_field in v3_data:
                normalized[full_field] = v3_data[v3_field]
        
        # Copy any unmapped fields as-is
        for key, value in v3_data.items():
            if key not in field_mapping:
                normalized[key] = value
        
        return normalized
    
    def _normalize_tick_type_for_callback(self, tick_type: str) -> str:
        """Normalize tick type for callback compatibility."""
        tick_type_map = {
            "bid_ask": "BidAsk",
            "last": "Last", 
            "all_last": "AllLast",
            "mid_point": "MidPoint"
        }
        
        return tick_type_map.get(tick_type, tick_type)
    
    async def _handle_v3_error_event(self, message: Dict) -> None:
        """Handle error event with v3 protocol awareness."""
        stream_id = message.get("stream_id", "")
        error_data = message.get("data", {})
        error_code = error_data.get("code", "unknown")
        error_message = error_data.get("message", "Unknown error")
        recoverable = error_data.get("recoverable", False)
        
        logger.error("V3 Stream error (stream_id=%s): %s - %s (recoverable=%s)", 
                    stream_id, error_code, error_message, recoverable)
        
        # Handle v3-specific error types
        if error_code == "STREAM_TIMEOUT":
            logger.info("Received timeout error - stopping client")
            self._stop_event.set()
        elif error_code == "V3_STORAGE_ERROR":
            logger.warning("V3 storage error - may affect historical data access")
    
    async def _handle_v3_complete_event(self, message: Dict) -> None:
        """Handle complete event with v3 protocol awareness."""
        stream_id = message.get("stream_id", "")
        complete_data = message.get("data", {})
        reason = complete_data.get("reason", "unknown")
        total_ticks = complete_data.get("total_ticks", 0)
        duration = complete_data.get("duration_seconds", 0)
        
        # V3-specific completion metrics
        v3_metrics = complete_data.get("v3_metrics", {})
        if v3_metrics:
            storage_efficiency = v3_metrics.get("storage_efficiency_percent", 0)
            logger.info("V3 Stream completed (stream_id=%s): %s (ticks: %d, duration: %.2fs, storage efficiency: %.1f%%)", 
                       stream_id, reason, total_ticks, duration, storage_efficiency)
        else:
            logger.info("V3 Stream completed (stream_id=%s): %s (total ticks: %d, duration: %.2fs)", 
                       stream_id, reason, total_ticks, duration)
        
        if reason == "timeout":
            logger.info("Stream completed due to timeout - stopping client")
            self._stop_event.set()
    
    async def _handle_v3_info_event(self, message: Dict) -> None:
        """Handle info event with v3 protocol awareness."""
        stream_id = message.get("stream_id", "")
        info_data = message.get("data", {})
        status = info_data.get("status", "unknown")
        
        # Log v3-specific info
        v3_info = info_data.get("v3_info", {})
        if v3_info:
            protocol_version = v3_info.get("protocol_version", "unknown")
            storage_format = v3_info.get("storage_format", "unknown")
            logger.info("V3 Stream info (stream_id=%s): %s (protocol: %s, storage: %s)", 
                       stream_id, status, protocol_version, storage_format)
        else:
            logger.info("V3 Stream info (stream_id=%s): %s", stream_id, status)
    
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
    
    async def disconnect(self) -> None:
        """Clean disconnect."""
        logger.info("Disconnecting from v3 stream")
        
        # Signal stop
        self._stop_event.set()
        
        # Close HTTP client
        if self.client:
            await self.client.aclose()
            self.client = None
        
        self.is_connected = False
        self.reconnect_attempts = 0
        
        logger.info("Disconnected from v3 stream")
    
    async def check_health(self) -> Dict:
        """Check stream server health with v3 awareness."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=10.0)
        
        try:
            url = urljoin(self.config.base_url, "/health")
            response = await self.client.get(url)
            response.raise_for_status()
            
            health_data = response.json()
            
            # Check for v3 capabilities
            v3_url = urljoin(self.config.base_url, "/v3/info")
            try:
                v3_response = await self.client.get(v3_url)
                if v3_response.status_code == 200:
                    health_data["v3_capabilities"] = v3_response.json()
            except:
                health_data["v3_capabilities"] = {"available": False}
            
            return health_data
            
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return {"status": "unhealthy", "error": str(e)}
    
    async def get_stream_info(self) -> Dict:
        """Get stream server information with v3 details."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=10.0)
        
        try:
            # Get v2 info
            v2_url = urljoin(self.config.base_url, "/v2/info")
            v2_response = await self.client.get(v2_url)
            v2_response.raise_for_status()
            info = v2_response.json()
            
            # Get v3 info
            v3_url = urljoin(self.config.base_url, "/v3/info")
            try:
                v3_response = await self.client.get(v3_url)
                if v3_response.status_code == 200:
                    info["v3_info"] = v3_response.json()
                    info["protocol_support"] = ["v2", "v3"]
                else:
                    info["protocol_support"] = ["v2"]
            except:
                info["protocol_support"] = ["v2"]
            
            return info
            
        except Exception as e:
            logger.error("Stream info request failed: %s", e)
            return {"error": str(e)}
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()