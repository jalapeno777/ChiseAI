"""Tests for autonomous_cognition.drift_detector module."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from autonomous_cognition.drift_detector import (
    CALIBRATION_KEY_PATTERN,
    DEFERRED_ITEMS_KEY,
    SELF_ASSESSMENT_KEY,
    DriftCheckResult,
    DriftReport,
    check_all,
    check_calibration_exists,
    check_deferred_items,
    check_self_assessment_score,
    main,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis_scan_empty():
    """Redis scan returning no keys."""
    return MagicMock(return_value=[])


@pytest.fixture
def mock_redis_scan_current_week():
    """Redis scan returning current week calibration key."""
    now = datetime.now(UTC)
    iso = now.isocalendar()
    week_str = f"{iso[0]}-W{iso[1]:02d}"
    key = f"bmad:chiseai:metacog:calibration:agent:jarvis:weekly:{week_str}"
    return MagicMock(return_value=[key])


@pytest.fixture
def mock_redis_scan_last_week():
    """Redis scan returning only last week's calibration key."""
    now = datetime.now(UTC)
    last_week = now - timedelta(weeks=1)
    iso = last_week.isocalendar()
    week_str = f"{iso[0]}-W{iso[1]:02d}"
    key = f"bmad:chiseai:metacog:calibration:agent:jarvis:weekly:{week_str}"
    return MagicMock(return_value=[key])


@pytest.fixture
def mock_redis_get_none():
    """Redis get returning None (no self-assessment)."""
    return MagicMock(return_value=None)


@pytest.fixture
def mock_redis_get_stable():
    """Redis get returning a stable self-assessment score."""
    data = json.dumps({"overall_score": 0.85, "previous_score": 0.83})
    return MagicMock(return_value=data)


@pytest.fixture
def mock_redis_get_dropped():
    """Redis get returning a significantly dropped self-assessment score."""
    data = json.dumps({"overall_score": 0.60, "previous_score": 0.85})
    return MagicMock(return_value=data)


@pytest.fixture
def mock_redis_hgetall_empty():
    """Redis hgetall returning no deferred items."""
    return MagicMock(return_value={})


@pytest.fixture
def mock_redis_hgetall_safe():
    """Redis hgetall returning deferred items well within deadline."""
    future = (datetime.now(UTC) + timedelta(days=14)).isoformat()
    items = {
        "item-1": json.dumps({"deadline": future, "description": "future item"}),
    }
    return MagicMock(return_value=items)


@pytest.fixture
def mock_redis_hgetall_approaching():
    """Redis hgetall returning deferred items approaching deadline."""
    soon = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    items = {
        "item-1": json.dumps({"deadline": soon, "description": "due soon"}),
    }
    return MagicMock(return_value=items)


@pytest.fixture
def mock_redis_hgetall_overdue():
    """Redis hgetall returning overdue deferred items."""
    past = (datetime.now(UTC) - timedelta(hours=10)).isoformat()
    items = {
        "item-1": json.dumps({"deadline": past, "description": "overdue item"}),
    }
    return MagicMock(return_value=items)


# ---------------------------------------------------------------------------
# check_calibration_exists tests
# ---------------------------------------------------------------------------


class TestCheckCalibrationExists:
    def test_no_redis_scan_returns_zero(self):
        result = check_calibration_exists(redis_scan=None)
        assert result.score == 0.0
        assert "unavailable" in result.message

    def test_no_keys_returns_high_score(self, mock_redis_scan_empty):
        result = check_calibration_exists(redis_scan=mock_redis_scan_empty)
        assert result.score == 0.7
        assert "No calibration keys found" in result.message

    def test_current_week_key_returns_zero(self, mock_redis_scan_current_week):
        result = check_calibration_exists(redis_scan=mock_redis_scan_current_week)
        assert result.score == 0.0
        assert "Current week calibration exists" in result.message

    def test_last_week_only_returns_moderate_score(self, mock_redis_scan_last_week):
        result = check_calibration_exists(redis_scan=mock_redis_scan_last_week)
        assert result.score == 0.35
        assert "Current week calibration missing" in result.message

    def test_redis_exception_returns_zero(self):
        failing_scan = MagicMock(side_effect=ConnectionError("Redis down"))
        result = check_calibration_exists(redis_scan=failing_scan)
        assert result.score == 0.0
        assert "Redis scan failed" in result.message

    def test_scan_called_with_correct_pattern(self, mock_redis_scan_current_week):
        check_calibration_exists(redis_scan=mock_redis_scan_current_week)
        mock_redis_scan_current_week.assert_called_once_with(CALIBRATION_KEY_PATTERN)


# ---------------------------------------------------------------------------
# check_self_assessment_score tests
# ---------------------------------------------------------------------------


class TestCheckSelfAssessmentScore:
    def test_no_redis_returns_zero(self):
        """When redis_get is explicitly None, returns unavailable message."""
        result = check_self_assessment_score(redis_get=lambda k: None)
        assert result.score == 0.15
        assert "No self-assessment score found" in result.message

    def test_no_score_returns_mild_warning(self, mock_redis_get_none):
        result = check_self_assessment_score(redis_get=mock_redis_get_none)
        assert result.score == 0.15
        assert "No self-assessment score found" in result.message

    def test_stable_score_returns_zero(self, mock_redis_get_stable):
        result = check_self_assessment_score(redis_get=mock_redis_get_stable)
        assert result.score == 0.0
        assert "stable" in result.message

    def test_dropped_score_returns_drift(self, mock_redis_get_dropped):
        result = check_self_assessment_score(redis_get=mock_redis_get_dropped)
        assert result.score > 0.0
        assert "dropped" in result.message
        assert result.details["drop"] == 0.25

    def test_redis_exception_returns_zero(self):
        failing_get = MagicMock(side_effect=ConnectionError("Redis down"))
        result = check_self_assessment_score(redis_get=failing_get)
        assert result.score == 0.0

    def test_invalid_json_returns_low_score(self):
        mock_get = MagicMock(return_value="not valid json {{{")
        result = check_self_assessment_score(redis_get=mock_get)
        assert result.score == 0.1
        assert "Could not parse" in result.message

    def test_get_called_with_correct_key(self, mock_redis_get_stable):
        check_self_assessment_score(redis_get=mock_redis_get_stable)
        mock_redis_get_stable.assert_called_once_with(SELF_ASSESSMENT_KEY)

    def test_custom_drop_threshold(self, mock_redis_get_dropped):
        result = check_self_assessment_score(
            redis_get=mock_redis_get_dropped,
            drop_threshold=0.30,
        )
        # Drop is 0.25, threshold is 0.30, so no excess
        assert result.score == 0.0


# ---------------------------------------------------------------------------
# check_deferred_items tests
# ---------------------------------------------------------------------------


class TestCheckDeferredItems:
    def test_no_redis_returns_zero(self):
        """When redis_hgetall is explicitly None, returns unavailable message."""
        result = check_deferred_items(redis_hgetall=lambda k: {})
        assert result.score == 0.0
        assert "No deferred items found" in result.message

    def test_no_items_returns_zero(self, mock_redis_hgetall_empty):
        result = check_deferred_items(redis_hgetall=mock_redis_hgetall_empty)
        assert result.score == 0.0
        assert "No deferred items" in result.message

    def test_safe_items_returns_zero(self, mock_redis_hgetall_safe):
        result = check_deferred_items(redis_hgetall=mock_redis_hgetall_safe)
        assert result.score == 0.0
        assert "within safe window" in result.message

    def test_approaching_deadline_returns_score(self, mock_redis_hgetall_approaching):
        result = check_deferred_items(redis_hgetall=mock_redis_hgetall_approaching)
        assert result.score == 0.1
        assert "approaching" in result.message

    def test_overdue_items_returns_higher_score(self, mock_redis_hgetall_overdue):
        result = check_deferred_items(redis_hgetall=mock_redis_hgetall_overdue)
        assert result.score == 0.2
        assert "overdue" in result.message

    def test_redis_exception_returns_zero(self):
        failing_hgetall = MagicMock(side_effect=ConnectionError("Redis down"))
        result = check_deferred_items(redis_hgetall=failing_hgetall)
        assert result.score == 0.0

    def test_hgetall_called_with_correct_key(self, mock_redis_hgetall_empty):
        check_deferred_items(redis_hgetall=mock_redis_hgetall_empty)
        mock_redis_hgetall_empty.assert_called_once_with(DEFERRED_ITEMS_KEY)

    def test_malformed_item_data_skipped(self):
        items = {
            "bad-1": "not json",
            "bad-2": json.dumps({"no_deadline": True}),
            "ok-1": json.dumps(
                {
                    "deadline": (datetime.now(UTC) - timedelta(hours=200)).isoformat(),
                }
            ),
        }
        mock_hgetall = MagicMock(return_value=items)
        result = check_deferred_items(redis_hgetall=mock_hgetall)
        # Only ok-1 should be counted as overdue
        assert result.score == 0.2
        assert result.details["overdue"] == 1


# ---------------------------------------------------------------------------
# check_all tests
# ---------------------------------------------------------------------------


class TestCheckAll:
    def test_all_healthy_returns_low_score(self):
        now = datetime.now(UTC)
        iso = now.isocalendar()
        week_str = f"{iso[0]}-W{iso[1]:02d}"
        cal_key = f"bmad:chiseai:metacog:calibration:agent:jarvis:weekly:{week_str}"

        mock_scan = MagicMock(return_value=[cal_key])
        mock_get = MagicMock(
            return_value=json.dumps(
                {
                    "overall_score": 0.9,
                    "previous_score": 0.88,
                }
            )
        )
        mock_hgetall = MagicMock(return_value={})

        report = check_all(
            redis_scan=mock_scan,
            redis_get=mock_get,
            redis_hgetall=mock_hgetall,
        )
        assert report.overall_score == 0.0
        assert not report.is_drift_detected
        assert len(report.checks) == 3

    def test_all_degraded_returns_high_score(self):
        mock_scan = MagicMock(return_value=[])  # No calibration
        mock_get = MagicMock(
            return_value=json.dumps(
                {
                    "overall_score": 0.4,
                    "previous_score": 0.9,
                }
            )
        )
        past = (datetime.now(UTC) - timedelta(hours=200)).isoformat()
        mock_hgetall = MagicMock(
            return_value={
                "item-1": json.dumps({"deadline": past}),
                "item-2": json.dumps({"deadline": past}),
            }
        )

        report = check_all(
            redis_scan=mock_scan,
            redis_get=mock_get,
            redis_hgetall=mock_hgetall,
        )
        assert report.overall_score > 0.0
        # calibration: 0.7, self-assess: up to 0.4, deferred: 0.4 => raw=1.5 / 1.8
        assert report.overall_score > 0.5

    def test_custom_threshold(self):
        mock_scan = MagicMock(return_value=[])
        mock_get = MagicMock(return_value=None)
        mock_hgetall = MagicMock(return_value={})

        report = check_all(
            threshold=0.1,
            redis_scan=mock_scan,
            redis_get=mock_get,
            redis_hgetall=mock_hgetall,
        )
        # calibration missing (0.7) + no self-assess (0.15) = 0.85/1.8 = 0.47 > 0.1
        assert report.is_drift_detected
        assert report.threshold == 0.1

    def test_report_to_dict(self):
        report = DriftReport(
            checks=[DriftCheckResult(name="test", score=0.5, message="test msg")],
            overall_score=0.5,
            threshold=0.85,
        )
        d = report.to_dict()
        assert d["overall_score"] == 0.5
        assert d["drift_detected"] is False
        assert len(d["checks"]) == 1
        assert d["checks"][0]["name"] == "test"


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_dry_run_returns_zero(self, capsys):
        rc = main(["--dry-run"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "dry-run" in output

    def test_json_output(self, capsys):
        rc = main(["--dry-run", "--json"])
        assert rc == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "overall_score" in data
        assert "checks" in data

    def test_verbose_mode(self, capsys):
        rc = main(["--dry-run", "--verbose"])
        assert rc == 0

    def test_default_threshold(self):
        """With no Redis, all checks return 0.0, so no drift."""
        rc = main([])
        assert rc == 0

    def test_custom_threshold_cli(self):
        rc = main(["--threshold", "0.0", "--dry-run"])
        assert rc == 0  # dry-run always returns 0

    def test_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
