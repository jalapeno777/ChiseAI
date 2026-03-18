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
        self._beliefs[belief.belief_id] = belief
        payload = json.dumps(belief.to_dict())

        try:
            if self._redis_client is not None:
                self._redis_client.hset(self.INDEX_KEY, belief.belief_id, payload)
                self._redis_client.set(
                    f"{self.BELIEF_KEY_PREFIX}:{belief.belief_id}",
                    payload,
                )
                return
            from tools.redis_state import redis_state_hset, redis_state_set

            redis_state_hset(self.INDEX_KEY, belief.belief_id, payload)
            redis_state_set(f"{self.BELIEF_KEY_PREFIX}:{belief.belief_id}", payload)
        except Exception as e:
            logger.debug("Belief Redis persistence skipped: %s", e)

    def get(self, belief_id: str) -> Belief | None:
        """Get belief by id."""
        if belief_id in self._beliefs:
            return self._beliefs[belief_id]
        try:
            if self._redis_client is not None:
                data = self._redis_client.get(f"{self.BELIEF_KEY_PREFIX}:{belief_id}")
                if data:
                    belief = Belief.from_dict(json.loads(data))
                    self._beliefs[belief_id] = belief
                    return belief
            from tools.redis_state import redis_state_get

            data = redis_state_get(f"{self.BELIEF_KEY_PREFIX}:{belief_id}")
            if data:
                belief = Belief.from_dict(json.loads(data))
                self._beliefs[belief_id] = belief
                return belief
        except Exception as e:
            logger.debug("Belief get failed: %s", e)
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
