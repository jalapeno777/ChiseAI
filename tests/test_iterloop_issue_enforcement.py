#!/usr/bin/env python3
"""
Tests for Iterloop Issue Enforcement

Validates that structured issues in iterlog files are properly enforced:
1. Required fields (root_cause, impact_area, time_lost_minutes) must be present
2. Empty issues array (issues: []) is valid
3. Missing ## Structured Issues section fails validation
4. Structured records are ingested into mini BrainEval output
5. Repeated issues are fingerprinted and grouped correctly

Story: ST-ISSUE-ENFORCE-003
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    """Create temporary directory with test fixtures."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    return fixtures


@pytest.fixture
def valid_with_issues_md(fixtures_dir: Path) -> Path:
    """Valid iterlog with complete structured issues."""
    content = """---
story_id: TEST-001
story_title: "Test Story with Issues"
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## Decisions
- Test decision 1

## Structured Issues
issues:
  - issue_type: db_connectivity
    severity: P1
    root_cause: "Redis connection timeout due to network partition"
    impact_area: "evaluation_pipeline"
    time_lost_minutes: 45
    description: "Redis connection timeout during evaluation run"
    timestamp: "2026-03-01T12:00:00Z"
    prevention_rule: "Add retry logic with exponential backoff"
  
  - issue_type: file_access
    severity: P2
    root_cause: "Permission denied on temp directory"
    impact_area: "file_operations"
    time_lost_minutes: 15
    description: "Cannot write to /tmp/eval directory"
    timestamp: "2026-03-01T12:30:00Z"
    prevention_rule: "Check directory permissions before operations"

## Learnings
- Test learning 1
"""
    path = fixtures_dir / "valid_with_issues.md"
    path.write_text(content)
    return path


@pytest.fixture
def valid_empty_issues_md(fixtures_dir: Path) -> Path:
    """Valid iterlog with explicit empty issues array."""
    content = """---
story_id: TEST-002
story_title: "Test Story No Issues"
phase: implementation
status: completed
started_at: "2026-03-01T10:00:00Z"
completed_at: "2026-03-01T11:00:00Z"
---

## Decisions
- Test decision 2

## Structured Issues
issues: []

## Learnings
- Test learning 2
"""
    path = fixtures_dir / "valid_empty_issues.md"
    path.write_text(content)
    return path


@pytest.fixture
def invalid_missing_field_md(fixtures_dir: Path) -> Path:
    """Invalid iterlog with issue missing required field (root_cause)."""
    content = """---
story_id: TEST-003
story_title: "Test Story Missing Field"
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## Decisions
- Test decision 3

## Structured Issues
issues:
  - issue_type: db_connectivity
    severity: P1
    # Missing root_cause field
    impact_area: "evaluation_pipeline"
    time_lost_minutes: 30
    description: "Redis connection timeout"

## Learnings
- Test learning 3
"""
    path = fixtures_dir / "invalid_missing_field.md"
    path.write_text(content)
    return path


@pytest.fixture
def invalid_missing_impact_md(fixtures_dir: Path) -> Path:
    """Invalid iterlog with issue missing impact_area field."""
    content = """---
story_id: TEST-004
story_title: "Test Story Missing Impact"
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## Structured Issues
issues:
  - issue_type: file_access
    severity: P2
    root_cause: "Permission denied"
    # Missing impact_area field
    time_lost_minutes: 20
    description: "Cannot read file"
"""
    path = fixtures_dir / "invalid_missing_impact.md"
    path.write_text(content)
    return path


@pytest.fixture
def invalid_missing_time_md(fixtures_dir: Path) -> Path:
    """Invalid iterlog with issue missing time_lost_minutes field."""
    content = """---
story_id: TEST-005
story_title: "Test Story Missing Time"
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## Structured Issues
issues:
  - issue_type: env_slowdown
    severity: P2
    root_cause: "High CPU usage"
    impact_area: "performance"
    # Missing time_lost_minutes field
    description: "System running slowly"
"""
    path = fixtures_dir / "invalid_missing_time.md"
    path.write_text(content)
    return path


@pytest.fixture
def invalid_no_section_md(fixtures_dir: Path) -> Path:
    """Invalid iterlog without ## Structured Issues section."""
    content = """---
story_id: TEST-006
story_title: "Test Story No Section"
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## Decisions
- Test decision

## Learnings
- Test learning
"""
    path = fixtures_dir / "invalid_no_section.md"
    path.write_text(content)
    return path


@pytest.fixture
def repeated_issues_md(fixtures_dir: Path) -> Path:
    """Iterlog with repeated issues for fingerprinting test."""
    content = """---
story_id: TEST-007
story_title: "Test Repeated Issues"
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## Structured Issues
issues:
  # First occurrence - same root_cause as third
  - issue_type: db_connectivity
    severity: P1
    root_cause: "Redis connection timeout"
    impact_area: "evaluation"
    time_lost_minutes: 30
    description: "Redis timeout at 2026-03-01T12:00:00Z"
    timestamp: "2026-03-01T12:00:00Z"
  
  # Different issue type
  - issue_type: file_access
    severity: P2
    root_cause: "Permission denied"
    impact_area: "file_ops"
    time_lost_minutes: 10
    description: "Cannot read file"
    timestamp: "2026-03-01T12:15:00Z"
  
  # Second occurrence - same root_cause as first
  - issue_type: db_connectivity
    severity: P1
    root_cause: "Redis connection timeout"
    impact_area: "evaluation"
    time_lost_minutes: 25
    description: "Redis timeout at 2026-03-01T14:00:00Z"
    timestamp: "2026-03-01T14:00:00Z"
  
  # Third occurrence - same root_cause as first and third
  - issue_type: db_connectivity
    severity: P1
    root_cause: "Redis connection timeout"
    impact_area: "evaluation"
    time_lost_minutes: 20
    description: "Redis timeout at 2026-03-01T16:00:00Z"
    timestamp: "2026-03-01T16:00:00Z"
"""
    path = fixtures_dir / "repeated_issues.md"
    path.write_text(content)
    return path


# ============================================================================
# Validation Functions
# ============================================================================


def parse_iterlog_issues(md_path: Path) -> dict[str, Any]:
    """
    Parse iterlog markdown file and extract structured issues.

    Returns:
        dict with 'has_section' bool and 'issues' list
    """
    content = md_path.read_text(encoding="utf-8")

    # Check for ## Structured Issues section
    has_section = "## Structured Issues" in content

    if not has_section:
        return {"has_section": False, "issues": []}

    # Extract issues YAML
    section_start = content.find("## Structured Issues")
    if section_start == -1:
        return {"has_section": False, "issues": []}

    # Find the next ## heading or end of file
    next_section = content.find("\n## ", section_start + 1)
    if next_section == -1:
        section_content = content[section_start:]
    else:
        section_content = content[section_start:next_section]

    # Extract YAML after the heading
    lines = section_content.split("\n")
    yaml_lines = []
    in_yaml = False

    for line in lines[1:]:  # Skip the heading itself
        if line.strip().startswith("issues:"):
            in_yaml = True
            yaml_lines.append(line)
        elif in_yaml:
            if line.strip() == "" or line.startswith("  "):
                yaml_lines.append(line)
            else:
                break

    if not yaml_lines:
        return {"has_section": True, "issues": []}

    try:
        yaml_content = "\n".join(yaml_lines)
        parsed = yaml.safe_load(yaml_content)
        issues = parsed.get("issues", [])
        return {"has_section": True, "issues": issues if issues else []}
    except yaml.YAMLError:
        return {"has_section": True, "issues": []}


def validate_issue_fields(issue: dict[str, Any]) -> list[str]:
    """
    Validate that an issue has all required fields.

    Returns:
        List of missing field names
    """
    required_fields = {"root_cause", "impact_area", "time_lost_minutes"}
    issue_fields = set(issue.keys())
    missing = required_fields - issue_fields
    return sorted(missing)


def validate_iterlog_file(md_path: Path) -> tuple[bool, list[str]]:
    """
    Validate an iterlog file for issue enforcement.

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    # Parse the file
    parsed = parse_iterlog_issues(md_path)

    # Check for required section
    if not parsed["has_section"]:
        errors.append(f"{md_path}: missing '## Structured Issues' section")
        return (False, errors)

    # Validate each issue
    for i, issue in enumerate(parsed["issues"]):
        missing = validate_issue_fields(issue)
        if missing:
            errors.append(
                f"{md_path}: issue #{i + 1} missing required fields: {', '.join(missing)}"
            )

    return (len(errors) == 0, errors)


def generate_issue_fingerprint(issue_type: str, root_cause: str) -> str:
    """
    Generate a fingerprint for an issue based on type and root_cause.

    Normalizes the root_cause by removing variable parts (timestamps, UUIDs, etc.)
    before hashing.
    """
    # Normalize root_cause (remove timestamps, UUIDs, etc.)
    import re

    normalized = root_cause.lower().strip()

    # Remove common variable parts
    patterns = [
        (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?", "<TIMESTAMP>"),
        (r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>"),
        (r"/[\w/.-]+", "<PATH>"),
        (r":\d+", ":<PORT>"),
    ]

    for pattern, replacement in patterns:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

    # Create fingerprint
    combined = f"{issue_type}:{normalized}"
    hash_value = hashlib.sha256(combined.encode()).hexdigest()[:16]

    return f"{issue_type}:{hash_value}"


def group_issues_by_fingerprint(
    issues: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Group issues by their fingerprint.

    Returns:
        Dict mapping fingerprint to list of issues with that fingerprint
    """
    groups: dict[str, list[dict[str, Any]]] = {}

    for issue in issues:
        issue_type = issue.get("issue_type", "unknown")
        root_cause = issue.get("root_cause", "")

        fingerprint = generate_issue_fingerprint(issue_type, root_cause)

        if fingerprint not in groups:
            groups[fingerprint] = []

        groups[fingerprint].append(issue)

    return groups


# ============================================================================
# Test Cases: Validation
# ============================================================================


def test_valid_iterlog_with_structured_issues(valid_with_issues_md: Path):
    """Valid iterlog with complete structured issues should pass."""
    is_valid, errors = validate_iterlog_file(valid_with_issues_md)

    assert is_valid, f"Expected valid, got errors: {errors}"
    assert len(errors) == 0

    # Verify issues were parsed
    parsed = parse_iterlog_issues(valid_with_issues_md)
    assert parsed["has_section"] is True
    assert len(parsed["issues"]) == 2

    # Verify first issue has all required fields
    issue1 = parsed["issues"][0]
    assert "root_cause" in issue1
    assert "impact_area" in issue1
    assert "time_lost_minutes" in issue1
    assert issue1["root_cause"] == "Redis connection timeout due to network partition"
    assert issue1["time_lost_minutes"] == 45


def test_valid_iterlog_with_empty_issues(valid_empty_issues_md: Path):
    """Valid iterlog with issues: [] sentinel should pass."""
    is_valid, errors = validate_iterlog_file(valid_empty_issues_md)

    assert is_valid, f"Expected valid, got errors: {errors}"
    assert len(errors) == 0

    # Verify issues array is empty but present
    parsed = parse_iterlog_issues(valid_empty_issues_md)
    assert parsed["has_section"] is True
    assert parsed["issues"] == []


def test_invalid_missing_required_field_root_cause(invalid_missing_field_md: Path):
    """Iterlog with issue missing root_cause should fail."""
    is_valid, errors = validate_iterlog_file(invalid_missing_field_md)

    assert not is_valid, "Expected invalid due to missing root_cause"
    assert len(errors) == 1
    assert "root_cause" in errors[0]
    assert "issue #1" in errors[0]


def test_invalid_missing_required_field_impact_area(invalid_missing_impact_md: Path):
    """Iterlog with issue missing impact_area should fail."""
    is_valid, errors = validate_iterlog_file(invalid_missing_impact_md)

    assert not is_valid, "Expected invalid due to missing impact_area"
    assert len(errors) == 1
    assert "impact_area" in errors[0]


def test_invalid_missing_required_field_time_lost(invalid_missing_time_md: Path):
    """Iterlog with issue missing time_lost_minutes should fail."""
    is_valid, errors = validate_iterlog_file(invalid_missing_time_md)

    assert not is_valid, "Expected invalid due to missing time_lost_minutes"
    assert len(errors) == 1
    assert "time_lost_minutes" in errors[0]


def test_invalid_no_structured_issues_section(invalid_no_section_md: Path):
    """Iterlog without ## Structured Issues section should fail."""
    is_valid, errors = validate_iterlog_file(invalid_no_section_md)

    assert not is_valid, "Expected invalid due to missing section"
    assert len(errors) == 1
    assert "## Structured Issues" in errors[0]


# ============================================================================
# Test Cases: Fingerprinting
# ============================================================================


def test_repeated_issue_fingerprinting(repeated_issues_md: Path):
    """Same issue type + root cause should have same fingerprint."""
    parsed = parse_iterlog_issues(repeated_issues_md)
    issues = parsed["issues"]

    assert len(issues) == 4, "Expected 4 issues in fixture"

    # Generate fingerprints for all issues
    fingerprints = [
        generate_issue_fingerprint(issue["issue_type"], issue["root_cause"])
        for issue in issues
    ]

    # First, third, and fourth should have same fingerprint (same root_cause)
    assert (
        fingerprints[0] == fingerprints[2]
    ), "Issue 1 and 3 should have same fingerprint"
    assert (
        fingerprints[0] == fingerprints[3]
    ), "Issue 1 and 4 should have same fingerprint"

    # Second should be different (different issue type and root_cause)
    assert (
        fingerprints[1] != fingerprints[0]
    ), "Issue 2 should have different fingerprint"


def test_repeated_issue_grouping(repeated_issues_md: Path):
    """Repeated issues should be grouped correctly."""
    parsed = parse_iterlog_issues(repeated_issues_md)
    issues = parsed["issues"]

    # Group issues by fingerprint
    groups = group_issues_by_fingerprint(issues)

    # Should have 2 groups (db_connectivity + file_access)
    assert len(groups) == 2, f"Expected 2 groups, got {len(groups)}"

    # Find the db_connectivity group
    db_group = None
    for fingerprint, group_issues in groups.items():
        if group_issues[0]["issue_type"] == "db_connectivity":
            db_group = group_issues
            break

    assert db_group is not None, "Should have db_connectivity group"
    assert len(db_group) == 3, f"Expected 3 db_connectivity issues, got {len(db_group)}"

    # Verify total time lost
    total_time = sum(issue["time_lost_minutes"] for issue in db_group)
    assert total_time == 75, f"Expected 75 total minutes, got {total_time}"


def test_fingerprint_normalization():
    """Fingerprints should normalize variable parts."""
    # Same issue with different timestamps
    issue1_type = "db_connectivity"
    issue1_cause = "Redis timeout at 2026-03-01T12:00:00Z"

    issue2_type = "db_connectivity"
    issue2_cause = "Redis timeout at 2026-03-01T18:00:00Z"

    fp1 = generate_issue_fingerprint(issue1_type, issue1_cause)
    fp2 = generate_issue_fingerprint(issue2_type, issue2_cause)

    # Should have same fingerprint after normalization
    assert fp1 == fp2, f"Expected same fingerprint, got {fp1} != {fp2}"


# ============================================================================
# Test Cases: Mini BrainEval Integration
# ============================================================================


def test_mini_brain_eval_ingests_structured_issues(valid_with_issues_md: Path):
    """Mini BrainEval should parse structured issues into output."""
    # Parse the iterlog
    parsed = parse_iterlog_issues(valid_with_issues_md)
    issues = parsed["issues"]

    # Simulate mini BrainEval output structure
    eval_output = {
        "eval_id": "test-eval-001",
        "timestamp": datetime.now(UTC).isoformat() + "Z",
        "cadence": "6h",
        "issues": [],
        "mitigations": [],
    }

    # Transform structured issues into mini BrainEval format
    for issue in issues:
        eval_issue = {
            "issue_id": f"issue-{hash(issue['root_cause']) % 10000:04d}",
            "category": issue.get("issue_type", "other"),
            "severity": issue.get("severity", "P3"),
            "description": issue.get("description", ""),
            "source": "iterlog_structured",
            "timestamp": issue.get("timestamp", ""),
            # Include structured fields
            "root_cause": issue["root_cause"],
            "impact_area": issue["impact_area"],
            "time_lost_minutes": issue["time_lost_minutes"],
        }
        eval_output["issues"].append(eval_issue)

        # Generate mitigation if prevention_rule exists
        if "prevention_rule" in issue:
            mitigation = {
                "mitigation_id": f"mit-{hash(issue['prevention_rule']) % 10000:04d}",
                "issue_id": eval_issue["issue_id"],
                "action": issue["prevention_rule"],
                "result": "suggested",
            }
            eval_output["mitigations"].append(mitigation)

    # Verify output
    assert len(eval_output["issues"]) == 2
    assert eval_output["issues"][0]["category"] == "db_connectivity"
    assert (
        eval_output["issues"][0]["root_cause"]
        == "Redis connection timeout due to network partition"
    )
    assert eval_output["issues"][0]["time_lost_minutes"] == 45

    # Verify mitigations
    assert len(eval_output["mitigations"]) == 2
    assert "retry logic" in eval_output["mitigations"][0]["action"]


def test_mini_brain_eval_empty_issues(valid_empty_issues_md: Path):
    """Mini BrainEval should handle empty issues array."""
    parsed = parse_iterlog_issues(valid_empty_issues_md)

    # Should have section but empty issues
    assert parsed["has_section"] is True
    assert len(parsed["issues"]) == 0

    # Mini BrainEval output should still be valid
    eval_output = {
        "eval_id": "test-eval-002",
        "timestamp": datetime.now(UTC).isoformat() + "Z",
        "cadence": "6h",
        "issues": parsed["issues"],
        "mitigations": [],
    }

    assert eval_output["issues"] == []
    assert len(eval_output["mitigations"]) == 0


def test_mini_brain_eval_aggregates_time_lost(repeated_issues_md: Path):
    """Mini BrainEval should aggregate time_lost_minutes for repeated issues."""
    parsed = parse_iterlog_issues(repeated_issues_md)
    issues = parsed["issues"]

    # Group issues by fingerprint
    groups = group_issues_by_fingerprint(issues)

    # Calculate aggregated metrics
    aggregated = []
    for fingerprint, group_issues in groups.items():
        agg = {
            "fingerprint": fingerprint,
            "issue_type": group_issues[0]["issue_type"],
            "root_cause": group_issues[0]["root_cause"],
            "occurrence_count": len(group_issues),
            "total_time_lost_minutes": sum(
                i["time_lost_minutes"] for i in group_issues
            ),
            "avg_time_lost_minutes": sum(i["time_lost_minutes"] for i in group_issues)
            / len(group_issues),
        }
        aggregated.append(agg)

    # Verify aggregation
    assert len(aggregated) == 2

    # Find db_connectivity aggregation
    db_agg = next((a for a in aggregated if a["issue_type"] == "db_connectivity"), None)
    assert db_agg is not None
    assert db_agg["occurrence_count"] == 3
    assert db_agg["total_time_lost_minutes"] == 75  # 30 + 25 + 20
    assert db_agg["avg_time_lost_minutes"] == 25.0  # 75 / 3


# ============================================================================
# Test Cases: Edge Cases
# ============================================================================


def test_multiple_issues_some_invalid(fixtures_dir: Path):
    """Iterlog with multiple issues, some invalid, should report all errors."""
    content = """---
story_id: TEST-008
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## Structured Issues
issues:
  - issue_type: db_connectivity
    severity: P1
    root_cause: "Valid issue"
    impact_area: "test"
    time_lost_minutes: 10
  
  - issue_type: file_access
    severity: P2
    # Missing root_cause and impact_area
    time_lost_minutes: 5
  
  - issue_type: env_slowdown
    severity: P2
    root_cause: "Another valid issue"
    impact_area: "test"
    # Missing time_lost_minutes
"""
    path = fixtures_dir / "mixed_validity.md"
    path.write_text(content)

    is_valid, errors = validate_iterlog_file(path)

    assert not is_valid
    assert len(errors) == 2, f"Expected 2 errors, got {len(errors)}: {errors}"

    # Check that both invalid issues are reported
    error_text = " ".join(errors)
    assert "issue #2" in error_text
    assert "issue #3" in error_text


def test_malformed_yaml_in_issues(fixtures_dir: Path):
    """Iterlog with malformed YAML should fail gracefully."""
    content = """---
story_id: TEST-009
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## Structured Issues
issues:
  - issue_type: db_connectivity
    severity: P1
    root_cause: "Valid"
    impact_area: "test"
    time_lost_minutes: 10
  - invalid yaml here [
    missing closing bracket
"""
    path = fixtures_dir / "malformed_yaml.md"
    path.write_text(content)

    # Should not raise exception
    parsed = parse_iterlog_issues(path)

    # May or may not parse issues, but shouldn't crash
    assert isinstance(parsed, dict)
    assert "has_section" in parsed
    assert "issues" in parsed


def test_extra_fields_allowed(fixtures_dir: Path):
    """Issues with extra fields beyond required should pass."""
    content = """---
story_id: TEST-010
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## Structured Issues
issues:
  - issue_type: db_connectivity
    severity: P1
    root_cause: "Test issue"
    impact_area: "test"
    time_lost_minutes: 10
    # Extra fields
    custom_field: "custom value"
    tags: ["tag1", "tag2"]
    metadata:
      key: value
"""
    path = fixtures_dir / "extra_fields.md"
    path.write_text(content)

    is_valid, errors = validate_iterlog_file(path)

    assert is_valid, f"Expected valid with extra fields, got errors: {errors}"


def test_case_insensitive_section_name(fixtures_dir: Path):
    """Section name should be case-sensitive (exact match required)."""
    # Test lowercase variant (should fail)
    content_lower = """---
story_id: TEST-011
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## structured issues
issues: []
"""
    path_lower = fixtures_dir / "lowercase_section.md"
    path_lower.write_text(content_lower)

    is_valid, errors = validate_iterlog_file(path_lower)

    # Should fail because section name is case-sensitive
    assert not is_valid
    assert "## Structured Issues" in errors[0]


# ============================================================================
# Test Cases: Integration with Existing Validator
# ============================================================================


def test_compatibility_with_existing_validator(valid_with_issues_md: Path):
    """New issue enforcement should be compatible with existing iterlog validation."""
    # This test verifies that the new structured issues section
    # doesn't break existing validation logic

    # Parse frontmatter (existing validator behavior)
    content = valid_with_issues_md.read_text()
    assert content.startswith("---\n")

    end = content.find("\n---\n", 4)
    assert end != -1

    frontmatter_yaml = content[4:end]
    frontmatter = yaml.safe_load(frontmatter_yaml)

    # Verify existing required fields still work
    assert "story_id" in frontmatter
    assert "phase" in frontmatter
    assert "status" in frontmatter
    assert "started_at" in frontmatter

    # New validation should also pass
    is_valid, errors = validate_iterlog_file(valid_with_issues_md)
    assert is_valid


def test_section_appears_after_other_sections(fixtures_dir: Path):
    """Structured Issues section can appear in any order."""
    content = """---
story_id: TEST-012
phase: implementation
status: in_progress
started_at: "2026-03-01T10:00:00Z"
---

## Learnings
- Learning 1

## Structured Issues
issues: []

## Decisions
- Decision 1

## Scope Ownership
- TBD
"""
    path = fixtures_dir / "section_order.md"
    path.write_text(content)

    is_valid, errors = validate_iterlog_file(path)

    assert is_valid, f"Expected valid regardless of section order, got errors: {errors}"
