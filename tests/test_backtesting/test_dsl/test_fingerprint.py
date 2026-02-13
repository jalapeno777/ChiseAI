"""Tests for DSL fingerprint and reproducibility."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


from src.backtesting.dsl.fingerprint import (
    ConfigDiff,
    DiffEntry,
    DSLFingerprint,
    compute_dsl_fingerprint,
    compute_dsl_fingerprint_short,
    configs_equal,
    diff_configs,
    get_fingerprint_metadata,
)

from tests.test_backtesting.test_dsl.fixtures import create_valid_config  # noqa: E402


class TestComputeDSLFingerprint:
    """Tests for compute_dsl_fingerprint function."""

    def test_same_config_same_hash(self):
        """Test that same config produces same hash."""
        config = create_valid_config()

        hash1 = compute_dsl_fingerprint(config)
        hash2 = compute_dsl_fingerprint(config)

        assert hash1 == hash2

    def test_equivalent_configs_same_hash(self):
        """Test that equivalent configs produce same hash."""
        config1 = create_valid_config()
        config2 = create_valid_config()

        hash1 = compute_dsl_fingerprint(config1)
        hash2 = compute_dsl_fingerprint(config2)

        assert hash1 == hash2

    def test_different_configs_different_hash(self):
        """Test that different configs produce different hashes."""
        config1 = create_valid_config()
        config2 = create_valid_config()
        config2["metadata"]["name"] = "DifferentName"

        hash1 = compute_dsl_fingerprint(config1)
        hash2 = compute_dsl_fingerprint(config2)

        assert hash1 != hash2

    def test_key_order_does_not_affect_hash(self):
        """Test that key ordering doesn't affect hash."""
        config1 = {"a": 1, "b": 2, "c": 3}
        config2 = {"c": 3, "a": 1, "b": 2}

        hash1 = compute_dsl_fingerprint(config1)
        hash2 = compute_dsl_fingerprint(config2)

        assert hash1 == hash2

    def test_hash_is_hex_string(self):
        """Test that hash is a valid hex string."""
        config = create_valid_config()
        hash_str = compute_dsl_fingerprint(config)

        # Should be 64 characters (SHA-256 hex)
        assert len(hash_str) == 64

        # Should be valid hex
        int(hash_str, 16)

    def test_short_fingerprint(self):
        """Test short fingerprint generation."""
        config = create_valid_config()

        short = compute_dsl_fingerprint_short(config)
        full = compute_dsl_fingerprint(config)

        assert short == full[:16]
        assert len(short) == 16

    def test_short_fingerprint_custom_length(self):
        """Test short fingerprint with custom length."""
        config = create_valid_config()

        short = compute_dsl_fingerprint_short(config, length=8)

        assert len(short) == 8


class TestDiffConfigs:
    """Tests for diff_configs function."""

    def test_identical_configs_no_diff(self):
        """Test that identical configs have no diff."""
        config1 = create_valid_config()
        config2 = create_valid_config()

        diff = diff_configs(config1, config2)

        assert diff.has_changes is False
        assert len(diff.additions) == 0
        assert len(diff.removals) == 0
        assert len(diff.modifications) == 0

    def test_modified_field_detected(self):
        """Test detection of modified fields."""
        config1 = create_valid_config()
        config2 = create_valid_config()
        config2["metadata"]["name"] = "ModifiedName"

        diff = diff_configs(config1, config2)

        assert diff.has_changes is True
        assert len(diff.modifications) == 1

        mod = diff.modifications[0]
        assert mod.path == "metadata.name"
        assert mod.operation == "modified"
        assert mod.old_value == config1["metadata"]["name"]
        assert mod.new_value == "ModifiedName"

    def test_added_field_detected(self):
        """Test detection of added fields."""
        config1 = {"existing": "value"}
        config2 = {"existing": "value", "new": "field"}

        diff = diff_configs(config1, config2)

        assert diff.has_changes is True
        assert len(diff.additions) == 1

        addition = diff.additions[0]
        assert addition.path == "new"
        assert addition.operation == "added"
        assert addition.new_value == "field"

    def test_removed_field_detected(self):
        """Test detection of removed fields."""
        config1 = {"keep": "value", "remove": "me"}
        config2 = {"keep": "value"}

        diff = diff_configs(config1, config2)

        assert diff.has_changes is True
        assert len(diff.removals) == 1

        removal = diff.removals[0]
        assert removal.path == "remove"
        assert removal.operation == "removed"
        assert removal.old_value == "me"

    def test_nested_diff(self):
        """Test diff of nested structures."""
        config1 = {"level1": {"level2": {"value": 1}}}
        config2 = {"level1": {"level2": {"value": 2}}}

        diff = diff_configs(config1, config2)

        assert diff.has_changes is True
        assert len(diff.modifications) == 1
        assert diff.modifications[0].path == "level1.level2.value"

    def test_list_diff(self):
        """Test diff of list fields."""
        config1 = {"items": [1, 2, 3]}
        config2 = {"items": [1, 2, 4]}

        diff = diff_configs(config1, config2)

        assert diff.has_changes is True
        assert len(diff.modifications) == 1
        assert diff.modifications[0].path == "items[2]"

    def test_diff_to_dict(self):
        """Test converting diff to dictionary."""
        config1 = {"a": 1}
        config2 = {"a": 2}

        diff = diff_configs(config1, config2)
        data = diff.to_dict()

        assert "has_changes" in data
        assert "additions" in data
        assert "removals" in data
        assert "modifications" in data
        assert "addition_count" in data


class TestConfigsEqual:
    """Tests for configs_equal function."""

    def test_equal_configs(self):
        """Test that equal configs return True."""
        config1 = create_valid_config()
        config2 = create_valid_config()

        assert configs_equal(config1, config2) is True

    def test_unequal_configs(self):
        """Test that unequal configs return False."""
        config1 = create_valid_config()
        config2 = create_valid_config()
        config2["metadata"]["name"] = "Different"

        assert configs_equal(config1, config2) is False


class TestDSLFingerprint:
    """Tests for DSLFingerprint class."""

    def test_create_fingerprint(self):
        """Test creating fingerprint object."""
        config = create_valid_config()
        fp = DSLFingerprint(config)

        assert fp.config == config
        assert fp.hash is not None
        assert len(fp.hash) == 64

    def test_fingerprint_hash_cached(self):
        """Test that hash is cached."""
        config = create_valid_config()
        fp = DSLFingerprint(config)

        hash1 = fp.hash
        hash2 = fp.hash

        assert hash1 is hash2  # Same object due to caching

    def test_fingerprint_short_hash(self):
        """Test short hash property."""
        config = create_valid_config()
        fp = DSLFingerprint(config)

        assert fp.short_hash == fp.hash[:16]

    def test_fingerprint_diff_with_another_fingerprint(self):
        """Test diff with another fingerprint."""
        config1 = create_valid_config()
        config2 = create_valid_config()
        config2["metadata"]["name"] = "Different"

        fp1 = DSLFingerprint(config1)
        fp2 = DSLFingerprint(config2)

        diff = fp1.diff(fp2)

        assert diff.has_changes is True

    def test_fingerprint_diff_with_dict(self):
        """Test diff with dict."""
        config1 = create_valid_config()
        config2 = create_valid_config()
        config2["metadata"]["name"] = "Different"

        fp = DSLFingerprint(config1)
        diff = fp.diff(config2)

        assert diff.has_changes is True

    def test_fingerprint_equals_with_fingerprint(self):
        """Test equals with another fingerprint."""
        config1 = create_valid_config()
        config2 = create_valid_config()

        fp1 = DSLFingerprint(config1)
        fp2 = DSLFingerprint(config2)

        assert fp1.equals(fp2) is True

    def test_fingerprint_equals_with_dict(self):
        """Test equals with dict."""
        config1 = create_valid_config()
        config2 = create_valid_config()

        fp = DSLFingerprint(config1)

        assert fp.equals(config2) is True

    def test_fingerprint_to_dict(self):
        """Test converting fingerprint to dict."""
        config = create_valid_config()
        fp = DSLFingerprint(config)

        data = fp.to_dict()

        assert "hash" in data
        assert "short_hash" in data
        assert "canonical" in data


class TestGetFingerprintMetadata:
    """Tests for get_fingerprint_metadata function."""

    def test_metadata_structure(self):
        """Test metadata structure."""
        config = create_valid_config()
        metadata = get_fingerprint_metadata(config)

        assert "hash" in metadata
        assert "short_hash" in metadata
        assert "canonical_size_bytes" in metadata
        assert "canonical_json" in metadata

        assert isinstance(metadata["canonical_size_bytes"], int)
        assert metadata["canonical_size_bytes"] > 0

    def test_hash_in_metadata(self):
        """Test that hash is included in metadata."""
        config = create_valid_config()
        metadata = get_fingerprint_metadata(config)

        expected_hash = compute_dsl_fingerprint(config)
        assert metadata["hash"] == expected_hash


class TestDiffEntry:
    """Tests for DiffEntry dataclass."""

    def test_create_diff_entry(self):
        """Test creating diff entry."""
        entry = DiffEntry(
            path="test.path",
            operation="modified",
            old_value="old",
            new_value="new",
        )

        assert entry.path == "test.path"
        assert entry.operation == "modified"
        assert entry.old_value == "old"
        assert entry.new_value == "new"

    def test_diff_entry_to_dict(self):
        """Test converting diff entry to dict."""
        entry = DiffEntry(
            path="test.path",
            operation="added",
            old_value=None,
            new_value="value",
        )

        data = entry.to_dict()

        assert data["path"] == "test.path"
        assert data["operation"] == "added"
        assert data["old_value"] is None
        assert data["new_value"] == "value"


class TestConfigDiff:
    """Tests for ConfigDiff dataclass."""

    def test_create_config_diff(self):
        """Test creating config diff."""
        entry = DiffEntry(path="test", operation="modified", old_value=1, new_value=2)

        diff = ConfigDiff(
            has_changes=True,
            additions=[],
            removals=[],
            modifications=[entry],
            all_changes=[entry],
        )

        assert diff.has_changes is True
        assert len(diff.modifications) == 1

    def test_config_diff_no_changes(self):
        """Test config diff with no changes."""
        diff = ConfigDiff(
            has_changes=False,
            additions=[],
            removals=[],
            modifications=[],
            all_changes=[],
        )

        assert diff.has_changes is False
        assert len(diff.all_changes) == 0
