"""Tests for ICT Confluence Strategy Executor.

ST-MVP-010: Protocol compliance, signal generation, execution simulation.
"""

from __future__ import annotations

import pytest

from strategy.contracts import StrategyProtocol
from strategy.executors.ict_executor import (
    ICTConfluenceExecutor,
    ICTSignalData,
)
from strategy.registry import StrategyRegistry
from strategy.strategies import register_ict_strategies

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def executor() -> ICTConfluenceExecutor:
    """Create a fresh ICTConfluenceExecutor instance."""
    return ICTConfluenceExecutor()


@pytest.fixture
def default_config() -> dict:
    """Default strategy configuration."""
    return {
        "min_confluence": 60.0,
        "min_signals": 2,
        "require_bos_choch": True,
        "exit_threshold": 30.0,
        "stop_loss_type": "atr",
        "risk_per_trade": 0.02,
        "take_profit_rr_ratio": 2.0,
    }


def _make_bar(
    timestamp: str = "2026-01-01T10:00:00Z",
    close: float = 50000.0,
    high: float = 50100.0,
    low: float = 49900.0,
    confluence_score: float = 75.0,
    ict_signals: list[dict] | None = None,
) -> dict:
    """Create a test market data bar."""
    if ict_signals is None:
        ict_signals = [
            {
                "signal_type": "bos_choch",
                "direction": "bullish",
                "confidence": 0.8,
                "timestamp": timestamp,
            },
            {
                "signal_type": "order_block",
                "direction": "bullish",
                "confidence": 0.7,
                "timestamp": timestamp,
            },
        ]
    return {
        "timestamp": timestamp,
        "open": close - 10,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000.0,
        "confluence_score": confluence_score,
        "ict_signals": ict_signals,
    }


# ---------------------------------------------------------------------------
# Protocol compliance tests
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    """Verify ICTConfluenceExecutor satisfies StrategyProtocol."""

    def test_satisfies_protocol(self, executor: ICTConfluenceExecutor) -> None:
        """Executor must pass isinstance check against StrategyProtocol."""
        assert isinstance(executor, StrategyProtocol)

    def test_name_property(self, executor: ICTConfluenceExecutor) -> None:
        assert executor.name == "ict_confluence"

    def test_version_property(self, executor: ICTConfluenceExecutor) -> None:
        assert executor.version == "1.0.0"

    def test_has_validate_config(self, executor: ICTConfluenceExecutor) -> None:
        assert callable(executor.validate_config)

    def test_has_generate_signals(self, executor: ICTConfluenceExecutor) -> None:
        assert callable(executor.generate_signals)

    def test_has_execute(self, executor: ICTConfluenceExecutor) -> None:
        assert callable(executor.execute)


# ---------------------------------------------------------------------------
# Config validation tests
# ---------------------------------------------------------------------------


class TestValidateConfig:
    """Tests for validate_config method."""

    def test_valid_default_config(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        assert executor.validate_config(default_config) is True

    def test_empty_config_accepted(self, executor: ICTConfluenceExecutor) -> None:
        """Empty config is valid (all params have defaults)."""
        assert executor.validate_config({}) is True

    def test_rejects_non_dict(self, executor: ICTConfluenceExecutor) -> None:
        assert executor.validate_config("not a dict") is False  # type: ignore[arg-type]
        assert executor.validate_config(42) is False  # type: ignore[arg-type]
        assert executor.validate_config(None) is False  # type: ignore[arg-type]

    def test_rejects_bad_min_confluence(self, executor: ICTConfluenceExecutor) -> None:
        assert executor.validate_config({"min_confluence": -1}) is False
        assert executor.validate_config({"min_confluence": 101}) is False
        assert executor.validate_config({"min_confluence": "bad"}) is False

    def test_rejects_bad_min_signals(self, executor: ICTConfluenceExecutor) -> None:
        assert executor.validate_config({"min_signals": 0}) is False
        assert executor.validate_config({"min_signals": 5}) is False
        assert executor.validate_config({"min_signals": 1.5}) is False

    def test_rejects_bad_stop_loss_type(self, executor: ICTConfluenceExecutor) -> None:
        assert executor.validate_config({"stop_loss_type": "trailing"}) is False

    def test_rejects_bad_risk_per_trade(self, executor: ICTConfluenceExecutor) -> None:
        assert executor.validate_config({"risk_per_trade": 0.0}) is False
        assert executor.validate_config({"risk_per_trade": 0.5}) is False

    def test_rejects_bad_rr_ratio(self, executor: ICTConfluenceExecutor) -> None:
        assert executor.validate_config({"take_profit_rr_ratio": 0.0}) is False
        assert executor.validate_config({"take_profit_rr_ratio": -1.0}) is False

    def test_valid_boundary_values(self, executor: ICTConfluenceExecutor) -> None:
        assert executor.validate_config({"min_confluence": 0.0}) is True
        assert executor.validate_config({"min_confluence": 100.0}) is True
        assert executor.validate_config({"min_signals": 1}) is True
        assert executor.validate_config({"min_signals": 4}) is True
        assert executor.validate_config({"risk_per_trade": 0.1}) is True


# ---------------------------------------------------------------------------
# Signal generation tests
# ---------------------------------------------------------------------------


class TestGenerateSignals:
    """Tests for generate_signals method."""

    def test_no_signals_with_empty_data(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        signals = executor.generate_signals([], default_config)
        assert signals == []

    def test_no_signals_without_ict_data(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        bars = [{"close": 50000, "timestamp": "2026-01-01T10:00:00Z"}]
        signals = executor.generate_signals(bars, default_config)
        assert signals == []

    def test_generates_entry_signal(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        bars = [_make_bar(confluence_score=75.0)]
        signals = executor.generate_signals(bars, default_config)

        assert len(signals) == 1
        assert signals[0].signal_type == "entry"
        assert signals[0].direction == "long"
        assert 0.0 < signals[0].confidence <= 1.0
        assert signals[0].metadata["confluence_score"] == 75.0
        assert "bos_choch" in signals[0].metadata["aligned_signals"]

    def test_no_entry_below_min_confluence(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        bars = [_make_bar(confluence_score=40.0)]
        signals = executor.generate_signals(bars, default_config)
        # confluence_score 40 < min_confluence 60 => no entry
        entry_signals = [s for s in signals if s.signal_type == "entry"]
        assert len(entry_signals) == 0

    def test_no_entry_without_bos_choch(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        """When require_bos_choch=True, signals without BOS/CHoCH
        should not generate entries."""
        signals_data = [
            {
                "signal_type": "fvg",
                "direction": "bullish",
                "confidence": 0.7,
                "timestamp": "2026-01-01T10:00:00Z",
            },
            {
                "signal_type": "cvd",
                "direction": "bullish",
                "confidence": 0.6,
                "timestamp": "2026-01-01T10:00:00Z",
            },
        ]
        bars = [_make_bar(confluence_score=75.0, ict_signals=signals_data)]
        signals = executor.generate_signals(bars, default_config)
        entry_signals = [s for s in signals if s.signal_type == "entry"]
        assert len(entry_signals) == 0

    def test_entry_without_bos_when_not_required(
        self, executor: ICTConfluenceExecutor
    ) -> None:
        """When require_bos_choch=False, non-BOS entries allowed."""
        config = {
            "min_confluence": 60.0,
            "min_signals": 2,
            "require_bos_choch": False,
            "exit_threshold": 30.0,
        }
        signals_data = [
            {
                "signal_type": "fvg",
                "direction": "bullish",
                "confidence": 0.7,
                "timestamp": "2026-01-01T10:00:00Z",
            },
            {
                "signal_type": "cvd",
                "direction": "bullish",
                "confidence": 0.6,
                "timestamp": "2026-01-01T10:00:00Z",
            },
        ]
        bars = [_make_bar(confluence_score=75.0, ict_signals=signals_data)]
        signals = executor.generate_signals(bars, config)
        entry_signals = [s for s in signals if s.signal_type == "entry"]
        assert len(entry_signals) == 1

    def test_exit_on_low_confluence(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        bars = [_make_bar(confluence_score=20.0)]
        signals = executor.generate_signals(bars, default_config)
        exit_signals = [
            s
            for s in signals
            if s.signal_type == "exit"
            and s.metadata.get("reason") == "confluence_below_threshold"
        ]
        assert len(exit_signals) == 1
        assert exit_signals[0].direction == "flat"

    def test_exit_on_opposing_bos(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        """Opposing BOS/CHoCH should generate exit signal."""
        signals_data = [
            {
                "signal_type": "bos_choch",
                "direction": "bullish",
                "confidence": 0.8,
                "timestamp": "2026-01-01T10:00:00Z",
            },
            {
                "signal_type": "order_block",
                "direction": "bullish",
                "confidence": 0.7,
                "timestamp": "2026-01-01T10:00:00Z",
            },
            {
                "signal_type": "bos_choch",
                "direction": "bearish",
                "confidence": 0.9,
                "timestamp": "2026-01-01T10:00:00Z",
            },
        ]
        bars = [_make_bar(confluence_score=75.0, ict_signals=signals_data)]
        signals = executor.generate_signals(bars, default_config)
        exit_signals = [
            s
            for s in signals
            if s.signal_type == "exit"
            and s.metadata.get("reason") == "opposing_bos_choch"
        ]
        assert len(exit_signals) == 1

    def test_short_direction_signal(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        signals_data = [
            {
                "signal_type": "bos_choch",
                "direction": "bearish",
                "confidence": 0.8,
                "timestamp": "2026-01-01T10:00:00Z",
            },
            {
                "signal_type": "fvg",
                "direction": "bearish",
                "confidence": 0.7,
                "timestamp": "2026-01-01T10:00:00Z",
            },
        ]
        bars = [_make_bar(confluence_score=75.0, ict_signals=signals_data)]
        signals = executor.generate_signals(bars, default_config)
        entry_signals = [s for s in signals if s.signal_type == "entry"]
        assert len(entry_signals) == 1
        assert entry_signals[0].direction == "short"

    def test_no_signal_for_single_signal_alignment(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        """Only one signal aligned => no entry (need min_signals=2)."""
        signals_data = [
            {
                "signal_type": "bos_choch",
                "direction": "bullish",
                "confidence": 0.8,
                "timestamp": "2026-01-01T10:00:00Z",
            },
        ]
        bars = [_make_bar(confluence_score=75.0, ict_signals=signals_data)]
        signals = executor.generate_signals(bars, default_config)
        entry_signals = [s for s in signals if s.signal_type == "entry"]
        assert len(entry_signals) == 0

    def test_unknown_signal_type_ignored(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        signals_data = [
            {
                "signal_type": "rsi_divergence",
                "direction": "bullish",
                "confidence": 0.9,
                "timestamp": "2026-01-01T10:00:00Z",
            },
            {
                "signal_type": "bos_choch",
                "direction": "bullish",
                "confidence": 0.7,
                "timestamp": "2026-01-01T10:00:00Z",
            },
        ]
        bars = [_make_bar(confluence_score=75.0, ict_signals=signals_data)]
        signals = executor.generate_signals(bars, default_config)
        # Only 1 valid signal (bos_choch), need min_signals=2
        entry_signals = [s for s in signals if s.signal_type == "entry"]
        assert len(entry_signals) == 0


# ---------------------------------------------------------------------------
# Execution simulation tests
# ---------------------------------------------------------------------------


class TestExecute:
    """Tests for execute method."""

    def test_empty_data(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        result = executor.execute(default_config, [], 10000.0)
        assert result["trades"] == 0
        assert result["pnl"] == 0.0
        assert result["win_rate"] == 0.0

    def test_result_keys(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        result = executor.execute(default_config, [], 10000.0)
        expected_keys = {
            "trades",
            "pnl",
            "sharpe",
            "max_drawdown",
            "win_rate",
            "metadata",
        }
        assert set(result.keys()) >= expected_keys

    def test_metadata_contains_strategy_info(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        result = executor.execute(default_config, [], 10000.0)
        assert result["metadata"]["strategy"] == "ict_confluence"
        assert result["metadata"]["version"] == "1.0.0"
        assert result["metadata"]["initial_capital"] == 10000.0

    def test_execution_with_entry_and_exit(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        """Simulate entry then exit via confluence drop."""
        bars = [
            _make_bar(
                timestamp="2026-01-01T10:00:00Z",
                close=50000.0,
                confluence_score=75.0,
            ),
            _make_bar(
                timestamp="2026-01-01T11:00:00Z",
                close=50500.0,
                confluence_score=20.0,
            ),
        ]
        result = executor.execute(default_config, bars, 10000.0)
        assert result["trades"] >= 1
        assert result["pnl"] != 0.0 or result["trades"] == 0

    def test_no_trade_when_no_signals(
        self, executor: ICTConfluenceExecutor, default_config: dict
    ) -> None:
        """Bars without ict_signals produce no trades."""
        bars = [
            {"close": 50000, "timestamp": "t1", "high": 50100, "low": 49900},
            {"close": 50100, "timestamp": "t2", "high": 50200, "low": 50000},
        ]
        result = executor.execute(default_config, bars, 10000.0)
        assert result["trades"] == 0


# ---------------------------------------------------------------------------
# Registry integration tests
# ---------------------------------------------------------------------------


class TestRegistryIntegration:
    """Tests for strategy registration."""

    def test_register_and_lookup(self) -> None:
        registry = StrategyRegistry()
        register_ict_strategies(registry)
        cls, meta = registry.get("ict_confluence")
        assert cls is ICTConfluenceExecutor
        assert meta.name == "ict_confluence"

    def test_registry_validate_strategy(self) -> None:
        registry = StrategyRegistry()
        register_ict_strategies(registry)
        assert registry.validate_strategy("ict_confluence") is True

    def test_registered_instance_satisfies_protocol(self) -> None:
        registry = StrategyRegistry()
        register_ict_strategies(registry)
        cls, _ = registry.get("ict_confluence")
        instance = cls()
        assert isinstance(instance, StrategyProtocol)


# ---------------------------------------------------------------------------
# ICTSignalData tests
# ---------------------------------------------------------------------------


class TestICTSignalData:
    """Tests for ICTSignalData dataclass."""

    def test_create_signal(self) -> None:
        sig = ICTSignalData(
            signal_type="bos_choch",
            direction="bullish",
            confidence=0.8,
            timestamp="2026-01-01T10:00:00Z",
            priority=1,
        )
        assert sig.signal_type == "bos_choch"
        assert sig.direction == "bullish"
        assert sig.priority == 1

    def test_default_priority(self) -> None:
        """Priority defaults to 4 when not specified."""
        sig = ICTSignalData(
            signal_type="fvg",
            direction="bullish",
            confidence=0.7,
            timestamp="2026-01-01T10:00:00Z",
        )
        assert sig.priority == 4

    def test_frozen_immutability(self) -> None:
        sig = ICTSignalData(
            signal_type="fvg",
            direction="bearish",
            confidence=0.6,
            timestamp="2026-01-01T10:00:00Z",
        )
        with pytest.raises(AttributeError):
            sig.confidence = 0.9  # type: ignore[misc]
