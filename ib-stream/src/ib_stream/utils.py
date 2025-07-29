"""
Utilities for IB Stream - logging configuration and error messages
"""

from ib_util import configure_cli_logging


def configure_logging(verbose: bool = False) -> None:
    """Configure logging for the application using ib-util standardized logging."""
    configure_cli_logging(verbose=verbose)




def print_connection_error(host: str = "127.0.0.1", ports: list = None) -> None:
    """Print helpful error message when connection fails."""
    ports = ports or [7497, 7496, 4002, 4001]
    print(f"Failed to connect to TWS/Gateway at {host}. Please check:")
    print("1. TWS or IB Gateway is running on the target host")
    print("2. API connections are enabled in TWS/Gateway settings")
    print("3. The correct host and ports are configured")
    print(f"4. Network connectivity to {host} on ports {ports}")
    print("   Default port mappings:")
    print("   - Paper TWS: 7497")
    print("   - Live TWS: 7496")
    print("   - Paper Gateway: 4002")
    print("   - Live Gateway: 4001")


def format_timestamp(unix_timestamp: int) -> str:
    """Format Unix timestamp to readable string using ib-util formatting."""
    from ib_util import format_timestamp as ib_format_timestamp
    return ib_format_timestamp(unix_timestamp)
