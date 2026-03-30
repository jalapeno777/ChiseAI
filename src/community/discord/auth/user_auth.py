"""User authentication and role management for Discord community bot.

Provides:
- User registration with Discord IDs
- Role-based access control (admin, moderator, member)
- Permission checking decorators
- Link Discord users to trading system accounts
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """User roles in the Discord community."""

    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"
    GUEST = "guest"

    @classmethod
    def from_discord_role(cls, role_name: str) -> UserRole:
        """Convert Discord role name to UserRole.

        Args:
            role_name: Name of the Discord role.

        Returns:
            Corresponding UserRole.
        """
        role_name_lower = role_name.lower()
        if "admin" in role_name_lower:
            return cls.ADMIN
        elif "mod" in role_name_lower:
            return cls.MODERATOR
        elif "member" in role_name_lower:
            return cls.MEMBER
        else:
            return cls.GUEST

    def can(self, permission: str) -> bool:
        """Check if role has a specific permission.

        Args:
            permission: Permission to check.

        Returns:
            True if role has permission.
        """
        permissions = ROLE_PERMISSIONS.get(self, set())
        return permission in permissions


# Role hierarchy and permissions
ROLE_HIERARCHY: list[UserRole] = [
    UserRole.ADMIN,
    UserRole.MODERATOR,
    UserRole.MEMBER,
    UserRole.GUEST,
]

ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.ADMIN: {
        "commands.signals",
        "commands.stats",
        "commands.subscribe",
        "commands.unsubscribe",
        "commands.help",
        "admin.manage_roles",
        "admin.manage_users",
        "admin.broadcast",
        "moderator.kick",
        "moderator.ban",
    },
    UserRole.MODERATOR: {
        "commands.signals",
        "commands.stats",
        "commands.subscribe",
        "commands.unsubscribe",
        "commands.help",
        "moderator.kick",
        "moderator.ban",
    },
    UserRole.MEMBER: {
        "commands.signals",
        "commands.stats",
        "commands.subscribe",
        "commands.unsubscribe",
        "commands.help",
    },
    UserRole.GUEST: {
        "commands.help",
        "commands.subscribe",
    },
}


@dataclass
class DiscordUser:
    """Represents a Discord user in the system.

    Attributes:
        discord_id: Discord user ID.
        username: Discord username.
        display_name: Display name in server.
        role: User's role.
        trading_account: Linked trading account ID (if any).
        joined_at: When user first interacted with bot.
        last_active: Last activity timestamp.
        is_active: Whether user account is active.
        metadata: Additional user data.
    """

    discord_id: str
    username: str
    display_name: str = ""
    role: UserRole = UserRole.GUEST
    trading_account: str | None = None
    joined_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set default display name if not provided."""
        if not self.display_name:
            self.display_name = self.username

    @property
    def mention(self) -> str:
        """Get Discord mention string."""
        return f"<@{self.discord_id}>"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "discord_id": self.discord_id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role.value,
            "trading_account": self.trading_account,
            "joined_at": self.joined_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "is_active": self.is_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscordUser:
        """Create from dictionary."""
        return cls(
            discord_id=data["discord_id"],
            username=data["username"],
            display_name=data.get("display_name", ""),
            role=UserRole(data.get("role", "guest")),
            trading_account=data.get("trading_account"),
            joined_at=(
                datetime.fromisoformat(data["joined_at"])
                if "joined_at" in data
                else datetime.now(UTC)
            ),
            last_active=(
                datetime.fromisoformat(data["last_active"])
                if "last_active" in data
                else datetime.now(UTC)
            ),
            is_active=data.get("is_active", True),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Permission:
    """Represents a permission check result.

    Attributes:
        granted: Whether permission is granted.
        reason: Human-readable reason.
        required_role: Role that was required.
        user_role: User's actual role.
    """

    granted: bool
    reason: str
    required_role: UserRole | None = None
    user_role: UserRole | None = None


def require_permission(permission: str) -> Callable:
    """Decorator to require a permission for a command.

    Args:
        permission: Permission string required.

    Returns:
        Decorator function.
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Get user from first argument (usually ctx)
            ctx = args[0] if args else kwargs.get("ctx")
            if ctx is None:
                logger.error("require_permission: No context provided")
                return

            user_id = getattr(ctx, "author_id", None) or getattr(ctx, "user_id", None)
            if not user_id:
                logger.error("require_permission: No user ID in context")
                return

            user = await self._auth.get_user(user_id)
            if not user:
                if hasattr(ctx, "send"):
                    await ctx.send(
                        "❌ You are not registered. Use `!register <account>` to sign up."
                    )
                return

            has_permission = user.role.can(permission)
            if not has_permission:
                if hasattr(ctx, "send"):
                    await ctx.send(
                        f"❌ You don't have permission for this command. "
                        f"Required: `{permission}`, Your role: `{user.role.value}`"
                    )
                return

            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


def require_role(min_role: UserRole) -> Callable:
    """Decorator to require a minimum role for a command.

    Args:
        min_role: Minimum role required.

    Returns:
        Decorator function.
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            ctx = args[0] if args else kwargs.get("ctx")
            if ctx is None:
                logger.error("require_role: No context provided")
                return

            user_id = getattr(ctx, "author_id", None) or getattr(ctx, "user_id", None)
            if not user_id:
                logger.error("require_role: No user ID in context")
                return

            user = await self._auth.get_user(user_id)
            if not user:
                if hasattr(ctx, "send"):
                    await ctx.send("❌ You are not registered.")
                return

            user_role_index = ROLE_HIERARCHY.index(user.role)
            required_index = ROLE_HIERARCHY.index(min_role)

            if user_role_index > required_index:
                if hasattr(ctx, "send"):
                    await ctx.send(
                        f"❌ You need at least `{min_role.value}` role to use this command. "
                        f"Your role: `{user.role.value}`"
                    )
                return

            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


class UserAuth:
    """Manages user authentication and permissions for Discord bot.

    Provides:
    - User registration
    - Role management
    - Permission checking
    - Trading account linking
    """

    # Redis key prefix for user storage
    REDIS_KEY_PREFIX = "chiseai:discord:users"

    def __init__(
        self,
        redis_client: Any | None = None,
        role_manager: Any | None = None,
    ):
        """Initialize UserAuth.

        Args:
            redis_client: Redis client for user storage.
            role_manager: RoleManager instance for role operations.
        """
        self._redis = redis_client
        self._role_manager = role_manager
        self._cache: dict[str, DiscordUser] = {}
        self._cache_ttl = 300  # 5 minute cache

    def _get_redis_key(self, user_id: str) -> str:
        """Get Redis key for user.

        Args:
            user_id: Discord user ID.

        Returns:
            Redis key string.
        """
        return f"{self.REDIS_KEY_PREFIX}:{user_id}"

    async def get_user(self, discord_id: str) -> DiscordUser | None:
        """Get user by Discord ID.

        Args:
            discord_id: Discord user ID.

        Returns:
            DiscordUser or None if not found.
        """
        # Check cache first
        if discord_id in self._cache:
            return self._cache[discord_id]

        if not self._redis:
            logger.warning("No Redis client, returning None for user %s", discord_id)
            return None

        try:
            from tools.redis_state import redis_state_hgetall

            key = self._get_redis_key(discord_id)
            user_data = redis_state_hgetall(key)

            if not user_data:
                return None

            user = DiscordUser.from_dict(user_data)
            self._cache[discord_id] = user
            return user

        except Exception as e:
            logger.error("Failed to get user %s: %s", discord_id, str(e))
            return None

    async def register_user(
        self,
        discord_id: str,
        username: str,
        display_name: str = "",
        role: UserRole = UserRole.MEMBER,
    ) -> DiscordUser:
        """Register a new user or update existing.

        Args:
            discord_id: Discord user ID.
            username: Discord username.
            display_name: Display name.
            role: Initial role.

        Returns:
            Created/updated DiscordUser.
        """
        existing = await self.get_user(discord_id)

        if existing:
            # Update existing user
            existing.username = username
            existing.display_name = display_name or existing.display_name
            existing.last_active = datetime.now(UTC)
            user = existing
        else:
            # Create new user
            user = DiscordUser(
                discord_id=discord_id,
                username=username,
                display_name=display_name or username,
                role=role,
            )

        # Store in Redis
        if self._redis:
            try:
                from tools.redis_state import redis_state_json_set

                key = self._get_redis_key(discord_id)
                redis_state_json_set(key, "$", user.to_dict())
            except Exception as e:
                logger.error("Failed to store user %s: %s", discord_id, str(e))

        # Update cache
        self._cache[discord_id] = user

        logger.info("Registered user: %s (%s)", username, discord_id)
        return user

    async def link_trading_account(self, discord_id: str, trading_account: str) -> bool:
        """Link a trading account to a Discord user.

        Args:
            discord_id: Discord user ID.
            trading_account: Trading account ID.

        Returns:
            True if successful.
        """
        user = await self.get_user(discord_id)
        if not user:
            logger.warning("Cannot link trading account: user %s not found", discord_id)
            return False

        user.trading_account = trading_account
        user.metadata["account_linked_at"] = datetime.now(UTC).isoformat()

        if self._redis:
            try:
                from tools.redis_state import redis_state_json_set

                key = self._get_redis_key(discord_id)
                redis_state_json_set(key, "$", user.to_dict())
            except Exception as e:
                logger.error("Failed to link trading account: %s", str(e))
                return False

        self._cache[discord_id] = user
        logger.info("Linked trading account %s to user %s", trading_account, discord_id)
        return True

    async def unlink_trading_account(self, discord_id: str) -> bool:
        """Unlink trading account from Discord user.

        Args:
            discord_id: Discord user ID.

        Returns:
            True if successful.
        """
        user = await self.get_user(discord_id)
        if not user:
            return False

        user.trading_account = None
        user.metadata["account_unlinked_at"] = datetime.now(UTC).isoformat()

        if self._redis:
            try:
                from tools.redis_state import redis_state_json_set

                key = self._get_redis_key(discord_id)
                redis_state_json_set(key, "$", user.to_dict())
            except Exception as e:
                logger.error("Failed to unlink trading account: %s", str(e))
                return False

        self._cache[discord_id] = user
        return True

    async def update_role(self, discord_id: str, role: UserRole, admin_id: str) -> bool:
        """Update user's role.

        Args:
            discord_id: Discord user ID to update.
            role: New role.
            admin_id: Admin performing the update.

        Returns:
            True if successful.
        """
        user = await self.get_user(discord_id)
        if not user:
            logger.warning("Cannot update role: user %s not found", discord_id)
            return False

        old_role = user.role
        user.role = role
        user.metadata["role_updated_by"] = admin_id
        user.metadata["role_updated_at"] = datetime.now(UTC).isoformat()

        if self._redis:
            try:
                from tools.redis_state import redis_state_json_set

                key = self._get_redis_key(discord_id)
                redis_state_json_set(key, "$", user.to_dict())
            except Exception as e:
                logger.error("Failed to update role: %s", str(e))
                return False

        self._cache[discord_id] = user
        logger.info(
            "Role updated for %s: %s -> %s (by %s)",
            discord_id,
            old_role.value,
            role.value,
            admin_id,
        )
        return True

    def check_permission(self, user: DiscordUser, permission: str) -> Permission:
        """Check if user has a specific permission.

        Args:
            user: DiscordUser to check.
            permission: Permission string.

        Returns:
            Permission result with details.
        """
        if user.role.can(permission):
            return Permission(
                granted=True,
                reason=f"User has `{permission}` via `{user.role.value}` role",
                user_role=user.role,
            )

        # Find which role would have this permission
        for role in ROLE_HIERARCHY:
            if permission in ROLE_PERMISSIONS.get(role, set()):
                return Permission(
                    granted=False,
                    reason=f"Required: `{role.value}` or higher",
                    required_role=role,
                    user_role=user.role,
                )

        return Permission(
            granted=False,
            reason=f"Permission `{permission}` does not exist",
            user_role=user.role,
        )

    async def get_all_users(self) -> list[DiscordUser]:
        """Get all registered users.

        Returns:
            List of all DiscordUser objects.
        """
        if not self._redis:
            return list(self._cache.values())

        try:
            from tools.redis_state import redis_state_scan_all_keys

            key_pattern = f"{self.REDIS_KEY_PREFIX}:*"
            keys = redis_state_scan_all_keys(key_pattern)

            users = []
            for key in keys:
                if key == key_pattern:  # Skip the pattern itself
                    continue
                user_id = key.replace(f"{self.REDIS_KEY_PREFIX}:", "")
                user = await self.get_user(user_id)
                if user:
                    users.append(user)

            return users

        except Exception as e:
            logger.error("Failed to get all users: %s", str(e))
            return list(self._cache.values())

    def invalidate_cache(self, discord_id: str | None = None) -> None:
        """Invalidate user cache.

        Args:
            discord_id: Specific user to invalidate, or None for all.
        """
        if discord_id:
            self._cache.pop(discord_id, None)
        else:
            self._cache.clear()
