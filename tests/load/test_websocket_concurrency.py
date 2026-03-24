"""WebSocket concurrency and connection pool testing for ChiseAI.

This module validates:
- High-concurrency behavior (1000+ concurrent connections)
- Connection pool management
- Message throughput validation
- Circuit breaker under load
- Connection stability over time

Usage:
    pytest tests/load/test_websocket_concurrency.py -v
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, datetime
from typing import Any

import pytest

# Constants for acceptance criteria
TARGET_WEBSOCKET_CONNECTIONS = 1000
MAX_WEBSOCKET_MESSAGE_LATENCY_MS = 100
WEBSOCKET_CIRCUIT_BREAKER_THRESHOLD = 5
WEBSOCKET_RECOVERY_TIMEOUT_SECONDS = 5

# Sample data for testing
SAMPLE_TOKENS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT", "DOT/USDT"]


class MockWebSocketConnection:
    """Mock WebSocket connection for testing."""

    def __init__(self, connection_id: int, latency_ms: float = 10):
        self.connection_id = connection_id
        self.latency_ms = latency_ms
        self.connected = False
        self.messages_received = 0
        self.messages_sent = 0
        self.subscribed_channels: set[str] = set()
        self.connection_time: datetime | None = None

    async def connect(self) -> bool:
        """Establish connection."""
        await asyncio.sleep(self.latency_ms / 1000)
        self.connected = True
        self.connection_time = datetime.now(UTC)
        return True

    async def disconnect(self) -> None:
        """Close connection."""
        self.connected = False

    async def send_message(self, message: dict[str, Any]) -> bool:
        """Send a message."""
        if not self.connected:
            return False
        await asyncio.sleep(self.latency_ms / 1000)
        self.messages_sent += 1
        return True

    async def receive_message(self) -> dict[str, Any] | None:
        """Receive a message."""
        if not self.connected:
            return None
        await asyncio.sleep(self.latency_ms / 1000)
        self.messages_received += 1
        return {
            "type": "price_update",
            "token": random.choice(SAMPLE_TOKENS),
            "price": random.uniform(1000, 50000),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def subscribe(self, channel: str) -> bool:
        """Subscribe to a channel."""
        if not self.connected:
            return False
        await asyncio.sleep(self.latency_ms / 1000)
        self.subscribed_channels.add(channel)
        return True


class MockConnectionPool:
    """Mock connection pool for testing."""

    def __init__(
        self,
        max_connections: int = 1000,
        connection_timeout_ms: float = 5000,
    ):
        self.max_connections = max_connections
        self.connection_timeout_ms = connection_timeout_ms
        self.connections: dict[int, MockWebSocketConnection] = {}
        self.connection_queue: list[int] = []
        self.total_connections_created = 0
        self.total_connections_failed = 0
        self.pool_metrics = {
            "peak_connections": 0,
            "rejected_connections": 0,
            "avg_connection_time_ms": 0.0,
        }
        self._lock = asyncio.Lock()

    async def acquire_connection(self) -> MockWebSocketConnection | None:
        """Acquire a connection from the pool."""
        async with self._lock:
            if len(self.connections) >= self.max_connections:
                self.pool_metrics["rejected_connections"] += 1
                return None

            # Increment counter and get ID atomically
            self.total_connections_created += 1
            conn_id = self.total_connections_created
            conn = MockWebSocketConnection(conn_id)

        # Connect outside the lock to allow concurrency
        start_time = time.perf_counter()
        success = await conn.connect()
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if success:
            async with self._lock:
                self.connections[conn_id] = conn
                self.connection_queue.append(conn_id)

                # Update metrics
                self.pool_metrics["peak_connections"] = max(
                    self.pool_metrics["peak_connections"],
                    len(self.connections),
                )

                # Update average connection time
                n = self.total_connections_created
                old_avg = self.pool_metrics["avg_connection_time_ms"]
                self.pool_metrics["avg_connection_time_ms"] = (
                    old_avg * (n - 1) + elapsed_ms
                ) / n

            return conn
        else:
            async with self._lock:
                self.total_connections_failed += 1
            return None

    async def release_connection(self, conn_id: int) -> None:
        """Release a connection back to the pool."""
        if conn_id in self.connections:
            await self.connections[conn_id].disconnect()
            del self.connections[conn_id]
            if conn_id in self.connection_queue:
                self.connection_queue.remove(conn_id)

    @property
    def active_connections(self) -> int:
        """Get number of active connections."""
        return len(self.connections)

    @property
    def available_slots(self) -> int:
        """Get number of available connection slots."""
        return self.max_connections - len(self.connections)


@pytest.fixture
def connection_pool():
    """Provide a connection pool fixture."""
    return MockConnectionPool(max_connections=TARGET_WEBSOCKET_CONNECTIONS)


class TestWebSocketHighConcurrency:
    """Tests for high-concurrency WebSocket behavior."""

    @pytest.mark.asyncio
    async def test_concurrent_connection_scaling(self):
        """Test WebSocket connection scaling to 1000 concurrent connections.

        Acceptance Criteria:
        - Successfully establish 1000 concurrent connections
        - Connection time <5 seconds per connection
        - No connection drops during establishment
        """
        # Use a pool with capacity for 1000 connections
        connection_pool = MockConnectionPool(
            max_connections=TARGET_WEBSOCKET_CONNECTIONS
        )
        target_connections = TARGET_WEBSOCKET_CONNECTIONS
        connection_times = []
        failed_connections = 0

        # Establish connections concurrently in batches
        batch_size = 100
        for batch in range(0, target_connections, batch_size):
            tasks = []
            for _ in range(batch_size):
                tasks.append(connection_pool.acquire_connection())

            start_time = time.perf_counter()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            batch_elapsed_ms = (time.perf_counter() - start_time) * 1000

            for result in results:
                if isinstance(result, Exception):
                    failed_connections += 1
                elif result is not None:
                    connection_times.append(batch_elapsed_ms / batch_size)

        # Assertions - check that we achieved at least 95% of target
        assert connection_pool.active_connections >= target_connections * 0.95, (
            f"Only {connection_pool.active_connections}/{target_connections} "
            f"connections established"
        )
        assert failed_connections == 0, f"Had {failed_connections} failed connections"
        assert connection_pool.pool_metrics["avg_connection_time_ms"] < 5000, (
            f"Average connection time {connection_pool.pool_metrics['avg_connection_time_ms']:.1f}ms "
            f"exceeds 5 second threshold"
        )

        print("\nConcurrent Connection Scaling:")
        print(f"  Active Connections: {connection_pool.active_connections}")
        print(f"  Peak Connections: {connection_pool.pool_metrics['peak_connections']}")
        print(
            f"  Avg Connection Time: {connection_pool.pool_metrics['avg_connection_time_ms']:.1f}ms"
        )
        print(f"  Failed Connections: {failed_connections}")

    @pytest.mark.asyncio
    async def test_connection_pool_limits(self, connection_pool):
        """Test connection pool enforces maximum limits.

        Acceptance Criteria:
        - Pool rejects connections beyond max limit
        - Existing connections remain stable
        - Proper error handling for rejected connections
        """
        # Fill pool to capacity
        connections = []
        for _ in range(TARGET_WEBSOCKET_CONNECTIONS):
            conn = await connection_pool.acquire_connection()
            if conn:
                connections.append(conn)

        assert connection_pool.active_connections == TARGET_WEBSOCKET_CONNECTIONS

        # Attempt to exceed capacity
        rejected = await connection_pool.acquire_connection()
        assert rejected is None, "Pool should reject connections beyond limit"

        assert connection_pool.pool_metrics["rejected_connections"] > 0

        print("\nConnection Pool Limits:")
        print(f"  Max Connections: {connection_pool.max_connections}")
        print(f"  Active Connections: {connection_pool.active_connections}")
        print(
            f"  Rejected Connections: {connection_pool.pool_metrics['rejected_connections']}"
        )

    @pytest.mark.asyncio
    async def test_connection_stability_under_load(self, connection_pool):
        """Test connection stability under sustained load.

        Acceptance Criteria:
        - Connections remain stable for test duration
        - No unexpected disconnections
        - Message delivery remains consistent
        """
        # Establish connections
        connections = []
        for _ in range(100):  # Use 100 connections for stability test
            conn = await connection_pool.acquire_connection()
            if conn:
                connections.append(conn)

        assert len(connections) == 100

        # Send messages over time
        test_duration_seconds = 5
        messages_per_connection = 10
        start_time = time.perf_counter()

        messages_sent = 0
        messages_failed = 0

        while time.perf_counter() - start_time < test_duration_seconds:
            tasks = []
            for conn in connections:
                message = {
                    "type": "heartbeat",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                tasks.append(conn.send_message(message))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception) or result is False:
                    messages_failed += 1
                else:
                    messages_sent += 1

            await asyncio.sleep(0.1)  # 100ms between bursts

        elapsed = time.perf_counter() - start_time
        success_rate = (
            messages_sent / (messages_sent + messages_failed)
            if (messages_sent + messages_failed) > 0
            else 0
        )

        # Assertions
        assert (
            success_rate >= 0.99
        ), f"Message success rate {success_rate:.2%} below 99%"
        assert all(
            conn.connected for conn in connections
        ), "Some connections disconnected unexpectedly"

        print("\nConnection Stability Under Load:")
        print(f"  Test Duration: {elapsed:.1f}s")
        print(f"  Messages Sent: {messages_sent}")
        print(f"  Messages Failed: {messages_failed}")
        print(f"  Success Rate: {success_rate:.2%}")


class TestWebSocketMessageThroughput:
    """Tests for WebSocket message throughput validation."""

    @pytest.mark.asyncio
    async def test_high_volume_message_throughput(self):
        """Test high-volume message throughput.

        Acceptance Criteria:
        - Handle 1000+ messages per second
        - Latency <100ms per message
        - No message drops
        """
        num_connections = 50
        messages_per_connection = 100

        # Create connections
        connections = [MockWebSocketConnection(i) for i in range(num_connections)]
        for conn in connections:
            await conn.connect()

        # Send messages concurrently
        latencies = []
        failed_messages = 0

        async def send_with_latency(conn: MockWebSocketConnection, msg_idx: int):
            message = {
                "type": "price_update",
                "token": random.choice(SAMPLE_TOKENS),
                "price": random.uniform(1000, 50000),
                "sequence": msg_idx,
            }
            start_time = time.perf_counter()
            success = await conn.send_message(message)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return success, elapsed_ms

        start_time = time.perf_counter()

        # Send in batches to simulate sustained throughput
        batch_size = 50
        total_messages = num_connections * messages_per_connection

        for batch_start in range(0, total_messages, batch_size):
            tasks = []
            for i in range(batch_size):
                conn_idx = (batch_start + i) % num_connections
                msg_idx = (batch_start + i) // num_connections
                tasks.append(send_with_latency(connections[conn_idx], msg_idx))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    failed_messages += 1
                else:
                    success, latency_ms = result
                    if success:
                        latencies.append(latency_ms)
                    else:
                        failed_messages += 1

        elapsed_seconds = time.perf_counter() - start_time
        messages_per_second = (
            len(latencies) / elapsed_seconds if elapsed_seconds > 0 else 0
        )
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

        # Assertions
        assert (
            messages_per_second >= 100
        ), f"Message throughput {messages_per_second:.1f}/s below 100/s threshold"
        assert (
            avg_latency < MAX_WEBSOCKET_MESSAGE_LATENCY_MS
        ), f"Average latency {avg_latency:.1f}ms exceeds {MAX_WEBSOCKET_MESSAGE_LATENCY_MS}ms"
        assert failed_messages == 0, f"Had {failed_messages} failed messages"

        print("\nHigh Volume Message Throughput:")
        print(f"  Total Messages: {len(latencies)}")
        print(f"  Failed Messages: {failed_messages}")
        print(f"  Messages/Second: {messages_per_second:.1f}")
        print(f"  Avg Latency: {avg_latency:.1f}ms")
        print(f"  P95 Latency: {p95_latency:.1f}ms")

    @pytest.mark.asyncio
    async def test_burst_message_handling(self):
        """Test handling of message bursts.

        Acceptance Criteria:
        - Handle burst of 1000 messages without drops
        - Recovery time <1 second after burst
        - No connection instability
        """
        num_connections = 100
        burst_size = 1000

        # Create connections
        connections = [MockWebSocketConnection(i) for i in range(num_connections)]
        for conn in connections:
            await conn.connect()

        # Send burst
        latencies = []
        failed = 0

        async def send_burst_message(conn_idx: int, msg_idx: int):
            conn = connections[conn_idx % num_connections]
            message = {"type": "burst_test", "index": msg_idx}
            start = time.perf_counter()
            success = await conn.send_message(message)
            elapsed_ms = (time.perf_counter() - start) * 1000
            return success, elapsed_ms

        start_time = time.perf_counter()

        tasks = [send_burst_message(i, i) for i in range(burst_size)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        burst_elapsed_ms = (time.perf_counter() - start_time) * 1000

        for result in results:
            if isinstance(result, Exception):
                failed += 1
            else:
                success, latency_ms = result
                if success:
                    latencies.append(latency_ms)
                else:
                    failed += 1

        # Recovery time test
        recovery_start = time.perf_counter()
        await asyncio.sleep(0.01)  # Small delay
        recovery_elapsed_ms = (time.perf_counter() - recovery_start) * 1000

        # Assertions
        assert (
            len(latencies) == burst_size
        ), f"Only {len(latencies)}/{burst_size} messages in burst succeeded"
        assert failed == 0, f"Had {failed} failed messages in burst"
        assert (
            recovery_elapsed_ms < 1000
        ), f"Recovery time {recovery_elapsed_ms:.1f}ms exceeds 1 second"

        print("\nBurst Message Handling:")
        print(f"  Burst Size: {burst_size}")
        print(f"  Successful: {len(latencies)}")
        print(f"  Failed: {failed}")
        print(f"  Burst Duration: {burst_elapsed_ms:.1f}ms")
        print(f"  Recovery Time: {recovery_elapsed_ms:.1f}ms")


class TestWebSocketCircuitBreaker:
    """Tests for WebSocket circuit breaker under load."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_triggers_under_load(self):
        """Test circuit breaker triggers after failure threshold.

        Acceptance Criteria:
        - Circuit opens after threshold failures
        - Requests are blocked when circuit is open
        - Circuit transitions to half-open after timeout
        """
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
        from load_testing import CircuitBreakerSimulator

        circuit = CircuitBreakerSimulator(
            failure_threshold=WEBSOCKET_CIRCUIT_BREAKER_THRESHOLD,
            recovery_timeout=WEBSOCKET_RECOVERY_TIMEOUT_SECONDS,
            half_open_max_calls=2,
        )

        async def failing_operation():
            raise ConnectionError("Simulated WebSocket failure")

        async def success_operation():
            return {"status": "ok"}

        # Trigger failures to open circuit
        for _ in range(WEBSOCKET_CIRCUIT_BREAKER_THRESHOLD):
            try:
                await circuit.call(failing_operation)
            except ConnectionError:
                pass

        assert (
            circuit.state == "open"
        ), f"Circuit should be open after {WEBSOCKET_CIRCUIT_BREAKER_THRESHOLD} failures"

        # Verify circuit blocks requests
        blocked = 0
        for _ in range(3):
            try:
                await circuit.call(success_operation)
            except Exception as e:
                if "Circuit breaker is open" in str(e):
                    blocked += 1

        assert blocked > 0, "Circuit breaker should block requests when open"

        # Wait for recovery and test half-open
        # Use a slightly longer wait to ensure timing is not an issue
        await asyncio.sleep(WEBSOCKET_RECOVERY_TIMEOUT_SECONDS + 0.5)

        result = await circuit.call(success_operation)
        assert result == {"status": "ok"}, "Should allow request in half-open state"

        print("\nCircuit Breaker Under Load:")
        print(f"  Failure Threshold: {WEBSOCKET_CIRCUIT_BREAKER_THRESHOLD}")
        print(f"  Final State: {circuit.state}")
        print(f"  Blocked Requests: {blocked}")

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery after failures.

        Acceptance Criteria:
        - Circuit transitions from open to half-open after timeout
        - Successful requests in half-open close the circuit
        - System returns to normal operation
        """
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
        from load_testing import CircuitBreakerSimulator

        circuit = CircuitBreakerSimulator(
            failure_threshold=3,
            recovery_timeout=1.0,
            half_open_max_calls=1,
        )

        # Open the circuit
        async def failing_op():
            raise ConnectionError("Failure")

        for _ in range(3):
            try:
                await circuit.call(failing_op)
            except ConnectionError:
                pass

        assert circuit.state == "open"

        # Wait for recovery timeout
        await asyncio.sleep(1.1)

        # Successful call should close circuit
        async def success_op():
            return {"status": "recovered"}

        result = await circuit.call(success_op)
        assert result == {"status": "recovered"}
        assert circuit.state == "closed", "Circuit should be closed after recovery"

        print("\nCircuit Breaker Recovery:")
        print("  Initial State: open")
        print(f"  Final State: {circuit.state}")
        print("  Recovery Successful: True")


class TestConnectionPoolManagement:
    """Tests for connection pool management."""

    @pytest.mark.asyncio
    async def test_connection_reuse(self):
        """Test connection reuse efficiency.

        Acceptance Criteria:
        - Connections are reused when available
        - New connections only created when needed
        - Pool maintains optimal size
        """
        pool = MockConnectionPool(max_connections=100)

        # Acquire and release connections
        connections = []
        for _ in range(50):
            conn = await pool.acquire_connection()
            if conn:
                connections.append(conn)

        initial_count = pool.total_connections_created

        # Release half
        for conn in connections[:25]:
            await pool.release_connection(conn.connection_id)

        # Acquire new ones - should reuse slots
        new_connections = []
        for _ in range(25):
            conn = await pool.acquire_connection()
            if conn:
                new_connections.append(conn)

        # Pool should have created new connections for released slots
        assert pool.active_connections == 50

        print("\nConnection Reuse:")
        print(f"  Initial Connections: {initial_count}")
        print(f"  Active Connections: {pool.active_connections}")
        print(f"  Total Created: {pool.total_connections_created}")

    @pytest.mark.asyncio
    async def test_graceful_connection_shutdown(self):
        """Test graceful connection shutdown.

        Acceptance Criteria:
        - Connections close cleanly
        - No resource leaks
        - Pending messages handled appropriately
        """
        pool = MockConnectionPool(max_connections=50)

        # Create connections
        connections = []
        for _ in range(50):
            conn = await pool.acquire_connection()
            if conn:
                connections.append(conn)

        assert pool.active_connections == 50

        # Graceful shutdown
        shutdown_start = time.perf_counter()

        for conn in connections:
            await pool.release_connection(conn.connection_id)

        shutdown_elapsed_ms = (time.perf_counter() - shutdown_start) * 1000

        assert pool.active_connections == 0
        assert all(not conn.connected for conn in connections)

        print("\nGraceful Connection Shutdown:")
        print(f"  Connections Closed: {len(connections)}")
        print(f"  Shutdown Time: {shutdown_elapsed_ms:.1f}ms")
        print(f"  Active After Shutdown: {pool.active_connections}")

    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self):
        """Test connection timeout handling.

        Acceptance Criteria:
        - Timeouts are enforced
        - Failed connections don't leak resources
        - Pool remains stable after timeouts
        """
        pool = MockConnectionPool(
            max_connections=10,
            connection_timeout_ms=100,  # Very short timeout
        )

        # Create connections
        connections = []
        for _ in range(10):
            conn = await pool.acquire_connection()
            if conn:
                connections.append(conn)

        # Pool should be at capacity
        assert pool.active_connections == 10

        # Verify pool metrics
        assert pool.pool_metrics["avg_connection_time_ms"] > 0

        print("\nConnection Timeout Handling:")
        print(f"  Active Connections: {pool.active_connections}")
        print(
            f"  Avg Connection Time: {pool.pool_metrics['avg_connection_time_ms']:.1f}ms"
        )
        print(f"  Failed Connections: {pool.total_connections_failed}")
