"""Trading mode configuration module for ChiseAI.

Provides centralized configuration management for different trading modes,
module tracking, and validation of trading configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any


class TradingMode(Enum):
    """Enumeration of supported trading modes.

    Attributes:
        PAPER: Simulated trading with virtual funds for testing strategies.
        LIVE: Real trading with actual funds on live exchanges.
        BACKTEST: Historical data simulation for strategy validation.
        DRY_RUN: Live market data but no actual order execution.
    """

    PAPER = auto()
    LIVE = auto()
    BACKTEST = auto()
    DRY_RUN = auto()


class ModuleType(Enum):
    """Enumeration of trading system module types.

    Attributes:
        SIGNAL_GENERATOR: Module responsible for generating trading signals.
        RISK_MANAGER: Module responsible for risk assessment and management.
        PAPER_EXECUTOR: Module for executing paper/simulated trades.
        LLM_PROVIDER: Module for LLM-based decision support.
        MARKET_DATA: Module for market data ingestion and processing.
    """

    SIGNAL_GENERATOR = auto()
    RISK_MANAGER = auto()
    PAPER_EXECUTOR = auto()
    LLM_PROVIDER = auto()
    MARKET_DATA = auto()


@dataclass
class ModuleStatus:
    """Status information for a trading system module.

    Attributes:
        name: Human-readable name of the module.
        loaded: Whether the module has been successfully loaded.
        healthy: Whether the module is currently healthy.
        error_message: Optional error message if module is unhealthy.
        last_check: Timestamp of the last health check.
    """

    name: str
    loaded: bool = False
    healthy: bool = False
    error_message: str | None = None
    last_check: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_operational(self) -> bool:
        """Check if the module is operational (loaded and healthy).

        Returns:
            True if the module is both loaded and healthy.
        """
        return self.loaded and self.healthy

    def mark_healthy(self) -> None:
        """Mark the module as healthy and update last check time."""
        self.healthy = True
        self.error_message = None
        self.last_check = datetime.now(UTC)

    def mark_unhealthy(self, error_message: str) -> None:
        """Mark the module as unhealthy with an error message.

        Args:
            error_message: Description of the error condition.
        """
        self.healthy = False
        self.error_message = error_message
        self.last_check = datetime.now(UTC)


@dataclass
class TradingModeConfig:
    """Configuration for trading mode and associated settings.

    This dataclass encapsulates all configuration parameters needed to
    run the trading system in various modes with appropriate safety
    constraints and module configurations.

    Attributes:
        mode: The current trading mode (PAPER, LIVE, BACKTEST, DRY_RUN).
        enabled_modules: Set of module types enabled for this configuration.
        provider_settings: Dictionary of provider-specific settings.
        risk_limits: Dictionary of risk limit parameters.
        paper_portfolio_value: Starting portfolio value for paper trading.
        signal_confidence_threshold: Minimum confidence for signal acceptance.
        max_position_size_pct: Maximum position size as percentage of portfolio.
        kill_switch_drawdown_pct: Drawdown percentage that triggers kill switch.
    """

    mode: TradingMode
    enabled_modules: set[ModuleType] = field(default_factory=set)
    provider_settings: dict[str, Any] = field(default_factory=dict)
    risk_limits: dict[str, float] = field(default_factory=dict)
    paper_portfolio_value: float = 10000.0
    signal_confidence_threshold: float = 0.75
    max_position_size_pct: float = 0.10
    kill_switch_drawdown_pct: float = 0.10

    # Define required modules for each trading mode
    _MODE_REQUIREMENTS: dict[TradingMode, set[ModuleType]] = field(
        default_factory=lambda: {
            TradingMode.PAPER: {
                ModuleType.SIGNAL_GENERATOR,
                ModuleType.RISK_MANAGER,
                ModuleType.PAPER_EXECUTOR,
                ModuleType.MARKET_DATA,
            },
            TradingMode.LIVE: {
                ModuleType.SIGNAL_GENERATOR,
                ModuleType.RISK_MANAGER,
                ModuleType.MARKET_DATA,
            },
            TradingMode.BACKTEST: {
                ModuleType.SIGNAL_GENERATOR,
                ModuleType.RISK_MANAGER,
                ModuleType.PAPER_EXECUTOR,
            },
            TradingMode.DRY_RUN: {
                ModuleType.SIGNAL_GENERATOR,
                ModuleType.RISK_MANAGER,
                ModuleType.MARKET_DATA,
            },
        },
        repr=False,
    )

    def get_required_modules(self) -> set[ModuleType]:
        """Get the set of modules required for the current trading mode.

        Returns:
            Set of ModuleType values required for the configured mode.
        """
        return self._MODE_REQUIREMENTS.get(self.mode, set()).copy()

    def validate_config(self) -> bool:
        """Validate that the configuration meets mode requirements.

        Checks that all required modules for the current trading mode
        are present in the enabled_modules set.

        Returns:
            True if configuration is valid, False otherwise.
        """
        required = self.get_required_modules()
        return required.issubset(self.enabled_modules)

    def get_missing_modules(self) -> set[ModuleType]:
        """Get the set of required modules that are not enabled.

        Returns:
            Set of ModuleType values that are required but not enabled.
        """
        required = self.get_required_modules()
        return required - self.enabled_modules

    def enable_module(self, module_type: ModuleType) -> None:
        """Enable a specific module type.

        Args:
            module_type: The module type to enable.
        """
        self.enabled_modules.add(module_type)

    def disable_module(self, module_type: ModuleType) -> None:
        """Disable a specific module type.

        Args:
            module_type: The module type to disable.
        """
        self.enabled_modules.discard(module_type)

    def is_module_enabled(self, module_type: ModuleType) -> bool:
        """Check if a specific module type is enabled.

        Args:
            module_type: The module type to check.

        Returns:
            True if the module is enabled, False otherwise.
        """
        return module_type in self.enabled_modules

    def get_validation_errors(self) -> list[str]:
        """Get a list of validation error messages.

        Returns:
            List of error messages describing configuration issues.
        """
        errors: list[str] = []

        # Check required modules
        missing = self.get_missing_modules()
        if missing:
            module_names = [m.name for m in missing]
            errors.append(
                f"Missing required modules for {self.mode.name}: "
                f"{', '.join(module_names)}"
            )

        # Validate risk limits
        if self.max_position_size_pct <= 0 or self.max_position_size_pct > 1.0:
            errors.append(
                f"max_position_size_pct must be between 0 and 1, "
                f"got {self.max_position_size_pct}"
            )

        if self.kill_switch_drawdown_pct <= 0 or self.kill_switch_drawdown_pct > 1.0:
            errors.append(
                f"kill_switch_drawdown_pct must be between 0 and 1, "
                f"got {self.kill_switch_drawdown_pct}"
            )

        if (
            self.signal_confidence_threshold < 0
            or self.signal_confidence_threshold > 1.0
        ):
            errors.append(
                f"signal_confidence_threshold must be between 0 and 1, "
                f"got {self.signal_confidence_threshold}"
            )

        # Validate paper portfolio value for paper mode
        if self.mode == TradingMode.PAPER and self.paper_portfolio_value <= 0:
            errors.append(
                f"paper_portfolio_value must be positive for PAPER mode, "
                f"got {self.paper_portfolio_value}"
            )

        return errors

    @classmethod
    def create_paper_config(
        cls,
        portfolio_value: float = 10000.0,
        signal_threshold: float = 0.75,
        max_position_pct: float = 0.10,
        kill_switch_pct: float = 0.10,
    ) -> TradingModeConfig:
        """Create a pre-configured paper trading configuration.

        Args:
            portfolio_value: Starting portfolio value for paper trading.
            signal_threshold: Minimum confidence for signal acceptance.
            max_position_pct: Maximum position size as percentage of portfolio.
            kill_switch_pct: Drawdown percentage that triggers kill switch.

        Returns:
            TradingModeConfig configured for paper trading.
        """
        return cls(
            mode=TradingMode.PAPER,
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR,
                ModuleType.RISK_MANAGER,
                ModuleType.PAPER_EXECUTOR,
                ModuleType.MARKET_DATA,
            },
            paper_portfolio_value=portfolio_value,
            signal_confidence_threshold=signal_threshold,
            max_position_size_pct=max_position_pct,
            kill_switch_drawdown_pct=kill_switch_pct,
        )

    @classmethod
    def create_backtest_config(
        cls,
        signal_threshold: float = 0.75,
        max_position_pct: float = 0.10,
    ) -> TradingModeConfig:
        """Create a pre-configured backtest configuration.

        Args:
            signal_threshold: Minimum confidence for signal acceptance.
            max_position_pct: Maximum position size as percentage of portfolio.

        Returns:
            TradingModeConfig configured for backtesting.
        """
        return cls(
            mode=TradingMode.BACKTEST,
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR,
                ModuleType.RISK_MANAGER,
                ModuleType.PAPER_EXECUTOR,
            },
            signal_confidence_threshold=signal_threshold,
            max_position_size_pct=max_position_pct,
        )

    @classmethod
    def create_dry_run_config(
        cls,
        signal_threshold: float = 0.75,
        max_position_pct: float = 0.10,
    ) -> TradingModeConfig:
        """Create a pre-configured dry run configuration.

        Args:
            signal_threshold: Minimum confidence for signal acceptance.
            max_position_pct: Maximum position size as percentage of portfolio.

        Returns:
            TradingModeConfig configured for dry run mode.
        """
        return cls(
            mode=TradingMode.DRY_RUN,
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR,
                ModuleType.RISK_MANAGER,
                ModuleType.MARKET_DATA,
            },
            signal_confidence_threshold=signal_threshold,
            max_position_size_pct=max_position_pct,
        )


# Convenience exports for direct import
__all__ = [
    "TradingMode",
    "ModuleType",
    "ModuleStatus",
    "TradingModeConfig",
]
