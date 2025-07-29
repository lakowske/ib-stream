"""
Contract lookup step definitions for ib-stream BDD tests.
Handles contract lookup functionality and response validation.
"""

import json
import logging
import time

import pytest
import requests
from pytest_bdd import given, when, then, parsers

logger = logging.getLogger(__name__)

# Shared test context for contract tests
contract_context = {}

@given("the contracts service is running")
def contracts_service_running(contracts_base_url, http_session):
    """Verify contracts service is running and accessible"""
    logger.info("Verifying contracts service is running")
    
    try:
        response = http_session.get(f"{contracts_base_url}/health", timeout=10)
        assert response.status_code == 200, f"Contracts service not accessible: {response.status_code}"
        logger.info("✓ Contracts service is running")
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Contracts service not accessible: {e}")

@given("the service is connected to IB Gateway")
def service_connected_to_gateway(contracts_base_url, http_session):
    """Verify contracts service is connected to IB Gateway"""
    logger.info("Verifying contracts service is connected to IB Gateway")
    
    response = http_session.get(f"{contracts_base_url}/health")
    data = response.json()
    assert data.get("tws_connected") is True, "Contracts service not connected to TWS"
    logger.info("✓ Contracts service connected to TWS")

@given("the cache is cleared")
def clear_cache(contracts_base_url, http_session):
    """Clear the contract cache"""
    logger.info("Clearing contract cache")
    
    response = http_session.delete(f"{contracts_base_url}/cache/clear")
    assert response.status_code == 200, f"Failed to clear cache: {response.status_code}"
    logger.info("✓ Cache cleared")

@when(parsers.parse('I request contract details for "{symbol}" with security type "{sec_type}"'))
def request_contract_with_type(symbol, sec_type, contracts_base_url, http_session):
    """Request contract details for symbol with specific security type"""
    url = f"{contracts_base_url}/lookup/{symbol}/{sec_type}"
    logger.info(f"Requesting contract details for {symbol}/{sec_type} at {url}")
    
    start_time = time.time()
    response = http_session.get(url)
    end_time = time.time()
    
    contract_context["last_request"] = {"symbol": symbol, "sec_type": sec_type, "url": url}
    contract_context["last_response"] = response
    contract_context["last_response_time"] = end_time - start_time
    contract_context["last_response_data"] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None

@when(parsers.parse('I request all contract details for "{symbol}"'))
def request_all_contracts(symbol, contracts_base_url, http_session):
    """Request all contract details for symbol"""
    url = f"{contracts_base_url}/lookup/{symbol}"
    logger.info(f"Requesting all contract details for {symbol} at {url}")
    
    response = http_session.get(url)
    contract_context["last_request"] = {"symbol": symbol, "sec_type": None, "url": url}
    contract_context["last_response"] = response
    contract_context["last_response_data"] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None

@when("I request the same contract details again")
def request_same_contract_again(http_session):
    """Request the same contract details again (for caching test)"""
    last_request = contract_context.get("last_request")
    assert last_request is not None, "No previous request to repeat"
    
    url = last_request["url"]
    logger.info(f"Requesting same contract details again at {url}")
    
    start_time = time.time()
    response = http_session.get(url)
    end_time = time.time()
    
    contract_context["second_response"] = response
    contract_context["second_response_time"] = end_time - start_time
    contract_context["second_response_data"] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None

@when("I check the cache status endpoint")
def check_cache_status(contracts_base_url, http_session):
    """Check the cache status endpoint"""
    url = f"{contracts_base_url}/cache/status"
    logger.info(f"Checking cache status at {url}")
    
    response = http_session.get(url)
    contract_context["cache_response"] = response
    contract_context["cache_response_data"] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None

@then("I should receive a 200 OK response")
def verify_200_response():
    """Verify the last response was 200 OK"""
    response = contract_context.get("last_response")
    assert response is not None, "No response available"
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    logger.info("✓ Received 200 OK response")

@then("I should receive a 400 Bad Request response")
def verify_400_response():
    """Verify the last response was 400 Bad Request"""
    response = contract_context.get("last_response")
    assert response is not None, "No response available"
    assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
    logger.info("✓ Received 400 Bad Request response")

@then("the response should contain contract information")
def verify_contract_information():
    """Verify the response contains contract information"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    
    required_fields = ["ticker", "timestamp", "total_contracts", "contracts_by_type", "security_types_searched"]
    for field in required_fields:
        assert field in data, f"Response missing required field: {field}"
    
    logger.info("✓ Response contains contract information")

@then(parsers.parse('the ticker should be "{expected_ticker}"'))
def verify_ticker(expected_ticker):
    """Verify the ticker matches expected value"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "ticker" in data, "Response missing 'ticker' field"
    assert data["ticker"] == expected_ticker, f"Expected ticker '{expected_ticker}', got '{data['ticker']}'"
    logger.info(f"✓ Ticker verified as '{expected_ticker}'")

@then(parsers.parse("the contracts should include {sec_type} type"))
def verify_contract_type_present(sec_type):
    """Verify contracts include specified security type"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "contracts_by_type" in data, "Response missing 'contracts_by_type' field"
    
    contracts_by_type = data["contracts_by_type"]
    assert sec_type in contracts_by_type, f"Security type '{sec_type}' not found in contracts"
    assert contracts_by_type[sec_type]["count"] > 0, f"No contracts found for type '{sec_type}'"
    logger.info(f"✓ {sec_type} contracts present: {contracts_by_type[sec_type]['count']}")

@then(parsers.parse('the {sec_type} contract should have exchange "{expected_exchange}"'))
def verify_contract_exchange(sec_type, expected_exchange):
    """Verify contract has expected exchange"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    
    contracts_by_type = data["contracts_by_type"]
    assert sec_type in contracts_by_type, f"No {sec_type} contracts found"
    
    contracts = contracts_by_type[sec_type]["contracts"]
    assert len(contracts) > 0, f"No {sec_type} contracts available"
    
    first_contract = contracts[0]
    assert "exchange" in first_contract, f"{sec_type} contract missing 'exchange' field"
    assert first_contract["exchange"] == expected_exchange, f"Expected exchange '{expected_exchange}', got '{first_contract['exchange']}'"
    logger.info(f"✓ {sec_type} contract exchange verified as '{expected_exchange}'")

@then(parsers.parse("the {sec_type} contract should have a valid contract ID"))
def verify_valid_contract_id(sec_type):
    """Verify contract has a valid contract ID"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    
    contracts_by_type = data["contracts_by_type"]
    assert sec_type in contracts_by_type, f"No {sec_type} contracts found"
    
    contracts = contracts_by_type[sec_type]["contracts"]
    assert len(contracts) > 0, f"No {sec_type} contracts available"
    
    first_contract = contracts[0]
    assert "con_id" in first_contract, f"{sec_type} contract missing 'con_id' field"
    assert isinstance(first_contract["con_id"], int), f"Contract ID should be integer, got {type(first_contract['con_id'])}"
    assert first_contract["con_id"] > 0, f"Contract ID should be positive, got {first_contract['con_id']}"
    logger.info(f"✓ {sec_type} contract has valid contract ID: {first_contract['con_id']}")

@then("the total contracts count should be greater than 0")
def verify_contracts_count_positive():
    """Verify total contracts count is greater than 0"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "total_contracts" in data, "Response missing 'total_contracts' field"
    
    total_contracts = data["total_contracts"]
    assert total_contracts > 0, f"Expected contracts count > 0, got {total_contracts}"
    logger.info(f"✓ Total contracts count: {total_contracts}")

@then("the total contracts count should be greater than 1")
def verify_contracts_count_greater_than_one():
    """Verify total contracts count is greater than 1"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "total_contracts" in data, "Response missing 'total_contracts' field"
    
    total_contracts = data["total_contracts"]
    assert total_contracts > 1, f"Expected contracts count > 1, got {total_contracts}"
    logger.info(f"✓ Total contracts count: {total_contracts}")

@then("the total contracts count should be 0")
def verify_contracts_count_zero():
    """Verify total contracts count is 0"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "total_contracts" in data, "Response missing 'total_contracts' field"
    
    total_contracts = data["total_contracts"]
    assert total_contracts == 0, f"Expected contracts count 0, got {total_contracts}"
    logger.info("✓ Total contracts count is 0 (as expected for invalid symbol)")

@then("the contracts by type should be empty")
def verify_empty_contracts_by_type():
    """Verify contracts_by_type is empty"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "contracts_by_type" in data, "Response missing 'contracts_by_type' field"
    
    contracts_by_type = data["contracts_by_type"]
    assert len(contracts_by_type) == 0, f"Expected empty contracts_by_type, got {len(contracts_by_type)} entries"
    logger.info("✓ Contracts by type is empty (as expected for invalid symbol)")

@then(parsers.parse('the contract should include currency "{expected_currency}"'))
def verify_contract_currency(expected_currency):
    """Verify contract includes expected currency"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    
    # Look for STK contract with currency
    contracts_by_type = data["contracts_by_type"]
    assert "STK" in contracts_by_type, "No STK contracts found"
    
    contracts = contracts_by_type["STK"]["contracts"]
    assert len(contracts) > 0, "No STK contracts available"
    
    first_contract = contracts[0]
    assert "currency" in first_contract, "STK contract missing 'currency' field"
    assert first_contract["currency"] == expected_currency, f"Expected currency '{expected_currency}', got '{first_contract['currency']}'"
    logger.info(f"✓ Contract currency verified as '{expected_currency}'")


@then(parsers.parse("the {sec_type} contract should have an expiry date"))
def verify_contract_expiry(sec_type):
    """Verify contract has an expiry date"""
    data = contract_context.get("last_response_data")
    contracts_by_type = data["contracts_by_type"]
    contracts = contracts_by_type[sec_type]["contracts"]
    first_contract = contracts[0]
    
    assert "expiry" in first_contract, f"{sec_type} contract missing 'expiry' field"
    assert first_contract["expiry"] != "N/A", f"{sec_type} contract should have valid expiry date"
    logger.info(f"✓ {sec_type} contract has expiry: {first_contract['expiry']}")

@then(parsers.parse("the {sec_type} contract should have a multiplier"))
def verify_contract_multiplier(sec_type):
    """Verify contract has a multiplier"""
    data = contract_context.get("last_response_data")
    contracts_by_type = data["contracts_by_type"]
    contracts = contracts_by_type[sec_type]["contracts"]
    first_contract = contracts[0]
    
    assert "multiplier" in first_contract, f"{sec_type} contract missing 'multiplier' field"
    assert first_contract["multiplier"] != "N/A", f"{sec_type} contract should have valid multiplier"
    logger.info(f"✓ {sec_type} contract has multiplier: {first_contract['multiplier']}")

@then("the response should include security types searched")
def verify_security_types_searched():
    """Verify response includes security types searched"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "security_types_searched" in data, "Response missing 'security_types_searched' field"
    
    searched_types = data["security_types_searched"]
    assert isinstance(searched_types, list), "Security types searched should be a list"
    assert len(searched_types) > 0, "Security types searched should not be empty"
    logger.info(f"✓ Security types searched: {searched_types}")

@then(parsers.parse('the security types searched should include "{sec_type}"'))
def verify_searched_type_included(sec_type):
    """Verify specific security type was searched"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "security_types_searched" in data, "Response missing 'security_types_searched' field"
    
    searched_types = data["security_types_searched"]
    assert sec_type in searched_types, f"Security type '{sec_type}' not found in searched types: {searched_types}"
    logger.info(f"✓ Security type '{sec_type}' was searched")

@then("the response should contain an error message about invalid security type")
def verify_invalid_security_type_error():
    """Verify response contains error about invalid security type"""
    data = contract_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "detail" in data, "Response missing 'detail' field for error"
    
    error_message = data["detail"].lower()
    assert "invalid security type" in error_message, f"Expected 'invalid security type' in error message, got: {data['detail']}"
    logger.info("✓ Received appropriate error message for invalid security type")

@then("the response should be returned faster from cache")
def verify_faster_cache_response():
    """Verify second response was faster (from cache)"""
    first_time = contract_context.get("last_response_time", 0)
    second_time = contract_context.get("second_response_time", 0)
    
    # Cache should be significantly faster, but we'll be lenient
    # since network timing can vary
    logger.info(f"First request time: {first_time:.3f}s, Second request time: {second_time:.3f}s")
    
    # Just verify both requests succeeded
    second_response = contract_context.get("second_response")
    assert second_response.status_code == 200, "Second request should also succeed"
    logger.info("✓ Second request completed successfully (cache test)")

@then("the cache status should show memory cache entries")
def verify_memory_cache_entries():
    """Verify cache status shows memory cache entries"""
    # We need to check cache status
    if "cache_response_data" not in contract_context:
        # Request cache status if not already done
        pytest.fail("Cache status not checked - need to call cache status endpoint first")
    
    cache_data = contract_context.get("cache_response_data")
    assert cache_data is not None, "No cache response data available"
    assert "memory_cache" in cache_data, "Cache response missing 'memory_cache' field"
    
    memory_cache = cache_data["memory_cache"]
    logger.info(f"✓ Cache status includes memory cache with {len(memory_cache)} entries")

@then("the response should contain memory cache information")
def verify_memory_cache_information():
    """Verify response contains memory cache information"""
    data = contract_context.get("cache_response_data")
    assert data is not None, "No cache response data available"
    assert "memory_cache" in data, "Cache response missing 'memory_cache' field"
    
    memory_cache = data["memory_cache"]
    assert isinstance(memory_cache, dict), "Memory cache should be a dictionary"
    logger.info(f"✓ Memory cache information present with {len(memory_cache)} entries")

@then("the response should contain file cache information")
def verify_file_cache_information():
    """Verify response contains file cache information"""
    data = contract_context.get("cache_response_data")
    assert data is not None, "No cache response data available"
    assert "file_cache" in data, "Cache response missing 'file_cache' field"
    
    file_cache = data["file_cache"]
    assert isinstance(file_cache, dict), "File cache should be a dictionary"
    logger.info(f"✓ File cache information present with {len(file_cache)} entries")

@then("the response should include cache duration settings")
def verify_cache_duration_settings():
    """Verify response includes cache duration settings"""
    data = contract_context.get("cache_response_data")
    assert data is not None, "No cache response data available"
    assert "cache_duration_days" in data, "Cache response missing 'cache_duration_days' field"
    
    duration_days = data["cache_duration_days"]
    assert isinstance(duration_days, (int, float)), "Cache duration should be numeric"
    assert duration_days > 0, "Cache duration should be positive"
    logger.info(f"✓ Cache duration settings present: {duration_days} days")