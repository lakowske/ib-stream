# Test Suite Generator for ib-stream

## Overview

Generate a comprehensive test suite for the ib-stream project using Gherkin-style test descriptions. Start with basic API functionality tests and progressively add more sophisticated tests.

## Instructions

### Phase 0: Environment Preparation
1. **Check service status first:**
   - Verify supervisor services are running: `./supervisor-wrapper.sh status`
   - If not running, start them: `make start-supervisor` or `./start-supervisor.sh`
   - Confirm services are healthy before proceeding with test creation
   - Note the actual ports from `ib-stream/config/instance.env`

2. **Understand the test approach:**
   - Create simple integration tests first to validate the live system
   - Then build comprehensive BDD scenarios
   - Start with working system validation, not theoretical tests

### Phase 1: Codebase Analysis
1. **Review the project architecture:**
   - Examine `CLAUDE.md` for project structure and commands
   - Review `ib-stream/` service for streaming functionality
   - Review `ib-contract/` service for contract lookup
   - Understand the shared `ib-util/` connection utilities
   - Check supervisor configuration and service management

2. **Analyze API endpoints and functionality:**
   - Health check endpoints for both services
   - Contract lookup capabilities
   - Streaming data endpoints (SSE/WebSocket)
   - Configuration and environment handling

3. **Review existing configuration:**
   - Environment files in `ib-stream/config/`
   - Dynamic instance configuration system
   - Remote gateway connection setup

### Phase 2: Test Design

Create Gherkin-style test scenarios covering:

#### Basic Infrastructure Tests
- **Connection Tests:**
  - Can connect to IB Gateway
  - Services start successfully with supervisor
  - Health endpoints respond correctly
  - Configuration is loaded properly

- **Service Status Tests:**
  - Both services are running
  - Services restart automatically on failure
  - Logs are being written correctly

#### Contract Lookup Tests
- **Basic Contract Tests:**
  - Can lookup AAPL stock contract ID
  - Can lookup MNQ future contract (front month)
  - Can lookup SPY ETF contract
  - Can lookup EURUSD forex contract
  - Handle invalid contract symbols gracefully

- **Contract Details Tests:**
  - Returns correct contract specifications
  - Includes exchange information
  - Provides trading hours
  - Returns contract multiplier for futures

#### API Functionality Tests
- **HTTP Endpoint Tests:**
  - Health endpoints return proper JSON
  - Contract lookup endpoints work
  - Error handling returns appropriate status codes
  - Rate limiting works if implemented

- **Streaming Tests (Basic):**
  - Can establish streaming connection
  - Receives market data for valid contracts
  - Handles connection drops gracefully
  - Properly formats streaming data

#### Configuration and Environment Tests
- **Environment Loading:**
  - Remote gateway configuration works
  - Instance-specific client IDs are generated
  - Port allocation works correctly
  - SSH tunnel configuration if present

- **Dynamic Configuration:**
  - Instance config generation works
  - MD5 hashing produces consistent results
  - Environment variables are properly exported

### Phase 3: Test Implementation

1. **Start with simple integration tests:**
   - Create `test_system_integration.py` first to validate live system
   - Test actual service health endpoints with real ports
   - Verify contract lookup with real IB Gateway connection
   - Validate API endpoints return expected responses
   - Use this to understand the actual system behavior before writing BDD scenarios

2. **Create BDD test framework:**
   - Use pytest with pytest-bdd for Gherkin support
   - Set up test configuration and fixtures in `conftest.py`
   - Create helper functions for common operations
   - **Important**: Add proper `__init__.py` files to make packages importable

3. **Implement BDD scenarios:**
   - Write step definitions that use actual API calls, not mocks
   - Import step definitions properly in test runner
   - Handle pytest-bdd parser limitations (avoid `{value:Bool}`, use `{value:w}`)
   - Test against the live system, not simulated responses

4. **Test execution strategy:**
   - Run simple integration tests first to verify system health
   - Run BDD scenarios after integration tests pass
   - Fix import and parsing issues before adding complex logic
   - Ensure tests can run in CI/CD environment

### Phase 4: Test Organization

Create the following test structure:
```
tests/
├── test_system_integration.py      # Start here - live system validation
├── features/
│   ├── basic_functionality.feature
│   ├── contract_lookup.feature
│   ├── streaming_api.feature
│   └── configuration.feature
├── step_definitions/
│   ├── __init__.py                 # Required for imports
│   ├── basic_steps.py
│   ├── contract_steps.py
│   ├── streaming_steps.py
│   └── config_steps.py
├── fixtures/
│   ├── test_contracts.py
│   └── mock_responses.py
├── __init__.py                     # Required for package
├── conftest.py
├── pytest.ini
├── test_bdd_runner.py              # BDD scenario runner
└── requirements.txt
```

**Test Implementation Order:**
1. `test_system_integration.py` - Verify live system works
2. Basic BDD framework setup with imports
3. Simple scenarios first, complex ones later
4. Fix parsing and import issues before adding logic

### Example Gherkin Scenarios

```gherkin
Feature: Basic API Functionality
  
  Scenario: Services are healthy
    Given the ib-stream services are running
    When I check the health endpoint for streaming service
    Then I should receive a 200 OK response
    And the response should contain "status": "healthy"
    
  Scenario: Contract lookup for AAPL
    Given the contract service is running
    When I request contract details for "AAPL"
    Then I should receive contract information
    And the symbol should be "AAPL"
    And the exchange should be "SMART"
    
  Scenario: MNQ future contract lookup
    Given the contract service is running
    When I request contract details for "MNQ" front month future
    Then I should receive contract information
    And the contract type should be "FUT"
    And the exchange should be "CME"
```

## Expected Deliverables

1. **Integration test file** proving the live system works
2. **Test feature files** with comprehensive Gherkin scenarios  
3. **Step definition files** implementing the test logic
4. **Test configuration** including pytest setup and requirements
5. **Test execution results** showing integration tests passing
6. **Test documentation** explaining how to run and extend the tests
7. **Test summary** with system status and validation results

## Success Criteria

- **Integration tests pass first** - Verify system is actually working
- All basic infrastructure tests pass
- Contract lookup tests work for major asset classes  
- API endpoints respond correctly
- Tests can be run repeatedly with consistent results
- Test framework is extensible for future enhancements

## Critical Implementation Tips

### Common Pitfalls to Avoid:
1. **Don't start with BDD scenarios** - Start with simple integration tests to validate the live system
2. **Check service status first** - Many test failures are due to services not running
3. **Use actual ports** - Read `ib-stream/config/instance.env` for real ports, don't assume defaults
4. **Fix imports early** - Add `__init__.py` files and import step definitions properly
5. **Handle parser limitations** - pytest-bdd has parsing quirks (e.g., avoid `{value:Bool}`)
6. **Test against reality** - Use actual API calls, not mocks, for integration validation

### Recommended Implementation Flow:
```bash
# 1. Verify services are running
./supervisor-wrapper.sh status

# 2. Create simple integration test first
# test_system_integration.py with actual service ports

# 3. Run integration test to validate system
python -m pytest test_system_integration.py -v -s

# 4. Only after integration tests pass, create BDD scenarios
# 5. Fix import and parsing issues before adding complex logic
```

### Debug Checklist:
- [ ] Services running via supervisor?  
- [ ] Actual ports from instance.env being used?
- [ ] `__init__.py` files in all package directories?
- [ ] Step definitions properly imported?
- [ ] pytest-bdd parsers using correct syntax?
- [ ] Testing against live system, not mocks?

## Notes

- **Start with integration validation, not theoretical tests**
- Use actual API calls and live system responses
- Ensure tests work with the dynamic configuration system
- Consider both development and production environments
- Plan for future tests of streaming data validation and storage verification
- **Success is measured by working integration tests first, comprehensive BDD scenarios second**