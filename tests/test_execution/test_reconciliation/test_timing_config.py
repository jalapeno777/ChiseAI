"""Tests for reconciliation timing configuration."""

import pytest
from datetime import timedelta

from execution.reconciliation.config import (
    ReconciliationConfig,
    ReconciliationTimingConfig,
)


class TestReconciliationTimingConfig:
    """Test timing configuration."""

    def test_default_interval_is_86400(self):
        """Default interval should be 24 hours (86400s)."""
        config = ReconciliationTimingConfig()
        assert config.default_interval_seconds == 86400
        assert config.default_time_range == timedelta(seconds=86400)

    def test_hourly_interval_constant(self):
        """Hourly interval constant should be 3600."""
        assert ReconciliationTimingConfig.INTERVAL_HOURLY == 3600

    def test_daily_interval_constant(self):
        """Daily interval constant should be 86400."""
        assert ReconciliationTimingConfig.INTERVAL_DAILY == 86400

    def test_get_time_range_with_custom_interval(self):
        """Should return correct timedelta for custom interval."""
        config = ReconciliationTimingConfig()
        result = config.get_time_range(7200)  # 2 hours
        assert result == timedelta(seconds=7200)

    def test_get_time_range_none_uses_default(self):
        """Should use default interval when None is passed."""
        config = ReconciliationTimingConfig()
        result = config.get_time_range(None)
        assert result == timedelta(seconds=86400)


class TestReconciliationConfig:
    """Test main reconciliation config."""

    def test_default_timing_config(self):
        """Should create default timing config if not provided."""
        config = ReconciliationConfig()
        assert config.timing is not None
        assert config.timing.default_interval_seconds == 86400

    def test_custom_timing_config(self):
        """Should accept custom timing config."""
        timing = ReconciliationTimingConfig(default_interval_seconds=3600)
        config = ReconciliationConfig(timing=timing)
        assert config.timing.default_interval_seconds == 3600

    def test_default_categories(self):
        """Should have default categories."""
        config = ReconciliationConfig()
        assert config.categories == ["signals", "orders", "fills", "outcomes"]

    def test_custom_categories(self):
        """Should accept custom categories."""
        config = ReconciliationConfig(categories=["signals", "orders"])
        assert config.categories == ["signals", "orders"]

    def test_backward_compatible_thresholds(self):
        """Should maintain backward-compatible default thresholds."""
        config = ReconciliationConfig()
        assert config.warn_threshold_pct == 1.0
        assert config.fail_threshold_pct == 5.0
