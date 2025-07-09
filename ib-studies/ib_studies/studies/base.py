"""Base class for all market studies."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ib_studies.models import StudyConfig


class BaseStudy(ABC):
    """Abstract base class for all market studies."""
    
    def __init__(self, config: Optional[StudyConfig] = None):
        """Initialize the study with configuration."""
        self.config = config or StudyConfig()
        self._start_time = datetime.now()
        self._tick_count = 0
        
    @abstractmethod
    def process_tick(self, tick_type: str, data: Dict[str, Any], stream_id: str = "", timestamp: str = "") -> Optional[Dict[str, Any]]:
        """
        Process incoming v2 protocol tick data.
        
        Args:
            tick_type: Type of tick (BidAsk, Last, AllLast, etc.)
            data: Tick data dictionary
            stream_id: V2 protocol stream identifier (optional for backward compatibility)
            timestamp: V2 protocol timestamp (optional for backward compatibility)
            
        Returns:
            Optional dictionary with study results or None
        """
        pass
    
    @abstractmethod
    def get_summary(self) -> Dict[str, Any]:
        """
        Get current study summary.
        
        Returns:
            Dictionary with summary statistics
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reset study state."""
        pass
    
    @property
    @abstractmethod
    def required_tick_types(self) -> List[str]:
        """
        List of required tick types for this study.
        
        Returns:
            List of tick type strings
        """
        pass
    
    @property
    def name(self) -> str:
        """Get study name."""
        return self.__class__.__name__.replace("Study", "").lower()
    
    @property
    def uptime(self) -> timedelta:
        """Get time since study started."""
        return datetime.now() - self._start_time
    
    @property
    def tick_count(self) -> int:
        """Get total number of ticks processed."""
        return self._tick_count
    
    def cleanup_old_data(self, data_points: List[Any], window_seconds: int) -> List[Any]:
        """
        Remove data points older than the window.
        
        Args:
            data_points: List of data points with timestamp attribute
            window_seconds: Window size in seconds
            
        Returns:
            Filtered list with only recent data points
        """
        if not data_points:
            return data_points
            
        from datetime import timezone
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        return [
            point for point in data_points 
            if hasattr(point, 'timestamp') and point.timestamp > cutoff_time
        ]
    
    def increment_tick_count(self) -> None:
        """Increment the tick counter."""
        self._tick_count += 1