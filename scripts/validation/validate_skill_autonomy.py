#!/usr/bin/env python3
"""Validate and record autonomous skill coverage/effectiveness.

Core policy:
- Missing recommended skills are warning-only (non-blocking by default).
- Record gaps as KPI signals for weekly reflection and roadmap decisions.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

TASK_MAP_PATH = Path("docs/metrics/skill-task-map.yaml")
SKILLS_DIR = Path(".opencode/skills")
TEMPMEM_DIR = Path("docs/tempmemories")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _week_id(dt: datetime | None = None) -> str:
    use_dt = dt or _utc_now()
    y, w, _ = use_dt.isocalendar()
    return f"{y}-W{w:02d}"


def _safe_story(story_id: str) -> str:
    return story_id.replace("/", "-").replace(" ", "-")


def _load_task_map(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"task_classes": {}, "default_task_class": "unclassified"}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {"task_classes": {}, "default_task_class": "unclassified"}
    data.setdefault("task_classes", {})
    data.setdefault("default_task_class", "unclassified")
    return data


def _discover_skills(skills_dir: Path) -> set[str]:
    if not skills_dir.exists():
        return set()
    found: set[str] = set()
    for child in skills_dir.iterdir():
        if child.is_dir() and (child / "SKILL.md").exists():
            found.add(child.name)
    return found


def _coverage_status(recommended: list[str], missing: list[str]) -> str:
    if not recommended:
        return "none"
    if not missing:
        return "full"
    if len(missing) == len(recommended):
        return "none"
    return "partial"


def _redis_client():
    try:
        import redis

        host = os.getenv("REDIS_HOST", "host.docker.internal")
        port = int(os.getenv("REDIS_PORT", "6380"))
        db = int(os.getenv("REDIS_DB", "0"))
        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        client.ping()
        return client
    except Exception:
        return None


def _persist_redis(payload: dict[str, Any], missing: list[str], task_class: str) -> tuple[bool, str | None]:
    client = _redis_client()
    if client is None:
        return False, "redis_unavailable"

    story_id = payload["story_id"]
    week = payload["week_id"]

    key_story = f"bmad:chiseai:skills:coverage:story:{story_id}"
    key_gaps = f"bmad:chiseai:skills:gaps:task_class:{task_class}:weekly:{week}"
    key_eff = None
    skill_name = payload.get("skill_name")
    if skill_name:
        key_eff = f"bmad:chiseai:skills:effectiveness:skill:{skill_name}:weekly:{week}"

    def _safe(v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    client.hset(
        key_story,
        mapping={
            "story_id": story_id,
            "task_class": task_class,
            "coverage_status": payload["coverage_status"],
            "recommended_skills": json.dumps(payload["recommended_skills"]),
            "available_skills": json.dumps(payload["available_skills"]),
            "missing_skills": json.dumps(payload["missing_skills"]),
            "fallback_used": str(payload["fallback_used"]).lower(),
            "impact_estimate": payload["impact_estimate"],
            "skill_name": _safe(payload.get("skill_name", "")),
            "skill_version": _safe(payload.get("skill_version", "")),
            "quality_score": _safe(payload.get("quality_score", "")),
            "cycle_time_minutes": _safe(payload.get("cycle_time_minutes", "")),
            "rework_flag": str(payload.get("rework_flag", False)).lower(),
            "regression_flag": str(payload.get("regression_flag", False)).lower(),
            "recorded_at": payload["generated_at_utc"],
        },
    )
    client.expire(key_story, 60 * 60 * 24 * 30)

    client.hincrby(key_gaps, "stories_total", 1)
    if missing:
        client.hincrby(key_gaps, "stories_with_missing_skills", 1)
        for skill in missing:
            client.hincrby(key_gaps, f"missing:{skill}", 1)
    client.expire(key_gaps, 60 * 60 * 24 * 90)

    if key_eff:
        client.hincrby(key_eff, "events_total", 1)
        if payload.get("quality_score") is not None:
            scaled = int(round(float(payload["quality_score"]) * 1000))
            client.hincrby(key_eff, "quality_score_milli_sum", scaled)
        if payload.get("cycle_time_minutes") is not None:
            client.hincrby(key_eff, "cycle_time_minutes_sum", int(payload["cycle_time_minutes"]))
        if payload.get("rework_flag"):
            client.hincrby(key_eff, "rework_events", 1)
        if payload.get("regression_flag"):
            client.hincrby(key_eff, "regression_events", 1)
        client.expire(key_eff, 60 * 60 * 24 * 90)

    return True, None


def _persist_markdown(payload: dict[str, Any]) -> Path:
    TEMPMEM_DIR.mkdir(parents=True, exist_ok=True)
    ts = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    out = TEMPMEM_DIR / f"skill-autonomy-{_safe_story(payload['story_id'])}-{ts}.md"

    fm = {
        "story_id": payload["story_id"],
        "task_class": payload["task_class"],
        "coverage_status": payload["coverage_status"],
        "generated_at_utc": payload["generated_at_utc"],
        "week_id": payload["week_id"],
        "needs_manual_qdrant_import": True,
    }

    body = {
        "recommended_skills": payload["recommended_skills"],
        "available_skills": payload["available_skills"],
        "missing_skills": payload["missing_skills"],
        "fallback_used": payload["fallback_used"],
        "impact_estimate": payload["impact_estimate"],
        "skill_name": payload.get("skill_name"),
        "skill_version": payload.get("skill_version"),
        "quality_score": payload.get("quality_score"),
        "cycle_time_minutes": payload.get("cycle_time_minutes"),
        "rework_flag": payload.get("rework_flag", False),
        "regression_flag": payload.get("regression_flag", False),
    }

    content = "---\n"
    content += yaml.safe_dump(fm, sort_keys=False)
    content += "---\n\n"
    content += "## Skill Autonomy KPI Event\n\n"
    content += yaml.safe_dump(body, sort_keys=False)

    out.write_text(content, encoding="utf-8")
    return out


@dataclass
class Outcome:
    payload: dict[str, Any]
    warnings: list[str]


def evaluate(args: argparse.Namespace) -> Outcome:
    warnings: list[str] = []

    task_map = _load_task_map(Path(args.task_map_path))
    task_classes = task_map.get("task_classes", {})

    task_class = args.task_class or task_map.get("default_task_class", "unclassified")
    if task_class not in task_classes:
        warnings.append(
            f"task_class '{task_class}' not found in task map; treating as unclassified (non-blocking)"
        )

    recommended = []
    if task_class in task_classes:
        recommended = list(task_classes[task_class].get("recommended_skills", []))

    available_set = _discover_skills(Path(args.skills_dir))
    available = sorted([s for s in recommended if s in available_set])
    missing = sorted([s for s in recommended if s not in available_set])

    coverage_status = _coverage_status(recommended, missing)
    fallback_used = bool(missing)

    payload: dict[str, Any] = {
        "story_id": args.story_id,
        "task_class": task_class,
        "recommended_skills": recommended,
        "available_skills": available,
        "missing_skills": missing,
        "coverage_status": coverage_status,
        "fallback_used": fallback_used,
        "impact_estimate": args.impact_estimate,
        "skill_name": args.skill_name,
        "skill_version": args.skill_version,
        "quality_score": args.quality_score,
        "cycle_time_minutes": args.cycle_time_minutes,
        "rework_flag": args.rework_flag,
        "regression_flag": args.regression_flag,
        "generated_at_utc": _iso(),
        "week_id": _week_id(),
    }

    if missing:
        warnings.append(
            "missing recommended skills detected (non-blocking): " + ", ".join(missing)
        )

    redis_ok, redis_reason = _persist_redis(payload, missing, task_class)
    payload["redis_persisted"] = redis_ok
    if not redis_ok:
        warnings.append(f"redis write skipped: {redis_reason}")

    md_path = _persist_markdown(payload)
    payload["markdown_artifact"] = str(md_path)

    return Outcome(payload=payload, warnings=warnings)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Evaluate autonomous skill coverage/effectiveness")
    ap.add_argument("--story-id", required=True, help="Story identifier")
    ap.add_argument("--task-class", default="", help="Task class from task map")
    ap.add_argument(
        "--impact-estimate",
        default="low",
        choices=["none", "low", "medium", "high"],
        help="Estimated impact from missing skills",
    )
    ap.add_argument("--quality-score", type=float, default=None, help="Optional 0.0-1.0 quality score")
    ap.add_argument("--cycle-time-minutes", type=int, default=None, help="Optional cycle time in minutes")
    ap.add_argument("--skill-name", default="", help="Optional active skill name for effectiveness attribution")
    ap.add_argument("--skill-version", default="", help="Optional active skill version")
    ap.add_argument("--rework-flag", action="store_true", help="Mark event as rework")
    ap.add_argument("--regression-flag", action="store_true", help="Mark event as regression")
    ap.add_argument("--task-map-path", default=str(TASK_MAP_PATH))
    ap.add_argument("--skills-dir", default=str(SKILLS_DIR))
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Fail when no recommended skills exist for task class (still does not fail for missing skills)",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    out = evaluate(args)

    print("SKILL_AUTONOMY_RESULT")
    print(yaml.safe_dump(out.payload, sort_keys=False).strip())

    for warning in out.warnings:
        print(f"WARNING: {warning}")

    # Non-blocking default: missing recommended skills do not fail execution.
    if args.strict and not out.payload.get("recommended_skills"):
        print("ERROR: strict mode enabled and task class has no recommended skills configured")
        return 1

    if args.quality_score is not None and not (0.0 <= args.quality_score <= 1.0):
        print("ERROR: --quality-score must be within [0.0, 1.0]")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
