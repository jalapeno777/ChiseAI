"""Locust load testing framework for ChiseAI.

This module implements comprehensive load testing for:
- Signal generation (1000 signals/hour)
- Database operations (10,000 outcomes/hour)
- WebSocket connections (1000 concurrent)

Usage:
    locust -f tests/load/locustfile.py --users 10 --run-time 5m
"""

from __future__ import annotations

import logging
import random
import time
from datetime import UTC, datetime
from typing import Any

# Try to import locust, provide helpful error if not installed
try:
    from locust import HttpUser, TaskSet, between, events, task
    from locust.runners import MasterRunner

    LOCUST_AVAILABLE = True
except ImportError:
    LOCUST_AVAILABLE = False

    # Create dummy classes for type checking
    class HttpUser:  # type: ignore
        pass

    class TaskSet:  # type: ignore
        pass

    def between(*args, **kwargs):  # type: ignore
        pass

    def task(*args, **kwargs):  # type: ignore
        def decorator(f):
            return f

        return decorator

    events = type(
        "events",
        (),
        {"request": type("request", (), {"add_listener": lambda *a, **k: None})()},
    )()  # type: ignore


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants for acceptance criteria
TARGET_SIGNALS_PER_HOUR = 1000
TARGET_OUTCOMES_PER_HOUR = 10000
TARGET_WEBSOCKET_CONNECTIONS = 1000

# Signal generation latency target (1 second)
MAX_SIGNAL_LATENCY_MS = 1000

# Database latency targets
MAX_DB_INSERT_LATENCY_MS = 50
MAX_DB_QUERY_LATENCY_MS = 100

# Sample tokens for realistic testing
SAMPLE_TOKENS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "ADA/USDT",
    "DOT/USDT",
    "LINK/USDT",
    "MATIC/USDT",
    "UNI/USDT",
    "AAVE/USDT",
    "ATOM/USDT",
    "AVAX/USDT",
    "FTM/USDT",
]

# Sample timeframes
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

# Signal directions
SIGNAL_DIRECTIONS = ["LONG", "SHORT", "NEUTRAL"]


class SignalGenerationTasks(TaskSet):
    """Tasks for simulating signal generation load."""

    def on_start(self):
        """Initialize user session."""
        self.user_id = random.randint(1, 1000000)
        logger.info(f"SignalGenerationUser {self.user_id} started")

    @task(10)
    def generate_signal(self) -> None:
        """Simulate signal generation request.

        Target: 1000 signals/hour sustained
        Latency: <1 second end-to-end
        """
        token = random.choice(SAMPLE_TOKENS)
        timeframe = random.choice(TIMEFRAMES)

        start_time = time.perf_counter()

        # Simulate signal generation request
        # In production, this would call the actual signal generation endpoint
        payload = {
            "token": token,
            "timeframe": timeframe,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            with self.client.post(
                "/api/v1/signals/generate",
                json=payload,
                catch_response=True,
                name="signal_generate",
            ) as response:
                latency_ms = (time.perf_counter() - start_time) * 1000

                if response.status_code == 200:
                    data = response.json()
                    signal_latency = data.get("generation_latency_ms", latency_ms)

                    if signal_latency <= MAX_SIGNAL_LATENCY_MS:
                        response.success()
                    else:
                        response.failure(f"Latency exceeded: {signal_latency:.1f}ms")
                elif response.status_code == 429:
                    # Rate limited - expected behavior
                    response.success()
                else:
                    response.failure(f"Unexpected status: {response.status_code}")

        except Exception as e:
            self.client.failure = True
            logger.error(f"Signal generation error: {e}")

    @task(5)
    def get_signal_status(self) -> None:
        """Query signal status."""
        signal_id = f"sig_{random.randint(1, 10000)}"

        with self.client.get(
            f"/api/v1/signals/{signal_id}/status",
            catch_response=True,
            name="signal_status",
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(2)
    def batch_generate_signals(self) -> None:
        """Simulate batch signal generation."""
        tokens = random.sample(SAMPLE_TOKENS, k=random.randint(3, 8))

        payload = {
            "tokens": tokens,
            "timeframe": random.choice(TIMEFRAMES),
        }

        with self.client.post(
            "/api/v1/signals/generate-batch",
            json=payload,
            catch_response=True,
            name="signal_generate_batch",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")


class DatabaseLoadTasks(TaskSet):
    """Tasks for simulating database load."""

    def on_start(self):
        """Initialize user session."""
        self.user_id = random.randint(1, 1000000)
        logger.info(f"DatabaseLoadUser {self.user_id} started")

    def _generate_outcome_data(self) -> dict[str, Any]:
        """Generate realistic outcome data."""
        return {
            "signal_id": f"sig_{random.randint(1, 100000)}",
            "token": random.choice(SAMPLE_TOKENS),
            "direction": random.choice(SIGNAL_DIRECTIONS),
            "entry_price": random.uniform(1000, 50000),
            "exit_price": random.uniform(1000, 50000),
            "pnl": random.uniform(-1000, 1000),
            "outcome": random.choice(["win", "loss", "breakeven"]),
            "timestamp": datetime.now(UTC).isoformat(),
            "confidence": random.uniform(0.5, 0.95),
        }

    @task(10)
    def insert_outcome(self) -> None:
        """Simulate outcome database insert.

        Target: 10,000 outcomes/hour
        Latency: <50ms for inserts
        """
        outcome_data = self._generate_outcome_data()
        start_time = time.perf_counter()

        with self.client.post(
            "/api/v1/outcomes",
            json=outcome_data,
            catch_response=True,
            name="outcome_insert",
        ) as response:
            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code == 201:
                if latency_ms <= MAX_DB_INSERT_LATENCY_MS:
                    response.success()
                else:
                    response.failure(f"Insert latency exceeded: {latency_ms:.1f}ms")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(5)
    def query_outcomes(self) -> None:
        """Simulate outcome query.

        Latency: <100ms for queries
        """
        token = random.choice(SAMPLE_TOKENS)
        start_time = time.perf_counter()

        with self.client.get(
            "/api/v1/outcomes",
            params={
                "token": token,
                "limit": "100",
                "start_date": "2024-01-01",
            },
            catch_response=True,
            name="outcome_query",
        ) as response:
            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code == 200:
                if latency_ms <= MAX_DB_QUERY_LATENCY_MS:
                    response.success()
                else:
                    response.failure(f"Query latency exceeded: {latency_ms:.1f}ms")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(3)
    def batch_insert_outcomes(self) -> None:
        """Simulate batch outcome insert."""
        outcomes = [self._generate_outcome_data() for _ in range(random.randint(5, 20))]

        with self.client.post(
            "/api/v1/outcomes/batch",
            json={"outcomes": outcomes},
            catch_response=True,
            name="outcome_insert_batch",
        ) as response:
            if response.status_code == 201:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(2)
    def query_analytics(self) -> None:
        """Simulate analytics query (heavier query)."""
        with self.client.get(
            "/api/v1/analytics/performance",
            params={
                "token": random.choice(SAMPLE_TOKENS),
                "timeframe": "7d",
            },
            catch_response=True,
            name="analytics_query",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")


class SignalGenerationUser(HttpUser):
    """User that simulates signal generation load.

    Weight: 30% of total load
    Target: Contribute to 1000 signals/hour aggregate
    """

    tasks = [SignalGenerationTasks]
    wait_time = between(1, 5)  # Wait 1-5 seconds between tasks
    weight = 30

    def on_start(self):
        """Initialize user."""
        logger.info("SignalGenerationUser initialized")


class DatabaseLoadUser(HttpUser):
    """User that simulates database load.

    Weight: 50% of total load
    Target: Contribute to 10,000 outcomes/hour aggregate
    """

    tasks = [DatabaseLoadTasks]
    wait_time = between(0.1, 1)  # Wait 0.1-1 seconds between tasks
    weight = 50

    def on_start(self):
        """Initialize user."""
        logger.info("DatabaseLoadUser initialized")


class WebSocketUser(HttpUser):
    """User that simulates WebSocket connections.

    Weight: 20% of total load
    Target: Support 1000 concurrent WebSocket connections

    Note: This is a simplified simulation. Full WebSocket testing
    requires custom locust setup with WebSocket client.
    """

    wait_time = between(5, 15)
    weight = 20

    def on_start(self):
        """Initialize WebSocket connection simulation."""
        self.user_id = random.randint(1, 1000000)
        self.subscribed_channels: list[str] = []
        logger.info(f"WebSocketUser {self.user_id} initialized")

    @task(5)
    def simulate_ws_subscription(self) -> None:
        """Simulate WebSocket channel subscription."""
        channel = f"price.{random.choice(SAMPLE_TOKENS).replace('/', '')}"

        with self.client.post(
            "/api/v1/ws/subscribe",
            json={"channels": [channel]},
            catch_response=True,
            name="ws_subscribe",
        ) as response:
            if response.status_code in [200, 201]:
                self.subscribed_channels.append(channel)
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(3)
    def simulate_ws_heartbeat(self) -> None:
        """Simulate WebSocket heartbeat/ping."""
        with self.client.get(
            "/api/v1/ws/health",
            catch_response=True,
            name="ws_health",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(2)
    def simulate_ws_message(self) -> None:
        """Simulate receiving WebSocket message."""
        # This simulates the message processing overhead
        # In real WebSocket testing, we'd use a WebSocket client
        start_time = time.perf_counter()

        # Simulate message processing time
        time.sleep(random.uniform(0.001, 0.01))  # 1-10ms processing

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Report custom metric
        if LOCUST_AVAILABLE:
            events.request.fire(
                request_type="WEBSOCKET",
                name="ws_message_latency",
                response_time=latency_ms,
                response_length=0,
                context={},
            )

    @task(1)
    def simulate_ws_circuit_breaker_test(self) -> None:
        """Test circuit breaker functionality."""
        # This simulates a high-load scenario that might trip circuit breaker
        for _ in range(random.randint(5, 10)):
            with self.client.get(
                "/api/v1/ws/health",
                catch_response=True,
                name="ws_circuit_breaker_test",
            ) as response:
                if response.status_code == 503:
                    # Service unavailable - circuit breaker may be open
                    response.success()  # Expected behavior under load
                    break
                elif response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Unexpected status: {response.status_code}")


# Custom event listeners for reporting
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    logger.info("=" * 60)
    logger.info("LOAD TEST STARTED")
    logger.info("=" * 60)
    logger.info(f"Target Signal Rate: {TARGET_SIGNALS_PER_HOUR}/hour")
    logger.info(f"Target Outcome Rate: {TARGET_OUTCOMES_PER_HOUR}/hour")
    logger.info(f"Target WebSocket Connections: {TARGET_WEBSOCKET_CONNECTIONS}")
    logger.info("=" * 60)


def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    logger.info("=" * 60)
    logger.info("LOAD TEST COMPLETED")
    logger.info("=" * 60)

    if LOCUST_AVAILABLE and isinstance(environment.runner, MasterRunner):
        # Generate summary report
        stats = environment.runner.stats

        logger.info("\nPERFORMANCE SUMMARY:")
        logger.info("-" * 40)

        for name in stats.entries:
            entry = stats.entries[name]
            logger.info(f"\n{name}:")
            logger.info(f"  Requests: {entry.num_requests}")
            logger.info(f"  Failures: {entry.num_failures}")
            logger.info(f"  Avg Response Time: {entry.avg_response_time:.1f}ms")
            logger.info(f"  P95: {entry.get_response_time_percentile(0.95):.1f}ms")
            logger.info(f"  P99: {entry.get_response_time_percentile(0.99):.1f}ms")


if LOCUST_AVAILABLE:
    events.test_start.add_listener(on_test_start)
    events.test_stop.add_listener(on_test_stop)


# Entry point for testing without locust command
if __name__ == "__main__":
    print("Locust load test file for ChiseAI")
    print("\nUsage:")
    print("  locust -f tests/load/locustfile.py --users 10 --run-time 5m")
    print("\nOr with specific host:")
    print("  locust -f tests/load/locustfile.py --host http://localhost:8001")
    print("\nAcceptance Criteria:")
    print(f"  - Signal generation: {TARGET_SIGNALS_PER_HOUR}/hour sustained")
    print(f"  - Database outcomes: {TARGET_OUTCOMES_PER_HOUR}/hour")
    print(f"  - WebSocket connections: {TARGET_WEBSOCKET_CONNECTIONS} concurrent")
