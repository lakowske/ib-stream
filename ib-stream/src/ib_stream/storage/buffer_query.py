"""
Buffer Query Methods for Tracked Contracts

This module provides convenient query methods for retrieving buffered historical data
from tracked contracts, designed to support seamless historical-to-live streaming.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple, AsyncIterator
from pathlib import Path

from .json_storage import JSONStorage

logger = logging.getLogger(__name__)


class BufferQuery:
    """Query interface for retrieving buffered data from tracked contracts"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.json_storage = JSONStorage(storage_path / "json")
    
    async def query_buffer(
        self, 
        contract_id: int, 
        tick_types: List[str], 
        buffer_duration: str = "1h"
    ) -> List[Dict]:
        """
        Query recent buffer data for a contract.
        
        Args:
            contract_id: Contract ID to query
            tick_types: List of tick types to include
            buffer_duration: Duration string (e.g., "1h", "30m", "2h")
            
        Returns:
            List of tick messages sorted by timestamp
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - self._parse_duration(buffer_duration)
        
        return await self.json_storage.query_range(
            contract_id=contract_id,
            tick_types=tick_types,
            start_time=start_time,
            end_time=end_time
        )
    
    async def query_buffer_since(
        self,
        contract_id: int,
        tick_types: List[str],
        since_time: datetime
    ) -> List[Dict]:
        """
        Query buffer data since a specific time.
        
        Args:
            contract_id: Contract ID to query
            tick_types: List of tick types to include  
            since_time: Start time for query
            
        Returns:
            List of tick messages sorted by timestamp
        """
        end_time = datetime.now(timezone.utc)
        
        return await self.json_storage.query_range(
            contract_id=contract_id,
            tick_types=tick_types,
            start_time=since_time,
            end_time=end_time
        )
    
    async def query_session_buffer(
        self,
        contract_id: int,
        tick_types: List[str],
        session_start: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Query buffer data since session start.
        
        Args:
            contract_id: Contract ID to query
            tick_types: List of tick types to include
            session_start: Session start time (defaults to market open estimation)
            
        Returns:
            List of tick messages sorted by timestamp
        """
        if session_start is None:
            # Estimate US market open (9:30 AM ET = 13:30 or 14:30 UTC depending on DST)
            # This is a simple estimation - could be enhanced with proper market calendar
            now = datetime.now(timezone.utc)
            today = now.date()
            
            # Try 14:30 UTC first (EST), then 13:30 UTC (EDT)
            session_start = datetime.combine(today, datetime.min.time().replace(hour=14, minute=30), timezone.utc)
            if session_start > now:
                # Try previous day
                session_start -= timedelta(days=1)
            
            # If still in the future, try EDT time
            if session_start > now:
                session_start = datetime.combine(today, datetime.min.time().replace(hour=13, minute=30), timezone.utc)
                if session_start > now:
                    session_start -= timedelta(days=1)
        
        return await self.query_buffer_since(contract_id, tick_types, session_start)
    
    def get_available_buffer_duration(
        self,
        contract_id: int,
        tick_types: List[str]
    ) -> Optional[timedelta]:
        """
        Get the available buffer duration for a contract.
        
        Args:
            contract_id: Contract ID to check
            tick_types: List of tick types to check
            
        Returns:
            Timedelta representing available buffer duration, or None if no data
        """
        # Find oldest available data
        files = self._find_contract_files(contract_id, tick_types)
        if not files:
            return None
        
        # Parse timestamps from oldest file to get start time
        oldest_file = min(files, key=lambda f: f.stat().st_mtime)
        
        try:
            # Try to read first message from oldest file
            with open(oldest_file, 'r') as f:
                for line in f:
                    if line.strip():
                        import json
                        message = json.loads(line.strip())
                        oldest_time = datetime.fromisoformat(
                            message['timestamp'].replace('Z', '+00:00')
                        )
                        current_time = datetime.now(timezone.utc)
                        return current_time - oldest_time
        except Exception as e:
            logger.warning("Could not determine buffer duration for contract %d: %s", 
                         contract_id, e)
        
        return None
    
    def is_contract_tracked(self, contract_id: int) -> bool:
        """
        Check if a contract has any stored data (indicating it's tracked).
        
        Args:
            contract_id: Contract ID to check
            
        Returns:
            True if contract has stored data
        """
        files = self._find_contract_files(contract_id, ["bid_ask", "last", "all_last", "mid_point"])
        return len(files) > 0
    
    def get_latest_tick_time(
        self,
        contract_id: int,
        tick_types: List[str]
    ) -> Optional[datetime]:
        """
        Get the timestamp of the most recent tick for a contract.
        
        Args:
            contract_id: Contract ID to check
            tick_types: List of tick types to check
            
        Returns:
            Datetime of most recent tick, or None if no data
        """
        files = self._find_contract_files(contract_id, tick_types)
        if not files:
            return None
        
        # Check most recent file
        newest_file = max(files, key=lambda f: f.stat().st_mtime)
        
        try:
            # Read from end of file to find latest timestamp
            with open(newest_file, 'r') as f:
                lines = f.readlines()
                for line in reversed(lines):
                    if line.strip():
                        import json
                        message = json.loads(line.strip())
                        return datetime.fromisoformat(
                            message['timestamp'].replace('Z', '+00:00')
                        )
        except Exception as e:
            logger.warning("Could not determine latest tick time for contract %d: %s", 
                         contract_id, e)
        
        return None
    
    async def get_buffer_stats(
        self,
        contract_id: int,
        tick_types: List[str],
        buffer_duration: str = "1h"
    ) -> Dict:
        """
        Get statistics about available buffer data.
        
        Args:
            contract_id: Contract ID to analyze
            tick_types: List of tick types to include
            buffer_duration: Duration to analyze
            
        Returns:
            Dictionary with buffer statistics
        """
        messages = await self.query_buffer(contract_id, tick_types, buffer_duration)
        
        if not messages:
            return {
                "message_count": 0,
                "tick_types": [],
                "time_range": None,
                "duration_requested": buffer_duration,
                "duration_available": None
            }
        
        # Analyze messages
        tick_type_counts = {}
        earliest_time = None
        latest_time = None
        
        for msg in messages:
            # Count by tick type
            tick_type = msg.get('data', {}).get('tick_type', 'unknown')
            tick_type_counts[tick_type] = tick_type_counts.get(tick_type, 0) + 1
            
            # Track time range
            msg_time = datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00'))
            if earliest_time is None or msg_time < earliest_time:
                earliest_time = msg_time
            if latest_time is None or msg_time > latest_time:
                latest_time = msg_time
        
        duration_available = None
        if earliest_time and latest_time:
            duration_available = latest_time - earliest_time
        
        return {
            "message_count": len(messages),
            "tick_type_counts": tick_type_counts,
            "tick_types": list(tick_type_counts.keys()),
            "time_range": {
                "start": earliest_time.isoformat() if earliest_time else None,
                "end": latest_time.isoformat() if latest_time else None
            },
            "duration_requested": buffer_duration,
            "duration_available": str(duration_available) if duration_available else None
        }
    
    def _parse_duration(self, duration_str: str) -> timedelta:
        """
        Parse duration string into timedelta.
        
        Supports formats like: 1h, 30m, 2h30m, 1d, etc.
        """
        duration_str = duration_str.lower().strip()
        
        # Simple mappings for common durations
        simple_mappings = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "2h": timedelta(hours=2),
            "4h": timedelta(hours=4),
            "6h": timedelta(hours=6),
            "12h": timedelta(hours=12),
            "1d": timedelta(days=1),
            "2d": timedelta(days=2),
            "1w": timedelta(weeks=1)
        }
        
        if duration_str in simple_mappings:
            return simple_mappings[duration_str]
        
        # Parse more complex formats
        import re
        
        total_delta = timedelta()
        
        # Find all patterns like "2h", "30m", "1d"
        patterns = re.findall(r'(\d+)([dhms])', duration_str)
        
        for value, unit in patterns:
            value = int(value)
            if unit == 'd':
                total_delta += timedelta(days=value)
            elif unit == 'h':
                total_delta += timedelta(hours=value)
            elif unit == 'm':
                total_delta += timedelta(minutes=value)
            elif unit == 's':
                total_delta += timedelta(seconds=value)
        
        if total_delta == timedelta():
            # Default to 1 hour if parsing fails
            logger.warning("Could not parse duration '%s', defaulting to 1 hour", duration_str)
            return timedelta(hours=1)
        
        return total_delta
    
    def _find_contract_files(self, contract_id: int, tick_types: List[str]) -> List[Path]:
        """Find all files for a contract and tick types"""
        files = []
        
        # Search for files in the JSON storage directory structure
        # Format: storage/json/YYYY/MM/DD/HH/contractid_ticktype_timestamp_random.jsonl
        json_path = self.storage_path / "json"
        
        if not json_path.exists():
            return files
        
        # Search through date directories for recent files
        # For efficiency, only check last few days
        now = datetime.now(timezone.utc)
        for days_back in range(7):  # Check last 7 days
            date = now - timedelta(days=days_back)
            date_path = json_path / date.strftime("%Y/%m/%d")
            
            if not date_path.exists():
                continue
            
            # Check all hours in this date
            for hour_dir in date_path.iterdir():
                if not hour_dir.is_dir():
                    continue
                
                # Look for files matching contract and tick types
                for file_path in hour_dir.iterdir():
                    if not file_path.is_file() or not file_path.name.endswith('.jsonl'):
                        continue
                    
                    # Parse filename: contractid_ticktype_timestamp_random.jsonl
                    parts = file_path.stem.split('_')
                    if len(parts) >= 2:
                        try:
                            file_contract_id = int(parts[0])
                            file_tick_type = parts[1]
                            
                            if (file_contract_id == contract_id and 
                                file_tick_type in tick_types):
                                files.append(file_path)
                        except ValueError:
                            continue
        
        return files


# Helper function for easy access
def create_buffer_query(storage_path: Path) -> BufferQuery:
    """Create a BufferQuery instance"""
    return BufferQuery(storage_path)