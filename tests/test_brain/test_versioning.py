"""Tests for brain versioning module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from brain.versioning import (
    BrainVersion,
    InvalidVersionError,
    VersionEntry,
    VersionError,
    VersionManager,
)


class TestBrainVersion:
    """Tests for BrainVersion class."""

    def test_creation(self) -> None:
        """Test basic version creation."""
        v = BrainVersion(1, 2, 3)
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_string_representation(self) -> None:
        """Test string conversion."""
        v = BrainVersion(1, 2, 3)
        assert str(v) == "1.2.3"
        assert repr(v) == "BrainVersion(major=1, minor=2, patch=3)"

    def test_from_string_valid(self) -> None:
        """Test parsing valid version strings."""
        v = BrainVersion.from_string("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

        v = BrainVersion.from_string("  2.10.0  ")
        assert v.major == 2
        assert v.minor == 10
        assert v.patch == 0

    def test_from_string_invalid(self) -> None:
        """Test parsing invalid version strings."""
        with pytest.raises(InvalidVersionError):
            BrainVersion.from_string("invalid")

        with pytest.raises(InvalidVersionError):
            BrainVersion.from_string("1.2")

        with pytest.raises(InvalidVersionError):
            BrainVersion.from_string("1.2.3.4")

    def test_negative_components(self) -> None:
        """Test that negative components are rejected."""
        with pytest.raises(InvalidVersionError):
            BrainVersion(-1, 0, 0)

    def test_bump_major(self) -> None:
        """Test major version bump."""
        v = BrainVersion(1, 2, 3)
        new_v = v.bump_major()
        assert new_v.major == 2
        assert new_v.minor == 0
        assert new_v.patch == 0

    def test_bump_minor(self) -> None:
        """Test minor version bump."""
        v = BrainVersion(1, 2, 3)
        new_v = v.bump_minor()
        assert new_v.major == 1
        assert new_v.minor == 3
        assert new_v.patch == 0

    def test_bump_patch(self) -> None:
        """Test patch version bump."""
        v = BrainVersion(1, 2, 3)
        new_v = v.bump_patch()
        assert new_v.major == 1
        assert new_v.minor == 2
        assert new_v.patch == 4

    def test_comparison(self) -> None:
        """Test version comparison."""
        v1 = BrainVersion(1, 0, 0)
        v2 = BrainVersion(1, 0, 1)
        v3 = BrainVersion(1, 1, 0)
        v4 = BrainVersion(2, 0, 0)

        assert v1 < v2 < v3 < v4
        assert v4 > v3 > v2 > v1
        assert v1 == BrainVersion(1, 0, 0)

    def test_is_compatible_with(self) -> None:
        """Test compatibility check."""
        v1 = BrainVersion(1, 0, 0)
        v2 = BrainVersion(1, 5, 3)
        v3 = BrainVersion(2, 0, 0)

        assert v1.is_compatible_with(v2)
        assert v2.is_compatible_with(v1)
        assert not v1.is_compatible_with(v3)


class TestVersionEntry:
    """Tests for VersionEntry class."""

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        entry = VersionEntry(
            version=BrainVersion(1, 0, 0),
            created_at="2024-01-01T00:00:00Z",
            commit_hash="abc123",
            author="test",
            is_active=True,
        )

        data = entry.to_dict()
        assert data["version"] == "1.0.0"
        assert data["created_at"] == "2024-01-01T00:00:00Z"
        assert data["commit_hash"] == "abc123"
        assert data["author"] == "test"
        assert data["is_active"] is True

    def test_from_dict(self) -> None:
        """Test deserialization from dict."""
        data = {
            "version": "1.2.3",
            "created_at": "2024-01-01T00:00:00Z",
            "commit_hash": "abc123",
            "author": "test",
            "is_active": True,
        }

        entry = VersionEntry.from_dict(data)
        assert entry.version == BrainVersion(1, 2, 3)
        assert entry.created_at == "2024-01-01T00:00:00Z"
        assert entry.commit_hash == "abc123"


class TestVersionManager:
    """Tests for VersionManager class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for version storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_initialization(self, temp_dir: str) -> None:
        """Test manager initialization."""
        manager = VersionManager(temp_dir)
        assert manager.current_version is None
        assert len(manager.version_history) == 0

    def test_initialize_version(self, temp_dir: str) -> None:
        """Test version initialization."""
        manager = VersionManager(temp_dir)
        version = manager.initialize_version("1.0.0", commit_hash="abc123")

        assert version == BrainVersion(1, 0, 0)
        assert manager.current_version == version
        assert len(manager.version_history) == 1

    def test_initialize_already_initialized(self, temp_dir: str) -> None:
        """Test that double initialization raises error."""
        manager = VersionManager(temp_dir)
        manager.initialize_version("1.0.0")

        with pytest.raises(VersionError):
            manager.initialize_version("2.0.0")

    def test_bump_patch(self, temp_dir: str) -> None:
        """Test patch version bump."""
        manager = VersionManager(temp_dir)
        manager.initialize_version("1.0.0")
        new_version = manager.bump_patch(changelog="Bug fix")

        assert new_version == BrainVersion(1, 0, 1)
        assert manager.current_version == new_version
        assert len(manager.version_history) == 2

    def test_bump_minor(self, temp_dir: str) -> None:
        """Test minor version bump."""
        manager = VersionManager(temp_dir)
        manager.initialize_version("1.0.0")
        new_version = manager.bump_minor(changelog="New feature")

        assert new_version == BrainVersion(1, 1, 0)
        assert manager.current_version == new_version

    def test_bump_major(self, temp_dir: str) -> None:
        """Test major version bump."""
        manager = VersionManager(temp_dir)
        manager.initialize_version("1.0.0")
        new_version = manager.bump_major(changelog="Breaking change")

        assert new_version == BrainVersion(2, 0, 0)
        assert manager.current_version == new_version

    def test_bump_without_initialization(self, temp_dir: str) -> None:
        """Test that bump without initialization raises error."""
        manager = VersionManager(temp_dir)

        with pytest.raises(VersionError):
            manager.bump_patch()

    def test_get_version_entry(self, temp_dir: str) -> None:
        """Test retrieving version entry."""
        manager = VersionManager(temp_dir)
        manager.initialize_version("1.0.0", commit_hash="abc123")

        entry = manager.get_version_entry("1.0.0")
        assert entry is not None
        assert entry.version == BrainVersion(1, 0, 0)
        assert entry.commit_hash == "abc123"

        # Non-existent version
        assert manager.get_version_entry("2.0.0") is None

    def test_get_previous_version(self, temp_dir: str) -> None:
        """Test getting previous version."""
        manager = VersionManager(temp_dir)
        manager.initialize_version("1.0.0")
        manager.bump_minor()

        prev = manager.get_previous_version()
        assert prev == BrainVersion(1, 0, 0)

    def test_list_versions(self, temp_dir: str) -> None:
        """Test listing all versions."""
        manager = VersionManager(temp_dir)
        manager.initialize_version("1.0.0")
        manager.bump_minor()
        manager.bump_patch()

        versions = manager.list_versions()
        assert len(versions) == 3
        assert versions[0] == BrainVersion(1, 0, 0)
        assert versions[1] == BrainVersion(1, 1, 0)
        assert versions[2] == BrainVersion(1, 1, 1)

    def test_compare_versions(self, temp_dir: str) -> None:
        """Test version comparison."""
        manager = VersionManager(temp_dir)

        assert manager.compare_versions("1.0.0", "1.0.1") == -1
        assert manager.compare_versions("1.0.0", "1.0.0") == 0
        assert manager.compare_versions("1.1.0", "1.0.0") == 1

    def test_persistence(self, temp_dir: str) -> None:
        """Test that versions persist across manager instances."""
        # Create and populate first manager
        manager1 = VersionManager(temp_dir)
        manager1.initialize_version("1.0.0", commit_hash="abc123")
        manager1.bump_minor()

        # Create second manager pointing to same directory
        manager2 = VersionManager(temp_dir)
        assert manager2.current_version == BrainVersion(1, 1, 0)
        assert len(manager2.version_history) == 2

    def test_version_files_created(self, temp_dir: str) -> None:
        """Test that version files are created."""
        manager = VersionManager(temp_dir)
        manager.initialize_version("1.0.0")

        version_file = Path(temp_dir) / "brain_version.json"
        history_file = Path(temp_dir) / "brain_version_history.json"

        assert version_file.exists()
        assert history_file.exists()

        # Verify content
        with open(version_file) as f:
            data = json.load(f)
            assert data["version"] == "1.0.0"
