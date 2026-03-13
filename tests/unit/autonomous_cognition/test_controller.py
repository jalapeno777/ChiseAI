"""Unit tests for autonomous cognition controller."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

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

