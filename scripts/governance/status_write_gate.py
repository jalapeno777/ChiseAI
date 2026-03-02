#!/usr/bin/env python3
"""
Status Write Gate for EP-AUTO-GIT

This module provides validation and gating for writes to the workflow status file
(docs/bmm-workflow-status.yaml). It ensures that:

1. Only authorized agents (merlin) can write status changes
2. Git SHA references are verified against actual git history
3. YAML structure is valid
4. EP-AUTO-GIT entries are properly formatted

The gate can be used as a pre-commit hook to prevent unauthorized or invalid
status modifications.

Usage:
    # As a CLI tool (for pre-commit hook)
    python status_write_gate.py --file docs/bmm-workflow-status.yaml

    # As a module
    from status_write_gate import validate_status_write

    result = validate_status_write(
        yaml_file="docs/bmm-workflow-status.yaml",
        agent="merlin",
    )
    if not result.valid:
        print(result.errors)
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_STATUS_FILE = "docs/bmm-workflow-status.yaml"
EP_AUTO_GIT_PATTERN = re.compile(r"EP-AUTO-GIT-\d+", re.IGNORECASE)
SHA_PATTERN = re.compile(r"^[a-f0-9]{7,40}$", re.IGNORECASE)
REQUIRED_YAML_KEYS = ["metadata", "epics"]


@dataclass
class ValidationError:
    """Represents a single validation error."""

    field: str
    message: str
    severity: str = "error"  # error, warning


@dataclass
class ValidationResult:
    """
    Result of a status write validation.

    Attributes:
        valid: Whether the validation passed
        errors: List of validation errors
        warnings: List of validation warnings
        git_shas_verified: List of SHAs that were verified
        git_shas_failed: List of SHAs that failed verification
        yaml_valid: Whether YAML syntax is valid
        authority_valid: Whether authority check passed
    """

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    git_shas_verified: list[str] = field(default_factory=list)
    git_shas_failed: list[str] = field(default_factory=list)
    yaml_valid: bool = False
    authority_valid: bool = False

    def add_error(self, field: str, message: str) -> None:
        """Add an error to the result."""
        self.errors.append(ValidationError(field, message, "error"))
        self.valid = False

    def add_warning(self, field: str, message: str) -> None:
        """Add a warning to the result."""
        self.warnings.append(ValidationError(field, message, "warning"))


def verify_git_sha(sha: str, repo_path: str | None = None) -> bool:
    """
    Verify that a git SHA exists in the repository history.

    This function uses git cat-file to check if the SHA refers to a valid
    commit object in the repository.

    Args:
        sha: The git SHA to verify (short or full form).
        repo_path: Path to the git repository. If None, uses current directory.

    Returns:
        True if the SHA exists and refers to a commit, False otherwise.

    Examples:
        >>> verify_git_sha("19e9e62")
        True
        >>> verify_git_sha("0000000")
        False
        >>> verify_git_sha("19e9e62f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d")
        True
    """
    if not sha or not isinstance(sha, str):
        return False

    # Basic SHA format validation
    if not SHA_PATTERN.match(sha):
        return False

    try:
        # Build git command
        if repo_path:
            cmd = ["git", "-C", repo_path, "cat-file", "-t", sha]
        else:
            cmd = ["git", "cat-file", "-t", sha]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Check if command succeeded and output contains "commit"
        return bool(result.returncode == 0 and "commit" in result.stdout.lower())

    except subprocess.TimeoutExpired:
        logger.warning(f"Git SHA verification timed out for '{sha}'")
        return False
    except FileNotFoundError:
        logger.warning("Git command not found")
        return False
    except Exception as e:
        logger.warning(f"Git SHA verification failed for '{sha}': {e}")
        return False


def extract_shas_from_yaml(data: Any, path: str = "") -> list[tuple[str, str]]:
    """
    Recursively extract all git SHAs from YAML data.

    Args:
        data: Parsed YAML data (dict, list, or primitive).
        path: Current path in the data structure (for error reporting).

    Returns:
        List of tuples (field_path, sha_value).
    """
    shas: list[tuple[str, str]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key

            # Check if key suggests this is a SHA field
            if any(
                keyword in key.lower()
                for keyword in ["sha", "commit", "merge_commit", "head_sha", "base_sha"]
            ):
                if isinstance(value, str) and SHA_PATTERN.match(value):
                    shas.append((current_path, value))

            # Recurse into nested structures
            shas.extend(extract_shas_from_yaml(value, current_path))

    elif isinstance(data, list):
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]"
            shas.extend(extract_shas_from_yaml(item, current_path))

    return shas


def validate_yaml_structure(data: Any) -> list[ValidationError]:
    """
    Validate the basic structure of the workflow status YAML.

    Args:
        data: Parsed YAML data.

    Returns:
        List of validation errors (empty if valid).
    """
    errors: list[ValidationError] = []

    # Check top-level keys
    if not isinstance(data, dict):
        errors.append(
            ValidationError("root", "YAML root must be a dictionary", "error")
        )
        return errors

    for key in REQUIRED_YAML_KEYS:
        if key not in data:
            errors.append(
                ValidationError(
                    "root", f"Missing required top-level key: '{key}'", "error"
                )
            )

    # Validate metadata structure
    if "metadata" in data:
        metadata = data["metadata"]
        if not isinstance(metadata, dict):
            errors.append(
                ValidationError("metadata", "metadata must be a dictionary", "error")
            )
        else:
            # Check for recent_changes array
            if "recent_changes" in metadata:
                if not isinstance(metadata["recent_changes"], list):
                    errors.append(
                        ValidationError(
                            "metadata.recent_changes",
                            "recent_changes must be a list",
                            "error",
                        )
                    )

    # Validate epics structure
    if "epics" in data:
        epics = data["epics"]
        if not isinstance(epics, list):
            errors.append(ValidationError("epics", "epics must be a list", "error"))
        else:
            for i, epic in enumerate(epics):
                if not isinstance(epic, dict):
                    errors.append(
                        ValidationError(
                            f"epics[{i}]",
                            f"Epic at index {i} must be a dictionary",
                            "error",
                        )
                    )
                elif "id" not in epic:
                    errors.append(
                        ValidationError(
                            f"epics[{i}]",
                            f"Epic at index {i} is missing 'id' field",
                            "error",
                        )
                    )

    return errors


def check_ep_auto_git_entries(data: Any) -> list[ValidationError]:
    """
    Check EP-AUTO-GIT entries for required fields and valid structure.

    Args:
        data: Parsed YAML data.

    Returns:
        List of validation errors (empty if valid).
    """
    errors: list[ValidationError] = []

    if not isinstance(data, dict) or "epics" not in data:
        return errors

    epics = data["epics"]
    if not isinstance(epics, list):
        return errors

    for i, epic in enumerate(epics):
        if not isinstance(epic, dict):
            continue

        epic_id = epic.get("id", "")
        if not EP_AUTO_GIT_PATTERN.match(str(epic_id)):
            continue

        epic_path = f"epics[{i}]"

        # Check required fields for EP-AUTO-GIT epics
        required_fields = ["status", "story_count", "story_points"]
        for required_field in required_fields:
            if required_field not in epic:
                errors.append(
                    ValidationError(
                        f"{epic_path}.{required_field}",
                        f"EP-AUTO-GIT epic '{epic_id}' missing required field: {required_field}",
                        "error",
                    )
                )

        # Validate story_ids if present
        if "story_ids" in epic:
            story_ids = epic["story_ids"]
            if not isinstance(story_ids, list):
                errors.append(
                    ValidationError(
                        f"{epic_path}.story_ids",
                        f"EP-AUTO-GIT epic '{epic_id}' story_ids must be a list",
                        "error",
                    )
                )

        # Validate completion fields if status is completed
        if epic.get("status") == "completed":
            if "completion_date" not in epic:
                errors.append(
                    ValidationError(
                        f"{epic_path}.completion_date",
                        f"Completed EP-AUTO-GIT epic '{epic_id}' should have completion_date",
                        "warning",
                    )
                )

    # Check recent_changes for EP-AUTO-GIT entries
    if "metadata" in data and isinstance(data["metadata"], dict):
        metadata = data["metadata"]
        if "recent_changes" in metadata and isinstance(
            metadata["recent_changes"], list
        ):
            for j, change in enumerate(metadata["recent_changes"]):
                if not isinstance(change, dict):
                    continue

                change_path = f"metadata.recent_changes[{j}]"

                # Check if this is an EP-AUTO-GIT related change
                epic_id = change.get("epic_id", "")
                if EP_AUTO_GIT_PATTERN.match(str(epic_id)):
                    # EP-AUTO-GIT changes should have certain fields
                    if "actor" not in change:
                        errors.append(
                            ValidationError(
                                f"{change_path}.actor",
                                "EP-AUTO-GIT change missing 'actor' field",
                                "warning",
                            )
                        )

                    if "timestamp" not in change:
                        errors.append(
                            ValidationError(
                                f"{change_path}.timestamp",
                                "EP-AUTO-GIT change missing 'timestamp' field",
                                "error",
                            )
                        )

    return errors


def validate_status_yaml(
    yaml_file: str,
    verify_shas: bool = True,
    repo_path: str | None = None,
) -> ValidationResult:
    """
    Validate the workflow status YAML file.

    This function performs comprehensive validation:
    1. YAML syntax validation
    2. Structure validation (required keys, types)
    3. EP-AUTO-GIT entry validation
    4. Git SHA verification (optional)

    Args:
        yaml_file: Path to the YAML file to validate.
        verify_shas: Whether to verify git SHAs against repository.
        repo_path: Path to git repository for SHA verification.

    Returns:
        ValidationResult with detailed validation status.

    Examples:
        >>> result = validate_status_yaml("docs/bmm-workflow-status.yaml")
        >>> result.valid
        True
        >>> result.yaml_valid
        True
        >>> result.git_shas_verified
        ['19e9e62', 'abc1234']
    """
    result = ValidationResult(valid=True)

    # Check file exists
    if not os.path.exists(yaml_file):
        result.add_error("file", f"YAML file not found: {yaml_file}")
        return result

    # Parse YAML
    try:
        with open(yaml_file, encoding="utf-8") as f:
            content = f.read()

        data = yaml.safe_load(content)
        result.yaml_valid = True

    except yaml.YAMLError as e:
        result.add_error("yaml", f"YAML parsing error: {e}")
        return result
    except Exception as e:
        result.add_error("file", f"Error reading file: {e}")
        return result

    # Validate structure
    structure_errors = validate_yaml_structure(data)
    for error in structure_errors:
        if error.severity == "error":
            result.add_error(error.field, error.message)
        else:
            result.add_warning(error.field, error.message)

    # Validate EP-AUTO-GIT entries
    ep_errors = check_ep_auto_git_entries(data)
    for error in ep_errors:
        if error.severity == "error":
            result.add_error(error.field, error.message)
        else:
            result.add_warning(error.field, error.message)

    # Verify git SHAs
    if verify_shas and data:
        shas = extract_shas_from_yaml(data)

        for field_path, sha in shas:
            if verify_git_sha(sha, repo_path):
                result.git_shas_verified.append(sha)
                logger.debug(f"Verified SHA '{sha}' at {field_path}")
            else:
                result.git_shas_failed.append(sha)
                result.add_error(
                    field_path, f"Git SHA '{sha}' not found in repository history"
                )

    return result


def check_authority(agent: str | None = None) -> tuple[bool, str]:
    """
    Check if the agent has authority to write to status file.

    Args:
        agent: The agent name. If None, detects from environment.

    Returns:
        Tuple of (authorized, message).
    """
    try:
        # Import merlin_authority for authority checking
        from scripts.governance.merlin_authority import check_ep_auto_git_authority

        result = check_ep_auto_git_authority("status", agent)
        return result.authorized, result.reason

    except ImportError:
        # Fallback: check environment variable directly
        detected_agent = agent or os.environ.get("AGENT_NAME", "unknown").lower()
        if detected_agent == "merlin":
            return True, f"Agent '{detected_agent}' authorized (fallback check)"
        else:
            return False, f"Agent '{detected_agent}' not authorized (fallback check)"

    except Exception as e:
        # Fail-secure: deny access on authority check errors
        # This catches AuthorityCheckError, EpicNotProtected, and any other exceptions
        return False, f"Authority check failed: {e}"


def validate_status_write(
    yaml_file: str = DEFAULT_STATUS_FILE,
    agent: str | None = None,
    verify_shas: bool = True,
    require_authority: bool = True,
    repo_path: str | None = None,
) -> ValidationResult:
    """
    Comprehensive validation for a status file write operation.

    This is the main entry point for validating status writes. It combines:
    1. Authority validation (is the agent allowed to write?)
    2. YAML validation (is the file valid?)
    3. SHA verification (do referenced commits exist?)
    4. EP-AUTO-GIT entry validation

    Args:
        yaml_file: Path to the YAML file to validate.
        agent: The agent name. If None, detects from environment.
        verify_shas: Whether to verify git SHAs.
        require_authority: Whether to require merlin authority.
        repo_path: Path to git repository for SHA verification.

    Returns:
        ValidationResult with complete validation status.

    Examples:
        >>> result = validate_status_write(
        ...     yaml_file="docs/bmm-workflow-status.yaml",
        ...     agent="merlin",
        ... )
        >>> if result.valid:
        ...     print("Status write is valid")
        ... else:
        ...     for error in result.errors:
        ...         print(f"Error: {error.message}")
    """
    result = ValidationResult(valid=True)

    # Check authority
    if require_authority:
        authorized, message = check_authority(agent)
        result.authority_valid = authorized

        if not authorized:
            result.add_error("authority", message)
            # Continue with other validations for comprehensive feedback
    else:
        result.authority_valid = True

    # Validate YAML content
    yaml_result = validate_status_yaml(yaml_file, verify_shas, repo_path)

    # Merge results
    result.valid = result.valid and yaml_result.valid
    result.yaml_valid = yaml_result.yaml_valid
    result.errors.extend(yaml_result.errors)
    result.warnings.extend(yaml_result.warnings)
    result.git_shas_verified = yaml_result.git_shas_verified
    result.git_shas_failed = yaml_result.git_shas_failed

    return result


def format_validation_report(result: ValidationResult, verbose: bool = False) -> str:
    """
    Format a validation result as a human-readable report.

    Args:
        result: The validation result to format.
        verbose: Whether to include verbose output.

    Returns:
        Formatted report string.
    """
    lines: list[str] = []

    # Summary
    if result.valid:
        lines.append("✓ Validation PASSED")
    else:
        lines.append("✗ Validation FAILED")

    lines.append("")

    # Authority
    if result.authority_valid:
        lines.append("✓ Authority check: PASSED")
    else:
        lines.append("✗ Authority check: FAILED")

    # YAML
    if result.yaml_valid:
        lines.append("✓ YAML syntax: VALID")
    else:
        lines.append("✗ YAML syntax: INVALID")

    # SHAs
    if result.git_shas_verified:
        lines.append(f"✓ Git SHAs verified: {len(result.git_shas_verified)}")
        if verbose:
            for sha in result.git_shas_verified:
                lines.append(f"  - {sha}")

    if result.git_shas_failed:
        lines.append(f"✗ Git SHAs failed: {len(result.git_shas_failed)}")
        for sha in result.git_shas_failed:
            lines.append(f"  - {sha}")

    # Errors
    if result.errors:
        lines.append("")
        lines.append("Errors:")
        for error in result.errors:
            lines.append(f"  [{error.severity.upper()}] {error.field}: {error.message}")

    # Warnings
    if verbose and result.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in result.warnings:
            lines.append(f"  [WARNING] {warning.field}: {warning.message}")

    return "\n".join(lines)


def main() -> int:
    """
    Main entry point for the CLI.

    Returns:
        Exit code (0 for valid, 1 for invalid).
    """
    parser = argparse.ArgumentParser(
        prog="status_write_gate",
        description="Status write gate for EP-AUTO-GIT workflow file",
    )

    parser.add_argument(
        "--file",
        default=DEFAULT_STATUS_FILE,
        help=f"Path to the workflow status YAML file (default: {DEFAULT_STATUS_FILE})",
    )

    parser.add_argument(
        "--agent",
        default=None,
        help="Agent name (default: auto-detect from environment)",
    )

    parser.add_argument(
        "--no-verify-shas",
        action="store_true",
        help="Skip git SHA verification",
    )

    parser.add_argument(
        "--no-require-authority",
        action="store_true",
        help="Skip authority check (use with caution)",
    )

    parser.add_argument(
        "--repo-path",
        default=None,
        help="Path to git repository (default: current directory)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Run validation
    result = validate_status_write(
        yaml_file=args.file,
        agent=args.agent,
        verify_shas=not args.no_verify_shas,
        require_authority=not args.no_require_authority,
        repo_path=args.repo_path,
    )

    # Output results
    if args.json:
        import json

        output = {
            "valid": result.valid,
            "authority_valid": result.authority_valid,
            "yaml_valid": result.yaml_valid,
            "shas_verified": len(result.git_shas_verified),
            "shas_failed": len(result.git_shas_failed),
            "errors": [
                {"field": e.field, "message": e.message, "severity": e.severity}
                for e in result.errors
            ],
            "warnings": [
                {"field": w.field, "message": w.message, "severity": w.severity}
                for w in result.warnings
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_validation_report(result, args.verbose))

    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
