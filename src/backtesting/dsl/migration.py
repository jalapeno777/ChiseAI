"""DSL Version Migration - Migrate DSL configs between versions.

This module provides migration capabilities for DSL configurations,
allowing strategies to be upgraded between DSL versions while maintaining
compatibility and safety.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MigrationStep:
    """A single migration step between versions.

    Attributes:
        from_version: Source version
        to_version: Target version
        description: Human-readable description of changes
        migrate_func: Function to perform migration
    """

    from_version: str
    to_version: str
    description: str
    migrate_func: Callable[[dict[str, Any]], dict[str, Any]]

    def apply(self, config: dict[str, Any]) -> dict[str, Any]:
        """Apply this migration step.

        Args:
            config: Configuration to migrate

        Returns:
            Migrated configuration
        """
        return self.migrate_func(config.copy())


class DSLMigration:
    """DSL version migration manager.

    Handles migration of DSL configurations between versions with
    support for multi-step migrations through intermediate versions.
    """

    # Known DSL versions in order
    VERSIONS = ["1.0.0"]

    def __init__(self) -> None:
        """Initialize migration manager."""
        self._migrations: dict[tuple[str, str], MigrationStep] = {}
        self._register_default_migrations()

    def _register_default_migrations(self) -> None:
        """Register default migration steps."""
        # Currently only v1.0.0 exists, so no migrations needed yet
        # Future migrations will be registered here
        pass

    def register_migration(
        self,
        from_version: str,
        to_version: str,
        description: str,
        migrate_func: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Register a new migration step.

        Args:
            from_version: Source version
            to_version: Target version
            description: Description of changes
            migrate_func: Migration function
        """
        step = MigrationStep(
            from_version=from_version,
            to_version=to_version,
            description=description,
            migrate_func=migrate_func,
        )
        self._migrations[(from_version, to_version)] = step

        # Add version to known versions if new
        if from_version not in self.VERSIONS:
            self.VERSIONS.append(from_version)
            self.VERSIONS.sort(key=self._version_key)
        if to_version not in self.VERSIONS:
            self.VERSIONS.append(to_version)
            self.VERSIONS.sort(key=self._version_key)

    def _version_key(self, version: str) -> tuple[int, ...]:
        """Convert version string to sortable tuple.

        Args:
            version: Version string (e.g., "1.0.0")

        Returns:
            Tuple of version components
        """
        return tuple(int(x) for x in version.split("."))

    def migrate(
        self,
        config: dict[str, Any],
        from_version: str,
        to_version: str,
    ) -> dict[str, Any]:
        """Migrate config between DSL versions.

        Args:
            config: Configuration to migrate
            from_version: Source version
            to_version: Target version

        Returns:
            Migrated configuration

        Raises:
            ValueError: If migration path not found
        """
        if from_version == to_version:
            return config.copy()

        path = self.get_migration_path(from_version, to_version)

        if not path:
            raise ValueError(f"No migration path from {from_version} to {to_version}")

        result = config.copy()

        for i in range(len(path) - 1):
            step_key = (path[i], path[i + 1])
            if step_key in self._migrations:
                result = self._migrations[step_key].apply(result)
            else:
                # Direct migration without registered step
                # Just update version number
                if "metadata" not in result:
                    result["metadata"] = {}
                result["metadata"]["version"] = path[i + 1]

        return result

    def get_migration_path(self, from_version: str, to_version: str) -> list[str]:
        """Get list of intermediate versions for migration.

        Args:
            from_version: Source version
            to_version: Target version

        Returns:
            List of versions to traverse (including start and end)
        """
        if from_version == to_version:
            return [from_version]

        from_idx = (
            self.VERSIONS.index(from_version) if from_version in self.VERSIONS else -1
        )
        to_idx = self.VERSIONS.index(to_version) if to_version in self.VERSIONS else -1

        if from_idx == -1 or to_idx == -1:
            # Unknown version, try direct migration
            return [from_version, to_version]

        if from_idx < to_idx:
            # Upgrade: return versions in order
            return self.VERSIONS[from_idx : to_idx + 1]
        else:
            # Downgrade: not supported
            raise ValueError(
                f"Downgrade from {from_version} to {to_version} is not supported"
            )

    def can_migrate(self, from_version: str, to_version: str) -> bool:
        """Check if migration is possible.

        Args:
            from_version: Source version
            to_version: Target version

        Returns:
            True if migration path exists
        """
        if from_version == to_version:
            return True

        try:
            path = self.get_migration_path(from_version, to_version)
            return len(path) >= 2
        except ValueError:
            return False

    def get_version(self, config: dict[str, Any]) -> str:
        """Extract version from config.

        Args:
            config: DSL configuration

        Returns:
            Version string (defaults to "1.0.0")
        """
        metadata = config.get("metadata", {})
        return metadata.get("version", "1.0.0")

    def set_version(self, config: dict[str, Any], version: str) -> dict[str, Any]:
        """Set version in config.

        Args:
            config: DSL configuration
            version: New version

        Returns:
            Updated configuration
        """
        result = config.copy()
        if "metadata" not in result:
            result["metadata"] = {}
        result["metadata"]["version"] = version
        return result

    def get_supported_versions(self) -> list[str]:
        """Get list of supported DSL versions.

        Returns:
            List of version strings
        """
        return self.VERSIONS.copy()

    def get_migration_info(self, from_version: str, to_version: str) -> dict[str, Any]:
        """Get information about a migration.

        Args:
            from_version: Source version
            to_version: Target version

        Returns:
            Dictionary with migration information
        """
        try:
            path = self.get_migration_path(from_version, to_version)
            steps = []

            for i in range(len(path) - 1):
                step_key = (path[i], path[i + 1])
                if step_key in self._migrations:
                    step = self._migrations[step_key]
                    steps.append(
                        {
                            "from": step.from_version,
                            "to": step.to_version,
                            "description": step.description,
                        }
                    )
                else:
                    steps.append(
                        {
                            "from": path[i],
                            "to": path[i + 1],
                            "description": "Automatic version update",
                        }
                    )

            return {
                "can_migrate": True,
                "path": path,
                "steps": steps,
                "step_count": len(steps),
            }
        except ValueError as e:
            return {
                "can_migrate": False,
                "error": str(e),
            }


# Global migration instance
_default_migration = DSLMigration()


def migrate_config(
    config: dict[str, Any],
    from_version: str,
    to_version: str,
) -> dict[str, Any]:
    """Migrate config using default migration manager.

    Args:
        config: Configuration to migrate
        from_version: Source version
        to_version: Target version

    Returns:
        Migrated configuration
    """
    return _default_migration.migrate(config, from_version, to_version)


def get_config_version(config: dict[str, Any]) -> str:
    """Get version from config using default migration manager.

    Args:
        config: DSL configuration

    Returns:
        Version string
    """
    return _default_migration.get_version(config)


def can_migrate(from_version: str, to_version: str) -> bool:
    """Check if migration is possible using default migration manager.

    Args:
        from_version: Source version
        to_version: Target version

    Returns:
        True if migration path exists
    """
    return _default_migration.can_migrate(from_version, to_version)
