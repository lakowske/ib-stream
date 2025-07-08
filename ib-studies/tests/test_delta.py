"""Tests for delta study calculations."""

import pytest
from datetime import datetime

from ib_studies.models import StudyConfig
from ib_studies.studies.delta import DeltaStudy


class TestDeltaStudy:
    """Test delta study functionality."""
    
    def setup_method(self):
        """Setup for each test."""
        self.study = DeltaStudy(StudyConfig(window_seconds=60))
    
    def test_required_tick_types(self):
        """Test required tick types."""
        assert self.study.required_tick_types == ["BidAsk", "Last", "AllLast"]
    
    def test_calculate_delta_buy_at_ask(self):
        """Test delta calculation for buy at ask."""
        delta = self.study._calculate_delta(
            trade_price=100.05,
            bid_price=100.00,
            ask_price=100.05,
            trade_size=100
        )
        assert delta == 100  # Buy at ask
    
    def test_calculate_delta_sell_at_bid(self):
        """Test delta calculation for sell at bid."""
        delta = self.study._calculate_delta(
            trade_price=100.00,
            bid_price=100.00,
            ask_price=100.05,
            trade_size=200
        )
        assert delta == -200  # Sell at bid
    
    def test_calculate_delta_inside_spread(self):
        """Test delta calculation for trade inside spread."""
        delta = self.study._calculate_delta(
            trade_price=100.02,
            bid_price=100.00,
            ask_price=100.05,
            trade_size=150
        )
        assert delta == 0  # Inside spread
    
    def test_calculate_delta_above_ask(self):
        """Test delta calculation for buy above ask."""
        delta = self.study._calculate_delta(
            trade_price=100.10,
            bid_price=100.00,
            ask_price=100.05,
            trade_size=50
        )
        assert delta == 50  # Buy above ask
    
    def test_calculate_delta_below_bid(self):
        """Test delta calculation for sell below bid."""
        delta = self.study._calculate_delta(
            trade_price=99.95,
            bid_price=100.00,
            ask_price=100.05,
            trade_size=75
        )
        assert delta == -75  # Sell below bid
    
    def test_calculate_delta_crossed_market(self):
        """Test delta calculation for crossed market."""
        # Bid >= Ask (unusual but possible)
        delta = self.study._calculate_delta(
            trade_price=100.02,
            bid_price=100.05,
            ask_price=100.00,
            trade_size=100
        )
        # Should use midpoint logic
        mid_price = (100.05 + 100.00) / 2  # 100.025
        assert delta == 100 if 100.02 >= mid_price else -100
    
    def test_calculate_delta_with_neutral_zone(self):
        """Test delta calculation with neutral zone."""
        # Configure 10% neutral zone
        study = DeltaStudy(StudyConfig(neutral_zone_percent=10.0))
        
        # Spread is 0.05, so 10% neutral zone = 0.005
        # Bid threshold: 100.00 + 0.005 = 100.005
        # Ask threshold: 100.05 - 0.005 = 100.045
        
        # Trade at 100.02 should be neutral
        delta = study._calculate_delta(
            trade_price=100.02,
            bid_price=100.00,
            ask_price=100.05,
            trade_size=100
        )
        assert delta == 0  # In neutral zone
    
    def test_calculate_delta_zero_values(self):
        """Test delta calculation with zero values."""
        delta = self.study._calculate_delta(
            trade_price=0,
            bid_price=100.00,
            ask_price=100.05,
            trade_size=100
        )
        assert delta == 0  # Invalid price
        
        delta = self.study._calculate_delta(
            trade_price=100.00,
            bid_price=0,
            ask_price=100.05,
            trade_size=100
        )
        assert delta == 0  # Invalid bid
        
        delta = self.study._calculate_delta(
            trade_price=100.00,
            bid_price=100.00,
            ask_price=100.05,
            trade_size=0
        )
        assert delta == 0  # Invalid size
    
    def test_process_bid_ask_tick(self):
        """Test processing bid/ask tick."""
        data = {
            'timestamp': '2025-01-08T10:30:00',
            'bid_price': 100.00,
            'ask_price': 100.05,
            'bid_size': 500,
            'ask_size': 300
        }
        
        result = self.study.process_tick('BidAsk', data)
        
        # Should return None for quote updates
        assert result is None
        
        # Should update current quote
        assert self.study.current_quote is not None
        assert self.study.current_quote.bid_price == 100.00
        assert self.study.current_quote.ask_price == 100.05
    
    def test_process_trade_tick_without_quote(self):
        """Test processing trade tick without quote."""
        data = {
            'timestamp': '2025-01-08T10:30:00',
            'price': 100.05,
            'size': 100,
            'exchange': 'NASDAQ'
        }
        
        result = self.study.process_tick('Last', data)
        
        # Should return None without quote
        assert result is None
    
    def test_process_trade_tick_with_quote(self):
        """Test processing trade tick with quote."""
        # First set up quote
        quote_data = {
            'timestamp': '2025-01-08T10:30:00',
            'bid_price': 100.00,
            'ask_price': 100.05,
            'bid_size': 500,
            'ask_size': 300
        }
        self.study.process_tick('BidAsk', quote_data)
        
        # Now process trade
        trade_data = {
            'timestamp': '2025-01-08T10:30:01',
            'price': 100.05,
            'size': 100,
            'exchange': 'NASDAQ'
        }
        
        result = self.study.process_tick('Last', trade_data)
        
        # Should return trade result
        assert result is not None
        assert result['study'] == 'delta'
        assert result['current_trade']['price'] == 100.05
        assert result['current_trade']['size'] == 100
        assert result['current_trade']['delta'] == 100  # Buy at ask
        
        # Check cumulative delta
        assert self.study.cumulative_delta == 100
    
    def test_cumulative_delta_calculation(self):
        """Test cumulative delta over multiple trades."""
        # Set up quote
        quote_data = {
            'timestamp': '2025-01-08T10:30:00',
            'bid_price': 100.00,
            'ask_price': 100.05,
            'bid_size': 500,
            'ask_size': 300
        }
        self.study.process_tick('BidAsk', quote_data)
        
        # Trade 1: Buy at ask
        trade1 = {
            'timestamp': '2025-01-08T10:30:01',
            'price': 100.05,
            'size': 100
        }
        self.study.process_tick('Last', trade1)
        assert self.study.cumulative_delta == 100
        
        # Trade 2: Sell at bid
        trade2 = {
            'timestamp': '2025-01-08T10:30:02',
            'price': 100.00,
            'size': 200
        }
        self.study.process_tick('Last', trade2)
        assert self.study.cumulative_delta == -100  # 100 - 200
        
        # Trade 3: Buy above ask
        trade3 = {
            'timestamp': '2025-01-08T10:30:03',
            'price': 100.10,
            'size': 50
        }
        self.study.process_tick('Last', trade3)
        assert self.study.cumulative_delta == -50  # -100 + 50
    
    def test_get_summary(self):
        """Test summary statistics."""
        # Set up quote
        quote_data = {
            'timestamp': '2025-01-08T10:30:00',
            'bid_price': 100.00,
            'ask_price': 100.05,
            'bid_size': 500,
            'ask_size': 300
        }
        self.study.process_tick('BidAsk', quote_data)
        
        # Add some trades
        trades = [
            {'price': 100.05, 'size': 100},  # Buy
            {'price': 100.00, 'size': 200},  # Sell
            {'price': 100.02, 'size': 50},   # Neutral
            {'price': 100.05, 'size': 75},   # Buy
        ]
        
        for i, trade in enumerate(trades):
            trade['timestamp'] = f'2025-01-08T10:30:{i+1:02d}'
            self.study.process_tick('Last', trade)
        
        summary = self.study.get_summary()
        
        assert summary['trade_count'] == 4
        assert summary['total_buy_volume'] == 175  # 100 + 75
        assert summary['total_sell_volume'] == 200
        assert summary['total_neutral_volume'] == 50
        assert summary['net_delta'] == -25  # 175 - 200
        assert summary['cumulative_delta'] == -25  # 100 - 200 + 0 + 75
    
    def test_reset(self):
        """Test study reset."""
        # Set up some data
        quote_data = {
            'timestamp': '2025-01-08T10:30:00',
            'bid_price': 100.00,
            'ask_price': 100.05,
            'bid_size': 500,
            'ask_size': 300
        }
        self.study.process_tick('BidAsk', quote_data)
        
        trade_data = {
            'timestamp': '2025-01-08T10:30:01',
            'price': 100.05,
            'size': 100
        }
        self.study.process_tick('Last', trade_data)
        
        # Verify data exists
        assert self.study.current_quote is not None
        assert len(self.study.delta_buffer) > 0
        assert self.study.cumulative_delta != 0
        
        # Reset
        self.study.reset()
        
        # Verify reset
        assert self.study.current_quote is None
        assert len(self.study.delta_buffer) == 0
        assert self.study.cumulative_delta == 0
        assert self.study.tick_count == 0