"""
Time monitoring and synchronization utilities for ib-stream
Provides high-precision time drift monitoring and health checks
"""

import time
import socket
import struct
import statistics
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional, NamedTuple
import logging
from dataclasses import dataclass
from enum import Enum

# NTP packet format constants
NTP_PACKET_FORMAT = "!12I"
NTP_DELTA = 2208988800  # Seconds between 1900-01-01 and 1970-01-01
NTP_QUERY = b'\x1b' + 47 * b'\0'

# Time drift classification thresholds (milliseconds)
class TimeDriftThresholds:
    EXCELLENT_MS = 1.0
    GOOD_MS = 5.0
    ACCEPTABLE_MS = 50.0
    POOR_MS = 500.0

# High-quality NTP servers
DEFAULT_NTP_SERVERS = [
    'time.google.com',
    'time.cloudflare.com', 
    'pool.ntp.org',
    'time.nist.gov',
    'us.pool.ntp.org'
]

class TimeDriftStatus(Enum):
    """Time drift severity levels"""
    EXCELLENT = "excellent"  # < 1ms
    GOOD = "good"           # < 5ms
    ACCEPTABLE = "acceptable" # < 50ms
    POOR = "poor"           # < 500ms
    CRITICAL = "critical"   # >= 500ms

@dataclass
class TimeDriftMeasurement:
    """Single time drift measurement"""
    drift_ms: float
    rtt_ms: float
    server: str
    timestamp: datetime
    system_time: float
    ntp_time: float

@dataclass
class TimeDriftSummary:
    """Summary of time drift measurements"""
    mean_ms: float
    median_ms: float
    stdev_ms: float
    min_ms: float
    max_ms: float
    range_ms: float
    status: TimeDriftStatus
    successful_servers: int
    total_measurements: int
    timestamp: datetime

class TimeMonitor:
    """High-precision time drift monitoring"""
    
    def __init__(self, 
                 ntp_servers: Optional[List[str]] = None,
                 timeout: float = 2.0,
                 samples: int = 3):
        self.ntp_servers = ntp_servers or DEFAULT_NTP_SERVERS
        self.timeout = timeout
        self.samples = samples
        self.logger = logging.getLogger(__name__)

    def _query_ntp_server(self, server: str) -> Optional[Tuple[float, float]]:
        """Query NTP server and return (ntp_time, round_trip_delay)"""
        # Validate server name
        if not server or len(server) > 255:
            self.logger.warning(f"Invalid server name: {server}")
            return None
            
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(self.timeout)
                
                t1 = time.time()
                sock.sendto(NTP_QUERY, (server, 123))
                
                data, addr = sock.recvfrom(48)
                t4 = time.time()
            
            # Validate NTP response
            if len(data) != 48:
                self.logger.warning(f"Invalid NTP response length from {server}: {len(data)}")
                return None
            
            # Parse NTP response
            unpacked = struct.unpack(NTP_PACKET_FORMAT, data)
            
            # Validate NTP timestamp (should not be zero)
            if unpacked[10] == 0 and unpacked[11] == 0:
                self.logger.warning(f"Invalid NTP timestamp from {server}")
                return None
            
            t2_ntp = unpacked[10] + float(unpacked[11]) / 2**32
            ntp_time = t2_ntp - NTP_DELTA
            round_trip = t4 - t1
            
            # Validate calculated time is reasonable (not in far future/past)
            current_time = time.time()
            time_diff = abs(ntp_time - current_time)
            if time_diff > 86400:  # More than 24 hours difference
                self.logger.warning(f"Unreasonable time from {server}: {time_diff}s difference")
                return None
            
            # Validate round trip time is reasonable
            if round_trip < 0 or round_trip > 10:  # Negative or >10 second RTT
                self.logger.warning(f"Invalid round trip time from {server}: {round_trip}s")
                return None
            
            return ntp_time, round_trip
            
        except socket.timeout:
            self.logger.debug(f"Timeout querying {server} after {self.timeout}s")
            return None
        except socket.gaierror as e:
            self.logger.warning(f"DNS resolution failed for {server}: {e}")
            return None
        except struct.error as e:
            self.logger.warning(f"Failed to parse NTP response from {server}: {e}")
            return None
        except (OSError, ValueError) as e:
            self.logger.warning(f"Network error querying {server}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error querying {server}: {e}")
            return None

    def measure_drift_from_server(self, server: str) -> List[TimeDriftMeasurement]:
        """Measure time drift against specific NTP server with multiple samples"""
        measurements = []
        
        for _ in range(self.samples):
            result = self._query_ntp_server(server)
            if result is None:
                continue
                
            ntp_time, rtt = result
            system_time = time.time()
            drift_seconds = system_time - ntp_time
            
            measurements.append(TimeDriftMeasurement(
                drift_ms=drift_seconds * 1000,
                rtt_ms=rtt * 1000,
                server=server,
                timestamp=datetime.now(timezone.utc),
                system_time=system_time,
                ntp_time=ntp_time
            ))
            
            if len(measurements) < self.samples:
                time.sleep(0.1)  # Small delay between samples
        
        return measurements

    def measure_drift_summary(self) -> Optional[TimeDriftSummary]:
        """Measure drift against all servers and return summary"""
        all_measurements = []
        successful_servers = 0
        
        for server in self.ntp_servers:
            try:
                measurements = self.measure_drift_from_server(server)
                if measurements:
                    all_measurements.extend(measurements)
                    successful_servers += 1
            except Exception as e:
                self.logger.error(f"Failed to measure drift from {server}: {e}")
                continue
        
        # Require at least 2 servers for reliable statistics
        if len(all_measurements) < 2:
            self.logger.warning(f"Insufficient measurements: {len(all_measurements)} from {successful_servers} servers")
            return None
        
        drifts_ms = [m.drift_ms for m in all_measurements]
        
        # Filter out outliers (more than 3 standard deviations)
        if len(drifts_ms) > 3:
            try:
                mean_drift = statistics.mean(drifts_ms)
                stdev_drift = statistics.stdev(drifts_ms)
                
                filtered_drifts = []
                for drift in drifts_ms:
                    if abs(drift - mean_drift) <= 3 * stdev_drift:
                        filtered_drifts.append(drift)
                
                # Use filtered data if we have enough samples
                if len(filtered_drifts) >= len(drifts_ms) * 0.5:
                    drifts_ms = filtered_drifts
                    self.logger.debug(f"Filtered {len(all_measurements) - len(filtered_drifts)} outliers")
            except statistics.StatisticsError:
                # If we can't calculate statistics, use original data
                pass
        
        try:
            mean_ms = statistics.mean(drifts_ms)
            status = self._classify_drift_status(abs(mean_ms))
            
            return TimeDriftSummary(
                mean_ms=mean_ms,
                median_ms=statistics.median(drifts_ms),
                stdev_ms=statistics.stdev(drifts_ms) if len(drifts_ms) > 1 else 0,
                min_ms=min(drifts_ms),
                max_ms=max(drifts_ms),
                range_ms=max(drifts_ms) - min(drifts_ms),
                status=status,
                successful_servers=successful_servers,
                total_measurements=len(drifts_ms),
                timestamp=datetime.now(timezone.utc)
            )
        except statistics.StatisticsError as e:
            self.logger.error(f"Failed to calculate drift statistics: {e}")
            return None

    def _classify_drift_status(self, abs_drift_ms: float) -> TimeDriftStatus:
        """Classify drift severity"""
        if abs_drift_ms < TimeDriftThresholds.EXCELLENT_MS:
            return TimeDriftStatus.EXCELLENT
        elif abs_drift_ms < TimeDriftThresholds.GOOD_MS:
            return TimeDriftStatus.GOOD
        elif abs_drift_ms < TimeDriftThresholds.ACCEPTABLE_MS:
            return TimeDriftStatus.ACCEPTABLE
        elif abs_drift_ms < TimeDriftThresholds.POOR_MS:
            return TimeDriftStatus.POOR
        else:
            return TimeDriftStatus.CRITICAL


    def get_health_status(self) -> Dict:
        """Get time monitoring health status for health endpoints"""
        summary = self.measure_drift_summary()
        
        if summary is None:
            return {
                "time_sync": {
                    "status": "error",
                    "message": "Unable to measure time drift",
                    "drift_ms": None,
                    "precision_ms": None,
                    "servers_available": 0
                }
            }
        
        # Determine overall health status
        if summary.status in [TimeDriftStatus.EXCELLENT, TimeDriftStatus.GOOD]:
            status = "healthy"
        elif summary.status == TimeDriftStatus.ACCEPTABLE:
            status = "warning"
        else:
            status = "critical"
        
        return {
            "time_sync": {
                "status": status,
                "drift_ms": round(summary.mean_ms, 3),
                "precision_ms": round(summary.stdev_ms, 3),
                "range_ms": round(summary.range_ms, 3),
                "servers_available": summary.successful_servers,
                "total_servers": len(self.ntp_servers),
                "classification": summary.status.value,
                "timestamp": summary.timestamp.isoformat()
            }
        }

# Convenience functions for CLI and service integration
def get_time_drift_status(samples: int = 3, timeout: float = 2.0) -> Optional[TimeDriftSummary]:
    """Get current time drift status"""
    monitor = TimeMonitor(samples=samples, timeout=timeout)
    return monitor.measure_drift_summary()

def get_time_health_status() -> Dict:
    """Get time health status for health endpoints using Chrony's superior tracking"""
    try:
        # Use Chrony's built-in tracking - much more accurate than our NTP queries
        import subprocess
        result = subprocess.run(['chronyc', 'tracking'], capture_output=True, text=True, timeout=5)
        
        if result.returncode != 0:
            # Fallback to our NTP monitoring if Chrony unavailable
            monitor = TimeMonitor(samples=2, timeout=1.5)
            return monitor.get_health_status()
        
        # Parse Chrony tracking output
        lines = result.stdout.strip().split('\n')
        system_time_line = next((line for line in lines if 'System time' in line), None)
        
        if not system_time_line:
            # Fallback if parsing fails
            monitor = TimeMonitor(samples=2, timeout=1.5)
            return monitor.get_health_status()
        
        # Extract drift from "System time : 0.001580169 seconds fast of NTP time"
        parts = system_time_line.split(':')[1].strip().split()
        drift_seconds = float(parts[0])
        drift_ms = drift_seconds * 1000
        
        # Determine status based on Chrony's more accurate measurement
        if abs(drift_ms) < 1:
            status = "healthy"
            classification = "excellent"
        elif abs(drift_ms) < 5:
            status = "healthy" 
            classification = "good"
        elif abs(drift_ms) < 50:
            status = "warning"
            classification = "acceptable"
        else:
            status = "critical"
            classification = "poor"
        
        return {
            "time_sync": {
                "status": status,
                "drift_ms": round(drift_ms, 3),
                "precision_ms": "chrony_internal",
                "range_ms": None,
                "servers_available": "chrony_managed",
                "total_servers": "chrony_managed", 
                "classification": classification,
                "source": "chrony_tracking",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
        
    except Exception as e:
        # Fallback to original monitoring on any error
        monitor = TimeMonitor(samples=2, timeout=1.5)
        return monitor.get_health_status()

