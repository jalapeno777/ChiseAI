#!/usr/bin/env python3
"""Autonomous Cognition Weekly Review Script.

Runs a full weekly review cycle including:
  1. Full self-assessment via AutonomousCognitionController
  2. Calibration: predicted vs actual comparison (Redis keys)
  3. Tempmemories review: read lessons.md, promote to Qdrant if needed
  4. Prevention rules review from lessons.md
  5. Writes summary to Redis: bmad:chiseai:autocog:weekly:{week}
  6. Emits Discord embed to #autocog-log

Usage:
    python3 scripts/autocog/weekly_review.py [--dry-run] [--force]
    python3 scripts/autocog/weekly_review.py --week 2026-W15
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

LESSONS_PATH = REPO_ROOT / "docs" / "tempmemories" / "lessons.md"
SELF_ASSESSMENTS_DIR = REPO_ROOT / "docs" / "governance" / "self_assessments"
CYCLES_DIR = REPO_ROOT / "_bmad-output" / "autocog" / "cycles"

REDIS_KEY_WEEKLY_PREFIX = "bmad:chiseai:autocog:weekly"
REDIS_KEY_SELF_ASSESSMENT = "bmad:chiseai:autocog:self_assessment:latest"
REDIS_KEY_SELF_ASSESSMENT_HISTORY = "bmad:chiseai:autocog:self_assessment:history"
REDIS_KEY_DEFERRED_ITEMS = "bmad:chiseai:autocog:deferred_items"
REDIS_KEY_CALIBRATION_PREFIX = "bmad:chiseai:metacog:calibration:agent:jarvis:weekly"

DISCORD_CHANNEL_AUTOLOG = "autocog-log"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CalibrationResult:
    """Result of calibration comparison."""

    total_predictions: int = 0
    matched_outcomes: int = 0
    unmatched_predictions: int = 0
    avg_confidence: float = 0.0
    avg_actual: float = 0.0
    calibration_error: float = 0.0
    bias_type: str = "none"
    pairs: list[dict] = field(default_factory=list)


@dataclass
class LessonsReview:
    """Result of lessons.md review."""

    total_lessons: int = 0
    new_this_week: int = 0
    prevention_rules: list[str] = field(default_factory=list)
    promoted_to_qdrant: int = 0
    qdrant_errors: int = 0


@dataclass
class DeferredItemsReview:
    """Result of deferred items review."""

    total_deferred: int = 0
    items: list[dict] = field(default_factory=list)
    stale_items: int = 0


@dataclass
class WeeklyReviewResult:
    """Complete weekly review result."""

    week_key: str = ""
    generated_at: str = ""
    overall_score: float | None = None
    dimensions: dict[str, float] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    calibration: CalibrationResult = field(default_factory=CalibrationResult)
    lessons_review: LessonsReview = field(default_factory=LessonsReview)
    deferred_items: DeferredItemsReview = field(default_factory=DeferredItemsReview)
    risks: list[str] = field(default_factory=list)
    status: str = "ok"


# ---------------------------------------------------------------------------
# Redis helpers (graceful degradation)
# ---------------------------------------------------------------------------

_redis_state_get: Any = None
_redis_state_set: Any = None
_redis_state_hgetall: Any = None
_redis_state_lrange: Any = None
_redis_state_llen: Any = None
_redis_state_scan_keys: Any = None

try:
    from tools.redis_state import (
        redis_state_get as _redis_state_get,
    )
    from tools.redis_state import (
        redis_state_hgetall as _redis_state_hgetall,
    )
    from tools.redis_state import (
        redis_state_llen as _redis_state_llen,
    )
    from tools.redis_state import (
        redis_state_lrange as _redis_state_lrange,
    )
    from tools.redis_state import (
        redis_state_scan_keys as _redis_state_scan_keys,
    )
    from tools.redis_state import (
        redis_state_set as _redis_state_set,
    )
except ImportError:
    logger.warning("tools.redis_state not available - Redis operations disabled")


def _redis_get(key: str) -> str | None:
    """Get a Redis key with graceful fallback."""
    if _redis_state_get is None:
        return None
    try:
        result = _redis_state_get(key)
        if result is None:
            return None
        return str(result)
    except Exception as e:
        logger.warning("Redis GET %s failed: %s", key, e)
        return None


def _redis_set(key: str, value: Any, expire: int | None = None) -> bool:
    """Set a Redis key with graceful fallback."""
    if _redis_state_set is None:
        return False
    try:
        _redis_state_set(key, value, expiration=expire)
        return True
    except Exception as e:
        logger.warning("Redis SET %s failed: %s", key, e)
        return False


def _redis_hgetall(name: str) -> dict[str, Any]:
    """Get all fields from a Redis hash."""
    if _redis_state_hgetall is None:
        return {}
    try:
        result = _redis_state_hgetall(name)
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            return json.loads(result)
        return {}
    except Exception as e:
        logger.warning("Redis HGETALL %s failed: %s", name, e)
        return {}


def _redis_lrange(name: str, start: int = 0, stop: int = -1) -> list:
    """Get range of a Redis list."""
    if _redis_state_lrange is None:
        return []
    try:
        result = _redis_state_lrange(name, start, stop)
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logger.warning("Redis LRANGE %s failed: %s", name, e)
        return []


def _redis_llen(name: str) -> int:
    """Get length of a Redis list."""
    if _redis_state_llen is None:
        return 0
    try:
        result = _redis_state_llen(name)
        return int(result) if result is not None else 0
    except Exception as e:
        logger.warning("Redis LLEN %s failed: %s", name, e)
        return 0


def _redis_scan(pattern: str) -> list[str]:
    """Scan for keys matching pattern."""
    if _redis_state_scan_keys is None:
        return []
    try:
        result = _redis_state_scan_keys(pattern)
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logger.warning("Redis SCAN %s failed: %s", pattern, e)
        return []


# ---------------------------------------------------------------------------
# Week key computation
# ---------------------------------------------------------------------------


def compute_week_key(dt: datetime | None = None) -> str:
    """Compute ISO week key like '2026-W15'."""
    if dt is None:
        dt = datetime.now(UTC)
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def parse_week_key(week_key: str) -> tuple[int, int]:
    """Parse '2026-W15' into (year, week)."""
    match = re.match(r"(\d{4})-W(\d{2})", week_key)
    if not match:
        raise ValueError(f"Invalid week key format: {week_key}. Expected YYYY-Www")
    return int(match.group(1)), int(match.group(2))


def week_key_to_redis_key(week_key: str) -> str:
    """Convert week key to Redis key."""
    return f"{REDIS_KEY_WEEKLY_PREFIX}:{week_key}"


# ---------------------------------------------------------------------------
# Self-assessment
# ---------------------------------------------------------------------------


def run_self_assessment() -> dict[str, Any]:
    """Run full self-assessment via AutonomousCognitionController.

    Falls back to reading latest from Redis if controller import fails.
    """
    try:
        from autonomous_cognition.controller import AutonomousCognitionController

        controller = AutonomousCognitionController()
        artifact, _ = controller.run_daily_self_assessment()
        return {
            "overall_score": artifact.overall_score,
            "dimensions": artifact.dimensions,
            "findings": artifact.findings,
            "recommendations": artifact.recommendations,
            "status": artifact.status,
            "source": "live",
        }
    except Exception as e:
        logger.warning("Live self-assessment failed, reading from Redis: %s", e)
        return _read_latest_assessment_from_redis()


def _read_latest_assessment_from_redis() -> dict[str, Any]:
    """Read the latest self-assessment from Redis as fallback."""
    payload = _redis_get(REDIS_KEY_SELF_ASSESSMENT)
    if payload is None:
        logger.warning("No self-assessment in Redis")
        return {
            "overall_score": None,
            "dimensions": {},
            "findings": ["No self-assessment data available"],
            "recommendations": ["Run a self-assessment cycle first"],
            "status": "unknown",
            "source": "redis_fallback",
        }

    try:
        data = json.loads(payload) if isinstance(payload, str) else payload
        return {
            "overall_score": data.get("overall_score"),
            "dimensions": data.get("dimensions", {}),
            "findings": data.get("findings", []),
            "recommendations": data.get("recommendations", []),
            "status": data.get("status", "unknown"),
            "source": "redis_fallback",
        }
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Failed to parse self-assessment: %s", e)
        return {
            "overall_score": None,
            "dimensions": {},
            "findings": ["Self-assessment data corrupt"],
            "recommendations": [],
            "status": "error",
            "source": "redis_fallback",
        }


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def run_calibration(week_key: str) -> CalibrationResult:
    """Run calibration comparison for the given week.

    Reads calibration keys matching
    bmad:chiseai:metacog:calibration:agent:jarvis:weekly:{week_key}:*
    and compares predicted vs actual values.
    """
    result = CalibrationResult()

    # Scan for calibration keys for this week
    pattern = f"{REDIS_KEY_CALIBRATION_PREFIX}:{week_key}:*"
    keys = _redis_scan(pattern)

    if not keys:
        logger.info("No calibration keys found for %s", week_key)
        return result

    pairs = []
    confidences = []
    actuals = []

    for key in keys:
        data = _redis_hgetall(key)
        if not data:
            continue

        confidence = data.get("confidence")
        actual = data.get("actual") or data.get("outcome")
        predicted = data.get("predicted") or data.get("prediction")

        if confidence is not None:
            try:
                confidence = float(confidence)
                confidences.append(confidence)
            except (ValueError, TypeError):
                continue

        if actual is not None:
            try:
                actual_val = float(actual)
                actuals.append(actual_val)
            except (ValueError, TypeError):
                # Boolean-like outcomes
                if isinstance(actual, str) and actual.lower() in (
                    "true",
                    "1",
                    "success",
                ):
                    actuals.append(1.0)
                elif isinstance(actual, str) and actual.lower() in (
                    "false",
                    "0",
                    "failure",
                ):
                    actuals.append(0.0)

        pair_dict = {
            "key": key,
            "confidence": confidence,
            "actual": actual,
            "predicted": predicted,
        }
        pairs.append(pair_dict)

    # Match predictions to outcomes
    result.total_predictions = len(confidences)
    result.matched_outcomes = min(len(confidences), len(actuals))
    result.unmatched_predictions = result.total_predictions - result.matched_outcomes
    result.pairs = pairs

    if confidences:
        result.avg_confidence = round(sum(confidences) / len(confidences), 3)

    if actuals:
        result.avg_actual = round(sum(actuals) / len(actuals), 3)

    # Compute calibration error
    n = min(len(confidences), len(actuals))
    if n > 0:
        errors = [abs(confidences[i] - actuals[i]) for i in range(n)]
        result.calibration_error = round(sum(errors) / n, 4)

        # Determine bias type
        avg_conf = sum(confidences[:n]) / n
        avg_act = sum(actuals[:n]) / n
        if avg_conf > avg_act + 0.1:
            result.bias_type = "overconfidence"
        elif avg_conf < avg_act - 0.1:
            result.bias_type = "underconfidence"
        else:
            result.bias_type = "none"

    return result


# ---------------------------------------------------------------------------
# Lessons review
# ---------------------------------------------------------------------------

_LESSON_PATTERN = re.compile(
    r"LESSON\s*\n"
    r"(-\s*id:\s*(?P<id>[^\n]+)\s*\n)?"
    r".*?"
    r"-\s*actionable_rule:\s*(?P<rule>[^\n]+)",
    re.DOTALL,
)

_LESSON_BLOCK_PATTERN = re.compile(
    r"```text\s*\n(LESSON[\s\S]*?)```",
    re.MULTILINE,
)


def run_lessons_review(week_start: datetime) -> LessonsReview:
    """Review lessons.md for new lessons and prevention rules.

    Returns parsed lessons and prevention rules from the current lessons file.
    """
    result = LessonsReview()

    if not LESSONS_PATH.exists():
        logger.warning("lessons.md not found at %s", LESSONS_PATH)
        return result

    try:
        content = LESSONS_PATH.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Failed to read lessons.md: %s", e)
        return result

    # Extract all LESSON blocks
    lesson_blocks = _LESSON_BLOCK_PATTERN.findall(content)
    result.total_lessons = len(lesson_blocks)

    for block in lesson_blocks:
        # Check if lesson was added this week
        added_match = re.search(r"-\s*added_utc:\s*(.+)", block)
        if added_match:
            try:
                added_str = added_match.group(1).strip()
                added_dt = datetime.fromisoformat(added_str.replace("Z", "+00:00"))
                if added_dt >= week_start:
                    result.new_this_week += 1
            except (ValueError, IndexError):
                pass

        # Extract prevention rules (actionable_rule)
        rule_match = re.search(r"-\s*actionable_rule:\s*(.+)", block)
        if rule_match:
            rule_text = rule_match.group(1).strip()
            if rule_text:
                result.prevention_rules.append(rule_text)

    return result


def promote_lessons_to_qdrant(lessons_review: LessonsReview) -> int:
    """Promote new lessons to Qdrant for long-term recall.

    Returns count of successfully promoted lessons.
    """
    promoted = 0

    if lessons_review.new_this_week == 0:
        return promoted

    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host="host.docker.internal", port=6333)
    except Exception as e:
        logger.warning("Qdrant client unavailable: %s", e)
        lessons_review.qdrant_errors = lessons_review.new_this_week
        return promoted

    # Re-read lessons to get full content of new lessons
    if not LESSONS_PATH.exists():
        return promoted

    try:
        content = LESSONS_PATH.read_text(encoding="utf-8")
        lesson_blocks = _LESSON_BLOCK_PATTERN.findall(content)
    except OSError:
        return promoted

    week_start = datetime.now(UTC) - timedelta(days=7)

    for block in lesson_blocks:
        added_match = re.search(r"-\s*added_utc:\s*(.+)", block)
        if not added_match:
            continue
        try:
            added_str = added_match.group(1).strip()
            added_dt = datetime.fromisoformat(added_str.replace("Z", "+00:00"))
            if added_dt < week_start:
                continue
        except (ValueError, IndexError):
            continue

        id_match = re.search(r"-\s*id:\s*(.+)", block)
        lesson_id = id_match.group(1).strip() if id_match else "unknown"

        try:
            # Simple deterministic embedding placeholder
            import hashlib

            vector = [
                (hashlib.md5(f"{lesson_id}-{i}".encode()).digest()[0] / 255.0) * 2 - 1
                for i in range(384)
            ]
            client.upsert(
                collection_name="ChiseAI",
                points=[
                    {
                        "id": hashlib.sha256(lesson_id.encode()).hexdigest()[:32],
                        "vector": vector,
                        "payload": {
                            "type": "lesson",
                            "lesson_id": lesson_id,
                            "content": block.strip(),
                            "promoted_at": datetime.now(UTC).isoformat(),
                        },
                    }
                ],
            )
            promoted += 1
        except Exception as e:
            logger.warning("Failed to promote lesson %s: %s", lesson_id, e)
            lessons_review.qdrant_errors += 1

    return promoted


# ---------------------------------------------------------------------------
# Deferred items review
# ---------------------------------------------------------------------------


def run_deferred_items_review() -> DeferredItemsReview:
    """Review deferred items from Redis hash."""
    result = DeferredItemsReview()

    data = _redis_hgetall(REDIS_KEY_DEFERRED_ITEMS)
    if not data:
        logger.info("No deferred items found")
        return result

    result.total_deferred = len(data)
    now = datetime.now(UTC)
    stale_threshold = timedelta(days=14)

    for item_key, item_value in data.items():
        item_dict = {}
        if isinstance(item_value, str):
            try:
                item_dict = json.loads(item_value)
            except json.JSONDecodeError:
                item_dict = {"raw": item_value}
        elif isinstance(item_value, dict):
            item_dict = item_value

        item_dict["key"] = item_key
        result.items.append(item_dict)

        # Check staleness
        deferred_at = item_dict.get("deferred_at") or item_dict.get("created_at")
        if deferred_at:
            try:
                deferred_dt = datetime.fromisoformat(
                    str(deferred_at).replace("Z", "+00:00")
                )
                if now - deferred_dt > stale_threshold:
                    result.stale_items += 1
            except (ValueError, TypeError):
                pass

    return result


# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------


def assess_risks(
    assessment: dict[str, Any],
    calibration: CalibrationResult,
    deferred: DeferredItemsReview,
) -> list[str]:
    """Assess risks from review data."""
    risks = []

    # Score-based risks
    score = assessment.get("overall_score")
    if score is not None:
        if score < 0.5:
            risks.append(
                "CRITICAL: Self-assessment score below 0.5 - system health degraded"
            )
        elif score < 0.7:
            risks.append(
                "WARNING: Self-assessment score below 0.7 - monitoring required"
            )

    # Calibration risks
    if calibration.calibration_error > 0.2:
        risks.append(
            f"HIGH: Calibration error {calibration.calibration_error:.2f} exceeds threshold 0.2 "
            f"(bias: {calibration.bias_type})"
        )
    elif calibration.calibration_error > 0.1:
        risks.append(
            f"MEDIUM: Calibration error {calibration.calibration_error:.2f} "
            f"(bias: {calibration.bias_type})"
        )

    # Deferred items risks
    if deferred.stale_items > 0:
        risks.append(
            f"MEDIUM: {deferred.stale_items} deferred item(s) older than 14 days need attention"
        )

    if deferred.total_deferred > 10:
        risks.append(
            f"WARNING: {deferred.total_deferred} total deferred items - review backlog"
        )

    return risks


# ---------------------------------------------------------------------------
# Discord notification
# ---------------------------------------------------------------------------


def build_discord_embed(result: WeeklyReviewResult) -> dict[str, Any]:
    """Build Discord embed payload for weekly review."""
    score_str = (
        f"{result.overall_score:.2f}" if result.overall_score is not None else "N/A"
    )
    cal_error_str = f"{result.calibration.calibration_error:.3f}"

    # Dimension strings
    dim_lines = []
    for dim_name, dim_val in sorted(result.dimensions.items()):
        dim_lines.append(f"  {dim_name}: {dim_val:.2f}")
    dim_text = "\n".join(dim_lines) if dim_lines else "N/A"

    # Risk level
    risk_count = len(result.risks)
    if risk_count == 0:
        risk_emoji = "\u2705"
    elif any(r.startswith("CRITICAL") for r in result.risks):
        risk_emoji = "\U0001f534"
    elif any(r.startswith("HIGH") for r in result.risks):
        risk_emoji = "\U0001f7e1"
    else:
        risk_emoji = "\U0001f7e2"

    # Build findings (truncated)
    findings_text = "\n".join(f"- {f}" for f in result.findings[:5])
    if len(result.findings) > 5:
        findings_text += f"\n- ... and {len(result.findings) - 5} more"

    # Build recommendations (truncated)
    recs_text = "\n".join(f"- {r}" for r in result.recommendations[:5])
    if len(result.recommendations) > 5:
        recs_text += f"\n- ... and {len(result.recommendations) - 5} more"

    embed = {
        "title": f"\U0001f4ca Weekly Review: {result.week_key}",
        "description": "Autonomous Cognition Weekly Review",
        "color": 0x5865F2,
        "fields": [
            {"name": "Overall Score", "value": score_str, "inline": True},
            {"name": "Calibration Error", "value": cal_error_str, "inline": True},
            {"name": "Bias", "value": result.calibration.bias_type, "inline": True},
            {
                "name": "New Lessons",
                "value": str(result.lessons_review.new_this_week),
                "inline": True,
            },
            {
                "name": "Deferred Items",
                "value": str(result.deferred_items.total_deferred),
                "inline": True,
            },
            {
                "name": "Risks",
                "value": f"{risk_emoji} {risk_count}",
                "inline": True,
            },
            {"name": "Dimensions", "value": dim_text, "inline": False},
            {"name": "Findings", "value": findings_text or "None", "inline": False},
            {"name": "Recommendations", "value": recs_text or "None", "inline": False},
        ],
        "footer": {
            "text": f"Generated at {result.generated_at} | Status: {result.status}"
        },
        "timestamp": result.generated_at,
    }

    # Add risk details if any
    if result.risks:
        risk_text = "\n".join(f"- {r}" for r in result.risks[:3])
        if len(result.risks) > 3:
            risk_text += f"\n- ... and {len(result.risks) - 3} more"
        embed["fields"].append(
            {"name": "\u26a0\ufe0f Risk Details", "value": risk_text, "inline": False}
        )

    return embed


def emit_discord_notification(result: WeeklyReviewResult) -> bool:
    """Emit Discord notification for weekly review."""
    try:
        from governance.notifications.discord_notifier import DiscordNotifier

        notifier = DiscordNotifier()
        embed = build_discord_embed(result)
        # Use the autocog event channel
        return bool(
            notifier._send_embed(channel_name=DISCORD_CHANNEL_AUTOLOG, embed=embed)
        )
    except Exception as e:
        logger.warning("Discord notification failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Redis persistence
# ---------------------------------------------------------------------------


def persist_weekly_result(result: WeeklyReviewResult) -> bool:
    """Persist weekly review result to Redis."""
    redis_key = week_key_to_redis_key(result.week_key)
    payload = json.dumps(asdict(result), default=str)

    # Store with 90-day TTL
    return _redis_set(redis_key, payload, expire=86400 * 90)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def run_weekly_review(
    week_key: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> WeeklyReviewResult:
    """Run the complete weekly review cycle.

    Args:
        week_key: ISO week key (e.g., '2026-W15'). Defaults to current week.
        dry_run: If True, run without persisting to Redis or sending Discord.
        force: If True, run even if a review for this week already exists.

    Returns:
        WeeklyReviewResult with all review data.
    """
    if week_key is None:
        week_key = compute_week_key()

    result = WeeklyReviewResult(
        week_key=week_key,
        generated_at=datetime.now(UTC).isoformat(),
    )

    # Check for existing review (skip unless --force)
    if not force and not dry_run:
        existing = _redis_get(week_key_to_redis_key(week_key))
        if existing is not None:
            logger.info(
                "Weekly review already exists for %s. Use --force to override.",
                week_key,
            )
            try:
                result = WeeklyReviewResult(**json.loads(existing))
                result.findings.append(
                    "Review loaded from cache. Use --force to regenerate."
                )
                return result
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to parse cached review, regenerating")

    # Compute week start for lesson filtering
    year, week_num = parse_week_key(week_key)
    # ISO week: Monday is day 1
    week_start = datetime.strptime(f"{year}-{week_num}-1", "%Y-%W-%w").replace(
        tzinfo=UTC
    )

    logger.info(
        "Running weekly review for %s (dry_run=%s, force=%s)", week_key, dry_run, force
    )

    # 1. Self-assessment
    logger.info("Step 1: Running self-assessment...")
    assessment = run_self_assessment()
    result.overall_score = assessment.get("overall_score")
    result.dimensions = assessment.get("dimensions", {})
    result.findings.extend(assessment.get("findings", []))
    result.recommendations.extend(assessment.get("recommendations", []))
    result.status = assessment.get("status", "unknown")

    # 2. Calibration
    logger.info("Step 2: Running calibration...")
    result.calibration = run_calibration(week_key)

    # 3. Lessons review
    logger.info("Step 3: Reviewing lessons...")
    result.lessons_review = run_lessons_review(week_start)

    # 4. Promote lessons to Qdrant (skip in dry-run)
    if not dry_run:
        logger.info("Step 4: Promoting lessons to Qdrant...")
        result.lessons_review.promoted_to_qdrant = promote_lessons_to_qdrant(
            result.lessons_review
        )

    # 5. Deferred items review
    logger.info("Step 5: Reviewing deferred items...")
    result.deferred_items = run_deferred_items_review()

    # 6. Risk assessment
    logger.info("Step 6: Assessing risks...")
    result.risks = assess_risks(assessment, result.calibration, result.deferred_items)

    # Determine final status
    if any(r.startswith("CRITICAL") for r in result.risks):
        result.status = "critical"
    elif any(r.startswith("HIGH") for r in result.risks):
        result.status = "at_risk"

    # 7. Persist to Redis (skip in dry-run)
    if not dry_run:
        logger.info("Step 7: Persisting to Redis...")
        persist_weekly_result(result)

    # 8. Discord notification (skip in dry-run)
    if not dry_run:
        logger.info("Step 8: Sending Discord notification...")
        emit_discord_notification(result)

    logger.info("Weekly review complete for %s. Status: %s", week_key, result.status)
    return result


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run autonomous cognition weekly review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 scripts/autocog/weekly_review.py              # Current week
    python3 scripts/autocog/weekly_review.py --week 2026-W15
    python3 scripts/autocog/weekly_review.py --dry-run     # Preview only
    python3 scripts/autocog/weekly_review.py --force       # Override existing
        """,
    )
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="ISO week key (e.g., 2026-W15). Default: current week.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run without persisting to Redis or sending Discord notifications.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force run even if a review for this week already exists.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output result as JSON to stdout.",
    )

    args = parser.parse_args()

    # Validate week key if provided
    if args.week:
        try:
            parse_week_key(args.week)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = run_weekly_review(
        week_key=args.week,
        dry_run=args.dry_run,
        force=args.force,
    )

    if args.json:
        print(json.dumps(asdict(result), default=str, indent=2))
    else:
        # Human-readable output
        score_str = (
            f"{result.overall_score:.2f}" if result.overall_score is not None else "N/A"
        )
        print(f"\n{'=' * 60}")
        print(f"  Weekly Review: {result.week_key}")
        print(f"  Status: {result.status}")
        print(f"  Generated: {result.generated_at}")
        print(f"{'=' * 60}")
        print(f"\n  Overall Score: {score_str}")
        print("\n  Dimensions:")
        for dim, val in sorted(result.dimensions.items()):
            print(f"    {dim}: {val:.2f}")
        print("\n  Calibration:")
        print(f"    Error: {result.calibration.calibration_error:.4f}")
        print(f"    Bias: {result.calibration.bias_type}")
        print(f"    Predictions: {result.calibration.total_predictions}")
        print(f"    Matched: {result.calibration.matched_outcomes}")
        print("\n  Lessons:")
        print(f"    Total: {result.lessons_review.total_lessons}")
        print(f"    New this week: {result.lessons_review.new_this_week}")
        print(f"    Prevention rules: {len(result.lessons_review.prevention_rules)}")
        if not args.dry_run:
            print(f"    Promoted to Qdrant: {result.lessons_review.promoted_to_qdrant}")
        print(f"\n  Deferred Items: {result.deferred_items.total_deferred}")
        print(f"    Stale (>14d): {result.deferred_items.stale_items}")
        print("\n  Findings:")
        for f in result.findings[:10]:
            print(f"    - {f}")
        print("\n  Recommendations:")
        for r in result.recommendations[:10]:
            print(f"    - {r}")
        if result.risks:
            print("\n  Risks:")
            for risk in result.risks:
                print(f"    {risk}")
        print(f"\n{'=' * 60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
