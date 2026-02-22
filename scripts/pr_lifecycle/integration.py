#!/usr/bin/env python3
"""Integration helpers for connecting PR lifecycle management to existing scripts.

This module provides convenience functions for integrating PR lifecycle
management into existing automerge and CI workflows.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

from pr_state_manager import PRState, PRStateManager, _utc_now


def register_new_pr(
    pr_number: int,
    story_id: str,
    branch: str,
    head_sha: str,
    agent_id: str,
    enable_monitoring: bool = True,
) -> bool:
    """Register a newly created PR in the lifecycle system.

    This function should be called after creating a PR to ensure it is
    tracked and monitored throughout its lifecycle.

    Args:
        pr_number: The PR number
        story_id: The story ID associated with this PR
        branch: The branch name
        head_sha: The head commit SHA
        agent_id: The agent that created the PR
        enable_monitoring: Whether to start background monitoring

    Returns:
        True if registration was successful

    Example:
        # In gitea_pr_automerge.py, after PR creation:
        from integration import register_new_pr
        register_new_pr(
            pr_number=pr["number"],
            story_id=args.story_id,
            branch=args.head,
            head_sha=sha,
            agent_id=args.agent_id,
        )
    """
    state_mgr = PRStateManager()

    state = PRState(
        pr_number=pr_number,
        story_id=story_id,
        branch=branch,
        head_sha=head_sha,
        opened_by_agent=agent_id,
        owned_by_agent=agent_id,
    )

    success = state_mgr.register_pr(state)

    if success and enable_monitoring:
        # Optionally start background monitoring
        # In practice, this would likely be done by a separate service
        pass

    return success


def update_pr_on_merge_attempt(pr_number: int, success: bool, error: str = "") -> bool:
    """Update PR state when a merge attempt occurs.

    This function should be called from merge_reconciler.py when
    attempting to merge a PR.

    Args:
        pr_number: The PR number
        success: Whether the merge was successful
        error: Error message if merge failed

    Returns:
        True if update was successful
    """
    state_mgr = PRStateManager()
    state = state_mgr.get_pr(pr_number)

    if not state:
        return False

    state.merge_attempts += 1
    state.last_merge_attempt_at = _utc_now()

    if success:
        state_mgr.transition_state(
            pr_number,
            to_state="merged",
            triggered_by="merge_api",
        )
    else:
        state_mgr.log_failure(
            pr_number,
            failure_type="merge_failed",
            message=error or "Merge API call failed",
        )

    return state_mgr.update_pr(state)


def handle_ci_status_change(
    pr_number: int,
    ci_status: str,
    required_context: str = "ci/woodpecker/pr/ci",
) -> bool:
    """Handle CI status change for a PR.

    This function should be called when CI status changes, either
    from webhooks or polling.

    Args:
        pr_number: The PR number
        ci_status: The new CI status (pending/success/failure)
        required_context: The required CI context name

    Returns:
        True if state was updated
    """
    state_mgr = PRStateManager()
    state = state_mgr.get_pr(pr_number)

    if not state:
        return False

    state.ci_status = ci_status

    # Transition state based on CI status
    if ci_status == "success":
        if state.approval_status == "approved":
            target_state = "mergeable"
        else:
            target_state = "ci_passed"
    elif ci_status == "failure":
        target_state = "ci_failed"
    else:
        target_state = "running_ci"

    if target_state != state.current_state:
        state_mgr.transition_state(
            pr_number,
            to_state=target_state,
            triggered_by="ci_webhook",
            metadata={"ci_status": ci_status, "required_context": required_context},
        )

    return state_mgr.update_pr(state)


def is_pr_monitored(pr_number: int) -> bool:
    """Check if a PR is being monitored by the lifecycle system.

    Args:
        pr_number: The PR number

    Returns:
        True if the PR is registered and being monitored
    """
    state_mgr = PRStateManager()
    state = state_mgr.get_pr(pr_number)
    return state is not None and not state.is_terminal()


def get_pr_summary(pr_number: int) -> dict[str, Any] | None:
    """Get a summary of PR state for reporting.

    Args:
        pr_number: The PR number

    Returns:
        Dictionary with PR summary or None if not found
    """
    state_mgr = PRStateManager()
    state = state_mgr.get_pr(pr_number)

    if not state:
        return None

    return {
        "pr_number": state.pr_number,
        "story_id": state.story_id,
        "branch": state.branch,
        "current_state": state.current_state,
        "ci_status": state.ci_status,
        "mergeable": state.mergeable,
        "approval_status": state.approval_status,
        "retry_count": state.retry_count,
        "escalated": state.escalated,
        "is_terminal": state.is_terminal(),
    }


def main() -> int:
    """CLI for integration helpers."""
    import argparse
    import json

    p = argparse.ArgumentParser(description="PR Lifecycle Integration")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Register
    register = sub.add_parser("register", help="Register a new PR")
    register.add_argument("--pr-number", type=int, required=True)
    register.add_argument("--story-id", required=True)
    register.add_argument("--branch", required=True)
    register.add_argument("--head-sha", required=True)
    register.add_argument("--agent", required=True)

    # Check monitored
    check = sub.add_parser("check", help="Check if PR is monitored")
    check.add_argument("--pr-number", type=int, required=True)

    # Summary
    summary = sub.add_parser("summary", help="Get PR summary")
    summary.add_argument("--pr-number", type=int, required=True)

    # Merge attempt
    merge = sub.add_parser("merge-attempt", help="Record merge attempt")
    merge.add_argument("--pr-number", type=int, required=True)
    merge.add_argument("--success", action="store_true")
    merge.add_argument("--error", default="")

    args = p.parse_args()

    if args.cmd == "register":
        if register_new_pr(
            args.pr_number,
            args.story_id,
            args.branch,
            args.head_sha,
            args.agent,
        ):
            print(f"Registered PR #{args.pr_number}")
            return 0
        else:
            print(f"Failed to register PR #{args.pr_number}", file=sys.stderr)
            return 1

    elif args.cmd == "check":
        monitored = is_pr_monitored(args.pr_number)
        print(f"PR #{args.pr_number} monitored: {monitored}")
        return 0 if monitored else 1

    elif args.cmd == "summary":
        summary_data = get_pr_summary(args.pr_number)
        if summary_data:
            print(json.dumps(summary_data, indent=2))
            return 0
        else:
            print(f"PR #{args.pr_number} not found", file=sys.stderr)
            return 1

    elif args.cmd == "merge-attempt":
        if update_pr_on_merge_attempt(args.pr_number, args.success, args.error):
            print(f"Recorded merge attempt for PR #{args.pr_number}")
            return 0
        else:
            print("Failed to record merge attempt", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
