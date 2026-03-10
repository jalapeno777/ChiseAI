"""Smoke tests for brain versioning module.

Verifies basic functionality and imports for the versioning system.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from brain.versioning import (
    BrainVersion,
    InvalidVersionError,
    VersionEntry,
    VersionError,
    VersionManager,
    VersionNotFoundError,
)


class TestBrainVersionSmoke:
    """Smoke tests for BrainVersion class."""

    def test_version_creation(self) -> None:
        """Test creating a version."""
        version = BrainVersion(major=1, minor=2, patch=3)
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3

    def test_version_from_string(self) -> None:
        """Test parsing version from string."""
        version = BrainVersion.from_string("1.2.3")
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3

    def test_version_string_invalid(self) -> None:
        """Test invalid version string raises error."""
        with pytest.raises(InvalidVersionError):
            BrainVersion.from_string("invalid")

    def test_version_comparison(self) -> None:
        """Test version comparison."""
        v1 = BrainVersion(1, 0, 0)
        v2 = BrainVersion(1, 1, 0)
        v3 = BrainVersion(2, 0, 0)

        assert v1 < v2
        assert v2 < v3
        assert v1 < v3

    def test_version_bump(self) -> None:
        """Test version bumping."""
        v = BrainVersion(1, 2, 3)

        major_bump = v.bump_major()
        assert major_bump == BrainVersion(2, 0, 0)

        minor_bump = v.bump_minor()
        assert minor_bump == BrainVersion(1, 3, 0)

        patch_bump = v.bump_patch()
        assert patch_bump == BrainVersion(1, 2, 4)

    def test_version_compatibility(self) -> None:
        """Test version compatibility check."""
        v1 = BrainVersion(1, 0, 0)
        v2 = BrainVersion(1, 5, 3)
        v3 = BrainVersion(2, 0, 0)

        assert v1.is_compatible_with(v2)
        assert not v1.is_compatible_with(v3)

    def test_version_str_repr(self) -> None:
        """Test string and repr representations."""
        v = BrainVersion(1, 2, 3)
        assert str(v) == "1.2.3"
        assert "BrainVersion" in repr(v)


class TestVersionEntrySmoke:
    """Smoke tests for VersionEntry class."""

    def test_entry_creation(self) -> None:
        """Test creating a version entry."""
        version = BrainVersion(1, 0, 0)
        entry = VersionEntry(
            version=version,
            created_at="2024-01-01T00:00:00Z",
            commit_hash="abc123",
            author="test",
        )

        assert entry.version == version
        assert entry.commit_hash == "abc123"
        assert entry.author == "test"

    def test_entry_to_dict(self) -> None:
        """Test converting entry to dict."""
        version = BrainVersion(1, 0, 0)
        entry = VersionEntry(
            version=version,
            created_at="2024-01-01T00:00:00Z",
        )

        data = entry.to_dict()
        assert data["version"] == "1.0.0"
        assert data["created_at"] == "2024-01-01T00:00:00Z"

    def test_entry_from_dict(self) -> None:
        """Test creating entry from dict."""
        data = {
            "version": "1.2.3",
            "created_at": "2024-01-01T00:00:00Z",
            "commit_hash": "abc123",
            "author": "test",
            "changelog": "Initial release",
            "is_active": True,
        }

        entry = VersionEntry.from_dict(data)
        assert entry.version == BrainVersion(1, 2, 3)
        assert entry.is_active is True


class TestVersionManagerSmoke:
    """Smoke tests for VersionManager class."""

    def test_manager_initialization(self) -> None:
        """Test initializing version manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = VersionManager(tmpdir)
            assert manager.current_version is None
            assert len(manager.version_history) == 0

    def test_initialize_version(self) -> None:
        """Test initializing first version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = VersionManager(tmpdir)
            version = manager.initialize_version("1.0.0")

            assert version == BrainVersion(1, 0, 0)
            assert manager.current_version == version

    def test_version_bumping(self) -> None:
        """Test version bumping through manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = VersionManager(tmpdir)
            manager.initialize_version("1.0.0")

            new_version = manager.bump_minor("Added feature")
            assert new_version == BrainVersion(1, 1, 0)

            new_version = manager.bump_patch("Bug fix")
            assert new_version == BrainVersion(1, 1, 1)

            new_version = manager.bump_major("Breaking change")
            assert new_version == BrainVersion(2, 0, 0)

    def test_list_versions(self) -> None:
        """Test listing all versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = VersionManager(tmpdir)
            manager.initialize_version("1.0.0")
            manager.bump_minor("Feature 1")
            manager.bump_patch("Fix")

            versions = manager.list_versions()
            assert len(versions) == 3

    def test_get_previous_version(self) -> None:
        """Test getting previous version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = VersionManager(tmpdir)
            manager.initialize_version("1.0.0")
            manager.bump_minor("Feature")

            prev = manager.get_previous_version()
            assert prev == BrainVersion(1, 0, 0)

    def test_persistence(self) -> None:
        """Test version persistence across manager instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First instance
            manager1 = VersionManager(tmpdir)
            manager1.initialize_version("1.0.0", commit_hash="abc123")

            # Second instance - should load persisted state
            manager2 = VersionManager(tmpdir)
            assert manager2.current_version == BrainVersion(1, 0, 0)

    def test_version_error_handling(self) -> None:
        """Test error handling for invalid operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = VersionManager(tmpdir)

            # Can't bump before initializing
            with pytest.raises(VersionError):
                manager.bump_patch()

            # Can't initialize twice
            manager.initialize_version("1.0.0")
            with pytest.raises(VersionError):
                manager.initialize_version("2.0.0")


class TestVersionExceptionsSmoke:
    """Smoke tests for version exceptions."""

    def test_version_error_is_exception(self) -> None:
        """Test VersionError is an Exception."""
        assert issubclass(VersionError, Exception)

    def test_invalid_version_error(self) -> None:
        """Test InvalidVersionError is VersionError."""
        assert issubclass(InvalidVersionError, VersionError)

    def test_version_not_found_error(self) -> None:
        """Test VersionNotFoundError is VersionError."""
        assert issubclass(VersionNotFoundError, VersionError)
