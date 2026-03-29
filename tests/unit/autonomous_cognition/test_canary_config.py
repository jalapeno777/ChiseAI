"""Tests for canary mode configuration validation.

Tests verify that:
1. Canary config file is valid YAML
2. Canary mode can be loaded and parsed
3. Canary settings override defaults correctly
4. Validation rules for canary mode are enforced
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path


# Path to the canary config file (relative to worktree root)
# test file: .../tests/unit/autonomous_cognition/test_canary_config.py
# worktree root: .../ (4 parents up from test file)
CANARY_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "autocog-canary.yaml"
)


class TestCanaryConfigFile:
    """Tests for canary config file validity."""

    def test_canary_config_file_exists(self):
        """Canary config file should exist."""
        assert CANARY_CONFIG_PATH.exists(), (
            f"Canary config file not found at {CANARY_CONFIG_PATH}"
        )

    def test_canary_config_is_valid_yaml(self):
        """Canary config file should be valid YAML."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)

        assert config is not None, "Canary config should not be empty"
        assert isinstance(config, dict), "Canary config should be a dictionary"

    def test_canary_config_has_version(self):
        """Canary config should have a version field."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)

        assert "version" in config, "Canary config should have 'version' field"
        assert config["version"] == 1, "Canary config version should be 1"


class TestCanaryModeSettings:
    """Tests for canary mode specific settings."""

    @pytest.fixture
    def canary_config(self):
        """Load and return the canary config."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f)

    def test_runtime_mode_is_canary(self, canary_config):
        """runtime_mode should be explicitly set to 'canary'."""
        assert "runtime_mode" in canary_config, (
            "Canary config should have 'runtime_mode' field"
        )
        assert canary_config["runtime_mode"] == "canary", (
            "runtime_mode should be 'canary' (not default)"
        )

    def test_canary_has_experiments_section(self, canary_config):
        """Canary config should have experiments section."""
        assert "experiments" in canary_config, (
            "Canary config should have 'experiments' section"
        )

        experiments = canary_config["experiments"]
        assert "max_experiments_per_cycle" in experiments, (
            "Canary experiments should have 'max_experiments_per_cycle'"
        )
        # Canary should have reduced experiments
        assert experiments["max_experiments_per_cycle"] == 1, (
            "Canary should have max_experiments_per_cycle=1"
        )

    def test_canary_has_canary_section(self, canary_config):
        """Canary config should have dedicated canary settings section."""
        assert "canary" in canary_config, "Canary config should have 'canary' section"

    def test_canary_position_limits(self, canary_config):
        """Canary should have strict position limits."""
        canary = canary_config["canary"]

        assert "max_position_fraction" in canary, (
            "Canary should have 'max_position_fraction'"
        )
        assert canary["max_position_fraction"] == 0.01, (
            "Canary max_position_fraction should be 0.01 (1%)"
        )

    def test_canary_divergence_threshold(self, canary_config):
        """Canary should have tighter divergence threshold than shadow."""
        canary = canary_config["canary"]

        assert "divergence_threshold" in canary, (
            "Canary should have 'divergence_threshold'"
        )
        # Canary threshold should be 0.15 (tighter than shadow's typical 0.25)
        assert canary["divergence_threshold"] == 0.15, (
            "Canary divergence_threshold should be 0.15"
        )

    def test_canary_auto_demote_threshold(self, canary_config):
        """Canary should have auto-demotion threshold."""
        canary = canary_config["canary"]

        assert "auto_demote_threshold" in canary, (
            "Canary should have 'auto_demote_threshold'"
        )
        assert canary["auto_demote_threshold"] == 0.40, (
            "Canary auto_demote_threshold should be 0.40"
        )

    def test_canary_required_consecutive_checks(self, canary_config):
        """Canary should require consecutive successful checks."""
        canary = canary_config["canary"]

        assert "required_consecutive_checks" in canary, (
            "Canary should have 'required_consecutive_checks'"
        )
        assert canary["required_consecutive_checks"] == 5, (
            "Canary required_consecutive_checks should be 5"
        )

    def test_canary_max_trades_per_day(self, canary_config):
        """Canary should cap daily trades."""
        canary = canary_config["canary"]

        assert "max_canary_trades_per_day" in canary, (
            "Canary should have 'max_canary_trades_per_day'"
        )
        assert canary["max_canary_trades_per_day"] == 3, (
            "Canary max_canary_trades_per_day should be 3"
        )


class TestCanarySafetySettings:
    """Tests for canary safety configuration."""

    @pytest.fixture
    def canary_config(self):
        """Load and return the canary config."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f)

    def test_canary_has_safety_section(self, canary_config):
        """Canary config should have safety section."""
        assert "safety" in canary_config, "Canary config should have 'safety' section"

    def test_canary_safety_max_risk_level(self, canary_config):
        """Canary should have lower max risk level."""
        safety = canary_config["safety"]

        assert "max_risk_level" in safety, "Canary safety should have 'max_risk_level'"
        assert safety["max_risk_level"] == "low", (
            "Canary max_risk_level should be 'low'"
        )

    def test_canary_safety_canary_specific_settings(self, canary_config):
        """Canary should have canary-specific safety settings."""
        safety = canary_config["safety"]

        assert "canary_safety" in safety, (
            "Canary safety should have 'canary_safety' subsection"
        )

        canary_safety = safety["canary_safety"]
        assert canary_safety["block_on_high_divergence"] is True, (
            "Canary should block on high divergence"
        )
        assert canary_safety["auto_demote_on_threshold"] is True, (
            "Canary should auto-demote on threshold"
        )


class TestCanaryMetricsSettings:
    """Tests for canary metrics configuration."""

    @pytest.fixture
    def canary_config(self):
        """Load and return the canary config."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f)

    def test_canary_has_metrics_section(self, canary_config):
        """Canary config should have metrics section."""
        assert "metrics" in canary_config, "Canary config should have 'metrics' section"

    def test_canary_metrics_skip_rate_threshold(self, canary_config):
        """Canary should have stricter skip rate threshold."""
        metrics = canary_config["metrics"]

        assert "skip_rate_alert_threshold" in metrics, (
            "Canary metrics should have 'skip_rate_alert_threshold'"
        )
        # Canary should have lower threshold (0.15 vs default 0.20)
        assert metrics["skip_rate_alert_threshold"] == 0.15, (
            "Canary skip_rate_alert_threshold should be 0.15"
        )


class TestCanaryNotificationSettings:
    """Tests for canary notification configuration."""

    @pytest.fixture
    def canary_config(self):
        """Load and return the canary config."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f)

    def test_canary_has_notifications_section(self, canary_config):
        """Canary config should have notifications section."""
        assert "notifications" in canary_config, (
            "Canary config should have 'notifications' section"
        )

    def test_canary_notifications_more_verbose(self, canary_config):
        """Canary should have more verbose notifications."""
        notifications = canary_config["notifications"]

        # Canary should have lower threshold (more notifications)
        assert notifications["notification_score_threshold"] == 0.005, (
            "Canary notification_score_threshold should be 0.005"
        )
        # Canary should have more frequent digests
        assert notifications["digest_interval_minutes"] == 30, (
            "Canary digest_interval_minutes should be 30"
        )

    def test_canary_notifications_canary_specific(self, canary_config):
        """Canary should have canary-specific notification settings."""
        notifications = canary_config["notifications"]

        assert "canary_notifications" in notifications, (
            "Canary notifications should have 'canary_notifications' subsection"
        )


class TestCanarySchedulingSettings:
    """Tests for canary scheduling configuration."""

    @pytest.fixture
    def canary_config(self):
        """Load and return the canary config."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f)

    def test_canary_has_scheduling_section(self, canary_config):
        """Canary config should have scheduling section."""
        assert "scheduling" in canary_config, (
            "Canary config should have 'scheduling' section"
        )

    def test_canary_scheduling_crons(self, canary_config):
        """Canary should have canary-specific cron jobs."""
        scheduling = canary_config["scheduling"]

        assert "woodpecker_crons" in scheduling, (
            "Canary scheduling should have 'woodpecker_crons'"
        )

        cron_names = [cron["name"] for cron in scheduling["woodpecker_crons"]]
        assert "autocog-canary-hourly" in cron_names, (
            "Canary should have 'autocog-canary-hourly' cron"
        )
        assert "autocog-canary-daily" in cron_names, (
            "Canary should have 'autocog-canary-daily' cron"
        )


class TestCanaryConfigValidation:
    """Tests for canary config validation rules."""

    def test_canary_max_position_fraction_in_valid_range(self):
        """max_position_fraction should be between 0 and 1."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)

        max_pos = config["canary"]["max_position_fraction"]
        assert 0 < max_pos <= 1, (
            f"max_position_fraction should be between 0 and 1, got {max_pos}"
        )

    def test_canary_divergence_threshold_in_valid_range(self):
        """divergence_threshold should be between 0 and 1."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)

        threshold = config["canary"]["divergence_threshold"]
        assert 0 <= threshold <= 1, (
            f"divergence_threshold should be between 0 and 1, got {threshold}"
        )

    def test_canary_auto_demote_threshold_greater_than_divergence(self):
        """auto_demote_threshold should be >= divergence_threshold."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)

        divergence = config["canary"]["divergence_threshold"]
        demote = config["canary"]["auto_demote_threshold"]

        assert demote >= divergence, (
            f"auto_demote_threshold ({demote}) should be >= "
            f"divergence_threshold ({divergence})"
        )

    def test_canary_required_consecutive_checks_is_positive(self):
        """required_consecutive_checks should be a positive integer."""
        with open(CANARY_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)

        checks = config["canary"]["required_consecutive_checks"]
        assert isinstance(checks, int) and checks > 0, (
            f"required_consecutive_checks should be positive integer, got {checks}"
        )
