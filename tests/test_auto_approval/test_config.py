"""Tests for auto-approval config."""

import os
import pytest
from pathlib import Path
from unittest.mock import mock_open, patch

from src.autonomous_git.auto_approval.config import (
    load_config,
    AutoApprovalConfig,
    RateLimitConfig,
    SafetyCheckConfig,
    ExclusionConfig,
    NotificationConfig,
)


class TestAutoApprovalConfig:
    """Test cases for AutoApprovalConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AutoApprovalConfig()

        assert config.enabled is True
        assert config.merge_strategy == "squash"
        assert isinstance(config.rate_limits, RateLimitConfig)
        assert isinstance(config.safety_checks, SafetyCheckConfig)
        assert isinstance(config.exclusions, ExclusionConfig)
        assert isinstance(config.notifications, NotificationConfig)

    def test_custom_values(self):
        """Test custom configuration values."""
        config = AutoApprovalConfig(
            enabled=False,
            merge_strategy="merge",
            gitea_url="https://gitea.example.com",
            gitea_token="secret",
        )

        assert config.enabled is False
        assert config.merge_strategy == "merge"
        assert config.gitea_url == "https://gitea.example.com"
        assert config.gitea_token == "secret"


class TestRateLimitConfig:
    """Test cases for RateLimitConfig."""

    def test_default_values(self):
        """Test default rate limit values."""
        config = RateLimitConfig()

        assert config.max_per_hour == 10
        assert config.max_consecutive == 3
        assert config.consecutive_pause_duration == 300

    def test_custom_values(self):
        """Test custom rate limit values."""
        config = RateLimitConfig(
            max_per_hour=20,
            max_consecutive=5,
            consecutive_pause_duration=600,
        )

        assert config.max_per_hour == 20
        assert config.max_consecutive == 5
        assert config.consecutive_pause_duration == 600


class TestSafetyCheckConfig:
    """Test cases for SafetyCheckConfig."""

    def test_default_values(self):
        """Test default safety check values."""
        config = SafetyCheckConfig()

        assert config.require_green_ci is True
        assert config.require_story_id is True
        assert config.check_merge_conflicts is True

    def test_custom_values(self):
        """Test custom safety check values."""
        config = SafetyCheckConfig(
            require_green_ci=False,
            require_story_id=False,
            check_merge_conflicts=False,
        )

        assert config.require_green_ci is False
        assert config.require_story_id is False
        assert config.check_merge_conflicts is False


class TestExclusionConfig:
    """Test cases for ExclusionConfig."""

    def test_default_values(self):
        """Test default exclusion values."""
        config = ExclusionConfig()

        assert config.paths == []
        assert config.authors == []
        assert config.title_patterns == []

    def test_custom_values(self):
        """Test custom exclusion values."""
        config = ExclusionConfig(
            paths=["docs/*.md"],
            authors=["external"],
            title_patterns=["HOTFIX.*"],
        )

        assert config.paths == ["docs/*.md"]
        assert config.authors == ["external"]
        assert config.title_patterns == ["HOTFIX.*"]


class TestNotificationConfig:
    """Test cases for NotificationConfig."""

    def test_default_values(self):
        """Test default notification values."""
        config = NotificationConfig()

        assert config.discord_channel == "#git-activity"
        assert config.alert_channel == "#alerts"
        assert config.rate_limit == "1 per 5 minutes"

    def test_custom_values(self):
        """Test custom notification values."""
        config = NotificationConfig(
            discord_channel="#custom",
            alert_channel="#custom-alerts",
            rate_limit="5 per 10 minutes",
        )

        assert config.discord_channel == "#custom"
        assert config.alert_channel == "#custom-alerts"
        assert config.rate_limit == "5 per 10 minutes"


class TestLoadConfig:
    """Test cases for load_config function."""

    def test_load_default(self):
        """Test loading default config when no file exists."""
        with patch.object(Path, "exists", return_value=False):
            config = load_config()

        assert config.enabled is True
        assert config.merge_strategy == "squash"

    def test_load_from_yaml(self):
        """Test loading config from YAML file."""
        yaml_content = """
auto_approval:
  enabled: false
  merge_strategy: merge
  rate_limits:
    max_per_hour: 20
    max_consecutive: 5
  safety_checks:
    require_green_ci: false
  exclusions:
    paths:
      - "docs/*.md"
    authors:
      - "external"
  notifications:
    discord_channel: "#custom"
"""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                config = load_config("config.yaml")

        assert config.enabled is False
        assert config.merge_strategy == "merge"
        assert config.rate_limits.max_per_hour == 20
        assert config.rate_limits.max_consecutive == 5
        assert config.safety_checks.require_green_ci is False
        assert "docs/*.md" in config.exclusions.paths
        assert "external" in config.exclusions.authors
        assert config.notifications.discord_channel == "#custom"

    def test_environment_override(self):
        """Test environment variable overrides."""
        env_vars = {
            "AUTO_APPROVAL_ENABLED": "false",
            "GITEA_URL": "https://env.example.com",
            "GITEA_TOKEN": "env_token",
            "GITEA_REPO_OWNER": "env_owner",
            "GITEA_REPO_NAME": "env_repo",
            "DISCORD_WEBHOOK_URL": "https://discord.env",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with patch.object(Path, "exists", return_value=False):
                config = load_config()

        assert config.enabled is False
        assert config.gitea_url == "https://env.example.com"
        assert config.gitea_token == "env_token"
        assert config.gitea_repo_owner == "env_owner"
        assert config.gitea_repo_name == "env_repo"
        assert config.discord_webhook_url == "https://discord.env"

    def test_environment_partial_override(self):
        """Test partial environment variable overrides."""
        yaml_content = """
auto_approval:
  enabled: true
  merge_strategy: squash
"""

        env_vars = {
            "AUTO_APPROVAL_ENABLED": "false",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("builtins.open", mock_open(read_data=yaml_content)):
                    config = load_config("config.yaml")

        # Environment should override YAML
        assert config.enabled is False
        # YAML value should be preserved
        assert config.merge_strategy == "squash"

    def test_yaml_file_not_found(self):
        """Test handling when YAML file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            config = load_config("nonexistent.yaml")

        # Should return default config
        assert config.enabled is True
        assert isinstance(config.rate_limits, RateLimitConfig)
