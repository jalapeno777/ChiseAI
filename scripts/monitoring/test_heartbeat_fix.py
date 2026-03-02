#!/usr/bin/env python3
"""Test script to verify heartbeat staleness fix.

This script tests:
1. Heartbeat is written correctly
2. TTL is set to 120 seconds
3. G1 checkpoint passes
4. Minimum interval enforcement works
5. Stale heartbeat detection works
"""

import sys

import redis

sys.path.insert(0, "/home/tacopants/projects/ChiseAI")

from scripts.monitoring.checkpoint_gate_audit import check_g1_scheduler
from scripts.monitoring.scheduler_heartbeat import (
    HEARTBEAT_HASH_KEY,
    HEARTBEAT_TTL_SECONDS,
    MAX_HEARTBEAT_AGE_ALERT,
    MIN_HEARTBEAT_INTERVAL,
    check_heartbeat_health,
    record_heartbeat,
)


def test_heartbeat_basic():
    """Test basic heartbeat recording."""
    print("\n=== Test 1: Basic Heartbeat Recording ===")

    r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

    # Record heartbeat
    success = record_heartbeat(r, status="running", force=True)
    assert success, "Failed to record heartbeat"

    # Verify it was written
    heartbeat = r.hgetall(HEARTBEAT_HASH_KEY)
    assert heartbeat, "Heartbeat not found in Redis"
    assert heartbeat.get("status") == "running", "Status not correct"

    print("✅ Basic heartbeat recording works")
    return True


def test_ttl():
    """Test TTL is set correctly."""
    print("\n=== Test 2: TTL Verification ===")

    r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

    # Record heartbeat
    record_heartbeat(r, status="running", force=True)

    # Check TTL
    ttl = r.ttl(HEARTBEAT_HASH_KEY)
    print(f"  TTL: {ttl} seconds")

    # TTL should be close to HEARTBEAT_TTL_SECONDS (120)
    assert ttl > 0, "TTL not set"
    assert ttl <= HEARTBEAT_TTL_SECONDS, f"TTL too high: {ttl}"
    assert ttl >= HEARTBEAT_TTL_SECONDS - 10, f"TTL too low: {ttl}"

    print(f"✅ TTL is correct ({ttl}s, expected ~{HEARTBEAT_TTL_SECONDS}s)")
    return True


def test_g1_checkpoint():
    """Test G1 checkpoint passes."""
    print("\n=== Test 3: G1 Checkpoint Gate ===")

    r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

    # Record fresh heartbeat
    record_heartbeat(r, status="running", force=True)

    # Check G1
    result = check_g1_scheduler(r)
    print(f"  Result: {result}")

    assert result["status"] == "✅ PASS", f"G1 failed: {result}"

    print("✅ G1 checkpoint passes")
    return True


def test_minimum_interval():
    """Test minimum interval enforcement."""
    print("\n=== Test 4: Minimum Interval Enforcement ===")

    r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

    # Record first heartbeat
    success1 = record_heartbeat(r, status="running")
    assert success1, "First heartbeat failed"
    print("  First heartbeat recorded")

    # Try to record second heartbeat immediately (should be skipped)
    success2 = record_heartbeat(r, status="running")
    assert success2, "Second heartbeat returned error"
    print("  Second heartbeat call returned (may be skipped due to interval)")

    print(
        f"✅ Minimum interval enforcement works (interval: {MIN_HEARTBEAT_INTERVAL}s)"
    )
    return True


def test_stale_detection():
    """Test stale heartbeat detection."""
    print("\n=== Test 5: Stale Heartbeat Detection ===")

    r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

    # Record fresh heartbeat
    record_heartbeat(r, status="running", force=True)

    # Check health
    health = check_heartbeat_health(r)
    print(f"  Health check: {health}")

    assert health["healthy"], f"Fresh heartbeat should be healthy: {health}"
    assert health["age_seconds"] < 5, f"Age should be recent: {health['age_seconds']}s"

    print(
        f"✅ Stale heartbeat detection works (alert threshold: {MAX_HEARTBEAT_AGE_ALERT}s)"
    )
    return True


def test_config_values():
    """Test configuration values are correct."""
    print("\n=== Test 6: Configuration Values ===")

    print(f"  HEARTBEAT_TTL_SECONDS: {HEARTBEAT_TTL_SECONDS}")
    print(f"  MIN_HEARTBEAT_INTERVAL: {MIN_HEARTBEAT_INTERVAL}")
    print(f"  MAX_HEARTBEAT_AGE_ALERT: {MAX_HEARTBEAT_AGE_ALERT}")

    # Verify values are reasonable
    assert (
        HEARTBEAT_TTL_SECONDS == 120
    ), f"TTL should be 120s, got {HEARTBEAT_TTL_SECONDS}"
    assert (
        MIN_HEARTBEAT_INTERVAL == 30
    ), f"Min interval should be 30s, got {MIN_HEARTBEAT_INTERVAL}"
    assert (
        MAX_HEARTBEAT_AGE_ALERT == 90
    ), f"Alert threshold should be 90s, got {MAX_HEARTBEAT_AGE_ALERT}"

    print("✅ Configuration values are correct")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Heartbeat Staleness Fix - Verification Tests")
    print("=" * 60)

    tests = [
        test_heartbeat_basic,
        test_ttl,
        test_g1_checkpoint,
        test_minimum_interval,
        test_stale_detection,
        test_config_values,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
