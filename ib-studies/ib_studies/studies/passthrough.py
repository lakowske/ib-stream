"""Pass-through study for debugging data flow."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ib_studies.models import StudyConfig
from ib_studies.studies.base import BaseStudy

logger = logging.getLogger(__name__)


class PassThroughStudy(BaseStudy):
    """
    Pass-through study that outputs all incoming tick data.
    Useful for debugging and understanding data flow.
    """
    
    def __init__(self, config: Optional[StudyConfig] = None):
        """Initialize pass-through study."""
        super().__init__(config)
        self.tick_history: List[Dict[str, Any]] = []
        
    @property
    def required_tick_types(self) -> List[str]:
        """Pass-through study accepts all tick types."""
        return ["BidAsk", "Last", "AllLast", "MidPoint"]
    
    def process_tick(self, tick_type: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process incoming tick data by passing it through."""
        self.increment_tick_count()
        
        # Create standardized output
        output = {
            "study": "passthrough",
            "timestamp": datetime.now().isoformat(),
            "tick_type": tick_type,
            "data": data,
            "metadata": {
                "tick_count": self._tick_count,
                "study_uptime_seconds": (datetime.now() - self._start_time).total_seconds()
            }
        }
        
        # Keep recent history
        self.tick_history.append(output)
        # Keep only last 100 ticks
        if len(self.tick_history) > 100:
            self.tick_history.pop(0)
        
        logger.debug("PassThrough tick #%d: %s -> %s", self._tick_count, tick_type, data)
        
        return output
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of tick activity."""
        # Count ticks by type
        tick_counts = {}
        for tick in self.tick_history:
            tick_type = tick["tick_type"]
            tick_counts[tick_type] = tick_counts.get(tick_type, 0) + 1
        
        return {
            "total_ticks": self._tick_count,
            "tick_types_seen": list(tick_counts.keys()),
            "tick_counts_by_type": tick_counts,
            "uptime_seconds": (datetime.now() - self._start_time).total_seconds(),
            "recent_ticks": len(self.tick_history)
        }
    
    def reset(self) -> None:
        """Reset study state."""
        self.tick_history.clear()
        self._tick_count = 0
        self._start_time = datetime.now()
        logger.info("Pass-through study reset")