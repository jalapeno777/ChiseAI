"""Tests for DSL models."""

import pytest
from src.backtesting.dsl.models import (
    Confluence,
    Cooldown,
    DayOfWeek,
    Direction,
    EntryLogic,
    ExecutionPolicy,
    Exits,
    Indicator,
    IndicatorCondition,
    IndicatorType,
    MarketType,
    Metadata,
    Operator,
    PositionLimits,
    RiskRules,
    Signals,
    Sizing,
    StopLoss,
    StopLossType,
    # Enums
    StrategyCategory,
    StrategyDSL,
    StrategyStatus,
    Symbol,
    TakeProfit,
    TakeProfitType,
    Timeframe,
    TradingSession,
    Universe,
    UniverseFilters,
)


class TestMetadata:
    """Tests for Metadata model."""

    def test_create_valid_metadata(self):
        """Test creating valid metadata."""
        metadata = Metadata(
            name="TestStrategy",
            version="1.0.0",
            description="A test strategy",
            author="test_user",
            tags=("btc", "grid"),
            category=StrategyCategory.GRID,
            timeframes=(Timeframe.H1, Timeframe.H4),
            status=StrategyStatus.DEVELOPMENT,
        )

        assert metadata.name == "TestStrategy"
        assert metadata.version == "1.0.0"
        assert metadata.category == StrategyCategory.GRID
        assert len(metadata.timeframes) == 2

    def test_metadata_requires_name(self):
        """Test that name is required."""
        with pytest.raises(ValueError, match="name is required"):
            Metadata(name="", version="1.0.0")

    def test_metadata_requires_version(self):
        """Test that version is required."""
        with pytest.raises(ValueError, match="version is required"):
            Metadata(name="Test", version="")

    def test_metadata_default_values(self):
        """Test default values for metadata."""
        metadata = Metadata(name="Test", version="1.0.0")

        assert metadata.description == ""
        assert metadata.author == ""
        assert metadata.tags == ()
        assert metadata.category == StrategyCategory.GRID
        assert metadata.status == StrategyStatus.DEVELOPMENT


class TestUniverse:
    """Tests for Universe model."""

    def test_create_symbol(self):
        """Test creating a symbol."""
        symbol = Symbol(
            symbol="BTCUSDT",
            exchange="bybit",
            market_type=MarketType.PERPETUAL,
        )

        assert symbol.symbol == "BTCUSDT"
        assert symbol.exchange == "bybit"
        assert symbol.market_type == MarketType.PERPETUAL

    def test_create_trading_session(self):
        """Test creating a trading session."""
        session = TradingSession(
            name="london_ny",
            timezone="UTC",
            start_time="13:00",
            end_time="17:00",
            days=(DayOfWeek.MON, DayOfWeek.TUE),
        )

        assert session.name == "london_ny"
        assert session.start_time == "13:00"
        assert len(session.days) == 2

    def test_create_universe(self):
        """Test creating universe."""
        symbol = Symbol(symbol="BTCUSDT", exchange="bybit")
        universe = Universe(
            symbols=(symbol,),
            filters=UniverseFilters(min_24h_volume_usd=1000000),
        )

        assert len(universe.symbols) == 1
        assert universe.filters.min_24h_volume_usd == 1000000


class TestSignals:
    """Tests for Signals model."""

    def test_create_indicator_condition(self):
        """Test creating indicator condition."""
        condition = IndicatorCondition(
            operator=Operator.LT,
            threshold=30.0,
            direction=Direction.LONG,
        )

        assert condition.operator == Operator.LT
        assert condition.threshold == 30.0
        assert condition.direction == Direction.LONG

    def test_create_indicator(self):
        """Test creating indicator."""
        condition = IndicatorCondition(
            operator=Operator.LT,
            threshold=30.0,
            direction=Direction.LONG,
        )
        indicator = Indicator(
            name="rsi",
            type=IndicatorType.RSI,
            parameters={"period": 14},
            conditions=(condition,),
        )

        assert indicator.name == "rsi"
        assert indicator.type == IndicatorType.RSI
        assert indicator.parameters["period"] == 14
        assert len(indicator.conditions) == 1

    def test_confluence_score_validation(self):
        """Test confluence score validation."""
        # Valid score
        confluence = Confluence(enabled=True, min_score=0.65)
        assert confluence.min_score == 0.65

        # Invalid - too low (below 0.0)
        with pytest.raises(ValueError, match="min_score must be 0.0-1.0"):
            Confluence(enabled=True, min_score=-0.1)

        # Invalid - too high (above 1.0)
        with pytest.raises(ValueError, match="min_score must be 0.0-1.0"):
            Confluence(enabled=True, min_score=1.5)

    def test_create_signals(self):
        """Test creating signals section."""
        indicator = Indicator(
            name="rsi",
            type=IndicatorType.RSI,
            parameters={"period": 14},
            conditions=(),
        )
        signals = Signals(
            entry_logic=EntryLogic.CONFLUENCE,
            indicators=(indicator,),
            confluence=Confluence(enabled=True, min_score=0.65),
            cooldown=Cooldown(bars=3, timeframe=Timeframe.H1),
        )

        assert signals.entry_logic == EntryLogic.CONFLUENCE
        assert len(signals.indicators) == 1
        assert signals.confluence.enabled is True


class TestExits:
    """Tests for Exits model."""

    def test_create_stop_loss(self):
        """Test creating stop loss."""
        sl = StopLoss(
            enabled=True,
            type=StopLossType.ATR_BASED,
            atr_multiplier=1.5,
            max_loss_percent=2.0,
        )

        assert sl.enabled is True
        assert sl.type == StopLossType.ATR_BASED
        assert sl.atr_multiplier == 1.5

    def test_create_take_profit(self):
        """Test creating take profit."""
        tp = TakeProfit(
            enabled=True,
            type=TakeProfitType.R_BASED,
            r_multiple=2.0,
        )

        assert tp.enabled is True
        assert tp.type == TakeProfitType.R_BASED
        assert tp.r_multiple == 2.0

    def test_create_exits(self):
        """Test creating exits section."""
        exits = Exits(
            stop_loss=StopLoss(enabled=True),
            take_profit=TakeProfit(enabled=True),
        )

        assert exits.stop_loss.enabled is True
        assert exits.take_profit.enabled is True


class TestRiskRules:
    """Tests for RiskRules model."""

    def test_create_position_limits(self):
        """Test creating position limits."""
        limits = PositionLimits(
            max_position_size_usd=50000,
            max_position_percent=10.0,
            max_leverage=3.0,
        )

        assert limits.max_position_size_usd == 50000
        assert limits.max_position_percent == 10.0
        assert limits.max_leverage == 3.0

    def test_create_risk_rules(self):
        """Test creating risk rules section."""
        risk_rules = RiskRules(
            position_limits=PositionLimits(max_leverage=2.0),
        )

        assert risk_rules.position_limits.max_leverage == 2.0


class TestStrategyDSL:
    """Tests for complete StrategyDSL."""

    def test_create_minimal_dsl(self):
        """Test creating minimal DSL."""
        dsl = StrategyDSL(
            metadata=Metadata(name="Test", version="1.0.0"),
            universe=Universe(symbols=(Symbol(symbol="BTCUSDT", exchange="bybit"),)),
            signals=Signals(),
            exits=Exits(),
            sizing=Sizing(),
            execution_policy=ExecutionPolicy(),
            risk_rules=RiskRules(),
        )

        assert dsl.metadata.name == "Test"
        assert dsl.metadata.version == "1.0.0"
        assert len(dsl.universe.symbols) == 1

    def test_dsl_immutability(self):
        """Test that DSL is immutable (frozen dataclass)."""
        dsl = StrategyDSL(
            metadata=Metadata(name="Test", version="1.0.0"),
            universe=Universe(),
            signals=Signals(),
            exits=Exits(),
            sizing=Sizing(),
            execution_policy=ExecutionPolicy(),
            risk_rules=RiskRules(),
        )

        # Should not be able to modify
        with pytest.raises(AttributeError):
            dsl.metadata = Metadata(name="Other", version="2.0.0")
