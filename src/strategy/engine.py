"""Strategy Engine - routes execution to registered implementations.

TEMPO-2026-001: Strategy execution with distributed tracing.
ST-MVP-009: Updated to use StrategyProtocol and StrategyRegistry.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace

from .contracts import ExecutionResult, StrategyMetadata
from .registry import StrategyRegistry
from .tracing import trace_strategy_execution


class StrategyEngine:
    """Strategy execution engine with OpenTelemetry tracing.

    Routes strategy execution to registered implementations via
    StrategyProtocol. Validates config before execution and wraps
    results in ExecutionResult dataclass.

    Usage::

        registry = StrategyRegistry()
        engine = StrategyEngine(registry)
        result = engine.execute("momentum_v1", config, data, 10000.0)
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        service_name: str = "chiseai-strategy",
    ) -> None:
        """Initialize the strategy engine.

        Args:
            registry: Strategy registry to look up implementations.
            service_name: Name of the service for OTel tracing.
        """
        self.registry = registry
        self.service_name = service_name
        self.tracer = trace.get_tracer(service_name)

    @trace_strategy_execution
    def execute(
        self,
        strategy_name: str,
        config: dict[str, Any],
        data: list[dict[str, Any]],
        initial_capital: float,
    ) -> ExecutionResult:
        """Execute a strategy by name via the registry.

        Looks up the strategy in the registry, validates config,
        instantiates the strategy, and delegates execution.

        Args:
            strategy_name: Name of the registered strategy.
            config: Strategy configuration dictionary.
            data: OHLCV market data to execute against.
            initial_capital: Starting capital for execution.

        Returns:
            ExecutionResult with P&L, risk metrics, and trade stats.

        Raises:
            StrategyNotFoundError: If strategy is not registered.
            ValueError: If config validation fails.
        """
        with self.tracer.start_as_current_span("strategy.execute.logic") as span:
            span.set_attribute("chiseai.strategy.name", strategy_name)
            span.set_attribute("chiseai.strategy.capital", initial_capital)

            strategy_class, _metadata = self.registry.get(strategy_name)
            strategy = strategy_class()

            if not strategy.validate_config(config):
                msg = f"Invalid config for strategy '{strategy_name}'"
                raise ValueError(msg)

            span.set_attribute("chiseai.strategy.config_valid", True)

            raw_result = strategy.execute(
                strategy_config=config,
                data=data,
                initial_capital=initial_capital,
            )

            result = ExecutionResult(
                trades=raw_result.get("trades", 0),
                pnl=raw_result.get("pnl", 0.0),
                sharpe=raw_result.get("sharpe", 0.0),
                max_drawdown=raw_result.get("max_drawdown", 0.0),
                win_rate=raw_result.get("win_rate", 0.0),
                metadata=raw_result.get("metadata", {}),
            )

            span.set_attribute("chiseai.strategy.result.trades", result.trades)
            span.set_attribute("chiseai.strategy.result.pnl", result.pnl)
            span.set_attribute("chiseai.strategy.result.status", "success")

            return result

    @trace_strategy_execution
    def validate(
        self,
        strategy_name: str,
        config: dict[str, Any],
    ) -> bool:
        """Validate a strategy configuration.

        Args:
            strategy_name: Name of the registered strategy.
            config: Strategy configuration to validate.

        Returns:
            True if the configuration is valid.

        Raises:
            StrategyNotFoundError: If strategy is not registered.
        """
        with self.tracer.start_as_current_span("strategy.validate") as span:
            span.set_attribute("chiseai.strategy.name", strategy_name)

            strategy_class, _metadata = self.registry.get(strategy_name)
            strategy = strategy_class()

            is_valid = strategy.validate_config(config)
            span.set_attribute("chiseai.strategy.validated", is_valid)
            return is_valid

    def get_metadata(self, strategy_name: str) -> StrategyMetadata:
        """Retrieve metadata for a registered strategy.

        Args:
            strategy_name: Name of the registered strategy.

        Returns:
            Strategy metadata.

        Raises:
            StrategyNotFoundError: If strategy is not registered.
        """
        return self.registry.get_metadata(strategy_name)
