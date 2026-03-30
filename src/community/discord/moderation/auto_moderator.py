"""Auto-moderation for Discord community."""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FilterType(Enum):
    """Type of auto-moderation filter."""

    SPAM = "spam"
    PROFANITY = "profanity"
    LINK_FILTER = "link_filter"
    MENTION_SPAM = "mention_spam"
    EMOJI_SPAM = "emoji_spam"


class FilterAction(Enum):
    """Action to take when filter triggers."""

    DELETE = "delete"
    WARN = "warn"
    MUTE = "mute"
    KICK = "kick"


@dataclass
class FilterConfig:
    """Configuration for an auto-moderation filter."""

    filter_type: FilterType
    enabled: bool = True
    action: FilterAction = FilterAction.DELETE
    # For spam detection
    spam_threshold_count: int = 5
    spam_threshold_seconds: int = 10
    # For profanity
    word_list: list[str] = field(default_factory=list)
    # For links
    allow_list: list[str] = field(default_factory=list)
    block_list: list[str] = field(default_factory=list)
    # For mutes
    mute_duration_minutes: int = 10
    # Warning message
    warn_message: str = "Please follow community guidelines."
    # Cooldown
    cooldown_seconds: int = 60

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "filter_type": self.filter_type.value,
            "enabled": self.enabled,
            "action": self.action.value,
            "spam_threshold_count": self.spam_threshold_count,
            "spam_threshold_seconds": self.spam_threshold_seconds,
            "word_list": self.word_list,
            "allow_list": self.allow_list,
            "block_list": self.block_list,
            "mute_duration_minutes": self.mute_duration_minutes,
            "warn_message": self.warn_message,
            "cooldown_seconds": self.cooldown_seconds,
        }


@dataclass
class Violation:
    """A detected rule violation."""

    filter_type: FilterType
    user_id: str
    user_name: str
    content: str
    severity: int  # 1-10
    matched_content: list[str] = field(default_factory=list)
    action_taken: FilterAction | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    message_id: str | None = None
    channel_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "filter_type": self.filter_type.value,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "content": self.content[:100],  # Truncate for storage
            "severity": self.severity,
            "matched_content": self.matched_content,
            "action_taken": self.action_taken.value if self.action_taken else None,
            "timestamp": self.timestamp.isoformat(),
            "message_id": self.message_id,
            "channel_id": self.channel_id,
        }


class AutoModerator:
    """Automatic content moderation for Discord.

    Detects and takes action on spam, profanity, prohibited links,
    and other community guideline violations.
    """

    DEFAULT_SPAM_THRESHOLD = 5  # messages
    DEFAULT_SPAM_WINDOW = 10  # seconds
    DEFAULT_MUTE_DURATION = 10  # minutes
    DEFAULT_WARN_BEFORE_ACTION = True

    def __init__(
        self,
        redis_client: Any = None,
        moderation_manager: Any = None,
    ):
        """Initialize AutoModerator.

        Args:
            redis_client: Redis client for storing violations and state
            moderation_manager: ModerationManager instance for taking actions
        """
        self._redis = redis_client
        self._mod_manager = moderation_manager
        self._violations: list[Violation] = []
        self._user_message_history: dict[str, list[datetime]] = {}
        self._config: dict[FilterType, FilterConfig] = self._default_config()

    def _default_config(self) -> dict[FilterType, FilterConfig]:
        """Get default filter configuration."""
        return {
            FilterType.SPAM: FilterConfig(
                filter_type=FilterType.SPAM,
                spam_threshold_count=self.DEFAULT_SPAM_THRESHOLD,
                spam_threshold_seconds=self.DEFAULT_SPAM_WINDOW,
                action=FilterAction.DELETE,
            ),
            FilterType.PROFANITY: FilterConfig(
                filter_type=FilterType.PROFANITY,
                word_list=[
                    # Example placeholder - would be configured per community
                ],
                action=FilterAction.DELETE,
                warn_message="Please keep the chat clean.",
            ),
            FilterType.LINK_FILTER: FilterConfig(
                filter_type=FilterType.LINK_FILTER,
                block_list=["spam.link", "malware.com"],
                action=FilterAction.DELETE,
                warn_message="Prohibited links are not allowed.",
            ),
            FilterType.MENTION_SPAM: FilterConfig(
                filter_type=FilterType.MENTION_SPAM,
                spam_threshold_count=5,
                action=FilterAction.DELETE,
                warn_message="Please don't spam mentions.",
            ),
            FilterType.EMOJI_SPAM: FilterConfig(
                filter_type=FilterType.EMOJI_SPAM,
                spam_threshold_count=10,
                action=FilterAction.DELETE,
                warn_message="Please don't spam emojis.",
            ),
        }

    def update_filter_config(self, config: FilterConfig) -> None:
        """Update configuration for a filter.

        Args:
            config: New FilterConfig
        """
        self._config[config.filter_type] = config
        logger.info(f"Updated config for {config.filter_type.value}")

    def get_filter_config(self, filter_type: FilterType) -> FilterConfig | None:
        """Get configuration for a filter.

        Args:
            filter_type: Filter to get config for

        Returns:
            FilterConfig or None
        """
        return self._config.get(filter_type)

    def enable_filter(self, filter_type: FilterType) -> None:
        """Enable a filter.

        Args:
            filter_type: Filter to enable
        """
        if filter_type in self._config:
            self._config[filter_type].enabled = True

    def disable_filter(self, filter_type: FilterType) -> None:
        """Disable a filter.

        Args:
            filter_type: Filter to disable
        """
        if filter_type in self._config:
            self._config[filter_type].enabled = False

    def _check_spam(
        self,
        user_id: str,
        timestamp: datetime,
    ) -> Violation | None:
        """Check for spam (rapid repeated messages).

        Args:
            user_id: Discord user ID
            timestamp: Message timestamp

        Returns:
            Violation or None
        """
        config = self._config.get(FilterType.SPAM)
        if not config or not config.enabled:
            return None

        # Get user's message history
        if user_id not in self._user_message_history:
            self._user_message_history[user_id] = []

        history = self._user_message_history[user_id]
        cutoff = timestamp - timedelta(seconds=config.spam_threshold_seconds)

        # Remove old messages
        history = [msg_time for msg_time in history if msg_time > cutoff]
        self._user_message_history[user_id] = history

        # Add current message
        history.append(timestamp)

        # Check if over threshold
        if len(history) >= config.spam_threshold_count:
            # Calculate severity based on how far over threshold
            excess = len(history) - config.spam_threshold_count
            severity = min(5 + excess, 10)

            return Violation(
                filter_type=FilterType.SPAM,
                user_id=user_id,
                user_name="",  # Would be filled by caller
                content="",
                severity=severity,
                matched_content=[
                    f"{len(history)} messages in {config.spam_threshold_seconds}s"
                ],
            )

        return None

    def _check_profanity(
        self,
        content: str,
    ) -> Violation | None:
        """Check for profanity.

        Args:
            content: Message content

        Returns:
            Violation or None
        """
        config = self._config.get(FilterType.PROFANITY)
        if not config or not config.enabled or not config.word_list:
            return None

        content_lower = content.lower()
        matched = []

        for word in config.word_list:
            if word.lower() in content_lower:
                matched.append(word)

        if matched:
            return Violation(
                filter_type=FilterType.PROFANITY,
                user_id="",
                user_name="",
                content=content,
                severity=min(len(matched) * 2, 10),
                matched_content=matched,
            )

        return None

    def _check_links(
        self,
        content: str,
    ) -> Violation | None:
        """Check for prohibited links.

        Args:
            content: Message content

        Returns:
            Violation or None
        """
        config = self._config.get(FilterType.LINK_FILTER)
        if not config or not config.enabled:
            return None

        # Find URLs in content
        url_pattern = r"https?://[^\s]+"
        urls = re.findall(url_pattern, content)

        if not urls:
            return None

        matched = []
        for url in urls:
            url_lower = url.lower()

            # Check block list
            for blocked in config.block_list:
                if blocked.lower() in url_lower:
                    matched.append(f"BLOCKED:{url}")

            # Check allow list first
            in_allow_list = any(
                allowed.lower() in url_lower for allowed in config.allow_list
            )
            if not in_allow_list and config.allow_list:
                # If allow list is configured and URL not in it, block
                for allowed in config.allow_list:
                    if allowed.lower() in url_lower:
                        break
                else:
                    matched.append(f"NOT_ALLOWED:{url}")

        if matched:
            return Violation(
                filter_type=FilterType.LINK_FILTER,
                user_id="",
                user_name="",
                content=content,
                severity=8,
                matched_content=matched,
            )

        return None

    def _check_mention_spam(
        self,
        content: str,
    ) -> Violation | None:
        """Check for mention spam.

        Args:
            content: Message content

        Returns:
            Violation or None
        """
        config = self._config.get(FilterType.MENTION_SPAM)
        if not config or not config.enabled:
            return None

        # Count mentions
        mention_pattern = r"<@!?\d+>"
        mentions = re.findall(mention_pattern, content)

        if len(mentions) >= config.spam_threshold_count:
            return Violation(
                filter_type=FilterType.MENTION_SPAM,
                user_id="",
                user_name="",
                content=content,
                severity=min(5 + len(mentions) - config.spam_threshold_count, 10),
                matched_content=[f"{len(mentions)} mentions"],
            )

        return None

    def _check_emoji_spam(
        self,
        content: str,
    ) -> Violation | None:
        """Check for emoji spam.

        Args:
            content: Message content

        Returns:
            Violation or None
        """
        config = self._config.get(FilterType.EMOJI_SPAM)
        if not config or not config.enabled:
            return None

        # Count emoji (unicode emoji ranges + custom emoji)
        emoji_pattern = r"<(a)?:[a-zA-Z0-9_]+:[0-9]+>"
        custom_emoji = len(re.findall(emoji_pattern, content))

        # Also count unicode emoji
        unicode_emoji = len(
            re.findall(
                r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]",
                content,
            )
        )

        total_emoji = custom_emoji + unicode_emoji

        if total_emoji >= config.spam_threshold_count:
            return Violation(
                filter_type=FilterType.EMOJI_SPAM,
                user_id="",
                user_name="",
                content=content,
                severity=min(3 + total_emoji - config.spam_threshold_count, 10),
                matched_content=[f"{total_emoji} emojis"],
            )

        return None

    async def check_message(
        self,
        user_id: str,
        user_name: str,
        content: str,
        message_id: str | None = None,
        channel_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> list[Violation]:
        """Check a message for violations.

        Args:
            user_id: Discord user ID
            user_name: Discord username
            content: Message content
            message_id: Discord message ID
            channel_id: Discord channel ID
            timestamp: Message timestamp

        Returns:
            List of violations found
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        violations: list[Violation] = []

        # Run all checks
        spam_violation = self._check_spam(user_id, timestamp)
        if spam_violation:
            spam_violation.user_id = user_id
            spam_violation.user_name = user_name
            spam_violation.message_id = message_id
            spam_violation.channel_id = channel_id
            violations.append(spam_violation)

        profanity_violation = self._check_profanity(content)
        if profanity_violation:
            profanity_violation.user_id = user_id
            profanity_violation.user_name = user_name
            profanity_violation.message_id = message_id
            profanity_violation.channel_id = channel_id
            violations.append(profanity_violation)

        link_violation = self._check_links(content)
        if link_violation:
            link_violation.user_id = user_id
            link_violation.user_name = user_name
            link_violation.message_id = message_id
            link_violation.channel_id = channel_id
            violations.append(link_violation)

        mention_violation = self._check_mention_spam(content)
        if mention_violation:
            mention_violation.user_id = user_id
            mention_violation.user_name = user_name
            mention_violation.message_id = message_id
            mention_violation.channel_id = channel_id
            violations.append(mention_violation)

        emoji_violation = self._check_emoji_spam(content)
        if emoji_violation:
            emoji_violation.user_id = user_id
            emoji_violation.user_name = user_name
            emoji_violation.message_id = message_id
            emoji_violation.channel_id = channel_id
            violations.append(emoji_violation)

        # Store violations
        self._violations.extend(violations)

        return violations

    async def take_action(
        self,
        violation: Violation,
        warn_before_action: bool = DEFAULT_WARN_BEFORE_ACTION,
        bot_user_id: str = "auto_mod",
        bot_user_name: str = "AutoMod",
    ) -> bool:
        """Take action on a violation.

        Args:
            violation: The violation to act on
            warn_before_action: Whether to warn before taking harsh action
            bot_user_id: User ID for the moderation actions
            bot_user_name: Username for the moderation actions

        Returns:
            True if action was taken
        """
        config = self._config.get(violation.filter_type)
        if not config:
            return False

        action = config.action

        # Warning before mute/kick
        if action in (FilterAction.MUTE, FilterAction.KICK) and warn_before_action:
            # Would send warning message here
            logger.info(f"Would warn {violation.user_name} before {action.value}")

        if action == FilterAction.DELETE:
            # Would delete the message here
            logger.info(
                f"Would delete message from {violation.user_name}: {violation.matched_content}"
            )
            violation.action_taken = FilterAction.DELETE
            return True

        elif action == FilterAction.WARN:
            if self._mod_manager:
                await self._mod_manager.warn_user(
                    target_user_id=violation.user_id,
                    target_user_name=violation.user_name,
                    moderator_id=bot_user_id,
                    moderator_name=bot_user_name,
                    reason=f"Auto-moderation: {violation.filter_type.value}",
                )
            violation.action_taken = FilterAction.WARN
            return True

        elif action == FilterAction.MUTE:
            if self._mod_manager:
                await self._mod_manager.mute_user(
                    target_user_id=violation.user_id,
                    target_user_name=violation.user_name,
                    moderator_id=bot_user_id,
                    moderator_name=bot_user_name,
                    reason=f"Auto-moderation: {violation.filter_type.value}",
                    duration_minutes=config.mute_duration_minutes,
                )
            violation.action_taken = FilterAction.MUTE
            return True

        elif action == FilterAction.KICK:
            if self._mod_manager:
                await self._mod_manager.kick_user(
                    target_user_id=violation.user_id,
                    target_user_name=violation.user_name,
                    moderator_id=bot_user_id,
                    moderator_name=bot_user_name,
                    reason=f"Auto-moderation: {violation.filter_type.value}",
                )
            violation.action_taken = FilterAction.KICK
            return True

        return False

    async def get_violations(
        self,
        user_id: str | None = None,
        filter_type: FilterType | None = None,
        limit: int = 100,
    ) -> list[Violation]:
        """Get recorded violations.

        Args:
            user_id: Filter by user ID
            filter_type: Filter by type
            limit: Maximum number to return

        Returns:
            List of violations
        """
        violations = list(self._violations)

        if user_id:
            violations = [v for v in violations if v.user_id == user_id]

        if filter_type:
            violations = [v for v in violations if v.filter_type == filter_type]

        # Sort by timestamp, newest first
        violations.sort(key=lambda x: x.timestamp, reverse=True)

        return violations[:limit]

    def get_violation_stats(self) -> dict[str, Any]:
        """Get violation statistics.

        Returns:
            Dictionary of statistics
        """
        total = len(self._violations)
        by_type: dict[str, int] = {}
        by_action: dict[str, int] = {}

        for v in self._violations:
            type_key = v.filter_type.value
            by_type[type_key] = by_type.get(type_key, 0) + 1
            if v.action_taken:
                action_key = v.action_taken.value
                by_action[action_key] = by_action.get(action_key, 0) + 1

        return {
            "total_violations": total,
            "by_filter_type": by_type,
            "by_action_taken": by_action,
        }
