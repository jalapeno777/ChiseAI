#!/usr/bin/env python3
"""
Comprehensive Traceability Drift Checker

Combines multiple validation checks into a single command:
- FR traceability (PRD FRs covered by stories)
- Validation registry completeness
- Epic status consistency with child stories
- Phase/sprint metadata consistency

Exit codes:
    0 - No drift detected
    1 - Drift detected (traceability issues)
    2 - Error (file not found, parsing error, etc.)

Usage:
    python scripts/validate_traceability_drift.py
    python scripts/validate_traceability_drift.py --json
    python scripts/validate_traceability_drift.py --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Bootstrap environment first (must be before any env access)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

# Configuration
WORKFLOW_STATUS_FILE = Path("docs/bmm-workflow-status.yaml")
VALIDATION_REGISTRY_FILE = Path("docs/validation/validation-registry.yaml")
PRD_FILE = Path("docs/prd.md")

# FR pattern: FR-XXX or FR-XX
FR_PATTERN = re.compile(r"FR-\d{2,3}")


@dataclass
class DriftIssue:
    """Represents a single drift issue."""

    category: str
    severity: str  # "error" or "warning"
    message: str
    entity_id: str | None = None
    suggestion: str | None = None


@dataclass
class DriftReport:
    """Complete drift report."""

    valid: bool = True
    errors: list[DriftIssue] = field(default_factory=list)
    warnings: list[DriftIssue] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def add_error(
        self,
        category: str,
        message: str,
        entity_id: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.errors.append(
            DriftIssue(
                category=category,
                severity="error",
                message=message,
                entity_id=entity_id,
                suggestion=suggestion,
            )
        )
        self.valid = False

    def add_warning(
        self,
        category: str,
        message: str,
        entity_id: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.warnings.append(
            DriftIssue(
                category=category,
                severity="warning",
                message=message,
                entity_id=entity_id,
                suggestion=suggestion,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "summary": {
                "total_issues": len(self.errors) + len(self.warnings),
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
            "stats": self.stats,
            "errors": [
                {
                    "category": e.category,
                    "severity": e.severity,
                    "message": e.message,
                    "entity_id": e.entity_id,
                    "suggestion": e.suggestion,
                }
                for e in self.errors
            ],
            "warnings": [
                {
                    "category": w.category,
                    "severity": w.severity,
                    "message": w.message,
                    "entity_id": w.entity_id,
                    "suggestion": w.suggestion,
                }
                for w in self.warnings
            ],
        }


def load_yaml_file(filepath: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load and parse a YAML file."""
    if not filepath.exists():
        return None, f"File not found: {filepath}"

    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
        return data, None
    except yaml.YAMLError as e:
        return None, f"YAML parsing error in {filepath}: {e}"
    except OSError as e:
        return None, f"IO error reading {filepath}: {e}"


def load_prd_file(filepath: Path) -> tuple[str | None, str | None]:
    """Load PRD markdown file."""
    if not filepath.exists():
        return None, f"File not found: {filepath}"

    try:
        with open(filepath) as f:
            return f.read(), None
    except OSError as e:
        return None, f"IO error reading {filepath}: {e}"


def extract_frs_from_prd(content: str) -> set[str]:
    """Extract all FR references from PRD content."""
    return set(FR_PATTERN.findall(content))


def extract_fr_coverage_from_stories(
    stories: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Extract FR coverage mapping from stories."""
    coverage: dict[str, list[str]] = {}

    for story in stories:
        if not isinstance(story, dict):
            continue

        story_id = story.get("id", "unknown")
        fr_coverage = story.get("fr_coverage", [])

        if isinstance(fr_coverage, str):
            fr_coverage = [fr_coverage]

        for fr_id in fr_coverage:
            if isinstance(fr_id, str):
                if fr_id not in coverage:
                    coverage[fr_id] = []
                coverage[fr_id].append(story_id)

    return coverage


def check_fr_traceability(
    report: DriftReport,
    workflow_data: dict[str, Any],
    prd_content: str,
) -> None:
    """Check FR traceability from PRD to stories."""
    prd_frs = extract_frs_from_prd(prd_content)
    stories = workflow_data.get("stories", [])
    fr_coverage = extract_fr_coverage_from_stories(stories)
    covered_frs = set(fr_coverage.keys())

    report.stats["fr_traceability"] = {
        "total_frs_in_prd": len(prd_frs),
        "frs_covered_by_stories": len(covered_frs),
        "orphaned_frs": len(prd_frs - covered_frs),
    }

    # Check for orphaned FRs
    orphaned_frs = prd_frs - covered_frs
    for fr_id in sorted(orphaned_frs):
        report.add_error(
            category="fr_traceability",
            message=f"FR '{fr_id}' is not covered by any story",
            entity_id=fr_id,
            suggestion="Add fr_coverage to an appropriate story or create a new story",
        )

    # Check for FRs covered by stories but not in PRD
    extra_frs = covered_frs - prd_frs
    for fr_id in sorted(extra_frs):
        report.add_warning(
            category="fr_traceability",
            message=f"FR '{fr_id}' is covered by stories but not defined in PRD",
            entity_id=fr_id,
            suggestion="Verify FR ID is correct or add to PRD",
        )


def check_validation_registry_coverage(
    report: DriftReport,
    workflow_data: dict[str, Any],
    validation_data: dict[str, Any],
) -> None:
    """Check validation registry coverage for stories."""
    validations = validation_data.get("validations", [])
    stories = workflow_data.get("stories", [])
    epics = workflow_data.get("epics", [])

    # Build set of story IDs with validations
    validated_story_ids: dict[str, str] = {}  # story_id -> validation status
    for validation in validations:
        if isinstance(validation, dict):
            story_id = validation.get("story_id")
            status = validation.get("status")
            if story_id:
                validated_story_ids[story_id] = status

    # Build set of all story IDs from stories section
    all_story_ids: dict[str, dict[str, Any]] = {}
    for story in stories:
        if isinstance(story, dict):
            story_id = story.get("id")
            if story_id:
                all_story_ids[story_id] = story

    # Also collect story IDs from epics
    epic_story_ids: set[str] = set()
    for epic in epics:
        if isinstance(epic, dict):
            for story_id in epic.get("story_ids", []):
                epic_story_ids.add(story_id)

    report.stats["validation_coverage"] = {
        "total_stories": len(all_story_ids),
        "stories_with_validation": len(validated_story_ids),
        "stories_without_validation": len(all_story_ids) - len(validated_story_ids),
    }

    # Check for stories without validation entries
    for story_id in sorted(all_story_ids.keys()):
        if story_id not in validated_story_ids:
            report.add_error(
                category="validation_coverage",
                message=f"Story '{story_id}' has no validation entry",
                entity_id=story_id,
                suggestion="Add validation entry to docs/validation/validation-registry.yaml",
            )

    # Check for validation entries referencing non-existent stories
    for story_id in sorted(validated_story_ids.keys()):
        if story_id not in all_story_ids and story_id not in epic_story_ids:
            report.add_error(
                category="validation_coverage",
                message=f"Validation references non-existent story '{story_id}'",
                entity_id=story_id,
                suggestion="Remove validation entry or create the story",
            )

    # Check for status inconsistencies
    for story_id, validation_status in validated_story_ids.items():
        story = all_story_ids.get(story_id)
        if story:
            story_status = story.get("status")

            # Flag if story is completed but validation is not validated
            if story_status == "completed" and validation_status != "validated":
                report.add_error(
                    category="validation_status_sync",
                    message=(
                        f"Story '{story_id}' is marked 'completed' but "
                        f"validation status is '{validation_status}'"
                    ),
                    entity_id=story_id,
                    suggestion="Update validation status to 'validated' or story status to 'in_progress'",
                )

            # Flag if validation is validated but story is not completed
            if validation_status == "validated" and story_status != "completed":
                report.add_warning(
                    category="validation_status_sync",
                    message=(
                        f"Validation for '{story_id}' is 'validated' but "
                        f"story status is '{story_status}'"
                    ),
                    entity_id=story_id,
                    suggestion="Verify story status is correct",
                )


def check_epic_consistency(
    report: DriftReport,
    workflow_data: dict[str, Any],
) -> None:
    """Check epic status consistency with child stories."""
    epics = workflow_data.get("epics", [])
    stories = workflow_data.get("stories", [])

    # Build story lookup
    story_map: dict[str, dict[str, Any]] = {}
    for story in stories:
        if isinstance(story, dict):
            story_id = story.get("id")
            if story_id:
                story_map[story_id] = story

    for epic in epics:
        if not isinstance(epic, dict):
            continue

        epic_id = epic.get("id")
        epic_status = epic.get("status")
        epic_story_ids = epic.get("story_ids", [])

        if not epic_id:
            continue

        # Get statuses of all child stories
        child_statuses: list[str] = []
        for story_id in epic_story_ids:
            story = story_map.get(story_id)
            if story:
                child_statuses.append(story.get("status", "unknown"))

        if not child_statuses:
            report.add_warning(
                category="epic_consistency",
                message=f"Epic '{epic_id}' has no child stories defined",
                entity_id=epic_id,
            )
            continue

        # Check consistency
        all_completed = all(s == "completed" for s in child_statuses)
        any_in_progress = any(s == "in_progress" for s in child_statuses)
        all_planned = all(s == "planned" for s in child_statuses)

        # Epic should be completed if all children are completed
        if all_completed and epic_status != "completed":
            report.add_warning(
                category="epic_consistency",
                message=(
                    f"Epic '{epic_id}' status is '{epic_status}' but "
                    f"all {len(child_statuses)} child stories are completed"
                ),
                entity_id=epic_id,
                suggestion=f"Consider updating epic status to 'completed'",
            )

        # Epic should be in_progress if any child is in_progress
        if any_in_progress and epic_status not in ["in_progress", "completed"]:
            report.add_warning(
                category="epic_consistency",
                message=(
                    f"Epic '{epic_id}' status is '{epic_status}' but "
                    f"at least one child story is in_progress"
                ),
                entity_id=epic_id,
                suggestion=f"Consider updating epic status to 'in_progress'",
            )

        # Epic should be planned if all children are planned
        if all_planned and epic_status not in ["planned", "in_progress", "completed"]:
            report.add_warning(
                category="epic_consistency",
                message=(
                    f"Epic '{epic_id}' status is '{epic_status}' but "
                    f"all child stories are planned"
                ),
                entity_id=epic_id,
                suggestion=f"Consider updating epic status to 'planned'",
            )


def check_phase_sprint_consistency(
    report: DriftReport,
    workflow_data: dict[str, Any],
) -> None:
    """Check phase and sprint metadata consistency."""
    current_phase = workflow_data.get("current_phase", {})
    epics = workflow_data.get("epics", [])
    stories = workflow_data.get("stories", [])

    phase_id = current_phase.get("phase")
    phase_status = current_phase.get("status")

    report.stats["phase_info"] = {
        "current_phase": phase_id,
        "phase_status": phase_status,
    }

    # Check if any epics are in_progress but phase is not
    if phase_status != "in_progress":
        for epic in epics:
            if not isinstance(epic, dict):
                continue
            if epic.get("status") == "in_progress":
                report.add_warning(
                    category="phase_consistency",
                    message=(
                        f"Epic '{epic.get('id')}' is in_progress but "
                        f"current phase '{phase_id}' is '{phase_status}'"
                    ),
                    entity_id=epic.get("id"),
                    suggestion=f"Consider updating phase status to 'in_progress'",
                )

    # Collect all sprint references
    epic_sprints: set[str] = set()
    for epic in epics:
        if isinstance(epic, dict):
            sprint_id = epic.get("sprint_id")
            if sprint_id:
                epic_sprints.add(sprint_id)

    story_sprints: set[str] = set()
    for story in stories:
        if isinstance(story, dict):
            sprint_id = story.get("sprint_id")
            if sprint_id:
                story_sprints.add(sprint_id)

    # Check for stories with sprints not in epics
    orphaned_sprints = story_sprints - epic_sprints
    for sprint_id in sorted(orphaned_sprints):
        report.add_warning(
            category="sprint_consistency",
            message=f"Sprint '{sprint_id}' is referenced by stories but not by any epic",
            entity_id=sprint_id,
        )


def print_report(report: DriftReport, verbose: bool = False) -> None:
    """Print drift report in human-readable format."""
    if report.errors:
        print("\n❌ ERRORS (blocking drift):")
        for error in report.errors:
            print(f"  [{error.category}] {error.message}")
            if error.suggestion:
                print(f"    💡 Suggestion: {error.suggestion}")

    if report.warnings:
        print("\n⚠️  WARNINGS (non-blocking):")
        for warning in report.warnings:
            print(f"  [{warning.category}] {warning.message}")
            if warning.suggestion:
                print(f"    💡 Suggestion: {warning.suggestion}")

    if verbose and report.stats:
        print("\n📊 Statistics:")
        for category, stats in report.stats.items():
            if isinstance(stats, dict):
                print(f"  {category}:")
                for key, value in stats.items():
                    print(f"    {key}: {value}")
            else:
                print(f"  {category}: {stats}")

    if report.valid and not report.warnings:
        print("\n✅ No traceability drift detected")
    elif report.valid:
        print(f"\n✅ No blocking drift detected ({len(report.warnings)} warnings)")
    else:
        print(
            f"\n❌ Drift detected: {len(report.errors)} errors, {len(report.warnings)} warnings"
        )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive traceability drift checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
    0 - No drift detected
    1 - Drift detected (traceability issues)
    2 - Error (file not found, parsing error)
        """,
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for CI parsing",
    )
    parser.add_argument(
        "--skip-fr-check",
        action="store_true",
        help="Skip FR traceability check",
    )
    parser.add_argument(
        "--skip-validation-check",
        action="store_true",
        help="Skip validation registry check",
    )
    parser.add_argument(
        "--skip-epic-check",
        action="store_true",
        help="Skip epic consistency check",
    )
    args = parser.parse_args()

    report = DriftReport()

    # Load required files
    workflow_data, error = load_yaml_file(WORKFLOW_STATUS_FILE)
    if error:
        if args.json:
            print(json.dumps({"error": error, "valid": False}))
        else:
            print(f"❌ {error}", file=sys.stderr)
        return 2

    validation_data, error = load_yaml_file(VALIDATION_REGISTRY_FILE)
    if error:
        if args.json:
            print(json.dumps({"error": error, "valid": False}))
        else:
            print(f"❌ {error}", file=sys.stderr)
        return 2

    prd_content, error = load_prd_file(PRD_FILE)
    if error:
        if args.json:
            print(json.dumps({"error": error, "valid": False}))
        else:
            print(f"❌ {error}", file=sys.stderr)
        return 2

    # Run checks
    if not args.skip_fr_check:
        check_fr_traceability(report, workflow_data, prd_content)

    if not args.skip_validation_check:
        check_validation_registry_coverage(report, workflow_data, validation_data)

    if not args.skip_epic_check:
        check_epic_consistency(report, workflow_data)
        check_phase_sprint_consistency(report, workflow_data)

    # Output results
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report, verbose=args.verbose)

    # Return appropriate exit code
    if not report.valid:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
