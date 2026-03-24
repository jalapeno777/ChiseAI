#!/usr/bin/env python3
"""
Governance Drift Guard - CI validation script for EP-GOV-001 status consistency.

This script detects drift between:
1. EP-GOV-001 epic status in docs/bmm-workflow-status.yaml
2. Governance merge evidence in docs/evidence/GOVERNANCE_MERGE_EVIDENCE_2026-03-08.md

Exit codes:
    0 - No drift detected (evidence matches workflow status)
    1 - Drift detected (mismatch found)
    2 - Script error (file not found, parse error, etc.)

Usage:
    python3 scripts/validation/governance_drift_guard.py
    python3 scripts/validation/governance_drift_guard.py --verbose
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

# Default file paths (relative to repo root)
DEFAULT_WORKFLOW_STATUS_PATH = Path("docs/bmm-workflow-status.yaml")
DEFAULT_EVIDENCE_PATH = Path("docs/evidence/GOVERNANCE_MERGE_EVIDENCE_2026-03-08.md")

# Epic ID to validate
EPIC_ID = "EP-GOV-001"


def parse_workflow_status(file_path: Path) -> dict:
    """
    Parse the workflow status YAML file.

    Args:
        file_path: Path to the workflow status YAML file.

    Returns:
        Dictionary containing the parsed YAML content.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the YAML is invalid.
    """
    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_epic_status(data: dict, epic_id: str) -> dict | None:
    """
    Extract the status information for a specific epic.

    Args:
        data: Parsed workflow status data.
        epic_id: The epic ID to look for.

    Returns:
        Dictionary with epic status info, or None if not found.
    """
    epics = data.get("epics", [])
    for epic in epics:
        if epic.get("id") == epic_id:
            return {
                "id": epic.get("id"),
                "status": epic.get("status"),
                "stories_completed": epic.get("stories_completed", 0),
                "story_ids": epic.get("story_ids", []),
                "story_count": epic.get("story_count", 0),
            }
    return None


def parse_evidence_file(file_path: Path) -> list:
    """
    Parse the governance merge evidence markdown file.

    Extracts story IDs from table rows in the evidence file.

    Args:
        file_path: Path to the evidence markdown file.

    Returns:
        List of story IDs found in the evidence file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    # Pattern to match story ID rows in tables
    # Looks for: | **Story ID** | ST-GOV-XXX | or | **Story ID** | ST-GOV-MINI-XXX |
    pattern = r"\|\s*\*\*Story ID\*\*\s*\|\s*(ST-GOV-(?:\d+|MINI-\d+))\s*\|"
    matches = re.findall(pattern, content)

    return sorted(set(matches))


def extract_evidence_summary(file_path: Path) -> dict:
    """
    Extract summary information from the evidence file.

    Args:
        file_path: Path to the evidence markdown file.

    Returns:
        Dictionary with evidence summary info.
    """
    # Find the cross-branch verification summary table
    story_ids = parse_evidence_file(file_path)

    return {
        "story_count": len(story_ids),
        "story_ids": story_ids,
    }


def detect_drift(
    workflow_status: dict,
    evidence_summary: dict,
    verbose: bool = False,
) -> tuple[bool, list[str]]:
    """
    Detect drift between workflow status and evidence.

    Args:
        workflow_status: Epic status from workflow status file.
        evidence_summary: Summary from evidence file.
        verbose: Whether to print detailed information.

    Returns:
        Tuple of (has_drift, list of drift messages).
    """
    drift_messages = []

    if workflow_status is None:
        return True, [f"Epic {EPIC_ID} not found in workflow status"]

    workflow_stories = set(workflow_status.get("story_ids", []))
    evidence_stories = set(evidence_summary.get("story_ids", []))

    # Check 1: Count mismatch (evidence stories should be subset of workflow stories)
    # The workflow may have more stories verified than evidence documents
    # This is OK as long as all evidence stories are in workflow

    # Check 2: Stories in evidence but not in workflow status
    evidence_only = evidence_stories - workflow_stories
    if evidence_only:
        drift_messages.append(
            f"Stories in evidence but not in workflow status: {sorted(evidence_only)}"
        )

    # Check 3: Stories count sanity check
    # Evidence should document a reasonable subset of workflow stories
    workflow_count = workflow_status.get("stories_completed", 0)
    evidence_count = evidence_summary.get("story_count", 0)

    if verbose:
        print(f"Workflow status: {workflow_count} stories completed")
        print(f"Evidence file: {evidence_count} stories documented")
        print(f"Workflow stories: {sorted(workflow_stories)}")
        print(f"Evidence stories: {sorted(evidence_stories)}")

    # Evidence stories should be subset of workflow stories
    if evidence_only:
        drift_messages.append(
            f"Evidence contains {len(evidence_only)} stories not in workflow status"
        )

    # Additional check: If evidence count > workflow count, that's a problem
    if evidence_count > workflow_count:
        drift_messages.append(
            f"Evidence count ({evidence_count}) exceeds workflow count ({workflow_count})"
        )

    has_drift = len(drift_messages) > 0
    return has_drift, drift_messages


def main() -> int:
    """
    Main entry point for the drift guard script.

    Returns:
        Exit code (0 = no drift, 1 = drift detected, 2 = error).
    """
    parser = argparse.ArgumentParser(
        description="Validate EP-GOV-001 status consistency between workflow status and evidence."
    )
    parser.add_argument(
        "--workflow-status",
        type=Path,
        default=DEFAULT_WORKFLOW_STATUS_PATH,
        help="Path to workflow status YAML file",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=DEFAULT_EVIDENCE_PATH,
        help="Path to governance merge evidence markdown file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    try:
        # Parse workflow status
        if args.verbose:
            print(f"Parsing workflow status: {args.workflow_status}")
        workflow_data = parse_workflow_status(args.workflow_status)
        epic_status = extract_epic_status(workflow_data, EPIC_ID)

        if epic_status is None:
            print(
                f"ERROR: Epic {EPIC_ID} not found in workflow status", file=sys.stderr
            )
            return 2

        if args.verbose:
            print(f"Found epic: {epic_status['id']}")
            print(f"Status: {epic_status['status']}")
            print(f"Stories completed: {epic_status['stories_completed']}")

        # Parse evidence file
        if args.verbose:
            print(f"\nParsing evidence file: {args.evidence}")
        evidence_summary = extract_evidence_summary(args.evidence)

        if args.verbose:
            print(f"Evidence stories documented: {evidence_summary['story_count']}")

        # Detect drift
        if args.verbose:
            print("\n--- Drift Detection ---")
        has_drift, messages = detect_drift(epic_status, evidence_summary, args.verbose)

        if has_drift:
            print("\nGOVERNANCE DRIFT DETECTED", file=sys.stderr)
            for msg in messages:
                print(f"  - {msg}", file=sys.stderr)
            return 1
        else:
            if args.verbose:
                print("\n✓ No drift detected")
                print(
                    f"  Workflow: {epic_status['stories_completed']} stories completed"
                )
                print(
                    f"  Evidence: {evidence_summary['story_count']} stories documented"
                )
                print("  All evidence stories verified in workflow status")
            else:
                print("✓ Governance status consistent")
            return 0

    except FileNotFoundError as e:
        print(f"ERROR: File not found: {e.filename}", file=sys.stderr)
        return 2
    except yaml.YAMLError as e:
        print(f"ERROR: Failed to parse YAML: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
