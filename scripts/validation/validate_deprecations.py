#!/usr/bin/env python3
"""
Validate deprecation warnings in the codebase.

This script checks for deprecation warnings in Python files and validates
against a baseline to prevent new deprecation warnings from being introduced.

Exit codes:
    0 - All validations passed (no new deprecation warnings)
    1 - New deprecation warnings found (fails the gate)
    2 - Configuration or file errors

Usage:
    python scripts/validation/validate_deprecations.py --check
    python scripts/validation/validate_deprecations.py --update-baseline
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Configuration
DEFAULT_BASELINE_PATH = Path("docs/baselines/deprecation-baseline.json")
BASELINE_PATH = Path(os.environ.get("DEPRECATION_BASELINE_PATH", DEFAULT_BASELINE_PATH))

# Directories to scan (relative to repo root)
SCAN_DIRECTORIES = ["src", "scripts", "tests"]

# File patterns to include
INCLUDE_PATTERNS = ["*.py"]

# Deprecation warning categories to check
DEPRECATION_CATEGORIES = [
    "DeprecationWarning",
    "PendingDeprecationWarning",
    "FutureWarning",
]

CHANGE_SCOPE_HELPER = Path("scripts/ci/ci_change_scope.py")


@dataclass
class DeprecationFinding:
    """Represents a single deprecation warning finding."""

    file: str
    line: int
    category: str
    message: str
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "category": self.category,
            "message": self.message,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeprecationFinding:
        return cls(
            file=data.get("file", ""),
            line=data.get("line", 0),
            category=data.get("category", ""),
            message=data.get("message", ""),
            source=data.get("source", ""),
        )

    def __hash__(self) -> int:
        return hash((self.file, self.line, self.category, self.message))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DeprecationFinding):
            return False
        return (
            self.file == other.file
            and self.line == other.line
            and self.category == other.category
            and self.message == other.message
        )


@dataclass
class ValidationResult:
    """Container for validation results."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings: list[DeprecationFinding] = field(default_factory=list)
    new_findings: list[DeprecationFinding] = field(default_factory=list)
    baseline_count: int = 0

    def add_error(self, message: str) -> None:
        """Add an error to the result."""
        self.errors.append(f"ERROR: {message}")
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning to the result."""
        self.warnings.append(f"WARNING: {message}")

    def print_report(self, verbose: bool = False) -> None:
        """Print validation report."""
        print("=" * 70)
        print("DEPRECATION WARNING VALIDATION REPORT")
        print("=" * 70)

        if self.warnings:
            print("\nWarnings:")
            for msg in self.warnings:
                print(f"  {msg}")

        if self.errors:
            print("\nErrors:")
            for msg in self.errors:
                print(f"  {msg}")

        print(f"\nBaseline findings: {self.baseline_count}")
        print(f"Current findings: {len(self.findings)}")
        print(f"New findings: {len(self.new_findings)}")

        if self.new_findings:
            print("\n" + "=" * 70)
            print("NEW DEPRECATION WARNINGS (BLOCKING)")
            print("=" * 70)
            for finding in self.new_findings:
                print(f"\n  File: {finding.file}:{finding.line}")
                print(f"  Category: {finding.category}")
                print(f"  Message: {finding.message}")
                if finding.source and verbose:
                    print(f"  Source: {finding.source}")

        if self.findings and verbose:
            print("\n" + "=" * 70)
            print("ALL CURRENT FINDINGS")
            print("=" * 70)
            for finding in self.findings:
                print(f"\n  File: {finding.file}:{finding.line}")
                print(f"  Category: {finding.category}")
                print(f"  Message: {finding.message}")

        print("\n" + "=" * 70)
        if self.valid:
            print("RESULT: PASS - No new deprecation warnings")
        else:
            print("RESULT: FAIL - New deprecation warnings detected")
        print("=" * 70)


def load_baseline(baseline_path: Path) -> set[DeprecationFinding]:
    """Load baseline findings from file."""
    if not baseline_path.exists():
        return set()

    try:
        with open(baseline_path, encoding="utf-8") as f:
            data = json.load(f)

        findings = set()
        for item in data.get("findings", []):
            findings.add(DeprecationFinding.from_dict(item))

        return findings
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Warning: Could not load baseline: {e}", file=sys.stderr)
        return set()


def save_baseline(
    baseline_path: Path,
    findings: list[DeprecationFinding],
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Save findings to baseline file."""
    try:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0.0",
            "generated_at": subprocess.check_output(
                ["date", "-Iseconds"], text=True
            ).strip(),
            "count": len(findings),
            "findings": [f.to_dict() for f in findings],
        }

        if metadata:
            data["metadata"] = metadata

        with open(baseline_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return True
    except Exception as e:
        print(f"Error saving baseline: {e}", file=sys.stderr)
        return False


def collect_deprecation_warnings(
    directories: list[str] | None = None,
    changed_files_only: bool = False,
) -> list[DeprecationFinding]:
    """Collect deprecation warnings by running Python with warnings enabled."""
    findings: list[DeprecationFinding] = []

    if directories is None:
        directories = SCAN_DIRECTORIES

    # Filter to only existing directories
    existing_dirs = [d for d in directories if Path(d).exists()]

    if not existing_dirs:
        print("Warning: No valid directories to scan", file=sys.stderr)
        return findings

    # Collect Python files to check
    python_files: list[Path] = []
    for directory in existing_dirs:
        dir_path = Path(directory)
        for pattern in INCLUDE_PATTERNS:
            python_files.extend(dir_path.rglob(pattern))

    # Limit to changed files if requested
    if changed_files_only:
        changed = get_changed_files()
        python_files = [
            f for f in python_files if str(f) in changed or f.name in changed
        ]

    # For each file, try to collect warnings
    # This is a simplified approach - in production, you'd use pytest or import
    for pyfile in python_files:
        # Skip __pycache__ and hidden files
        if "__pycache__" in str(pyfile) or pyfile.name.startswith("."):
            continue

        # Check for deprecation patterns in source
        try:
            with open(pyfile, encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # Check for warn() calls with deprecation
                if "warn(" in line or "warnings.warn" in line:
                    for category in DEPRECATION_CATEGORIES:
                        if category in line or category.replace("Warning", "") in line:
                            findings.append(
                                DeprecationFinding(
                                    file=str(pyfile),
                                    line=i,
                                    category=category,
                                    message=line.strip(),
                                    source="source",
                                )
                            )

                # Check for deprecated decorators (but not within string literals or comments about them)
                stripped = line.strip()
                if stripped.startswith("@deprecated") or stripped.startswith(
                    "@Deprecation"
                ):
                    findings.append(
                        DeprecationFinding(
                            file=str(pyfile),
                            line=i,
                            category="DeprecationWarning",
                            message=f"Deprecated decorator found: {stripped}",
                            source="source",
                        )
                    )

        except (OSError, UnicodeDecodeError) as e:
            print(f"Warning: Could not read {pyfile}: {e}", file=sys.stderr)

    return findings


def _resolve_base_ref() -> str | None:
    """Resolve a usable base ref for git diffs."""
    candidates = [
        "refs/remotes/origin/main",
        "origin/main",
        "main",
        "HEAD~1",
    ]
    for candidate in candidates:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", candidate],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return candidate
    return None


def get_changed_files() -> list[str]:
    """Get list of changed files from git or CI metadata."""
    env_files = os.environ.get("CI_PIPELINE_FILES", "").strip()
    if env_files:
        try:
            payload = json.loads(env_files)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            files = [str(item).strip() for item in payload if str(item).strip()]
            if files:
                return files

    if CHANGE_SCOPE_HELPER.exists():
        helper_base_ref = _resolve_base_ref() or "HEAD~1"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(CHANGE_SCOPE_HELPER),
                    "--base-ref",
                    helper_base_ref,
                    "--mode",
                    "summary",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            changed = payload.get("changed_files", [])
            if isinstance(changed, list):
                files = [str(item).strip() for item in changed if str(item).strip()]
                if files:
                    return files
        except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
            pass

    try:
        resolved_base_ref: str | None = _resolve_base_ref()
        if resolved_base_ref is None:
            return []
        diff_args = ["git", "diff", "--name-only"]
        if resolved_base_ref == "HEAD~1":
            diff_args.append(f"{resolved_base_ref}..HEAD")
        else:
            diff_args.extend([resolved_base_ref, "HEAD"])
        result = subprocess.run(
            diff_args,
            capture_output=True,
            text=True,
            check=True,
        )
        return [line for line in result.stdout.strip().split("\n") if line]
    except subprocess.CalledProcessError:
        return []


def validate_deprecations(
    baseline_path: Path | None = None,
    changed_files_only: bool = False,
    verbose: bool = False,
) -> ValidationResult:
    """Validate deprecations against baseline."""
    result = ValidationResult()

    if baseline_path is None:
        baseline_path = BASELINE_PATH

    # Load baseline
    baseline_findings = load_baseline(baseline_path)
    result.baseline_count = len(baseline_findings)

    if verbose:
        print(
            f"Loaded {len(baseline_findings)} findings from baseline: {baseline_path}"
        )

    # Collect current findings
    result.findings = collect_deprecation_warnings(
        changed_files_only=changed_files_only
    )

    if verbose:
        print(f"Found {len(result.findings)} current deprecation warnings")

    # Identify new findings (not in baseline)
    current_set = set(result.findings)
    new_findings = current_set - baseline_findings
    result.new_findings = list(new_findings)

    if new_findings:
        result.valid = False
        result.add_error(
            f"Found {len(new_findings)} new deprecation warning(s) not in baseline"
        )

    return result


def update_baseline(
    baseline_path: Path | None = None,
    verbose: bool = False,
) -> bool:
    """Update the baseline with current findings."""
    if baseline_path is None:
        baseline_path = BASELINE_PATH

    findings = collect_deprecation_warnings()

    metadata = {
        "tool_version": "1.0.0",
        "python_version": sys.version,
    }

    if save_baseline(baseline_path, findings, metadata):
        if verbose:
            print(f"Updated baseline at {baseline_path} with {len(findings)} findings")
        return True
    return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate deprecation warnings in the codebase"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for new deprecation warnings (default)",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Update the baseline with current findings",
    )
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=None,
        help=f"Path to baseline file (default: {DEFAULT_BASELINE_PATH})",
    )
    parser.add_argument(
        "--changed-files-only",
        action="store_true",
        help="Only check changed files",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    baseline_path = args.baseline_path or BASELINE_PATH

    if args.update_baseline:
        if update_baseline(baseline_path, args.verbose):
            return 0
        return 2

    # Default: check mode
    result = validate_deprecations(
        baseline_path=baseline_path,
        changed_files_only=args.changed_files_only,
        verbose=args.verbose,
    )

    result.print_report(verbose=args.verbose)

    if result.valid:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
