"""Human-readable formatter for study output."""

from datetime import datetime
from typing import Any, Dict, Optional, TextIO

from ib_studies.formatters.base import BaseFormatter


class HumanFormatter(BaseFormatter):
    """Human-readable formatter with table output."""
    
    def __init__(self, output_file: Optional[TextIO] = None, show_header: bool = True):
        """Initialize human formatter."""
        super().__init__(output_file)
        self.show_header = show_header
        self.header_shown = False
        self.last_summary_time = None
        self.summary_interval = 10  # Show summary every 10 seconds
    
    def format_header(self, contract_id: int, study_name: str, **kwargs) -> str:
        """Format header information."""
        window_seconds = kwargs.get('window_seconds', 60)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        header = f"""
IB-Studies {study_name.title()} Analysis
Contract: {contract_id}
Window: {window_seconds} seconds
Started: {timestamp}

Time         Price    Size     Bid      Ask      Delta    Cumulative
─────────────────────────────────────────────────────────────────────
"""
        return header
    
    def format_update(self, data: Dict[str, Any]) -> str:
        """Format a single trade update."""
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
        if timestamp:
            # Parse and format timestamp
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M:%S')
            except ValueError:
                time_str = timestamp[:8]  # Take first 8 chars
        else:
            time_str = datetime.now().strftime('%H:%M:%S')
        
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
    
    def format_summary(self, data: Dict[str, Any]) -> str:
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
    
    def format_final_summary(self, data: Dict[str, Any]) -> str:
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