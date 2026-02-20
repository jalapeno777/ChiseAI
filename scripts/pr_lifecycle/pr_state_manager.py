#!/usr/bin/env python3
"""PR State Manager - Core state tracking for PR lifecycle management.

This module provides Redis-based state tracking for PRs, ensuring all agents
can monitor and manage PRs consistently throughout their lifecycle.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

# Redis key prefixes
PR_PREFIX = "bmad:chiseai:pr"
PR_ACTIVE_SET = f"{PR_PREFIX}:active"
PR_STATE_PREFIX = f"{PR_PREFIX}:state"
PR_EVENTS_SUFFIX = "events"
PR_FAILURES_SUFFIX = "failures"
PR_RETRY_COUNT_SUFFIX = "retry_count"
PR_OWNER_SUFFIX = "owner"

# Default TTL (5 days)
DEFAULT_TTL_SECONDS = 432000


@dataclass
class PRState:
    """Represents the current state of a PR in the lifecycle."""

    # Identification
    pr_number: int
    story_id: str
    branch: str
    head_sha: str

    # Ownership
    opened_by_agent: str
    owned_by_agent: str = ""

    # State
    current_state: str = "created"
    previous_state: str = ""
    state_changed_at: str = field(default_factory=lambda: _utc_now())

    # Timestamps
    created_at: str = field(default_factory=lambda: _utc_now())
    last_updated_at: str = field(default_factory=lambda: _utc_now())
    terminal_at: str = ""

    # CI Status
    ci_status: str = "pending"
    ci_contexts: dict[str, str] = field(default_factory=dict)
    last_ci_pipeline_id: str = ""

    # Merge Status
    mergeable: str = "unknown"  # true/false/unknown
    merge_attempts: int = 0
    last_merge_attempt_at: str = ""

    # Approval
    approval_status: str = "pending"  # pending/approved/changes_requested
    approvers: list[str] = field(default_factory=list)

    # Recovery
    retry_count: int = 0
    max_retries: int = 5
    failure_type: str = ""
    recovery_action: str = ""

    # Escalation
    escalated: bool = False
    escalated_at: str = ""
    escalation_reason: str = ""

    # Cleanup
    cleanup_scheduled: bool = False
    cleanup_after: str = ""

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for Redis storage."""
        return {
            "pr_number": str(self.pr_number),
            "story_id": self.story_id,
            "branch": self.branch,
            "head_sha": self.head_sha,
            "opened_by_agent": self.opened_by_agent,
            "owned_by_agent": self.owned_by_agent or self.opened_by_agent,
            "current_state": self.current_state,
            "previous_state": self.previous_state,
            "state_changed_at": self.state_changed_at,
            "created_at": self.created_at,
            "last_updated_at": self.last_updated_at,
            "terminal_at": self.terminal_at,
            "ci_status": self.ci_status,
            "ci_contexts": json.dumps(self.ci_contexts),
            "last_ci_pipeline_id": self.last_ci_pipeline_id,
            "mergeable": self.mergeable,
            "merge_attempts": str(self.merge_attempts),
            "last_merge_attempt_at": self.last_merge_attempt_at,
            "approval_status": self.approval_status,
            "approvers": json.dumps(self.approvers),
            "retry_count": str(self.retry_count),
            "max_retries": str(self.max_retries),
            "failure_type": self.failure_type,
            "recovery_action": self.recovery_action,
            "escalated": "true" if self.escalated else "false",
            "escalated_at": self.escalated_at,
            "escalation_reason": self.escalation_reason,
            "cleanup_scheduled": "true" if self.cleanup_scheduled else "false",
            "cleanup_after": self.cleanup_after,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "PRState":
        """Create PRState from dictionary retrieved from Redis."""
        return cls(
            pr_number=int(data.get("pr_number", 0)),
            story_id=data.get("story_id", ""),
            branch=data.get("branch", ""),
            head_sha=data.get("head_sha", ""),
            opened_by_agent=data.get("opened_by_agent", ""),
            owned_by_agent=data.get("owned_by_agent", ""),
            current_state=data.get("current_state", "created"),
            previous_state=data.get("previous_state", ""),
            state_changed_at=data.get("state_changed_at", ""),
            created_at=data.get("created_at", ""),
            last_updated_at=data.get("last_updated_at", ""),
            terminal_at=data.get("terminal_at", ""),
            ci_status=data.get("ci_status", "pending"),
            ci_contexts=json.loads(data.get("ci_contexts", "{}")),
            last_ci_pipeline_id=data.get("last_ci_pipeline_id", ""),
            mergeable=data.get("mergeable", "unknown"),
            merge_attempts=int(data.get("merge_attempts", 0)),
            last_merge_attempt_at=data.get("last_merge_attempt_at", ""),
            approval_status=data.get("approval_status", "pending"),
            approvers=json.loads(data.get("approvers", "[]")),
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 5)),
            failure_type=data.get("failure_type", ""),
            recovery_action=data.get("recovery_action", ""),
            escalated=data.get("escalated", "false").lower() == "true",
            escalated_at=data.get("escalated_at", ""),
            escalation_reason=data.get("escalation_reason", ""),
            cleanup_scheduled=data.get("cleanup_scheduled", "false").lower() == "true",
            cleanup_after=data.get("cleanup_after", ""),
        )

    def is_terminal(self) -> bool:
        """Check if PR is in a terminal state."""
        return self.current_state in {"merged", "closed_unmerged", "escalated"}

    def can_retry(self) -> bool:
        """Check if PR can be retried."""
        return self.retry_count < self.max_retries and not self.is_terminal()


@dataclass
class PREvent:
    """Represents an event in a PR's lifecycle."""

    timestamp: str
    event_type: str  # state_transition/failure/recovery/escalation/merge/comment
    from_state: str = ""
    to_state: str = ""
    triggered_by: str = ""  # ci_webhook/poll/merge_api/recovery_action/manual
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "triggered_by": self.triggered_by,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PREvent":
        return cls(
            timestamp=data.get("timestamp", ""),
            event_type=data.get("event_type", ""),
            from_state=data.get("from_state", ""),
            to_state=data.get("to_state", ""),
            triggered_by=data.get("triggered_by", ""),
            metadata=data.get("metadata", {}),
        )


def _utc_now() -> str:
    """Get current UTC timestamp as ISO string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _get_redis_config() -> tuple[str, int, int]:
    """Get Redis connection config from environment."""
    host = (
        os.getenv("CHISE_REDIS_HOST")
        or os.getenv("REDIS_HOST")
        or "host.docker.internal"
    )
    port = int(os.getenv("CHISE_REDIS_PORT") or os.getenv("REDIS_PORT") or "6380")
    db = int(os.getenv("CHISE_REDIS_DB") or os.getenv("REDIS_DB") or "0")
    return host, port, db


def _redis_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a redis-cli command."""
    host, port, db = _get_redis_config()
    return subprocess.run(
        ["redis-cli", "-h", host, "-p", str(port), "-n", str(db), *args],
        text=True,
        capture_output=True,
        check=False,
    )


class PRStateManager:
    """Manages PR state in Redis."""

    def __init__(self) -> None:
        self.host, self.port, self.db = _get_redis_config()

    def _pr_key(self, pr_number: int) -> str:
        return f"{PR_PREFIX}:{pr_number}"

    def _events_key(self, pr_number: int) -> str:
        return f"{PR_PREFIX}:{pr_number}:{PR_EVENTS_SUFFIX}"

    def _failures_key(self, pr_number: int) -> str:
        return f"{PR_PREFIX}:{pr_number}:{PR_FAILURES_SUFFIX}"

    def _state_set_key(self, state: str) -> str:
        return f"{PR_STATE_PREFIX}:{state}"

    def _owner_key(self, pr_number: int) -> str:
        return f"{PR_PREFIX}:{pr_number}:{PR_OWNER_SUFFIX}"

    def _retry_count_key(self, pr_number: int) -> str:
        return f"{PR_PREFIX}:{pr_number}:{PR_RETRY_COUNT_SUFFIX}"

    def register_pr(self, state: PRState) -> bool:
        """Register a new PR in the lifecycle system."""
        pr_key = self._pr_key(state.pr_number)

        # Check if already exists
        check = _redis_cli("EXISTS", pr_key)
        if check.returncode == 0 and check.stdout.strip() == "1":
            # Already exists, update instead
            return self.update_pr(state)

        # Store state
        data = state.to_dict()
        for key, value in data.items():
            _redis_cli("HSET", pr_key, key, value)

        # Set TTL
        _redis_cli("EXPIRE", pr_key, str(DEFAULT_TTL_SECONDS))

        # Add to active set
        _redis_cli("SADD", PR_ACTIVE_SET, str(state.pr_number))
        _redis_cli("EXPIRE", PR_ACTIVE_SET, str(DEFAULT_TTL_SECONDS))

        # Add to state set
        _redis_cli(
            "SADD", self._state_set_key(state.current_state), str(state.pr_number)
        )
        _redis_cli(
            "EXPIRE", self._state_set_key(state.current_state), str(DEFAULT_TTL_SECONDS)
        )

        # Set owner
        _redis_cli(
            "SET",
            self._owner_key(state.pr_number),
            state.owned_by_agent or state.opened_by_agent,
        )
        _redis_cli("EXPIRE", self._owner_key(state.pr_number), str(DEFAULT_TTL_SECONDS))

        # Log creation event
        event = PREvent(
            timestamp=_utc_now(),
            event_type="state_transition",
            to_state=state.current_state,
            triggered_by="registration",
            metadata={"story_id": state.story_id, "branch": state.branch},
        )
        self._log_event(state.pr_number, event)

        return True

    def get_pr(self, pr_number: int) -> PRState | None:
        """Get PR state from Redis."""
        pr_key = self._pr_key(pr_number)
        result = _redis_cli("HGETALL", pr_key)

        if result.returncode != 0 or not result.stdout.strip():
            return None

        # Parse hash output
        lines = result.stdout.strip().split("\n")
        data: dict[str, str] = {}
        for i in range(0, len(lines), 2):
            if i + 1 < len(lines):
                data[lines[i]] = lines[i + 1]

        if not data:
            return None

        return PRState.from_dict(data)

    def update_pr(self, state: PRState) -> bool:
        """Update PR state in Redis."""
        pr_key = self._pr_key(state.pr_number)
        state.last_updated_at = _utc_now()

        data = state.to_dict()
        for key, value in data.items():
            _redis_cli("HSET", pr_key, key, value)

        return True

    def transition_state(
        self,
        pr_number: int,
        to_state: str,
        triggered_by: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Transition PR to a new state."""
        state = self.get_pr(pr_number)
        if not state:
            return False

        from_state = state.current_state

        # Don't transition if already in target state
        if from_state == to_state:
            return True

        # Update state tracking
        old_state_key = self._state_set_key(from_state)
        new_state_key = self._state_set_key(to_state)

        _redis_cli("SREM", old_state_key, str(pr_number))
        _redis_cli("SADD", new_state_key, str(pr_number))
        _redis_cli("EXPIRE", new_state_key, str(DEFAULT_TTL_SECONDS))

        # Update PR hash
        now = _utc_now()
        pr_key = self._pr_key(pr_number)
        _redis_cli("HSET", pr_key, "previous_state", from_state)
        _redis_cli("HSET", pr_key, "current_state", to_state)
        _redis_cli("HSET", pr_key, "state_changed_at", now)
        _redis_cli("HSET", pr_key, "last_updated_at", now)

        # Check if terminal state
        if to_state in {"merged", "closed_unmerged", "escalated"}:
            _redis_cli("HSET", pr_key, "terminal_at", now)
            _redis_cli("SREM", PR_ACTIVE_SET, str(pr_number))

        # Log event
        event = PREvent(
            timestamp=now,
            event_type="state_transition",
            from_state=from_state,
            to_state=to_state,
            triggered_by=triggered_by,
            metadata=metadata or {},
        )
        self._log_event(pr_number, event)

        return True

    def _log_event(self, pr_number: int, event: PREvent) -> None:
        """Log an event for a PR."""
        events_key = self._events_key(pr_number)
        _redis_cli("RPUSH", events_key, json.dumps(event.to_dict()))
        _redis_cli("EXPIRE", events_key, str(DEFAULT_TTL_SECONDS))

    def log_failure(
        self,
        pr_number: int,
        failure_type: str,
        message: str,
        evidence: dict[str, Any] | None = None,
    ) -> bool:
        """Log a failure for a PR."""
        state = self.get_pr(pr_number)
        if not state:
            return False

        # Increment retry count
        state.retry_count += 1
        state.failure_type = failure_type
        self.update_pr(state)

        # Log failure
        failures_key = self._failures_key(pr_number)
        failure_data = {
            "timestamp": _utc_now(),
            "type": failure_type,
            "message": message,
            "evidence": evidence or {},
            "retry_count": state.retry_count,
        }
        _redis_cli("RPUSH", failures_key, json.dumps(failure_data))
        _redis_cli("EXPIRE", failures_key, str(DEFAULT_TTL_SECONDS))

        # Log event
        event = PREvent(
            timestamp=_utc_now(),
            event_type="failure",
            triggered_by="monitor",
            metadata=failure_data,
        )
        self._log_event(pr_number, event)

        return True

    def get_active_prs(self) -> list[int]:
        """Get list of all active PR numbers."""
        result = _redis_cli("SMEMBERS", PR_ACTIVE_SET)
        if result.returncode != 0:
            return []

        prs = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    prs.append(int(line))
                except ValueError:
                    continue
        return prs

    def get_prs_by_state(self, state: str) -> list[int]:
        """Get list of PR numbers in a specific state."""
        result = _redis_cli("SMEMBERS", self._state_set_key(state))
        if result.returncode != 0:
            return []

        prs = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    prs.append(int(line))
                except ValueError:
                    continue
        return prs

    def get_pr_events(self, pr_number: int, limit: int = 50) -> list[PREvent]:
        """Get event history for a PR."""
        events_key = self._events_key(pr_number)
        result = _redis_cli("LRANGE", events_key, "0", str(limit - 1))

        if result.returncode != 0:
            return []

        events = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    events.append(PREvent.from_dict(data))
                except json.JSONDecodeError:
                    continue
        return events

    def mark_escalated(
        self,
        pr_number: int,
        reason: str,
        triggered_by: str = "system",
    ) -> bool:
        """Mark a PR as escalated to humans."""
        state = self.get_pr(pr_number)
        if not state:
            return False

        now = _utc_now()
        pr_key = self._pr_key(pr_number)

        _redis_cli("HSET", pr_key, "escalated", "true")
        _redis_cli("HSET", pr_key, "escalated_at", now)
        _redis_cli("HSET", pr_key, "escalation_reason", reason)

        # Transition state
        self.transition_state(
            pr_number,
            to_state="escalated",
            triggered_by=triggered_by,
            metadata={"escalation_reason": reason},
        )

        return True

    def schedule_cleanup(self, pr_number: int, delay_minutes: int = 5) -> bool:
        """Schedule branch cleanup for a PR."""
        state = self.get_pr(pr_number)
        if not state:
            return False

        from datetime import timedelta

        cleanup_time = (
            datetime.now(UTC) + timedelta(minutes=delay_minutes)
        ).isoformat()

        pr_key = self._pr_key(pr_number)
        _redis_cli("HSET", pr_key, "cleanup_scheduled", "true")
        _redis_cli("HSET", pr_key, "cleanup_after", cleanup_time)

        return True

    def delete_pr(self, pr_number: int) -> bool:
        """Delete PR state from Redis (use with caution)."""
        # Remove from all sets
        state = self.get_pr(pr_number)
        if state:
            _redis_cli("SREM", self._state_set_key(state.current_state), str(pr_number))

        _redis_cli("SREM", PR_ACTIVE_SET, str(pr_number))

        # Delete keys
        _redis_cli("DEL", self._pr_key(pr_number))
        _redis_cli("DEL", self._events_key(pr_number))
        _redis_cli("DEL", self._failures_key(pr_number))
        _redis_cli("DEL", self._owner_key(pr_number))
        _redis_cli("DEL", self._retry_count_key(pr_number))

        return True


def main() -> int:
    """CLI for PR state management."""
    import argparse

    p = argparse.ArgumentParser(description="PR State Manager")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Register command
    register = sub.add_parser("register", help="Register a new PR")
    register.add_argument("--pr-number", type=int, required=True)
    register.add_argument("--story-id", required=True)
    register.add_argument("--branch", required=True)
    register.add_argument("--head-sha", required=True)
    register.add_argument("--agent", required=True, help="Agent that opened the PR")

    # Get command
    get = sub.add_parser("get", help="Get PR state")
    get.add_argument("--pr-number", type=int, required=True)

    # Transition command
    transition = sub.add_parser("transition", help="Transition PR state")
    transition.add_argument("--pr-number", type=int, required=True)
    transition.add_argument("--to-state", required=True)
    transition.add_argument("--triggered-by", default="cli")

    # List active command
    sub.add_parser("list-active", help="List all active PRs")

    # List by state command
    list_state = sub.add_parser("list-state", help="List PRs in a specific state")
    list_state.add_argument("--state", required=True)

    # Escalate command
    escalate = sub.add_parser("escalate", help="Escalate a PR")
    escalate.add_argument("--pr-number", type=int, required=True)
    escalate.add_argument("--reason", required=True)

    args = p.parse_args()

    mgr = PRStateManager()

    if args.cmd == "register":
        state = PRState(
            pr_number=args.pr_number,
            story_id=args.story_id,
            branch=args.branch,
            head_sha=args.head_sha,
            opened_by_agent=args.agent,
        )
        if mgr.register_pr(state):
            print(f"Registered PR #{args.pr_number} for story {args.story_id}")
            return 0
        else:
            print(f"Failed to register PR #{args.pr_number}", file=sys.stderr)
            return 1

    elif args.cmd == "get":
        state = mgr.get_pr(args.pr_number)
        if state:
            print(json.dumps(state.to_dict(), indent=2))
            return 0
        else:
            print(f"PR #{args.pr_number} not found", file=sys.stderr)
            return 1

    elif args.cmd == "transition":
        if mgr.transition_state(args.pr_number, args.to_state, args.triggered_by):
            print(f"Transitioned PR #{args.pr_number} to {args.to_state}")
            return 0
        else:
            print(f"Failed to transition PR #{args.pr_number}", file=sys.stderr)
            return 1

    elif args.cmd == "list-active":
        prs = mgr.get_active_prs()
        print(f"Active PRs: {prs}")
        return 0

    elif args.cmd == "list-state":
        prs = mgr.get_prs_by_state(args.state)
        print(f"PRs in state '{args.state}': {prs}")
        return 0

    elif args.cmd == "escalate":
        if mgr.mark_escalated(args.pr_number, args.reason):
            print(f"Escalated PR #{args.pr_number}: {args.reason}")
            return 0
        else:
            print(f"Failed to escalate PR #{args.pr_number}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
