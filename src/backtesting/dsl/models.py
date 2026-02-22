"""Strategy DSL Models - Dataclasses for strategy configuration.

This module defines frozen dataclasses for each DSL section as specified
in docs/architecture/strategy-dsl.md. All classes are immutable to ensure
reproducibility and safety.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

# ============================================================================
# Enums
# ============================================================================


class StrategyCategory(Enum):
    """Strategy category types."""

    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    TREND_FOLLOWING = "trend_following"
    BREAKOUT = "breakout"
    GRID = "grid"
    ARBITRAGE = "arbitrage"


class StrategyStatus(Enum):
    """Strategy lifecycle status."""

    DEVELOPMENT = "development"
    BACKTESTING = "backtesting"
    PAPER = "paper"
    LIVE = "live"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class Timeframe(Enum):
    """Supported timeframes."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class MarketType(Enum):
    """Market types."""

    SPOT = "spot"
    PERPETUAL = "perpetual"
    MARGIN = "margin"


class EntryLogic(Enum):
    """Entry logic types."""

    SINGLE_INDICATOR = "single_indicator"
    CONFLUENCE = "confluence"
    ENSEMBLE = "ensemble"
    PATTERN = "pattern"


class IndicatorType(Enum):
    """Indicator types."""

    RSI = "rsi"
    MACD = "macd"
    EMA = "ema"
    SMA = "sma"
    BOLLINGER = "bollinger"
    ATR = "atr"
    VOLUME = "volume"
    CUSTOM = "custom"


class Operator(Enum):
    """Condition operators."""

    GT = "gt"
    LT = "lt"
    EQ = "eq"
    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"
    IN_RANGE = "in_range"


class Direction(Enum):
    """Trade direction."""

    LONG = "long"
    SHORT = "short"
    BOTH = "both"


class RegimeType(Enum):
    """Market regime types."""

    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    CALM = "calm"


class RegimeDetectionMethod(Enum):
    """Regime detection methods."""

    ADX = "adx"
    VOLATILITY = "volatility"
    ML_CLASSIFIER = "ml_classifier"


class VolatilityMethod(Enum):
    """Volatility calculation methods."""

    ATR = "atr"
    BOLLINGER = "bollinger"
    HISTORICAL = "historical"


class TimeFilterType(Enum):
    """Time-based filter types."""

    SESSION = "session"
    NEWS_EVENT = "news_event"
    WEEKEND = "weekend"


class TimeFilterAction(Enum):
    """Time-based filter actions."""

    BLOCK = "block"
    REDUCE_SIZE = "reduce_size"
    REQUIRE_CONFIRMATION = "require_confirmation"


class StopLossType(Enum):
    """Stop-loss types."""

    FIXED = "fixed"
    ATR_BASED = "atr_based"
    SUPPORT_RESISTANCE = "support_resistance"
    VOLATILITY = "volatility"


class TakeProfitType(Enum):
    """Take-profit types."""

    FIXED = "fixed"
    R_BASED = "r_based"
    FIBONACCI = "fibonacci"
    TRAILING = "trailing"


class TrailingActivation(Enum):
    """Trailing stop activation types."""

    IMMEDIATE = "immediate"
    PROFIT_BASED = "profit_based"


class TrailingDistanceType(Enum):
    """Trailing stop distance types."""

    FIXED = "fixed"
    ATR_BASED = "atr_based"
    PERCENT = "percent"


class SizingMethod(Enum):
    """Position sizing methods."""

    FIXED = "fixed"
    RISK_PERCENT = "risk_percent"
    KELLY = "kelly"
    VOLATILITY_TARGET = "volatility_target"
    FIXED_USD = "fixed_usd"


class PyramidingTrigger(Enum):
    """Pyramiding trigger types."""

    PROFIT_PERCENT = "profit_percent"
    ATR_DISTANCE = "atr_distance"


class OrderType(Enum):
    """Order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_LIMIT = "stop_limit"


class CircuitBreakerTrigger(Enum):
    """Circuit breaker trigger types."""

    DAILY_LOSS = "daily_loss"
    DRAWDOWN = "drawdown"
    VOLATILITY_SPIKE = "volatility_spike"


class CircuitBreakerAction(Enum):
    """Circuit breaker actions."""

    HALT = "halt"
    REDUCE_SIZE = "reduce_size"
    REQUIRE_APPROVAL = "require_approval"


class RiskTier(Enum):
    """Risk tier classifications."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class ApprovalStatus(Enum):
    """Approval status types."""

    AUTO = "auto"
    MANUAL = "manual"
    EXPERIMENTAL = "experimental"


class DayOfWeek(Enum):
    """Days of the week."""

    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


# ============================================================================
# Metadata Section
# ============================================================================


@dataclass(frozen=True)
class Metadata:
    """Strategy identification and versioning.

    Attributes:
        name: Unique strategy name
        version: Semantic version
        description: Human-readable description
        author: Strategy author/owner
        created_at: Creation timestamp
        updated_at: Last update timestamp
        tags: Classification tags
        category: Strategy category
        timeframes: Supported timeframes
        status: Strategy lifecycle status
    """

    name: str
    version: str
    description: str = ""
    author: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    category: StrategyCategory = StrategyCategory.GRID
    timeframes: tuple[Timeframe, ...] = field(default_factory=lambda: (Timeframe.H1,))
    status: StrategyStatus = StrategyStatus.DEVELOPMENT

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name is required")
        if not self.version:
            raise ValueError("version is required")


# ============================================================================
# Universe Section
# ============================================================================


@dataclass(frozen=True)
class Symbol:
    """Trading pair definition.

    Attributes:
        symbol: Trading pair (e.g., "BTCUSDT")
        exchange: Exchange identifier
        market_type: Market type
    """

    symbol: str
    exchange: str
    market_type: MarketType = MarketType.PERPETUAL


@dataclass(frozen=True)
class TradingSession:
    """Trading session definition.

    Attributes:
        name: Session name
        timezone: IANA timezone
        start_time: Session start (HH:MM)
        end_time: Session end (HH:MM)
        days: Active days
    """

    name: str
    timezone: str
    start_time: str
    end_time: str
    days: tuple[DayOfWeek, ...] = field(
        default_factory=lambda: (
            DayOfWeek.MON,
            DayOfWeek.TUE,
            DayOfWeek.WED,
            DayOfWeek.THU,
            DayOfWeek.FRI,
        )
    )


@dataclass(frozen=True)
class UniverseFilters:
    """Universe filters.

    Attributes:
        min_24h_volume_usd: Minimum daily volume
        max_spread_bps: Maximum spread in basis points
        min_liquidity_depth_usd: Minimum orderbook depth
    """

    min_24h_volume_usd: float = 0.0
    max_spread_bps: float = 100.0
    min_liquidity_depth_usd: float = 0.0


@dataclass(frozen=True)
class Universe:
    """Trading universe definition.

    Attributes:
        symbols: List of trading pairs
        sessions: Trading sessions (optional)
        filters: Universe filters
    """

    symbols: tuple[Symbol, ...] = field(default_factory=tuple)
    sessions: tuple[TradingSession, ...] = field(default_factory=tuple)
    filters: UniverseFilters = field(default_factory=UniverseFilters)


# ============================================================================
# Signals Section
# ============================================================================


@dataclass(frozen=True)
class IndicatorCondition:
    """Indicator entry condition.

    Attributes:
        operator: Comparison operator
        threshold: Threshold value
        direction: Trade direction
    """

    operator: Operator
    threshold: float
    direction: Direction


@dataclass(frozen=True)
class Indicator:
    """Indicator configuration.

    Attributes:
        name: Indicator name
        type: Indicator type
        parameters: Indicator-specific parameters
        conditions: Entry conditions
    """

    name: str
    type: IndicatorType
    parameters: dict[str, Any] = field(default_factory=dict)
    conditions: tuple[IndicatorCondition, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Confluence:
    """Confluence scoring configuration.

    Attributes:
        enabled: Whether confluence is enabled
        min_score: Minimum confluence score (0.0-1.0)
        min_confidence: Minimum confidence (0.0-1.0)
        require_alignment: Require all indicators align
    """

    enabled: bool = False
    min_score: float = 0.5
    min_confidence: float = 0.5
    require_alignment: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_score <= 1.0:
            raise ValueError(f"min_score must be 0.0-1.0, got {self.min_score}")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError(
                f"min_confidence must be 0.0-1.0, got {self.min_confidence}"
            )


@dataclass(frozen=True)
class Cooldown:
    """Signal cooldown configuration.

    Attributes:
        bars: Bars to wait between signals
        timeframe: Cooldown timeframe
    """

    bars: int = 1
    timeframe: Timeframe = Timeframe.H1


@dataclass(frozen=True)
class Signals:
    """Entry signal definitions.

    Attributes:
        entry_logic: Entry logic type
        indicators: Indicator configurations
        confluence: Confluence scoring
        cooldown: Signal cooldown
    """

    entry_logic: EntryLogic = EntryLogic.CONFLUENCE
    indicators: tuple[Indicator, ...] = field(default_factory=tuple)
    confluence: Confluence = field(default_factory=Confluence)
    cooldown: Cooldown = field(default_factory=Cooldown)


# ============================================================================
# Filters Section
# ============================================================================


@dataclass(frozen=True)
class RegimeFilter:
    """Market regime filter.

    Attributes:
        enabled: Whether filter is enabled
        allowed_regimes: Allowed market regimes
        detection_method: Regime detection method
        adx_threshold: ADX threshold for trending
    """

    enabled: bool = False
    allowed_regimes: tuple[RegimeType, ...] = field(default_factory=tuple)
    detection_method: RegimeDetectionMethod = RegimeDetectionMethod.ADX
    adx_threshold: float = 25.0


@dataclass(frozen=True)
class VolatilityFilter:
    """Volatility filter.

    Attributes:
        enabled: Whether filter is enabled
        method: Volatility calculation method
        atr_period: ATR period
        min_atr_percent: Minimum ATR as % of price
        max_atr_percent: Maximum ATR as % of price
    """

    enabled: bool = False
    method: VolatilityMethod = VolatilityMethod.ATR
    atr_period: int = 14
    min_atr_percent: float = 0.0
    max_atr_percent: float = 10.0


@dataclass(frozen=True)
class TimeBasedFilter:
    """Time-based filter.

    Attributes:
        name: Filter name
        type: Filter type
        action: Filter action
        parameters: Type-specific parameters
    """

    name: str
    type: TimeFilterType
    action: TimeFilterAction
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CorrelationFilter:
    """Correlation filter.

    Attributes:
        enabled: Whether filter is enabled
        max_correlation: Maximum correlation between positions
        lookback_days: Lookback period in days
    """

    enabled: bool = False
    max_correlation: float = 0.8
    lookback_days: int = 30


@dataclass(frozen=True)
class Filters:
    """Market regime and volatility filters.

    Attributes:
        regime: Market regime filter
        volatility: Volatility filter
        time_based: Time-based filters
        correlation: Correlation filter
    """

    regime: RegimeFilter = field(default_factory=RegimeFilter)
    volatility: VolatilityFilter = field(default_factory=VolatilityFilter)
    time_based: tuple[TimeBasedFilter, ...] = field(default_factory=tuple)
    correlation: CorrelationFilter = field(default_factory=CorrelationFilter)


# ============================================================================
# Exits Section
# ============================================================================


@dataclass(frozen=True)
class TakeProfitLevel:
    """Take-profit level.

    Attributes:
        percent: Profit percentage
        close_percent: % of position to close
    """

    percent: float
    close_percent: float


@dataclass(frozen=True)
class StopLoss:
    """Stop-loss configuration.

    Attributes:
        enabled: Whether stop-loss is enabled
        type: Stop-loss type
        fixed_percent: Fixed stop percentage
        atr_multiplier: ATR multiplier
        max_loss_percent: Maximum loss per trade
    """

    enabled: bool = True
    type: StopLossType = StopLossType.ATR_BASED
    fixed_percent: float = 0.0
    atr_multiplier: float = 1.5
    max_loss_percent: float = 2.0


@dataclass(frozen=True)
class TakeProfit:
    """Take-profit configuration.

    Attributes:
        enabled: Whether take-profit is enabled
        type: Take-profit type
        fixed_percent: Fixed take-profit percentage
        r_multiple: Risk multiple for R-based TP
        levels: Multiple TP levels
    """

    enabled: bool = True
    type: TakeProfitType = TakeProfitType.R_BASED
    fixed_percent: float = 0.0
    r_multiple: float = 2.0
    levels: tuple[TakeProfitLevel, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TrailingStop:
    """Trailing stop configuration.

    Attributes:
        enabled: Whether trailing stop is enabled
        activation: Activation type
        activation_percent: Profit % to activate
        distance_type: Distance type
        distance_value: Distance value
        atr_multiplier: ATR multiplier for atr_based distance
    """

    enabled: bool = False
    activation: TrailingActivation = TrailingActivation.IMMEDIATE
    activation_percent: float = 0.0
    distance_type: TrailingDistanceType = TrailingDistanceType.ATR_BASED
    distance_value: float = 0.0
    atr_multiplier: float = 1.0


@dataclass(frozen=True)
class TimeBasedExit:
    """Time-based exit configuration.

    Attributes:
        enabled: Whether time-based exit is enabled
        max_bars: Max bars to hold position
        max_hours: Max hours to hold position
        exit_at_session_end: Exit when session ends
    """

    enabled: bool = False
    max_bars: int = 0
    max_hours: float = 0.0
    exit_at_session_end: bool = False


@dataclass(frozen=True)
class BreakevenStop:
    """Breakeven stop configuration.

    Attributes:
        enabled: Whether breakeven is enabled
        activation_percent: Profit % to move to BE
        buffer_percent: Buffer above/below entry
    """

    enabled: bool = False
    activation_percent: float = 0.0
    buffer_percent: float = 0.0


@dataclass(frozen=True)
class Exits:
    """Exit rules configuration.

    Attributes:
        stop_loss: Stop-loss configuration
        take_profit: Take-profit configuration
        trailing_stop: Trailing stop configuration
        time_based: Time-based exits
        breakeven: Breakeven stop
    """

    stop_loss: StopLoss = field(default_factory=StopLoss)
    take_profit: TakeProfit = field(default_factory=TakeProfit)
    trailing_stop: TrailingStop = field(default_factory=TrailingStop)
    time_based: TimeBasedExit = field(default_factory=TimeBasedExit)
    breakeven: BreakevenStop = field(default_factory=BreakevenStop)


# ============================================================================
# Sizing Section
# ============================================================================


@dataclass(frozen=True)
class RiskPercentSizing:
    """Risk-based sizing configuration.

    Attributes:
        enabled: Whether risk-based sizing is enabled
        percent: % of equity to risk per trade
        max_position_percent: Max position as % of equity
    """

    enabled: bool = False
    percent: float = 1.0
    max_position_percent: float = 10.0


@dataclass(frozen=True)
class VolatilityTargetSizing:
    """Volatility targeting configuration.

    Attributes:
        enabled: Whether volatility targeting is enabled
        target_volatility: Target annualized volatility %
        lookback_days: Lookback period
        max_position_multiplier: Maximum position multiplier
    """

    enabled: bool = False
    target_volatility: float = 20.0
    lookback_days: int = 30
    max_position_multiplier: float = 2.0


@dataclass(frozen=True)
class DrawdownScaling:
    """Drawdown scaling configuration.

    Attributes:
        enabled: Whether drawdown scaling is enabled
        start_drawdown: DD % to start scaling
        max_drawdown: DD % to stop trading
        min_size_multiplier: Minimum size multiplier
    """

    enabled: bool = False
    start_drawdown: float = 5.0
    max_drawdown: float = 15.0
    min_size_multiplier: float = 0.25


@dataclass(frozen=True)
class Pyramiding:
    """Pyramiding configuration.

    Attributes:
        enabled: Whether pyramiding is enabled
        max_entries: Max number of entries
        size_reduction: Size reduction per entry (0-1)
        trigger: Pyramiding trigger
        trigger_value: Trigger value
    """

    enabled: bool = False
    max_entries: int = 3
    size_reduction: float = 0.5
    trigger: PyramidingTrigger = PyramidingTrigger.PROFIT_PERCENT
    trigger_value: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.size_reduction <= 1.0:
            raise ValueError(f"size_reduction must be 0-1, got {self.size_reduction}")


@dataclass(frozen=True)
class Sizing:
    """Position sizing rules.

    Attributes:
        method: Sizing method
        fixed_size: Fixed size (contracts/coins)
        fixed_usd: Fixed USD amount
        risk_percent: Risk-based sizing
        volatility_target: Volatility targeting
        drawdown_scaling: Drawdown scaling
        pyramiding: Pyramiding
    """

    method: SizingMethod = SizingMethod.RISK_PERCENT
    fixed_size: float = 0.0
    fixed_usd: float = 0.0
    risk_percent: RiskPercentSizing = field(default_factory=RiskPercentSizing)
    volatility_target: VolatilityTargetSizing = field(
        default_factory=VolatilityTargetSizing
    )
    drawdown_scaling: DrawdownScaling = field(default_factory=DrawdownScaling)
    pyramiding: Pyramiding = field(default_factory=Pyramiding)


# ============================================================================
# Execution Policy Section
# ============================================================================


@dataclass(frozen=True)
class OrderTypes:
    """Order type preferences.

    Attributes:
        entry: Entry order type
        exit: Exit order type
    """

    entry: OrderType = OrderType.LIMIT
    exit: OrderType = OrderType.MARKET


@dataclass(frozen=True)
class LimitOrderSettings:
    """Limit order settings.

    Attributes:
        enabled: Whether limit orders are enabled
        entry_offset_bps: Offset from signal price (basis points)
        exit_offset_bps: Exit offset in basis points
        timeout_seconds: Timeout before market order
    """

    enabled: bool = False
    entry_offset_bps: float = 5.0
    exit_offset_bps: float = 0.0
    timeout_seconds: int = 30


@dataclass(frozen=True)
class SlippageSettings:
    """Slippage handling settings.

    Attributes:
        max_entry_slippage_bps: Max entry slippage in basis points
        max_exit_slippage_bps: Max exit slippage in basis points
        cancel_on_excessive_slippage: Cancel on excessive slippage
    """

    max_entry_slippage_bps: float = 20.0
    max_exit_slippage_bps: float = 50.0
    cancel_on_excessive_slippage: bool = True


@dataclass(frozen=True)
class PartialFillSettings:
    """Partial fill handling.

    Attributes:
        allow_partial: Whether partial fills are allowed
        min_fill_percent: Minimum acceptable fill %
    """

    allow_partial: bool = True
    min_fill_percent: float = 80.0


@dataclass(frozen=True)
class RetrySettings:
    """Retry configuration.

    Attributes:
        max_retries: Maximum retry attempts
        retry_delay_ms: Delay between retries (ms)
        backoff_multiplier: Backoff multiplier
    """

    max_retries: int = 3
    retry_delay_ms: int = 500
    backoff_multiplier: float = 2.0


@dataclass(frozen=True)
class LiquiditySettings:
    """Liquidity requirements.

    Attributes:
        min_orderbook_depth_usd: Minimum orderbook depth
        max_spread_bps: Maximum spread in basis points
    """

    min_orderbook_depth_usd: float = 100000.0
    max_spread_bps: float = 10.0


@dataclass(frozen=True)
class TimingSettings:
    """Execution timing settings.

    Attributes:
        immediate_or_cancel: Immediate or cancel flag
        good_till_time_seconds: Good till time in seconds
    """

    immediate_or_cancel: bool = False
    good_till_time_seconds: int = 60


@dataclass(frozen=True)
class ExecutionPolicy:
    """Order execution parameters.

    Attributes:
        order_types: Order type preferences
        limit_orders: Limit order settings
        slippage: Slippage handling
        partial_fills: Partial fill handling
        retries: Retry configuration
        liquidity: Liquidity requirements
        timing: Execution timing
    """

    order_types: OrderTypes = field(default_factory=OrderTypes)
    limit_orders: LimitOrderSettings = field(default_factory=LimitOrderSettings)
    slippage: SlippageSettings = field(default_factory=SlippageSettings)
    partial_fills: PartialFillSettings = field(default_factory=PartialFillSettings)
    retries: RetrySettings = field(default_factory=RetrySettings)
    liquidity: LiquiditySettings = field(default_factory=LiquiditySettings)
    timing: TimingSettings = field(default_factory=TimingSettings)


# ============================================================================
# Risk Rules Section
# ============================================================================


@dataclass(frozen=True)
class PositionLimits:
    """Position-level limits.

    Attributes:
        max_position_size_usd: Maximum position size in USD
        max_position_percent: Max position as % of portfolio
        max_leverage: Maximum leverage (safety: 3x max)
    """

    max_position_size_usd: float = 0.0
    max_position_percent: float = 10.0
    max_leverage: float = 1.0


@dataclass(frozen=True)
class PortfolioLimits:
    """Portfolio-level limits.

    Attributes:
        max_open_positions: Maximum open positions
        max_correlated_positions: Maximum correlated positions
        max_sector_exposure_percent: Maximum sector exposure %
    """

    max_open_positions: int = 5
    max_correlated_positions: int = 2
    max_sector_exposure_percent: float = 50.0


@dataclass(frozen=True)
class DailyLimits:
    """Daily loss limits.

    Attributes:
        max_daily_loss_usd: Maximum daily loss in USD
        max_daily_loss_percent: Maximum daily loss %
        max_daily_trades: Maximum daily trades
    """

    max_daily_loss_usd: float = 0.0
    max_daily_loss_percent: float = 2.0
    max_daily_trades: int = 20


@dataclass(frozen=True)
class CircuitBreaker:
    """Circuit breaker configuration.

    Attributes:
        trigger: Trigger type
        threshold: Threshold value
        action: Action to take
        duration_minutes: Duration of action (0 = indefinite)
    """

    trigger: CircuitBreakerTrigger
    threshold: float
    action: CircuitBreakerAction
    duration_minutes: int = 0


@dataclass(frozen=True)
class CorrelationLimits:
    """Cross-position limits.

    Attributes:
        max_pair_correlation: Maximum pair correlation
        max_portfolio_correlation: Maximum portfolio correlation
    """

    max_pair_correlation: float = 0.8
    max_portfolio_correlation: float = 0.7


@dataclass(frozen=True)
class RiskRules:
    """Risk limits and caps.

    Attributes:
        position_limits: Position-level limits
        portfolio_limits: Portfolio-level limits
        daily_limits: Daily loss limits
        circuit_breakers: Trading halt triggers
        correlation_limits: Cross-position limits
    """

    position_limits: PositionLimits = field(default_factory=PositionLimits)
    portfolio_limits: PortfolioLimits = field(default_factory=PortfolioLimits)
    daily_limits: DailyLimits = field(default_factory=DailyLimits)
    circuit_breakers: tuple[CircuitBreaker, ...] = field(default_factory=tuple)
    correlation_limits: CorrelationLimits = field(default_factory=CorrelationLimits)


# ============================================================================
# Telemetry Tags Section
# ============================================================================


@dataclass(frozen=True)
class TelemetryTags:
    """Audit logging tags.

    Attributes:
        strategy_family: Strategy family identifier
        experiment_id: A/B test or experiment ID
        risk_tier: Risk tier classification
        approval_status: Approval status
        custom_tags: Additional custom tags
    """

    strategy_family: str = ""
    experiment_id: str = ""
    risk_tier: RiskTier = RiskTier.MODERATE
    approval_status: ApprovalStatus = ApprovalStatus.AUTO
    custom_tags: dict[str, str] = field(default_factory=dict)


# ============================================================================
# Complete Strategy DSL
# ============================================================================


@dataclass(frozen=True)
class StrategyDSL:
    """Complete strategy DSL configuration.

    This is the root dataclass that contains all sections of the strategy DSL.

    Attributes:
        metadata: Strategy identification and versioning
        universe: Trading universe
        signals: Entry signal definitions
        filters: Market regime and volatility filters
        exits: Exit rules
        sizing: Position sizing rules
        execution_policy: Order execution parameters
        risk_rules: Risk limits and caps
        telemetry_tags: Audit logging tags
    """

    metadata: Metadata
    universe: Universe
    signals: Signals
    exits: Exits
    sizing: Sizing
    execution_policy: ExecutionPolicy
    risk_rules: RiskRules
    filters: Filters = field(default_factory=Filters)
    telemetry_tags: TelemetryTags = field(default_factory=TelemetryTags)

    @classmethod
    def from_yaml(cls, path: Path | str) -> StrategyDSL:
        """Load strategy DSL from YAML file.

        Args:
            path: Path to YAML file

        Returns:
            Parsed StrategyDSL instance

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If YAML is invalid
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"DSL file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyDSL:
        """Create StrategyDSL from dictionary.

        Args:
            data: Dictionary containing DSL configuration

        Returns:
            StrategyDSL instance
        """
        from src.backtesting.dsl.parser import DSLParser

        return DSLParser.parse(data)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation of the DSL
        """
        from src.backtesting.dsl.serializer import DSLSerializer

        return DSLSerializer.serialize(self)

    def to_yaml(self, path: Path | str | None = None) -> str:
        """Convert to YAML string or write to file.

        Args:
            path: Optional path to write YAML file

        Returns:
            YAML string representation
        """
        data = self.to_dict()
        yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=True)

        if path:
            Path(path).write_text(yaml_str)

        return yaml_str
