"""Cross-system learning bridge between AUTOCOG and STRONG systems."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from .adapters import AutocogAdapter, DualAdapter, StrongAdapter
from .converters import BidirectionalConverter
from .protocols import KnowledgeTransferProtocol, TransferEvent, TransferStatus

logger = logging.getLogger(__name__)


class BridgeStatus(Enum):
    """Status of the learning bridge."""

    INITIALIZING = "initializing"
    CONNECTED = "connected"
    SYNCING = "syncing"
    PAUSED = "paused"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class BridgeMetrics:
    """Metrics for the learning bridge."""

    total_transfers: int = 0
    successful_transfers: int = 0
    failed_transfers: int = 0
    total_latency_ms: float = 0.0
    last_transfer_time: datetime | None = None
    autocog_items_transferred: int = 0
    strong_items_transferred: int = 0
    validation_failures: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate transfer success rate."""
        if self.total_transfers == 0:
            return 0.0
        return (self.successful_transfers / self.total_transfers) * 100

    @property
    def average_latency_ms(self) -> float:
        """Calculate average transfer latency."""
        if self.total_transfers == 0:
            return 0.0
        return self.total_latency_ms / self.total_transfers

    @property
    def autocog_transfer_rate(self) -> float:
        """Calculate AUTOCOG transfer rate."""
        if self.total_transfers == 0:
            return 0.0
        return (self.autocog_items_transferred / self.total_transfers) * 100

    @property
    def strong_transfer_rate(self) -> float:
        """Calculate STRONG transfer rate."""
        if self.total_transfers == 0:
            return 0.0
        return (self.strong_items_transferred / self.total_transfers) * 100


class LearningBridge:
    """
    Cross-system learning bridge between AUTOCOG and STRONG systems.

    Provides:
    - Bidirectional knowledge transfer
    - Automatic format conversion
    - Validation and verification
    - Metrics and monitoring
    - Error handling and retry logic
    """

    def __init__(
        self,
        autocog_adapter: AutocogAdapter | None = None,
        strong_adapter: StrongAdapter | None = None,
        enable_auto_sync: bool = True,
        sync_interval: float = 30.0,
        max_concurrent_transfers: int = 10,
    ):
        self.autocog_adapter = autocog_adapter or AutocogAdapter()
        self.strong_adapter = strong_adapter or StrongAdapter()
        self.dual_adapter = DualAdapter(self.autocog_adapter, self.strong_adapter)

        self.transfer_protocol = KnowledgeTransferProtocol()
        self.converter = BidirectionalConverter()

        self.enable_auto_sync = enable_auto_sync
        self.sync_interval = sync_interval
        self.max_concurrent_transfers = max_concurrent_transfers

        self._status = BridgeStatus.INITIALIZING
        self._metrics = BridgeMetrics()
        self._running = False
        self._sync_task: asyncio.Task | None = None
        self._transfer_semaphore = asyncio.Semaphore(max_concurrent_transfers)

        # Callbacks
        self._on_transfer_complete: Callable[[TransferEvent], None] | None = None
        self._on_transfer_failure: Callable[[TransferEvent, Exception], None] | None = None
        self._on_validation_failure: Callable[[TransferEvent], None] | None = None

    async def initialize(self) -> bool:
        """Initialize the learning bridge."""
        try:
            logger.info("Initializing learning bridge")

            # Connect to both systems
            connected = await self.dual_adapter.connect_both()
            if not connected:
                logger.error("Failed to connect to one or both systems")
                self._status = BridgeStatus.ERROR
                return False

            self._status = BridgeStatus.CONNECTED
            logger.info("Learning bridge initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Error initializing learning bridge: {e}")
            self._status = BridgeStatus.ERROR
            return False

    async def start(self) -> None:
        """Start the learning bridge."""
        if self._running:
            logger.warning("Learning bridge already running")
            return

        self._running = True

        if self.enable_auto_sync:
            self._sync_task = asyncio.create_task(self._auto_sync_loop())
            logger.info("Learning bridge started with auto-sync")
        else:
            logger.info("Learning bridge started (manual sync mode)")

    async def stop(self) -> None:
        """Stop the learning bridge."""
        if not self._running:
            return

        self._running = False

        if self._sync_task:
            self._sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sync_task

        await self.dual_adapter.disconnect_both()
        self._status = BridgeStatus.DISCONNECTED
        logger.info("Learning bridge stopped")

    async def transfer_to_strong(
        self,
        knowledge_item_id: str,
        knowledge_type: str,
        payload: dict[str, Any],
        priority: str = "medium",
    ) -> TransferEvent:
        """
        Transfer knowledge from AUTOCOG to STRONG system.

        Args:
            knowledge_item_id: ID of the knowledge item
            knowledge_type: Type of knowledge (action, assessment, etc.)
            payload: Knowledge data
            priority: Transfer priority

        Returns:
            TransferEvent with status
        """
        return await self._transfer(
            source_system="autocog",
            target_system="strong",
            knowledge_item_id=knowledge_item_id,
            knowledge_type=knowledge_type,
            payload=payload,
            priority=priority,
        )

    async def transfer_to_autocog(
        self,
        knowledge_item_id: str,
        knowledge_type: str,
        payload: dict[str, Any],
        priority: str = "medium",
    ) -> TransferEvent:
        """
        Transfer knowledge from STRONG to AUTOCOG system.

        Args:
            knowledge_item_id: ID of the knowledge item
            knowledge_type: Type of knowledge (belief_embedding, etc.)
            payload: Knowledge data
            priority: Transfer priority

        Returns:
            TransferEvent with status
        """
        return await self._transfer(
            source_system="strong",
            target_system="autocog",
            knowledge_item_id=knowledge_item_id,
            knowledge_type=knowledge_type,
            payload=payload,
            priority=priority,
        )

    async def sync_all(self) -> list[TransferEvent]:
        """
        Sync all knowledge items between systems.

        Returns:
            List of transfer events
        """
        logger.info("Starting full sync between AUTOCOG and STRONG")

        transfers = []

        # Get all knowledge items from both systems
        autocog_items = await self.autocog_adapter.list_knowledge_items()
        strong_items = await self.strong_adapter.list_knowledge_items()

        # Transfer from AUTOCOG to STRONG
        for item_id in autocog_items:
            item = await self.autocog_adapter.get_knowledge_item(item_id)
            if item:
                knowledge_type = item.get("knowledge_type", "generic")
                transfer = await self.transfer_to_strong(
                    knowledge_item_id=item_id,
                    knowledge_type=knowledge_type,
                    payload=item,
                )
                transfers.append(transfer)

        # Transfer from STRONG to AUTOCOG
        for item_id in strong_items:
            item = await self.strong_adapter.get_knowledge_item(item_id)
            if item:
                knowledge_type = item.get("knowledge_type", "generic")
                transfer = await self.transfer_to_autocog(
                    knowledge_item_id=item_id,
                    knowledge_type=knowledge_type,
                    payload=item,
                )
                transfers.append(transfer)

        logger.info(f"Completed sync with {len(transfers)} transfers")
        return transfers

    async def get_metrics(self) -> BridgeMetrics:
        """Get current bridge metrics."""
        return self._metrics

    async def get_status(self) -> BridgeStatus:
        """Get current bridge status."""
        return self._status

    def set_on_transfer_complete(
        self, callback: Callable[[TransferEvent], None]
    ) -> None:
        """Set callback for transfer completion."""
        self._on_transfer_complete = callback

    def set_on_transfer_failure(
        self, callback: Callable[[TransferEvent, Exception], None]
    ) -> None:
        """Set callback for transfer failure."""
        self._on_transfer_failure = callback

    def set_on_validation_failure(
        self, callback: Callable[[TransferEvent], None]
    ) -> None:
        """Set callback for validation failure."""
        self._on_validation_failure = callback

    async def _transfer(
        self,
        source_system: str,
        target_system: str,
        knowledge_item_id: str,
        knowledge_type: str,
        payload: dict[str, Any],
        priority: str = "medium",
    ) -> TransferEvent:
        """Internal transfer method."""
        from .protocols import TransferPriority

        # Map priority string to enum
        priority_map = {
            "low": TransferPriority.LOW,
            "medium": TransferPriority.MEDIUM,
            "high": TransferPriority.HIGH,
            "critical": TransferPriority.CRITICAL,
        }
        priority_enum = priority_map.get(priority, TransferPriority.MEDIUM)

        # Create transfer event
        event = self.transfer_protocol.create_transfer_event(
            source_system=source_system,
            target_system=target_system,
            knowledge_type=knowledge_type,
            knowledge_item_id=knowledge_item_id,
            payload=payload,
            priority=priority_enum,
        )

        # Process transfer with semaphore for concurrency control
        async with self._transfer_semaphore:
            await self._process_transfer(event)

        return event

    async def _process_transfer(self, event: TransferEvent) -> None:
        """Process a single transfer event."""
        start_time = time.time()
        event.mark_in_progress()

        try:
            # Update status
            self._status = BridgeStatus.SYNCING

            # Validate transfer
            validation_result = self.transfer_protocol.validate_transfer(event)
            if not validation_result.is_valid:
                event.mark_failed(f"Validation failed: {validation_result.errors}")
                self._metrics.validation_failures += 1

                if self._on_validation_failure:
                    self._on_validation_failure(event)
                return

            event.mark_validated()

            # Convert data format
            direction = f"{event.source_system}_to_{event.target_system}"
            converted_data = self.converter.convert(
                {
                    "knowledge_type": event.knowledge_type,
                    "knowledge_item_id": event.knowledge_item_id,
                    "payload": event.payload,
                    "source_system": event.source_system,
                },
                direction,
            )

            # Store in target system
            if event.target_system == "autocog":
                success = await self.autocog_adapter.store_knowledge_item(
                    event.knowledge_item_id, converted_data
                )
            else:  # strong
                success = await self.strong_adapter.store_knowledge_item(
                    event.knowledge_item_id, converted_data
                )

            if success:
                event.mark_completed()

                # Update metrics
                self._metrics.total_transfers += 1
                self._metrics.successful_transfers += 1

                if event.source_system == "autocog":
                    self._metrics.autocog_items_transferred += 1
                else:
                    self._metrics.strong_items_transferred += 1

                # Trigger callback
                if self._on_transfer_complete:
                    self._on_transfer_complete(event)

                logger.debug(f"Transfer completed: {event.knowledge_item_id}")

            else:
                raise Exception("Failed to store in target system")

        except Exception as e:
            event.mark_failed(str(e))
            self._metrics.total_transfers += 1
            self._metrics.failed_transfers += 1

            # Retry if possible
            if self.transfer_protocol.can_retry(event):
                self.transfer_protocol.record_retry(event)
                logger.warning(
                    f"Retrying transfer {event.transfer_id} "
                    f"(attempt {event.retry_count + 1})"
                )
                await asyncio.sleep(0.5 * (2**event.retry_count))
                await self._process_transfer(event)
            else:
                logger.error(f"Transfer failed after retries: {event.transfer_id}")

                if self._on_transfer_failure:
                    self._on_transfer_failure(event, e)

        finally:
            # Update metrics
            latency_ms = (time.time() - start_time) * 1000
            self._metrics.total_latency_ms += latency_ms
            self._metrics.last_transfer_time = datetime.now(UTC)

            # Reset status if no longer syncing
            if self._status == BridgeStatus.SYNCING:
                self._status = BridgeStatus.CONNECTED

    async def _auto_sync_loop(self) -> None:
        """Automatic sync loop."""
        while self._running:
            try:
                await asyncio.sleep(self.sync_interval)

                if self._status == BridgeStatus.CONNECTED:
                    logger.info("Starting automatic sync")
                    await self.sync_all()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto-sync loop: {e}")
                self._status = BridgeStatus.ERROR

    def get_transfer_history(self, transfer_id: str) -> TransferEvent | None:
        """Get transfer event from history."""
        return self.transfer_protocol.get_transfer_history(transfer_id)

    def get_transfers_by_status(self, status: TransferStatus) -> list[TransferEvent]:
        """Get all transfers with specific status."""
        return self.transfer_protocol.get_transfers_by_status(status)

    def get_transfers_by_system(self, system_id: str) -> list[TransferEvent]:
        """Get all transfers involving a system."""
        return self.transfer_protocol.get_transfers_by_system(system_id)


async def create_learning_bridge(
    autocog_adapter: AutocogAdapter | None = None,
    strong_adapter: StrongAdapter | None = None,
    enable_auto_sync: bool = True,
) -> LearningBridge:
    """Factory function to create and initialize a learning bridge."""
    bridge = LearningBridge(
        autocog_adapter=autocog_adapter,
        strong_adapter=strong_adapter,
        enable_auto_sync=enable_auto_sync,
    )

    initialized = await bridge.initialize()
    if not initialized:
        raise Exception("Failed to initialize learning bridge")

    return bridge
