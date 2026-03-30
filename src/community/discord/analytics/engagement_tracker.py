"""Engagement tracking for Discord community."""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ParticipationLevel(Enum):
    """User participation level."""

    INACTIVE = "inactive"
    Lurker = "lurker"
    PARTICIPANT = "participant"
    ACTIVE = "active"
    POWER_USER = "power_user"
    COMMUNITY_LEADER = "community_leader"


@dataclass
class UserParticipation:
    """A user's participation data."""

    user_id: str
    user_name: str
    messages_count: int = 0
    reactions_count: int = 0
    threads_created: int = 0
    helpful_votes_received: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    last_active_date: datetime | None = None
    joined_date: datetime | None = None
    participation_level: ParticipationLevel = ParticipationLevel.INACTIVE
    engagement_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "messages_count": self.messages_count,
            "reactions_count": self.reactions_count,
            "threads_created": self.threads_created,
            "helpful_votes_received": self.helpful_votes_received,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "last_active_date": (
                self.last_active_date.isoformat() if self.last_active_date else None
            ),
            "joined_date": self.joined_date.isoformat() if self.joined_date else None,
            "participation_level": self.participation_level.value,
            "engagement_score": self.engagement_score,
        }


@dataclass
class LeaderboardEntry:
    """A leaderboard entry."""

    rank: int
    user_id: str
    user_name: str
    engagement_score: float
    messages_count: int
    participation_level: ParticipationLevel
    badge: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rank": self.rank,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "engagement_score": self.engagement_score,
            "messages_count": self.messages_count,
            "participation_level": self.participation_level.value,
            "badge": self.badge,
        }


class EngagementTracker:
    """Track user participation and engagement.

    Calculates engagement scores, tracks participation streaks,
    identifies helpful community members, and generates leaderboards.
    """

    # Engagement score weights
    MESSAGE_WEIGHT = 1.0
    REACTION_WEIGHT = 0.5
    THREAD_WEIGHT = 3.0
    HELPFUL_VOTE_WEIGHT = 2.0
    STREAK_BONUS = 0.1  # 10% bonus per day of streak

    # Participation level thresholds
    LEVEL_THRESHOLDS = {
        ParticipationLevel.INACTIVE: 0,
        ParticipationLevel.Lurker: 1,
        ParticipationLevel.PARTICIPANT: 10,
        ParticipationLevel.ACTIVE: 50,
        ParticipationLevel.POWER_USER: 200,
        ParticipationLevel.COMMUNITY_LEADER: 500,
    }

    # Badges for achievements
    BADGES = {
        "streak_7": "🔥 7-Day Streak",
        "streak_30": "⚡ 30-Day Streak",
        "messages_100": "💬 100 Messages",
        "messages_1000": "💬 1000 Messages",
        "helpful_50": "👍 50 Helpful Votes",
        "first_post": "🌟 First Post",
        "power_user": "⭐ Power User",
        "community_hero": "🏆 Community Hero",
    }

    def __init__(
        self,
        redis_client: Any = None,
        streak_reset_hours: int = 48,
    ):
        """Initialize EngagementTracker.

        Args:
            redis_client: Redis client for storing engagement data
            streak_reset_hours: Hours of inactivity before streak resets
        """
        self._redis = redis_client
        self._streak_reset_hours = streak_reset_hours
        self._participation_cache: dict[str, UserParticipation] = {}

    def _get_participation_key(self, user_id: str) -> str:
        """Get Redis key for user participation."""
        return f"community:discord:engagement:user:{user_id}"

    def _get_activity_key(self, user_id: str, date: str) -> str:
        """Get Redis key for daily activity."""
        return f"community:discord:engagement:user:{user_id}:activity:{date}"

    def _calculate_engagement_score(
        self,
        participation: UserParticipation,
    ) -> float:
        """Calculate engagement score for a user.

        Args:
            participation: UserParticipation data

        Returns:
            Engagement score
        """
        score = (
            participation.messages_count * self.MESSAGE_WEIGHT
            + participation.reactions_count * self.REACTION_WEIGHT
            + participation.threads_created * self.THREAD_WEIGHT
            + participation.helpful_votes_received * self.HELPFUL_VOTE_WEIGHT
        )

        # Add streak bonus
        streak_bonus = participation.current_streak * self.STREAK_BONUS
        score *= 1 + streak_bonus

        return round(score, 2)

    def _determine_participation_level(
        self,
        engagement_score: float,
    ) -> ParticipationLevel:
        """Determine participation level based on score.

        Args:
            engagement_score: User's engagement score

        Returns:
            ParticipationLevel
        """
        if (
            engagement_score
            >= self.LEVEL_THRESHOLDS[ParticipationLevel.COMMUNITY_LEADER]
        ):
            return ParticipationLevel.COMMUNITY_LEADER
        elif engagement_score >= self.LEVEL_THRESHOLDS[ParticipationLevel.POWER_USER]:
            return ParticipationLevel.POWER_USER
        elif engagement_score >= self.LEVEL_THRESHOLDS[ParticipationLevel.ACTIVE]:
            return ParticipationLevel.ACTIVE
        elif engagement_score >= self.LEVEL_THRESHOLDS[ParticipationLevel.PARTICIPANT]:
            return ParticipationLevel.PARTICIPANT
        elif engagement_score >= self.LEVEL_THRESHOLDS[ParticipationLevel.Lurker]:
            return ParticipationLevel.Lurker
        else:
            return ParticipationLevel.INACTIVE

    def _get_badges(self, participation: UserParticipation) -> list[str]:
        """Get earned badges for a user.

        Args:
            participation: UserParticipation data

        Returns:
            List of badge IDs
        """
        badges: list[str] = []

        if participation.current_streak >= 30:
            badges.append("streak_30")
        elif participation.current_streak >= 7:
            badges.append("streak_7")

        if participation.messages_count >= 1000:
            badges.append("messages_1000")
        elif participation.messages_count >= 100:
            badges.append("messages_100")

        if participation.helpful_votes_received >= 50:
            badges.append("helpful_50")

        if participation.messages_count >= 1:
            badges.append("first_post")

        if participation.participation_level == ParticipationLevel.POWER_USER:
            badges.append("power_user")
        elif participation.participation_level == ParticipationLevel.COMMUNITY_LEADER:
            badges.append("community_hero")

        return badges

    async def record_activity(
        self,
        user_id: str,
        user_name: str,
        activity_type: str,
        count: int = 1,
    ) -> None:
        """Record a user activity.

        Args:
            user_id: Discord user ID
            user_name: Discord username
            activity_type: Type of activity ('message', 'reaction', 'thread', 'helpful')
            count: Number of activities
        """
        participation = await self.get_participation(user_id)
        if not participation:
            participation = UserParticipation(
                user_id=user_id,
                user_name=user_name,
                joined_date=datetime.now(),
            )

        participation.user_name = user_name

        # Update counts
        if activity_type == "message":
            participation.messages_count += count
        elif activity_type == "reaction":
            participation.reactions_count += count
        elif activity_type == "thread":
            participation.threads_created += count
        elif activity_type == "helpful":
            participation.helpful_votes_received += count

        # Update streak
        await self._update_streak(user_id, participation)

        # Update last active
        participation.last_active_date = datetime.now(UTC)

        # Recalculate score and level
        participation.engagement_score = self._calculate_engagement_score(participation)
        participation.participation_level = self._determine_participation_level(
            participation.engagement_score
        )

        await self._store_participation(participation)

    async def _update_streak(
        self,
        user_id: str,
        participation: UserParticipation,
    ) -> None:
        """Update user's participation streak.

        Args:
            user_id: Discord user ID
            participation: UserParticipation to update
        """
        today = datetime.now(UTC).date()
        last_active = participation.last_active_date

        if last_active is None:
            participation.current_streak = 1
        else:
            last_date = last_active.date()
            days_diff = (today - last_date).days

            if days_diff == 0:
                # Same day, no change
                pass
            elif days_diff == 1:
                # Consecutive day, increment streak
                participation.current_streak += 1
            elif days_diff <= self._streak_reset_hours / 24:
                # Within grace period, maintain streak
                pass
            else:
                # Streak broken
                participation.current_streak = 1

        # Update longest streak
        if participation.current_streak > participation.longest_streak:
            participation.longest_streak = participation.current_streak

    async def _store_participation(self, participation: UserParticipation) -> None:
        """Store user participation data.

        Args:
            participation: UserParticipation to store
        """
        self._participation_cache[participation.user_id] = participation

        if self._redis:
            try:
                from tools.redis_state import redis_state_set

                key = self._get_participation_key(participation.user_id)
                redis_state_set(key, json.dumps(participation.to_dict()))

            except Exception as e:
                logger.warning(f"Failed to store participation in Redis: {e}")

    async def get_participation(self, user_id: str) -> UserParticipation | None:
        """Get user participation data.

        Args:
            user_id: Discord user ID

        Returns:
            UserParticipation or None
        """
        if user_id in self._participation_cache:
            return self._participation_cache[user_id]

        if not self._redis:
            return None

        try:
            from tools.redis_state import redis_state_get

            key = self._get_participation_key(user_id)
            data = redis_state_get(key)

            if data:
                parsed = json.loads(data)

                # Parse dates
                last_active = parsed.get("last_active_date")
                if last_active and isinstance(last_active, str):
                    parsed["last_active_date"] = datetime.fromisoformat(last_active)
                joined = parsed.get("joined_date")
                if joined and isinstance(joined, str):
                    parsed["joined_date"] = datetime.fromisoformat(joined)

                level = parsed.get("participation_level", "inactive")
                parsed["participation_level"] = ParticipationLevel(level)

                participation = UserParticipation(**parsed)
                self._participation_cache[user_id] = participation
                return participation

        except Exception as e:
            logger.warning(f"Failed to get participation from Redis: {e}")

        return None

    async def get_leaderboard(
        self,
        limit: int = 20,
        period_days: int | None = None,
        metric: str = "engagement_score",
    ) -> list[LeaderboardEntry]:
        """Generate engagement leaderboard.

        Args:
            limit: Number of entries to return
            period_days: Days to analyze (None for all-time)
            metric: Metric to rank by

        Returns:
            List of LeaderboardEntry
        """
        leaderboard: list[LeaderboardEntry] = []

        # Get all user participations
        participations: list[UserParticipation] = []

        # Check cache first
        for participation in self._participation_cache.values():
            if self._matches_period(participation, period_days):
                participations.append(participation)

        # Query Redis if needed
        if not participations and self._redis:
            try:
                from tools.redis_state import redis_state_get, redis_state_scan_keys

                pattern = "community:discord:engagement:user:*"
                keys = redis_state_scan_keys(pattern, count=100)

                for key in keys:
                    data = redis_state_get(key)
                    if data:
                        parsed = json.loads(data)
                        level = parsed.get("participation_level", "inactive")
                        parsed["participation_level"] = ParticipationLevel(level)
                        participation = UserParticipation(**parsed)
                        if self._matches_period(participation, period_days):
                            participations.append(participation)

            except Exception as e:
                logger.warning(f"Failed to get leaderboard from Redis: {e}")

        # Sort by metric
        if metric == "engagement_score":
            participations.sort(key=lambda x: x.engagement_score, reverse=True)
        elif metric == "messages":
            participations.sort(key=lambda x: x.messages_count, reverse=True)
        elif metric == "streak":
            participations.sort(key=lambda x: x.current_streak, reverse=True)

        # Build leaderboard
        for rank, participation in enumerate(participations[:limit], 1):
            badges = self._get_badges(participation)
            badge = badges[0] if badges else None

            leaderboard.append(
                LeaderboardEntry(
                    rank=rank,
                    user_id=participation.user_id,
                    user_name=participation.user_name,
                    engagement_score=participation.engagement_score,
                    messages_count=participation.messages_count,
                    participation_level=participation.participation_level,
                    badge=badge,
                )
            )

        return leaderboard

    def _matches_period(
        self,
        participation: UserParticipation,
        period_days: int | None,
    ) -> bool:
        """Check if participation is within period.

        Args:
            participation: UserParticipation to check
            period_days: Days to check (None for all-time)

        Returns:
            True if within period
        """
        if period_days is None:
            return True

        if participation.last_active_date is None:
            return False

        cutoff = datetime.now(UTC) - timedelta(days=period_days)
        return participation.last_active_date >= cutoff

    async def get_most_helpful_members(
        self,
        limit: int = 10,
    ) -> list[UserParticipation]:
        """Get most helpful community members by votes received.

        Args:
            limit: Number of members to return

        Returns:
            List of UserParticipation
        """
        participations = list(self._participation_cache.values())

        # Sort by helpful votes
        participations.sort(key=lambda x: x.helpful_votes_received, reverse=True)

        return participations[:limit]

    async def get_participation_summary(self) -> dict[str, Any]:
        """Get overall participation summary.

        Returns:
            Summary dictionary
        """
        participations = list(self._participation_cache.values())

        if not participations and self._redis:
            try:
                from tools.redis_state import redis_state_get, redis_state_scan_keys

                pattern = "community:discord:engagement:user:*"
                keys = redis_state_scan_keys(pattern, count=100)

                for key in keys:
                    data = redis_state_get(key)
                    if data:
                        parsed = json.loads(data)
                        level = parsed.get("participation_level", "inactive")
                        parsed["participation_level"] = ParticipationLevel(level)
                        participations.append(UserParticipation(**parsed))

            except Exception as e:
                logger.warning(f"Failed to get participation summary: {e}")

        level_counts: dict[str, int] = {}
        total_messages = 0
        total_reactions = 0
        total_threads = 0

        for p in participations:
            level_counts[p.participation_level.value] = (
                level_counts.get(p.participation_level.value, 0) + 1
            )
            total_messages += p.messages_count
            total_reactions += p.reactions_count
            total_threads += p.threads_created

        return {
            "total_users": len(participations),
            "level_distribution": level_counts,
            "total_messages": total_messages,
            "total_reactions": total_reactions,
            "total_threads": total_threads,
            "avg_engagement_score": (
                sum(p.engagement_score for p in participations) / len(participations)
                if participations
                else 0
            ),
        }
