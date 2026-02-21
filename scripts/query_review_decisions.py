#!/usr/bin/env python3
"""Query review decisions and calibration data."""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autonomous_git.gitreviewbot import CalibrationTracker


async def query_decisions(
    pr_number: Optional[int] = None,
    days: int = 7,
    output_format: str = "table",
) -> None:
    """Query review decisions."""
    tracker = CalibrationTracker()

    if pr_number:
        # Query specific PR
        print(f"Querying decisions for PR #{pr_number}...")
        # Implementation would fetch from Redis
        print("Feature: Query by PR number (requires Redis connection)")
    else:
        # Query metrics for period
        print(f"Querying metrics for last {days} days...")
        metrics = await tracker.calculate_metrics(days=days)

        if output_format == "json":
            print(json.dumps(metrics.model_dump(), indent=2, default=str))
        else:
            print(f"\n📊 Calibration Metrics (Last {days} days)")
            print("=" * 50)
            print(f"Total Reviews:        {metrics.total_reviews}")
            print(f"Approved:             {metrics.approved_reviews}")
            print(f"Commented:            {metrics.commented_reviews}")
            print(f"Changes Requested:    {metrics.requested_changes_reviews}")
            print(f"")
            print(f"Human Overrides:      {metrics.human_overrides}")
            print(f"Human Agreements:     {metrics.human_agreements}")
            print(f"")
            print(f"Accuracy Rate:        {metrics.accuracy_rate:.1f}%")
            print(f"Avg Confidence:       {metrics.avg_confidence:.1f}%")
            print(f"False Positive Rate:  {metrics.false_positive_rate:.1f}%")
            print(f"False Negative Rate:  {metrics.false_negative_rate:.1f}%")


async def list_recent_reviews(days: int = 7) -> None:
    """List recent reviews."""
    tracker = CalibrationTracker()

    end = datetime.utcnow()
    start = end - timedelta(days=days)

    reviews = await tracker._get_reviews_in_period(start, end)

    print(f"\n📋 Recent Reviews (Last {days} days)")
    print("=" * 80)
    print(f"{'PR':<6} {'Decision':<18} {'Confidence':>10} {'Feedback':>10}")
    print("-" * 80)

    for review in reviews:
        feedback = review.human_feedback or "-"
        print(
            f"{review.pr_number:<6} {review.decision:<18} "
            f"{review.confidence:>9.1f}% {feedback:>10}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Query GitReviewBot decisions and calibration data"
    )
    parser.add_argument(
        "--pr",
        type=int,
        help="Query specific PR number",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to query (default: 7)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List individual reviews instead of metrics",
    )

    args = parser.parse_args()

    if args.list:
        asyncio.run(list_recent_reviews(days=args.days))
    else:
        asyncio.run(
            query_decisions(
                pr_number=args.pr,
                days=args.days,
                output_format=args.format,
            )
        )


if __name__ == "__main__":
    main()
