"""Tests for the learning bridge."""

import asyncio

import pytest
from src.autocog_integration.adapters import AutocogAdapter, StrongAdapter
from src.autocog_integration.bridge import (
    BridgeMetrics,
    BridgeStatus,
    LearningBridge,
    create_learning_bridge,
)
from src.autocog_integration.protocols import TransferStatus


class TestBridgeMetrics:
    """Tests for BridgeMetrics."""

    def test_create_metrics(self):
        """Test creating metrics."""
        metrics = BridgeMetrics()
        assert metrics.total_transfers == 0
        assert metrics.successful_transfers == 0
        assert metrics.failed_transfers == 0

    def test_success_rate_no_transfers(self):
        """Test success rate with no transfers."""
        metrics = BridgeMetrics()
        assert metrics.success_rate == 0.0

    def test_success_rate_with_transfers(self):
        """Test success rate with transfers."""
        metrics = BridgeMetrics()
        metrics.total_transfers = 10
        metrics.successful_transfers = 8
        metrics.failed_transfers = 2

        assert metrics.success_rate == 80.0

    def test_average_latency_no_transfers(self):
        """Test average latency with no transfers."""
        metrics = BridgeMetrics()
        assert metrics.average_latency_ms == 0.0

    def test_average_latency_with_transfers(self):
        """Test average latency with transfers."""
        metrics = BridgeMetrics()
        metrics.total_transfers = 5
        metrics.total_latency_ms = 1000.0  # 1 second total

        assert metrics.average_latency_ms == 200.0  # 200ms average

    def test_transfer_rates(self):
        """Test transfer rates calculation."""
        metrics = BridgeMetrics()
        metrics.total_transfers = 10
        metrics.autocog_items_transferred = 6
        metrics.strong_items_transferred = 4

        assert metrics.autocog_transfer_rate == 60.0
        assert metrics.strong_transfer_rate == 40.0


class TestLearningBridge:
    """Tests for LearningBridge."""

    @pytest.mark.asyncio
    async def test_create_bridge(self):
        """Test creating learning bridge."""
        bridge = LearningBridge()
        assert bridge is not None
        assert bridge.autocog_adapter is not None
        assert bridge.strong_adapter is not None
        assert bridge.enable_auto_sync is True

    @pytest.mark.asyncio
    async def test_initialize_bridge(self):
        """Test initializing learning bridge."""
        bridge = LearningBridge()
        result = await bridge.initialize()

        assert result is True
        assert bridge._status == BridgeStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_initialize_with_adapters(self):
        """Test initializing with custom adapters."""
        autocog_adapter = AutocogAdapter()
        strong_adapter = StrongAdapter()

        bridge = LearningBridge(
            autocog_adapter=autocog_adapter,
            strong_adapter=strong_adapter,
        )
        result = await bridge.initialize()

        assert result is True
        assert bridge.autocog_adapter == autocog_adapter
        assert bridge.strong_adapter == strong_adapter

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Test starting and stopping bridge."""
        bridge = LearningBridge()
        await bridge.initialize()

        # Start bridge
        await bridge.start()
        assert bridge._running is True

        # Stop bridge
        await bridge.stop()
        assert bridge._running is False
        assert bridge._status == BridgeStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_start_without_auto_sync(self):
        """Test starting bridge without auto-sync."""
        bridge = LearningBridge(enable_auto_sync=False)
        await bridge.initialize()

        await bridge.start()
        assert bridge._running is True
        assert bridge._sync_task is None  # No auto-sync task

    @pytest.mark.asyncio
    async def test_transfer_to_strong(self):
        """Test transferring knowledge to STRONG system."""
        bridge = LearningBridge()
        await bridge.initialize()

        item_id = "action_001"
        knowledge_type = "action"
        payload = {
            "action_id": "001",
            "action_type": "execute",
            "parameters": {"param": "value"},
        }

        transfer = await bridge.transfer_to_strong(
            knowledge_item_id=item_id,
            knowledge_type=knowledge_type,
            payload=payload,
        )

        assert transfer.source_system == "autocog"
        assert transfer.target_system == "strong"
        assert transfer.knowledge_item_id == item_id
        assert transfer.status == TransferStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_transfer_to_autocog(self):
        """Test transferring knowledge to AUTOCOG system."""
        bridge = LearningBridge()
        await bridge.initialize()

        item_id = "embedding_001"
        knowledge_type = "belief_embedding"
        payload = {
            "embedding_id": "001",
            "vector": [0.1, 0.2, 0.3],
            "metadata": {"test": "data"},
        }

        transfer = await bridge.transfer_to_autocog(
            knowledge_item_id=item_id,
            knowledge_type=knowledge_type,
            payload=payload,
        )

        assert transfer.source_system == "strong"
        assert transfer.target_system == "autocog"
        assert transfer.knowledge_item_id == item_id
        assert transfer.status == TransferStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_transfer_with_validation_failure(self):
        """Test transfer with validation failure."""
        bridge = LearningBridge()
        await bridge.initialize()

        # Create invalid transfer (missing required fields)
        item_id = "invalid_item"
        knowledge_type = "action"
        payload = {}  # Missing required fields

        transfer = await bridge.transfer_to_strong(
            knowledge_item_id=item_id,
            knowledge_type=knowledge_type,
            payload=payload,
        )

        assert transfer.status == TransferStatus.FAILED
        assert transfer.error is not None
        assert "validation" in transfer.error.lower()

    @pytest.mark.asyncio
    async def test_sync_all(self):
        """Test syncing all knowledge items."""
        bridge = LearningBridge()
        await bridge.initialize()

        # Store items in both systems
        await bridge.autocog_adapter.store_knowledge_item(
            "autocog_item_001",
            {
                "knowledge_type": "action",
                "action_id": "001",
                "action_type": "execute",
                "parameters": {"param": "value"},
            },
        )
        await bridge.strong_adapter.store_knowledge_item(
            "strong_item_001",
            {
                "knowledge_type": "belief_embedding",
                "embedding_id": "001",
                "vector": [0.1, 0.2, 0.3],
                "metadata": {"test": "data"},
            },
        )

        # Sync all
        transfers = await bridge.sync_all()

        assert len(transfers) == 2
        assert all(t.status == TransferStatus.COMPLETED for t in transfers)

    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Test getting bridge metrics."""
        bridge = LearningBridge()
        await bridge.initialize()

        # Perform some transfers
        await bridge.transfer_to_strong(
            "item_001",
            "action",
            {"action_id": "001", "action_type": "execute", "parameters": {}},
        )

        metrics = await bridge.get_metrics()

        assert metrics.total_transfers > 0
        assert metrics.successful_transfers > 0
        assert metrics.success_rate > 0

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Test getting bridge status."""
        bridge = LearningBridge()

        # Initial status
        status = await bridge.get_status()
        assert status == BridgeStatus.INITIALIZING

        # After initialization
        await bridge.initialize()
        status = await bridge.get_status()
        assert status == BridgeStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_set_callbacks(self):
        """Test setting callbacks."""
        bridge = LearningBridge()

        # Set callbacks
        def on_complete(transfer):
            pass

        def on_failure(transfer, error):
            pass

        def on_validation_failure(transfer):
            pass

        bridge.set_on_transfer_complete(on_complete)
        bridge.set_on_transfer_failure(on_failure)
        bridge.set_on_validation_failure(on_validation_failure)

        assert bridge._on_transfer_complete == on_complete
        assert bridge._on_transfer_failure == on_failure
        assert bridge._on_validation_failure == on_validation_failure

    @pytest.mark.asyncio
    async def test_get_transfer_history(self):
        """Test getting transfer from history."""
        bridge = LearningBridge()
        await bridge.initialize()

        # Perform transfer
        transfer = await bridge.transfer_to_strong(
            "item_001",
            "action",
            {"action_id": "001", "action_type": "execute", "parameters": {}},
        )

        # Get from history
        retrieved = bridge.get_transfer_history(transfer.transfer_id)
        assert retrieved is not None
        assert retrieved.transfer_id == transfer.transfer_id

    @pytest.mark.asyncio
    async def test_get_transfers_by_status(self):
        """Test getting transfers by status."""
        bridge = LearningBridge()
        await bridge.initialize()

        # Perform transfers
        await bridge.transfer_to_strong(
            "item_001",
            "action",
            {"action_id": "001", "action_type": "execute", "parameters": {}},
        )

        # Get completed transfers
        completed = bridge.get_transfers_by_status(TransferStatus.COMPLETED)
        assert len(completed) > 0

    @pytest.mark.asyncio
    async def test_get_transfers_by_system(self):
        """Test getting transfers by system."""
        bridge = LearningBridge()
        await bridge.initialize()

        # Perform transfers
        await bridge.transfer_to_strong(
            "item_001",
            "action",
            {"action_id": "001", "action_type": "execute", "parameters": {}},
        )

        # Get AUTOCOG transfers
        autocog_transfers = bridge.get_transfers_by_system("autocog")
        assert len(autocog_transfers) > 0

    @pytest.mark.asyncio
    async def test_auto_sync_loop(self):
        """Test auto-sync loop functionality."""
        bridge = LearningBridge(sync_interval=0.1)  # Short interval for testing
        await bridge.initialize()

        # Start bridge
        await bridge.start()

        # Store items
        await bridge.autocog_adapter.store_knowledge_item(
            "sync_item_001",
            {
                "knowledge_type": "action",
                "action_id": "001",
                "action_type": "execute",
                "parameters": {"param": "value"},
            },
        )

        # Wait for auto-sync to trigger
        await asyncio.sleep(0.2)

        # Check that sync happened
        metrics = await bridge.get_metrics()
        assert metrics.total_transfers > 0

        # Stop bridge
        await bridge.stop()


class TestCreateLearningBridge:
    """Tests for create_learning_bridge factory function."""

    @pytest.mark.asyncio
    async def test_create_learning_bridge(self):
        """Test creating learning bridge via factory."""
        bridge = await create_learning_bridge()

        assert bridge is not None
        assert bridge._status == BridgeStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_create_learning_bridge_with_adapters(self):
        """Test creating learning bridge with custom adapters."""
        autocog_adapter = AutocogAdapter()
        strong_adapter = StrongAdapter()

        bridge = await create_learning_bridge(
            autocog_adapter=autocog_adapter,
            strong_adapter=strong_adapter,
        )

        assert bridge is not None
        assert bridge.autocog_adapter == autocog_adapter
        assert bridge.strong_adapter == strong_adapter

    @pytest.mark.asyncio
    async def test_create_learning_bridge_disabled_auto_sync(self):
        """Test creating learning bridge with auto-sync disabled."""
        bridge = await create_learning_bridge(enable_auto_sync=False)

        assert bridge is not None
        assert bridge.enable_auto_sync is False

    @pytest.mark.asyncio
    async def test_create_learning_bridge_failure(self):
        """Test creating learning bridge with initialization failure."""
        # This would require mocking a failure scenario
        # For now, test that successful creation works
        bridge = await create_learning_bridge()
        assert bridge is not None
