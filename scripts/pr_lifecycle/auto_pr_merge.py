#!/usr/bin/env python3
"""Auto-create PRs from pushed branches and merge eligible PRs.

Policy:
- Auto-create PRs from non-protected branches targeting main when no open PR exists.
- During ensure-prs, optionally enable server-side ``merge_when_checks_succeed``.
- ``automerge`` performs a bounded merge reconciliation for eligible open PRs.
- Merge attempts are gated on a clean mergeable state and successful checks.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class Config:
    base_url: str
    token: str
    owner: str
    repo: str
    default_base: str
    protected: set[str]
    allowed_authors: set[str]
    max_branch_age_min: int
    source_branch: str
    enable_server_automerge: bool
    dry_run: bool


def _cfg(dry_run: bool) -> Config:
    protected_raw = os.getenv("CHISE_AUTOPR_PROTECTED_BRANCHES", "main,develop")
    authors_raw = os.getenv("CHISE_AUTOMERGE_AUTHORS", "chise-bot,craig")
    enable_server_automerge = os.getenv(
        "CHISE_AUTOPR_ENABLE_SERVER_AUTOMERGE", "1"
    ).strip().lower() in {"1", "true", "yes", "on"}
    return Config(
        base_url=os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000").rstrip(
            "/"
        ),
        token=os.getenv("GITEA_TOKEN", ""),
        owner=os.getenv("GITEA_OWNER", "craig"),
        repo=os.getenv("GITEA_REPO", "ChiseAI"),
        default_base=os.getenv("CHISE_AUTOPR_BASE", "main"),
        protected={x.strip() for x in protected_raw.split(",") if x.strip()},
        allowed_authors={x.strip() for x in authors_raw.split(",") if x.strip()},
        max_branch_age_min=int(os.getenv("CHISE_AUTOPR_MAX_BRANCH_AGE_MIN", "30")),
        source_branch=os.getenv("CHISE_AUTOPR_SOURCE_BRANCH", "").strip(),
        enable_server_automerge=enable_server_automerge,
        dry_run=dry_run,
    )


def _req_json(
    cfg: Config, method: str, path: str, body: dict[str, Any] | None = None
) -> Any:
    url = f"{cfg.base_url}{path}"
    headers = {"Accept": "application/json", "Authorization": f"token {cfg.token}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
        payload = resp.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def _safe_req_json(
    cfg: Config, method: str, path: str, body: dict[str, Any] | None = None
) -> Any | None:
    try:
        return _req_json(cfg, method, path, body)
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="ignore")
        print(f"HTTP {exc.code} {method} {path}: {msg}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"{method} {path} failed: {exc}", file=sys.stderr)
        return None


def _repo_path(cfg: Config) -> str:
    return f"/api/v1/repos/{cfg.owner}/{cfg.repo}"


def _branch_is_behind_main(
    cfg: Config, head_branch: str, base_branch: str = "main"
) -> tuple[bool, str]:
    """Check branch staleness via Gitea compare API.

    This avoids requiring `git` in CI runtime images such as python:3.11-slim.
    """
    path = (
        f"{_repo_path(cfg)}/compare/"
        f"{urllib.parse.quote(base_branch, safe='')}...{urllib.parse.quote(head_branch, safe='')}"
    )
    out = _safe_req_json(cfg, "GET", path)
    if not isinstance(out, dict):
        return False, "compare API unavailable"

    behind_by_raw = out.get("behind_by")
    ahead_by_raw = out.get("ahead_by")
    try:
        behind_by = int(behind_by_raw) if behind_by_raw is not None else 0
    except (TypeError, ValueError):
        behind_by = 0
    try:
        ahead_by = int(ahead_by_raw) if ahead_by_raw is not None else 0
    except (TypeError, ValueError):
        ahead_by = 0

    if behind_by > 0:
        return True, (
            f"branch is behind {base_branch} by {behind_by} commit(s)"
            + (f"; ahead by {ahead_by}" if ahead_by > 0 else "")
        )
    return False, f"branch includes latest {base_branch}"


def _issue_comments(cfg: Config, number: int) -> list[dict[str, Any]]:
    out = _safe_req_json(cfg, "GET", f"{_repo_path(cfg)}/issues/{number}/comments")
    return out if isinstance(out, list) else []


def _post_pr_comment(cfg: Config, number: int, body: str) -> bool:
    payload = {"body": body}
    if cfg.dry_run:
        print(f"[dry-run] comment on PR #{number}: {body}")
        return True
    result = _safe_req_json(
        cfg, "POST", f"{_repo_path(cfg)}/issues/{number}/comments", payload
    )
    return isinstance(result, dict)


def _ensure_stale_comment(cfg: Config, number: int, head: str, reason: str) -> None:
    marker = "[AUTO-STALE-MAIN]"
    comments = _issue_comments(cfg, number)
    for row in comments[-20:]:
        body = str((row or {}).get("body") or "")
        if marker in body:
            return
    body = (
        f"{marker} Branch `{head}` is behind `main` and must be rebased/merged with "
        f"`origin/main` before mergeability checks can pass. ({reason})"
    )
    _post_pr_comment(cfg, number, body)


def list_branches(cfg: Config) -> list[dict[str, Any]]:
    out = _safe_req_json(cfg, "GET", f"{_repo_path(cfg)}/branches")
    return out if isinstance(out, list) else []


def list_open_prs(cfg: Config, base: str | None = None) -> list[dict[str, Any]]:
    q = "state=open"
    if base:
        q += f"&base={urllib.parse.quote(base)}"
    out = _safe_req_json(cfg, "GET", f"{_repo_path(cfg)}/pulls?{q}")
    return out if isinstance(out, list) else []


def _open_pr_for_head(cfg: Config, head_branch: str) -> dict[str, Any] | None:
    prs = list_open_prs(cfg)
    full_head = f"{cfg.owner}:{head_branch}"
    for pr in prs:
        head_ref = (pr.get("head") or {}).get("ref")
        head_full = (pr.get("head") or {}).get("label")
        if head_ref == head_branch or head_full == full_head:
            return pr
    return None


def _enable_merge_check(cfg: Config, pr: dict[str, Any], head_branch: str) -> bool:
    """Enable server-side merge_when_checks_succeed on a PR.

    This does NOT execute a direct merge. It only configures the PR so that
    the Gitea server will merge automatically once all required checks pass.
    Only `merge_when_checks_succeed` is set -- no ``"Do": "merge"`` payload
    is sent, which prevents chise-bot from performing a direct merge action.
    Merge authority is reserved for Merlin (sole merge authority per AGENTS.md).
    """
    number = pr.get("number")
    if not number:
        return False
    payload = {
        "merge_when_checks_succeed": True,
        "head_commit_id": ((pr.get("head") or {}).get("sha") or ""),
    }
    if cfg.dry_run:
        print(
            f"[dry-run] enable merge_when_checks_succeed on PR #{number} ({head_branch})"
        )
        return True
    result = _safe_req_json(
        cfg, "POST", f"{_repo_path(cfg)}/pulls/{number}/merge", payload
    )
    if result is None:
        print(
            f"warning: unable to enable merge_when_checks_succeed for PR #{number} ({head_branch})",
            file=sys.stderr,
        )
        return False
    print(f"enabled merge_when_checks_succeed on PR #{number} ({head_branch})")
    return True


def _merge_pr(cfg: Config, pr: dict[str, Any], head_branch: str) -> bool:
    """Merge a PR once it is green and conflict-free."""
    number = pr.get("number")
    if not number:
        return False
    payload = {
        "head_commit_id": ((pr.get("head") or {}).get("sha") or ""),
        "merge_when_checks_succeed": True,
        "delete_branch_after_merge": True,
    }
    if cfg.dry_run:
        print(f"[dry-run] merge PR #{number} ({head_branch})")
        return True
    result = _safe_req_json(
        cfg, "POST", f"{_repo_path(cfg)}/pulls/{number}/merge", payload
    )
    if result is None:
        print(
            f"warning: unable to merge PR #{number} ({head_branch})",
            file=sys.stderr,
        )
        return False
    print(f"merged PR #{number} ({head_branch})")
    return True


def ensure_prs(cfg: Config) -> int:
    created = 0
    cutoff = datetime.now(UTC) - timedelta(minutes=cfg.max_branch_age_min)
    branches = list_branches(cfg)
    if cfg.source_branch:
        branches = [
            b for b in branches if (b.get("name") or "").strip() == cfg.source_branch
        ]

    for branch in branches:
        name = str(branch.get("name", "")).strip()
        if not name or name in cfg.protected:
            continue
        if name.startswith("dependabot/"):
            continue
        ts_raw = str((branch.get("commit") or {}).get("timestamp") or "").strip()
        if ts_raw:
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).astimezone(
                    UTC
                )
                if ts < cutoff:
                    continue
            except ValueError:
                pass
        is_stale = False
        stale_reason = ""
        if cfg.source_branch and name == cfg.source_branch:
            try:
                is_stale, stale_reason = _branch_is_behind_main(
                    cfg, name, cfg.default_base
                )
            except Exception as e:
                # If API check fails, skip the staleness comment rather than blocking
                stale_reason = f"staleness check unavailable: {e}"
        open_pr = _open_pr_for_head(cfg, name)
        if open_pr:
            if is_stale:
                number = int(open_pr.get("number") or 0)
                if number:
                    _ensure_stale_comment(cfg, number, name, stale_reason)
            if cfg.enable_server_automerge:
                _enable_merge_check(cfg, open_pr, name)
            continue
        title = f"REPO-AUTO-PR-001 {name}"
        body = (
            "Auto-created PR for pushed agent branch.\n\n"
            "Policy: auto-merge is attempted only when conflict-free."
        )
        payload = {"title": title, "head": name, "base": cfg.default_base, "body": body}
        if cfg.dry_run:
            print(f"[dry-run] create PR head={name} base={cfg.default_base}")
            created += 1
            continue
        result = _safe_req_json(cfg, "POST", f"{_repo_path(cfg)}/pulls", payload)
        if result and result.get("number"):
            print(f"created PR #{result['number']} for branch {name}")
            if is_stale:
                _ensure_stale_comment(
                    cfg,
                    int(result["number"]),
                    name,
                    stale_reason,
                )
            if cfg.enable_server_automerge:
                _enable_merge_check(cfg, result, name)
            created += 1
    return created


def _is_mergeable_clean(pr: dict[str, Any]) -> bool:
    if pr.get("state") != "open":
        return False
    mergeable = pr.get("mergeable")
    return mergeable is True


def _ci_gate_ok(cfg: Config, sha: str) -> bool:
    """Return True only when the ci-gate commit context is green.

    Fail-closed: if ci-gate is pending/failed, or if the API call fails,
    we cannot confirm safety — do not merge.
    """
    if not sha:
        return False  # cannot verify — fail closed
    statuses = _safe_req_json(
        cfg,
        "GET",
        f"{_repo_path(cfg)}/commits/{sha}/statuses",
    )
    if statuses is None:
        return False  # API failure — fail closed
    if not isinstance(statuses, list):
        return False  # unexpected response — fail closed
    for s in statuses:
        if isinstance(s, dict) and s.get("context") == "ci-gate":
            # Fail closed on pending, error, or failure.
            if s.get("status") in ("pending", "error", "failure"):
                return False
    return True


def _author_allowed(cfg: Config, pr: dict[str, Any]) -> bool:
    author = ((pr.get("user") or {}).get("login") or "").strip()
    return author in cfg.allowed_authors


def _pr_by_number(cfg: Config, number: int) -> dict[str, Any] | None:
    out = _safe_req_json(cfg, "GET", f"{_repo_path(cfg)}/pulls/{number}")
    return out if isinstance(out, dict) else None


def _wait_until_mergeable(
    cfg: Config, number: int, attempts: int = 6
) -> dict[str, Any] | None:
    for _ in range(attempts):
        pr = _pr_by_number(cfg, number)
        if not pr:
            return None
        if pr.get("mergeable") is not None:
            return pr
        time.sleep(2)
    return _pr_by_number(cfg, number)


def auto_merge(cfg: Config) -> int:
    """Merge eligible open PRs once checks are green.

    The job is intentionally conservative:
    - only open PRs on the configured base are considered
    - only mergeable PRs are considered
    - only authorized authors are considered
    - merge API failures are retried with bounded wait logic
    """
    merged = 0
    prs = list_open_prs(cfg, base=cfg.default_base)
    if cfg.source_branch:
        full_head = f"{cfg.owner}:{cfg.source_branch}"
        prs = [
            pr
            for pr in prs
            if ((pr.get("head") or {}).get("ref") == cfg.source_branch)
            or ((pr.get("head") or {}).get("label") == full_head)
        ]

    for pr in prs:
        number = pr.get("number")
        if not number:
            continue
        refreshed = _wait_until_mergeable(cfg, int(number))
        if refreshed:
            pr = refreshed
        if not _author_allowed(cfg, pr):
            continue
        if not _is_mergeable_clean(pr):
            print(
                f"skip PR #{number}: not conflict-free (mergeable={pr.get('mergeable')})"
            )
            continue
        status = _safe_req_json(
            cfg,
            "GET",
            f"{_repo_path(cfg)}/commits/{((pr.get('head') or {}).get('sha') or '')}/status",
        )
        if not isinstance(status, dict) or status.get("state") != "success":
            print(
                f"skip PR #{number}: commit status not green (state={status.get('state') if isinstance(status, dict) else 'unknown'})"
            )
            continue

        sha = (pr.get("head") or {}).get("sha") or ""
        if not _ci_gate_ok(cfg, sha):
            print(f"skip PR #{number}: ci-gate not green")
            continue

        for attempt in range(1, 4):
            if _merge_pr(cfg, pr, str(number)):
                merged += 1
                break
            if attempt < 3:
                refreshed = _wait_until_mergeable(cfg, int(number), attempts=2)
                if refreshed:
                    pr = refreshed
                time.sleep(2)
        else:
            print(
                f"warning: merge attempts exhausted for PR #{number} ({pr.get('head', {}).get('ref', 'unknown')})",
                file=sys.stderr,
            )
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto PR creation and merge-check configuration"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ensure = sub.add_parser(
        "ensure-prs", help="Create missing PRs for pushed branches"
    )
    p_ensure.add_argument("--dry-run", action="store_true")

    p_merge = sub.add_parser(
        "automerge", help="Merge eligible open PRs once checks are green"
    )
    p_merge.add_argument("--dry-run", action="store_true")
    p_merge.add_argument(
        "--enable-automerge",
        action="store_true",
        help="Explicitly enable merge actions for eligible PRs",
    )

    args = parser.parse_args()
    cfg = _cfg(dry_run=bool(getattr(args, "dry_run", False)))
    if not cfg.token:
        print("GITEA_TOKEN is required", file=sys.stderr)
        return 2

    if args.cmd == "ensure-prs":
        created = ensure_prs(cfg)
        print(f"auto-pr complete: created={created}")
        return 0
    if args.cmd == "automerge":
        if not args.enable_automerge:
            print("automerge skipped: pass --enable-automerge to allow merge actions")
            return 0
        merged = auto_merge(cfg)
        print(f"automerge complete: merged={merged}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
