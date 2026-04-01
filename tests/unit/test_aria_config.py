"""Tests for Aria governance configuration loader.

Tests validate that config/aria/*.yaml files are loadable at runtime
and that key governance fields are machine-detectable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from src.config.aria_config import (
    AriaConfig,
    get_aria_config,
    reset_aria_config,
)

# ---------------------------------------------------------------------------
# Fixture: path to the real config/aria/ directory in repo root
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "config" / "aria"


@pytest.fixture(autouse=True)
def _reset_global():
    """Reset the global singleton between tests."""
    reset_aria_config()
    yield
    reset_aria_config()


@pytest.fixture()
def real_aria_dir():
    """Return path to the real config/aria/ directory."""
    return FIXTURES_DIR


@pytest.fixture()
def aria_config(real_aria_dir):
    """Build an AriaConfig from the real YAML files."""
    return AriaConfig.from_directory(real_aria_dir)


# ---------------------------------------------------------------------------
# Tests: get_aria_config returns a valid config object
# ---------------------------------------------------------------------------


class TestGetAriaConfig:
    """Tests for the global singleton accessor."""

    def test_returns_aria_config_instance(self, real_aria_dir, monkeypatch):
        """get_aria_config() should return an AriaConfig instance."""
        monkeypatch.setenv("ARIA_CONFIG_PATH", str(real_aria_dir))
        config = get_aria_config()
        assert isinstance(config, AriaConfig)

    def test_singleton_returns_same_instance(self, real_aria_dir, monkeypatch):
        """Repeated calls should return the same instance."""
        monkeypatch.setenv("ARIA_CONFIG_PATH", str(real_aria_dir))
        first = get_aria_config()
        second = get_aria_config()
        assert first is second


# ---------------------------------------------------------------------------
# Tests: IdentityContract fields
# ---------------------------------------------------------------------------


class TestIdentityContract:
    """Tests for identity-contract.yaml loading."""

    def test_approval_gated_fields_is_list(self, aria_config):
        """identity_contract.approval_gated_fields should be a list of field names."""
        gated = aria_config.identity_contract.approval_gated_fields
        assert isinstance(gated, list)
        assert all(isinstance(f, str) for f in gated)

    def test_approval_gated_fields_has_expected_items(self, aria_config):
        """approval_gated_fields should include known soul-item entries."""
        gated = aria_config.identity_contract.approval_gated_fields
        assert "hardlined_soul_items" in gated
        assert "prd_objectives" in gated
        assert "approval_gated_rules" in gated

    def test_agent_name(self, aria_config):
        """agent_name should be 'Aria'."""
        assert aria_config.identity_contract.agent_name == "Aria"

    def test_owner_name(self, aria_config):
        """owner_name should be 'Craig'."""
        assert aria_config.identity_contract.owner_name == "Craig"


# ---------------------------------------------------------------------------
# Tests: GovernancePolicy fields
# ---------------------------------------------------------------------------


class TestGovernancePolicy:
    """Tests for governance-policy.yaml loading."""

    def test_belief_mutation_approval_required_is_list(self, aria_config):
        """governance_policy.belief_mutation.approval_required should be a list."""
        approval = aria_config.governance_policy.belief_mutation.approval_required
        assert isinstance(approval, list)
        assert all(isinstance(f, str) for f in approval)

    def test_belief_mutation_audit_required(self, aria_config):
        """belief_mutation.audit_required should be True."""
        assert aria_config.governance_policy.belief_mutation.audit_required is True


# ---------------------------------------------------------------------------
# Tests: NotificationPolicy fields
# ---------------------------------------------------------------------------


class TestNotificationPolicy:
    """Tests for notification-policy.yaml loading."""

    def test_digest_include_is_list(self, aria_config):
        """notification_policy.digest.include should be a list."""
        items = aria_config.notification_policy.digest_include
        assert isinstance(items, list)
        assert all(isinstance(f, str) for f in items)

    def test_digest_include_has_expected_entries(self, aria_config):
        """digest include should contain known notification types."""
        items = aria_config.notification_policy.digest_include
        assert "new_beliefs_added" in items
        assert "lessons_promoted" in items
        assert "top_3_things_aria_learned_today" in items


# ---------------------------------------------------------------------------
# Tests: ContextBudgetPolicy fields
# ---------------------------------------------------------------------------


class TestContextBudgetPolicy:
    """Tests for context-budget-policy.yaml loading."""

    def test_allocation_order_is_list(self, aria_config):
        """context_budget_policy.allocation_order should be a list."""
        order = aria_config.context_budget_policy.allocation_order
        assert isinstance(order, list)

    def test_allocation_order_entries_have_name_and_reserve_pct(self, aria_config):
        """Each allocation_order entry must have 'name' and 'reserve_pct'."""
        order = aria_config.context_budget_policy.allocation_order
        for entry in order:
            assert "name" in entry, f"Missing 'name' in entry: {entry}"
            assert "reserve_pct" in entry, f"Missing 'reserve_pct' in entry: {entry}"

    def test_allocation_order_reserve_pct_sums_reasonable(self, aria_config):
        """Total reserve_pct should sum to 100."""
        order = aria_config.context_budget_policy.allocation_order
        total = sum(e["reserve_pct"] for e in order)
        assert total == 100, f"reserve_pct sums to {total}, expected 100"


# ---------------------------------------------------------------------------
# Tests: env override ARIA_CONFIG_PATH
# ---------------------------------------------------------------------------


class TestEnvOverride:
    """Tests for ARIA_CONFIG_PATH environment variable override."""

    def test_env_override_loads_from_custom_path(self, real_aria_dir, monkeypatch):
        """ARIA_CONFIG_PATH should point to a custom config directory."""
        monkeypatch.setenv("ARIA_CONFIG_PATH", str(real_aria_dir))
        config = get_aria_config()
        assert isinstance(config, AriaConfig)
        assert config.identity_contract.agent_name == "Aria"

    def test_from_directory_raises_on_missing_dir(self, tmp_path):
        """from_directory should raise FileNotFoundError for missing directory."""
        missing = tmp_path / "nonexistent"
        with pytest.raises(FileNotFoundError):
            AriaConfig.from_directory(missing)
