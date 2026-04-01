"""Aria governance configuration loader.

Loads and provides runtime access to config/aria/*.yaml files.
Follows the feature_flags.py pattern (frozen dataclass, env override, global singleton).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

REDIS_PREFIX = "chise:aria:config"
CONFIG_PATH_ENV = "ARIA_CONFIG_PATH"
DEFAULT_ARIA_CONFIG_PATH = "/app/config/aria"


# ---------------------------------------------------------------------------
# Inner dataclasses for nested YAML structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BeliefMutation:
    """Governance rules for belief mutation."""

    audit_required: bool = True
    allowed_without_approval: list[str] = field(default_factory=list)
    approval_required: list[str] = field(default_factory=list)
    conflict_resolution: dict[str, Any] = field(default_factory=dict)
    blocked_if_conflicts_with: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DigestConfig:
    """Notification digest configuration."""

    enabled: bool = True
    delivery_time_local: str = "20:00"
    include: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContextAllocation:
    """Single entry in context budget allocation order."""

    name: str = ""
    reserve_pct: int = 0
    mandatory: bool = False


# ---------------------------------------------------------------------------
# Top-level dataclasses (one per YAML file)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentityContract:
    """Parsed identity-contract.yaml."""

    version: int = 1
    contract_id: str = ""
    agent_name: str = ""
    owner_name: str = ""
    status: str = ""
    updated_at: str = ""

    # Computed from YAML: fields that require Craig approval before mutation
    approval_gated_fields: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, data: dict[str, Any]) -> IdentityContract:
        """Build from parsed YAML dict."""
        # Derive approval_gated_fields from belief_policy.disallow_override_of
        belief_policy = data.get("belief_policy", {})
        approval_gated = belief_policy.get("disallow_override_of", [])

        return cls(
            version=data.get("version", 1),
            contract_id=data.get("contract_id", ""),
            agent_name=data.get("agent_name", ""),
            owner_name=data.get("owner_name", ""),
            status=data.get("status", ""),
            updated_at=data.get("updated_at", ""),
            approval_gated_fields=approval_gated,
        )


@dataclass(frozen=True)
class GovernancePolicy:
    """Parsed governance-policy.yaml."""

    version: int = 1
    policy_id: str = ""
    belief_mutation: BeliefMutation = field(default_factory=BeliefMutation)

    @classmethod
    def from_yaml(cls, data: dict[str, Any]) -> GovernancePolicy:
        """Build from parsed YAML dict."""
        bm_data = data.get("belief_mutation", {})
        belief_mutation = BeliefMutation(
            audit_required=bm_data.get("audit_required", True),
            allowed_without_approval=bm_data.get("allowed_without_approval", []),
            approval_required=bm_data.get("approval_required", []),
            conflict_resolution=bm_data.get("conflict_resolution", {}),
            blocked_if_conflicts_with=bm_data.get("blocked_if_conflicts_with", []),
        )
        return cls(
            version=data.get("version", 1),
            policy_id=data.get("policy_id", ""),
            belief_mutation=belief_mutation,
        )


@dataclass(frozen=True)
class NotificationPolicy:
    """Parsed notification-policy.yaml."""

    version: int = 1
    policy_id: str = ""
    timezone: str = "America/Toronto"
    digest_include: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, data: dict[str, Any]) -> NotificationPolicy:
        """Build from parsed YAML dict."""
        digest_data = data.get("digest", {})
        digest_include = digest_data.get("include", [])
        return cls(
            version=data.get("version", 1),
            policy_id=data.get("policy_id", ""),
            timezone=data.get("timezone", "America/Toronto"),
            digest_include=digest_include,
        )


@dataclass(frozen=True)
class ContextBudgetPolicy:
    """Parsed context-budget-policy.yaml."""

    version: int = 1
    policy_id: str = ""
    allocation_order: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, data: dict[str, Any]) -> ContextBudgetPolicy:
        """Build from parsed YAML dict."""
        return cls(
            version=data.get("version", 1),
            policy_id=data.get("policy_id", ""),
            allocation_order=data.get("allocation_order", []),
        )


# ---------------------------------------------------------------------------
# Top-level AriaConfig aggregator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AriaConfig:
    """Aggregated Aria governance configuration from all YAML files.

    Loads config/aria/*.yaml at initialization and exposes frozen dataclasses
    for machine-detectable governance fields.
    """

    identity_contract: IdentityContract = field(default_factory=IdentityContract)
    governance_policy: GovernancePolicy = field(default_factory=GovernancePolicy)
    notification_policy: NotificationPolicy = field(default_factory=NotificationPolicy)
    context_budget_policy: ContextBudgetPolicy = field(
        default_factory=ContextBudgetPolicy
    )

    @classmethod
    def from_directory(cls, config_dir: Path | str) -> AriaConfig:
        """Load all Aria YAML files from a directory.

        Args:
            config_dir: Path to the directory containing aria YAML files.

        Returns:
            AriaConfig instance with all four governance configs loaded.

        Raises:
            FileNotFoundError: If config_dir does not exist.
        """
        config_path = Path(config_dir)
        if not config_path.is_dir():
            raise FileNotFoundError(f"Aria config directory not found: {config_path}")

        identity = cls._load_yaml_file(
            config_path / "identity-contract.yaml", IdentityContract.from_yaml
        )
        governance = cls._load_yaml_file(
            config_path / "governance-policy.yaml", GovernancePolicy.from_yaml
        )
        notification = cls._load_yaml_file(
            config_path / "notification-policy.yaml", NotificationPolicy.from_yaml
        )
        context_budget = cls._load_yaml_file(
            config_path / "context-budget-policy.yaml",
            ContextBudgetPolicy.from_yaml,
        )

        logger.info(
            "Loaded Aria config from %s (identity=%s, governance=%s)",
            config_path,
            identity.contract_id,
            governance.policy_id,
        )

        return cls(
            identity_contract=identity,
            governance_policy=governance,
            notification_policy=notification,
            context_budget_policy=context_budget,
        )

    @staticmethod
    def _load_yaml_file(path: Path, parser: Any) -> Any:
        """Load and parse a single YAML file.

        Args:
            path: Path to the YAML file.
            parser: Callable that takes a dict and returns a dataclass.

        Returns:
            Parsed dataclass instance.
        """
        if not path.is_file():
            logger.warning("Aria config file not found: %s", path)
            return parser({})
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return parser(data)


# ---------------------------------------------------------------------------
# Global singleton (follows feature_flags.py pattern)
# ---------------------------------------------------------------------------

_aria_config: AriaConfig | None = None


def get_aria_config() -> AriaConfig:
    """Get the global AriaConfig instance.

    Lazily initializes from ARIA_CONFIG_PATH env var or default path.

    Returns:
        AriaConfig instance.
    """
    global _aria_config
    if _aria_config is None:
        config_dir = os.getenv(CONFIG_PATH_ENV, DEFAULT_ARIA_CONFIG_PATH)
        _aria_config = AriaConfig.from_directory(config_dir)
    return _aria_config


def set_aria_config(config: AriaConfig) -> None:
    """Set the global AriaConfig instance (mainly for testing).

    Args:
        config: AriaConfig instance to set.
    """
    global _aria_config
    _aria_config = config


def reset_aria_config() -> None:
    """Reset global AriaConfig to None (mainly for testing)."""
    global _aria_config
    _aria_config = None


def _get_repo_root() -> Path:
    """Return the repository root directory.

    Resolution order:
    1. CHISEAI_REPO_ROOT environment variable (if set)
    2. Walk up from this file's location looking for pyproject.toml marker
    """
    env_root = os.environ.get("CHISEAI_REPO_ROOT")
    if env_root:
        root = Path(env_root).resolve()
        if root.exists():
            return root

    current = Path(__file__).resolve()
    for _ in range(6):
        current = current.parent
        if (current / "pyproject.toml").exists():
            return current

    # Ultimate fallback
    return Path(__file__).resolve().parent.parent.parent


def load_aria_governance_policy() -> dict[str, Any]:
    """Load Aria governance policy from config/aria/governance-policy.yaml.

    Returns:
        Governance policy dictionary.
    """
    repo_root = _get_repo_root()
    policy_path = repo_root / "config" / "aria" / "governance-policy.yaml"
    with open(policy_path) as f:
        return yaml.safe_load(f)
