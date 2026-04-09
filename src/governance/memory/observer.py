"""
Observer Core Module for ChiseAI.

Monitors and accumulates conversation messages for analysis.

Feature Flag: chise:feature_flags:observations:observer_enabled
Default: Disabled (safe rollout)
"""

import json
import logging
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
