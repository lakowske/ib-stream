#!/usr/bin/env python3
"""
Test script to extract trading hours information from IB API
This script demonstrates how to get tradingHours, liquidHours, and timeZoneId
from the ContractDetails object for various contract types.
"""

import argparse
import json
import logging
import time
from datetime import datetime

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract

# Import shared utilities
from ib_util import IBConnection, connect_with_retry, configure_cli_logging, get_logger

configure_cli_logging(verbose=True)
logger = get_logger(__name__)


class TradingHoursApp(IBConnection):
    def __init__(self, config=None):
        if config is None:
            from ib_util import load_environment_config
            config = load_environment_config("contracts")
        
        super().__init__(config)
        self.contract_data = []
        self.req_id = 1000
        self.finished_requests = set()
        self.total_requests = 0

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
        logger.info("Found %s contract: %s", contract.secType, contract.symbol)

        # Extract comprehensive trading hours information
        trading_info = {
            # Basic contract information
            "symbol": contract.symbol,
            "sec_type": contract.secType,
            "exchange": contract.exchange,
            "primary_exchange": getattr(contract, "primaryExchange", ""),
            "currency": contract.currency,
            "con_id": contract.conId,
            "local_symbol": contract.localSymbol or "",
            "expiry": contract.lastTradeDateOrContractMonth or "",
            
            # Market information from ContractDetails
            "market_name": getattr(contractDetails, "marketName", ""),
            "long_name": getattr(contractDetails, "longName", ""),
            
            # Trading hours information - THE KEY DATA WE'RE AFTER
            "time_zone_id": getattr(contractDetails, "timeZoneId", ""),
            "trading_hours": getattr(contractDetails, "tradingHours", ""),
            "liquid_hours": getattr(contractDetails, "liquidHours", ""),
            
            # Additional useful information
            "min_tick": getattr(contractDetails, "minTick", 0),
            "price_magnifier": getattr(contractDetails, "priceMagnifier", 0),
            "multiplier": contract.multiplier or "",
            "trading_class": contract.tradingClass or "",
            
            # Timestamp for when this data was retrieved
            "retrieved_at": datetime.now().isoformat(),
        }
        
        self.contract_data.append(trading_info)
        
        # Log the trading hours information
        logger.info("Trading hours data for %s:", contract.symbol)
        logger.info("  Time Zone: %s", trading_info['time_zone_id'])
        logger.info("  Trading Hours: %s", trading_info['trading_hours'])
        logger.info("  Liquid Hours: %s", trading_info['liquid_hours'])

    def contractDetailsEnd(self, reqId):
        """Called when all contract details have been received"""
        logger.info("Contract details request %d completed", reqId)
        self.finished_requests.add(reqId)

    def request_contract_details(self, contracts):
        """Request contract details for the given contracts"""
        self.total_requests = len(contracts)
        
        for contract in contracts:
            logger.info("Requesting contract details for %s (%s)...", contract.symbol, contract.secType)
            self.reqContractDetails(self.req_id, contract)
            self.req_id += 1

    def is_finished(self):
        """Check if all requests are completed"""
        return len(self.finished_requests) >= self.total_requests

    def display_results(self):
        """Display all trading hours data"""
        if not self.contract_data:
            print("No trading hours data collected.")
            return

        print("\n" + "=" * 120)
        print("Trading Hours Information for {} contracts".format(len(self.contract_data)))
        print("=" * 120)

        for data in self.contract_data:
            print("\n" + "-" * 80)
            print("Contract: {} ({}) - {}".format(data['symbol'], data['sec_type'], data['market_name']))
            print("Contract ID: {}".format(data['con_id']))
            print("Exchange: {}".format(data['exchange']))
            if data['primary_exchange']:
                print("Primary Exchange: {}".format(data['primary_exchange']))
            print("Currency: {}".format(data['currency']))
            
            print("\nTRADING HOURS INFORMATION:")
            print("  Time Zone ID: {}".format(data['time_zone_id']))
            print("  Trading Hours: {}".format(data['trading_hours']))
            print("  Liquid Hours:  {}".format(data['liquid_hours']))
            
            print("\nAdditional Details:")
            print("  Min Tick: {}".format(data['min_tick']))
            if data['multiplier']:
                print("  Multiplier: {}".format(data['multiplier']))
            if data['expiry']:
                print("  Expiry: {}".format(data['expiry']))

    def save_to_json(self, filename):
        """Save results to JSON file"""
        output_data = {
            "metadata": {
                "retrieved_at": datetime.now().isoformat(),
                "total_contracts": len(self.contract_data),
                "description": "Trading hours information from IB API ContractDetails"
            },
            "contracts": self.contract_data
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print("\nData saved to {}".format(filename))


def create_test_contracts():
    """Create a set of test contracts to examine trading hours for"""
    contracts = []
    
    # Stock - AAPL
    stock = Contract()
    stock.symbol = "AAPL"
    stock.secType = "STK"
    stock.exchange = "SMART"
    stock.currency = "USD"
    contracts.append(stock)
    
    # Future - MNQ (Micro E-mini NASDAQ)
    future = Contract()
    future.symbol = "MNQ"
    future.secType = "FUT"
    future.exchange = "CME"
    future.currency = "USD"
    # Let's use the current front month
    future.lastTradeDateOrContractMonth = "202503"  # March 2025
    contracts.append(future)
    
    # Forex - EUR/USD
    forex = Contract()
    forex.symbol = "EUR"
    forex.secType = "CASH"
    forex.exchange = "IDEALPRO"
    forex.currency = "USD"
    contracts.append(forex)
    
    # Index - SPX
    index = Contract()
    index.symbol = "SPX"
    index.secType = "IND"
    index.exchange = "CBOE"
    index.currency = "USD"
    contracts.append(index)
    
    return contracts


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Extract trading hours information from IB API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script demonstrates how to get tradingHours, liquidHours, and timeZoneId
from the ContractDetails object. It tests with common contract types:
- Stocks (AAPL)
- Futures (MNQ)
- Forex (EUR/USD)
- Indices (SPX)

The trading hours data will show the format IB uses for scheduling information.
        """
    )
    
    parser.add_argument(
        "--output", "-o",
        help="Save results to JSON file",
        default="trading_hours_data.json"
    )
    
    args = parser.parse_args()
    
    print("Trading Hours Information Extractor")
    print("===================================")
    print("This script will extract trading hours from IB API ContractDetails")
    print("Make sure TWS or IB Gateway is running with API connections enabled.")
    print()

    # Connect to TWS
    app = TradingHoursApp()
    if not app.connect_and_start():
        print("Failed to connect to TWS. Please check:")
        print("1. TWS or IB Gateway is running")
        print("2. API connections are enabled")
        print("3. Connection parameters are correct")
        return

    try:
        # Create test contracts
        contracts = create_test_contracts()
        
        # Request contract details
        app.request_contract_details(contracts)

        # Wait for data to be received
        timeout = 30  # 30 second timeout
        start_time = time.time()

        while not app.is_finished() and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        if not app.is_finished():
            print("Timeout waiting for contract data")
            return

        # Display and save results
        app.display_results()
        app.save_to_json(args.output)

    except Exception as e:
        logger.error("An error occurred: %s", e)

    finally:
        # Clean up
        if app.isConnected():
            app.disconnect()


if __name__ == "__main__":
    main()