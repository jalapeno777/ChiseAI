"""Dead Letter Queue for failed retry operations.

Manages operations that have exceeded their retry limits or hit
budget constraints, allowing for manual review and reprocessing.

For ST-NS-039: Retry Coordinator with Budget Management
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.orm import Session

from src.autonomous_control_plane.models.retry_policy import (
    DeadLetterQueueItem,
    RetryStatus,
)

logger = logging.getLogger(__name__)


class DeadLetterQueue:
    """Queue for failed retry operations.

    Stores operations that have exceeded their retry limits or
    encountered budget constraints. Supports manual review and
    reprocessing.

    Uses PostgreSQL for persistent storage.

    Example:
        dlq = DeadLetterQueue(db_engine)

        # Add failed operation
        dlq.enqueue(
            service_name="api_client",
            operation="fetch_data",
            payload={"url": "..."},
            error="Connection timeout",
            retry_count=3
        )

        # List pending items
        items = dlq.list_pending(limit=10)

        # Retry an item
        item = dlq.get(item_id)
        dlq.mark_retried(item_id)
    """

    def __init__(
        self,
        db_engine: Engine | None = None,
        table_name: str = "dead_letter_queue",
    ):
        """Initialize dead letter queue.

        Args:
            db_engine: SQLAlchemy database engine
            table_name: Database table name
        """
        self._engine = db_engine
        self._table_name = table_name
        self._items: dict[str, DeadLetterQueueItem] = {}

    def _ensure_table(self) -> None:
        """Ensure the DLQ table exists in the database."""
        if not self._engine:
            return

        try:
            from sqlalchemy import (
                Column,
                DateTime,
                Integer,
                MetaData,
                String,
                Table,
                create_engine,
                inspect,
                text,
            )

            metadata = MetaData()

            Table(
                self._table_name,
                metadata,
                Column("id", String(36), primary_key=True),
                Column("service_name", String(255), nullable=False, index=True),
                Column("operation", String(255), nullable=False),
                Column("payload", String(4000)),
                Column("error_message", String(1000)),
                Column("retry_count", Integer, default=0),
                Column("created_at", DateTime, default=datetime.utcnow),
                Column("status", String(50), default="DLQ"),
                Column("last_error", String(1000)),
                Column("updated_at", DateTime, onupdate=datetime.utcnow),
            )

            # Create table if it doesn't exist
            if not inspect(self._engine).has_table(self._table_name):
                metadata.create_all(self._engine)
                logger.info(f"Created dead letter queue table: {self._table_name}")

        except Exception as e:
            logger.error(f"Failed to ensure DLQ table: {e}")
            raise

    def enqueue(
        self,
        service_name: str,
        operation: str,
        payload: dict[str, Any],
        error_message: str,
        retry_count: int,
    ) -> DeadLetterQueueItem:
        """Add an operation to the dead letter queue.

        Args:
            service_name: Service that failed
            operation: Operation name
            payload: Operation payload
            error_message: Error that caused failure
            retry_count: Number of retries attempted

        Returns:
            Created DLQ item
        """
        item = DeadLetterQueueItem(
            id=str(uuid.uuid4()),
            service_name=service_name,
            operation=operation,
            payload=payload,
            error_message=error_message,
            retry_count=retry_count,
        )

        if self._engine:
            self._insert_to_db(item)
        else:
            self._items[item.id] = item

        logger.warning(
            f"Added to DLQ: {service_name}/{operation} "
            f"(id={item.id}, retry_count={retry_count})"
        )

        return item

    def _insert_to_db(self, item: DeadLetterQueueItem) -> None:
        """Insert item into database."""
        self._ensure_table()

        try:
            from sqlalchemy import text

            with self._engine.connect() as conn:
                conn.execute(
                    text(f"""
                        INSERT INTO {self._table_name}
                        (id, service_name, operation, payload, error_message,
                         retry_count, created_at, status, last_error)
                        VALUES
                        (:id, :service_name, :operation, :payload, :error_message,
                         :retry_count, :created_at, :status, :last_error)
                    """),
                    {
                        "id": item.id,
                        "service_name": item.service_name,
                        "operation": item.operation,
                        "payload": json.dumps(item.payload),
                        "error_message": item.error_message,
                        "retry_count": item.retry_count,
                        "created_at": item.created_at,
                        "status": item.status.name,
                        "last_error": item.last_error,
                    },
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to insert DLQ item to DB: {e}")
            # Fall back to in-memory
            self._items[item.id] = item

    def get(self, item_id: str) -> DeadLetterQueueItem | None:
        """Get a DLQ item by ID.

        Args:
            item_id: Item identifier

        Returns:
            DLQ item or None if not found
        """
        if self._engine:
            return self._get_from_db(item_id)
        else:
            return self._items.get(item_id)

    def _get_from_db(self, item_id: str) -> DeadLetterQueueItem | None:
        """Get item from database."""
        try:
            from sqlalchemy import text

            with self._engine.connect() as conn:
                result = conn.execute(
                    text(f"""
                        SELECT * FROM {self._table_name} WHERE id = :id
                    """),
                    {"id": item_id},
                )
                row = result.fetchone()

                if row:
                    return self._row_to_item(row)
                return None

        except Exception as e:
            logger.error(f"Failed to get DLQ item from DB: {e}")
            return self._items.get(item_id)

    def _row_to_item(self, row: Any) -> DeadLetterQueueItem:
        """Convert database row to DLQ item."""
        return DeadLetterQueueItem(
            id=row.id,
            service_name=row.service_name,
            operation=row.operation,
            payload=json.loads(row.payload) if row.payload else {},
            error_message=row.error_message,
            retry_count=row.retry_count,
            created_at=row.created_at,
            status=RetryStatus[row.status] if row.status else RetryStatus.DLQ,
            last_error=row.last_error,
        )

    def list_pending(
        self,
        service_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DeadLetterQueueItem]:
        """List pending DLQ items.

        Args:
            service_name: Filter by service (optional)
            limit: Maximum items to return
            offset: Items to skip

        Returns:
            List of DLQ items
        """
        if self._engine:
            return self._list_from_db(service_name, limit, offset)
        else:
            items = list(self._items.values())
            if service_name:
                items = [i for i in items if i.service_name == service_name]
            return items[offset : offset + limit]

    def _list_from_db(
        self,
        service_name: str | None,
        limit: int,
        offset: int,
    ) -> list[DeadLetterQueueItem]:
        """List items from database."""
        try:
            from sqlalchemy import text

            with self._engine.connect() as conn:
                if service_name:
                    result = conn.execute(
                        text(f"""
                            SELECT * FROM {self._table_name}
                            WHERE service_name = :service_name
                            ORDER BY created_at DESC
                            LIMIT :limit OFFSET :offset
                        """),
                        {
                            "service_name": service_name,
                            "limit": limit,
                            "offset": offset,
                        },
                    )
                else:
                    result = conn.execute(
                        text(f"""
                            SELECT * FROM {self._table_name}
                            ORDER BY created_at DESC
                            LIMIT :limit OFFSET :offset
                        """),
                        {"limit": limit, "offset": offset},
                    )

                return [self._row_to_item(row) for row in result]

        except Exception as e:
            logger.error(f"Failed to list DLQ items from DB: {e}")
            items = list(self._items.values())
            if service_name:
                items = [i for i in items if i.service_name == service_name]
            return items[offset : offset + limit]

    def mark_retried(self, item_id: str, success: bool = False) -> bool:
        """Mark a DLQ item as retried.

        Args:
            item_id: Item identifier
            success: Whether retry succeeded

        Returns:
            True if item was updated
        """
        if self._engine:
            return self._mark_retried_db(item_id, success)
        else:
            if item_id in self._items:
                item = self._items[item_id]
                item.status = RetryStatus.SUCCESS if success else RetryStatus.FAILED
                return True
            return False

    def _mark_retried_db(self, item_id: str, success: bool) -> bool:
        """Mark item as retried in database."""
        try:
            from sqlalchemy import text

            status = RetryStatus.SUCCESS.name if success else RetryStatus.FAILED.name

            with self._engine.connect() as conn:
                result = conn.execute(
                    text(f"""
                        UPDATE {self._table_name}
                        SET status = :status, updated_at = :updated_at
                        WHERE id = :id
                    """),
                    {
                        "id": item_id,
                        "status": status,
                        "updated_at": datetime.utcnow(),
                    },
                )
                conn.commit()
                return result.rowcount > 0

        except Exception as e:
            logger.error(f"Failed to mark DLQ item as retried: {e}")
            return False

    def delete(self, item_id: str) -> bool:
        """Delete a DLQ item.

        Args:
            item_id: Item identifier

        Returns:
            True if item was deleted
        """
        if self._engine:
            return self._delete_from_db(item_id)
        else:
            if item_id in self._items:
                del self._items[item_id]
                return True
            return False

    def _delete_from_db(self, item_id: str) -> bool:
        """Delete item from database."""
        try:
            from sqlalchemy import text

            with self._engine.connect() as conn:
                result = conn.execute(
                    text(f"DELETE FROM {self._table_name} WHERE id = :id"),
                    {"id": item_id},
                )
                conn.commit()
                return result.rowcount > 0

        except Exception as e:
            logger.error(f"Failed to delete DLQ item from DB: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get DLQ statistics.

        Returns:
            Statistics dictionary
        """
        if self._engine:
            return self._get_stats_from_db()
        else:
            items = list(self._items.values())
            by_service: dict[str, int] = {}
            for item in items:
                by_service[item.service_name] = by_service.get(item.service_name, 0) + 1

            return {
                "total_count": len(items),
                "by_service": by_service,
                "pending_count": len([i for i in items if i.status == RetryStatus.DLQ]),
            }

    def _get_stats_from_db(self) -> dict[str, Any]:
        """Get stats from database."""
        try:
            from sqlalchemy import text

            with self._engine.connect() as conn:
                # Total count
                total_result = conn.execute(
                    text(f"SELECT COUNT(*) FROM {self._table_name}")
                )
                total_count = total_result.scalar()

                # By service
                service_result = conn.execute(
                    text(f"""
                        SELECT service_name, COUNT(*) as count
                        FROM {self._table_name}
                        GROUP BY service_name
                    """)
                )
                by_service = {row.service_name: row.count for row in service_result}

                # Pending count
                pending_result = conn.execute(
                    text(f"""
                        SELECT COUNT(*) FROM {self._table_name}
                        WHERE status = 'DLQ'
                    """)
                )
                pending_count = pending_result.scalar()

                return {
                    "total_count": total_count,
                    "by_service": by_service,
                    "pending_count": pending_count,
                }

        except Exception as e:
            logger.error(f"Failed to get DLQ stats from DB: {e}")
            return {"total_count": 0, "by_service": {}, "pending_count": 0}
