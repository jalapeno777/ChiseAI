#!/usr/bin/env python3
"""Monitoring Evidence Integrity Validator

Validates that monitoring scripts report true state and detects false positives.
Cross-checks reported metrics against actual system state.

Usage:
    python3 scripts/monitoring/validate_monitoring.py
    python3 scripts/monitoring/validate_monitoring.py --gate G1 G2 G4
    python3 scripts/monitoring/validate_monitoring.py --format json
"""

import os
import sys
import argparse
import json
import logging
import subprocess
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import redis
except ImportError:
    redis = None

try:
    from monitoring.checkpoint_gate_audit import run_all_checks as run_gate_checks
    from monitoring.hourly_health_check import (
        check_scheduler_health,
        check_kill_switch,
        check_daily_loss,
        get_metrics as get_hourly_metrics,
    )
except ImportError as e:
    print(f"Warning: Could not import monitoring modules: {e}")
    run_gate_checks = None
    check_scheduler_health = None
    check_kill_switch = None
    check_daily_loss = None
    get_hourly_metrics = None

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Validation result status."""

    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    WARNING = "WARNING"


@dataclass
class ValidationResult:
    """Result of a validation check."""

    check_name: str
    reported_status: str
    actual_status: str
    validation_status: ValidationStatus
    details: str = ""
    recommendations: List[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ValidationReport:
    """Complete validation report."""

    timestamp: str
    overall_status: str
    results: List[ValidationResult]
    summary: Dict[str, int]
    recommendations: List[str]


class MonitoringValidator:
    """Validates monitoring script accuracy."""

    def __init__(self):
        self.redis_client = self._get_redis()
        self.validation_results: List[ValidationResult] = []
        self.false_positives_found = 0

    def _get_redis(self) -> Optional[redis.Redis]:
        """Get Redis connection."""
        if redis is None:
            return None
        try:
            host = os.getenv("REDIS_HOST", "host.docker.internal")
            port = int(os.getenv("REDIS_PORT", "6380"))
            r = redis.Redis(
                host=host, port=port, decode_responses=True, socket_timeout=5
            )
            if r.ping():
                return r
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
        return None

    def validate_g1_scheduler(self) -> ValidationResult:
        """Validate G1 (Scheduler) - check for false positives.

        Issue: Shows PASS when no heartbeat data exists.
        Fix: Should show UNKNOWN if no heartbeat data.
        """
        check_name = "G1_Scheduler"

        if self.redis_client is None:
            return ValidationResult(
                check_name=check_name,
                reported_status="UNKNOWN",
                actual_status="Redis unavailable",
                validation_status=ValidationStatus.UNKNOWN,
                details="Cannot validate - Redis connection failed",
                recommendations=["Check Redis connectivity", "Verify Redis is running"],
            )

        try:
            # Check for scheduler heartbeat in Redis
            heartbeat = self.redis_client.hgetall("bmad:chiseai:scheduler:heartbeat")
            last_seen = self.redis_client.get("bmad:chiseai:scheduler:last_seen")

            # Check process status
            try:
                result = subprocess.run(
                    ["ps", "aux"], capture_output=True, text=True, timeout=5
                )
                process_running = any(
                    "trading_activity" in line or "scheduler" in line
                    for line in result.stdout.split("\n")
                    if "grep" not in line
                )
            except Exception:
                process_running = False

            # Check state file
            state_exists = os.path.exists("data/optimization_schedule.json")

            # Determine actual status
            has_heartbeat_data = bool(heartbeat or last_seen)

            if not has_heartbeat_data:
                actual_status = "NO_HEARTBEAT_DATA"
                validation_status = ValidationStatus.NOT_CONFIGURED
                details = "No scheduler heartbeat data found in Redis"
                recommendations = [
                    "Scheduler may not be running or not reporting heartbeats",
                    "Check if scheduler is configured to report heartbeats",
                    "Verify scheduler process is actually active",
                ]
            elif process_running and state_exists:
                actual_status = "HEALTHY"
                validation_status = ValidationStatus.VALID
                details = f"Process running, state exists, heartbeat: {last_seen or 'present'}"
                recommendations = []
            elif state_exists and has_heartbeat_data:
                actual_status = "STATE_ONLY"
                validation_status = ValidationStatus.WARNING
                details = "State file exists but process not detected"
                recommendations = [
                    "Verify scheduler process status",
                    "Check for zombie processes",
                ]
            else:
                actual_status = "UNHEALTHY"
                validation_status = ValidationStatus.INVALID
                details = "No process, state, or heartbeat detected"
                recommendations = ["Start scheduler process", "Check logs for errors"]

            # Check if monitoring script would report false positive
            reported_status = "PASS" if (process_running or state_exists) else "FAIL"
            if reported_status == "PASS" and not has_heartbeat_data:
                self.false_positives_found += 1
                validation_status = ValidationStatus.INVALID
                details += " | FALSE POSITIVE DETECTED: PASS without heartbeat data"

            return ValidationResult(
                check_name=check_name,
                reported_status=reported_status,
                actual_status=actual_status,
                validation_status=validation_status,
                details=details,
                recommendations=recommendations,
            )

        except Exception as e:
            return ValidationResult(
                check_name=check_name,
                reported_status="ERROR",
                actual_status=f"Exception: {e}",
                validation_status=ValidationStatus.UNKNOWN,
                details=str(e),
                recommendations=["Check scheduler configuration"],
            )

    def validate_g2_signals(self) -> ValidationResult:
        """Validate G2 (Signal Cadence) - check for false positives.

        Issue: Shows PASS when Redis is empty.
        Fix: Should show UNKNOWN if Redis empty, not PASS.
        """
        check_name = "G2_Signal_Cadence"

        if self.redis_client is None:
            return ValidationResult(
                check_name=check_name,
                reported_status="UNKNOWN",
                actual_status="Redis unavailable",
                validation_status=ValidationStatus.UNKNOWN,
                details="Cannot validate - Redis connection failed",
                recommendations=["Check Redis connectivity"],
            )

        try:
            # Get actual signal count
            signal_keys = self.redis_client.keys("bmad:chiseai:signals:*")
            signal_count = len(signal_keys)

            # Check for recent signals (within last hour)
            recent_signals = 0
            current_time = datetime.now(timezone.utc).timestamp()
            for key in signal_keys[:10]:  # Sample first 10
                try:
                    signal_data = self.redis_client.hgetall(key)
                    if signal_data:
                        timestamp = signal_data.get("timestamp") or signal_data.get(
                            "created_at"
                        )
                        if timestamp:
                            try:
                                signal_time = float(timestamp)
                                if current_time - signal_time < 3600:  # Within 1 hour
                                    recent_signals += 1
                            except (ValueError, TypeError):
                                pass
                except Exception:
                    pass

            # Determine actual status
            if signal_count == 0:
                actual_status = "NO_SIGNALS"
                validation_status = ValidationStatus.NOT_CONFIGURED
                details = "No signals found in Redis"
                recommendations = [
                    "Signal generation may not be configured",
                    "Check if signal sources are connected",
                    "Verify signal pipeline is active",
                ]
            elif recent_signals == 0 and signal_count > 0:
                actual_status = "STALE_SIGNALS"
                validation_status = ValidationStatus.STALE
                details = f"{signal_count} signals but none recent (may be stale)"
                recommendations = [
                    "Check signal generation frequency",
                    "Verify signal sources are still active",
                    "Review signal timestamps",
                ]
            else:
                actual_status = "HEALTHY"
                validation_status = ValidationStatus.VALID
                details = f"{signal_count} signals, {recent_signals} recent"
                recommendations = []

            # Check for false positive
            reported_status = "PASS" if signal_count > 0 else "CHECK"
            if reported_status == "PASS" and recent_signals == 0 and signal_count > 0:
                validation_status = ValidationStatus.WARNING
                details += " | WARNING: PASS but signals may be stale"
            elif signal_count == 0:
                self.false_positives_found += 1
                # Current script shows CHECK, but should show UNKNOWN
                validation_status = ValidationStatus.NOT_CONFIGURED
                details += " | Should show UNKNOWN (not CHECK) when no signals"

            return ValidationResult(
                check_name=check_name,
                reported_status=reported_status,
                actual_status=actual_status,
                validation_status=validation_status,
                details=details,
                recommendations=recommendations,
            )

        except Exception as e:
            return ValidationResult(
                check_name=check_name,
                reported_status="ERROR",
                actual_status=f"Exception: {e}",
                validation_status=ValidationStatus.UNKNOWN,
                details=str(e),
                recommendations=["Check signal storage configuration"],
            )

    def validate_g3_outcomes(self) -> ValidationResult:
        """Validate G3 (Data Flow/Outcomes) - check for false positives.

        Issue: Shows PASS when no outcomes exist.
        Fix: Should show UNKNOWN if no outcomes, not PASS.
        """
        check_name = "G3_Outcomes"

        if self.redis_client is None:
            return ValidationResult(
                check_name=check_name,
                reported_status="UNKNOWN",
                actual_status="Redis unavailable",
                validation_status=ValidationStatus.UNKNOWN,
                details="Cannot validate - Redis connection failed",
                recommendations=["Check Redis connectivity"],
            )

        try:
            # Get actual outcome count
            outcome_count = self.redis_client.scard("bmad:chiseai:outcomes:index")

            # Check for recent outcomes
            recent_outcomes = 0
            current_time = datetime.now(timezone.utc).timestamp()

            # Sample some outcomes to check recency
            outcome_ids = self.redis_client.smembers("bmad:chiseai:outcomes:index")
            for outcome_id in list(outcome_ids)[:10]:
                try:
                    outcome = self.redis_client.hgetall(
                        f"bmad:chiseai:outcomes:{outcome_id}"
                    )
                    if outcome:
                        timestamp = outcome.get("timestamp") or outcome.get(
                            "created_at"
                        )
                        if timestamp:
                            try:
                                outcome_time = float(timestamp)
                                if (
                                    current_time - outcome_time < 86400
                                ):  # Within 24 hours
                                    recent_outcomes += 1
                            except (ValueError, TypeError):
                                pass
                except Exception:
                    pass

            # Determine actual status
            if outcome_count == 0:
                actual_status = "NO_OUTCOMES"
                validation_status = ValidationStatus.NOT_CONFIGURED
                details = "No outcomes recorded in Redis"
                recommendations = [
                    "Outcome tracking may not be configured",
                    "Check if trading is actually executing",
                    "Verify outcome pipeline is connected",
                ]
            elif recent_outcomes == 0 and outcome_count > 0:
                actual_status = "STALE_OUTCOMES"
                validation_status = ValidationStatus.STALE
                details = f"{outcome_count} outcomes but none recent (may be stale)"
                recommendations = [
                    "Check if trading is still active",
                    "Verify outcome recording is working",
                    "Review recent trading activity",
                ]
            else:
                actual_status = "HEALTHY"
                validation_status = ValidationStatus.VALID
                details = f"{outcome_count} outcomes, {recent_outcomes} recent"
                recommendations = []

            # Check for false positive
            reported_status = (
                "PASS" if (outcome_count and outcome_count > 0) else "CHECK"
            )
            if reported_status == "PASS" and recent_outcomes == 0 and outcome_count > 0:
                validation_status = ValidationStatus.WARNING
                details += " | WARNING: PASS but outcomes may be stale"
            elif outcome_count == 0:
                self.false_positives_found += 1
                # Current script shows CHECK, but should show UNKNOWN
                validation_status = ValidationStatus.NOT_CONFIGURED
                details += " | Should show UNKNOWN (not CHECK) when no outcomes"

            return ValidationResult(
                check_name=check_name,
                reported_status=reported_status,
                actual_status=actual_status,
                validation_status=validation_status,
                details=details,
                recommendations=recommendations,
            )

        except Exception as e:
            return ValidationResult(
                check_name=check_name,
                reported_status="ERROR",
                actual_status=f"Exception: {e}",
                validation_status=ValidationStatus.UNKNOWN,
                details=str(e),
                recommendations=["Check outcome storage configuration"],
            )

    def validate_g4_kill_switch(self) -> ValidationResult:
        """Validate G4 (Kill Switch) - check for false positives.

        Issue: Shows PASS when not configured.
        Fix: Should show NOT_CONFIGURED if not set, not PASS.
        """
        check_name = "G4_Kill_Switch"

        if self.redis_client is None:
            return ValidationResult(
                check_name=check_name,
                reported_status="UNKNOWN",
                actual_status="Redis unavailable",
                validation_status=ValidationStatus.UNKNOWN,
                details="Cannot validate - Redis connection failed",
                recommendations=["Check Redis connectivity"],
            )

        try:
            # Get actual kill switch state
            enabled = self.redis_client.hget("bmad:chiseai:kill_switch", "enabled")
            triggered = self.redis_client.hget("bmad:chiseai:kill_switch", "triggered")

            # Check if kill switch is actually configured
            is_configured = enabled is not None
            is_enabled = enabled == "1"
            is_triggered = triggered == "1"

            # Determine actual status
            if not is_configured:
                actual_status = "NOT_CONFIGURED"
                validation_status = ValidationStatus.NOT_CONFIGURED
                details = "Kill switch not configured in Redis"
                recommendations = [
                    "Configure kill switch before trading",
                    "Set bmad:chiseai:kill_switch:enabled = 1",
                    "Verify kill switch mechanism is implemented",
                ]
            elif is_triggered:
                actual_status = "TRIGGERED"
                validation_status = ValidationStatus.INVALID
                details = "Kill switch is TRIGGERED - trading halted"
                recommendations = [
                    "URGENT: Trading is halted",
                    "Investigate trigger cause",
                    "Reset kill switch when safe",
                ]
            elif is_enabled:
                actual_status = "ARMED"
                validation_status = ValidationStatus.VALID
                details = "Kill switch armed and ready"
                recommendations = []
            else:
                actual_status = "DISABLED"
                validation_status = ValidationStatus.WARNING
                details = "Kill switch configured but disabled"
                recommendations = [
                    "Enable kill switch for safety",
                    "Set bmad:chiseai:kill_switch:enabled = 1",
                ]

            # Check for false positive
            if is_configured and is_enabled and not is_triggered:
                reported_status = "PASS"
            elif is_triggered:
                reported_status = "ALERT"
            else:
                reported_status = "CHECK"

            if reported_status == "PASS" and not is_configured:
                self.false_positives_found += 1
                validation_status = ValidationStatus.INVALID
                details += " | FALSE POSITIVE DETECTED: PASS when not configured"
            elif not is_configured:
                self.false_positives_found += 1
                validation_status = ValidationStatus.NOT_CONFIGURED
                details += " | Should show NOT_CONFIGURED (not CHECK)"

            return ValidationResult(
                check_name=check_name,
                reported_status=reported_status,
                actual_status=actual_status,
                validation_status=validation_status,
                details=details,
                recommendations=recommendations,
            )

        except Exception as e:
            return ValidationResult(
                check_name=check_name,
                reported_status="ERROR",
                actual_status=f"Exception: {e}",
                validation_status=ValidationStatus.UNKNOWN,
                details=str(e),
                recommendations=["Check kill switch configuration"],
            )

    def validate_g5_daily_loss(self) -> ValidationResult:
        """Validate G5 (Daily Loss Guard) - check for false positives.

        Issue: Shows PASS when not configured.
        Fix: Should show NOT_CONFIGURED if not set, not PASS.
        """
        check_name = "G5_Daily_Loss"

        if self.redis_client is None:
            return ValidationResult(
                check_name=check_name,
                reported_status="UNKNOWN",
                actual_status="Redis unavailable",
                validation_status=ValidationStatus.UNKNOWN,
                details="Cannot validate - Redis connection failed",
                recommendations=["Check Redis connectivity"],
            )

        try:
            # Get actual daily loss state
            max_loss = self.redis_client.hget(
                "bmad:chiseai:daily_loss_limit", "max_loss_percent"
            )
            current_loss = self.redis_client.hget(
                "bmad:chiseai:daily_loss_limit", "current_loss"
            )

            # Check if configured
            is_configured = max_loss is not None

            # Determine actual status
            if not is_configured:
                actual_status = "NOT_CONFIGURED"
                validation_status = ValidationStatus.NOT_CONFIGURED
                details = "Daily loss limit not configured in Redis"
                recommendations = [
                    "Configure daily loss limit before trading",
                    "Set bmad:chiseai:daily_loss_limit:max_loss_percent",
                    "Verify loss tracking is implemented",
                ]
            elif current_loss:
                try:
                    current = float(current_loss)
                    max_val = float(max_loss)
                    if current >= max_val:
                        actual_status = "LIMIT_REACHED"
                        validation_status = ValidationStatus.INVALID
                        details = (
                            f"Daily loss limit reached: ${current:.2f} / {max_val}%"
                        )
                        recommendations = [
                            "URGENT: Daily loss limit reached",
                            "Review trading activity",
                            "Consider halting trading",
                        ]
                    else:
                        actual_status = "WITHIN_LIMIT"
                        validation_status = ValidationStatus.VALID
                        details = f"Loss: ${current:.2f}, Limit: {max_val}%"
                        recommendations = []
                except (ValueError, TypeError):
                    actual_status = "CONFIG_ERROR"
                    validation_status = ValidationStatus.WARNING
                    details = "Invalid loss values in Redis"
                    recommendations = ["Check loss limit data format"]
            else:
                actual_status = "NO_CURRENT_DATA"
                validation_status = ValidationStatus.WARNING
                details = f"Limit set to {max_loss}% but no current loss data"
                recommendations = ["Verify loss tracking is active"]

            # Check for false positive
            reported_status = "PASS" if is_configured else "CHECK"
            if reported_status == "PASS" and not is_configured:
                self.false_positives_found += 1
                validation_status = ValidationStatus.INVALID
                details += " | FALSE POSITIVE DETECTED: PASS when not configured"
            elif not is_configured:
                self.false_positives_found += 1
                validation_status = ValidationStatus.NOT_CONFIGURED
                details += " | Should show NOT_CONFIGURED (not CHECK)"

            return ValidationResult(
                check_name=check_name,
                reported_status=reported_status,
                actual_status=actual_status,
                validation_status=validation_status,
                details=details,
                recommendations=recommendations,
            )

        except Exception as e:
            return ValidationResult(
                check_name=check_name,
                reported_status="ERROR",
                actual_status=f"Exception: {e}",
                validation_status=ValidationStatus.UNKNOWN,
                details=str(e),
                recommendations=["Check daily loss configuration"],
            )

    def validate_g6_connectivity(self) -> ValidationResult:
        """Validate G6 (Bybit Connectivity) - check for false positives."""
        check_name = "G6_Connectivity"

        try:
            import socket
            import ssl

            host = "api.bybit.com"
            port = 443
            timeout = 5

            # Try actual connection
            try:
                context = ssl.create_default_context()
                with socket.create_connection((host, port), timeout=timeout) as sock:
                    with context.wrap_socket(sock, server_hostname=host) as ssock:
                        request = f"GET /v5/market/time HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
                        ssock.send(request.encode())
                        response = ssock.recv(1024).decode()

                        if "200 OK" in response:
                            actual_status = "HEALTHY"
                            validation_status = ValidationStatus.VALID
                            details = "Bybit API reachable and responding"
                            recommendations = []
                        elif "HTTP/1.1" in response:
                            actual_status = "RESPONDING"
                            validation_status = ValidationStatus.WARNING
                            details = "API reachable but unexpected response"
                            recommendations = ["Verify API endpoint health"]
                        else:
                            actual_status = "UNEXPECTED"
                            validation_status = ValidationStatus.WARNING
                            details = "Connected but unexpected response"
                            recommendations = ["Check API status"]
            except socket.timeout:
                actual_status = "TIMEOUT"
                validation_status = ValidationStatus.INVALID
                details = "Connection to Bybit timed out"
                recommendations = ["Check network connectivity", "Verify Bybit status"]
            except Exception as e:
                actual_status = "UNREACHABLE"
                validation_status = ValidationStatus.INVALID
                details = f"Cannot reach Bybit: {e}"
                recommendations = [
                    "Check internet connection",
                    "Verify Bybit API status",
                ]

            reported_status = (
                "PASS" if validation_status == ValidationStatus.VALID else "FAIL"
            )

            return ValidationResult(
                check_name=check_name,
                reported_status=reported_status,
                actual_status=actual_status,
                validation_status=validation_status,
                details=details,
                recommendations=recommendations,
            )

        except Exception as e:
            return ValidationResult(
                check_name=check_name,
                reported_status="ERROR",
                actual_status=f"Exception: {e}",
                validation_status=ValidationStatus.UNKNOWN,
                details=str(e),
                recommendations=["Check connectivity validation"],
            )

    def validate_g7_observability(self) -> ValidationResult:
        """Validate G7 (Observability/Redis Health) - check for false positives."""
        check_name = "G7_Observability"

        if self.redis_client is None:
            return ValidationResult(
                check_name=check_name,
                reported_status="FAIL",
                actual_status="Redis unavailable",
                validation_status=ValidationStatus.INVALID,
                details="Redis connection failed - observability compromised",
                recommendations=[
                    "CRITICAL: Redis is down",
                    "Check Redis container status",
                    "Verify Redis configuration",
                ],
            )

        try:
            # Get Redis info
            ping_ok = self.redis_client.ping()
            key_count = self.redis_client.dbsize()
            info = self.redis_client.info("server")
            uptime = info.get("uptime_in_seconds", 0)
            version = info.get("redis_version", "unknown")

            # Check memory usage
            memory_info = self.redis_client.info("memory")
            used_memory = memory_info.get("used_memory_human", "unknown")
            max_memory = memory_info.get("maxmemory_human", "unlimited")

            # Determine actual status
            if ping_ok and uptime > 3600:
                actual_status = "HEALTHY"
                validation_status = ValidationStatus.VALID
                details = f"Redis {version}, {key_count} keys, {uptime // 3600}h uptime, {used_memory} used"
                recommendations = []
            elif ping_ok:
                actual_status = "RECENT_RESTART"
                validation_status = ValidationStatus.WARNING
                details = f"Redis OK but restarted recently ({uptime}s uptime)"
                recommendations = ["Monitor for stability"]
            else:
                actual_status = "UNHEALTHY"
                validation_status = ValidationStatus.INVALID
                details = "Redis ping failed"
                recommendations = ["Check Redis logs", "Restart Redis if needed"]

            reported_status = "PASS" if ping_ok else "FAIL"

            return ValidationResult(
                check_name=check_name,
                reported_status=reported_status,
                actual_status=actual_status,
                validation_status=validation_status,
                details=details,
                recommendations=recommendations,
            )

        except Exception as e:
            return ValidationResult(
                check_name=check_name,
                reported_status="ERROR",
                actual_status=f"Exception: {e}",
                validation_status=ValidationStatus.UNKNOWN,
                details=str(e),
                recommendations=["Check Redis health"],
            )

    def validate_g8_pipeline(self) -> ValidationResult:
        """Validate G8 (End-to-End Pipeline) - check for false positives."""
        check_name = "G8_Pipeline"

        if self.redis_client is None:
            return ValidationResult(
                check_name=check_name,
                reported_status="CHECK",
                actual_status="Redis unavailable",
                validation_status=ValidationStatus.UNKNOWN,
                details="Cannot validate - Redis connection failed",
                recommendations=["Check Redis connectivity"],
            )

        try:
            # Get pipeline components
            signal_count = len(self.redis_client.keys("bmad:chiseai:signals:*"))
            outcome_count = self.redis_client.scard("bmad:chiseai:outcomes:index")

            # Check for pipeline configuration
            pipeline_config = self.redis_client.hgetall("bmad:chiseai:pipeline:config")

            # Determine actual status
            has_signals = signal_count > 0
            has_outcomes = outcome_count > 0

            if has_signals and has_outcomes:
                actual_status = "FLOWING"
                validation_status = ValidationStatus.VALID
                details = f"Pipeline flowing: {signal_count} signals → {outcome_count} outcomes"
                recommendations = []
            elif has_signals and not has_outcomes:
                actual_status = "BLOCKED"
                validation_status = ValidationStatus.INVALID
                details = (
                    f"Signals exist ({signal_count}) but no outcomes - pipeline blocked"
                )
                recommendations = [
                    "Check signal-to-outcome pipeline",
                    "Verify execution layer",
                    "Review trading configuration",
                ]
            elif not has_signals and has_outcomes:
                actual_status = "ORPHANED_OUTCOMES"
                validation_status = ValidationStatus.WARNING
                details = f"Outcomes exist ({outcome_count}) but no signals - data inconsistency"
                recommendations = [
                    "Check for data cleanup issues",
                    "Verify signal retention policy",
                ]
            else:
                actual_status = "NO_DATA"
                validation_status = ValidationStatus.NOT_CONFIGURED
                details = "No signals or outcomes - pipeline not active"
                recommendations = [
                    "Pipeline not configured or started",
                    "Check trading system initialization",
                ]

            # Current script logic
            reported_status = "PASS" if (has_signals and has_outcomes) else "CHECK"

            return ValidationResult(
                check_name=check_name,
                reported_status=reported_status,
                actual_status=actual_status,
                validation_status=validation_status,
                details=details,
                recommendations=recommendations,
            )

        except Exception as e:
            return ValidationResult(
                check_name=check_name,
                reported_status="ERROR",
                actual_status=f"Exception: {e}",
                validation_status=ValidationStatus.UNKNOWN,
                details=str(e),
                recommendations=["Check pipeline configuration"],
            )

    def run_all_validations(
        self, gates: Optional[List[str]] = None
    ) -> ValidationReport:
        """Run all validation checks."""
        validators = {
            "G1": self.validate_g1_scheduler,
            "G2": self.validate_g2_signals,
            "G3": self.validate_g3_outcomes,
            "G4": self.validate_g4_kill_switch,
            "G5": self.validate_g5_daily_loss,
            "G6": self.validate_g6_connectivity,
            "G7": self.validate_g7_observability,
            "G8": self.validate_g8_pipeline,
        }

        if gates:
            # Filter to requested gates
            validators = {k: v for k, v in validators.items() if k in gates}

        results = []
        for gate_id, validator in validators.items():
            logger.info(f"Validating {gate_id}...")
            result = validator()
            results.append(result)

        # Calculate summary
        summary = {
            "total": len(results),
            "valid": sum(
                1 for r in results if r.validation_status == ValidationStatus.VALID
            ),
            "invalid": sum(
                1 for r in results if r.validation_status == ValidationStatus.INVALID
            ),
            "stale": sum(
                1 for r in results if r.validation_status == ValidationStatus.STALE
            ),
            "unknown": sum(
                1 for r in results if r.validation_status == ValidationStatus.UNKNOWN
            ),
            "not_configured": sum(
                1
                for r in results
                if r.validation_status == ValidationStatus.NOT_CONFIGURED
            ),
            "warning": sum(
                1 for r in results if r.validation_status == ValidationStatus.WARNING
            ),
            "false_positives_detected": self.false_positives_found,
        }

        # Determine overall status
        if summary["invalid"] > 0:
            overall = "CRITICAL"
        elif summary["not_configured"] > 0:
            overall = "NOT_CONFIGURED"
        elif summary["stale"] > 0 or summary["warning"] > 0:
            overall = "WARNING"
        elif summary["unknown"] > 0:
            overall = "UNKNOWN"
        else:
            overall = "HEALTHY"

        # Collect all recommendations
        all_recommendations = []
        for result in results:
            all_recommendations.extend(result.recommendations)

        # Add overall recommendations
        if self.false_positives_found > 0:
            all_recommendations.insert(
                0,
                f"URGENT: {self.false_positives_found} false positive(s) detected in monitoring",
            )

        return ValidationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            overall_status=overall,
            results=results,
            summary=summary,
            recommendations=list(
                dict.fromkeys(all_recommendations)
            ),  # Remove duplicates
        )


def format_text_report(report: ValidationReport) -> str:
    """Format validation report as text."""
    lines = [
        "=" * 70,
        "MONITORING EVIDENCE INTEGRITY VALIDATION REPORT",
        "=" * 70,
        f"Timestamp: {report.timestamp}",
        f"Overall Status: {report.overall_status}",
        "",
        "SUMMARY:",
        f"  Total Checks: {report.summary['total']}",
        f"  Valid: {report.summary['valid']} | Invalid: {report.summary['invalid']} | "
        f"Stale: {report.summary['stale']} | Unknown: {report.summary['unknown']}",
        f"  Not Configured: {report.summary['not_configured']} | Warning: {report.summary['warning']}",
        f"  False Positives Detected: {report.summary['false_positives_detected']}",
        "",
        "DETAILED RESULTS:",
        "-" * 70,
    ]

    for result in report.results:
        status_icon = {
            ValidationStatus.VALID: "✅",
            ValidationStatus.INVALID: "❌",
            ValidationStatus.STALE: "⏰",
            ValidationStatus.UNKNOWN: "❓",
            ValidationStatus.NOT_CONFIGURED: "⚙️",
            ValidationStatus.WARNING: "⚠️",
        }.get(result.validation_status, "❓")

        lines.extend(
            [
                f"",
                f"{status_icon} {result.check_name}",
                f"   Reported Status: {result.reported_status}",
                f"   Actual Status:   {result.actual_status}",
                f"   Validation:      {result.validation_status.value}",
                f"   Details:         {result.details}",
            ]
        )

        if result.recommendations:
            lines.append(f"   Recommendations:")
            for rec in result.recommendations:
                lines.append(f"      • {rec}")

    if report.recommendations:
        lines.extend(
            [
                "",
                "OVERALL RECOMMENDATIONS:",
                "-" * 70,
            ]
        )
        for rec in report.recommendations:
            lines.append(f"  • {rec}")

    lines.extend(
        [
            "",
            "=" * 70,
            "END OF REPORT",
            "=" * 70,
        ]
    )

    return "\n".join(lines)


def format_json_report(report: ValidationReport) -> str:
    """Format validation report as JSON."""

    def result_to_dict(r: ValidationResult) -> dict:
        d = asdict(r)
        d["validation_status"] = r.validation_status.value
        return d

    data = {
        "timestamp": report.timestamp,
        "overall_status": report.overall_status,
        "summary": report.summary,
        "results": [result_to_dict(r) for r in report.results],
        "recommendations": report.recommendations,
    }
    return json.dumps(data, indent=2)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate monitoring script accuracy and detect false positives"
    )
    parser.add_argument(
        "--gate",
        nargs="+",
        choices=["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"],
        help="Specific gates to validate (default: all)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit with non-zero code if issues found",
    )

    args = parser.parse_args()

    # Run validations
    validator = MonitoringValidator()
    report = validator.run_all_validations(gates=args.gate)

    # Format output
    if args.format == "json":
        output = format_json_report(report)
    else:
        output = format_text_report(report)

    # Write output
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Report written to: {args.output}")
    else:
        print(output)

    # Exit code
    if args.exit_code:
        if report.overall_status in ["CRITICAL", "INVALID"]:
            return 2
        elif report.overall_status in ["WARNING", "NOT_CONFIGURED", "UNKNOWN"]:
            return 1
        return 0

    return 0


if __name__ == "__main__":
    exit(main())
