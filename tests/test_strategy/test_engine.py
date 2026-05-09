"""Tests for StrategyEngine - execution routing and error handling.

ST-MVP-009: Strategy execution protocol and registry.
"""

from __future__ import annotations

import pytest

from strategy.contracts import ExecutionResult, StrategyMetadata
from strategy.engine import StrategyEngine
from strategy.registry import StrategyNotFoundError, StrategyRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class SuccessfulStrategy:
    """A strategy that returns successful execution results."""

    @property
    def name(self) -> str:
        return "success_strategy"

    @property
    def version(self) -> str:
        return "1.0.0"

    def validate_config(self, config: dict) -> bool:
        return "symbol" in config

    def generate_signals(self, market_data: list[dict], config: dict) -> list:
        return []

    def execute(
        self, strategy_config: dict, data: list[dict], initial_capital: float
    ) -> dict:
        return {
            "trades": 10,
            "pnl": 500.0,
            "sharpe": 1.5,
            "max_drawdown": 0.08,
            "win_rate": 0.65,
            "metadata": {"executed_at": "2026-01-01"},
        }


class FailingConfigStrategy:
    """A strategy that always fails config validation."""

    @property
    def name(self) -> str:
        return "failing_config"

    @property
    def version(self) -> str:
        return "1.0.0"

    def validate_config(self, config: dict) -> bool:
        return False

    def generate_signals(self, market_data: list[dict], config: dict) -> list:
        return []

    def execute(
        self, strategy_config: dict, data: list[dict], initial_capital: float
    ) -> dict:
        return {
            "trades": 0,
            "pnl": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
        }


def _make_meta(name: str = "test", version: str = "1.0.0") -> StrategyMetadata:
    return StrategyMetadata(name=name, version=version)


def _make_registry_with(
    name: str, cls: type, meta: StrategyMetadata | None = None
) -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(name, cls, meta or _make_meta(name))
    return registry


# ---------------------------------------------------------------------------
# Engine execution tests
# ---------------------------------------------------------------------------


class TestEngineExecution:
    """Tests for strategy execution through the engine."""

    def test_execute_success(self) -> None:
        registry = _make_registry_with("success", SuccessfulStrategy)
        engine = StrategyEngine(registry)

        result = engine.execute(
            strategy_name="success",
            config={"symbol": "BTCUSDT"},
            data=[{"close": 50000}],
            initial_capital=10000.0,
        )

        assert isinstance(result, ExecutionResult)
        assert result.trades == 10
        assert result.pnl == 500.0
        assert result.sharpe == 1.5
        assert result.max_drawdown == 0.08
        assert result.win_rate == 0.65
        assert result.metadata["executed_at"] == "2026-01-01"

    def test_execute_not_found(self) -> None:
        registry = StrategyRegistry()
        engine = StrategyEngine(registry)

        with pytest.raises(StrategyNotFoundError):
            engine.execute("nonexistent", {}, [], 10000.0)

    def test_execute_invalid_config(self) -> None:
        registry = _make_registry_with("fail", FailingConfigStrategy)
        engine = StrategyEngine(registry)

        with pytest.raises(ValueError, match="Invalid config"):
            engine.execute("fail", {"bad": True}, [], 10000.0)

    def test_execute_missing_result_fields_default(self) -> None:
        """Engine should handle missing optional fields gracefully."""

        class MinimalResultStrategy:
            @property
            def name(self) -> str:
                return "minimal"

            @property
            def version(self) -> str:
                return "1.0.0"

            def validate_config(self, config: dict) -> bool:
                return True

            def generate_signals(self, market_data: list[dict], config: dict) -> list:
                return []

            def execute(
                self, strategy_config: dict, data: list[dict], initial_capital: float
            ) -> dict:
                return {}  # Empty result dict

        registry = _make_registry_with("minimal", MinimalResultStrategy)
        engine = StrategyEngine(registry)

        result = engine.execute("minimal", {}, [], 1000.0)
        assert result.trades == 0
        assert result.pnl == 0.0
        assert result.sharpe == 0.0
        assert result.max_drawdown == 0.0
        assert result.win_rate == 0.0
        assert result.metadata == {}


# ---------------------------------------------------------------------------
# Engine validation tests
# ---------------------------------------------------------------------------


class TestEngineValidation:
    """Tests for engine config validation."""

    def test_validate_success(self) -> None:
        registry = _make_registry_with("success", SuccessfulStrategy)
        engine = StrategyEngine(registry)

        assert engine.validate("success", {"symbol": "BTCUSDT"}) is True

    def test_validate_failure(self) -> None:
        registry = _make_registry_with("fail", FailingConfigStrategy)
        engine = StrategyEngine(registry)

        assert engine.validate("fail", {}) is False

    def test_validate_not_found(self) -> None:
        registry = StrategyRegistry()
        engine = StrategyEngine(registry)

        with pytest.raises(StrategyNotFoundError):
            engine.validate("nonexistent", {})


# ---------------------------------------------------------------------------
# Engine metadata tests
# ---------------------------------------------------------------------------


class TestEngineMetadata:
    """Tests for engine metadata retrieval."""

    def test_get_metadata(self) -> None:
        meta = StrategyMetadata(
            name="test",
            version="2.0.0",
            description="Test desc",
            required_signals=["entry"],
        )
        registry = StrategyRegistry()
        registry.register("test", SuccessfulStrategy, meta)
        engine = StrategyEngine(registry)

        result = engine.get_metadata("test")
        assert result.version == "2.0.0"
        assert result.description == "Test desc"
        assert result.required_signals == ["entry"]

    def test_get_metadata_not_found(self) -> None:
        registry = StrategyRegistry()
        engine = StrategyEngine(registry)

        with pytest.raises(StrategyNotFoundError):
            engine.get_metadata("nonexistent")
