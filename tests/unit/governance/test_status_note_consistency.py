#!/usr/bin/env python3
"""Tests for status_note_consistency check in status_guard.py."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from scripts.governance.status_guard import (
    check_status_note_consistency,
)


class TestDeferredNote:
    def test_deferred_note_with_completed_item_raises_error(self):
        data = {
            "metadata": {"status_notes": ["ST-001 deferred to post-Day-3-checkpoint"]},
            "backlog": [{"id": "ST-001", "status": "completed"}],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1
        assert result.errors[0]["story_id"] == "ST-001"
        assert result.errors[0]["severity"] == "error"

    def test_deferred_note_with_in_progress_item_raises_error(self):
        data = {
            "metadata": {"status_notes": ["ST-001 deferred to post-Day-3-checkpoint"]},
            "in_progress": [{"id": "ST-001", "status": "in_progress"}],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1
        assert result.errors[0]["story_id"] == "ST-001"
        assert result.errors[0]["severity"] == "error"

    def test_deferred_note_with_backlog_item_ok(self):
        data = {
            "metadata": {"status_notes": ["ST-001 deferred to backlog"]},
            "backlog": [{"id": "ST-001", "status": "deferred"}],
        }
        result = check_status_note_consistency(data)
        assert result.passed


class TestBlockedNote:
    def test_blocked_note_with_completed_item_raises_error(self):
        data = {
            "metadata": {"status_notes": ["ST-001 blocked on upstream"]},
            "backlog": [{"id": "ST-001", "status": "completed"}],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1

    def test_blocked_note_with_in_progress_item_ok(self):
        data = {
            "metadata": {"status_notes": ["ST-001 blocked on upstream"]},
            "in_progress": [{"id": "ST-001", "status": "in_progress"}],
        }
        result = check_status_note_consistency(data)
        assert result.passed


class TestInProgressNote:
    def test_in_progress_note_with_backlog_item_raises_error(self):
        data = {
            "metadata": {"status_notes": ["ST-001 in progress"]},
            "backlog": [{"id": "ST-001", "status": "backlog"}],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1

    def test_in_progress_note_with_archived_item_raises_error(self):
        data = {
            "metadata": {"status_notes": ["ST-001 in progress"]},
            "backlog": [{"id": "ST-001", "status": "archived"}],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1

    def test_in_progress_note_with_completed_item_raises_error(self):
        data = {
            "metadata": {"status_notes": ["ST-001 in progress"]},
            "in_progress": [{"id": "ST-001", "status": "completed"}],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1


class TestCompletedNote:
    def test_completed_note_with_backlog_item_raises_error(self):
        data = {
            "metadata": {"status_notes": ["ST-001 completed"]},
            "backlog": [{"id": "ST-001", "status": "backlog"}],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1

    def test_completed_note_with_in_progress_item_raises_error(self):
        data = {
            "metadata": {"status_notes": ["ST-001 completed"]},
            "in_progress": [{"id": "ST-001", "status": "in_progress"}],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1


class TestOperationalNote:
    def test_operational_note_with_archived_item_raises_error(self):
        data = {
            "metadata": {"status_notes": ["ST-001 operational"]},
            "backlog": [{"id": "ST-001", "status": "archived"}],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1


class TestMultiIdNote:
    def test_multi_id_note_checks_each_id(self):
        data = {
            "metadata": {"status_notes": ["ST-001 and ST-002 deferred to backlog"]},
            "backlog": [
                {"id": "ST-001", "status": "completed"},  # contradiction
                {"id": "ST-002", "status": "deferred"},  # consistent
            ],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1
        assert result.errors[0]["story_id"] == "ST-001"


class TestUnknownStoryId:
    def test_unknown_story_id_warns(self):
        data = {
            "metadata": {"status_notes": ["ST-FUTURE-001 deferred to backlog"]},
            "backlog": [],
        }
        result = check_status_note_consistency(data)
        # Should pass (no errors) but warn about unknown ID
        assert result.passed  # no errors
        assert len(result.warnings) >= 1


class TestNoContradiction:
    def test_no_story_id_in_note_no_check(self):
        data = {
            "metadata": {"status_notes": ["LLM Providers: OPERATIONAL"]},
            "backlog": [],
        }
        result = check_status_note_consistency(data)
        assert result.passed
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_infrastructure_note_ignored(self):
        data = {
            "metadata": {
                "status_notes": ["Grafana: r2a-canary-health dashboard deployed"]
            },
            "backlog": [],
        }
        result = check_status_note_consistency(data)
        assert result.passed


class TestActualContradiction:
    """Test the actual ST-WIRE-ERROR-RATE-TRACKER contradiction."""

    def test_st_wire_error_rate_tracker_deferred_vs_completed(self):
        data = {
            "metadata": {
                "status_notes": [
                    "ST-WIRE-ERROR-RATE-TRACKER deferred to post-Day-3-checkpoint (2026-04-11) — P2, 3SP"
                ]
            },
            "backlog": [
                {
                    "id": "ST-WIRE-ERROR-RATE-TRACKER",
                    "status": "completed",
                    "priority": "P2",
                }
            ],
        }
        result = check_status_note_consistency(data)
        assert not result.passed
        assert len(result.errors) == 1
        assert result.errors[0]["story_id"] == "ST-WIRE-ERROR-RATE-TRACKER"
