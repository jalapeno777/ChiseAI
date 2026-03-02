#!/usr/bin/env python3
"""
Tests for Mini BrainEval - Structured Issue Parsing

Tests cover:
- Parsing structured issues from YAML blocks
- Fallback to regex when no structured section
- Repeated issue fingerprinting
- Empty issues: [] sentinel handling
"""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Add scripts to path for import
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from evaluation.mini_brain_eval import (
    IssueDetector,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    td = tempfile.mkdtemp()
    yield td
    shutil.rmtree(td)


@pytest.fixture
def detector_with_structured_issues(temp_dir):
    """Create detector with a file containing structured issues."""
    content = """---
date: 2026-03-01
story: ST-TEST-001
---

# Iteration Log

## Summary
Test iteration log for structured issue parsing.

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "missing dependency"
    fix_applied: "added package to requirements"
    time_lost_minutes: 30
    recurrence_hint: "check deps before commit"
    impact_area: "efficiency"
    resolved: true
  - issue_type: "db_connectivity"
    root_cause: "redis connection timeout"
    fix_applied: "increased timeout settings"
    time_lost_minutes: 45
    recurrence_hint: "monitor redis latency"
    impact_area: "reliability"
    resolved: true
  - issue_type: "ci_failure"
    root_cause: "missing dependency"
    fix_applied: "added another package"
    time_lost_minutes: 15
    recurrence_hint: "check deps before commit"
    impact_area: "efficiency"
    resolved: true

## Notes
This demonstrates repeated issue pattern.
"""
    test_file = Path(temp_dir) / "iterlog-001.md"
    test_file.write_text(content)

    detector = IssueDetector(temp_dir)
    return detector


@pytest.fixture
def detector_with_legacy_issues(temp_dir):
    """Create detector with a legacy file (no structured section)."""
    content = """---
date: 2026-03-01
story: ST-LEGACY-001
---

# Iteration Log

## Summary
Legacy format with no structured issues.

## Notes
- CI failed due to test failure
- Database connection refused error occurred
- Config error: missing settings
"""
    test_file = Path(temp_dir) / "legacy-iterlog.md"
    test_file.write_text(content)

    detector = IssueDetector(temp_dir)
    return detector


@pytest.fixture
def detector_with_empty_issues(temp_dir):
    """Create detector with empty issues sentinel."""
    content = """---
date: 2026-03-01
story: ST-EMPTY-001
---

# Iteration Log

## Summary
No issues encountered.

## Structured Issues

issues: []

## Notes
Clean iteration.
"""
    test_file = Path(temp_dir) / "clean-iterlog.md"
    test_file.write_text(content)

    detector = IssueDetector(temp_dir)
    return detector


@pytest.fixture
def detector_mixed_files(temp_dir):
    """Create detector with both structured and legacy files."""
    # Structured file
    structured_content = """---
date: 2026-03-01
---

## Structured Issues

issues:
  - issue_type: "config_error"
    root_cause: "invalid yaml syntax"
    time_lost_minutes: 20
    resolved: true
"""
    (Path(temp_dir) / "structured.md").write_text(structured_content)

    # Legacy file
    legacy_content = """---
date: 2026-03-01
---

## Notes
Config error: invalid settings detected.
"""
    (Path(temp_dir) / "legacy.md").write_text(legacy_content)

    detector = IssueDetector(temp_dir)
    return detector


class TestStructuredIssueParsing:
    """Tests for parsing structured issues from YAML blocks."""

    def test_parse_structured_issues_basic(self, detector_with_structured_issues):
        """Test basic parsing of structured issues from YAML block."""
        issues = detector_with_structured_issues.scan_files()

        assert len(issues) == 3, f"Expected 3 issues, got {len(issues)}"

        # Check that all issues are marked as structured
        structured_count = sum(1 for i in issues if i.is_structured)
        assert (
            structured_count == 3
        ), f"Expected 3 structured issues, got {structured_count}"

    def test_structured_issue_fields_populated(self, detector_with_structured_issues):
        """Test that structured issue fields are correctly populated."""
        issues = detector_with_structured_issues.scan_files()

        ci_issues = [i for i in issues if i.issue_type == "ci_failure"]
        assert len(ci_issues) >= 1, "Expected at least one ci_failure issue"

        issue = ci_issues[0]
        assert (
            issue.root_cause == "missing dependency"
        ), f"Expected root_cause 'missing dependency', got '{issue.root_cause}'"
        assert issue.fix_applied is not None, "fix_applied should be populated"
        assert (
            issue.time_lost_minutes is not None
        ), "time_lost_minutes should be populated"
        assert issue.recurrence_hint is not None, "recurrence_hint should be populated"
        assert issue.impact_area is not None, "impact_area should be populated"
        assert issue.resolved is True, "resolved should be True"
        assert issue.fingerprint is not None, "fingerprint should be generated"
        assert issue.is_structured is True, "is_structured should be True"

    def test_structured_issues_have_fingerprints(self, detector_with_structured_issues):
        """Test that structured issues have fingerprints for deduplication."""
        issues = detector_with_structured_issues.scan_files()

        for issue in issues:
            assert (
                issue.fingerprint is not None
            ), f"Issue {issue.issue_type} should have fingerprint"
            assert (
                len(issue.fingerprint) == 12
            ), f"Fingerprint should be 12 chars, got {len(issue.fingerprint)}"


class TestFallbackToRegex:
    """Tests for regex fallback when no structured section."""

    def test_legacy_file_uses_regex_detection(self, detector_with_legacy_issues):
        """Test that legacy files fall back to regex pattern detection."""
        issues = detector_with_legacy_issues.scan_files()

        # Should detect issues via regex
        assert len(issues) > 0, "Expected regex to detect issues"

        # All issues should be non-structured
        for issue in issues:
            assert (
                issue.is_structured is False
            ), "Legacy issues should not be marked as structured"

    def test_mixed_files_priority_logic(self, detector_mixed_files):
        """Test that structured issues take priority over regex."""
        issues = detector_mixed_files.scan_files()

        # Should have both structured and regex-detected issues
        structured = [i for i in issues if i.is_structured]
        non_structured = [i for i in issues if not i.is_structured]

        assert (
            len(structured) == 1
        ), f"Expected 1 structured issue, got {len(structured)}"
        assert len(non_structured) >= 1, "Expected at least one regex-detected issue"

    def test_no_double_detection_same_issue(self, detector_mixed_files):
        """Test that same issue isn't detected by both methods."""
        issues = detector_mixed_files.scan_files()

        # Each issue should have unique fingerprint
        fingerprints = [i.fingerprint for i in issues]
        unique_fingerprints = set(fingerprints)

        assert len(fingerprints) == len(
            unique_fingerprints
        ), "Should not have duplicate fingerprints"


class TestRepeatedIssueFingerprinting:
    """Tests for repeated issue detection via fingerprinting."""

    def test_recurring_issues_detected(self, detector_with_structured_issues):
        """Test that recurring issues are identified."""
        detector_with_structured_issues.scan_files()
        recurring = detector_with_structured_issues.get_recurring_issues()

        assert (
            len(recurring) == 1
        ), f"Expected 1 recurring pattern (ci_failure+missing dependency), got {len(recurring)}"

        rec = recurring[0]
        assert (
            rec.issue_type == "ci_failure"
        ), f"Expected ci_failure, got {rec.issue_type}"
        assert (
            rec.root_cause == "missing dependency"
        ), f"Expected 'missing dependency', got '{rec.root_cause}'"
        assert (
            rec.occurrence_count == 2
        ), f"Expected 2 occurrences, got {rec.occurrence_count}"

    def test_recurring_issue_time_aggregation(self, detector_with_structured_issues):
        """Test that time lost is aggregated across recurring issues."""
        detector_with_structured_issues.scan_files()
        recurring = detector_with_structured_issues.get_recurring_issues()

        # The ci_failure+missing dependency pattern has 30 + 15 = 45 minutes
        rec = recurring[0]
        assert (
            rec.total_time_lost_minutes == 45
        ), f"Expected 45 minutes total, got {rec.total_time_lost_minutes}"

    def test_total_time_lost(self, detector_with_structured_issues):
        """Test total time lost calculation."""
        detector_with_structured_issues.scan_files()
        total = detector_with_structured_issues.get_time_lost_total()

        # 30 + 45 + 15 = 90 minutes total
        assert total == 90, f"Expected 90 minutes total, got {total}"


class TestEmptyIssuesSentinel:
    """Tests for empty issues: [] sentinel handling."""

    def test_empty_issues_list(self, detector_with_empty_issues):
        """Test that empty issues list is handled correctly."""
        issues = detector_with_empty_issues.scan_files()

        # Should return empty list, not error
        assert len(issues) == 0, "Expected no issues from empty sentinel"

    def test_empty_issues_no_recurring(self, detector_with_empty_issues):
        """Test that empty issues produces no recurring patterns."""
        detector_with_empty_issues.scan_files()
        recurring = detector_with_empty_issues.get_recurring_issues()

        assert len(recurring) == 0, "Expected no recurring issues"

    def test_empty_issues_stats(self, detector_with_empty_issues):
        """Test that file stats are correct for empty issues."""
        detector_with_empty_issues.scan_files()
        stats = detector_with_empty_issues.get_file_stats()

        assert stats["total_issues"] == 0
        assert stats["structured_issues_count"] == 0


class TestMiniEvalResult:
    """Tests for MiniEvalResult output structure."""

    def test_result_includes_structured_count(self, detector_with_structured_issues):
        """Test that result includes structured_issues_found count."""
        detector_with_structured_issues.scan_files()

        # Check file stats
        stats = detector_with_structured_issues.get_file_stats()
        assert (
            "structured_issues_count" in stats
        ), "file_stats should include structured_issues_count"
        assert (
            stats["structured_issues_count"] == 3
        ), f"Expected 3 structured issues, got {stats['structured_issues_count']}"

    def test_result_includes_recurring_issues(self, detector_with_structured_issues):
        """Test that result includes recurring_issues list."""
        detector_with_structured_issues.scan_files()
        recurring = detector_with_structured_issues.get_recurring_issues()

        assert len(recurring) > 0, "Expected recurring issues"

        rec = recurring[0]
        assert hasattr(rec, "fingerprint"), "RecurringIssue should have fingerprint"
        assert hasattr(rec, "issue_type"), "RecurringIssue should have issue_type"
        assert hasattr(
            rec, "occurrence_count"
        ), "RecurringIssue should have occurrence_count"

    def test_result_includes_time_lost(self, detector_with_structured_issues):
        """Test that result includes time_lost_total_minutes."""
        detector_with_structured_issues.scan_files()
        total = detector_with_structured_issues.get_time_lost_total()

        assert total == 90, f"Expected 90 minutes, got {total}"


class TestFingerprintGeneration:
    """Tests for issue fingerprint generation."""

    def test_same_issue_same_fingerprint(self, temp_dir):
        """Test that identical issues get same fingerprint."""
        content = """---
date: 2026-03-01
---

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "missing dependency"
    resolved: true
"""
        (Path(temp_dir) / "file1.md").write_text(content)
        (Path(temp_dir) / "file2.md").write_text(content)

        detector = IssueDetector(temp_dir)
        issues = detector.scan_files()

        fingerprints = [i.fingerprint for i in issues]
        assert (
            fingerprints[0] == fingerprints[1]
        ), "Identical issues should have same fingerprint"

    def test_different_issue_different_fingerprint(self, temp_dir):
        """Test that different issues get different fingerprints."""
        content1 = """---
date: 2026-03-01
---

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "missing dependency"
    resolved: true
"""
        content2 = """---
date: 2026-03-01
---

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "test timeout"
    resolved: true
"""
        (Path(temp_dir) / "file1.md").write_text(content1)
        (Path(temp_dir) / "file2.md").write_text(content2)

        detector = IssueDetector(temp_dir)
        issues = detector.scan_files()

        fingerprints = [i.fingerprint for i in issues]
        assert (
            fingerprints[0] != fingerprints[1]
        ), "Different issues should have different fingerprints"


class TestYAMLParsingEdgeCases:
    """Tests for YAML parsing edge cases."""

    def test_quoted_string_values(self, temp_dir):
        """Test parsing quoted string values."""
        content = """---
date: 2026-03-01
---

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: 'single quoted value'
    resolved: true
"""
        (Path(temp_dir) / "test.md").write_text(content)

        detector = IssueDetector(temp_dir)
        issues = detector.scan_files()

        assert len(issues) == 1
        assert issues[0].root_cause == "single quoted value"

    def test_boolean_values(self, temp_dir):
        """Test parsing boolean values."""
        content = """---
date: 2026-03-01
---

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "test issue"
    resolved: false
"""
        (Path(temp_dir) / "test.md").write_text(content)

        detector = IssueDetector(temp_dir)
        issues = detector.scan_files()

        assert len(issues) == 1
        assert issues[0].resolved is False

    def test_integer_values(self, temp_dir):
        """Test parsing integer values."""
        content = """---
date: 2026-03-01
---

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "test issue"
    time_lost_minutes: 120
    resolved: true
"""
        (Path(temp_dir) / "test.md").write_text(content)

        detector = IssueDetector(temp_dir)
        issues = detector.scan_files()

        assert len(issues) == 1
        assert issues[0].time_lost_minutes == 120

    def test_optional_fields_missing(self, temp_dir):
        """Test handling of missing optional fields."""
        content = """---
date: 2026-03-01
---

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "minimal issue"
"""
        (Path(temp_dir) / "test.md").write_text(content)

        detector = IssueDetector(temp_dir)
        issues = detector.scan_files()

        assert len(issues) == 1
        assert issues[0].fix_applied is None
        assert issues[0].time_lost_minutes is None
        assert issues[0].resolved is True  # Default value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
