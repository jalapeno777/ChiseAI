"""Tests for DSL version migration."""

import pytest

from src.backtesting.dsl.migration import (
    DSLMigration,
    MigrationStep,
    migrate_config,
    get_config_version,
    can_migrate,
)


class TestMigrationStep:
    """Tests for MigrationStep dataclass."""

    def test_create_migration_step(self):
        """Test creating migration step."""

        def migrate_func(config):
            config["version"] = "2.0.0"
            return config

        step = MigrationStep(
            from_version="1.0.0",
            to_version="2.0.0",
            description="Test migration",
            migrate_func=migrate_func,
        )

        assert step.from_version == "1.0.0"
        assert step.to_version == "2.0.0"
        assert step.description == "Test migration"

    def test_apply_migration_step(self):
        """Test applying migration step."""

        def migrate_func(config):
            config["migrated"] = True
            return config

        step = MigrationStep(
            from_version="1.0.0",
            to_version="2.0.0",
            description="Test",
            migrate_func=migrate_func,
        )

        config = {"version": "1.0.0"}
        result = step.apply(config)

        assert result["migrated"] is True
        assert result["version"] == "1.0.0"  # Original unchanged


class TestDSLMigration:
    """Tests for DSLMigration class."""

    def test_create_migration_manager(self):
        """Test creating migration manager."""
        migration = DSLMigration()

        assert migration is not None
        assert "1.0.0" in migration.VERSIONS

    def test_get_version_from_config(self):
        """Test extracting version from config."""
        migration = DSLMigration()
        config = {"metadata": {"version": "1.0.0"}}

        version = migration.get_version(config)

        assert version == "1.0.0"

    def test_get_version_default(self):
        """Test default version when not specified."""
        migration = DSLMigration()
        config = {"metadata": {}}

        version = migration.get_version(config)

        assert version == "1.0.0"

    def test_set_version(self):
        """Test setting version in config."""
        migration = DSLMigration()
        config = {"metadata": {"version": "1.0.0"}}

        result = migration.set_version(config, "2.0.0")

        assert result["metadata"]["version"] == "2.0.0"

    def test_set_version_creates_metadata(self):
        """Test that set_version creates metadata if missing."""
        migration = DSLMigration()
        config = {}

        result = migration.set_version(config, "2.0.0")

        assert "metadata" in result
        assert result["metadata"]["version"] == "2.0.0"

    def test_migrate_same_version(self):
        """Test migration to same version returns copy."""
        migration = DSLMigration()
        config = {"metadata": {"version": "1.0.0"}, "data": "test"}

        result = migration.migrate(config, "1.0.0", "1.0.0")

        assert result == config
        assert result is not config  # Should be a copy

    def test_get_migration_path_same_version(self):
        """Test getting path for same version."""
        migration = DSLMigration()

        path = migration.get_migration_path("1.0.0", "1.0.0")

        assert path == ["1.0.0"]

    def test_get_migration_path_upgrade(self):
        """Test getting path for upgrade."""
        migration = DSLMigration()

        # Add a second version for testing
        migration.VERSIONS = ["1.0.0", "2.0.0"]

        path = migration.get_migration_path("1.0.0", "2.0.0")

        assert path == ["1.0.0", "2.0.0"]

    def test_get_migration_path_downgrade_raises(self):
        """Test that downgrade raises error."""
        migration = DSLMigration()
        migration.VERSIONS = ["1.0.0", "2.0.0"]

        with pytest.raises(ValueError, match="Downgrade"):
            migration.get_migration_path("2.0.0", "1.0.0")

    def test_can_migrate_same_version(self):
        """Test can_migrate for same version."""
        migration = DSLMigration()

        assert migration.can_migrate("1.0.0", "1.0.0") is True

    def test_can_migrate_upgrade(self):
        """Test can_migrate for upgrade."""
        migration = DSLMigration()
        migration.VERSIONS = ["1.0.0", "2.0.0"]

        assert migration.can_migrate("1.0.0", "2.0.0") is True

    def test_can_migrate_downgrade(self):
        """Test can_migrate for downgrade."""
        migration = DSLMigration()
        migration.VERSIONS = ["1.0.0", "2.0.0"]

        assert migration.can_migrate("2.0.0", "1.0.0") is False

    def test_get_supported_versions(self):
        """Test getting supported versions."""
        migration = DSLMigration()

        versions = migration.get_supported_versions()

        assert "1.0.0" in versions

    def test_register_migration(self):
        """Test registering custom migration."""
        migration = DSLMigration()

        def custom_migrate(config):
            config["custom"] = True
            return config

        migration.register_migration(
            from_version="1.0.0",
            to_version="2.0.0",
            description="Custom migration",
            migrate_func=custom_migrate,
        )

        assert ("1.0.0", "2.0.0") in migration._migrations

    def test_get_migration_info(self):
        """Test getting migration info."""
        migration = DSLMigration()
        migration.VERSIONS = ["1.0.0", "2.0.0"]

        info = migration.get_migration_info("1.0.0", "2.0.0")

        assert info["can_migrate"] is True
        assert "path" in info
        assert "steps" in info
        assert info["step_count"] >= 0

    def test_get_migration_info_downgrade(self):
        """Test getting migration info for downgrade."""
        migration = DSLMigration()
        migration.VERSIONS = ["1.0.0", "2.0.0"]

        info = migration.get_migration_info("2.0.0", "1.0.0")

        assert info["can_migrate"] is False
        assert "error" in info


class TestUtilityFunctions:
    """Tests for migration utility functions."""

    def test_migrate_config_function(self):
        """Test migrate_config utility function."""
        config = {"metadata": {"version": "1.0.0"}}

        # Same version should return copy
        result = migrate_config(config, "1.0.0", "1.0.0")

        assert result["metadata"]["version"] == "1.0.0"

    def test_get_config_version_function(self):
        """Test get_config_version utility function."""
        config = {"metadata": {"version": "1.0.0"}}

        version = get_config_version(config)

        assert version == "1.0.0"

    def test_can_migrate_function(self):
        """Test can_migrate utility function."""
        assert can_migrate("1.0.0", "1.0.0") is True


class TestVersionKeySorting:
    """Tests for version key sorting."""

    def test_version_key_sorting(self):
        """Test that versions are sorted correctly."""
        migration = DSLMigration()

        # Test version key function
        assert migration._version_key("1.0.0") == (1, 0, 0)
        assert migration._version_key("2.1.3") == (2, 1, 3)
        assert migration._version_key("10.0.0") == (10, 0, 0)

    def test_version_sorting_order(self):
        """Test version sorting produces correct order."""
        migration = DSLMigration()

        versions = ["2.0.0", "1.0.0", "1.1.0", "1.0.1"]
        sorted_versions = sorted(versions, key=migration._version_key)

        assert sorted_versions == ["1.0.0", "1.0.1", "1.1.0", "2.0.0"]
