"""
Latency Tracking Utilities
Tracks performance across Qu API, Deepgram, and UI layers
"""

import time
import json
import os
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict

# Log file location
LOG_FILE = os.path.join(os.path.dirname(__file__), "latency_logs.txt")

class LatencyTracker:
    """
    Centralized latency tracking for all system components
    """
    
    def __init__(self):
        self.metrics: Dict[str, List[float]] = defaultdict(list)
        self.current_timers: Dict[str, float] = {}
        
    def start_timer(self, operation: str) -> float:
        """Start timing an operation"""
        start_time = time.time()
        self.current_timers[operation] = start_time
        return start_time
    
    def end_timer(self, operation: str, metadata: Optional[Dict] = None) -> float:
        """End timing and record latency"""
        if operation not in self.current_timers:
            self._write_log("ERROR", f"No start time found for operation: {operation}")
            return 0.0
        
        start_time = self.current_timers.pop(operation)
        latency = (time.time() - start_time) * 1000  # Convert to ms
        
        # Record the metric
        self.metrics[operation].append(latency)
        
        # Write to log file
        self._write_log("LATENCY", operation, latency, metadata)
        
        return latency
    
    def _write_log(self, log_type: str, operation: str, latency: float = None, metadata: Optional[Dict] = None):
        """Write a log entry to the log file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Include milliseconds
        
        if latency is not None:
            log_line = f"{timestamp} | {log_type} | {operation} | {latency:.2f}ms"
            if metadata:
                # Format metadata as key=value pairs
                meta_str = " | ".join([f"{k}={v}" for k, v in metadata.items()])
                log_line += f" | {meta_str}"
        else:
            log_line = f"{timestamp} | {log_type} | {operation}"
        
        # Append to log file
        try:
            with open(LOG_FILE, 'a') as f:
                f.write(log_line + "\n")
        except Exception as e:
            print(f"Failed to write to log file: {e}")
    
    def get_stats(self, operation: str) -> Dict:
        """Get statistics for an operation"""
        if operation not in self.metrics or not self.metrics[operation]:
            return {
                "operation": operation,
                "count": 0,
                "avg_ms": 0,
                "min_ms": 0,
                "max_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0
            }
        
        latencies = sorted(self.metrics[operation])
        count = len(latencies)
        
        return {
            "operation": operation,
            "count": count,
            "avg_ms": round(sum(latencies) / count, 2),
            "min_ms": round(min(latencies), 2),
            "max_ms": round(max(latencies), 2),
            "p95_ms": round(latencies[int(count * 0.95)] if count > 0 else 0, 2),
            "p99_ms": round(latencies[int(count * 0.99)] if count > 0 else 0, 2)
        }
    
    def get_all_stats(self) -> List[Dict]:
        """Get statistics for all operations"""
        return [self.get_stats(op) for op in self.metrics.keys()]
    
    def print_summary(self):
        """Print a summary of all latency metrics"""
        print("\n" + "="*80)
        print("📊 LATENCY SUMMARY")
        print("="*80)
        
        for op in sorted(self.metrics.keys()):
            stats = self.get_stats(op)
            print(f"\n{op}:")
            print(f"  Count: {stats['count']}")
            print(f"  Avg: {stats['avg_ms']}ms | Min: {stats['min_ms']}ms | Max: {stats['max_ms']}ms")
            print(f"  P95: {stats['p95_ms']}ms | P99: {stats['p99_ms']}ms")
        
        print("="*80 + "\n")
    
    def reset(self):
        """Reset all metrics"""
        self.metrics.clear()
        self.current_timers.clear()


# Global singleton
_tracker = LatencyTracker()

def get_tracker() -> LatencyTracker:
    """Get the global latency tracker instance"""
    return _tracker


# Convenience functions
def start_timer(operation: str) -> float:
    """Start timing an operation"""
    return _tracker.start_timer(operation)

def end_timer(operation: str, metadata: Optional[Dict] = None) -> float:
    """End timing and record latency"""
    return _tracker.end_timer(operation, metadata)

def get_stats(operation: str) -> Dict:
    """Get statistics for an operation"""
    return _tracker.get_stats(operation)

def get_all_stats() -> List[Dict]:
    """Get statistics for all operations"""
    return _tracker.get_all_stats()

def print_summary():
    """Print a summary of all latency metrics"""
    _tracker.print_summary()

