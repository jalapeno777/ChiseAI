#!/usr/bin/env python3
"""Self-Review Script for GitReviewBot Integration.

Provides CLI interface for automated self-review of PRs.
Designed to be called from GitReviewBot (ST-AUTO-003).

For ST-GOV-006: Self-Review Quality Gate

Usage:
    python scripts/governance/self_review.py evaluate --pr-number 123 --branch feature/test
    python scripts/governance/self_review.py score --files src/foo.py src/bar.py
    python scripts/governance/self_review.py override --pr-number 123 --requester "user" ...
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config.bootstrap import bootstrap
from src.governance.quality_gate.gate import (
    BlockReason,
    QualityGate,
    QualityGateResult,
)
from src.governance.quality_gate.override import OverrideManager
from src.governance.quality_gate.scorer import QualityScorer, ScoreComponent

# Bootstrap environment
bootstrap(load_env=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_changed_files(
    pr_number: int | None = None, branch: str | None = None
) -> list[str]:
    """Get list of changed files.

    Args:
        pr_number: PR number (if available)
        branch: Branch name (for comparison)

    Returns:
        List of changed file paths
    """
    files: list[str] = []

    # Try git diff for changed files
    try:
        if branch:
            # Compare with main branch
            result = subprocess.run(
                ["git", "diff", "--name-only", f"origin/main...{branch}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                files = [f for f in result.stdout.strip().split("\n") if f]
        else:
            # Get staged/unstaged changes
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                files = [f for f in result.stdout.strip().split("\n") if f]
    except Exception as e:
        logger.warning(f"Failed to get changed files from git: {e}")

    return files


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate a PR through the quality gate."""
    scorer = QualityScorer(passing_threshold=args.threshold)
    gate = QualityGate(
        scorer=scorer,
        blocking_threshold=args.threshold,
        enable_blocking=not args.no_block,
    )

    # Get changed files
    if args.files:
        changed_files = args.files
    else:
        changed_files = get_changed_files(args.pr_number, args.branch)

    if not changed_files:
        print(
            json.dumps(
                {
                    "success": True,
                    "message": "No files to evaluate",
                    "data": {"passed": True, "score": {"overall_score": 1.0}},
                },
                indent=2,
            )
        )
        return 0

    result = gate.evaluate(
        pr_number=args.pr_number or 0,
        changed_files=changed_files,
        branch=args.branch or "unknown",
        repo_path=args.repo_path,
    )

    output = {
        "success": True,
        "passed": result.passed,
        "blocked": result.blocked,
        "score_percentage": round(result.score.overall_score * 100, 2),
        "threshold_percentage": round(args.threshold * 100, 2),
        "review_time_seconds": result.review_time_seconds,
        "block_reasons": [r.value for r in result.block_reasons],
        "recommendations": result.recommendations,
        "component_scores": {
            comp.value: {
                "score": round(score.score * 100, 2),
                "passed": score.passed,
            }
            for comp, score in result.score.component_scores.items()
        },
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        # Human-readable output
        status = "✅ PASSED" if result.passed else "❌ BLOCKED"
        print(f"\n{'=' * 60}")
        print(f"Quality Gate Evaluation: {status}")
        print(f"{'=' * 60}")
        print(
            f"Overall Score: {output['score_percentage']}% (threshold: {output['threshold_percentage']}%)"
        )
        print(f"Review Time: {result.review_time_seconds:.2f}s")
        print()

        print("Component Scores:")
        for comp, data in output["component_scores"].items():
            status_icon = "✓" if data["passed"] else "✗"
            print(f"  {status_icon} {comp}: {data['score']}%")
        print()

        if result.block_reasons:
            print("Block Reasons:")
            for reason in result.block_reasons:
                print(f"  - {reason}")
            print()

        if result.recommendations:
            print("Recommendations:")
            for rec in result.recommendations:
                print(f"  • {rec}")

        if result.override_active:
            print(f"\n⚠️  Override active: {result.override_id}")

    return 0 if result.passed else 1


def cmd_score(args: argparse.Namespace) -> int:
    """Calculate quality score without blocking."""
    scorer = QualityScorer(passing_threshold=args.threshold)

    if args.files:
        changed_files = args.files
    else:
        changed_files = get_changed_files()

    if not changed_files:
        print(
            json.dumps(
                {
                    "success": True,
                    "message": "No files to score",
                    "data": {"overall_score": 1.0},
                },
                indent=2,
            )
        )
        return 0

    score = scorer.calculate_score(
        changed_files=changed_files,
        pr_number=args.pr_number,
        branch=args.branch,
        repo_path=args.repo_path,
    )

    output = score.to_dict()

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"\nQuality Score: {output['overall_percentage']}%")
        print(f"Files: {output['file_count']}, Lines: {output['line_count']}")
        print("\nComponent Breakdown:")
        for comp, data in output["component_scores"].items():
            print(
                f"  {comp}: {round(data['score'] * 100, 2)}% (weight: {data['weight']})"
            )

    return 0


def cmd_override(args: argparse.Namespace) -> int:
    """Manage overrides."""
    manager = OverrideManager()

    if args.override_action == "create":
        try:
            override = manager.create_request(
                pr_number=args.pr_number,
                requester=args.requester,
                justification=args.justification,
                risk_assessment=args.risk_level,
                rollback_plan=args.rollback_plan,
                affected_systems=args.systems or [],
                expiration_hours=args.expiration_hours,
            )

            if args.json:
                print(
                    json.dumps(
                        {
                            "success": True,
                            "data": override.to_dict(),
                        },
                        indent=2,
                    )
                )
            else:
                print(f"Override request created: {override.id}")
                print(f"Status: {override.status.value}")
                print("Requires approval before activation.")

            return 0

        except ValueError as e:
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
            return 1

    elif args.override_action == "approve":
        try:
            override = manager.approve_request(args.override_id, args.approver)

            if args.json:
                print(
                    json.dumps(
                        {
                            "success": True,
                            "data": override.to_dict(),
                        },
                        indent=2,
                    )
                )
            else:
                print(f"Override {args.override_id} approved by {args.approver}")
                print("Activate to allow PR merge.")

            return 0

        except ValueError as e:
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
            return 1

    elif args.override_action == "activate":
        try:
            override = manager.activate_override(args.override_id)

            if args.json:
                print(
                    json.dumps(
                        {
                            "success": True,
                            "data": override.to_dict(),
                        },
                        indent=2,
                    )
                )
            else:
                print(f"Override {args.override_id} activated.")
                print("PR can now be merged.")

            return 0

        except ValueError as e:
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
            return 1

    elif args.override_action == "revoke":
        try:
            override = manager.revoke_override(
                args.override_id, args.revoked_by, args.reason
            )

            if args.json:
                print(
                    json.dumps(
                        {
                            "success": True,
                            "data": override.to_dict(),
                        },
                        indent=2,
                    )
                )
            else:
                print(f"Override {args.override_id} revoked.")

            return 0

        except ValueError as e:
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
            return 1

    elif args.override_action == "list":
        if args.pending:
            overrides = manager.get_pending_requests()
        else:
            overrides = manager.get_active_overrides()

        if args.json:
            print(
                json.dumps(
                    {
                        "success": True,
                        "data": [o.to_dict() for o in overrides],
                    },
                    indent=2,
                )
            )
        else:
            print(
                f"Found {len(overrides)} {'pending' if args.pending else 'active'} overrides:"
            )
            for o in overrides:
                print(f"  - {o.id}: PR #{o.pr_number} ({o.status.value})")

        return 0

    return 1


def cmd_stats(args: argparse.Namespace) -> int:
    """Show quality gate statistics."""
    gate = QualityGate()
    stats = gate.get_stats()

    if args.json:
        print(json.dumps({"success": True, "data": stats}, indent=2))
    else:
        print("\nQuality Gate Statistics")
        print("=" * 40)
        print(f"Total Reviews: {stats['total_reviews']}")
        print(f"Blocked: {stats['blocked_reviews']}")
        print(f"Overridden: {stats['overridden_reviews']}")
        print(f"Block Rate: {stats['block_rate'] * 100:.1f}%")
        print(f"Avg Review Time: {stats['avg_review_time_seconds']:.2f}s")
        print()
        print("Validation Gates:")
        for gate_name, passed in stats["validation_gates"].items():
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status} {gate_name}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Self-Review Quality Gate CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--repo-path", default=".", help="Path to repository root")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.80,
        help="Quality threshold (default: 0.80)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # Evaluate command
    eval_parser = sub.add_parser("evaluate", help="Evaluate a PR through quality gate")
    eval_parser.add_argument("--pr-number", type=int, help="PR number")
    eval_parser.add_argument("--branch", help="Branch name")
    eval_parser.add_argument("--files", nargs="+", help="List of changed files")
    eval_parser.add_argument(
        "--no-block", action="store_true", help="Don't actually block, just report"
    )
    eval_parser.set_defaults(func=cmd_evaluate)

    # Score command
    score_parser = sub.add_parser("score", help="Calculate quality score")
    score_parser.add_argument("--pr-number", type=int, help="PR number")
    score_parser.add_argument("--branch", help="Branch name")
    score_parser.add_argument("--files", nargs="+", help="List of changed files")
    score_parser.set_defaults(func=cmd_score)

    # Override command
    override_parser = sub.add_parser("override", help="Manage overrides")
    override_sub = override_parser.add_subparsers(dest="override_action", required=True)

    # Create override
    create_parser = override_sub.add_parser("create", help="Create override request")
    create_parser.add_argument("--pr-number", type=int, required=True)
    create_parser.add_argument("--requester", required=True)
    create_parser.add_argument("--justification", required=True)
    create_parser.add_argument(
        "--risk-level", required=True, choices=["low", "medium", "high", "critical"]
    )
    create_parser.add_argument("--rollback-plan", required=True)
    create_parser.add_argument("--systems", nargs="+", default=[])
    create_parser.add_argument("--expiration-hours", type=int, default=24)

    # Approve override
    approve_parser = override_sub.add_parser("approve", help="Approve override")
    approve_parser.add_argument("--override-id", required=True)
    approve_parser.add_argument("--approver", required=True)

    # Activate override
    activate_parser = override_sub.add_parser("activate", help="Activate override")
    activate_parser.add_argument("--override-id", required=True)

    # Revoke override
    revoke_parser = override_sub.add_parser("revoke", help="Revoke override")
    revoke_parser.add_argument("--override-id", required=True)
    revoke_parser.add_argument("--revoked-by", required=True)
    revoke_parser.add_argument("--reason", required=True)

    # List overrides
    list_parser = override_sub.add_parser("list", help="List overrides")
    list_parser.add_argument(
        "--pending", action="store_true", help="Show pending instead of active"
    )

    override_parser.set_defaults(func=cmd_override)

    # Stats command
    stats_parser = sub.add_parser("stats", help="Show statistics")
    stats_parser.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
