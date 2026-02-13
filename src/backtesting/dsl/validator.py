"""DSL Validator - Validate strategy DSL configurations.

This module provides comprehensive validation of DSL configurations with
field-level error reporting as required by ST-SIG-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.backtesting.dsl.models import (
    StrategyDSL,
    Timeframe,
    StrategyCategory,
    StrategyStatus,
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
)


@dataclass(frozen=True)
class ValidationError:
    """Field-level validation error.

    Attributes:
        field_path: Dot-notation path to the field (e.g., "risk_rules.position_limits.max_leverage")
        message: Human-readable error message
        value: The invalid value
        constraint: The constraint that was violated
    """

    field_path: str
    message: str
    value: Any
    constraint: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "field_path": self.field_path,
            "message": self.message,
            "value": self.value,
            "constraint": self.constraint,
        }


@dataclass(frozen=True)
class ValidationWarning:
    """Validation warning (non-blocking).

    Attributes:
        field_path: Dot-notation path to the field
        message: Human-readable warning message
        value: The value triggering the warning
        suggestion: Suggested fix or improvement
    """

    field_path: str
    message: str
    value: Any
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "field_path": self.field_path,
            "message": self.message,
            "value": self.value,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class ValidationResult:
    """Complete validation result.

    Attributes:
        is_valid: True if no errors (warnings OK)
        errors: List of validation errors
        warnings: List of validation warnings
        dsl_version: Detected DSL version
    """

    is_valid: bool
    errors: list[ValidationError]
    warnings: list[ValidationWarning]
    dsl_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "dsl_version": self.dsl_version,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }

    def get_errors_for_field(self, field_path: str) -> list[ValidationError]:
        """Get all errors for a specific field path."""
        return [e for e in self.errors if e.field_path == field_path]

    def has_error_in_path(self, path_prefix: str) -> bool:
        """Check if any errors exist in a path prefix."""
        return any(e.field_path.startswith(path_prefix) for e in self.errors)


class DSLValidator:
    """Validator for Strategy DSL configurations.

    Validates DSL configurations according to the specification in
    docs/architecture/strategy-dsl.md with field-level error reporting.
    """

    # Supported values from DSL spec
    SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}
    SUPPORTED_CATEGORIES = {
        "momentum",
        "mean_reversion",
        "trend_following",
        "breakout",
        "grid",
        "arbitrage",
    }
    SUPPORTED_STATUSES = {
        "development",
        "backtesting",
        "paper",
        "live",
        "deprecated",
        "archived",
    }

    # Safety constraints (hard limits)
    MAX_LEVERAGE = 3.0
    MAX_POSITION_PERCENT = 100.0
    MIN_CONFLUENCE_SCORE = 0.5
    MAX_CONFLUENCE_SCORE = 1.0
    MAX_DAILY_LOSS_PERCENT = 5.0

    def __init__(self) -> None:
        """Initialize validator."""
        self.errors: list[ValidationError] = []
        self.warnings: list[ValidationWarning] = []

    def validate(self, config: dict[str, Any]) -> ValidationResult:
        """Validate DSL configuration.

        Args:
            config: Raw dictionary configuration

        Returns:
            ValidationResult with errors and warnings
        """
        self.errors = []
        self.warnings = []

        # Get version from config
        metadata = config.get("metadata", {})
        version = metadata.get("version", "1.0.0")

        # Validate each section
        self._validate_metadata(config.get("metadata", {}))
        self._validate_universe(config.get("universe", {}))
        self._validate_signals(config.get("signals", {}))
        self._validate_filters(config.get("filters", {}))
        self._validate_exits(config.get("exits", {}))
        self._validate_sizing(config.get("sizing", {}))
        self._validate_execution_policy(config.get("execution_policy", {}))
        self._validate_risk_rules(config.get("risk_rules", {}))
        self._validate_telemetry_tags(config.get("telemetry_tags", {}))

        # Cross-section validation
        self._validate_cross_section(config)

        return ValidationResult(
            is_valid=len(self.errors) == 0,
            errors=self.errors.copy(),
            warnings=self.warnings.copy(),
            dsl_version=version,
        )

    def validate_file(self, path: Path | str) -> ValidationResult:
        """Validate DSL file.

        Args:
            path: Path to YAML file

        Returns:
            ValidationResult
        """
        path = Path(path)

        if not path.exists():
            return ValidationResult(
                is_valid=False,
                errors=[
                    ValidationError(
                        field_path="",
                        message=f"File not found: {path}",
                        value=str(path),
                        constraint="file must exist",
                    )
                ],
                warnings=[],
            )

        try:
            with open(path, "r") as f:
                config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return ValidationResult(
                is_valid=False,
                errors=[
                    ValidationError(
                        field_path="",
                        message=f"Invalid YAML: {e}",
                        value="",
                        constraint="valid YAML syntax",
                    )
                ],
                warnings=[],
            )

        return self.validate(config)

    def _add_error(
        self, field_path: str, message: str, value: Any, constraint: str
    ) -> None:
        """Add a validation error."""
        self.errors.append(
            ValidationError(
                field_path=field_path,
                message=message,
                value=value,
                constraint=constraint,
            )
        )

    def _add_warning(
        self, field_path: str, message: str, value: Any, suggestion: str
    ) -> None:
        """Add a validation warning."""
        self.warnings.append(
            ValidationWarning(
                field_path=field_path,
                message=message,
                value=value,
                suggestion=suggestion,
            )
        )

    def _validate_metadata(self, data: dict[str, Any]) -> None:
        """Validate metadata section."""
        # Required fields
        if not data.get("name"):
            self._add_error(
                "metadata.name",
                "Strategy name is required",
                data.get("name"),
                "required field",
            )

        if not data.get("version"):
            self._add_error(
                "metadata.version",
                "Version is required",
                data.get("version"),
                "required field",
            )

        # Validate category
        category = data.get("category", "")
        if category and category not in self.SUPPORTED_CATEGORIES:
            self._add_error(
                "metadata.category",
                f"Invalid category: {category}",
                category,
                f"must be one of: {self.SUPPORTED_CATEGORIES}",
            )

        # Validate status
        status = data.get("status", "")
        if status and status not in self.SUPPORTED_STATUSES:
            self._add_error(
                "metadata.status",
                f"Invalid status: {status}",
                status,
                f"must be one of: {self.SUPPORTED_STATUSES}",
            )

        # Validate timeframes
        timeframes = data.get("timeframes", [])
        if timeframes:
            for i, tf in enumerate(timeframes):
                if tf not in self.SUPPORTED_TIMEFRAMES:
                    self._add_error(
                        f"metadata.timeframes[{i}]",
                        f"Invalid timeframe: {tf}",
                        tf,
                        f"must be one of: {self.SUPPORTED_TIMEFRAMES}",
                    )
        else:
            self._add_warning(
                "metadata.timeframes",
                "No timeframes specified",
                [],
                "Add at least one timeframe for clarity",
            )

    def _validate_universe(self, data: dict[str, Any]) -> None:
        """Validate universe section."""
        symbols = data.get("symbols", [])

        if not symbols:
            self._add_error(
                "universe.symbols",
                "At least one symbol is required",
                [],
                "non-empty list required",
            )
        else:
            for i, symbol in enumerate(symbols):
                if not symbol.get("symbol"):
                    self._add_error(
                        f"universe.symbols[{i}].symbol",
                        "Symbol identifier is required",
                        symbol.get("symbol"),
                        "required field",
                    )

                if not symbol.get("exchange"):
                    self._add_error(
                        f"universe.symbols[{i}].exchange",
                        "Exchange is required",
                        symbol.get("exchange"),
                        "required field",
                    )

        # Validate filters
        filters = data.get("filters", {})
        if filters.get("max_spread_bps", 0) < 0:
            self._add_error(
                "universe.filters.max_spread_bps",
                "max_spread_bps cannot be negative",
                filters["max_spread_bps"],
                "must be >= 0",
            )

    def _validate_signals(self, data: dict[str, Any]) -> None:
        """Validate signals section."""
        # Validate entry logic
        entry_logic = data.get("entry_logic", "confluence")
        valid_logics = {"single_indicator", "confluence", "ensemble", "pattern"}
        if entry_logic not in valid_logics:
            self._add_error(
                "signals.entry_logic",
                f"Invalid entry_logic: {entry_logic}",
                entry_logic,
                f"must be one of: {valid_logics}",
            )

        # Validate confluence settings
        confluence = data.get("confluence", {})
        if confluence.get("enabled", False):
            min_score = confluence.get("min_score", 0.5)
            if not self.MIN_CONFLUENCE_SCORE <= min_score <= self.MAX_CONFLUENCE_SCORE:
                self._add_error(
                    "signals.confluence.min_score",
                    f"min_score must be between {self.MIN_CONFLUENCE_SCORE} and {self.MAX_CONFLUENCE_SCORE}",
                    min_score,
                    f"must be in range [{self.MIN_CONFLUENCE_SCORE}, {self.MAX_CONFLUENCE_SCORE}]",
                )

        # Validate indicators
        indicators = data.get("indicators", [])
        if not indicators:
            self._add_warning(
                "signals.indicators",
                "No indicators defined",
                [],
                "Add at least one indicator for entry signals",
            )

        for i, indicator in enumerate(indicators):
            if not indicator.get("name"):
                self._add_error(
                    f"signals.indicators[{i}].name",
                    "Indicator name is required",
                    indicator.get("name"),
                    "required field",
                )

            valid_indicators = {
                "rsi",
                "macd",
                "ema",
                "sma",
                "bollinger",
                "atr",
                "volume",
                "custom",
            }
            ind_type = indicator.get("type", "")
            if ind_type and ind_type not in valid_indicators:
                self._add_error(
                    f"signals.indicators[{i}].type",
                    f"Invalid indicator type: {ind_type}",
                    ind_type,
                    f"must be one of: {valid_indicators}",
                )

        # Validate cooldown
        cooldown = data.get("cooldown", {})
        if cooldown.get("bars", 1) < 1:
            self._add_warning(
                "signals.cooldown.bars",
                "Cooldown bars should be >= 1",
                cooldown["bars"],
                "Set bars to at least 1 to prevent overtrading",
            )

    def _validate_filters(self, data: dict[str, Any]) -> None:
        """Validate filters section."""
        # Regime filter
        regime = data.get("regime", {})
        if regime.get("enabled", False):
            valid_regimes = {"trending", "ranging", "volatile", "calm"}
            for i, r in enumerate(regime.get("allowed_regimes", [])):
                if r not in valid_regimes:
                    self._add_error(
                        f"filters.regime.allowed_regimes[{i}]",
                        f"Invalid regime: {r}",
                        r,
                        f"must be one of: {valid_regimes}",
                    )

        # Volatility filter
        volatility = data.get("volatility", {})
        if volatility.get("enabled", False):
            min_atr = volatility.get("min_atr_percent", 0)
            max_atr = volatility.get("max_atr_percent", 10)
            if min_atr >= max_atr:
                self._add_error(
                    "filters.volatility.min_atr_percent",
                    "min_atr_percent must be less than max_atr_percent",
                    min_atr,
                    f"must be < {max_atr}",
                )

    def _validate_exits(self, data: dict[str, Any]) -> None:
        """Validate exits section."""
        # Stop-loss validation
        stop_loss = data.get("stop_loss", {})
        if not stop_loss.get("enabled", True):
            self._add_warning(
                "exits.stop_loss.enabled",
                "Stop-loss is disabled",
                False,
                "Enable stop-loss for risk protection",
            )
        else:
            max_loss = stop_loss.get("max_loss_percent", 2.0)
            if max_loss > 5.0:
                self._add_warning(
                    "exits.stop_loss.max_loss_percent",
                    f"Large stop-loss: {max_loss}%",
                    max_loss,
                    "Consider reducing to <= 5% for better risk control",
                )

        # Take-profit validation
        take_profit = data.get("take_profit", {})
        if not take_profit.get("enabled", True):
            self._add_warning(
                "exits.take_profit.enabled",
                "Take-profit is disabled",
                False,
                "Consider enabling take-profit for profit targets",
            )

    def _validate_sizing(self, data: dict[str, Any]) -> None:
        """Validate sizing section."""
        method = data.get("method", "risk_percent")
        valid_methods = {
            "fixed",
            "risk_percent",
            "kelly",
            "volatility_target",
            "fixed_usd",
        }
        if method not in valid_methods:
            self._add_error(
                "sizing.method",
                f"Invalid sizing method: {method}",
                method,
                f"must be one of: {valid_methods}",
            )

        # Risk percent validation
        risk_percent = data.get("risk_percent", {})
        if risk_percent.get("enabled", False):
            percent = risk_percent.get("percent", 1.0)
            if percent > 5.0:
                self._add_warning(
                    "sizing.risk_percent.percent",
                    f"High risk per trade: {percent}%",
                    percent,
                    "Consider reducing to <= 5% for better risk management",
                )

            max_pos = risk_percent.get("max_position_percent", 10.0)
            if max_pos > 50.0:
                self._add_warning(
                    "sizing.risk_percent.max_position_percent",
                    f"High position concentration: {max_pos}%",
                    max_pos,
                    "Consider reducing to <= 50% to avoid over-concentration",
                )

    def _validate_execution_policy(self, data: dict[str, Any]) -> None:
        """Validate execution policy section."""
        order_types = data.get("order_types", {})
        valid_order_types = {"market", "limit", "stop_limit"}

        entry_type = order_types.get("entry", "limit")
        if entry_type not in valid_order_types:
            self._add_error(
                "execution_policy.order_types.entry",
                f"Invalid entry order type: {entry_type}",
                entry_type,
                f"must be one of: {valid_order_types}",
            )

        exit_type = order_types.get("exit", "market")
        valid_exit_types = {"market", "limit"}
        if exit_type not in valid_exit_types:
            self._add_error(
                "execution_policy.order_types.exit",
                f"Invalid exit order type: {exit_type}",
                exit_type,
                f"must be one of: {valid_exit_types}",
            )

    def _validate_risk_rules(self, data: dict[str, Any]) -> None:
        """Validate risk rules section with safety constraints."""
        # Position limits - SAFETY CONSTRAINT: max_leverage <= 3.0
        position_limits = data.get("position_limits", {})
        max_leverage = position_limits.get("max_leverage", 1.0)
        if max_leverage > self.MAX_LEVERAGE:
            self._add_error(
                "risk_rules.position_limits.max_leverage",
                f"max_leverage exceeds safety limit: {max_leverage}x",
                max_leverage,
                f"must be <= {self.MAX_LEVERAGE}x",
            )

        # SAFETY CONSTRAINT: max_position_percent <= 100%
        max_position_percent = position_limits.get("max_position_percent", 10.0)
        if max_position_percent > self.MAX_POSITION_PERCENT:
            self._add_error(
                "risk_rules.position_limits.max_position_percent",
                f"max_position_percent exceeds 100%: {max_position_percent}%",
                max_position_percent,
                f"must be <= {self.MAX_POSITION_PERCENT}%",
            )

        # Daily limits
        daily_limits = data.get("daily_limits", {})
        max_daily_loss = daily_limits.get("max_daily_loss_percent", 2.0)
        if max_daily_loss > self.MAX_DAILY_LOSS_PERCENT:
            self._add_warning(
                "risk_rules.daily_limits.max_daily_loss_percent",
                f"High daily loss limit: {max_daily_loss}%",
                max_daily_loss,
                f"Consider reducing to <= {self.MAX_DAILY_LOSS_PERCENT}%",
            )

        # Circuit breakers
        circuit_breakers = data.get("circuit_breakers", [])
        valid_triggers = {"daily_loss", "drawdown", "volatility_spike"}
        valid_actions = {"halt", "reduce_size", "require_approval"}

        for i, cb in enumerate(circuit_breakers):
            trigger = cb.get("trigger", "")
            if trigger not in valid_triggers:
                self._add_error(
                    f"risk_rules.circuit_breakers[{i}].trigger",
                    f"Invalid trigger: {trigger}",
                    trigger,
                    f"must be one of: {valid_triggers}",
                )

            action = cb.get("action", "")
            if action not in valid_actions:
                self._add_error(
                    f"risk_rules.circuit_breakers[{i}].action",
                    f"Invalid action: {action}",
                    action,
                    f"must be one of: {valid_actions}",
                )

    def _validate_telemetry_tags(self, data: dict[str, Any]) -> None:
        """Validate telemetry tags section."""
        risk_tier = data.get("risk_tier", "moderate")
        valid_tiers = {"conservative", "moderate", "aggressive"}
        if risk_tier not in valid_tiers:
            self._add_error(
                "telemetry_tags.risk_tier",
                f"Invalid risk_tier: {risk_tier}",
                risk_tier,
                f"must be one of: {valid_tiers}",
            )

        approval_status = data.get("approval_status", "auto")
        valid_statuses = {"auto", "manual", "experimental"}
        if approval_status not in valid_statuses:
            self._add_error(
                "telemetry_tags.approval_status",
                f"Invalid approval_status: {approval_status}",
                approval_status,
                f"must be one of: {valid_statuses}",
            )

    def _validate_cross_section(self, config: dict[str, Any]) -> None:
        """Validate cross-section consistency."""
        # Check that risk percent sizing matches position limits
        sizing = config.get("sizing", {})
        risk_rules = config.get("risk_rules", {})

        if sizing.get("method") == "risk_percent":
            risk_percent = sizing.get("risk_percent", {})
            position_limits = risk_rules.get("position_limits", {})

            if risk_percent.get("enabled", False):
                sizing_max_pos = risk_percent.get("max_position_percent", 10.0)
                risk_max_pos = position_limits.get("max_position_percent", 10.0)

                if sizing_max_pos > risk_max_pos:
                    self._add_warning(
                        "sizing.risk_percent.max_position_percent",
                        f"Sizing max_position_percent ({sizing_max_pos}%) exceeds risk limit ({risk_max_pos}%)",
                        sizing_max_pos,
                        f"Reduce to <= {risk_max_pos}%",
                    )
