#!/usr/bin/env python3
"""
Worktree Manager for ChiseAI Agent Swarm Parallel Coordination.

Manages isolated git worktrees for multiple agents working in parallel.
Provides worktree creation, cleanup, and tracking via Redis.

Story: ST-AUTO-007
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Redis key patterns
WORKTREE_PREFIX = "bmad:chiseai:swarm:worktree:"
AGENT_WORKTREE_PREFIX = "bmad:chiseai:swarm:agent:"
WORKTREE_LOCK_PREFIX = "bmad:chiseai:swarm:worktree-lock:"


class WorktreeError(Exception):
    """Exception raised for worktree management errors."""

    pass


class WorktreeConflictError(WorktreeError):
    """Exception raised when worktree conflicts are detected."""

    pass


@dataclass
class WorktreeInfo:
    """Information about a git worktree."""

    path: str
    branch: str
    commit: str
    story_id: str
    agent: str
    created_at: str
    status: str = "active"
    last_heartbeat: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "branch": self.branch,
            "commit": self.commit,
            "story_id": self.story_id,
            "agent": self.agent,
            "created_at": self.created_at,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorktreeInfo:
        """Create WorktreeInfo from dictionary."""
        return cls(
            path=data["path"],
            branch=data["branch"],
            commit=data["commit"],
            story_id=data["story_id"],
            agent=data["agent"],
            created_at=data["created_at"],
            status=data.get("status", "active"),
            last_heartbeat=data.get("last_heartbeat"),
            metadata=data.get("metadata", {}),
        )


class WorktreeManager:
    """Manages git worktrees for parallel agent execution."""

    def __init__(
        self,
        repo_root: Path | None = None,
        worktree_root: Path | None = None,
        redis_host: str | None = None,
        redis_port: int = 6380,
        redis_db: int = 0,
    ):
        """Initialize worktree manager.

        Args:
            repo_root: Root of the git repository. Auto-detected if not provided.
            worktree_root: Root directory for worktrees. Defaults to .swarm-worktrees.
            redis_host: Redis host for state tracking.
            redis_port: Redis port.
            redis_db: Redis database number.
        """
        self.repo_root = repo_root or self._find_repo_root()
        self.worktree_root = worktree_root or (self.repo_root / ".swarm-worktrees")
        self.redis_host = (
            redis_host
            or os.getenv("CHISE_REDIS_HOST")
            or os.getenv("REDIS_HOST")
            or "host.docker.internal"
        )
        self.redis_port = redis_port
        self.redis_db = redis_db
        self._redis_available = self._check_redis()

    def _find_repo_root(self) -> Path:
        """Find the git repository root."""
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise WorktreeError("Not in a git repository")
        return Path(result.stdout.strip())

    def _check_redis(self) -> bool:
        """Check if Redis is available."""
        try:
            result = subprocess.run(  # nosec B607
                [
                    "redis-cli",
                    "-h",
                    self.redis_host,
                    "-p",
                    str(self.redis_port),
                    "-n",
                    str(self.redis_db),
                    "PING",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0 and result.stdout.strip() == "PONG"
        except Exception:
            return False

    def _redis_cli(self, *args: str) -> tuple[int, str, str]:
        """Execute a redis-cli command."""
        cmd = [
            "redis-cli",
            "-h",
            self.redis_host,
            "-p",
            str(self.redis_port),
            "-n",
            str(self.redis_db),
            *args,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def _utc_now(self) -> str:
        """Get current UTC timestamp."""
        return (
            dt.datetime.now(dt.UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _worktree_key(self, worktree_path: str) -> str:
        """Generate Redis key for worktree."""
        path_hash = str(hash(worktree_path) % 10000000)
        return f"{WORKTREE_PREFIX}{path_hash}"

    def _agent_key(self, story_id: str, agent: str) -> str:
        """Generate Redis key for agent worktrees."""
        return f"{AGENT_WORKTREE_PREFIX}{story_id}:{agent}"

    def list_worktrees(self) -> list[dict[str, Any]]:
        """List all git worktrees."""
        result = subprocess.run(  # nosec B607
            ["git", "-C", str(self.repo_root), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise WorktreeError(f"Failed to list worktrees: {result.stderr}")

        worktrees: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        for line in result.stdout.split("\n"):
            line = line.strip()
            if not line:
                if current:
                    worktrees.append(current)
                    current = {}
            elif line.startswith("worktree "):
                current["path"] = line[9:]
            elif line.startswith("branch "):
                current["branch"] = line[7:].replace("refs/heads/", "")
            elif line.startswith("HEAD "):
                current["commit"] = line[5:]
            elif line.startswith("detached"):
                current["detached"] = True
            elif line.startswith("prunable"):
                current["prunable"] = True

        if current:
            worktrees.append(current)

        return worktrees

    def create_worktree(
        self,
        story_id: str,
        agent: str,
        branch: str,
        base_ref: str = "main",
        force: bool = False,
    ) -> WorktreeInfo:
        """Create a new worktree for an agent.

        Args:
            story_id: Story ID (e.g., ST-AUTO-007)
            agent: Agent identifier
            branch: Branch name to create/checkout
            base_ref: Base reference for new branch
            force: Force creation even if worktree exists

        Returns:
            WorktreeInfo object

        Raises:
            WorktreeConflictError: If worktree already exists and force=False
        """
        # Sanitize names for filesystem
        safe_story = "".join(c if c.isalnum() or c in "._-" else "-" for c in story_id)
        safe_agent = "".join(c if c.isalnum() or c in "._-" else "-" for c in agent)
        worktree_name = f"{safe_story}-{safe_agent}"
        worktree_path = self.worktree_root / worktree_name

        # Check if worktree already exists
        existing = self._get_worktree_by_path(str(worktree_path))
        if existing and not force:
            raise WorktreeConflictError(
                f"Worktree already exists at {worktree_path}. "
                "Use force=True to reuse or cleanup first."
            )

        # Create worktree root if needed
        self.worktree_root.mkdir(parents=True, exist_ok=True)

        # Check if branch exists
        branch_exists = (
            subprocess.run(  # nosec B607
                [
                    "git",
                    "-C",
                    str(self.repo_root),
                    "show-ref",
                    "--verify",
                    f"refs/heads/{branch}",
                ],
                capture_output=True,
                text=True,
                check=False,
            ).returncode
            == 0
        )

        # Create worktree
        if branch_exists:
            result = subprocess.run(  # nosec B607
                [
                    "git",
                    "-C",
                    str(self.repo_root),
                    "worktree",
                    "add",
                    str(worktree_path),
                    branch,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            result = subprocess.run(  # nosec B607
                [
                    "git",
                    "-C",
                    str(self.repo_root),
                    "worktree",
                    "add",
                    "-b",
                    branch,
                    str(worktree_path),
                    base_ref,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        if result.returncode != 0:
            raise WorktreeError(f"Failed to create worktree: {result.stderr}")

        # Get commit hash
        commit_result = subprocess.run(  # nosec B607
            ["git", "-C", str(worktree_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        commit = (
            commit_result.stdout.strip() if commit_result.returncode == 0 else "unknown"
        )

        # Create worktree info
        info = WorktreeInfo(
            path=str(worktree_path),
            branch=branch,
            commit=commit,
            story_id=story_id,
            agent=agent,
            created_at=self._utc_now(),
            status="active",
            last_heartbeat=self._utc_now(),
        )

        # Store in Redis
        if self._redis_available:
            self._store_worktree_info(info)

        logger.info(f"Created worktree at {worktree_path} for {story_id}/{agent}")
        return info

    def _get_worktree_by_path(self, path: str) -> WorktreeInfo | None:
        """Get worktree info by path from Redis."""
        if not self._redis_available:
            return None

        key = self._worktree_key(path)
        rc, stdout, _ = self._redis_cli("GET", key)
        if rc == 0 and stdout:
            try:
                data = json.loads(stdout)
                return WorktreeInfo.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                return None
        return None

    def _store_worktree_info(self, info: WorktreeInfo, ttl: int = 432000) -> None:
        """Store worktree info in Redis."""
        key = self._worktree_key(info.path)
        data = json.dumps(info.to_dict())
        self._redis_cli("SET", key, data, "EX", str(ttl))

        # Also add to agent's worktree list
        agent_key = self._agent_key(info.story_id, info.agent)
        self._redis_cli("SADD", agent_key, info.path)
        self._redis_cli("EXPIRE", agent_key, str(ttl))

    def cleanup_worktree(
        self,
        worktree_path: str,
        remove_branch: bool = False,
        force: bool = False,
    ) -> bool:
        """Clean up a worktree.

        Args:
            worktree_path: Path to the worktree
            remove_branch: Also remove the git branch
            force: Force removal even if worktree is locked

        Returns:
            True if cleanup was successful
        """
        # Check if worktree is locked
        if not force:
            lock_key = f"{WORKTREE_LOCK_PREFIX}{hash(worktree_path) % 10000000}"
            rc, stdout, _ = self._redis_cli("GET", lock_key)
            if rc == 0 and stdout:
                raise WorktreeError(
                    f"Worktree {worktree_path} is locked. Use force=True to override."
                )

        # Remove worktree
        result = subprocess.run(  # nosec B607
            [
                "git",
                "-C",
                str(self.repo_root),
                "worktree",
                "remove",
                str(worktree_path),
                "--force",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0 and "is not a working tree" not in result.stderr:
            if not force:
                raise WorktreeError(f"Failed to remove worktree: {result.stderr}")
            logger.warning(f"Worktree removal warning: {result.stderr}")

        # Get branch name before removing from Redis
        info = self._get_worktree_by_path(worktree_path)
        branch = info.branch if info else None

        # Remove from Redis
        if self._redis_available:
            key = self._worktree_key(worktree_path)
            self._redis_cli("DEL", key)

            if info:
                agent_key = self._agent_key(info.story_id, info.agent)
                self._redis_cli("SREM", agent_key, worktree_path)

        # Remove branch if requested
        if remove_branch and branch:
            subprocess.run(  # nosec B607
                ["git", "-C", str(self.repo_root), "branch", "-D", branch],
                capture_output=True,
                text=True,
                check=False,
            )

        logger.info(f"Cleaned up worktree at {worktree_path}")
        return True

    def get_agent_worktrees(self, story_id: str, agent: str) -> list[WorktreeInfo]:
        """Get all worktrees for a specific agent."""
        if not self._redis_available:
            return []

        agent_key = self._agent_key(story_id, agent)
        rc, stdout, _ = self._redis_cli("SMEMBERS", agent_key)

        if rc != 0 or not stdout:
            return []

        worktrees = []
        for path in stdout.split("\n"):
            if path:
                info = self._get_worktree_by_path(path)
                if info:
                    worktrees.append(info)

        return worktrees

    def update_heartbeat(self, worktree_path: str) -> bool:
        """Update heartbeat for a worktree.

        Args:
            worktree_path: Path to the worktree

        Returns:
            True if heartbeat was updated
        """
        info = self._get_worktree_by_path(worktree_path)
        if not info:
            return False

        info.last_heartbeat = self._utc_now()
        if self._redis_available:
            self._store_worktree_info(info)

        return True

    def lock_worktree(
        self, worktree_path: str, story_id: str, agent: str, ttl: int = 3600
    ) -> bool:
        """Lock a worktree to prevent concurrent modifications.

        Args:
            worktree_path: Path to the worktree
            story_id: Story ID of the locker
            agent: Agent identifier
            ttl: Lock TTL in seconds

        Returns:
            True if lock was acquired
        """
        if not self._redis_available:
            return True

        lock_key = f"{WORKTREE_LOCK_PREFIX}{hash(worktree_path) % 10000000}"
        lock_value = f"{story_id}/{agent}/{self._utc_now()}"

        # Use SET NX to atomically acquire lock
        rc, stdout, _ = self._redis_cli(
            "SET", lock_key, lock_value, "NX", "EX", str(ttl)
        )
        return rc == 0 and stdout == "OK"

    def unlock_worktree(self, worktree_path: str) -> bool:
        """Unlock a worktree.

        Args:
            worktree_path: Path to the worktree

        Returns:
            True if lock was released
        """
        if not self._redis_available:
            return True

        lock_key = f"{WORKTREE_LOCK_PREFIX}{hash(worktree_path) % 10000000}"
        rc, _, _ = self._redis_cli("DEL", lock_key)
        return rc == 0

    def get_all_active_worktrees(self) -> list[WorktreeInfo]:
        """Get all active worktrees from Redis."""
        if not self._redis_available:
            return []

        rc, stdout, _ = self._redis_cli("KEYS", f"{WORKTREE_PREFIX}*")
        if rc != 0 or not stdout:
            return []

        worktrees = []
        for key in stdout.split("\n"):
            if key:
                rc2, data, _ = self._redis_cli("GET", key)
                if rc2 == 0 and data:
                    try:
                        info = WorktreeInfo.from_dict(json.loads(data))
                        if info.status == "active":
                            worktrees.append(info)
                    except (json.JSONDecodeError, KeyError):
                        continue

        return worktrees

    def check_worktree_health(self, worktree_path: str) -> dict[str, Any]:
        """Check health of a worktree.

        Returns:
            Dict with health status information
        """
        info = self._get_worktree_by_path(worktree_path)
        path = Path(worktree_path)

        health = {
            "path": worktree_path,
            "exists": path.exists(),
            "is_git_repo": False,
            "has_changes": False,
            "last_heartbeat": info.last_heartbeat if info else None,
            "status": "unknown",
        }

        if not path.exists():
            health["status"] = "missing"
            return health

        # Check if it's a valid git repo
        result = subprocess.run(  # nosec B607
            ["git", "-C", str(path), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
        health["is_git_repo"] = result.returncode == 0

        if not health["is_git_repo"]:
            health["status"] = "invalid"
            return health

        # Check for uncommitted changes
        result = subprocess.run(  # nosec B607
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        health["has_changes"] = bool(result.stdout.strip())

        # Check heartbeat staleness
        if info and info.last_heartbeat:
            try:
                last_beat = dt.datetime.fromisoformat(
                    info.last_heartbeat.replace("Z", "+00:00")
                )
                stale_threshold = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=30)
                health["is_stale"] = last_beat < stale_threshold
            except (ValueError, TypeError):
                health["is_stale"] = True
        else:
            health["is_stale"] = True

        if health["is_stale"]:
            health["status"] = "stale"
        elif health["has_changes"]:
            health["status"] = "dirty"
        else:
            health["status"] = "healthy"

        return health

    def cleanup_stale_worktrees(
        self, max_age_minutes: int = 60, dry_run: bool = False
    ) -> list[str]:
        """Clean up worktrees that haven't had a heartbeat recently.

        Args:
            max_age_minutes: Maximum age in minutes before considering stale
            dry_run: If True, only report what would be cleaned up

        Returns:
            List of cleaned up worktree paths
        """
        worktrees = self.get_all_active_worktrees()
        cleaned = []
        threshold = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=max_age_minutes)

        for info in worktrees:
            try:
                if info.last_heartbeat:
                    last_beat = dt.datetime.fromisoformat(
                        info.last_heartbeat.replace("Z", "+00:00")
                    )
                    if last_beat < threshold:
                        if not dry_run:
                            try:
                                self.cleanup_worktree(info.path)
                                cleaned.append(info.path)
                            except WorktreeError as e:
                                logger.warning(f"Failed to cleanup {info.path}: {e}")
                        else:
                            cleaned.append(info.path)
            except (ValueError, TypeError) as e:
                logger.warning(f"Error parsing heartbeat for {info.path}: {e}")

        return cleaned


def main():
    """CLI entry point for worktree manager."""
    import argparse

    parser = argparse.ArgumentParser(description="ChiseAI Worktree Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new worktree")
    create_parser.add_argument("--story-id", required=True, help="Story ID")
    create_parser.add_argument("--agent", required=True, help="Agent identifier")
    create_parser.add_argument("--branch", required=True, help="Branch name")
    create_parser.add_argument("--base", default="main", help="Base reference")
    create_parser.add_argument("--force", action="store_true", help="Force creation")

    # List command
    list_parser = subparsers.add_parser("list", help="List all worktrees")
    list_parser.add_argument("--story-id", help="Filter by story ID")
    list_parser.add_argument("--agent", help="Filter by agent")

    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up a worktree")
    cleanup_parser.add_argument("--path", required=True, help="Worktree path")
    cleanup_parser.add_argument(
        "--remove-branch", action="store_true", help="Also remove branch"
    )
    cleanup_parser.add_argument("--force", action="store_true", help="Force cleanup")

    # Health command
    health_parser = subparsers.add_parser("health", help="Check worktree health")
    health_parser.add_argument("--path", help="Specific worktree path")
    health_parser.add_argument(
        "--cleanup-stale", action="store_true", help="Cleanup stale worktrees"
    )
    health_parser.add_argument(
        "--max-age", type=int, default=60, help="Max age in minutes"
    )
    health_parser.add_argument("--dry-run", action="store_true", help="Dry run mode")

    # Heartbeat command
    heartbeat_parser = subparsers.add_parser(
        "heartbeat", help="Update worktree heartbeat"
    )
    heartbeat_parser.add_argument("--path", required=True, help="Worktree path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    manager = WorktreeManager()

    try:
        if args.command == "create":
            info = manager.create_worktree(
                story_id=args.story_id,
                agent=args.agent,
                branch=args.branch,
                base_ref=args.base,
                force=args.force,
            )
            print(json.dumps(info.to_dict(), indent=2))

        elif args.command == "list":
            if args.story_id and args.agent:
                worktrees = manager.get_agent_worktrees(args.story_id, args.agent)
            else:
                worktrees = manager.get_all_active_worktrees()

            for wt in worktrees:
                print(f"{wt.path}: {wt.branch} ({wt.story_id}/{wt.agent})")

        elif args.command == "cleanup":
            manager.cleanup_worktree(
                worktree_path=args.path,
                remove_branch=args.remove_branch,
                force=args.force,
            )
            print(f"Cleaned up worktree: {args.path}")

        elif args.command == "health":
            if args.cleanup_stale:
                cleaned = manager.cleanup_stale_worktrees(
                    max_age_minutes=args.max_age,
                    dry_run=args.dry_run,
                )
                action = "Would clean up" if args.dry_run else "Cleaned up"
                print(f"{action} {len(cleaned)} stale worktrees:")
                for path in cleaned:
                    print(f"  - {path}")
            elif args.path:
                health = manager.check_worktree_health(args.path)
                print(json.dumps(health, indent=2))
            else:
                # Check all worktrees
                worktrees = manager.get_all_active_worktrees()
                for wt in worktrees:
                    health = manager.check_worktree_health(wt.path)
                    status_icon = "✓" if health["status"] == "healthy" else "✗"
                    print(f"{status_icon} {wt.path}: {health['status']}")

        elif args.command == "heartbeat":
            if manager.update_heartbeat(args.path):
                print(f"Updated heartbeat for {args.path}")
            else:
                print(f"Failed to update heartbeat for {args.path}")
                return 1

        return 0

    except WorktreeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
