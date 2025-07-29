Feature: Basic API Functionality
  As a developer using the ib-stream system
  I want to ensure basic API endpoints are working
  So that I can build reliable trading applications

  Background:
    Given the ib-stream services are running
    And the services are connected to IB Gateway

  Scenario: Streaming service health check
    When I check the health endpoint for streaming service
    Then I should receive a 200 OK response
    And the response should contain status "healthy"
    And the response should show TWS connection as true
    And the response should include client ID information

  Scenario: Contracts service health check  
    When I check the health endpoint for contracts service
    Then I should receive a 200 OK response
    And the response should contain status "healthy"
    And the response should show TWS connection as true
    And the service name should be "ib-contract"

  Scenario: Streaming service API information
    When I request the streaming service root endpoint
    Then I should receive a 200 OK response
    And the response should contain API version information
    And the response should list available endpoints
    And the response should include supported tick types
    And the supported tick types should include "last"
    And the supported tick types should include "bid_ask"

  Scenario: Contracts service API information
    When I request the contracts service root endpoint
    Then I should receive a 200 OK response
    And the response should contain API version information
    And the response should list available endpoints
    And the response should include supported security types
    And the supported security types should include "STK"
    And the supported security types should include "FUT"

  Scenario: Services use correct configuration
    When I check both service health endpoints
    Then the streaming service should use the correct client ID from config
    And the contracts service should report cached entries count
    And both services should report healthy TWS connections