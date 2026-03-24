#!/usr/bin/env python3
"""Decide skill promotion from benchmark artifacts and persist evidence.

Policy (default):
- PROMOTE when pass-rate delta meets threshold and cycle-time degradation is acceptable.
- HOLD otherwise.
"""

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
    configs = [k for k in run_summary if k != "delta"]
    if len(configs) < 2:
        raise ValueError(
            "benchmark run_summary must include at least two configurations"
        )

    preferred_primary = ["with_skill", "new_skill", "candidate", "vnext", "primary"]
    preferred_baseline = ["without_skill", "old_skill", "baseline", "incumbent"]

    primary = next((c for c in preferred_primary if c in configs), configs[0])
    baseline = next(
        (c for c in preferred_baseline if c in configs and c != primary), None
    )

    if not baseline:
        for c in configs:
            if c != primary:
                baseline = c
                break
    if not baseline:
        raise ValueError("unable to resolve baseline configuration")
    return primary, baseline


def metric_mean(run_summary: dict[str, Any], config: str, metric: str) -> float | None:
    raw = run_summary.get(config, {}).get(metric, {}).get("mean")
    try:
        return float(raw)
    except Exception:
        return None


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "skill_name": payload["skill_name"],
        "candidate_version": payload["candidate_version"],
        "decision": payload["decision"],
        "generated_at_utc": payload["generated_at_utc"],
        "needs_manual_qdrant_import": True,
    }
    body = {
        "benchmark_json": payload["benchmark_json"],
        "primary_config": payload["primary_config"],
        "baseline_config": payload["baseline_config"],
        "pass_rate_delta": payload["pass_rate_delta"],
        "cycle_time_degradation": payload["cycle_time_degradation"],
        "tokens_delta": payload["tokens_delta"],
        "thresholds": payload["thresholds"],
        "evidence_refs": payload["evidence_refs"],
        "reason": payload["reason"],
    }
    content = "---\n"
    content += yaml.safe_dump(frontmatter, sort_keys=False)
    content += "---\n\n"
    content += "## Skill Promotion Decision\n\n"
    content += yaml.safe_dump(body, sort_keys=False)
    path.write_text(content, encoding="utf-8")


def update_skill_registry(
    *,
    registry_path: Path,
    skill_name: str,
    candidate_version: str,
    incumbent_version: str,
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
            "preferred_version": incumbent_version or candidate_version,
            "previous_preferred_version": "",
            "status": "active",
            "last_decision": "HOLD",
            "last_decision_at_utc": generated_at_utc,
            "degraded_versions": [],
            "evidence_refs": [],
        }

    previous_preferred = str(entry.get("preferred_version", "")).strip()
    if decision == "PROMOTE":
        entry["previous_preferred_version"] = previous_preferred
        entry["preferred_version"] = candidate_version
        entry["status"] = "active"
    entry["last_decision"] = decision
    entry["last_decision_at_utc"] = generated_at_utc
    entry["evidence_refs"] = evidence_refs
    if not isinstance(entry.get("degraded_versions"), list):
        entry["degraded_versions"] = []

    skills[skill_name] = entry
    registry["updated_at_utc"] = generated_at_utc

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
    )
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Evaluate promotion from benchmark evidence"
    )
    ap.add_argument("--skill-name", required=True)
    ap.add_argument("--candidate-version", required=True)
    ap.add_argument("--incumbent-version", default="")
    ap.add_argument("--benchmark-json", required=True, help="Path to benchmark.json")
    ap.add_argument("--config-path", default=str(DEFAULT_CONFIG))
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    ap.add_argument("--registry-path", default=str(DEFAULT_REGISTRY_PATH))
    ap.add_argument("--apply-registry-update", action="store_true")
    ap.add_argument("--redis-key", default="bmad:chiseai:skills:promotions")
    ap.add_argument("--promote-quality-gain-min", type=float, default=None)
    ap.add_argument("--max-cycle-time-degradation", type=float, default=None)
    args = ap.parse_args()

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

    cfg = parse_yaml_file(
        Path(args.config_path),
        {
            "thresholds": {
                "promote_quality_gain_min": 0.10,
                "max_cycle_time_degradation": 0.10,
            }
        },
    )
    thresholds_cfg = cfg.get("thresholds", {}) if isinstance(cfg, dict) else {}
    promote_quality_gain_min = (
        float(args.promote_quality_gain_min)
        if args.promote_quality_gain_min is not None
        else float(thresholds_cfg.get("promote_quality_gain_min", 0.10))
    )
    max_cycle_time_degradation = (
        float(args.max_cycle_time_degradation)
        if args.max_cycle_time_degradation is not None
        else float(thresholds_cfg.get("max_cycle_time_degradation", 0.10))
    )

    try:
        primary_cfg, baseline_cfg = choose_configs(run_summary)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    primary_pass = metric_mean(run_summary, primary_cfg, "pass_rate")
    baseline_pass = metric_mean(run_summary, baseline_cfg, "pass_rate")
    primary_time = metric_mean(run_summary, primary_cfg, "time_seconds")
    baseline_time = metric_mean(run_summary, baseline_cfg, "time_seconds")
    primary_tokens = metric_mean(run_summary, primary_cfg, "tokens")
    baseline_tokens = metric_mean(run_summary, baseline_cfg, "tokens")

    if primary_pass is None or baseline_pass is None:
        print("ERROR: benchmark missing pass_rate means for selected configs")
        return 1

    pass_rate_delta = primary_pass - baseline_pass
    cycle_time_degradation = 0.0
    if primary_time is not None and baseline_time and baseline_time > 0:
        cycle_time_degradation = (primary_time - baseline_time) / baseline_time
    tokens_delta = None
    if primary_tokens is not None and baseline_tokens is not None:
        tokens_delta = primary_tokens - baseline_tokens

    quality_ok = pass_rate_delta >= promote_quality_gain_min
    time_ok = cycle_time_degradation <= max_cycle_time_degradation

    decision = "PROMOTE" if (quality_ok and time_ok) else "HOLD"
    reason = (
        "pass-rate delta meets threshold and time degradation is acceptable"
        if decision == "PROMOTE"
        else "insufficient improvement and/or harmful time degradation"
    )

    payload: dict[str, Any] = {
        "skill_name": args.skill_name,
        "candidate_version": args.candidate_version,
        "incumbent_version": args.incumbent_version,
        "decision": decision,
        "reason": reason,
        "benchmark_json": str(benchmark_path),
        "primary_config": primary_cfg,
        "baseline_config": baseline_cfg,
        "pass_rate_delta": round(pass_rate_delta, 6),
        "cycle_time_degradation": round(cycle_time_degradation, 6),
        "tokens_delta": None if tokens_delta is None else round(tokens_delta, 6),
        "thresholds": {
            "promote_quality_gain_min": promote_quality_gain_min,
            "max_cycle_time_degradation": max_cycle_time_degradation,
        },
        "evidence_refs": [str(benchmark_path), str(benchmark_path.with_suffix(".md"))],
        "generated_at_utc": iso(),
    }

    ts = utc_now().strftime("%Y%m%dT%H%M%SZ")
    slug = args.skill_name.replace("/", "-").replace(" ", "-")
    md_path = Path(args.output_dir) / f"skill-promotion-{slug}-{ts}.md"
    write_markdown(md_path, payload)
    payload["markdown_artifact"] = str(md_path)

    if args.apply_registry_update or decision == "PROMOTE":
        try:
            reg_entry = update_skill_registry(
                registry_path=Path(args.registry_path),
                skill_name=args.skill_name,
                candidate_version=args.candidate_version,
                incumbent_version=args.incumbent_version,
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

    print("SKILL_PROMOTION_DECISION")
    print(yaml.safe_dump(payload, sort_keys=False).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
