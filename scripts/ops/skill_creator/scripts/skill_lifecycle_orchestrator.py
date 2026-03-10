#!/usr/bin/env python3
"""Single-entry skill lifecycle orchestrator.

Pipeline (configurable):
1) optional scaffold
2) optional trigger optimization
3) benchmark run + aggregate
4) promotion/rollback evidence decision
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def run(cmd: str, cwd: Path) -> int:
    print(f"[RUN] {cmd}")
    proc = subprocess.run(shlex.split(cmd), cwd=cwd, check=False)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Run skill lifecycle orchestration")
    ap.add_argument("--skill-name", required=True)
    ap.add_argument("--skill-path", default="")
    ap.add_argument("--create-skill", action="store_true")
    ap.add_argument("--run-trigger-opt", action="store_true")
    ap.add_argument("--trigger-model", default="")
    ap.add_argument("--eval-set", default="")
    ap.add_argument("--workspace", default="")
    ap.add_argument("--iteration", type=int, default=1)
    ap.add_argument("--executor-cmd-template", default="")
    ap.add_argument("--grader-cmd-template", default="")
    ap.add_argument("--promote-candidate-version", default="")
    ap.add_argument("--promote-incumbent-version", default="")
    ap.add_argument("--rollback-degraded-version", default="")
    ap.add_argument("--rollback-fallback-version", default="")
    ap.add_argument("--regression-rate", type=float, default=0.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    skill_path = args.skill_path.strip() or f".opencode/skills/{args.skill_name}"
    eval_set = args.eval_set.strip() or f"{skill_path}/evals/evals.json"
    workspace = args.workspace.strip() or f"_bmad-output/skill-benchmarks/{args.skill_name}"

    scripts_dir = PROJECT_ROOT / "scripts" / "ops" / "skill_creator" / "scripts"

    if args.create_skill:
        cmd = (
            f"python3 {scripts_dir / 'init_skill.py'} {args.skill_name} "
            f"--path .opencode/skills"
        )
        if run(cmd, PROJECT_ROOT) != 0:
            return 1

    if args.run_trigger_opt:
        if not args.trigger_model:
            print("ERROR: --trigger-model required when --run-trigger-opt is set")
            return 1
        cmd = (
            f"python3 -m scripts.run_loop "
            f"--skill-path {PROJECT_ROOT / skill_path} "
            f"--eval-set {PROJECT_ROOT / eval_set} "
            f"--model {args.trigger_model} --max-iterations 5 --runs-per-query 3 "
            f"--trigger-threshold 0.5 --holdout 0.4 --verbose"
        )
        if args.dry_run:
            cmd += " --report none"
        if run(cmd, PROJECT_ROOT / "scripts" / "ops" / "skill_creator") != 0:
            return 1

    if args.executor_cmd_template:
        bench_cmd = (
            f"python3 {scripts_dir / 'run_benchmark_suite.py'} "
            f"--skill-name {args.skill_name} "
            f"--skill-path {PROJECT_ROOT / skill_path} "
            f"--eval-set {PROJECT_ROOT / eval_set} "
            f"--workspace {PROJECT_ROOT / workspace} "
            f"--iteration {args.iteration} "
            f"--executor-cmd-template {shlex.quote(args.executor_cmd_template)} "
        )
        if args.grader_cmd_template:
            bench_cmd += f"--grader-cmd-template {shlex.quote(args.grader_cmd_template)} "
        if args.dry_run:
            bench_cmd += "--dry-run "
        if run(bench_cmd, PROJECT_ROOT) != 0:
            return 1

        agg_cmd = (
            f"python3 -m scripts.aggregate_benchmark "
            f"{PROJECT_ROOT / workspace / f'iteration-{args.iteration}'} "
            f"--skill-name {args.skill_name} --skill-path {PROJECT_ROOT / skill_path}"
        )
        if run(agg_cmd, PROJECT_ROOT / "scripts" / "ops" / "skill_creator") != 0:
            return 1

    bench_json = PROJECT_ROOT / workspace / f"iteration-{args.iteration}" / "benchmark.json"

    if args.promote_candidate_version:
        promote_cmd = (
            f"python3 scripts/ops/skill_promote_from_benchmark.py "
            f"--skill-name {args.skill_name} "
            f"--candidate-version {args.promote_candidate_version} "
            f"--incumbent-version {args.promote_incumbent_version} "
            f"--benchmark-json {bench_json} --apply-registry-update"
        )
        if run(promote_cmd, PROJECT_ROOT) != 0:
            return 1

    if args.rollback_degraded_version:
        rollback_cmd = (
            f"python3 scripts/ops/skill_rollback_from_evidence.py "
            f"--skill-name {args.skill_name} "
            f"--degraded-version {args.rollback_degraded_version} "
            f"--fallback-version {args.rollback_fallback_version} "
            f"--benchmark-json {bench_json} --regression-rate {args.regression_rate}"
        )
        if run(rollback_cmd, PROJECT_ROOT) != 0:
            return 1

    print("Skill lifecycle orchestration complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
