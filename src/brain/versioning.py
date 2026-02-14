"""Brain versioning module.

Provides semantic versioning (MAJOR.MINOR.PATCH) for brain versions,
version tracking, comparison, and increment operations.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


# Constants
VERSION_FILE_NAME = "brain_version.json"
VERSION_HISTORY_FILE = "brain_version_history.json"
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class VersionError(Exception):
    """Base exception for version-related errors."""

    pass


class InvalidVersionError(VersionError):
    """Raised when an invalid version string is provided."""

    pass


class VersionNotFoundError(VersionError):
    """Raised when a version cannot be found."""

    pass


@dataclass(frozen=True, order=True)
class BrainVersion:
    """Represents a semantic version (MAJOR.MINOR.PATCH).

    Attributes:
        major: Major version number (incompatible API changes)
        minor: Minor version number (backward-compatible functionality)
        patch: Patch version number (backward-compatible bug fixes)

    Examples:
        >>> v1 = BrainVersion(1, 2, 3)
        >>> v2 = BrainVersion.from_string("1.2.3")
        >>> v1 == v2
        True
        >>> v1 > BrainVersion(1, 2, 2)
        True
    """

    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        """Validate version components."""
        if self.major < 0 or self.minor < 0 or self.patch < 0:
            raise InvalidVersionError(
                f"Version components must be non-negative: {self}"
            )

    def __str__(self) -> str:
        """Return version as MAJOR.MINOR.PATCH string."""
        return f"{self.major}.{self.minor}.{self.patch}"

    def __repr__(self) -> str:
        """Return detailed representation."""
        return (
            f"BrainVersion(major={self.major}, minor={self.minor}, patch={self.patch})"
        )

    @classmethod
    def from_string(cls, version_str: str) -> BrainVersion:
        """Parse a version string into a BrainVersion.

        Args:
            version_str: Version string in MAJOR.MINOR.PATCH format

        Returns:
            BrainVersion instance

        Raises:
            InvalidVersionError: If version string is invalid
        """
        match = VERSION_PATTERN.match(version_str.strip())
        if not match:
            raise InvalidVersionError(
                f"Invalid version string: '{version_str}'. "
                "Expected format: MAJOR.MINOR.PATCH (e.g., 1.2.3)"
            )

        major, minor, patch = map(int, match.groups())
        return cls(major=major, minor=minor, patch=patch)

    def bump_major(self) -> BrainVersion:
        """Return a new version with incremented major component.

        Minor and patch are reset to 0.
        """
        return BrainVersion(major=self.major + 1, minor=0, patch=0)

    def bump_minor(self) -> BrainVersion:
        """Return a new version with incremented minor component.

        Patch is reset to 0.
        """
        return BrainVersion(major=self.major, minor=self.minor + 1, patch=0)

    def bump_patch(self) -> BrainVersion:
        """Return a new version with incremented patch component."""
        return BrainVersion(major=self.major, minor=self.minor, patch=self.patch + 1)

    def is_compatible_with(self, other: BrainVersion) -> bool:
        """Check if this version is backward-compatible with another.

        Versions are compatible if they have the same major version.
        """
        return self.major == other.major


@dataclass
class VersionEntry:
    """Represents a version entry with metadata."""

    version: BrainVersion
    created_at: str
    commit_hash: str | None = None
    author: str | None = None
    changelog: str | None = None
    is_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": str(self.version),
            "created_at": self.created_at,
            "commit_hash": self.commit_hash,
            "author": self.author,
            "changelog": self.changelog,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VersionEntry:
        """Create from dictionary."""
        return cls(
            version=BrainVersion.from_string(data["version"]),
            created_at=data["created_at"],
            commit_hash=data.get("commit_hash"),
            author=data.get("author"),
            changelog=data.get("changelog"),
            is_active=data.get("is_active", False),
        )


class VersionManager:
    """Manages brain versions with persistence and history tracking.

    Attributes:
        storage_path: Directory path for version files
        current_version: The currently active version
        version_history: List of all registered versions

    Examples:
        >>> manager = VersionManager("/path/to/versions")
        >>> manager.initialize_version("1.0.0")
        >>> manager.bump_minor("Added new feature")
        BrainVersion(major=1, minor=1, patch=0)
    """

    def __init__(self, storage_path: str | Path) -> None:
        """Initialize the version manager.

        Args:
            storage_path: Directory to store version files
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._version_file = self.storage_path / VERSION_FILE_NAME
        self._history_file = self.storage_path / VERSION_HISTORY_FILE
        self._current_version: BrainVersion | None = None
        self._version_history: list[VersionEntry] = []
        self._load_state()

    def _load_state(self) -> None:
        """Load version state from storage."""
        # Load current version
        if self._version_file.exists():
            try:
                with open(self._version_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self._current_version = BrainVersion.from_string(
                        data.get("version", "0.0.0")
                    )
            except (json.JSONDecodeError, InvalidVersionError) as e:
                raise VersionError(f"Failed to load version file: {e}") from e

        # Load version history
        if self._history_file.exists():
            try:
                with open(self._history_file, encoding="utf-8") as f:
                    history_data = json.load(f)
                    self._version_history = [
                        VersionEntry.from_dict(entry)
                        for entry in history_data.get("versions", [])
                    ]
            except (json.JSONDecodeError, KeyError) as e:
                raise VersionError(f"Failed to load version history: {e}") from e

    def _save_state(self) -> None:
        """Save version state to storage."""
        # Save current version
        if self._current_version:
            version_data = {
                "version": str(self._current_version),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self._version_file, "w", encoding="utf-8") as f:
                json.dump(version_data, f, indent=2)

        # Save version history
        history_data = {
            "versions": [entry.to_dict() for entry in self._version_history],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self._history_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2)

    @property
    def current_version(self) -> BrainVersion | None:
        """Get the currently active version."""
        return self._current_version

    @property
    def version_history(self) -> Sequence[VersionEntry]:
        """Get the version history (read-only)."""
        return tuple(self._version_history)

    def initialize_version(
        self,
        version: str | BrainVersion,
        commit_hash: str | None = None,
        author: str | None = None,
        changelog: str | None = None,
    ) -> BrainVersion:
        """Initialize the first version.

        Args:
            version: Initial version (string or BrainVersion)
            commit_hash: Optional git commit hash
            author: Optional author name
            changelog: Optional changelog entry

        Returns:
            The initialized version

        Raises:
            VersionError: If a version already exists
        """
        if self._current_version is not None:
            raise VersionError(
                f"Version already initialized: {self._current_version}. "
                "Use bump methods to create new versions."
            )

        if isinstance(version, str):
            version = BrainVersion.from_string(version)

        self._current_version = version

        entry = VersionEntry(
            version=version,
            created_at=datetime.now(timezone.utc).isoformat(),
            commit_hash=commit_hash,
            author=author,
            changelog=changelog,
            is_active=True,
        )
        self._version_history.append(entry)
        self._save_state()

        return version

    def bump_major(
        self,
        changelog: str | None = None,
        commit_hash: str | None = None,
        author: str | None = None,
    ) -> BrainVersion:
        """Bump the major version.

        Args:
            changelog: Optional changelog entry
            commit_hash: Optional git commit hash
            author: Optional author name

        Returns:
            The new version

        Raises:
            VersionError: If no version is initialized
        """
        if self._current_version is None:
            raise VersionError("No version initialized. Call initialize_version first.")

        new_version = self._current_version.bump_major()
        return self._create_new_version(new_version, changelog, commit_hash, author)

    def bump_minor(
        self,
        changelog: str | None = None,
        commit_hash: str | None = None,
        author: str | None = None,
    ) -> BrainVersion:
        """Bump the minor version.

        Args:
            changelog: Optional changelog entry
            commit_hash: Optional git commit hash
            author: Optional author name

        Returns:
            The new version

        Raises:
            VersionError: If no version is initialized
        """
        if self._current_version is None:
            raise VersionError("No version initialized. Call initialize_version first.")

        new_version = self._current_version.bump_minor()
        return self._create_new_version(new_version, changelog, commit_hash, author)

    def bump_patch(
        self,
        changelog: str | None = None,
        commit_hash: str | None = None,
        author: str | None = None,
    ) -> BrainVersion:
        """Bump the patch version.

        Args:
            changelog: Optional changelog entry
            commit_hash: Optional git commit hash
            author: Optional author name

        Returns:
            The new version

        Raises:
            VersionError: If no version is initialized
        """
        if self._current_version is None:
            raise VersionError("No version initialized. Call initialize_version first.")

        new_version = self._current_version.bump_patch()
        return self._create_new_version(new_version, changelog, commit_hash, author)

    def _create_new_version(
        self,
        new_version: BrainVersion,
        changelog: str | None,
        commit_hash: str | None,
        author: str | None,
    ) -> BrainVersion:
        """Create a new version entry and update state."""
        # Mark previous version as inactive
        for entry in self._version_history:
            entry.is_active = False

        # Create new entry
        entry = VersionEntry(
            version=new_version,
            created_at=datetime.now(timezone.utc).isoformat(),
            commit_hash=commit_hash,
            author=author,
            changelog=changelog,
            is_active=True,
        )
        self._version_history.append(entry)
        self._current_version = new_version
        self._save_state()

        return new_version

    def get_version_entry(self, version: str | BrainVersion) -> VersionEntry | None:
        """Get the entry for a specific version.

        Args:
            version: Version to look up

        Returns:
            VersionEntry if found, None otherwise
        """
        if isinstance(version, str):
            version = BrainVersion.from_string(version)

        for entry in self._version_history:
            if entry.version == version:
                return entry

        return None

    def get_previous_version(self) -> BrainVersion | None:
        """Get the version before the current one.

        Returns:
            Previous version, or None if this is the first version
        """
        if len(self._version_history) < 2:
            return None

        # Return the second-to-last entry (last is current)
        return self._version_history[-2].version

    def list_versions(self) -> Sequence[BrainVersion]:
        """List all versions in chronological order."""
        return tuple(entry.version for entry in self._version_history)

    def compare_versions(self, v1: str | BrainVersion, v2: str | BrainVersion) -> int:
        """Compare two versions.

        Args:
            v1: First version
            v2: Second version

        Returns:
            -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2
        """
        if isinstance(v1, str):
            v1 = BrainVersion.from_string(v1)
        if isinstance(v2, str):
            v2 = BrainVersion.from_string(v2)

        if v1 < v2:
            return -1
        elif v1 > v2:
            return 1
        return 0
