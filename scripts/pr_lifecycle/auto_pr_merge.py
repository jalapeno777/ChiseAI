#!/usr/bin/env python3
"""Auto-create PRs from pushed branches and auto-merge conflict-free PRs.

Policy:
- Auto-create PRs from non-protected branches targeting main when no open PR exists.
- Auto-merge open PRs to main only when mergeable=true.
- Merge conflicts are skipped (never forced).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
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
    dry_run: bool


def _cfg(dry_run: bool) -> Config:
    protected_raw = os.getenv("CHISE_AUTOPR_PROTECTED_BRANCHES", "main,develop")
    authors_raw = os.getenv("CHISE_AUTOMERGE_AUTHORS", "chise-bot,craig")
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
    with urllib.request.urlopen(req, timeout=30) as resp:
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


def ensure_prs(cfg: Config) -> int:
    created = 0
    for branch in list_branches(cfg):
        name = str(branch.get("name", "")).strip()
        if not name or name in cfg.protected:
            continue
        if name.startswith("dependabot/"):
            continue
        if _open_pr_for_head(cfg, name):
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
            created += 1
    return created


def _is_mergeable_clean(pr: dict[str, Any]) -> bool:
    if pr.get("state") != "open":
        return False
    mergeable = pr.get("mergeable")
    return mergeable is True


def _author_allowed(cfg: Config, pr: dict[str, Any]) -> bool:
    author = ((pr.get("user") or {}).get("login") or "").strip()
    return author in cfg.allowed_authors


def auto_merge(cfg: Config) -> int:
    merged = 0
    for pr in list_open_prs(cfg, base=cfg.default_base):
        number = pr.get("number")
        if not number:
            continue
        if not _author_allowed(cfg, pr):
            continue
        if not _is_mergeable_clean(pr):
            print(f"skip PR #{number}: not conflict-free (mergeable={pr.get('mergeable')})")
            continue

        if cfg.dry_run:
            print(f"[dry-run] merge PR #{number}")
            merged += 1
            continue

        payload = {
            "Do": "merge",
            "delete_branch_after_merge": False,
            "merge_commit_id": "",
            "merge_message_field": f"Auto-merged PR #{number} (conflict-free)",
        }
        result = _safe_req_json(
            cfg, "POST", f"{_repo_path(cfg)}/pulls/{number}/merge", payload
        )
        if result is not None:
            print(f"merged PR #{number}")
            merged += 1
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto PR creation and conflict-only merge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ensure = sub.add_parser("ensure-prs", help="Create missing PRs for pushed branches")
    p_ensure.add_argument("--dry-run", action="store_true")

    p_merge = sub.add_parser("automerge", help="Merge open conflict-free PRs")
    p_merge.add_argument("--dry-run", action="store_true")

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
        merged = auto_merge(cfg)
        print(f"automerge complete: merged={merged}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
