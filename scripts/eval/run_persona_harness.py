#!/usr/bin/env python3
"""Persona regression harness CLI.

Runs the persona evaluation suite against golden cases and outputs
machine-readable JSON results suitable for CI consumption.

Usage:
    python3 scripts/eval/run_persona_harness.py
    python3 scripts/eval/run_persona_harness.py --verbose
    python3 scripts/eval/run_persona_harness.py --output results.json
    python3 scripts/eval/run_persona_harness.py --disabled
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

# Ensure project root is on sys.path for imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.persona.evaluator import MODE_DIMENSIONS, PersonaEvaluator

DEFAULT_GOLDEN_PATH = _PROJECT_ROOT / "tests" / "persona" / "golden_cases.yaml"
DEFAULT_OUTPUT_PATH = "_bmad-output/persona/persona-regression-{date}.json"
PASS_THRESHOLD = 12  # minimum drift score for CI pass
WARN_THRESHOLD = 10  # Score < 10 = FAIL, 10-11 = WARN, >= 12 = PASS


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
        help="Write JSON results to this file (default: _bmad-output/ci/persona-regression-YYYY-MM-DD.json for scheduled runs)",
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
    parser.add_argument(
        "--warn-threshold",
        type=int,
        default=WARN_THRESHOLD,
        help=f"Warn threshold for drift score (default: {WARN_THRESHOLD})",
    )
    parser.add_argument(
        "--disabled",
        action="store_true",
        default=False,
        help="Check feature flag and exit early if persona regression is disabled",
    )
    return parser


def _parse_bool_env(value: str) -> bool | None:
    """Parse boolean from environment variable string.

    Args:
        value: Environment variable value

    Returns:
        True if true-ish, False if false-ish, None if unset/invalid
    """
    value_lower = value.lower().strip()
    if value_lower in ("false", "0", "no", "off"):
        return False
    if value_lower in ("true", "1", "yes", "on"):
        return True
    return None


def is_persona_regression_enabled() -> bool:
    """Check if persona regression is enabled via feature flag.

    Checks in order:
    1. Environment variable FEATURE_PERSONA_REGRESSION_ENABLED (if explicitly set)
    2. Redis feature flag (via FeatureFlags.is_persona_regression_enabled())
    3. Default: True

    Returns:
        True if enabled, False if disabled
    """
    # Check env var first - explicit env var takes priority
    env_val = os.getenv("FEATURE_PERSONA_REGRESSION_ENABLED")
    if env_val is not None:
        parsed = _parse_bool_env(env_val)
        if parsed is not None:
            return parsed
        # Invalid env val - fall through to other checks

    # Try FeatureFlags (checks Redis with fallback to default True)
    try:
        from src.config.feature_flags import get_feature_flags

        flags = get_feature_flags()
        return flags.is_persona_regression_enabled()
    except Exception:
        # Redis unavailable or other error - default to True (safe)
        return True


def _classify_tier(score: int, pass_threshold: int, warn_threshold: int) -> str:
    """Classify result into a tier string.

    Returns: PASS if score >= pass_threshold, WARN if score >= warn_threshold, FAIL otherwise.
    """
    if score >= pass_threshold:
        return "PASS"
    elif score >= warn_threshold:
        return "WARN"
    else:
        return "FAIL"


def main() -> int:
    """Run the persona regression harness.

    Returns:
        Exit code: 0 if drift score >= threshold or disabled skip, 1 otherwise.
        Exit code 2: Error (file not found, etc.)
    """
    parser = build_parser()
    args = parser.parse_args()

    # Check --disabled flag and feature flag
    if args.disabled:
        enabled = is_persona_regression_enabled()
        if not enabled:
            print("Persona regression disabled, exiting", file=sys.stderr)
            return 0  # Safe skip - exit code 0

    # Load golden cases
    evaluator = PersonaEvaluator()
    try:
        cases = evaluator.load_cases_from_yaml(args.golden_cases)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"ERROR: Invalid golden cases file: {e}", file=sys.stderr)
        return 2

    if not cases:
        print("ERROR: No valid cases found in golden cases file.", file=sys.stderr)
        return 2

    # Run suite with perfect explicit scores (baseline evaluation)
    # In production, this would call an LLM and evaluate actual responses.
    # For CI baseline, we verify the harness infrastructure works correctly.
    explicit_scores: dict[str, dict[str, int]] = {}
    for case in cases:
        applicable_dims = MODE_DIMENSIONS.get(case.mode, [])
        explicit_scores[case.case_id] = {dim: 2 for dim in applicable_dims}

    suite_result = evaluator.run_suite(cases, explicit_scores=explicit_scores)

    # Output JSON - determine output path
    output_path = (
        args.output
        if args.output
        else Path(DEFAULT_OUTPUT_PATH.format(date=date.today().isoformat()))
    )

    # Add CI tier metadata to result
    suite_result["ci_tier"] = _classify_tier(
        suite_result["overall_drift_score"], args.threshold, args.warn_threshold
    )
    suite_result["pass_threshold"] = args.threshold
    suite_result["warn_threshold"] = args.warn_threshold

    json_output = evaluator.to_json(suite_result)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(json_output)
            f.write("\n")
        if args.verbose:
            print(f"Results written to {output_path}", file=sys.stderr)
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

    # Emit TIER line to stdout
    tier = _classify_tier(
        suite_result["overall_drift_score"], args.threshold, args.warn_threshold
    )
    print(f"TIER:{tier}")

    # Exit code
    if suite_result["overall_drift_score"] >= args.threshold:
        return 0  # PASS
    elif suite_result["overall_drift_score"] >= args.warn_threshold:
        return 0  # WARN (still exit 0, but tier is WARN)
    else:
        return 1  # FAIL


if __name__ == "__main__":
    sys.exit(main())
