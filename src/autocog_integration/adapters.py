"""API adapters for AUTOCOG and STRONG systems."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class SystemAdapter(ABC):
    """Abstract base class for system adapters."""

    def __init__(self, system_id: str):
        self.system_id = system_id
        self._is_connected = False
        self._event_handlers: dict[str, Callable] = {}

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the system."""
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from the system."""
        pass

    @abstractmethod
    async def get_knowledge_item(self, item_id: str) -> dict[str, Any] | None:
        """Get a knowledge item by ID."""
        pass

    @abstractmethod
    async def store_knowledge_item(self, item_id: str, data: dict[str, Any]) -> bool:
        """Store a knowledge item."""
        pass

    @abstractmethod
    async def update_knowledge_item(self, item_id: str, data: dict[str, Any]) -> bool:
        """Update a knowledge item."""
        pass

    @abstractmethod
    async def delete_knowledge_item(self, item_id: str) -> bool:
        """Delete a knowledge item."""
        pass

    @abstractmethod
    async def list_knowledge_items(
        self, knowledge_type: str | None = None
    ) -> list[str]:
        """List knowledge item IDs."""
        pass

    def register_event_handler(self, event_type: str, handler: Callable) -> None:
        """Register an event handler."""
        self._event_handlers[event_type] = handler

    async def trigger_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Trigger an event."""
        handler = self._event_handlers.get(event_type)
        if handler:
            await handler(data)

    @property
    def is_connected(self) -> bool:
        """Check if adapter is connected."""
        return self._is_connected


class AutocogAdapter(SystemAdapter):
    """Adapter for AUTOCOG (Autonomous Cognition) system."""

    def __init__(self, redis_client=None):
        super().__init__("autocog")
        self.redis_client = redis_client
        self._knowledge_store: dict[str, dict[str, Any]] = {}
        self._action_executor = None
        self._controller = None

    async def connect(self) -> bool:
        """Connect to AUTOCOG system."""
        try:
            # Initialize AUTOCOG components
            from src.autonomous_cognition.action_executor import ActionExecutor
            from src.autonomous_cognition.controller import (
                AutonomousCognitionController,
            )

            self._controller = AutonomousCognitionController()
            self._action_executor = ActionExecutor()

            # Simulate connection to Redis if client provided
            if self.redis_client:
                await self.redis_client.ping()

            self._is_connected = True
            logger.info("Connected to AUTOCOG system")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to AUTOCOG: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from AUTOCOG system."""
        try:
            self._is_connected = False
            logger.info("Disconnected from AUTOCOG system")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from AUTOCOG: {e}")
            return False

    async def get_knowledge_item(self, item_id: str) -> dict[str, Any] | None:
        """Get a knowledge item from AUTOCOG."""
        if not self._is_connected:
            logger.warning("Not connected to AUTOCOG")
            return None

        # Check local store first
        if item_id in self._knowledge_store:
            return self._knowledge_store[item_id]

        # Try to get from Redis if available
        if self.redis_client:
            try:
                data = await self.redis_client.get(f"autocog:{item_id}")
                if data:
                    import json

                    return json.loads(data)
            except Exception as e:
                logger.error(f"Error getting from Redis: {e}")

        return None

    async def store_knowledge_item(self, item_id: str, data: dict[str, Any]) -> bool:
        """Store a knowledge item in AUTOCOG."""
        if not self._is_connected:
            logger.warning("Not connected to AUTOCOG")
            return False

        try:
            # Store in local cache
            self._knowledge_store[item_id] = data

            # Store in Redis if available
            if self.redis_client:
                import json

                await self.redis_client.set(f"autocog:{item_id}", json.dumps(data))

            logger.debug(f"Stored knowledge item {item_id} in AUTOCOG")
            return True

        except Exception as e:
            logger.error(f"Error storing knowledge item: {e}")
            return False

    async def update_knowledge_item(self, item_id: str, data: dict[str, Any]) -> bool:
        """Update a knowledge item in AUTOCOG."""
        if not self._is_connected:
            logger.warning("Not connected to AUTOCOG")
            return False

        try:
            # Get existing item
            existing = await self.get_knowledge_item(item_id)
            if not existing:
                return False

            # Merge data
            updated = {**existing, **data}

            # Store updated item
            return await self.store_knowledge_item(item_id, updated)

        except Exception as e:
            logger.error(f"Error updating knowledge item: {e}")
            return False

    async def delete_knowledge_item(self, item_id: str) -> bool:
        """Delete a knowledge item from AUTOCOG."""
        if not self._is_connected:
            logger.warning("Not connected to AUTOCOG")
            return False

        try:
            # Remove from local store
            if item_id in self._knowledge_store:
                del self._knowledge_store[item_id]

            # Remove from Redis if available
            if self.redis_client:
                await self.redis_client.delete(f"autocog:{item_id}")

            logger.debug(f"Deleted knowledge item {item_id} from AUTOCOG")
            return True

        except Exception as e:
            logger.error(f"Error deleting knowledge item: {e}")
            return False

    async def list_knowledge_items(
        self, knowledge_type: str | None = None
    ) -> list[str]:
        """List knowledge item IDs from AUTOCOG."""
        if not self._is_connected:
            logger.warning("Not connected to AUTOCOG")
            return []

        try:
            # Get from local store
            items = list(self._knowledge_store.keys())

            # Filter by type if specified
            if knowledge_type:
                items = [
                    item_id
                    for item_id in items
                    if self._knowledge_store.get(item_id, {}).get("knowledge_type")
                    == knowledge_type
                ]

            return items

        except Exception as e:
            logger.error(f"Error listing knowledge items: {e}")
            return []

    async def execute_action(self, action_data: dict[str, Any]) -> dict[str, Any]:
        """Execute an action in AUTOCOG."""
        if not self._is_connected or not self._action_executor:
            logger.warning("Not connected to AUTOCOG or action executor not available")
            return {"status": "failed", "error": "Not connected"}

        try:
            # Execute action through action executor (mock implementation)
            # In production, this would use the real ActionExecutor
            action_id = action_data.get("action_id", "unknown")
            action_type = action_data.get("action_type", "execute")
            parameters = action_data.get("parameters", {})

            # Mock execution result
            result = {
                "action_id": action_id,
                "action_type": action_type,
                "status": "executed",
                "parameters": parameters,
                "timestamp": "2024-01-01T00:00:00Z",
            }

            return {"status": "success", "result": result}

        except Exception as e:
            logger.error(f"Error executing action: {e}")
            return {"status": "failed", "error": str(e)}


class StrongAdapter(SystemAdapter):
    """Adapter for STRONG (Strong AI) system."""

    def __init__(self, qdrant_client=None):
        super().__init__("strong")
        self.qdrant_client = qdrant_client
        self._knowledge_store: dict[str, dict[str, Any]] = {}
        self._belief_engine = None
        self._learning_engine = None

    async def connect(self) -> bool:
        """Connect to STRONG system."""
        try:
            # Initialize STRONG components (mock implementations for now)
            # In production, these would be real implementations
            class MockBeliefEngine:
                async def vectorize(self, data):
                    return [0.1, 0.2, 0.3]  # Mock vector

            class MockLearningEngine:
                async def process_update(self, data):
                    return {"status": "processed", "loss": 0.1}

            self._belief_engine = MockBeliefEngine()
            self._learning_engine = MockLearningEngine()

            # Simulate connection to Qdrant if client provided
            if self.qdrant_client:
                await self.qdrant_client.health_check()

            self._is_connected = True
            logger.info("Connected to STRONG system")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to STRONG: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from STRONG system."""
        try:
            self._is_connected = False
            logger.info("Disconnected from STRONG system")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from STRONG: {e}")
            return False

    async def get_knowledge_item(self, item_id: str) -> dict[str, Any] | None:
        """Get a knowledge item from STRONG."""
        if not self._is_connected:
            logger.warning("Not connected to STRONG")
            return None

        # Check local store first
        if item_id in self._knowledge_store:
            return self._knowledge_store[item_id]

        # Try to get from Qdrant if available
        if self.qdrant_client:
            try:
                result = await self.qdrant_client.retrieve(
                    collection_name="strong_knowledge", ids=[item_id]
                )
                if result and len(result) > 0:
                    return result[0].payload
            except Exception as e:
                logger.error(f"Error getting from Qdrant: {e}")

        return None

    async def store_knowledge_item(self, item_id: str, data: dict[str, Any]) -> bool:
        """Store a knowledge item in STRONG."""
        if not self._is_connected:
            logger.warning("Not connected to STRONG")
            return False

        try:
            # Store in local cache
            self._knowledge_store[item_id] = data

            # Store in Qdrant if available
            if self.qdrant_client:
                vector = data.get("vector", [])
                payload = {k: v for k, v in data.items() if k != "vector"}

                await self.qdrant_client.upsert(
                    collection_name="strong_knowledge",
                    points=[{"id": item_id, "vector": vector, "payload": payload}],
                )

            logger.debug(f"Stored knowledge item {item_id} in STRONG")
            return True

        except Exception as e:
            logger.error(f"Error storing knowledge item: {e}")
            return False

    async def update_knowledge_item(self, item_id: str, data: dict[str, Any]) -> bool:
        """Update a knowledge item in STRONG."""
        if not self._is_connected:
            logger.warning("Not connected to STRONG")
            return False

        try:
            # Get existing item
            existing = await self.get_knowledge_item(item_id)
            if not existing:
                return False

            # Merge data
            updated = {**existing, **data}

            # Store updated item
            return await self.store_knowledge_item(item_id, updated)

        except Exception as e:
            logger.error(f"Error updating knowledge item: {e}")
            return False

    async def delete_knowledge_item(self, item_id: str) -> bool:
        """Delete a knowledge item from STRONG."""
        if not self._is_connected:
            logger.warning("Not connected to STRONG")
            return False

        try:
            # Remove from local store
            if item_id in self._knowledge_store:
                del self._knowledge_store[item_id]

            # Remove from Qdrant if available
            if self.qdrant_client:
                await self.qdrant_client.delete(
                    collection_name="strong_knowledge",
                    points_selector={"ids": [item_id]},
                )

            logger.debug(f"Deleted knowledge item {item_id} from STRONG")
            return True

        except Exception as e:
            logger.error(f"Error deleting knowledge item: {e}")
            return False

    async def list_knowledge_items(
        self, knowledge_type: str | None = None
    ) -> list[str]:
        """List knowledge item IDs from STRONG."""
        if not self._is_connected:
            logger.warning("Not connected to STRONG")
            return []

        try:
            # Get from local store
            items = list(self._knowledge_store.keys())

            # Filter by type if specified
            if knowledge_type:
                items = [
                    item_id
                    for item_id in items
                    if self._knowledge_store.get(item_id, {}).get("knowledge_type")
                    == knowledge_type
                ]

            return items

        except Exception as e:
            logger.error(f"Error listing knowledge items: {e}")
            return []

    async def process_learning_update(
        self, update_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Process a learning update in STRONG."""
        if not self._is_connected or not self._learning_engine:
            logger.warning("Not connected to STRONG or learning engine not available")
            return {"status": "failed", "error": "Not connected"}

        try:
            # Process update through learning engine
            result = await self._learning_engine.process_update(update_data)
            return {"status": "success", "result": result}

        except Exception as e:
            logger.error(f"Error processing learning update: {e}")
            return {"status": "failed", "error": str(e)}

    async def vectorize_belief(self, belief_data: dict[str, Any]) -> dict[str, Any]:
        """Vectorize a belief in STRONG."""
        if not self._is_connected or not self._belief_engine:
            logger.warning("Not connected to STRONG or belief engine not available")
            return {"status": "failed", "error": "Not connected"}

        try:
            # Vectorize belief through belief engine
            vector = await self._belief_engine.vectorize(belief_data)
            return {"status": "success", "vector": vector}

        except Exception as e:
            logger.error(f"Error vectorizing belief: {e}")
            return {"status": "failed", "error": str(e)}


class DualAdapter:
    """Dual adapter managing both AUTOCOG and STRONG adapters."""

    def __init__(self, autocog_adapter: AutocogAdapter, strong_adapter: StrongAdapter):
        self.autocog = autocog_adapter
        self.strong = strong_adapter
        self._is_connected = False

    async def connect_both(self) -> bool:
        """Connect to both systems."""
        try:
            autocog_result = await self.autocog.connect()
            strong_result = await self.strong.connect()

            self._is_connected = autocog_result and strong_result
            return self._is_connected

        except Exception as e:
            logger.error(f"Error connecting dual adapter: {e}")
            return False

    async def disconnect_both(self) -> bool:
        """Disconnect from both systems."""
        try:
            autocog_result = await self.autocog.disconnect()
            strong_result = await self.strong.disconnect()

            self._is_connected = False
            return autocog_result and strong_result

        except Exception as e:
            logger.error(f"Error disconnecting dual adapter: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        """Check if both adapters are connected."""
        return (
            self._is_connected
            and self.autocog.is_connected
            and self.strong.is_connected
        )
