"""Tests for DSL serializer."""

import pytest

from src.backtesting.dsl.serializer import DSLSerializer
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
    Symbol,
    Indicator,
    IndicatorCondition,
    Confluence,
    Cooldown,
    StopLoss,
    TakeProfit,
    PositionLimits,
    # Enums
    StrategyCategory,
    StrategyStatus,
    Timeframe,
    MarketType,
    EntryLogic,
    IndicatorType,
    Operator,
    Direction,
)


class TestDSLSerializer:
    """Tests for DSLSerializer."""

    def test_serialize_minimal_dsl(self):
        """Test serializing minimal DSL."""
        dsl = StrategyDSL(
            metadata=Metadata(name="Test", version="1.0.0"),
            universe=Universe(symbols=(Symbol(symbol="BTCUSDT", exchange="bybit"),)),
            signals=Signals(),
            exits=Exits(),
            sizing=Sizing(),
            execution_policy=ExecutionPolicy(),
            risk_rules=RiskRules(),
        )

        data = DSLSerializer.serialize(dsl)

        assert "metadata" in data
        assert "universe" in data
        assert data["metadata"]["name"] == "Test"
        assert data["metadata"]["version"] == "1.0.0"

    def test_serialize_full_dsl(self):
        """Test serializing full DSL."""
        dsl = StrategyDSL(
            metadata=Metadata(
                name="FullStrategy",
                version="2.0.0",
                description="A full strategy",
                category=StrategyCategory.MOMENTUM,
                timeframes=(Timeframe.H1, Timeframe.H4),
                status=StrategyStatus.BACKTESTING,
            ),
            universe=Universe(
                symbols=(
                    Symbol(
                        symbol="BTCUSDT",
                        exchange="bybit",
                        market_type=MarketType.PERPETUAL,
                    ),
                ),
            ),
            signals=Signals(
                entry_logic=EntryLogic.CONFLUENCE,
                indicators=(
                    Indicator(
                        name="rsi",
                        type=IndicatorType.RSI,
                        parameters={"period": 14},
                        conditions=(
                            IndicatorCondition(
                                operator=Operator.LT,
                                threshold=30.0,
                                direction=Direction.LONG,
                            ),
                        ),
                    ),
                ),
                confluence=Confluence(enabled=True, min_score=0.65),
            ),
            exits=Exits(
                stop_loss=StopLoss(enabled=True),
                take_profit=TakeProfit(enabled=True),
            ),
            sizing=Sizing(),
            execution_policy=ExecutionPolicy(),
            risk_rules=RiskRules(
                position_limits=PositionLimits(max_leverage=2.0),
            ),
        )

        data = DSLSerializer.serialize(dsl)

        # Check metadata
        assert data["metadata"]["name"] == "FullStrategy"
        assert data["metadata"]["category"] == "momentum"
        assert data["metadata"]["timeframes"] == ["1h", "4h"]

        # Check universe
        assert len(data["universe"]["symbols"]) == 1
        assert data["universe"]["symbols"][0]["symbol"] == "BTCUSDT"
        assert data["universe"]["symbols"][0]["market_type"] == "perpetual"

        # Check signals
        assert data["signals"]["entry_logic"] == "confluence"
        assert len(data["signals"]["indicators"]) == 1
        assert data["signals"]["indicators"][0]["type"] == "rsi"

        # Check exits
        assert data["exits"]["stop_loss"]["enabled"] is True

        # Check risk rules
        assert data["risk_rules"]["position_limits"]["max_leverage"] == 2.0

    def test_serialize_enum_values(self):
        """Test that enums are serialized as strings."""
        dsl = StrategyDSL(
            metadata=Metadata(
                name="Test",
                version="1.0.0",
                category=StrategyCategory.GRID,
                timeframes=(Timeframe.M15, Timeframe.H1),
            ),
            universe=Universe(),
            signals=Signals(),
            exits=Exits(),
            sizing=Sizing(),
            execution_policy=ExecutionPolicy(),
            risk_rules=RiskRules(),
        )

        data = DSLSerializer.serialize(dsl)

        # Enums should be serialized as string values
        assert data["metadata"]["category"] == "grid"
        assert data["metadata"]["timeframes"] == ["15m", "1h"]
        assert isinstance(data["metadata"]["category"], str)

    def test_serialize_tuples_as_lists(self):
        """Test that tuples are serialized as lists."""
        dsl = StrategyDSL(
            metadata=Metadata(
                name="Test",
                version="1.0.0",
                tags=("tag1", "tag2", "tag3"),
            ),
            universe=Universe(),
            signals=Signals(),
            exits=Exits(),
            sizing=Sizing(),
            execution_policy=ExecutionPolicy(),
            risk_rules=RiskRules(),
        )

        data = DSLSerializer.serialize(dsl)

        # Tuples should be serialized as lists
        assert data["metadata"]["tags"] == ["tag1", "tag2", "tag3"]
        assert isinstance(data["metadata"]["tags"], list)


class TestSerializeMetadata:
    """Tests for metadata serialization."""

    def test_serialize_all_metadata_fields(self):
        """Test serializing all metadata fields."""
        metadata = Metadata(
            name="Test",
            version="1.0.0",
            description="Test description",
            author="test_author",
            created_at="2026-01-01",
            updated_at="2026-01-02",
            tags=("btc", "grid"),
            category=StrategyCategory.MOMENTUM,
            timeframes=(Timeframe.H1,),
            status=StrategyStatus.LIVE,
        )

        data = DSLSerializer._serialize_metadata(metadata)

        assert data["name"] == "Test"
        assert data["version"] == "1.0.0"
        assert data["description"] == "Test description"
        assert data["author"] == "test_author"
        assert data["created_at"] == "2026-01-01"
        assert data["updated_at"] == "2026-01-02"
        assert data["tags"] == ["btc", "grid"]
        assert data["category"] == "momentum"
        assert data["timeframes"] == ["1h"]
        assert data["status"] == "live"


class TestSerializeSignals:
    """Tests for signals serialization."""

    def test_serialize_indicator_conditions(self):
        """Test serializing indicator conditions."""
        indicator = Indicator(
            name="rsi",
            type=IndicatorType.RSI,
            parameters={"period": 14},
            conditions=(
                IndicatorCondition(
                    operator=Operator.LT,
                    threshold=30.0,
                    direction=Direction.LONG,
                ),
                IndicatorCondition(
                    operator=Operator.GT,
                    threshold=70.0,
                    direction=Direction.SHORT,
                ),
            ),
        )

        signals = Signals(
            entry_logic=EntryLogic.CONFLUENCE,
            indicators=(indicator,),
        )

        data = DSLSerializer._serialize_signals(signals)

        assert len(data["indicators"]) == 1
        conditions = data["indicators"][0]["conditions"]
        assert len(conditions) == 2

        assert conditions[0]["operator"] == "lt"
        assert conditions[0]["threshold"] == 30.0
        assert conditions[0]["direction"] == "long"

        assert conditions[1]["operator"] == "gt"
        assert conditions[1]["threshold"] == 70.0
        assert conditions[1]["direction"] == "short"


class TestSerializeRiskRules:
    """Tests for risk rules serialization."""

    def test_serialize_circuit_breakers(self):
        """Test serializing circuit breakers."""
        from src.backtesting.dsl.models import (
            CircuitBreaker,
            CircuitBreakerTrigger,
            CircuitBreakerAction,
        )

        risk_rules = RiskRules(
            circuit_breakers=(
                CircuitBreaker(
                    trigger=CircuitBreakerTrigger.DAILY_LOSS,
                    threshold=2.0,
                    action=CircuitBreakerAction.HALT,
                    duration_minutes=60,
                ),
            ),
        )

        data = DSLSerializer._serialize_risk_rules(risk_rules)

        assert len(data["circuit_breakers"]) == 1
        cb = data["circuit_breakers"][0]
        assert cb["trigger"] == "daily_loss"
        assert cb["threshold"] == 2.0
        assert cb["action"] == "halt"
        assert cb["duration_minutes"] == 60


class TestRoundTrip:
    """Tests for round-trip parsing and serialization."""

    def test_parse_then_serialize(self):
        """Test that parse then serialize preserves data."""
        from src.backtesting.dsl.parser import DSLParser

        original_data = {
            "metadata": {
                "name": "RoundTrip",
                "version": "1.0.0",
                "category": "grid",
                "timeframes": ["1h"],
            },
            "universe": {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "exchange": "bybit",
                        "market_type": "perpetual",
                    }
                ]
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
            },
            "exits": {
                "stop_loss": {"enabled": True, "type": "atr_based"},
            },
            "sizing": {"method": "risk_percent"},
            "execution_policy": {"order_types": {"entry": "limit", "exit": "market"}},
            "risk_rules": {"position_limits": {"max_leverage": 2.0}},
        }

        # Parse
        dsl = DSLParser.parse(original_data)

        # Serialize
        serialized_data = DSLSerializer.serialize(dsl)

        # Key fields should match
        assert serialized_data["metadata"]["name"] == "RoundTrip"
        assert serialized_data["metadata"]["category"] == "grid"
        assert serialized_data["universe"]["symbols"][0]["symbol"] == "BTCUSDT"
        assert serialized_data["signals"]["entry_logic"] == "confluence"
