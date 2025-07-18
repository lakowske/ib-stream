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

        # Study-specific column headers
        if study_name.lower() == 'vwap':
            columns = "Time         Price    Volume   VWAP     Upper(+3σ)  Lower(-3σ)  Status"
            separator = "─" * 75
        elif study_name.lower() == 'bollinger' or study_name.lower() == 'bollinger_bands':
            columns = "Time         Price    SMA      Upper(+1σ)  Lower(-1σ)  Position     %B"
            separator = "─" * 75
        else:
            # Default delta format for other studies
            columns = "Time         Price    Size     Bid      Ask      Delta    Cumulative"
            separator = "─" * 65

        header = f"""
IB-Studies {study_name.title()} Analysis
Contract: {contract_id}
Window: {window_seconds} seconds
Started: {timestamp}

{columns}
{separator}
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

            # Use table format: Time, Price (bid), Size (bid_size), Bid, Ask, Delta (0), Cumulative
            line = (
                f"{time_str:<12} {bid_price:<8.2f} {bid_size:<8.0f} {bid_price:<8.2f} "
                f"{ask_price:<8.2f} {'0':<8} {'0'}\n"
            )

        elif tick_type in ['last', 'Last', 'all_last', 'AllLast']:
            price = tick_data.get('price', 0.0)
            size = tick_data.get('size', 0.0)

            # Use table format: Time, Price, Size, Bid (last), Ask (last), Delta (0), Cumulative (0)
            line = (
                f"{time_str:<12} {price:<8.2f} {size:<8.0f} {self.last_bid:<8.2f} "
                f"{self.last_ask:<8.2f} {'0':<8} {'0'}\n"
            )

        elif tick_type in ['time_sales']:
            # time_sales contains nested trade data
            price = tick_data.get('price', 0.0)
            size = tick_data.get('size', 0.0)

            # Use table format: Time, Price, Size, Bid (last), Ask (last), Delta (0), Cumulative (0)
            line = (
                f"{time_str:<12} {price:<8.2f} {size:<8.0f} {self.last_bid:<8.2f} "
                f"{self.last_ask:<8.2f} {'0':<8} {'0'}\n"
            )

        else:
            # Generic format for other tick types
            line = (
                f"{time_str:<12} {'0.00':<8} {'0':<8} {'0.00':<8} {'0.00':<8} {'0':<8} {'0'} "
                f"# {tick_type}: {tick_data}\n"
            )

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

        # Get study name for formatting
        study_name = data.get('study', 'unknown').lower()

        # Format based on study type
        if study_name == 'vwap':
            result += self._format_vwap_update(data)
        elif study_name == 'bollinger' or study_name == 'bollinger_bands':
            result += self._format_bollinger_update(data)
        else:
            # Default delta format for other studies
            result += self._format_delta_update(data)

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

        study_name = data.get('study', 'unknown').lower()
        data.get('window_seconds', 60)
        data.get('trade_count', 0)

        # Study-specific summary formatting
        if study_name == 'vwap':
            return self._format_vwap_summary(data)
        elif study_name == 'bollinger' or study_name == 'bollinger_bands':
            return self._format_bollinger_summary(data)
        else:
            # Default delta summary
            return self._format_delta_summary(data)

    def _format_delta_summary(self, data: dict[str, Any]) -> str:
        """Format delta study summary."""
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

    def _format_vwap_update(self, data: dict[str, Any]) -> str:
        """Format VWAP study update."""
        current_trade = data.get('current_trade', {})
        vwap_data = data.get('vwap', {})

        timestamp = current_trade.get('timestamp', '')
        time_str = format_timestamp_for_display(timestamp, self.display_timezone)

        price = current_trade.get('price', 0)
        volume = current_trade.get('size', 0)
        vwap = vwap_data.get('value', 0)
        upper_band = vwap_data.get('upper_band', 0)
        lower_band = vwap_data.get('lower_band', 0)
        band_position = vwap_data.get('band_position', 'within')

        # Use the band_position from the VWAP study or determine status based on price relative to bands
        if band_position == "above_upper":
            status = "Above+3σ"
        elif band_position == "below_lower":
            status = "Below-3σ"
        else:
            status = "Within"

        line = (
            f"{time_str:<12} {price:<8.2f} {volume:<8.0f} {vwap:<8.2f} "
            f"{upper_band:<10.2f} {lower_band:<10.2f} {status}\n"
        )
        return line

    def _format_bollinger_update(self, data: dict[str, Any]) -> str:
        """Format Bollinger Bands study update."""
        current_trade = data.get('current_trade', {})
        bands_data = data.get('bands', {})
        analysis_data = data.get('analysis', {})

        timestamp = current_trade.get('timestamp', '')
        time_str = format_timestamp_for_display(timestamp, self.display_timezone)

        price = current_trade.get('price', 0)
        sma = bands_data.get('sma', 0)
        upper_band = bands_data.get('upper_band', 0)
        lower_band = bands_data.get('lower_band', 0)
        percent_b = analysis_data.get('percent_b', 0)
        band_position = analysis_data.get('band_position', 'within')

        # Use the band_position from the Bollinger Bands study
        if band_position == "above_upper":
            position = "Above+1σ"
        elif band_position == "below_lower":
            position = "Below-1σ"
        else:
            position = "Within"

        line = (
            f"{time_str:<12} {price:<8.2f} {sma:<8.2f} {upper_band:<10.2f} "
            f"{lower_band:<10.2f} {position:<10} {percent_b:<.2f}\n"
        )
        return line

    def _format_delta_update(self, data: dict[str, Any]) -> str:
        """Format delta study update."""
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

        line = (
            f"{time_str:<12} {price:<8.2f} {size:<8.0f} {bid:<8.2f} "
            f"{ask:<8.2f} {delta_str:<8} {cumulative_str}\n"
        )
        return line

    def _format_vwap_summary(self, data: dict[str, Any]) -> str:
        """Format VWAP study summary."""
        window_seconds = data.get('window_seconds', 60)
        trade_count = data.get('trade_count', 0)
        total_volume = data.get('total_volume', 0)
        current_vwap = data.get('vwap', 0)
        realized_volatility = data.get('realized_volatility', 0)
        band_touches = data.get('band_touches', {})
        upper_band_touches = band_touches.get('upper', 0)
        lower_band_touches = band_touches.get('lower', 0)

        window_str = f"{window_seconds}s" if window_seconds > 0 else "session"

        summary = f"""
VWAP Summary ({window_str}):
  Trade Count:      {trade_count}
  Total Volume:     {total_volume:.0f} shares
  Current VWAP:     ${current_vwap:.2f}
  Volatility:       {realized_volatility:.4f}
  Upper Band Hits:  {upper_band_touches}
  Lower Band Hits:  {lower_band_touches}
{'─' * 75}
"""
        return summary

    def _format_bollinger_summary(self, data: dict[str, Any]) -> str:
        """Format Bollinger Bands study summary."""
        period_seconds = data.get('period_seconds', 60)
        trade_count = data.get('trade_count', 0)
        current_sma = data.get('sma', 0)
        current_std_dev = data.get('std_dev', 0)
        band_touches = data.get('band_touches', {})
        upper_band_touches = band_touches.get('upper', 0)
        lower_band_touches = band_touches.get('lower', 0)
        mean_reversion_signals = data.get('mean_reversion_signals', 0)

        summary = f"""
Bollinger Bands Summary ({period_seconds}s):
  Trade Count:         {trade_count}
  Current SMA:         ${current_sma:.2f}
  Std Deviation:       {current_std_dev:.4f}
  Upper Band Hits:     {upper_band_touches}
  Lower Band Hits:     {lower_band_touches}
  Mean Reversion:      {mean_reversion_signals}
{'─' * 75}
"""
        return summary

    def format_final_summary(self, data: dict[str, Any]) -> str:
        """Format final summary when stopping."""
        summary = data.get('summary', {})
        if not summary:
            return "\nNo data to summarize.\n"

        study_name = summary.get('study', data.get('study', 'unknown')).lower()

        if study_name == 'vwap':
            return self._format_vwap_final_summary(summary)
        elif study_name == 'bollinger' or study_name == 'bollinger_bands':
            return self._format_bollinger_final_summary(summary)
        else:
            return self._format_delta_final_summary(summary)

    def _format_vwap_final_summary(self, summary: dict[str, Any]) -> str:
        """Format VWAP final summary."""
        window_seconds = summary.get('window_seconds', 0)
        window_str = f"{window_seconds}s" if window_seconds > 0 else "session"
        band_touches = summary.get('band_touches', {})

        return f"""
{'=' * 75}
Final VWAP Summary ({window_str}):
  Total Trades:        {summary.get('trade_count', 0)}
  Total Volume:        {summary.get('total_volume', 0):.0f} shares
  Final VWAP:          ${summary.get('vwap', 0):.2f}
  Realized Volatility: {summary.get('realized_volatility', 0):.4f}
  Upper Band Touches:  {band_touches.get('upper', 0)}
  Lower Band Touches:  {band_touches.get('lower', 0)}
{'=' * 75}
"""

    def _format_bollinger_final_summary(self, summary: dict[str, Any]) -> str:
        """Format Bollinger Bands final summary."""
        band_touches = summary.get('band_touches', {})

        return f"""
{'=' * 75}
Final Bollinger Bands Summary ({summary.get('period_seconds', 60)}s):
  Total Trades:        {summary.get('trade_count', 0)}
  Final SMA:           ${summary.get('sma', 0):.2f}
  Standard Deviation:  {summary.get('std_dev', 0):.4f}
  Upper Band Touches:  {band_touches.get('upper', 0)}
  Lower Band Touches:  {band_touches.get('lower', 0)}
  Mean Reversion:      {summary.get('mean_reversion_signals', 0)}
{'=' * 75}
"""

    def _format_delta_final_summary(self, summary: dict[str, Any]) -> str:
        """Format delta final summary."""
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
