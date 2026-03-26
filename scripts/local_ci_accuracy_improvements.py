#!/usr/bin/env python3
"""Local CI Accuracy Improvements - Enhanced error reporting and false positive detection.

Integrates error classification and diagnostics to provide:
- Better error messages with actionable next steps
- False positive detection for known flaky patterns
- Clear categorization of failures
- Suggested fixes based on error type
- Diagnostic context for troubleshooting

Usage:
    python scripts/local_ci_accuracy_improvements.py
    python scripts/local_ci_accuracy_improvements.py --input /path/to/ci.log
    python scripts/local_ci_accuracy_improvements.py --check-env
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path for imports
_script_dir = Path(__file__).parent.resolve()
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Import local modules
try:
    from scripts.ci.diagnostics import (
        DiagnosticReport,
        format_report_text,
        run_all_checks,
    )
    from scripts.ci.error_classifier import (
        ClassifiedError,
        ErrorCategory,
        classify_ci_output,
        format_classification_report,
    )
except ImportError:
    # Fallback if imports fail
    ErrorCategory = None
    CLASSIFICATION_AVAILABLE = False
else:
    CLASSIFICATION_AVAILABLE = True


class FalsePositivePattern(Enum):
    """Known false positive patterns to detect."""

    # Timing-related flakiness
    TIMING_FLAKY = "timing_flaky"
    # Network-related issues
    NETWORK_FLAKY = "network_flaky"
    # Known broken tests
    KNOWN_BROKEN = "known_broken"
    # Environment-specific issues
    ENV_SPECIFIC = "env_specific"


@dataclass
class FalsePositiveMatch:
    """A detected false positive pattern."""

    pattern: FalsePositivePattern
    confidence: float
    message: str
    suggestion: str


@dataclass
class EnhancedError:
    """An error with enhanced context and false positive analysis."""

    raw_error: str
    classified: ClassifiedError | None = None
    false_positive: FalsePositiveMatch | None = None
    is_likely_false_positive: bool = False
    enhanced_message: str = ""
    next_steps: list[str] = field(default_factory=list)


# Known false positive patterns
_FALSE_POSITIVE_PATTERNS: list[tuple[FalsePositivePattern, float, re.Pattern]] = [
    (
        FalsePositivePattern.TIMING_FLAKY,
        0.80,
        re.compile(
            r"""
            (?:
                (?:timeout|timed?\s*out)
                |
                (?:ConnectionRefusedError|ConnectionResetError)
                |
                (?:temporary\s+failure)
                |
                (?:ECONNREFUSED|ETIMEDOUT|ENETUNREACH)
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        FalsePositivePattern.NETWORK_FLAKY,
        0.75,
        re.compile(
            r"""
            (?:
                (?:network|internet)\s*(?:error|issue|failure|timeout)?
                |
                (?:DNS|dns)\s*(?:lookup|resolution)\s*(?:failed|error)?
                |
                (?:Could\s+not\s+resolve|Name\s+or\s+service\s+not\s+known)
                |
                (?:Remote\s+end\s+closed|Connection\s+closed)
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        FalsePositivePattern.KNOWN_BROKEN,
        0.90,
        re.compile(
            r"""
            (?:
                (?:xfail|strict)\s*-\s*(?:xfail|expected\s+to\s+fail)
                |
                (?:skip|skipped)\s*-\s*(?:reason|condition)
                |
                (?:@pytest\.mark\.skip|@pytest\.mark\.xfail)
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        FalsePositivePattern.ENV_SPECIFIC,
        0.70,
        re.compile(
            r"""
            (?:
                (?:CI|ci)\s*(?:only|environment)?
                |
                (?:platform|system)\s*(?:specific|dependent)?
                |
                (?:Windows|Linux|macOS)\s*(?:only|specific)?
                |
                (?:PYTHONPATH|PATH)\s*(?:issue|error|not\s+set)?
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
]


def detect_false_positive(error_text: str) -> FalsePositiveMatch | None:
    """Detect if an error matches a known false positive pattern.

    Args:
        error_text: Raw error text

    Returns:
        FalsePositiveMatch if detected, None otherwise
    """
    best_match: tuple[FalsePositivePattern, float, str] | None = None

    for pattern_enum, confidence, pattern in _FALSE_POSITIVE_PATTERNS:
        match = pattern.search(error_text)
        if match and (best_match is None or confidence > best_match[1]):
            best_match = (pattern_enum, confidence, match.group(0))

    if best_match is None:
        return None

    pattern_enum, confidence, matched_text = best_match

    suggestions = {
        FalsePositivePattern.TIMING_FLAKY: [
            "Retry the CI job - timing issues are often transient",
            "Check if the test has a timeout that's too aggressive",
            "Consider increasing test timeout for slow CI environments",
        ],
        FalsePositivePattern.NETWORK_FLAKY: [
            "Verify network connectivity in CI environment",
            "Check if external services are accessible",
            "Retry the CI job - network issues are often transient",
        ],
        FalsePositivePattern.KNOWN_BROKEN: [
            "Review test markers (xfail, skip)",
            "Check if test is expected to fail",
            "Update test if the underlying issue is fixed",
        ],
        FalsePositivePattern.ENV_SPECIFIC: [
            "Verify CI environment configuration",
            "Check for environment-specific dependencies",
            "Ensure CI and local environments match",
        ],
    }

    return FalsePositiveMatch(
        pattern=pattern_enum,
        confidence=confidence,
        message=f"Detected '{pattern_enum.value}' pattern: {matched_text}",
        suggestion=suggestions.get(pattern_enum, ["Review error in context"])[0],
    )


def enhance_error(error_text: str) -> EnhancedError:
    """Enhance a raw error with classification and false positive detection.

    Args:
        error_text: Raw error text from CI

    Returns:
        EnhancedError with full context
    """
    enhanced = EnhancedError(raw_error=error_text)

    # Classify if classifier is available
    if CLASSIFICATION_AVAILABLE:
        classified_list = classify_ci_output(error_text)
        if classified_list:
            enhanced.classified = classified_list[0]

    # Check for false positives
    fp_match = detect_false_positive(error_text)
    if fp_match:
        enhanced.false_positive = fp_match
        enhanced.is_likely_false_positive = fp_match.confidence >= 0.75

    # Build enhanced message
    if enhanced.classified:
        cat = enhanced.classified.category.value.upper()
        enhanced.enhanced_message = f"[{cat}] {enhanced.classified.message}"
    else:
        enhanced.enhanced_message = error_text.strip()

    # Add false positive context
    if enhanced.false_positive and enhanced.is_likely_false_positive:
        enhanced.enhanced_message += (
            f"\n⚠️  Likely false positive: {enhanced.false_positive.message}"
        )

    # Build next steps
    enhanced.next_steps = []

    if enhanced.is_likely_false_positive and enhanced.false_positive:
        enhanced.next_steps.append(enhanced.false_positive.suggestion)

    if enhanced.classified:
        for suggestion in enhanced.classified.fix_suggestions[:3]:
            enhanced.next_steps.append(suggestion)

    return enhanced


def analyze_ci_output(output: str) -> list[EnhancedError]:
    """Analyze CI output and return enhanced errors.

    Args:
        output: Raw CI output text

    Returns:
        List of EnhancedError objects
    """
    # Split into error blocks
    error_blocks = re.split(
        r"\n(?=ERROR|FAILED|Traceback|===|\Z)", output, flags=re.IGNORECASE
    )

    errors: list[EnhancedError] = []
    for block in error_blocks:
        block = block.strip()
        if not block:
            continue

        # Skip success indicators
        if re.search(r"^(PASSED|OK|success|All checks passed)", block, re.IGNORECASE):
            continue

        enhanced = enhance_error(block)
        if enhanced.classified or len(block) > 50:
            errors.append(enhanced)

    return errors


def format_enhanced_report(
    errors: list[EnhancedError], diagnostics: DiagnosticReport | None = None
) -> str:
    """Format enhanced error report.

    Args:
        errors: List of enhanced errors
        diagnostics: Optional diagnostic report

    Returns:
        Formatted report string
    """
    lines = [
        "=" * 70,
        "LOCAL CI ACCURACY IMPROVEMENTS REPORT",
        "=" * 70,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    # Add diagnostics if available
    if diagnostics:
        lines.append("-" * 70)
        lines.append("ENVIRONMENT DIAGNOSTICS")
        lines.append("-" * 70)
        lines.append(f"Python: {diagnostics.python_version}")
        lines.append(f"Platform: {diagnostics.platform}")
        lines.append(f"Git: {diagnostics.git_branch} (dirty={diagnostics.git_dirty})")
        lines.append(
            f"Checks: {diagnostics.summary['passed']} passed, {diagnostics.summary['failed']} failed"
        )
        lines.append("")

    # Error analysis
    lines.append("-" * 70)
    lines.append("ERROR ANALYSIS")
    lines.append("-" * 70)

    if not errors:
        lines.append("✓ No errors detected in CI output")
    else:
        # Count false positives
        fp_count = sum(1 for e in errors if e.is_likely_false_positive)
        real_errors = [e for e in errors if not e.is_likely_false_positive]

        lines.append(f"Total errors: {len(errors)}")
        lines.append(f"  - Likely false positives: {fp_count}")
        lines.append(f"  - Real failures: {len(real_errors)}")
        lines.append("")

        # Group by category
        by_category: dict[str, list[EnhancedError]] = {}
        for error in errors:
            if error.classified:
                cat = error.classified.category.value
            else:
                cat = "unknown"
            by_category.setdefault(cat, []).append(error)

        for cat in sorted(by_category.keys()):
            cat_errors = by_category[cat]
            lines.append(f"## {cat.upper()} ({len(cat_errors)} errors)")

            for error in cat_errors:
                lines.append(f"  Message: {error.enhanced_message[:70]}...")

                if error.is_likely_false_positive:
                    lines.append("  ⚠️  FALSE POSITIVE")
                else:
                    lines.append("  ✗ FAILURE")

                if error.next_steps:
                    lines.append("  Next steps:")
                    for step in error.next_steps[:2]:
                        lines.append(f"    → {step}")
                lines.append("")

    # Summary
    lines.append("=" * 70)
    lines.append("SUMMARY")
    lines.append("=" * 70)

    if not errors:
        lines.append("✓ All CI checks passed")
    else:
        real_failures = [e for e in errors if not e.is_likely_false_positive]
        if real_failures:
            lines.append(f"✗ {len(real_failures)} real failures detected")
            lines.append("  Fix the failures above and re-run CI")
        else:
            lines.append(f"⚠️  {len(errors)} potential false positives detected")
            lines.append("  Review each error and retry CI if appropriate")

    lines.append("")
    return "\n".join(lines)


def run_local_ci_checks() -> tuple[bool, str]:
    """Run local CI checks using pre_push_gate if available.

    Returns:
        Tuple of (success, output)
    """
    pre_push_script = Path(__file__).parent / "ci" / "pre_push_gate.py"
    if not pre_push_script.exists():
        return True, "pre_push_gate.py not found, skipping local CI"

    try:
        result = subprocess.run(
            [sys.executable, str(pre_push_script)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = result.stdout + "\n" + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Local CI timed out"
    except Exception as e:
        return False, f"Error running local CI: {str(e)}"


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Local CI Accuracy Improvements - Enhanced error reporting"
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Read CI output from file instead of running CI",
    )
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Run environment diagnostics only",
    )
    parser.add_argument(
        "--run-ci",
        action="store_true",
        help="Run local CI checks",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--no-classify",
        action="store_true",
        help="Skip error classification",
    )
    args = parser.parse_args()

    # Run diagnostics
    diagnostics = None
    try:
        diagnostics = run_all_checks()
    except Exception as e:
        print(f"Warning: Could not run diagnostics: {e}", file=sys.stderr)

    # Run local CI if requested
    ci_output = ""
    ci_success = True
    if args.run_ci:
        ci_success, ci_output = run_local_ci_checks()

    # Read input if provided
    if args.input:
        if not args.input.exists():
            print(f"Error: Input file not found: {args.input}")
            return 1
        ci_output = args.input.read_text()
        ci_success = False  # If reading from file, assume we're analyzing a failure

    # Run diagnostics only
    if args.check_env:
        if diagnostics:
            print(format_report_text(diagnostics))
        else:
            print("Diagnostics not available")
        return 0

    # Analyze CI output
    if ci_output:
        if args.no_classify or not CLASSIFICATION_AVAILABLE:
            errors = []
        else:
            errors = analyze_ci_output(ci_output)

        report = format_enhanced_report(errors, diagnostics)

        if args.json:
            import json

            output_data = {
                "success": ci_success,
                "errors": [
                    {
                        "raw": e.raw_error,
                        "classified": e.classified.category.value
                        if e.classified
                        else None,
                        "is_false_positive": e.is_likely_false_positive,
                        "next_steps": e.next_steps,
                    }
                    for e in errors
                ],
                "diagnostics": diagnostics.summary if diagnostics else None,
            }
            print(json.dumps(output_data, indent=2))
        else:
            print(report)
    else:
        if diagnostics:
            print(format_report_text(diagnostics))
        print("No CI output to analyze. Use --run-ci or --input")

    return 0 if ci_success else 1


if __name__ == "__main__":
    sys.exit(main())
