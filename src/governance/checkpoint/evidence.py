"""Evidence collection and formatting for checkpoint audits.

This module provides the EvidenceCollector class for:
- Collecting checkpoint evidence
- Storing to Redis
- Formatting for Discord
- Archiving to files
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.governance.checkpoint.gates import GateResult, GateSummary

logger = logging.getLogger(__name__)


@dataclass
class CheckpointEvidence:
    """Complete evidence from a checkpoint run."""

    checkpoint_id: str
    timestamp: datetime
    summary: GateSummary
    metadata: dict[str, Any] = field(default_factory=dict)
    archived_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert evidence to dictionary for serialization."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp.isoformat(),
            "summary": {
                "results": [
                    {
                        "gate": r.gate,
                        "status": r.status,
                        "detail": r.detail,
                        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    }
                    for r in self.summary.results
                ],
                "pass_count": self.summary.pass_count,
                "fail_count": self.summary.fail_count,
                "check_count": self.summary.check_count,
                "timestamp": self.summary.timestamp.isoformat(),
            },
            "metadata": self.metadata,
            "archived_path": self.archived_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointEvidence:
        """Create evidence from dictionary."""
        summary_data = data.get("summary", {})
        results = [
            GateResult(
                gate=r["gate"],
                status=r["status"],
                detail=r["detail"],
                timestamp=(
                    datetime.fromisoformat(r["timestamp"])
                    if r.get("timestamp")
                    else None
                ),
            )
            for r in summary_data.get("results", [])
        ]

        summary = GateSummary(
            results=results,
            pass_count=summary_data.get("pass_count", 0),
            fail_count=summary_data.get("fail_count", 0),
            check_count=summary_data.get("check_count", 0),
            timestamp=datetime.fromisoformat(
                summary_data.get("timestamp", datetime.now(UTC).isoformat())
            ),
        )

        return cls(
            checkpoint_id=data.get("checkpoint_id", ""),
            timestamp=datetime.fromisoformat(
                data.get("timestamp", datetime.now(UTC).isoformat())
            ),
            summary=summary,
            metadata=data.get("metadata", {}),
            archived_path=data.get("archived_path"),
        )


class EvidenceCollector:
    """Collects and manages checkpoint evidence.

    This class handles:
    - Collecting evidence from gate checks
    - Storing evidence in Redis
    - Formatting evidence for Discord notifications
    - Archiving evidence to files
    """

    # Redis key prefixes
    REDIS_KEY_PREFIX = "bmad:chiseai:checkpoint"
    REDIS_HISTORY_KEY = f"{REDIS_KEY_PREFIX}:history"
    REDIS_LATEST_KEY = f"{REDIS_KEY_PREFIX}:latest"

    def __init__(
        self,
        redis_client: Any | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
        archive_dir: str | None = None,
    ):
        """Initialize the evidence collector.

        Args:
            redis_client: Optional Redis client instance
            redis_host: Redis host (defaults to env or host.docker.internal)
            redis_port: Redis port (defaults to env or 6380)
            archive_dir: Directory for archiving evidence files
        """
        self._redis = redis_client
        self._redis_host = redis_host or os.getenv(
            "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
        )
        self._redis_port = redis_port or int(
            os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380"))
        )
        self._archive_dir = archive_dir or os.getenv(
            "CHECKPOINT_ARCHIVE_DIR", "logs/checkpoints"
        )

    def _get_redis(self) -> Any | None:
        """Get or create Redis connection."""
        if self._redis is not None:
            return self._redis

        try:
            import redis as redis_lib

            self._redis = redis_lib.Redis(
                host=self._redis_host,
                port=self._redis_port,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            return self._redis
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return None

    def _generate_checkpoint_id(self) -> str:
        """Generate unique checkpoint ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return f"checkpoint-{timestamp}"

    def collect(
        self,
        summary: GateSummary,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointEvidence:
        """Collect evidence from a gate summary.

        Args:
            summary: GateSummary from running all gate checks
            metadata: Optional metadata to attach to evidence

        Returns:
            CheckpointEvidence object with all collected data
        """
        checkpoint_id = self._generate_checkpoint_id()

        evidence = CheckpointEvidence(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(UTC),
            summary=summary,
            metadata=metadata or {},
        )

        logger.info(f"Collected evidence for checkpoint {checkpoint_id}")
        return evidence

    def store_in_redis(self, evidence: CheckpointEvidence) -> bool:
        """Store evidence in Redis.

        Stores:
        - Latest checkpoint in bmad:chiseai:checkpoint:latest
        - Historical record in bmad:chiseai:checkpoint:history (list)

        Args:
            evidence: CheckpointEvidence to store

        Returns:
            True if stored successfully, False otherwise
        """
        r = self._get_redis()
        if not r:
            logger.error("Redis unavailable - cannot store evidence")
            return False

        try:
            evidence_data = json.dumps(evidence.to_dict())

            # Store as latest
            r.set(self.REDIS_LATEST_KEY, evidence_data)

            # Add to history list (keep last 100)
            r.lpush(self.REDIS_HISTORY_KEY, evidence_data)
            r.ltrim(self.REDIS_HISTORY_KEY, 0, 99)

            logger.info(f"Stored evidence {evidence.checkpoint_id} in Redis")
            return True

        except Exception as e:
            logger.error(f"Failed to store evidence in Redis: {e}")
            return False

    def archive_to_file(self, evidence: CheckpointEvidence) -> str | None:
        """Archive evidence to a file.

        Args:
            evidence: CheckpointEvidence to archive

        Returns:
            Path to archived file if successful, None otherwise
        """
        try:
            # Create archive directory
            archive_path = Path(self._archive_dir)
            archive_path.mkdir(parents=True, exist_ok=True)

            # Generate filename
            date_dir = evidence.timestamp.strftime("%Y/%m/%d")
            date_path = archive_path / date_dir
            date_path.mkdir(parents=True, exist_ok=True)

            filename = f"{evidence.checkpoint_id}.json"
            file_path = date_path / filename

            # Write evidence to file
            with open(file_path, "w") as f:
                json.dump(evidence.to_dict(), f, indent=2)

            evidence.archived_path = str(file_path)
            logger.info(f"Archived evidence to {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"Failed to archive evidence: {e}")
            return None

    def format_for_discord(self, evidence: CheckpointEvidence) -> str:
        """Format evidence as Discord message.

        Args:
            evidence: CheckpointEvidence to format

        Returns:
            Formatted Discord message string
        """
        summary = evidence.summary
        timestamp = evidence.timestamp.strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            f"**📊 Burn-in Checkpoint** | {timestamp}",
            f"**ID:** `{evidence.checkpoint_id}`",
            "",
            f"**Gate Status:** {summary.pass_count} ✅ | {summary.check_count} ⚠️ | {summary.fail_count} ❌",
            "",
        ]

        for result in summary.results:
            lines.append(f"**{result.gate}:** {result.status} - {result.detail}")

        # Add metadata if present
        if evidence.metadata:
            lines.extend(["", "**Metadata:**"])
            for key, value in evidence.metadata.items():
                lines.append(f"  {key}: {value}")

        lines.extend(["", "_Next checkpoint in 6 hours_"])

        return "\n".join(lines)

    def format_compact(self, evidence: CheckpointEvidence) -> str:
        """Format evidence in compact form for logging.

        Args:
            evidence: CheckpointEvidence to format

        Returns:
            Compact formatted string
        """
        summary = evidence.summary
        status_emoji = {
            "PASS": "✅",
            "FAIL": "❌",
            "CHECK": "⚠️",
        }.get(summary.overall_status, "❓")

        return (
            f"[{status_emoji}] Checkpoint {evidence.checkpoint_id}: "
            f"{summary.pass_count} pass, {summary.check_count} check, {summary.fail_count} fail"
        )

    def get_latest_from_redis(self) -> CheckpointEvidence | None:
        """Retrieve latest checkpoint evidence from Redis.

        Returns:
            CheckpointEvidence if found, None otherwise
        """
        r = self._get_redis()
        if not r:
            return None

        try:
            data = r.get(self.REDIS_LATEST_KEY)
            if data:
                return CheckpointEvidence.from_dict(json.loads(data))
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve latest evidence: {e}")
            return None

    def get_history_from_redis(
        self,
        limit: int = 10,
        offset: int = 0,
    ) -> list[CheckpointEvidence]:
        """Retrieve checkpoint history from Redis.

        Args:
            limit: Maximum number of records to retrieve
            offset: Offset for pagination

        Returns:
            List of CheckpointEvidence objects
        """
        r = self._get_redis()
        if not r:
            return []

        try:
            data_list = r.lrange(self.REDIS_HISTORY_KEY, offset, offset + limit - 1)
            evidence_list = []
            for data in data_list:
                try:
                    evidence_list.append(CheckpointEvidence.from_dict(json.loads(data)))
                except Exception as e:
                    logger.warning(f"Failed to parse history entry: {e}")
            return evidence_list
        except Exception as e:
            logger.error(f"Failed to retrieve history: {e}")
            return []

    def collect_and_store(
        self,
        summary: GateSummary,
        metadata: dict[str, Any] | None = None,
        archive: bool = True,
    ) -> CheckpointEvidence:
        """Collect evidence and store in all locations.

        This is a convenience method that:
        1. Collects evidence from the summary
        2. Stores in Redis
        3. Archives to file (if archive=True)

        Args:
            summary: GateSummary from running all gate checks
            metadata: Optional metadata to attach
            archive: Whether to archive to file

        Returns:
            CheckpointEvidence object
        """
        evidence = self.collect(summary, metadata)

        # Store in Redis
        self.store_in_redis(evidence)

        # Archive to file
        if archive:
            self.archive_to_file(evidence)

        return evidence
