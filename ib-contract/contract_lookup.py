#!/usr/bin/env python3
"""
Contract Lookup Script
Retrieves and displays all available contracts for a given ticker symbol.
Can optionally filter by security type or show all types if none specified.
"""

import argparse
import json
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ibapi.client import EClient
from ibapi.wrapper import EWrapper

# Import shared utilities
from ib_util import IBConnection, connect_with_retry

# Configure logging using ib-util standardized logging
from ib_util import configure_cli_logging, get_logger

configure_cli_logging(verbose=False)
logger = get_logger(__name__)


class ContractLookupApp(IBConnection):
    def __init__(self, config=None):
        if config is None:
            from ib_util import load_environment_config
            config = load_environment_config("contracts")
        
        super().__init__(config)
        self.contracts = []
        self.req_id = 1000
        self.finished_requests = set()
        self.total_requests = 0
        self.ticker = None
        self.requested_types = []
        self.json_output = False

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        """Handle errors from TWS using standardized error handling"""
        from ib_util import handle_tws_error
        
        # Custom callback to handle contract lookup specific logic
        def contract_error_callback(req_id, error_code, error_msg):
            if error_code == 200:  # No security definition found
                self.finished_requests.add(req_id)
        
        handle_tws_error(reqId, errorCode, errorString, logger, contract_error_callback)

    def contractDetails(self, reqId, contractDetails):
        """Receive contract details from TWS"""
        contract = contractDetails.contract
        logger.info(
            f"Found {contract.secType} contract: {contract.symbol} {contract.lastTradeDateOrContractMonth or 'N/A'}"
        )

        # Store comprehensive contract information
        contract_info = {
            "symbol": contract.symbol,
            "sec_type": contract.secType,
            "exchange": contract.exchange,
            "primary_exchange": getattr(contract, "primaryExchange", "N/A"),
            "currency": contract.currency,
            "expiry": contract.lastTradeDateOrContractMonth or "N/A",
            "multiplier": contract.multiplier or "N/A",
            "trading_class": contract.tradingClass or "N/A",
            "con_id": contract.conId,
            "local_symbol": contract.localSymbol or "N/A",
            "strike": getattr(contract, "strike", "N/A"),
            "right": getattr(contract, "right", "N/A"),
            "min_tick": getattr(contractDetails, "minTick", "N/A"),
            "price_magnifier": getattr(contractDetails, "priceMagnifier", "N/A"),
            "market_name": getattr(contractDetails, "marketName", "N/A"),
            "long_name": getattr(contractDetails, "longName", "N/A"),
            "contract_month": getattr(contractDetails, "contractMonth", "N/A"),
            "industry": getattr(contractDetails, "industry", "N/A"),
            "category": getattr(contractDetails, "category", "N/A"),
            "subcategory": getattr(contractDetails, "subcategory", "N/A"),
        }
        self.contracts.append(contract_info)

    def contractDetailsEnd(self, reqId):
        """Called when all contract details have been received"""
        logger.info(f"Contract details request {reqId} completed")
        self.finished_requests.add(reqId)

    def request_contracts(self, ticker, sec_types=None):
        """Request contracts for the given ticker and security types"""
        self.ticker = ticker

        # Default security types to search if none specified
        if sec_types is None:
            sec_types = ["STK", "FUT", "OPT", "CASH", "IND", "CFD", "BOND", "FUND", "CMDTY"]

        self.requested_types = sec_types
        self.total_requests = len(sec_types)

        for sec_type in sec_types:
            logger.info(f"Requesting {sec_type} contracts for {ticker}...")

            # Create contract for lookup using ib-util factory
            from ib_util import create_contract_for_lookup
            contract = create_contract_for_lookup(ticker, sec_type)

            # Request contract details
            self.reqContractDetails(self.req_id, contract)
            self.req_id += 1

    def is_finished(self):
        """Check if all requests are completed"""
        return len(self.finished_requests) >= self.total_requests

    def display_contracts(self):
        """Display all found contracts grouped by security type"""
        if not self.contracts:
            if self.json_output:
                self._output_json(
                    {"ticker": self.ticker.upper(), "contracts_by_type": {}, "total_contracts": 0}
                )
            else:
                print(f"\nNo contracts found for ticker '{self.ticker}'.")
            return

        if self.json_output:
            self._output_json(self._prepare_json_data())
        else:
            print(f"\n{'=' * 100}")
            print(f"Contract Lookup Results for '{self.ticker.upper()}'")
            print(f"{'=' * 100}")

        if not self.json_output:
            # Group contracts by security type
            contracts_by_type = defaultdict(list)
            for contract in self.contracts:
                contracts_by_type[contract["sec_type"]].append(contract)

            total_contracts = 0

            for sec_type in sorted(contracts_by_type.keys()):
                contracts_list = contracts_by_type[sec_type]
                total_contracts += len(contracts_list)

                print(f"\n{sec_type} Contracts ({len(contracts_list)} found):")
                print("-" * 50)

                if sec_type == "STK":
                    self._display_stock_contracts(contracts_list)
                elif sec_type == "FUT":
                    self._display_futures_contracts(contracts_list)
                elif sec_type == "OPT":
                    self._display_options_contracts(contracts_list)
                elif sec_type == "CASH":
                    self._display_forex_contracts(contracts_list)
                else:
                    self._display_generic_contracts(contracts_list)

            print(f"\n{'=' * 100}")
            print(f"Total contracts found: {total_contracts}")
            print(f"Security types searched: {', '.join(self.requested_types)}")
            print(f"Retrieved at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def _display_stock_contracts(self, contracts):
        """Display stock contracts with comprehensive details"""
        print(
            f"{'Symbol':<8} {'Contract ID':<12} {'Exchange':<12} {'Primary':<10} {'Currency':<8} {'Long Name':<30}"
        )
        print("-" * 85)
        for contract in sorted(contracts, key=lambda x: x["exchange"]):
            long_name = (
                str(contract["long_name"])[:28] + ".."
                if len(str(contract["long_name"])) > 30
                else str(contract["long_name"])
            )
            print(
                f"{contract['symbol']:<8} "
                f"{contract['con_id']:<12} "
                f"{contract['exchange']:<12} "
                f"{str(contract['primary_exchange']):<10} "
                f"{contract['currency']:<8} "
                f"{long_name:<30}"
            )

        if contracts:
            print("\nAdditional Details:")
            for i, contract in enumerate(contracts[:3]):  # Show details for first 3
                print(
                    f"  [{i + 1}] {contract['symbol']} - Market: {contract['market_name']}, "
                    f"Industry: {contract['industry']}, Category: {contract['category']}"
                )

    def _display_futures_contracts(self, contracts):
        """Display futures contracts with comprehensive details"""
        print(
            f"{'Symbol':<8} {'Contract ID':<12} {'Expiry':<10} {'Exchange':<8} {'Currency':<8} {'Multiplier':<10} {'Min Tick':<10} {'Local Symbol':<15}"
        )
        print("-" * 95)
        for contract in sorted(contracts, key=lambda x: x["expiry"]):
            print(
                f"{contract['symbol']:<8} "
                f"{contract['con_id']:<12} "
                f"{contract['expiry']:<10} "
                f"{contract['exchange']:<8} "
                f"{contract['currency']:<8} "
                f"{str(contract['multiplier']):<10} "
                f"{str(contract['min_tick']):<10} "
                f"{contract['local_symbol']:<15}"
            )

        if contracts:
            print("\nContract Details:")
            for contract in contracts:
                print(
                    f"  {contract['symbol']} {contract['expiry']}: Market {contract['market_name']}, "
                    f"Contract Month {contract['contract_month']}, Trading Class {contract['trading_class']}"
                )

    def _display_options_contracts(self, contracts):
        """Display options contracts with comprehensive details (limited due to volume)"""
        print(
            f"{'Symbol':<8} {'Contract ID':<12} {'Expiry':<10} {'Strike':<10} {'Right':<5} {'Exchange':<8} {'Currency':<8} {'Multiplier':<10}"
        )
        print("-" * 85)

        # Sort by expiry, then strike
        sorted_contracts = sorted(
            contracts,
            key=lambda x: (
                x["expiry"],
                float(x["strike"])
                if str(x["strike"]).replace(".", "").replace("-", "").isdigit()
                else 0,
            ),
        )

        # Limit display to prevent overwhelming output
        display_count = min(15, len(sorted_contracts))
        for contract in sorted_contracts[:display_count]:
            print(
                f"{contract['symbol']:<8} "
                f"{contract['con_id']:<12} "
                f"{contract['expiry']:<10} "
                f"{str(contract['strike']):<10} "
                f"{contract['right']:<5} "
                f"{contract['exchange']:<8} "
                f"{contract['currency']:<8} "
                f"{str(contract['multiplier']):<10}"
            )

        if len(sorted_contracts) > display_count:
            print(f"\n... and {len(sorted_contracts) - display_count} more options contracts")
            print(
                f"Expiry range: {sorted_contracts[0]['expiry']} to {sorted_contracts[-1]['expiry']}"
            )
            strikes = [
                float(c["strike"])
                for c in sorted_contracts
                if str(c["strike"]).replace(".", "").replace("-", "").isdigit()
            ]
            if strikes:
                print(f"Strike range: ${min(strikes):.2f} to ${max(strikes):.2f}")

    def _display_forex_contracts(self, contracts):
        """Display forex contracts with comprehensive details"""
        print(
            f"{'Symbol':<8} {'Contract ID':<12} {'Currency':<8} {'Exchange':<15} {'Min Tick':<10} {'Local Symbol':<15}"
        )
        print("-" * 80)
        for contract in sorted(contracts, key=lambda x: x["currency"]):
            print(
                f"{contract['symbol']:<8} "
                f"{contract['con_id']:<12} "
                f"{contract['currency']:<8} "
                f"{contract['exchange']:<15} "
                f"{str(contract['min_tick']):<10} "
                f"{contract['local_symbol']:<15}"
            )

        if contracts:
            print("\nForex Details:")
            for contract in contracts:
                print(
                    f"  {contract['symbol']}/{contract['currency']}: Market {contract['market_name']}, "
                    f"Price Magnifier {contract['price_magnifier']}"
                )

    def _display_generic_contracts(self, contracts):
        """Display other contract types with comprehensive details"""
        print(
            f"{'Symbol':<8} {'Contract ID':<12} {'Exchange':<12} {'Currency':<8} {'Trading Class':<15} {'Local Symbol':<15}"
        )
        print("-" * 85)
        for contract in sorted(contracts, key=lambda x: (x["exchange"], x["symbol"])):
            print(
                f"{contract['symbol']:<8} "
                f"{contract['con_id']:<12} "
                f"{contract['exchange']:<12} "
                f"{contract['currency']:<8} "
                f"{str(contract['trading_class']):<15} "
                f"{contract['local_symbol']:<15}"
            )

        if contracts:
            print("\nAdditional Information:")
            for contract in contracts:
                details = []
                if contract["market_name"] != "N/A":
                    details.append(f"Market: {contract['market_name']}")
                if contract["long_name"] != "N/A":
                    details.append(f"Name: {contract['long_name']}")
                if contract["min_tick"] != "N/A":
                    details.append(f"Min Tick: {contract['min_tick']}")
                if details:
                    print(f"  {contract['symbol']}: {', '.join(details)}")

    def _prepare_json_data(self):
        """Prepare contract data for JSON output using ib-util formatting"""
        from ib_util import create_contract_lookup_response
        response = create_contract_lookup_response(
            ticker=self.ticker,
            contracts=self.contracts,
            security_types_searched=self.requested_types
        )
        return response["data"]  # Extract just the data portion

    def _output_json(self, data):
        """Output data as formatted JSON using ib-util formatting"""
        from ib_util import format_json_response
        print(format_json_response(data, ensure_ascii=False))


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Look up contract details for a given ticker symbol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python contract_lookup.py AAPL              # All contract types for AAPL
  python contract_lookup.py AAPL --type STK   # Only stocks for AAPL
  python contract_lookup.py ES --type FUT     # Only futures for ES
  python contract_lookup.py EUR --type CASH   # Only forex for EUR
  python contract_lookup.py SPY --type OPT    # Only options for SPY
  python contract_lookup.py AAPL --json       # All contracts for AAPL in JSON format
  python contract_lookup.py AAPL -t STK -j    # Stock contracts for AAPL in JSON

Security Types:
  STK   - Stocks
  FUT   - Futures
  OPT   - Options
  CASH  - Forex/Currency
  IND   - Indices
  CFD   - Contracts for Difference
  BOND  - Bonds
  FUND  - Mutual Funds
  CMDTY - Commodities
        """,
    )

    parser.add_argument("ticker", help="Ticker symbol to look up (e.g., AAPL, MNQ, EUR)")

    parser.add_argument(
        "--type",
        "-t",
        choices=["STK", "FUT", "OPT", "CASH", "IND", "CFD", "BOND", "FUND", "CMDTY"],
        help="Security type to filter by (if not specified, searches all types)",
    )

    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output results in JSON format instead of formatted text",
    )

    return parser.parse_args()


def connect_to_tws():
    """Connect to TWS/Gateway and return the app instance"""
    # Create ContractLookupApp with built-in reliable connection
    app = ContractLookupApp()
    
    # Connect using the reliable connection handling
    if app.connect_and_start():
        return app
    else:
        print("Failed to connect to TWS. Please check:")
        print("1. TWS or IB Gateway is running")
        print("2. API connections are enabled")
        print("3. Connection parameters are correct")
        return None


def main():
    """Main function"""
    args = parse_arguments()

    # Only show header for non-JSON output
    if not args.json:
        print("Contract Lookup Tool")
        print("===================")
        print(f"Looking up contracts for ticker: {args.ticker.upper()}")
        if args.type:
            print(f"Security type filter: {args.type}")
        else:
            print("Security type filter: All types")
        print("Make sure TWS or IB Gateway is running with API connections enabled.")
        print()

    # Connect to TWS
    app = connect_to_tws()
    if not app:
        return

    try:
        # Set JSON output mode
        app.json_output = args.json

        # Request contracts
        sec_types = [args.type] if args.type else None
        app.request_contracts(args.ticker.upper(), sec_types)

        # Wait for data to be received
        timeout = 30  # 30 second timeout
        start_time = time.time()

        while not app.is_finished() and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        if not app.is_finished():
            print("Timeout waiting for contract data")
            return

        # Display results
        app.display_contracts()

    except Exception as e:
        logger.error(f"An error occurred: {e}")

    finally:
        # Clean up
        if app.isConnected():
            app.disconnect()
            # Disconnected - only log errors


if __name__ == "__main__":
    main()
