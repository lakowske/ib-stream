#!/usr/bin/env python3
"""
MNQ Functional Test - BDD-style workflow without pytest-bdd complexity.
Demonstrates: Contract lookup + Market data streaming for MNQ front month.
"""

import json
import logging
import time
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

# Load configuration
CONFIG = load_instance_config()
STREAM_PORT = int(CONFIG.get('IB_STREAM_PORT', '8247'))
CONTRACTS_PORT = int(CONFIG.get('IB_CONTRACTS_PORT', '8257'))

logger.info(f"Using stream port: {STREAM_PORT}, contracts port: {CONTRACTS_PORT}")

class TestMNQFunctional:
    """
    MNQ Functional Tests - BDD-style scenarios as test methods
    
    Scenario 1: Lookup MNQ front month contract
    Scenario 2: Stream market data for MNQ contract
    """
    
    def test_mnq_contract_lookup_scenario(self):
        """
        BDD Scenario: Lookup MNQ front month contract
        
        Given the contracts service is running
        When I lookup MNQ future contracts  
        Then I should get at least one contract
        And the contract should have a valid contract ID
        And the contract should be a future
        """
        logger.info("🎯 SCENARIO: Lookup MNQ front month contract")
        
        # Given the contracts service is running
        logger.info("GIVEN the contracts service is running")
        contracts_url = f"http://localhost:{CONTRACTS_PORT}"
        
        response = requests.get(f"{contracts_url}/health", timeout=10)
        assert response.status_code == 200, f"Contracts service not accessible: {response.status_code}"
        
        health_data = response.json()
        assert health_data["status"] == "healthy", f"Service not healthy: {health_data['status']}"
        assert health_data["tws_connected"] is True, "Service not connected to TWS"
        logger.info("✓ Contracts service is running and connected to TWS")
        
        # When I lookup MNQ future contracts
        logger.info("WHEN I lookup MNQ future contracts")
        lookup_url = f"{contracts_url}/lookup/MNQ/FUT"
        
        response = requests.get(lookup_url, timeout=30)
        assert response.status_code == 200, f"Contract lookup failed: {response.status_code}"
        
        lookup_data = response.json()
        logger.info(f"✓ MNQ lookup completed - Total contracts: {lookup_data['total_contracts']}")
        
        # Then I should get at least one contract
        logger.info("THEN I should get at least one contract")
        assert lookup_data["total_contracts"] > 0, f"Expected > 0 contracts, got {lookup_data['total_contracts']}"
        assert "FUT" in lookup_data["contracts_by_type"], "No FUT contracts found"
        
        fut_contracts = lookup_data["contracts_by_type"]["FUT"]["contracts"]
        assert len(fut_contracts) > 0, "No FUT contracts available"
        logger.info(f"✓ Found {len(fut_contracts)} FUT contracts")
        
        # And the contract should have a valid contract ID
        logger.info("AND the contract should have a valid contract ID")
        front_month = fut_contracts[0]  # Front month is usually first
        
        assert "con_id" in front_month, "Contract missing con_id"
        assert isinstance(front_month["con_id"], int), "Contract ID should be integer"
        assert front_month["con_id"] > 0, "Contract ID should be positive"
        logger.info(f"✓ Valid contract ID: {front_month['con_id']}")
        
        # And the contract should be a future
        logger.info("AND the contract should be a future")
        assert front_month["sec_type"] == "FUT", f"Expected FUT, got {front_month['sec_type']}"
        assert "expiry" in front_month, "Future should have expiry date"
        assert front_month["expiry"] != "N/A", "Future should have valid expiry"
        logger.info(f"✓ Confirmed future contract - Symbol: {front_month['symbol']}, Expiry: {front_month['expiry']}")
        
        # Store for next test
        self.mnq_contract_id = front_month["con_id"]
        self.mnq_contract = front_month
        
        logger.info("🎯 SCENARIO PASSED: MNQ contract lookup successful")

    def test_mnq_streaming_scenario(self):
        """
        BDD Scenario: Stream MNQ market data
        
        Given the streaming service is running
        And I have a valid MNQ contract ID
        When I start streaming market data for 5 seconds
        Then I should receive streaming response
        And the connection should be established
        """
        logger.info("🎯 SCENARIO: Stream MNQ market data")
        
        # Given the streaming service is running
        logger.info("GIVEN the streaming service is running")
        stream_url = f"http://localhost:{STREAM_PORT}"
        
        response = requests.get(f"{stream_url}/health", timeout=10)
        assert response.status_code == 200, f"Streaming service not accessible: {response.status_code}"
        
        health_data = response.json()
        assert health_data["status"] == "healthy", f"Service not healthy: {health_data['status']}"
        assert health_data["tws_connected"] is True, "Service not connected to TWS"
        logger.info("✓ Streaming service is running and connected to TWS")
        
        # And I have a valid MNQ contract ID
        logger.info("AND I have a valid MNQ contract ID")
        if not hasattr(self, 'mnq_contract_id'):
            # Get contract ID if not already available
            contracts_url = f"http://localhost:{CONTRACTS_PORT}"
            response = requests.get(f"{contracts_url}/lookup/MNQ/FUT", timeout=30)
            assert response.status_code == 200
            
            data = response.json()
            assert data["total_contracts"] > 0
            fut_contracts = data["contracts_by_type"]["FUT"]["contracts"]
            self.mnq_contract_id = fut_contracts[0]["con_id"]
        
        contract_id = self.mnq_contract_id
        logger.info(f"✓ Using MNQ contract ID: {contract_id}")
        
        # When I start streaming market data for 5 seconds
        logger.info("WHEN I start streaming market data for 5 seconds")
        streaming_url = f"{stream_url}/v2/stream/{contract_id}/live/last"
        
        logger.info(f"Connecting to streaming endpoint: {streaming_url}")
        
        # Test streaming connection (we'll test the connection, not necessarily data)
        start_time = time.time()
        stream_data = []
        connection_established = False
        
        try:
            response = requests.get(streaming_url, stream=True, timeout=10)
            connection_established = True
            logger.info(f"✓ Streaming connection established - Status: {response.status_code}")
            
            # Try to read some data for a few seconds
            for line in response.iter_lines(decode_unicode=True, chunk_size=1):
                if time.time() - start_time > 3:  # Stream for 3 seconds
                    break
                    
                if line:
                    logger.info(f"Received line: {line[:100]}...")  # Log first 100 chars
                    if line.startswith('data: '):
                        try:
                            data_json = line[6:]  # Remove 'data: ' prefix
                            if data_json.strip() and data_json != '{}':
                                data = json.loads(data_json)
                                stream_data.append(data)
                        except json.JSONDecodeError:
                            continue  # Skip non-JSON lines
                        
        except requests.exceptions.RequestException as e:
            logger.warning(f"Streaming request failed: {e}")
            # Continue with test - connection establishment is what we're testing
        
        duration = time.time() - start_time
        logger.info(f"✓ Streaming test completed - Duration: {duration:.2f}s, Data points: {len(stream_data)}")
        
        # Then I should receive streaming response
        logger.info("THEN I should receive streaming response")
        assert connection_established, "Failed to establish streaming connection"
        logger.info("✓ Streaming response received")
        
        # And the connection should be established
        logger.info("AND the connection should be established")
        assert response.status_code == 200, f"Expected 200 status, got {response.status_code}"
        logger.info("✓ Streaming connection was successfully established")
        
        # Log results
        if len(stream_data) > 0:
            logger.info(f"✓ Received {len(stream_data)} market data updates")
            logger.info(f"Sample data: {stream_data[0] if stream_data else 'None'}")
        else:
            logger.info("ℹ️ No market data received (may be normal outside market hours)")
        
        logger.info("🎯 SCENARIO PASSED: MNQ streaming connection successful")

def run_mnq_functional_tests():
    """Run MNQ functional tests directly"""
    logger.info("=" * 70)
    logger.info("RUNNING MNQ FUNCTIONAL TESTS (BDD-STYLE)")
    logger.info("=" * 70)
    logger.info(f"Stream service port: {STREAM_PORT}")
    logger.info(f"Contracts service port: {CONTRACTS_PORT}")
    logger.info("")
    
    # Run pytest on this file
    exit_code = pytest.main([__file__, "-v", "-s", "--tb=short"])
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("MNQ FUNCTIONAL TESTS COMPLETED")
    logger.info("=" * 70)
    
    return exit_code

if __name__ == "__main__":
    exit_code = run_mnq_functional_tests()
    exit(exit_code)