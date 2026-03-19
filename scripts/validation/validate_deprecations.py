#!/usr/bin/env python3
"""
Deprecation Warning Validation Script

This script validates Python deprecation warnings from pytest output against a baseline.
It supports two modes:
  --baseline: Capture current warnings and save to baseline JSON
  --check: Compare current warnings against baseline and exit with error on new warnings

Usage:
  python3 scripts/validation/validate_deprecations.py --baseline
  python3 scripts/validation/validate_deprecations.py --check
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple


@dataclass(frozen=True)
class DeprecationWarning:
    """Represents a single deprecation warning."""

    file_path: str
    line_number: int
    message: str
    warning_type: str

    def to_dict(self) -> Dict:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "message": self.message,
            "warning_type": self.warning_type,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DeprecationWarning":
        return cls(
            file_path=data["file_path"],
            line_number=data["line_number"],
            message=data["message"],
            warning_type=data["warning_type"],
        )

    def __hash__(self):
        return hash((self.file_path, self.line_number, self.message, self.warning_type))


def normalize_warning_message(message: str) -> str:
    """
    Normalize warning message for comparison.

    Removes variable content like PIDs, timestamps, etc. that change between runs.
    """
    # Remove PIDs (e.g., "pid=12345" or "(pid=12345)")
    message = re.sub(r"\(?pid=\d+\)?", "(pid=<PID>)", message)
    return message


def parse_warning_line(line: str) -> DeprecationWarning | None:
    """
    Parse a single warning line from pytest output.

    Expected format:
      /path/to/file.py:123: DeprecationWarning: message here

    Returns None if the line doesn't match the expected format.
    """
    # Pattern to match: /path/to/file.py:123: DeprecationWarning: message
    pattern = r"^(.*?):(\d+):\s*(\w+Warning):\s*(.+)$"
    match = re.match(pattern, line.strip())

    if not match:
        return None

    file_path = match.group(1)
    line_number = int(match.group(2))
    warning_type = match.group(3)
    message = normalize_warning_message(match.group(4).strip())

    return DeprecationWarning(
        file_path=file_path,
        line_number=line_number,
        message=message,
        warning_type=warning_type,
    )


def run_pytest_and_capture_warnings(
    test_path: str = "tests/",
    timeout: int = 300,
) -> List[DeprecationWarning]:
    """
    Run pytest with warnings enabled and capture all deprecation warnings.

    Args:
        test_path: Path to test directory or file
        timeout: Maximum time to wait for pytest (seconds)

    Returns:
        List of DeprecationWarning objects
    """
    cmd = [
        "python3",
        "-m",
        "pytest",
        test_path,
        "-W",
        "always",  # Show all warnings
        "--tb=no",  # No traceback
        "-q",  # Quiet mode
    ]

    print(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"ERROR: pytest timed out after {timeout} seconds", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("ERROR: pytest not found. Is it installed?", file=sys.stderr)
        sys.exit(1)

    warnings: List[DeprecationWarning] = []

    # Parse stderr and stdout for warnings
    for line in (result.stdout + result.stderr).split("\n"):
        warning = parse_warning_line(line)
        if warning:
            warnings.append(warning)

    return warnings


def load_baseline(baseline_path: Path) -> Set[DeprecationWarning]:
    """Load baseline warnings from JSON file."""
    if not baseline_path.exists():
        print(f"ERROR: Baseline file not found: {baseline_path}", file=sys.stderr)
        sys.exit(1)

    with open(baseline_path, "r") as f:
        data = json.load(f)

    return {DeprecationWarning.from_dict(w) for w in data.get("warnings", [])}


def save_baseline(
    warnings: List[DeprecationWarning],
    baseline_path: Path,
    metadata: Dict | None = None,
) -> None:
    """Save warnings to baseline JSON file."""
    baseline_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "1.0",
        "warning_count": len(warnings),
        "warnings": [w.to_dict() for w in warnings],
    }

    if metadata:
        data["metadata"] = metadata

    with open(baseline_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Baseline saved to: {baseline_path}")
    print(f"Total warnings captured: {len(warnings)}")


def compare_warnings(
    current: List[DeprecationWarning],
    baseline: Set[DeprecationWarning],
) -> Tuple[List[DeprecationWarning], List[DeprecationWarning]]:
    """
    Compare current warnings against baseline.

    Returns:
        Tuple of (new_warnings, resolved_warnings)
    """
    current_set = set(current)

    new_warnings = list(current_set - baseline)
    resolved_warnings = list(baseline - current_set)

    return new_warnings, resolved_warnings


def check_command(
    baseline_path: Path,
    test_path: str = "tests/",
) -> int:
    """
    Check current warnings against baseline.

    Returns:
        Exit code (0 = no new warnings, 1 = new warnings found)
    """
    print("Loading baseline...")
    baseline = load_baseline(baseline_path)
    print(f"Baseline contains {len(baseline)} warnings")

    print("\nRunning pytest to capture current warnings...")
    current = run_pytest_and_capture_warnings(test_path)
    print(f"Current run captured {len(current)} warnings")

    new_warnings, resolved_warnings = compare_warnings(current, baseline)

    print("\n" + "=" * 60)
    print("DEPRECATION WARNING CHECK RESULTS")
    print("=" * 60)

    if resolved_warnings:
        print(f"\n✓ {len(resolved_warnings)} warnings have been resolved:")
        for w in sorted(resolved_warnings, key=lambda x: (x.file_path, x.line_number)):
            print(
                f"  - {w.file_path}:{w.line_number}: {w.warning_type}: {w.message[:60]}..."
            )

    if new_warnings:
        print(f"\n✗ {len(new_warnings)} NEW warnings found:")
        for w in sorted(new_warnings, key=lambda x: (x.file_path, x.line_number)):
            print(
                f"  - {w.file_path}:{w.line_number}: {w.warning_type}: {w.message[:60]}..."
            )
        print("\nThese new warnings must be addressed or added to the baseline.")
        return 1

    print(f"\n✓ All {len(current)} warnings match the baseline.")
    print("No new deprecation warnings detected.")
    return 0


def baseline_command(
    baseline_path: Path,
    test_path: str = "tests/",
) -> int:
    """
    Create a new baseline from current warnings.

    Returns:
        Exit code (0 = success)
    """
    print("Running pytest to capture current warnings...")
    warnings = run_pytest_and_capture_warnings(test_path)

    metadata = {
        "command": f"pytest {test_path} -W always --tb=no -q",
        "warning_count": len(warnings),
    }

    save_baseline(warnings, baseline_path, metadata)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Python deprecation warnings against a baseline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --baseline                    # Create baseline from current warnings
  %(prog)s --check                       # Check against existing baseline
  %(prog)s --baseline --test-path tests/unit  # Use custom test path
        """,
    )

    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Create a new baseline from current warnings",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check current warnings against baseline (exits 1 on new warnings)",
    )
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=Path("docs/evidence/TECH-001-A-baseline.json"),
        help="Path to baseline JSON file (default: docs/evidence/TECH-001-A-baseline.json)",
    )
    parser.add_argument(
        "--test-path",
        type=str,
        default="tests/",
        help="Path to test directory or file (default: tests/)",
    )

    args = parser.parse_args()

    if not args.baseline and not args.check:
        parser.error("Must specify either --baseline or --check")

    if args.baseline and args.check:
        parser.error("Cannot specify both --baseline and --check")

    if args.baseline:
        return baseline_command(args.baseline_path, args.test_path)
    else:
        return check_command(args.baseline_path, args.test_path)


if __name__ == "__main__":
    sys.exit(main())
