#!/usr/bin/env python3
"""Agent CLI - Command line interface for agents to interact with PR pipeline.

This module provides CLI commands for agents to:
- Check PR status
- Reserve scope ownership
- Submit work for review
- Check approval status
- View PR history

Usage:
    # Check PR status
    python3 scripts/pr_lifecycle/agent_cli.py pr-status --pr 123

    # Reserve scope
    python3 scripts/pr_lifecycle/agent_cli.py reserve-scope --story-id ST-001 --scope src/module/

    # Submit work
    python3 scripts/pr_lifecycle/agent_cli.py submit --story-id ST-001 --message "Work complete"

    # Check approval
    python3 scripts/pr_lifecycle/agent_cli.py approval-status --pr 123
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "src" if __file__ else ".")
)
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

# Constants
GITEA_BASE_URL = os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000")
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "")
GITEA_OWNER = os.getenv("GITEA_OWNER", os.getenv("CI_REPO_OWNER", ""))
GITEA_REPO = os.getenv("GITEA_REPO", os.getenv("CI_REPO_NAME", ""))


@dataclass
class PRStatusInfo:
    """Information about a PR's current status."""

    pr_number: int
    title: str = ""
    state: str = ""  # open/closed/merged
    branch: str = ""
    base_branch: str = ""
    author: str = ""

    # CI Status
    ci_status: str = "pending"  # pending/success/failure
    ci_contexts: dict[str, str] = field(default_factory=dict)

    # Merge Status
    mergeable: bool = False
    mergeable_state: str = ""  # clean/conflicted/unstable/etc

    # Approval
    approvals: int = 0
    changes_requested: int = 0
    review_state: str = "pending"  # pending/approved/changes_requested

    # Activity
    created_at: str = ""
    updated_at: str = ""
    last_activity: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pr_number": self.pr_number,
            "title": self.title,
            "state": self.state,
            "branch": self.branch,
            "base_branch": self.base_branch,
            "author": self.author,
            "ci_status": self.ci_status,
            "ci_contexts": self.ci_contexts,
            "mergeable": self.mergeable,
            "mergeable_state": self.mergeable_state,
            "approvals": self.approvals,
            "changes_requested": self.changes_requested,
            "review_state": self.review_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_activity": self.last_activity,
        }


@dataclass
class ScopeReservation:
    """Result of scope reservation attempt."""

    story_id: str
    scope: str
    success: bool
    owner: str = ""
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "story_id": self.story_id,
            "scope": self.scope,
            "success": self.success,
            "owner": self.owner,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class SubmitResult:
    """Result of work submission."""

    story_id: str
    branch: str
    success: bool
    head_sha: str = ""
    message: str = ""
    handoff_items: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "story_id": self.story_id,
            "branch": self.branch,
            "success": self.success,
            "head_sha": self.head_sha,
            "message": self.message,
            "handoff_items": self.handoff_items,
            "timestamp": self.timestamp,
        }


class AgentCLI:
    """Command line interface for agents."""

    def __init__(
        self,
        agent_id: str | None = None,
        repo_root: str | None = None,
    ):
        """Initialize CLI.

        Args:
            agent_id: Agent identifier (auto-detected if None)
            repo_root: Path to repository root (auto-detected if None)
        """
        self.agent_id = agent_id or os.getenv("AGENT_ID", "unknown")
        self.repo_root = Path(repo_root) if repo_root else self._find_repo_root()

    def _find_repo_root(self) -> Path:
        """Find repository root from current location."""
        try:
            result = subprocess.run(  # nosec B607
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            return Path(result.stdout.strip())
        except subprocess.CalledProcessError:
            return Path.cwd()

    def _run_git(self, *args: str) -> tuple[int, str, str]:
        """Run git command and return (rc, stdout, stderr)."""
        result = subprocess.run(  # nosec B607
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=self.repo_root,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def _get_current_branch(self) -> str:
        """Get current git branch."""
        rc, stdout, _ = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if rc == 0:
            return stdout
        return ""

    def _get_head_sha(self) -> str:
        """Get current HEAD SHA."""
        rc, stdout, _ = self._run_git("rev-parse", "HEAD")
        if rc == 0:
            return stdout
        return ""

    def _get_commit_count(self, base: str = "main") -> int:
        """Get number of commits ahead of base branch."""
        branch = self._get_current_branch()
        rc, stdout, _ = self._run_git("rev-list", "--count", f"{base}..{branch}")
        if rc == 0:
            try:
                return int(stdout)
            except ValueError:
                pass
        return 0

    def _check_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        rc, _, _ = self._run_git("diff-index", "--quiet", "HEAD", "--")
        return rc != 0  # Non-zero means there are changes

    def _get_changed_files(self, base: str = "main") -> list[str]:
        """Get list of changed files compared to base."""
        branch = self._get_current_branch()
        rc, stdout, _ = self._run_git("diff", "--name-only", f"{base}...{branch}")
        if rc == 0:
            return [f.strip() for f in stdout.split("\n") if f.strip()]
        return []

    def check_pr_status(self, pr_number: int) -> PRStatusInfo:
        """Check status of a PR.

        Args:
            pr_number: The PR number to check

        Returns:
            PRStatusInfo with current status
        """
        info = PRStatusInfo(pr_number=pr_number)

        # Try to get PR info from gitea CLI or API
        # First, try using gh CLI if available
        try:
            result = subprocess.run(  # nosec B607
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr_number),
                    "--json",
                    "number,title,state,headRefName,baseRefName,author,createdAt,updatedAt,mergeStateStatus,mergeable,reviews",
                ],
                capture_output=True,
                text=True,
                cwd=self.repo_root,
                timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                info.title = data.get("title", "")
                info.state = data.get("state", "")
                info.branch = data.get("headRefName", "")
                info.base_branch = data.get("baseRefName", "")
                info.author = data.get("author", {}).get("login", "")
                info.created_at = data.get("createdAt", "")
                info.updated_at = data.get("updatedAt", "")
                info.mergeable_state = data.get("mergeStateStatus", "")
                info.mergeable = data.get("mergeable", False)

                # Process reviews
                reviews = data.get("reviews", [])
                for review in reviews:
                    state = review.get("state", "").upper()
                    if state == "APPROVED":
                        info.approvals += 1
                    elif state == "CHANGES_REQUESTED":
                        info.changes_requested += 1

                if info.changes_requested > 0:
                    info.review_state = "changes_requested"
                elif info.approvals > 0:
                    info.review_state = "approved"

        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass

        # If gh CLI failed, try to get basic info from git
        if not info.branch:
            # Try to find branch from PR number in local refs
            rc, stdout, _ = self._run_git(
                "for-each-ref", "--format=%(refname:short)", "refs/heads/"
            )
            if rc == 0:
                branches = stdout.split("\n")
                for branch in branches:
                    if branch.strip():
                        info.branch = branch.strip()
                        break

        # Get CI status from environment or recent commits
        info.ci_status = self._infer_ci_status()

        return info

    def _infer_ci_status(self) -> str:
        """Infer CI status from recent activity."""
        # Check for CI status files or recent commit messages
        try:
            rc, stdout, _ = self._run_git("log", "-1", "--format=%s", "HEAD")
            if rc == 0 and stdout:
                msg = stdout.lower()
                if "[ci skip]" in msg or "[skip ci]" in msg:
                    return "skipped"
        except Exception:
            pass
        return "pending"

    def reserve_scope(
        self,
        story_id: str,
        scope: str,
        force: bool = False,
    ) -> ScopeReservation:
        """Reserve scope ownership.

        Args:
            story_id: The story ID
            scope: The scope path to reserve
            force: Force reservation even if owned

        Returns:
            ScopeReservation result
        """
        # Convert scope to slug
        slug = scope.strip("/").replace("/", ":").lower()

        # Check current ownership via Redis
        try:
            result = subprocess.run(  # nosec B607
                [
                    "redis-cli",
                    "-h",
                    "host.docker.internal",
                    "-p",
                    "6380",
                    "HGET",
                    "bmad:chiseai:ownership",
                    slug,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            current_owner = result.stdout.strip()

            if current_owner and not force:
                # Check if we already own it
                if (
                    story_id is not None
                    and story_id in current_owner
                    and self.agent_id is not None
                    and self.agent_id in current_owner
                ):
                    return ScopeReservation(
                        story_id=story_id,
                        scope=scope,
                        success=True,
                        owner=current_owner,
                        message=f"Already owned by you: {current_owner}",
                    )
                else:
                    return ScopeReservation(
                        story_id=story_id,
                        scope=scope,
                        success=False,
                        owner=current_owner,
                        message=f"Scope already owned by: {current_owner}",
                    )

            # Claim ownership
            timestamp = datetime.now(UTC).isoformat()
            owner_value = f"{story_id}/{self.agent_id}/{timestamp}"

            result = subprocess.run(  # nosec B607
                [
                    "redis-cli",
                    "-h",
                    "host.docker.internal",
                    "-p",
                    "6380",
                    "HSET",
                    "bmad:chiseai:ownership",
                    slug,
                    owner_value,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                # Set TTL
                subprocess.run(  # nosec B607
                    [
                        "redis-cli",
                        "-h",
                        "host.docker.internal",
                        "-p",
                        "6380",
                        "EXPIRE",
                        "bmad:chiseai:ownership",
                        "432000",
                    ],
                    capture_output=True,
                    timeout=5,
                )

                return ScopeReservation(
                    story_id=story_id,
                    scope=scope,
                    success=True,
                    owner=owner_value,
                    message="Scope reserved successfully",
                )
            else:
                return ScopeReservation(
                    story_id=story_id,
                    scope=scope,
                    success=False,
                    message=f"Failed to set ownership: {result.stderr}",
                )

        except subprocess.TimeoutExpired:
            return ScopeReservation(
                story_id=story_id,
                scope=scope,
                success=False,
                message="Redis connection timeout",
            )
        except FileNotFoundError:
            return ScopeReservation(
                story_id=story_id,
                scope=scope,
                success=False,
                message="Redis CLI not available",
            )

    def submit_work(
        self,
        story_id: str,
        message: str = "",
        base_branch: str = "main",
    ) -> SubmitResult:
        """Submit work for review.

        Args:
            story_id: The story ID
            message: Optional message for handoff
            base_branch: Base branch to compare against

        Returns:
            SubmitResult with handoff information
        """
        branch = self._get_current_branch()
        head_sha = self._get_head_sha()
        commit_count = self._get_commit_count(base_branch)
        changed_files = self._get_changed_files(base_branch)

        result = SubmitResult(
            story_id=story_id,
            branch=branch,
            success=False,
            head_sha=head_sha,
        )

        # Validate state
        if not branch.startswith("feature/") and not branch.startswith("safety/"):
            result.message = (
                f"Invalid branch name: {branch}. Must start with feature/ or safety/"
            )
            return result

        if self._check_uncommitted_changes():
            result.message = (
                "Uncommitted changes detected. Commit or stash before submitting."
            )
            return result

        if commit_count == 0:
            result.message = f"No commits ahead of {base_branch}. Nothing to submit."
            return result

        # Build handoff information
        result.success = True
        result.message = message or f"Work completed for {story_id}"
        result.handoff_items = [
            f"Story ID: {story_id}",
            f"Branch: {branch}",
            f"Head SHA: {head_sha}",
            f"Commits ahead of {base_branch}: {commit_count}",
            f"Files changed: {len(changed_files)}",
            "",
            "Changed files:",
        ]
        for f in changed_files[:20]:  # Show first 20
            result.handoff_items.append(f"  - {f}")
        if len(changed_files) > 20:
            result.handoff_items.append(f"  ... and {len(changed_files) - 20} more")

        result.handoff_items.extend(
            [
                "",
                "Next steps:",
                "  1. Push branch to origin (if not already pushed)",
                "  2. Report handoff to Jarvis",
                "  3. Do NOT open PR yourself - Jarvis will coordinate with merlin",
                "",
                f"Handoff message: {result.message}",
            ]
        )

        return result

    def check_approval_status(self, pr_number: int) -> dict[str, Any]:
        """Check approval status of a PR.

        Args:
            pr_number: The PR number

        Returns:
            Dictionary with approval information
        """
        pr_info = self.check_pr_status(pr_number)

        return {
            "pr_number": pr_number,
            "review_state": pr_info.review_state,
            "approvals": pr_info.approvals,
            "changes_requested": pr_info.changes_requested,
            "mergeable": pr_info.mergeable,
            "mergeable_state": pr_info.mergeable_state,
            "state": pr_info.state,
            "can_merge": (
                pr_info.review_state == "approved"
                and pr_info.mergeable
                and pr_info.state == "open"
            ),
        }

    def list_my_prs(self, state: str = "open") -> list[dict[str, Any]]:
        """List PRs opened by this agent.

        Args:
            state: PR state filter (open/closed/merged/all)

        Returns:
            List of PR information dictionaries
        """
        prs = []

        try:
            result = subprocess.run(  # nosec B607
                [
                    "gh",
                    "pr",
                    "list",
                    "--author",
                    "@me",
                    "--state",
                    state,
                    "--json",
                    "number,title,state,headRefName,baseRefName,createdAt,updatedAt",
                ],
                capture_output=True,
                text=True,
                cwd=self.repo_root,
                timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for pr in data:
                    prs.append(
                        {
                            "number": pr.get("number"),
                            "title": pr.get("title"),
                            "state": pr.get("state"),
                            "branch": pr.get("headRefName"),
                            "base": pr.get("baseRefName"),
                            "created": pr.get("createdAt"),
                            "updated": pr.get("updatedAt"),
                        }
                    )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass

        return prs


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Agent CLI - Interact with PR pipeline"
    )
    parser.add_argument(
        "--agent-id",
        default=os.getenv("AGENT_ID", "unknown"),
        help="Agent identifier",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # pr-status command
    status_parser = subparsers.add_parser("pr-status", help="Check PR status")
    status_parser.add_argument(
        "--pr",
        type=int,
        required=True,
        help="PR number to check",
    )

    # reserve-scope command
    reserve_parser = subparsers.add_parser(
        "reserve-scope", help="Reserve scope ownership"
    )
    reserve_parser.add_argument(
        "--story-id",
        required=True,
        help="Story ID",
    )
    reserve_parser.add_argument(
        "--scope",
        required=True,
        help="Scope path to reserve (e.g., src/module/)",
    )
    reserve_parser.add_argument(
        "--force",
        action="store_true",
        help="Force reservation even if owned",
    )

    # submit command
    submit_parser = subparsers.add_parser("submit", help="Submit work for review")
    submit_parser.add_argument(
        "--story-id",
        required=True,
        help="Story ID",
    )
    submit_parser.add_argument(
        "--message",
        default="",
        help="Handoff message",
    )
    submit_parser.add_argument(
        "--base",
        default="main",
        help="Base branch (default: main)",
    )

    # approval-status command
    approval_parser = subparsers.add_parser(
        "approval-status", help="Check approval status"
    )
    approval_parser.add_argument(
        "--pr",
        type=int,
        required=True,
        help="PR number to check",
    )

    # list-prs command
    list_parser = subparsers.add_parser("list-prs", help="List my PRs")
    list_parser.add_argument(
        "--state",
        default="open",
        choices=["open", "closed", "merged", "all"],
        help="PR state filter",
    )

    # worktree-status command
    subparsers.add_parser("worktree-status", help="Check current worktree status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    cli = AgentCLI(agent_id=args.agent_id)

    if args.command == "pr-status":
        info = cli.check_pr_status(args.pr)
        if args.json:
            print(json.dumps(info.to_dict(), indent=2))
        else:
            print(f"\n📋 PR #{info.pr_number} Status\n")
            print(f"Title: {info.title or 'N/A'}")
            print(f"State: {info.state or 'unknown'}")
            print(f"Branch: {info.branch or 'N/A'} -> {info.base_branch or 'N/A'}")
            print(f"Author: {info.author or 'N/A'}")
            print(f"\nCI Status: {info.ci_status}")
            print(
                f"Mergeable: {'Yes' if info.mergeable else 'No'} ({info.mergeable_state})"
            )
            print(
                f"\nReviews: {info.approvals} approval(s), {info.changes_requested} change request(s)"
            )
            print(f"Review State: {info.review_state}")

    elif args.command == "reserve-scope":
        result = cli.reserve_scope(args.story_id, args.scope, args.force)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            status = "✓" if result.success else "✗"
            print(f"\n{status} Scope Reservation\n")
            print(f"Story: {result.story_id}")
            print(f"Scope: {result.scope}")
            print(f"Success: {result.success}")
            print(f"Owner: {result.owner or 'N/A'}")
            print(f"Message: {result.message}")

    elif args.command == "submit":
        result = cli.submit_work(args.story_id, args.message, args.base)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            status = "✓" if result.success else "✗"
            print(f"\n{status} Work Submission\n")
            print(f"Story: {result.story_id}")
            print(f"Branch: {result.branch}")
            print(f"Head SHA: {result.head_sha}")
            print(f"Success: {result.success}")
            if result.message:
                print(f"\nMessage: {result.message}")
            if result.handoff_items:
                print("\n" + "=" * 60)
                print("HANDOFF DOCUMENT")
                print("=" * 60)
                for item in result.handoff_items:
                    print(item)

    elif args.command == "approval-status":
        status = cli.check_approval_status(args.pr)
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print(f"\n📝 Approval Status for PR #{args.pr}\n")
            print(f"Review State: {status['review_state']}")
            print(f"Approvals: {status['approvals']}")
            print(f"Changes Requested: {status['changes_requested']}")
            print(f"Mergeable: {'Yes' if status['mergeable'] else 'No'}")
            print(f"Mergeable State: {status['mergeable_state']}")
            print(f"\nCan Merge: {'✓ Yes' if status['can_merge'] else '✗ No'}")

    elif args.command == "list-prs":
        prs = cli.list_my_prs(args.state)
        if args.json:
            print(json.dumps(prs, indent=2))
        else:
            print(f"\n📋 My PRs ({args.state})\n")
            if not prs:
                print("No PRs found.")
            else:
                for pr in prs:
                    print(f"#{pr['number']}: {pr['title']}")
                    print(f"   Branch: {pr['branch']} -> {pr['base']}")
                    print(f"   State: {pr['state']} | Created: {pr['created']}")
                    print()

    elif args.command == "worktree-status":
        branch = cli._get_current_branch()
        head_sha = cli._get_head_sha()
        commit_count = cli._get_commit_count()
        has_changes = cli._check_uncommitted_changes()
        changed_files = cli._get_changed_files()

        status = {
            "agent_id": cli.agent_id,
            "branch": branch,
            "head_sha": head_sha,
            "commits_ahead": commit_count,
            "uncommitted_changes": has_changes,
            "files_changed": len(changed_files),
            "repo_root": str(cli.repo_root),
        }

        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print("\n🔧 Worktree Status\n")
            print(f"Agent: {status['agent_id']}")
            print(f"Branch: {status['branch']}")
            print(
                f"HEAD SHA: {status['head_sha'][:8] if status['head_sha'] else 'N/A'}..."
            )
            print(f"Commits ahead of main: {status['commits_ahead']}")
            print(
                f"Uncommitted changes: {'Yes' if status['uncommitted_changes'] else 'No'}"
            )
            print(f"Files changed: {status['files_changed']}")
            print(f"Repo root: {status['repo_root']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
