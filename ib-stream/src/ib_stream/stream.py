#!/usr/bin/env python3
"""
IB Stream CLI - Stream time & sales data from Interactive Brokers
"""

import argparse
import sys
import time

from .streaming_app import StreamingApp
from .utils import configure_logging, print_connection_error
from .config import create_config


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Stream time & sales data from Interactive Brokers TWS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Stream time & sales for Apple stock (using contract ID)
  ib-stream 265598

  # Stream only 20 ticks
  ib-stream 265598 --number 20

  # Stream bid/ask data instead of trades
  ib-stream 265598 --type BidAsk

  # Stream all trades including unreported
  ib-stream 265598 --type AllLast

  # Output as JSON for processing
  ib-stream 265598 --json

  # Combine options
  ib-stream 265598 --type BidAsk --number 50 --json

Tick Types:
  Last     - Regular trades during market hours (default)
  AllLast  - All trades including those outside regular hours
  BidAsk   - Bid and ask quotes
  MidPoint - Calculated midpoint between bid and ask

Notes:
  - Contract IDs can be found using the ib-contract lookup tool
  - Press Ctrl+C to stop streaming (when --number is not specified)
  - JSON output prints one JSON object per line for easy processing
        """,
    )

    parser.add_argument(
        "contract_id",
        type=int,
        help="Contract ID to stream (use ib-contract tool to find IDs)",
    )

    parser.add_argument(
        "--number",
        "-n",
        type=int,
        help="Number of ticks to stream before stopping (default: unlimited)",
    )

    parser.add_argument(
        "--type",
        "-t",
        choices=["Last", "AllLast", "BidAsk", "MidPoint"],
        default="Last",
        help="Type of tick data to stream (default: Last)",
    )

    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output data as JSON (one object per line)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--client-id",
        type=int,
        default=2,
        help="TWS client ID (default: 2, use different IDs for concurrent connections)",
    )

    return parser.parse_args()


def main():
    """Main entry point for the CLI."""
    args = parse_arguments()

    # Load configuration from environment
    try:
        config = create_config()
    except Exception as e:
        if not args.json:
            print(f"Configuration error: {e}")
        sys.exit(1)

    # Configure logging
    configure_logging(args.verbose)

    # Show header for non-JSON output
    if not args.json:
        print("IB Stream - Market Data Streamer")
        print("===============================")
        print(f"Contract ID: {args.contract_id}")
        print(f"Data Type: {args.type}")
        if args.number:
            print(f"Max Ticks: {args.number}")
        print(f"Connecting to TWS at {config.host}:{','.join(map(str, config.ports))}...")
        print()

    # Create streaming app with custom client ID if provided
    if args.client_id != 2:
        # Create custom config with override client ID
        from ib_util import ConnectionConfig
        custom_config = ConnectionConfig(
            host=config.host,
            ports=config.ports,
            client_id=args.client_id,
            connection_timeout=config.connection_timeout
        )
        app = StreamingApp(max_ticks=args.number, json_output=args.json, config=custom_config)
    else:
        app = StreamingApp(max_ticks=args.number, json_output=args.json)

    # Connect to TWS using the reliable connection handling
    if not app.connect_and_start():
        if not args.json:
            print_connection_error(host=config.host, ports=config.ports)
        sys.exit(1)

    try:
        # Start streaming
        app.stream_contract(args.contract_id, args.type)

        # Keep the program running
        while app.isConnected():
            time.sleep(1)

    except KeyboardInterrupt:
        # Handled by signal handler in StreamingApp
        pass
    except Exception as e:
        if not args.json:
            print(f"\nError: {e}")
        sys.exit(1)
    finally:
        if app.isConnected():
            app.disconnect()


if __name__ == "__main__":
    main()
