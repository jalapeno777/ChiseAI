#!/usr/bin/env python3
"""Stale PR Detector - Detects PRs that are behind main branch.

This module provides functionality to detect when a PR branch has fallen
behind main, requiring a rebase to maintain mergeability.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

# Redis key patterns
STALE_PREFIX = "bmad:chiseai:pr:stale"
REBASE_COOLDOWN_KEY = "bmad:chiseai:pr:rebase:cooldown"

# Configuration
DEFAULT_REBASE_COOLDOWN_MIN = int(os.getenv("CHISE_PR_REBASE_COOLDOWN_MIN", "10"))

# Gitea configuration
GITEA_BASE_URL = os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000").rstrip(
    "/"
)
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "")
GITEA_OWNER = os.getenv("GITEA_OWNER", "craig")
GITEA_REPO = os.getenv("GITEA_REPO", "ChiseAI")


def _redis_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a redis-cli command."""
    host = os.getenv("CHISE_REDIS_HOST", "host.docker.internal")
    port = int(os.getenv("CHISE_REDIS_PORT", "6380"))
    db = int(os.getenv("CHISE_REDIS_DB", "0"))

    return subprocess.run(  # nosec B607
        ["redis-cli", "-h", host, "-p", str(port), "-n", str(db), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _utc_now() -> str:
    """Get current UTC timestamp as ISO string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class StaleDetector:
    """Detects PRs that are behind main."""

    def __init__(self, repo_path: str | None = None):
        """Initialize the stale detector.

        Args:
            repo_path: Path to the git repository. If None, uses the repo containing
                       this script.
        """
        if repo_path is None:
            repo_path = str(Path(__file__).parent.parent.parent)
        self.repo_path = repo_path

    def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run a git command in the repository."""
        return subprocess.run(
            ["git", "-C", self.repo_path] + list(args),
            text=True,
            capture_output=True,
            check=False,
        )

    def is_behind_main(self, branch: str) -> tuple[bool, int]:
        """Check if a branch is behind main.

        Uses `git merge-base --is-ancestor` to determine if the branch's
        commit history is behind main.

        Args:
            branch: The branch name to check.

        Returns:
            Tuple of (is_behind, commits_behind). is_behind is True if the
            branch has commits that are not in main. commits_behind is the
            approximate number of commits main is ahead.
        """
        # Get the SHA of main
        main_sha_result = self._run_git("rev-parse", "main")
        if main_sha_result.returncode != 0:
            return False, 0

        # Get the SHA of the branch
        branch_sha_result = self._run_git("rev-parse", branch)
        if branch_sha_result.returncode != 0:
            return False, 0

        main_sha = main_sha_result.stdout.strip()
        branch_sha = branch_sha_result.stdout.strip()

        if not main_sha or not branch_sha:
            return False, 0

        # Check if branch is behind main using merge-base
        # If main is an ancestor of branch, then branch is NOT behind
        is_ancestor_result = self._run_git(
            "merge-base", "--is-ancestor", main_sha, branch_sha
        )

        # If main_sha IS an ancestor of branch_sha, then branch includes main's commits
        # so branch is NOT behind. merge-base returns 0 if first arg is ancestor of second
        is_behind = is_ancestor_result.returncode != 0

        # Count commits behind
        commits_behind = 0
        if is_behind:
            count_result = self._run_git(
                "rev-list",
                "--count",
                f"{branch}..main",
            )
            if count_result.returncode == 0:
                try:
                    commits_behind = int(count_result.stdout.strip())
                except ValueError:
                    commits_behind = 0

        return is_behind, commits_behind

    def get_ahead_behind(self, branch: str) -> dict[str, int]:
        """Get ahead/behind counts for a branch compared to main.

        Args:
            branch: The branch name to check.

        Returns:
            Dict with 'ahead' and 'behind' counts.
        """
        result = self._run_git(
            "rev-list", "--left-right", "--count", f"{branch}...main"
        )
        if result.returncode != 0:
            return {"ahead": 0, "behind": 0}

        try:
            ahead, behind = result.stdout.strip().split()
            return {"ahead": int(ahead), "behind": int(behind)}
        except (ValueError, IndexError):
            return {"ahead": 0, "behind": 0}

    def check_branch_is_feature(self, branch: str) -> bool:
        """Check if a branch is a feature branch.

        Args:
            branch: The branch name to check.

        Returns:
            True if branch starts with 'feature/' or 'fix/'.
        """
        return branch.startswith("feature/") or branch.startswith("fix/")

    def track_stale_pr(
        self, pr_number: int, is_behind: bool, commits_behind: int
    ) -> None:
        """Track stale PR state in Redis.

        Args:
            pr_number: The PR number.
            is_behind: Whether the PR is behind main.
            commits_behind: Number of commits behind.
        """
        key = f"{STALE_PREFIX}:{pr_number}"

        if is_behind:
            data = {
                "is_behind": "true",
                "commits_behind": str(commits_behind),
                "detected_at": _utc_now(),
            }
        else:
            # Clear stale tracking
            _redis_cli("DEL", key)
            return

        # Store as hash
        for field, value in data.items():
            _redis_cli("HSET", key, field, value)

        # Set TTL (24 hours for stale PRs)
        _redis_cli("EXPIRE", key, "86400")

    def get_stale_pr_state(self, pr_number: int) -> dict[str, Any] | None:
        """Get stale PR state from Redis.

        Args:
            pr_number: The PR number.

        Returns:
            Dict with stale PR state or None if not tracked.
        """
        key = f"{STALE_PREFIX}:{pr_number}"
        result = _redis_cli("HGETALL", key)

        if result.returncode != 0 or not result.stdout.strip():
            return None

        lines = result.stdout.strip().split("\n")
        data: dict[str, str] = {}
        for i in range(0, len(lines), 2):
            if i + 1 < len(lines):
                data[lines[i]] = lines[i + 1]

        if not data:
            return None

        return {
            "is_behind": data.get("is_behind", "false").lower() == "true",
            "commits_behind": int(data.get("commits_behind", "0")),
            "detected_at": data.get("detected_at", ""),
        }

    def is_in_rebase_cooldown(self, pr_number: int) -> bool:
        """Check if a PR is in rebase cooldown period.

        Args:
            pr_number: The PR number.

        Returns:
            True if PR was recently rebased (within cooldown period).
        """
        key = f"{REBASE_COOLDOWN_KEY}:{pr_number}"
        result = _redis_cli("EXISTS", key)
        return result.returncode == 0 and result.stdout.strip() == "1"

    def set_rebase_cooldown(
        self, pr_number: int, cooldown_min: int | None = None
    ) -> None:
        """Set rebase cooldown for a PR.

        Args:
            pr_number: The PR number.
            cooldown_min: Cooldown period in minutes. Defaults to DEFAULT_REBASE_COOLDOWN_MIN.
        """
        if cooldown_min is None:
            cooldown_min = DEFAULT_REBASE_COOLDOWN_MIN

        key = f"{REBASE_COOLDOWN_KEY}:{pr_number}"
        _redis_cli("SET", key, _utc_now())
        _redis_cli("EXPIRE", key, str(cooldown_min * 60))

    def clear_rebase_cooldown(self, pr_number: int) -> None:
        """Clear rebase cooldown for a PR.

        Args:
            pr_number: The PR number.
        """
        key = f"{REBASE_COOLDOWN_KEY}:{pr_number}"
        _redis_cli("DEL", key)

    def alert_discord_stale_pr(
        self,
        pr_number: int,
        branch: str,
        commits_behind: int,
        discord_webhook_url: str | None = None,
    ) -> bool:
        """Send Discord alert for stale PR.

        Args:
            pr_number: The PR number.
            branch: The branch name.
            commits_behind: Number of commits behind main.
            discord_webhook_url: Discord webhook URL. If None, uses DISCORD_WEBHOOK_URL env var.

        Returns:
            True if alert was sent successfully.
        """
        if discord_webhook_url is None:
            discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

        if not discord_webhook_url:
            return False

        import urllib.request

        message = {
            "content": (
                f"⚠️ **Stale PR Detected**: PR #{pr_number}\n"
                f"Branch: `{branch}`\n"
                f"Commits behind main: **{commits_behind}**\n"
                f"Action: Auto-rebase will be attempted."
            )
        }

        try:
            data = json.dumps(message).encode("utf-8")
            req = urllib.request.Request(
                discord_webhook_url,
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
                return resp.status == 200
        except Exception as e:
            print(f"Discord alert failed: {e}", file=sys.stderr)
            return False


class GiteaAPI:
    """Simple Gitea API client for listing PRs."""

    def __init__(self, base_url: str, token: str, owner: str, repo: str):
        self.base_url = base_url
        self.token = token
        self.owner = owner
        self.repo = repo

    def _req_json(
        self, method: str, path: str, body: dict | None = None
    ) -> dict | list | None:
        """Make a request to the Gitea API."""
        import urllib.error
        import urllib.request

        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"token {self.token}",
        }

        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, method=method, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            print(f"API Error: {method} {url} - HTTP {e.code}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Request Error: {method} {url} - {e}", file=sys.stderr)
            return None

    def list_open_prs(self) -> list[dict]:
        """List all open pull requests.

        Returns:
            List of PR data dicts.
        """
        result = self._req_json(
            "GET",
            f"/api/v1/repos/{self.owner}/{self.repo}/pulls?state=open&limit=100",
        )
        if isinstance(result, list):
            return result
        return []

    def get_pr(self, pr_number: int) -> dict | None:
        """Get PR details."""
        result = self._req_json(
            "GET",
            f"/api/v1/repos/{self.owner}/{self.repo}/pulls/{pr_number}",
        )
        if isinstance(result, dict):
            return result
        return None


def main() -> int:
    """CLI for stale PR detection."""
    import argparse

    p = argparse.ArgumentParser(description="Stale PR Detector")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Check command
    check = sub.add_parser("check", help="Check if a branch is behind main")
    check.add_argument("--branch", required=True, help="Branch name to check")

    # Detect command (for all open PRs)
    detect = sub.add_parser("detect", help="Detect stale PRs from Gitea")
    detect.add_argument(
        "--discord",
        action="store_true",
        help="Send Discord alerts if channel configured",
    )

    # List stale command
    sub.add_parser("list-stale", help="List known stale PRs from Redis")

    args = p.parse_args()

    detector = StaleDetector()
    gitea = GiteaAPI(GITEA_BASE_URL, GITEA_TOKEN, GITEA_OWNER, GITEA_REPO)

    if args.cmd == "check":
        is_behind, commits_behind = detector.is_behind_main(args.branch)
        print(f"Branch '{args.branch}' is behind main: {is_behind}")
        print(f"Commits behind: {commits_behind}")
        return 0

    elif args.cmd == "detect":
        open_prs = gitea.list_open_prs()
        stale_count = 0

        for pr in open_prs:
            pr_number = pr.get("number")
            if not pr_number:
                continue

            branch = pr.get("head", {}).get("ref", "")
            if not detector.check_branch_is_feature(branch):
                continue

            is_behind, commits_behind = detector.is_behind_main(branch)

            if is_behind:
                stale_count += 1
                print(
                    f"Stale PR #{pr_number}: branch={branch}, commits_behind={commits_behind}"
                )

                # Track in Redis
                detector.track_stale_pr(pr_number, is_behind, commits_behind)

                # Send Discord alert if requested
                if args.discord:
                    detector.alert_discord_stale_pr(pr_number, branch, commits_behind)

        print(f"\nTotal stale PRs detected: {stale_count}")
        return 0

    elif args.cmd == "list-stale":
        # This would need to iterate through known PRs
        # For now, just print the pattern
        print("Use Redis KEYS bmad:chiseai:pr:stale:* to list stale PRs")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
