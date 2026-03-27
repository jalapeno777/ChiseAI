"""Belief storage abstraction with Redis fallback."""

from __future__ import annotations

import json
import logging
from typing import Any

from autonomous_cognition.beliefs.models import Belief

logger = logging.getLogger(__name__)


class BeliefStore:
    """Stores beliefs in-memory with optional Redis persistence."""

    INDEX_KEY = "bmad:chiseai:autocog:beliefs:index"
    BELIEF_KEY_PREFIX = "bmad:chiseai:autocog:belief"

    def __init__(self, redis_client: Any | None = None):
        self._redis_client = redis_client
        self._beliefs: dict[str, Belief] = {}

    def put(self, belief: Belief) -> None:
        """Save or update belief."""
        logger.info("[BELIEF_STORE] ENTERING put() with belief_id=%s", belief.belief_id)
        self._beliefs[belief.belief_id] = belief
        logger.info("[BELIEF_STORE] Saved to memory: _beliefs[%s]", belief.belief_id)
        payload = json.dumps(belief.to_dict())
        logger.info("[BELIEF_STORE] Serialized payload length: %d", len(payload))

        try:
            if self._redis_client is not None:
                logger.info("[BELIEF_STORE] Using external redis_client")
                hset_result = self._redis_client.hset(
                    self.INDEX_KEY, belief.belief_id, payload
                )
                logger.info("[BELIEF_STORE] hset result: %s", hset_result)
                set_result = self._redis_client.set(
                    f"{self.BELIEF_KEY_PREFIX}:{belief.belief_id}",
                    payload,
                )
                logger.info("[BELIEF_STORE] set result: %s", set_result)
                logger.info("[BELIEF_STORE] Returning early after Redis ops")
                return
            logger.info("[BELIEF_STORE] redis_client is None, using module-level tools")
            from tools.redis_state import redis_state_hset, redis_state_set

            logger.info(
                "[BELIEF_STORE] Calling redis_state_hset(INDEX_KEY=%s, belief_id=%s)",
                self.INDEX_KEY,
                belief.belief_id,
            )
            hset_result = redis_state_hset(self.INDEX_KEY, belief.belief_id, payload)
            logger.info(
                "[BELIEF_STORE] redis_state_hset returned: %s (type: %s)",
                hset_result,
                type(hset_result).__name__,
            )

            belief_key = f"{self.BELIEF_KEY_PREFIX}:{belief.belief_id}"
            logger.info("[BELIEF_STORE] Calling redis_state_set(key=%s)", belief_key)
            set_result = redis_state_set(belief_key, payload)
            logger.info(
                "[BELIEF_STORE] redis_state_set returned: %s (type: %s)",
                set_result,
                type(set_result).__name__,
            )
        except Exception as e:
            logger.error(
                "[BELIEF_STORE] EXCEPTION during Redis operations: %s", e, exc_info=True
            )
            logger.debug("[BELIEF_STORE] Belief Redis persistence skipped: %s", e)
        logger.info("[BELIEF_STORE] EXITING put() for belief_id=%s", belief.belief_id)

    def get(self, belief_id: str) -> Belief | None:
        """Get belief by id."""
        logger.info("[BELIEF_STORE] ENTERING get(%s)", belief_id)
        if belief_id in self._beliefs:
            logger.info("[BELIEF_STORE] Found %s in memory cache", belief_id)
            return self._beliefs[belief_id]
        logger.info("[BELIEF_STORE] %s NOT in memory cache, trying Redis", belief_id)
        try:
            if self._redis_client is not None:
                logger.info("[BELIEF_STORE] Using external redis_client")
                data = self._redis_client.get(f"{self.BELIEF_KEY_PREFIX}:{belief_id}")
                logger.info(
                    "[BELIEF_STORE] External client get returned: %s (type: %s)",
                    data,
                    type(data).__name__,
                )
                if data:
                    belief = Belief.from_dict(json.loads(data))
                    self._beliefs[belief_id] = belief
                    logger.info(
                        "[BELIEF_STORE] Successfully deserialized from external Redis"
                    )
                    return belief
            else:
                from tools.redis_state import redis_state_get

                belief_key = f"{self.BELIEF_KEY_PREFIX}:{belief_id}"
                logger.info(
                    "[BELIEF_STORE] Calling redis_state_get(key=%s)", belief_key
                )
                data = redis_state_get(belief_key)
                logger.info(
                    "[BELIEF_STORE] redis_state_get returned: %s (type: %s)",
                    data,
                    type(data).__name__,
                )
                if data:
                    logger.info(
                        "[BELIEF_STORE] Data is truthy, attempting json.loads..."
                    )
                    try:
                        parsed = json.loads(data)
                        logger.info(
                            "[BELIEF_STORE] json.loads succeeded, parsed type: %s",
                            type(parsed).__name__,
                        )
                    except Exception as json_err:
                        logger.error("[BELIEF_STORE] json.loads FAILED: %s", json_err)
                        raise
                    belief = Belief.from_dict(parsed)
                    self._beliefs[belief_id] = belief
                    logger.info("[BELIEF_STORE] Successfully deserialized from Redis")
                    return belief
        except Exception as e:
            logger.error("[BELIEF_STORE] EXCEPTION during get: %s", e, exc_info=True)
            logger.debug("[BELIEF_STORE] Belief get failed: %s", e)
        logger.info("[BELIEF_STORE] get(%s) returning None", belief_id)
        return None

    def list_active(self) -> list[Belief]:
        """List active beliefs."""
        beliefs = list(self._beliefs.values())
        if beliefs:
            return [b for b in beliefs if b.status == "active"]
        try:
            if self._redis_client is not None:
                values = self._redis_client.hgetall(self.INDEX_KEY) or {}
            else:
                from tools.redis_state import redis_state_hgetall

                values = redis_state_hgetall(self.INDEX_KEY) or {}
            for _, payload in values.items():
                belief = Belief.from_dict(json.loads(payload))
                self._beliefs[belief.belief_id] = belief
        except Exception as e:
            logger.debug("Belief listing fallback to memory only: %s", e)
        return [b for b in self._beliefs.values() if b.status == "active"]
