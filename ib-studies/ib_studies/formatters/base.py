"""Base formatter for study output."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TextIO


class BaseFormatter(ABC):
    """Abstract base class for output formatters."""
    
    def __init__(self, output_file: Optional[TextIO] = None):
        """Initialize formatter with optional output file."""
        self.output_file = output_file
    
    @abstractmethod
    def format_update(self, data: Dict[str, Any]) -> str:
        """
        Format a single update/event.
        
        Args:
            data: Study output data
            
        Returns:
            Formatted string
        """
        pass
    
    @abstractmethod
    def format_summary(self, data: Dict[str, Any]) -> str:
        """
        Format summary statistics.
        
        Args:
            data: Summary data
            
        Returns:
            Formatted string
        """
        pass
    
    @abstractmethod
    def format_header(self, contract_id: int, study_name: str, **kwargs) -> str:
        """
        Format header information.
        
        Args:
            contract_id: Contract ID being analyzed
            study_name: Name of the study
            **kwargs: Additional header parameters
            
        Returns:
            Formatted header string
        """
        pass
    
    def output(self, text: str) -> None:
        """
        Output text to file or stdout.
        
        Args:
            text: Text to output
        """
        if self.output_file:
            self.output_file.write(text)
            self.output_file.flush()
        else:
            print(text, end='')
    
    def close(self) -> None:
        """Close output file if applicable."""
        if self.output_file and hasattr(self.output_file, 'close'):
            self.output_file.close()