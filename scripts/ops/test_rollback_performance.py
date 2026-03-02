#!/usr/bin/env python3
"""Rollback performance test script.

CRITICAL: Rollback must complete in <5 minutes (target: <2 minutes).

This script tests the rollback performance to ensure it meets the
acceptance criteria for ST-LAUNCH-013.

Usage:
    python scripts/ops/test_rollback_performance.py
"""

import asyncio
import importlib.util
import os
import sys
import time
from typing import Any, cast
from unittest.mock import MagicMock


# Direct import of the module file to avoid package import issues
def load_module_directly(module_name: str, file_path: str):
    """Load a module directly from file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Could not load module spec for {module_name} at {file_path}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Determine paths
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
src_path = os.path.join(project_root, "src")
model_rollback_path = os.path.join(src_path, "ml", "rollback", "model_rollback.py")


# First, set up minimal dependencies
# Create mock modules for external dependencies
class MockModule:
    def __getattr__(self, name):
        return MagicMock()


# Mock InfluxDB client
sys.modules["influxdb_client"] = cast(Any, MockModule())
sys.modules["influxdb_client.client"] = cast(Any, MockModule())
sys.modules["influxdb_client.client.write"] = cast(Any, MockModule())
sys.modules["influxdb_client.client.write.point"] = cast(Any, MockModule())
sys.modules["aiohttp"] = cast(Any, MockModule())

# Now load the model_rollback module
model_rollback = load_module_directly("ml.rollback.model_rollback", model_rollback_path)

InMemoryAuditStorage = model_rollback.InMemoryAuditStorage
RollbackConfig = model_rollback.RollbackConfig
RollbackManager = model_rollback.RollbackManager
RollbackTrigger = model_rollback.RollbackTrigger


def create_mock_registry():
    """Create mock model registry for testing."""
    registry = MagicMock()

    # Mock version
    version = MagicMock()
    version.version_id = "model_v2"
    version.model_type = MagicMock()
    version.model_type.value = "signal_predictor"

    # Mock target version
    target = MagicMock()
    target.version_id = "model_v1"

    registry.get_version.return_value = version
    registry.get_rollback_target.return_value = target
    registry.mark_failed.return_value = version
    registry.promote_to_champion.return_value = (target, version)

    return registry


async def test_rollback_performance():
    """Test rollback performance with timing."""
    print("=" * 60)
    print("Rollback Performance Test")
    print("=" * 60)
    print()

    # Test configurations
    configs = [
        ("Target (<2 minutes)", RollbackConfig(max_rollback_time_seconds=120.0)),
        ("Maximum (5 minutes)", RollbackConfig(max_rollback_time_seconds=300.0)),
    ]

    results = []

    for name, config in configs:
        print(f"\nTesting: {name}")
        print("-" * 40)

        registry = create_mock_registry()
        storage = InMemoryAuditStorage()
        manager = RollbackManager(
            registry=registry,
            config=config,
            audit_storage=storage,
        )

        # Measure rollback time
        start_time = time.time()

        event = await manager.execute_rollback(
            failed_version_id="model_v2",
            trigger=RollbackTrigger.DEGRADATION,
            reason="Performance degradation test",
        )

        elapsed = time.time() - start_time

        # Record results
        result = {
            "name": name,
            "elapsed": elapsed,
            "event_duration": event.duration_seconds,
            "status": event.status.value,
            "config_max": config.max_rollback_time_seconds,
            "passed": elapsed < config.max_rollback_time_seconds,
        }
        results.append(result)

        print(f"  Elapsed time: {elapsed:.4f}s")
        print(f"  Event duration: {event.duration_seconds:.4f}s")
        print(f"  Status: {event.status.value}")
        print(f"  Max allowed: {config.max_rollback_time_seconds}s")
        print(f"  Passed: {'✓' if result['passed'] else '✗'}")

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    all_passed = all(r["passed"] for r in results)

    for r in results:
        status = "✓ PASS" if r["passed"] else "✗ FAIL"
        print(f"  {r['name']}: {status} ({r['elapsed']:.4f}s)")

    print()

    if all_passed:
        print("✓ All rollback performance tests passed!")
        return 0
    else:
        print("✗ Some rollback performance tests failed!")
        return 1


async def test_rollback_stress():
    """Test multiple rapid rollbacks."""
    print("\n" + "=" * 60)
    print("Rollback Stress Test (10 rapid rollbacks)")
    print("=" * 60)
    print()

    registry = create_mock_registry()
    storage = InMemoryAuditStorage()
    manager = RollbackManager(
        registry=registry,
        config=RollbackConfig(max_rollback_time_seconds=120.0),
        audit_storage=storage,
    )

    times = []

    for i in range(10):
        start = time.time()

        event = await manager.execute_rollback(
            failed_version_id=f"model_v{i}",
            trigger=RollbackTrigger.MANUAL,
            reason=f"Stress test rollback {i}",
        )

        elapsed = time.time() - start
        times.append(elapsed)

        print(f"  Rollback {i + 1}: {elapsed:.4f}s - {event.status.value}")

    avg_time = sum(times) / len(times)
    max_time = max(times)
    min_time = min(times)

    print()
    print(f"  Average: {avg_time:.4f}s")
    print(f"  Min: {min_time:.4f}s")
    print(f"  Max: {max_time:.4f}s")
    print(f"  All under 2 minutes: {'✓' if max_time < 120 else '✗'}")
    print()

    return 0 if max_time < 120 else 1


def main():
    """Run all performance tests."""
    print()
    print("ST-LAUNCH-013: Rollback Performance Test")
    print("CRITICAL: Rollback must complete in <5 minutes (target: <2 minutes)")
    print()

    # Run tests
    result1 = asyncio.run(test_rollback_performance())
    result2 = asyncio.run(test_rollback_stress())

    # Exit code
    exit_code = max(result1, result2)

    if exit_code == 0:
        print("\n✓ All performance tests passed!")
    else:
        print("\n✗ Some performance tests failed!")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
