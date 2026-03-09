#!/usr/bin/env python3
"""Run autonomous skills instrumentation ticks with performance safeguards.

Modes:
- start/close: capture per-story skill coverage/effectiveness KPI event
- weekly: aggregate recent KPI artifacts into a weekly report
- all: start/close (if story_id provided) + weekly

Policy:
- Missing skills are non-blocking signals, never execution blockers.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import random
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
try:
    import fcntl
except Exception:  # pragma: no cover
    fcntl = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = PROJECT_ROOT / "scripts" / "validation" / "validate_skill_autonomy.py"
TEMPMEM_DIR = PROJECT_ROOT / "docs" / "tempmemories"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "skill_autonomy.yaml"


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def week_id(dt: datetime | None = None) -> str:
    y, w, _ = (dt or utc_now()).isocalendar()
    return f"{y}-W{w:02d}"


def parse_yaml_file(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return default


def redis_client():
    try:
        import os
        import redis

        port = int(
            os.getenv("REDIS_PORT")
            or os.getenv("CHISE_REDIS_PORT")
            or os.getenv("ACP_REDIS_PORT")
            or "6380"
        )
        db = int(os.getenv("REDIS_DB", "0"))
        hosts = [
            os.getenv("REDIS_HOST"),
            os.getenv("CHISE_REDIS_HOST"),
            os.getenv("ACP_REDIS_HOST"),
            "chiseai-redis",
            "host.docker.internal",
            "localhost",
        ]
        hosts = [h for i, h in enumerate(hosts) if h and h not in hosts[:i]]
        for host in hosts:
            try:
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
                continue
        return None
    except Exception:
        return None


def read_frontmatter_and_body(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm_raw = text[4:end]
    body = text[end + 5 :]
    fm = yaml.safe_load(fm_raw) or {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def read_kpi_body_yaml(body: str) -> dict[str, Any]:
    marker = "## Skill Autonomy KPI Event"
    if marker not in body:
        return {}
    chunk = body.split(marker, 1)[1].strip()
    try:
        data = yaml.safe_load(chunk) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@dataclass
class TickResult:
    ok: bool
    mode: str
    details: dict[str, Any]
    warnings: list[str]


def run_eval_tick(
    *,
    story_id: str,
    task_class: str,
    impact_estimate: str,
    quality_score: float | None,
    cycle_time_minutes: int | None,
    rework_flag: bool,
    regression_flag: bool,
    skill_name: str,
    skill_version: str,
    command_timeout_seconds: int,
    dry_run: bool,
) -> TickResult:
    cmd = [
        "python3",
        str(VALIDATOR),
        f"--story-id={story_id}",
        f"--task-class={task_class}",
        f"--impact-estimate={impact_estimate}",
    ]
    if quality_score is not None:
        cmd.append(f"--quality-score={quality_score}")
    if cycle_time_minutes is not None:
        cmd.append(f"--cycle-time-minutes={cycle_time_minutes}")
    if rework_flag:
        cmd.append("--rework-flag")
    if regression_flag:
        cmd.append("--regression-flag")
    if skill_name:
        cmd.append(f"--skill-name={skill_name}")
    if skill_version:
        cmd.append(f"--skill-version={skill_version}")

    if dry_run:
        return TickResult(
            ok=True,
            mode="eval",
            details={"dry_run": True, "command": " ".join(cmd)},
            warnings=[],
        )

    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=command_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return TickResult(
            ok=False,
            mode="eval",
            details={"error": f"validator timeout after {command_timeout_seconds}s"},
            warnings=["eval tick timed out (non-blocking)"],
        )

    details = {
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    warnings: list[str] = []
    if proc.returncode != 0:
        warnings.append("validator returned non-zero (non-blocking in autonomy tick)")
    return TickResult(ok=True, mode="eval", details=details, warnings=warnings)


def run_weekly_tick(
    *,
    lookback_days: int,
    max_artifacts_scan: int,
    missing_skill_rate_escalation: float,
    repeated_missing_skill_story_count: int,
    backlog_enabled: bool,
    backlog_output_dir: Path,
    backlog_redis_queue_key: str,
    dry_run: bool,
) -> TickResult:
    now = utc_now()
    cutoff = now - timedelta(days=lookback_days)
    files = sorted(TEMPMEM_DIR.glob("skill-autonomy-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    files = [p for p in files if "skill-autonomy-weekly-" not in p.name][:max_artifacts_scan]

    total = 0
    coverage_counter: Counter[str] = Counter()
    task_class_total: Counter[str] = Counter()
    task_class_missing: Counter[str] = Counter()
    missing_skill_counter: Counter[str] = Counter()

    skill_events: Counter[str] = Counter()
    skill_quality_sum: defaultdict[str, float] = defaultdict(float)
    skill_quality_n: Counter[str] = Counter()
    skill_rework: Counter[str] = Counter()
    skill_regression: Counter[str] = Counter()

    for path in files:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if mtime < cutoff:
            continue

        fm, body = read_frontmatter_and_body(path)
        payload = read_kpi_body_yaml(body)

        task_class = str(fm.get("task_class", payload.get("task_class", "unclassified")))
        coverage = str(fm.get("coverage_status", payload.get("coverage_status", "none")))
        missing = payload.get("missing_skills", []) or []

        total += 1
        coverage_counter[coverage] += 1
        task_class_total[task_class] += 1
        if missing:
            task_class_missing[task_class] += 1
            for skill in missing:
                missing_skill_counter[str(skill)] += 1

        skill_name = str(payload.get("skill_name") or "").strip()
        if skill_name:
            skill_events[skill_name] += 1
            q = payload.get("quality_score")
            if isinstance(q, (int, float)):
                skill_quality_sum[skill_name] += float(q)
                skill_quality_n[skill_name] += 1
            if bool(payload.get("rework_flag", False)):
                skill_rework[skill_name] += 1
            if bool(payload.get("regression_flag", False)):
                skill_regression[skill_name] += 1

    missing_rate_by_class: dict[str, float] = {}
    for tclass, cnt in task_class_total.items():
        missing_rate_by_class[tclass] = (task_class_missing[tclass] / cnt) if cnt else 0.0

    effectiveness_summary: dict[str, Any] = {}
    for skill, n in skill_events.items():
        qn = skill_quality_n[skill]
        effectiveness_summary[skill] = {
            "events": n,
            "avg_quality_score": (skill_quality_sum[skill] / qn) if qn else None,
            "rework_rate": (skill_rework[skill] / n) if n else 0.0,
            "regression_rate": (skill_regression[skill] / n) if n else 0.0,
        }

    report = {
        "week_id": week_id(now),
        "generated_at_utc": iso(now),
        "lookback_days": lookback_days,
        "events_analyzed": total,
        "coverage_distribution": dict(coverage_counter),
        "missing_skill_rate_by_task_class": missing_rate_by_class,
        "top_missing_skills": [
            {"skill": skill, "count": count}
            for skill, count in missing_skill_counter.most_common(10)
        ],
        "skill_effectiveness_summary": effectiveness_summary,
        "recommended_actions": [],
        "backlog_candidates": [],
    }

    if total == 0:
        report["recommended_actions"].append("No skill autonomy artifacts in lookback window; keep instrumentation enabled.")
    else:
        report["recommended_actions"].append("Prioritize hardening skills with highest rework/regression rates.")
        report["recommended_actions"].append("Only add new skills when missing-skill patterns are repeated over time.")

    candidates: list[dict[str, Any]] = []
    candidate_id = 1

    for skill, count in missing_skill_counter.most_common():
        if count < repeated_missing_skill_story_count:
            continue
        candidate = {
            "candidate_id": f"SKILL-GAP-{week_id(now)}-{candidate_id:02d}",
            "skill_name": skill,
            "trigger": "repeated_missing_skill_count",
            "count": count,
            "threshold": repeated_missing_skill_story_count,
            "priority": "high" if count >= repeated_missing_skill_story_count * 2 else "medium",
            "recommended_action": f"Create or import skill '{skill}' and add evaluation cases.",
        }
        candidates.append(candidate)
        candidate_id += 1

    for task_class, rate in sorted(missing_rate_by_class.items(), key=lambda kv: kv[1], reverse=True):
        if rate < missing_skill_rate_escalation:
            continue
        candidate = {
            "candidate_id": f"SKILL-GAP-{week_id(now)}-{candidate_id:02d}",
            "task_class": task_class,
            "trigger": "missing_skill_rate_by_task_class",
            "rate": round(rate, 4),
            "threshold": missing_skill_rate_escalation,
            "priority": "high" if rate >= 0.5 else "medium",
            "recommended_action": f"Define/add missing skills for task class '{task_class}'.",
        }
        candidates.append(candidate)
        candidate_id += 1

    report["backlog_candidates"] = candidates
    if candidates:
        report["recommended_actions"].append(
            f"Create backlog items for {len(candidates)} repeated capability gaps."
        )

    if dry_run:
        return TickResult(ok=True, mode="weekly", details=report, warnings=[])

    TEMPMEM_DIR.mkdir(parents=True, exist_ok=True)
    out = TEMPMEM_DIR / f"skill-autonomy-weekly-{week_id(now)}-{now.strftime('%Y%m%dT%H%M%SZ')}.md"
    content = "---\n"
    content += yaml.safe_dump(
        {
            "week_id": report["week_id"],
            "generated_at_utc": report["generated_at_utc"],
            "events_analyzed": report["events_analyzed"],
            "needs_manual_qdrant_import": True,
        },
        sort_keys=False,
    )
    content += "---\n\n"
    content += "## Skill Autonomy Weekly\n\n"
    content += yaml.safe_dump(report, sort_keys=False)
    out.write_text(content, encoding="utf-8")

    report["report_path"] = str(out.relative_to(PROJECT_ROOT))

    backlog_path = None
    if backlog_enabled and candidates:
        backlog_output_dir.mkdir(parents=True, exist_ok=True)
        backlog_path = backlog_output_dir / f"skills-autonomy-candidates-{week_id(now)}.md"
        lines = [
            "# Skills Autonomy Backlog Candidates",
            "",
            f"Generated at: {iso(now)}",
            f"Week: {week_id(now)}",
            "",
            "These candidates are generated automatically from repeated missing-skill KPIs.",
            "They are planning inputs, not execution blockers.",
            "",
            "## Candidates",
            "",
        ]
        for c in candidates:
            lines.append(f"- [ ] `{c['candidate_id']}`")
            if "skill_name" in c:
                lines.append(f"  - skill_name: `{c['skill_name']}`")
            if "task_class" in c:
                lines.append(f"  - task_class: `{c['task_class']}`")
            lines.append(f"  - trigger: `{c['trigger']}`")
            if "count" in c:
                lines.append(f"  - count: {c['count']} (threshold: {c['threshold']})")
            if "rate" in c:
                lines.append(f"  - rate: {c['rate']} (threshold: {c['threshold']})")
            lines.append(f"  - priority: `{c['priority']}`")
            lines.append(f"  - recommended_action: {c['recommended_action']}")
            lines.append("")
        backlog_path.write_text("\n".join(lines), encoding="utf-8")
        report["backlog_path"] = str(backlog_path.relative_to(PROJECT_ROOT))

        client = redis_client()
        if client is not None:
            for c in candidates:
                payload = {
                    "generated_at_utc": iso(now),
                    "week_id": week_id(now),
                    **c,
                }
                client.rpush(backlog_redis_queue_key, json.dumps(payload, sort_keys=True))
            client.expire(backlog_redis_queue_key, 60 * 60 * 24 * 90)
            report["backlog_redis_queue_key"] = backlog_redis_queue_key
        else:
            report["backlog_redis_queue_key"] = None

    return TickResult(ok=True, mode="weekly", details=report, warnings=[])


def should_sample(sample_rate: float, force: bool) -> bool:
    if force:
        return True
    if sample_rate >= 1.0:
        return True
    if sample_rate <= 0.0:
        return False
    return random.random() <= sample_rate


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run skill autonomy tick")
    ap.add_argument("--mode", choices=["start", "close", "weekly", "all"], default="all")
    ap.add_argument("--story-id", default="")
    ap.add_argument("--task-class", default="unclassified")
    ap.add_argument("--impact-estimate", choices=["none", "low", "medium", "high"], default="low")
    ap.add_argument("--quality-score", type=float, default=None)
    ap.add_argument("--cycle-time-minutes", type=int, default=None)
    ap.add_argument("--rework-flag", action="store_true")
    ap.add_argument("--regression-flag", action="store_true")
    ap.add_argument("--skill-name", default="")
    ap.add_argument("--skill-version", default="")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--force", action="store_true", help="ignore sampling and run eval tick")
    ap.add_argument("--dry-run", action="store_true")
    return ap.parse_args()


@contextlib.contextmanager
def acquire_lock(lock_file: str):
    if not lock_file or fcntl is None:
        yield True
        return

    path = Path(lock_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("w", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.write(str(time.time()))
        fh.flush()
        yield True
    except BlockingIOError:
        yield False
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        fh.close()


def main() -> int:
    args = parse_args()
    t0 = time.monotonic()

    cfg = parse_yaml_file(
        Path(args.config),
        {
            "runtime": {"max_runtime_seconds": 20, "command_timeout_seconds": 12},
            "sampling": {"start_close_sample_rate": 1.0},
            "weekly": {"lookback_days": 14, "max_artifacts_scan": 500},
            "thresholds": {
                "missing_skill_rate_escalation": 0.35,
                "repeated_missing_skill_story_count": 5,
            },
            "backlog": {
                "enabled": True,
                "output_dir": "docs/backlog",
                "redis_queue_key": "bmad:chiseai:skills:backlog:candidates",
            },
        },
    )

    max_runtime = int(cfg.get("runtime", {}).get("max_runtime_seconds", 20))
    command_timeout = int(cfg.get("runtime", {}).get("command_timeout_seconds", 12))
    enabled = bool(cfg.get("runtime", {}).get("enabled", True))
    lock_file = str(cfg.get("runtime", {}).get("lock_file", ""))
    sample_rate = float(cfg.get("sampling", {}).get("start_close_sample_rate", 1.0))
    lookback_days = int(cfg.get("weekly", {}).get("lookback_days", 14))
    max_scan = int(cfg.get("weekly", {}).get("max_artifacts_scan", 500))
    missing_skill_rate_escalation = float(
        cfg.get("thresholds", {}).get("missing_skill_rate_escalation", 0.35)
    )
    repeated_missing_skill_story_count = int(
        cfg.get("thresholds", {}).get("repeated_missing_skill_story_count", 5)
    )
    backlog_enabled = bool(cfg.get("backlog", {}).get("enabled", True))
    backlog_output_dir = PROJECT_ROOT / str(cfg.get("backlog", {}).get("output_dir", "docs/backlog"))
    backlog_redis_queue_key = str(
        cfg.get("backlog", {}).get("redis_queue_key", "bmad:chiseai:skills:backlog:candidates")
    )

    if not enabled:
        payload = {
            "tick_mode": args.mode,
            "generated_at_utc": iso(),
            "skipped": True,
            "reason": "runtime.enabled=false in config/skill_autonomy.yaml",
        }
        print("SKILL_AUTONOMY_TICK_RESULT")
        print(yaml.safe_dump(payload, sort_keys=False).strip())
        return 0

    with acquire_lock(lock_file) as lock_ok:
        if not lock_ok:
            payload = {
                "tick_mode": args.mode,
                "generated_at_utc": iso(),
                "skipped": True,
                "reason": f"lock busy: {lock_file}",
            }
            print("SKILL_AUTONOMY_TICK_RESULT")
            print(yaml.safe_dump(payload, sort_keys=False).strip())
            return 0

        results: list[TickResult] = []
        warnings: list[str] = []

        wants_eval = args.mode in {"start", "close", "all"}
        wants_weekly = args.mode in {"weekly", "all"}

        if wants_eval:
            if not args.story_id:
                warnings.append("story_id missing; skipping eval tick")
            elif should_sample(sample_rate, args.force):
                results.append(
                    run_eval_tick(
                        story_id=args.story_id,
                        task_class=args.task_class,
                        impact_estimate=args.impact_estimate,
                        quality_score=args.quality_score,
                        cycle_time_minutes=args.cycle_time_minutes,
                        rework_flag=args.rework_flag,
                        regression_flag=args.regression_flag,
                        skill_name=args.skill_name,
                        skill_version=args.skill_version,
                        command_timeout_seconds=command_timeout,
                        dry_run=args.dry_run,
                    )
                )
            else:
                warnings.append("eval tick skipped by sampling policy")

        elapsed = time.monotonic() - t0
        if wants_weekly and elapsed < max_runtime:
            results.append(
                run_weekly_tick(
                    lookback_days=lookback_days,
                    max_artifacts_scan=max_scan,
                    missing_skill_rate_escalation=missing_skill_rate_escalation,
                    repeated_missing_skill_story_count=repeated_missing_skill_story_count,
                    backlog_enabled=backlog_enabled,
                    backlog_output_dir=backlog_output_dir,
                    backlog_redis_queue_key=backlog_redis_queue_key,
                    dry_run=args.dry_run,
                )
            )
        elif wants_weekly:
            warnings.append("weekly tick skipped due to runtime budget")

        elapsed = time.monotonic() - t0
        payload = {
            "tick_mode": args.mode,
            "generated_at_utc": iso(),
            "elapsed_seconds": round(elapsed, 3),
            "max_runtime_seconds": max_runtime,
            "results": [
                {"mode": r.mode, "ok": r.ok, "details": r.details, "warnings": r.warnings}
                for r in results
            ],
            "warnings": warnings,
        }

        print("SKILL_AUTONOMY_TICK_RESULT")
        print(yaml.safe_dump(payload, sort_keys=False).strip())

        if elapsed > max_runtime:
            print("WARNING: autonomy tick exceeded runtime budget (non-blocking)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
