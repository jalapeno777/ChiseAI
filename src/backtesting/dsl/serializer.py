"""DSL Serializer - Convert DSL dataclasses to dictionaries.

This module handles serialization of typed DSL dataclasses into dictionaries
suitable for YAML/JSON output.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from src.backtesting.dsl.models import (
    StrategyDSL,
    Metadata,
    Universe,
    Signals,
    Filters,
    Exits,
    Sizing,
    ExecutionPolicy,
    RiskRules,
    TelemetryTags,
)


class DSLSerializer:
    """Serializer for converting DSL dataclasses to dictionaries."""

    @classmethod
    def serialize(cls, dsl: StrategyDSL) -> dict[str, Any]:
        """Serialize complete DSL to dictionary.

        Args:
            dsl: StrategyDSL instance

        Returns:
            Dictionary representation
        """
        return {
            "metadata": cls._serialize_metadata(dsl.metadata),
            "universe": cls._serialize_universe(dsl.universe),
            "signals": cls._serialize_signals(dsl.signals),
            "filters": cls._serialize_filters(dsl.filters),
            "exits": cls._serialize_exits(dsl.exits),
            "sizing": cls._serialize_sizing(dsl.sizing),
            "execution_policy": cls._serialize_execution_policy(dsl.execution_policy),
            "risk_rules": cls._serialize_risk_rules(dsl.risk_rules),
            "telemetry_tags": cls._serialize_telemetry_tags(dsl.telemetry_tags),
        }

    @classmethod
    def _serialize_enum(cls, value: Enum) -> str:
        """Serialize enum to string."""
        return value.value

    @classmethod
    def _serialize_metadata(cls, metadata: Metadata) -> dict[str, Any]:
        """Serialize metadata section."""
        return {
            "name": metadata.name,
            "version": metadata.version,
            "description": metadata.description,
            "author": metadata.author,
            "created_at": metadata.created_at,
            "updated_at": metadata.updated_at,
            "tags": list(metadata.tags),
            "category": cls._serialize_enum(metadata.category),
            "timeframes": [cls._serialize_enum(tf) for tf in metadata.timeframes],
            "status": cls._serialize_enum(metadata.status),
        }

    @classmethod
    def _serialize_universe(cls, universe: Universe) -> dict[str, Any]:
        """Serialize universe section."""
        return {
            "symbols": [
                {
                    "symbol": s.symbol,
                    "exchange": s.exchange,
                    "market_type": cls._serialize_enum(s.market_type),
                }
                for s in universe.symbols
            ],
            "sessions": [
                {
                    "name": s.name,
                    "timezone": s.timezone,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "days": [cls._serialize_enum(d) for d in s.days],
                }
                for s in universe.sessions
            ],
            "filters": {
                "min_24h_volume_usd": universe.filters.min_24h_volume_usd,
                "max_spread_bps": universe.filters.max_spread_bps,
                "min_liquidity_depth_usd": universe.filters.min_liquidity_depth_usd,
            },
        }

    @classmethod
    def _serialize_signals(cls, signals: Signals) -> dict[str, Any]:
        """Serialize signals section."""
        return {
            "entry_logic": cls._serialize_enum(signals.entry_logic),
            "indicators": [
                {
                    "name": i.name,
                    "type": cls._serialize_enum(i.type),
                    "parameters": i.parameters,
                    "conditions": [
                        {
                            "operator": cls._serialize_enum(c.operator),
                            "threshold": c.threshold,
                            "direction": cls._serialize_enum(c.direction),
                        }
                        for c in i.conditions
                    ],
                }
                for i in signals.indicators
            ],
            "confluence": {
                "enabled": signals.confluence.enabled,
                "min_score": signals.confluence.min_score,
                "min_confidence": signals.confluence.min_confidence,
                "require_alignment": signals.confluence.require_alignment,
            },
            "cooldown": {
                "bars": signals.cooldown.bars,
                "timeframe": cls._serialize_enum(signals.cooldown.timeframe),
            },
        }

    @classmethod
    def _serialize_filters(cls, filters: Filters) -> dict[str, Any]:
        """Serialize filters section."""
        return {
            "regime": {
                "enabled": filters.regime.enabled,
                "allowed_regimes": [
                    cls._serialize_enum(r) for r in filters.regime.allowed_regimes
                ],
                "detection_method": cls._serialize_enum(
                    filters.regime.detection_method
                ),
                "adx_threshold": filters.regime.adx_threshold,
            },
            "volatility": {
                "enabled": filters.volatility.enabled,
                "method": cls._serialize_enum(filters.volatility.method),
                "atr_period": filters.volatility.atr_period,
                "min_atr_percent": filters.volatility.min_atr_percent,
                "max_atr_percent": filters.volatility.max_atr_percent,
            },
            "time_based": [
                {
                    "name": t.name,
                    "type": cls._serialize_enum(t.type),
                    "action": cls._serialize_enum(t.action),
                    "parameters": t.parameters,
                }
                for t in filters.time_based
            ],
            "correlation": {
                "enabled": filters.correlation.enabled,
                "max_correlation": filters.correlation.max_correlation,
                "lookback_days": filters.correlation.lookback_days,
            },
        }

    @classmethod
    def _serialize_exits(cls, exits: Exits) -> dict[str, Any]:
        """Serialize exits section."""
        return {
            "stop_loss": {
                "enabled": exits.stop_loss.enabled,
                "type": cls._serialize_enum(exits.stop_loss.type),
                "fixed_percent": exits.stop_loss.fixed_percent,
                "atr_multiplier": exits.stop_loss.atr_multiplier,
                "max_loss_percent": exits.stop_loss.max_loss_percent,
            },
            "take_profit": {
                "enabled": exits.take_profit.enabled,
                "type": cls._serialize_enum(exits.take_profit.type),
                "fixed_percent": exits.take_profit.fixed_percent,
                "r_multiple": exits.take_profit.r_multiple,
                "levels": [
                    {
                        "percent": l.percent,
                        "close_percent": l.close_percent,
                    }
                    for l in exits.take_profit.levels
                ],
            },
            "trailing_stop": {
                "enabled": exits.trailing_stop.enabled,
                "activation": cls._serialize_enum(exits.trailing_stop.activation),
                "activation_percent": exits.trailing_stop.activation_percent,
                "distance_type": cls._serialize_enum(exits.trailing_stop.distance_type),
                "distance_value": exits.trailing_stop.distance_value,
                "atr_multiplier": exits.trailing_stop.atr_multiplier,
            },
            "time_based": {
                "enabled": exits.time_based.enabled,
                "max_bars": exits.time_based.max_bars,
                "max_hours": exits.time_based.max_hours,
                "exit_at_session_end": exits.time_based.exit_at_session_end,
            },
            "breakeven": {
                "enabled": exits.breakeven.enabled,
                "activation_percent": exits.breakeven.activation_percent,
                "buffer_percent": exits.breakeven.buffer_percent,
            },
        }

    @classmethod
    def _serialize_sizing(cls, sizing: Sizing) -> dict[str, Any]:
        """Serialize sizing section."""
        return {
            "method": cls._serialize_enum(sizing.method),
            "fixed_size": sizing.fixed_size,
            "fixed_usd": sizing.fixed_usd,
            "risk_percent": {
                "enabled": sizing.risk_percent.enabled,
                "percent": sizing.risk_percent.percent,
                "max_position_percent": sizing.risk_percent.max_position_percent,
            },
            "volatility_target": {
                "enabled": sizing.volatility_target.enabled,
                "target_volatility": sizing.volatility_target.target_volatility,
                "lookback_days": sizing.volatility_target.lookback_days,
                "max_position_multiplier": sizing.volatility_target.max_position_multiplier,
            },
            "drawdown_scaling": {
                "enabled": sizing.drawdown_scaling.enabled,
                "start_drawdown": sizing.drawdown_scaling.start_drawdown,
                "max_drawdown": sizing.drawdown_scaling.max_drawdown,
                "min_size_multiplier": sizing.drawdown_scaling.min_size_multiplier,
            },
            "pyramiding": {
                "enabled": sizing.pyramiding.enabled,
                "max_entries": sizing.pyramiding.max_entries,
                "size_reduction": sizing.pyramiding.size_reduction,
                "trigger": cls._serialize_enum(sizing.pyramiding.trigger),
                "trigger_value": sizing.pyramiding.trigger_value,
            },
        }

    @classmethod
    def _serialize_execution_policy(cls, policy: ExecutionPolicy) -> dict[str, Any]:
        """Serialize execution policy section."""
        return {
            "order_types": {
                "entry": cls._serialize_enum(policy.order_types.entry),
                "exit": cls._serialize_enum(policy.order_types.exit),
            },
            "limit_orders": {
                "enabled": policy.limit_orders.enabled,
                "entry_offset_bps": policy.limit_orders.entry_offset_bps,
                "exit_offset_bps": policy.limit_orders.exit_offset_bps,
                "timeout_seconds": policy.limit_orders.timeout_seconds,
            },
            "slippage": {
                "max_entry_slippage_bps": policy.slippage.max_entry_slippage_bps,
                "max_exit_slippage_bps": policy.slippage.max_exit_slippage_bps,
                "cancel_on_excessive_slippage": policy.slippage.cancel_on_excessive_slippage,
            },
            "partial_fills": {
                "allow_partial": policy.partial_fills.allow_partial,
                "min_fill_percent": policy.partial_fills.min_fill_percent,
            },
            "retries": {
                "max_retries": policy.retries.max_retries,
                "retry_delay_ms": policy.retries.retry_delay_ms,
                "backoff_multiplier": policy.retries.backoff_multiplier,
            },
            "liquidity": {
                "min_orderbook_depth_usd": policy.liquidity.min_orderbook_depth_usd,
                "max_spread_bps": policy.liquidity.max_spread_bps,
            },
            "timing": {
                "immediate_or_cancel": policy.timing.immediate_or_cancel,
                "good_till_time_seconds": policy.timing.good_till_time_seconds,
            },
        }

    @classmethod
    def _serialize_risk_rules(cls, risk_rules: RiskRules) -> dict[str, Any]:
        """Serialize risk rules section."""
        return {
            "position_limits": {
                "max_position_size_usd": risk_rules.position_limits.max_position_size_usd,
                "max_position_percent": risk_rules.position_limits.max_position_percent,
                "max_leverage": risk_rules.position_limits.max_leverage,
            },
            "portfolio_limits": {
                "max_open_positions": risk_rules.portfolio_limits.max_open_positions,
                "max_correlated_positions": risk_rules.portfolio_limits.max_correlated_positions,
                "max_sector_exposure_percent": risk_rules.portfolio_limits.max_sector_exposure_percent,
            },
            "daily_limits": {
                "max_daily_loss_usd": risk_rules.daily_limits.max_daily_loss_usd,
                "max_daily_loss_percent": risk_rules.daily_limits.max_daily_loss_percent,
                "max_daily_trades": risk_rules.daily_limits.max_daily_trades,
            },
            "circuit_breakers": [
                {
                    "trigger": cls._serialize_enum(cb.trigger),
                    "threshold": cb.threshold,
                    "action": cls._serialize_enum(cb.action),
                    "duration_minutes": cb.duration_minutes,
                }
                for cb in risk_rules.circuit_breakers
            ],
            "correlation_limits": {
                "max_pair_correlation": risk_rules.correlation_limits.max_pair_correlation,
                "max_portfolio_correlation": risk_rules.correlation_limits.max_portfolio_correlation,
            },
        }

    @classmethod
    def _serialize_telemetry_tags(cls, tags: TelemetryTags) -> dict[str, Any]:
        """Serialize telemetry tags section."""
        return {
            "strategy_family": tags.strategy_family,
            "experiment_id": tags.experiment_id,
            "risk_tier": cls._serialize_enum(tags.risk_tier),
            "approval_status": cls._serialize_enum(tags.approval_status),
            "custom_tags": tags.custom_tags,
        }
