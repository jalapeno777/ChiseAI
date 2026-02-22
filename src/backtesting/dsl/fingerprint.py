"""DSL Fingerprint - Deterministic hashing and diffing of DSL configs.

This module provides reproducibility features for DSL configurations:
- Deterministic SHA-256 hashing (same config = same hash)
- Structured diff between configurations
- Canonical form normalization
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DiffEntry:
    """Single difference entry.

    Attributes:
        path: Dot-notation path to the field
        operation: Type of change (added, removed, modified)
        old_value: Previous value (None for additions)
        new_value: New value (None for removals)
    """

    path: str
    operation: str  # 'added', 'removed', 'modified'
    old_value: Any
    new_value: Any

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": self.path,
            "operation": self.operation,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


@dataclass(frozen=True)
class ConfigDiff:
    """Structured diff between two configurations.

    Attributes:
        has_changes: True if there are any differences
        additions: Fields that were added
        removals: Fields that were removed
        modifications: Fields that were modified
        all_changes: All changes combined
    """

    has_changes: bool
    additions: list[DiffEntry]
    removals: list[DiffEntry]
    modifications: list[DiffEntry]
    all_changes: list[DiffEntry]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "has_changes": self.has_changes,
            "additions": [a.to_dict() for a in self.additions],
            "removals": [r.to_dict() for r in self.removals],
            "modifications": [m.to_dict() for m in self.modifications],
            "all_changes": [c.to_dict() for c in self.all_changes],
            "addition_count": len(self.additions),
            "removal_count": len(self.removals),
            "modification_count": len(self.modifications),
        }


def _normalize_value(value: Any) -> Any:
    """Normalize a value for consistent hashing.

    Args:
        value: Value to normalize

    Returns:
        Normalized value
    """
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in sorted(value.items())}
    elif isinstance(value, list):
        return [_normalize_value(v) for v in value]
    elif isinstance(value, float):
        # Normalize floats to avoid precision issues
        return round(value, 10)
    elif isinstance(value, bool) or isinstance(value, int):
        return value
    elif value is None:
        return None
    else:
        return str(value)


def _canonical_form(config: dict[str, Any]) -> dict[str, Any]:
    """Convert config to canonical form for hashing.

    This ensures that semantically equivalent configs produce
    the same hash by:
    - Sorting all dictionary keys
    - Normalizing floating point values
    - Converting to a consistent structure

    Args:
        config: DSL configuration

    Returns:
        Canonical form dictionary
    """
    result: dict[str, Any] = _normalize_value(config)
    return result


def compute_dsl_fingerprint(config: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of DSL config.

    This function ensures that the same configuration always
    produces the same hash, regardless of key ordering or
    formatting differences.

    Args:
        config: DSL configuration dictionary

    Returns:
        Hexadecimal SHA-256 hash string

    Example:
        >>> config1 = {'metadata': {'name': 'test', 'version': '1.0.0'}}
        >>> config2 = {'metadata': {'version': '1.0.0', 'name': 'test'}}
        >>> compute_dsl_fingerprint(config1) == compute_dsl_fingerprint(config2)
        True
    """
    # Convert to canonical form
    canonical = _canonical_form(config)

    # Serialize to JSON with sorted keys and no whitespace
    json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))

    # Compute SHA-256 hash
    hash_obj = hashlib.sha256(json_str.encode("utf-8"))

    return hash_obj.hexdigest()


def compute_dsl_fingerprint_short(config: dict[str, Any], length: int = 16) -> str:
    """Compute short fingerprint (truncated hash).

    Args:
        config: DSL configuration dictionary
        length: Length of short hash (default 16)

    Returns:
        Truncated hexadecimal hash string
    """
    full_hash = compute_dsl_fingerprint(config)
    return full_hash[:length]


def diff_configs(config1: dict[str, Any], config2: dict[str, Any]) -> ConfigDiff:
    """Return structured diff between two configs.

    Args:
        config1: First configuration
        config2: Second configuration

    Returns:
        ConfigDiff with all changes

    Example:
        >>> config1 = {'metadata': {'name': 'test', 'version': '1.0.0'}}
        >>> config2 = {'metadata': {'name': 'test', 'version': '1.1.0'}}
        >>> diff = diff_configs(config1, config2)
        >>> diff.has_changes
        True
        >>> diff.modifications[0].path
        'metadata.version'
    """
    additions: list[DiffEntry] = []
    removals: list[DiffEntry] = []
    modifications: list[DiffEntry] = []

    def _diff_recursive(
        obj1: Any,
        obj2: Any,
        path: str,
    ) -> None:
        """Recursively compare objects."""
        if isinstance(obj1, dict) and isinstance(obj2, dict):
            all_keys = set(obj1.keys()) | set(obj2.keys())
            for key in sorted(all_keys):
                new_path = f"{path}.{key}" if path else key
                if key not in obj1:
                    additions.append(
                        DiffEntry(
                            path=new_path,
                            operation="added",
                            old_value=None,
                            new_value=obj2[key],
                        )
                    )
                elif key not in obj2:
                    removals.append(
                        DiffEntry(
                            path=new_path,
                            operation="removed",
                            old_value=obj1[key],
                            new_value=None,
                        )
                    )
                else:
                    _diff_recursive(obj1[key], obj2[key], new_path)
        elif isinstance(obj1, list) and isinstance(obj2, list):
            max_len = max(len(obj1), len(obj2))
            for i in range(max_len):
                new_path = f"{path}[{i}]"
                if i >= len(obj1):
                    additions.append(
                        DiffEntry(
                            path=new_path,
                            operation="added",
                            old_value=None,
                            new_value=obj2[i],
                        )
                    )
                elif i >= len(obj2):
                    removals.append(
                        DiffEntry(
                            path=new_path,
                            operation="removed",
                            old_value=obj1[i],
                            new_value=None,
                        )
                    )
                else:
                    _diff_recursive(obj1[i], obj2[i], new_path)
        else:
            # Compare primitive values
            if obj1 != obj2:
                modifications.append(
                    DiffEntry(
                        path=path,
                        operation="modified",
                        old_value=obj1,
                        new_value=obj2,
                    )
                )

    _diff_recursive(config1, config2, "")

    all_changes = additions + removals + modifications

    return ConfigDiff(
        has_changes=len(all_changes) > 0,
        additions=additions,
        removals=removals,
        modifications=modifications,
        all_changes=all_changes,
    )


def configs_equal(config1: dict[str, Any], config2: dict[str, Any]) -> bool:
    """Check if two configs are semantically equal.

    Args:
        config1: First configuration
        config2: Second configuration

    Returns:
        True if configs are equal
    """
    return compute_dsl_fingerprint(config1) == compute_dsl_fingerprint(config2)


def get_fingerprint_metadata(config: dict[str, Any]) -> dict[str, Any]:
    """Get fingerprint with metadata.

    Args:
        config: DSL configuration

    Returns:
        Dictionary with hash and metadata
    """
    canonical = _canonical_form(config)
    json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    hash_obj = hashlib.sha256(json_str.encode("utf-8"))

    return {
        "hash": hash_obj.hexdigest(),
        "short_hash": hash_obj.hexdigest()[:16],
        "canonical_size_bytes": len(json_str.encode("utf-8")),
        "canonical_json": json_str,
    }


class DSLFingerprint:
    """Fingerprint manager for DSL configurations.

    Provides a class-based interface for computing and comparing
    DSL fingerprints.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with a configuration.

        Args:
            config: DSL configuration
        """
        self.config = config
        self._hash: str | None = None
        self._canonical: dict[str, Any] | None = None

    @property
    def hash(self) -> str:
        """Get SHA-256 hash of config."""
        if self._hash is None:
            self._hash = compute_dsl_fingerprint(self.config)
        return self._hash

    @property
    def short_hash(self) -> str:
        """Get truncated hash (16 chars)."""
        return self.hash[:16]

    @property
    def canonical(self) -> dict[str, Any]:
        """Get canonical form of config."""
        if self._canonical is None:
            self._canonical = _canonical_form(self.config)
        return self._canonical

    def diff(self, other: DSLFingerprint | dict[str, Any]) -> ConfigDiff:
        """Compute diff with another config.

        Args:
            other: Another fingerprint or config dict

        Returns:
            ConfigDiff with differences
        """
        if isinstance(other, DSLFingerprint):
            other_config = other.config
        else:
            other_config = other

        return diff_configs(self.config, other_config)

    def equals(self, other: DSLFingerprint | dict[str, Any]) -> bool:
        """Check if equal to another config.

        Args:
            other: Another fingerprint or config dict

        Returns:
            True if equal
        """
        if isinstance(other, DSLFingerprint):
            return self.hash == other.hash
        else:
            return self.hash == compute_dsl_fingerprint(other)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "hash": self.hash,
            "short_hash": self.short_hash,
            "canonical": self.canonical,
        }
