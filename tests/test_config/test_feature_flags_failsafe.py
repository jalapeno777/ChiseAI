"""Tests for feature flag fail-safe behavior (PAPER-READY-P0-FIX-002).

These tests verify that all safety-critical feature flags have fail-safe defaults,
meaning missing or invalid configuration will NOT disable safety features.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from src.config.feature_flags import (
    FeatureFlags,
    get_feature_flags,
    reset_feature_flags,
    set_feature_flags,
)


class TestFeatureFlagDefaults:
    """Test that all feature flags have safe defaults."""

    def test_all_safety_flags_default_to_true(self) -> None:
        """All safety-critical flags must default to True (enabled)."""
        flags = FeatureFlags()  # Uses dataclass defaults

        # All flags should default to True for fail-safe behavior
        assert flags.retraining_ece_trigger is True
        assert flags.retraining_performance_trigger is True
        assert flags.retraining_scheduled_trigger is True
        assert flags.retraining_deduplication is True
        assert flags.retraining_pre_validation is True
        assert flags.retraining_discord_alerts is True
        assert flags.launch_training_pipeline_enabled is True

    def test_from_env_with_no_env_vars(self) -> None:
        """When no env vars are set, all flags should use safe defaults (True)."""
        # Ensure no feature flag env vars are set
        env_vars_to_clear = [
            "FEATURE_RETRAINING_ECE_TRIGGER",
            "FEATURE_RETRAINING_PERF_TRIGGER",
            "FEATURE_RETRAINING_SCHEDULED_TRIGGER",
            "FEATURE_RETRAINING_DEDUPLICATION",
            "FEATURE_RETRAINING_PRE_VALIDATION",
            "FEATURE_RETRAINING_DISCORD_ALERTS",
            "LAUNCH_TRAINING_PIPELINE_ENABLED",
        ]

        cleared_env = {k: os.environ.pop(k, None) for k in env_vars_to_clear}

        try:
            flags = FeatureFlags.from_env()

            # All should default to True
            assert flags.retraining_ece_trigger is True
            assert flags.retraining_performance_trigger is True
            assert flags.retraining_scheduled_trigger is True
            assert flags.retraining_deduplication is True
            assert flags.retraining_pre_validation is True
            assert flags.retraining_discord_alerts is True
            assert flags.launch_training_pipeline_enabled is True
        finally:
            # Restore env vars
            for k, v in cleared_env.items():
                if v is not None:
                    os.environ[k] = v


class TestFeatureFlagDisableValues:
    """Test that flags can be explicitly disabled with valid values."""

    @pytest.mark.parametrize(
        "env_value",
        ["false", "False", "FALSE", "FaLsE", "0", "no", "NO", "off", "OFF"],
    )
    def test_explicit_disable_values(self, env_value: str) -> None:
        """Flags can be disabled with explicit false-like values."""
        with patch.dict(
            os.environ, {"FEATURE_RETRAINING_ECE_TRIGGER": env_value}, clear=False
        ):
            flags = FeatureFlags.from_env()
            assert (
                flags.retraining_ece_trigger is False
            ), f"Value '{env_value}' should disable flag"

    def test_whitespace_around_false(self) -> None:
        """Whitespace around false values should still disable."""
        with patch.dict(
            os.environ, {"FEATURE_RETRAINING_ECE_TRIGGER": "  false  "}, clear=False
        ):
            flags = FeatureFlags.from_env()
            assert flags.retraining_ece_trigger is False


class TestFeatureFlagFailSafeBehavior:
    """Test fail-safe behavior for invalid/missing values."""

    @pytest.mark.parametrize(
        "env_value",
        [
            "",  # Empty string
            "   ",  # Whitespace only
            "invalid",  # Invalid value
            "maybe",  # Ambiguous value
            "truee",  # Typo
            "1 ",  # Trailing space on truthy value
            "yes ",  # Trailing space on truthy value
        ],
    )
    def test_invalid_values_use_safe_default(self, env_value: str) -> None:
        """Invalid/malformed values should use safe default (True), not disable."""
        with patch.dict(
            os.environ, {"FEATURE_RETRAINING_ECE_TRIGGER": env_value}, clear=False
        ):
            flags = FeatureFlags.from_env()
            assert (
                flags.retraining_ece_trigger is True
            ), f"Invalid value '{env_value}' should use safe default (True)"

    def test_all_flags_fail_safe(self) -> None:
        """Test fail-safe behavior for all flags with invalid input."""
        env_vars = {
            "FEATURE_RETRAINING_ECE_TRIGGER": "invalid",
            "FEATURE_RETRAINING_PERF_TRIGGER": "",
            "FEATURE_RETRAINING_SCHEDULED_TRIGGER": "   ",
            "FEATURE_RETRAINING_DEDUPLICATION": "maybe",
            "FEATURE_RETRAINING_PRE_VALIDATION": "typo",
            "FEATURE_RETRAINING_DISCORD_ALERTS": "",
            "LAUNCH_TRAINING_PIPELINE_ENABLED": "invalid",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            flags = FeatureFlags.from_env()

            # All should use safe default (True) despite invalid values
            assert flags.retraining_ece_trigger is True
            assert flags.retraining_performance_trigger is True
            assert flags.retraining_scheduled_trigger is True
            assert flags.retraining_deduplication is True
            assert flags.retraining_pre_validation is True
            assert flags.retraining_discord_alerts is True
            assert flags.launch_training_pipeline_enabled is True


class TestFeatureFlagGlobalInstance:
    """Test global feature flags instance behavior."""

    def test_get_feature_flags_lazy_initialization(self) -> None:
        """Global instance is lazily initialized."""
        reset_feature_flags()

        # First call should initialize
        flags1 = get_feature_flags()
        assert isinstance(flags1, FeatureFlags)

        # Subsequent calls should return same instance
        flags2 = get_feature_flags()
        assert flags1 is flags2

    def test_set_feature_flags(self) -> None:
        """Test setting global feature flags."""
        custom_flags = FeatureFlags(
            retraining_ece_trigger=False,
            retraining_performance_trigger=False,
            retraining_scheduled_trigger=False,
            retraining_deduplication=False,
            retraining_pre_validation=False,
            retraining_discord_alerts=False,
            launch_training_pipeline_enabled=False,
        )

        set_feature_flags(custom_flags)
        retrieved = get_feature_flags()

        assert retrieved is custom_flags
        assert retrieved.retraining_ece_trigger is False

    def test_reset_feature_flags(self) -> None:
        """Test resetting global feature flags."""
        # Set custom flags
        custom_flags = FeatureFlags(retraining_ece_trigger=False)
        set_feature_flags(custom_flags)

        # Reset
        reset_feature_flags()

        # Next get should create new instance
        flags = get_feature_flags()
        assert flags is not custom_flags
        assert flags.retraining_ece_trigger is True  # Back to default


class TestFeatureFlagToDict:
    """Test feature flags serialization."""

    def test_to_dict_contains_all_flags(self) -> None:
        """to_dict should include all flags."""
        flags = FeatureFlags()
        data = flags.to_dict()

        expected_keys = {
            "retraining_ece_trigger",
            "retraining_performance_trigger",
            "retraining_scheduled_trigger",
            "retraining_deduplication",
            "retraining_pre_validation",
            "retraining_discord_alerts",
            "launch_training_pipeline_enabled",
        }

        assert set(data.keys()) == expected_keys

    def test_to_dict_values_match(self) -> None:
        """to_dict values should match flag values."""
        flags = FeatureFlags(
            retraining_ece_trigger=False,
            retraining_discord_alerts=False,
        )
        data = flags.to_dict()

        assert data["retraining_ece_trigger"] is False
        assert data["retraining_discord_alerts"] is False
        assert data["retraining_pre_validation"] is True


class TestFeatureFlagImmutability:
    """Test that FeatureFlags is immutable (frozen dataclass)."""

    def test_feature_flags_is_frozen(self) -> None:
        """FeatureFlags should be immutable."""
        flags = FeatureFlags()

        with pytest.raises(AttributeError):
            flags.retraining_ece_trigger = False


class TestSafetyFlagDocumentation:
    """Test that safety flags are properly documented."""

    def test_all_flags_documented_in_docstring(self) -> None:
        """All flags should be mentioned in class docstring."""
        docstring = FeatureFlags.__doc__
        assert docstring is not None

        # Check for safety markers
        assert "[SAFETY]" in docstring
        assert "SAFETY-FIRST DESIGN" in docstring

        # Check that all flags are mentioned
        assert "retraining_ece_trigger" in docstring
        assert "retraining_performance_trigger" in docstring
        assert "retraining_scheduled_trigger" in docstring
        assert "launch_training_pipeline_enabled" in docstring

    def test_fail_safe_behavior_documented(self) -> None:
        """Fail-safe behavior should be documented."""
        docstring = FeatureFlags.__doc__
        assert "fail-safe" in docstring.lower() or "SAFE" in docstring
