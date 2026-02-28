#!/usr/bin/env python3
"""
Signal→Order→Fill Chain Verification Script

Verifies the complete signal→order→fill chain is working during live scheduler operation.
Queries Redis for signal, order, and fill keys, cross-references linkages,
and reports counts and any broken chains.

Usage:
    python3 scripts/verify_signal_order_fill_chain.py [--interval MINUTES] [--duration MINUTES]

    # Single snapshot:
    python3 scripts/verify_signal_order_fill_chain.py

    # Monitor over time (T=0, T=5min, T=10min):
    python3 scripts/verify_signal_order_fill_chain.py --interval 5 --duration 10

Exit codes:
    0 - Chain is healthy
    1 - Chain issues detected
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ChainSnapshot:
    """Snapshot of chain state at a point in time."""

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    signal_count: int = 0
    order_count: int = 0
    fill_count: int = 0
    paper_signal_count: int = 0
    paper_order_count: int = 0
    paper_fill_count: int = 0
    bmad_signal_count: int = 0  # bmad:chiseai:signals:* pattern
    bmad_outcome_count: int = 0  # bmad:chiseai:outcomes:* pattern
    complete_chains: int = 0
    orphaned_orders: int = 0
    orphaned_fills: int = 0
    sample_chains: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ChainVerificationReport:
    """Report for signal→order→fill chain verification."""

    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    start_time: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    end_time: str = ""
    overall_status: str = "unknown"
    snapshots: list[ChainSnapshot] = field(default_factory=list)
    growth_analysis: dict[str, Any] = field(default_factory=dict)
    broken_chains: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def get_redis_client() -> Any:
    """Get Redis client with proper configuration.

    Note: In container context, we force host.docker.internal to connect
    to the host's Redis server, overriding any env vars that might point
    elsewhere (like 'redis-server' for other contexts).
    """
    try:
        import redis as redis_lib

        # Force host.docker.internal for container context validation
        # This overrides any env vars that might point to 'redis-server'
        redis_host = "host.docker.internal"
        redis_port = 6380
        client = redis_lib.Redis(
            host=redis_host,
            port=redis_port,
            socket_connect_timeout=5,
            decode_responses=True,
        )
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


def count_keys_by_pattern(client: Any, pattern: str) -> int:
    """Count keys matching a pattern."""
    count = 0
    try:
        for _ in client.scan_iter(match=pattern, count=1000):
            count += 1
    except Exception as e:
        logger.warning(f"Error scanning pattern {pattern}: {e}")
    return count


def get_keys_by_pattern(client: Any, pattern: str, limit: int = 1000) -> list[str]:
    """Get keys matching a pattern."""
    keys = []
    try:
        for key in client.scan_iter(match=pattern, count=1000):
            keys.append(key)
            if len(keys) >= limit:
                break
    except Exception as e:
        logger.warning(f"Error scanning pattern {pattern}: {e}")
    return keys


def get_signal_data(client: Any, key: str) -> dict[str, Any] | None:
    """Get signal data from Redis key.

    Handles both string (JSON) and hash data types.
    """
    try:
        key_type = client.type(key)

        if key_type == "string":
            data = client.get(key)
            if data:
                return json.loads(data)
        elif key_type == "hash":
            # bmad:chiseai:signals:* keys are stored as hashes
            data = client.hgetall(key)
            if data:
                return dict(data)
    except Exception as e:
        logger.warning(f"Error parsing signal data from {key}: {e}")
    return None


def get_order_data(client: Any, order_id: str) -> dict[str, Any] | None:
    """Get order data by order_id."""
    try:
        # Try order:* pattern first
        key = f"order:{order_id}"
        data = client.get(key)
        if data:
            return json.loads(data)

        # Try paper:order:* pattern
        pattern = f"paper:order:*:{order_id}"
        keys = list(client.scan_iter(match=pattern, count=10))
        if keys:
            data = client.get(keys[0])
            if data:
                parsed = json.loads(data)
                parsed["_key"] = keys[0]
                return parsed
    except Exception as e:
        logger.warning(f"Error getting order data for {order_id}: {e}")
    return None


def get_fill_data(client: Any, fill_id: str) -> dict[str, Any] | None:
    """Get fill data by fill_id."""
    try:
        # Try fill:* pattern first
        key = f"fill:{fill_id}"
        data = client.get(key)
        if data:
            return json.loads(data)

        # Try paper:fill:* pattern
        pattern = f"paper:fill:*:{fill_id}"
        keys = list(client.scan_iter(match=pattern, count=10))
        if keys:
            data = client.get(keys[0])
            if data:
                parsed = json.loads(data)
                parsed["_key"] = keys[0]
                return parsed
    except Exception as e:
        logger.warning(f"Error getting fill data for {fill_id}: {e}")
    return None


def get_fills_by_order(client: Any, order_id: str) -> list[dict[str, Any]]:
    """Get all fills associated with an order."""
    fills = []
    try:
        # Check fill:index:by_order
        index_key = "fill:index:by_order"
        if client.exists(index_key):
            entries = client.zrevrange(index_key, 0, -1)
            for entry in entries:
                if entry.startswith(f"{order_id}:"):
                    fill_id = entry.split(":", 1)[1]
                    fill_data = get_fill_data(client, fill_id)
                    if fill_data:
                        fills.append(fill_data)

        # Also check paper:fill:* pattern
        pattern = f"paper:fill:*:{order_id}"
        for key in client.scan_iter(match=pattern, count=100):
            data = client.get(key)
            if data:
                parsed = json.loads(data)
                parsed["_key"] = key
                fills.append(parsed)
    except Exception as e:
        logger.warning(f"Error getting fills for order {order_id}: {e}")
    return fills


def get_orders_by_signal(client: Any, signal_id: str) -> list[dict[str, Any]]:
    """Get all orders associated with a signal."""
    orders = []
    try:
        # Check order:index:by_signal
        index_key = "order:index:by_signal"
        if client.exists(index_key):
            entries = client.zrevrange(index_key, 0, -1)
            for entry in entries:
                if entry.startswith(f"{signal_id}:"):
                    order_id = entry.split(":", 1)[1]
                    order_data = get_order_data(client, order_id)
                    if order_data:
                        orders.append(order_data)

        # Also check paper:order:* pattern for signal_id field
        pattern = "paper:order:*"
        for key in client.scan_iter(match=pattern, count=1000):
            data = client.get(key)
            if data:
                try:
                    parsed = json.loads(data)
                    if parsed.get("signal_id") == signal_id:
                        parsed["_key"] = key
                        orders.append(parsed)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning(f"Error getting orders for signal {signal_id}: {e}")
    return orders


def take_snapshot(client: Any) -> ChainSnapshot:
    """Take a snapshot of the current chain state."""
    snapshot = ChainSnapshot()

    try:
        # Count signals - check multiple patterns
        snapshot.signal_count = count_keys_by_pattern(client, "signal:*")
        snapshot.paper_signal_count = count_keys_by_pattern(client, "paper:signal:*")
        # Also check bmad:chiseai:signals:* pattern
        snapshot.bmad_signal_count = count_keys_by_pattern(
            client, "bmad:chiseai:signals:*"
        )

        # Count orders
        snapshot.order_count = count_keys_by_pattern(client, "order:*")
        snapshot.paper_order_count = count_keys_by_pattern(client, "paper:order:*")

        # Count fills
        snapshot.fill_count = count_keys_by_pattern(client, "fill:*")
        snapshot.paper_fill_count = count_keys_by_pattern(client, "paper:fill:*")

        # Count outcomes
        snapshot.bmad_outcome_count = count_keys_by_pattern(
            client, "bmad:chiseai:outcomes:*"
        )

        # Find complete chains
        # Strategy: Get recent signals and trace forward
        # Try multiple signal patterns in order of preference
        signal_keys = get_keys_by_pattern(client, "bmad:chiseai:signals:*", limit=50)
        if not signal_keys:
            signal_keys = get_keys_by_pattern(client, "paper:signal:*", limit=50)
        if not signal_keys:
            signal_keys = get_keys_by_pattern(client, "signal:*", limit=50)

        complete_chains = 0
        orphaned_orders = 0
        orphaned_fills = 0
        sample_chains = []

        for signal_key in signal_keys[:10]:  # Check first 10 signals
            signal_data = get_signal_data(client, signal_key)
            if not signal_data:
                continue

            signal_id = signal_data.get("signal_id")
            if not signal_id:
                continue

            # Find orders for this signal
            orders = get_orders_by_signal(client, signal_id)

            if not orders:
                # Signal without orders - not necessarily broken, might be pending
                continue

            for order in orders:
                order_id = order.get("order_id")
                if not order_id:
                    continue

                # Find fills for this order
                fills = get_fills_by_order(client, order_id)

                if fills:
                    complete_chains += 1

                    # Save as sample if we don't have enough
                    if len(sample_chains) < 3:
                        sample_chains.append(
                            {
                                "signal_id": signal_id,
                                "signal_key": signal_key,
                                "order_id": order_id,
                                "order_state": order.get("state"),
                                "fill_count": len(fills),
                                "fills": [
                                    {
                                        "fill_id": f.get("fill_id"),
                                        "quantity": f.get("quantity"),
                                        "price": f.get("price"),
                                    }
                                    for f in fills[:3]
                                ],
                            }
                        )
                else:
                    # Order without fills - check if order is filled/partial
                    order_state = order.get("state")
                    if order_state in ["filled", "partial"]:
                        orphaned_orders += 1

        # Check for orphaned fills (fills without matching orders)
        fill_keys = get_keys_by_pattern(client, "fill:*", limit=50)
        for fill_key in fill_keys:
            fill_data = get_signal_data(client, fill_key)
            if fill_data:
                order_id = fill_data.get("order_id")
                if order_id and not get_order_data(client, order_id):
                    orphaned_fills += 1

        snapshot.complete_chains = complete_chains
        snapshot.orphaned_orders = orphaned_orders
        snapshot.orphaned_fills = orphaned_fills
        snapshot.sample_chains = sample_chains

    except Exception as e:
        snapshot.errors.append(str(e))
        logger.error(f"Error taking snapshot: {e}")

    return snapshot


def analyze_growth(snapshots: list[ChainSnapshot]) -> dict[str, Any]:
    """Analyze growth between snapshots."""
    if len(snapshots) < 2:
        return {"error": "Need at least 2 snapshots for growth analysis"}

    first = snapshots[0]
    last = snapshots[-1]

    analysis = {
        "duration_minutes": (
            datetime.fromisoformat(last.timestamp)
            - datetime.fromisoformat(first.timestamp)
        ).total_seconds()
        / 60,
        "signal_growth": {
            "absolute": last.signal_count - first.signal_count,
            "percentage": (
                ((last.signal_count - first.signal_count) / first.signal_count * 100)
                if first.signal_count > 0
                else 0
            ),
        },
        "order_growth": {
            "absolute": last.order_count - first.order_count,
            "percentage": (
                ((last.order_count - first.order_count) / first.order_count * 100)
                if first.order_count > 0
                else 0
            ),
        },
        "fill_growth": {
            "absolute": last.fill_count - first.fill_count,
            "percentage": (
                ((last.fill_count - first.fill_count) / first.fill_count * 100)
                if first.fill_count > 0
                else 0
            ),
        },
        "paper_signal_growth": {
            "absolute": last.paper_signal_count - first.paper_signal_count,
            "percentage": (
                (
                    (last.paper_signal_count - first.paper_signal_count)
                    / first.paper_signal_count
                    * 100
                )
                if first.paper_signal_count > 0
                else 0
            ),
        },
        "paper_order_growth": {
            "absolute": last.paper_order_count - first.paper_order_count,
            "percentage": (
                (
                    (last.paper_order_count - first.paper_order_count)
                    / first.paper_order_count
                    * 100
                )
                if first.paper_order_count > 0
                else 0
            ),
        },
        "paper_fill_growth": {
            "absolute": last.paper_fill_count - first.paper_fill_count,
            "percentage": (
                (
                    (last.paper_fill_count - first.paper_fill_count)
                    / first.paper_fill_count
                    * 100
                )
                if first.paper_fill_count > 0
                else 0
            ),
        },
        "chain_growth": {
            "absolute": last.complete_chains - first.complete_chains,
        },
    }

    return analysis


def generate_recommendations(report: ChainVerificationReport) -> list[str]:
    """Generate recommendations based on findings."""
    recommendations = []

    if not report.snapshots:
        recommendations.append("No snapshots available - check Redis connectivity")
        return recommendations

    latest = report.snapshots[-1]

    # Check for zero counts
    if latest.signal_count == 0 and latest.paper_signal_count == 0:
        recommendations.append(
            "CRITICAL: No signals found in Redis. Verify signal generation is active."
        )

    if latest.order_count == 0 and latest.paper_order_count == 0:
        recommendations.append(
            "WARNING: No orders found. Check if scheduler is creating orders from signals."
        )

    if latest.fill_count == 0 and latest.paper_fill_count == 0:
        recommendations.append(
            "WARNING: No fills found. Check if order execution is recording fills."
        )

    # Check for bmad signals
    if latest.bmad_signal_count == 0:
        recommendations.append(
            "No bmad:chiseai:signals:* keys found. Signal generation may not be active."
        )
    else:
        recommendations.append(
            f"Found {latest.bmad_signal_count} bmad:chiseai:signals:* keys."
        )

    # Check for orphaned entities
    if latest.orphaned_orders > 0:
        recommendations.append(
            f"Found {latest.orphaned_orders} orphaned orders (filled/partial but no fill records). "
            "Check fill recording logic."
        )

    if latest.orphaned_fills > 0:
        recommendations.append(
            f"Found {latest.orphaned_fills} orphaned fills (fills without matching orders). "
            "Check order persistence logic."
        )

    # Check growth
    if len(report.snapshots) >= 2 and report.growth_analysis:
        signal_growth = report.growth_analysis.get("signal_growth", {}).get(
            "absolute", 0
        )
        paper_signal_growth = report.growth_analysis.get("paper_signal_growth", {}).get(
            "absolute", 0
        )

        if signal_growth == 0 and paper_signal_growth == 0:
            recommendations.append(
                "No signal growth detected during monitoring period. "
                "Signal generation may not be active."
            )

        order_growth = report.growth_analysis.get("order_growth", {}).get("absolute", 0)
        paper_order_growth = report.growth_analysis.get("paper_order_growth", {}).get(
            "absolute", 0
        )

        if (
            (signal_growth > 0 or paper_signal_growth > 0)
            and order_growth == 0
            and paper_order_growth == 0
        ):
            recommendations.append(
                "Signals are being generated but no orders are being created. "
                "Check signal→order pipeline connection."
            )

    # Check complete chains
    if latest.complete_chains == 0 and latest.order_count > 0:
        recommendations.append(
            "Orders exist but no complete signal→order→fill chains found. "
            "Check order execution and fill recording."
        )

    if not recommendations:
        recommendations.append("Chain appears healthy. No issues detected.")

    return recommendations


def print_snapshot(snapshot: ChainSnapshot, index: int) -> None:
    """Print a snapshot in readable format."""
    print(f"\n{'=' * 60}")
    print(f"SNAPSHOT {index} - {snapshot.timestamp}")
    print(f"{'=' * 60}")

    print(f"\n📊 COUNTS:")
    print(
        f"  Signals:        {snapshot.signal_count} (paper: {snapshot.paper_signal_count}, bmad: {snapshot.bmad_signal_count})"
    )
    print(
        f"  Orders:         {snapshot.order_count} (paper: {snapshot.paper_order_count})"
    )
    print(
        f"  Fills:          {snapshot.fill_count} (paper: {snapshot.paper_fill_count})"
    )
    print(f"  Outcomes:       {snapshot.bmad_outcome_count}")
    print(f"  Complete Chains: {snapshot.complete_chains}")

    if snapshot.orphaned_orders > 0 or snapshot.orphaned_fills > 0:
        print(f"\n⚠️  ORPHANED:")
        print(f"  Orphaned Orders: {snapshot.orphaned_orders}")
        print(f"  Orphaned Fills:  {snapshot.orphaned_fills}")

    if snapshot.sample_chains:
        print(f"\n🔗 SAMPLE CHAINS:")
        for i, chain in enumerate(snapshot.sample_chains[:2], 1):
            print(f"  Chain {i}:")
            print(f"    Signal: {chain['signal_id'][:20]}...")
            print(
                f"    Order:  {chain['order_id'][:20]}... (state: {chain['order_state']})"
            )
            print(f"    Fills:  {chain['fill_count']} fills")

    if snapshot.errors:
        print(f"\n❌ ERRORS:")
        for error in snapshot.errors:
            print(f"  - {error}")


def print_report(report: ChainVerificationReport) -> None:
    """Print the full report."""
    print("\n" + "=" * 60)
    print("SIGNAL→ORDER→FILL CHAIN VERIFICATION REPORT")
    print("=" * 60)
    print(f"Execution ID: {report.execution_id}")
    print(f"Start Time:   {report.start_time}")
    print(f"End Time:     {report.end_time}")
    print(f"Status:       {report.overall_status.upper()}")

    # Print all snapshots
    for i, snapshot in enumerate(report.snapshots, 1):
        print_snapshot(snapshot, i)

    # Print growth analysis
    if report.growth_analysis and "error" not in report.growth_analysis:
        print(f"\n{'=' * 60}")
        print("GROWTH ANALYSIS")
        print(f"{'=' * 60}")

        duration = report.growth_analysis.get("duration_minutes", 0)
        print(f"\nDuration: {duration:.1f} minutes")

        print(f"\n📈 SIGNAL GROWTH:")
        sig_abs = report.growth_analysis.get("signal_growth", {}).get("absolute", 0)
        sig_pct = report.growth_analysis.get("signal_growth", {}).get("percentage", 0)
        print(f"  Standard: {sig_abs:+d} ({sig_pct:+.1f}%)")
        paper_sig_abs = report.growth_analysis.get("paper_signal_growth", {}).get(
            "absolute", 0
        )
        paper_sig_pct = report.growth_analysis.get("paper_signal_growth", {}).get(
            "percentage", 0
        )
        print(f"  Paper:    {paper_sig_abs:+d} ({paper_sig_pct:+.1f}%)")

        print(f"\n📈 ORDER GROWTH:")
        ord_abs = report.growth_analysis.get("order_growth", {}).get("absolute", 0)
        ord_pct = report.growth_analysis.get("order_growth", {}).get("percentage", 0)
        print(f"  Standard: {ord_abs:+d} ({ord_pct:+.1f}%)")
        paper_ord_abs = report.growth_analysis.get("paper_order_growth", {}).get(
            "absolute", 0
        )
        paper_ord_pct = report.growth_analysis.get("paper_order_growth", {}).get(
            "percentage", 0
        )
        print(f"  Paper:    {paper_ord_abs:+d} ({paper_ord_pct:+.1f}%)")

        print(f"\n📈 FILL GROWTH:")
        fill_abs = report.growth_analysis.get("fill_growth", {}).get("absolute", 0)
        fill_pct = report.growth_analysis.get("fill_growth", {}).get("percentage", 0)
        print(f"  Standard: {fill_abs:+d} ({fill_pct:+.1f}%)")
        paper_fill_abs = report.growth_analysis.get("paper_fill_growth", {}).get(
            "absolute", 0
        )
        paper_fill_pct = report.growth_analysis.get("paper_fill_growth", {}).get(
            "percentage", 0
        )
        print(f"  Paper:    {paper_fill_abs:+d} ({paper_fill_pct:+.1f}%)")

        print(f"\n📈 COMPLETE CHAIN GROWTH:")
        chain_abs = report.growth_analysis.get("chain_growth", {}).get("absolute", 0)
        print(f"  {chain_abs:+d} new complete chains")

    # Print broken chains
    if report.broken_chains:
        print(f"\n{'=' * 60}")
        print("BROKEN CHAINS")
        print(f"{'=' * 60}")
        for chain in report.broken_chains:
            print(f"\n  Issue: {chain.get('issue')}")
            print(f"  Details: {chain.get('details')}")

    # Print recommendations
    print(f"\n{'=' * 60}")
    print("RECOMMENDATIONS")
    print(f"{'=' * 60}")
    for rec in report.recommendations:
        print(f"  → {rec}")

    print(f"\n{'=' * 60}")


def save_report(report: ChainVerificationReport) -> Path:
    """Save report to file."""
    output_dir = Path("_bmad-output")
    output_dir.mkdir(exist_ok=True)

    report_file = output_dir / f"chain-verification-{report.execution_id}.json"

    # Convert dataclasses to dicts for JSON serialization
    report_dict = {
        "execution_id": report.execution_id,
        "start_time": report.start_time,
        "end_time": report.end_time,
        "overall_status": report.overall_status,
        "snapshots": [
            {
                "timestamp": s.timestamp,
                "signal_count": s.signal_count,
                "order_count": s.order_count,
                "fill_count": s.fill_count,
                "paper_signal_count": s.paper_signal_count,
                "paper_order_count": s.paper_order_count,
                "paper_fill_count": s.paper_fill_count,
                "bmad_signal_count": s.bmad_signal_count,
                "bmad_outcome_count": s.bmad_outcome_count,
                "complete_chains": s.complete_chains,
                "orphaned_orders": s.orphaned_orders,
                "orphaned_fills": s.orphaned_fills,
                "sample_chains": s.sample_chains,
                "errors": s.errors,
            }
            for s in report.snapshots
        ],
        "growth_analysis": report.growth_analysis,
        "broken_chains": report.broken_chains,
        "recommendations": report.recommendations,
    }

    with open(report_file, "w") as f:
        json.dump(report_dict, f, indent=2, default=str)

    logger.info(f"Report saved to: {report_file}")
    return report_file


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify signal→order→fill chain integrity"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="Monitoring interval in minutes (0 for single snapshot)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Total monitoring duration in minutes (0 for single snapshot)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("SIGNAL→ORDER→FILL CHAIN VERIFICATION")
    print("=" * 60)
    print(f"Start Time: {datetime.now(UTC).isoformat()}")
    print(f"Redis Host: host.docker.internal:6380")

    if args.interval > 0 and args.duration > 0:
        print(
            f"Mode: Continuous monitoring ({args.duration} min, every {args.interval} min)"
        )
    else:
        print("Mode: Single snapshot")

    print("")

    report = ChainVerificationReport()

    try:
        client = get_redis_client()

        # Test connection
        if not client.ping():
            logger.error("Redis ping failed")
            return 1

        logger.info("Redis connection established")

        if args.interval > 0 and args.duration > 0:
            # Continuous monitoring mode
            num_snapshots = (args.duration // args.interval) + 1
            logger.info(
                f"Taking {num_snapshots} snapshots over {args.duration} minutes"
            )

            for i in range(num_snapshots):
                logger.info(f"Taking snapshot {i + 1}/{num_snapshots}...")
                snapshot = take_snapshot(client)
                report.snapshots.append(snapshot)
                print_snapshot(snapshot, i + 1)

                if i < num_snapshots - 1:
                    wait_seconds = args.interval * 60
                    logger.info(
                        f"Waiting {args.interval} minutes until next snapshot..."
                    )
                    time.sleep(wait_seconds)
        else:
            # Single snapshot mode
            logger.info("Taking single snapshot...")
            snapshot = take_snapshot(client)
            report.snapshots.append(snapshot)
            print_snapshot(snapshot, 1)

        # Analyze growth if we have multiple snapshots
        if len(report.snapshots) >= 2:
            report.growth_analysis = analyze_growth(report.snapshots)

        # Generate recommendations
        report.recommendations = generate_recommendations(report)

        # Determine overall status
        latest = report.snapshots[-1] if report.snapshots else None
        if latest:
            if latest.errors:
                report.overall_status = "error"
            elif latest.orphaned_orders > 0 or latest.orphaned_fills > 0:
                report.overall_status = "degraded"
            elif latest.complete_chains == 0 and (
                latest.order_count > 0 or latest.paper_order_count > 0
            ):
                report.overall_status = "incomplete"
            elif latest.signal_count == 0 and latest.paper_signal_count == 0:
                report.overall_status = "no_signals"
            else:
                report.overall_status = "healthy"

        report.end_time = datetime.now(UTC).isoformat()

        # Print and save report
        print_report(report)
        report_file = save_report(report)

        print(f"\nFull report saved to: {report_file}")

        # Return exit code based on status
        if report.overall_status in ["error", "no_signals"]:
            return 1
        elif report.overall_status == "degraded":
            return 1
        else:
            return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
