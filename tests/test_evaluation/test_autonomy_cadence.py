"""Tests for autonomy cadence controller and job health diagnostics."""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scripts.evaluation.autonomy_cadence_controller import (
    cadence_seconds,
    calculate_job_health_score,
    emit_alert,
    format_age_human,
    format_duration,
    iso,
    now_utc,
    parse_iso,
)
from scripts.ops.autonomy_job_health import (
    calculate_health_score,
    get_job_trends,
    load_runs,
    load_state,
    needs_attention,
)


class TestTimeFormatting:
    """Tests for time formatting utilities."""

    def test_format_duration_seconds(self):
        assert format_duration(45) == "45s"

    def test_format_duration_minutes(self):
        assert format_duration(125) == "2m 5s"

    def test_format_duration_hours(self):
        assert format_duration(3665) == "1h 1m"

    def test_format_duration_days(self):
        assert format_duration(90061) == "1d 1h"

    def test_format_age_human_none(self):
        assert format_age_human(None) is None

    def test_format_age_human_invalid(self):
        assert format_age_human("invalid") is None

    def test_format_age_human_recent(self):
        recent = (now_utc() - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        result = format_age_human(recent)
        assert "ago" in result
        assert "m" in result

    def test_format_age_human_old(self):
        old = (now_utc() - timedelta(days=2)).isoformat().replace("+00:00", "Z")
        result = format_age_human(old)
        assert "ago" in result
        assert "d" in result


class TestCadenceParsing:
    """Tests for cadence parsing."""

    def test_cadence_6h(self):
        assert cadence_seconds("6h") == 6 * 3600

    def test_cadence_daily(self):
        assert cadence_seconds("daily") == 24 * 3600

    def test_cadence_weekly(self):
        assert cadence_seconds("weekly") == 7 * 24 * 3600

    def test_cadence_monthly(self):
        assert cadence_seconds("monthly") == 30 * 24 * 3600

    def test_cadence_event(self):
        assert cadence_seconds("event") is None

    def test_cadence_minutes(self):
        assert cadence_seconds("30m") == 30 * 60

    def test_cadence_custom_hours(self):
        assert cadence_seconds("12h") == 12 * 3600

    def test_cadence_case_insensitive(self):
        assert cadence_seconds("DAILY") == 24 * 3600


class TestJobHealthScore:
    """Tests for job health score calculation."""

    def test_perfect_score_success(self):
        job_state = {
            "last_status": "success",
            "last_success_at": iso(),
        }
        score, details = calculate_job_health_score(job_state, 3600)
        assert score == 100
        assert "last_run_success" in str(details["score_factors"])

    def test_failed_status_deduction(self):
        job_state = {
            "last_status": "failed",
            "last_success_at": iso(),
        }
        score, details = calculate_job_health_score(job_state, 3600)
        assert score == 70
        assert any("-30" in f for f in details["deductions"])

    def test_timeout_status_deduction(self):
        job_state = {
            "last_status": "timeout",
            "last_success_at": iso(),
        }
        score, details = calculate_job_health_score(job_state, 3600)
        assert score == 70

    def test_awaiting_approval_deduction(self):
        job_state = {
            "last_status": "awaiting_approval",
            "last_success_at": iso(),
        }
        score, details = calculate_job_health_score(job_state, 3600)
        assert score == 90

    def test_overdue_deduction(self):
        old_success = (
            (now_utc() - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        )
        job_state = {
            "last_status": "success",
            "last_success_at": old_success,
        }
        # 2 hour interval, 3 hours since success = overdue
        score, details = calculate_job_health_score(job_state, 2 * 3600)
        assert score < 100
        assert "expected_next_run" in details

    def test_severely_overdue(self):
        old_success = (
            (now_utc() - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        )
        job_state = {
            "last_status": "success",
            "last_success_at": old_success,
        }
        # 2 hour interval, 5 hours since success = severely overdue
        score, details = calculate_job_health_score(job_state, 2 * 3600)
        assert score <= 60
        assert any("severely_overdue" in d for d in details["deductions"])

    def test_error_deduction(self):
        job_state = {
            "last_status": "failed",
            "last_success_at": iso(),
            "last_error": "Some error",
        }
        score, details = calculate_job_health_score(job_state, 3600)
        assert score <= 65  # -30 for failed, -5 for error

    def test_score_bounds(self):
        job_state = {
            "last_status": "failed",
            "last_success_at": (now_utc() - timedelta(days=10))
            .isoformat()
            .replace("+00:00", "Z"),
            "last_error": "Error",
        }
        score, _ = calculate_job_health_score(job_state, 3600)
        assert 0 <= score <= 100


class TestAlertFormatting:
    """Tests for alert formatting and Discord notifications."""

    def test_emit_alert_creates_jsonl(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        emit_alert(
            output_dir=output_dir,
            alert_type="test_alert",
            job_id="test.job",
            severity="high",
            message="Test message",
            details={"key": "value"},
        )

        alerts_file = output_dir / "alerts.jsonl"
        assert alerts_file.exists()

        content = alerts_file.read_text()
        alert = json.loads(content.strip())
        assert alert["alert_type"] == "test_alert"
        assert alert["job_id"] == "test.job"
        assert alert["severity"] == "high"

    def test_missed_cadence_alert_includes_age_human(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        old_success = (
            (now_utc() - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        )

        with patch(
            "scripts.evaluation.autonomy_cadence_controller.send_discord"
        ) as mock_send:
            emit_alert(
                output_dir=output_dir,
                alert_type="missed_cadence",
                job_id="test.job",
                severity="high",
                message="Missed cadence",
                details={
                    "age_seconds": 18000,
                    "allowed_seconds": 21600,
                    "last_success_at": old_success,
                    "last_success_age_human": "5h ago",
                    "expected_next_run": "2026-03-10T20:00:00Z",
                    "job_health_score": 60,
                    "idempotency_key": "test:2026-03-10",
                },
            )

            # Check Discord was called with enhanced message
            mock_send.assert_called_once()
            discord_msg = mock_send.call_args[0][0]
            assert "last_success=" in discord_msg
            assert "expected_next=" in discord_msg
            assert "health_score=" in discord_msg


class TestJobHealthDiagnostics:
    """Tests for job health diagnostic script."""

    def test_load_state_empty(self, tmp_path):
        state = load_state(tmp_path / "nonexistent.json")
        assert state == {"jobs": {}}

    def test_load_state_valid(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_data = {
            "jobs": {
                "test.job": {
                    "last_status": "success",
                    "last_success_at": "2026-03-10T12:00:00Z",
                }
            }
        }
        state_file.write_text(json.dumps(state_data))

        state = load_state(state_file)
        assert "test.job" in state["jobs"]
        assert state["jobs"]["test.job"]["last_status"] == "success"

    def test_load_runs_empty(self, tmp_path):
        runs = load_runs(tmp_path / "nonexistent.jsonl")
        assert runs == []

    def test_load_runs_filtered(self, tmp_path):
        runs_file = tmp_path / "runs.jsonl"
        runs_data = [
            {
                "job_id": "job1",
                "status": "success",
                "timestamp_utc": "2026-03-10T12:00:00Z",
            },
            {
                "job_id": "job2",
                "status": "failed",
                "timestamp_utc": "2026-03-10T12:01:00Z",
            },
            {
                "job_id": "job1",
                "status": "success",
                "timestamp_utc": "2026-03-10T12:02:00Z",
            },
        ]
        runs_file.write_text("\n".join(json.dumps(r) for r in runs_data))

        runs = load_runs(runs_file, job_id="job1")
        assert len(runs) == 2
        assert all(r["job_id"] == "job1" for r in runs)

    def test_get_job_trends_empty(self):
        trends = get_job_trends([])
        assert trends["total_runs"] == 0
        assert trends["success_rate"] == 0.0

    def test_get_job_trends_calculates_rates(self):
        runs = [
            {"status": "success", "duration_seconds": 1.0},
            {"status": "success", "duration_seconds": 2.0},
            {"status": "failed", "duration_seconds": 1.5},
            {"status": "success", "duration_seconds": 1.0},
        ]
        trends = get_job_trends(runs)
        assert trends["total_runs"] == 4
        assert trends["success_rate"] == 75.0
        assert trends["avg_duration"] == 1.38  # (1+2+1.5+1)/4
        assert trends["status_breakdown"]["success"] == 3
        assert trends["status_breakdown"]["failed"] == 1

    def test_needs_attention_failed(self):
        job_state = {"last_status": "failed"}
        assert needs_attention(job_state) is True

    def test_needs_attention_timeout(self):
        job_state = {"last_status": "timeout"}
        assert needs_attention(job_state) is True

    def test_needs_attention_awaiting_approval(self):
        job_state = {"last_status": "awaiting_approval"}
        assert needs_attention(job_state) is True

    def test_needs_attention_no_success(self):
        job_state = {"last_status": "success"}  # No last_success_at
        assert needs_attention(job_state) is True

    def test_needs_attention_healthy(self):
        job_state = {
            "last_status": "success",
            "last_success_at": iso(),
        }
        assert needs_attention(job_state) is False

    def test_calculate_health_score_healthy(self):
        job_state = {"last_status": "success"}
        score, status = calculate_health_score(job_state)
        assert score == 100
        assert status == "healthy"

    def test_calculate_health_score_failed(self):
        job_state = {"last_status": "failed"}
        score, status = calculate_health_score(job_state)
        assert score == 70
        assert status == "degraded"

    def test_calculate_health_score_overdue(self):
        old_success = (
            (now_utc() - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        )
        job_state = {
            "last_status": "success",
            "last_success_at": old_success,
        }
        score, status = calculate_health_score(job_state, cadence="2h")
        assert score < 100


class TestIsoFormatting:
    """Tests for ISO timestamp formatting."""

    def test_iso_current_time(self):
        result = iso()
        assert result.endswith("Z")
        assert "T" in result

    def test_iso_specific_time(self):
        dt = datetime(2026, 3, 10, 12, 0, 0, tzinfo=UTC)
        result = iso(dt)
        assert result == "2026-03-10T12:00:00Z"

    def test_parse_iso_valid(self):
        result = parse_iso("2026-03-10T12:00:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 10

    def test_parse_iso_none(self):
        result = parse_iso(None)
        assert result is None

    def test_parse_iso_invalid(self):
        result = parse_iso("invalid")
        assert result is None
