"""Tests for post_run_reporter module."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "scripts" / "ci_integration")
)

from post_run_reporter import (
    CIReport,
    CIResultSummary,
    CoverageData,
    MetricsData,
    generate_influxdb_line_protocol,
    generate_markdown_report,
    get_git_info,
    parse_coverage_json,
    parse_pytest_json,
)
from post_run_reporter import (
    main as reporter_main,
)


class CIResultSummarySuite:
    """Tests for CIResultSummary dataclass."""

    def test_result_summary_defaults(self):
        """Test CIResultSummary with default values."""
        from post_run_reporter import CIResultSummary as TR

        summary = TR()
        assert summary.total == 0
        assert summary.passed == 0
        assert summary.failed == 0
        assert summary.skipped == 0
        assert summary.error == 0
        assert summary.duration_seconds == 0.0


class TestCoverageData:
    """Tests for CoverageData dataclass."""

    def test_coverage_summary_defaults(self):
        """Test CoverageData with default values."""
        summary = CoverageData()
        assert summary.line_percent == 0.0
        assert summary.branch_percent == 0.0


class TestMetricsData:
    """Tests for MetricsData dataclass."""

    def test_metrics_summary_defaults(self):
        """Test MetricsData with default values."""
        summary = MetricsData()
        assert summary.pylint_score is None
        assert summary.ruff_issues == 0


class TestCIReport:
    """Tests for CIReport dataclass."""

    def test_ci_report_creation(self):
        """Test CIReport can be created."""
        report = CIReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123",
            test_summary=CIResultSummary(),
        )
        assert report.branch == "main"
        assert report.commit_sha == "abc123"
        assert report.gates_passed is True

    def test_ci_report_with_coverage(self):
        """Test CIReport with coverage data."""
        report = CIReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123",
            test_summary=CIResultSummary(),
            coverage_summary=CoverageData(line_percent=85.0),
        )
        assert report.coverage_summary.line_percent == 85.0


class TestGetGitInfo:
    """Tests for get_git_info function."""

    @patch("subprocess.run")
    def test_get_git_info_success(self, mock_run):
        """Test successful git info retrieval."""
        mock_run.side_effect = [
            MagicMock(stdout="feature/test-branch\n"),
            MagicMock(stdout="abc123def456\n"),
        ]

        branch, sha = get_git_info(Path("/fake/path"))
        assert branch == "feature/test-branch"
        assert sha == "abc123def456"

    @patch("subprocess.run")
    def test_get_git_info_failure(self, mock_run):
        """Test git info on command failure."""
        mock_run.side_effect = FileNotFoundError("git not found")

        branch, sha = get_git_info(Path("/fake/path"))
        assert branch == "unknown"
        assert sha == "unknown"


class TestParsePytestJson:
    """Tests for parse_pytest_json function."""

    def test_parse_valid_pytest_json(self, tmp_path):
        """Test parsing valid pytest JSON."""
        pytest_file = tmp_path / "pytest.json"
        pytest_file.write_text(
            json.dumps(
                {
                    "num_tests": 100,
                    "summary": {
                        "passed": 95,
                        "failed": 3,
                        "skipped": 2,
                        "error": 0,
                    },
                    "duration": 45.5,
                }
            )
        )

        result = parse_pytest_json(pytest_file)
        assert result is not None
        assert result.total == 100
        assert result.passed == 95
        assert result.failed == 3
        assert result.skipped == 2
        assert result.duration_seconds == 45.5

    def test_parse_missing_file(self):
        """Test parsing non-existent file."""
        result = parse_pytest_json(Path("/nonexistent/pytest.json"))
        assert result is None

    def test_parse_invalid_json(self, tmp_path):
        """Test parsing invalid JSON."""
        pytest_file = tmp_path / "pytest.json"
        pytest_file.write_text("not valid json {{{")

        result = parse_pytest_json(pytest_file)
        assert result is None


class TestParseCoverageJson:
    """Tests for parse_coverage_json function."""

    def test_parse_valid_coverage_json(self, tmp_path):
        """Test parsing valid coverage JSON."""
        coverage_file = tmp_path / "coverage.json"
        coverage_file.write_text(
            json.dumps(
                {
                    "totals": {
                        "percent_covered": 85.5,
                        "branch_covered": 75.0,
                        "covered_lines": 500,
                        "total_lines": 585,
                    }
                }
            )
        )

        result = parse_coverage_json(coverage_file)
        assert result is not None
        assert result.line_percent == 85.5
        assert result.branch_percent == 75.0
        assert result.covered_lines == 500
        assert result.total_lines == 585

    def test_parse_missing_file(self):
        """Test parsing non-existent file."""
        result = parse_coverage_json(Path("/nonexistent/coverage.json"))
        assert result is None


class TestGenerateMarkdownReport:
    """Tests for generate_markdown_report function."""

    def test_markdown_report_basic(self):
        """Test basic markdown report generation."""
        report = CIReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123",
            test_summary=CIResultSummary(total=10, passed=10),
            gates_passed=True,
        )

        md = generate_markdown_report(report)

        assert "# CI Report - main" in md
        assert "✅ PASSED" in md
        assert "Total: 10" in md
        assert "Passed: 10" in md

    def test_markdown_report_with_coverage(self):
        """Test markdown report with coverage."""
        report = CIReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="feature/test",
            commit_sha="abc123",
            test_summary=CIResultSummary(total=10, passed=10),
            coverage_summary=CoverageData(line_percent=85.0, branch_percent=75.0),
            gates_passed=True,
        )

        md = generate_markdown_report(report)

        assert "## Coverage" in md
        assert "Line Coverage: 85.00%" in md
        assert "Branch Coverage: 75.00%" in md

    def test_markdown_report_failed(self):
        """Test markdown report for failed CI."""
        report = CIReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123",
            test_summary=CIResultSummary(total=10, passed=5, failed=5),
            gates_passed=False,
        )

        md = generate_markdown_report(report)

        assert "❌ FAILED" in md
        assert "Failed: 5" in md


class TestGenerateInfluxdbLineProtocol:
    """Tests for generate_influxdb_line_protocol function."""

    def test_influxdb_test_metrics(self):
        """Test InfluxDB line protocol for test metrics."""
        report = CIReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123def456",
            test_summary=CIResultSummary(total=10, passed=9, failed=1),
            gates_passed=True,
        )

        lines = generate_influxdb_line_protocol(report)

        assert len(lines) >= 1
        assert any("ci_tests,branch=main" in line for line in lines)
        assert any("total=10" in line for line in lines)

    def test_influxdb_coverage_metrics(self):
        """Test InfluxDB line protocol for coverage."""
        report = CIReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123def456",
            test_summary=CIResultSummary(total=10, passed=10),
            coverage_summary=CoverageData(line_percent=85.0),
            gates_passed=True,
        )

        lines = generate_influxdb_line_protocol(report)

        assert any("ci_coverage,branch=main" in line for line in lines)

    def test_influxdb_gate_metrics(self):
        """Test InfluxDB line protocol for gates."""
        report = CIReport(
            timestamp="2024-01-01T00:00:00Z",
            branch="main",
            commit_sha="abc123def456",
            test_summary=CIResultSummary(total=10, passed=10),
            gates_passed=True,
        )

        lines = generate_influxdb_line_protocol(report)

        assert any("ci_gates,branch=main" in line for line in lines)


class TestReporterMain:
    """Tests for post_run_reporter main function."""

    @patch("post_run_reporter.Path")
    @patch("subprocess.run")
    @patch("sys.argv", ["post_run_reporter"])
    def test_main_with_no_args(self, mock_run, mock_path):
        """Test main with no arguments."""
        mock_path.return_value.exists.return_value = False
        mock_run.return_value = MagicMock(stdout="main\n", returncode=0)

        with patch("sys.stdout", new=MagicMock()) as mock_stdout:
            exit_code = reporter_main()

        assert exit_code == 0

    @patch(
        "sys.argv",
        [
            "post_run_reporter",
            "--pytest-json",
            "/nonexistent/pytest.json",
            "--repo-path",
            "/fake/path",
        ],
    )
    def test_main_with_invalid_pytest_json(self):
        """Test main with non-existent pytest JSON."""
        with patch("sys.stdout", new=MagicMock()):
            exit_code = reporter_main()

        assert exit_code == 0  # Should still succeed, just no data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
