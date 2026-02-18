#!/usr/bin/env python3
"""
Post a PR review on Gitea (APPROVED or REQUEST_CHANGES) using a dedicated token.

Why: keep "review required" while staying autonomous. Use a separate user/token
from the PR author to preserve the gate's meaning.

Auth:
- Uses GITEA_REVIEW_TOKEN by default (configurable via --token-env).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from config.bootstrap import bootstrap

# Bootstrap environment first (must be before any env access)
bootstrap(load_env=True)


def _req_json(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = None
    headers = {"Accept": "application/json", "Authorization": f"token {token}"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {e.code}: {msg}") from e


def main() -> int:
    p = argparse.ArgumentParser(description="Post a PR review on Gitea")
    p.add_argument(
        "--base-url",
        default=os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000").rstrip(
            "/"
        ),
    )
    p.add_argument("--owner", default=os.getenv("GITEA_OWNER", "craig"))
    p.add_argument("--repo", default=os.getenv("GITEA_REPO", "ChiseAI"))
    p.add_argument("--pr", type=int, required=True, help="PR number")
    p.add_argument(
        "--state",
        required=True,
        choices=["APPROVED", "REQUEST_CHANGES"],
        help="Review event/state (Gitea uses this to submit the review)",
    )
    p.add_argument("--body", default="", help="Review comment body")
    p.add_argument(
        "--token-env",
        default="GITEA_REVIEW_TOKEN",
        help="Env var containing review token (default: GITEA_REVIEW_TOKEN)",
    )
    args = p.parse_args()

    token = os.getenv(args.token_env)
    if not token:
        print(f"ERROR: {args.token_env} env var is required", file=sys.stderr)
        return 1

    url = (
        f"{args.base_url}/api/v1/repos/{args.owner}/{args.repo}/pulls/{args.pr}/reviews"
    )
    # Gitea treats approvals as "events". Using "event" triggers server-side validation
    # (including "cannot approve your own PR"), which is desired.
    _req_json("POST", url, token, {"event": args.state, "body": args.body})
    print(f"PR #{args.pr}: review posted event={args.state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
