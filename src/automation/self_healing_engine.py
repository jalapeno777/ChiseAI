"""Self-healing engine for automated recovery actions.

Provides specific healing actions for common failure scenarios:
- Redis disconnect & reconnection with backoff
- Exchange API failure & backup exchange switching
- High error rate & service component restart
- Data gap & backfill triggering
- Bad deployment detection & rollback

For PAPER-003-004: Event-Driven Self-Healing Automation
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class HealingAction(Enum):
    """Types of healing actions available."""

    REDIS_RECONNECT = "redis_reconnect"
    EXCHANGE_FAILOVER = "exchange_failover"
    SERVICE_RESTART = "service_restart"
    DATA_BACKFILL = "data_backfill"
    DEPLOYMENT_ROLLBACK = "deployment_rollback"
    CIRCUIT_BREAKER_RESET = "circuit_breaker_reset"
    RATE_LIMIT_BACKOFF = "rate_limit_backoff"


class HealingStatus(StrEnum):
    """Status of a healing action."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class SelfHealingResult:
    """Result of a self-healing action.

    Attributes:
        action: The healing action performed
        status: Success/failure status
        source: Component that was healed
        duration_seconds: Time taken
        details: Additional output
        error: Error message if failed
        timestamp: When healing completed
    """

    action: HealingAction
    status: HealingStatus
    source: str
    duration_seconds: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action.value,
            "status": self.status.value,
            "source": self.source,
            "duration_seconds": self.duration_seconds,
            "details": self.details,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class DeploymentHealth:
    """Track deployment health for rollback decisions.

    Attributes:
        deployment_id: Unique deployment identifier
        version: Deployed version
        deployed_at: When deployed
        health_scores: List of health score samples
        last_healthy_at: Last time health was good
    """

    deployment_id: str
    version: str
    deployed_at: datetime
    health_scores: list[tuple[datetime, float]] = field(default_factory=list)
    last_healthy_at: datetime | None = None

    @property
    def current_health_score(self) -> float:
        """Get current health score (0-100)."""
        if not self.health_scores:
            return 100.0
        return self.health_scores[-1][1]

    @property
    def average_health_score(self) -> float:
        """Get average health score over last 10 minutes."""
        cutoff = datetime.now(UTC) - timedelta(minutes=10)
        recent_scores = [score for ts, score in self.health_scores if ts > cutoff]
        if not recent_scores:
            return 100.0
        return sum(recent_scores) / len(recent_scores)

    @property
    def is_healthy(self) -> bool:
        """Check if deployment is healthy (score >= 50)."""
        return self.current_health_score >= 50.0

    @property
    def needs_rollback(self) -> bool:
        """Check if deployment needs rollback (score < 50 for 5+ min)."""
        if self.current_health_score >= 50:
            return False

        # Check if unhealthy for 5+ minutes
        if not self.last_healthy_at:
            # Never been healthy since deployment
            unhealthy_duration = datetime.now(UTC) - self.deployed_at
        else:
            unhealthy_duration = datetime.now(UTC) - self.last_healthy_at

        return unhealthy_duration.total_seconds() >= 300  # 5 minutes


class RedisReconnector:
    """Handles Redis reconnection with exponential backoff."""

    BACKOFF_DELAYS = [1.0, 2.0, 5.0, 10.0, 30.0]  # seconds
    MAX_ATTEMPTS = 5

    def __init__(
        self,
        redis_client: Any | None = None,
        connection_string: str | None = None,
    ):
        """Initialize Redis reconnector.

        Args:
            redis_client: Existing Redis client to reconnect
            connection_string: Redis connection string
        """
        self._redis_client = redis_client
        self._connection_string = connection_string or os.getenv(
            "REDIS_URL", "redis://localhost:6380"
        )

    async def reconnect(self) -> SelfHealingResult:
        """Attempt to reconnect to Redis with backoff.

        Returns:
            Self-healing result
        """
        start_time = time.time()
        source = "redis"
        attempts = []

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            delay = self.BACKOFF_DELAYS[min(attempt - 1, len(self.BACKOFF_DELAYS) - 1)]

            logger.info(f"Redis reconnection attempt {attempt}/{self.MAX_ATTEMPTS}")

            try:
                if self._redis_client:
                    # Try to ping existing client
                    if hasattr(self._redis_client, "ping"):
                        await asyncio.wait_for(self._redis_client.ping(), timeout=5.0)
                    result = {"method": "existing_client", "ping": "success"}
                else:
                    # Try to create new connection
                    import redis.asyncio as redis

                    client = redis.from_url(
                        self._connection_string,
                        socket_connect_timeout=5,
                        socket_timeout=5,
                        retry_on_timeout=True,
                    )
                    await client.ping()
                    await client.close()
                    result = {"method": "new_connection", "ping": "success"}

                duration = time.time() - start_time
                logger.info(f"Redis reconnection succeeded after {attempt} attempts")

                return SelfHealingResult(
                    action=HealingAction.REDIS_RECONNECT,
                    status=HealingStatus.SUCCEEDED,
                    source=source,
                    duration_seconds=duration,
                    details={
                        "attempts": attempt,
                        "attempts_detail": attempts,
                        "final_backoff": delay,
                        **result,
                    },
                )

            except Exception as e:
                attempts.append({"attempt": attempt, "error": str(e)})
                logger.warning(f"Redis reconnection attempt {attempt} failed: {e}")

                if attempt < self.MAX_ATTEMPTS:
                    logger.info(f"Waiting {delay}s before next attempt...")
                    await asyncio.sleep(delay)

        # All attempts failed
        duration = time.time() - start_time
        logger.error(f"Redis reconnection failed after {self.MAX_ATTEMPTS} attempts")

        return SelfHealingResult(
            action=HealingAction.REDIS_RECONNECT,
            status=HealingStatus.FAILED,
            source=source,
            duration_seconds=duration,
            details={"attempts": self.MAX_ATTEMPTS, "attempts_detail": attempts},
            error=f"Failed after {self.MAX_ATTEMPTS} attempts",
        )


class ExchangeFailover:
    """Handles exchange API failover to backup exchanges."""

    EXCHANGE_PRIORITIES = {
        "bybit": ["bybit", "bitget", "binance"],
        "bitget": ["bitget", "bybit", "binance"],
        "binance": ["binance", "bybit", "bitget"],
    }

    def __init__(
        self,
        current_exchange: str = "bybit",
        exchange_connectors: dict[str, Any] | None = None,
    ):
        """Initialize exchange failover.

        Args:
            current_exchange: Current primary exchange
            exchange_connectors: Dict of exchange name -> connector
        """
        self._current = current_exchange
        self._connectors = exchange_connectors or {}

    async def failover(self, failed_exchange: str | None = None) -> SelfHealingResult:
        """Perform failover to backup exchange.

        Args:
            failed_exchange: Exchange that failed, or None for current

        Returns:
            Self-healing result
        """
        start_time = time.time()
        source = failed_exchange or self._current

        # Determine failover priority
        priority_list = self.EXCHANGE_PRIORITIES.get(source, ["bybit", "bitget"])

        logger.info(f"Starting exchange failover from {source}")

        for exchange in priority_list:
            if exchange == source:
                continue  # Skip the failed one

            logger.info(f"Trying failover to {exchange}")

            try:
                connector = self._connectors.get(exchange)

                if connector:
                    # Test connector
                    health = await connector.health_check()
                    if health.get("healthy"):
                        duration = time.time() - start_time
                        logger.info(f"Failover to {exchange} succeeded")

                        return SelfHealingResult(
                            action=HealingAction.EXCHANGE_FAILOVER,
                            status=HealingStatus.SUCCEEDED,
                            source=source,
                            duration_seconds=duration,
                            details={
                                "from_exchange": source,
                                "to_exchange": exchange,
                                "health_check": health,
                            },
                        )
                else:
                    # No connector available, check if we can create one
                    logger.warning(f"No connector available for {exchange}")

            except Exception as e:
                logger.warning(f"Failover to {exchange} failed: {e}")

        # All failovers failed
        duration = time.time() - start_time
        logger.error("All exchange failovers failed")

        return SelfHealingResult(
            action=HealingAction.EXCHANGE_FAILOVER,
            status=HealingStatus.FAILED,
            source=source,
            duration_seconds=duration,
            error="No backup exchanges available",
        )


class ServiceRestarter:
    """Handles service component restarts."""

    def __init__(
        self,
        docker_compose_file: str | None = None,
        use_systemd: bool = False,
    ):
        """Initialize service restarter.

        Args:
            docker_compose_file: Path to docker-compose.yml
            use_systemd: Whether to use systemd for service management
        """
        self._compose_file = docker_compose_file
        self._use_systemd = use_systemd

    async def restart(self, service_name: str) -> SelfHealingResult:
        """Restart a service component.

        Args:
            service_name: Name of service to restart

        Returns:
            Self-healing result
        """
        start_time = time.time()

        logger.info(f"Restarting service: {service_name}")

        try:
            if self._use_systemd:
                result = await self._restart_systemd(service_name)
            else:
                result = await self._restart_docker(service_name)

            duration = time.time() - start_time

            if result["success"]:
                return SelfHealingResult(
                    action=HealingAction.SERVICE_RESTART,
                    status=HealingStatus.SUCCEEDED,
                    source=service_name,
                    duration_seconds=duration,
                    details=result,
                )
            else:
                return SelfHealingResult(
                    action=HealingAction.SERVICE_RESTART,
                    status=HealingStatus.FAILED,
                    source=service_name,
                    duration_seconds=duration,
                    details=result,
                    error=result.get("error", "Unknown error"),
                )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Service restart failed: {e}")

            return SelfHealingResult(
                action=HealingAction.SERVICE_RESTART,
                status=HealingStatus.FAILED,
                source=service_name,
                duration_seconds=duration,
                error=str(e),
            )

    async def _restart_docker(self, service_name: str) -> dict[str, Any]:
        """Restart using Docker Compose."""
        compose_file = self._compose_file or "docker-compose.yml"

        cmd = ["docker-compose", "-f", compose_file, "restart", service_name]

        logger.debug(f"Running: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            return {
                "success": True,
                "method": "docker-compose",
                "output": stdout.decode().strip(),
            }
        else:
            return {
                "success": False,
                "method": "docker-compose",
                "error": stderr.decode().strip() or "Unknown error",
            }

    async def _restart_systemd(self, service_name: str) -> dict[str, Any]:
        """Restart using systemd."""
        cmd = ["systemctl", "restart", service_name]

        logger.debug(f"Running: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            return {
                "success": True,
                "method": "systemd",
                "output": stdout.decode().strip(),
            }
        else:
            return {
                "success": False,
                "method": "systemd",
                "error": stderr.decode().strip() or "Unknown error",
            }


class DataBackfillTrigger:
    """Triggers data backfill for detected gaps."""

    def __init__(
        self,
        backfill_script_path: str | None = None,
        influxdb_client: Any | None = None,
    ):
        """Initialize data backfill trigger.

        Args:
            backfill_script_path: Path to backfill script
            influxdb_client: InfluxDB client for gap detection
        """
        self._script_path = backfill_script_path or "scripts/backfill_data.py"
        self._influxdb = influxdb_client

    async def trigger_backfill(
        self,
        source: str,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> SelfHealingResult:
        """Trigger data backfill.

        Args:
            source: Data source (exchange)
            symbol: Trading symbol
            start_time: Gap start time
            end_time: Gap end time

        Returns:
            Self-healing result
        """
        start = time.time()

        logger.info(
            f"Triggering backfill for {source}/{symbol}: "
            f"{start_time.isoformat()} to {end_time.isoformat()}"
        )

        try:
            # Check if backfill script exists
            if not os.path.exists(self._script_path):
                return SelfHealingResult(
                    action=HealingAction.DATA_BACKFILL,
                    status=HealingStatus.FAILED,
                    source=f"{source}/{symbol}",
                    duration_seconds=time.time() - start,
                    error=f"Backfill script not found: {self._script_path}",
                )

            # Run backfill script
            cmd = [
                "python3",
                self._script_path,
                "--source",
                source,
                "--symbol",
                symbol,
                "--start",
                start_time.isoformat(),
                "--end",
                end_time.isoformat(),
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()
            duration = time.time() - start

            if proc.returncode == 0:
                return SelfHealingResult(
                    action=HealingAction.DATA_BACKFILL,
                    status=HealingStatus.SUCCEEDED,
                    source=f"{source}/{symbol}",
                    duration_seconds=duration,
                    details={
                        "stdout": stdout.decode().strip(),
                        "records_backfilled": self._parse_backfill_count(
                            stdout.decode()
                        ),
                    },
                )
            else:
                return SelfHealingResult(
                    action=HealingAction.DATA_BACKFILL,
                    status=HealingStatus.FAILED,
                    source=f"{source}/{symbol}",
                    duration_seconds=duration,
                    error=stderr.decode().strip(),
                )

        except Exception as e:
            duration = time.time() - start
            logger.error(f"Data backfill failed: {e}")

            return SelfHealingResult(
                action=HealingAction.DATA_BACKFILL,
                status=HealingStatus.FAILED,
                source=f"{source}/{symbol}",
                duration_seconds=duration,
                error=str(e),
            )

    def _parse_backfill_count(self, output: str) -> int:
        """Parse number of records backfilled from output."""
        # Look for patterns like "Backfilled 1234 records" or "Inserted: 1234"
        import re

        patterns = [
            r"Backfilled\s+(\d+)\s+records",
            r"Inserted:\s*(\d+)",
            r"(\d+)\s+records?\s+(?:inserted|backfilled)",
        ]

        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return 0


class DeploymentRollback:
    """Handles automatic deployment rollback."""

    def __init__(
        self,
        deployment_tracker: Any | None = None,
        rollback_script: str | None = None,
    ):
        """Initialize deployment rollback.

        Args:
            deployment_tracker: Tracker for deployment health
            rollback_script: Path to rollback script
        """
        self._tracker = deployment_tracker
        self._rollback_script = rollback_script or "scripts/ops/rollback_deployment.sh"
        self._deployments: dict[str, DeploymentHealth] = {}

    def register_deployment(
        self,
        deployment_id: str,
        version: str,
    ) -> DeploymentHealth:
        """Register a new deployment for tracking.

        Args:
            deployment_id: Unique deployment ID
            version: Deployed version

        Returns:
            Deployment health tracker
        """
        deployment = DeploymentHealth(
            deployment_id=deployment_id,
            version=version,
            deployed_at=datetime.now(UTC),
        )
        self._deployments[deployment_id] = deployment

        logger.info(f"Registered deployment {deployment_id} (version {version})")

        return deployment

    def record_health_score(
        self,
        deployment_id: str,
        score: float,
    ) -> None:
        """Record a health score sample.

        Args:
            deployment_id: Deployment to record for
            score: Health score (0-100)
        """
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            logger.warning(f"Unknown deployment: {deployment_id}")
            return

        now = datetime.now(UTC)
        deployment.health_scores.append((now, score))

        if score >= 50:
            deployment.last_healthy_at = now

        # Keep only last 100 samples
        if len(deployment.health_scores) > 100:
            deployment.health_scores = deployment.health_scores[-100:]

        logger.debug(f"Deployment {deployment_id} health score: {score:.1f}")

    def check_rollback_needed(self, deployment_id: str) -> bool:
        """Check if deployment needs rollback.

        Args:
            deployment_id: Deployment to check

        Returns:
            True if rollback needed
        """
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False

        return deployment.needs_rollback

    async def rollback(self, deployment_id: str) -> SelfHealingResult:
        """Perform rollback of a deployment.

        Args:
            deployment_id: Deployment to rollback

        Returns:
            Self-healing result
        """
        start_time = time.time()

        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return SelfHealingResult(
                action=HealingAction.DEPLOYMENT_ROLLBACK,
                status=HealingStatus.FAILED,
                source=deployment_id,
                duration_seconds=time.time() - start_time,
                error="Deployment not found",
            )

        logger.critical(
            f"Initiating rollback for deployment {deployment_id} "
            f"(version {deployment.version})"
        )

        try:
            # Check if rollback script exists
            if not os.path.exists(self._rollback_script):
                return SelfHealingResult(
                    action=HealingAction.DEPLOYMENT_ROLLBACK,
                    status=HealingStatus.FAILED,
                    source=deployment_id,
                    duration_seconds=time.time() - start_time,
                    error=f"Rollback script not found: {self._rollback_script}",
                )

            # Run rollback script
            cmd = [
                "bash",
                self._rollback_script,
                deployment_id,
                deployment.version,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()
            duration = time.time() - start_time

            if proc.returncode == 0:
                logger.info(f"Rollback succeeded for {deployment_id}")

                return SelfHealingResult(
                    action=HealingAction.DEPLOYMENT_ROLLBACK,
                    status=HealingStatus.SUCCEEDED,
                    source=deployment_id,
                    duration_seconds=duration,
                    details={
                        "version": deployment.version,
                        "stdout": stdout.decode().strip(),
                    },
                )
            else:
                logger.error(f"Rollback failed for {deployment_id}")

                return SelfHealingResult(
                    action=HealingAction.DEPLOYMENT_ROLLBACK,
                    status=HealingStatus.FAILED,
                    source=deployment_id,
                    duration_seconds=duration,
                    error=stderr.decode().strip(),
                )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Rollback failed: {e}")

            return SelfHealingResult(
                action=HealingAction.DEPLOYMENT_ROLLBACK,
                status=HealingStatus.FAILED,
                source=deployment_id,
                duration_seconds=duration,
                error=str(e),
            )

    def get_deployment_health(self, deployment_id: str) -> DeploymentHealth | None:
        """Get deployment health tracker."""
        return self._deployments.get(deployment_id)


class SelfHealingEngine:
    """Main self-healing engine that coordinates all healing actions.

    Provides a unified interface for:
    - Redis reconnection with backoff
    - Exchange failover
    - Service restarts
    - Data backfill
    - Deployment rollback

    For PAPER-003-004: Event-Driven Self-Healing Automation
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        exchange_connectors: dict[str, Any] | None = None,
        influxdb_client: Any | None = None,
        docker_compose_file: str | None = None,
        use_systemd: bool = False,
    ):
        """Initialize self-healing engine.

        Args:
            redis_client: Redis client for reconnection
            exchange_connectors: Exchange connectors for failover
            influxdb_client: InfluxDB client for backfill
            docker_compose_file: Docker compose file path
            use_systemd: Use systemd for restarts
        """
        self._redis_reconnector = RedisReconnector(redis_client=redis_client)
        self._exchange_failover = ExchangeFailover(
            exchange_connectors=exchange_connectors or {}
        )
        self._service_restarter = ServiceRestarter(
            docker_compose_file=docker_compose_file,
            use_systemd=use_systemd,
        )
        self._backfill_trigger = DataBackfillTrigger(influxdb_client=influxdb_client)
        self._deployment_rollback = DeploymentRollback()

        self._healing_history: list[SelfHealingResult] = []
        self._max_history = 1000

        logger.info("SelfHealingEngine initialized")

    async def heal_redis(self) -> SelfHealingResult:
        """Heal Redis connection."""
        result = await self._redis_reconnector.reconnect()
        self._record_result(result)
        return result

    async def heal_exchange_failover(
        self,
        failed_exchange: str | None = None,
    ) -> SelfHealingResult:
        """Heal by failing over to backup exchange."""
        result = await self._exchange_failover.failover(failed_exchange)
        self._record_result(result)
        return result

    async def heal_service_restart(self, service_name: str) -> SelfHealingResult:
        """Heal by restarting service."""
        result = await self._service_restarter.restart(service_name)
        self._record_result(result)
        return result

    async def heal_data_backfill(
        self,
        source: str,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> SelfHealingResult:
        """Heal by triggering data backfill."""
        result = await self._backfill_trigger.trigger_backfill(
            source, symbol, start_time, end_time
        )
        self._record_result(result)
        return result

    async def heal_deployment_rollback(
        self,
        deployment_id: str,
    ) -> SelfHealingResult:
        """Heal by rolling back deployment."""
        result = await self._deployment_rollback.rollback(deployment_id)
        self._record_result(result)
        return result

    def register_deployment(
        self,
        deployment_id: str,
        version: str,
    ) -> DeploymentHealth:
        """Register a deployment for health tracking."""
        return self._deployment_rollback.register_deployment(deployment_id, version)

    def record_deployment_health(
        self,
        deployment_id: str,
        score: float,
    ) -> None:
        """Record deployment health score."""
        self._deployment_rollback.record_health_score(deployment_id, score)

    def check_deployment_rollback_needed(self, deployment_id: str) -> bool:
        """Check if deployment needs rollback."""
        return self._deployment_rollback.check_rollback_needed(deployment_id)

    def _record_result(self, result: SelfHealingResult) -> None:
        """Record healing result to history."""
        self._healing_history.append(result)

        if len(self._healing_history) > self._max_history:
            self._healing_history = self._healing_history[-self._max_history :]

    def get_healing_history(
        self,
        action: HealingAction | None = None,
        limit: int = 100,
    ) -> list[SelfHealingResult]:
        """Get healing history.

        Args:
            action: Filter by action type
            limit: Maximum results

        Returns:
            List of healing results
        """
        history = self._healing_history

        if action:
            history = [h for h in history if h.action == action]

        return history[-limit:]

    def get_healing_stats(self) -> dict[str, Any]:
        """Get healing statistics."""
        total = len(self._healing_history)

        by_action: dict[str, dict[str, int]] = {}
        for result in self._healing_history:
            action = result.action.value
            status = result.status.value

            if action not in by_action:
                by_action[action] = {}
            by_action[action][status] = by_action[action].get(status, 0) + 1

        return {
            "total_healing_actions": total,
            "by_action": by_action,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def execute_healing(
        self,
        action: HealingAction,
        **kwargs: Any,
    ) -> SelfHealingResult:
        """Execute a healing action by type.

        Args:
            action: Type of healing action
            **kwargs: Action-specific arguments

        Returns:
            Healing result
        """
        if action == HealingAction.REDIS_RECONNECT:
            return await self.heal_redis()

        elif action == HealingAction.EXCHANGE_FAILOVER:
            return await self.heal_exchange_failover(kwargs.get("failed_exchange"))

        elif action == HealingAction.SERVICE_RESTART:
            service = kwargs.get("service_name")
            if not service:
                return SelfHealingResult(
                    action=action,
                    status=HealingStatus.FAILED,
                    source="unknown",
                    error="service_name required",
                )
            return await self.heal_service_restart(service)

        elif action == HealingAction.DATA_BACKFILL:
            source = kwargs.get("source")
            symbol = kwargs.get("symbol")
            start = kwargs.get("start_time")
            end = kwargs.get("end_time")

            if not all([source, symbol, start, end]):
                return SelfHealingResult(
                    action=action,
                    status=HealingStatus.FAILED,
                    source=f"{source}/{symbol}",
                    error="source, symbol, start_time, end_time required",
                )
            return await self.heal_data_backfill(source, symbol, start, end)

        elif action == HealingAction.DEPLOYMENT_ROLLBACK:
            deployment_id = kwargs.get("deployment_id")
            if not deployment_id:
                return SelfHealingResult(
                    action=action,
                    status=HealingStatus.FAILED,
                    source="unknown",
                    error="deployment_id required",
                )
            return await self.heal_deployment_rollback(deployment_id)

        else:
            return SelfHealingResult(
                action=action,
                status=HealingStatus.FAILED,
                source="unknown",
                error=f"Unknown healing action: {action}",
            )
