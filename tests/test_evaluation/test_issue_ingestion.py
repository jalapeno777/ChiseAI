"""
Tests for issue ingestion and parsing system.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from src.evaluation import Issue, IssueCategory, IssueSource
from src.evaluation.issue_ingestion import IssueIngestion
from src.evaluation.parsers import CILogParser, IterlogParser, WorkerReportParser


class TestIssueDataclass:
    """Tests for the Issue dataclass."""

    def test_issue_creation(self):
        """Test basic issue creation."""
        issue = Issue(
            category=IssueCategory.TOOL_ERROR,
            description="Test error message",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now(),
            raw_text="ERROR: Test error message",
        )

        assert issue.category == IssueCategory.TOOL_ERROR
        assert issue.description == "Test error message"
        assert issue.source == IssueSource.ITERLOG
        assert issue.fingerprint != ""  # Should be auto-generated

    def test_fingerprint_generation(self):
        """Test that fingerprints are generated correctly."""
        issue1 = Issue(
            category=IssueCategory.TOOL_ERROR,
            description="Error in file /path/to/file.py",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now(),
            raw_text="ERROR: Error in file /path/to/file.py",
        )

        issue2 = Issue(
            category=IssueCategory.TOOL_ERROR,
            description="Error in file /different/path.py",
            source=IssueSource.CI_LOG,
            timestamp=datetime.now(),
            raw_text="ERROR: Error in file /different/path.py",
        )

        # Same category + normalized description should produce same fingerprint
        assert issue1.fingerprint == issue2.fingerprint

    def test_fingerprint_different_categories(self):
        """Test that different categories produce different fingerprints."""
        issue1 = Issue(
            category=IssueCategory.TOOL_ERROR,
            description="Connection failed",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now(),
            raw_text="ERROR: Connection failed",
        )

        issue2 = Issue(
            category=IssueCategory.DB_CONNECTIVITY,
            description="Connection failed",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now(),
            raw_text="ERROR: Connection failed",
        )

        # Different categories should produce different fingerprints
        assert issue1.fingerprint != issue2.fingerprint

    def test_description_normalization(self):
        """Test that description normalization works correctly."""
        # Test path normalization
        norm1 = Issue._normalize_description("Error in /home/user/file.py line 42")
        norm2 = Issue._normalize_description("Error in /var/log/test.py line 100")

        # Both should have paths and numbers normalized
        assert "<PATH>" in norm1
        assert "<NUM>" in norm1
        assert norm1 == norm2  # Should be same after normalization


class TestIterlogParser:
    """Tests for the IterlogParser class."""

    @pytest.fixture
    def temp_iterlog_dir(self):
        """Create a temporary directory with sample iterlog files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create sample iterlog file
            iterlog_content = """---
project: ChiseAI
story_id: ST-TEST-001
date: 2026-03-01
---

## Blockers
- blocker: Redis connection refused
- Permission denied accessing /tmp/test

## Errors
- error: Import failed for module xyz
- Timeout waiting for response

## Notes
- slowdown: High latency detected
"""
            iterlog_path = Path(tmpdir) / "iterlog-2026-03-01.md"
            iterlog_path.write_text(iterlog_content)
            yield tmpdir

    def test_parse_file_detects_issues(self, temp_iterlog_dir):
        """Test that parsing detects various issue types."""
        parser = IterlogParser(base_path=temp_iterlog_dir)
        issues = parser.parse_all()

        # Should detect multiple issues
        assert len(issues) >= 3

        # Check categories
        categories = {issue.category for issue in issues}
        assert IssueCategory.DB_CONNECTIVITY in categories  # Redis error
        assert IssueCategory.FILE_ACCESS in categories  # Permission denied
        assert IssueCategory.TOOL_ERROR in categories  # Import failed

    def test_parse_file_extracts_story_id(self, temp_iterlog_dir):
        """Test that story_id is extracted from frontmatter."""
        parser = IterlogParser(base_path=temp_iterlog_dir)
        issues = parser.parse_all()

        # All issues should have the story_id
        for issue in issues:
            assert issue.story_id == "ST-TEST-001"

    def test_parse_since_respects_time_window(self, temp_iterlog_dir):
        """Test that parse_since respects the time window."""
        parser = IterlogParser(base_path=temp_iterlog_dir)

        # Parse only files from the last hour (should include our file)
        since = datetime.now() - timedelta(hours=1)
        issues_recent = parser.parse_since(since)

        # Parse only files from the future (should be empty)
        since_future = datetime.now() + timedelta(hours=1)
        issues_future = parser.parse_since(since_future)

        assert len(issues_recent) >= 1
        assert len(issues_future) == 0

    def test_categorize_file_access(self):
        """Test file access issue categorization."""
        parser = IterlogParser()

        detected = parser._detect_issues_in_line("Permission denied: /var/log/test.log")
        assert len(detected) == 1
        assert detected[0][0] == IssueCategory.FILE_ACCESS

    def test_categorize_db_connectivity(self):
        """Test database connectivity issue categorization."""
        parser = IterlogParser()

        detected = parser._detect_issues_in_line(
            "Redis connection refused on port 6379"
        )
        assert len(detected) == 1
        assert detected[0][0] == IssueCategory.DB_CONNECTIVITY


class TestCILogParser:
    """Tests for the CILogParser class."""

    @pytest.fixture
    def temp_ci_dir(self):
        """Create a temporary directory with sample CI log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create sample CI log file
            ci_log_content = """============================= test session starts ==============================
platform linux -- Python 3.13.7

==================================== ERRORS ====================================
_ ERROR collecting tests/test_example.py __
ImportError while importing test module:
E   ImportError: cannot import name 'MyClass' from 'src.module'

=================================== FAILURES ===================================
__ test_example_function __
    def test_example_function():
>       assert result == expected
E       AssertionError: expected value not found

============================= lint errors ======================================
src/module.py:42: E501 line too long
"""
            ci_log_path = Path(tmpdir) / "test-run.log"
            ci_log_path.write_text(ci_log_content)
            yield tmpdir

    def test_parse_file_detects_failures(self, temp_ci_dir):
        """Test that parsing detects test failures."""
        parser = CILogParser(base_path=temp_ci_dir)
        issues = parser.parse_all()

        # Should detect errors
        assert len(issues) >= 2

        # Check that tool errors are detected
        tool_errors = [i for i in issues if i.category == IssueCategory.TOOL_ERROR]
        assert len(tool_errors) >= 1

    def test_detect_import_errors(self):
        """Test detection of import errors."""
        parser = CILogParser()

        detected = parser._detect_issues_in_line(
            "ImportError: cannot import name 'MyClass'"
        )
        assert len(detected) == 1
        assert detected[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_test_failures(self):
        """Test detection of test failures."""
        parser = CILogParser()

        detected = parser._detect_issues_in_line(
            "FAILED test_example.py::test_function"
        )
        assert len(detected) == 1
        assert detected[0][0] == IssueCategory.TOOL_ERROR

    def test_detect_timeouts(self):
        """Test detection of timeout issues."""
        parser = CILogParser()

        detected = parser._detect_issues_in_line("ERROR: Timeout after 30 seconds")
        assert len(detected) == 1
        assert detected[0][0] == IssueCategory.ENV_SLOWDOWN

    def test_categorize_error(self):
        """Test error categorization."""
        parser = CILogParser()

        assert parser.categorize_error("Permission denied") == IssueCategory.FILE_ACCESS
        assert parser.categorize_error("Timeout waiting") == IssueCategory.ENV_SLOWDOWN
        assert parser.categorize_error("ImportError") == IssueCategory.TOOL_ERROR


class TestWorkerReportParser:
    """Tests for the WorkerReportParser class."""

    @pytest.fixture
    def temp_report_dir(self):
        """Create a temporary directory with sample worker reports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create sample worker report
            report_content = """---
story_id: ST-WORKER-001
---

## Task Completion Report

### Status: blocked

### Blockers
- blocker: Redis connection refused
- blocker: Waiting for external API

### Errors
- error: File not found at /tmp/input.csv
- slowdown: API latency exceeded threshold

### Files Changed
- src/module.py (42 lines)
"""
            report_path = Path(tmpdir) / "worker-ST-WORKER-001.md"
            report_path.write_text(report_content)
            yield tmpdir

    def test_parse_file_detects_issues(self, temp_report_dir):
        """Test that parsing detects issues in worker reports."""
        parser = WorkerReportParser(base_path=temp_report_dir)
        issues = parser.parse_all()

        # Should detect multiple issues
        assert len(issues) >= 2

        # Check categories
        categories = {issue.category for issue in issues}
        assert (
            IssueCategory.DB_CONNECTIVITY in categories
            or IssueCategory.TOOL_ERROR in categories
        )

    def test_parse_text_directly(self):
        """Test parsing worker report text directly."""
        parser = WorkerReportParser()

        text = """
        Blocker: Cannot connect to Redis
        Error: Import failed for module
        """
        issues = parser.parse_text(text)

        assert len(issues) >= 2

    def test_extract_story_id(self):
        """Test story_id extraction from various formats."""
        parser = WorkerReportParser()

        assert parser._extract_story_id("story_id: ST-123") == "ST-123"
        assert parser._extract_story_id("STORY: CH-456") == "CH-456"
        assert parser._extract_story_id("Working on ST-789-abc") == "ST-789-abc"

    def test_categorize_issues(self):
        """Test issue categorization."""
        parser = WorkerReportParser()

        # File access
        assert parser._categorize_issue("file not found") == IssueCategory.FILE_ACCESS

        # Database
        assert parser._categorize_issue("redis error") == IssueCategory.DB_CONNECTIVITY

        # Slowdown
        assert parser._categorize_issue("timeout waiting") == IssueCategory.ENV_SLOWDOWN

        # Default
        assert parser._categorize_issue("some error") == IssueCategory.TOOL_ERROR


class TestIssueIngestion:
    """Tests for the IssueIngestion engine."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories with sample data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create iterlog
            iterlog_dir = Path(tmpdir) / "iterlogs"
            iterlog_dir.mkdir()
            (iterlog_dir / "iterlog-001.md").write_text("""
---
story_id: ST-TEST-001
---
- blocker: Redis connection refused
- error: Import failed
""")

            # Create CI log
            ci_dir = Path(tmpdir) / "ci"
            ci_dir.mkdir()
            (ci_dir / "test.log").write_text("""
FAILED test_example.py
ERROR: ImportError
""")

            # Create worker report
            (iterlog_dir / "worker-001.md").write_text("""
---
story_id: ST-WORKER-001
---
- blocker: API timeout
- error: Permission denied
""")

            yield {
                "iterlog_path": str(iterlog_dir),
                "ci_log_path": str(ci_dir),
                "worker_report_path": str(iterlog_dir),
            }

    def test_ingest_from_iterlogs(self, temp_dirs):
        """Test iterlog ingestion."""
        ingestion = IssueIngestion(
            iterlog_path=temp_dirs["iterlog_path"],
            ci_log_path=temp_dirs["ci_log_path"],
            worker_report_path=temp_dirs["worker_report_path"],
        )

        issues = ingestion.ingest_from_iterlogs()
        assert len(issues) >= 1

    def test_ingest_from_ci_logs(self, temp_dirs):
        """Test CI log ingestion."""
        ingestion = IssueIngestion(
            iterlog_path=temp_dirs["iterlog_path"],
            ci_log_path=temp_dirs["ci_log_path"],
            worker_report_path=temp_dirs["worker_report_path"],
        )

        issues = ingestion.ingest_from_ci_logs()
        assert len(issues) >= 1

    def test_ingest_from_worker_reports(self, temp_dirs):
        """Test worker report ingestion."""
        ingestion = IssueIngestion(
            iterlog_path=temp_dirs["iterlog_path"],
            ci_log_path=temp_dirs["ci_log_path"],
            worker_report_path=temp_dirs["worker_report_path"],
        )

        issues = ingestion.ingest_from_worker_reports()
        assert len(issues) >= 1

    def test_ingest_all(self, temp_dirs):
        """Test ingestion from all sources."""
        ingestion = IssueIngestion(
            iterlog_path=temp_dirs["iterlog_path"],
            ci_log_path=temp_dirs["ci_log_path"],
            worker_report_path=temp_dirs["worker_report_path"],
        )

        issues = ingestion.ingest_all(include_redis=False)
        assert len(issues) >= 2

    def test_deduplication(self, temp_dirs):
        """Test that duplicate issues are removed."""
        ingestion = IssueIngestion(
            iterlog_path=temp_dirs["iterlog_path"],
            ci_log_path=temp_dirs["ci_log_path"],
            worker_report_path=temp_dirs["worker_report_path"],
        )

        # Ingest twice
        issues1 = ingestion.ingest_from_iterlogs()
        issues2 = ingestion.ingest_from_iterlogs()

        # Second call should return empty (already seen)
        assert len(issues2) == 0

    def test_reset_deduplication(self, temp_dirs):
        """Test resetting deduplication state."""
        ingestion = IssueIngestion(
            iterlog_path=temp_dirs["iterlog_path"],
            ci_log_path=temp_dirs["ci_log_path"],
            worker_report_path=temp_dirs["worker_report_path"],
        )

        # Ingest
        issues1 = ingestion.ingest_from_iterlogs()

        # Reset
        ingestion.reset_deduplication()

        # Ingest again should work
        issues2 = ingestion.ingest_from_iterlogs()
        assert len(issues2) == len(issues1)

    def test_get_issue_counts_by_category(self, temp_dirs):
        """Test counting issues by category."""
        ingestion = IssueIngestion(
            iterlog_path=temp_dirs["iterlog_path"],
            ci_log_path=temp_dirs["ci_log_path"],
            worker_report_path=temp_dirs["worker_report_path"],
        )

        issues = ingestion.ingest_all(include_redis=False)
        counts = ingestion.get_issue_counts_by_category(issues)

        # Should have entries for all categories
        assert IssueCategory.TOOL_ERROR in counts
        assert IssueCategory.FILE_ACCESS in counts
        assert IssueCategory.DB_CONNECTIVITY in counts
        assert IssueCategory.ENV_SLOWDOWN in counts
        assert IssueCategory.OTHER in counts

    def test_get_issue_counts_by_source(self, temp_dirs):
        """Test counting issues by source."""
        ingestion = IssueIngestion(
            iterlog_path=temp_dirs["iterlog_path"],
            ci_log_path=temp_dirs["ci_log_path"],
            worker_report_path=temp_dirs["worker_report_path"],
        )

        issues = ingestion.ingest_all(include_redis=False)
        counts = ingestion.get_issue_counts_by_source(issues)

        # Should have entries for all sources
        assert IssueSource.ITERLOG in counts
        assert IssueSource.CI_LOG in counts
        assert IssueSource.WORKER_REPORT in counts
        assert IssueSource.REDIS in counts

    def test_time_window_filtering(self, temp_dirs):
        """Test that time window filtering works."""
        ingestion = IssueIngestion(
            iterlog_path=temp_dirs["iterlog_path"],
            ci_log_path=temp_dirs["ci_log_path"],
            worker_report_path=temp_dirs["worker_report_path"],
        )

        # Future time window should return no issues
        future = datetime.now() + timedelta(hours=1)
        issues = ingestion.ingest_all(since=future, include_redis=False)
        assert len(issues) == 0


class TestFingerprintGeneration:
    """Tests for fingerprint generation and deduplication."""

    def test_same_issue_same_fingerprint(self):
        """Test that identical issues get the same fingerprint."""
        issue1 = Issue(
            category=IssueCategory.TOOL_ERROR,
            description="Error connecting to Redis",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now(),
            raw_text="Error connecting to Redis",
        )

        issue2 = Issue(
            category=IssueCategory.TOOL_ERROR,
            description="Error connecting to Redis",
            source=IssueSource.CI_LOG,
            timestamp=datetime.now(),
            raw_text="Error connecting to Redis",
        )

        assert issue1.fingerprint == issue2.fingerprint

    def test_different_category_different_fingerprint(self):
        """Test that different categories produce different fingerprints."""
        issue1 = Issue(
            category=IssueCategory.TOOL_ERROR,
            description="Connection failed",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now(),
            raw_text="Connection failed",
        )

        issue2 = Issue(
            category=IssueCategory.DB_CONNECTIVITY,
            description="Connection failed",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now(),
            raw_text="Connection failed",
        )

        assert issue1.fingerprint != issue2.fingerprint

    def test_normalized_paths_produce_same_fingerprint(self):
        """Test that paths are normalized in fingerprinting."""
        issue1 = Issue(
            category=IssueCategory.FILE_ACCESS,
            description="Permission denied /home/user/file.py",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now(),
            raw_text="Permission denied /home/user/file.py",
        )

        issue2 = Issue(
            category=IssueCategory.FILE_ACCESS,
            description="Permission denied /var/log/other.py",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now(),
            raw_text="Permission denied /var/log/other.py",
        )

        assert issue1.fingerprint == issue2.fingerprint

    def test_timestamp_not_in_fingerprint(self):
        """Test that timestamps don't affect fingerprints."""
        issue1 = Issue(
            category=IssueCategory.TOOL_ERROR,
            description="Error at 2026-03-01T10:00:00",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now() - timedelta(hours=1),
            raw_text="Error at 2026-03-01T10:00:00",
        )

        issue2 = Issue(
            category=IssueCategory.TOOL_ERROR,
            description="Error at 2026-03-01T12:00:00",
            source=IssueSource.ITERLOG,
            timestamp=datetime.now(),
            raw_text="Error at 2026-03-01T12:00:00",
        )

        assert issue1.fingerprint == issue2.fingerprint


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
