"""ACP Runtime Initialization Module.

Dependency injection container and startup orchestration for ACP components.
Ensures proper initialization order and dependency wiring.

For EP-NS-008: ACP Runtime Initialization
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.autonomous_control_plane.components.circuit_breaker_registry import (
    CircuitBreakerRegistry,
)
from src.autonomous_control_plane.components.log_monitor import LogMonitor
from src.autonomous_control_plane.components.log_parsers import SimpleLogParser
from src.autonomous_control_plane.components.retry_coordinator import RetryCoordinator
from src.autonomous_control_plane.components.self_healing_engine import (
    SelfHealingEngine,
)
from src.autonomous_control_plane.components.incident_manager import IncidentManager
from src.autonomous_control_plane.components.rollback_coordinator import (
    RollbackCoordinator,
)
from src.autonomous_control_plane.telemetry.dashboard_sync import DashboardSyncServer
from src.autonomous_control_plane.trigger_service import HealingTriggerService
from src.discord_alerts import DiscordInitializer
from src.discord_alerts.config import DiscordConfig

logger = logging.getLogger(__name__)


class ACPContainer:
    """Dependency injection container for ACP components.

    Manages component lifecycle and ensures proper dependency injection:

    CircuitBreakerRegistry
         ↓
    RetryCoordinator (uses CB registry)
         ↓
    SelfHealingEngine (uses RetryCoordinator)
         ↓
    IncidentManager (uses SelfHealingEngine)
         ↓
    RollbackCoordinator (uses IncidentManager)

    All components are singletons within the container context.
    """

    _instance: ACPContainer | None = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        trading_mode: str = "paper",
        redis_client: Any | None = None,
        influx_client: Any | None = None,
        discord_webhook_url: str | None = None,
        grafana_oncall_url: str | None = None,
        grafana_oncall_token: str | None = None,
        require_redis: bool = True,
    ):
        """Initialize ACP container.

        Args:
            trading_mode: Trading mode (paper/live/production)
            redis_client: Redis client for state tracking
            influx_client: InfluxDB client for telemetry
            discord_webhook_url: Discord webhook for incident notifications
            grafana_oncall_url: Grafana On-Call API URL
            grafana_oncall_token: Grafana On-Call API token
            require_redis: Whether Redis is mandatory (defaults to True in production)
        """
        if self._initialized:
            return

        self._trading_mode = trading_mode
        self._redis_client = redis_client
        self._influx_client = influx_client
        self._discord_webhook_url = discord_webhook_url
        self._grafana_oncall_url = grafana_oncall_url
        self._grafana_oncall_token = grafana_oncall_token
        self._require_redis = (
            require_redis
            if require_redis is not None
            else (trading_mode == "production")
        )

        # Component references (initialized in startup())
        self._cb_registry: CircuitBreakerRegistry | None = None
        self._retry_coordinator: RetryCoordinator | None = None
        self._healing_engine: SelfHealingEngine | None = None
        self._incident_manager: IncidentManager | None = None
        self._rollback_coordinator: RollbackCoordinator | None = None
        self._dashboard_sync: DashboardSyncServer | None = None
        self._discord_initializer: DiscordInitializer | None = None
        self._log_monitor: LogMonitor | None = None
        self._trigger_service: HealingTriggerService | None = None

        self._initialized = True
        logger.info(f"ACPContainer created (trading_mode={trading_mode})")

    async def _verify_dependencies(self) -> None:
        """Verify critical dependencies are available.

        Raises:
            RuntimeError: If Redis or InfluxDB is unavailable
        """
        errors = []

        # Check Redis
        if self._redis_client:
            try:
                await self._redis_client.ping()
                logger.info("Redis connectivity verified")
            except Exception as e:
                if self._require_redis:
                    errors.append(f"Redis mandatory in production but unavailable: {e}")
                else:
                    logger.warning(
                        f"Redis unavailable (optional in {self._trading_mode} mode): {e}"
                    )
        else:
            if self._require_redis:
                errors.append(
                    "Redis is mandatory in production mode but not configured"
                )

        # Check InfluxDB
        if self._influx_client:
            try:
                # InfluxDB health check
                health = self._influx_client.health()
                if health.status != "pass":
                    errors.append(f"InfluxDB health check failed: {health.status}")
                else:
                    logger.info("InfluxDB connectivity verified")
            except Exception as e:
                errors.append(f"InfluxDB unavailable: {e}")

        if errors:
            raise RuntimeError(f"Dependency verification failed: {'; '.join(errors)}")

    async def startup(self) -> None:
        """Initialize all ACP components in dependency order.

        This method creates and wires all components following the
        dependency injection pattern:

        1. Verify critical dependencies (Redis, InfluxDB)
        2. CircuitBreakerRegistry (singleton, no deps)
        3. RetryCoordinator (depends on CB registry)
        4. SelfHealingEngine (depends on RetryCoordinator, Redis, InfluxDB)
        5. IncidentManager (depends on SelfHealingEngine for context)
        6. RollbackCoordinator (depends on IncidentManager for P0/P1 alerts)

        Raises:
            RuntimeError: If dependency verification fails
        """
        logger.info("Starting ACP component initialization...")

        # Step 0: Verify critical dependencies before initializing components
        logger.info("Verifying critical dependencies...")
        await self._verify_dependencies()

        # Step 0.5: Initialize Discord with retry logic
        logger.info("Initializing Discord...")
        discord_config = DiscordConfig.from_env()
        self._discord_initializer = DiscordInitializer(discord_config)
        discord_ok = await self._discord_initializer.initialize()
        if not discord_ok:
            logger.warning(
                "Discord initialization failed, continuing without Discord alerts"
            )

        # Wire to health router
        from src.api.health_router import set_discord_initializer

        set_discord_initializer(self._discord_initializer)

        # Step 1: Initialize CircuitBreakerRegistry (singleton)
        logger.info("Initializing CircuitBreakerRegistry...")
        self._cb_registry = CircuitBreakerRegistry()

        # Step 2: Initialize RetryCoordinator with CB registry dependency
        logger.info("Initializing RetryCoordinator...")
        self._retry_coordinator = RetryCoordinator()
        # Note: RetryCoordinator uses CB registry via parameter in execute_with_retry

        # Step 3: Initialize SelfHealingEngine with dependencies
        logger.info("Initializing SelfHealingEngine...")
        self._healing_engine = SelfHealingEngine(
            trading_mode=self._trading_mode,
            redis_client=self._redis_client,
            enable_approval_gates=(self._trading_mode != "production"),
        )

        # Step 4: Initialize IncidentManager with dependencies
        logger.info("Initializing IncidentManager...")
        self._incident_manager = IncidentManager(
            discord_webhook_url=self._discord_webhook_url,
            grafana_oncall_url=self._grafana_oncall_url,
            grafana_oncall_token=self._grafana_oncall_token,
        )

        # Step 5: Initialize RollbackCoordinator with dependencies
        logger.info("Initializing RollbackCoordinator...")
        self._rollback_coordinator = RollbackCoordinator(
            incident_manager=self._incident_manager,
        )

        # Step 6: Initialize DashboardSyncServer with ACP components
        logger.info("Initializing DashboardSyncServer...")
        self._dashboard_sync = DashboardSyncServer(
            circuit_breaker_registry=self._cb_registry,
            incident_manager=self._incident_manager,
            healing_engine=self._healing_engine,
            rollback_coordinator=self._rollback_coordinator,
        )
        await self._dashboard_sync.start()
        logger.info("DashboardSyncServer started")

        # Step 7: Initialize LogMonitor and HealingTriggerService
        logger.info("Initializing LogMonitor...")
        self._log_monitor = LogMonitor()

        # Add watchers for common log files
        log_dir = os.getenv("LOG_DIR", "/app/logs")
        self._log_monitor.add_watcher(
            name="app",
            path=f"{log_dir}/app.log",
            parser=SimpleLogParser(),
        )
        self._log_monitor.add_watcher(
            name="error",
            path=f"{log_dir}/error.log",
            parser=SimpleLogParser(),
        )

        # Start log monitor
        await self._log_monitor.start()
        logger.info("LogMonitor started")

        # Create and start trigger service
        logger.info("Initializing HealingTriggerService...")
        self._trigger_service = HealingTriggerService(
            log_monitor=self._log_monitor,
            healing_engine=self._healing_engine,
        )
        await self._trigger_service.start()
        logger.info("HealingTriggerService started")

        logger.info("ACP component initialization complete")

        # Log component status
        self._log_component_status()

    def _log_component_status(self) -> None:
        """Log the status of all initialized components."""
        status = {
            "circuit_breaker_registry": self._cb_registry is not None,
            "retry_coordinator": self._retry_coordinator is not None,
            "self_healing_engine": self._healing_engine is not None,
            "incident_manager": self._incident_manager is not None,
            "rollback_coordinator": self._rollback_coordinator is not None,
            "log_monitor": self._log_monitor is not None,
            "trigger_service": self._trigger_service is not None,
        }
        logger.info(f"ACP Component Status: {status}")

    @property
    def circuit_breaker_registry(self) -> CircuitBreakerRegistry:
        """Get the circuit breaker registry.

        Returns:
            CircuitBreakerRegistry instance

        Raises:
            RuntimeError: If components not initialized
        """
        if self._cb_registry is None:
            raise RuntimeError(
                "CircuitBreakerRegistry not initialized. Call startup() first."
            )
        return self._cb_registry

    @property
    def retry_coordinator(self) -> RetryCoordinator:
        """Get the retry coordinator.

        Returns:
            RetryCoordinator instance

        Raises:
            RuntimeError: If components not initialized
        """
        if self._retry_coordinator is None:
            raise RuntimeError(
                "RetryCoordinator not initialized. Call startup() first."
            )
        return self._retry_coordinator

    @property
    def self_healing_engine(self) -> SelfHealingEngine:
        """Get the self-healing engine.

        Returns:
            SelfHealingEngine instance

        Raises:
            RuntimeError: If components not initialized
        """
        if self._healing_engine is None:
            raise RuntimeError(
                "SelfHealingEngine not initialized. Call startup() first."
            )
        return self._healing_engine

    @property
    def incident_manager(self) -> IncidentManager:
        """Get the incident manager.

        Returns:
            IncidentManager instance

        Raises:
            RuntimeError: If components not initialized
        """
        if self._incident_manager is None:
            raise RuntimeError("IncidentManager not initialized. Call startup() first.")
        return self._incident_manager

    @property
    def rollback_coordinator(self) -> RollbackCoordinator:
        """Get the rollback coordinator.

        Returns:
            RollbackCoordinator instance

        Raises:
            RuntimeError: If components not initialized
        """
        if self._rollback_coordinator is None:
            raise RuntimeError(
                "RollbackCoordinator not initialized. Call startup() first."
            )
        return self._rollback_coordinator

    @property
    def dashboard_sync(self) -> DashboardSyncServer:
        """Get the dashboard sync server.

        Returns:
            DashboardSyncServer instance

        Raises:
            RuntimeError: If components not initialized
        """
        if self._dashboard_sync is None:
            raise RuntimeError(
                "DashboardSyncServer not initialized. Call startup() first."
            )
        return self._dashboard_sync

    @property
    def discord_initializer(self) -> DiscordInitializer:
        """Get the Discord initializer.

        Returns:
            DiscordInitializer instance

        Raises:
            RuntimeError: If Discord not initialized
        """
        if self._discord_initializer is None:
            raise RuntimeError("Discord not initialized. Call startup() first.")
        return self._discord_initializer

    @property
    def log_monitor(self) -> LogMonitor:
        """Get the log monitor.

        Returns:
            LogMonitor instance

        Raises:
            RuntimeError: If LogMonitor not initialized
        """
        if self._log_monitor is None:
            raise RuntimeError("LogMonitor not initialized. Call startup() first.")
        return self._log_monitor

    @property
    def trigger_service(self) -> HealingTriggerService:
        """Get the healing trigger service.

        Returns:
            HealingTriggerService instance

        Raises:
            RuntimeError: If TriggerService not initialized
        """
        if self._trigger_service is None:
            raise RuntimeError("TriggerService not initialized. Call startup() first.")
        return self._trigger_service

    async def shutdown(self) -> None:
        """Shutdown all ACP components gracefully."""
        logger.info("Shutting down ACP components...")

        if self._trigger_service:
            await self._trigger_service.stop()
            logger.info("HealingTriggerService stopped")

        if self._log_monitor:
            await self._log_monitor.stop()
            logger.info("LogMonitor stopped")

        if self._dashboard_sync:
            await self._dashboard_sync.stop()
            logger.info("DashboardSyncServer stopped")

        if self._discord_initializer:
            await self._discord_initializer.shutdown()
            logger.info("Discord initializer shutdown")

        logger.info("ACP components shutdown complete")

    def get_status(self) -> dict[str, Any]:
        """Get overall ACP status.

        Returns:
            Status dictionary with component states
        """
        return {
            "initialized": self._initialized,
            "trading_mode": self._trading_mode,
            "components": {
                "circuit_breaker_registry": self._cb_registry is not None,
                "retry_coordinator": self._retry_coordinator is not None,
                "self_healing_engine": self._healing_engine is not None,
                "incident_manager": self._incident_manager is not None,
                "rollback_coordinator": self._rollback_coordinator is not None,
                "log_monitor": self._log_monitor is not None,
                "trigger_service": self._trigger_service is not None,
            },
            "healing_engine": self._healing_engine.get_status()
            if self._healing_engine
            else None,
        }


# Global container instance (initialized in main.py)
_acp_container: ACPContainer | None = None


def get_acp_container() -> ACPContainer:
    """Get the global ACP container instance.

    Returns:
        ACPContainer instance

    Raises:
        RuntimeError: If container not initialized
    """
    if _acp_container is None:
        raise RuntimeError("ACP container not initialized")
    return _acp_container


def set_acp_container(container: ACPContainer) -> None:
    """Set the global ACP container instance.

    Args:
        container: ACPContainer instance to set as global
    """
    global _acp_container
    _acp_container = container


def reset_acp_container() -> None:
    """Reset the global ACP container instance.

    This is primarily for testing purposes.
    """
    global _acp_container
    _acp_container = None


def create_acp_container(
    trading_mode: str | None = None,
    redis_client: Any | None = None,
    influx_client: Any | None = None,
    require_redis: bool | None = None,
) -> ACPContainer:
    """Create and configure the ACP container.

    Reads configuration from environment variables:
    - ACP_TRADING_MODE: paper/live/production (default: paper)
    - DISCORD_WEBHOOK_URL: Discord webhook for P0/P1 notifications
    - GRAFANA_ONCALL_URL: Grafana On-Call API URL
    - GRAFANA_ONCALL_TOKEN: Grafana On-Call API token

    Args:
        trading_mode: Override trading mode from env (if not provided, reads from ACP_TRADING_MODE env var)
        redis_client: Redis client for state tracking
        influx_client: InfluxDB client for telemetry
        require_redis: Whether Redis is mandatory (defaults to True in production mode)

    Returns:
        Configured ACPContainer instance
    """
    # Read from environment with safe defaults
    # Priority: explicit parameter > env var > default "paper"
    mode = trading_mode or os.getenv("ACP_TRADING_MODE", "paper")
    discord_url = os.getenv("DISCORD_WEBHOOK_URL")
    grafana_url = os.getenv("GRAFANA_ONCALL_URL")
    grafana_token = os.getenv("GRAFANA_ONCALL_TOKEN")

    # In production mode, Redis is mandatory by default
    if require_redis is None:
        require_redis = mode == "production"

    container = ACPContainer(
        trading_mode=mode,
        redis_client=redis_client,
        influx_client=influx_client,
        discord_webhook_url=discord_url,
        grafana_oncall_url=grafana_url,
        grafana_oncall_token=grafana_token,
        require_redis=require_redis,
    )

    set_acp_container(container)
    return container
