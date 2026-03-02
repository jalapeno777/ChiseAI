#!/usr/bin/env python3
"""
Compass Apply - Auto-labeling Script for Soul-Guided Compass Framework

This script auto-applies COMPASS-VETO label based on file changes in a PR.
It can be run in CI to automatically detect and label sensitive changes.

Usage:
    python3 scripts/ops/compass_apply.py --pr=<pr_number>
    python3 scripts/ops/compass_apply.py --dry-run --pr=<pr_number>
    python3 scripts/ops/compass_apply.py --files file1.py file2.py
    git diff --name-only | python3 scripts/ops/compass_apply.py
"""

import argparse
import fnmatch
import os
import sys
from pathlib import Path
from typing import Any

import yaml

# Get the repository root
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
COMPASS_CONFIG_PATH = REPO_ROOT / "docs" / "policy" / "compass.yaml"


class CompassApplyError(Exception):
    """Exception raised when compass apply operation fails."""

    pass


def load_compass_config() -> dict:
    """Load the compass policy configuration."""
    if not COMPASS_CONFIG_PATH.exists():
        raise CompassApplyError(f"Compass config not found: {COMPASS_CONFIG_PATH}")

    with open(COMPASS_CONFIG_PATH) as f:
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


def detect_sensitive_changes(files_changed: list[str]) -> dict[str, list[str]]:
    """
    Detect which files match veto path patterns.

    Returns:
        Dictionary mapping category to list of matching files
    """
    config = load_compass_config()
    veto_paths = config.get("veto_paths", {})

    matches = {}

    for category, patterns in veto_paths.items():
        category_matches = []
        for file_path in files_changed:
            file_path = file_path.strip()
            if not file_path:
                continue

            if match_glob_patterns(file_path, patterns):
                category_matches.append(file_path)

        if category_matches:
            matches[category] = category_matches

    return matches


def get_pr_labels(pr_number: int) -> list[str]:
    """
    Get current labels on a PR.

    In a real implementation, this would query the Gitea API.
    For now, returns from environment variable.
    """
    labels_env = os.environ.get("CI_PR_LABELS", "")
    return [label.strip() for label in labels_env.split(",") if label.strip()]


def apply_label(pr_number: int, label: str, dry_run: bool = False) -> bool:
    """
    Apply a label to a PR.

    In a real implementation, this would call the Gitea API.
    For now, it simulates the operation.

    Returns:
        True if label was applied (or would be in dry-run), False otherwise
    """
    current_labels = get_pr_labels(pr_number)

    if label in current_labels:
        print(f"  Label '{label}' already present on PR #{pr_number}")
        return False

    if dry_run:
        print(f"  [DRY RUN] Would apply label '{label}' to PR #{pr_number}")
        return True

    # In real implementation:
    # gitea_api.add_label(pr_number, label)
    print(f"  ✅ Applied label '{label}' to PR #{pr_number}")
    return True


def remove_label(pr_number: int, label: str, dry_run: bool = False) -> bool:
    """
    Remove a label from a PR.

    In a real implementation, this would call the Gitea API.

    Returns:
        True if label was removed (or would be in dry-run), False otherwise
    """
    current_labels = get_pr_labels(pr_number)

    if label not in current_labels:
        return False

    if dry_run:
        print(f"  [DRY RUN] Would remove label '{label}' from PR #{pr_number}")
        return True

    # In real implementation:
    # gitea_api.remove_label(pr_number, label)
    print(f"  ✅ Removed label '{label}' from PR #{pr_number}")
    return True


def run_apply(
    files_changed: list[str],
    pr_number: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Run the compass apply logic.

    Returns:
        Dictionary with results of the operation
    """
    print("=" * 60)
    print("SOUL-GUIDED COMPASS APPLY")
    print("=" * 60)

    if dry_run:
        print("\n🧪 DRY RUN MODE - No changes will be made\n")

    # Load config
    config = load_compass_config()
    auto_label_config = config.get("auto_label", {})

    if not auto_label_config.get("enabled", False):
        print("Auto-labeling is disabled in compass.yaml")
        return {"label_applied": False, "reason": "auto_label disabled"}

    label_name = auto_label_config.get("label_name", "COMPASS-VETO")

    # Detect sensitive changes
    print(f"\nAnalyzing {len(files_changed)} changed files...")
    sensitive_matches = detect_sensitive_changes(files_changed)

    if sensitive_matches:
        print("\n⚠️  SENSITIVE PATHS DETECTED:")
        for category, files in sensitive_matches.items():
            print(f"\n  {category.upper()}:")
            for f in files:
                print(f"    - {f}")
    else:
        print("\n✓ No sensitive paths detected")

    # Determine if label should be applied
    should_label = bool(sensitive_matches)

    result = {
        "label_applied": False,
        "label_removed": False,
        "sensitive_matches": sensitive_matches,
        "files_changed": files_changed,
        "pr_number": pr_number,
        "would_apply_label": False,
    }

    if should_label:
        result["would_apply_label"] = True
        result["reason"] = (
            f"Sensitive paths detected in: {list(sensitive_matches.keys())}"
        )

    if pr_number:
        print(f"\nPR #{pr_number} Label Management:")

        if should_label:
            # Apply COMPASS-VETO label
            applied = apply_label(pr_number, label_name, dry_run)
            result["label_applied"] = applied

            if applied:
                print(f"\n  🏷️  Label '{label_name}' applied because:")
                for category, files in sensitive_matches.items():
                    print(f"     - {len(files)} file(s) in {category} category")
        else:
            # Check if we should remove the label (if it was auto-applied before)
            # This is optional - could be controlled by a config flag
            current_labels = get_pr_labels(pr_number)
            if label_name in current_labels:
                print(f"\n  Note: Label '{label_name}' is present but no longer needed")
                # Uncomment to auto-remove:
                # removed = remove_label(pr_number, label_name, dry_run)
                # result['label_removed'] = removed
    else:
        # Just report what would happen
        if should_label:
            print(f"\n🏷️  Would apply label '{label_name}' to PR")
        else:
            print("\n✓ No labeling needed")

    print("\n" + "=" * 60)
    if should_label:
        print("⚠️  COMPASS-VETO RECOMMENDED")
    else:
        print("✅ NO VETO REQUIRED")
    print("=" * 60)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Compass Apply - Auto-label sensitive PR changes"
    )
    parser.add_argument("--pr", type=int, help="PR number to apply labels to")
    parser.add_argument(
        "--files", nargs="*", help="Files to check (if not provided, reads from stdin)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove COMPASS-VETO label instead of adding",
    )

    args = parser.parse_args()

    # Get files to check
    if args.files is not None:
        files_changed = args.files
    else:
        # Read from stdin
        files_changed = [line.strip() for line in sys.stdin if line.strip()]

    if not files_changed:
        print("No files to check.")
        sys.exit(0)

    # Run the apply logic
    try:
        if args.remove and args.pr:
            # Special case: remove label
            config = load_compass_config()
            label_name = config.get("auto_label", {}).get("label_name", "COMPASS-VETO")
            removed = remove_label(args.pr, label_name, args.dry_run)
            sys.exit(0 if removed else 0)  # Exit 0 even if not removed (idempotent)

        result = run_apply(files_changed, args.pr, args.dry_run)

        # Exit with appropriate code
        if result.get("label_applied") or result.get("would_apply_label"):
            # Label needed/was applied - this is informational, not an error
            sys.exit(0)
        else:
            sys.exit(0)

    except CompassApplyError as e:
        print(f"❌ Compass Apply Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
