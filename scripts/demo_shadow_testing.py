#!/usr/bin/env python3
"""
Shadow Testing Demonstration Script

ST-CHISE-001.2: Demonstrates shadow testing with <100ms latency overhead requirement.

This script shows how to use the ShadowTester to compare a candidate brain
version against a baseline, measuring latency overhead and validating that
it stays within the 100ms threshold.
"""

import asyncio
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.brain.shadow_testing import (
    ShadowTestConfig,
    ShadowTester,
    run_shadow_test,
)
from src.brain.version import BrainVersion

from config.bootstrap import bootstrap


async def fast_brain(input_data):
    """Simulates a fast brain with ~1ms latency."""
    await asyncio.sleep(0.001)
    return {"prediction": "buy", "confidence": 0.85, "latency_tier": "fast"}


async def medium_brain(input_data):
    """Simulates a medium brain with ~5ms latency."""
    await asyncio.sleep(0.005)
    return {"prediction": "buy", "confidence": 0.87, "latency_tier": "medium"}


async def slow_brain(input_data):
    """Simulates a slow brain with ~150ms latency."""
    await asyncio.sleep(0.15)
    return {"prediction": "sell", "confidence": 0.90, "latency_tier": "slow"}


async def demo_passing_shadow_test():
    """Demonstrates a shadow test that passes (<100ms overhead)."""
    print("=" * 70)
    print("DEMO 1: Shadow Test with Acceptable Latency")
    print("=" * 70)
    print()

    # Create versions
    candidate_version = BrainVersion(major=2, minor=0, patch=0)
    baseline_version = BrainVersion(major=1, minor=5, patch=3)

    # Create test inputs
    test_inputs = [
        {"symbol": "BTCUSDT", "price": 50000.0, "volume": 1000.0},
        {"symbol": "ETHUSDT", "price": 3000.0, "volume": 5000.0},
        {"symbol": "SOLUSDT", "price": 100.0, "volume": 10000.0},
    ]

    # Configure shadow test with 100ms threshold
    config = ShadowTestConfig(
        candidate_version=candidate_version,
        baseline_version=baseline_version,
        max_latency_overhead_ms=100.0,  # 100ms threshold
        sample_size=3,
        parallel_enabled=True,
        warmup_iterations=1,
        measurement_iterations=3,
    )

    # Create tester with medium candidate vs fast baseline
    # This should pass since the overhead is within 100ms
    tester = ShadowTester(config, medium_brain, fast_brain)
    result = await tester.run_shadow_test(test_inputs)

    print(f"Candidate Version: {candidate_version}")
    print(f"Baseline Version: {baseline_version}")
    print(f"Max Latency Threshold: {config.max_latency_overhead_ms}%")
    print()
    print(f"Test Result: {'✅ PASSED' if result.passed else '❌ FAILED'}")
    print(f"Latency Overhead: {result.latency_overhead_ms:.2f}%")
    print()
    print("Latency Statistics:")
    print(
        f"  Candidate - Mean: {result.candidate_latency_ms.mean_ms:.2f}ms, "
        f"P50: {result.candidate_latency_ms.p50_ms:.2f}ms, "
        f"P95: {result.candidate_latency_ms.p95_ms:.2f}ms, "
        f"P99: {result.candidate_latency_ms.p99_ms:.2f}ms"
    )
    print(
        f"  Baseline  - Mean: {result.baseline_latency_ms.mean_ms:.2f}ms, "
        f"P50: {result.baseline_latency_ms.p50_ms:.2f}ms, "
        f"P95: {result.baseline_latency_ms.p95_ms:.2f}ms, "
        f"P99: {result.baseline_latency_ms.p99_ms:.2f}ms"
    )
    print()
    print(f"Predictions tested: {len(result.candidate_predictions)}")
    print()


async def demo_failing_shadow_test():
    """Demonstrates a shadow test that fails (>100ms overhead)."""
    print("=" * 70)
    print("DEMO 2: Shadow Test with Excessive Latency")
    print("=" * 70)
    print()

    candidate_version = BrainVersion(major=2, minor=0, patch=0)
    baseline_version = BrainVersion(major=1, minor=5, patch=3)

    test_inputs = [
        {"symbol": "BTCUSDT", "price": 50000.0},
        {"symbol": "ETHUSDT", "price": 3000.0},
    ]

    config = ShadowTestConfig(
        candidate_version=candidate_version,
        baseline_version=baseline_version,
        max_latency_overhead_ms=100.0,  # 100ms threshold
        sample_size=2,
        parallel_enabled=True,
        warmup_iterations=0,
        measurement_iterations=2,
    )

    # Create tester with slow candidate vs fast baseline
    # This should fail since the overhead exceeds 100ms
    tester = ShadowTester(config, slow_brain, fast_brain)
    result = await tester.run_shadow_test(test_inputs)

    print(f"Candidate Version: {candidate_version}")
    print(f"Baseline Version: {baseline_version}")
    print(f"Max Latency Threshold: {config.max_latency_overhead_ms}%")
    print()
    print(f"Test Result: {'✅ PASSED' if result.passed else '❌ FAILED'}")
    print(f"Latency Overhead: {result.latency_overhead_ms:.2f}%")
    print()
    print("Latency Statistics:")
    print(
        f"  Candidate - Mean: {result.candidate_latency_ms.mean_ms:.2f}ms, "
        f"StdDev: {result.candidate_latency_ms.std_ms:.2f}ms"
    )
    print(
        f"  Baseline  - Mean: {result.baseline_latency_ms.mean_ms:.2f}ms, "
        f"StdDev: {result.baseline_latency_ms.std_ms:.2f}ms"
    )
    print()
    print(f"Error Message: {result.error_message}")
    print()


async def demo_convenience_function():
    """Demonstrates using the convenience function."""
    print("=" * 70)
    print("DEMO 3: Using Convenience Function")
    print("=" * 70)
    print()

    test_inputs = [
        {"symbol": "BTCUSDT", "price": 50000.0},
        {"symbol": "ETHUSDT", "price": 3000.0},
        {"symbol": "SOLUSDT", "price": 100.0},
    ]

    result = await run_shadow_test(
        candidate_version=BrainVersion(2, 0, 0),
        baseline_version=BrainVersion(1, 5, 3),
        candidate_brain=fast_brain,
        baseline_brain=fast_brain,
        inputs=test_inputs,
        max_latency_overhead_ms=100.0,
        sample_size=3,
        parallel_enabled=True,
    )

    print("Using run_shadow_test() convenience function:")
    print(f"  Result: {'✅ PASSED' if result.passed else '❌ FAILED'}")
    print(f"  Overhead: {result.latency_overhead_ms:.2f}%")
    print(f"  Candidate Mean: {result.candidate_latency_ms.mean_ms:.2f}ms")
    print(f"  Baseline Mean: {result.baseline_latency_ms.mean_ms:.2f}ms")
    print()


async def main():
    """Run all demonstrations."""
    # Bootstrap environment first
    bootstrap(load_env=True)

    print()
    print("*" * 70)
    print("SHADOW TESTING DEMONSTRATION")
    print("ST-CHISE-001.2: Shadow Testing with Latency Measurement")
    print("*" * 70)
    print()

    await demo_passing_shadow_test()
    await demo_failing_shadow_test()
    await demo_convenience_function()

    print("=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print()
    print("Key Takeaways:")
    print("  • Shadow tests measure latency overhead between candidate and baseline")
    print("  • Tests pass when overhead is within the configured threshold (100ms)")
    print("  • Statistical measurements include p50, p95, p99, mean, and std dev")
    print("  • Results include predictions from both versions for comparison")
    print()


if __name__ == "__main__":
    asyncio.run(main())
