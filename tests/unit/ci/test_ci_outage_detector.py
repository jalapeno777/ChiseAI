#!/usr/bin/env python3
"""Tests for ci_outage_detector."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path
from unittest.mock import patch

import pytest

# Import from the script under test
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "ci"))
from ci_outage_detector import (
    FAILED_STATUSES,
    _is_failed_status,
    _consecutive_failures_in_window,
    _normalize_pipeline,
)


class TestIsFailedStatus:
    def test_failure_statuses(self):
        for status in FAILED_STATUSES:
            assert _is_failed_status(status) is True

    def test_success_statuses(self):
        for status in ("success", "passing", "passed", "complete", "skipped"):
            assert _is_failed_status(status) is False

    def test_running_pending(self):
        assert _is_failed_status("running") is False
        assert _is_failed_status("pending") is False

    def test_unknown_empty(self):
        assert _is_failed_status("") is False
        assert _is_failed_status("unknown") is False


class TestConsecutiveFailuresInWindow:
    def _make_pipeline(self, number: int, status: str, started: int) -> dict:
        return {"number": number, "status": status, "started_at": started}

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp())

    def test_alert_when_more_than_three_consecutive_failures(self):
        now = self._now_ts()
        pipelines = [
            self._make_pipeline(1, "failure", now - 300),
            self._make_pipeline(2, "failure", now - 600),
            self._make_pipeline(3, "failure", now - 900),
            self._make_pipeline(4, "failure", now - 1200),
        ]
        alert, count, streak = _consecutive_failures_in_window(
            pipelines, window_hours=1, threshold=3
        )
        assert alert is True
        assert count == 4
        assert len(streak) == 4

    def test_no_alert_when_only_two_consecutive_failures(self):
        now = self._now_ts()
        pipelines = [
            self._make_pipeline(1, "failure", now - 300),
            self._make_pipeline(2, "failure", now - 600),
            self._make_pipeline(3, "success", now - 900),
        ]
        alert, count, streak = _consecutive_failures_in_window(
            pipelines, window_hours=1, threshold=3
        )
        assert alert is False
        assert count == 2
        assert len(streak) == 2

    def test_one_hour_window_boundary(self):
        """Only pipelines inside the time window are considered."""
        now = self._now_ts()
        one_hour_ago = now - 3600
        pipelines = [
            self._make_pipeline(1, "failure", one_hour_ago + 1),  # Just inside window
            self._make_pipeline(
                2, "failure", one_hour_ago - 1
            ),  # Just outside window - skipped
            self._make_pipeline(
                3, "failure", one_hour_ago - 100
            ),  # Well outside window - skipped
        ]
        # Only 1 failure inside window, not > threshold (3), so alert=False
        alert, count, streak = _consecutive_failures_in_window(
            pipelines, window_hours=1, threshold=3
        )
        assert alert is False
        assert count == 1
        assert len(streak) == 1

    def test_four_failures_in_window_triggers_alert(self):
        """Four failures within window should trigger alert (>3 threshold)."""
        now = self._now_ts()
        # All 4 inside the 1-hour window
        pipelines = [
            self._make_pipeline(1, "failure", now - 1200),
            self._make_pipeline(2, "failure", now - 900),
            self._make_pipeline(3, "failure", now - 600),
            self._make_pipeline(4, "failure", now - 300),
        ]
        # 4 failures inside window, 4 > 3 threshold, so alert=True
        alert, count, streak = _consecutive_failures_in_window(
            pipelines, window_hours=1, threshold=3
        )
        assert alert is True
        assert count == 4
        assert len(streak) == 4

    def test_success_breaks_consecutive_streak(self):
        now = self._now_ts()
        pipelines = [
            self._make_pipeline(1, "failure", now - 300),
            self._make_pipeline(2, "failure", now - 600),
            self._make_pipeline(3, "success", now - 900),
            self._make_pipeline(4, "failure", now - 1200),
            self._make_pipeline(5, "failure", now - 1500),
        ]
        alert, count, streak = _consecutive_failures_in_window(
            pipelines, window_hours=1, threshold=3
        )
        assert alert is False
        assert count == 2
        assert len(streak) == 2

    def test_empty_pipelines_list(self):
        alert, count, streak = _consecutive_failures_in_window(
            [], window_hours=1, threshold=3
        )
        assert alert is False
        assert count == 0
        assert len(streak) == 0

    def test_non_failed_in_middle_stops_streak(self):
        now = self._now_ts()
        pipelines = [
            self._make_pipeline(1, "failure", now - 300),
            self._make_pipeline(2, "failure", now - 600),
            self._make_pipeline(3, "pending", now - 900),  # Not a failed status
            self._make_pipeline(4, "failure", now - 1200),
            self._make_pipeline(5, "failure", now - 1500),
        ]
        alert, count, streak = _consecutive_failures_in_window(
            pipelines, window_hours=1, threshold=3
        )
        assert alert is False
        assert count == 2


class TestNormalizePipeline:
    def test_normalizes_status(self):
        raw = {"number": 42, "status": "FAILURE", "started": 123456}
        p = _normalize_pipeline(raw)
        assert p["number"] == 42
        assert p["status"] == "failure"
        assert p["started_at"] == 123456

    def test_handles_missing_fields(self):
        raw = {"number": 1}
        p = _normalize_pipeline(raw)
        assert p["number"] == 1
        assert p["status"] == "unknown"
        assert p["started_at"] is None
