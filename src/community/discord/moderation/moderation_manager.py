"""Moderation manager for Discord community."""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ModerationAction(Enum):
    """Type of moderation action."""

    KICK = "kick"
    BAN = "ban"
    MUTE = "mute"
    UNMUTE = "unmute"
    WARN = "warn"
    TEMP_BAN = "temp_ban"


class ActionStatus(Enum):
    """Status of a moderation action."""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    APPEALED = "appealed"


@dataclass
class ModerationLogEntry:
    """A moderation action log entry."""

    action_id: str
    action_type: ModerationAction
    target_user_id: str
    target_user_name: str
    moderator_id: str
    moderator_name: str
    reason: str
    status: ActionStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "target_user_id": self.target_user_id,
            "target_user_name": self.target_user_name,
            "moderator_id": self.moderator_id,
            "moderator_name": self.moderator_name,
            "reason": self.reason,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModerationLogEntry":
        """Create from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        expires_at = data.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        return cls(
            action_id=data["action_id"],
            action_type=ModerationAction(data["action_type"]),
            target_user_id=data["target_user_id"],
            target_user_name=data.get("target_user_name", "Unknown"),
            moderator_id=data["moderator_id"],
            moderator_name=data.get("moderator_name", "Unknown"),
            reason=data.get("reason", ""),
            status=ActionStatus(data.get("status", "active")),
            created_at=created_at or datetime.now(UTC),
            expires_at=expires_at,
            metadata=data.get("metadata", {}),
        )


@dataclass
class Appeal:
    """A moderation appeal."""

    appeal_id: str
    action_id: str
    user_id: str
    user_name: str
    reason: str
    status: str = "pending"  # pending, approved, rejected
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "appeal_id": self.appeal_id,
            "action_id": self.action_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "review_notes": self.review_notes,
        }


class ModerationManager:
    """Manage moderation actions for Discord community.

    Handles kick, ban, mute, unmute, and warn actions with full logging,
    temporary and permanent actions, and appeal tracking.
    """

    def __init__(
        self,
        redis_client: Any = None,
        default_mute_duration_minutes: int = 30,
        log_retention_days: int = 90,
    ):
        """Initialize ModerationManager.

        Args:
            redis_client: Redis client for storing moderation data
            default_mute_duration_minutes: Default mute duration
            log_retention_days: Days to retain moderation logs
        """
        self._redis = redis_client
        self._default_mute_duration = default_mute_duration_minutes
        self._log_retention_days = log_retention_days
        self._active_actions: dict[str, ModerationLogEntry] = {}

    def _get_action_key(self, action_id: str) -> str:
        """Get Redis key for moderation action."""
        return f"community:discord:moderation:action:{action_id}"

    def _get_user_actions_key(self, user_id: str) -> str:
        """Get Redis key for user's moderation history."""
        return f"community:discord:moderation:user:{user_id}:actions"

    def _get_appeal_key(self, appeal_id: str) -> str:
        """Get Redis key for appeal."""
        return f"community:discord:moderation:appeal:{appeal_id}"

    def _generate_action_id(self) -> str:
        """Generate a unique action ID."""
        import uuid

        return str(uuid.uuid4())[:12]

    async def _store_action(self, entry: ModerationLogEntry) -> None:
        """Store moderation action in Redis and local cache."""
        self._active_actions[entry.action_id] = entry

        if self._redis:
            try:
                from tools.redis_state import redis_state_set

                key = self._get_action_key(entry.action_id)
                redis_state_set(key, json.dumps(entry.to_dict()))

                # Add to user's action history
                self._get_user_actions_key(entry.target_user_id)
                # Would use list append in real implementation

            except Exception as e:
                logger.warning(f"Failed to store moderation action in Redis: {e}")

    async def kick_user(
        self,
        target_user_id: str,
        target_user_name: str,
        moderator_id: str,
        moderator_name: str,
        reason: str,
    ) -> str:
        """Kick a user from the server.

        Args:
            target_user_id: Discord user ID to kick
            target_user_name: Username for logging
            moderator_id: Discord user ID of moderator
            moderator_name: Username of moderator
            reason: Reason for kick

        Returns:
            Action ID
        """
        action_id = self._generate_action_id()

        entry = ModerationLogEntry(
            action_id=action_id,
            action_type=ModerationAction.KICK,
            target_user_id=target_user_id,
            target_user_name=target_user_name,
            moderator_id=moderator_id,
            moderator_name=moderator_name,
            reason=reason,
            status=ActionStatus.ACTIVE,
        )

        await self._store_action(entry)

        logger.info(
            f"Kicked user {target_user_name} ({target_user_id}) by {moderator_name}: {reason}"
        )

        return action_id

    async def ban_user(
        self,
        target_user_id: str,
        target_user_name: str,
        moderator_id: str,
        moderator_name: str,
        reason: str,
        permanent: bool = True,
        duration_minutes: int | None = None,
    ) -> str:
        """Ban a user from the server.

        Args:
            target_user_id: Discord user ID to ban
            target_user_name: Username for logging
            moderator_id: Discord user ID of moderator
            moderator_name: Username of moderator
            reason: Reason for ban
            permanent: Whether ban is permanent
            duration_minutes: Duration for temp ban (required if not permanent)

        Returns:
            Action ID
        """
        action_id = self._generate_action_id()

        expires_at = None
        if not permanent and duration_minutes:
            expires_at = datetime.now(UTC) + timedelta(minutes=duration_minutes)

        action_type = ModerationAction.BAN if permanent else ModerationAction.TEMP_BAN

        entry = ModerationLogEntry(
            action_id=action_id,
            action_type=action_type,
            target_user_id=target_user_id,
            target_user_name=target_user_name,
            moderator_id=moderator_id,
            moderator_name=moderator_name,
            reason=reason,
            status=ActionStatus.ACTIVE,
            expires_at=expires_at,
            metadata={"permanent": permanent, "duration_minutes": duration_minutes},
        )

        await self._store_action(entry)

        logger.info(
            f"Banned user {target_user_name} ({target_user_id}) by {moderator_name}: "
            f"{reason} (permanent={permanent})"
        )

        return action_id

    async def mute_user(
        self,
        target_user_id: str,
        target_user_name: str,
        moderator_id: str,
        moderator_name: str,
        reason: str,
        duration_minutes: int | None = None,
    ) -> str:
        """Mute a user in the server.

        Args:
            target_user_id: Discord user ID to mute
            target_user_name: Username for logging
            moderator_id: Discord user ID of moderator
            moderator_name: Username of moderator
            reason: Reason for mute
            duration_minutes: Duration of mute (uses default if None)

        Returns:
            Action ID
        """
        action_id = self._generate_action_id()
        duration = duration_minutes or self._default_mute_duration
        expires_at = datetime.now(UTC) + timedelta(minutes=duration)

        entry = ModerationLogEntry(
            action_id=action_id,
            action_type=ModerationAction.MUTE,
            target_user_id=target_user_id,
            target_user_name=target_user_name,
            moderator_id=moderator_id,
            moderator_name=moderator_name,
            reason=reason,
            status=ActionStatus.ACTIVE,
            expires_at=expires_at,
            metadata={"duration_minutes": duration},
        )

        await self._store_action(entry)

        logger.info(
            f"Muted user {target_user_name} ({target_user_id}) by {moderator_name} "
            f"for {duration} minutes: {reason}"
        )

        return action_id

    async def unmute_user(
        self,
        target_user_id: str,
        moderator_id: str,
        moderator_name: str,
        reason: str = "Unmuted by moderator",
    ) -> str | None:
        """Unmute a user.

        Args:
            target_user_id: Discord user ID to unmute
            moderator_id: Discord user ID of moderator
            moderator_name: Username of moderator
            reason: Reason for unmute

        Returns:
            Action ID of unmute action or None if no active mute found
        """
        # Find active mute for user
        active_mute = None
        for action in self._active_actions.values():
            if (
                action.target_user_id == target_user_id
                and action.action_type == ModerationAction.MUTE
                and action.status == ActionStatus.ACTIVE
            ):
                active_mute = action
                break

        if not active_mute:
            return None

        action_id = self._generate_action_id()

        # Revoke the mute
        active_mute.status = ActionStatus.REVOKED

        # Create unmute entry
        entry = ModerationLogEntry(
            action_id=action_id,
            action_type=ModerationAction.UNMUTE,
            target_user_id=target_user_id,
            target_user_name=active_mute.target_user_name,
            moderator_id=moderator_id,
            moderator_name=moderator_name,
            reason=reason,
            status=ActionStatus.ACTIVE,
            metadata={"original_mute_id": active_mute.action_id},
        )

        await self._store_action(entry)

        logger.info(f"Unmuted user {active_mute.target_user_name} by {moderator_name}")

        return action_id

    async def warn_user(
        self,
        target_user_id: str,
        target_user_name: str,
        moderator_id: str,
        moderator_name: str,
        reason: str,
    ) -> str:
        """Issue a warning to a user.

        Args:
            target_user_id: Discord user ID to warn
            target_user_name: Username for logging
            moderator_id: Discord user ID of moderator
            moderator_name: Username of moderator
            reason: Reason for warning

        Returns:
            Action ID
        """
        action_id = self._generate_action_id()

        entry = ModerationLogEntry(
            action_id=action_id,
            action_type=ModerationAction.WARN,
            target_user_id=target_user_id,
            target_user_name=target_user_name,
            moderator_id=moderator_id,
            moderator_name=moderator_name,
            reason=reason,
            status=ActionStatus.ACTIVE,
        )

        await self._store_action(entry)

        logger.info(
            f"Warned user {target_user_name} ({target_user_id}) by {moderator_name}: {reason}"
        )

        return action_id

    async def get_action(self, action_id: str) -> ModerationLogEntry | None:
        """Get a moderation action by ID.

        Args:
            action_id: Action ID

        Returns:
            ModerationLogEntry or None
        """
        if action_id in self._active_actions:
            return self._active_actions[action_id]

        if self._redis:
            try:
                from tools.redis_state import redis_state_get

                key = self._get_action_key(action_id)
                data = redis_state_get(key)
                if data:
                    return ModerationLogEntry.from_dict(json.loads(data))

            except Exception as e:
                logger.warning(f"Failed to get action from Redis: {e}")

        return None

    async def get_user_actions(
        self,
        target_user_id: str,
        limit: int = 20,
    ) -> list[ModerationLogEntry]:
        """Get moderation history for a user.

        Args:
            target_user_id: Discord user ID
            limit: Maximum number of entries to return

        Returns:
            List of ModerationLogEntry
        """
        user_actions = [
            action
            for action in self._active_actions.values()
            if action.target_user_id == target_user_id
        ]

        # Sort by creation time, newest first
        user_actions.sort(key=lambda x: x.created_at, reverse=True)

        return user_actions[:limit]

    async def get_active_mute(
        self,
        target_user_id: str,
    ) -> ModerationLogEntry | None:
        """Get active mute for a user.

        Args:
            target_user_id: Discord user ID

        Returns:
            ModerationLogEntry for active mute or None
        """
        for action in self._active_actions.values():
            if (
                action.target_user_id == target_user_id
                and action.action_type == ModerationAction.MUTE
                and action.status == ActionStatus.ACTIVE
            ):
                # Check if expired
                if action.expires_at and action.expires_at < datetime.now(UTC):
                    action.status = ActionStatus.EXPIRED
                    continue
                return action

        return None

    async def submit_appeal(
        self,
        action_id: str,
        user_id: str,
        user_name: str,
        reason: str,
    ) -> str:
        """Submit an appeal for a moderation action.

        Args:
            action_id: Action ID to appeal
            user_id: Discord user ID submitting appeal
            user_name: Username for logging
            reason: Reason for appeal

        Returns:
            Appeal ID
        """
        import uuid

        appeal_id = str(uuid.uuid4())[:12]

        appeal = Appeal(
            appeal_id=appeal_id,
            action_id=action_id,
            user_id=user_id,
            user_name=user_name,
            reason=reason,
        )

        if self._redis:
            try:
                from tools.redis_state import redis_state_set

                key = self._get_appeal_key(appeal_id)
                redis_state_set(key, json.dumps(appeal.to_dict()))

            except Exception as e:
                logger.warning(f"Failed to store appeal in Redis: {e}")

        logger.info(f"Appeal submitted by {user_name} for action {action_id}")

        return appeal_id

    async def process_expired_actions(self) -> int:
        """Mark expired temporary actions as expired.

        Returns:
            Number of actions expired
        """
        expired_count = 0
        now = datetime.now(UTC)

        for action in self._active_actions.values():
            if (
                action.status == ActionStatus.ACTIVE
                and action.expires_at
                and action.expires_at < now
            ):
                action.status = ActionStatus.EXPIRED
                expired_count += 1

        if expired_count > 0:
            logger.info(f"Processed {expired_count} expired moderation actions")

        return expired_count
