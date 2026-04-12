"""
Reflector Agent Core Module for ChiseAI.

Consolidates observations into long-term memory using LLM-based compression.

Feature Flag: chise:feature_flags:observations:reflector_enabled
Default: Disabled (safe rollout)
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Feature flag key in Redis
FEATURE_FLAG_KEY = "chise:feature_flags:observations:reflector_enabled"

# Redis key prefix for active observations
OBSERVATIONS_ACTIVE_PREFIX = "chise:observations:active"

# Redis key for reflector consolidation state
REFLECTOR_STATE_KEY = "chise:observations:reflector:state"

# Consolidation threshold in tokens (from research doc)
DEFAULT_CONSOLIDATION_THRESHOLD = 40000

# Minimum observations before consolidation (part of trigger guard)
MIN_OBSERVATIONS_FOR_CONSOLIDATION = 10

# Minimum time between consolidations (24 hours in seconds)
MIN_CONSOLIDATION_INTERVAL = 24 * 3600

# Convergence guard threshold (>80% overlap triggers skip)
CONVERGENCE_OVERLAP_THRESHOLD = 0.80

# Qdrant collection name
QDRANT_COLLECTION = "ChiseAI"

# Embedding dimension for ChiseAI (384 for current embedding model)
EMBEDDING_DIM = 384


@dataclass
class SupersededObservation:
    """
    Represents an observation that has been superseded by consolidation.

    Attributes:
        content: The text content of the observation.
        created_at: ISO8601 timestamp when the observation was originally created.
        updated_at: ISO8601 timestamp when the observation was last updated.
        superseded_at: ISO8601 timestamp when this observation was superseded, or None if still active.
        session_id: The session identifier this observation belongs to.
        priority: One of high/medium/low.
        category: One of decision/pattern/fact/preference/event.
        confidence: Confidence score between 0.0 and 1.0.
        source_observation_ids: List of observation IDs that contributed to this consolidated memory.
    """

    content: str
    created_at: str
    updated_at: str
    superseded_at: str | None
    session_id: str
    priority: str
    category: str
    confidence: float
    source_observation_ids: list[str]


class Reflector:
    """Reflector for consolidating observations into long-term memory.

    Attributes:
        redis_client: Optional pre-configured Redis client.
        qdrant_client: Optional pre-configured Qdrant client.
        llm_client: Optional injectable LLM client for consolidation.
        threshold: Consolidation batch size in tokens (default 40000).
            Note: This is NOT the trigger threshold. should_trigger() uses
            Observer's threshold (30000) as the trigger condition.
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
        llm_client: Any | None = None,
        threshold: int = DEFAULT_CONSOLIDATION_THRESHOLD,
    ) -> None:
        """Initialize the Reflector.

        Args:
            redis_client: Optional pre-configured Redis client.
            qdrant_client: Optional pre-configured Qdrant client.
            llm_client: Optional injectable LLM client for consolidation.
            threshold: Consolidation batch size in tokens.
                The trigger condition uses Observer's threshold (30000);
                this value controls how much the Reflector processes per run.
        """
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client
        self._llm_client = llm_client
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
                db=0,
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
        """Check if reflector feature flag is enabled.

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

    def _get_active_observations(self, session_id: str) -> list[dict]:
        """Get active observations for a session from Redis sorted set.

        Args:
            session_id: The session ID to get observations for.

        Returns:
            List of observation dicts.
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return []

        try:
            active_key = f"{OBSERVATIONS_ACTIVE_PREFIX}:{session_id}"
            raw_observations = redis_client.zrange(active_key, 0, -1)

            observations = []
            for obs_json in raw_observations:
                try:
                    if isinstance(obs_json, bytes):
                        obs_json = obs_json.decode("utf-8")
                    obs_data = json.loads(obs_json)
                    observations.append(obs_data)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse observation: {e}")
                    continue

            return observations
        except Exception as e:
            logger.error(f"Failed to get active observations: {e}")
            return []

    def _get_observation_count(self, session_id: str) -> int:
        """Get count of active observations for a session.

        Args:
            session_id: The session ID to count observations for.

        Returns:
            Number of active observations.
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return 0

        try:
            active_key = f"{OBSERVATIONS_ACTIVE_PREFIX}:{session_id}"
            return redis_client.zcard(active_key)
        except Exception as e:
            logger.warning(f"Failed to get observation count: {e}")
            return 0

    def _get_token_count_from_observations(self, observations: list[dict]) -> int:
        """Estimate total token count from observation contents.

        Uses simple word-based estimation (words * 1.3) for Phase 2.

        Args:
            observations: List of observation dicts with 'content' key.

        Returns:
            Estimated token count.
        """
        total_tokens = 0
        for obs in observations:
            content = obs.get("content", "")
            if content:
                word_count = len(content.split())
                token_count = int(word_count * 1.3)
                total_tokens += token_count
        return total_tokens

    def _get_last_consolidation_time(self, session_id: str) -> datetime | None:
        """Get the last consolidation time for a session.

        Args:
            session_id: The session ID to check.

        Returns:
            datetime of last consolidation, or None if never consolidated.
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return None

        try:
            state_key = f"{REFLECTOR_STATE_KEY}:{session_id}"
            last_time = redis_client.hget(state_key, "last_consolidation_time")
            if last_time:
                return datetime.fromisoformat(last_time.replace("Z", "+00:00"))
            return None
        except Exception as e:
            logger.warning(f"Failed to get last consolidation time: {e}")
            return None

    def _check_convergence(self, new_content: str, session_id: str) -> bool:
        """Check if new content converges too much with prior consolidated memory.

        Uses word overlap ratio: if >80% of words in prior content appear in
        new content, skip the write and log a warning.

        Args:
            new_content: The newly consolidated content.
            session_id: The session ID to check against.

        Returns:
            True if convergence detected (should skip write), False otherwise.
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return False

        try:
            # Get prior consolidated memory from Redis state
            state_key = f"{REFLECTOR_STATE_KEY}:{session_id}"
            prior_content = redis_client.hget(state_key, "last_consolidated_content")

            if not prior_content:
                return False

            # Calculate word overlap ratio
            prior_words = set(prior_content.lower().split())
            new_words = set(new_content.lower().split())

            if not prior_words:
                return False

            overlap = prior_words & new_words
            overlap_ratio = len(overlap) / len(prior_words)

            if overlap_ratio > CONVERGENCE_OVERLAP_THRESHOLD:
                logger.warning(
                    f"Convergence detected for session {session_id}: "
                    f"{overlap_ratio:.2%} word overlap exceeds "
                    f"{CONVERGENCE_OVERLAP_THRESHOLD:.0%} threshold. "
                    f"Skipping consolidation write."
                )
                return True

            return False
        except Exception as e:
            logger.warning(f"Failed to check convergence: {e}")
            return False

    def _supersede_prior_observations(self, session_id: str) -> None:
        """Mark prior observations as superseded.

        Updates the Redis sorted set to mark observations with superseded_at timestamp.

        Args:
            session_id: The session ID to supersede observations for.
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return

        try:
            active_key = f"{OBSERVATIONS_ACTIVE_PREFIX}:{session_id}"
            supersede_time = datetime.now(UTC).isoformat()

            # Get all observations
            raw_observations = redis_client.zrange(active_key, 0, -1)

            for obs_json in raw_observations:
                try:
                    if isinstance(obs_json, bytes):
                        obs_json = obs_json.decode("utf-8")
                    obs_data = json.loads(obs_json)
                    obs_data["superseded_at"] = supersede_time
                    # Re-add with updated data (same score keeps order)
                    redis_client.zadd(
                        active_key,
                        {
                            json.dumps(obs_data): redis_client.zscore(
                                active_key, obs_json
                            )
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to supersede observation: {e}")
                    continue

            logger.info(
                f"Superseded prior observations for session {session_id} at {supersede_time}"
            )
        except Exception as e:
            logger.error(f"Failed to supersede prior observations: {e}")

    def _generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for text.

        Phase 2: Uses configurable embedding client.
        Falls back to simple hash-based vector for testing.

        Args:
            text: The text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        # Try to use configured embedding client
        if hasattr(self, "_embedding_client") and self._embedding_client is not None:
            try:
                return self._embedding_client.embed(text)
            except Exception as e:
                logger.warning(f"Embedding client failed: {e}")

        # Fallback: simple deterministic hash-based embedding for testing
        # This produces a consistent but not semantically meaningful vector
        import hashlib

        vector = []
        text_hash = hashlib.sha256(text.encode()).digest()
        for i in range(EMBEDDING_DIM):
            byte_idx = i % len(text_hash)
            value = (text_hash[byte_idx] / 255.0) * 2 - 1  # Normalize to [-1, 1]
            vector.append(value)

        # Normalize to unit vector
        import math

        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude > 0:
            vector = [v / magnitude for v in vector]

        return vector

    def _llm_consolidate(self, observations: list[dict]) -> dict:
        """Consolidate observations using LLM.

        This is the injectable LLM interface for Phase 2.
        Takes a list of observation dicts and returns a dict with
        consolidated memory content.

        Args:
            observations: List of observation dicts with content, category,
                        priority, confidence, timestamp.

        Returns:
            Dict with keys:
                - content: Consolidated memory text
                - raw_tokens: Token count of input observations
                - consolidated_tokens: Token count of output content
                - priority: Priority from highest-priority source observation
                - category: Primary category from source observations
        """
        # Use injectable LLM client if available
        if self._llm_client is not None:
            try:
                result = self._llm_client.consolidate(observations)
                if result and "content" in result:
                    return result
            except Exception as e:
                logger.warning(f"LLM client consolidation failed: {e}")

        # Fallback: Simple concatenation with deduplication for testing
        # This is NOT real LLM consolidation - it's a placeholder
        logger.info(
            f"Using mock LLM consolidation for {len(observations)} observations"
        )

        # Sort by priority (high > medium > low) and confidence
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_obs = sorted(
            observations,
            key=lambda x: (
                priority_order.get(x.get("priority", "low"), 2),
                -x.get("confidence", 0.0),
            ),
        )

        # Build consolidated content
        categories = {}
        for obs in sorted_obs:
            cat = obs.get("category", "fact")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(obs.get("content", ""))

        content_parts = []
        for cat, items in categories.items():
            content_parts.append(f"[{cat.upper()}]:")
            content_parts.extend(f"  - {item}" for item in items)

        consolidated_content = "\n".join(content_parts)

        # Calculate token counts
        raw_tokens = self._get_token_count_from_observations(observations)
        consolidated_tokens = int(len(consolidated_content.split()) * 1.3)

        # Get highest priority and primary category
        highest_priority = (
            sorted_obs[0].get("priority", "medium") if sorted_obs else "medium"
        )
        primary_category = (
            sorted_obs[0].get("category", "fact") if sorted_obs else "fact"
        )

        return {
            "content": consolidated_content,
            "raw_tokens": raw_tokens,
            "consolidated_tokens": consolidated_tokens,
            "priority": highest_priority,
            "category": primary_category,
        }

    def should_trigger(self, session_id: str) -> bool:
        """Check if consolidation should be triggered for a session.

        TRIGGER GUARD (Aria mandatory): returns True only when:
        1. Observer threshold met (token_count >= 30000) AND
        2. (active_observations_count >= 10 OR 24h since last consolidation)

        Design: Uses Observer's threshold (30000) as the trigger condition,
        not Reflector's consolidation batch size (self.threshold = 40000).
        The Reflector's 40000 threshold controls the batch size for LLM
        consolidation, while the 30000 Observer threshold determines when
        consolidation is eligible to run.

        Args:
            session_id: The session ID to check.

        Returns:
            True if consolidation should be triggered, False otherwise.
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            logger.warning("Redis not available for trigger check")
            return False

        # Get token count from observations
        observations = self._get_active_observations(session_id)
        token_count = self._get_token_count_from_observations(observations)

        # Check Observer threshold (30000) - minimum condition.
        # Design: The Reflector's self.threshold (40000) is the consolidation
        # batch size, NOT the trigger threshold. The trigger uses Observer's
        # threshold (30000) so that consolidation starts before the batch fills.
        OBSERVER_THRESHOLD = 30000
        if token_count < OBSERVER_THRESHOLD:
            logger.debug(
                f"Token count {token_count} below Observer threshold {OBSERVER_THRESHOLD}"
            )
            return False

        # Get observation count
        obs_count = len(observations)
        if obs_count < MIN_OBSERVATIONS_FOR_CONSOLIDATION:
            # Check time since last consolidation
            last_consolidation = self._get_last_consolidation_time(session_id)
            if last_consolidation is None:
                # Never consolidated, use session start as proxy
                # For now, don't trigger if no observations yet
                logger.debug(
                    f"Observation count {obs_count} below minimum {MIN_OBSERVATIONS_FOR_CONSOLIDATION} "
                    "and no prior consolidation"
                )
                return False

            time_since = datetime.now(UTC) - last_consolidation
            if time_since.total_seconds() < MIN_CONSOLIDATION_INTERVAL:
                logger.debug(
                    f"Time since last consolidation {time_since.total_seconds():.0f}s "
                    f"below minimum {MIN_CONSOLIDATION_INTERVAL}s"
                )
                return False

        logger.info(
            f"Consolidation triggered for session {session_id}: "
            f"token_count={token_count}, obs_count={obs_count}"
        )
        return True

    def consolidate_observations(
        self,
        session_id: str,
        dry_run: bool = False,
    ) -> dict | None:
        """Consolidate observations for a session into long-term memory.

        Main entry point for the Reflector. Reads active observations from Redis,
        consolidates them via LLM, checks convergence, and writes to Qdrant.

        Args:
            session_id: The session ID to consolidate observations for.
            dry_run: If True, perform all logic but do NOT write to storage.
                    Default: False (actual storage).

        Returns:
            Dict with consolidation results, or None if consolidation not triggered.
        """
        logger.info(
            "Consolidating observations",
            extra={"session_id": session_id, "dry_run": dry_run},
        )

        # Check feature flag FIRST
        if not self._is_feature_enabled():
            if not dry_run:
                logger.info(
                    "Reflector feature not enabled, skipping consolidation",
                    extra={"session_id": session_id},
                )
            return None

        # Check trigger guard
        if not self.should_trigger(session_id):
            logger.info(
                "Trigger guard not met, skipping consolidation",
                extra={"session_id": session_id},
            )
            return None

        # Get active observations
        observations = self._get_active_observations(session_id)
        if not observations:
            logger.info(
                "No observations to consolidate", extra={"session_id": session_id}
            )
            return None

        # Consolidate via LLM
        consolidation_result = self._llm_consolidate(observations)
        new_content = consolidation_result.get("content", "")

        if not new_content:
            logger.warning("LLM consolidation returned empty content")
            return None

        # Check convergence guard
        if self._check_convergence(new_content, session_id):
            logger.info(
                "Convergence guard triggered, skipping write",
                extra={"session_id": session_id},
            )
            return {
                "status": "skipped",
                "reason": "convergence",
                "session_id": session_id,
            }

        # Get source observation IDs and metadata
        source_ids = []
        earliest_timestamp = None
        highest_priority = "medium"
        for obs in observations:
            if "source_message_ids" in obs:
                source_ids.extend(obs["source_message_ids"])
            ts = obs.get("timestamp")
            if ts and (earliest_timestamp is None or ts < earliest_timestamp):
                earliest_timestamp = ts
            priority = obs.get("priority", "medium")
            if priority == "high" or (
                priority == "medium" and highest_priority == "low"
            ):
                highest_priority = priority

        # Calculate compression ratio
        raw_tokens = consolidation_result.get("raw_tokens", 1)
        consolidated_tokens = consolidation_result.get("consolidated_tokens", 1)
        compression_ratio = raw_tokens / max(consolidated_tokens, 1)

        result = {
            "status": "success",
            "session_id": session_id,
            "content": new_content,
            "raw_tokens": raw_tokens,
            "consolidated_tokens": consolidated_tokens,
            "compression_ratio": compression_ratio,
            "observation_count": len(observations),
            "source_observation_ids": source_ids,
            "priority": highest_priority,
            "category": consolidation_result.get("category", "fact"),
            "earliest_timestamp": earliest_timestamp,
        }

        if dry_run:
            logger.info(
                "[DRY RUN] Would store consolidated memory",
                extra={
                    "session_id": session_id,
                    "content_preview": new_content[:100],
                    "compression_ratio": f"{compression_ratio:.2f}",
                },
            )
            return result

        # Supersede prior observations
        self._supersede_prior_observations(session_id)

        # Write to Qdrant
        qdrant_success = self._write_to_qdrant(result)

        if qdrant_success:
            # Update consolidation state in Redis
            self._update_consolidation_state(session_id, new_content)
            logger.info(
                f"Consolidated {len(observations)} observations into memory",
                extra={
                    "session_id": session_id,
                    "compression_ratio": f"{compression_ratio:.2f}",
                },
            )
        else:
            result["status"] = "qdrant_failed"
            logger.error(
                "Failed to write consolidated memory to Qdrant",
                extra={"session_id": session_id},
            )

        return result

    def _compute_staleness_score(self, created_at: str, updated_at: str) -> float:
        """Precompute staleness score at WRITE TIME.

        This is called when writing to Qdrant, NOT at query time.
        Precomputing at write time ensures O(1) L3 queries.

        Uses 30-day (720h) decay window for promoted memories.

        Args:
            created_at: ISO8601 creation timestamp.
            updated_at: ISO8601 last update timestamp.

        Returns:
            Staleness score 0.0 (stale) to 1.0 (fresh).
        """
        now = datetime.now(UTC)
        updated = datetime.fromisoformat(updated_at)
        hours_since = (now - updated).total_seconds() / 3600

        # 30-day (720h) decay window for promoted memories
        decay_window = 720.0
        return max(0.0, 1.0 - hours_since / decay_window)

    def _write_to_qdrant(self, consolidation_result: dict) -> bool:
        """Write consolidated memory to Qdrant.

        Args:
            consolidation_result: Dict with consolidation results.

        Returns:
            True if write succeeded, False otherwise.
        """
        qdrant_client = self._get_qdrant_client()
        if qdrant_client is None:
            logger.error("Qdrant client not available")
            return False

        try:
            import uuid as uuid_lib

            memory_id = str(uuid_lib.uuid4())
            content = consolidation_result.get("content", "")
            earliest_timestamp = consolidation_result.get("earliest_timestamp")
            created_at = earliest_timestamp or datetime.now(UTC).isoformat()
            updated_at = datetime.now(UTC).isoformat()

            # Generate embedding
            vector = self._generate_embedding(content)

            # Prepare payload
            priority = consolidation_result.get("priority", "medium")
            priority_emoji = {
                "high": "🔥",
                "medium": "⚡",
                "low": "💤",
            }.get(priority, "⚡")

            payload = {
                "story_id": consolidation_result.get("session_id"),
                "memory_type": "consolidated",
                "domain": {
                    "wing": "chiseai",
                    "room": "observations",
                    "hall": "consolidated",
                    "tunnels": [],
                },
                "content": content,
                "created_at": created_at,
                "updated_at": updated_at,
                "superseded_at": None,
                "observer_priority": priority_emoji,
                "source_observation_ids": consolidation_result.get(
                    "source_observation_ids", []
                ),
                "compression_ratio": consolidation_result.get("compression_ratio", 1.0),
            }

            # Precompute staleness_score at WRITE TIME (not query time)
            # This ensures O(1) L3 queries — no dynamic computation at query time
            payload["staleness_score"] = self._compute_staleness_score(
                created_at=created_at,
                updated_at=updated_at,
            )

            # Write to Qdrant
            qdrant_client.upsert(
                collection_name=QDRANT_COLLECTION,
                points=[
                    {
                        "id": memory_id,
                        "vector": vector,
                        "payload": payload,
                    }
                ],
            )

            logger.info(
                "Wrote consolidated memory to Qdrant",
                extra={
                    "memory_id": memory_id,
                    "collection": QDRANT_COLLECTION,
                    "session_id": consolidation_result.get("session_id"),
                },
            )
            return True

        except Exception as e:
            logger.error(f"Failed to write to Qdrant: {e}")
            return False

    def _update_consolidation_state(self, session_id: str, content: str) -> None:
        """Update consolidation state in Redis.

        Args:
            session_id: The session ID.
            content: The consolidated content (for convergence checking).
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return

        try:
            state_key = f"{REFLECTOR_STATE_KEY}:{session_id}"
            state_data = {
                "last_consolidation_time": datetime.now(UTC).isoformat(),
                "last_consolidated_content": content,
            }
            redis_client.hset(state_key, mapping=state_data)
            logger.debug(f"Updated consolidation state for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to update consolidation state: {e}")
