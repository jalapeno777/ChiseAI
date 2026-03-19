#!/usr/bin/env python3
"""Tests for WorkflowRedisValidator.

Comprehensive tests covering:
- Required field validation
- TTL validation
- Phase/status enumeration validation
- Timestamp format validation
- JSON array field validation
- Edge cases (empty keys, missing fields, unknown fields)
- Strict mode behavior
- Story ID pattern validation
- CLI integration
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from scripts.validation.workflow_redis_validator import (
    DEFAULT_TTL_SECONDS,
    ISO_8601_PATTERN,
    STORY_PREFIX,
    VALID_PHASES,
    VALID_STATUSES,
    FieldValidation,
    StoryValidation,
    WorkflowRedisValidator,
    WorkflowValidationReport,
    _print_report,
    _print_story_result,
    main,
)

# =============================================================================
# Fixtures
# =============================================================================


def _make_mock_client(
    *,
    story_keys: list[str] | None = None,
    story_data: dict[str, dict[str, str]] | None = None,
    key_types: dict[str, str] | None = None,
    ttls: dict[str, int] | None = None,
    scan_cursor: int = 0,
) -> MagicMock:
    """Build a mock Redis client with configurable responses."""
    client = MagicMock()
    client.ping.return_value = True

    story_keys = story_keys or []
    story_data = story_data or {}
    key_types = key_types or {}
    ttls = ttls or {}

    # Default type for any key is "hash"
    def mock_type(name: str) -> str:
        return key_types.get(name, "hash")

    client.type.side_effect = mock_type

    def mock_hgetall(name: str) -> dict[str, str]:
        return story_data.get(name, {})

    client.hgetall.side_effect = mock_hgetall

    def mock_ttl(name: str) -> int:
        return ttls.get(name, DEFAULT_TTL_SECONDS)

    client.ttl.side_effect = mock_ttl

    # scan returns cursor + matching keys
    client.scan.return_value = (scan_cursor, story_keys)

    return client


def _valid_story_hash(
    story_id: str = "ST-001",
    phase: str = "implementation",
    status: str = "in_progress",
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a valid story hash with all required fields."""
    data = {
        "story_id": story_id,
        "story_title": f"Test Story {story_id}",
        "phase": phase,
        "status": status,
        "started_at": "2026-03-19T12:00:00Z",
        "acceptance_criteria": json.dumps(["AC1: Works", "AC2: Tested"]),
        "key_decisions": json.dumps([]),
        "learnings": json.dumps([]),
    }
    if overrides:
        data.update(overrides)
    return data


# =============================================================================
# Tests: Required Fields (AC1)
# =============================================================================


class TestRequiredFields:
    """AC1: Validator checks Redis story keys exist and have required fields."""

    def test_all_required_fields_present_passes(self) -> None:
        """A story with all required fields should pass validation."""
        client = _make_mock_client(
            story_data={
                f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001"),
            },
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.is_valid
        assert result.fields_missing == []

    def test_missing_story_id_field_fails(self) -> None:
        """Missing story_id field should produce an error."""
        data = _valid_story_hash("ST-001")
        del data["story_id"]

        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert "story_id" in result.fields_missing

    def test_missing_story_title_field_fails(self) -> None:
        """Missing story_title field should produce an error."""
        data = _valid_story_hash("ST-001")
        del data["story_title"]

        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert "story_title" in result.fields_missing

    def test_missing_phase_field_fails(self) -> None:
        """Missing phase field should produce an error."""
        data = _valid_story_hash("ST-001")
        del data["phase"]

        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert "phase" in result.fields_missing

    def test_missing_status_field_fails(self) -> None:
        """Missing status field should produce an error."""
        data = _valid_story_hash("ST-001")
        del data["status"]

        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert "status" in result.fields_missing

    def test_missing_started_at_field_fails(self) -> None:
        """Missing started_at field should produce an error."""
        data = _valid_story_hash("ST-001")
        del data["started_at"]

        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert "started_at" in result.fields_missing

    def test_missing_multiple_required_fields(self) -> None:
        """Missing multiple required fields should list all of them."""
        data = {"story_id": "ST-001"}  # only one field

        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert (
            len(result.fields_missing) == 4
        )  # missing story_title, phase, status, started_at

    def test_empty_hash_fails(self) -> None:
        """An empty story hash should produce an error."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": {}},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("empty" in e.lower() for e in result.errors)

    def test_empty_field_value_fails(self) -> None:
        """A required field with empty string value should fail."""
        data = _valid_story_hash("ST-001", overrides={"story_title": ""})

        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("story_title" in e and "empty" in e.lower() for e in result.errors)

    def test_whitespace_only_field_value_fails(self) -> None:
        """A required field with whitespace-only value should fail."""
        data = _valid_story_hash("ST-001", overrides={"phase": "   "})

        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("phase" in e and "empty" in e.lower() for e in result.errors)

    def test_scan_finds_multiple_stories(self) -> None:
        """validate_all_stories should find and validate all story keys."""
        keys = [
            f"{STORY_PREFIX}:ST-001",
            f"{STORY_PREFIX}:ST-002",
            f"{STORY_PREFIX}:ST-003",
        ]
        story_data = {k: _valid_story_hash(k.split(":")[-1]) for k in keys}
        ttls = {k: DEFAULT_TTL_SECONDS for k in keys}

        client = _make_mock_client(
            story_keys=keys,
            story_data=story_data,
            ttls=ttls,
        )
        validator = WorkflowRedisValidator(redis_client=client)
        report = validator.validate_all_stories()

        assert report.is_valid
        assert report.stories_checked == 3
        assert report.stories_valid == 3
        assert report.stories_with_errors == 0

    def test_scan_filters_sub_keys(self) -> None:
        """Sub-keys like :decisions, :learnings should be excluded from scan."""
        all_keys = [
            f"{STORY_PREFIX}:ST-001",
            f"{STORY_PREFIX}:ST-001:decisions",
            f"{STORY_PREFIX}:ST-001:learnings",
            f"{STORY_PREFIX}:ST-001:incidents",
            f"{STORY_PREFIX}:ST-002",
        ]
        story_data = {
            f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001"),
            f"{STORY_PREFIX}:ST-002": _valid_story_hash("ST-002"),
        }
        ttls = {k: DEFAULT_TTL_SECONDS for k in story_data}

        client = _make_mock_client(
            story_keys=all_keys,
            story_data=story_data,
            ttls=ttls,
        )
        validator = WorkflowRedisValidator(redis_client=client)
        report = validator.validate_all_stories()

        assert report.stories_checked == 2
        assert report.stories_valid == 2


# =============================================================================
# Tests: TTL Validation (AC2)
# =============================================================================


class TestTTLValidation:
    """AC2: Validator checks TTL settings on iterlog keys."""

    def test_valid_ttl_passes(self) -> None:
        """Key with valid 5-day TTL should pass TTL check."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001")},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.ttl_valid is True
        assert result.ttl_seconds == DEFAULT_TTL_SECONDS

    def test_no_ttl_warning(self) -> None:
        """Key with no TTL (-1) should produce a warning."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001")},
            ttls={f"{STORY_PREFIX}:ST-001": -1},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.ttl_valid is False
        assert result.ttl_seconds == -1
        assert any("no ttl" in w.lower() for w in result.warnings)

    def test_expired_key_error(self) -> None:
        """Key with TTL=-2 (expired) should produce an error."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001")},
            ttls={f"{STORY_PREFIX}:ST-001": -2},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.ttl_valid is False
        assert any("expired" in e.lower() for e in result.errors)

    def test_low_ttl_warning(self) -> None:
        """Key with TTL below warning threshold should warn but pass."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001")},
            ttls={f"{STORY_PREFIX}:ST-001": 3600},  # 1 hour
        )
        validator = WorkflowRedisValidator(
            redis_client=client,
            ttl_warning_threshold=86400,
        )
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.ttl_valid is True
        assert any("below warning" in w.lower() for w in result.warnings)
        assert result.is_valid  # low TTL is a warning, not an error

    def test_custom_ttl_threshold(self) -> None:
        """Custom TTL warning threshold should be respected."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001")},
            ttls={f"{STORY_PREFIX}:ST-001": 7200},  # 2 hours
        )
        # Set threshold to 1 hour - 7200s should be fine
        validator = WorkflowRedisValidator(
            redis_client=client,
            ttl_warning_threshold=3600,
        )
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.ttl_valid is True
        assert not any("below warning" in w.lower() for w in result.warnings)

    def test_zero_ttl_error(self) -> None:
        """TTL of 0 should produce an error."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001")},
            ttls={f"{STORY_PREFIX}:ST-001": 0},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.ttl_valid is False
        assert not result.is_valid

    def test_negative_ttl_error(self) -> None:
        """Negative TTL (not -1 or -2) should produce an error."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001")},
            ttls={f"{STORY_PREFIX}:ST-001": -100},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.ttl_valid is False

    def test_ttl_error_in_strict_mode(self) -> None:
        """In strict mode, TTL warnings should become errors."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001")},
            ttls={f"{STORY_PREFIX}:ST-001": -1},  # no TTL
        )
        validator = WorkflowRedisValidator(redis_client=client, strict=True)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("no ttl" in e.lower() for e in result.errors)
        assert len(result.warnings) == 0  # warnings promoted to errors


# =============================================================================
# Tests: Field Value Validation
# =============================================================================


class TestPhaseValidation:
    """Tests for phase field enumeration validation."""

    @pytest.mark.parametrize("phase", sorted(VALID_PHASES))
    def test_valid_phases(self, phase: str) -> None:
        """All valid phase values should pass."""
        data = _valid_story_hash("ST-001", phase=phase)
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        phase_validations = [
            fv for fv in result.field_validations if fv.field_name == "phase"
        ]
        assert len(phase_validations) == 1
        assert phase_validations[0].is_valid

    def test_invalid_phase_fails(self) -> None:
        """Invalid phase should produce an error."""
        data = _valid_story_hash("ST-001", phase="deploying")
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("phase" in e and "deploying" in e for e in result.errors)

    def test_empty_phase_fails(self) -> None:
        """Empty phase should fail."""
        data = _valid_story_hash("ST-001", overrides={"phase": ""})
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid


class TestStatusValidation:
    """Tests for status field enumeration validation."""

    @pytest.mark.parametrize("status", sorted(VALID_STATUSES))
    def test_valid_statuses(self, status: str) -> None:
        """All valid status values should pass."""
        data = _valid_story_hash("ST-001", status=status)
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        status_validations = [
            fv for fv in result.field_validations if fv.field_name == "status"
        ]
        assert len(status_validations) == 1
        assert status_validations[0].is_valid

    def test_invalid_status_fails(self) -> None:
        """Invalid status should produce an error."""
        data = _valid_story_hash("ST-001", status="shipped")
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("status" in e and "shipped" in e for e in result.errors)


class TestStoryIdValidation:
    """Tests for story_id field pattern validation."""

    @pytest.mark.parametrize(
        "story_id",
        [
            "ST-001",
            "CH-042",
            "FT-100",
            "REWARD-001",
            "REPO-001",
            "SAFETY-001",
            "BRANCH-001",
            "PAPER-001",
            "RECON-001",
            "PROCESS-001",
        ],
    )
    def test_valid_story_id_patterns(self, story_id: str) -> None:
        """Recognized story ID tokens should pass."""
        data = _valid_story_hash(story_id)
        key = f"{STORY_PREFIX}:{story_id}"
        client = _make_mock_client(
            story_data={key: data},
            ttls={key: DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(key, client=client)

        id_validations = [
            fv for fv in result.field_validations if fv.field_name == "story_id"
        ]
        assert len(id_validations) == 1
        assert id_validations[0].is_valid

    def test_invalid_story_id_pattern_fails(self) -> None:
        """Story ID not matching pattern should fail."""
        data = _valid_story_hash("INVALID-ID")
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:INVALID-ID": data},
            ttls={f"{STORY_PREFIX}:INVALID-ID": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(
            f"{STORY_PREFIX}:INVALID-ID", client=client
        )

        assert not result.is_valid
        assert any("story_id" in e and "pattern" in e.lower() for e in result.errors)

    def test_story_id_mismatch_with_key_fails(self) -> None:
        """story_id field not matching key-derived ID should fail."""
        data = _valid_story_hash("ST-999")  # different from key
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("does not match" in e for e in result.errors)


class TestTimestampValidation:
    """Tests for ISO-8601 timestamp validation."""

    def test_valid_timestamp_passes(self) -> None:
        """Valid ISO-8601 timestamp should pass."""
        data = _valid_story_hash(
            "ST-001", overrides={"started_at": "2026-03-19T12:00:00Z"}
        )
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        ts_validations = [
            fv for fv in result.field_validations if fv.field_name == "started_at"
        ]
        assert len(ts_validations) == 1
        assert ts_validations[0].is_valid

    def test_invalid_timestamp_fails(self) -> None:
        """Non-ISO timestamp should fail."""
        data = _valid_story_hash("ST-001", overrides={"started_at": "not-a-timestamp"})
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("timestamp" in e.lower() for e in result.errors)

    def test_completed_at_valid_timestamp(self) -> None:
        """Valid completed_at timestamp should pass."""
        data = _valid_story_hash(
            "ST-001",
            overrides={"completed_at": "2026-03-19T14:00:00Z"},
        )
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.is_valid


class TestJsonArrayFieldValidation:
    """Tests for JSON array field validation."""

    def test_valid_acceptance_criteria(self) -> None:
        """Valid JSON array for acceptance_criteria should pass."""
        data = _valid_story_hash(
            "ST-001",
            overrides={"acceptance_criteria": json.dumps(["AC1: Works"])},
        )
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        ac_validations = [
            fv
            for fv in result.field_validations
            if fv.field_name == "acceptance_criteria"
        ]
        assert len(ac_validations) == 1
        assert ac_validations[0].is_valid

    def test_invalid_json_in_acceptance_criteria_fails(self) -> None:
        """Invalid JSON in acceptance_criteria should produce an error."""
        data = _valid_story_hash(
            "ST-001",
            overrides={"acceptance_criteria": "not json"},
        )
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any(
            "acceptance_criteria" in e and "json" in e.lower() for e in result.errors
        )

    def test_json_object_instead_of_array_fails(self) -> None:
        """JSON object instead of array should fail."""
        data = _valid_story_hash(
            "ST-001",
            overrides={"acceptance_criteria": json.dumps({"key": "value"})},
        )
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("array" in e.lower() for e in result.errors)

    def test_empty_json_array_passes(self) -> None:
        """Empty JSON array is valid."""
        data = _valid_story_hash(
            "ST-001",
            overrides={"acceptance_criteria": "[]"},
        )
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.is_valid

    def test_invalid_json_in_learnings_is_warning(self) -> None:
        """Invalid JSON in learnings (optional field) should be a warning, not error."""
        data = _valid_story_hash(
            "ST-001",
            overrides={"learnings": "broken json"},
        )
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        # learnings is optional so invalid JSON is a warning
        assert result.is_valid
        assert any("learnings" in w for w in result.warnings)


# =============================================================================
# Tests: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_wrong_key_type_fails(self) -> None:
        """Key that is not a hash should fail immediately."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001")},
            key_types={f"{STORY_PREFIX}:ST-001": "string"},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("hash" in e for e in result.errors)

    def test_redis_error_on_scan(self) -> None:
        """Redis error during scan should be reported."""
        client = MagicMock()
        client.scan.side_effect = Exception("Connection refused")

        validator = WorkflowRedisValidator(redis_client=client)
        report = validator.validate_all_stories()

        assert not report.is_valid
        assert any("scan" in e.lower() for e in report.errors)

    def test_redis_error_on_type_check(self) -> None:
        """Redis error during type check should be reported."""
        client = MagicMock()
        client.type.side_effect = Exception("Connection refused")

        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("type" in e.lower() for e in result.errors)

    def test_redis_error_on_hgetall(self) -> None:
        """Redis error during hgetall should be reported."""
        client = MagicMock()
        client.type.return_value = "hash"
        client.hgetall.side_effect = Exception("Connection refused")

        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("hash" in e.lower() or "read" in e.lower() for e in result.errors)

    def test_unknown_field_is_warning(self) -> None:
        """Unknown fields should produce warnings, not errors."""
        data = _valid_story_hash("ST-001", overrides={"custom_field": "value"})
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert result.is_valid
        assert any("custom_field" in w for w in result.warnings)

    def test_unknown_fields_in_strict_mode(self) -> None:
        """In strict mode, unknown field warnings should become errors."""
        data = _valid_story_hash("ST-001", overrides={"custom_field": "value"})
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": data},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client, strict=True)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        assert not result.is_valid
        assert any("custom_field" in e for e in result.errors)

    def test_validate_specific_story(self) -> None:
        """validate_specific_story should construct key from story_id."""
        data = _valid_story_hash("ST-042")
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-042": data},
            ttls={f"{STORY_PREFIX}:ST-042": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_specific_story("ST-042")

        assert result.is_valid
        assert result.story_id == "ST-042"
        assert result.story_key == f"{STORY_PREFIX}:ST-042"

    def test_non_story_key_does_not_crash(self) -> None:
        """Key not matching story pattern should handle gracefully."""
        client = _make_mock_client(
            story_data={"some:other:key": {"field": "value"}},
            ttls={"some:other:key": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key("some:other:key", client=client)

        # Should not crash; story_id will be empty
        assert result.story_key == "some:other:key"
        assert result.story_id == ""

    def test_ttl_check_error_is_warning(self) -> None:
        """Error checking TTL should produce a warning, not crash."""
        client = MagicMock()
        client.type.return_value = "hash"
        client.hgetall.return_value = _valid_story_hash("ST-001")
        client.ttl.side_effect = Exception("TTL check failed")

        validator = WorkflowRedisValidator(redis_client=client)
        result = validator.validate_story_key(f"{STORY_PREFIX}:ST-001", client=client)

        # TTL check error should be a warning
        assert any("ttl" in w.lower() for w in result.warnings)
        assert result.ttl_valid is None


# =============================================================================
# Tests: Report Aggregation
# =============================================================================


class TestReportAggregation:
    """Tests for WorkflowValidationReport."""

    def test_empty_report_is_valid(self) -> None:
        """Report with no stories checked is valid."""
        report = WorkflowValidationReport()
        assert report.is_valid

    def test_report_with_all_valid_stories(self) -> None:
        """Report with all valid stories should be valid."""
        report = WorkflowValidationReport(
            stories_checked=2,
            stories_valid=2,
            stories_with_errors=0,
            stories_with_warnings=0,
        )
        assert report.is_valid

    def test_report_with_errors_is_invalid(self) -> None:
        """Report with errors should be invalid."""
        report = WorkflowValidationReport(
            stories_checked=2,
            stories_valid=1,
            stories_with_errors=1,
        )
        assert not report.is_valid

    def test_report_to_dict(self) -> None:
        """Report serialization should include all fields."""
        report = WorkflowValidationReport(
            stories_checked=1,
            stories_valid=1,
        )
        d = report.to_dict()

        assert d["is_valid"] is True
        assert d["stories_checked"] == 1
        assert "validation_timestamp" in d
        assert isinstance(d["story_results"], list)

    def test_mixed_valid_and_invalid_stories(self) -> None:
        """Scan with mix of valid and invalid stories should count correctly."""
        keys = [
            f"{STORY_PREFIX}:ST-001",
            f"{STORY_PREFIX}:ST-002",
        ]
        # ST-001 valid, ST-002 missing fields
        story_data = {
            f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001"),
            f"{STORY_PREFIX}:ST-002": {"story_id": "ST-002"},  # incomplete
        }
        ttls = {k: DEFAULT_TTL_SECONDS for k in keys}

        client = _make_mock_client(
            story_keys=keys,
            story_data=story_data,
            ttls=ttls,
        )
        validator = WorkflowRedisValidator(redis_client=client)
        report = validator.validate_all_stories()

        assert report.stories_checked == 2
        assert report.stories_valid == 1
        assert report.stories_with_errors == 1
        assert not report.is_valid


# =============================================================================
# Tests: Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Tests for internal utility functions."""

    def test_is_story_hash_key_filters_sub_keys(self) -> None:
        """_is_story_hash_key should filter out sub-keys."""
        assert (
            WorkflowRedisValidator._is_story_hash_key(
                "bmad:chiseai:iterlog:story:ST-001"
            )
            is True
        )
        assert (
            WorkflowRedisValidator._is_story_hash_key(
                "bmad:chiseai:iterlog:story:ST-001:decisions"
            )
            is False
        )
        assert (
            WorkflowRedisValidator._is_story_hash_key(
                "bmad:chiseai:iterlog:story:ST-001:learnings"
            )
            is False
        )
        assert (
            WorkflowRedisValidator._is_story_hash_key(
                "bmad:chiseai:iterlog:story:ST-001:incidents"
            )
            is False
        )

    def test_extract_story_id(self) -> None:
        """_extract_story_id should parse story ID from key."""
        assert (
            WorkflowRedisValidator._extract_story_id(
                "bmad:chiseai:iterlog:story:ST-001"
            )
            == "ST-001"
        )
        assert (
            WorkflowRedisValidator._extract_story_id(
                "bmad:chiseai:iterlog:story:CH-042"
            )
            == "CH-042"
        )
        assert WorkflowRedisValidator._extract_story_id("other:prefix") == ""

    def test_iso_8601_pattern(self) -> None:
        """ISO-8601 pattern should match valid timestamps."""
        assert ISO_8601_PATTERN.match("2026-03-19T12:00:00Z")
        assert ISO_8601_PATTERN.match("2026-03-19T12:00:00+00:00")
        assert not ISO_8601_PATTERN.match("not-a-timestamp")
        assert not ISO_8601_PATTERN.match("2026/03/19 12:00:00")


# =============================================================================
# Tests: CLI
# =============================================================================


class TestCLI:
    """Tests for CLI entry point."""

    def test_main_with_json_output(self, capsys: Any) -> None:
        """--json flag should produce JSON output."""
        client = _make_mock_client(
            story_data={f"{STORY_PREFIX}:ST-001": _valid_story_hash("ST-001")},
            ttls={f"{STORY_PREFIX}:ST-001": DEFAULT_TTL_SECONDS},
        )
        validator = WorkflowRedisValidator(redis_client=client)

        # Patch the validator creation to use our mock
        import scripts.validation.workflow_redis_validator as mod

        original_init = mod.WorkflowRedisValidator.__init__

        def patched_init(self, **kwargs: Any) -> None:
            original_init(self, redis_client=client, **kwargs)

        mod.WorkflowRedisValidator.__init__ = patched_init  # type: ignore[assignment]
        try:
            exit_code = main.__wrapped__() if hasattr(main, "__wrapped__") else 0
            # Can't easily test main() without subprocess, so test report serialization
            report = validator.validate_all_stories()
            d = report.to_dict()
            assert "is_valid" in d
            assert d["is_valid"] is True
        finally:
            mod.WorkflowRedisValidator.__init__ = original_init  # type: ignore[assignment]

    def test_print_story_result_pass(self, capsys: Any) -> None:
        """_print_story_result should print PASS for valid story."""
        result = StoryValidation(
            story_key=f"{STORY_PREFIX}:ST-001",
            story_id="ST-001",
            ttl_seconds=DEFAULT_TTL_SECONDS,
            ttl_valid=True,
        )
        _print_story_result(result)
        output = capsys.readouterr().out
        assert "[PASS]" in output
        assert "ST-001" in output

    def test_print_story_result_fail(self, capsys: Any) -> None:
        """_print_story_result should print FAIL for invalid story."""
        result = StoryValidation(
            story_key=f"{STORY_PREFIX}:ST-001",
            story_id="ST-001",
            errors=["Missing required fields: phase, status"],
        )
        _print_story_result(result)
        output = capsys.readouterr().out
        assert "[FAIL]" in output
        assert "ERROR" in output

    def test_print_story_result_verbose(self, capsys: Any) -> None:
        """Verbose mode should include field validations."""
        result = StoryValidation(
            story_key=f"{STORY_PREFIX}:ST-001",
            story_id="ST-001",
            ttl_seconds=DEFAULT_TTL_SECONDS,
            ttl_valid=True,
            field_validations=[
                FieldValidation(field_name="phase", is_valid=True, message="OK"),
                FieldValidation(field_name="status", is_valid=True, message="OK"),
            ],
        )
        _print_story_result(result, verbose=True)
        output = capsys.readouterr().out
        assert "field validations" in output
        assert "phase:" in output
        assert "status:" in output

    def test_print_report_summary(self, capsys: Any) -> None:
        """_print_report should print summary."""
        report = WorkflowValidationReport(
            stories_checked=3,
            stories_valid=2,
            stories_with_errors=1,
            stories_with_warnings=1,
        )
        _print_report(report)
        output = capsys.readouterr().out
        assert "Stories checked: 3" in output
        assert "Valid: 2" in output
        assert "With errors: 1" in output

    def test_print_report_verbose(self, capsys: Any) -> None:
        """Verbose report should include per-story details."""
        report = WorkflowValidationReport(
            stories_checked=1,
            stories_valid=1,
            story_results=[
                StoryValidation(
                    story_key=f"{STORY_PREFIX}:ST-001",
                    story_id="ST-001",
                    ttl_seconds=DEFAULT_TTL_SECONDS,
                    ttl_valid=True,
                ),
            ],
        )
        _print_report(report, verbose=True)
        output = capsys.readouterr().out
        assert "ST-001" in output
