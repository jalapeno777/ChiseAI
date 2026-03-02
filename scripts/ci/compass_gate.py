#!/usr/bin/env python3
"""
Compass Gate - CI Script for Soul-Guided Compass Framework

This script checks if COMPASS-VETO label is present without HUMAN-APPROVED
and fails the CI gate if so. It also checks if sensitive paths were changed
without proper labeling.

Usage:
    python3 scripts/ci/compass_gate.py --pr=<pr_number>
    python3 scripts/ci/compass_gate.py --check <file1> <file2> ...
    git diff --name-only | xargs python3 scripts/ci/compass_gate.py --check
"""

import argparse
import fnmatch
import os
import sys
from pathlib import Path

import yaml

# Get the repository root
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
COMPASS_CONFIG_PATH = REPO_ROOT / "docs" / "policy" / "compass.yaml"
HUMAN_APPROVAL_CONFIG_PATH = REPO_ROOT / "docs" / "policy" / "human_approval.yaml"


class CompassGateError(Exception):
    """Exception raised when compass gate check fails."""

    pass


def load_compass_config() -> dict:
    """Load the compass policy configuration."""
    if not COMPASS_CONFIG_PATH.exists():
        raise CompassGateError(f"Compass config not found: {COMPASS_CONFIG_PATH}")

    with open(COMPASS_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_human_approval_config() -> dict:
    """Load the human approval policy configuration."""
    if not HUMAN_APPROVAL_CONFIG_PATH.exists():
        raise CompassGateError(
            f"Human approval config not found: {HUMAN_APPROVAL_CONFIG_PATH}"
        )

    with open(HUMAN_APPROVAL_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def match_glob_patterns(file_path: str, patterns: list[str]) -> bool:
    """Check if a file path matches any of the glob patterns.

    Supports ** (globstar) for recursive directory matching.
    """
    import re

    for pattern in patterns:
        # Handle ** patterns (recursive matching)
        if "**" in pattern:
            # Convert ** pattern to regex
            regex_pattern = pattern
            # Replace **/ with a placeholder for directory matching (0 or more dirs)
            regex_pattern = regex_pattern.replace("**/", "{{GLOBSTAR_DIR}}")
            # Replace /** with a placeholder for end matching
            regex_pattern = regex_pattern.replace("/**", "{{END_GLOBSTAR}}")
            # Replace standalone **
            regex_pattern = regex_pattern.replace("**", "{{GLOBSTAR_ALL}}")

            # Escape dots and other regex special chars (but not our placeholders)
            # We need to escape before we put back the placeholders
            # So first, escape the whole thing, then unescape our placeholders
            regex_pattern = re.escape(regex_pattern)

            # Unescape our placeholders
            regex_pattern = regex_pattern.replace(
                r"\{\{GLOBSTAR_DIR\}\}", "{{GLOBSTAR_DIR}}"
            )
            regex_pattern = regex_pattern.replace(
                r"\{\{END_GLOBSTAR\}\}", "{{END_GLOBSTAR}}"
            )
            regex_pattern = regex_pattern.replace(
                r"\{\{GLOBSTAR_ALL\}\}", "{{GLOBSTAR_ALL}}"
            )

            # Replace placeholders with proper regex
            regex_pattern = regex_pattern.replace("{{GLOBSTAR_DIR}}", "(?:.*/)?")
            regex_pattern = regex_pattern.replace("{{END_GLOBSTAR}}", "(?:/.*)?")
            regex_pattern = regex_pattern.replace("{{GLOBSTAR_ALL}}", ".*")
            regex_pattern = regex_pattern.replace(r"\*", "[^/]*")
            regex_pattern = regex_pattern.replace(r"\?", ".")

            # Anchor the pattern
            regex_pattern = "^" + regex_pattern + "$"

            if re.match(regex_pattern, file_path):
                return True
        else:
            # Use standard fnmatch for non-recursive patterns
            if fnmatch.fnmatch(file_path, pattern):
                return True
    return False


def get_veto_patterns(config: dict) -> list[str]:
    """Extract all veto path patterns from compass config."""
    patterns = []
    veto_paths = config.get("veto_paths", {})

    for category, category_patterns in veto_paths.items():
        patterns.extend(category_patterns)

    return patterns


def get_sensitive_path_patterns(config: dict) -> list[tuple[str, str]]:
    """Extract all sensitive path patterns with their categories from human approval config."""
    patterns = []
    sensitive_paths = config.get("sensitive_paths", {})

    for category, config_data in sensitive_paths.items():
        path_list = config_data.get("paths", [])
        for pattern in path_list:
            patterns.append((pattern, category))

    return patterns


def check_sensitive_paths(
    files_changed: list[str],
) -> tuple[bool, list[str], list[str]]:
    """
    Check if any files match veto or sensitive path patterns.

    Returns:
        Tuple of (has_sensitive_changes, veto_matches, sensitive_matches)
    """
    compass_config = load_compass_config()
    human_config = load_human_approval_config()

    veto_patterns = get_veto_patterns(compass_config)
    sensitive_patterns = get_sensitive_path_patterns(human_config)

    veto_matches = []
    sensitive_matches = []

    for file_path in files_changed:
        # Normalize path
        file_path = file_path.strip()
        if not file_path:
            continue

        # Check veto patterns
        if match_glob_patterns(file_path, veto_patterns):
            veto_matches.append(file_path)

        # Check sensitive patterns
        for pattern, category in sensitive_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                sensitive_matches.append(f"{file_path} ({category})")

    has_sensitive = bool(veto_matches or sensitive_matches)
    return has_sensitive, veto_matches, sensitive_matches


def check_pr_labels(pr_number: int) -> tuple[bool, bool]:
    """
    Check PR labels for COMPASS-VETO and HUMAN-APPROVED.

    Returns:
        Tuple of (has_compass_veto, has_human_approved)
    """
    # In a real implementation, this would query the Gitea API
    # For now, we'll check environment variables that CI would set
    labels_env = os.environ.get("CI_PR_LABELS", "")
    labels = [label.strip() for label in labels_env.split(",") if label.strip()]

    has_compass_veto = "COMPASS-VETO" in labels
    has_human_approved = "HUMAN-APPROVED" in labels

    return has_compass_veto, has_human_approved


def run_gate_check(files_changed: list[str], pr_number: int | None = None) -> bool:
    """
    Run the compass gate check.

    Returns:
        True if gate passes, False if it fails
    """
    print("=" * 60)
    print("SOUL-GUIDED COMPASS GATE")
    print("=" * 60)

    # Check for sensitive path changes
    has_sensitive, veto_matches, sensitive_matches = check_sensitive_paths(
        files_changed
    )

    print(f"\nFiles changed: {len(files_changed)}")
    for f in files_changed:
        print(f"  - {f}")

    if veto_matches:
        print(f"\n⚠️  VETO PATH MATCHES ({len(veto_matches)}):")
        for match in veto_matches:
            print(f"  ⚡ {match}")

    if sensitive_matches:
        print(f"\n⚠️  SENSITIVE PATH MATCHES ({len(sensitive_matches)}):")
        for match in sensitive_matches:
            print(f"  ⚡ {match}")

    # Check PR labels if PR number provided
    if pr_number:
        has_compass_veto, has_human_approved = check_pr_labels(pr_number)
    else:
        # For local testing, check environment
        has_compass_veto, has_human_approved = check_pr_labels(0)

    print("\nLabel Status:")
    print(f"  COMPASS-VETO: {'✓ Present' if has_compass_veto else '✗ Not present'}")
    print(f"  HUMAN-APPROVED: {'✓ Present' if has_human_approved else '✗ Not present'}")

    # Gate logic
    compass_config = load_compass_config()
    ci_gate_config = compass_config.get("ci_gate", {})
    fail_conditions = ci_gate_config.get("fail_on", [])

    gate_passed = True
    failures = []

    # Check: compass_veto_present_without_approval
    if "compass_veto_present_without_approval" in fail_conditions:
        if has_compass_veto and not has_human_approved:
            gate_passed = False
            failures.append("COMPASS-VETO label present without HUMAN-APPROVED")

    # Check: sensitive_path_changed_without_label
    if "sensitive_path_changed_without_label" in fail_conditions:
        if has_sensitive and not has_compass_veto and not has_human_approved:
            gate_passed = False
            failures.append(
                "Sensitive paths changed without COMPASS-VETO or HUMAN-APPROVED label"
            )

    print("\n" + "=" * 60)
    if gate_passed:
        print("✅ COMPASS GATE PASSED")
    else:
        print("❌ COMPASS GATE FAILED")
        print("\nFailures:")
        for failure in failures:
            print(f"  - {failure}")
    print("=" * 60)

    return gate_passed


def main():
    parser = argparse.ArgumentParser(
        description="Compass Gate - Constitutional governance CI check"
    )
    parser.add_argument("--pr", type=int, help="PR number to check labels for")
    parser.add_argument(
        "--check", nargs="*", help="Files to check (if not provided, reads from stdin)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would happen without failing"
    )

    args = parser.parse_args()

    # Get files to check
    if args.check is not None:
        files_changed = args.check
    else:
        # Read from stdin
        files_changed = [line.strip() for line in sys.stdin if line.strip()]

    if not files_changed:
        print("No files to check. Compass gate passes by default.")
        sys.exit(0)

    # Run the gate check
    try:
        passed = run_gate_check(files_changed, args.pr)

        if args.dry_run:
            print("\n(Dry run - exit code 0)")
            sys.exit(0)
        elif passed:
            sys.exit(0)
        else:
            sys.exit(1)
    except CompassGateError as e:
        print(f"❌ Compass Gate Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
