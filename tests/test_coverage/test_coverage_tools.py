"""Tests for Coverage Improvement Tools (ST-NS-029)."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the tests directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from coverage.improvement.analyzer import (
    CRITICAL_MODULES,
    CoverageAnalyzer,
    CoverageGap,
    CoverageReport,
    ModuleCoverage,
    Priority,
)
from coverage.improvement.reporter import (
    CoverageReporter,
    CoverageThresholds,
    ReportFormat,
)


class TestPriority:
    """Tests for Priority enum."""

    def test_priority_values(self):
        """Test that all expected priority levels exist."""
        assert Priority.CRITICAL.value == "critical"
        assert Priority.HIGH.value == "high"
        assert Priority.MEDIUM.value == "medium"
        assert Priority.LOW.value == "low"


class TestCoverageGap:
    """Tests for CoverageGap dataclass."""

    def test_coverage_gap_creation(self):
        """Test creating a coverage gap."""
        gap = CoverageGap(
            file_path="src/test.py",
            line_start=10,
            line_end=20,
            function_name="test_func",
            priority=Priority.HIGH,
            description="Missing test coverage",
        )
        assert gap.file_path == "src/test.py"
        assert gap.line_start == 10
        assert gap.line_end == 20
        assert gap.function_name == "test_func"
        assert gap.priority == Priority.HIGH
        assert gap.description == "Missing test coverage"

    def test_coverage_gap_to_dict(self):
        """Test converting gap to dictionary."""
        gap = CoverageGap(
            file_path="src/test.py",
            line_start=10,
            line_end=20,
            priority=Priority.CRITICAL,
        )
        data = gap.to_dict()
        assert data["file_path"] == "src/test.py"
        assert data["line_start"] == 10
        assert data["priority"] == "critical"


class TestModuleCoverage:
    """Tests for ModuleCoverage dataclass."""

    def test_module_coverage_creation(self):
        """Test creating module coverage."""
        module = ModuleCoverage(
            module_path="src/test.py",
            total_lines=100,
            covered_lines=80,
            coverage_percent=80.0,
        )
        assert module.module_path == "src/test.py"
        assert module.total_lines == 100
        assert module.covered_lines == 80
        assert module.coverage_percent == 80.0
        assert module.uncovered_lines == 20

    def test_module_coverage_critical_path(self):
        """Test module on critical path."""
        module = ModuleCoverage(
            module_path="src/execution/test.py",
            total_lines=100,
            covered_lines=80,
            coverage_percent=80.0,
            critical_path=True,
        )
        assert module.critical_path is True

    def test_module_coverage_to_dict(self):
        """Test converting module coverage to dictionary."""
        module = ModuleCoverage(
            module_path="src/test.py",
            total_lines=100,
            covered_lines=80,
            coverage_percent=80.0,
        )
        data = module.to_dict()
        assert data["module_path"] == "src/test.py"
        assert data["uncovered_lines"] == 20
        assert data["coverage_percent"] == 80.0


class TestCoverageReport:
    """Tests for CoverageReport dataclass."""

    def test_coverage_report_creation(self):
        """Test creating a coverage report."""
        report = CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=85.0,
            total_gaps=10,
            critical_gaps=2,
        )
        assert report.overall_coverage == 85.0
        assert report.total_gaps == 10
        assert report.critical_gaps == 2
        assert report.is_compliant() is True

    def test_is_compliant_above_threshold(self):
        """Test compliance check above threshold."""
        report = CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=85.0,
        )
        assert report.is_compliant(80.0) is True
        assert report.is_compliant(90.0) is False

    def test_coverage_report_to_dict(self):
        """Test converting report to dictionary."""
        report = CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=85.0,
            total_gaps=10,
            critical_gaps=2,
            recommendations=["Add more tests"],
        )
        data = report.to_dict()
        assert data["overall_coverage"] == 85.0
        assert data["total_gaps"] == 10
        assert "Add more tests" in data["recommendations"]


class TestCoverageAnalyzer:
    """Tests for CoverageAnalyzer class."""

    def test_analyzer_initialization(self):
        """Test analyzer initialization."""
        analyzer = CoverageAnalyzer()
        assert analyzer is not None
        assert analyzer.critical_modules == CRITICAL_MODULES

    def test_analyzer_custom_critical_modules(self):
        """Test analyzer with custom critical modules."""
        custom_modules = ["src/custom/"]
        analyzer = CoverageAnalyzer(critical_modules=custom_modules)
        assert analyzer.critical_modules == custom_modules

    @patch("tests.coverage.improvement.analyzer.subprocess.run")
    def test_run_coverage(self, mock_run):
        """Test running coverage command."""
        mock_run.return_value = MagicMock(returncode=0)

        analyzer = CoverageAnalyzer()
        result = analyzer.run_coverage()

        # Should return empty dict when coverage.json doesn't exist
        assert "files" in result

    def test_identify_gaps_empty_data(self):
        """Test gap identification with empty data."""
        analyzer = CoverageAnalyzer()
        gaps = analyzer._identify_gaps(
            "src/test.py",
            {"executed_lines": [], "missing_lines": []},
            is_critical=False,
        )
        assert gaps == []

    def test_identify_gaps_with_missing_lines(self):
        """Test gap identification with missing lines."""
        analyzer = CoverageAnalyzer()
        gaps = analyzer._identify_gaps(
            "src/test.py",
            {"executed_lines": [1, 2, 3], "missing_lines": [10, 11, 12]},
            is_critical=False,
        )
        assert len(gaps) == 3
        assert all(g.priority == Priority.MEDIUM for g in gaps)

    def test_identify_gaps_critical_module(self):
        """Test gap identification for critical module."""
        analyzer = CoverageAnalyzer()
        gaps = analyzer._identify_gaps(
            "src/execution/test.py",
            {"executed_lines": [1, 2, 3], "missing_lines": [10]},
            is_critical=True,
        )
        assert len(gaps) == 1
        assert gaps[0].priority == Priority.CRITICAL

    def test_generate_recommendations_low_coverage(self):
        """Test recommendation generation for low coverage."""
        analyzer = CoverageAnalyzer()

        modules = [
            ModuleCoverage(
                module_path="src/test.py",
                total_lines=100,
                covered_lines=30,
                coverage_percent=30.0,
            )
        ]

        recommendations = analyzer._generate_recommendations(modules, overall=30.0)

        # Should have recommendations about low coverage
        assert any("30" in r or "below" in r.lower() for r in recommendations)


class TestCoverageThresholds:
    """Tests for CoverageThresholds dataclass."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = CoverageThresholds.default()
        assert thresholds.minimum_coverage == 80.0
        assert thresholds.critical_path_minimum == 90.0
        assert thresholds.fail_on_violation is True

    def test_strict_thresholds(self):
        """Test strict threshold values."""
        thresholds = CoverageThresholds.strict()
        assert thresholds.minimum_coverage == 85.0
        assert thresholds.critical_path_minimum == 95.0

    def test_ci_thresholds(self):
        """Test CI threshold values."""
        thresholds = CoverageThresholds.ci()
        assert thresholds.minimum_coverage == 80.0
        assert thresholds.fail_on_violation is True


class TestCoverageReporter:
    """Tests for CoverageReporter class."""

    def test_reporter_initialization(self):
        """Test reporter initialization."""
        reporter = CoverageReporter()
        assert reporter is not None
        assert reporter.thresholds is not None

    def test_format_console(self):
        """Test console format generation."""
        reporter = CoverageReporter()
        report = CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=85.0,
            total_gaps=10,
            critical_gaps=2,
        )

        content = reporter._format_console(report)

        assert "COVERAGE REPORT" in content
        assert "85.0" in content or "85" in content

    def test_format_json(self):
        """Test JSON format generation."""
        reporter = CoverageReporter()
        report = CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=85.0,
            total_gaps=10,
            critical_gaps=2,
        )

        content = reporter._format_json(report)

        assert '"overall_coverage"' in content
        assert "85" in content

    def test_format_markdown(self):
        """Test Markdown format generation."""
        reporter = CoverageReporter()
        report = CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=85.0,
            total_gaps=10,
            critical_gaps=2,
        )

        content = reporter._format_markdown(report)

        assert "# Coverage Report" in content
        assert "85" in content

    def test_format_html(self):
        """Test HTML format generation."""
        reporter = CoverageReporter()
        report = CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=85.0,
            total_gaps=10,
            critical_gaps=2,
        )

        content = reporter._format_html(report)

        assert "<!DOCTYPE html>" in content
        assert "Coverage Report" in content

    def test_check_compliance_passing(self):
        """Test compliance check when passing."""
        reporter = CoverageReporter(
            thresholds=CoverageThresholds(minimum_coverage=80.0)
        )
        report = CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=85.0,
        )

        assert reporter.check_compliance(report) is True

    def test_check_compliance_failing(self):
        """Test compliance check when failing."""
        reporter = CoverageReporter(
            thresholds=CoverageThresholds(minimum_coverage=80.0)
        )
        report = CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=70.0,
        )

        assert reporter.check_compliance(report) is False

    def test_get_summary_for_ci(self):
        """Test CI summary generation."""
        reporter = CoverageReporter()
        report = CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=85.0,
            total_gaps=10,
            critical_gaps=2,
        )

        summary = reporter.get_summary_for_ci(report)

        assert summary["coverage"] == 85.0
        assert summary["gaps"] == 10
        assert "compliant" in summary


class TestReportFormat:
    """Tests for ReportFormat enum."""

    def test_report_format_values(self):
        """Test that all expected formats exist."""
        assert ReportFormat.CONSOLE.value == "console"
        assert ReportFormat.JSON.value == "json"
        assert ReportFormat.MARKDOWN.value == "markdown"
        assert ReportFormat.HTML.value == "html"
