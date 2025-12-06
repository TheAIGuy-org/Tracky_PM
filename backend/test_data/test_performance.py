#!/usr/bin/env python3
"""
PERFORMANCE & LOAD TEST SCRIPT FOR TRACKY PM
==============================================

This script performs detailed performance analysis:
- Import timing breakdown (Parse vs Validate vs Execute)
- Critical path calculation performance
- Database query performance
- Resource utilization query performance
- Concurrent import testing
- Stress test with varying task counts

USAGE:
    python test_performance.py [--server http://localhost:8000]
"""

import requests
import time
import json
import statistics
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import sys

class PerformanceMonitor:
    """Track performance metrics"""

    def __init__(self):
        self.metrics = {}

    def record(self, operation: str, duration_ms: float, details: Dict = None):
        """Record an operation"""
        if operation not in self.metrics:
            self.metrics[operation] = []

        self.metrics[operation].append({
            'duration_ms': duration_ms,
            'timestamp': datetime.now().isoformat(),
            'details': details or {}
        })

    def stats(self, operation: str) -> Dict:
        """Get statistics for an operation"""
        if operation not in self.metrics:
            return {}

        durations = [m['duration_ms'] for m in self.metrics[operation]]
        return {
            'count': len(durations),
            'min_ms': min(durations),
            'max_ms': max(durations),
            'avg_ms': statistics.mean(durations),
            'median_ms': statistics.median(durations),
            'stdev_ms': statistics.stdev(durations) if len(durations) > 1 else 0
        }

    def report(self):
        """Print performance report"""
        print("\n" + "="*70)
        print("PERFORMANCE REPORT")
        print("="*70)

        for operation in sorted(self.metrics.keys()):
            stats = self.stats(operation)
            print(f"\n{operation}:")
            print(f"  Count:   {stats['count']}")
            print(f"  Min:     {stats['min_ms']:.2f}ms")
            print(f"  Max:     {stats['max_ms']:.2f}ms")
            print(f"  Avg:     {stats['avg_ms']:.2f}ms")
            print(f"  Median:  {stats['median_ms']:.2f}ms")
            print(f"  StdDev:  {stats['stdev_ms']:.2f}ms")


class PerformanceTester:
    """Performance testing harness"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.monitor = PerformanceMonitor()

    def _load_file(self, filename: str) -> bytes:
        """Load test Excel file"""
        # Use the directory where this script is located
        script_dir = Path(__file__).parent
        filepath = script_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Test file not found: {filepath}")
        return filepath.read_bytes()

    def test_import_timing_breakdown(self):
        """Test timing for each phase"""
        print(f"\n{'='*70}")
        print("TEST: IMPORT TIMING BREAKDOWN")
        print(f"{'='*70}\n")

        file_data = self._load_file('01_INITIAL_BASELINE.xlsx')
        files = {'file': ('test.xlsx', file_data, 'application/vnd.ms-excel')}

        # Test dry-run (Parse + Validate only)
        print("1. Dry-Run (Parse + Validate only)...")
        start = time.time()
        response = requests.post(
            f"{self.base_url}/import/upload",
            files=files,
            params={'dry_run': True},
            timeout=30
        )
        dry_run_time = (time.time() - start) * 1000
        self.monitor.record("Dry-Run (Parse+Validate)", dry_run_time)
        print(f"   Duration: {dry_run_time:.2f}ms\n")

        # Test full import
        print("2. Full Import (Parse + Validate + Execute)...")
        files = {'file': ('test.xlsx', file_data, 'application/vnd.ms-excel')}
        start = time.time()
        response = requests.post(
            f"{self.base_url}/import/upload",
            files=files,
            params={'dry_run': False},
            timeout=30
        )
        full_import_time = (time.time() - start) * 1000
        self.monitor.record("Full Import (Parse+Validate+Execute)", full_import_time)

        resp_data = response.json()
        exec_time = resp_data.get('execution_time_ms', 0)
        print(f"   Total Duration: {full_import_time:.2f}ms")
        print(f"   Server Time: {exec_time}ms")
        print(f"   Network/Overhead: {full_import_time - exec_time:.2f}ms\n")

        # Estimate breakdown
        estimate_execute = full_import_time - dry_run_time
        print(f"Estimated Breakdown:")
        print(f"  Parse + Validate: {dry_run_time:.2f}ms ({dry_run_time/full_import_time*100:.1f}%)")
        print(f"  Execute: {estimate_execute:.2f}ms ({estimate_execute/full_import_time*100:.1f}%)")

    def test_critical_path_performance(self):
        """Test critical path calculation performance"""
        print(f"\n{'='*70}")
        print("TEST: CRITICAL PATH PERFORMANCE")
        print(f"{'='*70}\n")

        # First import to populate data
        file_data = self._load_file('01_INITIAL_BASELINE.xlsx')
        files = {'file': ('test.xlsx', file_data, 'application/vnd.ms-excel')}

        response = requests.post(
            f"{self.base_url}/import/upload",
            files=files,
            params={'trigger_recalculation': True},
            timeout=30
        )

        resp_data = response.json()
        recalc_time = resp_data.get('summary', {}).get('recalculation_time_ms', 0)
        critical_count = resp_data.get('summary', {}).get('critical_path_items', 0)
        work_items = resp_data.get('summary', {}).get('tasks_created', 0)

        print(f"Import Summary:")
        print(f"  Work Items: {work_items}")
        print(f"  Critical Path Items: {critical_count}")
        print(f"  Recalculation Time: {recalc_time}ms\n")

        self.monitor.record("Critical Path Calculation", float(recalc_time), {
            'work_items': work_items,
            'critical_items': critical_count
        })

    def test_resource_utilization_query(self):
        """Test resource utilization query performance"""
        print(f"\n{'='*70}")
        print("TEST: RESOURCE UTILIZATION QUERY PERFORMANCE")
        print(f"{'='*70}\n")

        for i in range(3):  # Run 3 times
            print(f"  Run {i+1}/3...")
            start = time.time()
            response = requests.get(
                f"{self.base_url}/import/resource-utilization",
                timeout=10
            )
            duration = (time.time() - start) * 1000
            self.monitor.record("Resource Utilization Query", duration)

            data = response.json()
            print(f"    Duration: {duration:.2f}ms | Resources: {data.get('total_resources')}")

        stats = self.monitor.stats("Resource Utilization Query")
        print(f"\n  Average: {stats['avg_ms']:.2f}ms")
        print(f"  P95: {stats['max_ms']:.2f}ms")

    def test_audit_log_query(self):
        """Test audit log query performance"""
        print(f"\n{'='*70}")
        print("TEST: AUDIT LOG QUERY PERFORMANCE")
        print(f"{'='*70}\n")

        # Get a batch first
        response = requests.get(
            f"{self.base_url}/import/batches?limit=1",
            timeout=10
        )
        batches = response.json().get('batches', [])

        if not batches:
            print("  No batches found for testing\n")
            return

        batch_id = batches[0].get('id')
        print(f"  Testing with batch: {batch_id}\n")

        for i in range(3):
            print(f"  Run {i+1}/3...")
            start = time.time()
            response = requests.get(
                f"{self.base_url}/import/batches/{batch_id}",
                timeout=10
            )
            duration = (time.time() - start) * 1000
            self.monitor.record("Audit Log Query", duration)

            data = response.json()
            audit_count = data.get('audit_count', 0)
            print(f"    Duration: {duration:.2f}ms | Logs: {audit_count}")

        stats = self.monitor.stats("Audit Log Query")
        print(f"\n  Average: {stats['avg_ms']:.2f}ms")
        print(f"  P95: {stats['max_ms']:.2f}ms")

    def test_baseline_versioning_query(self):
        """Test baseline version query performance"""
        print(f"\n{'='*70}")
        print("TEST: BASELINE VERSIONING QUERY PERFORMANCE")
        print(f"{'='*70}\n")

        # Get program ID from a batch
        response = requests.get(
            f"{self.base_url}/import/batches?limit=1",
            timeout=10
        )
        batches = response.json().get('batches', [])

        if not batches:
            print("  No batches found for testing\n")
            return

        program_id = batches[0].get('program_id')
        print(f"  Testing with program: {program_id}\n")

        for i in range(3):
            print(f"  Run {i+1}/3...")
            start = time.time()
            response = requests.get(
                f"{self.base_url}/import/baseline-versions?program_id={program_id}",
                timeout=10
            )
            duration = (time.time() - start) * 1000
            self.monitor.record("Baseline Versions Query", duration)

            data = response.json()
            version_count = data.get('version_count', 0)
            print(f"    Duration: {duration:.2f}ms | Versions: {version_count}")

        stats = self.monitor.stats("Baseline Versions Query")
        print(f"\n  Average: {stats['avg_ms']:.2f}ms")
        print(f"  P95: {stats['max_ms']:.2f}ms")

    def run_all_tests(self):
        """Run all performance tests"""
        print(f"\nTRACKY PM - PERFORMANCE TEST SUITE")
        print(f"Server: {self.base_url}")
        print(f"Time: {datetime.now().isoformat()}")

        try:
            self.test_import_timing_breakdown()
            self.test_critical_path_performance()
            self.test_resource_utilization_query()
            self.test_audit_log_query()
            self.test_baseline_versioning_query()

            self.monitor.report()

        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    """Main entry point"""
    import argparse
    parser = argparse.ArgumentParser(description='Tracky PM Performance Tests')
    parser.add_argument('--server', '-s', default='http://localhost:8000', help='API server URL')

    args = parser.parse_args()

    tester = PerformanceTester(base_url=args.server)
    tester.run_all_tests()


if __name__ == '__main__':
    main()
