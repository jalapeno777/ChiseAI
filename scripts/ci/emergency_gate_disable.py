#!/usr/bin/env python3
"""Emergency gate disable/restore mechanism for blocking CI gates.

This script provides an emergency rollback mechanism to disable all blocking
gates in the CI pipeline. Actions are logged to Redis for audit purposes.

Usage:
    python emergency_gate_disable.py --disable --reason "Emergency: critical bug in production"
    python emergency_gate_disable.py --restore --reason "Gates re-enabled after fix deployed"
    python emergency_gate_disable.py --status
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Redis key for gate disable state
GATE_DISABLE_KEY = "bmad:chiseai:ci:gates:disabled"
AUDIT_LOG_KEY = "bmad:chiseai:ci:gates:audit_log"


def _redis_candidates() -> list[tuple[str, int, int]]:
    """Get Redis connection candidates from environment."""
    host = (
        os.getenv("CHISE_REDIS_HOST")
        or os.getenv("REDIS_HOST")
        or "host.docker.internal"
    )
    port = int(os.getenv("CHISE_REDIS_PORT") or os.getenv("REDIS_PORT") or "6380")
    db = int(os.getenv("CHISE_REDIS_DB") or os.getenv("REDIS_DB") or "0")
    candidates = [(host, port, db)]
    if host != "localhost":
        candidates.append(("localhost", port, db))
    return candidates


def _redis_cli(
    host: str, port: int, db: int, *args: str
) -> subprocess.CompletedProcess[str]:
    """Execute redis-cli command."""
    return subprocess.run(  # nosec B607
        ["redis-cli", "-h", host, "-p", str(port), "-n", str(db), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _get_redis_connection() -> tuple[str, int, int]:
    """Get working Redis connection parameters."""
    for host, port, db in _redis_candidates():
        proc = _redis_cli(host, port, db, "PING")
        if proc.returncode == 0 and proc.stdout.strip() == "PONG":
            return host, port, db
    print("ERROR: Could not connect to Redis", file=sys.stderr)
    sys.exit(1)


def _log_action(action: str, reason: str, user: str | None = None) -> None:
    """Log an action to the audit log in Redis."""
    host, port, db = _get_redis_connection()
    timestamp = datetime.now(timezone.utc).isoformat()
    user = user or os.environ.get("USER", "unknown")

    log_entry = {
        "timestamp": timestamp,
        "action": action,
        "reason": reason,
        "user": user,
    }

    # Push to list
    proc = _redis_cli(host, port, db, "RPUSH", AUDIT_LOG_KEY, json.dumps(log_entry))
    if proc.returncode == 0:
        # Set TTL (90 days)
        _redis_cli(host, port, db, "EXPIRE", AUDIT_LOG_KEY, str(90 * 24 * 60 * 60))
        print(f"AUDIT: Logged {action} action at {timestamp}")
    else:
        print(f"WARNING: Failed to log to audit log: {proc.stderr}", file=sys.stderr)


def disable_gates(reason: str, user: str | None = None) -> int:
    """Disable all blocking gates by setting Redis key.

    Args:
        reason: The reason for disabling gates (required for audit)
        user: The user performing the action

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    host, port, db = _get_redis_connection()
    timestamp = datetime.now(timezone.utc).isoformat()
    user = user or os.environ.get("USER", "unknown")

    # Set the disable key with metadata
    disable_data = {
        "disabled_at": timestamp,
        "disabled_by": user,
        "reason": reason,
    }

    proc = _redis_cli(host, port, db, "SET", GATE_DISABLE_KEY, json.dumps(disable_data))
    if proc.returncode != 0:
        print(f"ERROR: Failed to disable gates: {proc.stderr}", file=sys.stderr)
        return 1

    # Set TTL (7 days max - gates should not be disabled indefinitely)
    _redis_cli(host, port, db, "EXPIRE", GATE_DISABLE_KEY, str(7 * 24 * 60 * 60))

    print(f"SUCCESS: All blocking gates DISABLED at {timestamp}")
    print(f"  Reason: {reason}")
    print(f"  Disabled by: {user}")
    print(f"  Key: {GATE_DISABLE_KEY}")
    print(f"  Auto-expires: 7 days")

    _log_action("disable", reason, user)
    return 0


def restore_gates(reason: str, user: str | None = None) -> int:
    """Restore (re-enable) all blocking gates by deleting Redis key.

    Args:
        reason: The reason for restoring gates (required for audit)
        user: The user performing the action

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    host, port, db = _get_redis_connection()
    user = user or os.environ.get("USER", "unknown")

    # Check if key exists first
    exists_proc = _redis_cli(host, port, db, "EXISTS", GATE_DISABLE_KEY)
    exists = exists_proc.stdout.strip() == "1"

    if not exists:
        print("WARNING: Gates were not disabled (key does not exist)")
        print("No action taken.")
        return 0

    # Get previous disable info for logging
    get_proc = _redis_cli(host, port, db, "GET", GATE_DISABLE_KEY)
    try:
        prev_data = json.loads(get_proc.stdout.strip() or "{}")
        disabled_at = prev_data.get("disabled_at", "unknown")
        disabled_by = prev_data.get("disabled_by", "unknown")
        disabled_reason = prev_data.get("reason", "unknown")
    except Exception:
        disabled_at = disabled_by = disabled_reason = "unknown"

    # Delete the disable key
    del_proc = _redis_cli(host, port, db, "DEL", GATE_DISABLE_KEY)
    if del_proc.returncode != 0:
        print(f"ERROR: Failed to restore gates: {del_proc.stderr}", file=sys.stderr)
        return 1

    timestamp = datetime.now(timezone.utc).isoformat()

    print(f"SUCCESS: All blocking gates RESTORED at {timestamp}")
    print(f"  Reason: {reason}")
    print(f"  Restored by: {user}")
    print(f"  Previously disabled: {disabled_at}")
    print(f"  Previous disable reason: {disabled_reason}")

    _log_action("restore", reason, user)
    return 0


def check_status() -> int:
    """Check current gate disable status.

    Returns:
        Exit code (0 if gates are enabled, 1 if disabled)
    """
    host, port, db = _get_redis_connection()

    exists_proc = _redis_cli(host, port, db, "EXISTS", GATE_DISABLE_KEY)
    exists = exists_proc.stdout.strip() == "1"

    if exists:
        get_proc = _redis_cli(host, port, db, "GET", GATE_DISABLE_KEY)
        try:
            data = json.loads(get_proc.stdout.strip() or "{}")
        except Exception:
            data = {}

        disabled_at = data.get("disabled_at", "unknown")
        disabled_by = data.get("disabled_by", "unknown")
        reason = data.get("reason", "unknown")

        ttl_proc = _redis_cli(host, port, db, "TTL", GATE_DISABLE_KEY)
        try:
            ttl = int(ttl_proc.stdout.strip())
        except Exception:
            ttl = -1

        print("STATUS: BLOCKING GATES ARE DISABLED")
        print(f"  Disabled at: {disabled_at}")
        print(f"  Disabled by: {disabled_by}")
        print(f"  Reason: {reason}")
        if ttl > 0:
            print(f"  Auto-expires in: {ttl} seconds ({ttl // 3600} hours)")
        return 1
    else:
        print("STATUS: All blocking gates are ENABLED")
        return 0


def show_audit_log(limit: int = 20) -> int:
    """Show recent audit log entries.

    Args:
        limit: Maximum number of entries to show

    Returns:
        Exit code (0 for success)
    """
    host, port, db = _get_redis_connection()

    # Get list length first
    len_proc = _redis_cli(host, port, db, "LLEN", AUDIT_LOG_KEY)
    try:
        total_len = int(len_proc.stdout.strip())
    except Exception:
        total_len = 0

    if total_len == 0:
        print("No audit log entries found.")
        return 0

    # Calculate range (get last 'limit' entries)
    start = max(0, total_len - limit)

    range_proc = _redis_cli(
        host, port, db, "LRANGE", AUDIT_LOG_KEY, str(start), str(total_len - 1)
    )
    entries = range_proc.stdout.strip().split("\n") if range_proc.stdout.strip() else []

    print(f"Recent audit log entries (last {len(entries)} of {total_len}):")
    print("-" * 80)
    for entry_json in entries:
        try:
            entry = json.loads(entry_json)
            print(
                f"[{entry.get('timestamp', 'unknown')}] {entry.get('action', 'unknown').upper()}"
            )
            print(f"  User: {entry.get('user', 'unknown')}")
            print(f"  Reason: {entry.get('reason', 'unknown')}")
            print()
        except Exception as e:
            print(f"  [Malformed entry: {e}]")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emergency gate disable/restore mechanism",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --disable --reason "Critical bug in production"
  %(prog)s --restore --reason "Bug fix deployed, gates re-enabled"
  %(prog)s --status
  %(prog)s --audit-log
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--disable",
        action="store_true",
        help="Disable all blocking gates",
    )
    group.add_argument(
        "--restore",
        action="store_true",
        help="Restore (re-enable) all blocking gates",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="Check current gate status",
    )
    group.add_argument(
        "--audit-log",
        action="store_true",
        help="Show recent audit log entries",
    )

    parser.add_argument(
        "--reason",
        type=str,
        help="Reason for the action (required for --disable and --restore)",
    )
    parser.add_argument(
        "--user",
        type=str,
        help="User performing the action (defaults to $USER)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum audit log entries to show (default: 20)",
    )

    args = parser.parse_args()

    # Validate reason is provided for disable/restore
    if (args.disable or args.restore) and not args.reason:
        parser.error("--reason is required when using --disable or --restore")

    if args.disable:
        return disable_gates(args.reason, args.user)
    elif args.restore:
        return restore_gates(args.reason, args.user)
    elif args.status:
        return check_status()
    elif args.audit_log:
        return show_audit_log(args.limit)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
