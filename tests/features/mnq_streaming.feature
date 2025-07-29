Feature: MNQ Front Month Streaming
  As a trader
  I want to lookup MNQ front month contract and stream market data
  So that I can monitor real-time futures prices

  Scenario: Lookup MNQ front month contract
    Given the contracts service is running
    When I lookup MNQ future contracts
    Then I should get at least one contract
    And the contract should have a valid contract ID
    And the contract should be a future

  Scenario: Stream MNQ market data
    Given the streaming service is running
    And I have a valid MNQ contract ID
    When I start streaming market data for 5 seconds
    Then I should receive market data updates
    And the data should contain price information