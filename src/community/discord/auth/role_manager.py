"""Role management for Discord community bot.

Provides:
- Role assignment and removal
- Role hierarchy enforcement
- Custom role configuration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .user_auth import ROLE_HIERARCHY, UserRole

logger = logging.getLogger(__name__)


@dataclass
class RoleConfig:
    """Configuration for a role.

    Attributes:
        role_id: Discord role ID.
        name: Role name.
        level: Hierarchy level (higher = more permissions).
        permissions: Set of permission strings.
        color: Discord role color (hex).
        is_auto_assignable: Whether users can self-assign.
        description: Role description.
    """

    role_id: str
    name: str
    level: int = 0
    permissions: set[str] = field(default_factory=set)
    color: int = 0x7289DA  # Default Discord blurple
    is_auto_assignable: bool = False
    description: str = ""


@dataclass
class RoleAssignment:
    """Record of a role assignment.

    Attributes:
        user_id: Discord user ID.
        role_id: Assigned role ID.
        assigned_by: User ID who assigned the role.
        assigned_at: When role was assigned.
        expires_at: Optional expiration time.
    """

    user_id: str
    role_id: str
    assigned_by: str
    assigned_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class RoleManager:
    """Manages Discord roles and assignments.

    Features:
    - Role hierarchy enforcement (can't assign roles above your level)
    - Configurable custom roles
    - Role assignment history
    - Expiring role assignments
    - Auto-assignment rules
    """

    # Redis key prefix
    REDIS_KEY_PREFIX = "chiseai:discord:roles"

    # Default role hierarchy
    DEFAULT_LEVELS: dict[UserRole, int] = {
        UserRole.ADMIN: 100,
        UserRole.MODERATOR: 50,
        UserRole.MEMBER: 10,
        UserRole.GUEST: 1,
    }

    def __init__(
        self,
        redis_client: Any | None = None,
        config: dict[str, RoleConfig] | None = None,
    ):
        """Initialize RoleManager.

        Args:
            redis_client: Redis client for storage.
            config: Dictionary of role_id -> RoleConfig.
        """
        self._redis = redis_client
        self._roles: dict[str, RoleConfig] = {}
        self._user_roles: dict[str, set[str]] = {}  # user_id -> set of role_ids
        self._assignment_history: list[RoleAssignment] = []

        # Initialize default roles
        self._init_default_roles()

        # Apply custom config
        if config:
            for role_id, role_config in config.items():
                self._roles[role_id] = role_config

    def _init_default_roles(self) -> None:
        """Initialize default roles based on UserRole enum."""
        self._roles = {
            "admin": RoleConfig(
                role_id="admin",
                name="Admin",
                level=self.DEFAULT_LEVELS[UserRole.ADMIN],
                permissions={"*"},
                color=0xFF0000,
                is_auto_assignable=False,
                description="Full bot administration access",
            ),
            "moderator": RoleConfig(
                role_id="moderator",
                name="Moderator",
                level=self.DEFAULT_LEVELS[UserRole.MODERATOR],
                permissions={"moderate", "kick", "ban", "manage_messages"},
                color=0xFF8800,
                is_auto_assignable=False,
                description="Moderation and user management",
            ),
            "member": RoleConfig(
                role_id="member",
                name="Member",
                level=self.DEFAULT_LEVELS[UserRole.MEMBER],
                permissions={"view", "subscribe", "stats"},
                color=0x43B581,
                is_auto_assignable=True,
                description="Standard community member",
            ),
            "guest": RoleConfig(
                role_id="guest",
                name="Guest",
                level=self.DEFAULT_LEVELS[UserRole.GUEST],
                permissions={"view", "help"},
                color=0x727C8A,
                is_auto_assignable=True,
                description="Guest with limited access",
            ),
        }

    def get_role(self, role_id: str) -> RoleConfig | None:
        """Get role configuration.

        Args:
            role_id: Role identifier.

        Returns:
            RoleConfig or None.
        """
        return self._roles.get(role_id)

    def get_all_roles(self) -> list[RoleConfig]:
        """Get all configured roles.

        Returns:
            List of RoleConfig objects.
        """
        return list(self._roles.values())

    def get_roles_by_level(self, min_level: int) -> list[RoleConfig]:
        """Get roles at or above a level.

        Args:
            min_level: Minimum hierarchy level.

        Returns:
            List of RoleConfig objects.
        """
        return [r for r in self._roles.values() if r.level >= min_level]

    def can_assign_role(self, assigner_role: str, target_role: str) -> bool:
        """Check if a role can assign another role.

        Args:
            assigner_role: Role ID of the assigner.
            target_role: Role ID being assigned.

        Returns:
            True if assignment is allowed.
        """
        assigner = self._roles.get(assigner_role)
        target = self._roles.get(target_role)

        if not assigner or not target:
            return False

        return assigner.level > target.level

    def get_user_roles(self, user_id: str) -> list[RoleConfig]:
        """Get all roles for a user.

        Args:
            user_id: Discord user ID.

        Returns:
            List of RoleConfig objects.
        """
        role_ids = self._user_roles.get(user_id, set())
        return [self._roles[r_id] for r_id in role_ids if r_id in self._roles]

    async def assign_role(
        self,
        user_id: str,
        role_id: str,
        assigned_by: str,
        expires_at: datetime | None = None,
    ) -> bool:
        """Assign a role to a user.

        Args:
            user_id: Discord user ID.
            role_id: Role ID to assign.
            assigned_by: User ID performing assignment.
            expires_at: Optional expiration time.

        Returns:
            True if successful.
        """
        role = self._roles.get(role_id)
        if not role:
            logger.error("Cannot assign unknown role: %s", role_id)
            return False

        # Initialize user roles set if needed
        if user_id not in self._user_roles:
            self._user_roles[user_id] = set()

        # Add role
        self._user_roles[user_id].add(role_id)

        # Record assignment
        assignment = RoleAssignment(
            user_id=user_id,
            role_id=role_id,
            assigned_by=assigned_by,
            expires_at=expires_at,
        )
        self._assignment_history.append(assignment)

        # Store in Redis
        if self._redis:
            try:
                await self._store_role_assignment(assignment)
            except Exception as e:
                logger.error("Failed to store role assignment: %s", str(e))

        logger.info("Role %s assigned to user %s by %s", role_id, user_id, assigned_by)
        return True

    async def remove_role(self, user_id: str, role_id: str, removed_by: str) -> bool:
        """Remove a role from a user.

        Args:
            user_id: Discord user ID.
            role_id: Role ID to remove.
            removed_by: User ID performing removal.

        Returns:
            True if successful.
        """
        if user_id not in self._user_roles:
            return False

        if role_id not in self._user_roles[user_id]:
            return False

        self._user_roles[user_id].discard(role_id)

        # Record removal
        assignment = RoleAssignment(
            user_id=user_id,
            role_id=role_id,
            assigned_by=removed_by,
        )
        self._assignment_history.append(assignment)

        if self._redis:
            try:
                await self._store_role_removal(user_id, role_id)
            except Exception as e:
                logger.error("Failed to store role removal: %s", str(e))

        logger.info("Role %s removed from user %s by %s", role_id, user_id, removed_by)
        return True

    async def sync_discord_roles(
        self,
        user_id: str,
        discord_role_ids: list[str],
    ) -> set[str]:
        """Sync bot roles with Discord server roles.

        Args:
            user_id: Discord user ID.
            discord_role_ids: List of Discord role IDs the user has.

        Returns:
            Set of synced role IDs.
        """
        # Map Discord role IDs to our role IDs
        # In production, this would use a mapping config
        synced_roles = set()

        for discord_role_id in discord_role_ids:
            # Check if we have a mapping for this Discord role
            for role_id, role_config in self._roles.items():
                if hasattr(role_config, "discord_role_id"):
                    if role_config.discord_role_id == discord_role_id:
                        synced_roles.add(role_id)

        # Update user's roles
        self._user_roles[user_id] = synced_roles

        return synced_roles

    def get_assignment_history(
        self,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[RoleAssignment]:
        """Get role assignment history.

        Args:
            user_id: Filter by user ID (None for all).
            limit: Maximum entries to return.

        Returns:
            List of RoleAssignment objects.
        """
        history = self._assignment_history

        if user_id:
            history = [h for h in history if h.user_id == user_id]

        return history[-limit:]

    def add_custom_role(
        self,
        role_id: str,
        name: str,
        level: int,
        permissions: set[str],
        **kwargs,
    ) -> bool:
        """Add a custom role.

        Args:
            role_id: Unique role identifier.
            name: Display name.
            level: Hierarchy level.
            permissions: Set of permissions.
            **kwargs: Additional RoleConfig fields.

        Returns:
            True if successful.
        """
        if role_id in self._roles:
            logger.error("Role %s already exists", role_id)
            return False

        self._roles[role_id] = RoleConfig(
            role_id=role_id,
            name=name,
            level=level,
            permissions=permissions,
            **kwargs,
        )

        logger.info("Custom role added: %s (%s)", name, role_id)
        return True

    def remove_custom_role(self, role_id: str) -> bool:
        """Remove a custom role.

        Args:
            role_id: Role to remove.

        Returns:
            True if successful.
        """
        if role_id not in self._roles:
            return False

        if role_id in ("admin", "moderator", "member", "guest"):
            logger.error("Cannot remove default role: %s", role_id)
            return False

        del self._roles[role_id]
        logger.info("Custom role removed: %s", role_id)
        return True

    def get_auto_assignable_roles(self) -> list[RoleConfig]:
        """Get roles that users can self-assign.

        Returns:
            List of self-assignable RoleConfig objects.
        """
        return [r for r in self._roles.values() if r.is_auto_assignable]

    async def _store_role_assignment(self, assignment: RoleAssignment) -> None:
        """Store role assignment in Redis.

        Args:
            assignment: RoleAssignment to store.
        """
        # Import here to avoid circular imports
        try:
            from tools.redis_state import redis_state_rpush

            key = f"{self.REDIS_KEY_PREFIX}:history:{assignment.user_id}"
            data = f"{assignment.role_id}:{assignment.assigned_by}:{assignment.assigned_at.isoformat()}"
            redis_state_rpush(key, data)

            # Set expiry on user roles
            from tools.redis_state import redis_state_expire

            user_key = f"{self.REDIS_KEY_PREFIX}:user:{assignment.user_id}"
            redis_state_expire(user_key, 86400 * 30)  # 30 days

        except Exception as e:
            logger.error("Failed to store role assignment in Redis: %s", str(e))

    async def _store_role_removal(self, user_id: str, role_id: str) -> None:
        """Store role removal in Redis.

        Args:
            user_id: Discord user ID.
            role_id: Role that was removed.
        """
        try:
            from tools.redis_state import redis_state_rpush

            key = f"{self.REDIS_KEY_PREFIX}:removals:{user_id}"
            data = f"{role_id}:{datetime.now(UTC).isoformat()}"
            redis_state_rpush(key, data)

        except Exception as e:
            logger.error("Failed to store role removal in Redis: %s", str(e))

    def to_dict(self) -> dict[str, Any]:
        """Export configuration as dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "roles": {
                role_id: {
                    "name": cfg.name,
                    "level": cfg.level,
                    "permissions": list(cfg.permissions),
                    "color": cfg.color,
                    "is_auto_assignable": cfg.is_auto_assignable,
                    "description": cfg.description,
                }
                for role_id, cfg in self._roles.items()
            },
            "user_roles": {
                user_id: list(role_ids)
                for user_id, role_ids in self._user_roles.items()
            },
        }
