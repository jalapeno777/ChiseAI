"""Gate validation implementation for G1-G12 checkpoint gates.

This module provides the GateChecker class that validates all 12 governance gates:
- G1: Scheduler Continuity
- G2: Signal Cadence
- G3: Data Flow Movement
- G4: Kill Switch Active
- G5: Cron Job Cadence
- G6: Bybit Connectivity
- G7: Observability Health
- G8: End-to-End Pipeline
- G9: Metric Integrity
- G10: Chain Integrity
- G11: Provenance (signal_outcomes table validation)
- G12: Bybit Truth Freshness

Additional monitoring:
- ActionableZeroAlert: Detects sustained periods with signals but no actionable output
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

from src.governance.checkpoint.alerts import ActionableZeroAlert
from src.governance.checkpoint.integrity import MetricIntegrityChecker

logger = logging.getLogger(__name__)

# Add scripts/monitoring to path for cron_evidence import
# Path: src/governance/checkpoint/gates.py -> 4 levels up to project root
SCRIPT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)
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
        """G1: Scheduler Continuity - Check Redis heartbeat + degradation.

        Validates that the scheduler is running and reporting heartbeats
        within the expected interval (2 minutes). Also checks degradation
        trend from the health monitoring system:
        - MILD/MODERATE degradation: warning (CHECK status)
        - SEVERE degradation: failure (FAIL status)
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

            # Check degradation trend
            degradation_detail = self._check_scheduler_degradation(r)
            if degradation_detail:
                detail_parts.append(degradation_detail)

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

    def _check_scheduler_degradation(self, r) -> str | None:
        """Check scheduler degradation trend from Redis state.

        Reads degradation state stored by DegradationTracker and adds
        degradation context to the G1 gate result.

        Args:
            r: Redis client.

        Returns:
            Degradation detail string, or None if no degradation.
        """
        try:
            import json

            from src.governance.health.degradation import DegradationLevel

            key = "bmad:chiseai:health:degradation:scheduler"
            raw = r.get(key)
            if raw is None:
                return None

            state = json.loads(raw)
            level_str = state.get("level", "stable")
            window = state.get("window", [])

            try:
                level = DegradationLevel(level_str)
            except ValueError:
                return None

            if level == DegradationLevel.STABLE:
                return None

            # Build degradation detail
            if window:
                slope = (window[-1] - window[0]) / max(len(window) - 1, 1)
                slope_str = f"slope={slope:.1f}"
            else:
                slope_str = "slope=N/A"

            detail = f"degradation={level.value}({slope_str})"
            logger.info(f"G1 degradation check: {detail}")
            return detail

        except Exception as e:
            logger.debug(f"Degradation check failed (non-critical): {e}")
            return None

    def check_g2_signal_cadence(self) -> GateResult:
        """G2: Signal Cadence - Check for active signal generation.

        Implements G2 Message Taxonomy with 4 distinct states:
        - NO_SIGNALS: No signals generated in window (healthy idle state)
        - FILTERED: Signals generated but none actionable (filters working)
        - BOTTLENECK: Actionable signals present but downstream not converting
        - HEALTHY: Normal operation with signals flowing through pipeline

        Uses pipeline liveness metrics from scheduler heartbeat to determine state.
        Paper-aware: checks both bmad:chiseai:signals:* and paper:signal:* keys.
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

            # Paper-aware: Count paper signals separately
            paper_signal_keys = r.keys("paper:signal:*")
            paper_signals = len(paper_signal_keys)

            # Calculate live (non-paper) signals
            live_signals = max(0, signals_15m - paper_signals)

            # Backlog threshold for bottleneck detection (configurable)
            backlog_threshold = int(os.getenv("G2_BACKLOG_THRESHOLD", "10"))

            # G2 Message Taxonomy implementation
            # State 1: NO_SIGNALS - No signals generated in window (healthy idle)
            if signals_15m == 0:
                # Check if pipeline is stale (no signals for extended period)
                if pipeline_status == "stale":
                    return GateResult(
                        gate="G2",
                        status=self.STATUS_FAIL,
                        detail=f"NO_SIGNALS: PAPER:{paper_signals} LIVE:{live_signals} signals in 15m window (pipeline stale, last age: {heartbeat.get('latest_signal_age_m', 'N/A')}m)",
                    )
                return GateResult(
                    gate="G2",
                    status=self.STATUS_PASS,
                    detail=f"NO_SIGNALS: PAPER:{paper_signals} LIVE:{live_signals} signals in 15m window (healthy idle state)",
                )

            # State 2: FILTERED - Signals generated but none actionable (filters working)
            if signals_15m > 0 and actionable_15m == 0:
                return GateResult(
                    gate="G2",
                    status=self.STATUS_PASS,
                    detail=f"FILTERED: PAPER:{paper_signals} LIVE:{live_signals} signals generated, 0 actionable (filters active)",
                )

            # State 3: BOTTLENECK - Actionable signals present but downstream stalled
            if actionable_15m > 0 and backlog > backlog_threshold:
                return GateResult(
                    gate="G2",
                    status=self.STATUS_CHECK,
                    detail=f"BOTTLENECK: PAPER:{paper_signals} LIVE:{live_signals} signals, {actionable_15m} actionable, {backlog} backlog (downstream stalled, threshold: {backlog_threshold})",
                )

            # State 4: HEALTHY - Normal operation
            return GateResult(
                gate="G2",
                status=self.STATUS_PASS,
                detail=f"HEALTHY: PAPER:{paper_signals} LIVE:{live_signals} signals, {actionable_15m} actionable, backlog {backlog} (normal)",
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

    def check_g9_metric_integrity(self) -> GateResult:
        """G9: Metric Integrity - Validate heartbeat aggregates match raw data."""
        try:
            checker = MetricIntegrityChecker(
                redis_host=self._redis_host,
                redis_port=self._redis_port,
            )
            return checker.to_gate_result()
        except Exception as e:
            return GateResult(
                gate="G9",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )

    def check_g11_provenance(self) -> GateResult:
        """G11: Provenance - Check signal_outcomes table for missing provenance fields.

        Validates that execution_venue, execution_mode, and execution_source fields
        are populated for all records in the last 60 minutes.

        Returns:
            GateResult with status:
            - PASS: No data in window OR all records have all provenance fields
            - FAIL: Any records missing provenance fields
            - CHECK: Connection error or query failure
        """
        import os

        # Database connection parameters
        db_host = os.getenv("DB_HOST", "host.docker.internal")
        db_port = os.getenv("DB_PORT", "5434")
        db_name = os.getenv("DB_NAME", "chiseai")
        db_user = os.getenv("DB_USER", "chiseai")
        db_password = os.getenv("DB_PASSWORD", "chiseai")

        try:
            # Try psycopg2 first, fallback to asyncpg if available
            try:
                import psycopg2

                conn = psycopg2.connect(
                    host=db_host,
                    port=db_port,
                    database=db_name,
                    user=db_user,
                    password=db_password,
                    connect_timeout=5,
                )
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(execution_venue) as with_venue,
                        COUNT(execution_mode) as with_mode,
                        COUNT(execution_source) as with_source
                    FROM signal_outcomes
                    WHERE created_at >= NOW() - INTERVAL '60 minutes'
                """)
                row = cursor.fetchone()
                cursor.close()
                conn.close()

                total, with_venue, with_mode, with_source = row

            except ImportError:
                # Fallback to asyncpg if psycopg2 not available
                try:
                    import asyncio

                    import asyncpg

                    async def query():
                        conn = await asyncpg.connect(
                            host=db_host,
                            port=db_port,
                            database=db_name,
                            user=db_user,
                            password=db_password,
                            timeout=5,
                        )
                        row = await conn.fetchrow("""
                            SELECT
                                COUNT(*) as total,
                                COUNT(execution_venue) as with_venue,
                                COUNT(execution_mode) as with_mode,
                                COUNT(execution_source) as with_source
                            FROM signal_outcomes
                            WHERE created_at >= NOW() - INTERVAL '60 minutes'
                        """)
                        await conn.close()
                        return row

                    row = asyncio.run(query())
                    total = row["total"]
                    with_venue = row["with_venue"]
                    with_mode = row["with_mode"]
                    with_source = row["with_source"]

                except ImportError:
                    return GateResult(
                        gate="G11",
                        status=self.STATUS_CHECK,
                        detail="No PostgreSQL driver available (psycopg2 or asyncpg required)",
                    )

            # Calculate missing counts
            missing_venue = total - with_venue
            missing_mode = total - with_mode
            missing_source = total - with_source

            # Build detail string
            detail = f"total={total} venue={with_venue} mode={with_mode} source={with_source} missing_venue={missing_venue} missing_mode={missing_mode} missing_source={missing_source}"

            # Determine status
            if total == 0:
                # No data in window - PASS (no provenance to check)
                return GateResult(
                    gate="G11",
                    status=self.STATUS_PASS,
                    detail=f"{detail} | No data in 60m window",
                )
            elif missing_venue == 0 and missing_mode == 0 and missing_source == 0:
                # All records have all provenance fields
                return GateResult(
                    gate="G11",
                    status=self.STATUS_PASS,
                    detail=f"{detail} | All records have provenance",
                )
            else:
                # Some records missing provenance fields
                missing_fields = []
                if missing_venue > 0:
                    missing_fields.append(f"venue({missing_venue})")
                if missing_mode > 0:
                    missing_fields.append(f"mode({missing_mode})")
                if missing_source > 0:
                    missing_fields.append(f"source({missing_source})")
                return GateResult(
                    gate="G11",
                    status=self.STATUS_FAIL,
                    detail=f"{detail} | Missing: {', '.join(missing_fields)}",
                )

        except Exception as e:
            logger.error(f"Error checking G11: {e}")
            return GateResult(
                gate="G11",
                status=self.STATUS_CHECK,
                detail=f"Connection/query error: {str(e)[:100]}",
            )

    def check_g10_chain_integrity(self) -> GateResult:
        """G10: Chain Integrity - Count signals -> orders -> fills -> outcomes in last 6h.

        Validates the complete pipeline chain by counting entities in the last 6 hours:
        - Signals (bmad:chiseai:signals:* and paper:signal:*)
        - Orders (paper:order:* keys with timestamp >= now-6h)
        - Fills (paper:fill:* keys with timestamp >= now-6h)
        - Outcomes (bmad:chiseai:outcomes:index members with timestamp >= now-6h)

        Status logic:
        - PASS: signals > 0 AND orders > 0 AND fills > 0 AND outcomes > 0
        - CHECK: signals = 0 (no activity in window)
        - FAIL: signals > 0 but any downstream stage = 0 (pipeline broken)
        """
        r = self._get_redis()
        if not r:
            return GateResult(
                gate="G10",
                status=self.STATUS_FAIL,
                detail="Redis unavailable - cannot check chain integrity",
            )

        try:
            # Calculate 6-hour window threshold
            now = datetime.now(UTC)
            six_hours_ago = now.timestamp() - 21600  # 6 hours in seconds

            # Count signals in last 6h (both bmad and paper signal keys)
            signal_keys = list(r.scan_iter(match="bmad:chiseai:signals:*", count=1000))
            signal_keys.extend(list(r.scan_iter(match="paper:signal:*", count=1000)))
            signal_count = len(signal_keys)

            # Count orders in last 6h (paper:order:* keys with timestamp >= now-6h)
            order_count = 0
            for key in r.scan_iter(match="paper:order:*", count=1000):
                try:
                    # Extract timestamp from key (format: paper:order:<timestamp>:<id>)
                    parts = key.split(":")
                    if len(parts) >= 3:
                        ts = float(parts[2])
                        if ts >= six_hours_ago:
                            order_count += 1
                except (ValueError, IndexError):
                    continue

            # Count fills in last 6h (paper:fill:* keys with timestamp >= now-6h)
            fill_count = 0
            for key in r.scan_iter(match="paper:fill:*", count=1000):
                try:
                    # Extract timestamp from key (format: paper:fill:<timestamp>:<id>)
                    parts = key.split(":")
                    if len(parts) >= 3:
                        ts = float(parts[2])
                        if ts >= six_hours_ago:
                            fill_count += 1
                except (ValueError, IndexError):
                    continue

            # Count outcomes in last 6h via score range if available
            outcome_count = len(
                r.zrangebyscore("bmad:chiseai:outcomes", six_hours_ago, now.timestamp())
            )

            # Build detail string
            detail = f"signals={signal_count} orders={order_count} fills={fill_count} outcomes={outcome_count}"

            # Determine status based on chain integrity
            if signal_count == 0:
                # No signals = no activity in window (CHECK status)
                return GateResult(
                    gate="G10",
                    status=self.STATUS_CHECK,
                    detail=f"{detail} | healthy idle (no activity in 6h window)",
                )
            elif (
                signal_count > 0
                and order_count > 0
                and fill_count > 0
                and outcome_count > 0
            ):
                # Complete chain - all stages have activity
                return GateResult(
                    gate="G10",
                    status=self.STATUS_PASS,
                    detail=f"{detail} | Chain intact",
                )
            else:
                # Pipeline broken - signals exist but downstream stage is empty
                missing = []
                if order_count == 0:
                    missing.append("orders")
                if fill_count == 0:
                    missing.append("fills")
                if outcome_count == 0:
                    missing.append("outcomes")
                return GateResult(
                    gate="G10",
                    status=self.STATUS_FAIL,
                    detail=f"{detail} | Pipeline broken: no {'/'.join(missing)}",
                )

        except Exception as e:
            logger.error(f"Error checking G10: {e}")
            return GateResult(
                gate="G10",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )

    def check_g12_bybit_freshness(self) -> GateResult:
        """G12: Bybit Truth Freshness - Check if Bybit truth data is fresh.

        Validates that Bybit truth data collection is recent by checking:
        - bmad:chiseai:bybit_truth:last_collection_timestamp (ISO format timestamp)
        - bmad:chiseai:bybit_truth:last_collection_status (optional context)

        Freshness threshold: 60 minutes (3600 seconds)

        Returns:
            GateResult with status:
            - PASS: Collection within last 60 minutes
            - FAIL: Collection older than 60 minutes
            - CHECK: Key missing or timestamp unparseable
        """
        r = self._get_redis()
        if not r:
            return GateResult(
                gate="G12",
                status=self.STATUS_FAIL,
                detail="Redis unavailable - cannot check Bybit truth freshness",
            )

        try:
            # Get the last collection timestamp
            timestamp_str = r.get("bmad:chiseai:bybit_truth:last_collection_timestamp")

            if not timestamp_str:
                return GateResult(
                    gate="G12",
                    status=self.STATUS_CHECK,
                    detail="missing collection timestamp",
                )

            # Parse ISO timestamp
            try:
                last_collection = datetime.fromisoformat(timestamp_str)
            except ValueError:
                return GateResult(
                    gate="G12",
                    status=self.STATUS_CHECK,
                    detail=f"unparseable timestamp: {timestamp_str[:50]}",
                )

            # Calculate age in minutes
            now = datetime.now(UTC)
            age_seconds = (now - last_collection).total_seconds()
            age_minutes = age_seconds / 60

            # Freshness threshold: 60 minutes
            max_age_minutes = 60

            freshness = "stale" if age_minutes > max_age_minutes else "fresh"
            detail = f"last_collection={age_minutes:.1f}m ago | status={freshness}"

            if age_minutes > max_age_minutes:
                return GateResult(
                    gate="G12",
                    status=self.STATUS_FAIL,
                    detail=detail,
                )
            else:
                return GateResult(
                    gate="G12",
                    status=self.STATUS_PASS,
                    detail=detail,
                )

        except Exception as e:
            logger.error(f"Error checking G12: {e}")
            return GateResult(
                gate="G12",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )

    def run_all_checks(self) -> GateSummary:
        """Run all G1-G12 checks and return summary.

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
            self.check_g9_metric_integrity(),
            self.check_g10_chain_integrity(),
            self.check_g11_provenance(),  # NEW
            self.check_g12_bybit_freshness(),
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

    def check_actionable_zero_alert(self) -> GateResult:
        """Check actionable-zero alert condition.

        This gate monitors for sustained periods where signals are generated
        but none are actionable (3 consecutive 15-minute windows = 45 minutes).

        The alert helps detect:
        - Confidence thresholds that are too high
        - Market conditions not matching strategy criteria
        - Signal filtering logic issues

        Returns:
            GateResult with status:
            - PASS: No actionable-zero condition detected
            - CHECK: Actionable-zero condition building up (1-2 windows)
            - ALERT: Actionable-zero condition triggered (3+ windows)
        """
        r = self._get_redis()
        if not r:
            return GateResult(
                gate="AZ",
                status=self.STATUS_FAIL,
                detail="Redis unavailable - cannot check actionable-zero alert",
            )

        try:
            # Get current signal metrics from scheduler heartbeat
            heartbeat = r.hgetall("bmad:chiseai:scheduler:heartbeat")
            signals_15m = int(heartbeat.get("signals_15m", "0"))
            actionable_15m = int(heartbeat.get("actionable_15m", "0"))

            # Initialize alert checker
            alert_checker = ActionableZeroAlert(redis_client=r)

            # Check the condition
            result = alert_checker.check(signals_15m, actionable_15m)

            if result.triggered and not result.suppressed:
                # Full alert triggered
                return GateResult(
                    gate="AZ",
                    status=self.STATUS_ALERT,
                    detail=f"🚨 {result.message}",
                )
            elif result.triggered and result.suppressed:
                # Alert condition present but suppressed
                return GateResult(
                    gate="AZ",
                    status=self.STATUS_CHECK,
                    detail=f"Actionable-zero condition active ({result.metadata.get('consecutive_windows', '?')} windows) - alert suppressed",
                )
            elif result.metadata.get("consecutive_windows", 0) > 0:
                # Building up but not yet at threshold
                consecutive = result.metadata.get("consecutive_windows", 0)
                threshold = result.metadata.get("threshold", 3)
                return GateResult(
                    gate="AZ",
                    status=self.STATUS_CHECK,
                    detail=f"Actionable-zero count: {consecutive}/{threshold} windows",
                )
            else:
                # No actionable-zero condition
                return GateResult(
                    gate="AZ",
                    status=self.STATUS_PASS,
                    detail="No actionable-zero condition detected",
                )

        except Exception as e:
            logger.error(f"Error checking actionable-zero alert: {e}")
            return GateResult(
                gate="AZ",
                status=self.STATUS_FAIL,
                detail=f"Exception: {str(e)[:100]}",
            )
