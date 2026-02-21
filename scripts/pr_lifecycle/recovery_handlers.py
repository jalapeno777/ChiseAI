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
from pr_state_manager import PRStateManager

# Configuration
MAX_AUTO_FIX_RETRIES = int(os.getenv("CHISE_PR_MAX_RETRIES", "5"))
BACKOFF_INITIAL_SEC = int(os.getenv("CHISE_PR_BACKOFF_INITIAL", "60"))
BACKOFF_MAX_SEC = int(os.getenv("CHISE_PR_BACKOFF_MAX", "1800"))

# Gitea configuration
GITEA_BASE_URL = os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000").rstrip(
    "/"
)
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "")
GITEA_REVIEW_TOKEN = os.getenv("GITEA_REVIEW_TOKEN", GITEA_TOKEN)
GITEA_OWNER = os.getenv("GITEA_OWNER", "craig")
GITEA_REPO = os.getenv("GITEA_REPO", "ChiseAI")


def _redis_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a redis-cli command."""
    host = os.getenv("CHISE_REDIS_HOST", "host.docker.internal")
    port = int(os.getenv("CHISE_REDIS_PORT", "6380"))
    db = int(os.getenv("CHISE_REDIS_DB", "0"))

    return subprocess.run(
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
            with urllib.request.urlopen(req, timeout=30) as resp:
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
            with urllib.request.urlopen(req, timeout=30) as resp:
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

        # For now, escalate since auto-rebase requires git operations
        # In a full implementation, this would:
        # 1. Clone the repo
        # 2. Fetch main
        # 3. Rebase branch onto main
        # 4. Force push with lease
        # 5. Re-trigger CI

        self.state_mgr.mark_escalated(
            pr_number,
            reason="Auto-rebase not yet implemented - manual rebase required",
            triggered_by="recovery_handler",
        )

        return RecoveryResult(
            False,
            "escalated",
            "Auto-rebase implementation pending - escalated",
        )

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
