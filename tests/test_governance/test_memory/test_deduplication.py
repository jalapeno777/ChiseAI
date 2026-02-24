"""
Tests for Memory Deduplication Engine - B3 Implementation.

This module tests the B3 subtasks:
- B3.1: Redis Config Loading
- B3.2: Deduplication Logic
- B3.3: Feature Flag Integration
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.governance.memory.deduplication import (
    CONFIG_KEY,
    FEATURE_FLAG_KEY,
    HASH_PREFIX,
    DeduplicationConfig,
    DeduplicationStats,
    MemoryDeduplicationEngine,
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


class TestB31RedisConfigLoading:
    """Tests for B3.1: Redis Config Loading."""

    def test_load_redis_config_returns_defaults_without_redis(self):
        """Test that _load_redis_config returns defaults when no Redis client."""
        engine = MemoryDeduplicationEngine()
        config = engine._load_redis_config()

        assert config["enabled"] is False
        assert config["threshold"] == 0.95
        assert config["ttl"] == 86400

    def test_load_redis_config_from_redis(self):
        """Test loading config from Redis."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(
            {"enabled": True, "threshold": 0.85, "ttl": 3600}
        )

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        config = engine._load_redis_config()

        assert config["enabled"] is True
        assert config["threshold"] == 0.85
        assert config["ttl"] == 3600
        mock_redis.get.assert_called_once_with(CONFIG_KEY)

    def test_load_redis_config_handles_bytes(self):
        """Test that _load_redis_config handles bytes response from Redis."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(
            {"enabled": True, "threshold": 0.9}
        ).encode("utf-8")

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        config = engine._load_redis_config()

        assert config["enabled"] is True
        assert config["threshold"] == 0.9

    def test_load_redis_config_returns_defaults_when_key_missing(self):
        """Test that defaults are returned when Redis key doesn't exist."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        config = engine._load_redis_config()

        assert config["enabled"] is False
        assert config["threshold"] == 0.95
        assert config["ttl"] == 86400

    def test_load_redis_config_handles_invalid_json(self):
        """Test that defaults are returned when Redis has invalid JSON."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "invalid json"

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        config = engine._load_redis_config()

        assert config["enabled"] is False
        assert config["threshold"] == 0.95
        assert config["ttl"] == 86400

    def test_load_redis_config_handles_redis_error(self):
        """Test that defaults are returned when Redis raises an exception."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis connection error")

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        config = engine._load_redis_config()

        assert config["enabled"] is False
        assert config["threshold"] == 0.95
        assert config["ttl"] == 86400

    def test_load_config_from_redis_applies_threshold(self):
        """Test that _load_config_from_redis applies threshold to config."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"threshold": 0.8})

        config = DeduplicationConfig(similarity_threshold=0.95)
        engine = MemoryDeduplicationEngine(config=config, redis_client=mock_redis)
        result = engine._load_config_from_redis()

        assert result.similarity_threshold == 0.8


class TestB32DeduplicationLogic:
    """Tests for B3.2: Deduplication Logic."""

    def test_calculate_hash_with_string_content(self):
        """Test _calculate_hash with string content."""
        engine = MemoryDeduplicationEngine()
        content = "test content"
        hash1 = engine._calculate_hash(content)
        hash2 = engine._calculate_hash(content)

        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 hex digest length
        assert hash1 == hash2  # Deterministic

    def test_calculate_hash_with_different_content(self):
        """Test that different content produces different hashes."""
        engine = MemoryDeduplicationEngine()
        hash1 = engine._calculate_hash("content A")
        hash2 = engine._calculate_hash("content B")

        assert hash1 != hash2

    def test_calculate_hash_with_empty_string(self):
        """Test _calculate_hash with empty string."""
        engine = MemoryDeduplicationEngine()
        hash_value = engine._calculate_hash("")

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

    def test_calculate_hash_with_large_content(self):
        """Test _calculate_hash with large content."""
        engine = MemoryDeduplicationEngine()
        content = "x" * 1000000  # 1MB content
        hash_value = engine._calculate_hash(content)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

    def test_is_duplicate_returns_true_when_hash_exists(self):
        """Test _is_duplicate returns True when hash exists in Redis."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine._is_duplicate("abc123")

        assert result is True
        mock_redis.exists.assert_called_once_with(f"{HASH_PREFIX}abc123")

    def test_is_duplicate_returns_false_when_hash_missing(self):
        """Test _is_duplicate returns False when hash doesn't exist."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine._is_duplicate("abc123")

        assert result is False

    def test_is_duplicate_returns_false_without_redis(self):
        """Test _is_duplicate returns False when no Redis client."""
        engine = MemoryDeduplicationEngine()
        result = engine._is_duplicate("abc123")

        assert result is False

    def test_store_hash_saves_to_redis_with_ttl(self):
        """Test _store_hash saves hash to Redis with TTL."""
        mock_redis = MagicMock()

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        engine._store_hash("abc123", ttl=3600)

        mock_redis.setex.assert_called_once_with(f"{HASH_PREFIX}abc123", 3600, "1")

    def test_store_hash_uses_default_ttl(self):
        """Test _store_hash uses default TTL from config (30 days)."""
        mock_redis = MagicMock()

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        engine._store_hash("abc123")

        # Default TTL is max_age_days * 86400 = 30 * 86400 = 2592000
        mock_redis.setex.assert_called_once_with(f"{HASH_PREFIX}abc123", 2592000, "1")

    def test_store_hash_handles_redis_error(self):
        """Test _store_hash handles Redis errors gracefully."""
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Redis error")

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        # Should not raise
        engine._store_hash("abc123")

    def test_deduplicate_content_finds_duplicate(self):
        """Test deduplicate_content finds and reports duplicate."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1  # Hash exists

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine.deduplicate_content("test content")

        assert result["is_duplicate"] is True
        assert result["hash"] is not None

    def test_deduplicate_content_stores_new_hash(self):
        """Test deduplicate_content stores hash for new content."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0  # Hash doesn't exist

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine.deduplicate_content("new content")

        assert result["is_duplicate"] is False
        assert result["hash"] is not None
        mock_redis.setex.assert_called_once()

    def test_deduplicate_content_without_redis(self):
        """Test deduplicate_content works without Redis (no dedup)."""
        engine = MemoryDeduplicationEngine()
        result = engine.deduplicate_content("content")

        assert result["is_duplicate"] is False
        assert result["hash"] is not None

    def test_deduplicate_content_with_empty_content(self):
        """Test deduplicate_content handles empty content."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine.deduplicate_content("")

        assert result["is_duplicate"] is False
        assert result["hash"] is not None


class TestB33FeatureFlagIntegration:
    """Tests for B3.3: Feature Flag Integration."""

    def test_is_feature_enabled_reads_from_redis(self):
        """Test _is_feature_enabled reads flag from Redis."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "true"

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine._is_feature_enabled()

        assert result is True
        mock_redis.get.assert_called_once_with(FEATURE_FLAG_KEY)

    def test_is_feature_enabled_handles_bytes(self):
        """Test _is_feature_enabled handles bytes response."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"true"

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine._is_feature_enabled()

        assert result is True

    def test_is_feature_enabled_returns_false_when_missing(self):
        """Test _is_feature_enabled returns False when flag missing."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine._is_feature_enabled()

        assert result is False

    def test_is_feature_enabled_returns_false_without_redis(self):
        """Test _is_feature_enabled returns False without Redis."""
        engine = MemoryDeduplicationEngine()
        result = engine._is_feature_enabled()

        assert result is False

    def test_is_feature_enabled_handles_redis_error(self):
        """Test _is_feature_enabled handles Redis errors."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis error")

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine._is_feature_enabled()

        assert result is False

    def test_set_feature_flag_sets_true(self):
        """Test _set_feature_flag sets flag to True."""
        mock_redis = MagicMock()

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine._set_feature_flag(True)

        assert result is True
        mock_redis.set.assert_called_once_with(FEATURE_FLAG_KEY, "true")

    def test_set_feature_flag_sets_false(self):
        """Test _set_feature_flag sets flag to False."""
        mock_redis = MagicMock()

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine._set_feature_flag(False)

        assert result is True
        mock_redis.set.assert_called_once_with(FEATURE_FLAG_KEY, "false")

    def test_set_feature_flag_returns_false_without_redis(self):
        """Test _set_feature_flag returns False without Redis."""
        engine = MemoryDeduplicationEngine()
        result = engine._set_feature_flag(True)

        assert result is False

    def test_set_feature_flag_handles_redis_error(self):
        """Test _set_feature_flag handles Redis errors."""
        mock_redis = MagicMock()
        mock_redis.set.side_effect = Exception("Redis error")

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine._set_feature_flag(True)

        assert result is False

    def test_is_enabled_uses_feature_flag_check(self):
        """Test is_enabled uses _is_feature_enabled when Redis available."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "true"

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine.is_enabled()

        assert result is True

    def test_enable_uses_set_feature_flag(self):
        """Test enable() uses _set_feature_flag."""
        mock_redis = MagicMock()

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine.enable()

        assert result is True
        mock_redis.set.assert_called_once_with(FEATURE_FLAG_KEY, "true")

    def test_disable_uses_set_feature_flag(self):
        """Test disable() uses _set_feature_flag."""
        mock_redis = MagicMock()

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine.disable()

        assert result is True
        mock_redis.set.assert_called_once_with(FEATURE_FLAG_KEY, "false")


class TestMemoryDeduplicationEngineIntegration:
    """Integration tests for MemoryDeduplicationEngine."""

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

    def test_deduplicate_updates_last_stats(self):
        """Test that deduplicate updates the last stats."""
        engine = MemoryDeduplicationEngine()

        stats = engine.deduplicate()
        assert engine.get_stats() is stats

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
        from src.governance.memory.deduplication import (
            MemoryDeduplicationEngine,
        )

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

    def test_config_key_constant(self):
        """Test that config key is correctly defined."""
        assert CONFIG_KEY == "chise:config:memory_dedup"

    def test_hash_prefix_constant(self):
        """Test that hash prefix is correctly defined."""
        assert HASH_PREFIX == "chise:memory:dedup:hash:"
