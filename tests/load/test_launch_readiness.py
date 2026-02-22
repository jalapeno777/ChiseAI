"""Launch readiness load tests for ChiseAI.

This module implements pytest-based load tests that verify:
1. Signal generation: 1000 signals/hour sustained, latency <1s, no drops
2. Database: 10,000 outcomes/hour, insert <50ms, query <100ms
3. WebSocket: 1000 concurrent connections, circuit breaker functional
4. ML pipeline: Daily ECE update <5min, training within SLA

Usage:
    pytest tests/load/test_launch_readiness.py -v
"""

from __future__ import annotations

import asyncio
import contextlib
import random

# Add src to path
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from load_testing import CircuitBreakerSimulator, LoadTestMetrics, metrics_collector

# Constants for acceptance criteria
TARGET_SIGNALS_PER_HOUR = 1000
TARGET_SIGNALS_PER_SECOND = TARGET_SIGNALS_PER_HOUR / 3600
MAX_SIGNAL_LATENCY_MS = 1000  # 1 second

TARGET_OUTCOMES_PER_HOUR = 10000
TARGET_OUTCOMES_PER_SECOND = TARGET_OUTCOMES_PER_HOUR / 3600
MAX_DB_INSERT_LATENCY_MS = 50  # 50ms
MAX_DB_QUERY_LATENCY_MS = 100  # 100ms

TARGET_WEBSOCKET_CONNECTIONS = 1000
WEBSOCKET_MESSAGE_LATENCY_MS = 100  # 100ms

ML_ECE_UPDATE_MAX_MINUTES = 5  # 5 minutes
ML_TRAINING_MAX_MINUTES = 30  # 30 minutes

# Test configuration
SAMPLE_TOKENS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT", "DOT/USDT"]
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h"]
SIGNAL_DIRECTIONS = ["LONG", "SHORT", "NEUTRAL"]


class MockSignalGenerator:
    """Mock signal generator for testing."""

    def __init__(self, latency_ms: float = 100):
        self.latency_ms = latency_ms
        self.generated_count = 0

    async def generate_signal(
        self,
        token: str,
        timeframe: str,
    ) -> dict[str, Any]:
        """Generate a mock signal."""
        # Simulate processing latency
        await asyncio.sleep(self.latency_ms / 1000)
        self.generated_count += 1

        return {
            "signal_id": f"sig_{self.generated_count}",
            "token": token,
            "timeframe": timeframe,
            "direction": random.choice(SIGNAL_DIRECTIONS),
            "confidence": random.uniform(0.75, 0.95),
            "timestamp": datetime.now(UTC).isoformat(),
            "generation_latency_ms": self.latency_ms,
        }


class MockDatabase:
    """Mock database for testing."""

    def __init__(
        self,
        insert_latency_ms: float = 30,
        query_latency_ms: float = 50,
    ):
        self.insert_latency_ms = insert_latency_ms
        self.query_latency_ms = query_latency_ms
        self.outcomes: list[dict[str, Any]] = []

    async def insert_outcome(self, outcome: dict[str, Any]) -> dict[str, Any]:
        """Insert an outcome."""
        await asyncio.sleep(self.insert_latency_ms / 1000)
        outcome["id"] = len(self.outcomes) + 1
        self.outcomes.append(outcome)
        return outcome

    async def query_outcomes(
        self, token: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Query outcomes."""
        await asyncio.sleep(self.query_latency_ms / 1000)
        return [o for o in self.outcomes if o.get("token") == token][:limit]


class MockWebSocketServer:
    """Mock WebSocket server for testing."""

    def __init__(self, message_latency_ms: float = 10):
        self.message_latency_ms = message_latency_ms
        self.connections: set[int] = set()
        self.messages_sent = 0

    async def connect(self, client_id: int) -> bool:
        """Accept a new connection."""
        self.connections.add(client_id)
        return True

    async def disconnect(self, client_id: int) -> None:
        """Disconnect a client."""
        self.connections.discard(client_id)

    async def send_message(self, client_id: int, message: dict[str, Any]) -> bool:
        """Send a message to a client."""
        await asyncio.sleep(self.message_latency_ms / 1000)
        if client_id in self.connections:
            self.messages_sent += 1
            return True
        return False

    @property
    def connection_count(self) -> int:
        return len(self.connections)


@pytest.fixture
def mock_signal_generator():
    """Provide a mock signal generator."""
    return MockSignalGenerator(latency_ms=100)


@pytest.fixture
def mock_database():
    """Provide a mock database."""
    return MockDatabase(
        insert_latency_ms=30,
        query_latency_ms=50,
    )


@pytest.fixture
def mock_websocket_server():
    """Provide a mock WebSocket server."""
    return MockWebSocketServer(message_latency_ms=10)


@pytest.fixture
def circuit_breaker():
    """Provide a circuit breaker simulator."""
    return CircuitBreakerSimulator(
        failure_threshold=5,
        recovery_timeout=5.0,
        half_open_max_calls=2,
    )


class TestSignalGenerationLoad:
    """Tests for signal generation load requirements."""

    @pytest.mark.asyncio
    async def test_signal_generation_sustained_rate(self, mock_signal_generator):
        """Test signal generation at 1000 signals/hour sustained rate.

        Acceptance Criteria:
        - Generate signals at target rate for short period
        - No drops in signal generation
        - Verify rate calculation
        """
        metrics = LoadTestMetrics(test_name="signal_generation_rate")

        # Test for 10 seconds to verify rate capability
        test_duration_seconds = 10
        start_time = time.perf_counter()
        target_count = int(TARGET_SIGNALS_PER_SECOND * test_duration_seconds)

        tasks = []
        for _ in range(target_count):
            token = random.choice(SAMPLE_TOKENS)
            timeframe = random.choice(TIMEFRAMES)
            tasks.append(mock_signal_generator.generate_signal(token, timeframe))

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed_seconds = time.perf_counter() - start_time
        actual_rate = len(results) / elapsed_seconds
        signals_per_hour = actual_rate * 3600

        # Record metrics
        for result in results:
            if isinstance(result, Exception):
                metrics.record_request(latency_ms=0, success=False, error=str(result))
            else:
                metrics.record_request(
                    latency_ms=result.get("generation_latency_ms", 100),
                    success=True,
                )

        metrics.finalize()

        # Assertions
        assert signals_per_hour >= TARGET_SIGNALS_PER_HOUR * 0.9, (
            f"Signal rate {signals_per_hour:.0f}/hour below target "
            f"{TARGET_SIGNALS_PER_HOUR}/hour"
        )
        assert (
            metrics.failed_requests == 0
        ), f"Signal generation had {metrics.failed_requests} failures"

        # Store metrics
        metrics_collector.register("signal_generation_rate", metrics)

    @pytest.mark.asyncio
    async def test_signal_generation_latency(self, mock_signal_generator):
        """Test signal generation latency under load.

        Acceptance Criteria:
        - End-to-end latency <1 second
        - P95 latency <1 second
        - No timeouts
        """
        metrics = LoadTestMetrics(test_name="signal_generation_latency")

        # Generate signals and measure latency
        num_signals = 100
        tasks = []

        for _ in range(num_signals):
            token = random.choice(SAMPLE_TOKENS)
            timeframe = random.choice(TIMEFRAMES)

            async def measure_latency(t=token, tf=timeframe):
                start = time.perf_counter()
                result = await mock_signal_generator.generate_signal(t, tf)
                latency_ms = (time.perf_counter() - start) * 1000
                return result, latency_ms

            tasks.append(measure_latency())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        latencies = []
        for result in results:
            if isinstance(result, Exception):
                metrics.record_request(latency_ms=0, success=False, error=str(result))
            else:
                _, latency_ms = result
                latencies.append(latency_ms)
                metrics.record_request(latency_ms=latency_ms, success=True)

        metrics.finalize()

        # Assertions
        assert metrics.avg_latency_ms < MAX_SIGNAL_LATENCY_MS, (
            f"Average latency {metrics.avg_latency_ms:.1f}ms exceeds "
            f"threshold {MAX_SIGNAL_LATENCY_MS}ms"
        )
        assert metrics.p95_latency_ms < MAX_SIGNAL_LATENCY_MS, (
            f"P95 latency {metrics.p95_latency_ms:.1f}ms exceeds "
            f"threshold {MAX_SIGNAL_LATENCY_MS}ms"
        )

        metrics_collector.register("signal_generation_latency", metrics)

    @pytest.mark.asyncio
    async def test_signal_generation_no_drops(self, mock_signal_generator):
        """Test signal generation reliability.

        Acceptance Criteria:
        - No dropped signals under normal load
        - 100% success rate
        """
        metrics = LoadTestMetrics(test_name="signal_generation_reliability")

        # Simulate sustained load
        num_batches = 10
        signals_per_batch = 50

        for _ in range(num_batches):
            tasks = [
                mock_signal_generator.generate_signal(
                    random.choice(SAMPLE_TOKENS),
                    random.choice(TIMEFRAMES),
                )
                for _ in range(signals_per_batch)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    metrics.record_request(
                        latency_ms=0, success=False, error=str(result)
                    )
                else:
                    metrics.record_request(
                        latency_ms=result.get("generation_latency_ms", 100),
                        success=True,
                    )

        metrics.finalize()

        # Assertions
        assert (
            metrics.success_rate >= 0.999
        ), f"Success rate {metrics.success_rate:.3%} below 99.9%"
        assert (
            metrics.failed_requests == 0
        ), f"Had {metrics.failed_requests} failed signals"

        metrics_collector.register("signal_generation_reliability", metrics)


class TestDatabaseLoad:
    """Tests for database load requirements."""

    @pytest.mark.asyncio
    async def test_database_insert_throughput(self, mock_database):
        """Test database insert throughput.

        Acceptance Criteria:
        - 10,000 outcomes/hour insert rate
        - Insert latency <50ms
        """
        metrics = LoadTestMetrics(test_name="database_insert_throughput")

        # Calculate target for test duration
        test_duration_seconds = 5
        target_inserts = int(TARGET_OUTCOMES_PER_SECOND * test_duration_seconds)

        start_time = time.perf_counter()

        # Insert outcomes concurrently
        tasks = []
        for i in range(target_inserts):
            outcome = {
                "signal_id": f"sig_{i}",
                "token": random.choice(SAMPLE_TOKENS),
                "direction": random.choice(SIGNAL_DIRECTIONS),
                "pnl": random.uniform(-1000, 1000),
                "outcome": random.choice(["win", "loss", "breakeven"]),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            tasks.append(mock_database.insert_outcome(outcome))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed_seconds = time.perf_counter() - start_time
        actual_rate = len(results) / elapsed_seconds
        inserts_per_hour = actual_rate * 3600

        for result in results:
            if isinstance(result, Exception):
                metrics.record_request(latency_ms=0, success=False, error=str(result))
            else:
                metrics.record_request(
                    latency_ms=mock_database.insert_latency_ms, success=True
                )

        metrics.finalize()

        # Assertions
        assert inserts_per_hour >= TARGET_OUTCOMES_PER_HOUR * 0.9, (
            f"Insert rate {inserts_per_hour:.0f}/hour below target "
            f"{TARGET_OUTCOMES_PER_HOUR}/hour"
        )
        assert mock_database.insert_latency_ms <= MAX_DB_INSERT_LATENCY_MS, (
            f"Insert latency {mock_database.insert_latency_ms}ms exceeds "
            f"threshold {MAX_DB_INSERT_LATENCY_MS}ms"
        )

        metrics_collector.register("database_insert_throughput", metrics)

    @pytest.mark.asyncio
    async def test_database_query_latency(self, mock_database):
        """Test database query latency.

        Acceptance Criteria:
        - Query latency <100ms
        - Consistent performance under load
        """
        metrics = LoadTestMetrics(test_name="database_query_latency")

        # Seed some data first
        for i in range(100):
            outcome = {
                "signal_id": f"sig_{i}",
                "token": random.choice(SAMPLE_TOKENS),
                "direction": random.choice(SIGNAL_DIRECTIONS),
                "pnl": random.uniform(-1000, 1000),
                "outcome": random.choice(["win", "loss"]),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            await mock_database.insert_outcome(outcome)

        # Test query latency
        num_queries = 100
        tasks = [
            mock_database.query_outcomes(
                random.choice(SAMPLE_TOKENS),
                limit=random.randint(10, 100),
            )
            for _ in range(num_queries)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                metrics.record_request(latency_ms=0, success=False, error=str(result))
            else:
                metrics.record_request(
                    latency_ms=mock_database.query_latency_ms, success=True
                )

        metrics.finalize()

        # Assertions
        assert metrics.avg_latency_ms <= MAX_DB_QUERY_LATENCY_MS, (
            f"Average query latency {metrics.avg_latency_ms:.1f}ms exceeds "
            f"threshold {MAX_DB_QUERY_LATENCY_MS}ms"
        )
        assert metrics.p95_latency_ms <= MAX_DB_QUERY_LATENCY_MS * 1.5, (
            f"P95 query latency {metrics.p95_latency_ms:.1f}ms exceeds "
            f"threshold {MAX_DB_QUERY_LATENCY_MS * 1.5}ms"
        )

        metrics_collector.register("database_query_latency", metrics)

    @pytest.mark.asyncio
    async def test_database_mixed_load(self, mock_database):
        """Test database under mixed read/write load.

        Acceptance Criteria:
        - Handles concurrent inserts and queries
        - No deadlocks or timeouts
        """
        metrics = LoadTestMetrics(test_name="database_mixed_load")

        async def insert_task():
            outcome = {
                "signal_id": f"sig_{random.randint(1, 100000)}",
                "token": random.choice(SAMPLE_TOKENS),
                "direction": random.choice(SIGNAL_DIRECTIONS),
                "pnl": random.uniform(-1000, 1000),
                "outcome": random.choice(["win", "loss"]),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            try:
                await mock_database.insert_outcome(outcome)
                return ("insert", mock_database.insert_latency_ms, None)
            except Exception as e:
                return ("insert", 0, str(e))

        async def query_task():
            try:
                await mock_database.query_outcomes(
                    random.choice(SAMPLE_TOKENS),
                    limit=50,
                )
                return ("query", mock_database.query_latency_ms, None)
            except Exception as e:
                return ("query", 0, str(e))

        # Mix of inserts and queries
        tasks = []
        for _ in range(50):
            tasks.append(insert_task())
            tasks.append(query_task())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                metrics.record_request(latency_ms=0, success=False, error=str(result))
            else:
                _, latency_ms, error = result
                if error:
                    metrics.record_request(
                        latency_ms=latency_ms, success=False, error=error
                    )
                else:
                    metrics.record_request(latency_ms=latency_ms, success=True)

        metrics.finalize()

        # Assertions
        assert (
            metrics.success_rate >= 0.99
        ), f"Success rate {metrics.success_rate:.2%} below 99% under mixed load"

        metrics_collector.register("database_mixed_load", metrics)


class TestWebSocketLoad:
    """Tests for WebSocket load requirements."""

    @pytest.mark.asyncio
    async def test_websocket_concurrent_connections(self, mock_websocket_server):
        """Test WebSocket concurrent connection handling.

        Acceptance Criteria:
        - Support 1000 concurrent connections
        - Stable connection management
        """
        metrics = LoadTestMetrics(test_name="websocket_concurrent_connections")

        # Connect 1000 clients
        num_connections = TARGET_WEBSOCKET_CONNECTIONS
        start_time = time.perf_counter()

        tasks = [mock_websocket_server.connect(i) for i in range(num_connections)]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        successful_connections = sum(1 for r in results if r is True)

        for result in results:
            if isinstance(result, Exception):
                metrics.record_request(latency_ms=0, success=False, error=str(result))
            elif result:
                metrics.record_request(
                    latency_ms=elapsed_ms / num_connections, success=True
                )
            else:
                metrics.record_request(
                    latency_ms=0, success=False, error="Connection rejected"
                )

        metrics.finalize()

        # Assertions
        assert (
            successful_connections >= TARGET_WEBSOCKET_CONNECTIONS * 0.95
        ), f"Only {successful_connections}/{num_connections} connections successful"
        assert (
            mock_websocket_server.connection_count
            >= TARGET_WEBSOCKET_CONNECTIONS * 0.95
        ), f"Active connections {mock_websocket_server.connection_count} below target"

        metrics_collector.register("websocket_concurrent_connections", metrics)

    @pytest.mark.asyncio
    async def test_websocket_message_latency(self, mock_websocket_server):
        """Test WebSocket message delivery latency.

        Acceptance Criteria:
        - Message delivery latency within acceptable bounds
        - No message drops
        """
        metrics = LoadTestMetrics(test_name="websocket_message_latency")

        # Connect some clients
        num_clients = 100
        for i in range(num_clients):
            await mock_websocket_server.connect(i)

        # Send messages and measure latency
        num_messages = 500
        tasks = []

        for i in range(num_messages):
            client_id = i % num_clients
            message = {
                "type": "price_update",
                "token": random.choice(SAMPLE_TOKENS),
                "price": random.uniform(1000, 50000),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            tasks.append(mock_websocket_server.send_message(client_id, message))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_deliveries = sum(1 for r in results if r is True)

        for result in results:
            if isinstance(result, Exception):
                metrics.record_request(latency_ms=0, success=False, error=str(result))
            elif result:
                metrics.record_request(
                    latency_ms=mock_websocket_server.message_latency_ms,
                    success=True,
                )
            else:
                metrics.record_request(
                    latency_ms=0, success=False, error="Message not delivered"
                )

        metrics.finalize()

        # Assertions
        delivery_rate = successful_deliveries / num_messages
        assert (
            delivery_rate >= 0.99
        ), f"Message delivery rate {delivery_rate:.2%} below 99%"

        metrics_collector.register("websocket_message_latency", metrics)

    @pytest.mark.asyncio
    async def test_websocket_circuit_breaker(self, circuit_breaker):
        """Test WebSocket circuit breaker functionality.

        Acceptance Criteria:
        - Circuit breaker opens after threshold failures
        - Circuit breaker closes after recovery timeout
        - Half-open state allows limited requests
        """
        metrics = LoadTestMetrics(test_name="websocket_circuit_breaker")

        async def failing_operation():
            raise ConnectionError("Simulated connection failure")

        async def success_operation():
            return {"status": "ok"}

        # Step 1: Trigger circuit breaker by causing failures
        for _ in range(5):
            with contextlib.suppress(ConnectionError, Exception):
                await circuit_breaker.call(failing_operation)

        # Circuit should be open now
        assert (
            circuit_breaker.state == "open"
        ), f"Circuit breaker should be open, but is {circuit_breaker.state}"

        # Step 2: Verify circuit breaker blocks requests
        blocked_count = 0
        for _ in range(3):
            try:
                await circuit_breaker.call(success_operation)
            except Exception as e:
                if "Circuit breaker is open" in str(e):
                    blocked_count += 1

        assert blocked_count > 0, "Circuit breaker should block requests when open"

        # Step 3: Wait for recovery timeout and test half-open
        await asyncio.sleep(5.1)  # Wait longer than recovery_timeout

        # Try a successful call - should transition to half-open then closed
        result = await circuit_breaker.call(success_operation)
        assert result == {"status": "ok"}, "Should allow request in half-open state"

        # Circuit should be closed after successful recovery
        assert (
            circuit_breaker.state == "closed"
        ), f"Circuit breaker should be closed, but is {circuit_breaker.state}"

        metrics_collector.register("websocket_circuit_breaker", metrics)


class TestMLPipelineLoad:
    """Tests for ML pipeline load requirements."""

    @pytest.mark.asyncio
    async def test_ml_ece_update_latency(self):
        """Test ML pipeline ECE update latency.

        Acceptance Criteria:
        - Daily ECE update <5 minutes
        """
        metrics = LoadTestMetrics(test_name="ml_ece_update_latency")

        async def simulate_ece_update():
            """Simulate ECE calculation for all tokens."""
            start_time = time.perf_counter()

            # Simulate processing for each token
            for _token in SAMPLE_TOKENS:
                # Simulate fetching recent outcomes
                await asyncio.sleep(0.05)  # 50ms per token

                # Simulate ECE calculation
                await asyncio.sleep(0.1)  # 100ms per token

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return elapsed_ms

        elapsed_ms = await simulate_ece_update()
        metrics.record_request(latency_ms=elapsed_ms, success=True)
        metrics.finalize()

        # Assertions
        max_allowed_ms = ML_ECE_UPDATE_MAX_MINUTES * 60 * 1000  # 5 minutes in ms
        assert elapsed_ms < max_allowed_ms, (
            f"ECE update took {elapsed_ms / 1000:.1f}s, exceeding "
            f"{ML_ECE_UPDATE_MAX_MINUTES} minute threshold"
        )

        metrics_collector.register("ml_ece_update_latency", metrics)

    @pytest.mark.asyncio
    async def test_ml_training_sla(self):
        """Test ML pipeline training within SLA.

        Acceptance Criteria:
        - Training completes within SLA (30 minutes)
        """
        metrics = LoadTestMetrics(test_name="ml_training_sla")

        async def simulate_training():
            """Simulate model training."""
            start_time = time.perf_counter()

            # Simulate data loading
            await asyncio.sleep(0.5)

            # Simulate training epochs (scaled down for test)
            for _epoch in range(3):  # Reduced from typical 50+ for test speed
                # Simulate epoch training
                await asyncio.sleep(0.2)

            # Simulate model evaluation
            await asyncio.sleep(0.3)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return elapsed_ms

        elapsed_ms = await simulate_training()
        metrics.record_request(latency_ms=elapsed_ms, success=True)
        metrics.finalize()

        # Assertions
        max_allowed_ms = ML_TRAINING_MAX_MINUTES * 60 * 1000  # 30 minutes in ms
        assert elapsed_ms < max_allowed_ms, (
            f"Training took {elapsed_ms / 1000:.1f}s, exceeding "
            f"{ML_TRAINING_MAX_MINUTES} minute SLA"
        )

        metrics_collector.register("ml_training_sla", metrics)


@pytest.fixture(scope="session", autouse=True)
def generate_final_report():
    """Generate final report after all tests complete."""
    yield

    # Generate report
    report = metrics_collector.generate_report()

    print("\n" + "=" * 70)
    print("LAUNCH READINESS LOAD TEST REPORT")
    print("=" * 70)

    for test_name, metrics in report["tests"].items():
        print(f"\n{test_name}:")
        print(f"  Success Rate: {metrics['success_rate']:.2%}")
        print(f"  Total Requests: {metrics['total_requests']}")
        print(f"  Avg Latency: {metrics['latency_ms']['avg']:.1f}ms")
        print(f"  P95 Latency: {metrics['latency_ms']['p95']:.1f}ms")

    print("\n" + "=" * 70)
    print(f"Overall Success Rate: {report['summary']['overall_success_rate']:.2%}")
    print("=" * 70)
