#!/usr/bin/env python3
"""Manage cadence approval gates in .env and show pending approvals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
STATE_PATH = PROJECT_ROOT / "_bmad-output" / "autonomy-cadence" / "state.json"


def env_name_for(approval: str) -> str:
    return f"CHISE_APPROVAL_{approval.upper().replace('-', '_')}"


def read_env_lines() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def write_env_lines(lines: list[str]) -> None:
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def set_env_key(key: str, value: str) -> None:
    lines = read_env_lines()
    updated = False
    out: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            updated = True
        else:
            out.append(line)
    if not updated:
        out.append(f"{key}={value}")
    write_env_lines(out)


def pending_approvals() -> list[dict[str, Any]]:
    if not STATE_PATH.exists():
        return []
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    jobs = state.get("jobs", {})
    if not isinstance(jobs, dict):
        return []
    out: list[dict[str, Any]] = []
    for job_id, js in jobs.items():
        if not isinstance(js, dict):
            continue
        err = str(js.get("last_error") or "")
        if (
            "missing approval:" in err
            or str(js.get("last_status")) == "awaiting_approval"
        ):
            out.append(
                {
                    "job_id": job_id,
                    "status": js.get("last_status"),
                    "reason": err,
                }
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Manage approval gates for autonomy cadence"
    )
    ap.add_argument("--list-pending", action="store_true")
    ap.add_argument("--approve", help="Approval key (e.g., strategy-autopilot)")
    ap.add_argument("--revoke", help="Approval key (e.g., strategy-autopilot)")
    args = ap.parse_args()

    if args.approve and args.revoke:
        print("ERROR: use only one of --approve or --revoke")
        return 1

    if args.approve:
        key = env_name_for(args.approve)
        set_env_key(key, "true")
        print(f"Approved: {args.approve} ({key}=true)")
        return 0

    if args.revoke:
        key = env_name_for(args.revoke)
        set_env_key(key, "false")
        print(f"Revoked: {args.revoke} ({key}=false)")
        return 0

    pending = pending_approvals()
    print(json.dumps({"pending_approvals": pending}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
