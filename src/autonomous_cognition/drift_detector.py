"""Metacognitive drift detection for autonomous cognition system.

Monitors calibration health, self-assessment quality, and deferred item status
to detect cognitive drift before it degrades system performance. Designed to
run as a periodic check (e.g., daily cron or scheduled task).

Exit code 1 if drift_score exceeds threshold (default 0.85).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols for Redis dependency injection (testability)
# ---------------------------------------------------------------------------


class RedisGetFunc(Protocol):
    def __call__(self, key: str) -> str | None: ...


class RedisScanFunc(Protocol):
    def __call__(self, pattern: str) -> list[str]: ...


class RedisHGetAllFunc(Protocol):
    def __call__(self, name: str) -> dict[str, str]: ...


# ---------------------------------------------------------------------------
# Default Redis implementations (lazy import for environments without Redis)
# ---------------------------------------------------------------------------

_redis_get: RedisGetFunc | None = None
_redis_scan_keys: RedisScanFunc | None = None
_redis_hgetall: RedisHGetAllFunc | None = None

try:
    from tools.redis_state import (
        redis_state_get as _redis_get,  # type: ignore[assignment]
    )
    from tools.redis_state import (
        redis_state_hgetall as _redis_hgetall,  # type: ignore[assignment]
    )
    from tools.redis_state import (
        redis_state_scan_all_keys as _redis_scan_keys,  # type: ignore[assignment]
    )
except ImportError:
    logger.warning("tools.redis_state not available - Redis checks will be no-ops")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DriftCheckResult:
    """Result of an individual drift check."""

    name: str
    score: float  # 0.0 = no drift, 1.0 = severe drift
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DriftReport:
    """Aggregated drift detection report."""

    checks: list[DriftCheckResult] = field(default_factory=list)
    overall_score: float = 0.0
    threshold: float = 0.85
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    @property
    def is_drift_detected(self) -> bool:
        return self.overall_score > self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 4),
            "threshold": self.threshold,
            "drift_detected": self.is_drift_detected,
            "timestamp": self.timestamp,
            "checks": [
                {
                    "name": c.name,
                    "score": round(c.score, 4),
                    "message": c.message,
                    "details": c.details,
                }
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Redis key patterns
# ---------------------------------------------------------------------------

CALIBRATION_KEY_PATTERN = "bmad:chiseai:metacog:calibration:agent:jarvis:weekly:*"
SELF_ASSESSMENT_KEY = "bmad:chiseai:autocog:self_assessment:latest"
DEFERRED_ITEMS_KEY = "bmad:chiseai:autocog:deferred_items"


# ---------------------------------------------------------------------------
# Individual drift checks
# ---------------------------------------------------------------------------


def check_calibration_exists(
    redis_scan: RedisScanFunc | None = None,
) -> DriftCheckResult:
    """Check if calibration keys exist for the current week.

    Returns a drift score based on whether weekly calibration data is present.
    Missing calibration for the current week contributes 0.35 to drift score.
    Missing calibration for >1 week contributes 0.7 (near-severe).

    Score: 0.0 if current week calibration exists,
           0.35 if last week exists but current does not,
           0.7 if no recent calibration found.
    """
    scan_fn = redis_scan or _redis_scan_keys
    name = "calibration_exists"

    if scan_fn is None:
        return DriftCheckResult(
            name=name,
            score=0.0,
            message="Redis scan unavailable - skipping calibration check",
            details={"available": False},
        )

    try:
        keys = scan_fn(CALIBRATION_KEY_PATTERN)
    except Exception as exc:
        logger.warning("Failed to scan calibration keys: %s", exc)
        return DriftCheckResult(
            name=name,
            score=0.0,
            message=f"Redis scan failed: {exc}",
            details={"error": str(exc)},
        )

    if not keys:
        return DriftCheckResult(
            name=name,
            score=0.7,
            message="No calibration keys found for any week",
            details={"key_count": 0, "pattern": CALIBRATION_KEY_PATTERN},
        )

    now = datetime.now(UTC)
    # Use ISO calendar for consistent week numbering
    current_iso = now.isocalendar()  # (year, week, weekday)
    current_year, current_week, _ = current_iso

    has_current_week = False
    has_last_week = False
    for key in keys:
        # Keys end with weekly identifier like "2026-W15"
        # Extract the date portion from the key
        parts = key.rsplit(":", 1)
        if len(parts) == 2:
            date_str = parts[1]
            try:
                # Parse "2026-W15" format - normalize both %W and %V
                # to ISO week number for comparison
                if "-W" in date_str:
                    parts_inner = date_str.split("-W", 1)
                    key_year = int(parts_inner[0])
                    key_week = int(parts_inner[1])
                    if key_year == current_year and key_week == current_week:
                        has_current_week = True
                    elif (
                        key_year == current_year and key_week == current_week - 1
                    ) or (
                        key_year == current_year - 1
                        and key_week >= 52
                        and current_week == 1
                    ):
                        has_last_week = True
                else:
                    # Try simple date format fallback
                    key_date = datetime.fromisoformat(date_str)
                    if key_date.tzinfo is None:
                        key_date = key_date.replace(tzinfo=UTC)
                    key_iso = key_date.isocalendar()
                    if key_iso[0] == current_year and key_iso[1] == current_week:
                        has_current_week = True
                    elif key_iso[0] == current_year and key_iso[1] == current_week - 1:
                        has_last_week = True
            except (ValueError, IndexError):
                pass

    if has_current_week:
        return DriftCheckResult(
            name=name,
            score=0.0,
            message="Current week calibration exists",
            details={"key_count": len(keys), "current_week": True},
        )
    elif has_last_week:
        return DriftCheckResult(
            name=name,
            score=0.35,
            message="Current week calibration missing (last week exists)",
            details={
                "key_count": len(keys),
                "current_week": False,
                "last_week": True,
            },
        )
    else:
        return DriftCheckResult(
            name=name,
            score=0.7,
            message="No recent calibration found (current or last week)",
            details={
                "key_count": len(keys),
                "current_week": False,
                "last_week": False,
            },
        )


def check_self_assessment_score(
    redis_get: RedisGetFunc | None = None,
    drop_threshold: float = 0.05,
) -> DriftCheckResult:
    """Check if self-assessment score has dropped significantly.

    Compares the latest score against the previous score in history.
    A drop > drop_threshold contributes proportionally to drift.

    Score: 0.0 if score is stable or improved,
           0.0-0.4 proportional to the magnitude of drop beyond threshold.
    """
    get_fn = redis_get or _redis_get
    name = "self_assessment_score"

    if get_fn is None:
        return DriftCheckResult(
            name=name,
            score=0.0,
            message="Redis get unavailable - skipping self-assessment check",
            details={"available": False},
        )

    try:
        raw = get_fn(SELF_ASSESSMENT_KEY)
    except Exception as exc:
        logger.warning("Failed to get self-assessment: %s", exc)
        return DriftCheckResult(
            name=name,
            score=0.0,
            message=f"Redis get failed: {exc}",
            details={"error": str(exc)},
        )

    if raw is None:
        return DriftCheckResult(
            name=name,
            score=0.15,
            message="No self-assessment score found",
            details={"key": SELF_ASSESSMENT_KEY},
        )

    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        latest_score = float(data.get("overall_score", data.get("score", 0.0)))
        previous_score = float(
            data.get("previous_score", data.get("baseline", latest_score))
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return DriftCheckResult(
            name=name,
            score=0.1,
            message=f"Could not parse self-assessment data: {exc}",
            details={"raw_preview": str(raw)[:100]},
        )

    drop = previous_score - latest_score
    if drop <= drop_threshold:
        return DriftCheckResult(
            name=name,
            score=0.0,
            message=f"Self-assessment stable (drop={drop:.4f}, threshold={drop_threshold})",
            details={
                "latest_score": latest_score,
                "previous_score": previous_score,
                "drop": round(drop, 4),
            },
        )

    # Score proportional to severity of drop, capped at 0.4
    excess = drop - drop_threshold
    score = min(0.4, excess * 4.0)  # Each 0.025 excess = 0.1 drift
    return DriftCheckResult(
        name=name,
        score=round(score, 4),
        message=f"Self-assessment dropped by {drop:.4f} (threshold={drop_threshold})",
        details={
            "latest_score": latest_score,
            "previous_score": previous_score,
            "drop": round(drop, 4),
            "excess": round(excess, 4),
        },
    )


def check_deferred_items(
    redis_hgetall: RedisHGetAllFunc | None = None,
    warning_hours: int = 48,
    critical_hours: int = 96,
) -> DriftCheckResult:
    """Check if deferred items are approaching or past deadline.

    Items within warning_hours of deadline contribute 0.1 each (max 0.3).
    Items past critical_hours contribute 0.2 each (max 0.4).

    Score: 0.0 if no deferred items or all are within safe window.
    """
    hgetall_fn = redis_hgetall or _redis_hgetall
    name = "deferred_items"

    if hgetall_fn is None:
        return DriftCheckResult(
            name=name,
            score=0.0,
            message="Redis hgetall unavailable - skipping deferred items check",
            details={"available": False},
        )

    try:
        items = hgetall_fn(DEFERRED_ITEMS_KEY)
    except Exception as exc:
        logger.warning("Failed to get deferred items: %s", exc)
        return DriftCheckResult(
            name=name,
            score=0.0,
            message=f"Redis hgetall failed: {exc}",
            details={"error": str(exc)},
        )

    if not items:
        return DriftCheckResult(
            name=name,
            score=0.0,
            message="No deferred items found",
            details={"item_count": 0},
        )

    now = datetime.now(UTC)
    warning_delta = timedelta(hours=warning_hours)

    approaching_count = 0
    overdue_count = 0
    total_items = len(items)

    for _, item_data in items.items():
        try:
            data = json.loads(item_data) if isinstance(item_data, str) else item_data
            deadline_str = data.get("deadline", data.get("due_date", ""))
            if not deadline_str:
                continue
            deadline = datetime.fromisoformat(deadline_str)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)

            remaining = deadline - now
            if remaining < timedelta(0):
                overdue_count += 1
            elif remaining < warning_delta:
                approaching_count += 1
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    score = min(0.3, approaching_count * 0.1) + min(0.4, overdue_count * 0.2)

    if score == 0.0:
        msg = f"All {total_items} deferred items within safe window"
    else:
        parts = []
        if approaching_count:
            parts.append(f"{approaching_count} approaching deadline")
        if overdue_count:
            parts.append(f"{overdue_count} overdue")
        msg = f"Deferred items at risk: {', '.join(parts)} (of {total_items} total)"

    return DriftCheckResult(
        name=name,
        score=round(score, 4),
        message=msg,
        details={
            "total_items": total_items,
            "approaching": approaching_count,
            "overdue": overdue_count,
            "warning_hours": warning_hours,
            "critical_hours": critical_hours,
        },
    )


# ---------------------------------------------------------------------------
# Aggregate check
# ---------------------------------------------------------------------------


def check_all(
    threshold: float = 0.85,
    redis_get: RedisGetFunc | None = None,
    redis_scan: RedisScanFunc | None = None,
    redis_hgetall: RedisHGetAllFunc | None = None,
) -> DriftReport:
    """Run all drift checks and return aggregated report.

    Args:
        threshold: Drift score threshold (default 0.85). Exit code 1 if exceeded.
        redis_get: Optional Redis get function for dependency injection.
        redis_scan: Optional Redis scan function for dependency injection.
        redis_hgetall: Optional Redis hgetall function for dependency injection.

    Returns:
        DriftReport with overall score and individual check results.
    """
    checks: list[DriftCheckResult] = [
        check_calibration_exists(redis_scan=redis_scan),
        check_self_assessment_score(redis_get=redis_get),
        check_deferred_items(redis_hgetall=redis_hgetall),
    ]

    # Weighted aggregation: sum of individual scores
    # Max possible = 0.7 + 0.4 + 0.7 = 1.8, normalized to 0.0-1.0
    max_possible = 1.8
    raw_score = sum(c.score for c in checks)
    overall = min(1.0, raw_score / max_possible)

    return DriftReport(
        checks=checks,
        overall_score=round(overall, 4),
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Discord alert emission
# ---------------------------------------------------------------------------


async def emit_drift_alert(report: DriftReport) -> bool:
    """Emit a drift alert to Discord via the existing notification system.

    Returns True if notification was sent successfully.
    """
    try:
        from autonomous_cognition.discord_events import emit_autocog_event
        from governance.notifications.discord_notifier import DiscordNotifier

        notifier = DiscordNotifier()
        severity = "critical" if report.overall_score > 0.9 else "warning"
        check_details = {c.name: c.score for c in report.checks}

        return await emit_autocog_event(
            notifier=notifier,
            event_type="drift_detected",
            severity=severity,
            summary=f"Cognitive drift score: {report.overall_score:.4f} (threshold: {report.threshold})",
            impact="Autonomous cognition system may be degrading. Review deferred items and calibration status.",
            top_metrics={
                "drift_score": report.overall_score,
                "threshold": report.threshold,
                "checks_passed": sum(1 for c in report.checks if c.score == 0.0),
                "checks_failed": sum(1 for c in report.checks if c.score > 0.0),
                **check_details,
            },
            artifact_path=None,
            run_id=f"drift-{report.timestamp}",
        )
    except Exception as exc:
        logger.error("Failed to emit drift alert: %s", exc)
        return False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for drift detection.

    Returns exit code 0 if no drift, 1 if drift exceeds threshold.
    """
    parser = argparse.ArgumentParser(
        description="Metacognitive drift detection for autonomous cognition",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Drift score threshold (default: 0.85)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report without sending alerts or returning error code",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    report = check_all(threshold=args.threshold)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"Drift Score: {report.overall_score:.4f} / {report.threshold}")
        print(f"Drift Detected: {report.is_drift_detected}")
        print(f"Timestamp: {report.timestamp}")
        print()
        for check in report.checks:
            status = "OK" if check.score == 0.0 else f"WARN ({check.score:.4f})"
            print(f"  [{status}] {check.name}: {check.message}")
        print()

    if args.dry_run and not args.json:
        print("(dry-run mode - no alerts sent, exit code 0)")
        return 0

    if report.is_drift_detected:
        print(
            f"ALERT: Drift score {report.overall_score:.4f} exceeds threshold {report.threshold}"
        )

        # Best-effort async alert emission
        try:
            import asyncio

            asyncio.run(emit_drift_alert(report))
        except Exception as exc:
            logger.warning("Could not emit Discord alert: %s", exc)

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
