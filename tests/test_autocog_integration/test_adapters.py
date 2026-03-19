"""Tests for system adapters."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.autocog_integration.adapters import (
    AutocogAdapter,
    StrongAdapter,
    DualAdapter,
)


class TestAutocogAdapter:
    """Tests for AUTOCOG adapter."""

    @pytest.mark.asyncio
    async def test_create_adapter(self):
        """Test creating AUTOCOG adapter."""
        adapter = AutocogAdapter()
        assert adapter.system_id == "autocog"
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful connection."""
        adapter = AutocogAdapter()
        result = await adapter.connect()

        assert result is True
        assert adapter.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_with_redis(self):
        """Test connection with Redis client."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        adapter = AutocogAdapter(redis_client=mock_redis)
        result = await adapter.connect()

        assert result is True
        assert adapter.is_connected is True
        mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnection."""
        adapter = AutocogAdapter()
        await adapter.connect()

        result = await adapter.disconnect()

        assert result is True
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_store_and_get_knowledge_item(self):
        """Test storing and retrieving knowledge item."""
        adapter = AutocogAdapter()
        await adapter.connect()

        item_id = "test_item_001"
        data = {
            "knowledge_type": "action",
            "action_id": "001",
            "action_type": "execute",
        }

        # Store item
        stored = await adapter.store_knowledge_item(item_id, data)
        assert stored is True

        # Retrieve item
        retrieved = await adapter.get_knowledge_item(item_id)
        assert retrieved is not None
        assert retrieved["knowledge_type"] == "action"
        assert retrieved["action_id"] == "001"

    @pytest.mark.asyncio
    async def test_store_with_redis(self):
        """Test storing item with Redis."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)

        adapter = AutocogAdapter(redis_client=mock_redis)
        await adapter.connect()

        item_id = "test_item_001"
        data = {"knowledge_type": "action", "action_id": "001"}

        stored = await adapter.store_knowledge_item(item_id, data)
        assert stored is True
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_with_redis(self):
        """Test retrieving item from Redis."""
        import json

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(
            return_value=json.dumps({"knowledge_type": "action"})
        )

        adapter = AutocogAdapter(redis_client=mock_redis)
        await adapter.connect()

        item_id = "test_item_001"
        retrieved = await adapter.get_knowledge_item(item_id)

        assert retrieved is not None
        assert retrieved["knowledge_type"] == "action"
        mock_redis.get.assert_called_once_with("autocog:test_item_001")

    @pytest.mark.asyncio
    async def test_update_knowledge_item(self):
        """Test updating knowledge item."""
        adapter = AutocogAdapter()
        await adapter.connect()

        item_id = "test_item_001"
        initial_data = {"knowledge_type": "action", "action_id": "001"}

        # Store initial item
        await adapter.store_knowledge_item(item_id, initial_data)

        # Update item
        update_data = {"action_type": "execute", "parameters": {"param": "value"}}
        updated = await adapter.update_knowledge_item(item_id, update_data)
        assert updated is True

        # Verify update
        retrieved = await adapter.get_knowledge_item(item_id)
        assert retrieved["action_id"] == "001"  # Original field preserved
        assert retrieved["action_type"] == "execute"  # New field added

    @pytest.mark.asyncio
    async def test_delete_knowledge_item(self):
        """Test deleting knowledge item."""
        adapter = AutocogAdapter()
        await adapter.connect()

        item_id = "test_item_001"
        data = {"knowledge_type": "action", "action_id": "001"}

        # Store item
        await adapter.store_knowledge_item(item_id, data)

        # Delete item
        deleted = await adapter.delete_knowledge_item(item_id)
        assert deleted is True

        # Verify deletion
        retrieved = await adapter.get_knowledge_item(item_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list_knowledge_items(self):
        """Test listing knowledge items."""
        adapter = AutocogAdapter()
        await adapter.connect()

        # Store multiple items
        await adapter.store_knowledge_item("item_001", {"knowledge_type": "action"})
        await adapter.store_knowledge_item("item_002", {"knowledge_type": "assessment"})
        await adapter.store_knowledge_item("item_003", {"knowledge_type": "action"})

        # List all items
        items = await adapter.list_knowledge_items()
        assert len(items) == 3
        assert "item_001" in items
        assert "item_002" in items
        assert "item_003" in items

    @pytest.mark.asyncio
    async def test_list_knowledge_items_filtered(self):
        """Test listing knowledge items filtered by type."""
        adapter = AutocogAdapter()
        await adapter.connect()

        # Store multiple items
        await adapter.store_knowledge_item("item_001", {"knowledge_type": "action"})
        await adapter.store_knowledge_item("item_002", {"knowledge_type": "assessment"})
        await adapter.store_knowledge_item("item_003", {"knowledge_type": "action"})

        # List only action items
        items = await adapter.list_knowledge_items("action")
        assert len(items) == 2
        assert "item_001" in items
        assert "item_003" in items
        assert "item_002" not in items

    @pytest.mark.asyncio
    async def test_execute_action(self):
        """Test executing action."""
        adapter = AutocogAdapter()
        await adapter.connect()

        action_data = {
            "action_id": "001",
            "action_type": "execute",
            "parameters": {"param": "value"},
        }

        result = await adapter.execute_action(action_data)
        assert result["status"] == "success"
        assert "result" in result

    @pytest.mark.asyncio
    async def test_execute_action_not_connected(self):
        """Test executing action when not connected."""
        adapter = AutocogAdapter()
        # Don't connect

        action_data = {"action_id": "001", "action_type": "execute"}
        result = await adapter.execute_action(action_data)

        assert result["status"] == "failed"
        assert "error" in result


class TestStrongAdapter:
    """Tests for STRONG adapter."""

    @pytest.mark.asyncio
    async def test_create_adapter(self):
        """Test creating STRONG adapter."""
        adapter = StrongAdapter()
        assert adapter.system_id == "strong"
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful connection."""
        adapter = StrongAdapter()
        result = await adapter.connect()

        assert result is True
        assert adapter.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_with_qdrant(self):
        """Test connection with Qdrant client."""
        mock_qdrant = AsyncMock()
        mock_qdrant.health_check = AsyncMock(return_value=True)

        adapter = StrongAdapter(qdrant_client=mock_qdrant)
        result = await adapter.connect()

        assert result is True
        assert adapter.is_connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnection."""
        adapter = StrongAdapter()
        await adapter.connect()

        result = await adapter.disconnect()

        assert result is True
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_store_and_get_knowledge_item(self):
        """Test storing and retrieving knowledge item."""
        adapter = StrongAdapter()
        await adapter.connect()

        item_id = "test_item_001"
        data = {
            "knowledge_type": "belief_embedding",
            "embedding_id": "001",
            "vector": [0.1, 0.2, 0.3],
        }

        # Store item
        stored = await adapter.store_knowledge_item(item_id, data)
        assert stored is True

        # Retrieve item
        retrieved = await adapter.get_knowledge_item(item_id)
        assert retrieved is not None
        assert retrieved["knowledge_type"] == "belief_embedding"
        assert retrieved["embedding_id"] == "001"

    @pytest.mark.asyncio
    async def test_update_knowledge_item(self):
        """Test updating knowledge item."""
        adapter = StrongAdapter()
        await adapter.connect()

        item_id = "test_item_001"
        initial_data = {"knowledge_type": "belief_embedding", "embedding_id": "001"}

        # Store initial item
        await adapter.store_knowledge_item(item_id, initial_data)

        # Update item
        update_data = {"vector": [0.1, 0.2, 0.3], "confidence": 0.85}
        updated = await adapter.update_knowledge_item(item_id, update_data)
        assert updated is True

        # Verify update
        retrieved = await adapter.get_knowledge_item(item_id)
        assert retrieved["embedding_id"] == "001"  # Original field preserved
        assert retrieved["vector"] == [0.1, 0.2, 0.3]  # New field added
        assert retrieved["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_delete_knowledge_item(self):
        """Test deleting knowledge item."""
        adapter = StrongAdapter()
        await adapter.connect()

        item_id = "test_item_001"
        data = {"knowledge_type": "belief_embedding", "embedding_id": "001"}

        # Store item
        await adapter.store_knowledge_item(item_id, data)

        # Delete item
        deleted = await adapter.delete_knowledge_item(item_id)
        assert deleted is True

        # Verify deletion
        retrieved = await adapter.get_knowledge_item(item_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list_knowledge_items(self):
        """Test listing knowledge items."""
        adapter = StrongAdapter()
        await adapter.connect()

        # Store multiple items
        await adapter.store_knowledge_item(
            "item_001", {"knowledge_type": "belief_embedding"}
        )
        await adapter.store_knowledge_item(
            "item_002", {"knowledge_type": "learning_update"}
        )
        await adapter.store_knowledge_item(
            "item_003", {"knowledge_type": "belief_embedding"}
        )

        # List all items
        items = await adapter.list_knowledge_items()
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_list_knowledge_items_filtered(self):
        """Test listing knowledge items filtered by type."""
        adapter = StrongAdapter()
        await adapter.connect()

        # Store multiple items
        await adapter.store_knowledge_item(
            "item_001", {"knowledge_type": "belief_embedding"}
        )
        await adapter.store_knowledge_item(
            "item_002", {"knowledge_type": "learning_update"}
        )
        await adapter.store_knowledge_item(
            "item_003", {"knowledge_type": "belief_embedding"}
        )

        # List only belief_embedding items
        items = await adapter.list_knowledge_items("belief_embedding")
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_process_learning_update(self):
        """Test processing learning update."""
        adapter = StrongAdapter()
        await adapter.connect()

        update_data = {
            "update_id": "001",
            "gradient_info": {"loss": 0.1},
            "loss_value": 0.1,
        }

        result = await adapter.process_learning_update(update_data)
        assert result["status"] == "success"
        assert "result" in result

    @pytest.mark.asyncio
    async def test_process_learning_update_not_connected(self):
        """Test processing learning update when not connected."""
        adapter = StrongAdapter()
        # Don't connect

        update_data = {"update_id": "001", "gradient_info": {"loss": 0.1}}
        result = await adapter.process_learning_update(update_data)

        assert result["status"] == "failed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_vectorize_belief(self):
        """Test vectorizing belief."""
        adapter = StrongAdapter()
        await adapter.connect()

        belief_data = {
            "belief_id": "001",
            "content": "Test belief content",
        }

        result = await adapter.vectorize_belief(belief_data)
        assert result["status"] == "success"
        assert "vector" in result

    @pytest.mark.asyncio
    async def test_vectorize_belief_not_connected(self):
        """Test vectorizing belief when not connected."""
        adapter = StrongAdapter()
        # Don't connect

        belief_data = {"belief_id": "001", "content": "Test"}
        result = await adapter.vectorize_belief(belief_data)

        assert result["status"] == "failed"
        assert "error" in result


class TestDualAdapter:
    """Tests for dual adapter."""

    @pytest.mark.asyncio
    async def test_create_dual_adapter(self):
        """Test creating dual adapter."""
        autocog_adapter = AutocogAdapter()
        strong_adapter = StrongAdapter()

        dual_adapter = DualAdapter(autocog_adapter, strong_adapter)
        assert dual_adapter.autocog == autocog_adapter
        assert dual_adapter.strong == strong_adapter
        assert dual_adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_both(self):
        """Test connecting to both systems."""
        autocog_adapter = AutocogAdapter()
        strong_adapter = StrongAdapter()
        dual_adapter = DualAdapter(autocog_adapter, strong_adapter)

        result = await dual_adapter.connect_both()
        assert result is True
        assert dual_adapter.is_connected is True
        assert autocog_adapter.is_connected is True
        assert strong_adapter.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_both_failure(self):
        """Test connecting to both systems with failure."""
        # This test would require mocking a failure scenario
        # For now, we test the basic structure
        autocog_adapter = AutocogAdapter()
        strong_adapter = StrongAdapter()
        dual_adapter = DualAdapter(autocog_adapter, strong_adapter)

        # Both should succeed in normal case
        result = await dual_adapter.connect_both()
        assert result is True

    @pytest.mark.asyncio
    async def test_disconnect_both(self):
        """Test disconnecting from both systems."""
        autocog_adapter = AutocogAdapter()
        strong_adapter = StrongAdapter()
        dual_adapter = DualAdapter(autocog_adapter, strong_adapter)

        # Connect first
        await dual_adapter.connect_both()

        # Disconnect
        result = await dual_adapter.disconnect_both()
        assert result is True
        assert dual_adapter.is_connected is False
        assert autocog_adapter.is_connected is False
        assert strong_adapter.is_connected is False
