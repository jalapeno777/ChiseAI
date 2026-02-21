"""Configuration for auto-approval module."""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path

import yaml


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    max_per_hour: int = 10
    max_consecutive: int = 3
    consecutive_pause_duration: int = 300  # seconds


@dataclass
class SafetyCheckConfig:
    """Safety check configuration."""

    require_green_ci: bool = True
    require_story_id: bool = True
    check_merge_conflicts: bool = True


@dataclass
class ExclusionConfig:
    """Exclusion list configuration."""

    paths: List[str] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    title_patterns: List[str] = field(default_factory=list)


@dataclass
class NotificationConfig:
    """Notification configuration."""

    discord_channel: str = "#git-activity"
    alert_channel: str = "#alerts"
    rate_limit: str = "1 per 5 minutes"


@dataclass
class AutoApprovalConfig:
    """Complete auto-approval configuration."""

    enabled: bool = True
    merge_strategy: str = "squash"  # or "merge"
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)
    safety_checks: SafetyCheckConfig = field(default_factory=SafetyCheckConfig)
    exclusions: ExclusionConfig = field(default_factory=ExclusionConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)

    # Gitea configuration
    gitea_url: Optional[str] = None
    gitea_token: Optional[str] = None
    gitea_repo_owner: Optional[str] = None
    gitea_repo_name: Optional[str] = None

    # Discord webhook
    discord_webhook_url: Optional[str] = None


def load_config(config_path: Optional[str] = None) -> AutoApprovalConfig:
    """Load configuration from YAML file or environment variables.

    Args:
        config_path: Path to config YAML file. If None, uses default locations.

    Returns:
        AutoApprovalConfig instance
    """
    # Default config locations
    if config_path is None:
        possible_paths = [
            "config.yaml",
            "src/autonomous_git/auto_approval/config.yaml",
            "/etc/chiseai/auto_approval_config.yaml",
        ]
        for path in possible_paths:
            if Path(path).exists():
                config_path = path
                break

    config = AutoApprovalConfig()

    # Load from YAML if file exists
    if config_path and Path(config_path).exists():
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)

        if data and "auto_approval" in data:
            aa = data["auto_approval"]
            config.enabled = aa.get("enabled", config.enabled)
            config.merge_strategy = aa.get("merge_strategy", config.merge_strategy)

            if "rate_limits" in aa:
                rl = aa["rate_limits"]
                config.rate_limits = RateLimitConfig(
                    max_per_hour=rl.get("max_per_hour", 10),
                    max_consecutive=rl.get("max_consecutive", 3),
                    consecutive_pause_duration=rl.get(
                        "consecutive_pause_duration", 300
                    ),
                )

            if "safety_checks" in aa:
                sc = aa["safety_checks"]
                config.safety_checks = SafetyCheckConfig(
                    require_green_ci=sc.get("require_green_ci", True),
                    require_story_id=sc.get("require_story_id", True),
                    check_merge_conflicts=sc.get("check_merge_conflicts", True),
                )

            if "exclusions" in aa:
                ex = aa["exclusions"]
                config.exclusions = ExclusionConfig(
                    paths=ex.get("paths", []),
                    authors=ex.get("authors", []),
                    title_patterns=ex.get("title_patterns", []),
                )

            if "notifications" in aa:
                nt = aa["notifications"]
                config.notifications = NotificationConfig(
                    discord_channel=nt.get("discord_channel", "#git-activity"),
                    alert_channel=nt.get("alert_channel", "#alerts"),
                    rate_limit=nt.get("rate_limit", "1 per 5 minutes"),
                )

    # Override with environment variables
    if os.getenv("AUTO_APPROVAL_ENABLED"):
        config.enabled = os.getenv("AUTO_APPROVAL_ENABLED").lower() == "true"
    if os.getenv("GITEA_URL"):
        config.gitea_url = os.getenv("GITEA_URL")
    if os.getenv("GITEA_TOKEN"):
        config.gitea_token = os.getenv("GITEA_TOKEN")
    if os.getenv("GITEA_REPO_OWNER"):
        config.gitea_repo_owner = os.getenv("GITEA_REPO_OWNER")
    if os.getenv("GITEA_REPO_NAME"):
        config.gitea_repo_name = os.getenv("GITEA_REPO_NAME")
    if os.getenv("DISCORD_WEBHOOK_URL"):
        config.discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    return config
