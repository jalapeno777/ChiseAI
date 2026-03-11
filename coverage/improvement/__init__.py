"""Coverage improvement package.

Re-exports from tests.coverage.improvement for backward compatibility.
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

# Import submodules to make them accessible
from coverage.improvement import analyzer
from coverage.improvement import reporter

# Re-export main classes for convenience
from coverage.improvement.analyzer import (
    CoverageAnalyzer,
    CoverageGap,
    CoverageReport,
    ModuleCoverage,
    Priority,
    CRITICAL_MODULES,
)
from coverage.improvement.reporter import (
    CoverageReporter,
    CoverageThresholds,
    ReportFormat,
)


def improvement_main() -> int:
    """
    Main CLI entry point for coverage improvement tools.

    Analyzes code coverage and generates improvement reports.

    Returns:
        Exit code (0 for success, 1 for coverage below threshold)
    """
    parser = argparse.ArgumentParser(
        description="Coverage analysis and improvement reporting"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run coverage analysis",
    )
    parser.add_argument(
        "--report",
        choices=["console", "json", "markdown", "html"],
        default="console",
        help="Report format",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=80.0,
        help="Minimum coverage threshold (default: 80.0)",
    )
    parser.add_argument(
        "--src-path",
        type=str,
        default="src",
        help="Source code path to analyze",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    if args.verbose:
        print(f"Analyzing coverage for: {args.src_path}")
        print(f"Threshold: {args.threshold}%")

    # Initialize analyzer and reporter
    coverage_analyzer = CoverageAnalyzer()
    thresholds = CoverageThresholds(minimum_coverage=args.threshold)
    coverage_reporter = CoverageReporter(thresholds=thresholds)

    # Run analysis
    if args.analyze:
        try:
            # Run coverage collection
            coverage_data = coverage_analyzer.run_coverage()

            # Generate report
            report = CoverageReport(
                timestamp=datetime.now(UTC),
                overall_coverage=coverage_data.get("overall", 0.0),
                total_gaps=len(coverage_data.get("gaps", [])),
            )

            # Output in requested format
            format_map = {
                "console": ReportFormat.CONSOLE,
                "json": ReportFormat.JSON,
                "markdown": ReportFormat.MARKDOWN,
                "html": ReportFormat.HTML,
            }
            report_format = format_map.get(args.report, ReportFormat.CONSOLE)

            # Generate report to stdout (output_path=None)
            coverage_reporter.generate(report, report_format, output_path=None)

            # Check compliance
            is_compliant = coverage_reporter.check_compliance(report)

            if args.verbose:
                print(f"\nCompliance: {'PASS' if is_compliant else 'FAIL'}")

            return 0 if is_compliant else 1

        except Exception as e:
            print(f"Error running coverage analysis: {e}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 0


__all__ = [
    # Submodules
    "analyzer",
    "reporter",
    # Analyzer exports
    "CoverageAnalyzer",
    "CoverageGap",
    "CoverageReport",
    "ModuleCoverage",
    "Priority",
    "CRITICAL_MODULES",
    # Reporter exports
    "CoverageReporter",
    "CoverageThresholds",
    "ReportFormat",
    # CLI
    "improvement_main",
]
