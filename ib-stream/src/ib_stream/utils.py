"""
Utilities for IB Stream - connection management and logging configuration
"""

import logging
import threading
import time

from ibapi.client import EClient


def configure_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    else:
        # Suppress all TWS API noise in non-verbose mode
        logging.basicConfig(
            level=logging.CRITICAL,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        logging.getLogger("ibapi").setLevel(logging.CRITICAL)
        logging.getLogger().setLevel(logging.CRITICAL)


def connect_to_tws(app: EClient, client_id: int = 2) -> bool:
    """
    Try to connect to TWS/Gateway on various ports.

    Args:
        app: The EClient instance to connect
        client_id: Client ID for the connection

    Returns:
        bool: True if connected successfully, False otherwise
    """
    host = "127.0.0.1"
    # Try different ports: Paper TWS, Live TWS, Paper Gateway, Live Gateway
    ports_to_try = [7497, 7496, 4002, 4001]

    for port in ports_to_try:
        try:
            app.connect(host, port, client_id)

            # Start the socket in a thread
            api_thread = threading.Thread(target=app.run, daemon=True)
            api_thread.start()

            # Wait for connection with shorter polling
            for _ in range(20):  # Wait up to 2 seconds (20 * 0.1)
                time.sleep(0.1)
                if app.isConnected():
                    return True
            
            app.disconnect()

        except Exception:
            continue

    return False


def print_connection_error() -> None:
    """Print helpful error message when connection fails."""
    print("Failed to connect to TWS. Please check:")
    print("1. TWS or IB Gateway is running")
    print("2. API connections are enabled in TWS settings")
    print("3. The correct port is being used")
    print("   - Paper TWS: 7497")
    print("   - Live TWS: 7496")
    print("   - Paper Gateway: 4002")
    print("   - Live Gateway: 4001")


def format_timestamp(unix_timestamp: int) -> str:
    """Format Unix timestamp to readable string."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(unix_timestamp))
