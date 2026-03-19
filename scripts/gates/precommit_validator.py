#!/usr/bin/env python3
"""
Pre-commit Validator - CI Blocking Gates Integration
Story: BATCH-3 CI-001-A

Validates code quality, status sync, and governance compliance
before allowing commits. This is the local pre-commit gate
that mirrors CI validation.

Exit codes:
    0: All validations passed
    1: One or more validations failed
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


class PrecommitValidator:
    """Validates pre-commit requirements for ChiseAI repository."""

    def __init__(self, verbose: bool = False, fix: bool = False):
        self.verbose = verbose
        self.fix = fix
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def log(self, message: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"[precommit] {message}")

    def run_command(
        self, cmd: List[str], description: str, allow_failure: bool = False
    ) -> Tuple[int, str, str]:
        """Run a shell command and return exit code, stdout, stderr."""
        self.log(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0 and not allow_failure:
                self.errors.append(f"{description} failed (exit {result.returncode})")
                if self.verbose:
                    print(f"STDOUT: {result.stdout}")
                    print(f"STDERR: {result.stderr}")
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self.errors.append(f"{description} timed out after 300s")
            return 1, "", "Timeout"
        except Exception as e:
            self.errors.append(f"{description} error: {e}")
            return 1, "", str(e)

    def validate_black(self, files: List[str]) -> bool:
        """Validate Python code formatting with black."""
        print("→ Validating code formatting (black)...")
        if not files:
            self.log("No Python files to check")
            return True

        cmd = ["black", "--check"] + files
        if self.fix:
            cmd = ["black"] + files

        exit_code, stdout, stderr = self.run_command(cmd, "Black formatting check")

        if exit_code == 0:
            print("  ✓ Black formatting OK")
            return True
        else:
            print(f"  ✗ Black formatting issues found")
            if not self.fix:
                print("    Run with --fix to auto-format")
            return False

    def validate_ruff(self, files: List[str]) -> bool:
        """Validate Python code with ruff linter."""
        print("→ Validating code with ruff...")
        if not files:
            self.log("No Python files to check")
            return True

        cmd = ["ruff", "check"] + files
        if self.fix:
            cmd.append("--fix")

        exit_code, stdout, stderr = self.run_command(cmd, "Ruff linting check")

        if exit_code == 0:
            print("  ✓ Ruff linting OK")
            return True
        else:
            print(f"  ✗ Ruff linting issues found")
            return False

    def validate_mypy(self, files: List[str]) -> bool:
        """Validate Python type annotations with mypy."""
        print("→ Validating type annotations (mypy)...")
        if not files:
            self.log("No Python files to check")
            return True

        # Only check src/ and scripts/ files with mypy
        src_files = [f for f in files if f.startswith(("src/", "scripts/"))]
        if not src_files:
            self.log("No src/scripts files to type-check")
            return True

        cmd = ["mypy"] + src_files
        exit_code, stdout, stderr = self.run_command(
            cmd,
            "Mypy type check",
            allow_failure=False,  # mypy failures should block
        )

        if exit_code == 0:
            print("  ✓ Type annotations OK")
            return True
        else:
            print("  ✗ Type annotation issues found")
            self.errors.append("mypy: type annotation issues found")
            return False  # mypy issues are blocking errors

    def validate_status_sync(self) -> bool:
        """Validate workflow status file sync."""
        print("→ Validating status sync...")

        exit_code, stdout, stderr = self.run_command(
            ["python3", "scripts/validate_status_sync.py"],
            "Status sync validation",
            allow_failure=True,
        )

        if exit_code == 0:
            print("  ✓ Status sync OK")
            return True
        else:
            print(f"  ⚠ Status sync issues (non-blocking)")
            self.warnings.append("status-sync: sync issues found")
            return True  # Status sync issues are warnings locally

    def validate_traceability(self) -> bool:
        """Validate FR traceability."""
        print("→ Validating FR traceability...")

        exit_code, stdout, stderr = self.run_command(
            ["python3", "scripts/validate_fr_traceability.py"],
            "FR traceability validation",
            allow_failure=True,
        )

        if exit_code == 0:
            print("  ✓ FR traceability OK")
            return True
        else:
            print(f"  ⚠ FR traceability issues (non-blocking)")
            self.warnings.append("traceability: issues found")
            return True

    def validate_swarm_policy(self) -> bool:
        """Validate AGENTS/agent policy consistency."""
        print("→ Validating swarm policy consistency...")

        exit_code, _, _ = self.run_command(
            ["python3", "scripts/validate_swarm_policy_consistency.py"],
            "Swarm policy consistency validation",
        )

        if exit_code == 0:
            print("  ✓ Swarm policy consistency OK")
            return True

        print("  ✗ Swarm policy consistency failed")
        return False

    def validate_git_sanity(self) -> bool:
        """Validate git state is sane."""
        print("→ Validating git sanity...")

        # Check we're not on main
        exit_code, stdout, _ = self.run_command(
            ["git", "branch", "--show-current"], "Git branch check"
        )

        if exit_code == 0:
            branch = stdout.strip()
            if branch == "main":
                self.errors.append("Cannot commit directly to main branch")
                print("  ✗ On main branch - create a feature branch")
                return False
            else:
                print(f"  ✓ On branch: {branch}")

        # Check for merge markers
        exit_code, stdout, _ = self.run_command(
            ["git", "diff", "--check"], "Git diff check", allow_failure=True
        )

        if exit_code != 0:
            self.errors.append("Merge conflict markers found")
            print("  ✗ Merge conflict markers detected")
            return False

        print("  ✓ Git sanity OK")
        return True

    def get_changed_files(self) -> List[str]:
        """Get list of changed Python files staged for commit."""
        # Get staged files
        exit_code, stdout, _ = self.run_command(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            "Get staged files",
        )

        if exit_code != 0:
            return []

        all_files = [f.strip() for f in stdout.split("\n") if f.strip()]

        # Filter to Python files only
        py_files = [f for f in all_files if f.endswith(".py")]

        self.log(f"Found {len(py_files)} staged Python files")
        return py_files

    def validate(self, skip_git_check: bool = False) -> bool:
        """Run all validations and return overall success."""
        print("=" * 60)
        print("Pre-commit Validation")
        print("=" * 60)

        # Git sanity first (unless skipped)
        if not skip_git_check:
            if not self.validate_git_sanity():
                return False
        else:
            print("→ Skipping git sanity checks (--skip-git-check)")

        # Get changed files
        changed_files = self.get_changed_files()

        if not changed_files:
            print("\nNo Python files changed - skipping code quality checks")
        else:
            print(f"\nValidating {len(changed_files)} changed Python file(s)...")

        # Code quality checks
        black_ok = self.validate_black(changed_files)
        ruff_ok = self.validate_ruff(changed_files)
        mypy_ok = self.validate_mypy(changed_files)

        if not all([black_ok, ruff_ok, mypy_ok]):
            return False

        # Status and governance checks
        status_ok = self.validate_status_sync()
        traceability_ok = self.validate_traceability()
        swarm_policy_ok = self.validate_swarm_policy()

        if not all([status_ok, traceability_ok, swarm_policy_ok]):
            return False

        return True

    def print_summary(self) -> None:
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("Validation Summary")
        print("=" * 60)

        if self.errors:
            print(f"\n✗ FAILED - {len(self.errors)} error(s):")
            for error in self.errors:
                print(f"  • {error}")

        if self.warnings:
            print(f"\n⚠ WARNINGS - {len(self.warnings)} warning(s):")
            for warning in self.warnings:
                print(f"  • {warning}")

        if not self.errors and not self.warnings:
            print("\n✓ All validations passed!")
        elif not self.errors:
            print("\n✓ Passed with warnings")


def main():
    parser = argparse.ArgumentParser(
        description="Pre-commit validator for ChiseAI repository"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix issues where possible (black, ruff --fix)",
    )
    parser.add_argument(
        "--skip-git-check", action="store_true", help="Skip git sanity checks"
    )

    args, _ = parser.parse_known_args()

    validator = PrecommitValidator(verbose=args.verbose, fix=args.fix)

    success = validator.validate(skip_git_check=args.skip_git_check)
    validator.print_summary()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
