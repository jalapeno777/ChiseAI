"""Tests for CI Observability Report (scripts/ci/ci_observability_report.py)."""

from __future__ import annotations

import json

# Import from the actual module
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.ci_observability_report import (
    CIObservabilityCollector,
    StepDiagnostics,
    StepTiming,
    format_human_report,
    format_json_report,
)


class TestStepTiming:
    """Tests for StepTiming dataclass - covers C-1 exit_code fix."""

    def test_create_minimal(self) -> None:
        """Test creating StepTiming with minimal data."""
        timing = StepTiming(step_name="test-step")
        assert timing.step_name == "test-step"
        assert timing.duration_seconds is None
        assert timing.start_time is None
        assert timing.end_time is None
        assert timing.status == "unknown"
        assert timing.has_timing is False
        assert timing.exit_code is None

    def test_create_full(self) -> None:
        """Test creating StepTiming with all fields."""
        timing = StepTiming(
            step_name="build",
            duration_seconds=120.5,
            start_time="2026-04-05T10:00:00Z",
            end_time="2026-04-05T10:02:00Z",
            status="pass",
            has_timing=True,
            exit_code=0,
        )
        assert timing.step_name == "build"
        assert timing.duration_seconds == 120.5
        assert timing.start_time == "2026-04-05T10:00:00Z"
        assert timing.end_time == "2026-04-05T10:02:00Z"
        assert timing.status == "pass"
        assert timing.has_timing is True
        assert timing.exit_code == 0

    def test_exit_code_can_be_set(self) -> None:
        """Test that exit_code can be set and retrieved - C-1 regression test."""
        timing = StepTiming(step_name="test-step")
        timing.exit_code = 1
        assert timing.exit_code == 1

    def test_to_dict_includes_exit_code(self) -> None:
        """Test that to_dict (via asdict) includes exit_code field."""
        timing = StepTiming(
            step_name="test-step",
            status="fail",
            exit_code=1,
        )
        timing_dict = asdict(timing)
        assert "exit_code" in timing_dict
        assert timing_dict["exit_code"] == 1


class TestStepDiagnostics:
    """Tests for StepDiagnostics dataclass."""

    def test_create_minimal(self) -> None:
        """Test creating StepDiagnostics with minimal data."""
        diag = StepDiagnostics(step_name="test-step")
        assert diag.step_name == "test-step"
        assert diag.exit_code is None
        assert diag.error_summary is None
        assert diag.failed_commands == []
        assert diag.traceback_lines == 0
        assert diag.has_stack_trace is False

    def test_create_full(self) -> None:
        """Test creating StepDiagnostics with all fields."""
        diag = StepDiagnostics(
            step_name="build",
            exit_code=1,
            error_summary="Command failed with exit code 1",
            failed_commands=["npm run build"],
            traceback_lines=10,
            has_stack_trace=True,
        )
        assert diag.step_name == "build"
        assert diag.exit_code == 1
        assert "Command failed" in diag.error_summary
        assert "npm run build" in diag.failed_commands
        assert diag.traceback_lines == 10
        assert diag.has_stack_trace is True

    def test_to_dict(self) -> None:
        """Test that to_dict includes all fields."""
        diag = StepDiagnostics(
            step_name="build",
            exit_code=1,
            error_summary="Error",
            failed_commands=["cmd1"],
            traceback_lines=5,
            has_stack_trace=True,
        )
        diag_dict = asdict(diag)
        assert "step_name" in diag_dict
        assert "exit_code" in diag_dict
        assert "error_summary" in diag_dict
        assert "failed_commands" in diag_dict
        assert "traceback_lines" in diag_dict
        assert "has_stack_trace" in diag_dict


class TestCIObservabilityCollector:
    """Tests for CIObservabilityCollector."""

    def test_collect_empty_directory(self) -> None:
        """Test collecting from non-existent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = CIObservabilityCollector(Path(tmpdir))
            report = collector.collect()
            assert report.overall_status == "unknown"
            assert report.steps == []
            assert report.summary["total_steps"] == 0

    def test_collect_with_status_files(self) -> None:
        """Test collecting from directory with status files - includes exit_code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ci_dir = Path(tmpdir)
            # Create status files
            (ci_dir / "build.status").write_text("0")  # pass, exit_code=0
            (ci_dir / "test.status").write_text("1")  # fail, exit_code=1
            (ci_dir / "lint.status").write_text("SKIP")  # skip

            collector = CIObservabilityCollector(ci_dir)
            report = collector.collect()

            assert report.summary["total_steps"] == 3

            # Find each step and verify exit_code is present
            steps_by_name = {s["step_name"]: s for s in report.steps}

            # build: pass with exit_code=0
            assert steps_by_name["build"]["status"] == "pass"
            assert steps_by_name["build"]["exit_code"] == 0

            # test: fail with exit_code=1
            assert steps_by_name["test"]["status"] == "fail"
            assert steps_by_name["test"]["exit_code"] == 1

            # lint: SKIP has no exit_code
            assert steps_by_name["lint"]["status"] == "pass"

    def test_collect_with_log_files(self) -> None:
        """Test collecting timing from log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ci_dir = Path(tmpdir)
            # Create log file with timing
            (ci_dir / "build.log").write_text("[build] Completed in 45s\n")

            collector = CIObservabilityCollector(ci_dir)
            report = collector.collect()

            steps_by_name = {s["step_name"]: s for s in report.steps}
            assert steps_by_name["build"]["duration_seconds"] == 45.0
            assert steps_by_name["build"]["has_timing"] is True


class TestDiagnosticsSerialization:
    """Tests for H-1: diagnostics serialization in report output."""

    def test_diagnostics_merged_into_step_data(self) -> None:
        """Test that diagnostics are merged into step data in report - H-1 regression test."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ci_dir = Path(tmpdir)
            # Create status file
            (ci_dir / "build.status").write_text("1")
            # Create log file with traceback
            (ci_dir / "build.log").write_text(
                "Traceback (most recent call last):\n"
                "Traceback: another line\n"
                "Error: Command failed\n"
            )

            collector = CIObservabilityCollector(ci_dir)
            report = collector.collect()

            # Find the build step
            steps_by_name = {s["step_name"]: s for s in report.steps}
            build_step = steps_by_name["build"]

            # Diagnostics should be merged into step data
            assert "diagnostics" in build_step
            diag = build_step["diagnostics"]
            assert diag["step_name"] == "build"
            assert diag["exit_code"] == 1
            assert diag["has_stack_trace"] is True
            assert diag["traceback_lines"] == 2  # 2 lines contain "Traceback"

    def test_report_json_includes_diagnostics(self) -> None:
        """Test that JSON report output includes diagnostics - H-1 verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ci_dir = Path(tmpdir)
            (ci_dir / "test.status").write_text("1")
            (ci_dir / "test.log").write_text(
                "Error: Test failed\nTraceback:\n  line 1\n  line 2\n"
            )

            collector = CIObservabilityCollector(ci_dir)
            report = collector.collect()
            json_output = format_json_report(report)

            parsed = json.loads(json_output)
            assert len(parsed["steps"]) > 0

            # Find the test step
            test_step = next(s for s in parsed["steps"] if s["step_name"] == "test")
            assert "diagnostics" in test_step
            assert test_step["diagnostics"]["exit_code"] == 1


class TestReportSerialization:
    """Tests for report serialization methods."""

    def test_json_report_includes_all_fields(self) -> None:
        """Test that JSON report includes all expected fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ci_dir = Path(tmpdir)
            (ci_dir / "build.status").write_text("0")

            collector = CIObservabilityCollector(ci_dir)
            report = collector.collect()
            json_output = format_json_report(report)

            parsed = json.loads(json_output)

            # Check top-level fields
            assert "version" in parsed
            assert "timestamp" in parsed
            assert "pipeline_number" in parsed
            assert "branch" in parsed
            assert "commit_sha" in parsed
            assert "steps" in parsed
            assert "total_duration_seconds" in parsed
            assert "overall_status" in parsed
            assert "diagnostics_available" in parsed
            assert "summary" in parsed

    def test_human_report_includes_step_timings(self) -> None:
        """Test that human report includes step timing table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ci_dir = Path(tmpdir)
            (ci_dir / "build.status").write_text("0")
            (ci_dir / "build.log").write_text("[build] Completed in 30s\n")

            collector = CIObservabilityCollector(ci_dir)
            report = collector.collect()
            human_output = format_human_report(report)

            assert "CI OBSERVABILITY REPORT" in human_output
            assert "SUMMARY:" in human_output
            assert "STEP TIMINGS:" in human_output
            assert "build" in human_output
            assert "30" in human_output
