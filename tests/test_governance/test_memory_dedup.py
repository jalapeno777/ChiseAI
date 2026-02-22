"""
Tests for Memory Deduplication Engine.

This module tests the MemoryDeduplicationEngine class including:
- Basic instantiation
- Feature flag behavior
- Configuration loading
- Deduplication stubs
- Statistics tracking
"""

import pytest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from src.governance.memory.deduplication import (
    MemoryDeduplicationEngine,
    DeduplicationConfig,
    DeduplicationStats,
    FEATURE_FLAG_KEY,
)


class TestDeduplicationConfig:
    """Tests for DeduplicationConfig dataclass."""

    def test_default_config_values(self):
        """Verify default configuration values."""
        config = DeduplicationConfig()

        assert config.similarity_threshold == 0.95
        assert config.max_age_days == 30
        assert config.batch_size == 100
        assert config.dry_run is True  # Safe default
        assert config.min_duplicates == 2
        assert config.config_prefix == "chise:governance:dedup:config"

    def test_custom_config_values(self):
        """Verify custom configuration values are applied."""
        config = DeduplicationConfig(
            similarity_threshold=0.8,
            max_age_days=7,
            batch_size=50,
            dry_run=False,
        )

        assert config.similarity_threshold == 0.8
        assert config.max_age_days == 7
        assert config.batch_size == 50
        assert config.dry_run is False


class TestDeduplicationStats:
    """Tests for DeduplicationStats dataclass."""

    def test_default_stats_values(self):
        """Verify default statistics values."""
        stats = DeduplicationStats()

        assert stats.entries_scanned == 0
        assert stats.duplicate_groups == 0
        assert stats.entries_to_remove == 0
        assert stats.entries_removed == 0
        assert stats.bytes_saved == 0
        assert stats.processing_time_seconds == 0.0
        assert stats.was_dry_run is True
        assert stats.error is None

    def test_stats_timestamp_auto_generated(self):
        """Verify timestamp is auto-generated."""
        before = datetime.now(UTC)
        stats = DeduplicationStats()
        after = datetime.now(UTC)

        assert before <= stats.timestamp <= after


class TestMemoryDeduplicationEngine:
    """Tests for MemoryDeduplicationEngine class."""

    def test_basic_instantiation(self):
        """Test basic engine instantiation without clients."""
        engine = MemoryDeduplicationEngine()

        assert engine is not None
        assert engine.get_config() is not None
        assert engine.is_enabled() is False  # Disabled by default

    def test_instantiation_with_custom_config(self):
        """Test engine instantiation with custom configuration."""
        config = DeduplicationConfig(
            similarity_threshold=0.9,
            dry_run=False,
        )
        engine = MemoryDeduplicationEngine(config=config)

        assert engine.get_config().similarity_threshold == 0.9
        assert engine.get_config().dry_run is False

    def test_feature_flag_disabled_by_default(self):
        """Test that engine is disabled by default (safe rollout)."""
        engine = MemoryDeduplicationEngine()

        # Without Redis client, should default to disabled
        assert engine.is_enabled() is False

    def test_feature_flag_disabled_without_redis(self):
        """Test that engine stays disabled when Redis is unavailable."""
        engine = MemoryDeduplicationEngine()

        # Multiple calls should consistently return False
        assert engine.is_enabled() is False
        assert engine.is_enabled() is False

    def test_get_stats_returns_none_initially(self):
        """Test that get_stats returns None before any deduplication run."""
        engine = MemoryDeduplicationEngine()

        assert engine.get_stats() is None

    def test_deduplicate_returns_stats(self):
        """Test that deduplicate returns valid statistics."""
        engine = MemoryDeduplicationEngine()
        stats = engine.deduplicate()

        assert stats is not None
        assert isinstance(stats, DeduplicationStats)
        assert stats.was_dry_run is True  # Default config

    def test_deduplicate_dry_run_override(self):
        """Test that dry_run can be overridden in deduplicate call."""
        engine = MemoryDeduplicationEngine()

        # Override to False
        stats = engine.deduplicate(dry_run=False)
        assert stats.was_dry_run is False

        # Override to True
        stats = engine.deduplicate(dry_run=True)
        assert stats.was_dry_run is True

    def test_deduplicate_updates_last_stats(self):
        """Test that deduplicate updates the last stats."""
        engine = MemoryDeduplicationEngine()

        stats = engine.deduplicate()
        assert engine.get_stats() is stats

    def test_deduplicate_blocked_when_disabled_and_not_dry_run(self):
        """Test that actual deduplication is blocked when disabled."""
        config = DeduplicationConfig(dry_run=False)
        engine = MemoryDeduplicationEngine(config=config)

        # Engine is disabled, so non-dry-run should fail
        stats = engine.deduplicate(dry_run=False)

        assert stats.error is not None
        assert "disabled" in stats.error.lower()

    def test_dry_run_allowed_when_disabled(self):
        """Test that dry run is allowed even when engine is disabled."""
        engine = MemoryDeduplicationEngine()

        # Engine is disabled, but dry run should work
        stats = engine.deduplicate(dry_run=True)

        assert stats.error is None


class TestImportPaths:
    """Tests for correct import paths."""

    def test_import_from_deduplication_module(self):
        """Test importing from the deduplication module."""
        from src.governance.memory.deduplication import MemoryDeduplicationEngine

        engine = MemoryDeduplicationEngine()
        assert engine is not None

    def test_import_from_memory_package(self):
        """Test importing from the memory package."""
        from src.governance.memory import MemoryDeduplicationEngine

        engine = MemoryDeduplicationEngine()
        assert engine is not None

    def test_import_from_governance_package(self):
        """Test importing from the governance package."""
        from src.governance import MemoryDeduplicationEngine

        engine = MemoryDeduplicationEngine()
        assert engine is not None

    def test_feature_flag_key_constant(self):
        """Test that feature flag key is correctly defined."""
        assert FEATURE_FLAG_KEY == "chise:feature_flags:governance:memory_dedup_enabled"


class TestEnableDisable:
    """Tests for enable/disable functionality."""

    def test_disable_sets_enabled_to_false(self):
        """Test that disable() sets enabled to False."""
        engine = MemoryDeduplicationEngine()

        # First check to cache the value
        engine.is_enabled()
        engine.disable()

        # Should return False after disable
        assert engine.is_enabled() is False

    def test_enable_returns_false_without_redis(self):
        """Test that enable() returns False without Redis client."""
        engine = MemoryDeduplicationEngine()

        result = engine.enable()
        assert result is False


# TODO: Add integration tests with mock Redis/Qdrant clients
# TODO: Add tests for actual deduplication logic once implemented
# TODO: Add tests for error handling and edge cases
