"""Unit tests for autonomous cognition controller."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import autonomous_cognition.controller as controller_module
from autonomous_cognition.controller import AutonomousCognitionController


def test_run_daily_self_assessment_persists_artifact(tmp_path: Path) -> None:
    """Controller should create and persist a daily artifact."""
    mock_redis = MagicMock()
    mock_qdrant = MagicMock()

    controller = AutonomousCognitionController(
        artifacts_dir=tmp_path,
        redis_client=mock_redis,
        qdrant_client=mock_qdrant,
    )

    artifact, artifact_path = controller.run_daily_self_assessment()

    assert artifact.assessment_id.startswith("sa-")
    assert artifact_path.exists()
    assert artifact.overall_score >= 0.0
    mock_redis.set.assert_called_once()
    mock_redis.lpush.assert_called_once()
    mock_qdrant.upsert.assert_called_once()


def test_build_artifact_sets_degraded_when_sweep_disabled(monkeypatch) -> None:
    """Disabling daily sweep should lower memory health score."""
    controller = AutonomousCognitionController()
    monkeypatch.setattr(controller, "_is_daily_sweep_enabled", lambda: False)
    monkeypatch.setattr(controller, "_check_redis_available", lambda: True)
    monkeypatch.setattr(controller, "_check_qdrant_available", lambda: True)

    artifact = controller._build_artifact()
    assert artifact.dimensions["memory_health"] < 0.5
    assert any("daily sweep" in finding.lower() for finding in artifact.findings)


def test_check_redis_available_falls_back_when_tools_import_unavailable(
    monkeypatch,
) -> None:
    """Redis availability check should use direct client fallback."""
    controller = AutonomousCognitionController()
    monkeypatch.setattr(controller_module, "redis_state_get_client", None)

    class _FakeRedisClient:
        def ping(self) -> bool:
            return True

    fake_redis_module = SimpleNamespace(Redis=lambda **_: _FakeRedisClient())
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)

    assert controller._check_redis_available() is True


class TestPreviousScorePath:
    """Tests for the previous_score retrieval and notification path."""

    def test_get_previous_score_returns_score_from_redis(self, monkeypatch) -> None:
        """Controller._get_previous_score should return score from Redis."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = (
            '{"assessment_id": "sa-test", '
            '"assessment_date": "2026-03-27", '
            '"created_at": "2026-03-27T10:00:00Z", '
            '"overall_score": 0.85}'
        )

        # Disable the redis_state_get_client fallback
        monkeypatch.setattr(controller_module, "redis_state_get_client", lambda: None)

        controller = AutonomousCognitionController(redis_client=mock_redis)
        previous = controller._get_previous_score()

        assert previous == 0.85
        mock_redis.get.assert_called_once_with(
            "bmad:chiseai:autocog:self_assessment:latest"
        )

    def test_get_previous_score_returns_none_when_no_redis(self, monkeypatch) -> None:
        """Controller._get_previous_score should return None when Redis unavailable."""
        # Disable the redis_state_get_client fallback
        monkeypatch.setattr(controller_module, "redis_state_get_client", lambda: None)

        controller = AutonomousCognitionController(redis_client=None)
        previous = controller._get_previous_score()

        assert previous is None

    def test_get_previous_score_returns_none_when_key_missing(
        self, monkeypatch
    ) -> None:
        """Controller._get_previous_score should return None when key is missing."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        # Disable the redis_state_get_client fallback
        monkeypatch.setattr(controller_module, "redis_state_get_client", lambda: None)

        controller = AutonomousCognitionController(redis_client=mock_redis)
        previous = controller._get_previous_score()

        assert previous is None

    def test_get_previous_score_parses_artifact_correctly(self, monkeypatch) -> None:
        """Controller._get_previous_score should parse artifact JSON correctly."""
        mock_redis = MagicMock()
        # Simulate artifact JSON with all required fields
        mock_redis.get.return_value = (
            '{"assessment_id": "sa-20260327-abc123", '
            '"assessment_date": "2026-03-27", '
            '"created_at": "2026-03-27T10:00:00Z", '
            '"overall_score": 0.92, "status": "ok"}'
        )

        # Disable the redis_state_get_client fallback
        monkeypatch.setattr(controller_module, "redis_state_get_client", lambda: None)

        controller = AutonomousCognitionController(redis_client=mock_redis)
        previous = controller._get_previous_score()

        assert previous == 0.92

    def test_get_previous_score_returns_none_when_artifact_parse_fails(
        self, monkeypatch
    ) -> None:
        """Controller._get_previous_score should return None when JSON is invalid."""
        mock_redis = MagicMock()
        # Artifact with invalid JSON - should cause parse failure
        mock_redis.get.return_value = "not valid json"

        # Disable the redis_state_get_client fallback
        monkeypatch.setattr(controller_module, "redis_state_get_client", lambda: None)

        controller = AutonomousCognitionController(redis_client=mock_redis)
        previous = controller._get_previous_score()

        # Parse failure returns None
        assert previous is None

    def test_persist_artifact_uses_date_only_filename(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Filename should be date-only (e.g., self_assessment_2026-04-13.json)."""
        from datetime import datetime as dt_class

        # Mock datetime to return a known date
        class FakeDatetime:
            @staticmethod
            def now(tz=None):
                if tz is not None:
                    return dt_class(2026, 4, 13, 10, 0, 0, tzinfo=tz)
                return dt_class(2026, 4, 13, 10, 0, 0)

            @staticmethod
            def fromisoformat(data):
                return dt_class.fromisoformat(data)

        # Patch datetime and disable redis_state_get_client fallback
        monkeypatch.setattr(controller_module, "datetime", FakeDatetime)
        monkeypatch.setattr(controller_module, "redis_state_get_client", lambda: None)

        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No previous score
        mock_qdrant = MagicMock()

        controller = controller_module.AutonomousCognitionController(
            artifacts_dir=tmp_path,
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        # Run assessment
        artifact, artifact_path = controller.run_daily_self_assessment()

        # Verify path is not None and filename follows date-only pattern
        assert artifact_path is not None, "Expected artifact_path to be written"

        filename = artifact_path.name
        # Date-only pattern: self_assessment_YYYY-MM-DD.json
        assert (
            filename == "self_assessment_2026-04-13.json"
        ), f"Expected date-only filename, got: {filename}"
        assert "sa-" not in filename, f"UUID fragment found in filename: {filename}"
        assert artifact_path.exists()
