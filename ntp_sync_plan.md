# NTP Synchronization Plan for IB-Stream Trading System

## Current Status After CMOS Battery Replacement

### ✅ Fixed Issues:
- **Hardware Clock**: Now properly set to UTC  
- **System Time**: Synchronized with NTP servers
- **Time Drift**: Reduced from -17 hours to +11ms (ACCEPTABLE)
- **RTC Configuration**: `RTC in local TZ: no` (correct)

### 🔧 Root Cause Analysis:
The CMOS battery replacement caused the BIOS to reset the hardware clock to **local time** instead of **UTC**, causing a ~17-hour drift (system thought it was 2 AM when it was 7 PM).

## Automated NTP Synchronization Strategy

### 1. Current NTP Service Status

```bash
# Check what's currently running
systemctl status ntpsec          # Main NTP service
systemctl status systemd-timesyncd  # Systemd fallback (currently masked)
systemctl status chronyd        # Alternative NTP implementation
```

**Current State**: `ntpsec.service` is enabled and should be handling sync.

### 2. Recommended NTP Server Configuration

#### Primary NTP Servers (already implemented in our monitoring):
```
time.google.com          # Google's NTP (Stratum 1)
time.cloudflare.com      # Cloudflare NTP (Stratum 1) 
pool.ntp.org            # NTP Pool Project
time.nist.gov           # NIST official time
us.pool.ntp.org         # US-specific NTP pool
```

#### Configuration File: `/etc/ntp.conf` or `/etc/ntpsec/ntp.conf`
```
# Stratum 1 servers for maximum accuracy
server time.google.com iburst
server time.cloudflare.com iburst
server time.nist.gov iburst

# Pool servers for redundancy  
pool us.pool.ntp.org iburst
pool pool.ntp.org iburst

# Local clock as fallback (stratum 10)
server 127.127.1.0
fudge 127.127.1.0 stratum 10

# Security and access control
restrict default nomodify notrap nopeer noquery
restrict 127.0.0.1
restrict ::1

# Drift file for hardware clock compensation
driftfile /var/lib/ntp/ntp.drift
```

### 3. Enhanced Monitoring Integration

#### A. Automated Time Sync Monitoring
```bash
# Add to cron for continuous monitoring
*/5 * * * * /usr/local/bin/ib-time-monitor

# Create wrapper script
#!/bin/bash
# /usr/local/bin/ib-time-monitor
cd /home/seth/Software/dev/ib-stream
.venv/bin/python ib.py monitor time-drift --samples 2 --json >> /var/log/time-drift.log

# Check if drift is critical and auto-sync
DRIFT_MS=$(tail -1 /var/log/time-drift.log | jq -r '.mean_ms // 0')
if (( $(echo "$DRIFT_MS > 100 || $DRIFT_MS < -100" | bc -l) )); then
    logger "Critical time drift detected: ${DRIFT_MS}ms - syncing time"
    .venv/bin/python ib.py monitor sync-time
    sudo hwclock --systohc
fi
```

#### B. Service Health Integration
The `/system/health` endpoint should include:
- NTP service status
- Last successful sync time  
- Current drift measurements
- Hardware clock vs system clock comparison

### 4. Failsafe Mechanisms

#### A. Hardware Clock Validation
```bash
# Daily hardware clock check
0 6 * * * /usr/local/bin/check-hwclock

#!/bin/bash
# /usr/local/bin/check-hwclock
SYSTEM_UTC=$(date -u +%s)
HW_UTC=$(sudo hwclock --utc --get --unix)
DIFF=$((SYSTEM_UTC - HW_UTC))

if [ ${DIFF#-} -gt 10 ]; then
    logger "Hardware clock drift detected: ${DIFF}s - syncing"
    sudo hwclock --systohc
fi
```

#### B. NTP Service Watchdog
```bash
# Monitor NTP service health
*/10 * * * * /usr/local/bin/ntp-watchdog

#!/bin/bash
# /usr/local/bin/ntp-watchdog
if ! systemctl is-active --quiet ntpsec; then
    logger "NTP service down - restarting"
    sudo systemctl restart ntpsec
fi

# Check if NTP is actually syncing
if ! ntpq -p | grep -q "^\*"; then
    logger "NTP not syncing - restarting service"  
    sudo systemctl restart ntpsec
fi
```

### 5. Implementation Steps

#### Step 1: Configure NTP Service
```bash
# Ensure ntpsec is configured with proper servers
sudo systemctl enable ntpsec
sudo systemctl restart ntpsec

# Verify sync status
ntpq -p
```

#### Step 2: Deploy Monitoring Scripts
```bash
# Install monitoring scripts
sudo cp ib-time-monitor /usr/local/bin/
sudo cp check-hwclock /usr/local/bin/
sudo cp ntp-watchdog /usr/local/bin/
sudo chmod +x /usr/local/bin/{ib-time-monitor,check-hwclock,ntp-watchdog}

# Install cron jobs
sudo crontab -e
# Add the monitoring entries above
```

#### Step 3: Integrate with Service Health
- Enhance `/system/health` endpoint with NTP status
- Add time sync metrics to UptimeRobot monitoring
- Include hardware clock validation in health checks

### 6. Testing & Validation

#### A. Test Time Drift Detection
```bash
# Simulate time drift
sudo date -s "1 hour ago"
# Run monitoring - should detect and auto-correct
.venv/bin/python ib.py monitor time-drift

# Verify auto-sync works
.venv/bin/python ib.py monitor sync-time
```

#### B. Validate Hardware Clock Sync
```bash
# Check hardware clock maintains UTC after reboot
sudo hwclock --show --verbose
timedatectl status

# Verify drift stays minimal
.venv/bin/python ib.py monitor time-drift --samples 10
```

### 7. Long-term Monitoring

#### A. Drift Trend Analysis
- Log drift measurements every 5 minutes
- Generate weekly drift reports
- Alert on increasing drift trends (may indicate CMOS battery degradation)

#### B. Hardware Clock Health
- Monitor hardware clock vs system clock daily
- Track drift patterns to predict CMOS battery replacement needs
- Include in system maintenance documentation

## Expected Outcomes

### Immediate Benefits:
- Sub-50ms time accuracy for trading operations
- Automated correction of time drift
- Integration with existing health monitoring
- Early warning of hardware clock issues

### Long-term Benefits:
- Predictive maintenance for CMOS battery
- Historical time accuracy records
- Reliable market data timestamps
- Compliance with financial data regulations

## Success Metrics:
- **Time Drift**: < 10ms average, < 50ms maximum
- **Sync Frequency**: Every 5 minutes maximum
- **Uptime**: 99.9% NTP service availability
- **Detection Time**: < 5 minutes for critical drift
- **Recovery Time**: < 1 minute automatic correction