"""Tests for strategy adapter - DSL→strategy translation.

ST-MVP-011: Tests for StrategyAdapter bridging StrategyDSL to
StrategyProtocol implementations.
"""

from __future__ import annotations

import pytest

from strategy.adapter import StrategyAdapter, StrategyValidationError
from strategy.registry import StrategyNotFoundError, StrategyRegistry
from strategy.strategies import register_ict_strategies

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> StrategyRegistry:
    """Create a registry with ICT strategies registered."""
    reg = StrategyRegistry()
    register_ict_strategies(reg)
    return reg


@pytest.fixture
def adapter(registry: StrategyRegistry) -> StrategyAdapter:
    """Create an adapter with ICT strategies."""
    return StrategyAdapter(registry)


@pytest.fixture
def valid_ict_dsl() -> dict:
    """Create a valid ICT confluence DSL definition."""
    return {
        "metadata": {"name": "ict_test", "version": "1.0"},
        "signals": {
            "type": "ict_confluence",
            "min_confluence": 60.0,
            "min_signals": 2,
            "require_bos_choch": True,
        },
        "universe": {"symbols": ["BTC/USDT"], "timeframe": "15m"},
        "exits": {
            "stop_loss_type": "atr",
            "take_profit_rr_ratio": 2.0,
        },
    }


# ---------------------------------------------------------------------------
# Adapter: adapt() tests
# ---------------------------------------------------------------------------


class TestAdapterAdapt:
    """Tests for StrategyAdapter.adapt()."""

    def test_adapt_returns_strategy_protocol(
        self, adapter: StrategyAdapter, valid_ict_dsl: dict
    ) -> None:
        """adapt() should return something satisfying StrategyProtocol."""
        strategy = adapter.adapt(valid_ict_dsl)
        assert hasattr(strategy, "name")
        assert hasattr(strategy, "version")
        assert hasattr(strategy, "validate_config")
        assert hasattr(strategy, "generate_signals")
        assert hasattr(strategy, "execute")

    def test_adapt_ict_confluence(
        self, adapter: StrategyAdapter, valid_ict_dsl: dict
    ) -> None:
        """adapt() returns ICT executor for ict_confluence type."""
        strategy = adapter.adapt(valid_ict_dsl)
        assert strategy.name == "ict_confluence"

    def test_adapt_ict_short_alias(self, adapter: StrategyAdapter) -> None:
        """adapt() resolves 'ict' alias to ict_confluence."""
        dsl = {"signals": {"type": "ict"}}
        strategy = adapter.adapt(dsl)
        assert strategy.name == "ict_confluence"

    def test_adapt_creates_fresh_instance(
        self, adapter: StrategyAdapter, valid_ict_dsl: dict
    ) -> None:
        """adapt() should create a new instance each call."""
        s1 = adapter.adapt(valid_ict_dsl)
        s2 = adapter.adapt(valid_ict_dsl)
        assert s1 is not s2


class TestAdapterAdaptErrors:
    """Tests for StrategyAdapter.adapt() error handling."""

    def test_adapt_missing_signals(self, adapter: StrategyAdapter) -> None:
        """adapt() raises on missing 'signals' section."""
        with pytest.raises(StrategyValidationError, match="signals"):
            adapter.adapt({"metadata": {"name": "x"}})

    def test_adapt_signals_not_dict(self, adapter: StrategyAdapter) -> None:
        """adapt() raises when signals is not a dict."""
        with pytest.raises(StrategyValidationError, match="must be a dict"):
            adapter.adapt({"signals": "not_a_dict"})

    def test_adapt_missing_type(self, adapter: StrategyAdapter) -> None:
        """adapt() raises when signals.type is missing."""
        with pytest.raises(StrategyValidationError, match="type"):
            adapter.adapt({"signals": {"min_confluence": 60}})

    def test_adapt_non_dict_input(self, adapter: StrategyAdapter) -> None:
        """adapt() raises when input is not a dict."""
        with pytest.raises(StrategyValidationError, match="must be a dict"):
            adapter.adapt("not a dict")  # type: ignore[arg-type]

    def test_adapt_unknown_type(self, adapter: StrategyAdapter) -> None:
        """adapt() raises for unknown DSL signal type."""
        with pytest.raises(StrategyNotFoundError):
            adapter.adapt({"signals": {"type": "nonexistent_strategy"}})

    def test_adapt_empty_registry(self) -> None:
        """adapt() raises when registry is empty."""
        empty_adapter = StrategyAdapter(StrategyRegistry())
        with pytest.raises(StrategyNotFoundError):
            empty_adapter.adapt({"signals": {"type": "ict_confluence"}})


# ---------------------------------------------------------------------------
# Adapter: adapt_config() tests
# ---------------------------------------------------------------------------


class TestAdapterAdaptConfig:
    """Tests for StrategyAdapter.adapt_config()."""

    def test_adapt_config_ict_signals(
        self, adapter: StrategyAdapter, valid_ict_dsl: dict
    ) -> None:
        """adapt_config() translates DSL signals to executor config."""
        config = adapter.adapt_config(valid_ict_dsl)
        assert config["min_confluence"] == 60.0
        assert config["min_signals"] == 2
        assert config["require_bos_choch"] is True

    def test_adapt_config_exits(
        self, adapter: StrategyAdapter, valid_ict_dsl: dict
    ) -> None:
        """adapt_config() translates DSL exits to executor config."""
        config = adapter.adapt_config(valid_ict_dsl)
        assert config["stop_loss_type"] == "atr"
        assert config["take_profit_rr_ratio"] == 2.0

    def test_adapt_config_exit_threshold_derived(
        self, adapter: StrategyAdapter
    ) -> None:
        """adapt_config() derives exit_threshold from min_confluence."""
        dsl = {
            "signals": {"type": "ict_confluence", "min_confluence": 70.0},
            "exits": {},
        }
        config = adapter.adapt_config(dsl)
        assert config["exit_threshold"] == 35.0  # 70.0 * 0.5

    def test_adapt_config_exit_threshold_explicit(
        self, adapter: StrategyAdapter
    ) -> None:
        """adapt_config() uses explicit exit_threshold when provided."""
        dsl = {
            "signals": {"type": "ict_confluence", "min_confluence": 70.0},
            "exits": {"exit_threshold": 40.0},
        }
        config = adapter.adapt_config(dsl)
        assert config["exit_threshold"] == 40.0

    def test_adapt_config_risk_per_trade(self, adapter: StrategyAdapter) -> None:
        """adapt_config() translates risk_per_trade from exits."""
        dsl = {
            "signals": {"type": "ict_confluence"},
            "exits": {"risk_per_trade": 0.05},
        }
        config = adapter.adapt_config(dsl)
        assert config["risk_per_trade"] == 0.05

    def test_adapt_config_minimal_dsl(self, adapter: StrategyAdapter) -> None:
        """adapt_config() works with minimal DSL (just type)."""
        dsl = {"signals": {"type": "ict_confluence"}, "exits": {}}
        config = adapter.adapt_config(dsl)
        assert isinstance(config, dict)

    def test_adapt_config_validates_dsl(self, adapter: StrategyAdapter) -> None:
        """adapt_config() validates DSL before translating."""
        with pytest.raises(StrategyValidationError):
            adapter.adapt_config({"metadata": {}})


# ---------------------------------------------------------------------------
# Adapter: registry property
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    """Tests for StrategyAdapter registry access."""

    def test_registry_property(
        self, registry: StrategyRegistry, adapter: StrategyAdapter
    ) -> None:
        """adapter.registry returns the injected registry."""
        assert adapter.registry is registry
