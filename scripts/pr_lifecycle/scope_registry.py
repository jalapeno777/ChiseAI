#!/usr/bin/env python3
"""Scope registry for tracking file ownership across parallel agents.

This module provides Redis-based scope ownership tracking, conflict detection,
and scope reservation/release mechanisms for the 10-agent parallel execution system.
"""

from __future__ import annotations

import fnmatch
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConflictType(Enum):
    """Types of scope conflicts."""

    NONE = "none"
    EXACT_OVERLAP = "exact_overlap"
    SUBSCOPE = "subscope"
    SUPERSCOPE = "superscope"
    PARTIAL_OVERLAP = "partial_overlap"
    GLOB_OVERLAP = "glob_overlap"


@dataclass
class ScopeConflict:
    """Represents a scope conflict between two agents."""

    conflict_type: ConflictType
    my_scope: str
    conflicting_scope: str
    owner: str
    story_id: str
    agent: str
    overlap_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_type": self.conflict_type.value,
            "my_scope": self.my_scope,
            "conflicting_scope": self.conflicting_scope,
            "owner": self.owner,
            "story_id": self.story_id,
            "agent": self.agent,
            "overlap_files": self.overlap_files,
        }


@dataclass
class ScopeReservation:
    """Represents a scope reservation by an agent."""

    story_id: str
    agent: str
    scopes: list[str]
    reserved_at: float
    expires_at: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "story_id": self.story_id,
            "agent": self.agent,
            "scopes": self.scopes,
            "reserved_at": self.reserved_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScopeReservation:
        return cls(
            story_id=data["story_id"],
            agent=data["agent"],
            scopes=data["scopes"],
            reserved_at=data["reserved_at"],
            expires_at=data["expires_at"],
            metadata=data.get("metadata", {}),
        )


class ScopeRegistry:
    """Registry for tracking scope ownership across parallel agents."""

    REDIS_HASH_KEY = "bmad:chiseai:scope_registry"
    DEFAULT_TTL_SECONDS = 432000  # 5 days

    def __init__(self, redis_client=None):
        """Initialize the scope registry.

        Args:
            redis_client: Optional Redis client. If not provided, will attempt
                to connect using environment variables.
        """
        self._redis = redis_client
        self._local_cache: dict[str, ScopeReservation] = {}

    def _get_redis(self):
        """Get or create Redis connection."""
        if self._redis is not None:
            return self._redis

        # Try to import and connect
        try:
            import redis

            host = (
                os.getenv("CHISE_REDIS_HOST")
                or os.getenv("REDIS_HOST")
                or "host.docker.internal"
            )
            port = int(
                os.getenv("CHISE_REDIS_PORT") or os.getenv("REDIS_PORT") or "6380"
            )
            db = int(os.getenv("CHISE_REDIS_DB") or os.getenv("REDIS_DB") or "0")

            self._redis = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self._redis.ping()
            return self._redis
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to Redis: {exc}") from exc

    def _path_slug(self, path: str) -> str:
        """Convert a path to a slug for Redis key storage."""
        p = path.strip().lstrip("./").strip("/")
        return p.lower().replace("/", ":")

    def _glob_to_pattern(self, glob_pattern: str) -> str:
        """Convert a glob pattern to a regex-like pattern for matching."""
        return glob_pattern.strip().lstrip("./").strip("/")

    def _paths_overlap(self, path1: str, path2: str) -> bool:
        """Check if two paths or glob patterns overlap.

        Args:
            path1: First path or glob pattern
            path2: Second path or glob pattern

        Returns:
            True if the paths overlap, False otherwise
        """
        p1 = self._glob_to_pattern(path1)
        p2 = self._glob_to_pattern(path2)

        # Exact match
        if p1 == p2:
            return True

        # Check if one is a prefix of the other
        if p1.startswith(p2 + "/") or p2.startswith(p1 + "/"):
            return True

        # Check glob patterns
        if "*" in p1 or "?" in p1 or "[" in p1:
            if fnmatch.fnmatch(p2, p1):
                return True
        if "*" in p2 or "?" in p2 or "[" in p2:
            if fnmatch.fnmatch(p1, p2):
                return True

        # Check for directory overlap
        p1_parts = p1.split("/")
        p2_parts = p2.split("/")
        min_len = min(len(p1_parts), len(p2_parts))
        return p1_parts[:min_len] == p2_parts[:min_len]

    def _determine_conflict_type(self, my_scope: str, other_scope: str) -> ConflictType:
        """Determine the type of conflict between two scopes."""
        p1 = self._glob_to_pattern(my_scope)
        p2 = self._glob_to_pattern(other_scope)

        if p1 == p2:
            return ConflictType.EXACT_OVERLAP

        if p1.startswith(p2 + "/"):
            return ConflictType.SUBSCOPE

        if p2.startswith(p1 + "/"):
            return ConflictType.SUPERSCOPE

        if "*" in p1 or "*" in p2:
            return ConflictType.GLOB_OVERLAP

        return ConflictType.PARTIAL_OVERLAP

    def check_conflicts(
        self, scopes: list[str], story_id: str, agent: str
    ) -> list[ScopeConflict]:
        """Check for conflicts between proposed scopes and existing reservations.

        Args:
            scopes: List of scope paths/globs to check
            story_id: Story ID of the requesting agent
            agent: Agent identifier

        Returns:
            List of scope conflicts found
        """
        conflicts = []
        redis_client = self._get_redis()

        # Get all existing reservations
        all_reservations = redis_client.hgetall(self.REDIS_HASH_KEY)

        for scope in scopes:
            for key, value in all_reservations.items():
                try:
                    reservation = ScopeReservation.from_dict(json.loads(value))
                except (json.JSONDecodeError, KeyError):
                    continue

                # Skip own reservations
                if reservation.story_id == story_id and reservation.agent == agent:
                    continue

                # Check for overlap
                for existing_scope in reservation.scopes:
                    if self._paths_overlap(scope, existing_scope):
                        conflict_type = self._determine_conflict_type(
                            scope, existing_scope
                        )
                        conflicts.append(
                            ScopeConflict(
                                conflict_type=conflict_type,
                                my_scope=scope,
                                conflicting_scope=existing_scope,
                                owner=f"{reservation.story_id}/{reservation.agent}",
                                story_id=reservation.story_id,
                                agent=reservation.agent,
                            )
                        )

        return conflicts

    def reserve_scopes(
        self,
        scopes: list[str],
        story_id: str,
        agent: str,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, list[ScopeConflict]]:
        """Reserve scopes for an agent.

        Args:
            scopes: List of scope paths/globs to reserve
            story_id: Story ID of the requesting agent
            agent: Agent identifier
            ttl_seconds: TTL for the reservation (default: 5 days)
            metadata: Optional metadata to store with the reservation

        Returns:
            Tuple of (success, conflicts). If success is False, conflicts
            contains the list of conflicting reservations.
        """
        # Check for conflicts first
        conflicts = self.check_conflicts(scopes, story_id, agent)
        if conflicts:
            return False, conflicts

        # Create reservation
        now = time.time()
        ttl = ttl_seconds or self.DEFAULT_TTL_SECONDS
        reservation = ScopeReservation(
            story_id=story_id,
            agent=agent,
            scopes=scopes,
            reserved_at=now,
            expires_at=now + ttl,
            metadata=metadata or {},
        )

        # Store in Redis
        redis_client = self._get_redis()
        key = f"{story_id}:{agent}"
        redis_client.hset(self.REDIS_HASH_KEY, key, json.dumps(reservation.to_dict()))
        redis_client.expire(self.REDIS_HASH_KEY, ttl)

        # Update local cache
        self._local_cache[key] = reservation

        return True, []

    def release_scopes(self, story_id: str, agent: str) -> bool:
        """Release all scopes reserved by an agent.

        Args:
            story_id: Story ID of the agent
            agent: Agent identifier

        Returns:
            True if scopes were released, False if no reservation found
        """
        redis_client = self._get_redis()
        key = f"{story_id}:{agent}"

        result = redis_client.hdel(self.REDIS_HASH_KEY, key)

        # Update local cache
        if key in self._local_cache:
            del self._local_cache[key]

        return result > 0

    def extend_reservation(
        self, story_id: str, agent: str, additional_seconds: int
    ) -> bool:
        """Extend the TTL of an existing reservation.

        Args:
            story_id: Story ID of the agent
            agent: Agent identifier
            additional_seconds: Additional seconds to add to the reservation

        Returns:
            True if reservation was extended, False if not found
        """
        redis_client = self._get_redis()
        key = f"{story_id}:{agent}"

        value = redis_client.hget(self.REDIS_HASH_KEY, key)
        if not value:
            return False

        try:
            reservation = ScopeReservation.from_dict(json.loads(value))
        except (json.JSONDecodeError, KeyError):
            return False

        reservation.expires_at += additional_seconds
        redis_client.hset(self.REDIS_HASH_KEY, key, json.dumps(reservation.to_dict()))

        # Update local cache
        self._local_cache[key] = reservation

        return True

    def get_reservation(self, story_id: str, agent: str) -> ScopeReservation | None:
        """Get the reservation for a specific agent.

        Args:
            story_id: Story ID of the agent
            agent: Agent identifier

        Returns:
            ScopeReservation if found, None otherwise
        """
        # Check local cache first
        key = f"{story_id}:{agent}"
        if key in self._local_cache:
            return self._local_cache[key]

        # Check Redis
        redis_client = self._get_redis()
        value = redis_client.hget(self.REDIS_HASH_KEY, key)
        if not value:
            return None

        try:
            reservation = ScopeReservation.from_dict(json.loads(value))
            self._local_cache[key] = reservation
            return reservation
        except (json.JSONDecodeError, KeyError):
            return None

    def get_all_reservations(self) -> dict[str, ScopeReservation]:
        """Get all active reservations.

        Returns:
            Dictionary mapping reservation keys to ScopeReservation objects
        """
        redis_client = self._get_redis()
        all_data = redis_client.hgetall(self.REDIS_HASH_KEY)

        reservations = {}
        for key, value in all_data.items():
            try:
                reservation = ScopeReservation.from_dict(json.loads(value))
                # Filter out expired reservations
                if reservation.expires_at > time.time():
                    reservations[key] = reservation
            except (json.JSONDecodeError, KeyError):
                continue

        return reservations

    def cleanup_expired(self) -> int:
        """Remove expired reservations from the registry.

        Returns:
            Number of expired reservations removed
        """
        redis_client = self._get_redis()
        all_data = redis_client.hgetall(self.REDIS_HASH_KEY)

        now = time.time()
        expired_keys = []

        for key, value in all_data.items():
            try:
                reservation = ScopeReservation.from_dict(json.loads(value))
                if reservation.expires_at <= now:
                    expired_keys.append(key)
            except (json.JSONDecodeError, KeyError):
                expired_keys.append(key)

        if expired_keys:
            redis_client.hdel(self.REDIS_HASH_KEY, *expired_keys)

        # Update local cache
        for key in expired_keys:
            if key in self._local_cache:
                del self._local_cache[key]

        return len(expired_keys)

    def validate_scope_access(
        self, file_path: str, story_id: str, agent: str
    ) -> tuple[bool, str]:
        """Validate if an agent has access to edit a specific file.

        Args:
            file_path: Path to the file being edited
            story_id: Story ID of the agent
            agent: Agent identifier

        Returns:
            Tuple of (has_access, reason). If has_access is False, reason
            explains why access was denied.
        """
        reservation = self.get_reservation(story_id, agent)
        if not reservation:
            return False, f"No scope reservation found for {story_id}/{agent}"

        # Normalize file path
        normalized_path = self._glob_to_pattern(file_path)

        # Check if file is within any reserved scope
        for scope in reservation.scopes:
            if self._paths_overlap(normalized_path, scope):
                return True, "Access granted"

        return (
            False,
            f"File {file_path} is not within reserved scopes: {reservation.scopes}",
        )


# Singleton instance for module-level access
_registry_instance: ScopeRegistry | None = None


def get_scope_registry(redis_client=None) -> ScopeRegistry:
    """Get or create the global scope registry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ScopeRegistry(redis_client)
    return _registry_instance
