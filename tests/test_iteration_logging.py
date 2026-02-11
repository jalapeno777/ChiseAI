"""Tests for iteration logging module."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import os
from unittest.mock import MagicMock, patch

from operations.iteration_logging import (
    DEFAULT_TTL_SECONDS,
    VALID_PHASES,
    VALID_STATUSES,
    IterationLogEntry,
    NotImplementedInEnvironmentError,
    QdrantStorageError,
    RedisConnectionError,
    _get_redis_client,
    check_ttl_validity,
    close_iteration,
    get_iteration_log,
    log_completion,
    log_decision,
    log_iteration_start,
    log_learning,
    promote_to_qdrant,
    query_by_story_pattern,
    validate_iteration_schema,
    validate_story_completeness,
)


class TestIterationLogEntry:
    """Test cases for IterationLogEntry dataclass."""

    def test_creation(self):
        """Test creating an IterationLogEntry."""
        entry = IterationLogEntry(
            story_id="ST-001",
            story_title="Test Story",
            phase="implementation",
            status="in_progress",
            started_at="2026-02-11T00:00:00Z",
            acceptance_criteria=["AC1: Works", "AC2: Tested"],
        )

        assert entry.story_id == "ST-001"
        assert entry.story_title == "Test Story"
        assert entry.phase == "implementation"
        assert entry.status == "in_progress"
        assert entry.started_at == "2026-02-11T00:00:00Z"
        assert entry.acceptance_criteria == ["AC1: Works", "AC2: Tested"]
        assert entry.key_decisions == []
        assert entry.learnings == []
        assert entry.completed_at is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        entry = IterationLogEntry(
            story_id="ST-001",
            story_title="Test Story",
            phase="implementation",
            status="in_progress",
            started_at="2026-02-11T00:00:00Z",
            acceptance_criteria=["AC1: Works"],
            key_decisions=[{"decision": "Use Redis", "rationale": "Fast"}],
            learnings=[{"learning": "Schema matters", "impact": "high"}],
        )

        data = entry.to_dict()

        assert data["story_id"] == "ST-001"
        assert data["story_title"] == "Test Story"
        assert data["phase"] == "implementation"
        assert data["status"] == "in_progress"
        assert data["started_at"] == "2026-02-11T00:00:00Z"
        assert json.loads(data["acceptance_criteria"]) == ["AC1: Works"]
        assert json.loads(data["key_decisions"]) == [
            {"decision": "Use Redis", "rationale": "Fast"}
        ]
        assert json.loads(data["learnings"]) == [
            {"learning": "Schema matters", "impact": "high"}
        ]

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "story_id": "ST-001",
            "story_title": "Test Story",
            "phase": "implementation",
            "status": "in_progress",
            "started_at": "2026-02-11T00:00:00Z",
            "acceptance_criteria": '["AC1: Works"]',
            "key_decisions": '[{"decision": "Use Redis"}]',
            "learnings": '[{"learning": "Schema matters"}]',
            "completed_at": "",
        }

        entry = IterationLogEntry.from_dict(data)

        assert entry.story_id == "ST-001"
        assert entry.story_title == "Test Story"
        assert entry.phase == "implementation"
        assert entry.acceptance_criteria == ["AC1: Works"]


class TestLogIterationStart:
    """Test cases for log_iteration_start function."""

    def test_basic_start(self):
        """Test starting an iteration with basic parameters."""
        result = log_iteration_start(
            story_id="ST-001",
            story_title="Test Story",
            acceptance_criteria=["AC1: Works", "AC2: Tested"],
        )

        assert result["key"] == "bmad:chiseai:iterlog:story:ST-001"
        assert result["ttl_seconds"] == DEFAULT_TTL_SECONDS
        assert result["data"]["story_id"] == "ST-001"
        assert result["data"]["story_title"] == "Test Story"
        assert result["data"]["phase"] == "implementation"
        assert result["data"]["status"] == "in_progress"

    def test_all_phases(self):
        """Test starting iterations with all valid phases."""
        for phase in VALID_PHASES:
            result = log_iteration_start(
                story_id="ST-001",
                story_title="Test",
                acceptance_criteria=["AC1"],
                phase=phase,
            )
            assert result["data"]["phase"] == phase

    def test_all_statuses(self):
        """Test starting iterations with all valid statuses."""
        for status in VALID_STATUSES:
            result = log_iteration_start(
                story_id="ST-001",
                story_title="Test",
                acceptance_criteria=["AC1"],
                status=status,
            )
            assert result["data"]["status"] == status

    def test_invalid_phase_raises(self):
        """Test that invalid phase raises ValueError."""
        with pytest.raises(ValueError, match="Invalid phase"):
            log_iteration_start(
                story_id="ST-001",
                story_title="Test",
                acceptance_criteria=["AC1"],
                phase="invalid_phase",
            )

    def test_invalid_status_raises(self):
        """Test that invalid status raises ValueError."""
        with pytest.raises(ValueError, match="Invalid status"):
            log_iteration_start(
                story_id="ST-001",
                story_title="Test",
                acceptance_criteria=["AC1"],
                status="invalid_status",
            )


class TestLogDecision:
    """Test cases for log_decision function."""

    def test_basic_decision(self):
        """Test logging a basic decision."""
        result = log_decision(
            story_id="ST-001",
            decision="Use Redis",
            rationale="Low latency storage",
        )

        assert result["key"] == "bmad:chiseai:iterlog:story:ST-001:decisions"
        assert result["decision"]["decision"] == "Use Redis"
        assert result["decision"]["rationale"] == "Low latency storage"
        assert "timestamp" in result["decision"]
        assert result["ttl_seconds"] == DEFAULT_TTL_SECONDS

    def test_decision_with_timestamp(self):
        """Test logging a decision with explicit timestamp."""
        timestamp = "2026-02-11T12:00:00Z"
        result = log_decision(
            story_id="ST-001",
            decision="Use Redis",
            rationale="Fast",
            timestamp=timestamp,
        )

        assert result["decision"]["timestamp"] == timestamp


class TestLogLearning:
    """Test cases for log_learning function."""

    def test_basic_learning(self):
        """Test logging a basic learning."""
        result = log_learning(
            story_id="ST-001",
            learning="Schema design took longer than expected",
        )

        assert result["key"] == "bmad:chiseai:iterlog:story:ST-001:learnings"
        assert (
            result["learning"]["learning"] == "Schema design took longer than expected"
        )
        assert result["learning"]["impact"] == "medium"
        assert result["learning"]["category"] == "general"
        assert "timestamp" in result["learning"]
        assert result["ttl_seconds"] == DEFAULT_TTL_SECONDS

    def test_learning_with_metadata(self):
        """Test logging a learning with impact and category."""
        result = log_learning(
            story_id="ST-001",
            learning="Redis TTL must be 5 days",
            impact="high",
            category="technical",
        )

        assert result["learning"]["impact"] == "high"
        assert result["learning"]["category"] == "technical"

    def test_learning_with_timestamp(self):
        """Test logging a learning with explicit timestamp."""
        timestamp = "2026-02-11T12:00:00Z"
        result = log_learning(
            story_id="ST-001",
            learning="Important lesson",
            timestamp=timestamp,
        )

        assert result["learning"]["timestamp"] == timestamp


class TestLogCompletion:
    """Test cases for log_completion function."""

    def test_basic_completion(self):
        """Test logging story completion."""
        result = log_completion(story_id="ST-001")

        assert result["key"] == "bmad:chiseai:iterlog:story:ST-001"
        assert result["data"]["story_id"] == "ST-001"
        assert result["data"]["status"] == "completed"
        assert "completed_at" in result["data"]
        assert result["ttl_seconds"] == DEFAULT_TTL_SECONDS

    def test_deprecated_status(self):
        """Test logging story as deprecated."""
        result = log_completion(story_id="ST-001", status="deprecated")

        assert result["data"]["status"] == "deprecated"

    def test_invalid_status_raises(self):
        """Test that invalid status raises ValueError."""
        with pytest.raises(ValueError, match="Invalid status"):
            log_completion(story_id="ST-001", status="invalid")

    def test_with_final_phase(self):
        """Test completion with final phase override."""
        result = log_completion(
            story_id="ST-001",
            final_phase="testing",
        )

        assert result["data"]["phase"] == "testing"


class TestCloseIteration:
    """Test cases for close_iteration function."""

    def test_basic_close(self):
        """Test closing an iteration without promotion."""
        result = close_iteration(story_id="ST-001")

        assert result["story_id"] == "ST-001"
        assert result["promoted_to_qdrant"] is False
        assert "closed_at" in result

    def test_close_with_promotion(self):
        """Test closing with Qdrant promotion."""
        result = close_iteration(
            story_id="ST-001",
            promote_to_qdrant=True,
        )

        assert result["promoted_to_qdrant"] is True
        assert "qdrant_metadata" in result
        assert result["qdrant_metadata"]["project"] == "ChiseAI"
        assert result["qdrant_metadata"]["type"] == "learning"
        assert result["qdrant_metadata"]["story_id"] == "ST-001"

    def test_close_with_custom_metadata(self):
        """Test closing with custom Qdrant metadata."""
        custom_metadata = {"epic_id": "EP-001", "priority": "high"}
        result = close_iteration(
            story_id="ST-001",
            promote_to_qdrant=True,
            qdrant_metadata=custom_metadata,
        )

        assert result["qdrant_metadata"]["epic_id"] == "EP-001"
        assert result["qdrant_metadata"]["priority"] == "high"


class TestValidateIterationSchema:
    """Test cases for validate_iteration_schema function."""

    def test_valid_schema(self):
        """Test validation with valid data."""
        data = {
            "story_id": "ST-001",
            "phase": "implementation",
            "status": "in_progress",
            "started_at": "2026-02-11T00:00:00Z",
        }

        is_valid, errors = validate_iteration_schema(data)

        assert is_valid is True
        assert errors == []

    def test_missing_required_fields(self):
        """Test validation with missing required fields."""
        data = {"story_id": "ST-001"}

        is_valid, errors = validate_iteration_schema(data)

        assert is_valid is False
        assert any("phase" in e for e in errors)
        assert any("status" in e for e in errors)
        assert any("started_at" in e for e in errors)

    def test_invalid_phase(self):
        """Test validation with invalid phase."""
        data = {
            "story_id": "ST-001",
            "phase": "invalid",
            "status": "in_progress",
            "started_at": "2026-02-11T00:00:00Z",
        }

        is_valid, errors = validate_iteration_schema(data)

        assert is_valid is False
        assert any("phase" in e for e in errors)

    def test_invalid_status(self):
        """Test validation with invalid status."""
        data = {
            "story_id": "ST-001",
            "phase": "implementation",
            "status": "invalid",
            "started_at": "2026-02-11T00:00:00Z",
        }

        is_valid, errors = validate_iteration_schema(data)

        assert is_valid is False
        assert any("status" in e for e in errors)


class TestValidateStoryCompleteness:
    """Test cases for validate_story_completeness function."""

    def test_complete_story(self):
        """Test validation with complete story data."""
        data = {
            "story_id": "ST-001",
            "story_title": "Test Story",
            "phase": "implementation",
            "status": "completed",
            "started_at": "2026-02-11T00:00:00Z",
            "completed_at": "2026-02-11T12:00:00Z",
            "acceptance_criteria": ["AC1: Works", "AC2: Tested"],
        }

        is_valid, errors = validate_story_completeness(data)

        assert is_valid is True
        assert errors == []

    def test_deprecated_story(self):
        """Test validation with deprecated story."""
        data = {
            "story_id": "ST-001",
            "story_title": "Test Story",
            "phase": "implementation",
            "status": "deprecated",
            "started_at": "2026-02-11T00:00:00Z",
            "acceptance_criteria": ["AC1"],
        }

        is_valid, errors = validate_story_completeness(data)

        assert is_valid is True

    def test_missing_required_fields(self):
        """Test validation with missing required fields."""
        data = {"story_id": "ST-001", "status": "completed"}

        is_valid, errors = validate_story_completeness(data)

        assert is_valid is False
        assert any("story_title" in e for e in errors)

    def test_non_terminal_status(self):
        """Test validation with non-terminal status."""
        data = {
            "story_id": "ST-001",
            "story_title": "Test",
            "phase": "implementation",
            "status": "in_progress",
            "started_at": "2026-02-11T00:00:00Z",
            "acceptance_criteria": ["AC1"],
        }

        is_valid, errors = validate_story_completeness(data)

        assert is_valid is False
        assert any("terminal status" in e for e in errors)

    def test_missing_completed_at(self):
        """Test validation with missing completed_at for completed story."""
        data = {
            "story_id": "ST-001",
            "story_title": "Test",
            "phase": "implementation",
            "status": "completed",
            "started_at": "2026-02-11T00:00:00Z",
            "acceptance_criteria": ["AC1"],
        }

        is_valid, errors = validate_story_completeness(data)

        assert is_valid is False
        assert any("completed_at" in e for e in errors)

    def test_empty_acceptance_criteria(self):
        """Test validation with empty acceptance criteria."""
        data = {
            "story_id": "ST-001",
            "story_title": "Test",
            "phase": "implementation",
            "status": "completed",
            "started_at": "2026-02-11T00:00:00Z",
            "completed_at": "2026-02-11T12:00:00Z",
            "acceptance_criteria": [],
        }

        is_valid, errors = validate_story_completeness(data)

        assert is_valid is False
        assert any("acceptance_criteria" in e for e in errors)

    def test_json_string_acceptance_criteria(self):
        """Test validation with JSON string acceptance criteria."""
        data = {
            "story_id": "ST-001",
            "story_title": "Test",
            "phase": "implementation",
            "status": "completed",
            "started_at": "2026-02-11T00:00:00Z",
            "completed_at": "2026-02-11T12:00:00Z",
            "acceptance_criteria": '["AC1: Works"]',
        }

        is_valid, errors = validate_story_completeness(data)

        assert is_valid is True

    def test_invalid_json_acceptance_criteria(self):
        """Test validation with invalid JSON acceptance criteria."""
        data = {
            "story_id": "ST-001",
            "story_title": "Test",
            "phase": "implementation",
            "status": "completed",
            "started_at": "2026-02-11T00:00:00Z",
            "completed_at": "2026-02-11T12:00:00Z",
            "acceptance_criteria": "not valid json",
        }

        is_valid, errors = validate_story_completeness(data)

        assert is_valid is False
        assert any("JSON" in e for e in errors)


class TestCheckTtlValidity:
    """Test cases for check_ttl_validity function."""

    def test_valid_ttl(self):
        """Test with valid 5-day TTL."""
        is_valid, message = check_ttl_validity(DEFAULT_TTL_SECONDS)

        assert is_valid is True
        assert "5 days" in message
        assert str(DEFAULT_TTL_SECONDS) in message

    def test_invalid_ttl_wrong_value(self):
        """Test with incorrect TTL value."""
        is_valid, message = check_ttl_validity(86400)  # 1 day

        assert is_valid is False
        assert str(DEFAULT_TTL_SECONDS) in message
        assert "86400" in message

    def test_invalid_ttl_negative(self):
        """Test with negative TTL."""
        is_valid, message = check_ttl_validity(-1)

        assert is_valid is False
        assert "cannot be negative" in message


class TestPromoteToQdrant:
    """Test cases for promote_to_qdrant function."""

    def test_basic_promotion(self):
        """Test basic promotion of learnings."""
        learnings = [
            {"learning": "Lesson 1", "impact": "high", "category": "technical"},
            {"learning": "Lesson 2", "impact": "medium", "category": "process"},
        ]

        result = promote_to_qdrant("ST-001", learnings)

        assert result["story_id"] == "ST-001"
        assert result["promoted_count"] == 2
        assert "promoted_at" in result
        assert len(result["entries"]) == 2

    def test_entry_format(self):
        """Test that entries have correct Qdrant format."""
        learnings = [{"learning": "Important lesson", "impact": "high"}]

        result = promote_to_qdrant("ST-001", learnings)

        entry = result["entries"][0]
        assert entry["information"] == "Important lesson"
        assert entry["metadata"]["project"] == "ChiseAI"
        assert entry["metadata"]["type"] == "learning"
        assert entry["metadata"]["story_id"] == "ST-001"
        assert entry["metadata"]["impact"] == "high"

    def test_with_custom_metadata(self):
        """Test promotion with custom metadata."""
        learnings = [{"learning": "Lesson"}]
        custom_metadata = {"epic_id": "EP-001", "tags": ["important"]}

        result = promote_to_qdrant("ST-001", learnings, custom_metadata)

        entry = result["entries"][0]
        assert entry["metadata"]["epic_id"] == "EP-001"
        assert entry["metadata"]["tags"] == ["important"]

    def test_empty_learnings(self):
        """Test promotion with empty learnings list."""
        result = promote_to_qdrant("ST-001", [])

        assert result["promoted_count"] == 0
        assert result["entries"] == []

    def test_stored_entries_tracking(self):
        """Test that stored_entries are tracked with storage status."""
        learnings = [
            {"learning": "Lesson 1", "impact": "high"},
            {"learning": "Lesson 2", "impact": "medium"},
        ]

        result = promote_to_qdrant("ST-001", learnings)

        # Should have stored_entries list
        assert "stored_entries" in result
        assert len(result["stored_entries"]) == 2

        # In test environment, entries should be marked as not stored
        for entry in result["stored_entries"]:
            assert "stored" in entry
            assert "information" in entry
            assert "metadata" in entry

        # actually_stored should be 0 in test environment
        assert result["actually_stored"] == 0

    def test_qdrant_storage_error_in_production(self):
        """Test that QdrantStorageError is raised in production on failure."""
        learnings = [{"learning": "Lesson 1"}]

        # Mock _store_in_qdrant to raise an exception
        with patch("operations.iteration_logging._store_in_qdrant") as mock_store:
            mock_store.side_effect = Exception("Storage failed")

            with patch.dict(os.environ, {"CHISEAI_ENV": "production"}):
                with pytest.raises(QdrantStorageError):
                    promote_to_qdrant("ST-001", learnings)


class TestQueryByStoryPattern:
    """Test cases for query_by_story_pattern function."""

    def test_default_pattern(self):
        """Test querying with default pattern."""
        result = query_by_story_pattern()

        assert isinstance(result, list)

    def test_custom_pattern(self):
        """Test querying with custom pattern."""
        result = query_by_story_pattern("ST-CHISE-*")

        assert isinstance(result, list)

    def test_redis_scan_implementation(self):
        """Test that query_by_story_pattern uses Redis SCAN when available."""
        # Mock Redis client
        mock_client = MagicMock()
        # Simulate SCAN returning some keys
        mock_client.scan.side_effect = [
            (
                0,
                [
                    "bmad:chiseai:iterlog:story:ST-001",
                    "bmad:chiseai:iterlog:story:ST-002",
                ],
            ),
        ]

        with patch(
            "operations.iteration_logging._get_redis_client",
            return_value=mock_client,
        ):
            result = query_by_story_pattern("*")

        assert isinstance(result, list)
        assert "ST-001" in result
        assert "ST-002" in result
        mock_client.scan.assert_called()

    def test_redis_connection_error_in_production(self):
        """Test that NotImplementedInEnvironmentError is raised in production."""
        with patch(
            "operations.iteration_logging._get_redis_client",
            side_effect=Exception("Redis unavailable"),
        ):
            with patch.dict(os.environ, {"CHISEAI_ENV": "production"}):
                with pytest.raises(NotImplementedInEnvironmentError):
                    query_by_story_pattern("*")


class TestGetIterationLog:
    """Test cases for get_iteration_log function."""

    def test_returns_none_without_redis(self):
        """Test that get_iteration_log returns None when Redis unavailable."""
        with patch(
            "operations.iteration_logging._get_redis_client",
            return_value=None,
        ):
            result = get_iteration_log("ST-001")

        assert result is None

    def test_redis_hgetall_retrieval(self):
        """Test that get_iteration_log uses Redis HGETALL when available."""
        mock_client = MagicMock()
        mock_client.hgetall.return_value = {
            "story_id": "ST-001",
            "story_title": "Test Story",
            "phase": "implementation",
            "status": "completed",
            "started_at": "2026-02-11T00:00:00Z",
            "acceptance_criteria": '["AC1: Works"]',
            "key_decisions": "[]",
            "learnings": "[]",
        }

        with patch(
            "operations.iteration_logging._get_redis_client",
            return_value=mock_client,
        ):
            result = get_iteration_log("ST-001")

        assert result is not None
        assert result["story_id"] == "ST-001"
        assert result["story_title"] == "Test Story"
        # JSON fields should be parsed
        assert result["acceptance_criteria"] == ["AC1: Works"]
        assert result["key_decisions"] == []
        mock_client.hgetall.assert_called_once()

    def test_not_found_returns_none(self):
        """Test that get_iteration_log returns None when key not found."""
        mock_client = MagicMock()
        mock_client.hgetall.return_value = {}

        with patch(
            "operations.iteration_logging._get_redis_client",
            return_value=mock_client,
        ):
            result = get_iteration_log("ST-NOTFOUND")

        assert result is None

    def test_production_error_raises(self):
        """Test that NotImplementedInEnvironmentError is raised in production."""
        with patch(
            "operations.iteration_logging._get_redis_client",
            side_effect=Exception("Redis unavailable"),
        ):
            with patch.dict(os.environ, {"CHISEAI_ENV": "production"}):
                with pytest.raises(NotImplementedInEnvironmentError):
                    get_iteration_log("ST-001")


class TestRedisConnectionError:
    """Test cases for RedisConnectionError exception."""

    def test_redis_connection_error_in_production(self):
        """Test that RedisConnectionError is raised in production."""
        # Mock the import to simulate redis module not available
        with patch.dict("sys.modules", {"redis": None}):
            with patch.dict(os.environ, {"CHISEAI_ENV": "production"}):
                with pytest.raises(RedisConnectionError):
                    _get_redis_client()

    def test_returns_none_in_test(self):
        """Test that None is returned in test environment."""
        # Mock the import to simulate redis module not available
        with patch.dict("sys.modules", {"redis": None}):
            result = _get_redis_client()

        assert result is None


class TestConstants:
    """Test cases for module constants."""

    def test_default_ttl_value(self):
        """Test that default TTL is 5 days in seconds."""
        assert DEFAULT_TTL_SECONDS == 432000  # 5 days = 5 * 24 * 60 * 60

    def test_valid_phases(self):
        """Test that valid phases are defined correctly."""
        expected = {"analysis", "planning", "solutioning", "implementation", "testing"}
        assert VALID_PHASES == expected

    def test_valid_statuses(self):
        """Test that valid statuses are defined correctly."""
        expected = {"planned", "in_progress", "blocked", "completed", "deprecated"}
        assert VALID_STATUSES == expected
