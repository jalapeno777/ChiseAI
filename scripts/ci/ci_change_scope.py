#!/usr/bin/env python3
"""Classify CI change scope for non-intrusive gating decisions."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

# Add src to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

DOC_ONLY_PREFIXES = (
    "docs/",
    ".opencode/",
    "_bmad-output/",
)
DOC_ONLY_FILES = {
    "AGENTS.md",
    "README.md",
    ".gitignore",
}


def _run_git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def _resolve_base_ref(explicit: str | None) -> str | None:
    candidates = [explicit] if explicit else []
    candidates.extend(
        [
            "refs/remotes/origin/main",
            "origin/main",
            "refs/remotes/origin/main",
            "origin/main",
            "main",
        ]
    )
    for candidate in candidates:
        if not candidate:
            continue
        rc, _ = _run_git("rev-parse", "--verify", candidate)
        if rc == 0:
            return candidate
    return None


def _pr_changed_files_from_gitea() -> list[str] | None:
    """Return changed files from Gitea PR API when running on PR builds."""
    env = os.environ
    pr_number = (
        env.get("CI_COMMIT_PULL_REQUEST", "").strip()
        or env.get("CI_PULL_REQUEST", "").strip()
        or env.get("WOODPECKER_PULL_REQUEST", "").strip()
    )
    repo = env.get("CI_REPO", "").strip()
    forge_url = (env.get("CI_FORGE_URL", "") or env.get("GITEA_BASE_URL", "")).strip()
    token = env.get("GITEA_TOKEN", "").strip()

    if not pr_number or not repo or "/" not in repo or not forge_url or not token:
        return None

    owner, name = repo.split("/", 1)
    url = (
        f"{forge_url.rstrip('/')}/api/v1/repos/{quote(owner)}/{quote(name)}"
        f"/pulls/{quote(pr_number)}/files"
    )
    req = Request(url=url, method="GET", headers={"Authorization": f"token {token}"})
    try:
        with urlopen(req, timeout=15) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            if not isinstance(payload, list):
                return None
            files: list[str] = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                filename = str(item.get("filename", "")).strip()
                if filename:
                    files.append(filename)
            return files
    except (OSError, URLError, json.JSONDecodeError):
        return None


def _pipeline_changed_files_from_env() -> list[str] | None:
    """Return changed files from CI-provided env payload when available."""
    raw = os.environ.get("CI_PIPELINE_FILES", "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    files: list[str] = []
    for item in payload:
        path = str(item).strip()
        if path:
            files.append(path)
    return files


def changed_files(base_ref: str | None) -> list[str]:
    env_files = _pipeline_changed_files_from_env()
    if env_files is not None:
        return env_files

    pr_files = _pr_changed_files_from_gitea()
    if pr_files is not None:
        return pr_files

    base = _resolve_base_ref(base_ref)
    if base:
        rc, merge_base = _run_git("merge-base", "HEAD", base)
        diff_base = merge_base if rc == 0 and merge_base else base
        rc, out = _run_git("diff", "--name-only", f"{diff_base}...HEAD")
        if rc == 0:
            files = [line.strip() for line in out.splitlines() if line.strip()]
            if files:
                return files
    rc, out = _run_git("diff", "--name-only", "HEAD~1..HEAD")
    if rc == 0:
        files = [line.strip() for line in out.splitlines() if line.strip()]
        if files:
            return files
    rc, out = _run_git("show", "--pretty=", "--name-only", "HEAD")
    if rc == 0:
        return [line.strip() for line in out.splitlines() if line.strip()]
    return []


def is_docs_only(paths: list[str]) -> bool:
    if not paths:
        return False
    for path in paths:
        if path in DOC_ONLY_FILES:
            continue
        if path.endswith(".md") and "/" not in path:
            continue
        if path.startswith(DOC_ONLY_PREFIXES):
            continue
        return False
    return True


def changed_python(paths: list[str]) -> list[str]:
    return [p for p in paths if p.endswith(".py") and Path(p).exists()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CI change scope helper")
    p.add_argument("--base-ref", default=None)
    p.add_argument(
        "--mode",
        choices=("summary", "docs-only", "changed-python"),
        default="summary",
    )
    return p


def main() -> int:
    # Bootstrap environment first
    bootstrap(load_env=True)
    args = build_parser().parse_args()
    paths = changed_files(args.base_ref)
    docs_only = is_docs_only(paths)
    py_files = changed_python(paths)

    if args.mode == "summary":
        print(
            json.dumps(
                {
                    "changed_files": paths,
                    "docs_only": docs_only,
                    "changed_python": py_files,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.mode == "docs-only":
        print("true" if docs_only else "false")
        return 0 if docs_only else 1

    for path in py_files:
        print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
