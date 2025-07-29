"""
Test contract fixtures for ib-stream BDD tests.
Provides common contract data for testing.
"""

# Known test contracts with expected properties
TEST_CONTRACTS = {
    "AAPL": {
        "symbol": "AAPL",
        "sec_type": "STK",
        "expected_exchange": "SMART",
        "expected_currency": "USD",
        "expected_primary_exchange": "ISLAND",
        "description": "Apple Inc. stock",
    },
    "SPY": {
        "symbol": "SPY",
        "sec_type": "STK", 
        "expected_exchange": "SMART",
        "expected_currency": "USD",
        "expected_primary_exchange": "ARCA",
        "description": "SPDR S&P 500 ETF",
    },
    "MNQ": {
        "symbol": "MNQ",
        "sec_type": "FUT",
        "expected_exchange": "CME",
        "expected_currency": "USD",
        "description": "E-mini NASDAQ-100 Future",
        "has_expiry": True,
        "has_multiplier": True,
    },
    "EUR": {
        "symbol": "EUR",
        "sec_type": "CASH",
        "expected_exchange": "IDEALPRO",
        "expected_currency": "USD",
        "description": "EUR/USD Forex",
    },
}

# Invalid contracts for error testing
INVALID_CONTRACTS = {
    "INVALID123": {
        "symbol": "INVALID123",
        "description": "Non-existent symbol for testing error handling",
    },
    "BADTYPE": {
        "symbol": "AAPL",
        "sec_type": "INVALID",
        "description": "Valid symbol with invalid security type",
    },
}

# Expected tick types for streaming tests
SUPPORTED_TICK_TYPES = ["last", "all_last", "bid_ask", "mid_point"]

# Expected security types for contract lookup
SUPPORTED_SECURITY_TYPES = ["STK", "FUT", "OPT", "CASH", "IND", "CFD", "BOND", "FUND", "CMDTY"]

def get_test_contract(symbol):
    """Get test contract data by symbol"""
    return TEST_CONTRACTS.get(symbol.upper())

def get_invalid_contract(symbol):
    """Get invalid contract data by symbol"""
    return INVALID_CONTRACTS.get(symbol.upper())

def is_valid_tick_type(tick_type):
    """Check if tick type is supported"""
    return tick_type in SUPPORTED_TICK_TYPES

def is_valid_security_type(sec_type):
    """Check if security type is supported"""
    return sec_type.upper() in SUPPORTED_SECURITY_TYPES