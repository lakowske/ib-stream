"""Tests for V3 protocol clients."""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from ib_studies.models import StreamConfig
from ib_studies.v3_stream_client import V3StreamClient
from ib_studies.v3_historical_client import V3HistoricalClient, TimeRange


class TestV3StreamClient:
    """Test V3StreamClient functionality."""
    
    @pytest.fixture
    def stream_config(self):
        """Create test stream config."""
        return StreamConfig(base_url="http://localhost:8001")
    
    @pytest.fixture
    def v3_client(self, stream_config):
        """Create V3StreamClient instance."""
        return V3StreamClient(stream_config)
    
    def test_init(self, v3_client):
        """Test V3StreamClient initialization."""
        assert v3_client.protocol_version == "v3"
        assert not v3_client.is_connected
        assert v3_client.reconnect_attempts == 0
    
    @pytest.mark.asyncio
    async def test_connect_single_tick_type(self, v3_client):
        """Test connecting with single tick type."""
        with patch.object(v3_client, 'client') as mock_client:
            mock_client = AsyncMock()
            v3_client.client = mock_client
            
            await v3_client.connect(12345, ["BidAsk"])
            
            assert v3_client.is_connected
            assert "/v2/stream/12345/live/bid_ask" in v3_client._stream_url
    
    @pytest.mark.asyncio
    async def test_connect_multiple_tick_types(self, v3_client):
        """Test connecting with multiple tick types."""
        with patch.object(v3_client, 'client') as mock_client:
            mock_client = AsyncMock()
            v3_client.client = mock_client
            
            await v3_client.connect(12345, ["BidAsk", "Last"])
            
            assert v3_client.is_connected
            assert "/v2/stream/12345/live" in v3_client._stream_url
            assert "tick_types=bid_ask%2Clast" in v3_client._stream_url
    
    @pytest.mark.asyncio
    async def test_connect_with_buffer(self, v3_client):
        """Test connecting with buffer support."""
        with patch.object(v3_client, 'client') as mock_client:
            mock_client = AsyncMock()
            v3_client.client = mock_client
            
            await v3_client.connect(12345, ["BidAsk"], use_buffer=True, buffer_duration="2h")
            
            assert v3_client.is_connected
            assert "/v2/stream/12345/buffer" in v3_client._stream_url
            assert "buffer_duration=2h" in v3_client._stream_url
    
    def test_is_v3_raw_format(self, v3_client):
        """Test detection of v3 raw format."""
        v3_data = {"ts": 1234567890, "cid": 12345, "tt": "bid_ask", "bp": 100.5}
        v2_data = {"timestamp": "2025-01-01T00:00:00Z", "contract_id": 12345, "tick_type": "BidAsk"}
        
        assert v3_client._is_v3_raw_format(v3_data) is True
        assert v3_client._is_v3_raw_format(v2_data) is False
    
    def test_convert_v3_to_normalized(self, v3_client):
        """Test conversion of v3 raw format to normalized format."""
        v3_data = {
            "ts": 1234567890,
            "st": 1234567891,
            "cid": 12345,
            "tt": "bid_ask",
            "rid": 123,
            "bp": 100.5,
            "bs": 10,
            "ap": 100.6,
            "as": 5
        }
        
        normalized = v3_client._convert_v3_to_normalized(v3_data)
        
        assert normalized["ib_timestamp"] == 1234567890
        assert normalized["system_timestamp"] == 1234567891
        assert normalized["contract_id"] == 12345
        assert normalized["tick_type"] == "bid_ask"
        assert normalized["request_id"] == 123
        assert normalized["bid_price"] == 100.5
        assert normalized["bid_size"] == 10
        assert normalized["ask_price"] == 100.6
        assert normalized["ask_size"] == 5
    
    def test_normalize_tick_type_for_callback(self, v3_client):
        """Test tick type normalization for callback."""
        assert v3_client._normalize_tick_type_for_callback("bid_ask") == "BidAsk"
        assert v3_client._normalize_tick_type_for_callback("last") == "Last"
        assert v3_client._normalize_tick_type_for_callback("all_last") == "AllLast"
        assert v3_client._normalize_tick_type_for_callback("mid_point") == "MidPoint"
        assert v3_client._normalize_tick_type_for_callback("unknown") == "unknown"


class TestV3HistoricalClient:
    """Test V3HistoricalClient functionality."""
    
    @pytest.fixture
    def stream_config(self):
        """Create test stream config."""
        return StreamConfig(base_url="http://localhost:8001")
    
    @pytest.fixture
    def v3_historical_client(self, stream_config):
        """Create V3HistoricalClient instance."""
        return V3HistoricalClient(stream_config)
    
    def test_init(self, v3_historical_client):
        """Test V3HistoricalClient initialization."""
        assert v3_historical_client.config.base_url == "http://localhost:8001"
        assert v3_historical_client.client is None
    
    @pytest.mark.asyncio
    async def test_context_manager(self, v3_historical_client):
        """Test async context manager."""
        async with v3_historical_client as client:
            assert client.client is not None
        # Client should be closed after exiting context manager
    
    def test_microseconds_to_iso(self, v3_historical_client):
        """Test timestamp conversion."""
        # Test valid timestamp
        microseconds = 1640995200000000  # 2022-01-01T00:00:00Z
        iso_time = v3_historical_client._microseconds_to_iso(microseconds)
        assert iso_time.startswith("2022-01-01T00:00:00")
        
        # Test None
        assert v3_historical_client._microseconds_to_iso(None) == ""
        
        # Test invalid timestamp
        assert v3_historical_client._microseconds_to_iso(0) == "1970-01-01T00:00:00+00:00"
    
    def test_v3_raw_to_tick_data_bid_ask(self, v3_historical_client):
        """Test conversion of v3 raw to tick data for bid_ask."""
        v3_message = {
            "ts": 1640995200000000,
            "st": 1640995201000000,
            "cid": 12345,
            "tt": "bid_ask",
            "rid": 123,
            "bp": 100.5,
            "bs": 10,
            "ap": 100.6,
            "as": 5
        }
        
        tick_data = v3_historical_client._v3_raw_to_tick_data(v3_message)
        
        assert tick_data["contract_id"] == 12345
        assert tick_data["tick_type"] == "bid_ask"
        assert tick_data["ib_timestamp"] == 1640995200000000
        assert tick_data["system_timestamp"] == 1640995201000000
        assert tick_data["request_id"] == 123
        assert tick_data["bid_price"] == 100.5
        assert tick_data["bid_size"] == 10
        assert tick_data["ask_price"] == 100.6
        assert tick_data["ask_size"] == 5
    
    def test_v3_raw_to_tick_data_last(self, v3_historical_client):
        """Test conversion of v3 raw to tick data for last."""
        v3_message = {
            "ts": 1640995200000000,
            "st": 1640995201000000,
            "cid": 12345,
            "tt": "last",
            "rid": 123,
            "p": 100.55,
            "s": 100
        }
        
        tick_data = v3_historical_client._v3_raw_to_tick_data(v3_message)
        
        assert tick_data["contract_id"] == 12345
        assert tick_data["tick_type"] == "last"
        assert tick_data["price"] == 100.55
        assert tick_data["size"] == 100
        assert "bid_price" not in tick_data
    
    def test_expanded_to_tick_data(self, v3_historical_client):
        """Test conversion of expanded message to tick data."""
        expanded_message = {
            "contract_id": 12345,
            "tick_type": "bid_ask",
            "ib_timestamp": 1640995200000000,
            "system_timestamp": 1640995201000000,
            "request_id": 123,
            "bid_price": 100.5,
            "bid_size": 10,
            "ask_price": 100.6,
            "ask_size": 5
        }
        
        tick_data = v3_historical_client._expanded_to_tick_data(expanded_message)
        
        assert tick_data["contract_id"] == 12345
        assert tick_data["tick_type"] == "bid_ask"
        assert tick_data["bid_price"] == 100.5
        assert tick_data["bid_size"] == 10
        assert tick_data["ask_price"] == 100.6
        assert tick_data["ask_size"] == 5
    
    def test_normalize_tick_type(self, v3_historical_client):
        """Test tick type normalization."""
        assert v3_historical_client._normalize_tick_type("bid_ask") == "BidAsk"
        assert v3_historical_client._normalize_tick_type("last") == "Last"
        assert v3_historical_client._normalize_tick_type("all_last") == "AllLast"
        assert v3_historical_client._normalize_tick_type("mid_point") == "MidPoint"
        assert v3_historical_client._normalize_tick_type("unknown") == "unknown"


class TestTimeRange:
    """Test TimeRange helper class."""
    
    def test_last_hour(self):
        """Test last hour time range."""
        end_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        start_time, returned_end_time = TimeRange.last_hour(end_time)
        
        assert returned_end_time == end_time
        assert start_time == datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    
    def test_last_hour_default_end(self):
        """Test last hour with default end time."""
        start_time, end_time = TimeRange.last_hour()
        
        assert end_time > start_time
        assert (end_time - start_time) == timedelta(hours=1)
    
    def test_last_day(self):
        """Test last day time range."""
        end_time = datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        start_time, returned_end_time = TimeRange.last_day(end_time)
        
        assert returned_end_time == end_time
        assert start_time == datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    def test_trading_session(self):
        """Test trading session time range."""
        date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        start_time, end_time = TimeRange.trading_session(date)
        
        # Should be 9:30 AM - 4:00 PM ET (approximated as 2:30 PM - 9:00 PM UTC)
        assert start_time.hour == 14
        assert start_time.minute == 30
        assert end_time.hour == 21
        assert end_time.minute == 0
    
    def test_custom_range(self):
        """Test custom time range."""
        start = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        
        returned_start, returned_end = TimeRange.custom_range(start, end)
        
        assert returned_start == start
        assert returned_end == end


@pytest.mark.asyncio
async def test_v3_stream_client_message_processing():
    """Integration test for V3StreamClient message processing."""
    config = StreamConfig(base_url="http://localhost:8001")
    client = V3StreamClient(config)
    
    # Mock callback
    callback_calls = []
    
    async def mock_callback(tick_type, data, stream_id, timestamp):
        callback_calls.append((tick_type, data, stream_id, timestamp))
    
    # Test v3 raw message processing
    v3_message = {
        "type": "tick",
        "stream_id": "12345_bid_ask_test",
        "timestamp": "2025-01-01T00:00:00Z",
        "data": {
            "ts": 1640995200000000,
            "cid": 12345,
            "tt": "bid_ask",
            "bp": 100.5,
            "ap": 100.6
        }
    }
    
    await client._handle_v3_tick_event(v3_message, mock_callback)
    
    assert len(callback_calls) == 1
    tick_type, data, stream_id, timestamp = callback_calls[0]
    
    assert tick_type == "BidAsk"
    assert data["contract_id"] == 12345
    assert data["bid_price"] == 100.5
    assert data["ask_price"] == 100.6
    assert stream_id == "12345_bid_ask_test"
    assert timestamp == "2025-01-01T00:00:00Z"


@pytest.mark.asyncio
async def test_v3_historical_client_stream_historical_data():
    """Integration test for V3HistoricalClient stream_historical_data."""
    config = StreamConfig(base_url="http://localhost:8001")
    
    # Mock the query_historical_data method
    mock_result = {
        "contract_id": 12345,
        "tick_types": ["bid_ask"],
        "total_messages": 2,
        "messages": [
            {
                "tick_type": "bid_ask",
                "ib_timestamp_iso": "2025-01-01T00:00:00Z",
                "contract_id": 12345,
                "bid_price": 100.5,
                "ask_price": 100.6
            },
            {
                "tick_type": "bid_ask", 
                "ib_timestamp_iso": "2025-01-01T00:01:00Z",
                "contract_id": 12345,
                "bid_price": 100.7,
                "ask_price": 100.8
            }
        ]
    }
    
    callback_calls = []
    
    async def mock_callback(tick_type, data, stream_id, timestamp):
        callback_calls.append((tick_type, data, stream_id, timestamp))
    
    async with V3HistoricalClient(config) as client:
        # Mock the query method
        client.query_historical_data = AsyncMock(return_value=mock_result)
        
        await client.stream_historical_data(
            contract_id=12345,
            tick_types=["bid_ask"],
            callback=mock_callback,
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
        )
    
    assert len(callback_calls) == 2
    
    # Check first message
    tick_type, data, stream_id, timestamp = callback_calls[0]
    assert tick_type == "BidAsk"
    assert data["contract_id"] == 12345
    assert data["bid_price"] == 100.5
    assert "12345_historical_0" == stream_id
    
    # Check second message
    tick_type, data, stream_id, timestamp = callback_calls[1]
    assert tick_type == "BidAsk"
    assert data["bid_price"] == 100.7
    assert "12345_historical_1" == stream_id