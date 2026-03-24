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


def test_check_qdrant_available_falls_back_to_env_client(monkeypatch) -> None:
    """Qdrant availability check should instantiate a client when not injected."""
    controller = AutonomousCognitionController()
    monkeypatch.setenv("QDRANT_HOST", "host.docker.internal")
    monkeypatch.setenv("QDRANT_PORT", "6334")
    monkeypatch.delenv("QDRANT_URL", raising=False)

    class _FakeQdrantClient:
        def __init__(self, **_: object) -> None:
            pass

        def get_collections(self) -> object:
            return object()

    fake_qdrant_module = SimpleNamespace(QdrantClient=_FakeQdrantClient)
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_qdrant_module)

    assert controller._check_qdrant_available() is True
