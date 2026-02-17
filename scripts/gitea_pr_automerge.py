#!/usr/bin/env python3
"""
Open a PR on Gitea and enable merge-when-checks-succeed (or merge immediately).

This is intended for autonomous agents to keep the repo convergent:
- open PR for a branch
- optionally set "merge_when_checks_succeed"
- optionally poll commit status contexts and merge once green

Auth:
- Set GITEA_TOKEN in environment (short-lived PAT recommended).

Environment Variables:
- GITEA_POLL_INTERVAL: Seconds between status checks (default: 60)
- GITEA_MAX_RETRIES: Maximum merge attempts before giving up (default: 3)
- AGENT_ID: Caller identity (must be `merlin` for PR submission/merge)
- CHISE_ALLOW_NON_MERLIN_PR: Set to `1` only for explicit human override
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


def _get_pr(
    owner: str, repo: str, base_url: str, token: str, head_ref: str
) -> dict | None:
    """Find the open PR for a given head branch ref.

    Note: Some Gitea installations do not reliably honor the `head=` query
    parameter for the pulls listing endpoint. We therefore always filter
    client-side.
    """

    q = urllib.parse.urlencode({"state": "open", "limit": "50"})
    url = f"{base_url}/api/v1/repos/{owner}/{repo}/pulls?{q}"
    prs = _req_json("GET", url, token)
    if not isinstance(prs, list):
        return None
    for pr in prs:
        try:
            if pr.get("head", {}).get("ref") == head_ref:
                return pr
        except AttributeError:
            continue
    return None


def _create_pr(
    owner: str,
    repo: str,
    base_url: str,
    token: str,
    *,
    head: str,
    base: str,
    title: str,
    body: str,
) -> dict:
    url = f"{base_url}/api/v1/repos/{owner}/{repo}/pulls"
    return _req_json(
        "POST",
        url,
        token,
        {"head": head, "base": base, "title": title, "body": body, "draft": False},
    )


def _commit_status(owner: str, repo: str, base_url: str, token: str, sha: str) -> dict:
    url = f"{base_url}/api/v1/repos/{owner}/{repo}/commits/{sha}/status"
    return _req_json("GET", url, token)


def _get_pr_reviews(
    owner: str, repo: str, base_url: str, token: str, index: int
) -> list:
    """Get PR reviews to check for required approvals."""
    url = f"{base_url}/api/v1/repos/{owner}/{repo}/pulls/{index}/reviews"
    try:
        result = _req_json("GET", url, token)
        if isinstance(result, list):
            return result
        return []
    except RuntimeError:
        return []


def _has_required_approval(reviews: list) -> bool:
    """Check if PR has at least one required reviewer approval."""
    return any(review.get("state") == "APPROVED" for review in reviews)


def _post_pr_comment(
    owner: str,
    repo: str,
    base_url: str,
    token: str,
    index: int,
    body: str,
) -> None:
    """Post a comment on a PR."""
    url = f"{base_url}/api/v1/repos/{owner}/{repo}/issues/{index}/comments"
    _req_json("POST", url, token, {"body": body})


def _check_merge_conflict(
    owner: str, repo: str, base_url: str, token: str, index: int
) -> bool:
    """Check if PR has merge conflicts.

    Returns True if there is a conflict, False otherwise.
    """
    url = f"{base_url}/api/v1/repos/{owner}/{repo}/pulls/{index}"
    try:
        pr = _req_json("GET", url, token)
        mergeable = pr.get("mergeable")
        # mergeable can be True, False, or None (unknown/not computed yet)
        return mergeable is False
    except RuntimeError:
        return False


def _merge_pr(
    owner: str,
    repo: str,
    base_url: str,
    token: str,
    *,
    index: int,
    head_sha: str,
    merge_when_checks_succeed: bool,
    delete_branch_after_merge: bool,
) -> None:
    url = f"{base_url}/api/v1/repos/{owner}/{repo}/pulls/{index}/merge"
    _req_json(
        "POST",
        url,
        token,
        {
            "Do": "merge",
            "head_commit_id": head_sha,
            "merge_when_checks_succeed": merge_when_checks_succeed,
            "delete_branch_after_merge": delete_branch_after_merge,
        },
    )


def _try_merge_with_retry(
    owner: str,
    repo: str,
    base_url: str,
    token: str,
    index: int,
    head_sha: str,
    delete_branch: bool,
    max_retries: int,
) -> tuple[bool, int]:
    """Attempt to merge PR with retry logic.

    Returns (success, attempts_made).
    """
    for attempt in range(1, max_retries + 1):
        try:
            _merge_pr(
                owner,
                repo,
                base_url,
                token,
                index=index,
                head_sha=head_sha,
                merge_when_checks_succeed=False,
                delete_branch_after_merge=delete_branch,
            )
            return True, attempt
        except RuntimeError:
            if attempt == max_retries:
                return False, attempt
            # Wait briefly before retry
            time.sleep(1)
    return False, max_retries


def main() -> int:
    # Environment variable defaults
    default_poll_interval = int(os.getenv("GITEA_POLL_INTERVAL", "60"))
    default_max_retries = int(os.getenv("GITEA_MAX_RETRIES", "3"))

    p = argparse.ArgumentParser()
    p.add_argument(
        "--base-url",
        default=os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000"),
    )
    p.add_argument("--owner", default=os.getenv("GITEA_OWNER", "craig"))
    p.add_argument("--repo", default=os.getenv("GITEA_REPO", "ChiseAI"))
    p.add_argument("--base", default="main")
    p.add_argument("--head", required=True, help="Branch name, e.g. feature/foo")
    p.add_argument(
        "--story-id",
        required=True,
        help="Story ID to include in PR title, e.g. ST-NS-001 or CH-PB-001",
    )
    p.add_argument("--title", default=None)
    p.add_argument("--body", default="")
    p.add_argument("--required-context", default="ci/woodpecker/pr/woodpecker")
    p.add_argument(
        "--wait",
        action="store_true",
        help="Poll until required context is success, then merge",
    )
    p.add_argument("--timeout-sec", type=int, default=1800)
    p.add_argument(
        "--poll-sec",
        type=int,
        default=default_poll_interval,
        help=f"Seconds between status checks (default: {default_poll_interval})",
    )
    p.add_argument(
        "--max-retries",
        type=int,
        default=default_max_retries,
        help=(
            f"Maximum merge attempts before giving up (default: {default_max_retries})"
        ),
    )
    p.add_argument(
        "--delete-branch", action="store_true", help="Delete branch after merge"
    )
    p.add_argument(
        "--require-approval",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require at least one reviewer approval before merging (default: True)",
    )
    p.add_argument(
        "--agent-id",
        default=os.getenv("AGENT_ID", "merlin"),
        help="Agent identity. Must be 'merlin' unless explicit override is enabled.",
    )
    args = p.parse_args()

    token = os.getenv("GITEA_TOKEN")
    if not token:
        print("ERROR: GITEA_TOKEN env var is required", file=sys.stderr)
        return 1

    agent_id = (args.agent_id or "").strip().lower()
    allow_non_merlin = os.getenv("CHISE_ALLOW_NON_MERLIN_PR", "0") == "1"
    if agent_id != "merlin" and not allow_non_merlin:
        print(
            "ERROR: PR submission is restricted to agent 'merlin'. "
            "Set --agent-id merlin (or AGENT_ID=merlin).",
            file=sys.stderr,
        )
        return 1

    base_url = args.base_url.rstrip("/")
    head_ref = args.head

    story_id = args.story_id.strip()
    if not story_id:
        print("ERROR: --story-id must be non-empty", file=sys.stderr)
        return 1

    pr = _get_pr(args.owner, args.repo, base_url, token, head_ref)
    if pr is None:
        base_title = args.title or f"{head_ref}"
        title = f"{story_id} {base_title}"
        pr = _create_pr(
            args.owner,
            args.repo,
            base_url,
            token,
            head=head_ref,
            base=args.base,
            title=title,
            body=args.body,
        )
    else:
        # If PR exists but lacks story ID in title, patch it to include the prefix.
        pr_title = str(pr.get("title", ""))
        if story_id not in pr_title:
            pr_num = int(pr["number"])
            url = f"{base_url}/api/v1/repos/{args.owner}/{args.repo}/pulls/{pr_num}"
            new_title = f"{story_id} {pr_title}".strip()
            _req_json("PATCH", url, token, {"title": new_title})
            pr["title"] = new_title

    index = int(pr["number"])
    sha = pr["head"]["sha"]

    # Check for merge conflicts before proceeding
    if _check_merge_conflict(args.owner, args.repo, base_url, token, index):
        msg = (
            "⚠️ **Auto-merge skipped**: This PR has merge conflicts "
            "that must be resolved before merging.\n\n"
            "@author please resolve the conflicts and re-run the auto-merge."
        )
        _post_pr_comment(args.owner, args.repo, base_url, token, index, msg)
        print(
            f"ERROR: PR #{index} has merge conflicts. Skipping auto-merge.",
            file=sys.stderr,
        )
        return 1

    # Check for required reviewer approval
    if args.require_approval:
        reviews = _get_pr_reviews(args.owner, args.repo, base_url, token, index)
        if not _has_required_approval(reviews):
            print(
                f"ERROR: PR #{index} does not have required reviewer approval",
                file=sys.stderr,
            )
            return 1

    if not args.wait:
        # Enable server-side automerge when checks succeed.
        _merge_pr(
            args.owner,
            args.repo,
            base_url,
            token,
            index=index,
            head_sha=sha,
            merge_when_checks_succeed=True,
            delete_branch_after_merge=args.delete_branch,
        )
        print(f"PR #{index}: merge_when_checks_succeed enabled")
        return 0

    deadline = time.time() + args.timeout_sec
    while time.time() < deadline:
        # Re-check for merge conflicts during polling
        if _check_merge_conflict(args.owner, args.repo, base_url, token, index):
            msg = (
                "⚠️ **Auto-merge skipped**: This PR has merge conflicts "
                "that must be resolved before merging.\n\n"
                "@author please resolve the conflicts and re-run the auto-merge."
            )
            _post_pr_comment(args.owner, args.repo, base_url, token, index, msg)
            print(
                f"ERROR: PR #{index} has merge conflicts during polling. "
                f"Skipping auto-merge.",
                file=sys.stderr,
            )
            return 1

        status = _commit_status(args.owner, args.repo, base_url, token, sha)
        state = status.get("state")
        statuses = status.get("statuses") or []
        ctx_state = None
        for s in statuses:
            if s.get("context") == args.required_context:
                # Gitea uses "status" in per-context entries; some clients use "state".
                ctx_state = s.get("state") or s.get("status")
                break
        if ctx_state == "success":
            success, attempts = _try_merge_with_retry(
                args.owner,
                args.repo,
                base_url,
                token,
                index,
                sha,
                args.delete_branch,
                args.max_retries,
            )
            if success:
                print(
                    f"PR #{index}: merged (state={state}, ctx={ctx_state}, "
                    f"attempts={attempts})"
                )
                return 0
            else:
                print(
                    f"ERROR: Failed to merge PR #{index} after {attempts} attempt(s)",
                    file=sys.stderr,
                )
                return 1
        if ctx_state in {"failure", "error"}:
            print(
                f"ERROR: required context {args.required_context} is {ctx_state}",
                file=sys.stderr,
            )
            return 1

        time.sleep(args.poll_sec)

    print("ERROR: timed out waiting for required context to succeed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
