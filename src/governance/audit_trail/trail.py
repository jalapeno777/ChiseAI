"""
Core Audit Trail implementation with tamper-evident hash chain.

Provides the main AuditTrail class for logging autonomous decisions
with cryptographic integrity verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from src.governance.audit_trail.decision import (
    Decision,
    DecisionOutcome,
    DecisionType,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class RedisClient(Protocol):
    """Protocol for Redis client interface."""

    def hset(self, name: str, key: str, value: Any) -> int: ...

    def hget(self, name: str, key: str) -> bytes | None: ...

    def hgetall(self, name: str) -> dict[bytes, bytes]: ...

    def expire(self, name: str, time: int) -> bool: ...

    def lpush(self, name: str, value: Any) -> int: ...

    def lrange(self, name: str, start: int, stop: int) -> list[bytes]: ...

    def zadd(self, name: str, mapping: dict[str, float]) -> int: ...

    def zrange(
        self, name: str, start: int, stop: int, withscores: bool = False
    ) -> list[Any]: ...

    def zrangebyscore(
        self,
        name: str,
        min_score: float,
        max_score: float,
        withscores: bool = False,
    ) -> list[Any]: ...

    def delete(self, *names: str) -> int: ...


@dataclass
class HashChainState:
    """
    Represents the state of the hash chain for integrity verification.

    The hash chain creates a tamper-evident link between entries,
    making it impossible to modify past entries without detection.

    Attributes:
        last_hash: The hash of the most recent entry
        chain_length: Total number of entries in the chain
        genesis_hash: Hash of the first entry (chain root)
        last_timestamp: Timestamp of the most recent entry
    """

    last_hash: str = "sha256:genesis"
    chain_length: int = 0
    genesis_hash: str = "sha256:genesis"
    last_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert chain state to dictionary."""
        return {
            "last_hash": self.last_hash,
            "chain_length": self.chain_length,
            "genesis_hash": self.genesis_hash,
            "last_timestamp": self.last_timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HashChainState":
        """Create chain state from dictionary."""
        return cls(
            last_hash=data.get("last_hash", "sha256:genesis"),
            chain_length=data.get("chain_length", 0),
            genesis_hash=data.get("genesis_hash", "sha256:genesis"),
            last_timestamp=datetime.fromisoformat(data["last_timestamp"])
            if "last_timestamp" in data
            else datetime.now(UTC),
        )


@dataclass
class DecisionContext:
    """
    Context for a decision being logged.

    Provides structured context about the decision environment.

    Attributes:
        pr_id: Pull request ID if applicable
        story_id: Story/task ID if applicable
        branch: Branch name if applicable
        classification: Risk/safety classification
        additional_data: Any additional context data
    """

    pr_id: int | None = None
    story_id: str | None = None
    branch: str | None = None
    classification: str | None = None
    additional_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary."""
        result = {}
        if self.pr_id is not None:
            result["pr_id"] = self.pr_id
        if self.story_id is not None:
            result["story_id"] = self.story_id
        if self.branch is not None:
            result["branch"] = self.branch
        if self.classification is not None:
            result["classification"] = self.classification
        result.update(self.additional_data)
        return result


@dataclass
class AuditTrailEntry:
    """
    A single entry in the audit trail with hash chain linkage.

    This is the core data structure for tamper-evident logging.
    Each entry contains a hash of its contents and links to the
    previous entry, creating an immutable chain.

    Attributes:
        decision_id: Unique identifier (UUID)
        timestamp: UTC timestamp of the decision
        agent_id: ID of the agent that made the decision
        decision_type: Type of decision (enum)
        context: Decision context (PR, story, etc.)
        rationale: Explanation of the decision
        outcome: Result of the decision
        constitution_principles: Applicable constitution principles
        hash: SHA-256 hash of this entry
        prev_hash: Hash of the previous entry (chain link)
    """

    decision_id: str
    timestamp: datetime
    agent_id: str
    decision_type: DecisionType
    context: dict[str, Any]
    rationale: str
    outcome: DecisionOutcome
    constitution_principles: list[str]
    hash: str
    prev_hash: str

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary matching the export schema."""
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "decision_type": self.decision_type.value,
            "context": self.context,
            "rationale": self.rationale,
            "outcome": self.outcome.value,
            "constitution_principles": self.constitution_principles,
            "hash": self.hash,
            "prev_hash": self.prev_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditTrailEntry":
        """Create entry from dictionary."""
        return cls(
            decision_id=data["decision_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            agent_id=data["agent_id"],
            decision_type=DecisionType(data["decision_type"]),
            context=data.get("context", {}),
            rationale=data.get("rationale", ""),
            outcome=DecisionOutcome(data.get("outcome", "pending")),
            constitution_principles=data.get("constitution_principles", []),
            hash=data["hash"],
            prev_hash=data["prev_hash"],
        )

    def verify_hash(self) -> bool:
        """
        Verify that the entry's hash matches its contents.

        Returns:
            True if hash is valid, False otherwise
        """
        computed = AuditTrailEntry._compute_hash(
            prev_hash=self.prev_hash,
            decision_id=self.decision_id,
            timestamp=self.timestamp,
            agent_id=self.agent_id,
            decision_type=self.decision_type,
            context=self.context,
            rationale=self.rationale,
            outcome=self.outcome,
            constitution_principles=self.constitution_principles,
        )
        return computed == self.hash

    @staticmethod
    def _compute_hash(
        prev_hash: str,
        decision_id: str = "",
        timestamp: datetime | None = None,
        agent_id: str = "",
        decision_type: DecisionType | str = "",
        context: dict[str, Any] | None = None,
        rationale: str = "",
        outcome: DecisionOutcome | str = "",
        constitution_principles: list[str] | None = None,
    ) -> str:
        """
        Compute SHA-256 hash of entry contents.

        Args:
            All entry fields

        Returns:
            Hex-encoded SHA-256 hash with 'sha256:' prefix
        """
        # Normalize types
        if isinstance(decision_type, DecisionType):
            decision_type = decision_type.value
        if isinstance(outcome, DecisionOutcome):
            outcome = outcome.value
        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Build canonical representation
        content = json.dumps(
            {
                "prev_hash": prev_hash,
                "decision_id": decision_id,
                "timestamp": timestamp.isoformat() if timestamp else "",
                "agent_id": agent_id,
                "decision_type": decision_type,
                "context": context or {},
                "rationale": rationale,
                "outcome": outcome,
                "constitution_principles": constitution_principles or [],
            },
            sort_keys=True,
        )

        hash_hex = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return f"sha256:{hash_hex}"


class AuditTrail:
    """
    Main audit trail class for logging autonomous decisions.

    Provides tamper-evident logging with hash chain integrity.
    All decisions are logged with cryptographic hashes that link
    to previous entries, making tampering detectable.

    Example:
        >>> trail = AuditTrail(redis_client=my_redis)
        >>> entry = trail.log_decision(
        ...     agent_id="jarvis-001",
        ...     decision_type=DecisionType.PR_MERGE,
        ...     context={"pr_id": 230, "classification": "SAFE"},
        ...     rationale="All CI checks passed",
        ...     outcome=DecisionOutcome.SUCCESS,
        ...     constitution_principles=["P002", "P003"],
        ... )
    """

    # Redis key patterns
    ENTRIES_KEY = "governance:audit_trail:entries"
    CHAIN_STATE_KEY = "governance:audit_trail:chain_state"
    INDEX_AGENT_PREFIX = "governance:audit_trail:index:agent"
    INDEX_TYPE_PREFIX = "governance:audit_trail:index:type"
    INDEX_OUTCOME_PREFIX = "governance:audit_trail:index:outcome"
    INDEX_TIME_KEY = "governance:audit_trail:index:time"

    # Retention: 7 years (2557 days including leap years)
    RETENTION_SECONDS = 2557 * 24 * 60 * 60

    def __init__(
        self,
        redis_client: RedisClient | None = None,
        retention_days: int = 2557,
    ):
        """
        Initialize the audit trail.

        Args:
            redis_client: Redis client for persistence (optional)
            retention_days: Number of days to retain entries (default: 7 years)
        """
        self._redis = redis_client
        self._retention_days = retention_days
        self._chain_state = HashChainState()
        self._entries: list[AuditTrailEntry] = []
        self._entry_index: dict[str, AuditTrailEntry] = {}

        # Load existing chain state if Redis available
        if self._redis is not None:
            self._load_chain_state()

    def _load_chain_state(self) -> None:
        """Load chain state from Redis."""
        if self._redis is None:
            return
        try:
            data = self._redis.hgetall(self.CHAIN_STATE_KEY)
            if data:
                decoded = {k.decode(): v.decode() for k, v in data.items()}
                self._chain_state = HashChainState.from_dict(decoded)
                logger.info(
                    f"Loaded chain state: length={self._chain_state.chain_length}"
                )
        except Exception as e:
            logger.warning(f"Failed to load chain state: {e}")

    def _save_chain_state(self) -> None:
        """Save chain state to Redis."""
        if self._redis is None:
            return

        try:
            data = self._chain_state.to_dict()
            for key, value in data.items():
                self._redis.hset(self.CHAIN_STATE_KEY, key, str(value))
            self._redis.expire(self.CHAIN_STATE_KEY, self.RETENTION_SECONDS)
        except Exception as e:
            logger.error(f"Failed to save chain state: {e}")

    def log_decision(
        self,
        agent_id: str,
        decision_type: DecisionType,
        context: dict[str, Any] | DecisionContext,
        rationale: str,
        outcome: DecisionOutcome,
        constitution_principles: list[str] | None = None,
        decision_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> AuditTrailEntry:
        """
        Log an autonomous decision to the audit trail.

        This is the primary method for recording decisions. Each entry
        is linked to the previous entry via a cryptographic hash,
        creating a tamper-evident chain.

        Args:
            agent_id: ID of the agent making the decision
            decision_type: Type of decision (from DecisionType enum)
            context: Decision context (dict or DecisionContext)
            rationale: Explanation of why the decision was made
            outcome: Result of the decision
            constitution_principles: List of applicable constitution principles
            decision_id: Optional explicit decision ID (auto-generated if None)
            timestamp: Optional explicit timestamp (defaults to now)

        Returns:
            The created AuditTrailEntry
        """
        # Normalize context
        if isinstance(context, DecisionContext):
            context_dict = context.to_dict()
        else:
            context_dict = context

        # Generate decision ID if not provided
        if decision_id is None:
            decision_id = str(uuid.uuid4())

        # Use provided timestamp or current time
        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Normalize constitution principles
        if constitution_principles is None:
            constitution_principles = []

        # Get previous hash from chain state
        prev_hash = self._chain_state.last_hash

        # Compute hash for this entry
        entry_hash = AuditTrailEntry._compute_hash(
            prev_hash=prev_hash,
            decision_id=decision_id,
            timestamp=timestamp,
            agent_id=agent_id,
            decision_type=decision_type,
            context=context_dict,
            rationale=rationale,
            outcome=outcome,
            constitution_principles=constitution_principles,
        )

        # Create entry
        entry = AuditTrailEntry(
            decision_id=decision_id,
            timestamp=timestamp,
            agent_id=agent_id,
            decision_type=decision_type,
            context=context_dict,
            rationale=rationale,
            outcome=outcome,
            constitution_principles=constitution_principles,
            hash=entry_hash,
            prev_hash=prev_hash,
        )

        # Update chain state
        if self._chain_state.chain_length == 0:
            self._chain_state.genesis_hash = entry_hash
        self._chain_state.last_hash = entry_hash
        self._chain_state.chain_length += 1
        self._chain_state.last_timestamp = timestamp

        # Store entry
        self._entries.append(entry)
        self._entry_index[decision_id] = entry

        # Persist to Redis
        self._persist_entry(entry)

        logger.info(
            f"Logged decision: {decision_id} type={decision_type.value} "
            f"agent={agent_id} outcome={outcome.value}"
        )

        return entry

    def _persist_entry(self, entry: AuditTrailEntry) -> None:
        """Persist entry to Redis with indices."""
        if self._redis is None:
            return

        try:
            entry_json = json.dumps(entry.to_dict())

            # Store entry in main list
            self._redis.lpush(self.ENTRIES_KEY, entry_json)
            self._redis.expire(self.ENTRIES_KEY, self.RETENTION_SECONDS)

            # Index by agent
            agent_key = f"{self.INDEX_AGENT_PREFIX}:{entry.agent_id}"
            self._redis.zadd(
                agent_key, {entry.decision_id: entry.timestamp.timestamp()}
            )
            self._redis.expire(agent_key, self.RETENTION_SECONDS)

            # Index by decision type
            type_key = f"{self.INDEX_TYPE_PREFIX}:{entry.decision_type.value}"
            self._redis.zadd(type_key, {entry.decision_id: entry.timestamp.timestamp()})
            self._redis.expire(type_key, self.RETENTION_SECONDS)

            # Index by outcome
            outcome_key = f"{self.INDEX_OUTCOME_PREFIX}:{entry.outcome.value}"
            self._redis.zadd(
                outcome_key, {entry.decision_id: entry.timestamp.timestamp()}
            )
            self._redis.expire(outcome_key, self.RETENTION_SECONDS)

            # Index by time (for range queries)
            self._redis.zadd(
                self.INDEX_TIME_KEY, {entry.decision_id: entry.timestamp.timestamp()}
            )
            self._redis.expire(self.INDEX_TIME_KEY, self.RETENTION_SECONDS)

            # Save chain state
            self._save_chain_state()

        except Exception as e:
            logger.error(f"Failed to persist entry to Redis: {e}")

    def get_entry(self, decision_id: str) -> AuditTrailEntry | None:
        """
        Get a specific entry by decision ID.

        Args:
            decision_id: The decision ID to look up

        Returns:
            AuditTrailEntry if found, None otherwise
        """
        # Check in-memory first
        if decision_id in self._entry_index:
            return self._entry_index[decision_id]

        # Try Redis
        if self._redis is not None:
            try:
                # Scan through entries (inefficient but works for now)
                entries = self._redis.lrange(self.ENTRIES_KEY, 0, -1)
                for entry_bytes in entries:
                    entry_dict = json.loads(entry_bytes.decode())
                    if entry_dict["decision_id"] == decision_id:
                        entry = AuditTrailEntry.from_dict(entry_dict)
                        self._entry_index[decision_id] = entry
                        return entry
            except Exception as e:
                logger.error(f"Failed to get entry from Redis: {e}")

        return None

    def get_chain_state(self) -> HashChainState:
        """
        Get the current state of the hash chain.

        Returns:
            HashChainState with current chain information
        """
        return self._chain_state

    def verify_chain(self, start_hash: str | None = None) -> tuple[bool, str]:
        """
        Verify the integrity of the hash chain.

        This checks that each entry's hash correctly links to the
        previous entry, detecting any tampering.

        Args:
            start_hash: Optional hash to start verification from
                       (defaults to genesis)

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self._entries:
            return True, "Chain is empty"

        # Load entries from Redis if not in memory
        loaded_from_redis = False
        if (
            self._redis is not None
            and len(self._entries) < self._chain_state.chain_length
        ):
            try:
                entries = self._redis.lrange(self.ENTRIES_KEY, 0, -1)
                self._entries = []
                for entry_bytes in entries:
                    entry_dict = json.loads(entry_bytes.decode())
                    self._entries.append(AuditTrailEntry.from_dict(entry_dict))
                loaded_from_redis = True
            except Exception as e:
                return False, f"Failed to load entries: {e}"

        # Get entries in chronological order
        # In-memory entries are appended (oldest first)
        # Redis entries are lpushed (newest first), so need reversal
        if loaded_from_redis:
            entries = list(reversed(self._entries))
        else:
            entries = self._entries

        # Determine starting point
        expected_prev = start_hash or "sha256:genesis"

        for i, entry in enumerate(entries):
            # Skip if we're starting mid-chain and haven't reached start_hash
            if start_hash and entry.hash != start_hash and expected_prev == start_hash:
                continue

            # Verify hash linkage
            if entry.prev_hash != expected_prev:
                return False, (
                    f"Chain break at entry {i}: expected prev_hash={expected_prev}, "
                    f"got {entry.prev_hash}"
                )

            # Verify entry's own hash
            if not entry.verify_hash():
                return False, f"Invalid hash at entry {i}"

            expected_prev = entry.hash

        return True, "Chain verified successfully"

    def get_entries(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditTrailEntry]:
        """
        Get entries from the audit trail.

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            List of AuditTrailEntry objects (newest first)
        """
        if self._redis is not None:
            try:
                entries = self._redis.lrange(
                    self.ENTRIES_KEY, offset, offset + limit - 1
                )
                return [
                    AuditTrailEntry.from_dict(json.loads(e.decode())) for e in entries
                ]
            except Exception as e:
                logger.error(f"Failed to get entries from Redis: {e}")

        # Fall back to in-memory
        return self._entries[offset : offset + limit]

    def get_entry_count(self) -> int:
        """
        Get the total number of entries in the audit trail.

        Returns:
            Total entry count
        """
        return self._chain_state.chain_length

    def log_from_decision(self, decision: Decision) -> AuditTrailEntry:
        """
        Log a decision from a Decision object.

        Convenience method for logging Decision objects.

        Args:
            decision: Decision object to log

        Returns:
            The created AuditTrailEntry
        """
        return self.log_decision(
            agent_id=decision.agent_id,
            decision_type=decision.decision_type,
            context=decision.context,
            rationale=decision.rationale,
            outcome=decision.outcome,
            constitution_principles=[p.value for p in decision.constitution_principles],
            decision_id=decision.decision_id,
            timestamp=decision.timestamp,
        )
