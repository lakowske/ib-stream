"""Timezone utilities for displaying timestamps in human-readable format."""

import zoneinfo
from datetime import datetime, timezone
from typing import Optional


def get_display_timezone(display_timezone: Optional[str] = None):
    """
    Get the timezone to use for displaying timestamps.

    Args:
        display_timezone: Timezone name (e.g., "US/Eastern", "Europe/London", "UTC")
                         If None, uses system local timezone

    Returns:
        timezone object for displaying timestamps
    """
    if display_timezone is None:
        # Use system local timezone
        return datetime.now().astimezone().tzinfo

    try:
        # Handle common timezone name aliases
        timezone_map = {
            "US/Eastern": "America/New_York",
            "US/Central": "America/Chicago",
            "US/Mountain": "America/Denver",
            "US/Pacific": "America/Los_Angeles",
        }

        # Try to parse the timezone name
        if display_timezone.upper() == "UTC":
            return timezone.utc
        else:
            # Map common aliases to proper timezone names
            tz_name = timezone_map.get(display_timezone, display_timezone)
            return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        # Fall back to system local timezone if parsing fails
        return datetime.now().astimezone().tzinfo


def format_timestamp_for_display(timestamp: str, display_timezone: Optional[str] = None,
                                 format_str: str = "%H:%M:%S") -> str:
    """
    Format a UTC timestamp for display in the specified timezone.

    Args:
        timestamp: UTC timestamp string (e.g., "2025-07-09T16:30:51.893834Z")
        display_timezone: Timezone name for display (defaults to system local)
        format_str: strftime format string (default: "%H:%M:%S")

    Returns:
        Formatted timestamp string in the display timezone
    """
    if not timestamp:
        return datetime.now().strftime(format_str)

    try:
        # Parse the UTC timestamp
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

        # Convert to display timezone
        display_tz = get_display_timezone(display_timezone)
        local_dt = dt.astimezone(display_tz)

        # Format for display
        return local_dt.strftime(format_str)
    except ValueError:
        # Fallback for unparseable timestamps
        if len(timestamp) > 19:
            return timestamp[11:19]  # Extract HH:MM:SS portion
        elif len(timestamp) > 8:
            return timestamp[:8]     # First 8 chars
        else:
            return datetime.now().strftime(format_str)


def format_header_timestamp(display_timezone: Optional[str] = None,
                           format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format current time for header display in the specified timezone.

    Args:
        display_timezone: Timezone name for display (defaults to system local)
        format_str: strftime format string (default: "%Y-%m-%d %H:%M:%S")

    Returns:
        Formatted current timestamp string in the display timezone
    """
    display_tz = get_display_timezone(display_timezone)
    now = datetime.now(display_tz)
    return now.strftime(format_str)
