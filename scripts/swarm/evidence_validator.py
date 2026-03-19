#!/usr/bin/env python3
"""Evidence validator for worker completion claims.

Validates that worker completion evidence includes machine-checkable file
existence proof, preventing phantom claims where agents report files changed,
tests passed, or commands run without verifiable proof.

Core problem addressed:
- GOV-BATCH-003: Workers reported specific commit SHAs that cannot be verified;
  claimed file changes that don't exist; provided fabricated test coverage metrics.
- MULTI-AUDIT-001: 9 false completion claims detected across governance stories.

This module provides deterministic, machine-checkable validation that runs as a
gate before accepting worker completion evidence.

Story: SWARM-HARDEN-001
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class EvidenceCheckStatus(str, Enum):
    """Status of a single evidence check."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class EvidenceSeverity(str, Enum):
    """Severity of an evidence validation failure."""

    CRITICAL = "critical"  # Claim is demonstrably false
    WARNING = "warning"  # Claim cannot be fully verified
    INFO = "info"  # Informational finding


class EvidenceValidationError(RuntimeError):
    """Raised when evidence validation detects a phantom or unverifiable claim."""

    pass


@dataclass
class FileExistenceResult:
    """Result of checking whether a single file exists."""

    path: str
    exists: bool
    check_method: str  # "os.path", "glob", "git_ls_files"
    detail: str = ""
    severity: EvidenceSeverity = EvidenceSeverity.INFO


@dataclass
class TestClaimResult:
    """Result of validating a test result claim against actual test files."""

    test_file_pattern: str
    claimed_result: str
    test_file_exists: bool
    actual_test_files: list[str] = field(default_factory=list)
    match_found: bool = False
    severity: EvidenceSeverity = EvidenceSeverity.INFO


@dataclass
class CommandProofResult:
    """Result of verifying a command execution claim."""

    command: str
    claimed_exit_code: int
    verified: bool
    detail: str = ""
    severity: EvidenceSeverity = EvidenceSeverity.INFO


@dataclass
class EvidenceValidationResult:
    """Aggregate result of validating a complete evidence package."""

    overall_status: EvidenceCheckStatus = EvidenceCheckStatus.SKIP
    file_existence_results: list[FileExistenceResult] = field(default_factory=list)
    test_claim_results: list[TestClaimResult] = field(default_factory=list)
    command_proof_results: list[CommandProofResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Evidence is valid if no critical failures exist."""
        return self.overall_status == EvidenceCheckStatus.PASS

    @property
    def critical_count(self) -> int:
        """Count of critical-severity findings."""
        all_results: list[Any] = [
            *self.file_existence_results,
            *self.test_claim_results,
            *self.command_proof_results,
        ]
        return sum(
            1
            for r in all_results
            if getattr(r, "severity", None) == EvidenceSeverity.CRITICAL
        )

    @property
    def warning_count(self) -> int:
        """Count of warning-severity findings."""
        all_results: list[Any] = [
            *self.file_existence_results,
            *self.test_claim_results,
            *self.command_proof_results,
        ]
        return sum(
            1
            for r in all_results
            if getattr(r, "severity", None) == EvidenceSeverity.WARNING
        )

    def summary(self) -> str:
        """Human-readable summary of validation results."""
        lines = [
            f"Overall: {self.overall_status.value}",
            f"Files checked: {len(self.file_existence_results)}",
            f"Test claims checked: {len(self.test_claim_results)}",
            f"Command proofs checked: {len(self.command_proof_results)}",
            f"Critical: {self.critical_count}, Warnings: {self.warning_count}",
        ]
        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
        if self.warnings:
            lines.append(f"Warnings: {len(self.warnings)}")
        return "\n".join(lines)


class EvidenceValidator:
    """Validates worker completion evidence for machine-checkable proof.

    The validator checks three categories of evidence:
    1. File existence: Do claimed files actually exist on disk or in git?
    2. Test claims: Do test result claims map to real test files?
    3. Command proofs: Can claimed commands be verified?

    Usage:
        validator = EvidenceValidator(repo_root="/path/to/repo")
        result = validator.validate({
            "files_changed": ["src/foo.py", "tests/test_foo.py"],
            "test_results": {"tests/test_foo.py": "passed"},
            "commands_run": ["pytest tests/test_foo.py -v"],
        })
        if not result.is_valid:
            raise EvidenceValidationError(result.summary())
    """

    def __init__(self, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()
        self._git_available: bool | None = None

    @property
    def git_available(self) -> bool:
        """Check if git is available in the environment."""
        if self._git_available is None:
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--git-dir"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=str(self.repo_root),
                )
                self._git_available = result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                self._git_available = False
        return self._git_available

    def check_file_exists(
        self,
        path: str,
        check_methods: list[str] | None = None,
    ) -> FileExistenceResult:
        """Check if a claimed file exists using specified verification methods.

        Args:
            path: Relative or absolute file path to verify.
            check_methods: List of methods to try. Options: "os.path", "glob",
                "git_ls_files". Defaults to ["os.path", "glob"].

        Returns:
            FileExistenceResult with existence status and method used.
        """
        if check_methods is None:
            check_methods = ["os.path", "glob"]

        resolved = self._resolve_path(path)

        # Try each method in order
        for method in check_methods:
            if method == "os.path":
                if resolved.exists() and resolved.is_file():
                    return FileExistenceResult(
                        path=path,
                        exists=True,
                        check_method="os.path",
                        detail=f"File exists at {resolved}",
                        severity=EvidenceSeverity.INFO,
                    )

            elif method == "glob":
                parent = resolved.parent
                pattern = resolved.name
                if parent.exists():
                    matches = [m for m in parent.glob(pattern) if m.is_file()]
                    if matches:
                        return FileExistenceResult(
                            path=path,
                            exists=True,
                            check_method="glob",
                            detail=f"Matched via glob: {matches[0]}",
                            severity=EvidenceSeverity.INFO,
                        )

            elif method == "git_ls_files":
                if self.git_available:
                    result = self._git_ls_files(path)
                    if result:
                        return FileExistenceResult(
                            path=path,
                            exists=True,
                            check_method="git_ls_files",
                            detail=f"Git tracked: {result}",
                            severity=EvidenceSeverity.INFO,
                        )

        # File not found by any method
        return FileExistenceResult(
            path=path,
            exists=False,
            check_method="+".join(check_methods),
            detail=f"File not found by any method: {check_methods}",
            severity=EvidenceSeverity.CRITICAL,
        )

    def check_files_exist(
        self,
        paths: list[str],
        check_methods: list[str] | None = None,
        require_all: bool = True,
    ) -> list[FileExistenceResult]:
        """Check multiple files for existence.

        Args:
            paths: List of file paths to verify.
            check_methods: Verification methods to use per file.
            require_all: If True, all files must exist for overall pass.

        Returns:
            List of FileExistenceResult, one per path.
        """
        results = []
        for path in paths:
            result = self.check_file_exists(path, check_methods)
            results.append(result)
            if not result.exists:
                level = logging.CRITICAL if require_all else logging.WARNING
                logger.log(level, "File existence check failed: %s", path)
        return results

    def validate_test_claim(
        self,
        test_file_pattern: str,
        claimed_result: str,
    ) -> TestClaimResult:
        """Validate that a test result claim maps to an actual test file.

        Args:
            test_file_pattern: File pattern for the test file (e.g.,
                "tests/test_foo.py").
            claimed_result: The claimed test result (e.g., "passed", "failed",
                "5 passed, 0 failed").

        Returns:
            TestClaimResult with validation details.
        """
        resolved = self._resolve_path(test_file_pattern)

        # Check if the exact test file exists
        if resolved.exists() and resolved.is_file():
            return TestClaimResult(
                test_file_pattern=test_file_pattern,
                claimed_result=claimed_result,
                test_file_exists=True,
                actual_test_files=[str(resolved)],
                match_found=True,
                severity=EvidenceSeverity.INFO,
            )

        # Try glob matching for partial patterns
        parent = resolved.parent
        pattern = resolved.name
        actual_test_files = []

        if parent.exists():
            matches = list(parent.glob(pattern))
            actual_test_files = [str(m.relative_to(self.repo_root)) for m in matches]

        if actual_test_files:
            return TestClaimResult(
                test_file_pattern=test_file_pattern,
                claimed_result=claimed_result,
                test_file_exists=True,
                actual_test_files=actual_test_files,
                match_found=True,
                severity=EvidenceSeverity.WARNING,
                # Warning because pattern matched but exact file didn't
            )

        # No test file found — this is a phantom claim
        return TestClaimResult(
            test_file_pattern=test_file_pattern,
            claimed_result=claimed_result,
            test_file_exists=False,
            actual_test_files=[],
            match_found=False,
            severity=EvidenceSeverity.CRITICAL,
        )

    def validate_test_claims(
        self,
        test_claims: dict[str, str],
    ) -> list[TestClaimResult]:
        """Validate multiple test result claims.

        Args:
            test_claims: Mapping of test file patterns to claimed results.

        Returns:
            List of TestClaimResult, one per claim.
        """
        results = []
        for test_file, claimed_result in test_claims.items():
            result = self.validate_test_claim(test_file, claimed_result)
            results.append(result)
            if not result.match_found:
                logger.critical(
                    "Phantom test claim: %s claimed %s but file not found",
                    test_file,
                    claimed_result,
                )
        return results

    def validate_command_proof(
        self,
        command: str,
        claimed_exit_code: int = 0,
        cwd: str | None = None,
    ) -> CommandProofResult:
        """Verify a command execution claim.

        For file-existence commands (ls, test, stat), re-runs the command
        to verify the claim. For other commands, marks as unverified.

        Args:
            command: The command that was claimed to have been run.
            claimed_exit_code: The claimed exit code.
            cwd: Working directory for the command (defaults to repo_root).

        Returns:
            CommandProofResult with verification details.
        """
        # Only verify file-existence commands — don't re-run arbitrary commands
        file_check_commands = ["ls", "test", "stat", "file", "find"]
        cmd_parts = command.split()

        if not cmd_parts:
            return CommandProofResult(
                command=command,
                claimed_exit_code=claimed_exit_code,
                verified=False,
                detail="Empty command",
                severity=EvidenceSeverity.WARNING,
            )

        base_cmd = os.path.basename(cmd_parts[0])

        if base_cmd in file_check_commands:
            try:
                result = subprocess.run(
                    cmd_parts,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=cwd or str(self.repo_root),
                )
                verified = result.returncode == claimed_exit_code
                severity = (
                    EvidenceSeverity.INFO if verified else EvidenceSeverity.CRITICAL
                )
                detail = (
                    f"Re-ran command: exit={result.returncode} "
                    f"(claimed={claimed_exit_code})"
                )
                return CommandProofResult(
                    command=command,
                    claimed_exit_code=claimed_exit_code,
                    verified=verified,
                    detail=detail,
                    severity=severity,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
                return CommandProofResult(
                    command=command,
                    claimed_exit_code=claimed_exit_code,
                    verified=False,
                    detail=f"Could not re-run command: {exc}",
                    severity=EvidenceSeverity.WARNING,
                )

        # Non-file-check commands: mark as unverified but not critical
        return CommandProofResult(
            command=command,
            claimed_exit_code=claimed_exit_code,
            verified=False,
            detail="Command not auto-verifiable (not a file-existence command)",
            severity=EvidenceSeverity.WARNING,
        )

    def validate_command_proofs(
        self,
        commands: list[dict[str, Any]] | list[str],
    ) -> list[CommandProofResult]:
        """Validate multiple command execution claims.

        Args:
            commands: List of command claims. Each can be a string (command only)
                or a dict with keys "command" and optionally "exit_code" and "cwd".

        Returns:
            List of CommandProofResult, one per claim.
        """
        results = []
        for cmd in commands:
            if isinstance(cmd, str):
                result = self.validate_command_proof(cmd)
            elif isinstance(cmd, dict):
                result = self.validate_command_proof(
                    command=cmd.get("command", ""),
                    claimed_exit_code=cmd.get("exit_code", 0),
                    cwd=cmd.get("cwd"),
                )
            else:
                result = CommandProofResult(
                    command=str(cmd),
                    claimed_exit_code=0,
                    verified=False,
                    detail="Invalid command format",
                    severity=EvidenceSeverity.WARNING,
                )
            results.append(result)
        return results

    def validate(
        self,
        evidence: dict[str, Any],
    ) -> EvidenceValidationResult:
        """Validate a complete evidence package.

        Args:
            evidence: Dict with optional keys:
                - "files_changed": list[str] — files claimed to be changed
                - "test_results": dict[str, str] — test file -> claimed result
                - "commands_run": list[dict|str] — commands claimed to have run
                - "require_all_files": bool — if True, all files must exist

        Returns:
            EvidenceValidationResult with aggregate pass/fail status.
        """
        result = EvidenceValidationResult()

        # --- File existence checks ---
        files_changed = evidence.get("files_changed", [])
        if files_changed:
            require_all = evidence.get("require_all_files", True)
            result.file_existence_results = self.check_files_exist(
                paths=files_changed,
                require_all=require_all,
            )
        else:
            result.warnings.append("No files_changed provided in evidence")

        # --- Test claim checks ---
        test_results = evidence.get("test_results", {})
        if test_results:
            result.test_claim_results = self.validate_test_claims(test_results)
        else:
            result.warnings.append("No test_results provided in evidence")

        # --- Command proof checks ---
        commands_run = evidence.get("commands_run", [])
        if commands_run:
            result.command_proof_results = self.validate_command_proofs(commands_run)
        else:
            result.warnings.append("No commands_run provided in evidence")

        # --- Aggregate status ---
        all_results: list[Any] = [
            *result.file_existence_results,
            *result.test_claim_results,
            *result.command_proof_results,
        ]

        has_critical = any(
            getattr(r, "severity", None) == EvidenceSeverity.CRITICAL
            for r in all_results
        )
        has_failures = any(
            getattr(r, "exists", True) is False
            or getattr(r, "match_found", True) is False
            or getattr(r, "verified", True) is False
            for r in all_results
        )

        if has_critical:
            result.overall_status = EvidenceCheckStatus.FAIL
            result.errors.extend(
                [
                    f"CRITICAL: {r}"
                    for r in all_results
                    if getattr(r, "severity", None) == EvidenceSeverity.CRITICAL
                ]
            )
        elif has_failures:
            result.overall_status = EvidenceCheckStatus.FAIL
            result.errors.append("Evidence contains unverifiable claims")
        elif all_results:
            result.overall_status = EvidenceCheckStatus.PASS
        else:
            result.overall_status = EvidenceCheckStatus.SKIP

        logger.info("Evidence validation: %s", result.summary())
        return result

    # --- Private helpers ---

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to repo_root, handling absolute paths."""
        p = Path(path)
        if p.is_absolute():
            return p
        return (self.repo_root / p).resolve()

    def _git_ls_files(self, path: str) -> str:
        """Run git ls-files to check if path is tracked by git."""
        try:
            result = subprocess.run(
                ["git", "ls-files", "--error-unmatch", path],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.repo_root),
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return ""
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point for evidence validation."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Validate worker completion evidence for machine-checkable proof.",
    )
    parser.add_argument(
        "--evidence-file",
        type=str,
        help="Path to JSON evidence file to validate.",
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=".",
        help="Repository root path (default: current directory).",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        help="Files to check for existence (shorthand).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output results as JSON.",
    )

    args = parser.parse_args()

    validator = EvidenceValidator(repo_root=args.repo_root)

    if args.evidence_file:
        with open(args.evidence_file) as f:
            evidence = json.load(f)
        result = validator.validate(evidence)
    elif args.files:
        result = EvidenceValidationResult()
        result.file_existence_results = validator.check_files_exist(args.files)
        if any(not r.exists for r in result.file_existence_results):
            result.overall_status = EvidenceCheckStatus.FAIL
        else:
            result.overall_status = EvidenceCheckStatus.PASS
    else:
        parser.error("Either --evidence-file or --files must be provided.")
        return 1

    if args.output_json:
        output = {
            "overall_status": result.overall_status.value,
            "is_valid": result.is_valid,
            "critical_count": result.critical_count,
            "warning_count": result.warning_count,
            "file_existence": [
                {
                    "path": r.path,
                    "exists": r.exists,
                    "method": r.check_method,
                    "severity": r.severity.value,
                    "detail": r.detail,
                }
                for r in result.file_existence_results
            ],
            "test_claims": [
                {
                    "pattern": r.test_file_pattern,
                    "claimed_result": r.claimed_result,
                    "file_exists": r.test_file_exists,
                    "match_found": r.match_found,
                    "severity": r.severity.value,
                    "actual_files": r.actual_test_files,
                }
                for r in result.test_claim_results
            ],
            "command_proofs": [
                {
                    "command": r.command,
                    "claimed_exit_code": r.claimed_exit_code,
                    "verified": r.verified,
                    "severity": r.severity.value,
                    "detail": r.detail,
                }
                for r in result.command_proof_results
            ],
            "errors": result.errors,
            "warnings": result.warnings,
        }
        print(json.dumps(output, indent=2))
    else:
        print(result.summary())

    return 0 if result.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
