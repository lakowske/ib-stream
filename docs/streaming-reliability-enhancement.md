# Streaming Reliability Enhancement - Planning Document

## Executive Summary

This document outlines a comprehensive plan to enhance the reliability, consistency, and uptime of the contract streaming to disk feature in the ib-stream system. Based on the recent incident where background streaming stopped during MNQ market break periods and failed to automatically resume, we propose implementing market-aware retry mechanisms and enhanced monitoring capabilities.

## Problem Statement

### Current Issues Identified

1. **Market Break Handling**: Streaming stops during market breaks (e.g., MNQ 1-hour break 4:00-5:00 PM CDT) and fails to resume automatically
2. **Inadequate Retry Logic**: Current 10-second connection checks don't detect stream data starvation
3. **No Market Hours Awareness**: System doesn't understand when markets are open vs. closed vs. in break periods
4. **Limited Monitoring**: No alerts when streaming stops unexpectedly during trading hours
5. **Single Point of Failure**: Background streaming depends on a single connection that may silently fail

### Impact Assessment

- **Data Loss**: Missing critical market data during active trading periods
- **Manual Intervention Required**: System operators must manually restart services
- **Reduced Reliability**: Decreases confidence in automated trading systems
- **Business Risk**: Incomplete historical data affects backtesting and analysis

## Current Architecture Analysis

### Background Stream Manager (Existing)
```python
# Current retry intervals:
connection_check_interval = 10s    # _manage_connection loop
stream_monitor_interval = 60s      # _monitor_streams loop  
reconnect_delay = 30s              # after exceptions
```

### Limitations of Current Design

1. **Connection vs. Data Flow**: Checks TWS connection but not actual data reception
2. **No Data Staleness Detection**: Doesn't detect when streams stop sending data
3. **Fixed Retry Intervals**: No adaptive retry based on market conditions
4. **No Circuit Breaker Integration**: Missing resilience patterns for external dependencies

## Proposed Enhancements

### 1. Market-Aware Streaming Manager

#### 1.1 Trading Hours Integration
```python
class MarketAwareStreamManager(BackgroundStreamManager):
    """Enhanced stream manager with market hours awareness"""
    
    def __init__(self, tracked_contracts, trading_hours_service):
        super().__init__(tracked_contracts)
        self.trading_hours_service = trading_hours_service
        self.market_status_cache = {}
        self.data_staleness_threshold = timedelta(minutes=5)
```

#### 1.2 Smart Retry Logic
- **During Trading Hours**: Aggressive retry (every 10s) if no data received for 5+ minutes
- **During Market Breaks**: Relaxed retry (every 5 minutes) to check for market reopening
- **During Market Closed**: Minimal retry (every 30 minutes) for overnight sessions
- **Weekend/Holidays**: No retry to conserve resources

#### 1.3 Data Flow Monitoring
```python
class StreamHealthMonitor:
    """Monitor actual data flow rather than just connection status"""
    
    def __init__(self):
        self.last_data_timestamps = {}  # contract_id -> timestamp
        self.data_staleness_threshold = timedelta(minutes=5)
        self.market_break_tolerance = timedelta(hours=2)
    
    def is_stream_healthy(self, contract_id: int) -> bool:
        """Check if stream is receiving data appropriately for market conditions"""
        now = datetime.now(timezone.utc)
        last_data = self.last_data_timestamps.get(contract_id)
        
        if not last_data:
            return False
            
        time_since_data = now - last_data
        market_status = self.get_market_status(contract_id, now)
        
        if market_status.is_open:
            return time_since_data < self.data_staleness_threshold
        elif market_status.is_in_break:
            return time_since_data < self.market_break_tolerance
        else:
            return True  # Market closed, no data expected
```

### 2. Enhanced Retry Mechanisms

#### 2.1 Hierarchical Retry Strategy
```python
class AdaptiveRetryManager:
    """Implements different retry strategies based on failure patterns"""
    
    RETRY_STRATEGIES = {
        'immediate': {'intervals': [1, 2, 5, 10], 'max_attempts': 4},
        'standard': {'intervals': [10, 30, 60, 300], 'max_attempts': 4}, 
        'conservative': {'intervals': [300, 600, 1800], 'max_attempts': 3},
        'maintenance': {'intervals': [3600], 'max_attempts': 1}
    }
    
    def get_retry_strategy(self, contract_id: int, failure_context: str):
        """Select appropriate retry strategy based on market conditions"""
        market_status = self.trading_hours_service.get_market_status(contract_id)
        
        if market_status.is_open:
            return 'immediate' if failure_context == 'data_stale' else 'standard'
        elif market_status.is_in_break:
            return 'standard'
        else:
            return 'conservative'
```

#### 2.2 Circuit Breaker Integration
```python
class StreamCircuitBreaker(CircuitBreaker):
    """Market-aware circuit breaker for streaming connections"""
    
    def __init__(self, contract_id: int, trading_hours_service):
        super().__init__(failure_threshold=5, recovery_timeout=300)
        self.contract_id = contract_id
        self.trading_hours_service = trading_hours_service
    
    def should_attempt_call(self) -> bool:
        """Override to consider market conditions"""
        market_status = self.trading_hours_service.get_market_status(self.contract_id)
        
        # Always try during trading hours
        if market_status.is_open:
            return True
            
        # Use standard circuit breaker logic during breaks/closed
        return super().should_attempt_call()
```

### 3. Monitoring and Alerting Framework

#### 3.1 Stream Health Metrics
```python
@dataclass
class StreamHealthMetrics:
    """Comprehensive health metrics for stream monitoring"""
    
    contract_id: int
    last_data_timestamp: Optional[datetime]
    messages_per_minute: float
    connection_uptime: timedelta
    retry_attempts_last_hour: int
    circuit_breaker_state: str
    market_status: str
    expected_activity_level: str  # 'high', 'medium', 'low', 'none'
    
    def health_score(self) -> float:
        """Calculate overall health score 0.0-1.0"""
        # Implementation details...
```

#### 3.2 Automated Alerting
```python
class StreamingAlertsManager:
    """Manages alerts for streaming anomalies"""
    
    ALERT_RULES = [
        {
            'name': 'data_stale_during_trading',
            'condition': lambda m: m.market_status == 'open' and 
                                 m.last_data_age > timedelta(minutes=5),
            'severity': 'critical',
            'cooldown': timedelta(minutes=15)
        },
        {
            'name': 'frequent_reconnections',
            'condition': lambda m: m.retry_attempts_last_hour > 10,
            'severity': 'warning', 
            'cooldown': timedelta(hours=1)
        }
    ]
```

### 4. Enhanced Configuration Management

#### 4.1 Contract-Specific Settings
```python
@dataclass
class EnhancedTrackedContract(TrackedContract):
    """Extended tracked contract configuration"""
    
    # Existing fields...
    contract_id: int
    symbol: str
    tick_types: List[str]
    enabled: bool
    
    # New reliability fields
    retry_strategy: str = 'standard'
    data_staleness_threshold: int = 300  # seconds
    market_break_tolerance: int = 7200   # seconds
    circuit_breaker_threshold: int = 5
    priority: int = 1  # 1=critical, 2=important, 3=optional
    
    # Market hours override
    custom_trading_hours: Optional[str] = None
    timezone_override: Optional[str] = None
```

#### 4.2 Environment-Based Configuration
```python
# Production configuration
IB_STREAM_DATA_STALENESS_THRESHOLD=300
IB_STREAM_AGGRESSIVE_RETRY_DURING_TRADING=true
IB_STREAM_MARKET_AWARE_RETRY=true
IB_STREAM_ENABLE_STREAM_ALERTS=true
IB_STREAM_ALERT_WEBHOOK_URL=https://alerts.company.com/webhook

# Development configuration (more lenient)
IB_STREAM_DATA_STALENESS_THRESHOLD=600
IB_STREAM_AGGRESSIVE_RETRY_DURING_TRADING=false
```

## Implementation Plan

### Phase 1: Foundation (Week 1-2)
1. **Implement StreamHealthMonitor**: Track actual data flow timestamps
2. **Add Market Status Integration**: Connect trading hours service to background manager
3. **Create Basic Alerting**: Log warnings when streams are stale during trading hours
4. **Enhanced Logging**: Add structured logging for retry attempts and failures

### Phase 2: Smart Retry Logic (Week 3-4)  
1. **Implement AdaptiveRetryManager**: Market-aware retry strategies
2. **Enhance BackgroundStreamManager**: Use adaptive retry and health monitoring
3. **Add Data Staleness Detection**: Monitor time since last received data
4. **Circuit Breaker Integration**: Prevent excessive retry during persistent failures

### Phase 3: Advanced Monitoring (Week 5-6)
1. **StreamHealthMetrics Collection**: Comprehensive health scoring
2. **Automated Alerting System**: Webhook/email notifications for critical issues
3. **Health Dashboard Endpoints**: API endpoints for monitoring tools
4. **Performance Metrics**: Track streaming performance and reliability over time

### Phase 4: Testing and Validation (Week 7-8)
1. **Simulate Market Break Scenarios**: Test automatic resumption after breaks
2. **Connection Failure Testing**: Verify retry behavior during network issues
3. **Load Testing**: Ensure enhanced monitoring doesn't impact performance
4. **Documentation**: Update operational runbooks and monitoring guides

## Risk Assessment

### Technical Risks
- **Increased Complexity**: More moving parts could introduce new failure modes
- **Resource Usage**: Enhanced monitoring may increase CPU/memory consumption
- **False Positives**: Overly sensitive alerting could cause alarm fatigue

### Mitigation Strategies
- **Gradual Rollout**: Deploy enhancements incrementally with feature flags
- **Comprehensive Testing**: Extensive simulation of failure scenarios
- **Performance Monitoring**: Track resource usage impact during implementation
- **Tunable Thresholds**: Make all timing thresholds configurable

## Success Metrics

### Reliability Metrics
- **Stream Uptime**: Target >99.9% during trading hours
- **Automatic Recovery Rate**: >95% of interruptions recover without manual intervention
- **Data Completeness**: <0.1% data loss during trading hours
- **Alert Accuracy**: <5% false positive rate for critical alerts

### Performance Metrics
- **Recovery Time**: <30 seconds for automatic stream restart
- **Resource Overhead**: <5% increase in CPU/memory usage
- **Alerting Latency**: <2 minutes from issue detection to notification

## Conclusion

This enhancement plan addresses the core reliability issues identified in the current streaming system while adding sophisticated market-aware capabilities. By implementing data flow monitoring, adaptive retry strategies, and comprehensive alerting, we can achieve near-100% uptime for critical market data collection.

The phased approach allows for incremental validation and reduces implementation risk, while the configurable nature of the enhancements ensures adaptability to different market conditions and operational requirements.

## Next Steps

1. **Stakeholder Review**: Present plan to development and operations teams
2. **Resource Allocation**: Assign development resources for 8-week implementation
3. **Environment Setup**: Prepare testing environments for reliability testing
4. **Monitoring Integration**: Plan integration with existing monitoring infrastructure
5. **Documentation Planning**: Prepare user guides and operational procedures

---

*Document Version: 1.0*  
*Created: August 12, 2025*  
*Last Updated: August 12, 2025*  
*Status: Draft - Pending Review*