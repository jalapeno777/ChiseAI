#!/usr/bin/env python3
"""
Tests for Mini BrainEval Structured Issue Parsing

These tests verify the deterministic structured issue parsing works correctly:
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

# Import the modules under test
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "evaluation"))

from mini_brain_eval import Issue, IssueDetector, run_evaluation
from repeated_issue_analyzer import RepeatedIssueAnalyzer


# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "iterlog"


class TestStructuredIssuesParsed:
    """Verify structured section is ingested correctly."""

    def test_structured_issues_parsed(self):
        """Test that structured issues are parsed from valid fixture."""
        detector = IssueDetector(str(FIXTURES_DIR))
        issues = detector.scan_files()

        # Find issues from the valid_with_issues.md fixture
        valid_issues = [i for i in issues if "valid_with_issues" in i.source_file]

        assert len(valid_issues) == 2, (
            f"Expected 2 structured issues, got {len(valid_issues)}"
        )

        # Verify structured fields are populated
        for issue in valid_issues:
            assert issue.is_structured is True
            assert issue.root_cause is not None
            assert issue.fix_applied is not None
            assert issue.time_lost_minutes is not None
            assert issue.recurrence_hint is not None
            assert issue.impact_area is not None
            assert issue.resolved is not None

    def test_empty_issues_list(self):
        """Verify `issues: []` yields no structured issues."""
        detector = IssueDetector(str(FIXTURES_DIR))
        issues = detector.scan_files()

        # Find issues from valid_empty_issues.md fixture
        empty_issues = [i for i in issues if "valid_empty_issues" in i.source_file]

        # Should have no issues (empty list)
        assert len(empty_issues) == 0, (
            f"Expected 0 issues from empty list, got {len(empty_issues)}"
        )

    def test_regex_fallback(self):
        """Verify regex patterns work when no structured section."""
        detector = IssueDetector(str(FIXTURES_DIR))
        issues = detector.scan_files()

        # Find issues from without_structured_issues.md fixture
        regex_issues = [
            i for i in issues if "without_structured_issues" in i.source_file
        ]

        # Should have issues from regex patterns
        assert len(regex_issues) >= 1, f"Expected regex issues, got {len(regex_issues)}"

        # Verify these are NOT structured
        for issue in regex_issues:
            assert issue.is_structured is False

    def test_structured_preferred_over_regex(self):
        """Verify structured takes precedence when both exist."""
        detector = IssueDetector(str(FIXTURES_DIR))
        issues = detector.scan_files()

        # Find issues from with_both.md fixture
        both_issues = [i for i in issues if "with_both" in i.source_file]

        # Should have only structured issues (no regex fallback)
        assert len(both_issues) >= 1, f"Expected structured issues from with_both.md"

        # All should be structured
        for issue in both_issues:
            assert issue.is_structured is True

    def test_repeated_issue_grouping_structured(self):
        """Verify fingerprinting uses structured fields for clustering."""
        analyzer = RepeatedIssueAnalyzer()

        # Create mock issues with structured data
        structured_issue = {
            "issue_type": "ci_failure",
            "severity": "P2",
            "description": "Root cause: missing dep; Fix: added dependency",
            "source_file": "test.md",
            "root_cause": "missing dependency",
            "impact_area": "efficiency",
            "recurrence_hint": "check deps",
            "is_structured": True,
        }

        # Test normalization for structured issue
        normalized = analyzer.normalize_description("any description", structured_issue)

        # Should use structured fields, not description
        assert "ci_failure" in normalized
        assert "missing dependency" in normalized
        assert "efficiency" in normalized

        # Test cluster ID generation
        cluster_id = analyzer.generate_cluster_id(
            normalized, "ci_failure", structured_issue
        )

        # Cluster ID should be deterministic based on structured fields
        assert cluster_id is not None
        assert len(cluster_id) == 12  # MD5 hash truncated to 12 chars

    def test_is_structured_issue_method(self):
        """Test the is_structured_issue helper method."""
        analyzer = RepeatedIssueAnalyzer()

        structured_issue = {"is_structured": True}
        regex_issue = {"is_structured": False}
        missing_field_issue = {}

        assert analyzer.is_structured_issue(structured_issue) is True
        assert analyzer.is_structured_issue(regex_issue) is False
        assert analyzer.is_structured_issue(missing_field_issue) is False


class TestIssueDataclassExtensions:
    """Test Issue dataclass has new structured fields."""

    def test_issue_has_structured_fields(self):
        """Verify Issue dataclass has all required fields."""
        issue = Issue(
            issue_type="test",
            severity="P1",
            description="test issue",
            source_file="test.md",
            root_cause="test root cause",
            fix_applied="test fix",
            time_lost_minutes=30,
            recurrence_hint="test hint",
            impact_area="efficiency",
            resolved=True,
            is_structured=True,
        )

        assert issue.root_cause == "test root cause"
        assert issue.fix_applied == "test fix"
        assert issue.time_lost_minutes == 30
        assert issue.recurrence_hint == "test hint"
        assert issue.impact_area == "efficiency"
        assert issue.resolved is True
        assert issue.is_structured is True

    def test_issue_defaults(self):
        """Verify default values for structured fields."""
        issue = Issue(
            issue_type="test",
            severity="P1",
            description="test issue",
            source_file="test.md",
        )

        assert issue.root_cause is None
        assert issue.fix_applied is None
        assert issue.time_lost_minutes is None
        assert issue.recurrence_hint is None
        assert issue.impact_area is None
        assert issue.resolved is None
        assert issue.is_structured is False
