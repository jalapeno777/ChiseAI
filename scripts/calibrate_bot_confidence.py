#!/usr/bin/env python3
"""Calibrate bot confidence thresholds based on historical accuracy."""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autonomous_git.gitreviewbot import CalibrationTracker


async def calibrate(
    days: int = 30,
    dry_run: bool = False,
) -> None:
    """Calibrate confidence thresholds."""
    tracker = CalibrationTracker()

    print(f"📊 Analyzing last {days} days of review data...")

    # Calculate current metrics
    metrics = await tracker.calculate_metrics(days=days)

    print(f"\nCurrent Performance:")
    print(f"  Total Reviews: {metrics.total_reviews}")
    print(f"  Accuracy Rate: {metrics.accuracy_rate:.1f}%")
    print(f"  Avg Confidence: {metrics.avg_confidence:.1f}%")
    print(f"  False Positives: {metrics.false_positive_rate:.1f}%")
    print(f"  False Negatives: {metrics.false_negative_rate:.1f}%")

    # Get recommended thresholds
    recommended = await tracker.get_recommended_thresholds()

    print(f"\n📈 Recommended Thresholds:")
    print(f"  Approve:     {recommended['approve']:.1f}%")
    print(f"  Comment:     {recommended['comment']:.1f}%")
    print(f"  Auto-merge:  {recommended['auto_merge']:.1f}%")

    if dry_run:
        print(f"\n🔍 Dry run - no changes applied")
        return

    # Apply new thresholds
    print(f"\n✅ Applying new thresholds...")
    # Implementation would update Redis/config
    print("Feature: Threshold updates (requires Redis connection)")

    # Export to Grafana
    grafana_data = await tracker.export_to_grafana(metrics)
    print(f"\n📤 Exported metrics to Grafana format")

    # Save report
    report = {
        "calibrated_at": datetime.utcnow().isoformat(),
        "period_days": days,
        "metrics": metrics.model_dump(),
        "recommended_thresholds": recommended,
    }

    report_path = Path("reports/gitreviewbot_calibration.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n📝 Report saved to {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Calibrate GitReviewBot confidence thresholds"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show recommendations without applying",
    )

    args = parser.parse_args()

    asyncio.run(
        calibrate(
            days=args.days,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    from datetime import datetime

    main()
