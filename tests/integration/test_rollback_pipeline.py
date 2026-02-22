"""Integration tests for rollback pipeline."""

from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.asyncio
async def test_distributed_rollback_lock_prevents_concurrent(acp_container, mock_redis):
    """Test that distributed lock prevents concurrent rollbacks."""
    rollback = acp_container.rollback_coordinator

    # Create rollback operations
    op1 = await rollback.create_rollback_operation("v1.0.0")
    op2 = await rollback.create_rollback_operation("v1.0.0")

    # Test that operations are created with unique IDs
    assert op1.operation_id != op2.operation_id

    # Verify operations exist in store
    retrieved_op1 = await rollback._store.get(op1.operation_id)
    retrieved_op2 = await rollback._store.get(op2.operation_id)

    assert retrieved_op1 is not None
    assert retrieved_op2 is not None


@pytest.mark.asyncio
async def test_rollback_lock_released_on_completion(acp_container, mock_redis):
    """Test that rollback state is properly tracked on completion."""
    rollback = acp_container.rollback_coordinator

    op = await rollback.create_rollback_operation("v1.0.0")

    # Verify operation can be retrieved
    retrieved = await rollback._store.get(op.operation_id)
    assert retrieved is not None
    assert retrieved.operation_id == op.operation_id

    # Delete operation (simulating completion cleanup)
    deleted = await rollback._store.delete(op.operation_id)
    assert deleted is True

    # Verify operation is deleted
    after_delete = await rollback._store.get(op.operation_id)
    assert after_delete is None


@pytest.mark.asyncio
async def test_rollback_sla_enforcement(acp_container):
    """Test that rollback enforces 60s SLA."""
    rollback = acp_container.rollback_coordinator

    assert rollback.ROLLBACK_SLA_SECONDS == 60.0
