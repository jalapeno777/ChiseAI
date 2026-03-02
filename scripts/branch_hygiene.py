#!/usr/bin/env python3
"""
Branch Hygiene Automation - Prune + Prevention

Automates branch cleanup and enforces branch naming conventions.

Features:
- Auto-delete merged branches after 24 hours
- Warn on stale branches (>30 days)
- Alert on divergence from main (>50 commits)
- Enforce branch naming conventions (feature/*, bugfix/*, hotfix/*)
- Log operations to Redis
- Protect main and release/* branches from deletion

Environment Variables:
- GITEA_BASE_URL: Gitea API base URL (default: http://host.docker.internal:3000)
- GITEA_TOKEN: Gitea API token (required)
- GITEA_OWNER: Repository owner (default: craig)
- GITEA_REPO: Repository name (default: ChiseAI)
- REDIS_HOST: Redis host (default: host.docker.internal)
- REDIS_PORT: Redis port (default: 6380)
- BRANCH_HYGIENE_DRY_RUN: If set, don't actually delete branches (default: False)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.bootstrap import bootstrap


@dataclass
class BranchInfo:
    """Information about a git branch."""

    name: str
    author: str
    last_commit_date: datetime
    merged_to_main: bool = False
    merge_date: datetime | None = None
    commit_count_ahead: int = 0
    commit_count_behind: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class HygieneResult:
    """Result of a branch hygiene check."""

    branch_name: str
    action: str  # 'deleted', 'warned', 'validated', 'skipped'
    reason: str
    author: str
    timestamp: datetime
    details: dict[str, Any] = field(default_factory=dict)


class BranchHygieneError(Exception):
    """Custom exception for branch hygiene errors."""

    pass


class RedisLogger:
    """Logger for branch hygiene operations to Redis."""

    def __init__(
        self,
        host: str = "host.docker.internal",
        port: int = 6380,
        prefix: str = "bmad:chiseai:branch_hygiene",
    ):
        self.host = host
        self.port = port
        self.prefix = prefix
        self._redis_available = self._check_redis()

    def _check_redis(self) -> bool:
        """Check if Redis is available."""
        try:
            import redis

            client = redis.Redis(host=self.host, port=self.port, db=0, socket_timeout=2)
            client.ping()
            return True
        except Exception:
            return False

    def log_operation(self, result: HygieneResult) -> None:
        """Log a branch hygiene operation to Redis."""
        if not self._redis_available:
            # Fallback: print to stderr
            print(
                f"[BRANCH_HYGIENE] {result.action}: {result.branch_name} "
                f"({result.reason})",
                file=sys.stderr,
            )
            return

        try:
            import redis

            client = redis.Redis(host=self.host, port=self.port, db=0)
            timestamp = result.timestamp.isoformat()
            key = f"{self.prefix}:{result.action}:{result.branch_name}"
            value = {
                "branch": result.branch_name,
                "action": result.action,
                "reason": result.reason,
                "author": result.author,
                "timestamp": timestamp,
                "details": result.details,
            }
            client.hset(key, mapping={"data": json.dumps(value)})
            # Set expiration to 90 days
            client.expire(key, 90 * 24 * 60 * 60)
        except Exception as e:
            print(f"[BRANCH_HYGIENE] Redis log failed: {e}", file=sys.stderr)

    def log_summary(self, results: list[HygieneResult]) -> None:
        """Log a summary of all operations."""
        if not self._redis_available:
            return

        try:
            import redis

            client = redis.Redis(host=self.host, port=self.port, db=0)
            timestamp = datetime.now(UTC).isoformat()
            key = f"{self.prefix}:summary:{timestamp[:10]}"
            summary = {
                "timestamp": timestamp,
                "total_branches_checked": len(results),
                "deleted": len([r for r in results if r.action == "deleted"]),
                "warned": len([r for r in results if r.action == "warned"]),
                "validated": len([r for r in results if r.action == "validated"]),
                "skipped": len([r for r in results if r.action == "skipped"]),
            }
            client.hset(key, mapping={"data": json.dumps(summary)})
            client.expire(key, 90 * 24 * 60 * 60)
        except Exception as e:
            print(f"[BRANCH_HYGIENE] Redis summary log failed: {e}", file=sys.stderr)


class BranchHygiene:
    """Branch hygiene automation handler."""

    # Protected branch patterns
    PROTECTED_PATTERNS = [
        r"^main$",
        r"^master$",
        r"^release/.*$",
        r"^safety/.*$",
    ]

    # Valid branch naming patterns
    VALID_PREFIXES = ["feature/", "bugfix/", "hotfix/", "docs/", "chore/", "test/"]

    # Time thresholds
    MERGE_DELETE_DELAY_HOURS = 24
    STALE_BRANCH_DAYS = 30
    DIVERGENCE_THRESHOLD = 50

    def __init__(
        self,
        owner: str,
        repo: str,
        base_url: str,
        token: str,
        dry_run: bool = False,
        redis_logger: RedisLogger | None = None,
    ):
        self.owner = owner
        self.repo = repo
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.dry_run = dry_run
        self.logger = redis_logger or RedisLogger()

    def _api_request(self, method: str, endpoint: str, body: dict | None = None) -> Any:
        """Make a Gitea API request."""
        url = f"{self.base_url}/api/v1/repos/{self.owner}/{self.repo}{endpoint}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"token {self.token}",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace")
            raise BranchHygieneError(
                f"API {method} {endpoint} failed: HTTP {e.code}: {msg}"
            ) from e

    def is_protected_branch(self, branch_name: str) -> bool:
        """Check if a branch is protected from deletion."""
        for pattern in self.PROTECTED_PATTERNS:
            if re.match(pattern, branch_name):
                return True
        return False

    def validate_branch_name(self, branch_name: str) -> tuple[bool, str]:
        """
        Validate branch naming conventions.

        Returns (is_valid, reason).
        """
        # Protected branches are always valid
        if self.is_protected_branch(branch_name):
            return True, "protected branch"

        # Check for valid prefixes
        for prefix in self.VALID_PREFIXES:
            if branch_name.startswith(prefix):
                # Ensure there's something after the prefix
                suffix = branch_name[len(prefix) :]
                if suffix and len(suffix) >= 2:
                    return True, f"valid {prefix[:-1]} branch"
                return False, f"branch name too short after '{prefix}'"

        # Check for dependabot-style branches
        if branch_name.startswith("dependabot/"):
            return True, "dependabot branch"

        return False, (
            f"branch name '{branch_name}' does not follow naming convention. "
            f"Valid prefixes: {', '.join(self.VALID_PREFIXES)}"
        )

    def get_branches(self) -> list[dict]:
        """Get all branches from the repository."""
        try:
            result = self._api_request("GET", "/branches?limit=100")
            if isinstance(result, list):
                return result
            return []
        except BranchHygieneError:
            return []

    def get_branch_details(self, branch_name: str) -> dict | None:
        """Get detailed information about a specific branch."""
        try:
            result = self._api_request("GET", f"/branches/{branch_name}")
            if isinstance(result, dict):
                return result
            return None
        except BranchHygieneError:
            return None

    def get_commit_info(self, sha: str) -> dict | None:
        """Get commit information."""
        try:
            result = self._api_request("GET", f"/git/commits/{sha}")
            if isinstance(result, dict):
                return result
            return None
        except BranchHygieneError:
            return None

    def compare_branches(self, base: str, head: str) -> dict | None:
        """Compare two branches to get ahead/behind counts."""
        try:
            result = self._api_request("GET", f"/compare/{base}...{head}")
            if isinstance(result, dict):
                return result
            return None
        except BranchHygieneError:
            return None

    def delete_branch(self, branch_name: str) -> bool:
        """Delete a branch via API."""
        if self.dry_run:
            print(f"[DRY RUN] Would delete branch: {branch_name}")
            return True

        try:
            self._api_request("DELETE", f"/git/refs/heads/{branch_name}")
            return True
        except BranchHygieneError as e:
            print(f"Failed to delete branch {branch_name}: {e}", file=sys.stderr)
            return False

    def get_pr_for_branch(self, branch_name: str) -> dict | None:
        """Find merged PR for a branch."""
        try:
            prs = self._api_request(
                "GET", f"/pulls?state=closed&head={self.owner}:{branch_name}"
            )
            if isinstance(prs, list):
                for pr in prs:
                    if (
                        isinstance(pr, dict)
                        and pr.get("head", {}).get("ref") == branch_name
                        and pr.get("merged", False)
                    ):
                        return pr
            return None
        except BranchHygieneError:
            return None

    def cleanup_merged_branches(self) -> list[HygieneResult]:
        """
        Delete branches that have been merged for more than 24 hours.

        AC1: Merged branches are auto-deleted after 24 hours of merge completion
        """
        results: list[HygieneResult] = []
        branches = self.get_branches()
        now = datetime.now(UTC)

        for branch in branches:
            branch_name = branch.get("name", "")

            # Skip protected branches
            if self.is_protected_branch(branch_name):
                results.append(
                    HygieneResult(
                        branch_name=branch_name,
                        action="skipped",
                        reason="protected branch",
                        author=branch.get("commit", {})
                        .get("author", {})
                        .get("name", "unknown"),
                        timestamp=now,
                    )
                )
                continue

            # Check if there's a merged PR for this branch
            pr = self.get_pr_for_branch(branch_name)
            if pr and pr.get("merged"):
                merged_at_str = pr.get("merged_at")
                if merged_at_str:
                    merged_at = datetime.fromisoformat(
                        merged_at_str.replace("Z", "+00:00")
                    )
                    hours_since_merge = (now - merged_at).total_seconds() / 3600

                    if hours_since_merge >= self.MERGE_DELETE_DELAY_HOURS:
                        success = self.delete_branch(branch_name)
                        results.append(
                            HygieneResult(
                                branch_name=branch_name,
                                action="deleted" if success else "skipped",
                                reason=f"merged {hours_since_merge:.1f} hours ago",
                                author=pr.get("user", {}).get("login", "unknown"),
                                timestamp=now,
                                details={
                                    "merged_at": merged_at_str,
                                    "pr_number": pr.get("number"),
                                },
                            )
                        )
                        self.logger.log_operation(results[-1])

        return results

    def check_stale_branches(self) -> list[HygieneResult]:
        """
        Check for branches older than 30 days and generate warnings.

        AC2: Branches older than 30 days trigger warning notifications
        """
        results: list[HygieneResult] = []
        branches = self.get_branches()
        now = datetime.now(UTC)

        for branch in branches:
            branch_name = branch.get("name", "")

            # Skip protected branches
            if self.is_protected_branch(branch_name):
                continue

            # Get commit date
            commit = branch.get("commit", {})
            commit_date_str = commit.get("timestamp") or commit.get("created")

            if commit_date_str:
                commit_date = datetime.fromisoformat(
                    commit_date_str.replace("Z", "+00:00")
                )
                days_since_commit = (now - commit_date).days

                if days_since_commit >= self.STALE_BRANCH_DAYS:
                    results.append(
                        HygieneResult(
                            branch_name=branch_name,
                            action="warned",
                            reason=(
                                f"stale branch - {days_since_commit} days "
                                "since last commit"
                            ),
                            author=commit.get("author", {}).get("name", "unknown"),
                            timestamp=now,
                            details={
                                "days_stale": days_since_commit,
                                "last_commit": commit_date_str,
                            },
                        )
                    )
                    self.logger.log_operation(results[-1])

        return results

    def check_divergence(self) -> list[HygieneResult]:
        """
        Check for branches that have diverged significantly from main.

        AC3: Divergence detection alerts on >50 commits drift from main
        """
        results: list[HygieneResult] = []
        branches = self.get_branches()
        now = datetime.now(UTC)

        for branch in branches:
            branch_name = branch.get("name", "")

            # Skip main/master branches
            if branch_name in ("main", "master"):
                continue

            # Compare with main
            comparison = self.compare_branches("main", branch_name)
            if comparison:
                ahead_by = comparison.get("ahead_by", 0)
                behind_by = comparison.get("behind_by", 0)

                if (
                    ahead_by > self.DIVERGENCE_THRESHOLD
                    or behind_by > self.DIVERGENCE_THRESHOLD
                ):
                    results.append(
                        HygieneResult(
                            branch_name=branch_name,
                            action="warned",
                            reason=(
                                f"significant divergence from main "
                                f"(+{ahead_by}/-{behind_by} commits)"
                            ),
                            author=branch.get("commit", {})
                            .get("author", {})
                            .get("name", "unknown"),
                            timestamp=now,
                            details={
                                "commits_ahead": ahead_by,
                                "commits_behind": behind_by,
                                "threshold": self.DIVERGENCE_THRESHOLD,
                            },
                        )
                    )
                    self.logger.log_operation(results[-1])

        return results

    def validate_all_branch_names(self) -> list[HygieneResult]:
        """
        Validate all branch names against naming conventions.

        AC4: Branch naming conventions are enforced (feature/*, bugfix/*, hotfix/*)
        """
        results: list[HygieneResult] = []
        branches = self.get_branches()
        now = datetime.now(UTC)

        for branch in branches:
            branch_name = branch.get("name", "")
            is_valid, reason = self.validate_branch_name(branch_name)

            results.append(
                HygieneResult(
                    branch_name=branch_name,
                    action="validated" if is_valid else "warned",
                    reason=reason,
                    author=branch.get("commit", {})
                    .get("author", {})
                    .get("name", "unknown"),
                    timestamp=now,
                    details={"valid": is_valid},
                )
            )
            if not is_valid:
                self.logger.log_operation(results[-1])

        return results

    def run_all_checks(self) -> list[HygieneResult]:
        """Run all branch hygiene checks."""
        all_results: list[HygieneResult] = []

        print("Running branch hygiene checks...")

        # AC1: Cleanup merged branches
        print("\n1. Checking for merged branches to delete...")
        results = self.cleanup_merged_branches()
        all_results.extend(results)
        deleted = len([r for r in results if r.action == "deleted"])
        print(f"   Deleted {deleted} merged branches")

        # AC2: Check for stale branches
        print("\n2. Checking for stale branches...")
        results = self.check_stale_branches()
        all_results.extend(results)
        stale = len([r for r in results if r.action == "warned"])
        print(f"   Found {stale} stale branches")

        # AC3: Check for divergence
        print("\n3. Checking for branch divergence...")
        results = self.check_divergence()
        all_results.extend(results)
        diverged = len([r for r in results if r.action == "warned"])
        print(f"   Found {diverged} diverged branches")

        # AC4: Validate branch names
        print("\n4. Validating branch names...")
        results = self.validate_all_branch_names()
        all_results.extend(results)
        invalid = len([r for r in results if r.action == "warned"])
        print(f"   Found {invalid} branches with naming issues")

        # Log summary
        self.logger.log_summary(all_results)

        print(f"\nBranch hygiene complete. Total branches checked: {len(all_results)}")
        return all_results


def main() -> int:
    """Main entry point."""
    # Bootstrap environment first
    bootstrap(load_env=True)

    p = argparse.ArgumentParser(description="Branch Hygiene Automation")
    p.add_argument(
        "--base-url",
        default=os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000"),
        help="Gitea API base URL",
    )
    p.add_argument(
        "--owner", default=os.getenv("GITEA_OWNER", "craig"), help="Repository owner"
    )
    p.add_argument(
        "--repo", default=os.getenv("GITEA_REPO", "ChiseAI"), help="Repository name"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    p.add_argument(
        "--check",
        choices=["all", "merged", "stale", "divergence", "names"],
        default="all",
        help="Which check to run",
    )
    p.add_argument(
        "--redis-host",
        default=os.getenv("REDIS_HOST", "host.docker.internal"),
        help="Redis host",
    )
    p.add_argument(
        "--redis-port",
        type=int,
        default=int(os.getenv("REDIS_PORT", "6380")),
        help="Redis port",
    )
    args = p.parse_args()

    token = os.getenv("GITEA_TOKEN")
    if not token:
        print("ERROR: GITEA_TOKEN env var is required", file=sys.stderr)
        return 1

    # Initialize logger
    logger = RedisLogger(host=args.redis_host, port=args.redis_port)

    # Initialize hygiene handler
    hygiene = BranchHygiene(
        owner=args.owner,
        repo=args.repo,
        base_url=args.base_url,
        token=token,
        dry_run=args.dry_run,
        redis_logger=logger,
    )

    # Run requested check
    if args.check == "all":
        results = hygiene.run_all_checks()
    elif args.check == "merged":
        results = hygiene.cleanup_merged_branches()
    elif args.check == "stale":
        results = hygiene.check_stale_branches()
    elif args.check == "divergence":
        results = hygiene.check_divergence()
    elif args.check == "names":
        results = hygiene.validate_all_branch_names()
    else:
        results = []

    # Print results
    warnings = [r for r in results if r.action == "warned"]
    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  - {w.branch_name}: {w.reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
