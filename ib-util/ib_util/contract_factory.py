"""
Contract factory functions for creating IB API Contract objects

This module provides standardized factory functions for creating Contract objects
for common use cases across ib-stream, ib-contract, and other IB services.
"""

try:
    from ibapi.contract import Contract
except ImportError:
    # Fallback for when ibapi is not available (testing, etc.)
    class Contract:
        def __init__(self):
            self.conId = 0
            self.symbol = ""
            self.secType = ""
            self.exchange = ""
            self.currency = ""
            self.lastTradeDateOrContractMonth = ""
            self.multiplier = ""
            self.tradingClass = ""
            self.localSymbol = ""
            self.strike = 0.0
            self.right = ""
            self.primaryExchange = ""


def create_contract_by_id(contract_id: int) -> Contract:
    """
    Create a contract using only the contract ID
    
    This is commonly used for streaming data when you already know the exact contract ID.
    
    Args:
        contract_id: The IB contract ID
        
    Returns:
        Contract object with conId set
    """
    contract = Contract()
    contract.conId = contract_id
    return contract


def create_stock_contract(
    symbol: str,
    exchange: str = "SMART",
    currency: str = "USD",
    primary_exchange: str = ""
) -> Contract:
    """
    Create a stock contract with standard defaults
    
    Args:
        symbol: Stock symbol (e.g., "AAPL", "MSFT")
        exchange: Exchange (default: "SMART" for best execution)
        currency: Currency (default: "USD")
        primary_exchange: Primary exchange if needed for disambiguation
        
    Returns:
        Stock Contract object
    """
    contract = Contract()
    contract.symbol = symbol.upper()
    contract.secType = "STK"
    contract.exchange = exchange
    contract.currency = currency.upper()
    if primary_exchange:
        contract.primaryExchange = primary_exchange
    return contract


def create_futures_contract(
    symbol: str,
    exchange: str = "CME",
    currency: str = "USD",
    expiry: str = ""
) -> Contract:
    """
    Create a futures contract with standard defaults
    
    Args:
        symbol: Futures symbol (e.g., "ES", "NQ", "YM")
        exchange: Exchange (default: "CME")
        currency: Currency (default: "USD")
        expiry: Contract expiry date (YYYYMM format)
        
    Returns:
        Futures Contract object
    """
    contract = Contract()
    contract.symbol = symbol.upper()
    contract.secType = "FUT"
    contract.exchange = exchange
    contract.currency = currency.upper()
    if expiry:
        contract.lastTradeDateOrContractMonth = expiry
    return contract


def create_option_contract(
    symbol: str,
    strike: float,
    right: str,
    expiry: str,
    exchange: str = "SMART",
    currency: str = "USD",
    multiplier: str = "100"
) -> Contract:
    """
    Create an option contract
    
    Args:
        symbol: Underlying symbol (e.g., "AAPL", "SPY")
        strike: Strike price
        right: "C" for call, "P" for put
        expiry: Expiry date (YYYYMMDD format)
        exchange: Exchange (default: "SMART")
        currency: Currency (default: "USD")
        multiplier: Option multiplier (default: "100")
        
    Returns:
        Option Contract object
    """
    contract = Contract()
    contract.symbol = symbol.upper()
    contract.secType = "OPT"
    contract.exchange = exchange
    contract.currency = currency.upper()
    contract.strike = float(strike)
    contract.right = right.upper()
    contract.lastTradeDateOrContractMonth = expiry
    contract.multiplier = str(multiplier)
    return contract


def create_forex_contract(
    symbol: str,
    exchange: str = "IDEALPRO",
    currency: str = "USD"
) -> Contract:
    """
    Create a forex contract
    
    Args:
        symbol: Currency pair symbol (e.g., "EUR", "GBP", "JPY")
        exchange: Exchange (default: "IDEALPRO")
        currency: Base currency (default: "USD")
        
    Returns:
        Forex Contract object
    """
    contract = Contract()
    contract.symbol = symbol.upper()
    contract.secType = "CASH"
    contract.exchange = exchange
    contract.currency = currency.upper()
    return contract


def create_index_contract(
    symbol: str,
    exchange: str = "CME",
    currency: str = "USD"
) -> Contract:
    """
    Create an index contract
    
    Args:
        symbol: Index symbol (e.g., "SPX", "VIX")
        exchange: Exchange (default: "CME")
        currency: Currency (default: "USD")
        
    Returns:
        Index Contract object
    """
    contract = Contract()
    contract.symbol = symbol.upper()
    contract.secType = "IND"
    contract.exchange = exchange
    contract.currency = currency.upper()
    return contract


def create_contract_for_lookup(
    symbol: str,
    sec_type: str,
    exchange: str = "",
    currency: str = ""
) -> Contract:
    """
    Create a contract for contract lookup/search operations
    
    This function applies appropriate defaults based on security type for lookup operations.
    
    Args:
        symbol: Symbol to search for
        sec_type: Security type ("STK", "FUT", "OPT", "CASH", "IND", etc.)
        exchange: Exchange (will apply defaults if empty)
        currency: Currency (will apply defaults if empty)
        
    Returns:
        Contract object configured for lookup
    """
    contract = Contract()
    contract.symbol = symbol.upper()
    contract.secType = sec_type.upper()
    
    # Apply defaults based on security type if not specified
    if not exchange or not currency:
        defaults = _get_lookup_defaults(sec_type)
        contract.exchange = exchange or defaults["exchange"]
        contract.currency = (currency or defaults["currency"]).upper()
    else:
        contract.exchange = exchange
        contract.currency = currency.upper()
    
    return contract


def _get_lookup_defaults(sec_type: str) -> dict:
    """Get default exchange and currency for contract lookup by security type"""
    defaults = {
        "STK": {"exchange": "SMART", "currency": "USD"},
        "FUT": {"exchange": "CME", "currency": "USD"},
        "OPT": {"exchange": "SMART", "currency": "USD"},
        "CASH": {"exchange": "IDEALPRO", "currency": "USD"},
        "IND": {"exchange": "CME", "currency": "USD"},
        "CFD": {"exchange": "SMART", "currency": "USD"},
        "BOND": {"exchange": "SMART", "currency": "USD"},
        "FUND": {"exchange": "FUNDSERV", "currency": "USD"},
        "CMDTY": {"exchange": "NYMEX", "currency": "USD"},
    }
    return defaults.get(sec_type.upper(), {"exchange": "", "currency": "USD"})


def validate_contract(contract: Contract) -> list:
    """
    Validate a contract object and return any validation errors
    
    Args:
        contract: Contract object to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if not contract.symbol and contract.conId <= 0:
        errors.append("Contract must have either symbol or valid conId")
    
    if not contract.secType:
        errors.append("Security type (secType) is required")
    
    if contract.secType == "OPT":
        if not contract.right:
            errors.append("Option right (C/P) is required for options")
        if contract.strike <= 0:
            errors.append("Strike price is required for options")
        if not contract.lastTradeDateOrContractMonth:
            errors.append("Expiry date is required for options")
    
    if contract.secType == "FUT" and not contract.lastTradeDateOrContractMonth:
        errors.append("Expiry date is typically required for futures")
    
    return errors


# Common contract factory shortcuts
def aapl_stock() -> Contract:
    """Create AAPL stock contract"""
    return create_stock_contract("AAPL")


def es_future(expiry: str = "") -> Contract:
    """Create E-mini S&P 500 futures contract"""
    return create_futures_contract("ES", expiry=expiry)


def spy_option(strike: float, right: str, expiry: str) -> Contract:
    """Create SPY option contract"""
    return create_option_contract("SPY", strike, right, expiry)


def eur_usd_forex() -> Contract:
    """Create EUR/USD forex contract"""
    return create_forex_contract("EUR")


def spx_index() -> Contract:
    """Create S&P 500 index contract"""
    return create_index_contract("SPX")