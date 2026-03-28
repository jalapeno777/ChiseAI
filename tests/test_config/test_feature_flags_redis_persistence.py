"""Tests for feature flag Redis persistence.

Tests verify:
- Flags persist across restart via Redis
- Redis toggle functionality
- Backward compatibility with existing in-memory usage
- Fallback to defaults when Redis unavailable
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from src.config.feature_flags import (
    FeatureFlags,
    get_feature_flags,
    reset_feature_flags,
    set_feature_flags,
)


class TestFeatureFlagRedisPersistence:
    """Test Redis-backed persistence for feature flags."""

    def test_get_redis_value_fallback_to_default(self) -> None:
        """When Redis unavailable, should fallback to default."""
        flags = FeatureFlags()
        with patch.object(FeatureFlags, "_get_redis_client", return_value=None):
            result = flags.get_redis_value("chise:feature_flags:config:test_flag", True)
            assert result is True

    def test_get_redis_value_from_redis(self) -> None:
        """Should read value from Redis when available."""
        flags = FeatureFlags()
        mock_client = MagicMock()
        mock_client.get.return_value = "false"
        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            result = flags.get_redis_value(
                "chise:feature_flags:config:retraining_ece_trigger", True
            )
            assert result is False

    def test_get_redis_value_none_returns_default(self) -> None:
        """When Redis returns None (key not set), should return default."""
        flags = FeatureFlags()
        mock_client = MagicMock()
        mock_client.get.return_value = None
        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            result = flags.get_redis_value(
                "chise:feature_flags:config:retraining_ece_trigger", False
            )
            assert result is False  # Returns the default

    def test_set_redis_value_success(self) -> None:
        """Should set value in Redis with TTL."""
        flags = FeatureFlags()
        mock_client = MagicMock()
        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            result = flags.set_redis_value(
                "chise:feature_flags:config:retraining_ece_trigger", False
            )
            assert result is True
            mock_client.setex.assert_called_once()
            call_args = mock_client.setex.call_args
            assert (
                call_args[0][0] == "chise:feature_flags:config:retraining_ece_trigger"
            )
            assert call_args[0][1] == 86400  # TTL
            assert call_args[0][2] == "false"

    def test_set_redis_value_redis_unavailable(self) -> None:
        """Should return False when Redis unavailable."""
        flags = FeatureFlags()
        with patch.object(FeatureFlags, "_get_redis_client", return_value=None):
            result = flags.set_redis_value(
                "chise:feature_flags:config:retraining_ece_trigger", False
            )
            assert result is False


class TestFeatureFlagRuntimeMethods:
    """Test runtime flag checking methods that consult Redis."""

    def test_is_retraining_ece_trigger_enabled_uses_redis(self) -> None:
        """is_retraining_ece_trigger_enabled should check Redis first."""
        flags = FeatureFlags()
        mock_client = MagicMock()
        mock_client.get.return_value = "false"
        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            result = flags.is_retraining_ece_trigger_enabled()
            assert result is False
            mock_client.get.assert_called_with(
                "chise:feature_flags:config:retraining_ece_trigger"
            )

    def test_is_retraining_ece_trigger_enabled_fallback_to_default(self) -> None:
        """When Redis has no value, should use default (True)."""
        flags = FeatureFlags()
        mock_client = MagicMock()
        mock_client.get.return_value = None
        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            result = flags.is_retraining_ece_trigger_enabled()
            assert result is True  # Default is True

    def test_is_launch_training_pipeline_enabled_uses_redis(self) -> None:
        """is_launch_training_pipeline_enabled should check Redis first."""
        flags = FeatureFlags()
        mock_client = MagicMock()
        mock_client.get.return_value = "true"
        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            result = flags.is_launch_training_pipeline_enabled()
            assert result is True


class TestFeatureFlagRuntimeSetters:
    """Test runtime flag setter methods that write to Redis."""

    def test_set_retraining_ece_trigger_enabled(self) -> None:
        """Should set value in Redis."""
        flags = FeatureFlags()
        mock_client = MagicMock()
        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            result = flags.set_retraining_ece_trigger_enabled(False)
            assert result is True
            mock_client.setex.assert_called_once()
            call_args = mock_client.setex.call_args
            assert "retraining_ece_trigger" in call_args[0][0]

    def test_set_launch_training_pipeline_enabled(self) -> None:
        """Should set training pipeline flag in Redis."""
        flags = FeatureFlags()
        mock_client = MagicMock()
        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            result = flags.set_launch_training_pipeline_enabled(False)
            assert result is True
            mock_client.setex.assert_called_once()
            call_args = mock_client.setex.call_args
            assert "launch_training_pipeline_enabled" in call_args[0][0]

    def test_set_flag_redis_unavailable_returns_false(self) -> None:
        """Should return False when Redis unavailable."""
        flags = FeatureFlags()
        with patch.object(FeatureFlags, "_get_redis_client", return_value=None):
            result = flags.set_retraining_ece_trigger_enabled(False)
            assert result is False


class TestFeatureFlagRedisPersistenceAcrossRestart:
    """Test that flags persist across restart via Redis."""

    def test_flags_survive_restart(self) -> None:
        """Verify that after setting a flag in Redis, it's read back correctly.

        This simulates the restart scenario where:
        1. First instance sets a flag
        2. System restarts
        3. New instance reads the flag from Redis
        """
        # Simulate first instance setting a flag
        mock_client = MagicMock()
        mock_client.setex.return_value = True

        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            flags1 = FeatureFlags()
            flags1.set_retraining_ece_trigger_enabled(False)

        # Simulate restart - new client, same Redis
        mock_client2 = MagicMock()
        mock_client2.get.return_value = "false"  # The value that was set

        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client2):
            flags2 = FeatureFlags()
            result = flags2.is_retraining_ece_trigger_enabled()
            assert result is False

    def test_all_flags_have_redis_keys(self) -> None:
        """All feature flags should have corresponding Redis keys."""
        flags = FeatureFlags()
        assert (
            flags.KEY_RETRAINING_ECE
            == "chise:feature_flags:config:retraining_ece_trigger"
        )
        assert (
            flags.KEY_RETRAINING_PERF
            == "chise:feature_flags:config:retraining_performance_trigger"
        )
        assert (
            flags.KEY_RETRAINING_SCHEDULED
            == "chise:feature_flags:config:retraining_scheduled_trigger"
        )
        assert (
            flags.KEY_RETRAINING_DEDUP
            == "chise:feature_flags:config:retraining_deduplication"
        )
        assert (
            flags.KEY_RETRAINING_PRE_VALIDATION
            == "chise:feature_flags:config:retraining_pre_validation"
        )
        assert (
            flags.KEY_RETRAINING_DISCORD
            == "chise:feature_flags:config:retraining_discord_alerts"
        )
        assert (
            flags.KEY_LAUNCH_PIPELINE
            == "chise:feature_flags:config:launch_training_pipeline_enabled"
        )


class TestFeatureFlagToDictRedis:
    """Test Redis-aware to_dict method."""

    def test_to_dict_uses_redis_runtime_values(self) -> None:
        """to_dict should return Redis-aware runtime values."""
        flags = FeatureFlags()
        mock_client = MagicMock()

        # Simulate Redis having some values set
        def get_side_effect(key):
            if "ece" in key:
                return "false"
            if "pipeline" in key:
                return "true"
            return None

        mock_client.get.side_effect = get_side_effect

        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            data = flags.to_dict()
            assert data["retraining_ece_trigger"] is False
            assert data["launch_training_pipeline_enabled"] is True
            # Others should use defaults (True)
            assert data["retraining_performance_trigger"] is True
            assert data["retraining_scheduled_trigger"] is True

    def test_to_defaults_dict_ignores_redis(self) -> None:
        """to_defaults_dict should return raw defaults, ignoring Redis."""
        flags = FeatureFlags(
            retraining_ece_trigger=False,
            launch_training_pipeline_enabled=False,
        )
        mock_client = MagicMock()
        mock_client.get.return_value = "true"  # Redis has different value

        with patch.object(FeatureFlags, "_get_redis_client", return_value=mock_client):
            data = flags.to_defaults_dict()
            assert data["retraining_ece_trigger"] is False  # Raw default
            assert data["launch_training_pipeline_enabled"] is False  # Raw default
            # Redis was queried but to_defaults_dict ignores it


class TestFeatureFlagBackwardCompatibility:
    """Test backward compatibility with existing in-memory usage."""

    def test_default_values_still_work(self) -> None:
        """Default values should still be used when Redis is unavailable."""
        reset_feature_flags()
        with patch.object(FeatureFlags, "_get_redis_client", return_value=None):
            flags = get_feature_flags()
            # All should default to True
            assert flags.retraining_ece_trigger is True
            assert flags.retraining_performance_trigger is True
            assert flags.retraining_scheduled_trigger is True
            assert flags.retraining_deduplication is True
            assert flags.retraining_pre_validation is True
            assert flags.retraining_discord_alerts is True
            assert flags.launch_training_pipeline_enabled is True

    def test_from_env_still_works(self) -> None:
        """from_env should still load from environment variables."""
        env_vars = {
            "FEATURE_RETRAINING_ECE_TRIGGER": "false",
            "LAUNCH_TRAINING_PIPELINE_ENABLED": "false",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            flags = FeatureFlags.from_env()
            assert flags.retraining_ece_trigger is False
            assert flags.launch_training_pipeline_enabled is False
            # Others should use defaults
            assert flags.retraining_performance_trigger is True

    def test_feature_flags_is_frozen(self) -> None:
        """FeatureFlags should still be immutable."""
        flags = FeatureFlags()
        with pytest.raises(AttributeError):
            flags.retraining_ece_trigger = False

    def test_global_instance_pattern_preserved(self) -> None:
        """Global instance pattern should still work."""
        reset_feature_flags()
        flags1 = get_feature_flags()
        flags2 = get_feature_flags()
        assert flags1 is flags2

        # set_feature_flags should still work
        custom_flags = FeatureFlags(retraining_ece_trigger=False)
        set_feature_flags(custom_flags)
        assert get_feature_flags() is custom_flags
