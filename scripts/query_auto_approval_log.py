#!/usr/bin/env python3
"""Query auto-approval log.

Usage:
    python query_auto_approval_log.py [--limit N] [--pr NUMBER] [--format FORMAT]

Query and display auto-approval audit logs from Redis.
"""

import argparse
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Redis keys
LOG_KEY = "bmad:chiseai:auto_approval:log"
EMERGENCY_STOP_KEY = "bmad:chiseai:auto_approval:disabled"
HOURLY_COUNT_PATTERN = "bmad:chiseai:auto_approval:hourly_count:*"
CONSECUTIVE_KEY = "bmad:chiseai:auto_approval:consecutive_count"


async def get_redis_client():
    """Get Redis client."""
    try:
        import redis.asyncio as redis

        return redis.Redis(
            host="host.docker.internal", port=6380, decode_responses=True
        )
    except ImportError:
        logger.error("❌ redis package not installed")
        return None


async def get_logs(
    limit: int = 100, pr_number: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get auto-approval logs.

    Args:
        limit: Maximum number of logs to retrieve
        pr_number: Filter by PR number

    Returns:
        List of log entries
    """
    r = await get_redis_client()
    if not r:
        return []

    try:
        # Get logs from Redis list
        logs_raw = await r.lrange(LOG_KEY, 0, limit - 1)
        await r.close()

        logs = []
        for log_raw in logs_raw:
            try:
                # Try to parse as JSON
                if log_raw.startswith("{"):
                    log_entry = json.loads(log_raw)
                else:
                    # Handle string representation of dict
                    log_entry = eval(log_raw)

                # Filter by PR number if specified
                if pr_number is None or log_entry.get("pr_number") == pr_number:
                    logs.append(log_entry)
            except Exception as e:
                logger.warning(f"Failed to parse log entry: {e}")
                continue

        return logs

    except Exception as e:
        logger.error(f"Failed to get logs: {e}")
        return []


async def get_status() -> Dict[str, Any]:
    """Get current auto-approval status.

    Returns:
        Status dictionary
    """
    r = await get_redis_client()
    if not r:
        return {}

    try:
        # Check emergency stop
        emergency_stop = await r.get(EMERGENCY_STOP_KEY)

        # Get consecutive count
        consecutive = await r.get(CONSECUTIVE_KEY)

        # Get hourly counts
        hourly_keys = await r.keys(HOURLY_COUNT_PATTERN)
        hourly_counts = {}
        for key in hourly_keys:
            hour = key.split(":")[-1]
            count = await r.get(key)
            hourly_counts[hour] = int(count) if count else 0

        await r.close()

        return {
            "emergency_stop": emergency_stop
            and emergency_stop.lower() in ("true", "1", "yes"),
            "consecutive_count": int(consecutive) if consecutive else 0,
            "hourly_counts": hourly_counts,
        }

    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        return {}


def format_log_entry(entry: Dict[str, Any], format_type: str) -> str:
    """Format a log entry for display.

    Args:
        entry: Log entry dictionary
        format_type: Output format (text, json)

    Returns:
        Formatted string
    """
    if format_type == "json":
        return json.dumps(entry, indent=2)

    # Text format
    lines = []
    lines.append(f"\n{'=' * 60}")
    lines.append(f"Event: {entry.get('event', 'unknown')}")
    lines.append(f"PR: #{entry.get('pr_number', 'unknown')}")
    lines.append(f"Timestamp: {entry.get('timestamp', 'unknown')}")

    if "risk_level" in entry:
        lines.append(f"Risk Level: {entry['risk_level']}")
    if "confidence" in entry:
        lines.append(f"Confidence: {entry['confidence']:.2%}")
    if "files" in entry:
        files = entry["files"]
        lines.append(f"Files: {len(files)} total")
        for f in files[:5]:  # Show first 5 files
            lines.append(f"  - {f}")
        if len(files) > 5:
            lines.append(f"  ... and {len(files) - 5} more")

    if "reasoning" in entry:
        lines.append(f"Reasoning: {entry['reasoning']}")

    if "safety_checks" in entry:
        sc = entry["safety_checks"]
        if "checks" in sc:
            lines.append("Safety Checks:")
            for check in sc["checks"]:
                status = check.get("status", "unknown")
                icon = (
                    "✅" if status == "passed" else "❌" if status == "failed" else "⏭️"
                )
                lines.append(f"  {icon} {check.get('name', 'unknown')}: {status}")

    return "\n".join(lines)


def format_status(status: Dict[str, Any]) -> str:
    """Format status for display.

    Args:
        status: Status dictionary

    Returns:
        Formatted string
    """
    lines = []
    lines.append(f"\n{'=' * 60}")
    lines.append("Auto-Approval Status")
    lines.append(f"{'=' * 60}")

    emergency_stop = status.get("emergency_stop", False)
    lines.append(f"Emergency Stop: {'🛑 ACTIVE' if emergency_stop else '✅ Inactive'}")
    lines.append(f"Consecutive Count: {status.get('consecutive_count', 0)}")

    hourly = status.get("hourly_counts", {})
    if hourly:
        lines.append("\nHourly Counts:")
        for hour, count in sorted(hourly.items()):
            lines.append(f"  {hour}: {count} approvals")

    return "\n".join(lines)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Query auto-approval audit logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python query_auto_approval_log.py --limit 10
    python query_auto_approval_log.py --pr 123
    python query_auto_approval_log.py --status
    python query_auto_approval_log.py --format json --limit 5
        """,
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of logs to retrieve (default: 20)",
    )

    parser.add_argument(
        "--pr",
        type=int,
        help="Filter by PR number",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current status instead of logs",
    )

    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    if args.status:
        status = await get_status()
        if args.format == "json":
            print(json.dumps(status, indent=2))
        else:
            print(format_status(status))
    else:
        logs = await get_logs(limit=args.limit, pr_number=args.pr)

        if not logs:
            logger.info("No logs found")
            return

        if args.format == "json":
            print(json.dumps(logs, indent=2))
        else:
            logger.info(f"Found {len(logs)} log entries")
            for entry in logs:
                print(format_log_entry(entry, args.format))


if __name__ == "__main__":
    asyncio.run(main())
