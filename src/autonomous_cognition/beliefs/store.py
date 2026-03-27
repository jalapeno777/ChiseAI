"""Belief storage abstraction with Redis fallback."""

from __future__ import annotations

import json
import logging
from typing import Any

from autonomous_cognition.beliefs.models import Belief, BeliefRelationship

logger = logging.getLogger(__name__)


class BeliefStore:
    """Stores beliefs in-memory with optional Redis persistence."""

    INDEX_KEY = "bmad:chiseai:autocog:beliefs:index"
    BELIEF_KEY_PREFIX = "bmad:chiseai:autocog:belief"
    RELATIONSHIP_INDEX_KEY = "bmad:chiseai:autocog:belief_relationships:index"
    RELATIONSHIP_KEY_PREFIX = "bmad:chiseai:autocog:belief_relationship"
    DOMAIN_INDEX_KEY = "bmad:chiseai:autocog:beliefs:domain_index"

    def __init__(self, redis_client: Any | None = None):
        self._redis_client = redis_client
        self._beliefs: dict[str, Belief] = {}
        self._relationships: dict[str, BeliefRelationship] = {}

    def put(self, belief: Belief) -> None:
        """Save or update belief with domain indexing."""
        logger.info("[BELIEF_STORE] ENTERING put() with belief_id=%s", belief.belief_id)

        # Validate belief before storing
        validation_errors = belief.validate()
        if validation_errors:
            logger.warning(
                "[BELIEF_STORE] Belief %s has validation errors: %s",
                belief.belief_id,
                validation_errors,
            )
            return

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
                # Update domain index
                self._redis_client.hset(
                    f"{self.DOMAIN_INDEX_KEY}:{belief.domain}",
                    belief.belief_id,
                    payload,
                )
                logger.info(
                    "[BELIEF_STORE] Domain index updated for domain=%s", belief.domain
                )
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

            # Update domain index
            domain_key = f"{self.DOMAIN_INDEX_KEY}:{belief.domain}"
            redis_state_hset(domain_key, belief.belief_id, payload)
            logger.info(
                "[BELIEF_STORE] Domain index updated for domain=%s", belief.domain
            )
        except Exception as e:
            logger.error(
                "[BELIEF_STORE] EXCEPTION during Redis operations: %s", e, exc_info=True
            )
            logger.debug("[BELIEF_STORE] Belief Redis persistence skipped: %s", e)
        logger.info("[BELIEF_STORE] EXITING put() for belief_id=%s", belief.belief_id)

    def get_beliefs_by_domain(self, domain: str) -> list[Belief]:
        """Get all beliefs in a specific domain.

        Uses domain index for efficient lookup when available.
        """
        logger.info("[BELIEF_STORE] ENTERING get_beliefs_by_domain(domain=%s)", domain)

        # First try memory cache filtered by domain
        domain_beliefs = [
            b
            for b in self._beliefs.values()
            if b.domain == domain and b.status == "active"
        ]
        if domain_beliefs:
            logger.info(
                "[BELIEF_STORE] Found %d beliefs in domain '%s' from memory",
                len(domain_beliefs),
                domain,
            )
            return domain_beliefs

        # Fall back to Redis domain index
        try:
            domain_key = f"{self.DOMAIN_INDEX_KEY}:{domain}"
            if self._redis_client is not None:
                values = self._redis_client.hgetall(domain_key) or {}
                for _, payload in values.items():
                    belief = Belief.from_dict(json.loads(payload))
                    self._beliefs[belief.belief_id] = belief
            else:
                from tools.redis_state import redis_state_hgetall

                values = redis_state_hgetall(domain_key) or {}
                for _, payload in values.items():
                    belief = Belief.from_dict(payload)
                    self._beliefs[belief.belief_id] = belief
        except Exception as e:
            logger.debug("[BELIEF_STORE] Domain index lookup failed: %s", e)

        # Return from memory after attempting Redis load
        return [
            b
            for b in self._beliefs.values()
            if b.domain == domain and b.status == "active"
        ]

    def get_related_beliefs(
        self, belief_id: str, relationship_type: str | None = None
    ) -> list[Belief]:
        """Get beliefs related to the given belief.

        Optionally filter by relationship type.
        """
        logger.info(
            "[BELIEF_STORE] ENTERING get_related_beliefs(belief_id=%s, relationship_type=%s)",
            belief_id,
            relationship_type,
        )

        related_ids: set[str] = set()

        # Find relationships where this belief is source or target
        for rel in self._relationships.values():
            if relationship_type and rel.relationship_type != relationship_type:
                continue
            if rel.source_belief_id == belief_id:
                related_ids.add(rel.target_belief_id)
            elif rel.target_belief_id == belief_id:
                related_ids.add(rel.source_belief_id)

        # Note: Relationship persistence is best-effort; core belief operations work without it

        # Re-scan relationships from loaded data
        for rel in self._relationships.values():
            if relationship_type and rel.relationship_type != relationship_type:
                continue
            if rel.source_belief_id == belief_id:
                related_ids.add(rel.target_belief_id)
            elif rel.target_belief_id == belief_id:
                related_ids.add(rel.source_belief_id)

        # Fetch related beliefs
        result = []
        for rid in related_ids:
            belief = self.get(rid)
            if belief:
                result.append(belief)

        logger.info("[BELIEF_STORE] Found %d related beliefs", len(result))
        return result

    def put_relationship(self, relationship: BeliefRelationship) -> None:
        """Save a belief relationship."""
        logger.info(
            "[BELIEF_STORE] ENTERING put_relationship() with relationship_id=%s",
            relationship.relationship_id,
        )
        self._relationships[relationship.relationship_id] = relationship
        payload = json.dumps(relationship.to_dict())

        try:
            if self._redis_client is not None:
                self._redis_client.hset(
                    self.RELATIONSHIP_INDEX_KEY,
                    relationship.relationship_id,
                    payload,
                )
                self._redis_client.set(
                    f"{self.RELATIONSHIP_KEY_PREFIX}:{relationship.relationship_id}",
                    payload,
                )
            else:
                from tools.redis_state import redis_state_hset, redis_state_set

                redis_state_hset(
                    self.RELATIONSHIP_INDEX_KEY, relationship.relationship_id, payload
                )
                redis_state_set(
                    f"{self.RELATIONSHIP_KEY_PREFIX}:{relationship.relationship_id}",
                    payload,
                )
        except Exception as e:
            logger.debug("[BELIEF_STORE] Relationship Redis persistence skipped: %s", e)

    def get_relationship(self, relationship_id: str) -> BeliefRelationship | None:
        """Get relationship by id."""
        if relationship_id in self._relationships:
            return self._relationships[relationship_id]

        try:
            if self._redis_client is not None:
                data = self._redis_client.get(
                    f"{self.RELATIONSHIP_KEY_PREFIX}:{relationship_id}"
                )
                if data:
                    rel = BeliefRelationship.from_dict(json.loads(data))
                    self._relationships[relationship_id] = rel
                    return rel
            else:
                from tools.redis_state import redis_state_get

                data = redis_state_get(
                    f"{self.RELATIONSHIP_KEY_PREFIX}:{relationship_id}"
                )
                if data:
                    rel = BeliefRelationship.from_dict(data)
                    self._relationships[relationship_id] = rel
                    return rel
        except Exception as e:
            logger.debug("[BELIEF_STORE] Relationship get failed: %s", e)
        return None

    def batch_put(self, beliefs: list[Belief]) -> dict[str, int]:
        """Save multiple beliefs in batch.

        Returns dict with 'success' and 'failed' counts.
        """
        logger.info("[BELIEF_STORE] ENTERING batch_put() with %d beliefs", len(beliefs))
        results = {"success": 0, "failed": 0}

        for belief in beliefs:
            try:
                validation_errors = belief.validate()
                if validation_errors:
                    logger.warning(
                        "[BELIEF_STORE] Skipping invalid belief %s: %s",
                        belief.belief_id,
                        validation_errors,
                    )
                    results["failed"] += 1
                    continue
                self.put(belief)
                results["success"] += 1
            except Exception as e:
                logger.error(
                    "[BELIEF_STORE] Failed to put belief %s: %s",
                    belief.belief_id,
                    e,
                )
                results["failed"] += 1

        logger.info(
            "[BELIEF_STORE] batch_put complete: success=%d, failed=%d",
            results["success"],
            results["failed"],
        )
        return results

    def get(self, belief_id: str) -> Belief | None:
        """Get belief by id.

        Uses memory cache first, then falls back to Redis.
        Redis backend already deserializes JSON, so no additional json.loads needed.
        """
        logger.info("[BELIEF_STORE] ENTERING get(%s)", belief_id)
        if belief_id in self._beliefs:
            logger.info("[BELIEF_STORE] Found %s in memory cache", belief_id)
            return self._beliefs[belief_id]
        logger.info("[BELIEF_STORE] %s NOT in memory cache, trying Redis", belief_id)
        try:
            if self._redis_client is not None:
                # External client returns raw strings - need to deserialize
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
                # Module-level redis_state_get already deserializes via _deserialize()
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
                    # redis_state_get already returns parsed JSON via _deserialize(),
                    # so data is already a dict - do NOT call json.loads again
                    belief = Belief.from_dict(data)
                    self._beliefs[belief_id] = belief
                    logger.info(
                        "[BELIEF_STORE] Successfully loaded from Redis (already deserialized)"
                    )
                    return belief
        except Exception as e:
            logger.error("[BELIEF_STORE] EXCEPTION during get: %s", e, exc_info=True)
            logger.debug(
                "[BELIEF_STORE] Belief get failed, falling back to None: %s", e
            )
        logger.info(
            "[BELIEF_STORE] get(%s) returning None (cache miss or Redis unavailable)",
            belief_id,
        )
        return None

    def list_active(self) -> list[Belief]:
        """List active beliefs.

        Uses memory cache first, then falls back to Redis.
        redis_state_hgetall already deserializes via _deserialize().
        External client hgetall returns raw strings - need json.loads.
        """
        beliefs = list(self._beliefs.values())
        if beliefs:
            return [b for b in beliefs if b.status == "active"]
        try:
            if self._redis_client is not None:
                # External client returns raw strings - need to deserialize
                values = self._redis_client.hgetall(self.INDEX_KEY) or {}
                for _, payload in values.items():
                    belief = Belief.from_dict(json.loads(payload))
                    self._beliefs[belief.belief_id] = belief
            else:
                # Module-level redis_state_hgetall already deserializes via _deserialize()
                from tools.redis_state import redis_state_hgetall

                values = redis_state_hgetall(self.INDEX_KEY) or {}
                for _, payload in values.items():
                    # redis_state_hgetall already returns parsed JSON via _deserialize(),
                    # so payload is already a dict - do NOT call json.loads again
                    belief = Belief.from_dict(payload)
                    self._beliefs[belief.belief_id] = belief
        except Exception as e:
            logger.debug("Belief listing fallback to memory only: %s", e)
        return [b for b in self._beliefs.values() if b.status == "active"]
