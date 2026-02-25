#!/usr/bin/env python3
"""
Verification script for ST-MEMORY-002 Memory Stewardship Automation.

This script verifies the implementation by directly loading modules from files
to avoid circular imports in the existing governance package.
"""

import sys
import importlib.util
from pathlib import Path


# Load modules directly from files
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


src_path = Path(__file__).parent.parent.parent.parent / "src"

# Load deduplication
dedup = load_module(
    "deduplication", src_path / "governance" / "memory" / "deduplication.py"
)

# Load promotion
promo = load_module("promotion", src_path / "governance" / "memory" / "promotion.py")

# Load contradiction
contr = load_module(
    "contradiction", src_path / "governance" / "memory" / "contradiction.py"
)

# Load sweep
sweep = load_module("sweep", src_path / "governance" / "memory" / "sweep.py")

# Extract classes
MemoryDeduplicationEngine = dedup.MemoryDeduplicationEngine
DeduplicationConfig = dedup.DeduplicationConfig

MemoryPromotionEngine = promo.MemoryPromotionEngine
PromotionConfig = promo.PromotionConfig
MemoryEntry = promo.MemoryEntry
MemoryCategory = promo.MemoryCategory
PromotionRule = promo.PromotionRule

ContradictionDetector = contr.ContradictionDetector
ContradictionConfig = contr.ContradictionConfig
Contradiction = contr.Contradiction

MemorySweepEngine = sweep.MemorySweepEngine
SweepConfig = sweep.SweepConfig


def test_memory_categories():
    """Test MemoryCategory enum."""
    print("Testing MemoryCategory...")
    assert MemoryCategory.INVARIANT.value == "invariant"
    assert MemoryCategory.DECISION.value == "decision"
    assert MemoryCategory.PATTERN.value == "pattern"
    assert MemoryCategory.POSTMORTEM.value == "postmortem"
    assert MemoryCategory.METRIC.value == "metric"
    assert MemoryCategory.RESEARCH.value == "research"
    print("  ✓ All categories correct")


def test_promotion_rules():
    """Test PromotionRule enum."""
    print("Testing PromotionRule...")
    assert PromotionRule.IMMEDIATE.value == "immediate"
    assert PromotionRule.OCCURRENCES.value == "occurrences"
    assert PromotionRule.CI_IMPACT.value == "ci_impact"
    print("  ✓ All rules correct")


def test_memory_entry():
    """Test MemoryEntry creation and methods."""
    print("Testing MemoryEntry...")
    from datetime import UTC, datetime

    entry = MemoryEntry(
        id="test-123",
        content="Test content",
        category=MemoryCategory.DECISION,
        story_id="ST-TEST-001",
        agent="test-agent",
        timestamp=datetime.now(UTC),
    )

    assert entry.id == "test-123"
    assert entry.content == "Test content"

    # Test hash computation
    hash1 = entry.compute_hash()
    hash2 = entry.compute_hash()
    assert hash1 == hash2
    assert len(hash1) == 32

    # Test payload conversion
    payload = entry.to_qdrant_payload()
    assert payload["content"] == "Test content"
    assert payload["category"] == "decision"

    print("  ✓ MemoryEntry working correctly")


def test_promotion_config():
    """Test PromotionConfig."""
    print("Testing PromotionConfig...")

    config = PromotionConfig()

    assert config.similarity_threshold == 0.92
    assert config.min_occurrences == 2
    assert config.dry_run is True

    # Test category config
    invariant_config = config.get_category_config(MemoryCategory.INVARIANT)
    assert invariant_config.get("promotion_rule") == "immediate"

    metric_config = config.get_category_config(MemoryCategory.METRIC)
    assert metric_config.get("storage") == "redis"

    print("  ✓ PromotionConfig working correctly")


def test_promotion_engine():
    """Test MemoryPromotionEngine."""
    print("Testing MemoryPromotionEngine...")

    engine = MemoryPromotionEngine()

    # Test disabled by default
    assert engine.is_enabled() is False

    # Test promotion rules
    from datetime import UTC, datetime

    # Immediate promotion
    invariant_entry = MemoryEntry(
        id="test-1",
        content="Test",
        category=MemoryCategory.INVARIANT,
        story_id="ST-TEST",
        agent="test",
        timestamp=datetime.now(UTC),
    )
    should_promote, reason = engine.should_promote(invariant_entry)
    assert should_promote is True
    assert reason == "immediate_promotion"

    # Aggregate only - should not promote
    metric_entry = MemoryEntry(
        id="test-2",
        content="Test",
        category=MemoryCategory.METRIC,
        story_id="ST-TEST",
        agent="test",
        timestamp=datetime.now(UTC),
    )
    should_promote, reason = engine.should_promote(metric_entry)
    assert should_promote is False
    assert reason == "aggregate_only"

    # Occurrence-based promotion
    decision_entry = MemoryEntry(
        id="test-3",
        content="Test",
        category=MemoryCategory.DECISION,
        story_id="ST-TEST",
        agent="test",
        timestamp=datetime.now(UTC),
        occurrence_count=2,
    )
    should_promote, reason = engine.should_promote(decision_entry)
    assert should_promote is True
    assert reason == "duplicate_clustering"

    # CI impact promotion
    pattern_entry = MemoryEntry(
        id="test-4",
        content="Test",
        category=MemoryCategory.PATTERN,
        story_id="ST-TEST",
        agent="test",
        timestamp=datetime.now(UTC),
        ci_failure=True,
    )
    should_promote, reason = engine.should_promote(pattern_entry)
    assert should_promote is True
    assert reason == "ci_impact"

    print("  ✓ MemoryPromotionEngine working correctly")


def test_contradiction_detector():
    """Test ContradictionDetector."""
    print("Testing ContradictionDetector...")

    detector = ContradictionDetector()

    # Test enabled by default
    assert detector.is_enabled() is True

    # Test keyword detection
    content = "This contradicts the previous approach"
    keywords = detector.check_keywords(content)
    assert "contradicts" in keywords

    # Test similarity computation
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [0.0, 1.0, 0.0]
    similarity = detector.compute_similarity(vec1, vec2)
    assert similarity == 0.0  # Orthogonal vectors

    vec3 = [1.0, 0.0, 0.0]
    similarity = detector.compute_similarity(vec1, vec3)
    assert similarity == 1.0  # Identical vectors

    # Test contradiction detection with vectors in the right similarity range
    memory_1 = {
        "id": "mem-1",
        "content": "Use approach A",
        # Vectors with ~0.89 similarity
        "vector": [0.669, 0.703, 0.201, 0.134],
    }
    memory_2 = {
        "id": "mem-2",
        "content": "This contradicts previous advice, use approach B",
        "vector": [0.502, 0.574, 0.610, 0.215],
    }

    contradiction = detector.detect_contradiction(memory_1, memory_2)
    assert contradiction is not None
    assert contradiction.severity == "high"

    print("  ✓ ContradictionDetector working correctly")


def test_sweep_config():
    """Test SweepConfig."""
    print("Testing SweepConfig...")

    config = SweepConfig()

    assert config.dry_run is True
    assert config.max_memories_per_sweep == 1000

    # Test TTL for permanent category
    ttl = config.get_ttl_for_category(MemoryCategory.INVARIANT)
    assert ttl is None  # Permanent

    # Test TTL for ephemeral category
    ttl = config.get_ttl_for_category(MemoryCategory.METRIC)
    assert ttl is not None
    assert ttl > 0

    print("  ✓ SweepConfig working correctly")


def test_sweep_engine():
    """Test MemorySweepEngine."""
    print("Testing MemorySweepEngine...")

    engine = MemorySweepEngine()

    # Test disabled by default
    assert engine.is_enabled() is False

    # Test category inference
    assert (
        engine._infer_category_from_key("story:incident:123")
        == MemoryCategory.POSTMORTEM
    )
    assert (
        engine._infer_category_from_key("story:decision:123") == MemoryCategory.DECISION
    )
    assert (
        engine._infer_category_from_key("story:other:123") == MemoryCategory.DECISION
    )  # Default

    print("  ✓ MemorySweepEngine working correctly")


def test_deduplication_engine():
    """Test MemoryDeduplicationEngine."""
    print("Testing MemoryDeduplicationEngine...")

    engine = MemoryDeduplicationEngine()

    # Test disabled by default
    assert engine.is_enabled() is False

    # Test config
    assert engine._config.similarity_threshold == 0.95

    print("  ✓ MemoryDeduplicationEngine working correctly")


def main():
    """Run all tests."""
    print("=" * 60)
    print("ST-MEMORY-002 Memory Stewardship Verification")
    print("=" * 60)
    print()

    tests = [
        test_memory_categories,
        test_promotion_rules,
        test_memory_entry,
        test_promotion_config,
        test_promotion_engine,
        test_contradiction_detector,
        test_sweep_config,
        test_sweep_engine,
        test_deduplication_engine,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__} failed: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
