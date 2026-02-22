"""Semantic versioning for Brain versions.

ST-CHISE-001.1: Add Semantic Versioning Validation for Brain Versions

This module provides semantic versioning support for brain versions,
following the Semantic Versioning 2.0.0 specification.

Supported formats:
- "1.0.0" - Basic version
- "1.0.0-alpha" - With pre-release
- "1.0.0-alpha.1" - With pre-release and number
- "1.0.0+build" - With build metadata
- "1.0.0-alpha+build" - With pre-release and build metadata
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class InvalidVersionError(ValueError):
    """Raised when a version string is invalid."""

    pass


@dataclass(frozen=True, order=False)
class BrainVersion:
    """Represents a semantic version for brain versions.

    Attributes:
        major: Major version number (incompatible API changes)
        minor: Minor version number (backward compatible functionality)
        patch: Patch version number (backward compatible bug fixes)
        prerelease: Optional pre-release identifier (e.g., "alpha", "beta.1")
        build: Optional build metadata (e.g., "build", "exp.sha.5114f85")

    Examples:
        >>> BrainVersion(1, 0, 0)
        BrainVersion(major=1, minor=0, patch=0, prerelease=None, build=None)
        >>> BrainVersion(1, 0, 0, prerelease="alpha")
        BrainVersion(major=1, minor=0, patch=0, prerelease='alpha', build=None)
    """

    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    def __str__(self) -> str:
        """Convert version to string representation."""
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        if self.build:
            version += f"+{self.build}"
        return version

    def __repr__(self) -> str:
        """Return detailed string representation."""
        return (
            f"BrainVersion(major={self.major}, minor={self.minor}, "
            f"patch={self.patch}, prerelease={self.prerelease!r}, "
            f"build={self.build!r})"
        )


# Semantic versioning regex pattern (simplified for our use case)
# Matches: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
VERSION_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[a-zA-Z0-9.-]+))?"
    r"(?:\+(?P<build>[a-zA-Z0-9.-]+))?$"
)


def validate_version(version_str: str) -> BrainVersion:
    """Parse and validate a semantic version string.

    Args:
        version_str: Version string to parse (e.g., "1.0.0", "1.0.0-alpha")

    Returns:
        BrainVersion: Parsed and validated version object

    Raises:
        InvalidVersionError: If the version string is invalid

    Examples:
        >>> validate_version("1.0.0")
        BrainVersion(major=1, minor=0, patch=0, prerelease=None, build=None)
        >>> validate_version("1.0.0-alpha.1")
        BrainVersion(major=1, minor=0, patch=0, prerelease='alpha.1', build=None)
    """
    if not version_str or not isinstance(version_str, str):
        raise InvalidVersionError(
            f"Version must be a non-empty string, got: {type(version_str).__name__}"
        )

    match = VERSION_PATTERN.match(version_str.strip())

    if not match:
        raise InvalidVersionError(
            f"Invalid version format: '{version_str}'. "
            "Expected format: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD] "
            "(e.g., '1.0.0', '1.0.0-alpha', '1.0.0+build', '1.0.0-alpha+build')"
        )

    groups = match.groupdict()

    # Parse numeric components
    try:
        major = int(groups["major"])
        minor = int(groups["minor"])
        patch = int(groups["patch"])
    except ValueError as e:
        raise InvalidVersionError(f"Invalid numeric component in version: {e}") from e

    # Validate non-negative (regex ensures this, but double-check)
    if major < 0 or minor < 0 or patch < 0:
        raise InvalidVersionError(
            f"Version components must be non-negative: {version_str}"
        )

    # Extract optional components
    prerelease = groups.get("prerelease")
    build = groups.get("build")

    return BrainVersion(
        major=major,
        minor=minor,
        patch=patch,
        prerelease=prerelease,
        build=build,
    )


def _compare_prerelease(a: str | None, b: str | None) -> int:
    """Compare two pre-release identifiers.

    According to SemVer 2.0.0:
    - A version without a pre-release has higher precedence than one with
    - Pre-release identifiers are compared dot-separated, left to right
    - Numeric identifiers are compared as integers
    - Alphanumeric identifiers are compared lexically (ASCII sort order)
    - Numeric identifiers always have lower precedence than alphanumeric

    Args:
        a: First pre-release identifier (or None)
        b: Second pre-release identifier (or None)

    Returns:
        -1 if a < b, 0 if a == b, 1 if a > b
    """
    # No pre-release > has pre-release
    if a is None and b is None:
        return 0
    if a is None:
        return 1  # a (no pre-release) > b (has pre-release)
    if b is None:
        return -1  # a (has pre-release) < b (no pre-release)

    # Both have pre-releases, compare dot-separated identifiers
    a_parts = a.split(".")
    b_parts = b.split(".")

    for a_part, b_part in zip(a_parts, b_parts):
        # Determine if each part is numeric
        a_is_num = a_part.isdigit()
        b_is_num = b_part.isdigit()

        if a_is_num and b_is_num:
            # Both numeric: compare as integers
            a_int = int(a_part)
            b_int = int(b_part)
            if a_int < b_int:
                return -1
            elif a_int > b_int:
                return 1
        elif a_is_num:
            # Numeric < alphanumeric
            return -1
        elif b_is_num:
            # Alphanumeric > numeric
            return 1
        else:
            # Both alphanumeric: compare lexically
            if a_part < b_part:
                return -1
            elif a_part > b_part:
                return 1

    # All compared parts equal, longer pre-release has higher precedence
    if len(a_parts) < len(b_parts):
        return -1
    elif len(a_parts) > len(b_parts):
        return 1

    return 0


def compare_versions(a: str, b: str) -> int:
    """Compare two version strings.

    Comparison follows Semantic Versioning 2.0.0 precedence rules:
    1. Major, minor, patch are compared numerically
    2. Versions without pre-release have higher precedence
    3. Pre-release identifiers are compared per SemVer spec
    4. Build metadata is ignored in precedence

    Args:
        a: First version string
        b: Second version string

    Returns:
        -1 if a < b, 0 if a == b, 1 if a > b

    Raises:
        InvalidVersionError: If either version string is invalid

    Examples:
        >>> compare_versions("1.0.0", "2.0.0")
        -1
        >>> compare_versions("1.0.0", "1.0.0")
        0
        >>> compare_versions("2.0.0", "1.0.0")
        1
        >>> compare_versions("1.0.0-alpha", "1.0.0")
        -1
    """
    v_a = validate_version(a)
    v_b = validate_version(b)

    # Compare major
    if v_a.major < v_b.major:
        return -1
    elif v_a.major > v_b.major:
        return 1

    # Compare minor
    if v_a.minor < v_b.minor:
        return -1
    elif v_a.minor > v_b.minor:
        return 1

    # Compare patch
    if v_a.patch < v_b.patch:
        return -1
    elif v_a.patch > v_b.patch:
        return 1

    # Compare pre-release (build metadata is ignored for precedence)
    return _compare_prerelease(v_a.prerelease, v_b.prerelease)


def increment_major(version: str) -> str:
    """Increment the major version.

    Increments major version, resets minor and patch to 0,
    and removes pre-release and build metadata.

    Args:
        version: Version string to increment

    Returns:
        New version string with incremented major

    Raises:
        InvalidVersionError: If version string is invalid

    Examples:
        >>> increment_major("1.0.0")
        '2.0.0'
        >>> increment_major("1.5.3-alpha+build")
        '2.0.0'
    """
    v = validate_version(version)
    new_version = BrainVersion(major=v.major + 1, minor=0, patch=0)
    return str(new_version)


def increment_minor(version: str) -> str:
    """Increment the minor version.

    Increments minor version, resets patch to 0,
    and removes pre-release and build metadata.

    Args:
        version: Version string to increment

    Returns:
        New version string with incremented minor

    Raises:
        InvalidVersionError: If version string is invalid

    Examples:
        >>> increment_minor("1.0.0")
        '1.1.0'
        >>> increment_minor("1.5.3-alpha+build")
        '1.6.0'
    """
    v = validate_version(version)
    new_version = BrainVersion(major=v.major, minor=v.minor + 1, patch=0)
    return str(new_version)


def increment_patch(version: str) -> str:
    """Increment the patch version.

    Increments patch version and removes pre-release and build metadata.

    Args:
        version: Version string to increment

    Returns:
        New version string with incremented patch

    Raises:
        InvalidVersionError: If version string is invalid

    Examples:
        >>> increment_patch("1.0.0")
        '1.0.1'
        >>> increment_patch("1.5.3-alpha+build")
        '1.5.4'
    """
    v = validate_version(version)
    new_version = BrainVersion(major=v.major, minor=v.minor, patch=v.patch + 1)
    return str(new_version)
