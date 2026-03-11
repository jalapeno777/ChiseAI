"""Gate validation implementation for G1-G8 checkpoint gates.

This module provides the GateChecker class that validates all 8 governance gates:
- G1: Scheduler Continuity
- G2: Signal Cadence
- G3: Data Flow Movement
- G4: Kill Switch Active
- G5: Cron Job Cadence
- G6: Bybit Connectivity
- G7: Observability Health
- G8: End-to-End Pipeline
"""

from __future__ import annotations

import logging
import os
import socket
import ssl
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

import redis

logger = logging.getLogger(__name__)

# Add scripts/monitoring to path for cron_evidence import
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
MONITORING_DIR = os.path.join(SCRIPT_DIR, "scripts", "monitoring")
if MONITORING_DIR not in sys.path:
    sys.path.insert(0, MONITORING_DIR)


@dataclass
class GateResult:
    """Result of a single gate check."""

    gate: str
    status: str  # "✅ PASS", "❌ FAIL", "⚠️ CHECK", "🚨 ALERT", "❓ UNKNOWN"
    detail: str
    timestamp: datetime | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)


@dataclass
class GateSummary:
    """Summary of all gate checks."""

    results: list[GateResult]
    pass_count: int
    fail_count: int
    check_count: int
    timestamp: datetime

    @property
    def overall_status(self) -> str:
        """Determine overall status based on gate results."""
        if self.fail_count > 0:
            return "FAIL"
        elif self.check_count > 0:
            return "CHECK"
        return "PASS"


class GateChecker:
    """Validates G1-G8 governance checkpoint gates.

    This class implements all 8 checkpoint gates used to validate system
    health and readiness during trading operations.
    """

    # Gate status constants
    STATUS_PASS = "✅ PASS"
    STATUS_FAIL = "❌ FAIL"
    STATUS_CHECK = "⚠️ CHECK"
    STATUS_ALERT = "🚨 ALERT"
    STATUS_UNKNOWN = "❓ UNKNOWN"

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
    ):
        """Initialize the gate checker.

        Args:
            redis_client: Optional Redis client instance
            redis_host: Redis host (defaults to env or host.docker.internal)
            redis_port: Redis port (defaults to env or 6380)
        """
        self._redis = redis_client
        self._redis_host = redis_host or os.getenv(
            "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
        )
        self._redis_port = redis_port or int(
            os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380"))
        )

    def _get_redis(self) -> redis.Redis | None:
        """Get or create Redis connection."""
        if self._redis is not None:
            return self._redis

        try:
            self._redis = redis.Redis(
                host=self._redis_host,
                port=self._redis_port,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            return self._redis
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return None

    def check_g1_scheduler(self) -> GateResult:
        """G1: Scheduler Continuity - Check Redis heartbeat.

        Validates that the scheduler is running and reporting heartbeats
        within the expected interval (2 minutes).
        """
        r = self._get_redis()
        if not r:
            return GateResult(
                gate="G1",
                status=self.STATUS_FAIL,
                detail="Redis unavailable - cannot check scheduler",
            )

        try:
            heartbeat = r.hgetall("bmad:chiseai:scheduler:heartbeat")

            if not heartbeat:
                return GateResult(
                    gate="G1",
                    status=self.STATUS_FAIL,
                    detail="No scheduler heartbeat in Redis",
                )

            timestamp_str = heartbeat.get("timestamp", "")
            status = heartbeat.get("status", "unknown")
            uptime_seconds = heartbeat.get("uptime_seconds", "")

            if not timestamp_str:
                return GateResult(
                    gate="G1",
                    status=self.STATUS_FAIL,
                    detail="Invalid heartbeat data - no timestamp",
                )

            # Parse timestamp and check age
            last_heartbeat = datetime.fromisoformat(timestamp_str)
            now = datetime.now(UTC)
            age_seconds = (now - last_heartbeat).total_seconds()

            # Consider healthy if heartbeat within 2 minutes and status is running
            max_age = 120  # seconds

            if status != "running":
                return GateResult(
                    gate="G1",
                    status=self.STATUS_FAIL,
                    detail=f"Scheduler status: {status} (expected: running)",
                )

            if age_seconds > max_age:
                return GateResult(
                    gate="G1",
                    status=self.STATUS_CHECK,
                    detail=f"Heartbeat stale: {age_seconds:.0f}s old (max: {max_age}s)",
                )

            # Build detail message
            detail_parts = [f"Heartbeat {age_seconds:.0f}s ago"]
            if uptime_seconds:
                detail_parts.append(f"uptime: {int(uptime_seconds) // 60}m")

            return GateResult(
                gate="G1",
                status=self.STATUS_PASS,
                detail=", ".join(detail_parts),
            )

        except Exception as e:
            logger.error(f"Error checking G1: {e}")
            return GateResult(
                gate="G1",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )

    def check_g2_signal_cadence(self) -> GateResult:
        """G2: Signal Cadence - Check for active signal generation.

        Now uses pipeline liveness metrics to distinguish:
        - Healthy no-signal (attempts > 0, actionable = 0)
        - Stale pipeline (no attempts in 15m)
        """
        r = self._get_redis()
        if not r:
            return GateResult(
                gate="G2",
                status=self.STATUS_FAIL,
                detail="Redis unavailable - cannot check signals",
            )

        try:
            # Get liveness data from heartbeat
            heartbeat = r.hgetall("bmad:chiseai:scheduler:heartbeat")
            pipeline_status = heartbeat.get("pipeline_status", "unknown")
            signals_15m = int(heartbeat.get("signals_15m", "0"))
            actionable_15m = int(heartbeat.get("actionable_15m", "0"))
            backlog = int(heartbeat.get("consumer_backlog", "0"))

            if pipeline_status == "healthy":
                return GateResult(
                    gate="G2",
                    status=self.STATUS_PASS,
                    detail=f"Pipeline healthy: {signals_15m} attempts, {actionable_15m} actionable, {backlog} backlog",
                )
            elif pipeline_status == "stale":
                return GateResult(
                    gate="G2",
                    status=self.STATUS_FAIL,
                    detail=f"Pipeline stale: No signals in 15m, last age: {heartbeat.get('latest_signal_age_m', 'N/A')}m",
                )
            else:
                return GateResult(
                    gate="G2",
                    status=self.STATUS_CHECK,
                    detail=f"Pipeline status: {pipeline_status}, attempts: {signals_15m}",
                )
        except Exception as e:
            logger.error(f"Error checking G2: {e}")
            return GateResult(
                gate="G2",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )

    def check_g3_data_flow(self) -> GateResult:
        """G3: Data Flow Movement - Check outcomes recorded.

        Validates that data is flowing through the pipeline by checking
        the outcomes index.
        """
        r = self._get_redis()
        if not r:
            return GateResult(
                gate="G3",
                status=self.STATUS_FAIL,
                detail="Redis unavailable - cannot check data flow",
            )

        try:
            count = r.scard("bmad:chiseai:outcomes:index")
            if count and count > 0:
                return GateResult(
                    gate="G3",
                    status=self.STATUS_PASS,
                    detail=f"{count} outcomes recorded",
                )
            else:
                return GateResult(
                    gate="G3",
                    status=self.STATUS_CHECK,
                    detail="No outcomes found in Redis",
                )
        except Exception as e:
            logger.error(f"Error checking G3: {e}")
            return GateResult(
                gate="G3",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )

    def check_g4_kill_switch(self) -> GateResult:
        """G4: Kill Switch Active - Check kill switch status.

        Validates that the kill switch is armed and ready. Reports ALERT
        if the kill switch has been triggered.
        """
        r = self._get_redis()
        if not r:
            return GateResult(
                gate="G4",
                status=self.STATUS_FAIL,
                detail="Redis unavailable - cannot check kill switch",
            )

        try:
            enabled = r.hget("bmad:chiseai:kill_switch", "enabled")
            triggered = r.hget("bmad:chiseai:kill_switch", "triggered")

            if enabled == "1" and triggered == "0":
                return GateResult(
                    gate="G4",
                    status=self.STATUS_PASS,
                    detail="Kill switch armed and ready",
                )
            elif triggered == "1":
                return GateResult(
                    gate="G4",
                    status=self.STATUS_ALERT,
                    detail="KILL SWITCH TRIGGERED - Trading halted",
                )
            else:
                return GateResult(
                    gate="G4",
                    status=self.STATUS_CHECK,
                    detail="Kill switch not configured or disabled",
                )
        except Exception as e:
            logger.error(f"Error checking G4: {e}")
            return GateResult(
                gate="G4",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )

    def check_g5_cron_cadence(self) -> GateResult:
        """G5: Cron Job Cadence - Verify cron jobs are executing.

        Validates that all cron jobs are running on their expected cadence:
        - pager (5m = 300s)
        - signal-growth (30m = 1800s)
        - hourly-health (60m = 3600s)
        - checkpoint-audit (6h = 21600s)
        """
        r = self._get_redis()
        if not r:
            return GateResult(
                gate="G5",
                status=self.STATUS_FAIL,
                detail="Redis unavailable - cannot check cron cadence",
            )

        try:
            # Import cron evidence checker
            try:
                from cron_evidence import check_cron_cadence
            except ImportError:
                # Fallback if import fails
                return GateResult(
                    gate="G5",
                    status=self.STATUS_CHECK,
                    detail="Cron evidence module not available",
                )

            results = check_cron_cadence(r)

            if "error" in results:
                return GateResult(
                    gate="G5",
                    status=self.STATUS_FAIL,
                    detail=f"Cron cadence check failed: {results['error']}",
                )

            overall = results.get("overall_status", "UNKNOWN")
            jobs = results.get("jobs", {})

            # Build detail string
            job_details = []
            for job_name, job_data in jobs.items():
                status = job_data.get("status", "UNKNOWN")
                elapsed = job_data.get("elapsed_seconds")
                missed = job_data.get("missed_count", 0)

                if elapsed is not None:
                    if elapsed < 60:
                        time_str = f"{elapsed}s"
                    elif elapsed < 3600:
                        time_str = f"{elapsed // 60}m"
                    else:
                        time_str = f"{elapsed // 3600}h"

                    if missed > 0:
                        job_details.append(
                            f"{job_name}:{status}({time_str},missed={missed})"
                        )
                    else:
                        job_details.append(f"{job_name}:{status}({time_str})")
                else:
                    job_details.append(f"{job_name}:{status}(no data)")

            detail = (
                " | ".join(job_details) if job_details else "No cron data available"
            )

            # Map overall status to gate status
            if overall == "PASS":
                return GateResult(gate="G5", status=self.STATUS_PASS, detail=detail)
            elif overall == "CHECK":
                return GateResult(gate="G5", status=self.STATUS_CHECK, detail=detail)
            else:  # FAIL or UNKNOWN
                return GateResult(gate="G5", status=self.STATUS_FAIL, detail=detail)

        except Exception as e:
            logger.error(f"Error checking G5: {e}")
            return GateResult(
                gate="G5",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )

    def check_g6_bybit_connectivity(self) -> GateResult:
        """G6: Bybit Connectivity - Test API reachability.

        Performs a simple TCP connection test to Bybit API to verify
        connectivity.
        """
        try:
            # Simple TCP connection test to Bybit API
            host = "api.bybit.com"
            port = 443
            timeout = 5

            context = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    # Send a simple HTTPS request
                    request = (
                        f"GET /v5/market/time HTTP/1.1\r\n"
                        f"Host: {host}\r\n"
                        f"Connection: close\r\n\r\n"
                    )
                    ssock.send(request.encode())
                    response = ssock.recv(1024).decode()
                    if "200 OK" in response or "HTTP/1.1" in response:
                        return GateResult(
                            gate="G6",
                            status=self.STATUS_PASS,
                            detail="Bybit API reachable",
                        )
                    else:
                        return GateResult(
                            gate="G6",
                            status=self.STATUS_CHECK,
                            detail="API responded unexpectedly",
                        )
        except TimeoutError:
            return GateResult(
                gate="G6",
                status=self.STATUS_FAIL,
                detail="Connection timeout to Bybit API",
            )
        except socket.gaierror as e:
            return GateResult(
                gate="G6",
                status=self.STATUS_FAIL,
                detail=f"DNS resolution failed: {str(e)[:50]}",
            )
        except Exception as e:
            logger.error(f"Error checking G6: {e}")
            return GateResult(
                gate="G6",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:50]}",
            )

    def check_g7_observability(self) -> GateResult:
        """G7: Observability Health - Check Redis health.

        Validates that Redis is healthy and responsive with good uptime.
        """
        r = self._get_redis()
        if not r:
            return GateResult(
                gate="G7",
                status=self.STATUS_FAIL,
                detail="Redis unavailable",
            )

        try:
            ping = r.ping()
            keys = r.dbsize()
            info = r.info("server")
            uptime = info.get("uptime_in_seconds", 0)

            if ping and uptime > 3600:
                return GateResult(
                    gate="G7",
                    status=self.STATUS_PASS,
                    detail=f"Redis OK, {keys} keys, {uptime // 3600}h uptime",
                )
            elif ping:
                return GateResult(
                    gate="G7",
                    status=self.STATUS_CHECK,
                    detail=f"Redis OK but uptime <1h ({uptime // 60}m)",
                )
            else:
                return GateResult(
                    gate="G7",
                    status=self.STATUS_FAIL,
                    detail="Redis ping failed",
                )
        except Exception as e:
            logger.error(f"Error checking G7: {e}")
            return GateResult(
                gate="G7",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )

    def check_g8_pipeline(self) -> GateResult:
        """G8: End-to-End Pipeline - Burn-in verdict integration.

        Reads burn-in verdict from Redis string key bmad:chiseai:burnin:verdict.
        Verdict values: "GO" or "NO-GO".
        Verdict is authoritative for G8 status.
        """
        r = self._get_redis()
        if not r:
            return GateResult(
                gate="G8",
                status=self.STATUS_FAIL,
                detail="Redis unavailable - cannot check pipeline",
            )

        try:
            # Read burn-in verdict from Redis (stored as STRING, not hash)
            verdict = r.get("bmad:chiseai:burnin:verdict")

            # Get pipeline counts for context
            signals = len(r.keys("bmad:chiseai:signals:*"))
            outcomes = r.scard("bmad:chiseai:outcomes:index")

            if verdict is None:
                # No verdict found - burn-in not completed
                return GateResult(
                    gate="G8",
                    status=self.STATUS_UNKNOWN,
                    detail="No burn-in verdict found - burn-in not completed",
                )
            elif verdict == "GO":
                # Burn-in passed - pipeline approved
                return GateResult(
                    gate="G8",
                    status=self.STATUS_PASS,
                    detail=f"Burn-in verdict: GO | Pipeline: {signals} signals → {outcomes} outcomes",
                )
            elif verdict == "NO-GO":
                # Burn-in failed - pipeline halted
                return GateResult(
                    gate="G8",
                    status=self.STATUS_FAIL,
                    detail="Burn-in verdict: NO-GO | Pipeline halted",
                )
            else:
                # Unexpected verdict value
                return GateResult(
                    gate="G8",
                    status=self.STATUS_CHECK,
                    detail=f"Unexpected verdict: '{verdict}' | Pipeline: {signals} signals → {outcomes} outcomes",
                )
        except Exception as e:
            logger.error(f"Error checking G8: {e}")
            return GateResult(
                gate="G8",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )

    def run_all_checks(self) -> GateSummary:
        """Run all G1-G8 checks and return summary.

        Returns:
            GateSummary with all results and counts
        """
        checks = [
            self.check_g1_scheduler(),
            self.check_g2_signal_cadence(),
            self.check_g3_data_flow(),
            self.check_g4_kill_switch(),
            self.check_g5_cron_cadence(),
            self.check_g6_bybit_connectivity(),
            self.check_g7_observability(),
            self.check_g8_pipeline(),
        ]

        pass_count = sum(1 for c in checks if self.STATUS_PASS in c.status)
        fail_count = sum(1 for c in checks if self.STATUS_FAIL in c.status)
        check_count = sum(1 for c in checks if self.STATUS_CHECK in c.status)

        return GateSummary(
            results=checks,
            pass_count=pass_count,
            fail_count=fail_count,
            check_count=check_count,
            timestamp=datetime.now(UTC),
        )

    def get_failing_gates(self, summary: GateSummary | None = None) -> list[str]:
        """Get list of failing gate names.

        Args:
            summary: Optional pre-computed summary. If None, runs all checks.

        Returns:
            List of gate names that are failing
        """
        if summary is None:
            summary = self.run_all_checks()

        return [r.gate for r in summary.results if self.STATUS_FAIL in r.status]

    def is_healthy(self, summary: GateSummary | None = None) -> bool:
        """Check if all gates are passing.

        Args:
            summary: Optional pre-computed summary. If None, runs all checks.

        Returns:
            True if no gates are failing, False otherwise
        """
        if summary is None:
            summary = self.run_all_checks()

        return summary.fail_count == 0
