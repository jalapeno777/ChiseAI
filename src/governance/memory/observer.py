"""
Observer Core Module for ChiseAI.

Monitors and accumulates conversation messages for analysis.

Feature Flag: chise:feature_flags:observations:observer_enabled
Default: Disabled (safe rollout)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Feature flag key in Redis
FEATURE_FLAG_KEY = "chise:feature_flags:observations:observer_enabled"

# Redis key prefix for raw observation messages
RAW_OBSERVATIONS_KEY_PREFIX = "chise:observations:raw:"

# Redis key for observer state
OBSERVER_STATE_KEY = "chise:observations:observer:state"

# Default token threshold for triggering extraction
DEFAULT_TOKEN_THRESHOLD = 30000

# TTL for raw observations list (24 hours in seconds)
RAW_OBSERVATIONS_TTL = 24 * 3600

# TTL for active observations sorted set (7 days)
ACTIVE_OBSERVATIONS_TTL = 7 * 24 * 3600

# Redis key prefixes
OBSERVATIONS_RAW_PREFIX = "chise:observations:raw"
OBSERVATIONS_ACTIVE_PREFIX = "chise:observations:active"


@dataclass
class Observation:
    """
    Represents a single extracted observation from a session.

    Attributes:
        content: The text content of the observation.
        timestamp: ISO8601 timestamp when the observation was created.
        category: One of decision/pattern/fact/preference/event.
        priority: One of high/medium/low.
        session_id: The session identifier this observation belongs to.
        confidence: Confidence score between 0.0 and 1.0.
        source_message_ids: List of message IDs that contributed to this observation.
    """

    content: str
    timestamp: str
    category: str
    priority: str
    session_id: str
    confidence: float = 0.7
    source_message_ids: list[str] = field(default_factory=list)


class Observer:
    """Observer for accumulating and monitoring conversation messages.

    Attributes:
        session_id: Unique identifier for the observation session.
        redis_client: Redis client for message storage.
        qdrant_client: Qdrant client for vector operations.
        threshold: Token count threshold for triggering extraction (default 30000).
    """

    def __init__(
        self,
        session_id: str,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
        threshold: int = DEFAULT_TOKEN_THRESHOLD,
    ) -> None:
        """Initialize the Observer.

        Args:
            session_id: Unique identifier for this observation session.
            redis_client: Optional pre-configured Redis client.
            qdrant_client: Optional pre-configured Qdrant client.
            threshold: Token count threshold for triggering extraction.
        """
        self.session_id = session_id
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client
        self.threshold = threshold
        self._redis: Any | None = None
        self._qdrant: Any | None = None

    def _get_redis_client(self) -> Any | None:
        """Get or create Redis client.

        Returns:
            Redis client instance or None if connection fails.
        """
        if self._redis_client is not None:
            return self._redis_client

        if self._redis is not None:
            return self._redis

        try:
            import redis as redis_lib

            self._redis = redis_lib.Redis(
                host="host.docker.internal",
                port=6380,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            self._redis.ping()
            return self._redis
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            return None

    def _get_qdrant_client(self) -> Any | None:
        """Get or create Qdrant client.

        Returns:
            QdrantClient instance or None if connection fails.
        """
        if self._qdrant_client is not None:
            return self._qdrant_client

        if self._qdrant is not None:
            return self._qdrant

        try:
            from qdrant_client import QdrantClient

            self._qdrant = QdrantClient(
                host="host.docker.internal",
                port=6334,
                timeout=10,
            )
            return self._qdrant
        except ImportError:
            logger.error("qdrant_client package not installed")
            return None
        except Exception as e:
            logger.warning(f"Qdrant connection failed: {e}")
            return None

    def _is_feature_enabled(self) -> bool:
        """Check if observer feature flag is enabled.

        Returns:
            True if feature flag is set to 'true', False otherwise.
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            logger.warning("Redis not available, cannot check feature flag")
            return False

        try:
            flag_value = redis_client.get(FEATURE_FLAG_KEY)
            return flag_value is not None and flag_value.lower() == "true"
        except Exception as e:
            logger.warning(f"Failed to check feature flag: {e}")
            return False

    def accumulate_message(self, session_id: str, message: str) -> bool:
        """Accumulate a message for the given session.

        Appends the message to a Redis list with timestamp and 24h TTL.
        Must check feature flag first - if not enabled, logs and returns without writing.

        Args:
            session_id: Session identifier for the conversation.
            message: The message content to accumulate.

        Returns:
            True if message was accumulated, False if feature disabled or error.
        """
        # Check feature flag FIRST
        if not self._is_feature_enabled():
            logger.debug(
                f"Observer feature not enabled, skipping message accumulation "
                f"for session {session_id}"
            )
            return False

        redis_client = self._get_redis_client()
        if redis_client is None:
            logger.error("Redis client not available for message accumulation")
            return False

        try:
            key = f"{RAW_OBSERVATIONS_KEY_PREFIX}{session_id}"
            payload = json.dumps(
                {
                    "message": message,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            redis_client.rpush(key, payload)
            redis_client.expire(key, RAW_OBSERVATIONS_TTL)
            logger.debug(
                f"Accumulated message for session {session_id}, "
                f"key {key} set with {RAW_OBSERVATIONS_TTL}s TTL"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to accumulate message: {e}")
            return False

    def get_token_count(self, session_id: str) -> int:
        """Get estimated token count for accumulated messages.

        Uses simple word-based estimation (words * 1.3) for Phase 1.
        TODO: Phase 2 - integrate tiktoken for accurate token counting.

        Args:
            session_id: Session identifier to count tokens for.

        Returns:
            Estimated token count based on word count * 1.3.
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            logger.warning("Redis client not available for token count")
            return 0

        try:
            key = f"{RAW_OBSERVATIONS_KEY_PREFIX}{session_id}"
            messages = redis_client.lrange(key, 0, -1)

            total_tokens = 0
            for msg_json in messages:
                try:
                    payload = json.loads(msg_json)
                    message_text = payload.get("message", "")
                    # Simple word-based token estimation: words * 1.3
                    word_count = len(message_text.split())
                    # TODO: Phase 2 - replace with tiktoken for accurate counting:
                    # import tiktoken
                    # enc = tiktoken.get_encoding("cl100k_base")
                    # token_count = len(enc.encode(message_text))
                    token_count = int(word_count * 1.3)
                    total_tokens += token_count
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse message payload: {e}")
                    continue

            logger.debug(
                f"Token count for session {session_id}: {total_tokens} "
                f"(from {len(messages)} messages)"
            )
            return total_tokens
        except Exception as e:
            logger.error(f"Failed to get token count: {e}")
            return 0

    def check_threshold(self, session_id: str) -> bool:
        """Check if token count has reached the threshold.

        Args:
            session_id: Session identifier to check.

        Returns:
            True if token_count >= threshold, False otherwise.
        """
        token_count = self.get_token_count(session_id)
        exceeded = token_count >= self.threshold

        if exceeded:
            logger.info(
                f"Threshold exceeded for session {session_id}: "
                f"{token_count} >= {self.threshold}"
            )
        else:
            logger.debug(
                f"Threshold not exceeded for session {session_id}: "
                f"{token_count} < {self.threshold}"
            )

        return exceeded

    def get_state(self) -> dict[str, Any]:
        """Get current observer state.

        Returns:
            Dictionary with last_run, token_count, and threshold.
            State is stored in Redis hash chise:observations:observer:state.
        """
        redis_client = self._get_redis_client()
        state: dict[str, Any] = {
            "last_run": None,
            "token_count": 0,
            "threshold": self.threshold,
        }

        if redis_client is None:
            logger.warning("Redis not available for state retrieval")
            return state

        try:
            state_data = redis_client.hgetall(OBSERVER_STATE_KEY)
            if state_data:
                state["last_run"] = state_data.get("last_run")
                state["token_count"] = int(state_data.get("token_count", 0))
                state["threshold"] = int(state_data.get("threshold", self.threshold))
            logger.debug(f"Retrieved observer state: {state}")
        except Exception as e:
            logger.error(f"Failed to get observer state: {e}")

        return state

    def update_state(self, token_count: int | None = None) -> bool:
        """Update observer state in Redis.

        Args:
            token_count: Optional token count to store. If None, uses current count.

        Returns:
            True if state was updated, False otherwise.
        """
        if not self._is_feature_enabled():
            logger.debug("Observer feature not enabled, skipping state update")
            return False

        redis_client = self._get_redis_client()
        if redis_client is None:
            logger.error("Redis client not available for state update")
            return False

        try:
            updates: dict[str, str] = {
                "last_run": datetime.now(UTC).isoformat(),
                "threshold": str(self.threshold),
            }
            if token_count is not None:
                updates["token_count"] = str(token_count)

            redis_client.hset(OBSERVER_STATE_KEY, mapping=updates)
            logger.debug(f"Updated observer state: {updates}")
            return True
        except Exception as e:
            logger.error(f"Failed to update observer state: {e}")
            return False

    # -------------------------------------------------------------------------
    # Observation Extraction Methods (Task T2)
    # -------------------------------------------------------------------------

    def _llm_extract(self, messages: list[dict]) -> list[dict]:
        """
        Pattern-based mock extraction for Phase 1.

        This is NOT real LLM extraction - it's a placeholder that uses
        keyword patterns to categorize observations.

        Args:
            messages: List of message dicts with 'content' and optional 'id'.

        Returns:
            List of observation dicts with keys: content, category, priority,
            confidence, timestamp, source_message_ids.
        """
        observations = []
        decision_keywords = ["decided", "chose", "agreed", "confirmed"]
        pattern_keywords = ["pattern", "trend", "observed", "noticed"]
        preference_keywords = ["prefer", "like", "want", "need"]
        event_keywords = ["happened", "occurred", "completed", "failed"]
        high_priority_keywords = ["critical", "important", "must", "safety"]
        medium_priority_keywords = ["should", "prefer"]

        for msg in messages:
            content = msg.get("content", "")
            msg_id = msg.get("id", "unknown")

            if not content:
                continue

            # Categorize based on keywords
            category = "fact"  # default
            for kw in decision_keywords:
                if kw in content.lower():
                    category = "decision"
                    break

            if category == "fact":
                for kw in pattern_keywords:
                    if kw in content.lower():
                        category = "pattern"
                        break

            if category == "fact":
                for kw in preference_keywords:
                    if kw in content.lower():
                        category = "preference"
                        break

            if category == "fact":
                for kw in event_keywords:
                    if kw in content.lower():
                        category = "event"
                        break

            # Determine priority
            priority = "low"  # default
            for kw in high_priority_keywords:
                if kw in content.lower():
                    priority = "high"
                    break

            if priority == "low":
                for kw in medium_priority_keywords:
                    if kw in content.lower():
                        priority = "medium"
                        break

            observations.append(
                {
                    "content": content,
                    "category": category,
                    "priority": priority,
                    "confidence": 0.7,  # mock confidence
                    "timestamp": datetime.now(UTC).isoformat(),
                    "source_message_ids": [msg_id],
                }
            )

        return observations

    def extract_observations(
        self,
        session_id: str,
        prompt_template: str | None = None,
        dry_run: bool = False,
    ) -> list[Observation]:
        """
        Extract observations from session messages.

        Reads messages from Redis list `chise:observations:raw:<session_id>`,
        extracts observations using pattern-based mock extraction,
        deduplicates via MemoryDeduplicationEngine, and optionally stores
        in Redis sorted set.

        Args:
            session_id: The session ID to extract observations for.
            prompt_template: Optional prompt template (unused in Phase 1).
            dry_run: If True, log observations but do NOT write to storage.
                    Default: False (actual storage).

        Returns:
            List of Observation objects.
        """
        logger.info(
            "Extracting observations",
            extra={"session_id": session_id, "dry_run": dry_run},
        )

        # Read messages from Redis
        messages = []
        redis_client = self._get_redis_client()
        if redis_client is not None:
            try:
                raw_key = f"{OBSERVATIONS_RAW_PREFIX}:{session_id}"
                raw_messages = redis_client.lrange(raw_key, 0, -1)
                for msg_data in raw_messages:
                    if isinstance(msg_data, bytes):
                        msg_data = msg_data.decode("utf-8")
                    messages.append({"content": msg_data, "id": raw_key})
            except Exception as e:
                logger.warning(f"Failed to read raw messages: {e}")

        # Extract observations using mock LLM
        observation_dicts = self._llm_extract(messages)

        # Convert to Observation objects
        observations = []
        for obs_dict in observation_dicts:
            try:
                obs = Observation(
                    content=obs_dict["content"],
                    timestamp=obs_dict["timestamp"],
                    category=obs_dict["category"],
                    priority=obs_dict["priority"],
                    session_id=session_id,
                    confidence=obs_dict["confidence"],
                    source_message_ids=obs_dict["source_message_ids"],
                )
                observations.append(obs)
            except Exception as e:
                logger.warning(f"Failed to convert observation dict: {e}")

        # Run deduplication
        observations = self.run_dedup(observations)

        logger.info(
            f"Extracted {len(observations)} observations",
            extra={"session_id": session_id, "count": len(observations)},
        )

        # Check feature flag before any write operations
        if not self._is_feature_enabled():
            if not dry_run:
                logger.info(
                    "Observer feature flag not enabled, skipping storage",
                    extra={"session_id": session_id},
                )
            return observations

        # Store or log based on dry_run mode
        if dry_run:
            for obs in observations:
                logger.info(
                    "[DRY RUN] Would store observation",
                    extra={
                        "session_id": session_id,
                        "category": obs.category,
                        "priority": obs.priority,
                        "content_preview": obs.content[:50],
                    },
                )
        else:
            self._store_observations(observations)

        # Update state tracking
        self._update_extraction_state(session_id, len(observations), dry_run)

        return observations

    def run_dedup(self, new_observations: list[Observation]) -> list[Observation]:
        """
        Deduplicate observations using MemoryDeduplicationEngine.

        Args:
            new_observations: List of Observation objects to deduplicate.

        Returns:
            List of observations with duplicates removed.
        """
        if not new_observations:
            return []

        # Try to import and use the dedup engine
        dedup_engine = getattr(self, "_dedup_engine", None)
        if dedup_engine is None:
            try:
                from src.governance.memory.deduplication import (
                    MemoryDeduplicationEngine,
                )

                dedup_engine = MemoryDeduplicationEngine(
                    redis_client=self._get_redis_client()
                )
                self._dedup_engine = dedup_engine
                logger.info("Loaded MemoryDeduplicationEngine for dedup")
            except ImportError as e:
                logger.warning(
                    f"Cannot import MemoryDeduplicationEngine, skipping dedup: {e}"
                )
                return new_observations
            except Exception as e:
                logger.warning(
                    f"Failed to initialize dedup engine, skipping dedup: {e}"
                )
                return new_observations

        filtered = []
        for obs in new_observations:
            try:
                result = dedup_engine.deduplicate_content(obs.content)
                if result.get("is_duplicate"):
                    logger.debug(
                        f"Skipping duplicate observation: {obs.content[:30]}..."
                    )
                    continue
                filtered.append(obs)
            except Exception as e:
                logger.warning(f"Dedup check failed for observation: {e}")
                # On error, include the observation rather than lose it
                filtered.append(obs)

        logger.info(
            f"Dedup filtered {len(new_observations)} -> {len(filtered)} observations"
        )
        return filtered

    def _store_observations(self, observations: list[Observation]) -> None:
        """
        Store observations in Redis sorted set.

        Uses key `chise:observations:active:<session_id>` with timestamp
        as score and 7-day TTL.

        Args:
            observations: List of Observation objects to store.
        """
        if not observations or not observations[0]:
            return

        redis_client = self._get_redis_client()
        if redis_client is None:
            return

        try:
            session_id = observations[0].session_id
            active_key = f"{OBSERVATIONS_ACTIVE_PREFIX}:{session_id}"

            # Prepare sorted set members
            members = {}
            for obs in observations:
                # Use timestamp as score (Unix timestamp as float)
                try:
                    ts = datetime.fromisoformat(obs.timestamp.replace("Z", "+00:00"))
                    score = ts.timestamp()
                except Exception:
                    score = datetime.now(UTC).timestamp()

                # Store as JSON string
                member_data = {
                    "content": obs.content,
                    "category": obs.category,
                    "priority": obs.priority,
                    "confidence": obs.confidence,
                    "timestamp": obs.timestamp,
                    "source_message_ids": obs.source_message_ids,
                }
                members[json.dumps(member_data)] = score

            # Add to sorted set
            if members:
                redis_client.zadd(active_key, members)
                # Set TTL
                redis_client.expire(active_key, ACTIVE_OBSERVATIONS_TTL)

                logger.info(f"Stored {len(members)} observations in {active_key}")

        except Exception as e:
            logger.error(f"Failed to store observations: {e}")

    def _update_extraction_state(
        self, session_id: str, observation_count: int, dry_run: bool
    ) -> None:
        """
        Update observer state tracking after extraction.

        Args:
            session_id: The session ID.
            observation_count: Number of observations extracted.
            dry_run: Whether this was a dry run.
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return

        try:
            state_data = {
                "last_session_id": session_id,
                "last_extraction_count": str(observation_count),
                "last_extraction_time": datetime.now(UTC).isoformat(),
                "last_dry_run": str(dry_run),
            }
            redis_client.hset(OBSERVER_STATE_KEY, mapping=state_data)
            logger.debug(f"Updated observer extraction state for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to update observer extraction state: {e}")
