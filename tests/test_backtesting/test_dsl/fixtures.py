"""Test fixtures and utilities for DSL tests."""

from __future__ import annotations

from typing import Any


def create_valid_config() -> dict[str, Any]:
    """Create a valid DSL configuration for testing."""
    return {
        "metadata": {
            "name": "TestStrategy",
            "version": "1.0.0",
            "description": "A test strategy",
            "author": "test",
            "created_at": "2026-02-12T00:00:00Z",
            "updated_at": "2026-02-12T00:00:00Z",
            "tags": ["test", "btc"],
            "category": "grid",
            "timeframes": ["1h", "4h"],
            "status": "development",
        },
        "universe": {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "exchange": "bybit",
                    "market_type": "perpetual",
                }
            ],
            "sessions": [],
            "filters": {
                "min_24h_volume_usd": 10000000,
                "max_spread_bps": 10,
                "min_liquidity_depth_usd": 500000,
            },
        },
        "signals": {
            "entry_logic": "confluence",
            "indicators": [
                {
                    "name": "rsi",
                    "type": "rsi",
                    "parameters": {"period": 14},
                    "conditions": [
                        {"operator": "lt", "threshold": 30, "direction": "long"},
                    ],
                }
            ],
            "confluence": {
                "enabled": True,
                "min_score": 0.65,
                "min_confidence": 0.75,
                "require_alignment": False,
            },
            "cooldown": {
                "bars": 3,
                "timeframe": "1h",
            },
        },
        "filters": {
            "regime": {
                "enabled": True,
                "allowed_regimes": ["trending", "ranging"],
                "detection_method": "adx",
                "adx_threshold": 20,
            },
            "volatility": {
                "enabled": True,
                "method": "atr",
                "atr_period": 14,
                "min_atr_percent": 0.5,
                "max_atr_percent": 5.0,
            },
            "time_based": [],
            "correlation": {
                "enabled": True,
                "max_correlation": 0.8,
                "lookback_days": 30,
            },
        },
        "exits": {
            "stop_loss": {
                "enabled": True,
                "type": "atr_based",
                "fixed_percent": 0,
                "atr_multiplier": 1.5,
                "max_loss_percent": 2.0,
            },
            "take_profit": {
                "enabled": True,
                "type": "r_based",
                "fixed_percent": 0,
                "r_multiple": 2.0,
                "levels": [],
            },
            "trailing_stop": {
                "enabled": False,
                "activation": "immediate",
                "activation_percent": 0,
                "distance_type": "atr_based",
                "distance_value": 0,
                "atr_multiplier": 1.0,
            },
            "time_based": {
                "enabled": False,
                "max_bars": 0,
                "max_hours": 0,
                "exit_at_session_end": False,
            },
            "breakeven": {
                "enabled": False,
                "activation_percent": 0,
                "buffer_percent": 0,
            },
        },
        "sizing": {
            "method": "risk_percent",
            "fixed_size": 0,
            "fixed_usd": 0,
            "risk_percent": {
                "enabled": True,
                "percent": 1.0,
                "max_position_percent": 10.0,
            },
            "volatility_target": {
                "enabled": False,
                "target_volatility": 20.0,
                "lookback_days": 30,
                "max_position_multiplier": 2.0,
            },
            "drawdown_scaling": {
                "enabled": False,
                "start_drawdown": 5.0,
                "max_drawdown": 15.0,
                "min_size_multiplier": 0.25,
            },
            "pyramiding": {
                "enabled": False,
                "max_entries": 3,
                "size_reduction": 0.5,
                "trigger": "profit_percent",
                "trigger_value": 1.0,
            },
        },
        "execution_policy": {
            "order_types": {
                "entry": "limit",
                "exit": "market",
            },
            "limit_orders": {
                "enabled": True,
                "entry_offset_bps": 5,
                "exit_offset_bps": 0,
                "timeout_seconds": 30,
            },
            "slippage": {
                "max_entry_slippage_bps": 20,
                "max_exit_slippage_bps": 50,
                "cancel_on_excessive_slippage": True,
            },
            "partial_fills": {
                "allow_partial": True,
                "min_fill_percent": 80,
            },
            "retries": {
                "max_retries": 3,
                "retry_delay_ms": 500,
                "backoff_multiplier": 2.0,
            },
            "liquidity": {
                "min_orderbook_depth_usd": 100000,
                "max_spread_bps": 10,
            },
            "timing": {
                "immediate_or_cancel": False,
                "good_till_time_seconds": 60,
            },
        },
        "risk_rules": {
            "position_limits": {
                "max_position_size_usd": 50000,
                "max_position_percent": 10.0,
                "max_leverage": 1.0,
            },
            "portfolio_limits": {
                "max_open_positions": 5,
                "max_correlated_positions": 2,
                "max_sector_exposure_percent": 50.0,
            },
            "daily_limits": {
                "max_daily_loss_usd": 1000,
                "max_daily_loss_percent": 2.0,
                "max_daily_trades": 20,
            },
            "circuit_breakers": [
                {
                    "trigger": "daily_loss",
                    "threshold": 2.0,
                    "action": "halt",
                    "duration_minutes": 60,
                }
            ],
            "correlation_limits": {
                "max_pair_correlation": 0.8,
                "max_portfolio_correlation": 0.7,
            },
        },
        "telemetry_tags": {
            "strategy_family": "test_family",
            "experiment_id": "test_exp_001",
            "risk_tier": "moderate",
            "approval_status": "auto",
            "custom_tags": {},
        },
    }


def create_invalid_leverage_config() -> dict[str, Any]:
    """Create config with invalid leverage (exceeds 3.0)."""
    config = create_valid_config()
    config["risk_rules"]["position_limits"]["max_leverage"] = 5.0
    return config


def create_invalid_position_percent_config() -> dict[str, Any]:
    """Create config with invalid position percent (exceeds 100%)."""
    config = create_valid_config()
    config["risk_rules"]["position_limits"]["max_position_percent"] = 150.0
    return config


def create_invalid_confluence_score_config() -> dict[str, Any]:
    """Create config with invalid confluence score (below 0.5)."""
    config = create_valid_config()
    config["signals"]["confluence"]["min_score"] = 0.3
    return config


def create_invalid_timeframe_config() -> dict[str, Any]:
    """Create config with invalid timeframe."""
    config = create_valid_config()
    config["metadata"]["timeframes"] = ["1h", "invalid_tf"]
    return config


def create_no_stop_loss_config() -> dict[str, Any]:
    """Create config with stop-loss disabled (should warn)."""
    config = create_valid_config()
    config["exits"]["stop_loss"]["enabled"] = False
    return config


def create_missing_required_fields_config() -> dict[str, Any]:
    """Create config missing required fields."""
    config = create_valid_config()
    config["metadata"]["name"] = ""
    config["metadata"]["version"] = ""
    config["universe"]["symbols"] = []
    return config


def create_minimal_valid_config() -> dict[str, Any]:
    """Create minimal valid config."""
    return {
        "metadata": {
            "name": "MinimalStrategy",
            "version": "1.0.0",
        },
        "universe": {
            "symbols": [{"symbol": "BTCUSDT", "exchange": "bybit"}],
        },
        "signals": {},
        "exits": {},
        "sizing": {},
        "execution_policy": {},
        "risk_rules": {},
    }
