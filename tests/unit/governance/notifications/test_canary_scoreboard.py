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

    def test_legacy_trading_defaults_to_memory_schema(self, legacy_trading_canary):
        """When canary_mode absent, safe default is now memory (rollout-safe)."""
        with patch("glob.glob", return_value=[legacy_trading_canary]):
            from scripts.ops.canary_scoreboard_discord import (
                build_memory_embed,
                load_canary_json,
                select_schema,
            )

            c = load_canary_json(legacy_trading_canary)
            # No canary_mode field
            assert "canary_mode" not in c
            # Safe default is now memory (not trading) for rollout safety
            schema = select_schema(c)
            assert schema == "memory"
            embed = build_memory_embed(c)
            field_names = [f["name"] for f in embed["fields"]]
            # Legacy canary without mode now uses memory schema
            assert "Recall Quality" in field_names
            assert "Context Cost" in field_names


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


class TestModePrecedence:
    """Test mode precedence: env override > payload mode > safe default."""

    def test_env_override_memory(self, trading_canary, monkeypatch):
        """CANARY_SCOREBOARD_MODE=memory forces memory schema even with canary_mode=trading."""
        monkeypatch.setenv("CANARY_SCOREBOARD_MODE", "memory")
        from scripts.ops.canary_scoreboard_discord import select_schema

        canary = {"canary_mode": "trading"}
        assert select_schema(canary) == "memory"

    def test_env_override_trading(self, memory_canary, monkeypatch):
        """CANARY_SCOREBOARD_MODE=trading forces trading schema even with canary_mode=memory."""
        monkeypatch.setenv("CANARY_SCOREBOARD_MODE", "trading")
        from scripts.ops.canary_scoreboard_discord import select_schema

        canary = {"canary_mode": "memory"}
        assert select_schema(canary) == "trading"

    def test_payload_mode_memory(self):
        """canary_mode=memory without env override → memory schema."""
        from scripts.ops.canary_scoreboard_discord import select_schema

        canary = {"canary_mode": "memory"}
        assert select_schema(canary) == "memory"

    def test_payload_mode_trading(self):
        """canary_mode=trading without env override → trading schema."""
        from scripts.ops.canary_scoreboard_discord import select_schema

        canary = {"canary_mode": "trading"}
        assert select_schema(canary) == "trading"

    def test_safe_default_is_memory(self, monkeypatch):
        """No canary_mode, no env → defaults to memory (rollout-safe default)."""
        # Ensure env is NOT set
        monkeypatch.delenv("CANARY_SCOREBOARD_MODE", raising=False)
        from scripts.ops.canary_scoreboard_discord import select_schema

        canary = {}
        assert select_schema(canary) == "memory"

    def test_memory_mode_never_renders_trading_metrics(self):
        """Memory schema must never include Total Trades/Net PnL/Win Rate/Max Drawdown."""
        from scripts.ops.canary_scoreboard_discord import build_memory_embed

        # Memory canary → memory embed should never have trading fields
        canary = {
            "canary_id": "mem-test",
            "name": "Memory Test",
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
        }
        embed = build_memory_embed(canary)
        field_names = [f["name"] for f in embed["fields"]]
        assert "Total Trades" not in field_names
        assert "Net PnL" not in field_names
        assert "Win Rate" not in field_names
        assert "Max Drawdown" not in field_names

    def test_missing_memory_metrics_shows_sentinel(self, tmp_path):
        """When all memory metrics are None, shows MEMORY METRICS MISSING notice."""
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
            assert "MEMORY METRICS MISSING" in field_names


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


# ── Memory Canary Producer Integration Tests ───────────────────────────────


class TestMemoryCanaryProducer:
    """Tests for the memory canary producer script and its output."""

    def test_producer_emits_all_six_fields(self, tmp_path, monkeypatch):
        """Producer output has all 6 metric fields present and non-null."""
        from scripts.ops.canary_memory_producer import (
            build_canary_payload,
            produce_metrics,
        )

        redis_metrics = {}  # empty = use all defaults
        metrics = produce_metrics(redis_metrics)
        payload = build_canary_payload(metrics)

        assert "metrics" in payload
        expected_fields = [
            "recall_quality",
            "context_cost",
            "token_efficiency",
            "staleness_quality",
            "anti_gaming_status",
            "operational_reliability",
        ]
        for field in expected_fields:
            assert field in payload["metrics"], f"Missing field: {field}"
            assert payload["metrics"][field] is not None, f"Null field: {field}"

    def test_producer_no_null_values(self, tmp_path, monkeypatch):
        """When source metrics are available, producer should not write null."""
        from scripts.ops.canary_memory_producer import produce_metrics

        # Simulate available Redis metrics (non-zero)
        redis_metrics = {
            "recall_accuracy": 0.88,
            "context_cost": 12500.0,
            "coverage": 0.75,
            "staleness": 0.90,
            "fp_rate": 0.03,
            "near_dup_rate": 0.05,
        }
        metrics = produce_metrics(redis_metrics)
        for key, value in metrics.items():
            assert value is not None, f"Null value in {key}"

    def test_scoreboard_renders_values_not_missing(self, tmp_path, monkeypatch):
        """With the produced canary, scoreboard build_memory_embed shows no MISSING."""
        from scripts.ops.canary_memory_producer import produce_metrics
        from scripts.ops.canary_scoreboard_discord import build_memory_embed

        # Use defaults (Redis unavailable path)
        redis_metrics = {}
        metrics = produce_metrics(redis_metrics)
        canary = {
            "canary_id": "memory-canary-001",
            "name": "Memory Hybrid Canary",
            "status": "running",
            "canary_mode": "memory",
            "metrics": metrics,
            "description": "Memory domain validation",
        }

        embed = build_memory_embed(canary)
        field_values = {f["name"]: f["value"] for f in embed["fields"]}
        for field_name, field_value in field_values.items():
            assert field_value != "MISSING", f"{field_name} shows MISSING"

    def test_producer_idempotent(self, tmp_path, monkeypatch):
        """Running producer twice produces valid output both times."""
        from scripts.ops.canary_memory_producer import (
            build_canary_payload,
            produce_metrics,
        )

        for i in range(2):
            redis_metrics = {}
            metrics = produce_metrics(redis_metrics)
            payload = build_canary_payload(metrics)

            assert payload["canary_id"] == "memory-canary-001"
            assert payload["status"] == "running"
            assert payload["canary_mode"] == "memory"
            assert "metrics" in payload
            for field in (
                "recall_quality",
                "context_cost",
                "token_efficiency",
                "staleness_quality",
                "anti_gaming_status",
                "operational_reliability",
            ):
                assert field in payload["metrics"], f"Run {i+1}: missing {field}"
