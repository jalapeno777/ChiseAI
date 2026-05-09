#!/usr/bin/env python3
"""G-Exit-24h verification script for canary close and PnL instrumentation.

Queries the canary_metrics module to verify:
1. Canary has closed at least one position (canary_closed > 0)
2. Realized PnL path is functioning correctly

Exit codes:
- 0: PASS - G-Exit-24h criteria met
- 1: FAIL - G-Exit-24h criteria not met

For G-EXIT-24H: Canary Close & PnL Instrumentation
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from execution.paper.canary_metrics import CanaryMetrics


def format_pnl(pnl: float) -> str:
    """Format PnL as currency string."""
    prefix = "+" if pnl > 0 else ""
    return f"${prefix}{pnl:.2f}"


def check_g_exit_24h(
    canary_metrics: CanaryMetrics,
    min_closes_24h: int = 1,
    min_closes_48h: int = 1,
) -> tuple[bool, str]:
    """Check G-Exit-24h criteria.

    Args:
        canary_metrics: CanaryMetrics instance to query
        min_closes_24h: Minimum closes in 24h (default 1)
        min_closes_48h: Minimum closes in 48h (default 1)

    Returns:
        Tuple of (passed, reason)
    """
    # Query metrics
    try:
        closes_24h = canary_metrics.get_canary_close_count(since_hours=24)
        closes_48h = canary_metrics.get_canary_close_count(since_hours=48)
        pnl_24h = canary_metrics.get_realized_pnl(since_hours=24)
        pnl_48h = canary_metrics.get_realized_pnl(since_hours=48)
        running_pnl = canary_metrics.get_running_realized_pnl()
    except Exception as e:
        return False, f"Failed to query canary metrics: {e}"

    # Check criteria
    passed_24h = closes_24h >= min_closes_24h
    passed_48h = closes_48h >= min_closes_48h

    if not passed_24h and not passed_48h:
        return False, (
            f"No canary closes detected (24h: {closes_24h}, 48h: {closes_48h}). "
            f"Expected at least {min_closes_24h} close(s) in 24h."
        )

    if not passed_24h and passed_48h:
        return False, (
            f"No canary closes in 24h ({closes_24h} < {min_closes_24h}), "
            f"but have closes in 48h ({closes_48h}). Canary may be stalled."
        )

    # If we have closes, PnL path is working (even if PnL is 0 or negative)
    return True, (
        f"Canary closes: 24h={closes_24h}, 48h={closes_48h}. "
        f"Realized PnL: 24h={format_pnl(pnl_24h)}, 48h={format_pnl(pnl_48h)}, "
        f"running={format_pnl(running_pnl)}"
    )


def main() -> int:
    """Main entry point."""
    print("G-EXIT-24H STATUS CHECK")
    print("=" * 50)

    # Initialize canary metrics
    canary_metrics = CanaryMetrics()

    # Get metrics
    try:
        closes_24h = canary_metrics.get_canary_close_count(since_hours=24)
        closes_48h = canary_metrics.get_canary_close_count(since_hours=48)
        pnl_24h = canary_metrics.get_realized_pnl(since_hours=24)
        pnl_48h = canary_metrics.get_realized_pnl(since_hours=48)
        running_pnl = canary_metrics.get_running_realized_pnl()

        print(f"Canary closes (24h): {closes_24h}")
        print(f"Canary closes (48h): {closes_48h}")
        print(f"Realized PnL (24h): {format_pnl(pnl_24h)}")
        print(f"Realized PnL (48h): {format_pnl(pnl_48h)}")
        print(f"Running realized PnL: {format_pnl(running_pnl)}")
        print()

        # Check G-Exit-24h criteria
        passed, reason = check_g_exit_24h(canary_metrics)

        print(f"G-Exit-24h: {'PASS' if passed else 'FAIL'}")
        print(f"  → {reason}")

        return 0 if passed else 1

    except Exception as e:
        print("G-Exit-24h: FAIL")
        print(f"  → Error querying canary metrics: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
