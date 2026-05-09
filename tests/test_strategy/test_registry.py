"""Tests for StrategyRegistry - registration, lookup, validation.

ST-MVP-009: Strategy execution protocol and registry.
"""

from __future__ import annotations

import pytest

from strategy.contracts import StrategyMetadata
from strategy.registry import (
    StrategyNotFoundError,
    StrategyRegistrationError,
    StrategyRegistry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class GoodStrategy:
    """A strategy that satisfies StrategyProtocol."""

    @property
    def name(self) -> str:
        return "good"

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
        return {
            "trades": 0,
            "pnl": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
        }


class PartialStrategy:
    """A strategy missing some protocol methods."""

    @property
    def name(self) -> str:
        return "partial"

    # Missing: version property and several methods


def _make_metadata(name: str = "test", version: str = "1.0.0") -> StrategyMetadata:
    return StrategyMetadata(name=name, version=version)


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegistryRegistration:
    """Tests for strategy registration."""

    def test_register_and_get(self) -> None:
        registry = StrategyRegistry()
        meta = _make_metadata("momentum_v1")
        registry.register("momentum_v1", GoodStrategy, meta)

        cls, returned_meta = registry.get("momentum_v1")
        assert cls is GoodStrategy
        assert returned_meta.name == "momentum_v1"

    def test_register_duplicate_rejected(self) -> None:
        registry = StrategyRegistry()
        meta = _make_metadata("test")
        registry.register("test", GoodStrategy, meta)

        with pytest.raises(StrategyRegistrationError, match="already registered"):
            registry.register("test", GoodStrategy, meta)

    def test_register_empty_name_rejected(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(StrategyRegistrationError, match="non-empty"):
            registry.register("", GoodStrategy, _make_metadata())

    def test_register_whitespace_name_rejected(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(StrategyRegistrationError, match="non-empty"):
            registry.register("   ", GoodStrategy, _make_metadata())

    def test_register_none_class_rejected(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(StrategyRegistrationError, match="must not be None"):
            registry.register("test", None, _make_metadata())  # type: ignore[arg-type]

    def test_register_wrong_metadata_type_rejected(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(StrategyRegistrationError, match="StrategyMetadata"):
            registry.register("test", GoodStrategy, "not_metadata")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Lookup tests
# ---------------------------------------------------------------------------


class TestRegistryLookup:
    """Tests for strategy lookup and listing."""

    def test_get_not_found(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(StrategyNotFoundError):
            registry.get("nonexistent")

    def test_list_strategies_empty(self) -> None:
        registry = StrategyRegistry()
        assert registry.list_strategies() == []

    def test_list_strategies_sorted(self) -> None:
        registry = StrategyRegistry()
        registry.register("zebra", GoodStrategy, _make_metadata("zebra"))
        registry.register("alpha", GoodStrategy, _make_metadata("alpha"))
        registry.register("mid", GoodStrategy, _make_metadata("mid"))

        assert registry.list_strategies() == ["alpha", "mid", "zebra"]

    def test_contains(self) -> None:
        registry = StrategyRegistry()
        registry.register("test", GoodStrategy, _make_metadata())
        assert "test" in registry
        assert "other" not in registry

    def test_len(self) -> None:
        registry = StrategyRegistry()
        assert len(registry) == 0
        registry.register("a", GoodStrategy, _make_metadata("a"))
        assert len(registry) == 1
        registry.register("b", GoodStrategy, _make_metadata("b"))
        assert len(registry) == 2

    def test_get_metadata(self) -> None:
        registry = StrategyRegistry()
        meta = StrategyMetadata(
            name="test",
            version="2.0.0",
            description="Test strategy",
            required_signals=["entry", "exit"],
        )
        registry.register("test", GoodStrategy, meta)

        result = registry.get_metadata("test")
        assert result.version == "2.0.0"
        assert result.description == "Test strategy"
        assert result.required_signals == ["entry", "exit"]

    def test_get_metadata_not_found(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(StrategyNotFoundError):
            registry.get_metadata("nonexistent")


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestRegistryValidation:
    """Tests for strategy protocol validation."""

    def test_validate_good_strategy(self) -> None:
        registry = StrategyRegistry()
        registry.register("good", GoodStrategy, _make_metadata())
        assert registry.validate_strategy("good") is True

    def test_validate_partial_strategy(self) -> None:
        registry = StrategyRegistry()
        registry.register("partial", PartialStrategy, _make_metadata())
        assert registry.validate_strategy("partial") is False

    def test_validate_not_found(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(StrategyNotFoundError):
            registry.validate_strategy("nonexistent")


# ---------------------------------------------------------------------------
# Unregister tests
# ---------------------------------------------------------------------------


class TestRegistryUnregister:
    """Tests for strategy unregistration."""

    def test_unregister(self) -> None:
        registry = StrategyRegistry()
        registry.register("test", GoodStrategy, _make_metadata())
        assert "test" in registry

        registry.unregister("test")
        assert "test" not in registry
        assert len(registry) == 0

    def test_unregister_not_found(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(StrategyNotFoundError):
            registry.unregister("nonexistent")

    def test_unregister_then_reregister(self) -> None:
        registry = StrategyRegistry()
        meta1 = _make_metadata("test", "1.0.0")
        registry.register("test", GoodStrategy, meta1)
        registry.unregister("test")

        meta2 = _make_metadata("test", "2.0.0")
        registry.register("test", GoodStrategy, meta2)
        _, returned = registry.get("test")
        assert returned.version == "2.0.0"
