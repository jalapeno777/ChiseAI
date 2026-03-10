#!/usr/bin/env python3
"""Run a benchmark suite for skill A/B comparisons.

This script orchestrates run directory creation and pluggable executor/grader commands.
It does not assume a specific agent runtime; callers provide command templates.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_eval_set(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("eval set must be a JSON object")
    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        raise ValueError("eval set must contain non-empty 'evals' list")
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def render(template: str, mapping: dict[str, str]) -> str:
    out = template
    for key, value in mapping.items():
        out = out.replace("{" + key + "}", value)
    return out


def run_shell(cmd: str, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        shlex.split(cmd),
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Run skill benchmark suite")
    ap.add_argument("--skill-name", required=True)
    ap.add_argument("--skill-path", required=True)
    ap.add_argument("--eval-set", required=True)
    ap.add_argument("--workspace", required=True, help="Workspace root for benchmark artifacts")
    ap.add_argument("--iteration", type=int, required=True)
    ap.add_argument("--runs-per-configuration", type=int, default=1)
    ap.add_argument(
        "--configurations",
        nargs="+",
        default=["with_skill", "without_skill"],
        help="Benchmark configurations (e.g., with_skill without_skill or new_skill old_skill)",
    )
    ap.add_argument(
        "--executor-cmd-template",
        required=True,
        help=(
            "Shell command template for run execution. Available placeholders: "
            "{config}, {skill_name}, {skill_path}, {prompt_file}, {output_dir}, {run_dir}, {files_json}"
        ),
    )
    ap.add_argument(
        "--grader-cmd-template",
        default="",
        help=(
            "Optional shell command template for grading. Placeholders: "
            "{config}, {skill_name}, {skill_path}, {prompt_file}, {output_dir}, {run_dir}, {files_json}"
        ),
    )
    ap.add_argument("--timeout-seconds", type=int, default=1800)
    ap.add_argument("--allow-missing-grading", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    skill_path = Path(args.skill_path).resolve()
    eval_set_path = Path(args.eval_set).resolve()
    workspace_root = Path(args.workspace).resolve()

    eval_set = load_eval_set(eval_set_path)
    eval_items = eval_set["evals"]

    iteration_dir = workspace_root / f"iteration-{args.iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)

    run_log: list[dict[str, Any]] = []

    for item in eval_items:
        eval_id = item.get("id")
        prompt = str(item.get("prompt", "")).strip()
        files = item.get("files", []) if isinstance(item.get("files", []), list) else []
        eval_name = str(item.get("name") or f"eval-{eval_id}").strip().replace("/", "-")
        eval_dir = iteration_dir / eval_name
        eval_dir.mkdir(parents=True, exist_ok=True)

        eval_meta = {
            "eval_id": eval_id,
            "eval_name": eval_name,
            "prompt": prompt,
            "expectations": item.get("expectations", []),
            "generated_at_utc": iso_now(),
        }
        write_json(eval_dir / "eval_metadata.json", eval_meta)

        prompt_file = eval_dir / "prompt.txt"
        prompt_file.write_text(prompt + "\n", encoding="utf-8")

        for config in args.configurations:
            cfg_dir = eval_dir / config
            cfg_dir.mkdir(parents=True, exist_ok=True)

            for run_num in range(1, args.runs_per_configuration + 1):
                run_dir = cfg_dir / f"run-{run_num}"
                output_dir = run_dir / "outputs"
                output_dir.mkdir(parents=True, exist_ok=True)

                mapping = {
                    "config": config,
                    "skill_name": args.skill_name,
                    "skill_path": str(skill_path),
                    "prompt_file": str(prompt_file),
                    "output_dir": str(output_dir),
                    "run_dir": str(run_dir),
                    "files_json": json.dumps(files),
                }

                timing = {
                    "started_at_utc": iso_now(),
                    "executor_cmd": render(args.executor_cmd_template, mapping),
                    "grader_cmd": render(args.grader_cmd_template, mapping) if args.grader_cmd_template else "",
                }

                if args.dry_run:
                    timing["dry_run"] = True
                    write_json(run_dir / "timing.json", timing)
                    run_log.append({"eval": eval_name, "config": config, "run": run_num, "status": "dry_run"})
                    continue

                t0 = time.monotonic()
                exec_proc = run_shell(timing["executor_cmd"], cwd=Path.cwd(), timeout=args.timeout_seconds)
                elapsed = time.monotonic() - t0
                timing.update(
                    {
                        "executor_returncode": exec_proc.returncode,
                        "executor_elapsed_seconds": round(elapsed, 3),
                        "executor_stdout_tail": exec_proc.stdout[-4000:],
                        "executor_stderr_tail": exec_proc.stderr[-4000:],
                        "finished_at_utc": iso_now(),
                    }
                )
                write_json(run_dir / "timing.json", timing)

                if exec_proc.returncode != 0:
                    run_log.append(
                        {
                            "eval": eval_name,
                            "config": config,
                            "run": run_num,
                            "status": "executor_failed",
                            "returncode": exec_proc.returncode,
                        }
                    )
                    continue

                if args.grader_cmd_template:
                    grader_cmd = render(args.grader_cmd_template, mapping)
                    grade_proc = run_shell(grader_cmd, cwd=Path.cwd(), timeout=args.timeout_seconds)
                    run_log.append(
                        {
                            "eval": eval_name,
                            "config": config,
                            "run": run_num,
                            "status": "ok" if grade_proc.returncode == 0 else "grader_failed",
                            "grader_returncode": grade_proc.returncode,
                        }
                    )
                else:
                    run_log.append(
                        {
                            "eval": eval_name,
                            "config": config,
                            "run": run_num,
                            "status": "ok_no_grader",
                        }
                    )

                grading_path = run_dir / "grading.json"
                if not grading_path.exists() and not args.allow_missing_grading:
                    run_log.append(
                        {
                            "eval": eval_name,
                            "config": config,
                            "run": run_num,
                            "status": "missing_grading_json",
                        }
                    )

    suite_report = {
        "generated_at_utc": iso_now(),
        "skill_name": args.skill_name,
        "skill_path": str(skill_path),
        "eval_set": str(eval_set_path),
        "iteration_dir": str(iteration_dir),
        "configurations": args.configurations,
        "runs_per_configuration": args.runs_per_configuration,
        "results": run_log,
    }
    write_json(iteration_dir / "suite-run-report.json", suite_report)

    missing_grading = [r for r in run_log if r.get("status") == "missing_grading_json"]
    failed = [r for r in run_log if "failed" in str(r.get("status", ""))]

    print(json.dumps({
        "iteration_dir": str(iteration_dir),
        "runs_total": len(run_log),
        "failed": len(failed),
        "missing_grading": len(missing_grading),
    }, indent=2))

    if failed:
        return 1
    if missing_grading and not args.allow_missing_grading:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
