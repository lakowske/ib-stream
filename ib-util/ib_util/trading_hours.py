"""
Trading Hours Utilities for Interactive Brokers API
Parses IB trading hours format and determines market status
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, NamedTuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# Security and validation constants
ALLOWED_TIMEZONES = {
    'US/Eastern', 'US/Central', 'US/Mountain', 'US/Pacific',
    'Europe/London', 'Europe/Berlin', 'Europe/Zurich',
    'Asia/Tokyo', 'Asia/Hong_Kong', 'Asia/Shanghai',
    'Australia/Sydney', 'Australia/Melbourne',
    'UTC'
}

MAX_CONTRACT_ID = 999999999999  # IB contract IDs are typically 12 digits max
MIN_CONTRACT_ID = 1

class ValidationError(Exception):
    """Custom exception for input validation errors"""
    pass

def validate_contract_id(contract_id: int) -> int:
    """
    Validate contract ID is within acceptable bounds
    
    Args:
        contract_id: Contract ID to validate
        
    Returns:
        Validated contract ID
        
    Raises:
        ValidationError: If contract ID is invalid
    """
    if not isinstance(contract_id, int):
        raise ValidationError(f"Contract ID must be an integer, got {type(contract_id)}")
    
    if not (MIN_CONTRACT_ID <= contract_id <= MAX_CONTRACT_ID):
        raise ValidationError(f"Contract ID {contract_id} out of valid range [{MIN_CONTRACT_ID}, {MAX_CONTRACT_ID}]")
    
    return contract_id

def validate_timezone(timezone_id: str) -> str:
    """
    Validate timezone ID against allowed list
    
    Args:
        timezone_id: Timezone identifier to validate
        
    Returns:
        Validated timezone ID
        
    Raises:
        ValidationError: If timezone is not allowed
    """
    if not isinstance(timezone_id, str):
        raise ValidationError(f"Timezone must be a string, got {type(timezone_id)}")
    
    if not timezone_id or timezone_id == "N/A":
        return "UTC"  # Default fallback
    
    if timezone_id not in ALLOWED_TIMEZONES:
        logger.warning(f"Unknown timezone '{timezone_id}', falling back to UTC")
        return "UTC"
    
    return timezone_id

def validate_hours_string(hours_string: str) -> str:
    """
    Validate trading hours string format
    
    Args:
        hours_string: Trading hours string to validate
        
    Returns:
        Validated hours string
        
    Raises:
        ValidationError: If format is invalid
    """
    if not isinstance(hours_string, str):
        raise ValidationError(f"Hours string must be a string, got {type(hours_string)}")
    
    if not hours_string or hours_string == "N/A":
        return ""
    
    # Basic format validation - handle both same-day and cross-date patterns
    # Same-day: YYYYMMDD:HHMM-HHMM  Cross-date: YYYYMMDD:HHMM-YYYYMMDD:HHMM
    pattern = r'^(\d{8}:(CLOSED|(\d{4}-\d{4}|\d{4}-\d{8}:\d{4})(,(\d{4}-\d{4}|\d{4}-\d{8}:\d{4}))*);?)+$'
    if not re.match(pattern, hours_string.replace(' ', '')):
        logger.warning(f"Trading hours string may have invalid format: {hours_string}")
    
    return hours_string

class MarketStatus(Enum):
    """Market status enumeration"""
    OPEN = "open"
    CLOSED = "closed" 
    PRE_MARKET = "pre_market"
    AFTER_HOURS = "after_hours"
    UNKNOWN = "unknown"

@dataclass
class TradingSession:
    """Single trading session within a day"""
    date: str          # YYYYMMDD format
    start_time: str    # HHMM format
    end_time: str      # HHMM format
    is_closed: bool = False

@dataclass
class MarketStatusResult:
    """Result of market status check"""
    contract_id: int
    is_trading: bool
    is_liquid: bool
    market_status: MarketStatus
    next_open: Optional[datetime] = None
    next_close: Optional[datetime] = None
    time_zone: str = "UTC"
    current_time: datetime = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses"""
        return {
            "contract_id": self.contract_id,
            "is_trading": self.is_trading,
            "is_liquid": self.is_liquid,
            "market_status": self.market_status.value,
            "next_open": self.next_open.isoformat() if self.next_open else None,
            "next_close": self.next_close.isoformat() if self.next_close else None,
            "time_zone": self.time_zone,
            "current_time": self.current_time.isoformat() if self.current_time else None
        }

class TradingHoursParser:
    """Parse IB API trading hours format and determine market status"""
    
    @staticmethod
    def parse_hours_string(hours_string: str) -> List[TradingSession]:
        """
        Parse IB trading hours format
        
        Format: "YYYYMMDD:HHMM-HHMM,HHMM-HHMM;YYYYMMDD:CLOSED"
        Example: "20090507:0700-1830,1830-2330;20090508:CLOSED"
        
        Args:
            hours_string: IB trading hours string
            
        Returns:
            List of TradingSession objects
        """
        if not hours_string or hours_string == "N/A":
            return []
        
        sessions = []
        
        try:
            # Split by semicolon for different dates
            date_segments = hours_string.split(';')
            
            for segment in date_segments:
                if ':' not in segment:
                    continue
                    
                date_part, time_part = segment.split(':', 1)
                
                if time_part.upper() == 'CLOSED':
                    sessions.append(TradingSession(
                        date=date_part,
                        start_time="",
                        end_time="",
                        is_closed=True
                    ))
                else:
                    # Split by comma for multiple sessions in same day
                    time_ranges = time_part.split(',')
                    
                    for time_range in time_ranges:
                        if '-' in time_range:
                            start_part, end_part = time_range.split('-', 1)
                            
                            # Handle cross-date sessions (e.g., "1700-20250811:1600")
                            if ':' in end_part:
                                # Cross-date session: end_part contains date:time
                                end_date_time = end_part.split(':', 1)
                                if len(end_date_time) == 2:
                                    end_date, end_time = end_date_time
                                    sessions.append(TradingSession(
                                        date=date_part,
                                        start_time=start_part.strip(),
                                        end_time=f"{end_date}:{end_time.strip()}",  # Keep cross-date format
                                        is_closed=False
                                    ))
                                else:
                                    # Malformed cross-date, treat as same day
                                    sessions.append(TradingSession(
                                        date=date_part,
                                        start_time=start_part.strip(),
                                        end_time=end_part.strip(),
                                        is_closed=False
                                    ))
                            else:
                                # Same-day session
                                sessions.append(TradingSession(
                                    date=date_part,
                                    start_time=start_part.strip(),
                                    end_time=end_part.strip(),
                                    is_closed=False
                                ))
                        
        except Exception as e:
            logger.warning(f"Failed to parse trading hours string '{hours_string}': {e}")
            
        return sessions
    
    @staticmethod
    def _parse_date_time(date_str: str, time_str: str, time_zone_id: str) -> Optional[datetime]:
        """
        Parse IB date and time into timezone-aware datetime
        
        Args:
            date_str: YYYYMMDD format
            time_str: HHMM format or YYYYMMDD:HHMM format (for cross-date sessions)
            time_zone_id: Timezone identifier (e.g., "US/Eastern")
            
        Returns:
            Timezone-aware datetime or None if parsing fails
        """
        try:
            # Validate and handle timezone securely
            validated_tz_id = validate_timezone(time_zone_id)
            
            try:
                import pytz
                tz = pytz.timezone(validated_tz_id)
            except ImportError:
                logger.warning("pytz not available, using UTC for timezone calculations")
                tz = timezone.utc
            except Exception as e:
                logger.warning(f"Failed to parse validated timezone '{validated_tz_id}': {e}")
                tz = timezone.utc
            
            # Handle cross-date format (YYYYMMDD:HHMM)
            if ':' in time_str:
                cross_date_parts = time_str.split(':', 1)
                if len(cross_date_parts) == 2:
                    actual_date_str, actual_time_str = cross_date_parts
                else:
                    # Fallback if malformed
                    actual_date_str, actual_time_str = date_str, time_str.replace(':', '')
            else:
                actual_date_str, actual_time_str = date_str, time_str
            
            # Parse date: YYYYMMDD -> YYYY, MM, DD
            year = int(actual_date_str[:4])
            month = int(actual_date_str[4:6])
            day = int(actual_date_str[6:8])
            
            # Parse time: HHMM -> HH, MM
            hour = int(actual_time_str[:2])
            minute = int(actual_time_str[2:4])
            
            # Create timezone-aware datetime
            dt = tz.localize(datetime(year, month, day, hour, minute))
            return dt
            
        except Exception as e:
            logger.warning(f"Failed to parse date/time {date_str}:{time_str} in {time_zone_id}: {e}")
            return None
    
    @classmethod
    def is_market_open(cls, contract_id: int, trading_hours: str, 
                      liquid_hours: str, time_zone_id: str,
                      check_time: Optional[datetime] = None) -> MarketStatusResult:
        """
        Determine if market is currently open for trading
        
        Args:
            contract_id: Contract ID for reference
            trading_hours: IB trading hours string
            liquid_hours: IB liquid hours string  
            time_zone_id: Market timezone
            check_time: Time to check (defaults to now)
            
        Returns:
            MarketStatusResult with trading status
        """
        # Validate inputs
        contract_id = validate_contract_id(contract_id)
        trading_hours = validate_hours_string(trading_hours)
        liquid_hours = validate_hours_string(liquid_hours)
        time_zone_id = validate_timezone(time_zone_id)
        
        if check_time is None:
            check_time = datetime.now(timezone.utc)
        
        # Parse trading and liquid hours
        trading_sessions = cls.parse_hours_string(trading_hours)
        liquid_sessions = cls.parse_hours_string(liquid_hours)
        
        # Default result
        result = MarketStatusResult(
            contract_id=contract_id,
            is_trading=False,
            is_liquid=False,
            market_status=MarketStatus.UNKNOWN,
            time_zone=time_zone_id,
            current_time=check_time
        )
        
        if not trading_sessions:
            result.market_status = MarketStatus.UNKNOWN
            return result
        
        # Check current status against trading sessions
        current_trading = False
        current_liquid = False
        next_open = None
        next_close = None
        
        for session in trading_sessions:
            if session.is_closed:
                continue
                
            session_start = cls._parse_date_time(session.date, session.start_time, time_zone_id)
            session_end = cls._parse_date_time(session.date, session.end_time, time_zone_id)
            
            if session_start and session_end:
                # Convert to UTC for comparison
                session_start_utc = session_start.astimezone(timezone.utc)
                session_end_utc = session_end.astimezone(timezone.utc)
                
                # Check if currently in trading session
                if session_start_utc <= check_time <= session_end_utc:
                    current_trading = True
                    next_close = session_end_utc
                
                # Find next open/close times
                if session_start_utc > check_time:
                    if next_open is None or session_start_utc < next_open:
                        next_open = session_start_utc
                        
                if session_end_utc > check_time:
                    if next_close is None or session_end_utc < next_close:
                        next_close = session_end_utc
        
        # Check liquid hours similarly
        for session in liquid_sessions:
            if session.is_closed:
                continue
                
            session_start = cls._parse_date_time(session.date, session.start_time, time_zone_id)
            session_end = cls._parse_date_time(session.date, session.end_time, time_zone_id)
            
            if session_start and session_end:
                session_start_utc = session_start.astimezone(timezone.utc)
                session_end_utc = session_end.astimezone(timezone.utc)
                
                if session_start_utc <= check_time <= session_end_utc:
                    current_liquid = True
                    break
        
        # Determine market status
        if current_trading and current_liquid:
            market_status = MarketStatus.OPEN
        elif current_trading:
            market_status = MarketStatus.AFTER_HOURS  # Trading but low liquidity
        else:
            market_status = MarketStatus.CLOSED
        
        result.is_trading = current_trading
        result.is_liquid = current_liquid
        result.market_status = market_status
        result.next_open = next_open
        result.next_close = next_close
        
        return result
    
    @classmethod
    def get_trading_schedule(cls, trading_hours: str, liquid_hours: str, 
                           time_zone_id: str, days_ahead: int = 7) -> List[Dict]:
        """
        Get upcoming trading schedule
        
        Args:
            trading_hours: IB trading hours string
            liquid_hours: IB liquid hours string
            time_zone_id: Market timezone
            days_ahead: Number of days to look ahead
            
        Returns:
            List of trading schedule entries
        """
        trading_sessions = cls.parse_hours_string(trading_hours)
        liquid_sessions = cls.parse_hours_string(liquid_hours)
        
        schedule = []
        
        for session in trading_sessions:
            if session.is_closed:
                schedule.append({
                    "date": session.date,
                    "status": "closed",
                    "trading_start": None,
                    "trading_end": None,
                    "liquid_start": None,
                    "liquid_end": None
                })
            else:
                trading_start = cls._parse_date_time(session.date, session.start_time, time_zone_id)
                trading_end = cls._parse_date_time(session.date, session.end_time, time_zone_id)
                
                # Find corresponding liquid session
                liquid_start = None
                liquid_end = None
                
                for liquid_session in liquid_sessions:
                    if (liquid_session.date == session.date and 
                        not liquid_session.is_closed):
                        liquid_start = cls._parse_date_time(liquid_session.date, liquid_session.start_time, time_zone_id)
                        liquid_end = cls._parse_date_time(liquid_session.date, liquid_session.end_time, time_zone_id)
                        break
                
                schedule.append({
                    "date": session.date,
                    "status": "open",
                    "trading_start": trading_start.isoformat() if trading_start else None,
                    "trading_end": trading_end.isoformat() if trading_end else None,
                    "liquid_start": liquid_start.isoformat() if liquid_start else None,
                    "liquid_end": liquid_end.isoformat() if liquid_end else None,
                    "time_zone": time_zone_id
                })
        
        return schedule


# Convenience functions for API integration
def check_contract_market_status(contract_data: Dict, check_time: Optional[datetime] = None) -> MarketStatusResult:
    """
    Check market status for a contract using cached contract data
    
    Args:
        contract_data: Contract information from cache (must include trading hours)
        check_time: Time to check (defaults to now)
        
    Returns:
        MarketStatusResult
    """
    return TradingHoursParser.is_market_open(
        contract_id=contract_data.get("con_id", 0),
        trading_hours=contract_data.get("trading_hours", ""),
        liquid_hours=contract_data.get("liquid_hours", ""),
        time_zone_id=contract_data.get("time_zone_id", "UTC"),
        check_time=check_time
    )


def get_contract_trading_schedule(contract_data: Dict, days_ahead: int = 7) -> List[Dict]:
    """
    Get trading schedule for a contract using cached contract data
    
    Args:
        contract_data: Contract information from cache
        days_ahead: Number of days to look ahead
        
    Returns:
        List of trading schedule entries
    """
    return TradingHoursParser.get_trading_schedule(
        trading_hours=contract_data.get("trading_hours", ""),
        liquid_hours=contract_data.get("liquid_hours", ""),
        time_zone_id=contract_data.get("time_zone_id", "UTC"),
        days_ahead=days_ahead
    )