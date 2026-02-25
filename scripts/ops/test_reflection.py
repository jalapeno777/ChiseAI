#!/usr/bin/env python3
"""
Test script for reflection functionality.

This script demonstrates that the reflection module works correctly
by running all three loop types with mock storage.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Create mock src module to satisfy 'from src.xxx' imports
import types

src_module = types.ModuleType("src")
sys.modules["src"] = src_module

# Import governance and link it to src.governance
import governance as _real_governance

src_module.governance = _real_governance
sys.modules["src.governance"] = _real_governance

# Link all governance submodules
for _attr_name in dir(_real_governance):
    if not _attr_name.startswith("_"):
        _attr = getattr(_real_governance, _attr_name)
        if isinstance(_attr, types.ModuleType):
            setattr(src_module.governance, _attr_name, _attr)
            sys.modules[f"src.governance.{_attr_name}"] = _attr

from governance.reflection.artifacts import (
    KPISnapshot,
    FailureObservation,
    FailureType,
    Severity,
    RootCause,
    RootCauseCategory,
    ReflectionType,
)
from governance.reflection.loops import ReflectionLoops, ReflectionStorage


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self.data = {}

    def lpush(self, key, value):
        if key not in self.data:
            self.data[key] = []
        self.data[key].insert(0, value)

    def set(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def lrange(self, key, start, end):
        if key not in self.data:
            return []
        lst = self.data[key]
        if end == -1:
            return lst[start:]
        return lst[start : end + 1]

    def expire(self, key, seconds):
        pass

    def ping(self):
        return True


class MockQdrant:
    """Mock Qdrant client for testing."""

    def __init__(self):
        self.collections = {}

    def upsert(self, collection_name, points):
        if collection_name not in self.collections:
            self.collections[collection_name] = []
        self.collections[collection_name].extend(points)


def test_micro_reflection():
    """Test micro-reflection loop."""
    print("Testing micro-reflection...")

    mock_redis = MockRedis()
    loops = ReflectionLoops(redis_client=mock_redis)

    artifact = loops.micro_loop(
        story_id="ST-TEST-001",
        action="tool_call",
        result="success",
        duration_ms=150,
    )

    assert artifact.story_id == "ST-TEST-001"
    assert artifact.reflection_type == ReflectionType.MICRO
    assert "tool_call" in artifact.what_changed
    print("  ✓ Micro-reflection created successfully")

    # Verify stored in Redis
    key = ReflectionStorage.MICRO_KEY.format(story_id="ST-TEST-001")
    assert key in mock_redis.data
    print("  ✓ Micro-reflection stored in Redis")


def test_meso_reflection():
    """Test meso-reflection loop."""
    print("\nTesting meso-reflection...")

    mock_redis = MockRedis()
    mock_qdrant = MockQdrant()
    loops = ReflectionLoops(redis_client=mock_redis, qdrant_client=mock_qdrant)

    kpi = KPISnapshot(coverage=0.90, ci_pass_rate=0.96, test_count=50)
    artifact = loops.meso_loop(
        story_id="ST-TEST-001",
        what_changed="Story completed successfully",
        kpi_snapshot=kpi,
        failures_observed=[
            FailureObservation(
                type=FailureType.TEST_FAILURE,
                timestamp="2026-02-25T18:00:00Z",
                description="One test failed",
                severity=Severity.LOW,
            )
        ],
        root_causes=[
            RootCause(
                category=RootCauseCategory.TEST_COVERAGE,
                description="Edge case not covered",
            )
        ],
    )

    assert artifact.story_id == "ST-TEST-001"
    assert artifact.reflection_type == ReflectionType.MESO
    assert artifact.kpi_snapshot.coverage == 0.90
    print("  ✓ Meso-reflection created successfully")

    # Verify stored in Redis
    key = ReflectionStorage.MESO_KEY.format(story_id="ST-TEST-001")
    assert key in mock_redis.data
    print("  ✓ Meso-reflection stored in Redis")

    # Verify promoted to Qdrant (high coverage triggers promotion)
    assert "reflection_artifacts" in mock_qdrant.collections
    print("  ✓ Meso-reflection promoted to Qdrant")


def test_macro_reflection():
    """Test macro-reflection loop."""
    print("\nTesting macro-reflection...")

    mock_redis = MockRedis()
    mock_qdrant = MockQdrant()
    storage = ReflectionStorage(redis_client=mock_redis, qdrant_client=mock_qdrant)
    loops = ReflectionLoops(redis_client=mock_redis, qdrant_client=mock_qdrant)

    # First store some meso-reflections
    for story_id in ["ST-001", "ST-002"]:
        kpi = KPISnapshot(coverage=0.85, ci_pass_rate=0.95)
        storage.store_meso_reflection(
            story_id=story_id,
            what_changed=f"Story {story_id} completed",
            kpi_snapshot=kpi,
        )

    # Now run macro loop
    artifact = loops.macro_loop(
        period="daily",
        stories_completed=["ST-001", "ST-002"],
    )

    assert artifact.reflection_type == ReflectionType.MACRO
    assert "daily" in artifact.what_changed.lower()
    assert "ST-001" in artifact.what_changed
    assert "ST-002" in artifact.what_changed
    print("  ✓ Macro-reflection created successfully")

    # Verify stored in Redis
    from datetime import datetime, timezone

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = ReflectionStorage.MACRO_DAILY_KEY.format(date=date_str)
    assert key in mock_redis.data
    print("  ✓ Macro-reflection stored in Redis")

    # Verify promoted to Qdrant
    assert "reflection_artifacts" in mock_qdrant.collections
    print("  ✓ Macro-reflection promoted to Qdrant")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Reflection Module Test Suite")
    print("=" * 60)

    try:
        test_micro_reflection()
        test_meso_reflection()
        test_macro_reflection()

        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
