"""Trading Mode Loader - Main module for loading and coordinating trading components.

This module provides the TradingModeLoader class which is responsible for:
- Loading and initializing all trading components (signal generator, risk enforcer,
  paper orchestrator, LLM provider chain)
- Tracking module health status
- Graceful shutdown of all modules
- Health check aggregation across all modules
"""

import asyncio
import logging
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, Protocol

from pydantic import BaseModel, Field

# Configure logging
logger = logging.getLogger(__name__)


class ModuleType(Enum):
    """Enumeration of trading module types."""

    SIGNAL_GENERATOR = auto()
    RISK_ENFORCER = auto()
    PAPER_ORCHESTRATOR = auto()
    LLM_PROVIDER_CHAIN = auto()


class ModuleState(Enum):
    """Enumeration of module lifecycle states."""

    UNINITIALIZED = auto()
    LOADING = auto()
    LOADED = auto()
    ERROR = auto()
    SHUTDOWN = auto()


class ModuleStatus(BaseModel):
    """Status information for a trading module.

    Attributes:
        module_type: The type of module
        state: Current lifecycle state
        enabled: Whether the module is enabled
        loaded: Whether the module is successfully loaded
        healthy: Whether the module is healthy
        error_message: Error message if module failed to load
        last_check: Timestamp of last health check
    """

    module_type: ModuleType
    state: ModuleState = ModuleState.UNINITIALIZED
    enabled: bool = True
    loaded: bool = False
    healthy: bool = False
    error_message: str | None = None
    last_check: datetime | None = None


class TradingModeConfig(BaseModel):
    """Configuration for trading mode loader.

    Attributes:
        mode: Trading mode (paper, live, backtest)
        enabled_modules: Dict mapping module types to enabled status
        llm_provider_priority: Priority order for LLM providers (KIMI-first default)
        health_check_interval: Seconds between health checks
    """

    mode: str = Field(default="paper", pattern="^(paper|live|backtest)$")
    enabled_modules: dict[ModuleType, bool] = Field(
        default_factory=lambda: {
            ModuleType.SIGNAL_GENERATOR: True,
            ModuleType.RISK_ENFORCER: True,
            ModuleType.PAPER_ORCHESTRATOR: True,
            ModuleType.LLM_PROVIDER_CHAIN: True,
        }
    )
    llm_provider_priority: list[str] = Field(
        default_factory=lambda: ["kimi", "zai", "zhipu", "minimax"]
    )
    health_check_interval: int = Field(default=30, ge=5)


class HealthCheckable(Protocol):
    """Protocol for modules that support health checks."""

    async def health_check(self) -> dict[str, Any]:
        """Return health status of the module."""
        ...

    async def shutdown(self) -> None:
        """Gracefully shutdown the module."""
        ...


class TradingModeLoader:
    """Main loader and coordinator for trading components.

    This class is responsible for loading, coordinating, and managing the lifecycle
    of all trading modules including signal generation, risk enforcement,
    paper trading orchestration, and LLM provider chains.

    Attributes:
        config: TradingModeConfig instance with loader configuration
        module_status: Dict tracking status of each module
        _loaded: Whether all modules have been loaded successfully
        _modules: Dict storing references to loaded module instances
    """

    def __init__(self, config: TradingModeConfig) -> None:
        """Initialize the TradingModeLoader.

        Args:
            config: Configuration for the trading mode loader
        """
        self.config = config
        self.module_status: dict[ModuleType, ModuleStatus] = {
            module_type: ModuleStatus(module_type=module_type, enabled=enabled)
            for module_type, enabled in config.enabled_modules.items()
        }
        self._loaded = False
        self._modules: dict[ModuleType, Any] = {}

        logger.info(f"TradingModeLoader initialized in {config.mode} mode")

    async def load(self) -> bool:
        """Load all enabled trading modules.

        Loads modules in the following order:
        1. Signal Generator - for generating trading signals
        2. Risk Enforcer - for enforcing risk limits
        3. Paper Orchestrator - for paper trading execution
        4. LLM Provider Chain - for LLM-based enhancements (KIMI-first)

        Returns:
            bool: True if all enabled modules loaded successfully, False otherwise
        """
        logger.info("Starting module loading sequence")

        load_order = [
            (ModuleType.SIGNAL_GENERATOR, self._load_signal_generator),
            (ModuleType.RISK_ENFORCER, self._load_risk_enforcer),
            (ModuleType.PAPER_ORCHESTRATOR, self._load_paper_orchestrator),
            (ModuleType.LLM_PROVIDER_CHAIN, self._load_llm_provider_chain),
        ]

        all_successful = True

        for module_type, loader_func in load_order:
            status = self.module_status[module_type]

            if not status.enabled:
                logger.info(f"Module {module_type.name} is disabled, skipping")
                continue

            status.state = ModuleState.LOADING

            try:
                logger.info(f"Loading module: {module_type.name}")
                module = await loader_func()

                if module is not None:
                    self._modules[module_type] = module
                    status.loaded = True
                    status.healthy = True
                    status.state = ModuleState.LOADED
                    status.last_check = datetime.now(UTC)
                    logger.info(f"Successfully loaded module: {module_type.name}")
                else:
                    status.state = ModuleState.ERROR
                    status.error_message = "Module loader returned None"
                    all_successful = False
                    logger.error(f"Module {module_type.name} returned None")

            except Exception as e:
                status.state = ModuleState.ERROR
                status.error_message = f"{type(e).__name__}: {str(e)}"
                all_successful = False
                logger.exception(f"Failed to load module {module_type.name}: {e}")

        self._loaded = all_successful

        if self._loaded:
            logger.info("All modules loaded successfully")
        else:
            logger.warning("Some modules failed to load")

        return self._loaded

    async def _load_signal_generator(self) -> Any | None:
        """Load the signal generator module.

        Returns:
            Signal generator instance or None if loading fails
        """
        try:
            from src.signal_generation.signal_generator import SignalGenerator

            # Initialize signal generator with default configuration
            signal_generator = SignalGenerator()

            # Perform any async initialization if available
            if hasattr(signal_generator, "initialize") and callable(
                signal_generator.initialize
            ):
                await signal_generator.initialize()

            return signal_generator

        except ImportError as e:
            logger.error(f"Failed to import signal_generator: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize signal_generator: {e}")
            raise

    async def _load_risk_enforcer(self) -> Any | None:
        """Load the risk enforcer module.

        Returns:
            Risk enforcer instance or None if loading fails
        """
        try:
            from src.execution.paper.risk_enforcer import PaperRiskEnforcer

            # Initialize risk enforcer
            risk_enforcer = PaperRiskEnforcer()

            # Perform any async initialization if available
            if hasattr(risk_enforcer, "initialize") and callable(
                risk_enforcer.initialize
            ):
                await risk_enforcer.initialize()

            return risk_enforcer

        except ImportError as e:
            logger.error(f"Failed to import risk_enforcer: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize risk_enforcer: {e}")
            raise

    async def _load_paper_orchestrator(self) -> Any | None:
        """Load the paper trading orchestrator module.

        Returns:
            Paper orchestrator instance or None if loading fails
        """
        try:
            from src.execution.paper.orchestrator import PaperTradingOrchestrator
            from src.execution.paper.order_simulator import (
                OrderSimulator,
                MarketDataProvider,
            )
            from src.execution.paper.risk_enforcer import PaperRiskEnforcer
            from src.execution.telemetry.collector import ExecutionCollector
            from src.execution.telemetry.exporter import ExecutionTelemetryExporter
            from src.execution.kill_switch.executor import KillSwitchExecutor
            from src.execution.outcome_capture.integration import (
                OutcomeCaptureIntegration,
            )
            from src.portfolio.paper_tracker import PaperPositionTracker
            from src.signal_generation.signal_generator import SignalGenerator

            # Create required components
            signal_generator = SignalGenerator()
            market_data = MarketDataProvider()
            order_simulator = OrderSimulator(market_data=market_data)
            position_tracker = PaperPositionTracker()
            risk_enforcer = PaperRiskEnforcer()
            kill_switch = KillSwitchExecutor()

            # Create telemetry
            telemetry_exporter = ExecutionTelemetryExporter()
            telemetry = ExecutionCollector(exporter=telemetry_exporter)

            # Create outcome capture integration for Discord alerts
            outcome_capture = OutcomeCaptureIntegration()

            # Initialize paper orchestrator with outcome capture
            paper_orchestrator = PaperTradingOrchestrator(
                signal_generator=signal_generator,
                order_simulator=order_simulator,
                position_tracker=position_tracker,
                risk_enforcer=risk_enforcer,
                telemetry_collector=telemetry,
                kill_switch=kill_switch,
                outcome_capture=outcome_capture,
            )

            # Perform any async initialization if available
            if hasattr(paper_orchestrator, "initialize") and callable(
                paper_orchestrator.initialize
            ):
                await paper_orchestrator.initialize()

            return paper_orchestrator

        except ImportError as e:
            logger.error(f"Failed to import orchestrator: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize orchestrator: {e}")
            raise

    async def _load_llm_provider_chain(self) -> Any | None:
        """Load the LLM provider chain module (KIMI-first).

        Returns:
            LLM provider chain instance or None if loading fails
        """
        try:
            from src.llm.provider_chain import LLMProviderChain

            # Initialize provider chain with KIMI-first priority
            provider_chain = LLMProviderChain(
                provider_priority=self.config.llm_provider_priority
            )

            # Perform any async initialization if available
            if hasattr(provider_chain, "initialize") and callable(
                provider_chain.initialize
            ):
                await provider_chain.initialize()

            return provider_chain

        except ImportError as e:
            logger.error(f"Failed to import provider_chain: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize provider_chain: {e}")
            raise

    def is_healthy(self) -> bool:
        """Check if all enabled modules are loaded and healthy.

        Returns:
            bool: True if all enabled modules are healthy, False otherwise
        """
        for _module_type, status in self.module_status.items():
            if status.enabled and (not status.loaded or not status.healthy):
                return False
        return True

    def get_module_status(self) -> dict[ModuleType, ModuleStatus]:
        """Get current status of all modules.

        Returns:
            Dict mapping ModuleType to ModuleStatus
        """
        return self.module_status.copy()

    async def shutdown(self) -> None:
        """Gracefully shutdown all loaded modules.

        Shuts down modules in reverse order of loading to ensure
        proper dependency handling.
        """
        logger.info("Starting graceful shutdown of all modules")

        shutdown_order = [
            ModuleType.LLM_PROVIDER_CHAIN,
            ModuleType.PAPER_ORCHESTRATOR,
            ModuleType.RISK_ENFORCER,
            ModuleType.SIGNAL_GENERATOR,
        ]

        for module_type in shutdown_order:
            status = self.module_status.get(module_type)

            if status is None or not status.loaded:
                continue

            module = self._modules.get(module_type)

            if module is None:
                continue

            try:
                logger.info(f"Shutting down module: {module_type.name}")

                # Call shutdown if available
                if hasattr(module, "shutdown") and callable(module.shutdown):
                    if asyncio.iscoroutinefunction(module.shutdown):
                        await module.shutdown()
                    else:
                        module.shutdown()

                status.state = ModuleState.SHUTDOWN
                status.healthy = False
                logger.info(f"Successfully shutdown module: {module_type.name}")

            except Exception as e:
                status.error_message = f"Shutdown error: {type(e).__name__}: {str(e)}"
                logger.exception(f"Error shutting down module {module_type.name}: {e}")

        self._loaded = False
        self._modules.clear()
        logger.info("Shutdown complete")

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on all modules.

        Checks each loaded module's health and aggregates results.

        Returns:
            Dict containing:
                - overall_healthy: bool indicating overall health status
                - modules: dict of module health statuses
                - timestamp: ISO format timestamp of the check
        """
        timestamp = datetime.now(UTC)
        modules_health: dict[str, Any] = {}
        overall_healthy = True

        for module_type, status in self.module_status.items():
            if not status.enabled or not status.loaded:
                continue

            module = self._modules.get(module_type)
            module_health: dict[str, Any] = {
                "enabled": status.enabled,
                "loaded": status.loaded,
                "state": status.state.name,
            }

            if (
                module is not None
                and hasattr(module, "health_check")
                and callable(module.health_check)
            ):
                try:
                    if asyncio.iscoroutinefunction(module.health_check):
                        health_result = await module.health_check()
                    else:
                        health_result = module.health_check()

                    module_health["healthy"] = health_result.get("healthy", False)
                    module_health["details"] = health_result
                    status.healthy = module_health["healthy"]

                except Exception as e:
                    module_health["healthy"] = False
                    module_health["error"] = f"{type(e).__name__}: {str(e)}"
                    status.healthy = False
                    status.error_message = module_health["error"]
                    logger.exception(f"Health check failed for {module_type.name}: {e}")
            else:
                # No health_check method, use loaded status as proxy
                module_health["healthy"] = status.loaded
                status.healthy = status.loaded

            status.last_check = timestamp
            modules_health[module_type.name] = module_health

            if status.enabled and not module_health.get("healthy", False):
                overall_healthy = False

        return {
            "overall_healthy": overall_healthy,
            "modules": modules_health,
            "timestamp": timestamp.isoformat(),
        }


# Convenience function for creating a loader instance
async def create_trading_mode_loader(
    config: TradingModeConfig | None = None,
) -> TradingModeLoader:
    """Create and load a TradingModeLoader instance.

    Args:
        config: Optional configuration. Uses defaults if not provided.

    Returns:
        Loaded TradingModeLoader instance

    Raises:
        RuntimeError: If module loading fails
    """
    if config is None:
        config = TradingModeConfig()

    loader = TradingModeLoader(config)
    success = await loader.load()

    if not success:
        # Get error details
        errors = {
            mt.name: st.error_message
            for mt, st in loader.module_status.items()
            if st.error_message
        }
        raise RuntimeError(f"Failed to load trading modules: {errors}")

    return loader
