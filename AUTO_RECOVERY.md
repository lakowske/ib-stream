# Enhanced Auto-Recovery System

## Overview

The ib-stream service features a sophisticated auto-recovery system that automatically detects and resolves connection and data flow issues without manual intervention. This system is critical for maintaining continuous market data collection during trading hours.

## Key Features

### 🔍 Dual-State Detection
- **Socket Connection Monitoring**: Tracks TWS/IB Gateway connectivity status
- **Data Flow Monitoring**: Monitors actual market data reception (independent of socket status)
- **Degraded State Detection**: Identifies "zombie connections" (connected but no data flowing)

### ⚡ Escalating Recovery Actions
- **Progressive escalation** with increasing intervention levels
- **Automatic stream restarts** for individual contracts
- **Connection resets** for persistent issues  
- **Comprehensive logging** for debugging and monitoring

### 🚀 Production-Optimized Timing
- **1-minute detection** for rapid problem identification
- **Active market monitoring** with appropriate escalation intervals
- **Reduced log noise** with debug-level storage logging

## Auto-Recovery Architecture

### State Detection System

```python
# Two independent monitoring channels:
socket_connected = _is_socket_connected()    # IB Gateway API connection
data_flowing = _is_data_flowing()           # Actual market data reception

# Health states:
# - Healthy: socket_connected=True, data_flowing=True  
# - Degraded: socket_connected=True, data_flowing=False  (zombie connection)
# - Disconnected: socket_connected=False, data_flowing=False
```

### Escalation Timeline

| **Time** | **Level** | **Action** | **Log Level** |
|----------|-----------|------------|---------------|
| 1 minute | Level 1 | Warning logs | WARNING |
| 3 minutes | Level 2 | Restart contract streams | INFO |
| 5 minutes | Level 3 | Force connection reset | WARNING |
| 10 minutes | Level 4 | Service restart warning | CRITICAL |

### Monitoring Frequency
- **Monitor cycle**: Every 60 seconds
- **Data staleness threshold**: 1 minute  
- **Zombie connection timeout**: 2 minutes (streams active but no data)

## Common Scenarios

### 1. TWS Session Conflict (Most Common)

**Scenario:** User logs into TWS on another machine while ib-stream is running

**Detection:**
```
Monitor cycle: socket_connected=True, data_flowing=False
Error 10189: Trading TWS session is connected from a different IP address
```

**Auto-Recovery:**
1. **1 minute**: Warning logs about stale data
2. **3 minutes**: Restart contract streams (usually resolves issue)
3. **Automatic resolution** when competing TWS session is closed

### 2. IB Gateway Restart/Crash

**Scenario:** IB Gateway service restarts or crashes

**Detection:**
```
Monitor cycle: socket_connected=False, data_flowing=False
Connection timeout errors
```

**Auto-Recovery:**
1. **Immediate**: Connection management loop attempts reconnection
2. **5-second intervals**: Retry connection across all configured ports
3. **Automatic**: Restart all background streams once connected
4. **Full recovery** typically within 30-60 seconds

### 3. Network Interruption

**Scenario:** Temporary network connectivity loss

**Detection:**
```
Monitor cycle: socket_connected=False, data_flowing=False
Connection failure errors
```

**Auto-Recovery:**
1. **Continuous retry**: Connection attempts every 5 seconds
2. **Port cycling**: Try all configured ports (7497, 7496, 4002, 4001)
3. **Stream restoration**: Automatically restart background streams
4. **Resume data flow** once network is restored

### 4. Market Data Subscription Issues

**Scenario:** IB data subscription problems or market hours

**Detection:**
```
Monitor cycle: socket_connected=True, data_flowing=False
No Error 10189 (distinguishes from TWS conflict)
```

**Auto-Recovery:**
1. **3 minutes**: Restart contract streams
2. **5 minutes**: Force connection reset (new client ID)
3. **May require manual intervention** if subscription-related

## Configuration

### Key Settings

```python
# Timing configuration
monitor_interval = 60  # seconds
data_flow_threshold = 60  # seconds (1 minute)
stream_restart_threshold = 180  # seconds (3 minutes)  
connection_reset_threshold = 300  # seconds (5 minutes)

# Connection settings
connection_check_interval = 5  # seconds
reconnect_delay = 5  # seconds
ports = [7497, 7496, 4002, 4001]  # IB Gateway/TWS ports
```

### Environment Variables

```bash
# Production configuration
IB_STREAM_HOST=localhost
IB_STREAM_CLIENT_ID=851
IB_STREAM_ENABLE_BACKGROUND_STREAMING=true
```

## Monitoring and Alerting

### Health Endpoints

```bash
# Overall system health
curl http://localhost:8851/health

# Background streaming health  
curl http://localhost:8851/background/health/711280073

# System health for external monitoring
curl http://localhost:8851/system/health
```

### Health Status Interpretation

```json
{
  "status": "healthy",           // healthy | degraded | warning
  "tws_connected": true,         // Socket connection status
  "background_streaming": {
    "status": "running",         // running | degraded | disconnected
    "data_flowing": true         // Actual data reception
  }
}
```

### Log Analysis

**Key log patterns to monitor:**

```bash
# Normal operation
"Monitor cycle: socket_connected=True, data_flowing=True"

# Degraded state (zombie connection)  
"Monitor cycle: socket_connected=True, data_flowing=False"
"STALE DATA (Level 1): Contract 711280073 (MNQ) - no data for 0:01:30"

# Connection issues
"Monitor cycle: socket_connected=False, data_flowing=False"
"Attempting to connect to 0.0.0.0:4002 with client ID 851"

# Recovery actions
"Restarting streams for contract 711280073"
"✅ Connection reset completed successfully"
```

## Troubleshooting

### When Auto-Recovery Fails

**Level 4 warnings indicate persistent issues:**
```
CRITICAL: Consider service restart - auto-recovery not resolving issue
```

**Manual intervention may be needed for:**
- IB account/subscription issues
- Network firewall changes
- IB Gateway configuration problems
- Market data permission changes

### Debugging Commands

```bash
# Check service status
source .venv/bin/activate && python ib.py services status

# Test IB connection
source .venv/bin/activate && python ib.py test connection

# View real-time logs
source .venv/bin/activate && python ib.py services logs

# Check recent data files
find ./ib-stream/storage -name "*.pb" -newermt "5 minutes ago" | wc -l
```

### Common Issues

**1. Persistent "Error 10189"**
- **Cause**: Multiple TWS sessions running
- **Solution**: Close competing TWS instances
- **Prevention**: Use dedicated server for ib-stream

**2. No data during market hours**
- **Cause**: Market data subscription issues
- **Solution**: Check IB account permissions and subscription status
- **Action**: Contact IB support if needed

**3. Connection timeouts**
- **Cause**: IB Gateway not running or port conflicts
- **Solution**: Verify IB Gateway is running on expected ports
- **Check**: `netstat -an | grep 4002`

## Performance Impact

### Resource Usage
- **CPU**: Minimal overhead (monitoring every 60 seconds)
- **Memory**: ~10MB additional for monitoring tasks
- **Network**: Negligible (status checks only)
- **Storage**: Debug logs reduced to minimal impact

### Recovery Time Targets
- **Detection**: 1-2 minutes
- **Stream restart**: 3-4 minutes  
- **Connection reset**: 5-6 minutes
- **Full recovery**: Typically under 5 minutes

## Best Practices

### Deployment
1. **Dedicated server**: Run ib-stream on dedicated hardware
2. **No competing TWS**: Don't run TWS on the same machine
3. **Stable network**: Ensure reliable network connectivity
4. **Monitor logs**: Set up log monitoring for Level 3+ warnings

### Development
1. **Test with conflicts**: Simulate TWS session conflicts
2. **Network testing**: Test with network interruptions
3. **Load testing**: Verify recovery under high data volumes
4. **Health monitoring**: Implement external health checks

## Version History

### v2.1 (Current)
- Enhanced auto-recovery with escalating actions
- Dual-state monitoring (socket + data flow)
- Tightened timing for active market monitoring
- Reduced log verbosity
- Comprehensive health endpoints

### v2.0
- Initial auto-recovery implementation  
- Basic connection monitoring
- Simple reconnection logic

---

**Note**: This auto-recovery system is designed for production trading environments where continuous data collection is critical. The aggressive timing and escalation ensure minimal data loss during market hours.