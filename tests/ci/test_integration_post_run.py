#!/usr/bin/env python3
"""Unit tests for post_run_reporter.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module under test
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "scripts" / "ci_integration")
)
from post_run_reporter import (  # noqa: I001
    TestStatus,
    TestCase,
    TestSuite,
    CoverageData,
    MetricsData,
    CIReport,
    parse_junit_xml,
    parse_coverage_report,
    collect_results,
    calculate_summary,
    generate_next_steps,
    format_markdown_report,
    export_influx_line_protocol,
    main,
)


class TestTestStatusEnum:
    """Tests for TestStatus enum."""

    def test_all_statuses_exist(self):
        """Test that all expected statuses exist."""
        assert TestStatus.PASSED
        assert TestStatus.FAILED
        assert TestStatus.SKIPPED
        assert TestStatus.ERROR


class TestParseJunitXml:
    """Tests for parse_junit_xml function."""

    def test_returns_none_for_missing_file(self, tmp_path):
        """Test that missing file returns None."""
        result = parse_junit_xml(tmp_path / "nonexistent.xml")
        assert result is None

    def test_parses_valid_junit_xml(self, tmp_path):
        """Test parsing valid JUnit XML."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <testsuite name="test_suite" tests="2" failures="1" errors="0" skipped="0" time="1.5">
            <testcase name="test_pass" classname="TestClass" time="0.5"/>
            <testcase name="test_fail" classname="TestClass" time="1.0">
                <failure message="Test failed" type="AssertionError"/>
            </testcase>
        </testsuite>
        """
        xml_file = tmp_path / "junit.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)
        assert result is not None
        assert result.name == "test_suite"
        assert result.tests == 2
        assert result.failures == 1
        assert result.errors == 0
        assert len(result.test_cases) == 2

    def test_handles_testsuites_root(self, tmp_path):
        """Test parsing testsuites (multiple suites)."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <testsuites>
            <testsuite name="suite1" tests="1" failures="0" errors="0" skipped="0" time="0.5">
                <testcase name="test1" classname="TestClass" time="0.5"/>
            </testsuite>
            <testsuite name="suite2" tests="1" failures="0" errors="0" skipped="0" time="0.3">
                <testcase name="test2" classname="TestClass2" time="0.3"/>
            </testsuite>
        </testsuites>
        """
        xml_file = tmp_path / "junit.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)
        assert result is not None
        assert result.name == "combined"
        assert result.tests == 2

    def test_handles_skipped_tests(self, tmp_path):
        """Test parsing skipped tests."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <testsuite name="test_suite" tests="1" failures="0" errors="0" skipped="1" time="0.1">
            <testcase name="test_skip" classname="TestClass" time="0.0">
                <skipped/>
            </testcase>
        </testsuite>
        """
        xml_file = tmp_path / "junit.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)
        assert result is not None
        assert result.skipped == 1
        assert len(result.test_cases) == 1
        assert result.test_cases[0].status == TestStatus.SKIPPED


class TestParseCoverageReport:
    """Tests for parse_coverage_report function."""

    def test_returns_none_for_missing_file(self, tmp_path):
        """Test that missing file returns None."""
        result = parse_coverage_report(tmp_path / "nonexistent.json")
        assert result is None

    def test_parses_valid_coverage_json(self, tmp_path):
        """Test parsing valid coverage JSON."""
        coverage_content = {
            "totals": {
                "percent_covered": 85.5,
                "covered_lines": 500,
                "executable_lines": 585,
            },
            "files": {
                "src/module.py": {
                    "summary": {
                        "percent_covered": 90.0,
                        "covered_lines": 100,
                        "executable_lines": 111,
                    }
                }
            },
        }
        coverage_file = tmp_path / "coverage.json"
        coverage_file.write_text(json.dumps(coverage_content))

        result = parse_coverage_report(coverage_file)
        assert result is not None
        assert result.total_percent == 85.5
        assert result.covered_lines == 500
        assert result.total_lines == 585


class TestCollectResults:
    """Tests for collect_results function."""

    def test_returns_empty_when_no_files(self, tmp_path):
        """Test that empty result when no files found."""
        suites, coverage = collect_results(tmp_path)
        assert suites == []
        assert coverage is None


class TestCalculateSummary:
    """Tests for calculate_summary function."""

    def test_empty_suites(self):
        """Test summary with empty suites."""
        summary = calculate_summary([])
        assert summary["total"] == 0
        assert summary["passed"] == 0
        assert summary["failed"] == 0

    def test_calculates_totals(self):
        """Test summary calculation with test suites."""
        suite = TestSuite(
            name="test",
            tests=2,
            failures=1,
            errors=0,
            skipped=0,
            duration_ms=1000,
            test_cases=[
                TestCase("pass", "Test", TestStatus.PASSED, 500),
                TestCase("fail", "Test", TestStatus.FAILED, 500),
            ],
        )
        summary = calculate_summary([suite])
        assert summary["total"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1

    def test_calculates_pass_rate(self):
        """Test pass rate calculation."""
        suite = TestSuite(
            name="test",
            tests=4,
            failures=1,
            errors=0,
            skipped=0,
            duration_ms=1000,
            test_cases=[
                TestCase("pass1", "Test", TestStatus.PASSED, 250),
                TestCase("pass2", "Test", TestStatus.PASSED, 250),
                TestCase("pass3", "Test", TestStatus.PASSED, 250),
                TestCase("fail", "Test", TestStatus.FAILED, 250),
            ],
        )
        summary = calculate_summary([suite])
        assert summary["pass_rate"] == 75.0


class TestGenerateNextSteps:
    """Tests for generate_next_steps function."""

    def test_no_failures(self):
        """Test next steps when all passes."""
        summary = {"failed": 0, "errors": 0, "total": 10, "skipped": 0}
        steps = generate_next_steps(summary, None)
        assert "All checks passed" in steps[0]

    def test_with_failures(self):
        """Test next steps when failures exist."""
        summary = {"failed": 5, "errors": 0, "total": 10, "skipped": 0}
        steps = generate_next_steps(summary, None)
        assert any("5 failing" in s for s in steps)

    def test_with_low_coverage(self):
        """Test next steps for low coverage."""
        summary = {"failed": 0, "errors": 0, "total": 10, "skipped": 0}
        coverage = CoverageData(total_percent=50.0, covered_lines=50, total_lines=100)
        steps = generate_next_steps(summary, coverage)
        assert any("coverage" in s.lower() for s in steps)


class TestFormatMarkdownReport:
    """Tests for format_markdown_report function."""

    def test_basic_format(self):
        """Test basic markdown format."""
        report = CIReport(
            timestamp="2024-01-01T00:00:00Z",
            hostname="test-host",
            python_version="3.10.0",
            test_suites=[],
            summary={
                "total": 10,
                "passed": 10,
                "failed": 0,
                "skipped": 0,
                "errors": 0,
                "pass_rate": 100.0,
                "duration_ms": 1000,
            },
        )
        markdown = format_markdown_report(report)
        assert "CI Report" in markdown
        assert "10" in markdown
        assert "test-host" in markdown


class TestExportInfluxLineProtocol:
    """Tests for export_influx_line_protocol function."""

    def test_basic_export(self):
        """Test basic line protocol export."""
        metrics = MetricsData(
            timestamp="test-host",
            test_count=10,
            passed_count=9,
            failed_count=1,
            skipped_count=0,
            error_count=0,
            coverage_percent=85.0,
            duration_ms=1000,
            exit_code=0,
        )
        lines = export_influx_line_protocol(metrics)
        assert len(lines) == 1
        assert "ci_run" in lines[0]
        assert "test_count=10i" in lines[0]


class TestMain:
    """Tests for main function."""

    def test_parses_help_flag(self, capsys):
        """Test that --help is parsed correctly."""
        with patch("sys.argv", ["post_run_reporter.py", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0

    def test_creates_output_with_empty_dir(self, tmp_path, capsys):
        """Test running with empty directory."""
        input_dir = tmp_path / "ci"
        input_dir.mkdir()
        with patch("sys.argv", ["post_run_reporter.py", "--input-dir", str(input_dir)]):
            exit_code = main()
        # Should complete even with no results
        assert exit_code in (0, 1)
