#!/usr/bin/env python3
"""Stress test for telemetry pipeline throughput.

ST-CONTROL-001: Telemetry Pipeline Throughput Remediation

Usage:
    python3 stress_test_e2e.py --duration 60 --target-eps 10000
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

# Add src to path
sys.path.insert(0, "/tmp/worktrees/ST-CONTROL-001-throughput-remediation-1/src")

from autonomous_control_plane.pipeline import TelemetryPipeline
from autonomous_control_plane.pipeline.ingestion import IngestionStatus


@dataclass
class StressTestResult:
    """Results from stress test."""

    duration_seconds: float
    target_eps: int
    total_events_sent: int
    total_events_accepted: int
    total_events_rejected: int
    errors: list[str] = field(default_factory=list)
    throughput_samples: list[tuple[float, float]] = field(default_factory=list)

    @property
    def actual_eps(self) -> float:
        """Calculate actual events per second."""
        if self.duration_seconds <= 0:
            return 0.0
        return self.total_events_accepted / self.duration_seconds

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.total_events_sent
        if total == 0:
            return 0.0
        return (self.total_events_accepted / total) * 100

    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        return 100 - self.success_rate

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "duration_seconds": self.duration_seconds,
            "target_eps": self.target_eps,
            "total_events_sent": self.total_events_sent,
            "total_events_accepted": self.total_events_accepted,
            "total_events_rejected": self.total_events_rejected,
            "actual_eps": round(self.actual_eps, 2),
            "success_rate_percent": round(self.success_rate, 2),
            "error_rate_percent": round(self.error_rate, 2),
            "errors": self.errors,
            "throughput_samples": self.throughput_samples,
        }


def run_stress_test(duration_seconds: int, target_eps: int) -> StressTestResult:
    """Run stress test against telemetry pipeline.

    Args:
        duration_seconds: How long to run the test
        target_eps: Target events per second

    Returns:
        StressTestResult with test metrics
    """
    print(f"Starting stress test: {duration_seconds}s at {target_eps} eps target")

    # Create and start pipeline
    pipeline = TelemetryPipeline()
    if not pipeline.start():
        return StressTestResult(
            duration_seconds=0,
            target_eps=target_eps,
            total_events_sent=0,
            total_events_accepted=0,
            total_events_rejected=0,
            errors=["Failed to start pipeline"],
        )

    result = StressTestResult(
        duration_seconds=float(duration_seconds),
        target_eps=target_eps,
        total_events_sent=0,
        total_events_accepted=0,
        total_events_rejected=0,
    )

    try:
        start_time = time.time()
        end_time = start_time + duration_seconds
        batch_size = 100
        batch_interval = batch_size / target_eps if target_eps > 0 else 0.01

        print(
            f"Sending events in batches of {batch_size}, interval {batch_interval:.4f}s"
        )

        # Send events until duration expires
        sample_time = start_time
        sample_events = 0

        while time.time() < end_time:
            batch_start = time.time()

            # Send batch of events
            for i in range(batch_size):
                result.total_events_sent += 1
                ingest_result = pipeline.ingest_log(
                    {
                        "message": f"Stress test event {result.total_events_sent}",
                        "level": "info",
                        "test": True,
                        "timestamp": time.time(),
                    }
                )

                if ingest_result.status == IngestionStatus.ACCEPTED:
                    result.total_events_accepted += 1
                    sample_events += 1
                else:
                    result.total_events_rejected += 1

            # Calculate and record throughput sample every second
            now = time.time()
            if now - sample_time >= 1.0:
                eps = sample_events / (now - sample_time)
                result.throughput_samples.append((now - start_time, eps))
                print(f"  [{now - start_time:.1f}s] Throughput: {eps:.0f} eps")
                sample_time = now
                sample_events = 0

            # Sleep to maintain target rate
            elapsed = time.time() - batch_start
            sleep_time = batch_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Final metrics
        actual_duration = time.time() - start_time
        result.duration_seconds = actual_duration

        # Wait for pipeline to process remaining events
        print("Waiting for pipeline to process remaining events...")
        time.sleep(2.0)

        # Get pipeline metrics
        pipeline_metrics = pipeline.get_metrics()
        print(f"\nPipeline metrics: {pipeline_metrics}")

    except Exception as e:
        result.errors.append(f"Test error: {e}")
        print(f"Error during test: {e}")

    finally:
        pipeline.stop()

    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Stress test telemetry pipeline")
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Test duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--target-eps",
        type=int,
        default=10000,
        help="Target events per second (default: 10000)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("TELEMETRY PIPELINE STRESS TEST")
    print("=" * 60)
    print(f"Duration: {args.duration}s")
    print(f"Target EPS: {args.target_eps}")
    print("=" * 60)

    result = run_stress_test(args.duration, args.target_eps)

    print("\n" + "=" * 60)
    print("STRESS TEST RESULTS")
    print("=" * 60)
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"Target EPS: {result.target_eps}")
    print(f"Events Sent: {result.total_events_sent}")
    print(f"Events Accepted: {result.total_events_accepted}")
    print(f"Events Rejected: {result.total_events_rejected}")
    print(f"Actual EPS: {result.actual_eps:.2f}")
    print(f"Success Rate: {result.success_rate:.2f}%")
    print(f"Error Rate: {result.error_rate:.2f}%")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  - {error}")

    # Success criteria check
    print("\n" + "=" * 60)
    print("SUCCESS CRITERIA CHECK")
    print("=" * 60)

    success = True

    if result.actual_eps >= 10000:
        print(f"✓ Throughput >= 10,000 eps: {result.actual_eps:.2f} eps")
    else:
        print(f"✗ Throughput >= 10,000 eps: {result.actual_eps:.2f} eps (FAILED)")
        success = False

    if result.error_rate < 0.1:
        print(f"✓ Error rate < 0.1%: {result.error_rate:.4f}%")
    else:
        print(f"✗ Error rate < 0.1%: {result.error_rate:.4f}% (FAILED)")
        success = False

    print("=" * 60)

    if success:
        print("\n✓ ALL SUCCESS CRITERIA MET")
        return 0
    else:
        print("\n✗ SOME CRITERIA NOT MET")
        return 1


if __name__ == "__main__":
    sys.exit(main())
