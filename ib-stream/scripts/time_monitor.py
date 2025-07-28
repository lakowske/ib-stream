#!/usr/bin/env python3
"""
Time Drift Monitor for IB Stream System

Monitors system time drift against NTP servers and logs discrepancies.
Particularly important for financial data timestamping accuracy.
"""

import asyncio
import datetime
import json
import logging
import socket
import struct
import time
from pathlib import Path
from typing import Optional, Dict, Any
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('time_monitor')

class TimeMonitor:
    """Monitor system time drift against authoritative sources"""
    
    def __init__(self, log_file: Path = None):
        self.log_file = log_file or Path("logs/time_drift.log")
        self.log_file.parent.mkdir(exist_ok=True)
        
        # Configure file logging
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(file_handler)
        
    async def get_ntp_time(self, server: str = 'pool.ntp.org') -> Optional[datetime.datetime]:
        """Get time from NTP server"""
        try:
            # Create NTP client
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(5)
            
            # NTP packet format
            packet = b'\x1b' + 47 * b'\0'
            
            # Send request
            client.sendto(packet, (server, 123))
            
            # Receive response
            data, _ = client.recvfrom(1024)
            client.close()
            
            # Extract timestamp (bytes 40-43 for seconds, 44-47 for fraction)
            unpacked = struct.unpack('!12I', data)
            timestamp = unpacked[10] + unpacked[11] / 2**32
            
            # Convert NTP timestamp (since 1900) to Unix timestamp (since 1970)
            unix_timestamp = timestamp - 2208988800
            
            return datetime.datetime.fromtimestamp(unix_timestamp, datetime.timezone.utc)
            
        except Exception as e:
            logger.error(f"Failed to get NTP time from {server}: {e}")
            return None
    
    async def get_system_time(self) -> datetime.datetime:
        """Get current system time in UTC"""
        return datetime.datetime.now(datetime.timezone.utc)
    
    async def check_time_drift(self) -> Dict[str, Any]:
        """Check time drift against multiple sources"""
        system_time = await self.get_system_time()
        
        results = {
            'timestamp': system_time.isoformat(),
            'system_time': system_time.isoformat(),
            'sources': {},
            'max_drift': 0,
            'status': 'unknown'
        }
        
        # Check multiple NTP servers
        ntp_servers = ['pool.ntp.org', 'time.nist.gov', 'time.google.com']
        
        for server in ntp_servers:
            ntp_time = await self.get_ntp_time(server)
            if ntp_time:
                drift = (system_time - ntp_time).total_seconds()
                results['sources'][server] = {
                    'time': ntp_time.isoformat(),
                    'drift_seconds': round(drift, 3)
                }
                results['max_drift'] = max(results['max_drift'], abs(drift))
        
        # Determine status
        if results['max_drift'] > 30:
            results['status'] = 'critical'
            logger.error(f"CRITICAL time drift: {results['max_drift']:.3f} seconds")
        elif results['max_drift'] > 5:
            results['status'] = 'warning'
            logger.warning(f"Notable time drift: {results['max_drift']:.3f} seconds")
        elif results['max_drift'] > 1:
            results['status'] = 'caution'
            logger.info(f"Minor time drift: {results['max_drift']:.3f} seconds")
        else:
            results['status'] = 'good'
            logger.info(f"Time sync good: {results['max_drift']:.3f} seconds drift")
        
        return results
    
    async def log_timestamp_comparison(self):
        """Log comparison of different timestamp sources (like in our data)"""
        system_time = await self.get_system_time()
        ntp_time = await self.get_ntp_time()
        
        if ntp_time:
            drift = (system_time - ntp_time).total_seconds()
            
            comparison = {
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'system_time_utc': system_time.isoformat(),
                'ntp_time_utc': ntp_time.isoformat(),
                'drift_seconds': round(drift, 3),
                'note': 'Similar to main_timestamp vs unix_timestamp discrepancy in stored data'
            }
            
            logger.info(f"Timestamp comparison: {json.dumps(comparison)}")
            return comparison
        
        return None
    
    async def monitor_continuously(self, interval_seconds: int = 300):
        """Monitor time drift continuously"""
        logger.info(f"Starting continuous time drift monitoring (interval: {interval_seconds}s)")
        
        while True:
            try:
                results = await self.check_time_drift()
                
                # Log to file
                with open(self.log_file.parent / "time_drift_data.jsonl", "a") as f:
                    f.write(json.dumps(results) + "\n")
                
                # Also log timestamp comparison
                await self.log_timestamp_comparison()
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            await asyncio.sleep(interval_seconds)

async def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Monitor system time drift')
    parser.add_argument('--check', action='store_true', help='Run single time check')
    parser.add_argument('--monitor', action='store_true', help='Start continuous monitoring')
    parser.add_argument('--interval', type=int, default=300, help='Monitoring interval in seconds')
    parser.add_argument('--log-file', type=str, help='Log file path')
    
    args = parser.parse_args()
    
    # Create monitor
    log_file = Path(args.log_file) if args.log_file else None
    monitor = TimeMonitor(log_file)
    
    if args.check:
        # Single check
        results = await monitor.check_time_drift()
        print(json.dumps(results, indent=2))
        
        # Also do timestamp comparison
        comparison = await monitor.log_timestamp_comparison()
        if comparison:
            print("\nTimestamp Comparison:")
            print(json.dumps(comparison, indent=2))
            
    elif args.monitor:
        # Continuous monitoring
        await monitor.monitor_continuously(args.interval)
    else:
        print("Use --check for single check or --monitor for continuous monitoring")

if __name__ == "__main__":
    asyncio.run(main())