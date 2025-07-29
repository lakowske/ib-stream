Feature: Contract Lookup
  As a developer using the ib-stream system
  I want to lookup contract information for various securities
  So that I can get accurate contract IDs for streaming market data

  Background:
    Given the contracts service is running
    And the service is connected to IB Gateway

  Scenario: AAPL stock contract lookup
    When I request contract details for "AAPL" with security type "STK"
    Then I should receive a 200 OK response
    And the response should contain contract information
    And the ticker should be "AAPL"
    And the contracts should include STK type
    And the STK contract should have exchange "SMART"
    And the STK contract should have a valid contract ID
    And the total contracts count should be greater than 0

  Scenario: SPY ETF contract lookup
    When I request contract details for "SPY" with security type "STK"
    Then I should receive a 200 OK response
    And the response should contain contract information
    And the ticker should be "SPY"
    And the STK contract should have a valid contract ID
    And the contract should include currency "USD"

  Scenario: MNQ future contract lookup
    When I request contract details for "MNQ" with security type "FUT"
    Then I should receive a 200 OK response
    And the response should contain contract information
    And the ticker should be "MNQ"

  Scenario: Multi-type contract lookup
    When I request all contract details for "AAPL"
    Then I should receive a 200 OK response
    And the response should contain contract information
    And the ticker should be "AAPL"
    And the response should include security types searched
    And the security types searched should include "STK"
    And the security types searched should include "OPT"
    And the total contracts count should be greater than 1

  Scenario: Invalid symbol handling
    When I request contract details for "INVALID123" with security type "STK"
    Then I should receive a 200 OK response
    And the ticker should be "INVALID123"
    And the total contracts count should be 0
    And the contracts by type should be empty

  Scenario: Invalid security type handling
    When I request contract details for "AAPL" with security type "INVALID"
    Then I should receive a 400 Bad Request response
    And the response should contain an error message about invalid security type

  Scenario: Contract lookup caching
    Given the cache is cleared
    When I request contract details for "AAPL" with security type "STK"
    Then I should receive a 200 OK response
    When I request the same contract details again
    Then the response should be returned faster from cache
    And the cache status should show memory cache entries

  Scenario: Cache status information
    When I check the cache status endpoint
    Then I should receive a 200 OK response
    And the response should contain memory cache information
    And the response should contain file cache information
    And the response should include cache duration settings