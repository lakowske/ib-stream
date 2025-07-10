"""
Storage metrics collection for IB Stream.

Tracks storage performance, queue sizes, and error rates
for monitoring and optimization.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from collections import defaultdict, deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StorageStats:
    """Storage statistics for a single backend."""
    
    # Message counts
    messages_received: int = 0
    messages_queued: int = 0
    messages_written: int = 0
    messages_dropped: int = 0
    messages_errored: int = 0
    
    # Batch statistics
    batches_written: int = 0
    total_batch_time: float = 0.0
    max_batch_time: float = 0.0
    min_batch_time: float = float('inf')
    
    # File statistics
    files_created: int = 0
    bytes_written: int = 0
    
    # Time tracking
    last_write_time: float = 0.0
    start_time: float = field(default_factory=time.time)
    
    def get_avg_batch_time(self) -> float:
        """Get average batch write time."""
        if self.batches_written == 0:
            return 0.0
        return self.total_batch_time / self.batches_written
        
    def get_messages_per_second(self) -> float:
        """Get messages written per second."""
        elapsed = time.time() - self.start_time
        if elapsed == 0:
            return 0.0
        return self.messages_written / elapsed
        
    def get_bytes_per_second(self) -> float:
        """Get bytes written per second."""
        elapsed = time.time() - self.start_time
        if elapsed == 0:
            return 0.0
        return self.bytes_written / elapsed


class StorageMetrics:
    """
    Storage metrics collector and aggregator.
    
    Tracks performance metrics for all storage backends,
    maintains rolling windows for real-time monitoring.
    """
    
    def __init__(self, window_size: int = 100):
        """
        Initialize metrics collector.
        
        Args:
            window_size: Number of recent operations to track for rolling averages
        """
        self.window_size = window_size
        
        # Per-backend statistics
        self.backend_stats: Dict[str, StorageStats] = defaultdict(StorageStats)
        
        # Rolling windows for real-time metrics
        self.write_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        self.batch_sizes: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        self.queue_sizes: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        
        # Error tracking
        self.recent_errors: deque = deque(maxlen=100)
        
        # Overall stats
        self.start_time = time.time()
        
    def record_message_received(self):
        """Record that a message was received for storage."""
        for stats in self.backend_stats.values():
            stats.messages_received += 1
            
    def record_write_queued(self, backend: str):
        """Record that a message was queued for writing."""
        self.backend_stats[backend].messages_queued += 1
        
    def record_write_dropped(self, backend: str):
        """Record that a message was dropped due to queue full."""
        self.backend_stats[backend].messages_dropped += 1
        
    def record_batch_written(self, backend: str, batch_size: int, duration: float):
        """
        Record a successful batch write operation.
        
        Args:
            backend: Storage backend name
            batch_size: Number of messages in the batch
            duration: Time taken to write the batch in seconds
        """
        stats = self.backend_stats[backend]
        
        # Update batch statistics
        stats.batches_written += 1
        stats.messages_written += batch_size
        stats.total_batch_time += duration
        stats.max_batch_time = max(stats.max_batch_time, duration)
        stats.min_batch_time = min(stats.min_batch_time, duration)
        stats.last_write_time = time.time()
        
        # Update rolling windows
        self.write_times[backend].append(duration)
        self.batch_sizes[backend].append(batch_size)
        
    def record_write_error(self, backend: str, error_msg: str = ""):
        """
        Record a write error.
        
        Args:
            backend: Storage backend name
            error_msg: Error message
        """
        self.backend_stats[backend].messages_errored += 1
        
        # Track recent errors
        error_record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'backend': backend,
            'message': error_msg
        }
        self.recent_errors.append(error_record)
        
    def record_file_created(self, backend: str, file_size: int = 0):
        """
        Record that a new file was created.
        
        Args:
            backend: Storage backend name
            file_size: Size of the file in bytes
        """
        stats = self.backend_stats[backend]
        stats.files_created += 1
        stats.bytes_written += file_size
        
    def record_queue_size(self, backend: str, size: int):
        """
        Record current queue size for a backend.
        
        Args:
            backend: Storage backend name
            size: Current queue size
        """
        self.queue_sizes[backend].append(size)
        
    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive storage statistics.
        
        Returns:
            Dictionary containing all metrics
        """
        now = time.time()
        total_elapsed = now - self.start_time
        
        # Aggregate stats across all backends
        total_received = sum(stats.messages_received for stats in self.backend_stats.values())
        total_written = sum(stats.messages_written for stats in self.backend_stats.values())
        total_dropped = sum(stats.messages_dropped for stats in self.backend_stats.values())
        total_errored = sum(stats.messages_errored for stats in self.backend_stats.values())
        
        # Calculate overall rates
        overall_write_rate = total_written / total_elapsed if total_elapsed > 0 else 0.0
        overall_error_rate = total_errored / max(total_received, 1)
        overall_drop_rate = total_dropped / max(total_received, 1)
        
        # Per-backend statistics
        backend_details = {}
        for backend, stats in self.backend_stats.items():
            # Calculate rolling averages
            recent_write_times = list(self.write_times[backend])
            recent_batch_sizes = list(self.batch_sizes[backend])
            recent_queue_sizes = list(self.queue_sizes[backend])
            
            avg_write_time = sum(recent_write_times) / len(recent_write_times) if recent_write_times else 0.0
            avg_batch_size = sum(recent_batch_sizes) / len(recent_batch_sizes) if recent_batch_sizes else 0.0
            current_queue_size = recent_queue_sizes[-1] if recent_queue_sizes else 0
            avg_queue_size = sum(recent_queue_sizes) / len(recent_queue_sizes) if recent_queue_sizes else 0.0
            
            backend_details[backend] = {
                'messages': {
                    'received': stats.messages_received,
                    'written': stats.messages_written,
                    'dropped': stats.messages_dropped,
                    'errored': stats.messages_errored,
                    'success_rate': stats.messages_written / max(stats.messages_received, 1)
                },
                'performance': {
                    'messages_per_second': stats.get_messages_per_second(),
                    'bytes_per_second': stats.get_bytes_per_second(),
                    'avg_batch_time_ms': stats.get_avg_batch_time() * 1000,
                    'recent_avg_write_time_ms': avg_write_time * 1000,
                    'max_batch_time_ms': stats.max_batch_time * 1000,
                    'min_batch_time_ms': stats.min_batch_time * 1000 if stats.min_batch_time != float('inf') else 0.0
                },
                'batches': {
                    'total_batches': stats.batches_written,
                    'avg_batch_size': avg_batch_size,
                    'recent_batch_sizes': recent_batch_sizes[-10:]  # Last 10 batches
                },
                'files': {
                    'files_created': stats.files_created,
                    'bytes_written': stats.bytes_written,
                    'mb_written': round(stats.bytes_written / 1024 / 1024, 2)
                },
                'queue': {
                    'current_size': current_queue_size,
                    'avg_size': round(avg_queue_size, 1),
                    'max_size': max(recent_queue_sizes) if recent_queue_sizes else 0
                },
                'timing': {
                    'last_write_ago_seconds': now - stats.last_write_time if stats.last_write_time > 0 else None,
                    'uptime_seconds': now - stats.start_time
                }
            }
            
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'uptime_seconds': total_elapsed,
            'overall': {
                'messages_received': total_received,
                'messages_written': total_written,
                'messages_dropped': total_dropped,
                'messages_errored': total_errored,
                'write_rate_per_second': round(overall_write_rate, 2),
                'error_rate': round(overall_error_rate, 4),
                'drop_rate': round(overall_drop_rate, 4)
            },
            'backends': backend_details,
            'recent_errors': list(self.recent_errors)[-10:],  # Last 10 errors
            'health': self._calculate_health_score()
        }
        
    def _calculate_health_score(self) -> Dict[str, Any]:
        """
        Calculate an overall health score for the storage system.
        
        Returns:
            Health score and status information
        """
        score = 100.0
        issues = []
        
        # Check error rates
        for backend, stats in self.backend_stats.items():
            if stats.messages_received > 0:
                error_rate = stats.messages_errored / stats.messages_received
                drop_rate = stats.messages_dropped / stats.messages_received
                
                if error_rate > 0.05:  # 5% error rate
                    score -= 20
                    issues.append(f"{backend} has high error rate: {error_rate:.2%}")
                    
                if drop_rate > 0.01:  # 1% drop rate
                    score -= 15
                    issues.append(f"{backend} has high drop rate: {drop_rate:.2%}")
                    
        # Check queue sizes
        for backend, queue_sizes in self.queue_sizes.items():
            if queue_sizes:
                current_size = queue_sizes[-1]
                if current_size > 5000:  # Queue getting full
                    score -= 10
                    issues.append(f"{backend} queue size is high: {current_size}")
                    
        # Check write performance
        for backend, write_times in self.write_times.items():
            if write_times:
                avg_time = sum(write_times) / len(write_times)
                if avg_time > 1.0:  # Slow writes
                    score -= 10
                    issues.append(f"{backend} has slow writes: {avg_time:.2f}s")
                    
        # Determine status
        if score >= 90:
            status = "excellent"
        elif score >= 75:
            status = "good"
        elif score >= 50:
            status = "degraded"
        else:
            status = "poor"
            
        return {
            'score': max(0.0, score),
            'status': status,
            'issues': issues
        }
        
    def get_backend_stats(self, backend: str) -> Dict[str, Any]:
        """
        Get detailed statistics for a specific backend.
        
        Args:
            backend: Storage backend name
            
        Returns:
            Detailed statistics for the backend
        """
        if backend not in self.backend_stats:
            return {}
            
        stats = self.backend_stats[backend]
        write_times = list(self.write_times[backend])
        batch_sizes = list(self.batch_sizes[backend])
        queue_sizes = list(self.queue_sizes[backend])
        
        return {
            'backend': backend,
            'messages': {
                'received': stats.messages_received,
                'written': stats.messages_written,
                'dropped': stats.messages_dropped,
                'errored': stats.messages_errored
            },
            'performance': {
                'messages_per_second': stats.get_messages_per_second(),
                'bytes_per_second': stats.get_bytes_per_second(),
                'avg_batch_time': stats.get_avg_batch_time()
            },
            'recent_metrics': {
                'write_times': write_times,
                'batch_sizes': batch_sizes,
                'queue_sizes': queue_sizes
            }
        }
        
    def reset_stats(self, backend: str = None):
        """
        Reset statistics for a backend or all backends.
        
        Args:
            backend: Backend to reset, or None for all backends
        """
        if backend:
            if backend in self.backend_stats:
                self.backend_stats[backend] = StorageStats()
                self.write_times[backend].clear()
                self.batch_sizes[backend].clear()
                self.queue_sizes[backend].clear()
        else:
            self.backend_stats.clear()
            self.write_times.clear()
            self.batch_sizes.clear()
            self.queue_sizes.clear()
            self.recent_errors.clear()
            self.start_time = time.time()
            
        logger.info(f"Reset metrics for {backend or 'all backends'}")
        
    def export_metrics(self) -> List[Dict[str, Any]]:
        """
        Export metrics in a format suitable for external monitoring systems.
        
        Returns:
            List of metric records
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        metrics = []
        
        for backend, stats in self.backend_stats.items():
            base_labels = {'backend': backend}
            
            # Message metrics
            metrics.extend([
                {'name': 'storage_messages_received_total', 'value': stats.messages_received, 'labels': base_labels, 'timestamp': timestamp},
                {'name': 'storage_messages_written_total', 'value': stats.messages_written, 'labels': base_labels, 'timestamp': timestamp},
                {'name': 'storage_messages_dropped_total', 'value': stats.messages_dropped, 'labels': base_labels, 'timestamp': timestamp},
                {'name': 'storage_messages_errored_total', 'value': stats.messages_errored, 'labels': base_labels, 'timestamp': timestamp},
            ])
            
            # Performance metrics
            metrics.extend([
                {'name': 'storage_messages_per_second', 'value': stats.get_messages_per_second(), 'labels': base_labels, 'timestamp': timestamp},
                {'name': 'storage_bytes_per_second', 'value': stats.get_bytes_per_second(), 'labels': base_labels, 'timestamp': timestamp},
                {'name': 'storage_avg_batch_time_seconds', 'value': stats.get_avg_batch_time(), 'labels': base_labels, 'timestamp': timestamp},
            ])
            
            # Queue metrics
            if backend in self.queue_sizes and self.queue_sizes[backend]:
                queue_size = self.queue_sizes[backend][-1]
                metrics.append({
                    'name': 'storage_queue_size', 
                    'value': queue_size, 
                    'labels': base_labels, 
                    'timestamp': timestamp
                })
                
        return metrics