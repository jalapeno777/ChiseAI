"""Tests for ICT feature flags (ST-ICT-018).

Tests verify:
- Default values (CVD, FVG, Order Block enabled; BOS/CHoCH disabled)
- Environment variable overrides
- Redis runtime toggling
- BOS/CHoCH safety behavior
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from src.config.ict_feature_flags import (
    ICTFeatureFlags,
    get_ict_feature_flags,
    reset_ict_feature_flags,
    set_ict_feature_flags,
)


class TestICTFeatureFlagDefaults:
    """Test that all ICT feature flags have correct defaults."""

    def test_cvd_defaults_to_enabled(self) -> None:
        """CVD signals should default to enabled (True)."""
        flags = ICTFeatureFlags()
        assert flags.ict_cvd_enabled is True

    def test_fvg_defaults_to_enabled(self) -> None:
        """FVG signals should default to enabled (True)."""
        flags = ICTFeatureFlags()
        assert flags.ict_fvg_enabled is True

    def test_order_block_defaults_to_enabled(self) -> None:
        """Order Block signals should default to enabled (True)."""
        flags = ICTFeatureFlags()
        assert flags.ict_order_block_enabled is True

    def test_bos_choch_defaults_to_enabled(self) -> None:
        """BOS/CHoCH signals should default to enabled (True) after accuracy fix."""
        flags = ICTFeatureFlags()
        assert flags.ict_bos_choch_enabled is True

    def test_integration_defaults_to_enabled(self) -> None:
        """ICT integration master flag should default to enabled (True)."""
        flags = ICTFeatureFlags()
        assert flags.ict_integration_enabled is True


class TestICTFeatureFlagFromEnv:
    """Test loading flags from environment variables."""

    def test_from_env_with_no_env_vars(self) -> None:
        """When no env vars are set, defaults should be used."""
        env_vars = [
            "ICT_CVD_ENABLED",
            "ICT_FVG_ENABLED",
            "ICT_ORDER_BLOCK_ENABLED",
            "ICT_BOS_CHOCH_ENABLED",
            "ICT_INTEGRATION_ENABLED",
        ]
        cleared_env = {k: os.environ.pop(k, None) for k in env_vars}

        try:
            flags = ICTFeatureFlags.from_env()

            # CVD, FVG, Order Block, Integration should default to True
            assert flags.ict_cvd_enabled is True
            assert flags.ict_fvg_enabled is True
            assert flags.ict_order_block_enabled is True
            assert flags.ict_integration_enabled is True
            # BOS/CHoCH should default to True (re-enabled)
            assert flags.ict_bos_choch_enabled is True
        finally:
            for k, v in cleared_env.items():
                if v is not None:
                    os.environ[k] = v

    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
        ],
    )
    def test_cvd_enabled_values(self, env_value: str, expected: bool) -> None:
        """Test that CVD can be enabled via env var."""
        with patch.dict(os.environ, {"ICT_CVD_ENABLED": env_value}, clear=False):
            flags = ICTFeatureFlags.from_env()
            assert flags.ict_cvd_enabled is expected

    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("off", False),
        ],
    )
    def test_cvd_disabled_values(self, env_value: str, expected: bool) -> None:
        """Test that CVD can be disabled via env var."""
        with patch.dict(os.environ, {"ICT_CVD_ENABLED": env_value}, clear=False):
            flags = ICTFeatureFlags.from_env()
            assert flags.ict_cvd_enabled is expected


class TestICTFeatureFlagRedisIntegration:
    """Test Redis-backed runtime toggling."""

    def test_get_redis_value_fallback_to_default(self) -> None:
        """When Redis unavailable, should fallback to default."""
        flags = ICTFeatureFlags()
        # Mock Redis client returning None by patching _get_redis_client
        with patch.object(ICTFeatureFlags, "_get_redis_client", return_value=None):
            result = flags.get_redis_value("ict:feature_flags:cvd", True)
            assert result is True

    def test_get_redis_value_from_redis(self) -> None:
        """Should read value from Redis when available."""
        flags = ICTFeatureFlags()
        mock_client = MagicMock()
        mock_client.get.return_value = "false"
        with patch.object(
            ICTFeatureFlags, "_get_redis_client", return_value=mock_client
        ):
            # Force recreation of the instance to pick up the mocked client
            result = flags.get_redis_value("ict:feature_flags:cvd", True)
            assert result is False

    def test_set_redis_value_success(self) -> None:
        """Should set value in Redis with TTL."""
        flags = ICTFeatureFlags()
        mock_client = MagicMock()
        with patch.object(
            ICTFeatureFlags, "_get_redis_client", return_value=mock_client
        ):
            result = flags.set_redis_value("ict:feature_flags:cvd", False)
            assert result is True
            mock_client.setex.assert_called_once()
            call_args = mock_client.setex.call_args
            assert call_args[0][0] == "ict:feature_flags:cvd"
            assert call_args[0][1] == 3600  # TTL
            assert call_args[0][2] == "false"

    def test_set_redis_value_redis_unavailable(self) -> None:
        """Should return False when Redis unavailable."""
        flags = ICTFeatureFlags()
        with patch.object(ICTFeatureFlags, "_get_redis_client", return_value=None):
            result = flags.set_redis_value("ict:feature_flags:cvd", False)
            assert result is False


class TestICTRuntimeMethods:
    """Test runtime flag checking methods."""

    def test_is_cvd_enabled_uses_redis(self) -> None:
        """is_cvd_enabled should check Redis first."""
        flags = ICTFeatureFlags()
        mock_client = MagicMock()
        mock_client.get.return_value = "true"
        with patch.object(
            ICTFeatureFlags, "_get_redis_client", return_value=mock_client
        ):
            result = flags.is_cvd_enabled()
            assert result is True
            mock_client.get.assert_called_with("ict:feature_flags:cvd")

    def test_is_bos_choch_enabled_default(self) -> None:
        """BOS/CHoCH should use default when Redis has no value."""
        flags = ICTFeatureFlags()
        # Redis returns None (no value) and default is True
        mock_client = MagicMock()
        mock_client.get.return_value = None
        with patch.object(
            ICTFeatureFlags, "_get_redis_client", return_value=mock_client
        ):
            result = flags.is_bos_choch_enabled()
            # Should return True because that's the default
            assert result is True


class TestICTRuntimeSetters:
    """Test runtime flag setter methods."""

    def test_set_bos_choch_disabled_logs_warning(self) -> None:
        """Setting BOS/CHoCH to disabled should log warning."""
        flags = ICTFeatureFlags()
        mock_client = MagicMock()
        with patch.object(
            ICTFeatureFlags, "_get_redis_client", return_value=mock_client
        ):
            with patch("src.config.ict_feature_flags.logger") as mock_logger:
                flags.set_bos_choch_enabled(False)
                mock_logger.warning.assert_called_once()


class TestICTFeatureFlagToDict:
    """Test ICT feature flags serialization."""

    def test_to_dict_contains_all_flags(self) -> None:
        """to_dict should include all ICT flags."""
        flags = ICTFeatureFlags()
        # Mock Redis to return defaults
        with patch.object(ICTFeatureFlags, "_get_redis_client", return_value=None):
            data = flags.to_dict()

        expected_keys = {
            "ict_cvd_enabled",
            "ict_fvg_enabled",
            "ict_order_block_enabled",
            "ict_bos_choch_enabled",
            "ict_integration_enabled",
        }
        assert set(data.keys()) == expected_keys

    def test_to_defaults_dict(self) -> None:
        """to_defaults_dict should return default values."""
        flags = ICTFeatureFlags()
        data = flags.to_defaults_dict()

        assert data["ict_cvd_enabled"] is True
        assert data["ict_fvg_enabled"] is True
        assert data["ict_order_block_enabled"] is True
        assert data["ict_bos_choch_enabled"] is True
        assert data["ict_integration_enabled"] is True


class TestICTFeatureFlagGlobalInstance:
    """Test global ICT feature flags instance behavior."""

    def test_get_ict_feature_flags_lazy_initialization(self) -> None:
        """Global instance is lazily initialized."""
        reset_ict_feature_flags()

        # First call should initialize
        flags1 = get_ict_feature_flags()
        assert isinstance(flags1, ICTFeatureFlags)

        # Subsequent calls should return same instance
        flags2 = get_ict_feature_flags()
        assert flags1 is flags2

    def test_set_ict_feature_flags(self) -> None:
        """Test setting global feature flags."""
        custom_flags = ICTFeatureFlags(
            ict_cvd_enabled=False,
            ict_fvg_enabled=False,
            ict_order_block_enabled=False,
            ict_bos_choch_enabled=False,  # Override for testing
            ict_integration_enabled=False,
        )

        set_ict_feature_flags(custom_flags)
        retrieved = get_ict_feature_flags()

        assert retrieved is custom_flags
        assert retrieved.ict_cvd_enabled is False

    def test_reset_ict_feature_flags(self) -> None:
        """Test resetting global feature flags."""
        # Set custom flags
        custom_flags = ICTFeatureFlags(ict_cvd_enabled=False)
        set_ict_feature_flags(custom_flags)

        # Reset
        reset_ict_feature_flags()

        # Next get should create new instance
        flags = get_ict_feature_flags()
        assert flags is not custom_flags
        assert flags.ict_cvd_enabled is True  # Back to default


class TestICTSafetyDocumentation:
    """Test that ICT safety flags are properly documented."""

    def test_bos_choch_safety_documented(self) -> None:
        """BOS/CHoCH should be documented as re-enabled."""
        docstring = ICTFeatureFlags.__doc__
        assert docstring is not None
        assert "ENABLED" in docstring or "True" in docstring

    def test_bos_choch_default_true(self) -> None:
        """BOS/CHoCH should default to True (re-enabled)."""
        flags = ICTFeatureFlags()
        assert flags.ict_bos_choch_enabled is True
