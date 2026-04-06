#!/usr/bin/env python3
"""Smoke test for NotificationEventRouter routing pipeline.

This script exercises the notification routing logic without actually sending
Discord messages. It validates that events are routed to the correct mode
(immediate vs digest) based on the notification policy.

Usage:
    python scripts/notification_smoke_test.py              # Run with dry-run
    python scripts/notification_smoke_test.py --verbose     # Detailed output
    python scripts/notification_smoke_test.py --dry-run     # Skip Discord delivery
    python scripts/notification_smoke_test.py --help        # Show help

Exit codes:
    0 - All routing decisions correct
    1 - One or more routing decisions incorrect
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from governance.notifications.event_router import (
    NotificationEventRouter,
    RoutingDecision,
)


class MockDiscordNotifier:
    """Mock Discord notifier that tracks calls without sending messages.

    This notifier records all attempts to send notifications but does not
    actually deliver them to Discord. This allows testing the routing logic
    without requiring Discord credentials or network access.
    """

    def __init__(self, dry_run: bool = True):
        """Initialize mock notifier.

        Args:
            dry_run: If True, all sends are simulated without actual delivery.
        """
        self._dry_run = dry_run
        self._immediate_calls: list[dict[str, Any]] = []
        self._digest_calls: list[dict[str, Any]] = []
        self._low_severity_buffer: list[dict[str, Any]] = []

    @property
    def dry_run(self) -> bool:
        """Return dry run mode setting."""
        return self._dry_run

    async def notify_autocog_event(self, **kwargs: Any) -> bool:
        """Record immediate notification attempt."""
        if self._dry_run:
            self._immediate_calls.append(kwargs)
            return True
        return False

    def add_to_digest(self, event: dict[str, Any]) -> bool:
        """Record digest buffer addition."""
        if self._dry_run:
            self._digest_calls.append(event)
            self._low_severity_buffer.append(event)
            return True
        return False

    def get_immediate_count(self) -> int:
        """Return number of immediate notifications recorded."""
        return len(self._immediate_calls)

    def get_digest_count(self) -> int:
        """Return number of events added to digest."""
        return len(self._digest_calls)

    def reset(self) -> None:
        """Clear all recorded calls."""
        self._immediate_calls.clear()
        self._digest_calls.clear()
        self._low_severity_buffer.clear()


def create_test_events() -> list[dict[str, Any]]:
    """Create test events covering all routing paths.

    Returns:
        List of event dictionaries with expected routing mode.
    """
    return [
        # Test case 1: High severity → immediate
        {
            "event_type": "execution_quality_change",
            "severity": "high",
            "event_id": "test-high-severity-001",
            "summary": "High severity test event",
            "expected_mode": "immediate",
            "description": "high severity event",
        },
        # Test case 2: Critical severity → immediate
        {
            "event_type": "major_contradiction",
            "severity": "critical",
            "event_id": "test-critical-severity-001",
            "summary": "Critical severity test event",
            "expected_mode": "immediate",
            "description": "critical severity event",
        },
        # Test case 3: Medium severity → digest
        {
            "event_type": "useful_new_belief",
            "severity": "medium",
            "event_id": "test-medium-severity-001",
            "summary": "Medium severity test event",
            "expected_mode": "digest",
            "description": "medium severity event",
        },
        # Test case 4: Low severity → digest
        {
            "event_type": "minor_preference_refinement",
            "severity": "low",
            "event_id": "test-low-severity-001",
            "summary": "Low severity test event",
            "expected_mode": "digest",
            "description": "low severity event",
        },
        # Test case 5: approval_request → always immediate
        {
            "event_type": "approval_request",
            "severity": "low",  # Would normally be digest, but approval_request is always immediate
            "event_id": "test-approval-request-001",
            "summary": "Approval request test event",
            "expected_mode": "immediate",
            "description": "approval_request event",
        },
        # Test case 6: core_identity_conflict → always immediate
        {
            "event_type": "core_identity_conflict",
            "severity": "low",  # Would normally be digest, but core_identity_conflict is always immediate
            "event_id": "test-core-identity-conflict-001",
            "summary": "Core identity conflict test event",
            "expected_mode": "immediate",
            "description": "core_identity_conflict event",
        },
        # Test case 7: Unknown event type with no explicit severity → digest (safe default)
        {
            "event_type": "unknown_event_type_xyz",
            # No severity field - should default to 'low' via SeverityMapper
            "event_id": "test-unknown-event-001",
            "summary": "Unknown event type test",
            "expected_mode": "digest",
            "description": "unknown event type with no explicit severity",
        },
    ]


def run_smoke_test(
    router: NotificationEventRouter,
    events: list[dict[str, Any]],
    verbose: bool = False,
    dry_run: bool = True,
) -> tuple[int, list[dict[str, Any]], list[float]]:
    """Run the smoke test against all events.

    Args:
        router: NotificationEventRouter instance to test.
        events: List of test events with expected routing mode.
        verbose: If True, print detailed output for each event.
        dry_run: If True, skip actual Discord delivery attempts.

    Returns:
        Tuple of (correct_count, results, immediate_latencies).
    """
    results: list[dict[str, Any]] = []
    immediate_latencies: list[float] = []
    correct_count = 0

    for event in events:
        event_desc = event.pop("description")
        expected_mode = event.pop("expected_mode")

        if verbose:
            print(f"Testing: {event_desc}")

        # Measure routing decision time
        start_time = time.perf_counter()
        decision = router.route_event(event)
        elapsed = time.perf_counter() - start_time

        # Record latency for immediate-path events
        if decision.mode == "immediate":
            immediate_latencies.append(elapsed)

        # Check if routing decision matches expected
        is_correct = decision.mode == expected_mode

        if verbose:
            expected_label = expected_mode
            actual_label = decision.mode
            status = "✓" if is_correct else "✗"
            print(f"  Expected: {expected_label} | Actual: {actual_label} {status}")
            print(f"  Reason: {decision.reason}")
            print(f"  Latency: {elapsed * 1000:.3f}ms")
            print()

        result = {
            "description": event_desc,
            "expected_mode": expected_mode,
            "actual_mode": decision.mode,
            "reason": decision.reason,
            "latency_ms": elapsed * 1000,
            "correct": is_correct,
        }
        results.append(result)

        if is_correct:
            correct_count += 1

    return correct_count, results, immediate_latencies


def print_summary(
    total: int,
    correct: int,
    results: list[dict[str, Any]],
    immediate_latencies: list[float],
) -> None:
    """Print test summary.

    Args:
        total: Total number of test events.
        correct: Number of correct routing decisions.
        results: List of result dictionaries.
        immediate_latencies: List of latencies for immediate-path events.
    """
    print("=" * 50)
    print("=== Notification Routing Smoke Test ===")
    print()

    for result in results:
        status = "✓" if result["correct"] else "✗"
        print(f"Testing: {result['description']}")
        print(
            f"  Expected: {result['expected_mode']} | Actual: {result['actual_mode']} {status}"
        )

    print()
    print(f"=== All {correct}/{total} routing decisions correct ===")
    print()

    if immediate_latencies:
        avg_latency = sum(immediate_latencies) / len(immediate_latencies)
        max_latency = max(immediate_latencies)
        min_latency = min(immediate_latencies)
        # Latencies stored as seconds, display as milliseconds
        print(
            f"Immediate path latency: min={min_latency * 1000:.3f}ms, "
            f"avg={avg_latency * 1000:.3f}ms, max={max_latency * 1000:.3f}ms"
        )
    else:
        print("No immediate-path events tested")


def main() -> int:
    """Main entry point for smoke test.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(
        description="Smoke test for NotificationEventRouter routing pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/notification_smoke_test.py              Run with dry-run mode
  python scripts/notification_smoke_test.py --verbose     Show detailed output
  python scripts/notification_smoke_test.py --no-dry-run  Allow Discord delivery

Exit codes:
  0 - All routing decisions correct
  1 - One or more routing decisions incorrect
        """,
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output for each test event",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Skip actual Discord delivery attempts (default: True)",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Allow actual Discord delivery attempts",
    )

    args = parser.parse_args()

    # Create mock notifier
    mock_notifier = MockDiscordNotifier(dry_run=args.dry_run)

    # Initialize router with mock notifier and explicit policy path
    repo_root = Path(__file__).parent.parent
    policy_path = str(repo_root / "config" / "aria" / "notification-policy.yaml")

    router = NotificationEventRouter(
        notifier=mock_notifier,
        policy_path=policy_path,
    )

    # Create test events
    events = create_test_events()

    # Run smoke test
    print()
    print("=" * 50)
    print("=== Notification Routing Smoke Test ===")
    print()

    correct, results, immediate_latencies = run_smoke_test(
        router=router,
        events=events,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )

    total = len(events)
    print_summary(total, correct, results, immediate_latencies)

    # Exit with appropriate code
    if correct == total:
        print(f"✓ All {total} routing decisions correct")
        return 0
    else:
        print(f"✗ {total - correct} routing decision(s) incorrect")
        return 1


if __name__ == "__main__":
    sys.exit(main())
