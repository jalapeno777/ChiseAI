"""DSL Parser - Convert dictionaries to DSL dataclasses.

This module handles parsing of raw dictionary data into typed DSL dataclasses.
"""

from __future__ import annotations

from typing import Any

from src.backtesting.dsl.models import (
    # Enums
    StrategyCategory,
    StrategyStatus,
    Timeframe,
    MarketType,
    EntryLogic,
    IndicatorType,
    Operator,
    Direction,
    RegimeType,
    RegimeDetectionMethod,
    VolatilityMethod,
    TimeFilterType,
    TimeFilterAction,
    StopLossType,
    TakeProfitType,
    TrailingActivation,
    TrailingDistanceType,
    SizingMethod,
    PyramidingTrigger,
    OrderType,
    CircuitBreakerTrigger,
    CircuitBreakerAction,
    RiskTier,
    ApprovalStatus,
    DayOfWeek,
    # Dataclasses
    Metadata,
    Symbol,
    TradingSession,
    UniverseFilters,
    Universe,
    IndicatorCondition,
    Indicator,
    Confluence,
    Cooldown,
    Signals,
    RegimeFilter,
    VolatilityFilter,
    TimeBasedFilter,
    CorrelationFilter,
    Filters,
    TakeProfitLevel,
    StopLoss,
    TakeProfit,
    TrailingStop,
    TimeBasedExit,
    BreakevenStop,
    Exits,
    RiskPercentSizing,
    VolatilityTargetSizing,
    DrawdownScaling,
    Pyramiding,
    Sizing,
    OrderTypes,
    LimitOrderSettings,
    SlippageSettings,
    PartialFillSettings,
    RetrySettings,
    LiquiditySettings,
    TimingSettings,
    ExecutionPolicy,
    PositionLimits,
    PortfolioLimits,
    DailyLimits,
    CircuitBreaker,
    CorrelationLimits,
    RiskRules,
    TelemetryTags,
    StrategyDSL,
)


class DSLParser:
    """Parser for converting dictionaries to DSL dataclasses."""

    @classmethod
    def parse(cls, data: dict[str, Any]) -> StrategyDSL:
        """Parse complete DSL configuration from dictionary.

        Args:
            data: Raw dictionary from YAML/JSON

        Returns:
            Parsed StrategyDSL instance
        """
        return StrategyDSL(
            metadata=cls._parse_metadata(data.get("metadata", {})),
            universe=cls._parse_universe(data.get("universe", {})),
            signals=cls._parse_signals(data.get("signals", {})),
            filters=cls._parse_filters(data.get("filters", {})),
            exits=cls._parse_exits(data.get("exits", {})),
            sizing=cls._parse_sizing(data.get("sizing", {})),
            execution_policy=cls._parse_execution_policy(
                data.get("execution_policy", {})
            ),
            risk_rules=cls._parse_risk_rules(data.get("risk_rules", {})),
            telemetry_tags=cls._parse_telemetry_tags(data.get("telemetry_tags", {})),
        )

    @classmethod
    def _parse_enum(cls, value: str | Any, enum_class: type) -> Any:
        """Parse enum value safely."""
        if isinstance(value, enum_class):
            return value
        if isinstance(value, str):
            try:
                return enum_class(value.lower())
            except ValueError:
                # Try uppercase variant
                try:
                    return enum_class[value.upper()]
                except KeyError:
                    raise ValueError(f"Invalid {enum_class.__name__}: {value}")
        raise ValueError(f"Cannot parse {enum_class.__name__} from {type(value)}")

    @classmethod
    def _parse_metadata(cls, data: dict[str, Any]) -> Metadata:
        """Parse metadata section."""
        return Metadata(
            name=data.get("name", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            author=data.get("author", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            tags=tuple(data.get("tags", [])),
            category=cls._parse_enum(data.get("category", "grid"), StrategyCategory),
            timeframes=tuple(
                cls._parse_enum(tf, Timeframe) for tf in data.get("timeframes", ["1h"])
            ),
            status=cls._parse_enum(data.get("status", "development"), StrategyStatus),
        )

    @classmethod
    def _parse_universe(cls, data: dict[str, Any]) -> Universe:
        """Parse universe section."""
        symbols_data = data.get("symbols", [])
        symbols = tuple(
            Symbol(
                symbol=s.get("symbol", ""),
                exchange=s.get("exchange", ""),
                market_type=cls._parse_enum(
                    s.get("market_type", "perpetual"), MarketType
                ),
            )
            for s in symbols_data
        )

        sessions_data = data.get("sessions", [])
        sessions = tuple(
            TradingSession(
                name=s.get("name", ""),
                timezone=s.get("timezone", "UTC"),
                start_time=s.get("start_time", "00:00"),
                end_time=s.get("end_time", "23:59"),
                days=tuple(
                    cls._parse_enum(d, DayOfWeek)
                    for d in s.get("days", ["mon", "tue", "wed", "thu", "fri"])
                ),
            )
            for s in sessions_data
        )

        filters_data = data.get("filters", {})
        filters = UniverseFilters(
            min_24h_volume_usd=filters_data.get("min_24h_volume_usd", 0.0),
            max_spread_bps=filters_data.get("max_spread_bps", 100.0),
            min_liquidity_depth_usd=filters_data.get("min_liquidity_depth_usd", 0.0),
        )

        return Universe(symbols=symbols, sessions=sessions, filters=filters)

    @classmethod
    def _parse_signals(cls, data: dict[str, Any]) -> Signals:
        """Parse signals section."""
        indicators_data = data.get("indicators", [])
        indicators = tuple(
            Indicator(
                name=i.get("name", ""),
                type=cls._parse_enum(i.get("type", "rsi"), IndicatorType),
                parameters=i.get("parameters", {}),
                conditions=tuple(
                    IndicatorCondition(
                        operator=cls._parse_enum(c.get("operator", "gt"), Operator),
                        threshold=c.get("threshold", 0.0),
                        direction=cls._parse_enum(
                            c.get("direction", "both"), Direction
                        ),
                    )
                    for c in i.get("conditions", [])
                ),
            )
            for i in indicators_data
        )

        confluence_data = data.get("confluence", {})
        confluence = Confluence(
            enabled=confluence_data.get("enabled", False),
            min_score=confluence_data.get("min_score", 0.5),
            min_confidence=confluence_data.get("min_confidence", 0.5),
            require_alignment=confluence_data.get("require_alignment", False),
        )

        cooldown_data = data.get("cooldown", {})
        cooldown = Cooldown(
            bars=cooldown_data.get("bars", 1),
            timeframe=cls._parse_enum(cooldown_data.get("timeframe", "1h"), Timeframe),
        )

        return Signals(
            entry_logic=cls._parse_enum(
                data.get("entry_logic", "confluence"), EntryLogic
            ),
            indicators=indicators,
            confluence=confluence,
            cooldown=cooldown,
        )

    @classmethod
    def _parse_filters(cls, data: dict[str, Any]) -> Filters:
        """Parse filters section."""
        regime_data = data.get("regime", {})
        regime = RegimeFilter(
            enabled=regime_data.get("enabled", False),
            allowed_regimes=tuple(
                cls._parse_enum(r, RegimeType)
                for r in regime_data.get("allowed_regimes", [])
            ),
            detection_method=cls._parse_enum(
                regime_data.get("detection_method", "adx"), RegimeDetectionMethod
            ),
            adx_threshold=regime_data.get("adx_threshold", 25.0),
        )

        volatility_data = data.get("volatility", {})
        volatility = VolatilityFilter(
            enabled=volatility_data.get("enabled", False),
            method=cls._parse_enum(
                volatility_data.get("method", "atr"), VolatilityMethod
            ),
            atr_period=volatility_data.get("atr_period", 14),
            min_atr_percent=volatility_data.get("min_atr_percent", 0.0),
            max_atr_percent=volatility_data.get("max_atr_percent", 10.0),
        )

        time_based_data = data.get("time_based", [])
        time_based = tuple(
            TimeBasedFilter(
                name=t.get("name", ""),
                type=cls._parse_enum(t.get("type", "session"), TimeFilterType),
                action=cls._parse_enum(t.get("action", "block"), TimeFilterAction),
                parameters=t.get("parameters", {}),
            )
            for t in time_based_data
        )

        correlation_data = data.get("correlation", {})
        correlation = CorrelationFilter(
            enabled=correlation_data.get("enabled", False),
            max_correlation=correlation_data.get("max_correlation", 0.8),
            lookback_days=correlation_data.get("lookback_days", 30),
        )

        return Filters(
            regime=regime,
            volatility=volatility,
            time_based=time_based,
            correlation=correlation,
        )

    @classmethod
    def _parse_exits(cls, data: dict[str, Any]) -> Exits:
        """Parse exits section."""
        stop_loss_data = data.get("stop_loss", {})
        stop_loss = StopLoss(
            enabled=stop_loss_data.get("enabled", True),
            type=cls._parse_enum(stop_loss_data.get("type", "atr_based"), StopLossType),
            fixed_percent=stop_loss_data.get("fixed_percent", 0.0),
            atr_multiplier=stop_loss_data.get("atr_multiplier", 1.5),
            max_loss_percent=stop_loss_data.get("max_loss_percent", 2.0),
        )

        take_profit_data = data.get("take_profit", {})
        levels_data = take_profit_data.get("levels", [])
        levels = tuple(
            TakeProfitLevel(
                percent=l.get("percent", 0.0),
                close_percent=l.get("close_percent", 0.0),
            )
            for l in levels_data
        )
        take_profit = TakeProfit(
            enabled=take_profit_data.get("enabled", True),
            type=cls._parse_enum(
                take_profit_data.get("type", "r_based"), TakeProfitType
            ),
            fixed_percent=take_profit_data.get("fixed_percent", 0.0),
            r_multiple=take_profit_data.get("r_multiple", 2.0),
            levels=levels,
        )

        trailing_stop_data = data.get("trailing_stop", {})
        trailing_stop = TrailingStop(
            enabled=trailing_stop_data.get("enabled", False),
            activation=cls._parse_enum(
                trailing_stop_data.get("activation", "immediate"), TrailingActivation
            ),
            activation_percent=trailing_stop_data.get("activation_percent", 0.0),
            distance_type=cls._parse_enum(
                trailing_stop_data.get("distance_type", "atr_based"),
                TrailingDistanceType,
            ),
            distance_value=trailing_stop_data.get("distance_value", 0.0),
            atr_multiplier=trailing_stop_data.get("atr_multiplier", 1.0),
        )

        time_based_data = data.get("time_based", {})
        time_based = TimeBasedExit(
            enabled=time_based_data.get("enabled", False),
            max_bars=time_based_data.get("max_bars", 0),
            max_hours=time_based_data.get("max_hours", 0.0),
            exit_at_session_end=time_based_data.get("exit_at_session_end", False),
        )

        breakeven_data = data.get("breakeven", {})
        breakeven = BreakevenStop(
            enabled=breakeven_data.get("enabled", False),
            activation_percent=breakeven_data.get("activation_percent", 0.0),
            buffer_percent=breakeven_data.get("buffer_percent", 0.0),
        )

        return Exits(
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop=trailing_stop,
            time_based=time_based,
            breakeven=breakeven,
        )

    @classmethod
    def _parse_sizing(cls, data: dict[str, Any]) -> Sizing:
        """Parse sizing section."""
        risk_percent_data = data.get("risk_percent", {})
        risk_percent = RiskPercentSizing(
            enabled=risk_percent_data.get("enabled", False),
            percent=risk_percent_data.get("percent", 1.0),
            max_position_percent=risk_percent_data.get("max_position_percent", 10.0),
        )

        volatility_target_data = data.get("volatility_target", {})
        volatility_target = VolatilityTargetSizing(
            enabled=volatility_target_data.get("enabled", False),
            target_volatility=volatility_target_data.get("target_volatility", 20.0),
            lookback_days=volatility_target_data.get("lookback_days", 30),
            max_position_multiplier=volatility_target_data.get(
                "max_position_multiplier", 2.0
            ),
        )

        drawdown_scaling_data = data.get("drawdown_scaling", {})
        drawdown_scaling = DrawdownScaling(
            enabled=drawdown_scaling_data.get("enabled", False),
            start_drawdown=drawdown_scaling_data.get("start_drawdown", 5.0),
            max_drawdown=drawdown_scaling_data.get("max_drawdown", 15.0),
            min_size_multiplier=drawdown_scaling_data.get("min_size_multiplier", 0.25),
        )

        pyramiding_data = data.get("pyramiding", {})
        pyramiding = Pyramiding(
            enabled=pyramiding_data.get("enabled", False),
            max_entries=pyramiding_data.get("max_entries", 3),
            size_reduction=pyramiding_data.get("size_reduction", 0.5),
            trigger=cls._parse_enum(
                pyramiding_data.get("trigger", "profit_percent"), PyramidingTrigger
            ),
            trigger_value=pyramiding_data.get("trigger_value", 1.0),
        )

        return Sizing(
            method=cls._parse_enum(data.get("method", "risk_percent"), SizingMethod),
            fixed_size=data.get("fixed_size", 0.0),
            fixed_usd=data.get("fixed_usd", 0.0),
            risk_percent=risk_percent,
            volatility_target=volatility_target,
            drawdown_scaling=drawdown_scaling,
            pyramiding=pyramiding,
        )

    @classmethod
    def _parse_execution_policy(cls, data: dict[str, Any]) -> ExecutionPolicy:
        """Parse execution policy section."""
        order_types_data = data.get("order_types", {})
        order_types = OrderTypes(
            entry=cls._parse_enum(order_types_data.get("entry", "limit"), OrderType),
            exit=cls._parse_enum(order_types_data.get("exit", "market"), OrderType),
        )

        limit_orders_data = data.get("limit_orders", {})
        limit_orders = LimitOrderSettings(
            enabled=limit_orders_data.get("enabled", False),
            entry_offset_bps=limit_orders_data.get("entry_offset_bps", 5.0),
            exit_offset_bps=limit_orders_data.get("exit_offset_bps", 0.0),
            timeout_seconds=limit_orders_data.get("timeout_seconds", 30),
        )

        slippage_data = data.get("slippage", {})
        slippage = SlippageSettings(
            max_entry_slippage_bps=slippage_data.get("max_entry_slippage_bps", 20.0),
            max_exit_slippage_bps=slippage_data.get("max_exit_slippage_bps", 50.0),
            cancel_on_excessive_slippage=slippage_data.get(
                "cancel_on_excessive_slippage", True
            ),
        )

        partial_fills_data = data.get("partial_fills", {})
        partial_fills = PartialFillSettings(
            allow_partial=partial_fills_data.get("allow_partial", True),
            min_fill_percent=partial_fills_data.get("min_fill_percent", 80.0),
        )

        retries_data = data.get("retries", {})
        retries = RetrySettings(
            max_retries=retries_data.get("max_retries", 3),
            retry_delay_ms=retries_data.get("retry_delay_ms", 500),
            backoff_multiplier=retries_data.get("backoff_multiplier", 2.0),
        )

        liquidity_data = data.get("liquidity", {})
        liquidity = LiquiditySettings(
            min_orderbook_depth_usd=liquidity_data.get(
                "min_orderbook_depth_usd", 100000.0
            ),
            max_spread_bps=liquidity_data.get("max_spread_bps", 10.0),
        )

        timing_data = data.get("timing", {})
        timing = TimingSettings(
            immediate_or_cancel=timing_data.get("immediate_or_cancel", False),
            good_till_time_seconds=timing_data.get("good_till_time_seconds", 60),
        )

        return ExecutionPolicy(
            order_types=order_types,
            limit_orders=limit_orders,
            slippage=slippage,
            partial_fills=partial_fills,
            retries=retries,
            liquidity=liquidity,
            timing=timing,
        )

    @classmethod
    def _parse_risk_rules(cls, data: dict[str, Any]) -> RiskRules:
        """Parse risk rules section."""
        position_limits_data = data.get("position_limits", {})
        position_limits = PositionLimits(
            max_position_size_usd=position_limits_data.get(
                "max_position_size_usd", 0.0
            ),
            max_position_percent=position_limits_data.get("max_position_percent", 10.0),
            max_leverage=position_limits_data.get("max_leverage", 1.0),
        )

        portfolio_limits_data = data.get("portfolio_limits", {})
        portfolio_limits = PortfolioLimits(
            max_open_positions=portfolio_limits_data.get("max_open_positions", 5),
            max_correlated_positions=portfolio_limits_data.get(
                "max_correlated_positions", 2
            ),
            max_sector_exposure_percent=portfolio_limits_data.get(
                "max_sector_exposure_percent", 50.0
            ),
        )

        daily_limits_data = data.get("daily_limits", {})
        daily_limits = DailyLimits(
            max_daily_loss_usd=daily_limits_data.get("max_daily_loss_usd", 0.0),
            max_daily_loss_percent=daily_limits_data.get("max_daily_loss_percent", 2.0),
            max_daily_trades=daily_limits_data.get("max_daily_trades", 20),
        )

        circuit_breakers_data = data.get("circuit_breakers", [])
        circuit_breakers = tuple(
            CircuitBreaker(
                trigger=cls._parse_enum(
                    cb.get("trigger", "daily_loss"), CircuitBreakerTrigger
                ),
                threshold=cb.get("threshold", 0.0),
                action=cls._parse_enum(cb.get("action", "halt"), CircuitBreakerAction),
                duration_minutes=cb.get("duration_minutes", 0),
            )
            for cb in circuit_breakers_data
        )

        correlation_limits_data = data.get("correlation_limits", {})
        correlation_limits = CorrelationLimits(
            max_pair_correlation=correlation_limits_data.get(
                "max_pair_correlation", 0.8
            ),
            max_portfolio_correlation=correlation_limits_data.get(
                "max_portfolio_correlation", 0.7
            ),
        )

        return RiskRules(
            position_limits=position_limits,
            portfolio_limits=portfolio_limits,
            daily_limits=daily_limits,
            circuit_breakers=circuit_breakers,
            correlation_limits=correlation_limits,
        )

    @classmethod
    def _parse_telemetry_tags(cls, data: dict[str, Any]) -> TelemetryTags:
        """Parse telemetry tags section."""
        return TelemetryTags(
            strategy_family=data.get("strategy_family", ""),
            experiment_id=data.get("experiment_id", ""),
            risk_tier=cls._parse_enum(data.get("risk_tier", "moderate"), RiskTier),
            approval_status=cls._parse_enum(
                data.get("approval_status", "auto"), ApprovalStatus
            ),
            custom_tags=data.get("custom_tags", {}),
        )
