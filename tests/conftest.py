"""
Pytest configuration and fixtures for ib-stream BDD tests.
"""

import json
import logging
from pathlib import Path

import pytest
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_instance_config():
    """Load instance configuration to get actual service ports"""
    config_path = Path(__file__).parent.parent / "ib-stream" / "config" / "instance.env"
    config = {}
    
    if config_path.exists():
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key] = value
    
    return config

# Load configuration at module level
CONFIG = load_instance_config()

@pytest.fixture(scope="session")
def instance_config():
    """Fixture providing instance configuration"""
    return CONFIG

@pytest.fixture(scope="session") 
def stream_port():
    """Fixture providing streaming service port"""
    return int(CONFIG.get('IB_STREAM_PORT', '8247'))

@pytest.fixture(scope="session")
def contracts_port():
    """Fixture providing contracts service port"""
    return int(CONFIG.get('IB_CONTRACTS_PORT', '8257'))

@pytest.fixture(scope="session")
def stream_base_url(stream_port):
    """Fixture providing streaming service base URL"""
    return f"http://localhost:{stream_port}"

@pytest.fixture(scope="session")
def contracts_base_url(contracts_port):
    """Fixture providing contracts service base URL"""
    return f"http://localhost:{contracts_port}"

@pytest.fixture
def http_session():
    """Fixture providing a requests session with default timeout"""
    session = requests.Session()
    session.timeout = 30
    return session

@pytest.fixture(scope="session")
def test_contracts():
    """Fixture providing test contract data"""
    return {
        "aapl_stock": {
            "symbol": "AAPL",
            "sec_type": "STK",
            "expected_exchange": "SMART"
        },
        "spy_etf": {
            "symbol": "SPY", 
            "sec_type": "STK",
            "expected_exchange": "SMART"
        },
        "mnq_future": {
            "symbol": "MNQ",
            "sec_type": "FUT",
            "expected_exchange": "CME"
        },
        "eurusd_forex": {
            "symbol": "EUR",
            "sec_type": "CASH",
            "expected_exchange": "IDEALPRO"
        }
    }

@pytest.fixture
def aapl_contract_id(contracts_base_url, http_session):
    """Fixture providing AAPL contract ID for streaming tests"""
    url = f"{contracts_base_url}/lookup/AAPL/STK"
    response = http_session.get(url)
    
    if response.status_code != 200:
        pytest.skip(f"Cannot get AAPL contract ID: {response.status_code}")
    
    data = response.json()
    if data.get("total_contracts", 0) == 0:
        pytest.skip("No AAPL contracts found")
    
    contract_id = data["contracts_by_type"]["STK"]["contracts"][0]["con_id"]
    logger.info(f"Using AAPL contract ID: {contract_id}")
    return contract_id

def pytest_configure(config):
    """Pytest configuration hook"""
    logger.info("Configuring ib-stream BDD tests")
    logger.info(f"Stream port: {CONFIG.get('IB_STREAM_PORT', 'unknown')}")
    logger.info(f"Contracts port: {CONFIG.get('IB_CONTRACTS_PORT', 'unknown')}")

def pytest_sessionstart(session):
    """Called after the Session object has been created"""
    logger.info("Starting ib-stream BDD test session")

def pytest_sessionfinish(session, exitstatus):
    """Called after whole test run finished, right before returning exit status"""
    logger.info(f"ib-stream BDD test session finished with exit status: {exitstatus}")