"""Tests for DSL parser."""

import pytest

from src.backtesting.dsl.parser import DSLParser
from src.backtesting.dsl.models import (
    StrategyDSL,
    Metadata,
    StrategyCategory,
    StrategyStatus,
    Timeframe,
    MarketType,
    EntryLogic,
    IndicatorType,
    Operator,
    Direction,
)


class TestDSLParser:
    """Tests for DSLParser."""

    def test_parse_minimal_config(self):
        """Test parsing minimal valid config."""
        data = {
            "metadata": {
                "name": "TestStrategy",
                "version": "1.0.0",
            },
            "universe": {"symbols": [{"symbol": "BTCUSDT", "exchange": "bybit"}]},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        dsl = DSLParser.parse(data)

        assert isinstance(dsl, StrategyDSL)
        assert dsl.metadata.name == "TestStrategy"
        assert dsl.metadata.version == "1.0.0"

    def test_parse_full_config(self):
        """Test parsing full config."""
        data = {
            "metadata": {
                "name": "FullStrategy",
                "version": "2.0.0",
                "description": "A full strategy",
                "category": "momentum",
                "timeframes": ["1h", "4h"],
                "status": "backtesting",
            },
            "universe": {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "exchange": "bybit",
                        "market_type": "perpetual",
                    }
                ],
                "filters": {
                    "min_24h_volume_usd": 1000000,
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
                            {"operator": "lt", "threshold": 30, "direction": "long"}
                        ],
                    }
                ],
                "confluence": {
                    "enabled": True,
                    "min_score": 0.65,
                },
            },
            "exits": {
                "stop_loss": {
                    "enabled": True,
                    "type": "atr_based",
                    "atr_multiplier": 1.5,
                },
            },
            "sizing": {
                "method": "risk_percent",
                "risk_percent": {
                    "enabled": True,
                    "percent": 1.0,
                },
            },
            "execution_policy": {
                "order_types": {
                    "entry": "limit",
                    "exit": "market",
                },
            },
            "risk_rules": {
                "position_limits": {
                    "max_leverage": 2.0,
                },
            },
            "telemetry_tags": {
                "strategy_family": "test",
            },
        }

        dsl = DSLParser.parse(data)

        assert dsl.metadata.name == "FullStrategy"
        assert dsl.metadata.category == StrategyCategory.MOMENTUM
        assert len(dsl.universe.symbols) == 1
        assert dsl.universe.symbols[0].market_type == MarketType.PERPETUAL
        assert dsl.signals.entry_logic == EntryLogic.CONFLUENCE
        assert len(dsl.signals.indicators) == 1
        assert dsl.signals.indicators[0].type == IndicatorType.RSI
        assert dsl.exits.stop_loss.enabled is True
        assert dsl.sizing.method.value == "risk_percent"

    def test_parse_enum_values(self):
        """Test parsing of enum values."""
        data = {
            "metadata": {
                "name": "Test",
                "version": "1.0.0",
                "category": "GRID",
                "status": "LIVE",
            },
            "universe": {"symbols": [{"symbol": "BTC", "exchange": "bybit"}]},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        dsl = DSLParser.parse(data)

        # Should handle case-insensitive enum parsing
        assert dsl.metadata.category == StrategyCategory.GRID
        assert dsl.metadata.status == StrategyStatus.LIVE

    def test_parse_invalid_enum(self):
        """Test parsing of invalid enum value."""
        data = {
            "metadata": {
                "name": "Test",
                "version": "1.0.0",
                "category": "invalid_category",
            },
            "universe": {"symbols": []},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        # Should raise ValueError for invalid enum
        with pytest.raises(ValueError):
            DSLParser.parse(data)

    def test_parse_timeframes(self):
        """Test parsing timeframes."""
        data = {
            "metadata": {
                "name": "Test",
                "version": "1.0.0",
                "timeframes": ["1m", "15m", "1h"],
            },
            "universe": {"symbols": []},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        dsl = DSLParser.parse(data)

        assert len(dsl.metadata.timeframes) == 3
        assert Timeframe.M1 in dsl.metadata.timeframes
        assert Timeframe.M15 in dsl.metadata.timeframes
        assert Timeframe.H1 in dsl.metadata.timeframes


class TestParseMetadata:
    """Tests for metadata parsing."""

    def test_parse_metadata_with_all_fields(self):
        """Test parsing metadata with all fields."""
        data = {
            "name": "Test",
            "version": "1.0.0",
            "description": "Test description",
            "author": "test_author",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-02",
            "tags": ["btc", "grid"],
            "category": "grid",
            "timeframes": ["1h"],
            "status": "development",
        }

        metadata = DSLParser._parse_metadata(data)

        assert metadata.name == "Test"
        assert metadata.version == "1.0.0"
        assert metadata.description == "Test description"
        assert metadata.author == "test_author"
        assert metadata.tags == ("btc", "grid")


class TestParseSignals:
    """Tests for signals parsing."""

    def test_parse_indicator_conditions(self):
        """Test parsing indicator conditions."""
        data = {
            "entry_logic": "confluence",
            "indicators": [
                {
                    "name": "rsi",
                    "type": "rsi",
                    "parameters": {"period": 14},
                    "conditions": [
                        {"operator": "lt", "threshold": 30, "direction": "long"},
                        {"operator": "gt", "threshold": 70, "direction": "short"},
                    ],
                }
            ],
        }

        signals = DSLParser._parse_signals(data)

        assert len(signals.indicators) == 1
        indicator = signals.indicators[0]
        assert len(indicator.conditions) == 2

        cond1 = indicator.conditions[0]
        assert cond1.operator == Operator.LT
        assert cond1.threshold == 30
        assert cond1.direction == Direction.LONG

        cond2 = indicator.conditions[1]
        assert cond2.operator == Operator.GT
        assert cond2.threshold == 70
        assert cond2.direction == Direction.SHORT


class TestParseRiskRules:
    """Tests for risk rules parsing."""

    def test_parse_circuit_breakers(self):
        """Test parsing circuit breakers."""
        data = {
            "position_limits": {},
            "portfolio_limits": {},
            "daily_limits": {},
            "circuit_breakers": [
                {
                    "trigger": "daily_loss",
                    "threshold": 2.0,
                    "action": "halt",
                    "duration_minutes": 60,
                }
            ],
        }

        risk_rules = DSLParser._parse_risk_rules(data)

        assert len(risk_rules.circuit_breakers) == 1
        cb = risk_rules.circuit_breakers[0]
        assert cb.trigger.value == "daily_loss"
        assert cb.threshold == 2.0
        assert cb.action.value == "halt"
        assert cb.duration_minutes == 60
