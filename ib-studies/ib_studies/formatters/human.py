"""Human-readable formatter for study output."""

from datetime import datetime
from typing import Any, Optional, TextIO

from ib_studies.formatters.base import BaseFormatter
from ib_studies.timezone_utils import format_header_timestamp, format_timestamp_for_display


class HumanFormatter(BaseFormatter):
    """Human-readable formatter with table output."""

    def __init__(self, output_file: Optional[TextIO] = None, show_header: bool = True,
                 display_timezone: Optional[str] = None):
        """Initialize human formatter."""
        super().__init__(output_file)
        self.show_header = show_header
        self.header_shown = False
        self.last_summary_time = None
        self.summary_interval = 10  # Show summary every 10 seconds
        # Track last known bid/ask for passthrough
        self.last_bid = 0.0
        self.last_ask = 0.0
        # Timezone for displaying timestamps
        self.display_timezone = display_timezone

    def format_header(self, contract_id: int, study_name: str, **kwargs) -> str:
        """Format header information."""
        window_seconds = kwargs.get('window_seconds', 60)
        timestamp = format_header_timestamp(self.display_timezone)

        header = f"""
IB-Studies {study_name.title()} Analysis
Contract: {contract_id}
Window: {window_seconds} seconds
Started: {timestamp}

Time         Price    Size     Bid      Ask      Delta    Cumulative
─────────────────────────────────────────────────────────────────────
"""
        return header

    def _format_passthrough_as_table(self, data: dict[str, Any]) -> str:
        """Format passthrough data using the original table format."""
        if not self.header_shown and self.show_header:
            contract_id = data.get('contract_id', 'unknown')
            study_name = data.get('study', 'passthrough')
            header = self.format_header(contract_id, study_name)
            self.header_shown = True
            result = header
        else:
            result = ""

        # Extract tick data
        tick_type = data.get('tick_type', 'unknown')
        tick_data = data.get('data', {})
        timestamp = data.get('timestamp', '')

        time_str = format_timestamp_for_display(timestamp, self.display_timezone)

        # Format based on tick type
        if tick_type in ['bid_ask', 'BidAsk']:
            bid_price = tick_data.get('bid_price', 0.0)
            ask_price = tick_data.get('ask_price', 0.0)
            bid_size = tick_data.get('bid_size', 0.0)
            tick_data.get('ask_size', 0.0)

            # Update last known bid/ask
            if bid_price > 0:
                self.last_bid = bid_price
            if ask_price > 0:
                self.last_ask = ask_price

            # Use table format: Time, Price (bid), Size (bid_size), Bid, Ask, Delta (0), Cumulative (0)
            line = f"{time_str:<12} {bid_price:<8.2f} {bid_size:<8.0f} {bid_price:<8.2f} {ask_price:<8.2f} {'0':<8} {'0'}\n"

        elif tick_type in ['last', 'Last', 'all_last', 'AllLast']:
            price = tick_data.get('price', 0.0)
            size = tick_data.get('size', 0.0)

            # Use table format: Time, Price, Size, Bid (last), Ask (last), Delta (0), Cumulative (0)
            line = f"{time_str:<12} {price:<8.2f} {size:<8.0f} {self.last_bid:<8.2f} {self.last_ask:<8.2f} {'0':<8} {'0'}\n"

        elif tick_type in ['time_sales']:
            # time_sales contains nested trade data
            price = tick_data.get('price', 0.0)
            size = tick_data.get('size', 0.0)

            # Use table format: Time, Price, Size, Bid (last), Ask (last), Delta (0), Cumulative (0)
            line = f"{time_str:<12} {price:<8.2f} {size:<8.0f} {self.last_bid:<8.2f} {self.last_ask:<8.2f} {'0':<8} {'0'}\n"

        else:
            # Generic format for other tick types
            line = f"{time_str:<12} {'0.00':<8} {'0':<8} {'0.00':<8} {'0.00':<8} {'0':<8} {'0'} # {tick_type}: {tick_data}\n"

        result += line
        return result

    def format_update(self, data: dict[str, Any]) -> str:
        """Format a single trade update."""
        # Handle passthrough study - use original table format but extract data differently
        if data.get('study') == 'passthrough':
            return self._format_passthrough_as_table(data)

        if not self.header_shown and self.show_header:
            contract_id = data.get('contract_id', 'unknown')
            study_name = data.get('study', 'unknown')
            window_seconds = data.get('summary', {}).get('window_seconds', 60)

            header = self.format_header(contract_id, study_name, window_seconds=window_seconds)
            self.header_shown = True
            result = header
        else:
            result = ""

        # Format current trade
        current_trade = data.get('current_trade', {})
        current_quote = data.get('current_quote', {})

        timestamp = current_trade.get('timestamp', '')
        time_str = format_timestamp_for_display(timestamp, self.display_timezone)

        price = current_trade.get('price', 0)
        size = current_trade.get('size', 0)
        delta = current_trade.get('delta', 0)
        bid = current_quote.get('bid', 0)
        ask = current_quote.get('ask', 0)

        # Get cumulative delta from summary
        cumulative_delta = data.get('summary', {}).get('cumulative_delta', 0)

        # Format delta with sign
        delta_str = f"{delta:+.0f}" if delta != 0 else "0"
        cumulative_str = f"{cumulative_delta:+.0f}" if cumulative_delta != 0 else "0"

        line = f"{time_str:<12} {price:<8.2f} {size:<8.0f} {bid:<8.2f} {ask:<8.2f} {delta_str:<8} {cumulative_str}\n"
        result += line

        # Show summary periodically
        now = datetime.now()
        if (self.last_summary_time is None or
            (now - self.last_summary_time).total_seconds() >= self.summary_interval):

            summary = self.format_summary(data.get('summary', {}))
            result += summary
            self.last_summary_time = now

        return result

    def format_summary(self, data: dict[str, Any]) -> str:
        """Format summary statistics."""
        if not data:
            return ""

        window_seconds = data.get('window_seconds', 60)
        trade_count = data.get('trade_count', 0)
        total_buy_volume = data.get('total_buy_volume', 0)
        total_sell_volume = data.get('total_sell_volume', 0)
        net_delta = data.get('net_delta', 0)
        buy_sell_ratio = data.get('buy_sell_ratio')
        buy_percentage = data.get('buy_percentage', 0)

        # Format buy/sell ratio
        ratio_str = f"{buy_sell_ratio:.2f}" if buy_sell_ratio is not None else "N/A"

        summary = f"""
Summary (last {window_seconds}s):
  Trade Count:     {trade_count}
  Total Buys:      {total_buy_volume:.0f} shares
  Total Sells:     {total_sell_volume:.0f} shares
  Net Delta:       {net_delta:+.0f} shares
  Buy/Sell Ratio:  {ratio_str}
  Buy Percentage:  {buy_percentage:.1f}%
{'─' * 65}
"""
        return summary

    def format_final_summary(self, data: dict[str, Any]) -> str:
        """Format final summary when stopping."""
        summary = data.get('summary', {})
        if not summary:
            return "\nNo data to summarize.\n"

        return f"""
{'=' * 65}
Final Summary:
  Total Trades:    {summary.get('trade_count', 0)}
  Total Buys:      {summary.get('total_buy_volume', 0):.0f} shares
  Total Sells:     {summary.get('total_sell_volume', 0):.0f} shares
  Net Delta:       {summary.get('net_delta', 0):+.0f} shares
  Cumulative:      {summary.get('cumulative_delta', 0):+.0f} shares
  Buy Percentage:  {summary.get('buy_percentage', 0):.1f}%
{'=' * 65}
"""
