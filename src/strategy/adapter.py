"""Backtest adapter - bridges StrategyDSL definitions to executable strategies.

ST-MVP-011: Takes a StrategyDSL document (as dict) and routes it to the
appropriate StrategyProtocol implementation via the StrategyRegistry.
Translates DSL config format to executor-expected format.

Does NOT import from src/backtesting/ directly — accepts DSL as plain dict.
"""

from __future__ import annotations

from typing import Any

from strategy.contracts import StrategyProtocol
from strategy.registry import StrategyNotFoundError, StrategyRegistry


class StrategyValidationError(ValueError):
    """Raised when a DSL strategy configuration is invalid."""


# Mapping from DSL signal type strings to registry strategy names
_DSL_TYPE_TO_REGISTRY: dict[str, str] = {
    "ict_confluence": "ict_confluence",
    "ict": "ict_confluence",
}


class StrategyAdapter:
    """Adapter bridging StrategyDSL definitions to executable strategies.

    Takes a StrategyDSL document and routes it to the appropriate
    StrategyProtocol implementation via the StrategyRegistry.
    Translates DSL config format to executor-expected format.

    Usage::

        registry = StrategyRegistry()
        register_ict_strategies(registry)
        adapter = StrategyAdapter(registry)

        dsl = {"metadata": {...}, "signals": {"type": "ict_confluence", ...}}
        strategy = adapter.adapt(dsl)
        result = strategy.execute(config, data, capital)
    """

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> StrategyRegistry:
        """The strategy registry used for lookups."""
        return self._registry

    def adapt(self, strategy_dsl: dict[str, Any]) -> StrategyProtocol:
        """Convert DSL strategy definition to executable strategy.

        Args:
            strategy_dsl: StrategyDSL as dict (from YAML/JSON).

        Returns:
            StrategyProtocol implementation ready for execution.

        Raises:
            StrategyValidationError: If DSL is missing required fields.
            StrategyNotFoundError: If strategy type not in registry.
        """
        self._validate_dsl(strategy_dsl)

        strategy_name = self._resolve_strategy_name(strategy_dsl)
        strategy_class, _metadata = self._registry.get(strategy_name)
        strategy = strategy_class()

        return strategy

    def adapt_config(self, strategy_dsl: dict[str, Any]) -> dict[str, Any]:
        """Translate DSL config to executor-specific config.

        Extracts parameters from the DSL ``signals`` and ``exits``
        sections and maps them to the executor's expected config
        format.

        Args:
            strategy_dsl: StrategyDSL as dict.

        Returns:
            Executor-specific configuration dictionary.

        Raises:
            StrategyValidationError: If DSL is missing required fields.
        """
        self._validate_dsl(strategy_dsl)

        signals = strategy_dsl.get("signals", {})
        exits = strategy_dsl.get("exits", {})
        strategy_name = self._resolve_strategy_name(strategy_dsl)

        if strategy_name == "ict_confluence":
            return self._translate_ict_config(signals, exits)

        # Generic passthrough for unknown strategy types
        config: dict[str, Any] = {}
        config.update(signals)
        config.update(exits)
        return config

    def _validate_dsl(self, strategy_dsl: dict[str, Any]) -> None:
        """Validate that DSL has minimum required structure."""
        if not isinstance(strategy_dsl, dict):
            msg = "strategy_dsl must be a dict"
            raise StrategyValidationError(msg)

        if "signals" not in strategy_dsl:
            msg = "strategy_dsl must contain 'signals' section"
            raise StrategyValidationError(msg)

        signals = strategy_dsl["signals"]
        if not isinstance(signals, dict):
            msg = "'signals' must be a dict"
            raise StrategyValidationError(msg)

        if "type" not in signals:
            msg = "'signals' section must contain 'type' key"
            raise StrategyValidationError(msg)

    def _resolve_strategy_name(self, strategy_dsl: dict[str, Any]) -> str:
        """Resolve the DSL signal type to a registry strategy name."""
        signals = strategy_dsl["signals"]
        dsl_type = signals["type"]

        registry_name = _DSL_TYPE_TO_REGISTRY.get(dsl_type)
        if registry_name is None:
            # Try direct lookup as fallback
            if dsl_type in self._registry:
                return dsl_type
            registered = ", ".join(self._registry.list_strategies()) or "(empty)"
            msg = (
                f"DSL signal type '{dsl_type}' not mapped to any "
                f"registered strategy. Registered: {registered}"
            )
            raise StrategyNotFoundError(msg)

        return registry_name

    def _translate_ict_config(
        self,
        signals: dict[str, Any],
        exits: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate ICT DSL sections to ICTConfluenceExecutor config."""
        config: dict[str, Any] = {}

        # Signals section parameters
        if "min_confluence" in signals:
            config["min_confluence"] = float(signals["min_confluence"])

        if "min_signals" in signals:
            config["min_signals"] = int(signals["min_signals"])

        if "require_bos_choch" in signals:
            config["require_bos_choch"] = bool(signals["require_bos_choch"])

        # Exit section parameters
        if "stop_loss_type" in exits:
            config["stop_loss_type"] = exits["stop_loss_type"]

        if "take_profit_rr_ratio" in exits:
            config["take_profit_rr_ratio"] = float(exits["take_profit_rr_ratio"])

        if "risk_per_trade" in exits:
            config["risk_per_trade"] = float(exits["risk_per_trade"])

        # Exit threshold derived from min_confluence if not explicit
        if "exit_threshold" in exits:
            config["exit_threshold"] = float(exits["exit_threshold"])
        elif "min_confluence" in signals:
            config["exit_threshold"] = float(signals["min_confluence"]) * 0.5

        return config
