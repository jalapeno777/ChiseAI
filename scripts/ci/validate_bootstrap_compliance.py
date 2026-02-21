#!/usr/bin/env python3
"""Validate bootstrap compliance for scripts/**/*.py entrypoints.

This script enforces that all Python scripts in scripts/ that use environment
variables (os.getenv, os.environ) properly import and call bootstrap() first.

Exit codes:
    0 - All scripts compliant
    1 - Violations found
    2 - Internal error (e.g., file system issues)

ST-CI-005: Bootstrap Compliance CI Validation
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

# Scripts directory path
SCRIPTS_DIR = Path(__file__).parent.parent


def get_all_scripts() -> list[Path]:
    """Get all Python scripts in the scripts directory.

    Returns:
        Sorted list of Path objects for all .py files excluding __init__.py
    """
    scripts = []
    for root, dirs, files in os.walk(SCRIPTS_DIR):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                scripts.append(Path(root) / file)
    return sorted(scripts)


def has_bootstrap_import(tree: ast.AST) -> bool:
    """Check if AST has bootstrap import.

    Detects the following patterns:
    - from config.bootstrap import bootstrap
    - from config.bootstrap import bootstrap, format_provider_status
    - from config import bootstrap (alternative import style)

    Args:
        tree: Parsed AST of the script

    Returns:
        True if bootstrap import is found
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # Check for: from config.bootstrap import bootstrap
            if node.module == "config.bootstrap":
                for alias in node.names:
                    if alias.name == "bootstrap":
                        return True
            # Check for: from config import bootstrap (alternative)
            if node.module == "config":
                for alias in node.names:
                    if alias.name == "bootstrap":
                        return True
    return False


def has_bootstrap_call(tree: ast.AST) -> bool:
    """Check if AST has bootstrap() call.

    Detects direct calls to bootstrap() function.
    Does NOT count references or assignments.

    Args:
        tree: Parsed AST of the script

    Returns:
        True if bootstrap() call is found
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Direct call: bootstrap()
            if isinstance(node.func, ast.Name) and node.func.id == "bootstrap":
                return True
    return False


def get_first_os_getenv_call(tree: ast.AST) -> int | None:
    """Get the line number of the first os.getenv() or os.environ.get().

    Args:
        tree: Parsed AST of the script

    Returns:
        Line number of first os.getenv call, or None if not found
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check for os.getenv() or os.environ.get()
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "getenv":
                    if isinstance(node.func.value, ast.Name):
                        if node.func.value.id == "os":
                            return node.lineno
                    # os.environ.get()
                    if isinstance(node.func.value, ast.Attribute):
                        if node.func.value.attr == "environ":
                            return node.lineno
    return None


def get_first_os_environ_access(tree: ast.AST) -> int | None:
    """Get the line number of the first os.environ access.

    Args:
        tree: Parsed AST of the script

    Returns:
        Line number of first os.environ access, or None if not found
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr == "environ":
                if isinstance(node.value, ast.Name):
                    if node.value.id == "os":
                        return node.lineno
    return None


def uses_os_getenv(tree: ast.AST) -> bool:
    """Check if script uses os.getenv() or os.environ.

    Args:
        tree: Parsed AST of the script

    Returns:
        True if script uses environment variables
    """
    return (
        get_first_os_getenv_call(tree) is not None
        or get_first_os_environ_access(tree) is not None
    )


class Violation:
    """Represents a bootstrap compliance violation."""

    def __init__(
        self,
        script_path: Path,
        violation_type: str,
        message: str,
        line_number: int | None = None,
    ) -> None:
        self.script_path = script_path
        self.violation_type = violation_type
        self.message = message
        self.line_number = line_number

    def __str__(self) -> str:
        rel_path = self.script_path.relative_to(SCRIPTS_DIR.parent)
        line_info = f":{self.line_number}" if self.line_number else ""
        return f"ERROR: {rel_path}{line_info} {self.message}"


class ComplianceResult:
    """Container for compliance check results."""

    def __init__(self) -> None:
        self.violations: list[Violation] = []
        self.skipped: list[tuple[Path, str]] = []
        self.compliant: list[Path] = []
        self.no_env_usage: list[Path] = []

    def add_violation(self, violation: Violation) -> None:
        self.violations.append(violation)

    def add_skipped(self, script_path: Path, reason: str) -> None:
        self.skipped.append((script_path, reason))

    def add_compliant(self, script_path: Path) -> None:
        self.compliant.append(script_path)

    def add_no_env_usage(self, script_path: Path) -> None:
        self.no_env_usage.append(script_path)

    @property
    def is_compliant(self) -> bool:
        return len(self.violations) == 0

    def print_report(self, verbose: bool = False) -> None:
        """Print compliance check report."""
        # Print violations first (most important)
        for violation in self.violations:
            print(str(violation), file=sys.stderr)

        if verbose:
            # Print summary
            print("\n" + "=" * 60)
            print("BOOTSTRAP COMPLIANCE REPORT")
            print("=" * 60)
            print(
                f"Total scripts analyzed: {len(self.compliant) + len(self.no_env_usage) + len(self.violations)}"
            )
            print(f"Compliant (uses env + bootstrap): {len(self.compliant)}")
            print(f"No env usage (exempt): {len(self.no_env_usage)}")
            print(f"Violations: {len(self.violations)}")
            print(f"Skipped (syntax errors): {len(self.skipped)}")
            print("=" * 60)

            if self.compliant:
                print("\nCompliant scripts:")
                for script_path in sorted(self.compliant):
                    rel_path = script_path.relative_to(SCRIPTS_DIR.parent)
                    print(f"  ✓ {rel_path}")

            if self.no_env_usage:
                print("\nScripts without env usage (exempt):")
                for script_path in sorted(self.no_env_usage):
                    rel_path = script_path.relative_to(SCRIPTS_DIR.parent)
                    print(f"  - {rel_path}")

            if self.skipped:
                print("\nSkipped (syntax errors):")
                for script_path, reason in self.skipped:
                    rel_path = script_path.relative_to(SCRIPTS_DIR.parent)
                    print(f"  ⚠ {rel_path}: {reason}")


class BootstrapComplianceChecker:
    """Checker for bootstrap compliance across scripts."""

    def __init__(self, allowlist: set[str] | None = None) -> None:
        self.allowlist = allowlist or set()

    def is_allowlisted(self, script_path: Path) -> bool:
        """Check if a script is in the allowlist.

        Args:
            script_path: Path to the script

        Returns:
            True if script is allowlisted
        """
        rel_path = script_path.relative_to(SCRIPTS_DIR.parent)
        # Check various path formats
        checks = [
            str(rel_path),
            str(rel_path).replace("\\", "/"),  # Windows compatibility
            script_path.name,
        ]
        # Add path relative to scripts/ if applicable
        try:
            checks.append(str(script_path.relative_to(SCRIPTS_DIR)))
        except ValueError:
            pass
        return any(check in self.allowlist for check in checks)

    def check_script(self, script_path: Path) -> list[Violation]:
        """Check a single script for bootstrap compliance.

        Args:
            script_path: Path to the Python script

        Returns:
            List of violations found (empty if compliant)
        """
        violations = []

        try:
            code = script_path.read_text(encoding="utf-8")
        except OSError as e:
            violations.append(
                Violation(
                    script_path,
                    "read_error",
                    f"Failed to read file: {e}",
                )
            )
            return violations

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            violations.append(
                Violation(
                    script_path,
                    "syntax_error",
                    f"Syntax error: {e}",
                    line_number=e.lineno,
                )
            )
            return violations

        # Skip allowlisted scripts
        if self.is_allowlisted(script_path):
            return violations

        # Check if script uses environment variables
        uses_env = uses_os_getenv(tree)

        if not uses_env:
            # Script doesn't use env variables - exempt from bootstrap requirement
            return violations

        # Script uses env variables - must have bootstrap
        has_import = has_bootstrap_import(tree)
        has_call = has_bootstrap_call(tree)

        if not has_import and not has_call:
            violations.append(
                Violation(
                    script_path,
                    "missing_bootstrap",
                    "uses os.getenv() or os.environ but missing bootstrap import",
                )
            )
        elif has_import and not has_call:
            violations.append(
                Violation(
                    script_path,
                    "missing_bootstrap_call",
                    "imports bootstrap but never calls it",
                )
            )

        return violations

    def check_all_scripts(self, verbose: bool = False) -> ComplianceResult:
        """Check all scripts for bootstrap compliance.

        Args:
            verbose: Whether to print detailed output

        Returns:
            ComplianceResult with all findings
        """
        result = ComplianceResult()
        scripts = get_all_scripts()

        for script_path in scripts:
            try:
                code = script_path.read_text(encoding="utf-8")
            except OSError as e:
                result.add_skipped(script_path, f"Read error: {e}")
                continue

            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                result.add_skipped(script_path, f"Syntax error: {e}")
                continue

            # Skip allowlisted scripts
            if self.is_allowlisted(script_path):
                if verbose:
                    rel_path = script_path.relative_to(SCRIPTS_DIR.parent)
                    print(f"  (allowlisted) {rel_path}")
                continue

            # Check if script uses environment variables
            uses_env = uses_os_getenv(tree)

            if not uses_env:
                result.add_no_env_usage(script_path)
                continue

            # Script uses env variables - check for bootstrap
            has_import = has_bootstrap_import(tree)
            has_call = has_bootstrap_call(tree)

            if not has_import:
                result.add_violation(
                    Violation(
                        script_path,
                        "missing_bootstrap",
                        "uses os.getenv() or os.environ but missing bootstrap import",
                    )
                )
            elif not has_call:
                result.add_violation(
                    Violation(
                        script_path,
                        "missing_bootstrap_call",
                        "imports bootstrap but never calls it",
                    )
                )
            else:
                result.add_compliant(script_path)

        return result


def parse_allowlist_file(filepath: Path) -> set[str]:
    """Parse an allowlist file containing script paths.

    Args:
        filepath: Path to the allowlist file

    Returns:
        Set of allowlisted script paths
    """
    allowlist = set()
    if not filepath.exists():
        return allowlist

    try:
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if line and not line.startswith("#"):
                    allowlist.add(line)
    except OSError:
        pass

    return allowlist


def main() -> int:
    """Main entry point.

    Returns:
        Exit code: 0=pass, 1=violations, 2=internal error
    """
    parser = argparse.ArgumentParser(
        description="Validate bootstrap compliance for scripts/**/*.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/ci/validate_bootstrap_compliance.py
    python scripts/ci/validate_bootstrap_compliance.py --verbose
    python scripts/ci/validate_bootstrap_compliance.py --allowlist scripts/allowlist.txt
    python scripts/ci/validate_bootstrap_compliance.py --allowlist scripts/foo.py,scripts/bar.py
        """,
    )
    parser.add_argument(
        "--allowlist",
        type=str,
        help="Comma-separated list of script paths to exclude, or path to a file containing paths (one per line)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output including compliant scripts",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: exit 0 only if all compliant, exit 1 if violations",
    )

    args = parser.parse_args()

    # Parse allowlist
    allowlist: set[str] = set()
    if args.allowlist:
        # Check if it's a file path
        allowlist_path = Path(args.allowlist)
        if allowlist_path.exists() and allowlist_path.is_file():
            allowlist = parse_allowlist_file(allowlist_path)
            if args.verbose:
                print(f"Loaded allowlist from file: {allowlist_path}")
                print(f"Allowlisted scripts: {sorted(allowlist)}")
        else:
            # Treat as comma-separated list
            allowlist = set(p.strip() for p in args.allowlist.split(",") if p.strip())
            if args.verbose:
                print(f"Allowlisted scripts: {sorted(allowlist)}")

    try:
        checker = BootstrapComplianceChecker(allowlist=allowlist)
        result = checker.check_all_scripts(verbose=args.verbose)

        result.print_report(verbose=args.verbose)

        if result.is_compliant:
            if args.verbose:
                print("\n✅ All scripts are bootstrap compliant")
            return 0
        else:
            if not args.verbose:
                # Print summary even without verbose
                print(
                    f"\nFound {len(result.violations)} violation(s)",
                    file=sys.stderr,
                )
            return 1

    except Exception as e:
        print(f"INTERNAL ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
