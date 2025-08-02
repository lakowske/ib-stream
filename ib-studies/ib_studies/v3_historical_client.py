"""Historical data client for IB-Stream v3 optimized storage format."""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional, Union
from urllib.parse import urljoin, urlencode

import httpx

from ib_studies.models import StreamConfig

logger = logging.getLogger(__name__)


class V3HistoricalClient:
    """Client for accessing v3 optimized historical data with time-range queries."""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        """Initialize v3 historical client."""
        self.config = config or StreamConfig()
        self.client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(timeout=60.0)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()
    
    async def get_buffer_info(self, contract_id: int, tick_types: List[str]) -> Dict:
        """Get v3 buffer information for a contract."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=60.0)
        
        try:
            url = urljoin(self.config.base_url, f"/v3/buffer/{contract_id}/info")
            params = {"tick_types": ",".join(tick_types)}
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error("Failed to get v3 buffer info: %s", e)
            raise
    
    async def query_historical_data(
        self,
        contract_id: int,
        tick_types: List[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        buffer_duration: str = "1h",
        limit: Optional[int] = None,
        format: str = "json",
        raw: bool = False
    ) -> Dict:
        """
        Query v3 historical data with time range.
        
        Args:
            contract_id: Contract ID to query
            tick_types: List of tick types (bid_ask, last, etc.)
            start_time: Start time for data range (UTC)
            end_time: End time for data range (UTC)
            buffer_duration: Duration string (e.g., "1h", "30m", "2h") if no start/end time
            limit: Maximum number of records to return
            format: Storage format ("json" or "protobuf")
            raw: Return raw v3 format (True) or expanded format (False)
            
        Returns:
            Dictionary containing historical data and metadata
        """
        if not self.client:
            self.client = httpx.AsyncClient(timeout=60.0)
        
        try:
            url = urljoin(self.config.base_url, f"/v3/buffer/{contract_id}/query")
            
            params = {
                "tick_types": ",".join(tick_types),
                "format": format,
                "buffer_duration": buffer_duration,
                "raw": str(raw).lower()
            }
            
            if start_time:
                params["start_time"] = start_time.isoformat()
            if end_time:
                params["end_time"] = end_time.isoformat()
            if limit:
                params["limit"] = str(limit)
            
            logger.info("Querying v3 historical data: %s?%s", url, urlencode(params))
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error("Failed to query v3 historical data: %s", e)
            raise
    
    async def stream_historical_data(
        self,
        contract_id: int,
        tick_types: List[str],
        callback: Callable[[str, Dict, str, str], None],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        buffer_duration: str = "1h",
        limit: Optional[int] = None,
        format: str = "json",
        raw: bool = False
    ) -> None:
        """
        Stream historical data through callback, similar to live streaming interface.
        
        This method queries historical data and then streams it through the callback
        to provide a consistent interface with live streaming clients.
        """
        try:
            # Query the historical data
            result = await self.query_historical_data(
                contract_id=contract_id,
                tick_types=tick_types,
                start_time=start_time,
                end_time=end_time,
                buffer_duration=buffer_duration,
                limit=limit,
                format=format,
                raw=raw
            )
            
            messages = result.get("messages", [])
            total_messages = len(messages)
            
            logger.info("Streaming %d historical messages for contract %d", 
                       total_messages, contract_id)
            
            # Stream each message through the callback
            for i, message in enumerate(messages):
                # Create a synthetic stream_id for compatibility
                stream_id = f"{contract_id}_historical_{i}"
                
                if raw:
                    # Raw v3 format - need to determine tick type and normalize
                    tick_type = message.get("tt", "unknown")
                    timestamp = self._microseconds_to_iso(message.get("ts"))
                    
                    # Convert v3 raw message to callback format
                    tick_data = self._v3_raw_to_tick_data(message)
                    
                else:
                    # Expanded format - extract fields
                    tick_type = message.get("tick_type", "unknown")
                    timestamp = message.get("ib_timestamp_iso", "")
                    
                    # Convert expanded message to callback format
                    tick_data = self._expanded_to_tick_data(message)
                
                # Normalize tick type to match v2 expectations
                normalized_tick_type = self._normalize_tick_type(tick_type)
                
                try:
                    await callback(normalized_tick_type, tick_data, stream_id, timestamp)
                except Exception as e:
                    logger.error("Error in historical data callback: %s", e)
                    
        except Exception as e:
            logger.error("Error streaming historical data: %s", e)
            raise
    
    def _microseconds_to_iso(self, microseconds: Optional[int]) -> str:
        """Convert microseconds timestamp to ISO format."""
        if not microseconds:
            return ""
        
        try:
            dt = datetime.fromtimestamp(microseconds / 1_000_000, tz=timezone.utc)
            return dt.isoformat()
        except (ValueError, OSError):
            return ""
    
    def _v3_raw_to_tick_data(self, v3_message: Dict) -> Dict:
        """Convert v3 raw message to tick data format expected by studies."""
        tick_data = {
            "contract_id": v3_message.get("cid"),
            "tick_type": v3_message.get("tt"),
            "ib_timestamp": v3_message.get("ts"),
            "system_timestamp": v3_message.get("st"),
            "request_id": v3_message.get("rid")
        }
        
        # Add optional fields based on tick type
        tick_type = v3_message.get("tt", "")
        
        if tick_type == "bid_ask":
            if "bp" in v3_message:
                tick_data["bid_price"] = v3_message["bp"]
            if "bs" in v3_message:
                tick_data["bid_size"] = v3_message["bs"]
            if "ap" in v3_message:
                tick_data["ask_price"] = v3_message["ap"]
            if "as" in v3_message:
                tick_data["ask_size"] = v3_message["as"]
        elif tick_type in ["last", "all_last"]:
            if "p" in v3_message:
                tick_data["price"] = v3_message["p"]
            if "s" in v3_message:
                tick_data["size"] = v3_message["s"]
        elif tick_type == "mid_point":
            if "mp" in v3_message:
                tick_data["mid_point"] = v3_message["mp"]
        
        return tick_data
    
    def _expanded_to_tick_data(self, expanded_message: Dict) -> Dict:
        """Convert expanded v3 message to tick data format expected by studies."""
        tick_data = {
            "contract_id": expanded_message.get("contract_id"),
            "tick_type": expanded_message.get("tick_type"),
            "ib_timestamp": expanded_message.get("ib_timestamp"),
            "system_timestamp": expanded_message.get("system_timestamp"),
            "request_id": expanded_message.get("request_id")
        }
        
        # Map expanded field names to expected names
        field_mapping = {
            "bid_price": "bid_price",
            "bid_size": "bid_size", 
            "ask_price": "ask_price",
            "ask_size": "ask_size",
            "price": "price",
            "size": "size",
            "mid_point": "mid_point"
        }
        
        for expanded_name, tick_name in field_mapping.items():
            if expanded_name in expanded_message:
                tick_data[tick_name] = expanded_message[expanded_name]
        
        return tick_data
    
    def _normalize_tick_type(self, tick_type: str) -> str:
        """Normalize v3 tick type to match v2 expectations."""
        tick_type_map = {
            "bid_ask": "BidAsk",
            "last": "Last",
            "all_last": "AllLast",
            "mid_point": "MidPoint"
        }
        
        return tick_type_map.get(tick_type, tick_type)
    
    async def get_storage_stats(self) -> Dict:
        """Get v3 storage statistics."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=60.0)
        
        try:
            url = urljoin(self.config.base_url, "/v3/storage/stats")
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error("Failed to get v3 storage stats: %s", e)
            raise
    
    async def list_storage_files(self, contract_id: int, format: str = "json", 
                                tick_type: Optional[str] = None) -> Dict:
        """List v3 storage files for a contract."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=60.0)
        
        try:
            url = urljoin(self.config.base_url, f"/v3/storage/files/{contract_id}")
            params = {"format": format}
            if tick_type:
                params["tick_type"] = tick_type
                
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error("Failed to list v3 storage files: %s", e)
            raise


class TimeRange:
    """Helper class for creating time ranges for historical queries."""
    
    @staticmethod
    def last_hour(end_time: Optional[datetime] = None) -> tuple[datetime, datetime]:
        """Get time range for the last hour."""
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        return start_time, end_time
    
    @staticmethod
    def last_day(end_time: Optional[datetime] = None) -> tuple[datetime, datetime]:
        """Get time range for the last day."""
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=1)
        return start_time, end_time
    
    @staticmethod
    def trading_session(date: datetime) -> tuple[datetime, datetime]:
        """Get time range for a trading session (9:30 AM - 4:00 PM ET)."""
        # Convert to ET timezone would require pytz, using UTC approximation
        # In production, this should handle timezone conversion properly
        session_start = date.replace(hour=14, minute=30, second=0, microsecond=0)  # 9:30 AM ET ≈ 2:30 PM UTC
        session_end = date.replace(hour=21, minute=0, second=0, microsecond=0)     # 4:00 PM ET ≈ 9:00 PM UTC
        return session_start, session_end
    
    @staticmethod
    def custom_range(start_time: datetime, end_time: datetime) -> tuple[datetime, datetime]:
        """Create a custom time range."""
        return start_time, end_time