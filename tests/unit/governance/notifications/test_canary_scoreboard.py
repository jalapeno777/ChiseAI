"""Tests for canary scoreboard Discord notification."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def memory_canary(tmp_path):
    """Memory-mode canary JSON."""
    data = {
        "canary_id": "mem-canary-001",
        "name": "Memory Canary",
        "status": "running",
        "canary_mode": "memory",
        "metrics": {
            "recall_quality": 0.85,
            "context_cost": 12500,
            "token_efficiency": 0.72,
            "staleness_quality": 0.91,
            "anti_gaming_status": "pass",
            "operational_reliability": 0.95,
        },
        "description": "Memory domain validation",
    }
    path = tmp_path / "memory-canary.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture
def partial_memory_canary(tmp_path):
    """Memory-mode canary with SOME fields missing."""
    data = {
        "canary_id": "mem-canary-partial",
        "name": "Partial Memory Canary",
        "status": "running",
        "canary_mode": "memory",
        "metrics": {
            "recall_quality": 0.85,
            # context_cost, token_efficiency MISSING
            "staleness_quality": 0.91,
            # anti_gaming_status MISSING
            "operational_reliability": 0.95,
        },
        "description": "Partial metrics",
    }
    path = tmp_path / "partial-memory-canary.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture
def trading_canary(tmp_path):
    """Trading-mode canary (backward compat)."""
    data = {
        "canary_id": "trade-canary-001",
        "name": "Trading Canary",
        "status": "running",
        "canary_mode": "trading",
        "metrics": {
            "total_trades": 47,
            "net_profit": 312.50,
            "win_rate": 0.583,
            "max_drawdown_pct": 0.032,
        },
        "description": "Trading domain validation",
    }
    path = tmp_path / "trading-canary.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture
def legacy_trading_canary(tmp_path):
    """Trading canary WITHOUT canary_mode field (legacy backward compat)."""
    data = {
        "canary_id": "legacy-trade",
        "name": "Legacy Trading Canary",
        "status": "running",
        # no canary_mode field at all
        "metrics": {
            "total_trades": 20,
            "net_profit": 150.0,
            "win_rate": 0.55,
            "max_drawdown_pct": 0.05,
        },
        "description": "Legacy",
    }
    path = tmp_path / "legacy-trading-canary.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture
def no_active_canaries(tmp_path):
    """Empty canary dir."""
    return str(tmp_path)


# ── Schema Selection Tests ────────────────────────────────────────────────


class TestSchemaSelection:
    """Test that correct schema is selected by canary_mode."""

    def test_memory_mode_selects_memory_schema(self, memory_canary):
        """When canary_mode=memory, memory schema fields are used."""
        # Patch glob to return our memory canary
        with patch("glob.glob", return_value=[memory_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_memory_embed,
                load_canary_json,
            )

            c = load_canary_json(memory_canary)
            assert c.get("canary_mode") == "memory"
            # Should use memory schema, not trading
            embed = build_memory_embed(c)
            field_names = [f["name"] for f in embed["fields"]]
            assert "Recall Quality" in field_names
            assert "Context Cost" in field_names
            assert "Token Efficiency" in field_names
            assert "Staleness Quality" in field_names
            assert "Anti-Gaming Status" in field_names
            assert "Operational Reliability" in field_names
            # Should NOT have trading fields
            assert "Total Trades" not in field_names
            assert "Net PnL" not in field_names
            assert "Win Rate" not in field_names
            assert "Max Drawdown" not in field_names

    def test_trading_mode_selects_trading_schema(self, trading_canary):
        """When canary_mode=trading, trading schema fields are used."""
        with patch("glob.glob", return_value=[trading_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_trading_embed,
                load_canary_json,
            )

            c = load_canary_json(trading_canary)
            assert c.get("canary_mode") == "trading"
            embed = build_trading_embed(c)
            field_names = [f["name"] for f in embed["fields"]]
            assert "Total Trades" in field_names
            assert "Net PnL" in field_names
            assert "Win Rate" in field_names
            assert "Max Drawdown" in field_names
            # Should NOT have memory fields
            assert "Recall Quality" not in field_names
            assert "Context Cost" not in field_names

    def test_legacy_trading_defaults_to_trading_schema(self, legacy_trading_canary):
        """When canary_mode absent, default to trading schema (backward compat)."""
        with patch("glob.glob", return_value=[legacy_trading_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_trading_embed,
                load_canary_json,
                select_schema,
            )

            c = load_canary_json(legacy_trading_canary)
            # No canary_mode field
            assert "canary_mode" not in c
            # Should default to trading
            schema = select_schema(c)
            assert schema == "trading"
            embed = build_trading_embed(c)
            field_names = [f["name"] for f in embed["fields"]]
            assert "Total Trades" in field_names
            assert "Net PnL" in field_names


# ── Missing-Data Rendering Tests ──────────────────────────────────────────


class TestMissingDataRendering:
    """Test MISSING display for partial data."""

    def test_missing_memory_fields_shows_missing_label(self, partial_memory_canary):
        """When memory fields are absent, field shows MISSING not zero."""
        with patch("glob.glob", return_value=[partial_memory_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_memory_embed,
                load_canary_json,
            )

            c = load_canary_json(partial_memory_canary)
            embed = build_memory_embed(c)
            field_names = [f["name"] for f in embed["fields"]]
            # Present fields should show values
            recall_field = next(
                f for f in embed["fields"] if f["name"] == "Recall Quality"
            )
            assert recall_field["value"] == "0.85"
            # Missing fields should show MISSING
            cost_field = next(f for f in embed["fields"] if f["name"] == "Context Cost")
            assert cost_field["value"] == "MISSING"
            eff_field = next(
                f for f in embed["fields"] if f["name"] == "Token Efficiency"
            )
            assert eff_field["value"] == "MISSING"
            gaming_field = next(
                f for f in embed["fields"] if f["name"] == "Anti-Gaming Status"
            )
            assert gaming_field["value"] == "MISSING"

    def test_all_memory_fields_missing_shows_full_missing_notice(self, tmp_path):
        """When ALL memory fields are absent, shows MEMORY METRICS MISSING notice."""
        # Create a canary with memory mode but NO metrics at all
        data = {
            "canary_id": "all-missing",
            "name": "All Missing Canary",
            "status": "running",
            "canary_mode": "memory",
            "metrics": {},
            "description": "All fields missing",
        }
        path = tmp_path / "all-missing.json"
        path.write_text(json.dumps(data))

        with patch("glob.glob", return_value=[str(path)]):
            from scripts.ops.canary_scoreboard_discord import (
                build_memory_embed,
                load_canary_json,
            )

            c = load_canary_json(str(path))
            embed = build_memory_embed(c)
            field_names = [f["name"] for f in embed["fields"]]
            # Should have the full missing notice
            assert "MEMORY METRICS MISSING" in field_names
            missing_field = next(
                f for f in embed["fields"] if f["name"] == "MEMORY METRICS MISSING"
            )
            assert "context_cost" in missing_field["value"].lower()
            assert "token_efficiency" in missing_field["value"].lower()
            assert "anti_gaming_status" in missing_field["value"].lower()

    def test_trading_zeros_not_shown_for_memory_canary(self, memory_canary):
        """Trading fields (PnL, Win Rate) are NOT shown at all for memory canary."""
        with patch("glob.glob", return_value=[memory_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_memory_embed,
                load_canary_json,
            )

            c = load_canary_json(memory_canary)
            embed = build_memory_embed(c)
            field_names = [f["name"] for f in embed["fields"]]
            # Trading fields should not even exist in the field list
            assert "Total Trades" not in field_names
            assert "Net PnL" not in field_names
            assert "Win Rate" not in field_names
            assert "Max Drawdown" not in field_names


# ── Discord Payload Tests ──────────────────────────────────────────────────


class TestDiscordPayload:
    """Test Discord embed structure for each mode."""

    def test_memory_embed_has_correct_fields(self, memory_canary):
        """Memory embed contains: recall_quality, context_cost, token_efficiency,
        staleness_quality, anti_gaming_status, operational_reliability."""
        with patch("glob.glob", return_value=[memory_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_memory_embed,
                load_canary_json,
            )

            c = load_canary_json(memory_canary)
            embed = build_memory_embed(c)
            field_names = [f["name"] for f in embed["fields"]]
            expected = [
                "Recall Quality",
                "Context Cost",
                "Token Efficiency",
                "Staleness Quality",
                "Anti-Gaming Status",
                "Operational Reliability",
            ]
            for exp in expected:
                assert exp in field_names, f"Missing field: {exp}"

    def test_trading_embed_has_correct_fields(self, trading_canary):
        """Trading embed contains: Total Trades, Net PnL, Win Rate, Max Drawdown."""
        with patch("glob.glob", return_value=[trading_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_trading_embed,
                load_canary_json,
            )

            c = load_canary_json(trading_canary)
            embed = build_trading_embed(c)
            field_names = [f["name"] for f in embed["fields"]]
            expected = ["Total Trades", "Net PnL", "Win Rate", "Max Drawdown"]
            for exp in expected:
                assert exp in field_names, f"Missing field: {exp}"

    def test_memory_embed_color_is_neutral_blue(self, memory_canary):
        """Memory embed uses neutral color (0x0088FF), not PnL-based."""
        with patch("glob.glob", return_value=[memory_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_memory_embed,
                load_canary_json,
            )

            c = load_canary_json(memory_canary)
            embed = build_memory_embed(c)
            # Memory mode uses blue/neutral color
            assert embed["color"] == 0x0088FF

    def test_trading_embed_color_is_pnl_based(self, trading_canary):
        """Trading embed uses green/red based on PnL."""
        with patch("glob.glob", return_value=[trading_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_trading_embed,
                load_canary_json,
            )

            c = load_canary_json(trading_canary)
            embed = build_trading_embed(c)
            # Positive PnL -> green
            assert embed["color"] == 0x00FF00

    def test_missing_embed_shows_grey_color(self, no_active_canaries):
        """No-active-canary embed uses grey (0x808080)."""
        # This tests the no-active-canaries path
        with patch("glob.glob", return_value=[]):
            from scripts.ops.canary_scoreboard_discord import build_missing_embed

            embed = build_missing_embed()
            assert embed["color"] == 0x808080

    def test_memory_embed_uses_blue_not_green_red(self, memory_canary):
        """Memory embed never uses green/red even if all metrics are positive."""
        with patch("glob.glob", return_value=[memory_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_memory_embed,
                load_canary_json,
            )

            c = load_canary_json(memory_canary)
            embed = build_memory_embed(c)
            # Should be blue/neutral, not green or red
            assert embed["color"] == 0x0088FF
            assert embed["color"] != 0x00FF00  # not green
            assert embed["color"] != 0xFF0000  # not red
