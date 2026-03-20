"""Tests for dead letter queue with mocked PostgreSQL.

Tests:
- DLQ operations without real database
- Mocked PostgreSQL connection
- Queue operations (enqueue, get, list, mark retried, delete)
- DLQ retry functionality
- Stats collection
- Error handling

For ST-NS-039: Retry Coordinator with Budget Management - Coverage Improvement
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from src.autonomous_control_plane.components.dead_letter_queue import DeadLetterQueue
from src.autonomous_control_plane.models.retry_policy import (
    DeadLetterQueueItem,
    RetryStatus,
)


class TestDeadLetterQueueInMemory:
    """Tests for DLQ using in-memory storage (no database)."""

    @pytest.fixture
    def dlq(self):
        """Create a DLQ without database connection."""
        return DeadLetterQueue(db_engine=None, table_name="test_dlq")

    def test_initialization_without_db(self):
        """Test DLQ initialization without database."""
        dlq = DeadLetterQueue(db_engine=None)
        assert dlq._engine is None
        assert dlq._table_name == "dead_letter_queue"
        assert dlq._items == {}

    def test_enqueue_without_db(self, dlq):
        """Test enqueueing item without database."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_operation",
            payload={"key": "value"},
            error_message="Test error",
            retry_count=3,
        )

        assert item.service_name == "test_service"
        assert item.operation == "test_operation"
        assert item.payload == {"key": "value"}
        assert item.error_message == "Test error"
        assert item.retry_count == 3
        assert item.status == RetryStatus.DLQ
        assert item.id is not None

    def test_enqueue_stores_in_memory(self, dlq):
        """Test that enqueue stores item in memory."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_operation",
            payload={},
            error_message="Error",
            retry_count=1,
        )

        assert item.id in dlq._items
        assert dlq._items[item.id] == item

    def test_get_existing_item(self, dlq):
        """Test getting an existing item."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_operation",
            payload={},
            error_message="Error",
            retry_count=1,
        )

        retrieved = dlq.get(item.id)
        assert retrieved == item

    def test_get_nonexistent_item(self, dlq):
        """Test getting a non-existent item."""
        retrieved = dlq.get("nonexistent-id")
        assert retrieved is None

    def test_list_pending_all_items(self, dlq):
        """Test listing all pending items."""
        # Add multiple items
        for i in range(5):
            dlq.enqueue(
                service_name=f"service_{i}",
                operation="test_op",
                payload={"index": i},
                error_message="Error",
                retry_count=1,
            )

        items = dlq.list_pending()
        assert len(items) == 5

    def test_list_pending_with_service_filter(self, dlq):
        """Test listing items filtered by service."""
        dlq.enqueue(
            service_name="service_a",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )
        dlq.enqueue(
            service_name="service_b",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )
        dlq.enqueue(
            service_name="service_a",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )

        items = dlq.list_pending(service_name="service_a")
        assert len(items) == 2
        assert all(i.service_name == "service_a" for i in items)

    def test_list_pending_with_limit(self, dlq):
        """Test listing items with limit."""
        for i in range(10):
            dlq.enqueue(
                service_name="test_service",
                operation="test_op",
                payload={"index": i},
                error_message="Error",
                retry_count=1,
            )

        items = dlq.list_pending(limit=5)
        assert len(items) == 5

    def test_list_pending_with_offset(self, dlq):
        """Test listing items with offset."""
        for i in range(5):
            dlq.enqueue(
                service_name="test_service",
                operation="test_op",
                payload={"index": i},
                error_message="Error",
                retry_count=1,
            )

        items = dlq.list_pending(limit=2, offset=2)
        assert len(items) == 2

    def test_mark_retried_success(self, dlq):
        """Test marking an item as retried successfully."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )

        result = dlq.mark_retried(item.id, success=True)
        assert result is True
        assert item.status == RetryStatus.SUCCESS

    def test_mark_retried_failure(self, dlq):
        """Test marking an item as retried but failed."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )

        result = dlq.mark_retried(item.id, success=False)
        assert result is True
        assert item.status == RetryStatus.FAILED

    def test_mark_retried_nonexistent(self, dlq):
        """Test marking non-existent item as retried."""
        result = dlq.mark_retried("nonexistent-id", success=True)
        assert result is False

    def test_delete_existing_item(self, dlq):
        """Test deleting an existing item."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )

        result = dlq.delete(item.id)
        assert result is True
        assert item.id not in dlq._items

    def test_delete_nonexistent_item(self, dlq):
        """Test deleting a non-existent item."""
        result = dlq.delete("nonexistent-id")
        assert result is False

    def test_get_stats_empty(self, dlq):
        """Test getting stats with no items."""
        stats = dlq.get_stats()
        assert stats["total_count"] == 0
        assert stats["by_service"] == {}
        assert stats["pending_count"] == 0

    def test_get_stats_with_items(self, dlq):
        """Test getting stats with items."""
        dlq.enqueue(
            service_name="service_a",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )
        dlq.enqueue(
            service_name="service_a",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )
        dlq.enqueue(
            service_name="service_b",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )

        stats = dlq.get_stats()
        assert stats["total_count"] == 3
        assert stats["by_service"]["service_a"] == 2
        assert stats["by_service"]["service_b"] == 1
        assert stats["pending_count"] == 3

    def test_get_stats_after_mark_retried(self, dlq):
        """Test stats after marking items as retried."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )
        dlq.mark_retried(item.id, success=True)

        stats = dlq.get_stats()
        # After marking as SUCCESS, it's no longer in DLQ status
        assert stats["pending_count"] == 0


class TestDeadLetterQueueWithMockedDB:
    """Tests for DLQ with mocked PostgreSQL database."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        return MagicMock()

    @pytest.fixture
    def dlq_with_db(self, mock_engine):
        """Create a DLQ with mocked database."""
        return DeadLetterQueue(db_engine=mock_engine, table_name="test_dlq")

    def test_ensure_table_creates_table_if_not_exists(self, mock_engine):
        """Test that _ensure_table creates table if it doesn't exist."""
        dlq = DeadLetterQueue(db_engine=mock_engine)

        # Mock inspector to say table doesn't exist
        with patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspector = MagicMock()
            mock_inspector.has_table.return_value = False
            mock_inspect.return_value = mock_inspector

            with patch("sqlalchemy.MetaData") as mock_metadata:
                with patch("sqlalchemy.Table"):
                    with patch.object(mock_metadata.return_value, "create_all"):
                        dlq._ensure_table()

        # Table creation should be attempted
        mock_inspect.assert_called_once_with(mock_engine)

    def test_ensure_table_skips_if_exists(self, mock_engine):
        """Test that _ensure_table skips if table exists."""
        dlq = DeadLetterQueue(db_engine=mock_engine)

        with patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspector = MagicMock()
            mock_inspector.has_table.return_value = True
            mock_inspect.return_value = mock_inspector

            dlq._ensure_table()

            # Should check if table exists
            mock_inspector.has_table.assert_called_once_with("dead_letter_queue")

    def test_enqueue_with_db(self, dlq_with_db, mock_engine):
        """Test enqueueing with database stores in DB."""
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspector = MagicMock()
            mock_inspector.has_table.return_value = True
            mock_inspect.return_value = mock_inspector

            with patch("sqlalchemy.text") as mock_text:
                mock_text.return_value = "INSERT_SQL"

                dlq_with_db.enqueue(
                    service_name="test_service",
                    operation="test_op",
                    payload={"key": "value"},
                    error_message="Test error",
                    retry_count=3,
                )

                # Should execute insert
                mock_conn.execute.assert_called_once()
                mock_conn.commit.assert_called_once()

    def test_enqueue_db_fallback_to_memory(self, dlq_with_db, mock_engine):
        """Test enqueue falls back to memory on DB error."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("DB Error")
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspector = MagicMock()
            mock_inspector.has_table.return_value = True
            mock_inspect.return_value = mock_inspector

            with patch("sqlalchemy.text"):
                item = dlq_with_db.enqueue(
                    service_name="test_service",
                    operation="test_op",
                    payload={},
                    error_message="Error",
                    retry_count=1,
                )

                # Should still create item and fall back to memory
                assert item is not None
                assert item.id in dlq_with_db._items

    def test_get_from_db(self, dlq_with_db, mock_engine):
        """Test getting item from database."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = "test-id"
        mock_row.service_name = "test_service"
        mock_row.operation = "test_op"
        mock_row.payload = '{"key": "value"}'
        mock_row.error_message = "Error"
        mock_row.retry_count = 3
        mock_row.created_at = datetime.now(UTC)
        mock_row.status = "DLQ"
        mock_row.last_error = None

        mock_result.fetchone.return_value = mock_row
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with patch("sqlalchemy.text"):
            item = dlq_with_db.get("test-id")

            assert item is not None
            assert item.id == "test-id"
            assert item.service_name == "test_service"

    def test_get_from_db_not_found(self, dlq_with_db, mock_engine):
        """Test getting non-existent item from database."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with patch("sqlalchemy.text"):
            item = dlq_with_db.get("nonexistent-id")
            assert item is None

    def test_get_from_db_error_fallback(self, dlq_with_db, mock_engine):
        """Test get falls back to memory on DB error."""
        mock_engine.connect.side_effect = Exception("DB Error")

        # Pre-populate memory
        dlq_with_db._items["test-id"] = DeadLetterQueueItem(
            id="test-id",
            service_name="test_service",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )

        with patch("sqlalchemy.text"):
            item = dlq_with_db.get("test-id")
            assert item is not None
            assert item.id == "test-id"

    def test_list_from_db_with_service_filter(self, dlq_with_db, mock_engine):
        """Test listing items from DB with service filter."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = "test-id"
        mock_row.service_name = "test_service"
        mock_row.operation = "test_op"
        mock_row.payload = "{}"
        mock_row.error_message = "Error"
        mock_row.retry_count = 1
        mock_row.created_at = datetime.now(UTC)
        mock_row.status = "DLQ"
        mock_row.last_error = None

        mock_result.__iter__.return_value = [mock_row]
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with patch("sqlalchemy.text"):
            dlq_with_db.list_pending(service_name="test_service", limit=10)

            # Should include service filter in query
            mock_conn.execute.assert_called_once()

    def test_list_from_db_error_fallback(self, dlq_with_db, mock_engine):
        """Test list falls back to memory on DB error."""
        mock_engine.connect.side_effect = Exception("DB Error")

        # Pre-populate memory
        dlq_with_db._items["test-id"] = DeadLetterQueueItem(
            id="test-id",
            service_name="test_service",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )

        with patch("sqlalchemy.text"):
            items = dlq_with_db.list_pending()
            assert len(items) == 1

    def test_mark_retried_db(self, dlq_with_db, mock_engine):
        """Test marking item as retried in database."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with patch("sqlalchemy.text"):
            result = dlq_with_db.mark_retried("test-id", success=True)
            assert result is True
            mock_conn.commit.assert_called_once()

    def test_mark_retried_db_not_found(self, dlq_with_db, mock_engine):
        """Test marking non-existent item as retried in database."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with patch("sqlalchemy.text"):
            result = dlq_with_db.mark_retried("nonexistent-id", success=True)
            assert result is False

    def test_delete_from_db(self, dlq_with_db, mock_engine):
        """Test deleting item from database."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with patch("sqlalchemy.text"):
            result = dlq_with_db.delete("test-id")
            assert result is True
            mock_conn.commit.assert_called_once()

    def test_delete_from_db_not_found(self, dlq_with_db, mock_engine):
        """Test deleting non-existent item from database."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with patch("sqlalchemy.text"):
            result = dlq_with_db.delete("nonexistent-id")
            assert result is False

    def test_get_stats_from_db(self, dlq_with_db, mock_engine):
        """Test getting stats from database."""
        mock_conn = MagicMock()

        # Mock total count
        mock_total_result = MagicMock()
        mock_total_result.scalar.return_value = 10

        # Mock service breakdown
        mock_service_result = MagicMock()
        mock_row_a = MagicMock()
        mock_row_a.service_name = "service_a"
        mock_row_a.count = 7
        mock_row_b = MagicMock()
        mock_row_b.service_name = "service_b"
        mock_row_b.count = 3
        mock_service_result.__iter__.return_value = [mock_row_a, mock_row_b]

        # Mock pending count
        mock_pending_result = MagicMock()
        mock_pending_result.scalar.return_value = 5

        mock_conn.execute.side_effect = [
            mock_total_result,
            mock_service_result,
            mock_pending_result,
        ]
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with patch("sqlalchemy.text"):
            stats = dlq_with_db.get_stats()
            assert stats["total_count"] == 10
            assert stats["by_service"]["service_a"] == 7
            assert stats["by_service"]["service_b"] == 3
            assert stats["pending_count"] == 5

    def test_get_stats_from_db_error(self, dlq_with_db, mock_engine):
        """Test stats returns defaults on DB error."""
        mock_engine.connect.side_effect = Exception("DB Error")

        with patch("sqlalchemy.text"):
            stats = dlq_with_db.get_stats()
            assert stats["total_count"] == 0
            assert stats["by_service"] == {}
            assert stats["pending_count"] == 0


class TestDeadLetterQueueItemConversion:
    """Tests for row-to-item conversion."""

    def test_row_to_item_with_null_payload(self):
        """Test converting row with null payload."""
        dlq = DeadLetterQueue(db_engine=None)

        mock_row = MagicMock()
        mock_row.id = "test-id"
        mock_row.service_name = "test_service"
        mock_row.operation = "test_op"
        mock_row.payload = None
        mock_row.error_message = "Error"
        mock_row.retry_count = 1
        mock_row.created_at = datetime.now(UTC)
        mock_row.status = "DLQ"
        mock_row.last_error = None

        item = dlq._row_to_item(mock_row)
        assert item.payload == {}

    def test_row_to_item_with_invalid_status(self):
        """Test converting row with invalid status."""
        dlq = DeadLetterQueue(db_engine=None)

        mock_row = MagicMock()
        mock_row.id = "test-id"
        mock_row.service_name = "test_service"
        mock_row.operation = "test_op"
        mock_row.payload = "{}"
        mock_row.error_message = "Error"
        mock_row.retry_count = 1
        mock_row.created_at = datetime.now(UTC)
        mock_row.status = None
        mock_row.last_error = None

        item = dlq._row_to_item(mock_row)
        assert item.status == RetryStatus.DLQ


class TestDeadLetterQueueRetryFunctionality:
    """Tests for DLQ retry functionality."""

    @pytest.fixture
    def dlq(self):
        """Create a DLQ without database."""
        return DeadLetterQueue(db_engine=None)

    def test_retry_workflow_success(self, dlq):
        """Test complete retry workflow for successful retry."""
        # Add item to DLQ
        item = dlq.enqueue(
            service_name="test_service",
            operation="fetch_data",
            payload={"url": "https://example.com"},
            error_message="Connection timeout",
            retry_count=3,
        )

        # Mark as retried successfully
        result = dlq.mark_retried(item.id, success=True)
        assert result is True

        # Verify status updated
        updated_item = dlq.get(item.id)
        assert updated_item.status == RetryStatus.SUCCESS

    def test_retry_workflow_failure(self, dlq):
        """Test complete retry workflow for failed retry."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="fetch_data",
            payload={"url": "https://example.com"},
            error_message="Connection timeout",
            retry_count=3,
        )

        # Mark as retried but failed
        result = dlq.mark_retried(item.id, success=False)
        assert result is True

        updated_item = dlq.get(item.id)
        assert updated_item.status == RetryStatus.FAILED

    def test_multiple_items_same_service(self, dlq):
        """Test managing multiple items for the same service."""
        items = []
        for i in range(5):
            item = dlq.enqueue(
                service_name="api_client",
                operation="fetch_data",
                payload={"id": i},
                error_message=f"Error {i}",
                retry_count=i,
            )
            items.append(item)

        # List all items
        pending = dlq.list_pending(service_name="api_client")
        assert len(pending) == 5

        # Retry some items
        dlq.mark_retried(items[0].id, success=True)
        dlq.mark_retried(items[1].id, success=False)

        # Check stats
        stats = dlq.get_stats()
        assert stats["total_count"] == 5
        assert stats["by_service"]["api_client"] == 5
        # 2 items marked as retried, so 3 pending
        assert stats["pending_count"] == 3

    def test_item_preserved_after_failed_retry(self, dlq):
        """Test item remains in DLQ after failed retry for audit."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="critical_op",
            payload={"data": "important"},
            error_message="Permanent failure",
            retry_count=5,
        )

        # Mark as failed
        dlq.mark_retried(item.id, success=False)

        # Item should still be retrievable
        retrieved = dlq.get(item.id)
        assert retrieved is not None
        assert retrieved.status == RetryStatus.FAILED

    def test_delete_after_successful_retry(self, dlq):
        """Test deleting item after successful retry."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=3,
        )

        # Mark as retried and delete
        dlq.mark_retried(item.id, success=True)
        dlq.delete(item.id)

        # Item should be gone
        assert dlq.get(item.id) is None


class TestDeadLetterQueueEdgeCases:
    """Tests for edge cases in DLQ."""

    @pytest.fixture
    def dlq(self):
        """Create a DLQ without database."""
        return DeadLetterQueue(db_engine=None)

    def test_empty_payload(self, dlq):
        """Test enqueueing with empty payload."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_op",
            payload={},
            error_message="Error",
            retry_count=1,
        )
        assert item.payload == {}

    def test_large_payload(self, dlq):
        """Test enqueueing with large payload."""
        large_payload = {"data": "x" * 10000}
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_op",
            payload=large_payload,
            error_message="Error",
            retry_count=1,
        )
        assert item.payload == large_payload

    def test_unicode_in_error_message(self, dlq):
        """Test enqueueing with unicode error message."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_op",
            payload={},
            error_message="Error with unicode: 你好世界 🌍",
            retry_count=1,
        )
        assert "你好世界" in item.error_message

    def test_zero_retry_count(self, dlq):
        """Test enqueueing with zero retry count."""
        item = dlq.enqueue(
            service_name="test_service",
            operation="test_op",
            payload={},
            error_message="Immediate failure",
            retry_count=0,
        )
        assert item.retry_count == 0

    def test_ensure_table_with_no_engine(self, dlq):
        """Test _ensure_table with no database engine."""
        # Should not raise
        dlq._ensure_table()

    def test_ensure_table_error_handling(self):
        """Test _ensure_table error handling."""
        mock_engine = MagicMock()
        dlq = DeadLetterQueue(db_engine=mock_engine)

        with patch("sqlalchemy.inspect") as mock_inspect:
            mock_inspect.side_effect = Exception("Inspection failed")

            with pytest.raises(Exception):
                dlq._ensure_table()
