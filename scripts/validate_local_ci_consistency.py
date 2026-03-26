#!/usr/bin/env python3
"""Local CI Consistency Validator.

Validates that the local development environment matches the CI configuration
to prevent "works on my machine" issues.

Exit codes:
    0 - No drift detected (consistent)
    1 - Drift detected (inconsistent)

Usage:
    python scripts/validate_local_ci_consistency.py [options]

Options:
    --verbose      Show detailed output
    --json         Output in JSON format
    --output FILE  Write report to FILE
    --help         Show this help message
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root))

from scripts.ci.consistency_checks.config_comparator import (
    ConfigDrift,
    compare_configurations,
    format_config_report,
)
from scripts.ci.consistency_checks.drift_reporter import (
    build_report,
    format_remediation,
    write_report,
)
from scripts.ci.consistency_checks.version_checker import (
    ToolVersion,
    check_tool_versions,
    detect_version_drift,
    format_version_report,
)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate local CI consistency",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output in JSON format"
    )
    parser.add_argument("--output", "-o", metavar="FILE", help="Write report to FILE")
    parser.add_argument(
        "--check",
        "-c",
        choices=["all", "version", "config"],
        default="all",
        help="Which checks to run (default: all)",
    )
    return parser.parse_args()


def run_version_check(verbose: bool = False) -> tuple[list, list]:
    """Run version consistency check.

    Returns:
        Tuple of (results, drifts)
    """
    if verbose:
        print("Checking tool versions...")

    results = check_tool_versions()
    drifts = detect_version_drift(results)

    if verbose:
        print(format_version_report(results, drifts))

    return results, drifts


def run_config_check(verbose: bool = False) -> tuple:
    """Run configuration consistency check.

    Returns:
        Tuple of (comparison, drifts)
    """
    if verbose:
        print("Checking configuration drift...")

    comparison = compare_configurations()

    if verbose:
        print(format_config_report(comparison))

    return comparison, comparison.drifts


def main() -> int:
    """Main entry point."""
    args = parse_args()

    version_drifts: list[ToolVersion] = []
    config_drifts: list[ConfigDrift] = []

    # Run checks based on --check argument
    if args.check in ("all", "version"):
        _, version_drifts = run_version_check(args.verbose)

    if args.check in ("all", "config"):
        _, config_drifts = run_config_check(args.verbose)

    # Build combined report
    report = build_report(version_drifts, config_drifts)

    # Output report
    if args.json:
        output = write_report(report, args.output, format="json")
    else:
        # Text format with remediation steps
        output_lines = [report.to_text()]
        if not report.passed:
            output_lines.append(format_remediation(report))
        output = "\n".join(output_lines)

        if args.output:
            Path(args.output).write_text(output)
        else:
            print(output)

    # Return appropriate exit code
    if report.passed:
        print("\n✓ Local environment is consistent with CI")
        return 0
    else:
        print(f"\n✗ Drift detected: {report.summary['total']} issue(s)")
        print("  Run with --verbose for details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
