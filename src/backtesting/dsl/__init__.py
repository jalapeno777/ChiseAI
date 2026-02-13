"""Strategy DSL - Domain-Specific Language for trading strategies.

This package provides a complete DSL for defining, validating, and managing
trading strategies with safety constraints, versioning, and reproducibility.

Example:

    from src.backtesting.dsl import (
        StrategyDSL,
        DSLValidator,
        StrategySubmission,
        compute_dsl_fingerprint,
    )

    # Load and validate a strategy
    dsl = StrategyDSL.from_yaml('strategy.yaml')

    # Validate
    validator = DSLValidator()
    result = validator.validate(dsl.to_dict())

    if result.is_valid:
        print("Strategy is valid!")
    else:
        for error in result.errors:
            print(f"Error at {error.field_path}: {error.message}")

    # Submit
    submission = StrategySubmission()
    result = submission.submit(dsl.to_dict())
    print(f"Fingerprint: {result.fingerprint}")
"""

from src.backtesting.dsl.models import (
    # Main DSL class
    StrategyDSL,
    # Sections
    Metadata,
    Universe,
    Signals,
    Filters,
    Exits,
    Sizing,
    ExecutionPolicy,
    RiskRules,
    TelemetryTags,
    # Enums
    StrategyCategory,
    StrategyStatus,
    Timeframe,
    MarketType,
    EntryLogic,
    IndicatorType,
    Operator,
    Direction,
    # Sub-models
    Symbol,
    Indicator,
    StopLoss,
    TakeProfit,
    PositionLimits,
)

from src.backtesting.dsl.validator import (
    DSLValidator,
    ValidationResult,
    ValidationError,
    ValidationWarning,
)

from src.backtesting.dsl.safety import (
    SafetyChecker,
    check_safety,
    is_safe,
    SAFETY_CONSTRAINTS,
)

from src.backtesting.dsl.fingerprint import (
    compute_dsl_fingerprint,
    compute_dsl_fingerprint_short,
    diff_configs,
    configs_equal,
    DSLFingerprint,
    ConfigDiff,
    DiffEntry,
)

from src.backtesting.dsl.migration import (
    DSLMigration,
    migrate_config,
    get_config_version,
    can_migrate,
)

from src.backtesting.dsl.submission import (
    StrategySubmission,
    SubmissionResult,
    submit_strategy,
    submit_strategy_file,
    validate_strategy,
    check_strategy_safety,
)

__all__ = [
    # Models
    "StrategyDSL",
    "Metadata",
    "Universe",
    "Signals",
    "Filters",
    "Exits",
    "Sizing",
    "ExecutionPolicy",
    "RiskRules",
    "TelemetryTags",
    # Enums
    "StrategyCategory",
    "StrategyStatus",
    "Timeframe",
    "MarketType",
    "EntryLogic",
    "IndicatorType",
    "Operator",
    "Direction",
    # Sub-models
    "Symbol",
    "Indicator",
    "StopLoss",
    "TakeProfit",
    "PositionLimits",
    # Validator
    "DSLValidator",
    "ValidationResult",
    "ValidationError",
    "ValidationWarning",
    # Safety
    "SafetyChecker",
    "check_safety",
    "is_safe",
    "SAFETY_CONSTRAINTS",
    # Fingerprint
    "compute_dsl_fingerprint",
    "compute_dsl_fingerprint_short",
    "diff_configs",
    "configs_equal",
    "DSLFingerprint",
    "ConfigDiff",
    "DiffEntry",
    # Migration
    "DSLMigration",
    "migrate_config",
    "get_config_version",
    "can_migrate",
    # Submission
    "StrategySubmission",
    "SubmissionResult",
    "submit_strategy",
    "submit_strategy_file",
    "validate_strategy",
    "check_strategy_safety",
]

__version__ = "1.0.0"
