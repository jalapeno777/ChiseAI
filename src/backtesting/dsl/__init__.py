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

from src.backtesting.dsl.fingerprint import (
    ConfigDiff,
    DiffEntry,
    DSLFingerprint,
    compute_dsl_fingerprint,
    compute_dsl_fingerprint_short,
    configs_equal,
    diff_configs,
)
from src.backtesting.dsl.migration import (
    DSLMigration,
    can_migrate,
    get_config_version,
    migrate_config,
)
from src.backtesting.dsl.models import (
    Direction,
    EntryLogic,
    ExecutionPolicy,
    Exits,
    Filters,
    Indicator,
    IndicatorType,
    MarketType,
    # Sections
    Metadata,
    Operator,
    PositionLimits,
    RiskRules,
    Signals,
    Sizing,
    StopLoss,
    # Enums
    StrategyCategory,
    # Main DSL class
    StrategyDSL,
    StrategyStatus,
    # Sub-models
    Symbol,
    TakeProfit,
    TelemetryTags,
    Timeframe,
    Universe,
)
from src.backtesting.dsl.safety import (
    SAFETY_CONSTRAINTS,
    SafetyChecker,
    check_safety,
    is_safe,
)
from src.backtesting.dsl.submission import (
    StrategySubmission,
    SubmissionResult,
    check_strategy_safety,
    submit_strategy,
    submit_strategy_file,
    validate_strategy,
)
from src.backtesting.dsl.validator import (
    DSLValidator,
    ValidationError,
    ValidationResult,
    ValidationWarning,
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
