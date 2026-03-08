#!/usr/bin/env python3
"""Merlin PR sweep automation for branch drift cleanup.

Responsibilities:
- Discover non-main branches with unique commits ahead of main
- Resolve story IDs via explicit mapping file (plus fallback regex)
- Open/update PRs through scripts/gitea_pr_automerge.py
- Enforce supersession-link comments when running consolidation mode
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Add src to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

try:
    story_id_module = importlib.import_module("scripts.story_id")
except ModuleNotFoundError:
    # Allow execution as `python scripts/ops/merlin_pr_sweep.py`.
    import pathlib

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    story_id_module = importlib.import_module("story_id")

extract_story_ids = story_id_module.extract_story_ids
normalize_story_id = story_id_module.normalize_story_id

DEFAULT_MAPPING_FILE = Path("docs/operations/merlin-branch-story-map.json")
DEFAULT_BASE_URL = "http://host.docker.internal:3000"
DEFAULT_OWNER = "craig"
DEFAULT_REPO = "ChiseAI"


class SweepError(Exception):
    """Raised for recoverable sweep failures."""


def _req_json(
    method: str, url: str, token: str, body: dict[str, Any] | None = None
) -> Any:
    data = None
    headers = {"Accept": "application/json", "Authorization": f"token {token}"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="replace")
        raise SweepError(f"{method} {url} failed: HTTP {exc.code}: {msg}") from exc


def _run_git(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(  # nosec B607
        ["git", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def load_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exact": {}, "notes": "mapping file missing; using regex fallback"}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SweepError(f"Invalid mapping JSON in {path}")
    exact = data.get("exact", {})
    if not isinstance(exact, dict):
        raise SweepError(f"Invalid 'exact' mapping in {path}")
    return data


def normalize_branch(ref: str) -> str:
    b = ref.strip()
    if b.startswith("gitea/"):
        return b[len("gitea/") :]
    return b


def resolve_story_id(branch: str, mapping: dict[str, Any]) -> str | None:
    exact = mapping.get("exact", {})
    if isinstance(exact, dict) and branch in exact:
        val = exact[branch]
        if isinstance(val, str) and val.strip():
            mapped_ids = extract_story_ids(val)
            if mapped_ids:
                return normalize_story_id(mapped_ids[0])

    branch_ids = extract_story_ids(branch)
    if branch_ids:
        return normalize_story_id(branch_ids[0])
    return None


def ahead_count(branch: str) -> int:
    for ref in (branch, f"gitea/{branch}"):
        rc, out, _err = _run_git("rev-list", "--left-right", "--count", f"main...{ref}")
        if rc == 0 and out:
            parts = out.split()
            if len(parts) == 2 and parts[1].isdigit():
                return int(parts[1])
    return 0


def discover_candidate_branches() -> list[str]:
    _run_git("fetch", "--all", "--prune")
    rc, out, err = _run_git(
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads",
        "refs/remotes/gitea",
    )
    if rc != 0:
        raise SweepError(f"Failed to list refs: {err}")

    seen: set[str] = set()
    candidates: list[str] = []
    for ref in out.splitlines():
        b = normalize_branch(ref)
        if b in {"main", "HEAD"}:
            continue
        if b.endswith("/main"):
            continue
        if b not in seen:
            seen.add(b)
            if ahead_count(b) > 0:
                candidates.append(b)
    return sorted(candidates)


def run_automerge_for_branch(
    branch: str,
    story_id: str,
    *,
    wait: bool,
    delete_branch: bool,
    dry_run: bool,
    agent_id: str,
) -> int:
    cmd = [
        "python3",
        "scripts/gitea_pr_automerge.py",
        "--story-id",
        story_id,
        "--head",
        branch,
        "--agent-id",
        agent_id,
    ]
    if wait:
        cmd.extend(["--wait", "--enable-automerge"])
    if delete_branch:
        cmd.append("--delete-branch")

    if dry_run:
        print("DRY-RUN:", " ".join(cmd))
        return 0

    proc = subprocess.run(cmd, text=True, check=False)
    return proc.returncode


def build_supersession_comment(
    supersession_pr: int,
    *,
    base_url: str,
    owner: str,
    repo: str,
) -> str:
    url = f"{base_url.rstrip('/')}/{owner}/{repo}/pulls/{supersession_pr}"
    return (
        "Superseded by consolidation PR "
        f"#{supersession_pr}: {url}\n\n"
        "This branch/PR is being retired to avoid duplicate CI churn."
    )


def post_supersession_comment(
    pr_number: int,
    comment: str,
    *,
    token: str,
    base_url: str,
    owner: str,
    repo: str,
) -> None:
    url = f"{base_url.rstrip('/')}/api/v1/repos/{owner}/{repo}/issues/{pr_number}/comments"
    _req_json("POST", url, token, {"body": comment})


def validate_consolidation_args(args: argparse.Namespace) -> None:
    if not args.consolidation_mode:
        return
    if not args.supersede_pr:
        raise SweepError("--consolidation-mode requires at least one --supersede-pr")
    if not args.supersession_pr:
        raise SweepError("--consolidation-mode requires --supersession-pr")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Merlin PR sweep automation")
    p.add_argument("--mapping-file", default=str(DEFAULT_MAPPING_FILE))
    p.add_argument("--agent-id", default=os.getenv("AGENT_ID", "merlin"))
    p.add_argument("--wait", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--delete-branch", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--include-branch", action="append", default=[])
    p.add_argument("--consolidation-mode", action="store_true")
    p.add_argument("--supersede-pr", action="append", type=int, default=[])
    p.add_argument("--supersession-pr", type=int)
    p.add_argument("--base-url", default=os.getenv("GITEA_BASE_URL", DEFAULT_BASE_URL))
    p.add_argument("--owner", default=os.getenv("GITEA_OWNER", DEFAULT_OWNER))
    p.add_argument("--repo", default=os.getenv("GITEA_REPO", DEFAULT_REPO))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Bootstrap environment first
    bootstrap(load_env=True)
    args = parse_args(argv)

    if args.agent_id.strip().lower() != "merlin":
        print("ERROR: merlin_pr_sweep must run with --agent-id merlin", file=sys.stderr)
        return 1

    try:
        validate_consolidation_args(args)
        mapping = load_mapping(Path(args.mapping_file))
    except SweepError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    branches = (
        sorted(set(args.include_branch))
        if args.include_branch
        else discover_candidate_branches()
    )

    processed = 0
    skipped: list[str] = []
    failures: list[str] = []

    for branch in branches:
        story_id = resolve_story_id(branch, mapping)
        if not story_id:
            skipped.append(branch)
            continue

        rc = run_automerge_for_branch(
            branch,
            story_id,
            wait=args.wait,
            delete_branch=args.delete_branch,
            dry_run=args.dry_run,
            agent_id=args.agent_id,
        )
        processed += 1
        if rc != 0:
            failures.append(branch)

    if args.consolidation_mode:
        token = os.getenv("GITEA_TOKEN", "")
        if not token and not args.dry_run:
            print(
                "ERROR: GITEA_TOKEN required for consolidation comments",
                file=sys.stderr,
            )
            return 1

        comment = build_supersession_comment(
            int(args.supersession_pr),
            base_url=args.base_url,
            owner=args.owner,
            repo=args.repo,
        )
        for pr_num in args.supersede_pr:
            if args.dry_run:
                print(f"DRY-RUN: comment on PR #{pr_num}: {comment}")
                continue
            try:
                post_supersession_comment(
                    pr_num,
                    comment,
                    token=token,
                    base_url=args.base_url,
                    owner=args.owner,
                    repo=args.repo,
                )
            except SweepError as exc:
                failures.append(f"supersede-pr-{pr_num}:{exc}")

    print(
        json.dumps(
            {
                "processed": processed,
                "skipped": skipped,
                "failures": failures,
                "consolidation_mode": bool(args.consolidation_mode),
            },
            sort_keys=True,
        )
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
