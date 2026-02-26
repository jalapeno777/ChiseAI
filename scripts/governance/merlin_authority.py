#!/usr/bin/env python3
"""
Merlin Authority Enforcement Module.

ST-AUTO-CONTROL-001: Merlin-only authority enforcement for EP-AUTO-GIT mutations.

This module enforces that only the Merlin agent can perform sensitive operations
on EP-AUTO-GIT epic resources, including:
- Merging to main
- Creating/updating PRs
- Writing to workflow status files

Usage:
    # Check if current process is Merlin
    python3 scripts/governance/merlin_authority.py check

    # Verify authority for an action
    python3 scripts/governance/merlin_authority.py verify --action status_write --epic EP-AUTO-GIT-001

    # Import in Python code
    from scripts.governance.merlin_authority import enforce_merlin_only, AuthorityViolation
    enforce_merlin_only(epic_id="EP-AUTO-GIT-001")

Exit Codes:
    0 - Authorized / Success
    1 - Not authorized
    2 - Error (Redis failure, invalid arguments, etc.)
"""

from __future__ import annotations

import argparse
import functools
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class AuthorityViolation(Exception):
    """Raised when non-Merlin attempts Merlin-only action.

    Attributes:
        action: The action that was attempted
        epic_id: The epic ID for which authority was checked
        agent: The agent that attempted the action
        message: Human-readable error message
    """

    def __init__(
        self,
        action: str,
        epic_id: str,
        agent: str | None = None,
        message: str | None = None,
    ):
        self.action = action
        self.epic_id = epic_id
        self.agent = agent or get_current_agent()
        self.message = message or (
            f"Authority violation: Agent '{self.agent}' attempted '{action}' "
            f"on epic '{epic_id}' which requires Merlin-only authority."
        )
        super().__init__(self.message)


class EpicNotProtected(Exception):
    """Raised when checking authority for unprotected epic.

    Attributes:
        epic_id: The epic ID that is not protected
        message: Human-readable error message
    """

    def __init__(self, epic_id: str, message: str | None = None):
        self.epic_id = epic_id
        self.message = (
            message or f"Epic '{epic_id}' is not protected by authority controls."
        )
        super().__init__(self.message)


class AuthorityCheckError(Exception):
    """Raised when authority check fails due to technical error.

    Attributes:
        reason: Technical reason for the failure
        message: Human-readable error message
    """

    def __init__(self, reason: str, message: str | None = None):
        self.reason = reason
        self.message = message or f"Authority check failed: {reason}"
        super().__init__(self.message)


class ActionType(Enum):
    """Types of actions that require authority checks."""

    MERGE = "merge"
    PR_UPDATE = "pr_update"
    STATUS_WRITE = "status_write"

    @classmethod
    def from_string(cls, value: str) -> ActionType:
        """Convert string to ActionType enum."""
        try:
            return cls(value)
        except ValueError:
            raise ValueError(
                f"Invalid action type: {value}. Valid types: {[a.value for a in cls]}"
            )


@dataclass
class AuthoritySettings:
    """Authority settings for an epic.

    Attributes:
        epic_id: The epic ID these settings apply to
        merge_authority: Authority required for merge operations
        pr_authority: Authority required for PR operations
        status_authority: Authority required for status write operations
        lock_timestamp: When these settings were locked
    """

    epic_id: str
    merge_authority: str
    pr_authority: str
    status_authority: str
    lock_timestamp: str | None = None

    @classmethod
    def from_redis_hash(cls, epic_id: str, data: dict[str, str]) -> AuthoritySettings:
        """Create AuthoritySettings from Redis hash data."""
        return cls(
            epic_id=epic_id,
            merge_authority=data.get("merge_authority", "any"),
            pr_authority=data.get("pr_authority", "any"),
            status_authority=data.get("status_authority", "any"),
            lock_timestamp=data.get("lock_timestamp"),
        )

    def is_merlin_only(self, action: ActionType) -> bool:
        """Check if an action requires Merlin-only authority."""
        authority_map = {
            ActionType.MERGE: self.merge_authority,
            ActionType.PR_UPDATE: self.pr_authority,
            ActionType.STATUS_WRITE: self.status_authority,
        }
        return authority_map.get(action) == "merlin-only"


# Cache for authority settings to avoid repeated Redis queries
_authority_cache: dict[str, tuple[AuthoritySettings, datetime]] = {}
_CACHE_TTL_SECONDS = 60  # Cache authority checks for 1 minute


def get_current_agent() -> str:
    """Get the current agent identity.

    Checks (in order):
    1. CHISE_AGENT environment variable
    2. Process name detection
    3. Default to "unknown"

    Returns:
        The current agent identifier
    """
    # Check environment variable first
    agent = os.environ.get("CHISE_AGENT")
    if agent:
        return agent.lower()

    # Try to detect from process arguments
    try:
        import psutil

        process = psutil.Process()
        cmdline = " ".join(process.cmdline()).lower()
        if "merlin" in cmdline:
            return "merlin"
        if "jarvis" in cmdline:
            return "jarvis"
        if "senior-dev" in cmdline or "senior_dev" in cmdline:
            return "senior-dev"
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Could not detect agent from process: {e}")

    # Default fallback
    return "unknown"


def is_merlin() -> bool:
    """Check if current process is running as Merlin agent.

    Returns:
        True if current agent is Merlin, False otherwise
    """
    agent = get_current_agent()
    return agent == "merlin"


def _get_redis_hash(name: str) -> dict[str, str]:
    """Get all fields from a Redis hash.

    This is a wrapper that handles Redis tool invocation.
    In production, this calls the redis_state_hgetall tool.

    Args:
        name: The Redis hash key

    Returns:
        Dictionary of field-value pairs

    Raises:
        AuthorityCheckError: If Redis query fails
    """
    try:
        # Try to import from redis_state module (if available)
        try:
            from redis_state import redis_state_hgetall

            result = redis_state_hgetall(name=name)
            if isinstance(result, dict):
                return result
            elif isinstance(result, str):
                import json

                return json.loads(result)
            return {}
        except ImportError:
            pass

        # Fallback: try subprocess to call the tool
        import json
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"""
import sys
sys.path.insert(0, '{Path(__file__).parent.parent.parent}')
try:
    from redis_state import redis_state_hgetall
    result = redis_state_hgetall(name='{name}')
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
""",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent.parent),
        )

        output = result.stdout.strip()
        if output:
            data = json.loads(output)
            if isinstance(data, dict) and "error" not in data:
                return data

        # If subprocess fails, return empty dict
        logger.warning(f"Could not query Redis for {name}, returning empty")
        return {}

    except Exception as e:
        logger.error(f"Redis query failed for {name}: {e}")
        raise AuthorityCheckError(f"Redis query failed: {e}")


def _get_authority_redis_key(epic_id: str) -> str:
    """Get the Redis key for epic authority settings.

    Args:
        epic_id: The epic ID (e.g., "EP-AUTO-GIT-001")

    Returns:
        The Redis hash key for authority settings
    """
    # Normalize epic ID to lowercase with hyphens
    # EP-AUTO-GIT-001 -> auto-git (strip number suffix and ep- prefix)
    normalized = epic_id.lower().replace("_", "-")
    # Remove 'ep-' prefix if present
    if normalized.startswith("ep-"):
        normalized = normalized[3:]  # Remove 'ep-' prefix
    # Strip numeric suffix (e.g., -001, -042) for key lookup
    # The actual Redis key is bmad:chiseai:ep:auto-git (without number)
    parts = normalized.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        normalized = parts[0]
    return f"bmad:chiseai:ep:{normalized.replace('-', ':')}"


def get_authority_settings(epic_id: str, use_cache: bool = True) -> AuthoritySettings:
    """Get authority settings for an epic from Redis.

    Args:
        epic_id: The epic ID (e.g., "EP-AUTO-GIT-001")
        use_cache: Whether to use cached results (default: True)

    Returns:
        AuthoritySettings for the epic

    Raises:
        AuthorityCheckError: If Redis query fails
    """
    cache_key = epic_id.lower()

    # Check cache
    if use_cache and cache_key in _authority_cache:
        settings, cached_at = _authority_cache[cache_key]
        if datetime.now() - cached_at < timedelta(seconds=_CACHE_TTL_SECONDS):
            logger.debug(f"Using cached authority settings for {epic_id}")
            return settings

    # Query Redis
    redis_key = _get_authority_redis_key(epic_id)
    logger.debug(f"Querying Redis for authority settings: {redis_key}")

    try:
        data = _get_redis_hash(redis_key)
    except AuthorityCheckError:
        # If Redis fails, check if we have stale cache
        if cache_key in _authority_cache:
            logger.warning(f"Redis failed, using stale cache for {epic_id}")
            return _authority_cache[cache_key][0]
        raise

    settings = AuthoritySettings.from_redis_hash(epic_id, data)

    # Update cache
    _authority_cache[cache_key] = (settings, datetime.now())

    return settings


def check_ep_auto_git_authority(action: str) -> bool:
    """Check if action is authorized for EP-AUTO-GIT.

    Args:
        action: One of 'merge', 'pr_update', 'status_write'

    Returns:
        True if authorized, False otherwise

    Raises:
        ValueError: If action is not a valid action type
        AuthorityCheckError: If authority check fails technically
    """
    action_type = ActionType.from_string(action)
    return check_epic_authority("EP-AUTO-GIT-001", action_type)


def check_epic_authority(epic_id: str, action: ActionType) -> bool:
    """Check if current agent is authorized for an action on an epic.

    Args:
        epic_id: The epic ID (e.g., "EP-AUTO-GIT-001")
        action: The action type to check

    Returns:
        True if authorized, False otherwise

    Raises:
        AuthorityCheckError: If authority check fails technically
    """
    try:
        settings = get_authority_settings(epic_id)
    except AuthorityCheckError:
        # If we can't check authority, deny by default (fail secure)
        logger.error(
            f"Could not retrieve authority settings for {epic_id}, denying access"
        )
        return False

    # If epic is not protected (no authority settings), allow
    if not settings.lock_timestamp:
        logger.debug(f"Epic {epic_id} has no authority settings, allowing action")
        return True

    # Check if action requires Merlin-only
    if not settings.is_merlin_only(action):
        logger.debug(f"Action {action.value} on {epic_id} does not require Merlin")
        return True

    # Check if current agent is Merlin
    if is_merlin():
        logger.debug(f"Merlin authorized for {action.value} on {epic_id}")
        return True

    logger.warning(f"Non-Merlin agent denied for {action.value} on {epic_id}")
    return False


def enforce_merlin_only(
    epic_id: str = "EP-AUTO-GIT-001", action: str | None = None
) -> None:
    """Enforce Merlin-only authority for an epic.

    This function should be called before any sensitive operation on
    protected epics. It will raise an exception if the current agent
    is not Merlin and the action requires Merlin-only authority.

    Args:
        epic_id: The epic ID to check (default: EP-AUTO-GIT-001)
        action: Optional action type for more specific error messages

    Raises:
        AuthorityViolation: If not running as Merlin and action requires it
        EpicNotProtected: If epic is not configured for protection
        AuthorityCheckError: If authority check fails technically
    """
    try:
        settings = get_authority_settings(epic_id)
    except AuthorityCheckError as e:
        raise AuthorityCheckError(
            f"Could not verify authority for {epic_id}",
            message=f"Authority verification failed: {e.reason}",
        )

    # Check if epic is protected
    if not settings.lock_timestamp:
        raise EpicNotProtected(epic_id)

    # Check if current agent is Merlin
    if not is_merlin():
        raise AuthorityViolation(
            action=action or "unspecified",
            epic_id=epic_id,
            message=(
                f"Authority violation: Only Merlin can perform this operation on '{epic_id}'. "
                f"Current agent: '{get_current_agent()}'. "
                f"This epic requires Merlin-only authority for: "
                f"merge={settings.merge_authority}, "
                f"pr={settings.pr_authority}, "
                f"status={settings.status_authority}"
            ),
        )

    logger.debug(f"Merlin authority confirmed for {epic_id}")


def require_merlin(func: Callable) -> Callable:
    """Decorator to require Merlin authority for a function.

    Usage:
        @require_merlin
        def merge_to_main():
            ...

        @require_merlin
        def update_status(epic_id: str):
            ...
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Try to extract epic_id from kwargs or args
        epic_id = kwargs.get("epic_id", "EP-AUTO-GIT-001")
        enforce_merlin_only(epic_id=epic_id, action=func.__name__)
        return func(*args, **kwargs)

    return wrapper


def clear_authority_cache() -> None:
    """Clear the authority settings cache.

    Useful for testing or when authority settings have been updated.
    """
    global _authority_cache
    _authority_cache = {}
    logger.debug("Authority cache cleared")


# CLI Interface


def cli_check(args: argparse.Namespace | None = None) -> int:
    """CLI handler for 'check' command.

    Args:
        args: Parsed command line arguments (optional)

    Returns:
        0 if current agent is Merlin, 1 otherwise
    """
    agent = get_current_agent()
    is_merlin_agent = is_merlin()

    result = {
        "agent": agent,
        "is_merlin": is_merlin_agent,
        "authorized": is_merlin_agent,
    }

    print(result)
    return 0 if is_merlin_agent else 1


def cli_verify(args: argparse.Namespace) -> int:
    """CLI handler for 'verify' command.

    Args:
        args: Parsed command line arguments

    Returns:
        0 if authorized, 1 if not authorized, 2 on error
    """
    epic_id = args.epic
    action = args.action

    try:
        authorized = check_ep_auto_git_authority(action)

        result = {
            "epic": epic_id,
            "action": action,
            "agent": get_current_agent(),
            "authorized": authorized,
        }

        print(result)
        return 0 if authorized else 1

    except ValueError as e:
        print(f"Error: {e}")
        return 2
    except AuthorityCheckError as e:
        print(f"Error checking authority: {e.message}")
        return 2


def cli_enforce(args: argparse.Namespace) -> int:
    """CLI handler for 'enforce' command.

    Args:
        args: Parsed command line arguments

    Returns:
        0 if authorized, 1 if not authorized, 2 on error
    """
    epic_id = args.epic
    action = args.action

    try:
        enforce_merlin_only(epic_id=epic_id, action=action)
        print(f"✓ Authority verified: Merlin confirmed for {action} on {epic_id}")
        return 0

    except AuthorityViolation as e:
        print(f"✗ Authority violation: {e.message}")
        return 1
    except EpicNotProtected as e:
        print(f"⚠ Epic not protected: {e.message}")
        return 1
    except AuthorityCheckError as e:
        print(f"✗ Authority check failed: {e.message}")
        return 2


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Merlin Authority Enforcement (ST-AUTO-CONTROL-001)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check if current process is Merlin
  python3 scripts/governance/merlin_authority.py check

  # Verify authority for an action
  python3 scripts/governance/merlin_authority.py verify --action status_write --epic EP-AUTO-GIT-001

  # Enforce authority (raises error if not Merlin)
  python3 scripts/governance/merlin_authority.py enforce --action merge --epic EP-AUTO-GIT-001

Exit Codes:
  0 - Authorized / Success
  1 - Not authorized
  2 - Error (Redis failure, invalid arguments, etc.)
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # check command
    check_parser = subparsers.add_parser(
        "check",
        help="Check if current process is Merlin",
    )
    check_parser.set_defaults(func=cli_check)

    # verify command
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify authority for an action",
    )
    verify_parser.add_argument(
        "--action",
        required=True,
        choices=[a.value for a in ActionType],
        help="Action to verify",
    )
    verify_parser.add_argument(
        "--epic",
        default="EP-AUTO-GIT-001",
        help="Epic ID (default: EP-AUTO-GIT-001)",
    )
    verify_parser.set_defaults(func=cli_verify)

    # enforce command
    enforce_parser = subparsers.add_parser(
        "enforce",
        help="Enforce Merlin authority (fails if not Merlin)",
    )
    enforce_parser.add_argument(
        "--action",
        default="unspecified",
        help="Action being performed",
    )
    enforce_parser.add_argument(
        "--epic",
        default="EP-AUTO-GIT-001",
        help="Epic ID (default: EP-AUTO-GIT-001)",
    )
    enforce_parser.set_defaults(func=cli_enforce)

    # Global options
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.command:
        parser.print_help()
        return 2

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
