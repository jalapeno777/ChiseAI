#!/usr/bin/env python3
"""
Merlin Authority Enforcement Module

This module provides authority enforcement for the EP-AUTO-GIT epic, ensuring
that only the 'merlin' agent can perform critical operations like merging to main,
creating/updating PRs, and writing to the workflow status file.

The module implements a fail-secure design: when Redis is unavailable, access
is denied by default.

Usage:
    # As a decorator
    from merlin_authority import require_merlin

    @require_merlin(action="merge")
    def merge_to_main():
        pass

    # As a function
    from merlin_authority import check_ep_auto_git_authority, is_merlin

    if is_merlin():
        # Perform merlin-only operation
        pass

    # Check specific authority
    result = check_ep_auto_git_authority("merge", "EP-AUTO-GIT-001")
"""

from __future__ import annotations

import argparse
import functools
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])

# Constants
REDIS_KEY_EP_AUTO_GIT = "bmad:chiseai:ep:auto-git"
MERLIN_AGENT_NAME = "merlin"
CACHE_TTL_SECONDS = 60


class AuthorityAction(Enum):
    """Enumeration of authority-controlled actions."""

    MERGE = "merge"
    PR = "pr"
    STATUS = "status"


class AuthoritySetting(Enum):
    """Enumeration of authority settings."""

    MERLIN_ONLY = "merlin-only"
    OPEN = "open"
    RESTRICTED = "restricted"


class AuthorityViolation(Exception):
    """
    Exception raised when an authority violation is detected.

    This exception is raised when a non-authorized agent attempts to perform
    an operation that requires merlin authority.

    Attributes:
        action: The action that was attempted
        agent: The agent that attempted the action
        epic_id: The epic ID involved (if applicable)
        message: Human-readable error message
    """

    def __init__(
        self,
        action: str,
        agent: str,
        epic_id: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        self.action = action
        self.agent = agent
        self.epic_id = epic_id

        if message is None:
            epic_str = f" for epic {epic_id}" if epic_id else ""
            message = (
                f"Authority violation: Agent '{agent}' attempted '{action}'"
                f"{epic_str} but lacks required authority. "
                f"Only '{MERLIN_AGENT_NAME}' is authorized."
            )

        super().__init__(message)


class EpicNotProtected(Exception):
    """
    Exception raised when checking authority for an unprotected epic.

    This exception indicates that the requested epic does not have
    authority protection configured in Redis.

    Attributes:
        epic_id: The epic ID that is not protected
        message: Human-readable error message
    """

    def __init__(
        self,
        epic_id: str,
        message: Optional[str] = None,
    ) -> None:
        self.epic_id = epic_id

        if message is None:
            message = (
                f"Epic '{epic_id}' is not configured with authority protection. "
                f"No authority settings found in Redis."
            )

        super().__init__(message)


class AuthorityCheckError(Exception):
    """
    Exception raised when authority check fails due to technical issues.

    This exception is raised when the authority check cannot be completed
    due to Redis unavailability, network issues, or other technical problems.

    Attributes:
        reason: The reason for the check failure
        original_error: The original exception that caused the failure
        message: Human-readable error message
    """

    def __init__(
        self,
        reason: str,
        original_error: Optional[Exception] = None,
        message: Optional[str] = None,
    ) -> None:
        self.reason = reason
        self.original_error = original_error

        if message is None:
            message = f"Authority check failed: {reason}"
            if original_error:
                message += f" (caused by: {type(original_error).__name__})"

        super().__init__(message)


@dataclass(frozen=True)
class AuthorityCheckResult:
    """
    Result of an authority check.

    Attributes:
        authorized: Whether the action is authorized
        action: The action that was checked
        agent: The agent requesting the action
        epic_id: The epic ID involved (if applicable)
        setting: The authority setting that was applied
        reason: Human-readable explanation of the result
    """

    authorized: bool
    action: str
    agent: str
    epic_id: Optional[str]
    setting: str
    reason: str


# Simple in-memory cache for authority settings
_authority_cache: dict[str, tuple[Any, float]] = {}


def _get_cached(key: str) -> Optional[Any]:
    """Get a cached value if it hasn't expired."""
    if key in _authority_cache:
        value, timestamp = _authority_cache[key]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            return value
        else:
            del _authority_cache[key]
    return None


def _set_cached(key: str, value: Any) -> None:
    """Cache a value with current timestamp."""
    _authority_cache[key] = (value, time.time())


def _clear_cache() -> None:
    """Clear the authority cache. Used primarily for testing."""
    _authority_cache.clear()


def _detect_agent_from_environment() -> str:
    """
    Detect the current agent from environment variables.

    Checks the AGENT_NAME environment variable first, then falls back
    to detecting from process information.

    Returns:
        The detected agent name, or "unknown" if detection fails.
    """
    # Check environment variable first
    agent = os.environ.get("AGENT_NAME", "").strip().lower()
    if agent:
        return agent

    # Try to detect from process
    return _detect_agent_from_process()


def _detect_agent_from_process() -> str:
    """
    Detect the current agent by examining process information.

    This function attempts to identify the agent by looking at:
    - Parent process name
    - Command line arguments
    - Process environment

    Returns:
        The detected agent name, or "unknown" if detection fails.
    """
    try:
        # Check if we're running in a known agent context
        # This is a simplified detection - in production, this would be
        # more sophisticated

        # Check for common agent indicators in environment
        for key in ["OPENCODE_AGENT", "AGENT_ROLE", "WORKER_TYPE"]:
            value = os.environ.get(key, "").strip().lower()
            if value:
                if "merlin" in value:
                    return MERLIN_AGENT_NAME
                return value

        # Check parent process if available
        try:
            import psutil

            parent = psutil.Process().parent()
            if parent:
                parent_name = parent.name().lower()
                cmdline = " ".join(parent.cmdline()).lower()

                # Look for agent indicators in parent process
                if "merlin" in parent_name or "merlin" in cmdline:
                    return MERLIN_AGENT_NAME
        except ImportError:
            pass  # psutil not available
        except Exception:
            pass  # Process detection failed

        return "unknown"
    except Exception as e:
        logger.debug(f"Agent detection from process failed: {e}")
        return "unknown"


def is_merlin(agent: Optional[str] = None) -> bool:
    """
    Check if the specified (or current) agent is merlin.

    Args:
        agent: The agent name to check. If None, detects from environment.

    Returns:
        True if the agent is merlin, False otherwise.

    Examples:
        >>> is_merlin("merlin")
        True
        >>> is_merlin("jarvis")
        False
        >>> is_merlin()  # Checks current environment
        ...  # Returns True if AGENT_NAME=merlin
    """
    if agent is None:
        agent = _detect_agent_from_environment()

    return agent.lower() == MERLIN_AGENT_NAME


def _get_redis_authority_settings(epic_id: str) -> dict[str, str]:
    """
    Retrieve authority settings from Redis for the given epic.

    Args:
        epic_id: The epic ID to retrieve settings for.

    Returns:
        Dictionary of authority settings.

    Raises:
        AuthorityCheckError: If Redis is unavailable or query fails.
    """
    cache_key = f"authority_settings:{epic_id}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        # Import here to avoid dependency issues if Redis is not available
        from redis_state import hgetall

        # Map epic_id to Redis key
        if epic_id == "EP-AUTO-GIT-001" or epic_id.startswith("EP-AUTO-GIT"):
            redis_key = REDIS_KEY_EP_AUTO_GIT
        else:
            # For other epics, use a pattern-based key
            redis_key = f"bmad:chiseai:ep:{epic_id.lower().replace('_', '-')}"

        settings = hgetall(redis_key)

        if not settings:
            raise EpicNotProtected(epic_id)

        # Convert to string dictionary
        settings_dict = {k: str(v) for k, v in settings.items()}

        _set_cached(cache_key, settings_dict)
        return settings_dict

    except EpicNotProtected:
        raise
    except ImportError as e:
        raise AuthorityCheckError(
            "Redis module not available",
            original_error=e,
        )
    except Exception as e:
        raise AuthorityCheckError(
            f"Failed to query Redis: {e}",
            original_error=e,
        )


def _parse_authority_setting(
    settings: dict[str, str],
    action: str,
) -> AuthoritySetting:
    """
    Parse the authority setting for a specific action.

    Args:
        settings: Dictionary of authority settings from Redis.
        action: The action to check (merge, pr, status).

    Returns:
        The authority setting for the action.
    """
    # Map action to setting key
    action_key_map = {
        "merge": "merge_authority",
        "pr": "pr_authority",
        "status": "status_authority",
    }

    key = action_key_map.get(action, f"{action}_authority")
    value = settings.get(key, "").lower().strip()

    if value == AuthoritySetting.MERLIN_ONLY.value:
        return AuthoritySetting.MERLIN_ONLY
    elif value == AuthoritySetting.OPEN.value:
        return AuthoritySetting.OPEN
    else:
        return AuthoritySetting.RESTRICTED


def check_epic_authority(
    action: str,
    epic_id: str,
    agent: Optional[str] = None,
) -> AuthorityCheckResult:
    """
    Check if the agent has authority to perform an action on an epic.

    This function queries Redis for the epic's authority settings and
    determines if the specified agent is authorized to perform the action.

    Args:
        action: The action to check (merge, pr, status).
        epic_id: The epic ID to check authority for.
        agent: The agent name. If None, detects from environment.

    Returns:
        AuthorityCheckResult indicating whether the action is authorized.

    Raises:
        EpicNotProtected: If the epic has no authority protection configured.
        AuthorityCheckError: If the authority check fails due to technical issues.

    Examples:
        >>> result = check_epic_authority("merge", "EP-AUTO-GIT-001", "merlin")
        >>> result.authorized
        True
        >>> result = check_epic_authority("merge", "EP-AUTO-GIT-001", "jarvis")
        >>> result.authorized
        False
    """
    if agent is None:
        agent = _detect_agent_from_environment()

    try:
        settings = _get_redis_authority_settings(epic_id)
        setting = _parse_authority_setting(settings, action)

        if setting == AuthoritySetting.MERLIN_ONLY:
            authorized = is_merlin(agent)
            reason = (
                f"Action '{action}' requires merlin authority. "
                f"Agent '{agent}' is {'authorized' if authorized else 'not authorized'}."
            )
        elif setting == AuthoritySetting.OPEN:
            authorized = True
            reason = f"Action '{action}' is open to all agents."
        else:
            authorized = False
            reason = f"Action '{action}' is restricted. Agent '{agent}' denied."

        return AuthorityCheckResult(
            authorized=authorized,
            action=action,
            agent=agent,
            epic_id=epic_id,
            setting=setting.value,
            reason=reason,
        )

    except EpicNotProtected:
        raise
    except AuthorityCheckError:
        raise
    except Exception as e:
        raise AuthorityCheckError(
            f"Unexpected error during authority check: {e}",
            original_error=e,
        )


def check_ep_auto_git_authority(
    action: str,
    agent: Optional[str] = None,
) -> AuthorityCheckResult:
    """
    Check authority for EP-AUTO-GIT epic operations.

    This is a convenience function that checks authority for the EP-AUTO-GIT-001
    epic, which is the primary epic protected by this module.

    Args:
        action: The action to check (merge, pr, status).
        agent: The agent name. If None, detects from environment.

    Returns:
        AuthorityCheckResult indicating whether the action is authorized.

    Raises:
        EpicNotProtected: If EP-AUTO-GIT has no authority protection.
        AuthorityCheckError: If the authority check fails.

    Examples:
        >>> result = check_ep_auto_git_authority("merge")
        >>> if result.authorized:
        ...     perform_merge()
        ... else:
        ...     raise AuthorityViolation("merge", result.agent)
    """
    return check_epic_authority(action, "EP-AUTO-GIT-001", agent)


def enforce_merlin_only(
    action: str,
    epic_id: str = "EP-AUTO-GIT-001",
    agent: Optional[str] = None,
) -> AuthorityCheckResult:
    """
    Enforce merlin-only authority for an action.

    This function checks authority and raises AuthorityViolation if the
    agent is not authorized. Use this when you want to halt execution
    on authority failure rather than returning a result.

    Args:
        action: The action to enforce authority for.
        epic_id: The epic ID to check. Defaults to EP-AUTO-GIT-001.
        agent: The agent name. If None, detects from environment.

    Returns:
        AuthorityCheckResult if the agent is authorized.

    Raises:
        AuthorityViolation: If the agent is not authorized.
        EpicNotProtected: If the epic has no authority protection.
        AuthorityCheckError: If the authority check fails.

    Examples:
        >>> enforce_merlin_only("merge")  # Raises if not merlin
        AuthorityCheckResult(authorized=True, ...)

        >>> enforce_merlin_only("merge", agent="jarvis")
        Traceback (most recent call last):
            ...
        AuthorityViolation: Authority violation: Agent 'jarvis' attempted 'merge'...
    """
    result = check_epic_authority(action, epic_id, agent)

    if not result.authorized:
        raise AuthorityViolation(
            action=action,
            agent=result.agent,
            epic_id=epic_id,
        )

    return result


def require_merlin(
    action: str = "execute",
    epic_id: str = "EP-AUTO-GIT-001",
) -> Callable[[F], F]:
    """
    Decorator that enforces merlin-only authority for a function.

    This decorator wraps a function and checks merlin authority before
    allowing execution. If the current agent is not merlin, an
    AuthorityViolation is raised.

    Args:
        action: The action name for error messages. Defaults to "execute".
        epic_id: The epic ID to check. Defaults to EP-AUTO-GIT-001.

    Returns:
        A decorator that enforces merlin authority.

    Raises:
        AuthorityViolation: If the calling agent is not merlin.

    Examples:
        >>> @require_merlin(action="merge")
        ... def merge_to_main(branch_name: str) -> None:
        ...     print(f"Merging {branch_name}")
        ...
        >>> merge_to_main("feature/test")  # Only works if agent is merlin

        >>> @require_merlin(action="status_write", epic_id="EP-AUTO-GIT-001")
        ... def update_workflow_status(status: str) -> None:
        ...     print(f"Updating status to {status}")
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            enforce_merlin_only(action, epic_id)
            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def verify_git_sha(sha: str, repo_path: Optional[str] = None) -> bool:
    """
    Verify that a git SHA exists in the repository history.

    Args:
        sha: The git SHA to verify.
        repo_path: Path to the git repository. If None, uses current directory.

    Returns:
        True if the SHA exists, False otherwise.

    Examples:
        >>> verify_git_sha("abc123")
        True
        >>> verify_git_sha("0000000")
        False
    """
    try:
        cmd = ["git", "cat-file", "-t", sha]
        if repo_path:
            cmd = ["git", "-C", repo_path, "cat-file", "-t", sha]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return result.returncode == 0 and "commit" in result.stdout

    except subprocess.TimeoutExpired:
        logger.warning(f"Git SHA verification timed out for {sha}")
        return False
    except Exception as e:
        logger.warning(f"Git SHA verification failed for {sha}: {e}")
        return False


def cli_check(args: argparse.Namespace) -> int:
    """
    CLI handler for the 'check' subcommand.

    Checks authority for the specified action and prints the result.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for authorized, 1 for denied, 2 for error).
    """
    try:
        result = check_ep_auto_git_authority(args.action, args.agent)

        print(f"Authority Check Result:")
        print(f"  Action: {result.action}")
        print(f"  Agent: {result.agent}")
        print(f"  Epic: {result.epic_id}")
        print(f"  Setting: {result.setting}")
        print(f"  Authorized: {result.authorized}")
        print(f"  Reason: {result.reason}")

        return 0 if result.authorized else 1

    except EpicNotProtected as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except AuthorityCheckError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


def cli_verify(args: argparse.Namespace) -> int:
    """
    CLI handler for the 'verify' subcommand.

    Verifies a git SHA and checks authority.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    # First verify the SHA
    sha_valid = verify_git_sha(args.sha, args.repo_path)

    if not sha_valid:
        print(f"Error: Git SHA '{args.sha}' not found in repository", file=sys.stderr)
        return 1

    print(f"Git SHA '{args.sha}' verified in repository")

    # Then check authority
    try:
        result = check_ep_auto_git_authority(args.action, args.agent)

        print(f"\nAuthority Check:")
        print(f"  Agent: {result.agent}")
        print(f"  Action: {result.action}")
        print(f"  Authorized: {result.authorized}")

        if result.authorized:
            print(f"\nVerification PASSED: SHA valid and agent authorized")
            return 0
        else:
            print(f"\nVerification FAILED: Agent not authorized", file=sys.stderr)
            return 1

    except (EpicNotProtected, AuthorityCheckError) as e:
        print(f"\nAuthority check failed: {e}", file=sys.stderr)
        return 1


def cli_enforce(args: argparse.Namespace) -> int:
    """
    CLI handler for the 'enforce' subcommand.

    Enforces merlin-only authority, exiting with error if not authorized.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for authorized, 1 for denied).
    """
    try:
        result = enforce_merlin_only(args.action, args.epic_id, args.agent)

        print(f"Authority ENFORCED:")
        print(f"  Action: {result.action}")
        print(f"  Agent: {result.agent}")
        print(f"  Status: AUTHORIZED")

        return 0

    except AuthorityViolation as e:
        print(f"Authority DENIED: {e}", file=sys.stderr)
        return 1
    except EpicNotProtected as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        return 1
    except AuthorityCheckError as e:
        print(f"System Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """
    Main entry point for the CLI.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        prog="merlin_authority",
        description="Merlin authority enforcement for EP-AUTO-GIT",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 'check' subcommand
    check_parser = subparsers.add_parser(
        "check",
        help="Check authority for an action",
    )
    check_parser.add_argument(
        "--action",
        default="merge",
        choices=["merge", "pr", "status"],
        help="Action to check authority for (default: merge)",
    )
    check_parser.add_argument(
        "--agent",
        default=None,
        help="Agent name (default: auto-detect)",
    )
    check_parser.set_defaults(func=cli_check)

    # 'verify' subcommand
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify a git SHA and check authority",
    )
    verify_parser.add_argument(
        "sha",
        help="Git SHA to verify",
    )
    verify_parser.add_argument(
        "--action",
        default="merge",
        choices=["merge", "pr", "status"],
        help="Action to check authority for (default: merge)",
    )
    verify_parser.add_argument(
        "--agent",
        default=None,
        help="Agent name (default: auto-detect)",
    )
    verify_parser.add_argument(
        "--repo-path",
        default=None,
        help="Path to git repository (default: current directory)",
    )
    verify_parser.set_defaults(func=cli_verify)

    # 'enforce' subcommand
    enforce_parser = subparsers.add_parser(
        "enforce",
        help="Enforce merlin-only authority (exits with error if denied)",
    )
    enforce_parser.add_argument(
        "--action",
        default="merge",
        choices=["merge", "pr", "status"],
        help="Action to enforce (default: merge)",
    )
    enforce_parser.add_argument(
        "--agent",
        default=None,
        help="Agent name (default: auto-detect)",
    )
    enforce_parser.add_argument(
        "--epic-id",
        default="EP-AUTO-GIT-001",
        help="Epic ID to check (default: EP-AUTO-GIT-001)",
    )
    enforce_parser.set_defaults(func=cli_enforce)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
