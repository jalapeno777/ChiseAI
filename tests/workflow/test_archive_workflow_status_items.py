from datetime import UTC, datetime

from scripts.workflow.archive_workflow_status_items import (
    _build_stub,
    _has_completion_evidence,
    _parse_date,
    _should_archive,
)


def test_parse_date_supports_iso_and_date_only():
    dt1 = _parse_date("2026-03-25")
    dt2 = _parse_date("2026-03-25T12:30:00Z")

    assert dt1 is not None
    assert dt2 is not None
    assert dt1.tzinfo == UTC
    assert dt2.tzinfo == UTC
    assert dt1.date().isoformat() == "2026-03-25"
    assert dt2.date().isoformat() == "2026-03-25"


def test_should_archive_story_by_age():
    now = datetime(2026, 4, 6, tzinfo=UTC)
    story = {
        "id": "ST-TEST-001",
        "status": "merged",
        "completion_date": "2026-03-25",
    }
    should, reason, age_days, _ = _should_archive(
        item=story,
        item_type="story",
        retention_days=7,
        now=now,
        story_dates={},
    )
    assert should is True
    assert reason == "age"
    assert age_days == 12


def test_completion_evidence_gate_detects_pr_or_merge():
    with_pr = {"pr_number": 123}
    with_merge = {"merge_commit": "abcdef1"}
    with_none = {"pr_number": "N/A", "merge_commit": ""}

    assert _has_completion_evidence(with_pr) is True
    assert _has_completion_evidence(with_merge) is True
    assert _has_completion_evidence(with_none) is False


def test_build_stub_story_and_epic_status_archived():
    story = {
        "id": "ST-TEST-002",
        "title": "Story Title",
        "status": "merged",
        "epic_id": "EP-TEST-001",
        "completion_date": "2026-03-25",
        "pr_number": 99,
    }
    epic = {
        "id": "EP-TEST-001",
        "name": "Epic Name",
        "status": "completed",
        "story_count": 5,
    }

    story_stub = _build_stub(story, "story", "ARCH-1", _parse_date("2026-03-25"))
    epic_stub = _build_stub(epic, "epic", "ARCH-2", _parse_date("2026-03-20"))

    assert story_stub["status"] == "archived"
    assert story_stub["archive_ref"] == "ARCH-1"
    assert story_stub["id"] == "ST-TEST-002"

    assert epic_stub["status"] == "archived"
    assert epic_stub["archive_ref"] == "ARCH-2"
    assert epic_stub["id"] == "EP-TEST-001"
    assert epic_stub["name"] == "Epic Name"
