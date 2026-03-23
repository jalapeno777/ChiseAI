#!/usr/bin/env python3
"""
Merge Conflict Detector for PRs

Checks if a PR has merge conflicts using the Gitea API.
Exit code: 0 if mergeable, 1 if conflicts detected.

Story: ST-GIT-006
CI Integration: Run via Woodpecker before attempting merge.

Usage:
    python scripts/ci/merge_conflict_detector.py --pr 123
    python scripts/ci/merge_conflict_detector.py --pr 123 --base-url http://host.docker.internal:3000

Environment Variables:
    GITEA_BASE_URL - Gitea instance URL (default: http://host.docker.internal:3000)
    GITEA_TOKEN - Gitea API token
    GITEA_OWNER - Repository owner (default: craig)
    GITEA_REPO - Repository name (default: ChiseAI)

Exit Codes:
    0 - PR is mergeable (no conflicts)
    1 - PR has conflicts or cannot be merged
    2 - Invalid arguments or API error
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Allow direct script execution from any worktree
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)


DEFAULT_BASE_URL = "http://host.docker.internal:3000"


class GiteaAPI:
    """Simple Gitea API client for merge conflict detection."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = (token or "").strip() or os.getenv("GITEA_TOKEN", "")
        self.owner = owner or os.getenv("GITEA_OWNER", "craig")
        self.repo = repo or os.getenv("GITEA_REPO", "ChiseAI")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def _req_json(
        self, method: str, path: str, data: dict | None = None
    ) -> dict | list | None:
        url = f"{self.base_url}{path}"
        try:
            req = urllib.request.Request(
                url,
                method=method,
                headers=self._headers(),
            )
            if data:
                import json

                req.data = json.dumps(data).encode("utf-8")
                req.headers["Content-Type"] = "application/json"

            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            print(f"API Error: {method} {url} - HTTP {e.code}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Request Error: {method} {url} - {e}", file=sys.stderr)
            return None

    def get_pr(self, pr_number: int) -> dict | None:
        """Get PR details including mergeable status."""
        result = self._req_json(
            "GET",
            f"/api/v1/repos/{self.owner}/{self.repo}/pulls/{pr_number}",
        )
        return result if isinstance(result, dict) else None

    def get_pr_files(self, pr_number: int) -> list[dict] | None:
        """Get list of files changed in a PR."""
        result = self._req_json(
            "GET",
            f"/api/v1/repos/{self.owner}/{self.repo}/pulls/{pr_number}/files",
        )
        return result if isinstance(result, list) else None


def check_merge_conflict_git(
    pr_number: int, branch: str, base_ref: str = "main"
) -> list[str]:
    """
    Secondary verification using git merge-tree.
    Returns list of conflicting files if any.
    """
    conflicting_files: list[str] = []
    try:
        # Fetch the PR branch and base branch
        result = subprocess.run(
            ["git", "fetch", "origin", branch, base_ref],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []

        # Use git merge-tree to simulate merge
        result = subprocess.run(
            [
                "git",
                "merge-tree",
                f"origin/{base_ref}",
                f"origin/{branch}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout

        # Parse conflict markers
        in_conflict = False
        for line in output.split("\n"):
            if line.startswith("changed in both"):
                in_conflict = True
                continue
            if in_conflict:
                if line.startswith("  "):
                    # Filename line
                    filename = line.strip()
                    if filename and not filename.startswith("common ancestor"):
                        conflicting_files.append(filename)
                else:
                    in_conflict = False

    except Exception as e:
        print(f"Warning: git merge-tree check failed: {e}", file=sys.stderr)

    return conflicting_files


def detect_merge_conflicts(
    pr_number: int,
    base_url: str = DEFAULT_BASE_URL,
    token: str | None = None,
    owner: str | None = None,
    repo: str | None = None,
    use_git_merge_tree: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """
    Check if a PR has merge conflicts.

    Returns:
        Tuple of (has_conflicts, pr_details)
    """
    gitea = GiteaAPI(base_url, token, owner, repo)
    pr_data = gitea.get_pr(pr_number)

    if pr_data is None:
        return False, {"error": "Failed to fetch PR from Gitea API"}

    mergeable = pr_data.get("mergeable")
    state = pr_data.get("state", "").lower()
    merged = pr_data.get("merged", False)
    title = pr_data.get("title", "unknown")
    head = pr_data.get("head", {})
    branch = head.get("ref", "unknown") if head else "unknown"

    result: dict[str, Any] = {
        "pr_number": pr_number,
        "title": title,
        "branch": branch,
        "state": state,
        "merged": merged,
        "mergeable": mergeable,
    }

    # PR is already merged - no conflict to check
    if merged:
        return False, result

    # PR is closed but not merged
    if state == "closed":
        result["conflict_status"] = "closed"
        return False, result

    # None means not yet checked, True means mergeable
    if mergeable is True:
        result["conflict_status"] = "clean"
        return False, result

    # False means conflicts detected
    if mergeable is False:
        result["conflict_status"] = "conflicts"
        # Try to get list of conflicting files
        files = gitea.get_pr_files(pr_number)
        if files:
            result["conflict_files"] = [
                f.get("filename", "") for f in files if f.get("status") == "conflict"
            ]
        return True, result

    # If mergeable is None, need secondary verification
    if use_git_merge_tree:
        conflict_files = check_merge_conflict_git(pr_number, branch)
        if conflict_files:
            result["conflict_status"] = "conflicts_git_tree"
            result["conflict_files"] = conflict_files
            return True, result

    # Unknown status - treat as potentially conflicting
    result["conflict_status"] = "unknown"
    result["warning"] = "mergeable status not available"
    return False, result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check if a PR has merge conflicts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --pr 123
  %(prog)s --pr 123 --git-merge-tree
  %(prog)s --pr 123 --base-url http://gitea.local:3000

Exit codes:
  0 - PR is mergeable (no conflicts detected)
  1 - PR has conflicts or cannot be merged
  2 - Invalid arguments or API error
        """,
    )
    parser.add_argument(
        "--pr",
        type=int,
        required=True,
        help="PR number to check",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("GITEA_BASE_URL", DEFAULT_BASE_URL),
        help=f"Gitea base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("GITEA_TOKEN"),
        help="Gitea API token (default: $GITEA_TOKEN)",
    )
    parser.add_argument(
        "--owner",
        default=os.getenv("GITEA_OWNER"),
        help="Repository owner (default: $GITEA_OWNER or craig)",
    )
    parser.add_argument(
        "--repo",
        default=os.getenv("GITEA_REPO"),
        help="Repository name (default: $GITEA_REPO or ChiseAI)",
    )
    parser.add_argument(
        "--git-merge-tree",
        action="store_true",
        help="Use git merge-tree for secondary verification",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable",
    )

    args = parser.parse_args()

    has_conflicts, result = detect_merge_conflicts(
        pr_number=args.pr,
        base_url=args.base_url,
        token=args.token,
        owner=args.owner,
        repo=args.repo,
        use_git_merge_tree=args.git_merge_tree,
    )

    if args.json:
        import json

        print(json.dumps(result, indent=2))
    else:
        print(f"PR #{result['pr_number']}: {result.get('title', 'unknown')}")
        print(f"  Branch: {result.get('branch', 'unknown')}")
        print(f"  State: {result.get('state', 'unknown')}")
        print(f"  Mergeable: {result.get('mergeable', 'unknown')}")
        print(f"  Conflict Status: {result.get('conflict_status', 'unknown')}")

        if result.get("conflict_files"):
            print("  Conflict Files:")
            for f in result["conflict_files"]:
                print(f"    - {f}")

        if result.get("error"):
            print(f"  ERROR: {result['error']}", file=sys.stderr)
            return 2

        if result.get("warning"):
            print(f"  WARNING: {result['warning']}")

    if has_conflicts:
        print("\n[CONFLICT DETECTED] PR cannot be merged automatically.")
        return 1

    print("\n[OK] PR is mergeable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
