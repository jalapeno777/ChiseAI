#!/usr/bin/env python3
"""Persona regression harness CLI.

Runs the persona evaluation suite against golden cases and outputs
machine-readable JSON results suitable for CI consumption.

Usage:
    python3 scripts/eval/run_persona_harness.py
    python3 scripts/eval/run_persona_harness.py --verbose
    python3 scripts/eval/run_persona_harness.py --output results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.persona.evaluator import MODE_DIMENSIONS, PersonaEvaluator

DEFAULT_GOLDEN_PATH = _PROJECT_ROOT / "tests" / "persona" / "golden_cases.yaml"
PASS_THRESHOLD = 14  # minimum drift score for CI pass


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Run persona regression harness for CI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--golden-cases",
        type=Path,
        default=DEFAULT_GOLDEN_PATH,
        help=f"Path to golden cases YAML (default: {DEFAULT_GOLDEN_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON results to this file (default: stdout)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print human-readable summary alongside JSON",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=PASS_THRESHOLD,
        help=f"Minimum drift score for pass (default: {PASS_THRESHOLD})",
    )
    return parser


def main() -> int:
    """Run the persona regression harness.

    Returns:
        Exit code: 0 if drift score >= threshold, 1 otherwise.
    """
    parser = build_parser()
    args = parser.parse_args()

    # Load golden cases
    evaluator = PersonaEvaluator()
    try:
        cases = evaluator.load_cases_from_yaml(args.golden_cases)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"ERROR: Invalid golden cases file: {e}", file=sys.stderr)
        return 1

    if not cases:
        print("ERROR: No valid cases found in golden cases file.", file=sys.stderr)
        return 1

    # Run suite with perfect explicit scores (baseline evaluation)
    # In production, this would call an LLM and evaluate actual responses.
    # For CI baseline, we verify the harness infrastructure works correctly.
    explicit_scores: dict[str, dict[str, int]] = {}
    for case in cases:
        applicable_dims = MODE_DIMENSIONS.get(case.mode, [])
        explicit_scores[case.case_id] = {dim: 2 for dim in applicable_dims}

    suite_result = evaluator.run_suite(cases, explicit_scores=explicit_scores)

    # Output JSON
    json_output = evaluator.to_json(suite_result)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(json_output)
            f.write("\n")
        if args.verbose:
            print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(json_output)

    # Verbose output
    if args.verbose:
        drift = suite_result["overall_drift_score"]
        status = suite_result["drift_status"]
        passed = suite_result["passed_cases"]
        total = suite_result["total_cases"]
        print(f"\n{'=' * 60}", file=sys.stderr)
        print("Persona Regression Results", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
        print(f"  Suite:       {suite_result['suite']}", file=sys.stderr)
        print(f"  Run ID:      {suite_result['run_id']}", file=sys.stderr)
        print(f"  Cases:       {passed}/{total} passed", file=sys.stderr)
        print(f"  Drift Score: {drift}", file=sys.stderr)
        print(f"  Status:      {status}", file=sys.stderr)
        print(f"  Threshold:   {args.threshold}", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)

        for cr in suite_result["case_results"]:
            mark = "PASS" if cr["passed"] else "FAIL"
            print(
                f"  [{mark}] {cr['case_id']} ({cr['mode']}): {cr['total_score']} pts",
                file=sys.stderr,
            )
            if cr["failure_reasons"]:
                for reason in cr["failure_reasons"]:
                    print(f"        - {reason}", file=sys.stderr)

    # Exit code
    if suite_result["overall_drift_score"] >= args.threshold:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
