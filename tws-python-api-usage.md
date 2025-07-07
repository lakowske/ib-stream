# TWS Python API Usage Guide

## Overview

This guide covers how to use the Interactive Brokers TWS (Trader Workstation) Python API for building trading applications. The API provides programmatic access to IB's trading platform, allowing you to place orders, request market data, manage positions, and more.

## API Structure

The TWS Python API is located in `twsapi_macunix.1030.01/IBJts/source/pythonclient/` and consists of:

- **Core API Package (`ibapi/`)**: The main library with client and wrapper classes
- **Examples (`samples/Python/Testbed/`)**: Working examples demonstrating API usage
- **Tests (`tests/`)**: Unit tests and manual testing scripts

### Key Components

#### 1. EClient Class (`ibapi/client.py`)
The main interface for sending requests to TWS:
- Market data requests
- Order placement and management  
- Account information requests
- Contract details lookup

#### 2. EWrapper Class (`ibapi/wrapper.py`)
Handles responses and callbacks from TWS:
- Error handling
- Market data updates
- Order status notifications
- Account updates

#### 3. Data Classes
- `Contract`: Define financial instruments
- `Order`: Specify order parameters
- `Execution`: Trade execution details

## Installation and Setup

### Prerequisites

1. **TWS or IB Gateway** running and configured
2. **Python 3.1+** installed
3. **API connections enabled** in TWS/Gateway settings

### Install the Python API

```bash
cd twsapi_macunix.1030.01/IBJts/source/pythonclient
python setup.py sdist
python setup.py bdist_wheel
pip install --user --upgrade dist/ibapi-*.whl
```

### Configure TWS/Gateway

1. In TWS, go to **File → Global Configuration → API → Settings**
2. Check **Enable ActiveX and Socket Clients**
3. Add your IP address (127.0.0.1 for local) to **Trusted IPs**
4. Set the **Socket port** (default: 7496 for TWS, 4001 for Gateway)
5. Optionally check **Read-Only API** for market data only

## Basic Usage Pattern

### 1. Create Application Class

```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
import threading
import time

class TradingApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.nextOrderId = None
        self.data = {}
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        print(f"Error {errorCode}: {errorString}")
        
    def nextValidId(self, orderId):
        self.nextOrderId = orderId
        print(f"Next valid order ID: {orderId}")
        
    def tickPrice(self, reqId, tickType, price, attrib):
        print(f"Tick Price - ReqId: {reqId}, Type: {tickType}, Price: {price}")
        
    def tickSize(self, reqId, tickType, size):
        print(f"Tick Size - ReqId: {reqId}, Type: {tickType}, Size: {size}")
```

### 2. Connect and Run

```python
def main():
    app = TradingApp()
    
    # Connect to TWS
    app.connect("127.0.0.1", 7496, clientId=0)
    
    # Start the socket in a thread
    api_thread = threading.Thread(target=app.run, daemon=True)
    api_thread.start()
    
    # Wait for connection
    time.sleep(1)
    
    # Your trading logic here
    
    # Disconnect
    app.disconnect()

if __name__ == "__main__":
    main()
```

## Common Use Cases

### 1. Request Market Data

```python
def request_market_data(app):
    # Create contract for Apple stock
    contract = Contract()
    contract.symbol = "AAPL"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"
    
    # Request real-time market data
    app.reqMktData(
        reqId=1001,
        contract=contract,
        genericTickList="",
        snapshot=False,
        regulatorySnapshot=False,
        mktDataOptions=[]
    )
```

### 2. Place Orders

```python
def place_market_order(app):
    # Create contract
    contract = Contract()
    contract.symbol = "AAPL"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"
    
    # Create market order
    order = Order()
    order.action = "BUY"
    order.orderType = "MKT"
    order.totalQuantity = 100
    
    # Place order
    app.placeOrder(app.nextOrderId, contract, order)
    app.nextOrderId += 1
```

### 3. Request Account Information

```python
def request_account_summary(app):
    app.reqAccountSummary(
        reqId=9001,
        groupName="All",
        tags="NetLiquidation,TotalCashValue,SettledCash,AccruedCash,BuyingPower"
    )
    
def accountSummary(self, reqId, account, tag, value, currency):
    print(f"Account {account}: {tag} = {value} {currency}")
```

### 4. Request Positions

```python
def request_positions(app):
    app.reqPositions()
    
def position(self, account, contract, position, avgCost):
    print(f"Position: {contract.symbol} = {position} @ {avgCost}")
```

## Working with Contracts

### Stock Contract
```python
def create_stock_contract(symbol, exchange="SMART", currency="USD"):
    contract = Contract()
    contract.symbol = symbol
    contract.secType = "STK"
    contract.exchange = exchange
    contract.currency = currency
    return contract
```

### Option Contract
```python
def create_option_contract(symbol, expiry, strike, right, exchange="SMART"):
    contract = Contract()
    contract.symbol = symbol
    contract.secType = "OPT"
    contract.lastTradeDateOrContractMonth = expiry  # YYYYMMDD
    contract.strike = strike
    contract.right = right  # "C" or "P"
    contract.exchange = exchange
    contract.currency = "USD"
    return contract
```

### Forex Contract
```python
def create_forex_contract(symbol, currency="USD"):
    contract = Contract()
    contract.symbol = symbol  # e.g., "EUR"
    contract.secType = "CASH"
    contract.currency = currency
    contract.exchange = "IDEALPRO"
    return contract
```

## Order Types

### Market Order
```python
def create_market_order(action, quantity):
    order = Order()
    order.action = action  # "BUY" or "SELL"
    order.orderType = "MKT"
    order.totalQuantity = quantity
    return order
```

### Limit Order
```python
def create_limit_order(action, quantity, price):
    order = Order()
    order.action = action
    order.orderType = "LMT"
    order.totalQuantity = quantity
    order.lmtPrice = price
    return order
```

### Stop Loss Order
```python
def create_stop_order(action, quantity, stop_price):
    order = Order()
    order.action = action
    order.orderType = "STP"
    order.totalQuantity = quantity
    order.auxPrice = stop_price
    return order
```

## Running the Examples

### 1. Basic Connection Test

```bash
cd twsapi_macunix.1030.01/IBJts/source/pythonclient
python tests/manual.py
```

### 2. Full Testbed Application

```bash
cd twsapi_macunix.1030.01/IBJts/samples/Python/Testbed
python Program.py
```

This example demonstrates:
- Connection establishment
- Contract creation
- Order placement
- Market data requests
- Account information retrieval

### 3. Individual Sample Components

Explore specific functionality:
```bash
# Contract examples
python -c "from ContractSamples import *; print(EurGbpFx())"

# Order examples  
python -c "from OrderSamples import *; print(LimitOrder('BUY', 100, 150))"
```

## Error Handling and Debugging

### Common Connection Issues

1. **Connection Refused**: Check TWS/Gateway is running and API is enabled
2. **Authentication Failed**: Verify client ID and trusted IPs
3. **Socket Error**: Confirm port number (7496 for TWS, 4001 for Gateway)

### Error Codes

Key error codes to handle:
- **502**: Couldn't connect to TWS
- **504**: Not connected
- **2104**: Market data farm connection is OK
- **2106**: HMDS data farm connection is OK

### Logging

Enable detailed logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Best Practices

### 1. Connection Management
- Use separate client IDs for different applications
- Implement reconnection logic for production applications
- Handle connection state properly

### 2. Order Management
- Always check `nextValidId` before placing orders
- Implement proper error handling for order rejections
- Use unique request IDs for tracking

### 3. Market Data
- Cancel unnecessary market data subscriptions
- Respect IB's market data permissions and fees
- Handle data feed interruptions gracefully

### 4. Threading
- Run the API in a separate thread
- Use proper synchronization for shared data
- Implement clean shutdown procedures

## Packaging for Applications

### 1. Direct Installation
Install the API package globally:
```bash
pip install ibapi
```

### 2. Local Package
Include the API source in your project:
```
your_project/
├── ibapi/          # Copy from pythonclient/ibapi/
├── your_app.py
└── requirements.txt
```

### 3. Virtual Environment
```bash
python -m venv trading_env
source trading_env/bin/activate
pip install path/to/ibapi/wheel/file
```

### 4. Docker Container
```dockerfile
FROM python:3.9
COPY twsapi_macunix.1030.01/IBJts/source/pythonclient /app/pythonclient
WORKDIR /app/pythonclient
RUN pip install .
COPY your_app.py /app/
WORKDIR /app
CMD ["python", "your_app.py"]
```

## Resources

- **API Documentation**: Available in the TWS API installation
- **Sample Code**: `twsapi_macunix.1030.01/IBJts/samples/Python/Testbed/`
- **IB Knowledge Base**: Interactive Brokers website
- **Source Code**: `twsapi_macunix.1030.01/IBJts/source/pythonclient/`

## Version Information

This guide is based on TWS API version 10.30.1. Check the `API_VersionNum.txt` file for the exact version of your installation.