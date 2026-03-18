"""Artifact storage backend for training artifacts.

Provides filesystem-based storage for training artifacts with JSON metadata
serialization and binary file handling for checkpoints.

Storage layout:
    <base_path>/
        <experiment_id>/
            <artifact_id>.json          # Metadata
            <artifact_id>.bin           # Binary payload (checkpoints)
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from ml.training.artifacts.models import (
    ArtifactType,
    CheckpointArtifact,
    ConfigArtifact,
    LogArtifact,
    TrainingArtifact,
)

logger = logging.getLogger(__name__)

# Map artifact types to their concrete classes for deserialization
_ARTIFACT_TYPE_MAP: dict[ArtifactType, type[TrainingArtifact]] = {
    ArtifactType.CHECKPOINT: CheckpointArtifact,
    ArtifactType.CONFIG: ConfigArtifact,
    ArtifactType.LOG: LogArtifact,
}


class ArtifactStorageError(Exception):
    """Raised when artifact storage operations fail."""

    pass


class ArtifactNotFoundError(ArtifactStorageError):
    """Raised when an artifact is not found."""

    pass


class ArtifactStorage:
    """Filesystem-based storage for training artifacts.

    Saves artifact metadata as JSON and handles binary payloads
    (e.g., model checkpoint files) separately.

    Example:
        storage = ArtifactStorage()
        storage.save_artifact(checkpoint, "/data/artifacts")
        loaded = storage.load_artifact("ckpt-001", "/data/artifacts")
    """

    def save_artifact(
        self,
        artifact: TrainingArtifact,
        base_path: str | Path,
        binary_data: bytes | None = None,
    ) -> Path:
        """Save an artifact to disk.

        Args:
            artifact: TrainingArtifact instance to save
            base_path: Root directory for artifact storage
            binary_data: Optional binary payload (e.g., model weights)

        Returns:
            Path to the saved metadata file

        Raises:
            ArtifactStorageError: If save fails
        """
        base = Path(base_path)
        experiment_dir = base / artifact.experiment_id
        experiment_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata as JSON
        meta_path = experiment_dir / f"{artifact.artifact_id}.json"
        try:
            meta_path.write_text(artifact.to_json(), encoding="utf-8")
        except OSError as e:
            raise ArtifactStorageError(f"Failed to write artifact metadata: {e}") from e

        # Save binary data if provided
        if binary_data is not None:
            bin_path = experiment_dir / f"{artifact.artifact_id}.bin"
            try:
                bin_path.write_bytes(binary_data)
            except OSError as e:
                # Clean up partial metadata on failure
                meta_path.unlink(missing_ok=True)
                raise ArtifactStorageError(
                    f"Failed to write artifact binary data: {e}"
                ) from e

        logger.debug(
            "Saved artifact %s (type=%s) to %s",
            artifact.artifact_id,
            artifact.artifact_type.value,
            meta_path,
        )
        return meta_path

    def load_artifact(
        self, artifact_id: str, base_path: str | Path
    ) -> TrainingArtifact:
        """Load an artifact from disk.

        Searches all experiment directories under base_path for the
        given artifact_id.

        Args:
            artifact_id: Unique artifact identifier
            base_path: Root directory for artifact storage

        Returns:
            Loaded TrainingArtifact instance

        Raises:
            ArtifactNotFoundError: If artifact is not found
            ArtifactStorageError: If loading fails
        """
        base = Path(base_path)
        meta_path = self._find_metadata_file(base, artifact_id)

        if meta_path is None:
            raise ArtifactNotFoundError(
                f"Artifact '{artifact_id}' not found under {base}"
            )

        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ArtifactStorageError(f"Failed to read artifact metadata: {e}") from e

        artifact_type = ArtifactType(data.get("artifact_type", "log"))
        cls = _ARTIFACT_TYPE_MAP.get(artifact_type, TrainingArtifact)
        return cls.from_dict(data)

    def load_binary(self, artifact_id: str, base_path: str | Path) -> bytes | None:
        """Load binary data for an artifact.

        Args:
            artifact_id: Unique artifact identifier
            base_path: Root directory for artifact storage

        Returns:
            Binary data bytes, or None if no binary file exists

        Raises:
            ArtifactNotFoundError: If artifact is not found
        """
        base = Path(base_path)
        bin_path = self._find_binary_file(base, artifact_id)

        if bin_path is None:
            return None

        try:
            return bin_path.read_bytes()
        except OSError as e:
            raise ArtifactStorageError(f"Failed to read binary data: {e}") from e

    def list_artifacts(
        self,
        experiment_id: str,
        base_path: str | Path,
        artifact_type: ArtifactType | None = None,
    ) -> list[TrainingArtifact]:
        """List all artifacts for an experiment.

        Args:
            experiment_id: Experiment identifier to filter by
            base_path: Root directory for artifact storage
            artifact_type: Optional type filter

        Returns:
            List of TrainingArtifact instances
        """
        base = Path(base_path)
        experiment_dir = base / experiment_id

        if not experiment_dir.exists():
            return []

        artifacts: list[TrainingArtifact] = []
        for json_file in sorted(experiment_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                atype = ArtifactType(data.get("artifact_type", "log"))
                if artifact_type is not None and atype != artifact_type:
                    continue
                cls = _ARTIFACT_TYPE_MAP.get(atype, TrainingArtifact)
                artifacts.append(cls.from_dict(data))
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning("Skipping corrupt artifact file %s: %s", json_file, e)

        return artifacts

    def list_experiments(self, base_path: str | Path) -> list[str]:
        """List all experiment IDs under base_path.

        Args:
            base_path: Root directory for artifact storage

        Returns:
            Sorted list of experiment ID strings
        """
        base = Path(base_path)
        if not base.exists():
            return []
        return sorted(
            d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")
        )

    def delete_artifact(self, artifact_id: str, base_path: str | Path) -> bool:
        """Delete an artifact from disk (metadata and binary data).

        Args:
            artifact_id: Unique artifact identifier
            base_path: Root directory for artifact storage

        Returns:
            True if artifact was deleted, False if not found
        """
        base = Path(base_path)
        deleted = False

        # Find and remove metadata file
        meta_path = self._find_metadata_file(base, artifact_id)
        if meta_path is not None:
            meta_path.unlink()
            deleted = True

        # Find and remove binary file
        bin_path = self._find_binary_file(base, artifact_id)
        if bin_path is not None:
            bin_path.unlink()
            deleted = True

        return deleted

    def delete_experiment(self, experiment_id: str, base_path: str | Path) -> bool:
        """Delete an entire experiment directory and all its artifacts.

        Args:
            experiment_id: Experiment identifier
            base_path: Root directory for artifact storage

        Returns:
            True if experiment was deleted, False if not found
        """
        experiment_dir = Path(base_path) / experiment_id
        if not experiment_dir.exists():
            return False
        shutil.rmtree(experiment_dir)
        return True

    def _find_metadata_file(self, base: Path, artifact_id: str) -> Path | None:
        """Search for a metadata JSON file by artifact_id."""
        if not base.exists():
            return None
        for experiment_dir in base.iterdir():
            if not experiment_dir.is_dir():
                continue
            candidate = experiment_dir / f"{artifact_id}.json"
            if candidate.exists():
                return candidate
        return None

    def _find_binary_file(self, base: Path, artifact_id: str) -> Path | None:
        """Search for a binary file by artifact_id."""
        if not base.exists():
            return None
        for experiment_dir in base.iterdir():
            if not experiment_dir.is_dir():
                continue
            candidate = experiment_dir / f"{artifact_id}.bin"
            if candidate.exists():
                return candidate
        return None
