"""JSON formatter for study output."""

import json
from typing import Any, Dict, Optional, TextIO

from ib_studies.formatters.base import BaseFormatter


class JSONFormatter(BaseFormatter):
    """JSON formatter for machine-readable output."""
    
    def __init__(self, output_file: Optional[TextIO] = None, pretty: bool = False):
        """Initialize JSON formatter."""
        super().__init__(output_file)
        self.pretty = pretty
        self.indent = 2 if pretty else None
    
    def format_header(self, contract_id: int, study_name: str, **kwargs) -> str:
        """Format header information as JSON."""
        header_data = {
            "event": "session_start",
            "contract_id": contract_id,
            "study": study_name,
            "timestamp": kwargs.get('timestamp', ''),
            "config": kwargs
        }
        return self._format_json(header_data) + "\n"
    
    def format_update(self, data: Dict[str, Any]) -> str:
        """Format a single update as JSON."""
        # Add event type
        output_data = {
            "event": "tick_update",
            **data
        }
        return self._format_json(output_data) + "\n"
    
    def format_summary(self, data: Dict[str, Any]) -> str:
        """Format summary statistics as JSON."""
        summary_data = {
            "event": "summary",
            "timestamp": data.get('timestamp', ''),
            "summary": data
        }
        return self._format_json(summary_data) + "\n"
    
    def format_final_summary(self, data: Dict[str, Any]) -> str:
        """Format final summary as JSON."""
        final_data = {
            "event": "session_end",
            "timestamp": data.get('timestamp', ''),
            "final_summary": data.get('summary', {})
        }
        return self._format_json(final_data) + "\n"
    
    def format_error(self, error: str, **kwargs) -> str:
        """Format error message as JSON."""
        error_data = {
            "event": "error",
            "error": error,
            "timestamp": kwargs.get('timestamp', ''),
            **kwargs
        }
        return self._format_json(error_data) + "\n"
    
    def _format_json(self, data: Dict[str, Any]) -> str:
        """Format data as JSON string."""
        try:
            return json.dumps(
                data,
                indent=self.indent,
                ensure_ascii=False,
                sort_keys=True
            )
        except (TypeError, ValueError) as e:
            # Fallback for non-serializable data
            return json.dumps({
                "event": "format_error",
                "error": str(e),
                "original_data": str(data)
            })