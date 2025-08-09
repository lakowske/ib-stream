"""
Storage monitoring utilities for ib-stream
Provides monitoring of data streaming and storage file growth
"""

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, NamedTuple, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import json

logger = logging.getLogger(__name__)

class StorageStatus(Enum):
    """Storage system status levels"""
    ACTIVE = "active"        # Files growing within last minute
    STALE = "stale"          # Files exist but not growing
    MISSING = "missing"      # No files found
    ERROR = "error"          # Error accessing storage

@dataclass
class FileInfo:
    """Information about a storage file"""
    path: Path
    size_bytes: int
    modified_time: datetime
    age_seconds: float

@dataclass
class StorageFileSet:
    """Information about current hour's storage files"""
    hour_path: Path
    files: List[FileInfo]
    total_size_bytes: int
    newest_file_age: float
    oldest_file_age: float
    status: StorageStatus

class StorageMonitor:
    """Monitor storage system health and data streaming"""
    
    def __init__(self, storage_base_path: Path):
        self.storage_base_path = Path(storage_base_path)
        self.logger = logging.getLogger(__name__)

    def get_current_hour_files(self, version: str = "v2", format_type: str = "protobuf") -> StorageFileSet:
        """Get information about current hour's storage files"""
        # Validate inputs
        if not version or not format_type:
            raise ValueError("Version and format_type cannot be empty")
        
        if version not in ["v2", "v3"]:
            raise ValueError(f"Invalid version: {version}. Must be 'v2' or 'v3'")
            
        if format_type not in ["protobuf", "json"]:
            raise ValueError(f"Invalid format_type: {format_type}. Must be 'protobuf' or 'json'")
        
        now = datetime.now()
        current_hour_path = (
            self.storage_base_path / 
            version / 
            format_type / 
            f"{now.year:04d}" / 
            f"{now.month:02d}" / 
            f"{now.day:02d}" / 
            f"{now.hour:02d}"
        )
        
        try:
            if not current_hour_path.exists():
                return StorageFileSet(
                    hour_path=current_hour_path,
                    files=[],
                    total_size_bytes=0,
                    newest_file_age=float('inf'),
                    oldest_file_age=float('inf'),
                    status=StorageStatus.MISSING
                )
            
            files = []
            current_time = time.time()
            
            for file_path in current_hour_path.glob("*.pb"):
                try:
                    stat = file_path.stat()
                    modified_time = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                    age_seconds = current_time - stat.st_mtime
                    
                    files.append(FileInfo(
                        path=file_path,
                        size_bytes=stat.st_size,
                        modified_time=modified_time,
                        age_seconds=age_seconds
                    ))
                except OSError as e:
                    self.logger.warning(f"Error accessing file {file_path}: {e}")
            
            if not files:
                status = StorageStatus.MISSING
                newest_age = oldest_age = float('inf')
            else:
                files.sort(key=lambda f: f.age_seconds)
                newest_age = files[0].age_seconds  # Most recently modified
                oldest_age = files[-1].age_seconds # Least recently modified
                
                # Determine status based on newest file age
                if newest_age < 60:  # Modified within last minute
                    status = StorageStatus.ACTIVE
                elif newest_age < 300:  # Modified within last 5 minutes
                    status = StorageStatus.STALE
                else:
                    status = StorageStatus.STALE
            
            total_size = sum(f.size_bytes for f in files)
            
            return StorageFileSet(
                hour_path=current_hour_path,
                files=files,
                total_size_bytes=total_size,
                newest_file_age=newest_age,
                oldest_file_age=oldest_age,
                status=status
            )
            
        except Exception as e:
            self.logger.error(f"Error monitoring storage files: {e}")
            return StorageFileSet(
                hour_path=current_hour_path,
                files=[],
                total_size_bytes=0,
                newest_file_age=float('inf'),
                oldest_file_age=float('inf'),
                status=StorageStatus.ERROR
            )

    def get_storage_health(self) -> Dict:
        """Get comprehensive storage health status"""
        v2_files = self.get_current_hour_files("v2", "protobuf")
        v3_files = self.get_current_hour_files("v3", "protobuf")
        
        # Determine overall storage status
        if v2_files.status == StorageStatus.ACTIVE or v3_files.status == StorageStatus.ACTIVE:
            overall_status = "healthy"
        elif v2_files.status == StorageStatus.STALE or v3_files.status == StorageStatus.STALE:
            overall_status = "warning"
        else:
            overall_status = "critical"
        
        return {
            "storage_streaming": {
                "status": overall_status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "current_hour": datetime.now().strftime("%Y-%m-%d %H:00"),
                "formats": {
                    "v2_protobuf": {
                        "status": v2_files.status.value,
                        "files_count": len(v2_files.files),
                        "total_size_mb": round(v2_files.total_size_bytes / 1024 / 1024, 2),
                        "newest_file_age_seconds": round(v2_files.newest_file_age, 1) if v2_files.newest_file_age != float('inf') else None,
                        "hour_path": str(v2_files.hour_path)
                    },
                    "v3_protobuf": {
                        "status": v3_files.status.value,
                        "files_count": len(v3_files.files),
                        "total_size_mb": round(v3_files.total_size_bytes / 1024 / 1024, 2),
                        "newest_file_age_seconds": round(v3_files.newest_file_age, 1) if v3_files.newest_file_age != float('inf') else None,
                        "hour_path": str(v3_files.hour_path)
                    }
                }
            }
        }

    def monitor_file_growth(self, duration_seconds: int = 60, check_interval: int = 5) -> Dict:
        """Monitor file growth over a specified duration"""
        initial_v2 = self.get_current_hour_files("v2", "protobuf")
        initial_v3 = self.get_current_hour_files("v3", "protobuf")
        
        initial_time = time.time()
        checks = []
        
        self.logger.info(f"Monitoring storage growth for {duration_seconds} seconds...")
        
        while time.time() - initial_time < duration_seconds:
            time.sleep(check_interval)
            
            current_v2 = self.get_current_hour_files("v2", "protobuf")
            current_v3 = self.get_current_hour_files("v3", "protobuf")
            
            check_time = time.time()
            elapsed = check_time - initial_time
            
            checks.append({
                "elapsed_seconds": round(elapsed, 1),
                "timestamp": datetime.fromtimestamp(check_time, timezone.utc).isoformat(),
                "v2_size_mb": round(current_v2.total_size_bytes / 1024 / 1024, 2),
                "v3_size_mb": round(current_v3.total_size_bytes / 1024 / 1024, 2),
                "v2_files": len(current_v2.files),
                "v3_files": len(current_v3.files)
            })
        
        final_v2 = self.get_current_hour_files("v2", "protobuf") 
        final_v3 = self.get_current_hour_files("v3", "protobuf")
        
        # Calculate growth metrics
        v2_growth_bytes = final_v2.total_size_bytes - initial_v2.total_size_bytes
        v3_growth_bytes = final_v3.total_size_bytes - initial_v3.total_size_bytes
        
        growth_rate_v2_mb_per_min = (v2_growth_bytes / 1024 / 1024) / (duration_seconds / 60)
        growth_rate_v3_mb_per_min = (v3_growth_bytes / 1024 / 1024) / (duration_seconds / 60)
        
        # Determine if streaming is active
        is_streaming = v2_growth_bytes > 0 or v3_growth_bytes > 0
        
        return {
            "monitoring_duration_seconds": duration_seconds,
            "check_interval_seconds": check_interval,
            "checks_performed": len(checks),
            "is_streaming": is_streaming,
            "growth_summary": {
                "v2_protobuf": {
                    "initial_size_mb": round(initial_v2.total_size_bytes / 1024 / 1024, 2),
                    "final_size_mb": round(final_v2.total_size_bytes / 1024 / 1024, 2),
                    "growth_mb": round(v2_growth_bytes / 1024 / 1024, 2),
                    "growth_rate_mb_per_minute": round(growth_rate_v2_mb_per_min, 2),
                    "file_count_change": len(final_v2.files) - len(initial_v2.files)
                },
                "v3_protobuf": {
                    "initial_size_mb": round(initial_v3.total_size_bytes / 1024 / 1024, 2),
                    "final_size_mb": round(final_v3.total_size_bytes / 1024 / 1024, 2),
                    "growth_mb": round(v3_growth_bytes / 1024 / 1024, 2),
                    "growth_rate_mb_per_minute": round(growth_rate_v3_mb_per_min, 2),
                    "file_count_change": len(final_v3.files) - len(initial_v3.files)
                }
            },
            "detailed_checks": checks
        }

    def get_recent_activity_summary(self, hours_back: int = 1) -> Dict:
        """Get summary of recent storage activity across multiple hours"""
        now = datetime.now()
        summaries = []
        
        for hour_offset in range(hours_back + 1):
            check_time = now.replace(minute=0, second=0, microsecond=0)
            check_time = check_time.replace(hour=now.hour - hour_offset)
            
            if check_time < now.replace(hour=0):  # Don't go back to previous day
                break
                
            hour_path_v2 = (
                self.storage_base_path / 
                "v2" / 
                "protobuf" / 
                f"{check_time.year:04d}" / 
                f"{check_time.month:02d}" / 
                f"{check_time.day:02d}" / 
                f"{check_time.hour:02d}"
            )
            
            if hour_path_v2.exists():
                files = list(hour_path_v2.glob("*.pb"))
                total_size = sum(f.stat().st_size for f in files if f.exists())
                
                summaries.append({
                    "hour": check_time.strftime("%Y-%m-%d %H:00"),
                    "files_count": len(files),
                    "total_size_mb": round(total_size / 1024 / 1024, 2),
                    "is_current_hour": hour_offset == 0
                })
        
        return {
            "hours_checked": len(summaries),
            "activity_summary": summaries
        }

# Convenience functions for CLI and service integration
def get_storage_health_status(storage_path: str = "ib-stream/storage") -> Dict:
    """Get storage health status for health endpoints"""
    monitor = StorageMonitor(Path(storage_path))
    return monitor.get_storage_health()

def monitor_storage_growth(storage_path: str = "ib-stream/storage", 
                         duration_seconds: int = 60) -> Dict:
    """Monitor storage file growth for specified duration"""
    monitor = StorageMonitor(Path(storage_path))
    return monitor.monitor_file_growth(duration_seconds)

def get_current_hour_status(storage_path: str = "ib-stream/storage") -> Dict:
    """Get current hour storage file status"""
    monitor = StorageMonitor(Path(storage_path))
    v2_files = monitor.get_current_hour_files("v2", "protobuf")
    v3_files = monitor.get_current_hour_files("v3", "protobuf")
    
    return {
        "current_hour": datetime.now().strftime("%Y-%m-%d %H:00"),
        "v2_protobuf": {
            "files": len(v2_files.files),
            "size_mb": round(v2_files.total_size_bytes / 1024 / 1024, 2),
            "status": v2_files.status.value,
            "newest_age_seconds": round(v2_files.newest_file_age, 1) if v2_files.newest_file_age != float('inf') else None
        },
        "v3_protobuf": {
            "files": len(v3_files.files),
            "size_mb": round(v3_files.total_size_bytes / 1024 / 1024, 2),
            "status": v3_files.status.value,
            "newest_age_seconds": round(v3_files.newest_file_age, 1) if v3_files.newest_file_age != float('inf') else None
        }
    }