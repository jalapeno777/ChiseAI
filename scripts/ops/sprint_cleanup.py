#!/usr/bin/env python3
"""
Pre-sprint cleanup routine for ChiseAI repository.

Ensures repository hygiene before starting new sprint work.
Handles: working tree cleanliness, branch hygiene, main sync, PR status,
canonical file integrity, and automated cleanup actions.

Usage:
    python3 scripts/ops/sprint_cleanup.py --check-all
    python3 scripts/ops/sprint_cleanup.py --dry-run
    python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe

Exit codes:
    0 - Cleanup successful, repository ready for sprint
    1 - Cleanup required manual intervention
    2 - Critical issues that block sprint start
    3 - Redis/infrastructure unavailable
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

# Add src to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
import contextlib

from config.bootstrap import bootstrap

# Redis import with fallback
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Constants
DEFAULT_GITEA_BASE_URL = "http://host.docker.internal:3000"
DEFAULT_GITEA_OWNER = "craig"
DEFAULT_GITEA_REPO = "ChiseAI"
STALE_BRANCH_DAYS = 30
BEHIND_MAIN_WARNING_THRESHOLD = 7
MAIN_BRANCH_NAME = "main"

# Redis key patterns
REDIS_CLEANUP_STATE = "bmad:chiseai:sprint_cleanup:state"
REDIS_CLEANUP_LOG = "bmad:chiseai:sprint_cleanup:log"
REDIS_CLEANUP_SUMMARY = "bmad:chiseai:sprint_cleanup:summary"
REDIS_SPRINT_BOUNDARY = "bmad:chiseai:sprint:boundary"
REDIS_BRANCH_HYGIENE = "bmad:chiseai:branch_hygiene"


class CleanupError(Exception):
    """Base exception for cleanup failures."""

    pass


class CriticalCleanupError(CleanupError):
    """Critical error that blocks sprint start."""

    pass


class IssueSeverity(Enum):
    CRITICAL = "critical"  # Blocks sprint start
    WARNING = "warning"  # Requires attention
    INFO = "info"  # FYI only


@dataclass
class CleanupIssue:
    """Represents a cleanup issue."""

    severity: IssueSeverity
    category: str
    description: str
    action: str
    auto_fixable: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CleanupResult:
    """Results of cleanup check."""

    timestamp: str
    dry_run: bool
    issues: list[CleanupIssue] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    actions_blocked: list[str] = field(default_factory=list)

    def add_issue(self, issue: CleanupIssue) -> None:
        self.issues.append(issue)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @property
    def has_critical(self) -> bool:
        return self.critical_count > 0


@dataclass
class BranchInfo:
    """Information about a git branch."""

    name: str
    last_commit: str
    last_commit_date: datetime | None = None
    merged_to_main: bool = False
    commits_behind: int = 0
    commits_ahead: int = 0
    has_remote: bool = False
    is_valid_name: bool = True
    naming_issue: str | None = None
    days_inactive: int = 0


@dataclass
class WorktreeInfo:
    """Information about a git worktree."""

    path: str
    branch: str
    is_clean: bool = True
    uncommitted_changes: bool = False
    untracked_files: list[str] = field(default_factory=list)
    has_session_file: bool = False
    session_data: dict | None = None


@dataclass
class PRInfo:
    """Information about a pull request."""

    number: int
    title: str
    state: str
    head_branch: str
    base_branch: str
    is_merged: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    mergeable: bool | None = None
    mergeable_state: str | None = None


class GitHelper:
    """Helper class for git operations."""

    def __init__(self, repo_root: Path | None = None):
        self.repo_root = repo_root or self._find_repo_root()

    @staticmethod
    def _find_repo_root() -> Path:
        """Find the repository root."""
        result = subprocess.run(  # nosec B607
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())

    def run(
        self, *args: str, check: bool = True, cwd: Path | None = None
    ) -> tuple[int, str, str]:
        """Run a git command."""
        proc = subprocess.run(  # nosec B607
            ["git", *args],
            cwd=str(cwd or self.repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if check and proc.returncode != 0:
            raise CleanupError(
                f"Git command failed: git {' '.join(args)}\n{proc.stderr}"
            )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def get_current_branch(self) -> str:
        """Get current branch name."""
        _, out, _ = self.run("rev-parse", "--abbrev-ref", "HEAD")
        return out

    def get_all_branches(self, include_remote: bool = True) -> list[str]:
        """Get all local and optionally remote branches."""
        refs = ["refs/heads"]
        if include_remote:
            refs.append("refs/remotes")

        _, out, _ = self.run("for-each-ref", "--format=%(refname:short)", *refs)

        branches = []
        for line in out.split("\n"):
            line = line.strip()
            if (
                line
                and line not in {"HEAD", "origin", "gitea"}
                and not line.endswith("/HEAD")
            ):
                # Normalize remote refs
                if line.startswith("origin/") or line.startswith("gitea/"):
                    line = line.split("/", 1)[1]
                branches.append(line)

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for b in branches:
            if b not in seen and b != MAIN_BRANCH_NAME:
                seen.add(b)
                unique.append(b)
        return unique

    def get_branch_info(self, branch: str) -> BranchInfo:
        """Get detailed information about a branch."""
        info = BranchInfo(name=branch, last_commit="")

        # Last commit date
        rc, out, _ = self.run("log", "-1", "--format=%ci", branch, check=False)
        if rc == 0 and out:
            info.last_commit = out
            try:
                info.last_commit_date = datetime.fromisoformat(
                    out.replace("Z", "+00:00")
                )
                info.days_inactive = (datetime.now(UTC) - info.last_commit_date).days
            except ValueError:
                pass

        # Check if merged to main
        rc, out, _ = self.run(
            "branch", "--merged", MAIN_BRANCH_NAME, "--list", branch, check=False
        )
        info.merged_to_main = branch in out

        # Commits behind main
        rc, out, _ = self.run(
            "rev-list", "--count", f"{branch}..{MAIN_BRANCH_NAME}", check=False
        )
        if rc == 0 and out:
            with contextlib.suppress(ValueError):
                info.commits_behind = int(out)

        # Commits ahead of main
        rc, out, _ = self.run(
            "rev-list", "--count", f"{MAIN_BRANCH_NAME}..{branch}", check=False
        )
        if rc == 0 and out:
            with contextlib.suppress(ValueError):
                info.commits_ahead = int(out)

        # Check remote tracking
        rc, _, _ = self.run(
            "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}", check=False
        )
        info.has_remote = rc == 0

        # Validate naming
        info.is_valid_name, info.naming_issue = self._validate_branch_name(branch)

        return info

    @staticmethod
    def _validate_branch_name(name: str) -> tuple[bool, str | None]:
        """Validate branch naming convention.

        Branch naming is now advisory only. Always returns True.
        PR title validation provides the authoritative story-ID gate.
        """
        return True, None

    def get_worktrees(self) -> list[WorktreeInfo]:
        """Get all worktrees."""
        _, out, _ = self.run("worktree", "list", "--porcelain")

        worktrees = []
        current_worktree: dict[str, Any] = {}

        for line in out.split("\n"):
            line = line.strip()
            if line.startswith("worktree "):
                if current_worktree:
                    worktrees.append(self._parse_worktree(current_worktree))
                current_worktree = {"path": line[9:]}
            elif line.startswith("branch "):
                current_worktree["branch"] = line[7:].replace("refs/heads/", "")
            elif line == "bare":
                current_worktree["bare"] = True
            elif line.startswith("HEAD "):
                current_worktree["head"] = line[5:]

        if current_worktree:
            worktrees.append(self._parse_worktree(current_worktree))

        return [w for w in worktrees if not w.branch.startswith("(detached")]

    def _parse_worktree(self, data: dict) -> WorktreeInfo:
        """Parse worktree data."""
        path = data.get("path", "")
        branch = data.get("branch", "")

        info = WorktreeInfo(path=path, branch=branch)

        # Check for session file
        session_file = Path(path) / ".swarm-session.json"
        info.has_session_file = session_file.exists()

        if info.has_session_file:
            with contextlib.suppress(OSError, json.JSONDecodeError):
                info.session_data = json.loads(session_file.read_text())

        # Check cleanliness
        self._check_worktree_cleanliness(info)

        return info

    def _check_worktree_cleanliness(self, info: WorktreeInfo) -> None:
        """Check if worktree has uncommitted changes."""
        rc, out, _ = self.run("status", "--porcelain", cwd=Path(info.path), check=False)
        if out:
            info.is_clean = False
            for line in out.split("\n"):
                if line:
                    status = line[:2]
                    filename = line[3:]
                    if status.strip() in ["M", "A", "D", "R", "C"]:
                        info.uncommitted_changes = True
                    elif status == "??":
                        info.untracked_files.append(filename)

    def is_main_synced(self) -> tuple[bool, str]:
        """Check if local main is synced with remote."""
        # Fetch latest
        self.run("fetch", "origin", MAIN_BRANCH_NAME, check=False)

        # Compare local and remote
        rc, out, _ = self.run(
            "rev-list",
            "--left-right",
            "--count",
            f"{MAIN_BRANCH_NAME}...origin/{MAIN_BRANCH_NAME}",
            check=False,
        )

        if rc != 0:
            return False, "Could not compare local and remote main"

        parts = out.split()
        if len(parts) != 2:
            return False, f"Unexpected output: {out}"

        local_ahead, remote_ahead = int(parts[0]), int(parts[1])

        if local_ahead > 0 and remote_ahead > 0:
            return (
                False,
                f"Diverged: local ahead by {local_ahead}, remote ahead by {remote_ahead}",
            )
        elif local_ahead > 0:
            return False, f"Local ahead of remote by {local_ahead} commits"
        elif remote_ahead > 0:
            return (
                False,
                f"Remote ahead of local by {remote_ahead} commits (needs pull)",
            )

        return True, "Local main is in sync with remote"

    def delete_branch(self, branch: str, force: bool = False) -> bool:
        """Delete a branch locally and remotely."""
        try:
            # Delete local
            flag = "-D" if force else "-d"
            self.run("branch", flag, branch)

            # Delete remote if exists
            self.run("push", "origin", "--delete", branch, check=False)

            return True
        except CleanupError:
            return False

    def rebase_branch(self, branch: str, onto: str = MAIN_BRANCH_NAME) -> bool:
        """Rebase a branch onto main."""
        try:
            current = self.get_current_branch()
            self.run("checkout", branch)
            self.run("rebase", onto)
            self.run("checkout", current)
            return True
        except CleanupError:
            # Try to abort rebase if in progress
            self.run("rebase", "--abort", check=False)
            return False

    def update_main(self) -> bool:
        """Pull latest main from remote."""
        try:
            current = self.get_current_branch()
            if current != MAIN_BRANCH_NAME:
                self.run("checkout", MAIN_BRANCH_NAME)
            self.run("pull", "origin", MAIN_BRANCH_NAME)
            if current != MAIN_BRANCH_NAME:
                self.run("checkout", current)
            return True
        except CleanupError:
            return False


class GiteaHelper:
    """Helper for Gitea API operations."""

    def __init__(
        self,
        base_url: str = DEFAULT_GITEA_BASE_URL,
        owner: str = DEFAULT_GITEA_OWNER,
        repo: str = DEFAULT_GITEA_REPO,
        token: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.owner = owner
        self.repo = repo
        self.token = token or os.getenv("GITEA_TOKEN", "")

    def _api_request(
        self, method: str, endpoint: str, data: dict | None = None
    ) -> tuple[bool, Any]:
        """Make an API request to Gitea."""
        if not self.token:
            return False, "GITEA_TOKEN not set"

        url = f"{self.base_url}/api/v1/repos/{self.owner}/{self.repo}/{endpoint}"

        headers = {"Accept": "application/json", "Authorization": f"token {self.token}"}

        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, method=method, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                raw = resp.read()
                return True, json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            return False, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
        except Exception as e:
            return False, str(e)

    def get_open_prs(self) -> list[PRInfo]:
        """Get all open pull requests."""
        prs = []
        page = 1

        while page <= 10:  # Limit to 500 PRs
            success, data = self._api_request(
                "GET", f"pulls?state=open&limit=50&page={page}"
            )

            if not success:
                break

            if not isinstance(data, list):
                break

            for pr_data in data:
                pr = PRInfo(
                    number=pr_data.get("number", 0),
                    title=pr_data.get("title", ""),
                    state=pr_data.get("state", ""),
                    head_branch=pr_data.get("head", {}).get("ref", ""),
                    base_branch=pr_data.get("base", {}).get("ref", ""),
                    is_merged=pr_data.get("merged", False),
                    created_at=pr_data.get("created_at"),
                    updated_at=pr_data.get("updated_at"),
                    mergeable=pr_data.get("mergeable"),
                    mergeable_state=pr_data.get("mergeable_state"),
                )
                prs.append(pr)

            if len(data) < 50:
                break
            page += 1

        return prs

    def get_pr(self, number: int) -> PRInfo | None:
        """Get a specific pull request."""
        success, data = self._api_request("GET", f"pulls/{number}")

        if not success or not isinstance(data, dict):
            return None

        return PRInfo(
            number=data.get("number", 0),
            title=data.get("title", ""),
            state=data.get("state", ""),
            head_branch=data.get("head", {}).get("ref", ""),
            base_branch=data.get("base", {}).get("ref", ""),
            is_merged=data.get("merged", False),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            mergeable=data.get("mergeable"),
            mergeable_state=data.get("mergeable_state"),
        )


class RedisHelper:
    """Helper for Redis operations."""

    def __init__(self):
        self.client: Any | None = None
        self.host = os.getenv("CHISE_REDIS_HOST", "host.docker.internal")
        self.port = int(os.getenv("CHISE_REDIS_PORT", "6380"))
        self.db = int(os.getenv("CHISE_REDIS_DB", "0"))
        self._connect()

    def _connect(self) -> bool:
        """Connect to Redis."""
        if not REDIS_AVAILABLE:
            return False

        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            return bool(self.client.ping())
        except Exception:
            self.client = None
            return False

    def is_available(self) -> bool:
        """Check if Redis is available."""
        if self.client is None:
            return False
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def log_cleanup_action(self, action: str, details: dict) -> bool:
        """Log a cleanup action to Redis."""
        if not self.is_available():
            return False

        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": action,
            "details": json.dumps(details),
        }

        try:
            assert self.client is not None
            self.client.lpush(REDIS_CLEANUP_LOG, json.dumps(entry))
            return True
        except Exception:
            return False

    def set_cleanup_state(self, state: str, data: dict) -> bool:
        """Set current cleanup state."""
        if not self.is_available():
            return False

        try:
            assert self.client is not None
            payload = {
                "state": state,
                "timestamp": datetime.now(UTC).isoformat(),
                "data": json.dumps(data),
            }
            self.client.hset(REDIS_CLEANUP_STATE, "current", json.dumps(payload))
            return True
        except Exception:
            return False

    def save_cleanup_summary(self, result: CleanupResult) -> bool:
        """Save cleanup summary to Redis."""
        if not self.is_available():
            return False

        try:
            assert self.client is not None
            date_key = datetime.now(UTC).strftime("%Y-%m-%d")
            summary = {
                "timestamp": result.timestamp,
                "dry_run": result.dry_run,
                "critical_count": result.critical_count,
                "warning_count": result.warning_count,
                "actions_taken": len(result.actions_taken),
                "actions_blocked": len(result.actions_blocked),
            }
            self.client.hset(
                f"{REDIS_CLEANUP_SUMMARY}:{date_key}", "report", json.dumps(summary)
            )
            return True
        except Exception:
            return False

    def mark_sprint_boundary(
        self, sprint_id: str, cleanup_result: CleanupResult
    ) -> bool:
        """Mark the boundary of a new sprint."""
        if not self.is_available():
            return False

        try:
            assert self.client is not None
            boundary_data = {
                "sprint_id": sprint_id,
                "started_at": datetime.now(UTC).isoformat(),
                "cleanup_timestamp": cleanup_result.timestamp,
                "issues_critical": cleanup_result.critical_count,
                "issues_warning": cleanup_result.warning_count,
                "repository_state": (
                    "ready" if not cleanup_result.has_critical else "blocked"
                ),
            }
            self.client.lpush(REDIS_SPRINT_BOUNDARY, json.dumps(boundary_data))
            return True
        except Exception:
            return False


class SprintCleanup:
    """Main cleanup orchestrator."""

    def __init__(self, dry_run: bool = True, auto_fix_safe: bool = False):
        self.dry_run = dry_run
        self.auto_fix_safe = auto_fix_safe
        self.git = GitHelper()
        self.gitea = GiteaHelper()
        self.redis = RedisHelper()
        self.result = CleanupResult(
            timestamp=datetime.now(UTC).isoformat(), dry_run=dry_run
        )

        # Set state in Redis
        self.redis.set_cleanup_state(
            "started", {"dry_run": dry_run, "auto_fix_safe": auto_fix_safe}
        )

    def run_full_cleanup(self) -> CleanupResult:
        """Run the complete cleanup routine."""
        print("=" * 60)
        print("ChiseAI Pre-Sprint Cleanup Routine")
        print(f"Started: {self.result.timestamp}")
        print(f"Dry Run: {self.dry_run}")
        print(f"Auto-fix Safe: {self.auto_fix_safe}")
        print("=" * 60)

        try:
            # 1. Check working tree cleanliness
            self._check_worktrees()

            # 2. Check branch hygiene
            self._check_branch_hygiene()

            # 3. Check main branch synchronization
            self._check_main_sync()

            # 4. Check PR status
            self._check_pr_status()

            # 5. Check canonical files
            self._check_canonical_files()

            # 6. Execute cleanup actions
            if not self.dry_run and self.auto_fix_safe:
                self._execute_safe_fixes()

        except CriticalCleanupError as e:
            self.result.add_issue(
                CleanupIssue(
                    severity=IssueSeverity.CRITICAL,
                    category="cleanup",
                    description=f"Critical error during cleanup: {e}",
                    action="Manual intervention required",
                    auto_fixable=False,
                )
            )

        # Save results
        self.redis.save_cleanup_summary(self.result)
        self.redis.set_cleanup_state(
            "completed",
            {
                "critical_count": self.result.critical_count,
                "warning_count": self.result.warning_count,
            },
        )

        return self.result

    def _check_worktrees(self) -> None:
        """Check all worktrees for cleanliness."""
        print("\n🔍 Checking worktrees...")

        worktrees = self.git.get_worktrees()
        dirty_worktrees = []

        for wt in worktrees:
            if not wt.is_clean:
                dirty_worktrees.append(wt)

                if wt.uncommitted_changes:
                    self.result.add_issue(
                        CleanupIssue(
                            severity=IssueSeverity.CRITICAL,
                            category="worktree",
                            description=f"Worktree '{wt.path}' has uncommitted changes on branch '{wt.branch}'",
                            action="Commit changes or stash them before sprint start",
                            auto_fixable=False,
                            details={"path": wt.path, "branch": wt.branch},
                        )
                    )

                if wt.untracked_files:
                    self.result.add_issue(
                        CleanupIssue(
                            severity=IssueSeverity.WARNING,
                            category="worktree",
                            description=f"Worktree '{wt.path}' has {len(wt.untracked_files)} untracked files",
                            action="Review and either add to .gitignore or commit",
                            auto_fixable=False,
                            details={
                                "path": wt.path,
                                "untracked": wt.untracked_files[:10],
                            },
                        )
                    )

                # Check for stale sessions
                if wt.has_session_file and wt.session_data:
                    session_age = self._get_session_age(wt.session_data)
                    if session_age and session_age > timedelta(days=3):
                        self.result.add_issue(
                            CleanupIssue(
                                severity=IssueSeverity.WARNING,
                                category="session",
                                description=f"Stale session in '{wt.path}' ({session_age.days} days old)",
                                action="Close session or verify agent is still working",
                                auto_fixable=True,
                                details={"path": wt.path, "age_days": session_age.days},
                            )
                        )

        if not dirty_worktrees:
            print("  ✓ All worktrees are clean")
        else:
            print(f"  ⚠️  Found {len(dirty_worktrees)} worktrees with issues")

    def _get_session_age(self, session_data: dict) -> timedelta | None:
        """Get the age of a session."""
        created_at = session_data.get("created_at")
        if not created_at:
            return None

        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return datetime.now(UTC) - created
        except ValueError:
            return None

    def _check_branch_hygiene(self) -> None:
        """Check branch hygiene."""
        print("\n🔍 Checking branch hygiene...")

        branches = self.git.get_all_branches()
        merged_branches = []
        stale_branches = []
        behind_branches = []
        invalid_branches = []

        for branch in branches:
            info = self.git.get_branch_info(branch)

            # Already merged to main
            if info.merged_to_main:
                merged_branches.append(info)
                self.result.add_issue(
                    CleanupIssue(
                        severity=IssueSeverity.INFO,
                        category="branch",
                        description=f"Branch '{branch}' is already merged to main",
                        action="Delete branch (safe to auto-fix)",
                        auto_fixable=True,
                        details={"branch": branch, "commits_ahead": info.commits_ahead},
                    )
                )
                continue

            # Invalid naming
            if not info.is_valid_name:
                invalid_branches.append(info)
                self.result.add_issue(
                    CleanupIssue(
                        severity=IssueSeverity.WARNING,
                        category="branch",
                        description=info.naming_issue
                        or f"Invalid branch name: {branch}",
                        action="Rename branch or delete if abandoned",
                        auto_fixable=False,
                        details={"branch": branch},
                    )
                )
                continue

            # Stale branches (>30 days)
            if info.days_inactive > STALE_BRANCH_DAYS:
                stale_branches.append(info)
                self.result.add_issue(
                    CleanupIssue(
                        severity=IssueSeverity.WARNING,
                        category="branch",
                        description=f"Branch '{branch}' has no activity for {info.days_inactive} days",
                        action="Archive or delete if abandoned",
                        auto_fixable=False,
                        details={
                            "branch": branch,
                            "days_inactive": info.days_inactive,
                            "last_commit": info.last_commit,
                        },
                    )
                )

            # Behind main
            if info.commits_behind > BEHIND_MAIN_WARNING_THRESHOLD:
                behind_branches.append(info)
                self.result.add_issue(
                    CleanupIssue(
                        severity=IssueSeverity.WARNING,
                        category="branch",
                        description=f"Branch '{branch}' is {info.commits_behind} commits behind main",
                        action="Rebase onto main or merge main into branch",
                        auto_fixable=info.commits_ahead
                        == 0,  # Safe to auto-rebase if no local commits
                        details={
                            "branch": branch,
                            "commits_behind": info.commits_behind,
                            "commits_ahead": info.commits_ahead,
                        },
                    )
                )

        # Summary
        print(f"  Total branches: {len(branches)}")
        print(f"  Already merged: {len(merged_branches)}")
        print(f"  Stale (>30 days): {len(stale_branches)}")
        print(f"  Behind main: {len(behind_branches)}")
        print(f"  Invalid naming: {len(invalid_branches)}")

    def _check_main_sync(self) -> None:
        """Check if local main is synced with remote."""
        print("\n🔍 Checking main branch synchronization...")

        synced, message = self.git.is_main_synced()

        if synced:
            print(f"  ✓ {message}")
        else:
            self.result.add_issue(
                CleanupIssue(
                    severity=IssueSeverity.CRITICAL,
                    category="main",
                    description=f"Main branch out of sync: {message}",
                    action="Pull latest main from remote",
                    auto_fixable=True,
                    details={"message": message},
                )
            )
            print(f"  ❌ {message}")

    def _check_pr_status(self) -> None:
        """Check PR status for stuck/merged PRs."""
        print("\n🔍 Checking PR status...")

        prs = self.gitea.get_open_prs()

        stuck_prs = []
        for pr in prs:
            # Check for stuck PRs (no mergeable status, or blocked)
            if pr.mergeable is False:
                stuck_prs.append(pr)
                self.result.add_issue(
                    CleanupIssue(
                        severity=IssueSeverity.WARNING,
                        category="pr",
                        description=f"PR #{pr.number} '{pr.title[:50]}...' has merge conflicts",
                        action="Resolve conflicts or close PR",
                        auto_fixable=False,
                        details={
                            "pr_number": pr.number,
                            "branch": pr.head_branch,
                            "mergeable_state": pr.mergeable_state,
                        },
                    )
                )

        print(f"  Open PRs: {len(prs)}")
        print(f"  Stuck PRs: {len(stuck_prs)}")

        if not stuck_prs:
            print("  ✓ No stuck PRs")

    def _check_canonical_files(self) -> None:
        """Check canonical file integrity."""
        print("\n🔍 Checking canonical files...")

        canonical_files = [
            "docs/bmm-workflow-status.yaml",
            "docs/validation/validation-registry.yaml",
        ]

        for cf in canonical_files:
            path = self.git.repo_root / cf
            if not path.exists():
                self.result.add_issue(
                    CleanupIssue(
                        severity=IssueSeverity.CRITICAL,
                        category="canonical",
                        description=f"Canonical file missing: {cf}",
                        action="Restore file from git or backup",
                        auto_fixable=False,
                    )
                )
            else:
                # Check if file is valid YAML
                try:
                    import yaml

                    yaml.safe_load(path.read_text())
                    print(f"  ✓ {cf} is valid")
                except ImportError:
                    print(f"  ✓ {cf} exists (yaml parser not available)")
                except Exception as e:
                    self.result.add_issue(
                        CleanupIssue(
                            severity=IssueSeverity.CRITICAL,
                            category="canonical",
                            description=f"Canonical file invalid: {cf} - {e}",
                            action="Fix YAML syntax or restore from git",
                            auto_fixable=False,
                        )
                    )

    def _execute_safe_fixes(self) -> None:
        """Execute auto-fixable issues."""
        print("\n🔧 Executing safe fixes...")

        for issue in self.result.issues:
            if not issue.auto_fixable:
                continue

            if (
                issue.category == "branch"
                and "already merged" in issue.description.lower()
            ):
                branch = issue.details.get("branch")
                if branch and self.git.delete_branch(branch):
                    action = f"Deleted merged branch: {branch}"
                    self.result.actions_taken.append(action)
                    self.redis.log_cleanup_action(
                        "delete_merged_branch", {"branch": branch}
                    )
                    print(f"  ✓ {action}")
                else:
                    action = f"Failed to delete branch: {branch}"
                    self.result.actions_blocked.append(action)
                    print(f"  ❌ {action}")

            elif (
                issue.category == "main" and "out of sync" in issue.description.lower()
            ):
                if self.git.update_main():
                    action = "Updated main branch from remote"
                    self.result.actions_taken.append(action)
                    self.redis.log_cleanup_action("update_main", {})
                    print(f"  ✓ {action}")
                else:
                    action = "Failed to update main branch"
                    self.result.actions_blocked.append(action)
                    print(f"  ❌ {action}")

            elif (
                issue.category == "branch"
                and "commits behind" in issue.description.lower()
            ):
                branch = issue.details.get("branch")
                commits_ahead = issue.details.get("commits_ahead", 0)

                # Only auto-rebase if no local commits
                if branch and commits_ahead == 0:
                    if self.git.rebase_branch(branch):
                        action = f"Rebased branch onto main: {branch}"
                        self.result.actions_taken.append(action)
                        self.redis.log_cleanup_action(
                            "rebase_branch", {"branch": branch}
                        )
                        print(f"  ✓ {action}")
                    else:
                        action = f"Failed to rebase branch: {branch}"
                        self.result.actions_blocked.append(action)
                        print(f"  ❌ {action}")

    def generate_report(self) -> str:
        """Generate a formatted cleanup report."""
        lines = []
        lines.append("=" * 60)
        lines.append("PRE-SPRINT CLEANUP REPORT")
        lines.append("=" * 60)
        lines.append(f"Timestamp: {self.result.timestamp}")
        lines.append(f"Dry Run: {self.result.dry_run}")
        lines.append("")

        # Summary
        lines.append("SUMMARY")
        lines.append("-" * 40)
        lines.append(f"Critical Issues: {self.result.critical_count}")
        lines.append(f"Warnings: {self.result.warning_count}")
        lines.append(f"Actions Taken: {len(self.result.actions_taken)}")
        lines.append(f"Actions Blocked: {len(self.result.actions_blocked)}")
        lines.append("")

        # Issues by severity
        for severity in [
            IssueSeverity.CRITICAL,
            IssueSeverity.WARNING,
            IssueSeverity.INFO,
        ]:
            issues = [i for i in self.result.issues if i.severity == severity]
            if issues:
                lines.append(f"{severity.value.upper()} ISSUES ({len(issues)})")
                lines.append("-" * 40)
                for issue in issues:
                    icon = (
                        "❌"
                        if severity == IssueSeverity.CRITICAL
                        else "⚠️"
                        if severity == IssueSeverity.WARNING
                        else "ℹ️"
                    )
                    lines.append(f"{icon} [{issue.category}] {issue.description}")
                    lines.append(f"   Action: {issue.action}")
                    if issue.auto_fixable:
                        lines.append("   Auto-fixable: ✓")
                    lines.append("")

        # Actions taken
        if self.result.actions_taken:
            lines.append("ACTIONS TAKEN")
            lines.append("-" * 40)
            for action in self.result.actions_taken:
                lines.append(f"  ✓ {action}")
            lines.append("")

        # Actions blocked
        if self.result.actions_blocked:
            lines.append("ACTIONS BLOCKED")
            lines.append("-" * 40)
            for action in self.result.actions_blocked:
                lines.append(f"  ❌ {action}")
            lines.append("")

        # Sprint readiness
        lines.append("SPRINT READINESS")
        lines.append("-" * 40)
        if self.result.has_critical:
            lines.append(
                "❌ BLOCKED - Critical issues must be resolved before sprint start"
            )
        elif self.result.warning_count > 0:
            lines.append(
                "⚠️  READY WITH WARNINGS - Review warnings before starting sprint"
            )
        else:
            lines.append("✅ READY - Repository is clean and ready for sprint work")

        lines.append("=" * 60)

        return "\n".join(lines)

    def generate_discord_summary(self) -> str:
        """Generate a Discord-friendly summary."""
        emoji = (
            "🟢"
            if not self.result.has_critical and self.result.warning_count == 0
            else "🟡"
            if not self.result.has_critical
            else "🔴"
        )

        summary = f"""
{emoji} **Pre-Sprint Cleanup Report**

**Status:** {"Blocked" if self.result.has_critical else "Ready with warnings" if self.result.warning_count > 0 else "Ready"}
**Critical:** {self.result.critical_count}
**Warnings:** {self.result.warning_count}
**Actions Taken:** {len(self.result.actions_taken)}

**Summary:**
{"✅ Repository is clean and ready for sprint work" if not self.result.has_critical and self.result.warning_count == 0 else "⚠️ Review required before sprint start" if not self.result.has_critical else "❌ Critical issues must be resolved first"}
"""
        return summary


def main():
    """Main entry point."""
    # Bootstrap environment first
    bootstrap(load_env=True)

    parser = argparse.ArgumentParser(
        description="ChiseAI Pre-Sprint Cleanup Routine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - check without making changes
  python3 scripts/ops/sprint_cleanup.py --check-all

  # Execute with safe auto-fixes
  python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe

  # Mark sprint boundary after cleanup
  python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe --mark-sprint SPRINT-2026-Q1-01
        """,
    )

    parser.add_argument(
        "--check-all", action="store_true", help="Run all checks (default behavior)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes (default)",
    )
    parser.add_argument(
        "--execute", action="store_true", help="Actually perform cleanup actions"
    )
    parser.add_argument(
        "--auto-fix-safe",
        action="store_true",
        help="Automatically fix safe issues (merged branches, behind-main with no local commits)",
    )
    parser.add_argument(
        "--mark-sprint",
        metavar="SPRINT_ID",
        help="Mark sprint boundary in Redis after successful cleanup",
    )
    parser.add_argument("--json", action="store_true", help="Output report as JSON")

    args = parser.parse_args()

    # Determine mode
    dry_run = not args.execute
    auto_fix = args.auto_fix_safe

    # Run cleanup
    cleanup = SprintCleanup(dry_run=dry_run, auto_fix_safe=auto_fix)
    result = cleanup.run_full_cleanup()

    # Mark sprint boundary if requested and successful
    if args.mark_sprint and not result.has_critical:
        cleanup.redis.mark_sprint_boundary(args.mark_sprint, result)
        print(f"\n📌 Marked sprint boundary: {args.mark_sprint}")

    # Output report
    if args.json:
        # JSON output
        output = {
            "timestamp": result.timestamp,
            "dry_run": result.dry_run,
            "critical_count": result.critical_count,
            "warning_count": result.warning_count,
            "issues": [
                {
                    "severity": i.severity.value,
                    "category": i.category,
                    "description": i.description,
                    "action": i.action,
                    "auto_fixable": i.auto_fixable,
                }
                for i in result.issues
            ],
            "actions_taken": result.actions_taken,
            "actions_blocked": result.actions_blocked,
            "ready": not result.has_critical,
        }
        print(json.dumps(output, indent=2))
    else:
        # Text report
        print("\n" + cleanup.generate_report())

        # Discord summary (for copy-paste)
        print("\n" + "=" * 60)
        print("DISCORD SUMMARY")
        print("=" * 60)
        print(cleanup.generate_discord_summary())

    # Exit code
    if result.has_critical:
        return 2
    elif result.warning_count > 0:
        return 1
    else:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
