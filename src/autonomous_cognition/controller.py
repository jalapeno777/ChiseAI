"""Autonomous cognition controller for daily self-assessment runs."""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autonomous_cognition.artifacts import SelfAssessmentArtifact

logger = logging.getLogger(__name__)

try:
    from tools.redis_state import (
        _get_redis_client as redis_state_get_client,  # type: ignore[attr-defined]
    )
    from tools.redis_state import redis_state_lpush, redis_state_set
except Exception:
    redis_state_get_client = None
    redis_state_lpush = None
    redis_state_set = None


class AutonomousCognitionController:
    """Runs autonomous daily self-assessment and persists artifacts."""

    REDIS_CURRENT_KEY = "bmad:chiseai:autocog:self_assessment:latest"
    REDIS_HISTORY_KEY = "bmad:chiseai:autocog:self_assessment:history"
    DEFAULT_ARTIFACTS_DIR = "docs/governance/self_assessments"

    def __init__(
        self,
        artifacts_dir: str | Path | None = None,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
    ):
        self._artifacts_dir = Path(artifacts_dir or self.DEFAULT_ARTIFACTS_DIR)
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client

    def run_daily_self_assessment(self) -> tuple[SelfAssessmentArtifact, Path]:
        """Execute full self-assessment cycle and persist output."""
        artifact = self._build_artifact()
        artifact_path = self._persist_artifact(artifact)
        self._persist_redis(artifact)
        self._persist_qdrant(artifact)
        return artifact, artifact_path

    def _build_artifact(self) -> SelfAssessmentArtifact:
        """Build self-assessment artifact from live system signals."""
        assessment_id = f"sa-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        artifact = SelfAssessmentArtifact.create_empty(assessment_id=assessment_id)

        signals = self._collect_signals()
        dimensions = self._score_dimensions(signals)
        overall_score = round(sum(dimensions.values()) / max(len(dimensions), 1), 2)

        findings: list[str] = []
        recommendations: list[str] = []

        if not signals["memory_daily_sweep_enabled"]:
            findings.append("Memory daily sweep is disabled.")
            recommendations.append("Enable memory.daily_sweep to maintain memory hygiene.")

        if signals["redis_available"] is False:
            findings.append("Redis unavailable during assessment.")
            recommendations.append("Restore Redis connectivity for full autonomous operation.")

        if signals["qdrant_available"] is False:
            findings.append("Qdrant unavailable during assessment.")
            recommendations.append(
                "Restore Qdrant connectivity for long-term cognition memory."
            )

        if not findings:
            findings.append("No critical cognition health issues detected in this cycle.")
            recommendations.append("Continue autonomous monitoring and trend tracking.")

        status = "ok"
        if overall_score < 0.6:
            status = "degraded"
        if overall_score < 0.35:
            status = "failed"

        artifact.status = status
        artifact.overall_score = overall_score
        artifact.dimensions = dimensions
        artifact.findings = findings
        artifact.recommendations = recommendations
        artifact.evidence = signals
        artifact.run_metadata = {
            "runner": "autonomous_cognition.controller",
            "host": os.getenv("HOSTNAME", "unknown"),
            "python_env": os.getenv("CHISEAI_ENV", "development"),
        }
        return artifact

    def _collect_signals(self) -> dict[str, Any]:
        """Collect low-latency signals for assessment scoring."""
        memory_daily_sweep_enabled = self._is_daily_sweep_enabled()
        redis_available = self._check_redis_available()
        qdrant_available = self._check_qdrant_available()

        return {
            "memory_daily_sweep_enabled": memory_daily_sweep_enabled,
            "redis_available": redis_available,
            "qdrant_available": qdrant_available,
            "qdrant_write_enabled": os.getenv("CHISEAI_ENABLE_QDRANT_WRITE", "false")
            .lower()
            .strip()
            == "true",
            "timestamp_utc": datetime.now(UTC).isoformat(),
        }

    def _score_dimensions(self, signals: dict[str, Any]) -> dict[str, float]:
        """Score cognition dimensions (0.0-1.0)."""
        memory_score = 1.0 if signals.get("memory_daily_sweep_enabled") else 0.35
        infra_score = (
            1.0
            if signals.get("redis_available") and signals.get("qdrant_available")
            else 0.45
        )
        safety_score = 1.0 if signals.get("memory_daily_sweep_enabled") else 0.7
        adaptation_score = (
            0.9
            if signals.get("qdrant_write_enabled") and signals.get("qdrant_available")
            else 0.5
        )

        return {
            "memory_health": round(memory_score, 2),
            "infrastructure_health": round(infra_score, 2),
            "safety_alignment": round(safety_score, 2),
            "adaptive_learning_readiness": round(adaptation_score, 2),
        }

    def _persist_artifact(self, artifact: SelfAssessmentArtifact) -> Path:
        """Persist artifact to file system for auditability."""
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        filename = f"self_assessment_{artifact.assessment_date}_{artifact.assessment_id}.json"
        path = self._artifacts_dir / filename
        path.write_text(artifact.to_json(indent=2), encoding="utf-8")
        return path

    def _persist_redis(self, artifact: SelfAssessmentArtifact) -> None:
        """Persist latest and history to Redis with graceful fallback."""
        payload = artifact.to_json(indent=None)

        if self._redis_client is not None:
            try:
                self._redis_client.set(self.REDIS_CURRENT_KEY, payload)
                self._redis_client.lpush(self.REDIS_HISTORY_KEY, payload)
                self._redis_client.ltrim(self.REDIS_HISTORY_KEY, 0, 99)
                return
            except Exception as e:
                logger.warning("Redis persistence via client failed: %s", e)

        try:
            if redis_state_set:
                redis_state_set(self.REDIS_CURRENT_KEY, payload)
            if redis_state_lpush:
                redis_state_lpush(self.REDIS_HISTORY_KEY, payload, expire=86400 * 30)
        except Exception as e:
            logger.warning("Redis persistence skipped: %s", e)

    def _persist_qdrant(self, artifact: SelfAssessmentArtifact) -> None:
        """Persist artifact summary to Qdrant if client is configured."""
        if self._qdrant_client is None:
            return

        try:
            collection_name = "ChiseAI"
            vector_size = 384
            content = (
                f"{artifact.status} {artifact.overall_score} "
                f"{' '.join(artifact.findings)} {' '.join(artifact.recommendations)}"
            )
            vector = self._deterministic_embedding(content, dimensions=vector_size)
            self._qdrant_client.upsert(
                collection_name=collection_name,
                points=[
                    {
                        "id": hashlib.sha256(
                            artifact.assessment_id.encode("utf-8")
                        ).hexdigest()[:32],
                        "vector": vector,
                        "payload": artifact.to_dict(),
                    }
                ],
            )
        except Exception as e:
            logger.warning("Qdrant persistence skipped: %s", e)

    def _is_daily_sweep_enabled(self) -> bool:
        """Read memory.daily_sweep enablement from job registry."""
        registry_path = Path("config/autonomy_job_registry.yaml")
        if not registry_path.exists():
            return False
        try:
            import yaml

            data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
            jobs = data.get("jobs", [])
            for job in jobs:
                if job.get("job_id") == "memory.daily_sweep":
                    return bool(job.get("enabled", False))
            return False
        except Exception as e:
            logger.warning("Failed reading autonomy registry: %s", e)
            return False

    def _check_redis_available(self) -> bool:
        """Check whether Redis is reachable."""
        try:
            if self._redis_client is not None:
                self._redis_client.ping()
                return True

            if redis_state_get_client is None:
                return False
            client = redis_state_get_client()
            if client is None:
                return False
            client.ping()
            return True
        except Exception:
            return False

    def _check_qdrant_available(self) -> bool:
        """Check whether Qdrant is reachable."""
        try:
            if self._qdrant_client is None:
                return False
            if hasattr(self._qdrant_client, "get_collections"):
                self._qdrant_client.get_collections()
                return True
            return True
        except Exception:
            return False

    @staticmethod
    def _deterministic_embedding(text: str, dimensions: int = 384) -> list[float]:
        """Generate deterministic embedding vector without ML dependencies."""
        if not text:
            return [0.0] * dimensions

        values: list[float] = []
        data = text.encode("utf-8")
        for i in range(dimensions):
            digest = hashlib.sha256(data + i.to_bytes(4, "little")).digest()
            raw = int.from_bytes(digest[:4], "little")
            values.append((raw % 20000) / 10000 - 1.0)
        return values
