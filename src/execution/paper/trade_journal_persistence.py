"""Redis persistence layer for trade journal.

Provides non-blocking persistence for TradeJournal and TradeJournalEntry
using Redis as the canonical store. All operations are designed to fail
gracefully without interrupting trading operations.

For PAPER-2025-BATCH3-001: Trade Journal Persistence
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.execution.paper.trade_journal import TradeJournal, TradeJournalEntry

logger = logging.getLogger(__name__)

# Redis key patterns
KEY_METADATA = "paper:journal:{session_id}:metadata"
KEY_ENTRIES = "paper:journal:{session_id}:entries"
KEY_ENTRY = "paper:journal:{session_id}:entry:{entry_id}"
KEY_SESSIONS = "paper:journal:sessions"

# Default timeouts (seconds)
DEFAULT_REDIS_TIMEOUT = 2.0


class TradeJournalRedisPersistence:
    """Redis persistence layer for trade journal.

    Provides save/load operations for TradeJournal with graceful degradation
    on Redis failures. All operations are non-blocking and return False/None
    on failure to preserve trading continuity.

    Attributes:
        _redis: Redis client instance
        _host: Redis host
        _port: Redis port
        _timeout: Redis operation timeout in seconds
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        host: str = "host.docker.internal",
        port: int = 6380,
        timeout: float = DEFAULT_REDIS_TIMEOUT,
    ) -> None:
        """Initialize the persistence layer.

        Args:
            redis_client: Optional pre-configured Redis client
            host: Redis host (default: host.docker.internal)
            port: Redis port (default: 6380)
            timeout: Redis operation timeout in seconds (default: 2.0)
        """
        self._host = host
        self._port = port
        self._timeout = timeout
        self._redis: Any | None = None

        if redis_client is not None:
            self._redis = redis_client
        else:
            self._redis = self._create_redis_client()

    def _create_redis_client(self) -> Any | None:
        """Create a Redis client with timeout configuration.

        Returns:
            Redis client or None if connection fails
        """
        try:
            import redis

            client = redis.Redis(
                host=self._host,
                port=self._port,
                decode_responses=True,
                socket_connect_timeout=self._timeout,
                socket_timeout=self._timeout,
                health_check_interval=30,
            )
            # Test connection
            client.ping()
            return client
        except Exception as e:
            logger.warning(
                f"Failed to connect to Redis at {self._host}:{self._port}: {e}"
            )
            return None

    def is_healthy(self) -> bool:
        """Check if Redis connection is healthy.

        Returns:
            True if Redis is connected and responsive, False otherwise
        """
        if self._redis is None:
            return False
        try:
            return self._redis.ping()
        except Exception as e:
            logger.debug(f"Redis health check failed: {e}")
            return False

    def _get_metadata_key(self, session_id: str) -> str:
        """Get Redis key for session metadata."""
        return KEY_METADATA.format(session_id=session_id)

    def _get_entries_key(self, session_id: str) -> str:
        """Get Redis key for session entries list."""
        return KEY_ENTRIES.format(session_id=session_id)

    def _get_entry_key(self, session_id: str, entry_id: str) -> str:
        """Get Redis key for individual entry."""
        return KEY_ENTRY.format(session_id=session_id, entry_id=entry_id)

    def save_journal(self, journal: TradeJournal) -> bool:
        """Save entire journal to Redis.

        Args:
            journal: The TradeJournal to save

        Returns:
            True if saved successfully, False on failure
        """
        if self._redis is None:
            logger.debug("Redis not available, skipping journal save")
            return False

        try:
            session_id = journal.session_id
            entries = journal.get_all_entries()

            # Save metadata
            metadata = {
                "session_id": session_id,
                "entry_count": len(entries),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._redis.hset(self._get_metadata_key(session_id), mapping=metadata)

            # Save all entries
            entry_ids = []
            for entry in entries:
                if self._save_entry_internal(session_id, entry):
                    entry_ids.append(entry.entry_id)

            # Update entries list
            if entry_ids:
                self._redis.delete(self._get_entries_key(session_id))
                self._redis.rpush(self._get_entries_key(session_id), *entry_ids)

            # Add to sessions set
            self._redis.sadd(KEY_SESSIONS, session_id)

            logger.debug(
                f"Saved journal for session {session_id} with {len(entries)} entries"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save journal: {e}")
            return False

    def load_journal(self, session_id: str) -> TradeJournal | None:
        """Load journal from Redis by session_id.

        Args:
            session_id: The session ID to load

        Returns:
            TradeJournal if loaded successfully, None on failure or not found
        """
        if self._redis is None:
            logger.debug("Redis not available, cannot load journal")
            return None

        try:
            # Check if journal exists
            if not self.journal_exists(session_id):
                logger.debug(f"Journal not found for session {session_id}")
                return None

            # Get entry IDs
            entry_ids = self._redis.lrange(self._get_entries_key(session_id), 0, -1)

            # Load all entries
            entries = []
            for entry_id in entry_ids:
                entry = self._load_entry_internal(session_id, entry_id)
                if entry:
                    entries.append(entry)

            # Create journal and populate entries
            journal = TradeJournal(session_id=session_id)
            for entry in entries:
                journal._entries[entry.entry_id] = entry

            logger.debug(
                f"Loaded journal for session {session_id} with {len(entries)} entries"
            )
            return journal

        except Exception as e:
            logger.error(f"Failed to load journal: {e}")
            return None

    def save_entry(self, session_id: str, entry: TradeJournalEntry) -> bool:
        """Save single entry to Redis.

        Args:
            session_id: The session ID for the entry
            entry: The TradeJournalEntry to save

        Returns:
            True if saved successfully, False on failure
        """
        if self._redis is None:
            logger.debug("Redis not available, skipping entry save")
            return False

        try:
            # Save the entry
            if not self._save_entry_internal(session_id, entry):
                return False

            # Add to entries list if not already present
            entry_key = self._get_entry_key(session_id, entry.entry_id)
            entries_key = self._get_entries_key(session_id)

            # Check if entry_id is already in the list
            existing_ids = self._redis.lrange(entries_key, 0, -1)
            if entry.entry_id not in existing_ids:
                self._redis.rpush(entries_key, entry.entry_id)

            # Add to sessions set
            self._redis.sadd(KEY_SESSIONS, session_id)

            # Update metadata
            self._update_metadata(session_id)

            logger.debug(f"Saved entry {entry.entry_id} for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save entry: {e}")
            return False

    def _save_entry_internal(self, session_id: str, entry: TradeJournalEntry) -> bool:
        """Internal method to save entry data to Redis hash.

        Args:
            session_id: The session ID for the entry
            entry: The TradeJournalEntry to save

        Returns:
            True if saved successfully, False on failure
        """
        try:
            entry_key = self._get_entry_key(session_id, entry.entry_id)
            entry_data = entry.to_dict()

            # Convert to JSON for storage
            entry_json = json.dumps(entry_data)

            # Store in hash with single field
            self._redis.hset(entry_key, "data", entry_json)

            return True
        except Exception as e:
            logger.error(f"Failed to save entry internal: {e}")
            return False

    def load_entry(self, session_id: str, entry_id: str) -> TradeJournalEntry | None:
        """Load single entry from Redis.

        Args:
            session_id: The session ID for the entry
            entry_id: The entry ID to load

        Returns:
            TradeJournalEntry if loaded successfully, None on failure or not found
        """
        if self._redis is None:
            logger.debug("Redis not available, cannot load entry")
            return None

        return self._load_entry_internal(session_id, entry_id)

    def _load_entry_internal(
        self, session_id: str, entry_id: str
    ) -> TradeJournalEntry | None:
        """Internal method to load entry data from Redis hash.

        Args:
            session_id: The session ID for the entry
            entry_id: The entry ID to load

        Returns:
            TradeJournalEntry if loaded successfully, None on failure or not found
        """
        try:
            entry_key = self._get_entry_key(session_id, entry_id)
            entry_json = self._redis.hget(entry_key, "data")

            if not entry_json:
                logger.debug(f"Entry {entry_id} not found in session {session_id}")
                return None

            entry_data = json.loads(entry_json)
            return TradeJournalEntry.from_dict(entry_data)

        except Exception as e:
            logger.error(f"Failed to load entry {entry_id}: {e}")
            return None

    def _update_metadata(self, session_id: str) -> None:
        """Update session metadata with current timestamp.

        Args:
            session_id: The session ID to update
        """
        try:
            metadata_key = self._get_metadata_key(session_id)
            metadata = {
                "session_id": session_id,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._redis.hset(metadata_key, mapping=metadata)
        except Exception as e:
            logger.warning(f"Failed to update metadata: {e}")

    def list_sessions(self) -> list[str]:
        """List all session IDs with journals.

        Returns:
            List of session IDs (empty list on failure)
        """
        if self._redis is None:
            logger.debug("Redis not available, cannot list sessions")
            return []

        try:
            sessions = self._redis.smembers(KEY_SESSIONS)
            return sorted(list(sessions))
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def delete_journal(self, session_id: str) -> bool:
        """Delete journal from Redis.

        Args:
            session_id: The session ID to delete

        Returns:
            True if deleted successfully, False on failure
        """
        if self._redis is None:
            logger.debug("Redis not available, cannot delete journal")
            return False

        try:
            # Get entry IDs to delete
            entry_ids = self._redis.lrange(self._get_entries_key(session_id), 0, -1)

            # Delete all entry hashes
            for entry_id in entry_ids:
                self._redis.delete(self._get_entry_key(session_id, entry_id))

            # Delete entries list
            self._redis.delete(self._get_entries_key(session_id))

            # Delete metadata
            self._redis.delete(self._get_metadata_key(session_id))

            # Remove from sessions set
            self._redis.srem(KEY_SESSIONS, session_id)

            logger.debug(f"Deleted journal for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete journal: {e}")
            return False

    def journal_exists(self, session_id: str) -> bool:
        """Check if journal exists in Redis.

        Args:
            session_id: The session ID to check

        Returns:
            True if journal exists, False otherwise
        """
        if self._redis is None:
            return False

        try:
            # Check if metadata key exists
            metadata_key = self._get_metadata_key(session_id)
            return self._redis.exists(metadata_key) > 0
        except Exception as e:
            logger.debug(f"Failed to check journal existence: {e}")
            return False

    def get_journal_metadata(self, session_id: str) -> dict[str, Any] | None:
        """Get journal metadata from Redis.

        Args:
            session_id: The session ID to get metadata for

        Returns:
            Metadata dictionary if found, None otherwise
        """
        if self._redis is None:
            return None

        try:
            metadata_key = self._get_metadata_key(session_id)
            metadata = self._redis.hgetall(metadata_key)
            return metadata if metadata else None
        except Exception as e:
            logger.error(f"Failed to get metadata: {e}")
            return None

    def get_entry_count(self, session_id: str) -> int:
        """Get the number of entries in a journal.

        Args:
            session_id: The session ID to count entries for

        Returns:
            Number of entries (0 on failure)
        """
        if self._redis is None:
            return 0

        try:
            entries_key = self._get_entries_key(session_id)
            return self._redis.llen(entries_key)
        except Exception as e:
            logger.error(f"Failed to get entry count: {e}")
            return 0
