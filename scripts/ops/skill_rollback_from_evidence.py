#!/usr/bin/env python3
"""Decide skill rollback from benchmark/live evidence and persist artifacts."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "skill_autonomy.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "tempmemories"
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "docs" / "metrics" / "skill-versions.yaml"


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def choose_configs(run_summary: dict[str, Any]) -> tuple[str, str]:
    configs = [k for k in run_summary.keys() if k != "delta"]
    if len(configs) < 2:
        raise ValueError("benchmark run_summary must include at least two configurations")

    preferred_degraded = ["with_skill", "new_skill", "candidate", "vnext", "primary"]
    preferred_baseline = ["without_skill", "old_skill", "baseline", "incumbent"]

    degraded_cfg = next((c for c in preferred_degraded if c in configs), configs[0])
    baseline_cfg = next((c for c in preferred_baseline if c in configs and c != degraded_cfg), None)
    if not baseline_cfg:
        for c in configs:
            if c != degraded_cfg:
                baseline_cfg = c
                break
    if not baseline_cfg:
        raise ValueError("unable to resolve baseline configuration")
    return degraded_cfg, baseline_cfg


def metric_mean(run_summary: dict[str, Any], config: str, metric: str) -> float | None:
    raw = run_summary.get(config, {}).get(metric, {}).get("mean")
    try:
        return float(raw)
    except Exception:
        return None


def resolve_fallback_from_registry(registry_path: Path, skill_name: str) -> str:
    registry = parse_yaml_file(registry_path, {"skills": {}})
    entry = registry.get("skills", {}).get(skill_name, {})
    if not isinstance(entry, dict):
        return ""
    prev = str(entry.get("previous_preferred_version", "")).strip()
    pref = str(entry.get("preferred_version", "")).strip()
    return prev or pref


def update_registry_for_rollback(
    *,
    registry_path: Path,
    skill_name: str,
    degraded_version: str,
    fallback_version: str,
    decision: str,
    generated_at_utc: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    registry = parse_yaml_file(
        registry_path,
        {"version": 1, "updated_at_utc": generated_at_utc, "skills": {}},
    )
    skills = registry.get("skills")
    if not isinstance(skills, dict):
        skills = {}
        registry["skills"] = skills

    entry = skills.get(skill_name)
    if not isinstance(entry, dict):
        entry = {
            "preferred_version": fallback_version or degraded_version,
            "previous_preferred_version": "",
            "status": "active",
            "last_decision": "HOLD",
            "last_decision_at_utc": generated_at_utc,
            "degraded_versions": [],
            "evidence_refs": [],
        }

    degraded_versions = entry.get("degraded_versions")
    if not isinstance(degraded_versions, list):
        degraded_versions = []
    if degraded_version and degraded_version not in degraded_versions:
        degraded_versions.append(degraded_version)
    entry["degraded_versions"] = degraded_versions

    if decision == "ROLLBACK":
        entry["previous_preferred_version"] = str(entry.get("preferred_version", "")).strip()
        if fallback_version:
            entry["preferred_version"] = fallback_version
        entry["status"] = "active"

    entry["last_decision"] = decision
    entry["last_decision_at_utc"] = generated_at_utc
    entry["evidence_refs"] = evidence_refs
    skills[skill_name] = entry
    registry["updated_at_utc"] = generated_at_utc
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    return entry


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "skill_name": payload["skill_name"],
        "degraded_version": payload["degraded_version"],
        "decision": payload["decision"],
        "generated_at_utc": payload["generated_at_utc"],
        "needs_manual_qdrant_import": True,
    }
    body = {
        "fallback_version": payload["fallback_version"],
        "pass_rate_drop": payload["pass_rate_drop"],
        "cycle_time_increase": payload["cycle_time_increase"],
        "regression_rate": payload["regression_rate"],
        "thresholds": payload["thresholds"],
        "benchmark_json": payload.get("benchmark_json"),
        "evidence_refs": payload["evidence_refs"],
        "reason": payload["reason"],
    }
    content = "---\n"
    content += yaml.safe_dump(fm, sort_keys=False)
    content += "---\n\n"
    content += "## Skill Rollback Decision\n\n"
    content += yaml.safe_dump(body, sort_keys=False)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate rollback decision from evidence")
    ap.add_argument("--skill-name", required=True)
    ap.add_argument("--degraded-version", required=True)
    ap.add_argument("--fallback-version", default="")
    ap.add_argument("--benchmark-json", default="")
    ap.add_argument("--regression-rate", type=float, default=0.0)
    ap.add_argument("--config-path", default=str(DEFAULT_CONFIG))
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    ap.add_argument("--registry-path", default=str(DEFAULT_REGISTRY_PATH))
    ap.add_argument("--redis-key", default="bmad:chiseai:skills:promotions")
    ap.add_argument("--rollback-quality-drop-min", type=float, default=None)
    ap.add_argument("--rollback-cycle-time-increase-max", type=float, default=None)
    ap.add_argument("--rollback-regression-rate-max", type=float, default=None)
    args = ap.parse_args()

    cfg = parse_yaml_file(
        Path(args.config_path),
        {
            "thresholds": {
                "rollback_quality_drop_min": 0.05,
                "rollback_cycle_time_increase_max": 0.15,
                "rollback_regression_rate_max": 0.20,
            }
        },
    )
    thresholds_cfg = cfg.get("thresholds", {}) if isinstance(cfg, dict) else {}
    rollback_quality_drop_min = (
        float(args.rollback_quality_drop_min)
        if args.rollback_quality_drop_min is not None
        else float(thresholds_cfg.get("rollback_quality_drop_min", 0.05))
    )
    rollback_cycle_time_increase_max = (
        float(args.rollback_cycle_time_increase_max)
        if args.rollback_cycle_time_increase_max is not None
        else float(thresholds_cfg.get("rollback_cycle_time_increase_max", 0.15))
    )
    rollback_regression_rate_max = (
        float(args.rollback_regression_rate_max)
        if args.rollback_regression_rate_max is not None
        else float(thresholds_cfg.get("rollback_regression_rate_max", 0.20))
    )

    pass_rate_drop = 0.0
    cycle_time_increase = 0.0
    benchmark_ref = None

    if args.benchmark_json:
        benchmark_path = Path(args.benchmark_json)
        if not benchmark_path.exists():
            print(f"ERROR: benchmark json not found: {benchmark_path}")
            return 1
        try:
            benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"ERROR: failed to parse benchmark json: {exc}")
            return 1

        run_summary = benchmark.get("run_summary")
        if not isinstance(run_summary, dict):
            print("ERROR: benchmark missing run_summary")
            return 1

        try:
            degraded_cfg, baseline_cfg = choose_configs(run_summary)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 1

        degraded_pass = metric_mean(run_summary, degraded_cfg, "pass_rate")
        baseline_pass = metric_mean(run_summary, baseline_cfg, "pass_rate")
        degraded_time = metric_mean(run_summary, degraded_cfg, "time_seconds")
        baseline_time = metric_mean(run_summary, baseline_cfg, "time_seconds")
        if degraded_pass is not None and baseline_pass is not None:
            pass_rate_drop = baseline_pass - degraded_pass
        if degraded_time is not None and baseline_time and baseline_time > 0:
            cycle_time_increase = (degraded_time - baseline_time) / baseline_time
        benchmark_ref = str(benchmark_path)

    fallback_version = args.fallback_version.strip() or resolve_fallback_from_registry(
        Path(args.registry_path), args.skill_name
    )

    triggers = []
    if pass_rate_drop >= rollback_quality_drop_min:
        triggers.append("quality_drop")
    if cycle_time_increase >= rollback_cycle_time_increase_max:
        triggers.append("cycle_time_increase")
    if args.regression_rate >= rollback_regression_rate_max:
        triggers.append("regression_rate")

    decision = "ROLLBACK" if triggers else "HOLD"
    reason = (
        "rollback triggers exceeded thresholds: " + ", ".join(triggers)
        if triggers
        else "rollback thresholds not exceeded"
    )

    payload: dict[str, Any] = {
        "skill_name": args.skill_name,
        "degraded_version": args.degraded_version,
        "fallback_version": fallback_version,
        "decision": decision,
        "reason": reason,
        "pass_rate_drop": round(pass_rate_drop, 6),
        "cycle_time_increase": round(cycle_time_increase, 6),
        "regression_rate": round(args.regression_rate, 6),
        "thresholds": {
            "rollback_quality_drop_min": rollback_quality_drop_min,
            "rollback_cycle_time_increase_max": rollback_cycle_time_increase_max,
            "rollback_regression_rate_max": rollback_regression_rate_max,
        },
        "benchmark_json": benchmark_ref,
        "evidence_refs": [x for x in [benchmark_ref, benchmark_ref[:-5] + ".md" if benchmark_ref else ""] if x],
        "generated_at_utc": iso(),
    }

    ts = utc_now().strftime("%Y%m%dT%H%M%SZ")
    slug = args.skill_name.replace("/", "-").replace(" ", "-")
    md_path = Path(args.output_dir) / f"skill-rollback-{slug}-{ts}.md"
    write_markdown(md_path, payload)
    payload["markdown_artifact"] = str(md_path)

    try:
        reg_entry = update_registry_for_rollback(
            registry_path=Path(args.registry_path),
            skill_name=args.skill_name,
            degraded_version=args.degraded_version,
            fallback_version=fallback_version,
            decision=decision,
            generated_at_utc=payload["generated_at_utc"],
            evidence_refs=payload["evidence_refs"],
        )
        payload["registry_updated"] = True
        payload["registry_path"] = args.registry_path
        payload["registry_entry"] = reg_entry
    except Exception as exc:
        payload["registry_updated"] = False
        payload["registry_error"] = str(exc)

    client = redis_client()
    if client is None:
        payload["redis_persisted"] = False
        payload["redis_reason"] = "redis_unavailable"
    else:
        try:
            client.lpush(args.redis_key, json.dumps(payload, sort_keys=True))
            client.expire(args.redis_key, 60 * 60 * 24 * 180)
            payload["redis_persisted"] = True
        except Exception as exc:
            payload["redis_persisted"] = False
            payload["redis_reason"] = f"redis_write_failed:{exc}"

    print("SKILL_ROLLBACK_DECISION")
    print(yaml.safe_dump(payload, sort_keys=False).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
