#!/usr/bin/env python3
"""
Integration tests for ib-stream system
Tests the live system with actual service ports and IB Gateway connection.
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import pytest
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load instance configuration to get actual ports
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

class TestSystemIntegration:
    """Integration tests for the live ib-stream system"""
    
    @pytest.fixture(autouse=True)
    def setup_logging(self, request):
        """Setup test logging"""
        logger.info(f"Starting test: {request.node.name}")
        yield
        logger.info(f"Completed test: {request.node.name}")
    
    def test_streaming_service_health(self):
        """Test streaming service health endpoint"""
        url = f"http://localhost:{STREAM_PORT}/health"
        
        logger.info(f"Testing streaming service health at {url}")
        
        response = requests.get(url, timeout=10)
        assert response.status_code == 200, f"Health check failed with status {response.status_code}"
        
        data = response.json()
        logger.info(f"Streaming service health response: {json.dumps(data, indent=2)}")
        
        # Validate response structure
        assert "status" in data, "Response missing 'status' field"
        assert data["status"] == "healthy", f"Expected healthy status, got {data['status']}"
        assert "timestamp" in data, "Response missing 'timestamp' field"
        assert "tws_connected" in data, "Response missing 'tws_connected' field"
        assert data["tws_connected"] is True, "TWS should be connected"
        assert "client_id" in data, "Response missing 'client_id' field"
        
        # Validate storage information
        if "storage" in data:
            storage = data["storage"]
            assert "enabled" in storage, "Storage missing 'enabled' field"
            assert "health" in storage, "Storage missing 'health' field"
            
        logger.info("✓ Streaming service health check passed")

    def test_contracts_service_health(self):
        """Test contracts service health endpoint"""
        url = f"http://localhost:{CONTRACTS_PORT}/health"
        
        logger.info(f"Testing contracts service health at {url}")
        
        response = requests.get(url, timeout=10)
        assert response.status_code == 200, f"Health check failed with status {response.status_code}"
        
        data = response.json()
        logger.info(f"Contracts service health response: {json.dumps(data, indent=2)}")
        
        # Validate response structure
        assert "service" in data, "Response missing 'service' field"
        assert data["service"] == "ib-contract", f"Expected service name 'ib-contract', got {data['service']}"
        assert "status" in data, "Response missing 'status' field"
        assert data["status"] == "healthy", f"Expected healthy status, got {data['status']}"
        assert "timestamp" in data, "Response missing 'timestamp' field"
        assert "tws_connected" in data, "Response missing 'tws_connected' field"
        assert data["tws_connected"] is True, "TWS should be connected"
        
        logger.info("✓ Contracts service health check passed")

    def test_streaming_service_root_endpoint(self):
        """Test streaming service root endpoint"""
        url = f"http://localhost:{STREAM_PORT}/"
        
        logger.info(f"Testing streaming service root at {url}")
        
        response = requests.get(url, timeout=10)
        assert response.status_code == 200, f"Root endpoint failed with status {response.status_code}"
        
        data = response.json()
        logger.info(f"Streaming service root response keys: {list(data.keys())}")
        
        # Validate response structure
        assert "message" in data, "Response missing 'message' field"
        assert "version" in data, "Response missing 'version' field"
        assert "endpoints" in data, "Response missing 'endpoints' field"
        assert "tick_types" in data, "Response missing 'tick_types' field"
        assert "configuration" in data, "Response missing 'configuration' field"
        
        # Validate tick types
        expected_tick_types = ["last", "all_last", "bid_ask", "mid_point"]
        for tick_type in expected_tick_types:
            assert tick_type in data["tick_types"], f"Missing tick type: {tick_type}"
        
        logger.info("✓ Streaming service root endpoint passed")

    def test_contracts_service_root_endpoint(self):
        """Test contracts service root endpoint"""
        url = f"http://localhost:{CONTRACTS_PORT}/"
        
        logger.info(f"Testing contracts service root at {url}")
        
        response = requests.get(url, timeout=10)
        assert response.status_code == 200, f"Root endpoint failed with status {response.status_code}"
        
        data = response.json()
        logger.info(f"Contracts service root response keys: {list(data.keys())}")
        
        # Validate response structure
        assert "message" in data, "Response missing 'message' field"
        assert "version" in data, "Response missing 'version' field"
        assert "endpoints" in data, "Response missing 'endpoints' field"
        assert "security_types" in data, "Response missing 'security_types' field"
        
        # Validate security types
        expected_sec_types = ["STK", "FUT", "OPT", "CASH"]
        for sec_type in expected_sec_types:
            assert sec_type in data["security_types"], f"Missing security type: {sec_type}"
        
        logger.info("✓ Contracts service root endpoint passed")

    def test_contract_lookup_aapl_stock(self):
        """Test contract lookup for AAPL stock"""
        url = f"http://localhost:{CONTRACTS_PORT}/lookup/AAPL/STK"
        
        logger.info(f"Testing AAPL stock contract lookup at {url}")
        
        response = requests.get(url, timeout=30)
        assert response.status_code == 200, f"Contract lookup failed with status {response.status_code}"
        
        data = response.json()
        logger.info(f"AAPL contract lookup - Total contracts: {data.get('total_contracts', 0)}")
        
        # Validate response structure
        assert "ticker" in data, "Response missing 'ticker' field"
        assert data["ticker"] == "AAPL", f"Expected ticker 'AAPL', got {data['ticker']}"
        assert "timestamp" in data, "Response missing 'timestamp' field"
        assert "total_contracts" in data, "Response missing 'total_contracts' field"
        assert "contracts_by_type" in data, "Response missing 'contracts_by_type' field"
        
        # Validate STK contract data
        contracts_by_type = data["contracts_by_type"]
        assert "STK" in contracts_by_type, "Missing STK contracts"
        
        stk_data = contracts_by_type["STK"]
        assert "count" in stk_data, "STK data missing 'count' field"
        assert "contracts" in stk_data, "STK data missing 'contracts' field"
        assert stk_data["count"] > 0, "Should have at least one STK contract"
        
        # Validate first STK contract
        first_contract = stk_data["contracts"][0]
        assert first_contract["symbol"] == "AAPL", f"Expected symbol 'AAPL', got {first_contract['symbol']}"
        assert first_contract["sec_type"] == "STK", f"Expected sec_type 'STK', got {first_contract['sec_type']}"
        assert "con_id" in first_contract, "Contract missing 'con_id' field"
        assert "exchange" in first_contract, "Contract missing 'exchange' field"
        
        logger.info(f"✓ AAPL contract lookup passed - Contract ID: {first_contract['con_id']}")

    def test_contract_lookup_spy_etf(self):
        """Test contract lookup for SPY ETF"""
        url = f"http://localhost:{CONTRACTS_PORT}/lookup/SPY/STK"
        
        logger.info(f"Testing SPY ETF contract lookup at {url}")
        
        response = requests.get(url, timeout=30)
        assert response.status_code == 200, f"Contract lookup failed with status {response.status_code}"
        
        data = response.json()
        logger.info(f"SPY contract lookup - Total contracts: {data.get('total_contracts', 0)}")
        
        # Validate response structure
        assert data["ticker"] == "SPY", f"Expected ticker 'SPY', got {data['ticker']}"
        assert "STK" in data["contracts_by_type"], "Missing STK contracts for SPY"
        
        stk_data = data["contracts_by_type"]["STK"]
        assert stk_data["count"] > 0, "Should have at least one SPY STK contract"
        
        first_contract = stk_data["contracts"][0]
        assert first_contract["symbol"] == "SPY", f"Expected symbol 'SPY', got {first_contract['symbol']}"
        
        logger.info(f"✓ SPY contract lookup passed - Contract ID: {first_contract['con_id']}")

    def test_contract_lookup_mnq_future(self):
        """Test contract lookup for MNQ future"""
        url = f"http://localhost:{CONTRACTS_PORT}/lookup/MNQ/FUT"
        
        logger.info(f"Testing MNQ future contract lookup at {url}")
        
        response = requests.get(url, timeout=30)
        assert response.status_code == 200, f"Contract lookup failed with status {response.status_code}"
        
        data = response.json()
        logger.info(f"MNQ contract lookup - Total contracts: {data.get('total_contracts', 0)}")
        
        # Validate response structure
        assert data["ticker"] == "MNQ", f"Expected ticker 'MNQ', got {data['ticker']}"
        
        # Check if we found FUT contracts
        if "FUT" in data["contracts_by_type"]:
            fut_data = data["contracts_by_type"]["FUT"]
            assert fut_data["count"] > 0, "Should have at least one MNQ FUT contract"
            
            first_contract = fut_data["contracts"][0]
            assert first_contract["symbol"] == "MNQ", f"Expected symbol 'MNQ', got {first_contract['symbol']}"
            assert first_contract["sec_type"] == "FUT", f"Expected sec_type 'FUT', got {first_contract['sec_type']}"
            assert "expiry" in first_contract, "Future contract missing 'expiry' field"
            
            logger.info(f"✓ MNQ future contract lookup passed - Contract ID: {first_contract['con_id']}")
        else:
            logger.warning("No MNQ future contracts found - this may be expected if not available")

    def test_contract_lookup_invalid_symbol(self):
        """Test contract lookup for invalid symbol"""
        url = f"http://localhost:{CONTRACTS_PORT}/lookup/INVALID123"
        
        logger.info(f"Testing invalid symbol contract lookup at {url}")
        
        response = requests.get(url, timeout=30)
        assert response.status_code == 200, "Should return 200 even for invalid symbols"
        
        data = response.json()
        logger.info(f"Invalid symbol lookup - Total contracts: {data.get('total_contracts', 0)}")
        
        # Should return empty result
        assert data["ticker"] == "INVALID123", f"Expected ticker 'INVALID123', got {data['ticker']}"
        assert data["total_contracts"] == 0, "Should have 0 contracts for invalid symbol"
        assert len(data["contracts_by_type"]) == 0, "Should have empty contracts_by_type"
        
        logger.info("✓ Invalid symbol contract lookup handled correctly")

    def test_cache_status_endpoint(self):
        """Test cache status endpoint"""
        url = f"http://localhost:{CONTRACTS_PORT}/cache/status"
        
        logger.info(f"Testing cache status at {url}")
        
        response = requests.get(url, timeout=10)
        assert response.status_code == 200, f"Cache status failed with status {response.status_code}"
        
        data = response.json()
        logger.info(f"Cache status response keys: {list(data.keys())}")
        
        # Validate response structure
        assert "memory_cache" in data, "Response missing 'memory_cache' field"
        assert "file_cache" in data, "Response missing 'file_cache' field" 
        assert "cache_duration_days" in data, "Response missing 'cache_duration_days' field"
        
        logger.info("✓ Cache status endpoint passed")

    def test_streaming_service_configuration(self):
        """Test streaming service configuration in health response"""
        url = f"http://localhost:{STREAM_PORT}/health"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # Validate client ID matches instance config
        expected_client_id = int(CONFIG.get('IB_STREAM_CLIENT_ID', '347'))
        assert data["client_id"] == expected_client_id, f"Expected client_id {expected_client_id}, got {data['client_id']}"
        
        logger.info(f"✓ Streaming service using correct client ID: {expected_client_id}")

    def test_system_connectivity_full_chain(self):
        """Test full system connectivity chain"""
        logger.info("Testing full system connectivity chain...")
        
        # 1. Check both services are healthy
        stream_health = requests.get(f"http://localhost:{STREAM_PORT}/health", timeout=10)
        contracts_health = requests.get(f"http://localhost:{CONTRACTS_PORT}/health", timeout=10)
        
        assert stream_health.status_code == 200, "Streaming service not healthy"
        assert contracts_health.status_code == 200, "Contracts service not healthy"
        
        # 2. Verify both are connected to TWS
        stream_data = stream_health.json()
        contracts_data = contracts_health.json()
        
        assert stream_data["tws_connected"] is True, "Streaming service not connected to TWS"
        assert contracts_data["tws_connected"] is True, "Contracts service not connected to TWS"
        
        # 3. Test contract lookup works
        lookup_response = requests.get(f"http://localhost:{CONTRACTS_PORT}/lookup/AAPL/STK", timeout=30)
        assert lookup_response.status_code == 200, "Contract lookup failed"
        
        lookup_data = lookup_response.json()
        assert lookup_data["total_contracts"] > 0, "No contracts found for AAPL"
        
        # 4. Get contract ID for potential streaming test
        aapl_contract_id = lookup_data["contracts_by_type"]["STK"]["contracts"][0]["con_id"]
        
        logger.info(f"✓ Full system connectivity verified - AAPL Contract ID: {aapl_contract_id}")

def run_integration_tests():
    """Run integration tests and report results"""
    logger.info("=" * 60)
    logger.info("RUNNING IB-STREAM SYSTEM INTEGRATION TESTS")
    logger.info("=" * 60)
    logger.info(f"Stream service port: {STREAM_PORT}")
    logger.info(f"Contracts service port: {CONTRACTS_PORT}")
    logger.info(f"Test started at: {datetime.now().isoformat()}")
    logger.info("")
    
    # Run tests
    exit_code = pytest.main([__file__, "-v", "-s", "--tb=short"])
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("INTEGRATION TESTS COMPLETED")
    logger.info("=" * 60)
    
    return exit_code

if __name__ == "__main__":
    exit_code = run_integration_tests()
    exit(exit_code)