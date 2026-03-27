"""Autonomous cognition controller for daily self-assessment runs."""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from autonomous_cognition.schema.assessment_schema import AssessmentArtifact

logger = logging.getLogger(__name__)


class RedisGetClient(Protocol):
    def __call__(self) -> Any: ...


class RedisPushFunc(Protocol):
    def __call__(self, name: str, value: Any, expire: int | None = None) -> bool: ...


class RedisSetFunc(Protocol):
    def __call__(self, key: str, value: Any, expiration: int | None = None) -> bool: ...


redis_state_get_client: RedisGetClient | None = None
redis_state_lpush: RedisPushFunc | None = None
redis_state_set: RedisSetFunc | None = None

try:
    from tools.redis_state import (
        _get_redis_client as redis_state_get_client,  # type: ignore[attr-defined]
    )
    from tools.redis_state import redis_state_lpush, redis_state_set
except ImportError:
    logger.warning("Failed to import tools.redis_state - Redis persistence disabled")
    redis_state_get_client = None
    redis_state_lpush = None
    redis_state_set = None


class AutonomousCognitionController:
    """Runs autonomous daily self-assessment and persists artifacts."""

    REDIS_CURRENT_KEY = "bmad:chiseai:autocog:self_assessment:latest"
    REDIS_HISTORY_KEY = "bmad:chiseai:autocog:self_assessment:history"
    DEFAULT_ARTIFACTS_DIR = "docs/governance/self_assessments"
    CONFIG_PATH = Path("config/autocog.yaml")

    def __init__(
        self,
        artifacts_dir: str | Path | None = None,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
    ):
        self._artifacts_dir = Path(artifacts_dir or self.DEFAULT_ARTIFACTS_DIR)
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client
        self._config = self._load_config()
        # Deduplication stats (instance-level for test isolation)
        self._stats_files_written: int = 0
        self._stats_files_skipped: int = 0

    def run_daily_self_assessment(self) -> tuple[AssessmentArtifact, Path | None]:
        """Execute full self-assessment cycle and persist output."""
        artifact = self._build_artifact()
        artifact_path, _ = self._persist_artifact(artifact)
        self._persist_redis(artifact)
        self._persist_qdrant(artifact)
        return artifact, artifact_path

    def get_dedup_stats(self) -> dict[str, int]:
        """Return deduplication statistics."""
        return {
            "files_written": self._stats_files_written,
            "files_skipped": self._stats_files_skipped,
        }

    def _build_artifact(self) -> AssessmentArtifact:
        """Build self-assessment artifact from live system signals."""
        assessment_id = (
            f"sa-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        )
        assessment_date = datetime.now(UTC).date().isoformat()
        created_at = datetime.now(UTC).isoformat()

        signals = self._collect_signals()
        dimensions = self._score_dimensions(signals)
        overall_score = round(sum(dimensions.values()) / max(len(dimensions), 1), 2)

        findings: list[str] = []
        recommendations: list[str] = []

        if not signals["memory_daily_sweep_enabled"]:
            findings.append("Memory daily sweep is disabled.")
            recommendations.append(
                "Enable memory.daily_sweep to maintain memory hygiene."
            )

        if signals["redis_available"] is False:
            findings.append("Redis unavailable during assessment.")
            recommendations.append(
                "Restore Redis connectivity for full autonomous operation."
            )

        if signals["qdrant_available"] is False:
            findings.append("Qdrant unavailable during assessment.")
            recommendations.append(
                "Restore Qdrant connectivity for long-term cognition memory."
            )

        if not findings:
            findings.append(
                "No critical cognition health issues detected in this cycle."
            )
            recommendations.append("Continue autonomous monitoring and trend tracking.")

        status = "ok"
        if overall_score < 0.7:
            status = "degraded"
        if overall_score < 0.5:
            status = "failed"

        # Build artifact dict in legacy format for backward compatibility
        # AssessmentArtifact.from_dict() handles conversion to typed structures
        artifact_dict = {
            "assessment_id": assessment_id,
            "assessment_date": assessment_date,
            "created_at": created_at,
            "schema_version": "1.1.0",
            "status": status,
            "overall_score": overall_score,
            "dimensions": dimensions,  # Legacy dict format - from_dict converts to DimensionScore list
            "findings": findings,  # Legacy str list - from_dict converts to Finding list
            "recommendations": recommendations,  # Legacy str list - from_dict converts to Recommendation list
            "evidence": signals,  # Legacy dict format - from_dict converts to Evidence list
            "metadata": {  # Note: 'metadata' not 'run_metadata'
                "runner": "autonomous_cognition.controller",
                "host": os.getenv("HOSTNAME", "unknown"),
                "python_env": os.getenv("CHISEAI_ENV", "development"),
            },
        }
        return AssessmentArtifact.from_dict(artifact_dict)

    def _collect_signals(self) -> dict[str, Any]:
        """Collect low-latency signals for assessment scoring."""
        memory_daily_sweep_enabled = self._is_daily_sweep_enabled()
        redis_available = self._check_redis_available()
        qdrant_available = self._check_qdrant_available()

        # Check config and env for qdrant write enablement
        config_qdrant_write = self._config.get("qdrant", {}).get("write_enabled", False)
        env_qdrant_write = (
            os.getenv("CHISEAI_ENABLE_QDRANT_WRITE", "false").lower().strip() == "true"
        )
        qdrant_write_enabled = config_qdrant_write or env_qdrant_write

        # Check config for experiments enablement
        experiments_enabled = self._config.get("experiments", {}).get("enabled", False)

        return {
            "memory_daily_sweep_enabled": memory_daily_sweep_enabled,
            "redis_available": redis_available,
            "qdrant_available": qdrant_available,
            "qdrant_write_enabled": qdrant_write_enabled,
            "experiments_enabled": experiments_enabled,
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

    def _get_previous_score(self) -> float | None:
        """Retrieve overall_score from the previous assessment run via Redis."""
        payload: str | None = None

        if self._redis_client is not None:
            try:
                payload = self._redis_client.get(self.REDIS_CURRENT_KEY)
            except Exception as e:
                logger.warning("Redis get failed: %s", e)

        if payload is None and redis_state_get_client is not None:
            try:
                client = redis_state_get_client()
                if client is not None:
                    payload = client.get(self.REDIS_CURRENT_KEY)
            except Exception as e:
                logger.warning("redis_state get failed: %s", e)

        if payload is None:
            return None

        try:
            previous = AssessmentArtifact.from_json(payload)
            return previous.overall_score
        except Exception as e:
            logger.warning("Failed to parse previous assessment: %s", e)
            return None

    def _persist_artifact(
        self, artifact: AssessmentArtifact
    ) -> tuple[Path | None, str]:
        """Persist artifact to file system with deduplication.

        Returns:
            Tuple of (path, status) where status is "written" or "skipped".
        """
        previous_score = self._get_previous_score()

        if (
            previous_score is not None
            and abs(artifact.overall_score - previous_score) < 1e-9
        ):
            logger.info(
                "skipped redundant assessment (score unchanged: %.2f)",
                artifact.overall_score,
            )
            self._stats_files_skipped += 1
            return None, "skipped"

        try:
            self._artifacts_dir.mkdir(parents=True, exist_ok=True)
            filename = f"self_assessment_{artifact.assessment_date}_{artifact.assessment_id}.json"
            path = self._artifacts_dir / filename
            path.write_text(artifact.to_json(indent=2), encoding="utf-8")
            logger.info("Persisted self-assessment artifact to %s", path)
            self._stats_files_written += 1
            return path, "written"
        except Exception as e:
            logger.error("Failed to persist artifact: %s", e)
            return None, "error"

    def _persist_redis(self, artifact: AssessmentArtifact) -> None:
        """Persist latest and history to Redis with graceful fallback."""
        payload = artifact.to_json()

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

    def _persist_qdrant(self, artifact: AssessmentArtifact) -> None:
        """Persist artifact summary to Qdrant if client is configured."""
        if self._qdrant_client is None:
            return

        try:
            collection_name = "ChiseAI"
            vector_size = 384
            # Extract string descriptions from typed Finding/Recommendation objects
            findings_text = " ".join(
                f.description if hasattr(f, "description") else str(f)
                for f in artifact.findings
            )
            recommendations_text = " ".join(
                r.description if hasattr(r, "description") else str(r)
                for r in artifact.recommendations
            )
            content = (
                f"{artifact.status} {artifact.overall_score} "
                f"{findings_text} {recommendations_text}"
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

    def _load_config(self) -> dict[str, Any]:
        """Load autocog configuration from YAML file."""
        if not self.CONFIG_PATH.exists():
            logger.warning(
                "Autocog config not found at %s, using defaults", self.CONFIG_PATH
            )
            return self._default_config()
        try:
            import yaml

            data = yaml.safe_load(self.CONFIG_PATH.read_text(encoding="utf-8")) or {}
            return self._merge_with_defaults(data)
        except Exception as e:
            logger.warning("Failed loading autocog config: %s", e)
            return self._default_config()

    def _default_config(self) -> dict[str, Any]:
        """Return default configuration."""
        return {
            "experiments": {
                "enabled": False,
                "max_experiments_per_cycle": 3,
                "safe_mode": True,
            },
            "qdrant": {
                "write_enabled": False,
                "collection_name": "ChiseAI",
                "vector_size": 384,
            },
            "metrics": {
                "skip_rate_alert_threshold": 0.20,
                "skip_rate_window_days": 7,
                "alert_on_high_skip_rate": True,
            },
            "safety": {
                "max_risk_level": "medium",
                "require_approval_for": ["high", "critical"],
            },
        }

    def _merge_with_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        """Merge loaded config with defaults."""
        defaults = self._default_config()
        for key, default_value in defaults.items():
            if key not in data:
                data[key] = default_value
            elif isinstance(default_value, dict) and isinstance(data[key], dict):
                for sub_key, sub_default in default_value.items():
                    if sub_key not in data[key]:
                        data[key][sub_key] = sub_default
        return data

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

            if redis_state_get_client is not None:
                client = redis_state_get_client()
                if client is not None:
                    client.ping()
                    return True

            # Fallback for script/cron contexts where tools package import may be unavailable.
            import redis

            host = os.getenv("REDIS_HOST", "host.docker.internal")
            port = int(os.getenv("REDIS_PORT", "6380"))
            db = int(os.getenv("REDIS_DB", "0"))
            password = os.getenv("REDIS_PASSWORD") or None
            direct_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            direct_client.ping()
            return True
        except Exception:
            return False

    def _check_qdrant_available(self) -> bool:
        """Check whether Qdrant is reachable."""
        try:
            if self._qdrant_client is not None:
                if hasattr(self._qdrant_client, "get_collections"):
                    self._qdrant_client.get_collections()
                    return True
                return True

            from qdrant_client import QdrantClient

            qdrant_url = os.getenv("QDRANT_URL")
            if qdrant_url:
                client = QdrantClient(url=qdrant_url, timeout=3)
            else:
                host = (
                    os.getenv("QDRANT_HOST")
                    or os.getenv("CHISE_QDRANT_HOST")
                    or "host.docker.internal"
                )
                port = int(os.getenv("QDRANT_PORT", "6334"))
                client = QdrantClient(host=host, port=port, timeout=3)
            client.get_collections()
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
