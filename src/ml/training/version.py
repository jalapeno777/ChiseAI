"""Training data schema versioning for ChiseAI.

Manages semantic versioning for training data schemas to ensure
backward compatibility and migration paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SchemaVersion:
    """Semantic version for training data schema.

    Attributes:
        major: Major version (breaking changes)
        minor: Minor version (new features, backward compatible)
        patch: Patch version (bug fixes)
    """

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        """Return version string."""
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def from_string(cls, version_str: str) -> SchemaVersion:
        """Parse version from string.

        Args:
            version_str: Version string like "1.0.0"

        Returns:
            SchemaVersion instance

        Raises:
            ValueError: If version string is invalid
        """
        parts = version_str.split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid version string: {version_str}")
        return cls(
            major=int(parts[0]),
            minor=int(parts[1]),
            patch=int(parts[2]),
        )

    def is_compatible_with(self, other: SchemaVersion) -> bool:
        """Check if this version is compatible with another.

        Compatibility rules:
        - Same major version = compatible
        - Different major version = breaking change

        Args:
            other: Version to check compatibility with

        Returns:
            True if compatible, False otherwise
        """
        return self.major == other.major

    def is_newer_than(self, other: SchemaVersion) -> bool:
        """Check if this version is newer than another.

        Args:
            other: Version to compare against

        Returns:
            True if this version is newer
        """
        if self.major != other.major:
            return self.major > other.major
        if self.minor != other.minor:
            return self.minor > other.minor
        return self.patch > other.patch


# Current schema version
CURRENT_SCHEMA_VERSION = SchemaVersion(1, 0, 0)

# Version history with changelog
VERSION_HISTORY: dict[str, dict[str, Any]] = {
    "1.0.0": {
        "date": "2026-02-16",
        "changes": [
            "Initial training data schema",
            "Support for signal features and outcomes",
            "Parquet/CSV/JSON export formats",
        ],
        "breaking": False,
    },
}


class SchemaVersionManager:
    """Manages schema versioning and migrations."""

    def __init__(self, current_version: SchemaVersion | None = None) -> None:
        """Initialize version manager.

        Args:
            current_version: Current schema version (defaults to CURRENT_SCHEMA_VERSION)
        """
        self.current_version = current_version or CURRENT_SCHEMA_VERSION

    def get_version(self) -> SchemaVersion:
        """Get current schema version."""
        return self.current_version

    def get_version_string(self) -> str:
        """Get current version as string."""
        return str(self.current_version)

    def validate_version(self, version_str: str) -> bool:
        """Validate a version string.

        Args:
            version_str: Version string to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            version = SchemaVersion.from_string(version_str)
            return version.is_compatible_with(self.current_version)
        except ValueError:
            return False

    def get_changelog(self, since_version: str | None = None) -> list[dict[str, Any]]:
        """Get changelog entries.

        Args:
            since_version: Only return changes since this version

        Returns:
            List of changelog entries
        """
        if since_version is None:
            return [
                {"version": v, **data} for v, data in sorted(VERSION_HISTORY.items())
            ]

        since = SchemaVersion.from_string(since_version)
        return [
            {"version": v, **data}
            for v, data in sorted(VERSION_HISTORY.items())
            if SchemaVersion.from_string(v).is_newer_than(since)
        ]

    def check_compatibility(self, data_version: str) -> tuple[bool, str]:
        """Check if data version is compatible with current schema.

        Args:
            data_version: Version string from data

        Returns:
            Tuple of (is_compatible, message)
        """
        try:
            data_ver = SchemaVersion.from_string(data_version)
        except ValueError as e:
            return False, f"Invalid version string: {e}"

        if data_ver.is_compatible_with(self.current_version):
            if data_ver.is_newer_than(self.current_version):
                return False, (
                    f"Data version {data_ver} is newer than "
                    f"schema version {self.current_version}"
                )
            return True, f"Compatible: {data_ver} with {self.current_version}"

        return False, (
            f"Incompatible versions: data={data_ver}, "
            f"schema={self.current_version} (different major version)"
        )
