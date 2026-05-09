"""Tests for strategy contracts - Protocol compliance and dataclass validation.

ST-MVP-009: Strategy execution protocol and registry.
"""

from __future__ import annotations

import pytest

from strategy.contracts import (
    ExecutionResult,
    SignalResult,
    StrategyMetadata,
    StrategyProtocol,
)

# ---------------------------------------------------------------------------
# Helper: concrete class satisfying StrategyProtocol
# ---------------------------------------------------------------------------


class DummyStrategy:
    """Minimal concrete implementation satisfying StrategyProtocol."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def version(self) -> str:
        return "0.1.0"

    def validate_config(self, config: dict) -> bool:
        return "symbol" in config

    def generate_signals(self, market_data: list[dict], config: dict) -> list:
        return [
            SignalResult(
                signal_type="entry",
                direction="long",
                confidence=0.8,
                timestamp="2026-01-01T00:00:00Z",
            )
        ]

    def execute(
        self, strategy_config: dict, data: list[dict], initial_capital: float
    ) -> dict:
        return {
            "trades": 5,
            "pnl": 100.0,
            "sharpe": 1.5,
            "max_drawdown": 0.1,
            "win_rate": 0.6,
            "metadata": {},
        }


# ---------------------------------------------------------------------------
# SignalResult tests
# ---------------------------------------------------------------------------


class TestSignalResult:
    """Tests for SignalResult dataclass validation."""

    def test_valid_signal(self) -> None:
        signal = SignalResult(
            signal_type="entry",
            direction="long",
            confidence=0.8,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert signal.signal_type == "entry"
        assert signal.direction == "long"
        assert signal.confidence == 0.8

    def test_default_metadata(self) -> None:
        signal = SignalResult(
            signal_type="exit",
            direction="short",
            confidence=0.5,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert signal.metadata == {}

    def test_custom_metadata(self) -> None:
        signal = SignalResult(
            signal_type="stop",
            direction="flat",
            confidence=0.9,
            timestamp="2026-01-01T00:00:00Z",
            metadata={"reason": "trailing_stop_hit"},
        )
        assert signal.metadata["reason"] == "trailing_stop_hit"

    def test_confidence_too_high(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            SignalResult(
                signal_type="entry",
                direction="long",
                confidence=1.5,
                timestamp="2026-01-01T00:00:00Z",
            )

    def test_confidence_negative(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            SignalResult(
                signal_type="entry",
                direction="long",
                confidence=-0.1,
                timestamp="2026-01-01T00:00:00Z",
            )

    def test_invalid_signal_type(self) -> None:
        with pytest.raises(ValueError, match="signal_type"):
            SignalResult(
                signal_type="invalid",
                direction="long",
                confidence=0.5,
                timestamp="2026-01-01T00:00:00Z",
            )

    def test_invalid_direction(self) -> None:
        with pytest.raises(ValueError, match="direction"):
            SignalResult(
                signal_type="entry",
                direction="sideways",
                confidence=0.5,
                timestamp="2026-01-01T00:00:00Z",
            )

    def test_frozen_immutability(self) -> None:
        signal = SignalResult(
            signal_type="entry",
            direction="long",
            confidence=0.8,
            timestamp="2026-01-01T00:00:00Z",
        )
        with pytest.raises(AttributeError):
            signal.confidence = 0.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ExecutionResult tests
# ---------------------------------------------------------------------------


class TestExecutionResult:
    """Tests for ExecutionResult dataclass validation."""

    def test_valid_result(self) -> None:
        result = ExecutionResult(
            trades=10,
            pnl=500.0,
            sharpe=1.5,
            max_drawdown=0.1,
            win_rate=0.6,
        )
        assert result.trades == 10
        assert result.pnl == 500.0
        assert result.sharpe == 1.5

    def test_negative_trades_rejected(self) -> None:
        with pytest.raises(ValueError, match="trades"):
            ExecutionResult(
                trades=-1,
                pnl=0.0,
                sharpe=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
            )

    def test_drawdown_over_one(self) -> None:
        with pytest.raises(ValueError, match="max_drawdown"):
            ExecutionResult(
                trades=5,
                pnl=100.0,
                sharpe=1.0,
                max_drawdown=1.5,
                win_rate=0.5,
            )

    def test_win_rate_over_one(self) -> None:
        with pytest.raises(ValueError, match="win_rate"):
            ExecutionResult(
                trades=5,
                pnl=100.0,
                sharpe=1.0,
                max_drawdown=0.1,
                win_rate=1.5,
            )

    def test_frozen_immutability(self) -> None:
        result = ExecutionResult(
            trades=1,
            pnl=10.0,
            sharpe=1.0,
            max_drawdown=0.05,
            win_rate=0.5,
        )
        with pytest.raises(AttributeError):
            result.pnl = 999.0  # type: ignore[misc]

    def test_boundary_values(self) -> None:
        """Test boundary values (0 and 1) are accepted."""
        result = ExecutionResult(
            trades=0,
            pnl=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
        )
        assert result.trades == 0

        result2 = ExecutionResult(
            trades=100,
            pnl=1000.0,
            sharpe=3.0,
            max_drawdown=1.0,
            win_rate=1.0,
        )
        assert result2.max_drawdown == 1.0


# ---------------------------------------------------------------------------
# StrategyMetadata tests
# ---------------------------------------------------------------------------


class TestStrategyMetadata:
    """Tests for StrategyMetadata dataclass validation."""

    def test_valid_metadata(self) -> None:
        meta = StrategyMetadata(
            name="momentum_v1",
            version="1.0.0",
            description="A momentum strategy",
        )
        assert meta.name == "momentum_v1"
        assert meta.version == "1.0.0"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name"):
            StrategyMetadata(name="", version="1.0.0")

    def test_empty_version_rejected(self) -> None:
        with pytest.raises(ValueError, match="version"):
            StrategyMetadata(name="test", version="")

    def test_defaults(self) -> None:
        meta = StrategyMetadata(name="test", version="0.1.0")
        assert meta.description == ""
        assert meta.required_signals == []
        assert meta.risk_parameters == {}

    def test_frozen_immutability(self) -> None:
        meta = StrategyMetadata(name="test", version="0.1.0")
        with pytest.raises(AttributeError):
            meta.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StrategyProtocol runtime_checkable tests
# ---------------------------------------------------------------------------


class TestStrategyProtocol:
    """Tests for StrategyProtocol runtime checkability."""

    def test_concrete_satisfies_protocol(self) -> None:
        strategy = DummyStrategy()
        assert isinstance(strategy, StrategyProtocol)

    def test_incomplete_class_fails_check(self) -> None:
        class IncompleteStrategy:
            @property
            def name(self) -> str:
                return "incomplete"

            # Missing: version, validate_config, generate_signals, execute

        assert not isinstance(IncompleteStrategy(), StrategyProtocol)

    def test_protocol_methods_callable(self) -> None:
        strategy = DummyStrategy()
        assert strategy.validate_config({"symbol": "BTCUSDT"}) is True
        assert strategy.validate_config({}) is False

        signals = strategy.generate_signals([], {})
        assert len(signals) == 1
        assert isinstance(signals[0], SignalResult)

        result = strategy.execute({}, [], 10000.0)
        assert result["trades"] == 5
