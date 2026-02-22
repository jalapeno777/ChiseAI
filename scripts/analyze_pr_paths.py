#!/usr/bin/env python3
"""
CLI tool for analyzing PR file paths.

Usage:
    python scripts/analyze_pr_paths.py --files file1.py file2.md
    python scripts/analyze_pr_paths.py --pr 123 --commit abc123
    python scripts/analyze_pr_paths.py --batch --input files.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autonomous_git.path_analyzer import (
    RiskLevel,
    analyze_paths,
)


def format_result(result) -> str:
    """Format analysis result for display."""
    lines = [
        "=" * 60,
        "PATH ANALYSIS RESULT",
        "=" * 60,
        f"Risk Level: {result.risk_level.value.upper()}",
        f"Confidence: {result.confidence:.0%}",
        f"Files Analyzed: {len(result.files)}",
        "-" * 60,
        "Reasoning:",
        f"  {result.reasoning}",
    ]

    if result.pr_number:
        lines.append(f"PR Number: #{result.pr_number}")
    if result.commit_sha:
        lines.append(f"Commit: {result.commit_sha[:8]}")
    if result.timestamp:
        lines.append(f"Timestamp: {result.timestamp}")
    if result.analysis_duration_ms:
        lines.append(f"Analysis Time: {result.analysis_duration_ms:.1f}ms")

    lines.extend(
        [
            "-" * 60,
            "File Classifications:",
        ]
    )

    for fc in result.file_classifications:
        icon = (
            "✓"
            if fc.risk_level == RiskLevel.SAFE
            else "⚠" if fc.risk_level == RiskLevel.MEDIUM_RISK else "✗"
        )
        lines.append(f"  {icon} {fc.path}")
        lines.append(
            f"     Risk: {fc.risk_level.value} (confidence: {fc.confidence:.0%})"
        )
        if fc.pattern_matched:
            lines.append(f"     Pattern: {fc.pattern_matched}")
        if fc.semantic_flags:
            lines.append(f"     Flags: {', '.join(fc.semantic_flags)}")

    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze PR file paths for risk classification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --files docs/README.md tests/test_foo.py
  %(prog)s --files src/main.py --content '{"src/main.py": "import os\\n"}'
  %(prog)s --pr 123 --commit abc123def456
  %(prog)s --batch --input files.json --output result.json
        """,
    )

    parser.add_argument("--files", nargs="+", help="List of file paths to analyze")
    parser.add_argument("--pr", type=int, help="PR number for caching")
    parser.add_argument("--commit", help="Commit SHA for caching")
    parser.add_argument(
        "--content", help="JSON dict of file path -> content for semantic analysis"
    )
    parser.add_argument("--config", help="Path to pattern config YAML")
    parser.add_argument(
        "--batch", action="store_true", help="Batch mode: read files from --input"
    )
    parser.add_argument("--input", help="Input JSON file (for batch mode)")
    parser.add_argument("--output", help="Output JSON file (default: print to stdout)")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    parser.add_argument(
        "--json", action="store_true", help="Output raw JSON instead of formatted text"
    )
    parser.add_argument(
        "--threshold",
        choices=["safe", "medium", "complex"],
        help="Only report if risk level is at or above threshold",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    args = parser.parse_args()

    # Validate arguments
    if not args.batch and not args.files:
        parser.error("--files is required unless using --batch mode")

    if args.batch and not args.input:
        parser.error("--input is required when using --batch mode")

    # Load file contents if provided
    file_contents = None
    if args.content:
        try:
            file_contents = json.loads(args.content)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --content: {e}", file=sys.stderr)
            sys.exit(1)

    # Load files for batch mode
    files = args.files or []
    if args.batch:
        try:
            with open(args.input, "r") as f:
                batch_data = json.load(f)
                if isinstance(batch_data, list):
                    files = batch_data
                elif isinstance(batch_data, dict) and "files" in batch_data:
                    files = batch_data["files"]
                    if "contents" in batch_data:
                        file_contents = batch_data["contents"]
                else:
                    print(
                        "Error: Invalid input format. Expected list or object with 'files' key",
                        file=sys.stderr,
                    )
                    sys.exit(1)
        except FileNotFoundError:
            print(f"Error: Input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in input file: {e}", file=sys.stderr)
            sys.exit(1)

    # Run analysis
    try:
        result = analyze_paths(
            files=files,
            pr_number=args.pr,
            commit_sha=args.commit,
            file_contents=file_contents,
            config_path=args.config,
            use_cache=not args.no_cache,
        )
    except Exception as e:
        print(f"Error during analysis: {e}", file=sys.stderr)
        sys.exit(1)

    # Check threshold
    if args.threshold:
        threshold_level = RiskLevel(args.threshold)
        if result.risk_level.priority < threshold_level.priority:
            print(
                f"Risk level {result.risk_level.value} is below threshold {args.threshold}"
            )
            sys.exit(0)

    # Output result
    if args.json:
        output = json.dumps(result.to_dict(), indent=2)
    else:
        output = format_result(result)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Result written to {args.output}")
    else:
        print(output)

    # Exit with appropriate code
    if result.risk_level == RiskLevel.COMPLEX:
        sys.exit(2)
    elif result.risk_level == RiskLevel.MEDIUM_RISK:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
