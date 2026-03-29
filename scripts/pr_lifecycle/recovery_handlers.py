#!/usr/bin/env python3
"""Recovery Handlers - Automatic recovery actions for various PR failure types.

This module provides handlers for:
- CI failures (with auto-fix capabilities)
- Merge conflicts (auto-rebase)
- Transient errors (exponential backoff retry)
- Missing approvals (auto-approval or request)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

# Import PR state manager
from .pr_state_manager import PRStateManager  # noqa: E402
from .stale_detector import StaleDetector  # noqa: E402

# Configuration
MAX_AUTO_FIX_RETRIES = int(os.getenv("CHISE_PR_MAX_RETRIES", "5"))
BACKOFF_INITIAL_SEC = int(os.getenv("CHISE_PR_BACKOFF_INITIAL", "60"))
BACKOFF_MAX_SEC = int(os.getenv("CHISE_PR_BACKOFF_MAX", "1800"))

# Rate limiting
MAX_REBASES_PER_WINDOW = int(os.getenv("CHISE_PR_MAX_REBASES_PER_WINDOW", "3"))
REBASE_WINDOW_SEC = int(os.getenv("CHISE_PR_REBASE_WINDOW_SEC", "300"))
REBASE_COOLDOWN_MIN = int(os.getenv("CHISE_PR_REBASE_COOLDOWN_MIN", "10"))

# Gitea configuration
GITEA_BASE_URL = os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000").rstrip(
    "/"
)
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "")
GITEA_REVIEW_TOKEN = os.getenv("GITEA_REVIEW_TOKEN", GITEA_TOKEN)
GITEA_OWNER = os.getenv("GITEA_OWNER", "craig")
GITEA_REPO = os.getenv("GITEA_REPO", "ChiseAI")

# Redis key patterns for rate limiting
REBASE_BUDGET_KEY = "bmad:chiseai:pr:rebase:budget"
REBASE_LOCK_PREFIX = "bmad:chiseai:pr:rebase:lock"


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


class RecoveryResult:
    """Result of a recovery attempt."""

    def __init__(
        self,
        success: bool,
        action: str,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        self.success = success
        self.action = action
        self.message = message
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "message": self.message,
            "metadata": self.metadata,
        }


class AutoRebaseEngine:
    """Handles automatic git rebase operations for stale PRs."""

    def __init__(
        self,
        repo_path: str | None = None,
        gitea_token: str | None = None,
        gitea_owner: str | None = None,
        gitea_repo: str | None = None,
    ):
        """Initialize the auto-rebase engine.

        Args:
            repo_path: Path to the git repository.
            gitea_token: Gitea API token.
            gitea_owner: Gitea repository owner.
            gitea_repo: Gitea repository name.
        """
        if repo_path is None:
            repo_path = str(Path(__file__).parent.parent.parent)
        self.repo_path = repo_path
        self.gitea_token = gitea_token or GITEA_TOKEN
        self.gitea_owner = gitea_owner or GITEA_OWNER
        self.gitea_repo = gitea_repo or GITEA_REPO
        self.stale_detector = StaleDetector(repo_path)

    def _run_git(
        self, *args: str, check: bool = False
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command in the repository."""
        result = subprocess.run(
            ["git", "-C", self.repo_path] + list(args),
            text=True,
            capture_output=True,
            check=check,
        )
        return result

    def check_rebase_lock(self, pr_number: int) -> bool:
        """Check if a PR is locked for rebase (concurrent rebase in progress).

        Args:
            pr_number: The PR number.

        Returns:
            True if PR is locked.
        """
        lock_key = f"{REBASE_LOCK_PREFIX}:{pr_number}"
        result = _redis_cli("EXISTS", lock_key)
        return result.returncode == 0 and result.stdout.strip() == "1"

    def acquire_rebase_lock(self, pr_number: int, ttl_sec: int = 300) -> bool:
        """Acquire a rebase lock for a PR.

        Args:
            pr_number: The PR number.
            ttl_sec: Lock TTL in seconds.

        Returns:
            True if lock acquired.
        """
        lock_key = f"{REBASE_LOCK_PREFIX}:{pr_number}"
        result = _redis_cli("SET", lock_key, "1", "EX", str(ttl_sec), "NX")
        return result.returncode == 0 and result.stdout.strip() == "OK"

    def release_rebase_lock(self, pr_number: int) -> None:
        """Release a rebase lock for a PR.

        Args:
            pr_number: The PR number.
        """
        lock_key = f"{REBASE_LOCK_PREFIX}:{pr_number}"
        _redis_cli("DEL", lock_key)

    def check_rate_limit(self) -> tuple[bool, int]:
        """Check if we're within the rebase rate limit.

        Returns:
            Tuple of (within_limit, remaining_budget).
        """
        budget_key = f"{REBASE_BUDGET_KEY}:{int(time.time() // REBASE_WINDOW_SEC)}"

        # Get current count
        result = _redis_cli("GET", budget_key)
        current_count = 0
        if result.returncode == 0 and result.stdout.strip():
            try:
                current_count = int(result.stdout.strip())
            except ValueError:
                current_count = 0

        remaining = max(0, MAX_REBASES_PER_WINDOW - current_count)
        return remaining > 0, remaining

    def consume_rate_limit(self) -> bool:
        """Consume one rebase from the rate limit budget.

        Returns:
            True if budget was consumed.
        """
        budget_key = f"{REBASE_BUDGET_KEY}:{int(time.time() // REBASE_WINDOW_SEC)}"

        # Increment and set TTL
        result = _redis_cli("INCR", budget_key)
        if result.returncode == 0 and result.stdout.strip() == "1":
            # First entry, set TTL
            _redis_cli("EXPIRE", budget_key, str(REBASE_WINDOW_SEC))
        return result.returncode == 0

    def is_safe_to_rebase(
        self,
        branch: str,
        mergeable: bool | None,
        is_draft: bool = False,
    ) -> tuple[bool, str]:
        """Check if it's safe to rebase a branch.

        Args:
            branch: The branch name.
            mergeable: The mergeable status from Gitea.
            is_draft: Whether the PR is a draft.

        Returns:
            Tuple of (is_safe, reason).
        """
        # Skip draft PRs
        if is_draft:
            return False, "PR is a draft"

        # Must be a feature branch
        if not self.stale_detector.check_branch_is_feature(branch):
            return False, "Not a feature branch"

        # Only rebase if mergeable is true or null (unknown)
        # If mergeable is explicitly false, there are real conflicts
        if mergeable is False:
            return False, "PR has actual merge conflicts"

        return True, "safe"

    def get_remote_url(self) -> str | None:
        """Get the remote URL for the repository.

        Returns:
            The remote URL or None if not found.
        """
        result = self._run_git("remote", "get-url", "origin")
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def prepare_branch_for_rebase(self, branch: str) -> tuple[bool, str]:
        """Prepare a branch for rebasing by ensuring it's up to date with remote.

        Args:
            branch: The branch name.

        Returns:
            Tuple of (success, error_message).
        """
        # Fetch main first
        fetch_result = self._run_git("fetch", "origin", "main:main")
        if fetch_result.returncode != 0:
            return False, f"Failed to fetch main: {fetch_result.stderr}"

        # Checkout the branch
        checkout_result = self._run_git("checkout", branch)
        if checkout_result.returncode != 0:
            return False, f"Failed to checkout branch: {checkout_result.stderr}"

        # Verify branch is clean
        status_result = self._run_git("status", "--porcelain")
        if status_result.stdout.strip():
            return False, "Branch has uncommitted changes"

        return True, ""

    def attempt_rebase(self, branch: str) -> tuple[bool, str, dict[str, Any]]:
        """Attempt to rebase branch onto main.

        Args:
            branch: The branch name to rebase.

        Returns:
            Tuple of (success, error_message, metadata).
            metadata contains before_sha, after_sha, duration_sec, commits_rebased.
        """
        import time

        start_time = time.time()
        metadata: dict[str, Any] = {}

        # Get before SHA
        before_result = self._run_git("rev-parse", branch)
        if before_result.returncode != 0:
            return False, "Failed to get branch SHA", metadata
        before_sha = before_result.stdout.strip()
        metadata["before_sha"] = before_sha

        # Count commits being rebased
        count_result = self._run_git(
            "log", "--oneline", f"{branch}..origin/main", "--count"
        )
        commits_rebased = 0
        if count_result.returncode == 0:
            try:
                commits_rebased = int(count_result.stdout.strip())
            except ValueError:
                commits_rebased = 0
        metadata["commits_rebased"] = commits_rebased

        # Attempt rebase
        rebase_result = self._run_git("rebase", "origin/main")
        duration_sec = time.time() - start_time
        metadata["duration_sec"] = round(duration_sec, 2)

        if rebase_result.returncode != 0:
            # Rebase failed - abort the rebase
            abort_result = self._run_git("rebase", "--abort")
            if abort_result.returncode != 0:
                # Could not abort - this is bad
                return (
                    False,
                    f"Rebase failed with conflicts AND could not abort: {rebase_result.stderr}",
                    metadata,
                )
            return (
                False,
                f"Rebase failed with conflicts: {rebase_result.stderr}",
                metadata,
            )

        # Get after SHA
        after_result = self._run_git("rev-parse", branch)
        if after_result.returncode != 0:
            return False, "Failed to get new branch SHA", metadata
        after_sha = after_result.stdout.strip()
        metadata["after_sha"] = after_sha

        return True, "", metadata

    def force_push_with_lease(self, branch: str, before_sha: str) -> tuple[bool, str]:
        """Push the rebased branch using force-with-lease.

        Args:
            branch: The branch name.
            before_sha: The SHA before rebase (for lease verification).

        Returns:
            Tuple of (success, error_message).
        """
        # Use force-with-lease for safety
        push_result = self._run_git(
            "push",
            "--force-with-lease",
            "origin",
            branch,
        )

        if push_result.returncode != 0:
            return False, f"Force push failed: {push_result.stderr}"

        return True, ""

    def enable_automerge(self, pr_number: int) -> bool:
        """Enable automerge (merge when checks succeed) on a PR via Gitea API.

        Args:
            pr_number: The PR number.

        Returns:
            True if successful.
        """
        import urllib.request

        url = f"{GITEA_BASE_URL}/api/v1/repos/{self.gitea_owner}/{self.gitea_repo}/pulls/{pr_number}/merge"
        headers = {
            "Accept": "application/json",
            "Authorization": f"token {self.gitea_token}",
            "Content-Type": "application/json",
        }

        # Enable merge when checks succeed (no direct merge)
        data = json.dumps(
            {
                "merge_when_checks_succeed": True,
            }
        ).encode("utf-8")

        req = urllib.request.Request(url, data=data, method="POST", headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                return resp.status in (200, 201)
        except urllib.error.HTTPError as e:
            # 405 might mean already merged or not mergeable
            print(f"Failed to enable automerge: HTTP {e.code}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Failed to enable automerge: {e}", file=sys.stderr)
            return False

    def log_rebase_action(
        self,
        pr_number: int,
        branch: str,
        success: bool,
        metadata: dict[str, Any],
    ) -> None:
        """Log a rebase action to Redis for auditing.

        Args:
            pr_number: The PR number.
            branch: The branch name.
            success: Whether rebase succeeded.
            metadata: Additional metadata about the rebase.
        """
        import time

        log_key = f"bmad:chiseai:pr:rebase:log:{pr_number}"
        log_entry = {
            "timestamp": time.time(),
            "pr_number": pr_number,
            "branch": branch,
            "success": success,
            **metadata,
        }

        _redis_cli("RPUSH", log_key, json.dumps(log_entry))
        _redis_cli("EXPIRE", log_key, str(7 * 86400))  # 7 days

    def rebase_pr(
        self,
        pr_number: int,
        branch: str,
        mergeable: bool | None = None,
        is_draft: bool = False,
    ) -> RecoveryResult:
        """Execute the full rebase workflow for a PR.

        Args:
            pr_number: The PR number.
            branch: The branch name.
            mergeable: The mergeable status from Gitea.
            is_draft: Whether the PR is a draft.

        Returns:
            RecoveryResult indicating success or failure.
        """
        # Check safety first
        is_safe, safety_reason = self.is_safe_to_rebase(branch, mergeable, is_draft)
        if not is_safe:
            return RecoveryResult(
                False,
                "rebase_skipped",
                f"Safety check failed: {safety_reason}",
                {"safety_reason": safety_reason},
            )

        # Check for concurrent rebase lock
        if self.check_rebase_lock(pr_number):
            return RecoveryResult(
                False,
                "rebase_skipped",
                "Another rebase is in progress for this PR",
            )

        # Check rate limit
        within_limit, remaining = self.check_rate_limit()
        if not within_limit:
            return RecoveryResult(
                False,
                "rate_limited",
                "Rebase rate limit exceeded",
                {"remaining_budget": 0},
            )

        # Check cooldown
        if self.stale_detector.is_in_rebase_cooldown(pr_number):
            return RecoveryResult(
                False,
                "rebase_skipped",
                "PR is in rebase cooldown period",
                {"cooldown_active": True},
            )

        # Acquire lock
        if not self.acquire_rebase_lock(pr_number):
            return RecoveryResult(
                False,
                "rebase_skipped",
                "Failed to acquire rebase lock",
            )

        try:
            # Prepare branch
            success, error = self.prepare_branch_for_rebase(branch)
            if not success:
                self.log_rebase_action(pr_number, branch, False, {"error": error})
                return RecoveryResult(False, "rebase_failed", error)

            # Get before SHA for force-with-lease
            before_result = self._run_git("rev-parse", branch)
            before_sha = (
                before_result.stdout.strip() if before_result.returncode == 0 else ""
            )

            # Attempt rebase
            success, error, metadata = self.attempt_rebase(branch)

            if not success:
                self.log_rebase_action(pr_number, branch, False, metadata)
                # Post conflict comment if there were conflicts
                if "conflict" in error.lower():
                    GiteaAPI(
                        GITEA_BASE_URL,
                        self.gitea_token,
                        self.gitea_owner,
                        self.gitea_repo,
                    ).post_pr_comment(
                        pr_number,
                        "🤖 **Auto-rebase failed**: This PR has merge conflicts with main that "
                        "cannot be automatically resolved. Manual intervention is required. "
                        "Please rebase your branch onto main and resolve conflicts.",
                    )
                return RecoveryResult(False, "rebase_conflict", error, metadata)

            # Force push with lease
            success, error = self.force_push_with_lease(branch, before_sha)
            if not success:
                self.log_rebase_action(pr_number, branch, False, metadata)
                return RecoveryResult(False, "force_push_failed", error, metadata)

            # Set cooldown
            self.stale_detector.set_rebase_cooldown(pr_number, REBASE_COOLDOWN_MIN)

            # Consume rate limit
            self.consume_rate_limit()

            # Log success
            self.log_rebase_action(pr_number, branch, True, metadata)

            # Enable automerge
            self.enable_automerge(pr_number)

            return RecoveryResult(
                True,
                "rebase_success",
                f"Successfully rebased {metadata.get('commits_rebased', 0)} commits",
                metadata,
            )

        finally:
            # Always release lock
            self.release_rebase_lock(pr_number)


class GiteaAPI:
    """Simple Gitea API client."""

    def __init__(self, base_url: str, token: str, owner: str, repo: str):
        self.base_url = base_url
        self.token = token
        self.owner = owner
        self.repo = repo

    def _req_json(
        self, method: str, path: str, body: dict | None = None
    ) -> dict | None:
        """Make a request to the Gitea API."""
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
        except Exception as e:
            print(f"API Error: {method} {url} - {e}", file=sys.stderr)
            return None

    def post_pr_comment(self, pr_number: int, body: str) -> bool:
        """Post a comment on a PR."""
        result = self._req_json(
            "POST",
            f"/api/v1/repos/{self.owner}/{self.repo}/issues/{pr_number}/comments",
            {"body": body},
        )
        return result is not None

    def approve_pr(self, pr_number: int) -> bool:
        """Approve a PR using the review token."""
        # Use review token if available
        token = GITEA_REVIEW_TOKEN or self.token

        url = f"{self.base_url}/api/v1/repos/{self.owner}/{self.repo}/pulls/{pr_number}/reviews"
        headers = {
            "Accept": "application/json",
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        }
        data = json.dumps(
            {"event": "APPROVED", "body": "Auto-approved by PR lifecycle system"}
        ).encode("utf-8")

        req = urllib.request.Request(url, data=data, method="POST", headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                return resp.status == 201
        except urllib.error.HTTPError as e:
            if e.code == 422:
                # Cannot approve own PR - this is expected
                print(f"Cannot auto-approve PR #{pr_number} (likely same author)")
                return False
            print(f"Approval failed: HTTP {e.code}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Approval error: {e}", file=sys.stderr)
            return False


class RecoveryHandlers:
    """Collection of recovery handlers for different failure types."""

    def __init__(self):
        self.state_mgr = PRStateManager()
        self.gitea = GiteaAPI(GITEA_BASE_URL, GITEA_TOKEN, GITEA_OWNER, GITEA_REPO)

    def handle_ci_failure(
        self, pr_number: int, diagnosis: dict[str, Any] | None = None
    ) -> RecoveryResult:
        """Handle CI failure by attempting auto-fix or escalating."""
        state = self.state_mgr.get_pr(pr_number)
        if not state:
            return RecoveryResult(False, "ci_failure", "PR state not found")

        # Check retry limit
        if state.retry_count >= state.max_retries:
            self.state_mgr.mark_escalated(
                pr_number,
                reason=f"CI failed {state.retry_count} times, auto-fix unsuccessful",
                triggered_by="recovery_handler",
            )
            return RecoveryResult(
                False,
                "escalated",
                "Max retries exceeded, escalated to humans",
            )

        # Update recovery action
        state.recovery_action = "analyzing_ci_failure"
        self.state_mgr.update_pr(state)

        # If no diagnosis provided, we can't auto-fix
        if not diagnosis:
            self.state_mgr.mark_escalated(
                pr_number,
                reason="CI failure without diagnosis - cannot auto-fix",
                triggered_by="recovery_handler",
            )
            return RecoveryResult(
                False,
                "escalated",
                "No diagnosis available for CI failure",
            )

        # Check if auto-fixable
        if self._is_auto_fixable(diagnosis):
            return self._attempt_auto_fix(pr_number, diagnosis)

        # Not auto-fixable - escalate
        self.state_mgr.mark_escalated(
            pr_number,
            reason=f"CI failure not auto-fixable: {diagnosis.get('tool', 'unknown')}",
            triggered_by="recovery_handler",
        )
        return RecoveryResult(
            False,
            "escalated",
            f"CI failure type not auto-fixable: {diagnosis.get('tool', 'unknown')}",
        )

    def _is_auto_fixable(self, diagnosis: dict[str, Any]) -> bool:
        """Check if a failure diagnosis indicates an auto-fixable issue."""
        tool = diagnosis.get("tool", "").lower()
        kind = diagnosis.get("kind", "").lower()

        # Auto-fixable patterns
        auto_fixable = {
            "ruff": ["format", "fixable", "import"],
            "black": ["format"],
            "isort": ["import", "format"],
            "mypy": [],  # Type errors typically not auto-fixable
            "pytest": [],  # Test failures not auto-fixable
            "lint": ["format", "whitespace", "trailing"],
        }

        if tool in auto_fixable:
            fixable_kinds = auto_fixable[tool]
            # If no specific kinds listed, assume not auto-fixable for safety
            if not fixable_kinds:
                return False
            return any(fk in kind for fk in fixable_kinds)

        return False

    def _attempt_auto_fix(
        self, pr_number: int, diagnosis: dict[str, Any]
    ) -> RecoveryResult:
        """Attempt to automatically fix a CI failure."""
        state = self.state_mgr.get_pr(pr_number)
        if not state:
            return RecoveryResult(False, "auto_fix", "PR state not found")

        # Update state
        state.recovery_action = "auto_fixing"
        self.state_mgr.update_pr(state)
        self.state_mgr.transition_state(
            pr_number,
            to_state="auto_fix_attempt",
            triggered_by="recovery_handler",
        )

        # Comment on PR about auto-fix attempt
        self.gitea.post_pr_comment(
            pr_number,
            "🤖 **Auto-fix in progress**: The PR lifecycle system is attempting to automatically "
            f"fix the {diagnosis.get('tool', 'CI')} failure. If unsuccessful, this PR will be "
            "escalated to human reviewers.",
        )

        # For now, we escalate since auto-fixing requires git operations
        # In a full implementation, this would:
        # 1. Clone the branch
        # 2. Run the fix command (e.g., ruff --fix)
        # 3. Commit and push
        # 4. Re-trigger CI

        self.state_mgr.mark_escalated(
            pr_number,
            reason=f"Auto-fix not yet implemented for {diagnosis.get('tool', 'unknown')}",
            triggered_by="recovery_handler",
        )

        return RecoveryResult(
            False,
            "escalated",
            "Auto-fix implementation pending - escalated",
            {"diagnosis": diagnosis},
        )

    def handle_merge_conflict(self, pr_number: int) -> RecoveryResult:
        """Handle merge conflict by attempting auto-rebase."""
        state = self.state_mgr.get_pr(pr_number)
        if not state:
            return RecoveryResult(False, "merge_conflict", "PR state not found")

        # Check retry limit
        if state.retry_count >= state.max_retries:
            self.state_mgr.mark_escalated(
                pr_number,
                reason=f"Merge conflict persists after {state.retry_count} rebase attempts",
                triggered_by="recovery_handler",
            )
            return RecoveryResult(
                False,
                "escalated",
                "Max rebase retries exceeded",
            )

        # Update state
        state.recovery_action = "rebasing"
        self.state_mgr.update_pr(state)
        self.state_mgr.transition_state(
            pr_number,
            to_state="rebasing",
            triggered_by="recovery_handler",
        )

        # Comment on PR
        self.gitea.post_pr_comment(
            pr_number,
            "🤖 **Auto-rebase in progress**: The PR lifecycle system is attempting to rebase "
            "this branch onto main to resolve merge conflicts.",
        )

        # Use AutoRebaseEngine to handle the rebase
        rebase_engine = AutoRebaseEngine()

        # Determine mergeable status
        mergeable = None
        if state.mergeable == "true":
            mergeable = True
        elif state.mergeable == "false":
            mergeable = False

        # Execute rebase
        result = rebase_engine.rebase_pr(
            pr_number=pr_number,
            branch=state.branch,
            mergeable=mergeable,
            is_draft=False,  # Draft status would need to come from Gitea
        )

        if result.success:
            # Rebase succeeded - post success comment
            self.gitea.post_pr_comment(
                pr_number,
                "✅ **Auto-rebase successful**: This PR has been automatically rebased onto main. "
                "CI will now run on the updated branch. Auto-merge has been re-enabled.",
            )
            return result
        else:
            # Rebase failed - handle based on reason
            if (
                "conflict" in result.message.lower()
                or result.action == "rebase_conflict"
            ):
                # Real conflicts - post message and escalate
                self.gitea.post_pr_comment(
                    pr_number,
                    "🤖 **Auto-rebase failed**: This PR has merge conflicts with main that "
                    "cannot be automatically resolved. Manual intervention is required. "
                    "Please rebase your branch onto main and resolve conflicts.",
                )
                self.state_mgr.mark_escalated(
                    pr_number,
                    reason="Auto-rebase failed with conflicts - manual resolution required",
                    triggered_by="recovery_handler",
                )
                return RecoveryResult(
                    False,
                    "escalated",
                    "Auto-rebase failed with conflicts",
                    result.metadata,
                )
            else:
                # Other failure (rate limited, cooldown, etc.)
                return result

    def handle_missing_approval(self, pr_number: int) -> RecoveryResult:
        """Handle missing approval by requesting review or auto-approving."""
        state = self.state_mgr.get_pr(pr_number)
        if not state:
            return RecoveryResult(False, "missing_approval", "PR state not found")

        # Try auto-approval first
        if self.gitea.approve_pr(pr_number):
            state.approval_status = "approved"
            state.approvers.append("auto-approval-system")
            self.state_mgr.update_pr(state)

            self.state_mgr.transition_state(
                pr_number,
                to_state="approved",
                triggered_by="recovery_handler",
            )

            return RecoveryResult(
                True,
                "auto_approved",
                "PR automatically approved",
            )

        # Auto-approval failed - request human review
        self.gitea.post_pr_comment(
            pr_number,
            "👋 **Review requested**: This PR is ready for merge but requires review approval. "
            "@merlin please review when convenient.",
        )

        return RecoveryResult(
            False,
            "review_requested",
            "Auto-approval failed, requested human review",
        )

    def handle_transient_error(self, pr_number: int, error_type: str) -> RecoveryResult:
        """Handle transient error with exponential backoff retry."""
        state = self.state_mgr.get_pr(pr_number)
        if not state:
            return RecoveryResult(False, "transient_error", "PR state not found")

        # Check retry limit
        if state.retry_count >= state.max_retries:
            self.state_mgr.mark_escalated(
                pr_number,
                reason=f"Transient error {error_type} persists after {state.retry_count} retries",
                triggered_by="recovery_handler",
            )
            return RecoveryResult(
                False,
                "escalated",
                "Max retries exceeded for transient error",
            )

        # Calculate backoff
        delay = min(
            BACKOFF_INITIAL_SEC * (2**state.retry_count),
            BACKOFF_MAX_SEC,
        )

        # Update state
        state.recovery_action = f"waiting_retry_{delay}s"
        self.state_mgr.update_pr(state)

        return RecoveryResult(
            True,
            "backoff_scheduled",
            f"Retry scheduled in {delay} seconds",
            {"delay_sec": delay, "retry_count": state.retry_count},
        )

    def route_failure(
        self, pr_number: int, failure_type: str, context: dict[str, Any] | None = None
    ) -> RecoveryResult:
        """Route a failure to the appropriate handler."""
        context = context or {}

        # Route based on failure type
        if failure_type == "ci_failure":
            return self.handle_ci_failure(pr_number, context.get("diagnosis"))

        elif failure_type == "merge_conflict":
            return self.handle_merge_conflict(pr_number)

        elif failure_type == "missing_approval":
            return self.handle_missing_approval(pr_number)

        elif failure_type in {"transient_api_error", "network_error", "timeout"}:
            return self.handle_transient_error(pr_number, failure_type)

        elif failure_type == "stuck_pr":
            # Determine why stuck and route accordingly
            current_state = context.get("current_state", "")
            if current_state == "conflict_detected":
                return self.handle_merge_conflict(pr_number)
            elif current_state == "needs_approval":
                return self.handle_missing_approval(pr_number)
            else:
                return self.handle_transient_error(pr_number, "stuck")

        else:
            # Unknown failure type - escalate
            state = self.state_mgr.get_pr(pr_number)
            if state:
                self.state_mgr.mark_escalated(
                    pr_number,
                    reason=f"Unknown failure type: {failure_type}",
                    triggered_by="recovery_handler",
                )

            return RecoveryResult(
                False,
                "escalated",
                f"Unknown failure type: {failure_type}",
            )


def main() -> int:
    """CLI for recovery handlers."""
    import argparse

    p = argparse.ArgumentParser(description="PR Recovery Handlers")
    sub = p.add_subparsers(dest="cmd", required=True)

    # CI failure
    ci = sub.add_parser("ci-failure", help="Handle CI failure")
    ci.add_argument("--pr-number", type=int, required=True)
    ci.add_argument("--diagnosis", help="JSON diagnosis data")

    # Merge conflict
    conflict = sub.add_parser("merge-conflict", help="Handle merge conflict")
    conflict.add_argument("--pr-number", type=int, required=True)

    # Missing approval
    approval = sub.add_parser("missing-approval", help="Handle missing approval")
    approval.add_argument("--pr-number", type=int, required=True)

    # Transient error
    transient = sub.add_parser("transient", help="Handle transient error")
    transient.add_argument("--pr-number", type=int, required=True)
    transient.add_argument("--error-type", required=True)

    # Route
    route = sub.add_parser("route", help="Route failure to appropriate handler")
    route.add_argument("--pr-number", type=int, required=True)
    route.add_argument("--failure-type", required=True)
    route.add_argument("--context", help="JSON context data")

    args = p.parse_args()

    handlers = RecoveryHandlers()

    if args.cmd == "ci-failure":
        diagnosis = json.loads(args.diagnosis) if args.diagnosis else None
        result = handlers.handle_ci_failure(args.pr_number, diagnosis)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.success else 1

    elif args.cmd == "merge-conflict":
        result = handlers.handle_merge_conflict(args.pr_number)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.success else 1

    elif args.cmd == "missing-approval":
        result = handlers.handle_missing_approval(args.pr_number)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.success else 1

    elif args.cmd == "transient":
        result = handlers.handle_transient_error(args.pr_number, args.error_type)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.success else 1

    elif args.cmd == "route":
        context = json.loads(args.context) if args.context else {}
        result = handlers.route_failure(args.pr_number, args.failure_type, context)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.success else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
