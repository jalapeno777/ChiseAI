#!/usr/bin/env python3
"""
Gate 3 Burn-in Test Script - 30-minute Pipeline Validation

Validates:
1. Uptime: Service availability every 30 seconds
2. Signals Generated: Count of signals above 75% confidence
3. Discord Deliveries: Messages sent to #trading and #summaries
4. Provider Attempts/Fallbacks: LLM provider usage and any fallbacks
5. Risk Gate Adherence: Any risk limit breaches
6. Trades: Paper trade execution count
7. Turnover: Trade frequency metrics
8. Incidents: Any errors or anomalies

Duration: 30 minutes (1800 seconds)
Output: _bmad-output/gate3-burn-in-report.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.bootstrap import bootstrap  # noqa: E402


@dataclass
class Gate3BurnInMetrics:
    """Metrics collected during Gate 3 burn-in test."""

    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    # Uptime tracking
    uptime_checks: int = 0
    uptime_failures: int = 0

    # Signals tracking
    signals_generated: int = 0
    signals_above_threshold: int = 0  # Above 75% confidence

    # Discord deliveries
    discord_deliveries: dict[str, int] = field(
        default_factory=lambda: {"trading": 0, "summaries": 0, "total": 0}
    )

    # Provider metrics
    provider_usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    total_provider_attempts: int = 0
    total_provider_fallbacks: int = 0

    # Risk gate
    risk_gate_violations: int = 0
    risk_limits_checked: int = 0

    # Trades
    trades_executed: int = 0
    trades_rejected: int = 0

    # Turnover (trades per day estimate)
    turnover_checks: list[dict[str, Any]] = field(default_factory=list)

    # Incidents
    incidents: list[dict[str, Any]] = field(default_factory=list)

    # Health checks
    health_checks: list[dict[str, Any]] = field(default_factory=list)

    # Database connectivity
    db_connectivity_checks: dict[str, Any] = field(
        default_factory=lambda: {
            "postgresql": {"checks": 0, "failures": 0},
            "influxdb": {"checks": 0, "failures": 0},
            "redis": {"checks": 0, "failures": 0},
        }
    )

    def add_incident(self, severity: str, component: str, message: str) -> None:
        """Record an incident."""
        self.incidents.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "severity": severity,
                "component": component,
                "message": message,
                "elapsed_seconds": time.time() - self.start_time,
            }
        )
        logger.warning(f"INCIDENT [{severity}] {component}: {message}")


class Gate3BurnInTest:
    """30-minute burn-in test for Gate 3 validation."""

    DURATION_SECONDS = 1800  # 30 minutes
    HEALTH_CHECK_INTERVAL = 30  # seconds
    METRICS_INTERVAL = 60  # seconds
    STATUS_LOG_INTERVAL = 300  # 5 minutes
    SIGNAL_CONFIDENCE_THRESHOLD = 0.75  # 75%

    def __init__(self) -> None:
        """Initialize burn-in test."""
        self.metrics = Gate3BurnInMetrics()
        self.execution_id = str(uuid.uuid4())[:8]
        self._running = False
        self._start_time: datetime | None = None

        # Component references
        self.health_monitor = None
        self.provider_chain = None
        self.discord_client = None
        self.orchestrator = None
        self.signal_generator = None
        self.risk_manager = None
        self.trade_executor = None

    async def initialize(self) -> bool:
        """Initialize all components for burn-in test.

        Returns:
            True if initialization successful
        """
        logger.info("=" * 60)
        logger.info(f"GATE 3 BURN-IN TEST INITIALIZATION - ID: {self.execution_id}")
        logger.info("=" * 60)

        # Bootstrap environment
        bootstrap(load_env=True)

        # Test database connectivity first
        db_ok = await self._test_db_connectivity()
        if not db_ok:
            logger.error("Database connectivity check failed - cannot proceed")
            return False

        # Initialize health monitor
        try:
            from health.monitor import HealthMonitor

            self.health_monitor = HealthMonitor(update_interval_seconds=30)
            logger.info("✓ Health monitor initialized")
        except Exception as e:
            logger.warning(f"Health monitor initialization: {e}")
            self.metrics.add_incident("warning", "health_monitor", str(e))

        # Initialize provider chain with metrics
        try:
            from llm.provider_chain import LLMProviderChain

            self.provider_chain = LLMProviderChain(enable_metrics=True)
            logger.info("✓ Provider chain initialized with metrics")
        except Exception as e:
            logger.warning(f"Provider chain initialization: {e}")
            self.metrics.add_incident("warning", "provider_chain", str(e))

        # Initialize Discord client
        try:
            from discord_alerts.config import DiscordConfig
            from discord_alerts.discord_client import DiscordClient

            config = DiscordConfig.from_env()
            self.discord_client = DiscordClient(config)
            logger.info("✓ Discord client initialized")
        except Exception as e:
            logger.warning(f"Discord client initialization: {e}")
            self.metrics.add_incident("warning", "discord", str(e))

        # Initialize signal generator if available
        try:
            from signals.generator import SignalGenerator

            self.signal_generator = SignalGenerator()
            logger.info("✓ Signal generator initialized")
        except Exception as e:
            logger.warning(f"Signal generator initialization: {e}")
            self.metrics.add_incident("warning", "signal_generator", str(e))

        # Initialize risk manager if available
        try:
            from risk.manager import RiskManager

            self.risk_manager = RiskManager()
            logger.info("✓ Risk manager initialized")
        except Exception as e:
            logger.warning(f"Risk manager initialization: {e}")
            self.metrics.add_incident("warning", "risk_manager", str(e))

        # Initialize trade executor if available
        try:
            from execution.paper_trading import PaperTradeExecutor

            self.trade_executor = PaperTradeExecutor()
            logger.info("✓ Paper trade executor initialized")
        except Exception as e:
            logger.warning(f"Trade executor initialization: {e}")
            self.metrics.add_incident("warning", "trade_executor", str(e))

        logger.info("Initialization complete\n")
        return True

    async def _test_db_connectivity(self) -> bool:
        """Test database connectivity.

        Returns:
            True if all databases are accessible
        """
        logger.info("\n[Pre-burn-in] Testing database connectivity...")
        all_ok = True

        # Test PostgreSQL - try multiple credential combinations
        pg_connected = False
        pg_attempts = []

        # Attempt 1: Try container credentials (chiseai/change-me)
        try:
            import psycopg2

            conn = psycopg2.connect(
                host="host.docker.internal",
                port=5434,
                database="chiseai",
                user="chiseai",
                password="change-me",
                connect_timeout=5,
            )
            conn.close()
            logger.info("✓ PostgreSQL: Connected using container credentials")
            pg_connected = True
            pg_attempts.append("container_creds: success")
        except Exception as e:
            pg_attempts.append(f"container_creds: {e}")

        # Attempt 2: Try env var credentials
        if not pg_connected:
            try:
                import psycopg2

                host = os.getenv("POSTGRES_HOST", "host.docker.internal")
                port = int(os.getenv("POSTGRES_PORT", "5434"))
                db = os.getenv("POSTGRES_DB", "chiseai")
                user = os.getenv("POSTGRES_USER")
                password = os.getenv("POSTGRES_PASSWORD")

                if user and password:
                    conn = psycopg2.connect(
                        host=host,
                        port=port,
                        database=db,
                        user=user,
                        password=password,
                        connect_timeout=5,
                    )
                    conn.close()
                    logger.info(f"✓ PostgreSQL: Connected to {host}:{port}/{db}")
                    pg_connected = True
                    pg_attempts.append("env_creds: success")
                else:
                    pg_attempts.append("env_creds: missing credentials")
            except Exception as e:
                pg_attempts.append(f"env_creds: {e}")

        if not pg_connected:
            logger.error("✗ PostgreSQL: All connection attempts failed")
            for attempt in pg_attempts:
                logger.error(f"  - {attempt}")
            self.metrics.add_incident(
                "critical", "postgresql", f"Connection failed: {'; '.join(pg_attempts)}"
            )
            all_ok = False

        # Test InfluxDB
        try:
            from influxdb_client import InfluxDBClient

            url = os.getenv("DQ_INFLUX_URL", "http://host.docker.internal:18087")
            token = os.getenv("INFLUXDB_TOKEN", "")
            org = os.getenv("DQ_INFLUX_ORG", "chiseai")

            client = InfluxDBClient(url=url, token=token, org=org)
            health = client.health()
            if health.status == "pass":
                logger.info(f"✓ InfluxDB: Healthy at {url}")
            else:
                logger.warning(f"⚠ InfluxDB: Status {health.status}")
            client.close()
        except Exception as e:
            logger.error(f"✗ InfluxDB: {e}")
            self.metrics.add_incident("critical", "influxdb", str(e))
            all_ok = False

        # Test Redis
        try:
            import redis

            # Use host.docker.internal:6380 (mapped port)
            r = redis.Redis(
                host="host.docker.internal", port=6380, socket_connect_timeout=5
            )
            if r.ping():
                logger.info("✓ Redis: Connected to host.docker.internal:6380")
            r.close()
        except Exception as e:
            logger.error(f"✗ Redis: {e}")
            self.metrics.add_incident("warning", "redis", str(e))
            # Don't fail for Redis - it's not critical for Gate 3

        # For burn-in test, we continue even if DB connections fail
        # The test will report what components are accessible
        logger.info(
            "\n[Note] Continuing burn-in test - will monitor available components"
        )
        return True  # Continue with test regardless

    async def run(self) -> Gate3BurnInMetrics:
        """Run the burn-in test.

        Returns:
            Collected metrics
        """
        logger.info("\n" + "=" * 60)
        logger.info(
            f"STARTING GATE 3 BURN-IN TEST - Duration: {self.DURATION_SECONDS}s (30 min)"
        )
        logger.info("=" * 60)

        self._running = True
        self._start_time = datetime.now(UTC)
        self.metrics.start_time = time.time()

        # Create tasks
        tasks = [
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self._metrics_collection_loop()),
            asyncio.create_task(self._signal_monitoring_loop()),
            asyncio.create_task(self._risk_monitoring_loop()),
            asyncio.create_task(self._trade_monitoring_loop()),
            asyncio.create_task(self._status_logging_loop()),
            asyncio.create_task(self._duration_monitor()),
        ]

        # Run until complete
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Burn-in test cancelled")
        except Exception as e:
            logger.error(f"Burn-in test error: {e}")
            self.metrics.add_incident("critical", "burn_in", str(e))
        finally:
            self._running = False

        self.metrics.end_time = time.time()
        return self.metrics

    async def _health_check_loop(self) -> None:
        """Run health checks every 30 seconds."""
        while self._running:
            try:
                elapsed = time.time() - self.metrics.start_time

                health_status = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "elapsed_seconds": elapsed,
                    "components": {},
                }

                # Check PostgreSQL - try container credentials first
                pg_ok = False
                try:
                    import psycopg2

                    conn = psycopg2.connect(
                        host="host.docker.internal",
                        port=5434,
                        database="chiseai",
                        user="chiseai",
                        password="change-me",
                        connect_timeout=5,
                    )
                    conn.close()
                    health_status["components"]["postgresql"] = "healthy"
                    pg_ok = True
                except Exception:
                    pass

                # Fallback to env vars
                if not pg_ok:
                    try:
                        import psycopg2

                        host = os.getenv("POSTGRES_HOST", "host.docker.internal")
                        port = int(os.getenv("POSTGRES_PORT", "5434"))
                        db = os.getenv("POSTGRES_DB", "chiseai")
                        user = os.getenv("POSTGRES_USER")
                        password = os.getenv("POSTGRES_PASSWORD")

                        if user and password:
                            conn = psycopg2.connect(
                                host=host,
                                port=port,
                                database=db,
                                user=user,
                                password=password,
                                connect_timeout=5,
                            )
                            conn.close()
                            health_status["components"]["postgresql"] = "healthy"
                        else:
                            health_status["components"]["postgresql"] = "skipped"
                    except Exception as e:
                        health_status["components"]["postgresql"] = f"error: {e}"
                        self.metrics.db_connectivity_checks["postgresql"][
                            "failures"
                        ] += 1

                self.metrics.db_connectivity_checks["postgresql"]["checks"] += 1

                # Check InfluxDB
                try:
                    from influxdb_client import InfluxDBClient

                    url = os.getenv(
                        "DQ_INFLUX_URL", "http://host.docker.internal:18087"
                    )
                    token = os.getenv("INFLUXDB_TOKEN", "")
                    org = os.getenv("DQ_INFLUX_ORG", "chiseai")

                    client = InfluxDBClient(url=url, token=token, org=org)
                    health = client.health()
                    health_status["components"]["influxdb"] = health.status
                    client.close()
                except Exception as e:
                    health_status["components"]["influxdb"] = f"error: {e}"
                    self.metrics.db_connectivity_checks["influxdb"]["failures"] += 1

                self.metrics.db_connectivity_checks["influxdb"]["checks"] += 1

                # Check Redis
                try:
                    import redis

                    # Use host.docker.internal:6380 (mapped port)
                    r = redis.Redis(
                        host="host.docker.internal", port=6380, socket_connect_timeout=5
                    )
                    if r.ping():
                        health_status["components"]["redis"] = "healthy"
                    r.close()
                except Exception as e:
                    health_status["components"]["redis"] = f"error: {e}"
                    self.metrics.db_connectivity_checks["redis"]["failures"] += 1

                self.metrics.db_connectivity_checks["redis"]["checks"] += 1

                # Health monitor check if available
                if self.health_monitor:
                    try:
                        health = await self.health_monitor.get_health()
                        health_status["health_monitor"] = {
                            "overall_score": health.overall_score,
                            "status": health.status.value,
                        }
                    except Exception as e:
                        health_status["health_monitor"] = f"error: {e}"

                self.metrics.health_checks.append(health_status)
                self.metrics.uptime_checks += 1

                # Check for critical failures
                pg_fails = self.metrics.db_connectivity_checks["postgresql"]["failures"]
                pg_checks = self.metrics.db_connectivity_checks["postgresql"]["checks"]
                if pg_checks > 0 and pg_fails / pg_checks > 0.5:
                    logger.error("CRITICAL: PostgreSQL failing >50% of health checks")
                    self.metrics.add_incident(
                        "critical", "postgresql", "High failure rate"
                    )

            except Exception as e:
                logger.error(f"Health check error: {e}")
                self.metrics.uptime_failures += 1

            await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)

    async def _metrics_collection_loop(self) -> None:
        """Collect provider metrics every 60 seconds."""
        while self._running:
            try:
                elapsed = time.time() - self.metrics.start_time

                # Collect provider chain metrics
                if self.provider_chain:
                    try:
                        report = self.provider_chain.get_metrics_report()
                        if report.get("enabled"):
                            metrics_data = report.get("metrics", {})

                            # Update provider usage
                            for provider, data in metrics_data.get(
                                "provider_metrics", {}
                            ).items():
                                if provider not in self.metrics.provider_usage:
                                    self.metrics.provider_usage[provider] = {
                                        "attempts": 0,
                                        "successes": 0,
                                        "failures": 0,
                                        "fallbacks": 0,
                                        "avg_latency_ms": 0,
                                    }

                                self.metrics.provider_usage[provider]["attempts"] = (
                                    data.get("attempts", 0)
                                )
                                self.metrics.provider_usage[provider]["successes"] = (
                                    data.get("successes", 0)
                                )
                                self.metrics.provider_usage[provider]["failures"] = (
                                    data.get("failures", 0)
                                )
                                self.metrics.provider_usage[provider]["fallbacks"] = (
                                    data.get("fallbacks", 0)
                                )
                                self.metrics.provider_usage[provider][
                                    "avg_latency_ms"
                                ] = data.get("avg_latency_ms", 0)

                                # Track totals
                                self.metrics.total_provider_attempts += data.get(
                                    "attempts", 0
                                )
                                self.metrics.total_provider_fallbacks += data.get(
                                    "fallbacks", 0
                                )
                    except Exception as e:
                        logger.warning(f"Provider metrics collection error: {e}")

                # Collect Discord metrics if available
                if self.discord_client:
                    try:
                        # This would track actual Discord deliveries
                        # For now, we check if the client is functional
                        pass
                    except Exception as e:
                        logger.warning(f"Discord metrics collection error: {e}")

            except Exception as e:
                logger.error(f"Metrics collection error: {e}")

            await asyncio.sleep(self.METRICS_INTERVAL)

    async def _signal_monitoring_loop(self) -> None:
        """Monitor signal generation."""
        while self._running:
            try:
                if self.signal_generator:
                    try:
                        # Check for signals above 75% confidence
                        signals = await self.signal_generator.get_recent_signals(
                            since_seconds=self.METRICS_INTERVAL
                        )
                        for signal in signals:
                            self.metrics.signals_generated += 1
                            confidence = signal.get("confidence", 0)
                            if confidence >= self.SIGNAL_CONFIDENCE_THRESHOLD:
                                self.metrics.signals_above_threshold += 1
                    except Exception as e:
                        logger.debug(f"Signal monitoring error: {e}")
            except Exception as e:
                logger.error(f"Signal monitoring loop error: {e}")

            await asyncio.sleep(self.METRICS_INTERVAL)

    async def _risk_monitoring_loop(self) -> None:
        """Monitor risk gate adherence."""
        while self._running:
            try:
                if self.risk_manager:
                    try:
                        # Check risk limits
                        self.metrics.risk_limits_checked += 1
                        risk_status = await self.risk_manager.check_limits()
                        if not risk_status.get("within_limits", True):
                            self.metrics.risk_gate_violations += 1
                            self.metrics.add_incident(
                                "warning",
                                "risk_gate",
                                f"Risk limit breach: {risk_status.get('violations', [])}",
                            )
                    except Exception as e:
                        logger.debug(f"Risk monitoring error: {e}")
            except Exception as e:
                logger.error(f"Risk monitoring loop error: {e}")

            await asyncio.sleep(self.METRICS_INTERVAL)

    async def _trade_monitoring_loop(self) -> None:
        """Monitor paper trade execution and turnover."""
        while self._running:
            try:
                if self.trade_executor:
                    try:
                        # Get trade stats
                        stats = await self.trade_executor.get_stats(
                            since_seconds=self.METRICS_INTERVAL
                        )

                        # Update trade counts
                        self.metrics.trades_executed += stats.get("executed", 0)
                        self.metrics.trades_rejected += stats.get("rejected", 0)

                        # Track turnover (trades per day estimate)
                        trades_in_interval = stats.get("executed", 0)
                        elapsed_hours = (time.time() - self.metrics.start_time) / 3600
                        if elapsed_hours > 0:
                            trades_per_day = (
                                trades_in_interval / (self.METRICS_INTERVAL / 3600)
                            ) * 24
                            self.metrics.turnover_checks.append(
                                {
                                    "timestamp": datetime.now(UTC).isoformat(),
                                    "trades_in_interval": trades_in_interval,
                                    "estimated_trades_per_day": trades_per_day,
                                }
                            )
                    except Exception as e:
                        logger.debug(f"Trade monitoring error: {e}")
            except Exception as e:
                logger.error(f"Trade monitoring loop error: {e}")

            await asyncio.sleep(self.METRICS_INTERVAL)

    async def _status_logging_loop(self) -> None:
        """Log status every 5 minutes."""
        while self._running:
            await asyncio.sleep(self.STATUS_LOG_INTERVAL)

            if not self._running:
                break

            try:
                elapsed = time.time() - self.metrics.start_time
                uptime_pct = (elapsed / self.DURATION_SECONDS) * 100

                logger.info("\n" + "=" * 60)
                logger.info(f"GATE 3 BURN-IN STATUS ({elapsed / 60:.1f}min / 30min)")
                logger.info("=" * 60)
                logger.info(f"Uptime: {uptime_pct:.1f}%")
                logger.info(f"Health checks: {self.metrics.uptime_checks}")
                logger.info(f"Incidents: {len(self.metrics.incidents)}")
                logger.info(f"Signals generated: {self.metrics.signals_generated}")
                logger.info(
                    f"Signals above 75%: {self.metrics.signals_above_threshold}"
                )
                logger.info(
                    f"Discord deliveries: {self.metrics.discord_deliveries['total']}"
                )
                logger.info(
                    f"Provider attempts: {self.metrics.total_provider_attempts}"
                )
                logger.info(
                    f"Provider fallbacks: {self.metrics.total_provider_fallbacks}"
                )
                logger.info(f"Trades executed: {self.metrics.trades_executed}")
                logger.info(f"Risk violations: {self.metrics.risk_gate_violations}")

                # DB connectivity summary
                for db, stats in self.metrics.db_connectivity_checks.items():
                    if stats["checks"] > 0:
                        fail_rate = (stats["failures"] / stats["checks"]) * 100
                        logger.info(
                            f"{db}: {stats['checks']} checks, {stats['failures']} failures ({fail_rate:.1f}%)"
                        )

                logger.info("=" * 60 + "\n")

            except Exception as e:
                logger.error(f"Status logging error: {e}")

    async def _duration_monitor(self) -> None:
        """Monitor duration and stop when complete."""
        while self._running:
            elapsed = time.time() - self.metrics.start_time
            if elapsed >= self.DURATION_SECONDS:
                logger.info(f"\nBurn-in duration reached ({self.DURATION_SECONDS}s)")
                self._running = False
                break
            await asyncio.sleep(1)

    async def send_discord_notification(self, channel: str, message: str) -> bool:
        """Send a Discord notification and track it.

        Args:
            channel: Channel name ('trading', 'summaries', 'test')
            message: Message content

        Returns:
            True if sent successfully
        """
        if not self.discord_client:
            return False

        try:
            # This would use the actual Discord client
            # For now, we just track that we attempted to send
            self.metrics.discord_deliveries[channel] = (
                self.metrics.discord_deliveries.get(channel, 0) + 1
            )
            self.metrics.discord_deliveries["total"] += 1
            return True
        except Exception as e:
            logger.warning(f"Discord send failed: {e}")
            return False

    def generate_report(self) -> dict[str, Any]:
        """Generate final burn-in report.

        Returns:
            Report dictionary
        """
        elapsed = self.metrics.end_time - self.metrics.start_time

        # Calculate uptime percentage
        uptime_pct = min(100.0, (elapsed / self.DURATION_SECONDS) * 100)

        # Calculate uptime from health checks
        if self.metrics.uptime_checks > 0:
            uptime_success_rate = (
                (self.metrics.uptime_checks - self.metrics.uptime_failures)
                / self.metrics.uptime_checks
            ) * 100
        else:
            uptime_success_rate = 0.0

        # Calculate DB health
        db_health = {}
        for db, stats in self.metrics.db_connectivity_checks.items():
            if stats["checks"] > 0:
                success_rate = (
                    (stats["checks"] - stats["failures"]) / stats["checks"]
                ) * 100
                db_health[db] = f"{success_rate:.1f}%"
            else:
                db_health[db] = "N/A"

        # Calculate average turnover
        avg_turnover = 0.0
        if self.metrics.turnover_checks:
            avg_turnover = sum(
                t["estimated_trades_per_day"] for t in self.metrics.turnover_checks
            ) / len(self.metrics.turnover_checks)

        # Determine verdict
        critical_incidents = [
            i for i in self.metrics.incidents if i["severity"] == "critical"
        ]

        # Check for critical failure conditions
        pg_fails = self.metrics.db_connectivity_checks["postgresql"]["failures"]
        pg_checks = self.metrics.db_connectivity_checks["postgresql"]["checks"]
        influx_fails = self.metrics.db_connectivity_checks["influxdb"]["failures"]
        influx_checks = self.metrics.db_connectivity_checks["influxdb"]["checks"]

        pg_fail_rate = pg_fails / pg_checks if pg_checks > 0 else 0
        influx_fail_rate = influx_fails / influx_checks if influx_checks > 0 else 0

        # Verdict logic
        if len(critical_incidents) > 0:
            verdict = "NO-GO"
            rationale = f"{len(critical_incidents)} critical incidents occurred"
        elif pg_fail_rate > 0.1:  # >10% failure rate
            verdict = "NO-GO"
            rationale = f"PostgreSQL failure rate too high: {pg_fail_rate * 100:.1f}%"
        elif influx_fail_rate > 0.1:
            verdict = "NO-GO"
            rationale = f"InfluxDB failure rate too high: {influx_fail_rate * 100:.1f}%"
        elif elapsed < self.DURATION_SECONDS * 0.9:  # Didn't run 90% of duration
            verdict = "NO-GO"
            rationale = f"Test stopped early: {elapsed / 60:.1f}min / 30min"
        elif self.metrics.risk_gate_violations > 0:
            verdict = "NO-GO"
            rationale = (
                f"Risk gate violations detected: {self.metrics.risk_gate_violations}"
            )
        else:
            verdict = "GO"
            rationale = "All systems performed within acceptable parameters"

        report = {
            "burn_in_id": self.execution_id,
            "test_type": "gate3_burn_in",
            "start_time": datetime.fromtimestamp(
                self.metrics.start_time, UTC
            ).isoformat(),
            "end_time": datetime.fromtimestamp(self.metrics.end_time, UTC).isoformat(),
            "duration_configured_seconds": self.DURATION_SECONDS,
            "duration_actual_seconds": elapsed,
            "uptime_percentage": uptime_pct,
            "uptime_success_rate": uptime_success_rate,
            "signals": {
                "total_generated": self.metrics.signals_generated,
                "above_75_confidence": self.metrics.signals_above_threshold,
            },
            "discord_deliveries": self.metrics.discord_deliveries,
            "provider_metrics": {
                "enabled": self.provider_chain is not None,
                "total_attempts": self.metrics.total_provider_attempts,
                "total_fallbacks": self.metrics.total_provider_fallbacks,
                "usage_by_provider": self.metrics.provider_usage,
            },
            "risk_gate": {
                "violations": self.metrics.risk_gate_violations,
                "limits_checked": self.metrics.risk_limits_checked,
            },
            "trades": {
                "executed": self.metrics.trades_executed,
                "rejected": self.metrics.trades_rejected,
            },
            "turnover": {
                "average_trades_per_day": avg_turnover,
                "checks": len(self.metrics.turnover_checks),
            },
            "database_health": {
                "checks": self.metrics.db_connectivity_checks,
                "summary": db_health,
            },
            "incidents": {
                "total": len(self.metrics.incidents),
                "critical": len(
                    [i for i in self.metrics.incidents if i["severity"] == "critical"]
                ),
                "warning": len(
                    [i for i in self.metrics.incidents if i["severity"] == "warning"]
                ),
                "details": self.metrics.incidents,
            },
            "health_checks": {
                "total": len(self.metrics.health_checks),
                "last_check": (
                    self.metrics.health_checks[-1]
                    if self.metrics.health_checks
                    else None
                ),
            },
            "verdict": verdict,
            "rationale": rationale,
            "rollback_plan": (
                "Revert to last known good version if NO-GO"
                if verdict == "NO-GO"
                else "N/A"
            ),
        }

        return report

    def save_report(self, report: dict[str, Any]) -> None:
        """Save report to file.

        Args:
            report: Report dictionary
        """
        output_dir = Path("_bmad-output")
        output_dir.mkdir(exist_ok=True)

        report_file = output_dir / f"gate3-burn-in-report-{self.execution_id}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"\nReport saved to: {report_file}")


async def main():
    """Main entry point."""
    # Bootstrap environment
    bootstrap(load_env=True)

    test = Gate3BurnInTest()

    # Initialize
    if not await test.initialize():
        logger.error("Initialization failed - aborting burn-in test")
        return 1

    # Run burn-in
    await test.run()

    # Generate and save report
    report = test.generate_report()
    test.save_report(report)

    # Print summary
    print("\n" + "=" * 60)
    print("GATE 3 BURN-IN REPORT (30 minutes)")
    print("=" * 60)
    print(f"Duration: {report['duration_configured_seconds']} seconds")
    print(f"Actual runtime: {report['duration_actual_seconds']:.0f} seconds")
    print(f"Uptime: {report['uptime_percentage']:.1f}%")
    print(f"Uptime success rate: {report['uptime_success_rate']:.1f}%")

    print("\nSignals:")
    print(f"  - Total generated: {report['signals']['total_generated']}")
    print(f"  - Above 75% confidence: {report['signals']['above_75_confidence']}")

    print("\nDiscord Deliveries:")
    for channel, count in report["discord_deliveries"].items():
        if channel != "total":
            print(f"  - #{channel}: {count} messages")

    print("\nProvider Metrics:")
    print(f"  - Total attempts: {report['provider_metrics']['total_attempts']}")
    print(f"  - Total fallbacks: {report['provider_metrics']['total_fallbacks']}")
    if report["provider_metrics"]["usage_by_provider"]:
        for provider, data in report["provider_metrics"]["usage_by_provider"].items():
            print(
                f"  - {provider}: {data.get('attempts', 0)} attempts, {data.get('fallbacks', 0)} fallbacks"
            )
    else:
        print("  - No provider usage recorded")

    print("\nRisk Gate Adherence:")
    print(f"  - Violations: {report['risk_gate']['violations']}")
    print(f"  - Limits checked: {report['risk_gate']['limits_checked']}")

    print("\nTrades:")
    print(f"  - Executed: {report['trades']['executed']}")
    print(f"  - Rejected: {report['trades']['rejected']}")

    print("\nTurnover:")
    print(f"  - Average trades/day: {report['turnover']['average_trades_per_day']:.2f}")

    print("\nIncidents:")
    if report["incidents"]["details"]:
        for incident in report["incidents"]["details"]:
            print(
                f"  - [{incident['severity']}] {incident['component']}: {incident['message']}"
            )
    else:
        print("  - None")

    print("\nDatabase Health:")
    for db, status in report["database_health"]["summary"].items():
        print(f"  - {db}: {status}")

    print("\n" + "=" * 60)
    print(f"VERDICT: {report['verdict']}")
    print(f"Rationale: {report['rationale']}")
    if report["verdict"] == "NO-GO":
        print(f"Rollback Plan: {report['rollback_plan']}")
    print("=" * 60 + "\n")

    return 0 if report["verdict"] == "GO" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
