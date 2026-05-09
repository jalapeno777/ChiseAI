"""Strategy implementations - registration and configuration.

ST-MVP-010: ICT Confluence Strategy registration.
"""

from __future__ import annotations

from strategy.contracts import StrategyMetadata
from strategy.executors.ict_executor import ICTConfluenceExecutor
from strategy.registry import StrategyRegistry


def register_ict_strategies(registry: StrategyRegistry) -> None:
    """Register ICT strategies with the strategy registry.

    Args:
        registry: Strategy registry to register into.
    """
    registry.register(
        name="ict_confluence",
        strategy_class=ICTConfluenceExecutor,
        metadata=StrategyMetadata(
            name="ict_confluence",
            version="1.0.0",
            description=(
                "ICT Confluence Strategy using multi-signal "
                "confirmation with BOS/CHoCH priority gate"
            ),
            required_signals=[
                "bos_choch",
                "order_block",
                "fvg",
                "cvd",
            ],
            risk_parameters={
                "max_risk_per_trade": 0.02,
                "stop_loss_type": "atr",
            },
        ),
    )


__all__ = ["register_ict_strategies"]
