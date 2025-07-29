"""
Basic step definitions for ib-stream BDD tests.
Handles common API interactions and response validation.
"""

import json
import logging
import time

import pytest
import requests
from pytest_bdd import given, when, then, parsers

logger = logging.getLogger(__name__)

# Shared test context
test_context = {}

@given("the ib-stream services are running")
def services_running(stream_base_url, contracts_base_url, http_session):
    """Verify both services are running and accessible"""
    logger.info("Verifying ib-stream services are running")
    
    # Check streaming service
    try:
        response = http_session.get(f"{stream_base_url}/health", timeout=10)
        assert response.status_code == 200, f"Streaming service not accessible: {response.status_code}"
        logger.info("✓ Streaming service is running")
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Streaming service not accessible: {e}")
    
    # Check contracts service
    try:
        response = http_session.get(f"{contracts_base_url}/health", timeout=10)
        assert response.status_code == 200, f"Contracts service not accessible: {response.status_code}"
        logger.info("✓ Contracts service is running")
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Contracts service not accessible: {e}")

@given("the services are connected to IB Gateway")
def services_connected_to_gateway(stream_base_url, contracts_base_url, http_session):
    """Verify both services are connected to IB Gateway"""
    logger.info("Verifying services are connected to IB Gateway")
    
    # Check streaming service TWS connection
    response = http_session.get(f"{stream_base_url}/health")
    data = response.json()
    assert data.get("tws_connected") is True, "Streaming service not connected to TWS"
    logger.info("✓ Streaming service connected to TWS")
    
    # Check contracts service TWS connection
    response = http_session.get(f"{contracts_base_url}/health")
    data = response.json()
    assert data.get("tws_connected") is True, "Contracts service not connected to TWS"
    logger.info("✓ Contracts service connected to TWS")

@when("I check the health endpoint for streaming service")
def check_streaming_health(stream_base_url, http_session):
    """Make request to streaming service health endpoint"""
    url = f"{stream_base_url}/health"
    logger.info(f"Checking streaming service health at {url}")
    
    response = http_session.get(url)
    test_context["last_response"] = response
    test_context["last_response_data"] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None

@when("I check the health endpoint for contracts service")
def check_contracts_health(contracts_base_url, http_session):
    """Make request to contracts service health endpoint"""
    url = f"{contracts_base_url}/health"
    logger.info(f"Checking contracts service health at {url}")
    
    response = http_session.get(url)
    test_context["last_response"] = response
    test_context["last_response_data"] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None

@when("I request the streaming service root endpoint")
def request_streaming_root(stream_base_url, http_session):
    """Make request to streaming service root endpoint"""
    url = f"{stream_base_url}/"
    logger.info(f"Requesting streaming service root at {url}")
    
    response = http_session.get(url)
    test_context["last_response"] = response
    test_context["last_response_data"] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None

@when("I request the contracts service root endpoint")
def request_contracts_root(contracts_base_url, http_session):
    """Make request to contracts service root endpoint"""
    url = f"{contracts_base_url}/"
    logger.info(f"Requesting contracts service root at {url}")
    
    response = http_session.get(url)
    test_context["last_response"] = response
    test_context["last_response_data"] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None

@when("I check both service health endpoints")
def check_both_health_endpoints(stream_base_url, contracts_base_url, http_session):
    """Check health endpoints for both services"""
    logger.info("Checking both service health endpoints")
    
    # Get streaming service health
    stream_response = http_session.get(f"{stream_base_url}/health")
    stream_data = stream_response.json()
    
    # Get contracts service health
    contracts_response = http_session.get(f"{contracts_base_url}/health")
    contracts_data = contracts_response.json()
    
    test_context["stream_health"] = {"response": stream_response, "data": stream_data}
    test_context["contracts_health"] = {"response": contracts_response, "data": contracts_data}

@then("I should receive a 200 OK response")
def verify_200_response():
    """Verify the last response was 200 OK"""
    response = test_context.get("last_response")
    assert response is not None, "No response available"
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    logger.info("✓ Received 200 OK response")

@then(parsers.parse('the response should contain status "{expected_status}"'))
def verify_status_field(expected_status):
    """Verify the response contains expected status"""
    data = test_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "status" in data, "Response missing 'status' field"
    assert data["status"] == expected_status, f"Expected status '{expected_status}', got '{data['status']}'"
    logger.info(f"✓ Response contains status '{expected_status}'")

@then("the response should show TWS connection as true")
def verify_tws_connected():
    """Verify TWS connection status is true"""
    data = test_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "tws_connected" in data, "Response missing 'tws_connected' field"
    assert data["tws_connected"] is True, f"Expected TWS connected true, got {data['tws_connected']}"
    logger.info("✓ TWS connection verified as true")

@then("the response should include client ID information")
def verify_client_id_present():
    """Verify client ID information is present"""
    data = test_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "client_id" in data, "Response missing 'client_id' field"
    assert isinstance(data["client_id"], int), f"Client ID should be integer, got {type(data['client_id'])}"
    logger.info(f"✓ Client ID present: {data['client_id']}")

@then(parsers.parse('the service name should be "{expected_service}"'))
def verify_service_name(expected_service):
    """Verify the service name in response"""
    data = test_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "service" in data, "Response missing 'service' field"
    assert data["service"] == expected_service, f"Expected service '{expected_service}', got '{data['service']}'"
    logger.info(f"✓ Service name verified as '{expected_service}'")

@then("the response should contain API version information")
def verify_api_version_info():
    """Verify API version information is present"""
    data = test_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "version" in data, "Response missing 'version' field"
    assert "message" in data, "Response missing 'message' field"
    logger.info(f"✓ API version info present: {data['version']}")

@then("the response should list available endpoints")
def verify_endpoints_listed():
    """Verify endpoints are listed in response"""
    data = test_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "endpoints" in data, "Response missing 'endpoints' field"
    assert isinstance(data["endpoints"], dict), "Endpoints should be a dictionary"
    assert len(data["endpoints"]) > 0, "Endpoints dictionary should not be empty"
    logger.info(f"✓ {len(data['endpoints'])} endpoints listed")

@then("the response should include supported tick types")
def verify_tick_types_present():
    """Verify tick types are present in response"""
    data = test_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "tick_types" in data, "Response missing 'tick_types' field"
    assert isinstance(data["tick_types"], list), "Tick types should be a list"
    assert len(data["tick_types"]) > 0, "Tick types list should not be empty"
    logger.info(f"✓ Tick types present: {data['tick_types']}")

@then(parsers.parse('the supported tick types should include "{tick_type}"'))
def verify_tick_type_included(tick_type):
    """Verify specific tick type is included"""
    data = test_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "tick_types" in data, "Response missing 'tick_types' field"
    assert tick_type in data["tick_types"], f"Tick type '{tick_type}' not found in {data['tick_types']}"
    logger.info(f"✓ Tick type '{tick_type}' included")

@then("the response should include supported security types")
def verify_security_types_present():
    """Verify security types are present in response"""
    data = test_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "security_types" in data, "Response missing 'security_types' field"
    assert isinstance(data["security_types"], list), "Security types should be a list"
    assert len(data["security_types"]) > 0, "Security types list should not be empty"
    logger.info(f"✓ Security types present: {data['security_types']}")

@then(parsers.parse('the supported security types should include "{sec_type}"'))
def verify_security_type_included(sec_type):
    """Verify specific security type is included"""
    data = test_context.get("last_response_data")
    assert data is not None, "No response data available"
    assert "security_types" in data, "Response missing 'security_types' field"
    assert sec_type in data["security_types"], f"Security type '{sec_type}' not found in {data['security_types']}"
    logger.info(f"✓ Security type '{sec_type}' included")

@then("the streaming service should use the correct client ID from config")
def verify_streaming_client_id_from_config(instance_config):
    """Verify streaming service uses correct client ID from config"""
    health_data = test_context.get("stream_health", {}).get("data", {})
    expected_client_id = int(instance_config.get('IB_STREAM_CLIENT_ID', '347'))
    
    assert "client_id" in health_data, "Streaming service health missing client_id"
    actual_client_id = health_data["client_id"]
    assert actual_client_id == expected_client_id, f"Expected client ID {expected_client_id}, got {actual_client_id}"
    logger.info(f"✓ Streaming service using correct client ID: {expected_client_id}")

@then("the contracts service should report cached entries count")
def verify_contracts_cache_entries():
    """Verify contracts service reports cache entries count"""
    health_data = test_context.get("contracts_health", {}).get("data", {})
    assert "cache_entries" in health_data, "Contracts service health missing cache_entries"
    cache_count = health_data["cache_entries"]
    assert isinstance(cache_count, int), f"Cache entries should be integer, got {type(cache_count)}"
    logger.info(f"✓ Contracts service cache entries: {cache_count}")

@then("both services should report healthy TWS connections")
def verify_both_services_tws_connected():
    """Verify both services report healthy TWS connections"""
    stream_data = test_context.get("stream_health", {}).get("data", {})
    contracts_data = test_context.get("contracts_health", {}).get("data", {})
    
    assert stream_data.get("tws_connected") is True, "Streaming service not connected to TWS"
    assert contracts_data.get("tws_connected") is True, "Contracts service not connected to TWS"
    logger.info("✓ Both services report healthy TWS connections")