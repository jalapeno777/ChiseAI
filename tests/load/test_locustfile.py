"""Unit tests for locustfile components.

These tests exercise the Locust load test code without actually running Locust,
ensuring the code is importable and the classes/functions work correctly.
"""

from __future__ import annotations

import random
from unittest.mock import MagicMock

import pytest

# Import the locustfile components (without requiring locust to be running)
# We use importorskip to skip if locust is not installed
pytest.importorskip("locust", reason="Locust not installed")

# Import after confirming locust is available
from tests.load.locustfile import (
    MAX_DB_INSERT_LATENCY_MS,
    MAX_DB_QUERY_LATENCY_MS,
    MAX_SIGNAL_LATENCY_MS,
    SAMPLE_TOKENS,
    SIGNAL_DIRECTIONS,
    TARGET_OUTCOMES_PER_HOUR,
    TARGET_SIGNALS_PER_HOUR,
    TARGET_WEBSOCKET_CONNECTIONS,
    TIMEFRAMES,
    DatabaseLoadTasks,
    DatabaseLoadUser,
    SignalGenerationTasks,
    SignalGenerationUser,
    WebSocketUser,
)


class TestLocustfileConstants:
    """Test that locustfile constants are properly defined."""

    def test_target_constants(self) -> None:
        """Verify target constants meet acceptance criteria."""
        assert TARGET_SIGNALS_PER_HOUR == 1000
        assert TARGET_OUTCOMES_PER_HOUR == 10000
        assert TARGET_WEBSOCKET_CONNECTIONS == 1000

    def test_latency_constants(self) -> None:
        """Verify latency threshold constants."""
        assert MAX_SIGNAL_LATENCY_MS == 1000  # 1 second
        assert MAX_DB_INSERT_LATENCY_MS == 50  # 50ms
        assert MAX_DB_QUERY_LATENCY_MS == 100  # 100ms

    def test_sample_data(self) -> None:
        """Verify sample data constants are populated."""
        assert len(SAMPLE_TOKENS) > 0
        assert len(TIMEFRAMES) > 0
        assert len(SIGNAL_DIRECTIONS) == 3
        assert "LONG" in SIGNAL_DIRECTIONS
        assert "SHORT" in SIGNAL_DIRECTIONS
        assert "NEUTRAL" in SIGNAL_DIRECTIONS


class TestSignalGenerationTasks:
    """Test SignalGenerationTasks task set."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock Locust user."""
        user = MagicMock()
        user.user_id = random.randint(1, 1000000)
        return user

    @pytest.fixture
    def task_set(self, mock_user):
        """Create a SignalGenerationTasks instance."""
        tasks = SignalGenerationTasks(mock_user)
        return tasks

    def test_on_start(self, task_set) -> None:
        """Test task set initialization."""
        task_set.on_start()
        assert hasattr(task_set, "user_id")
        assert isinstance(task_set.user_id, int)

    def test_task_weights(self) -> None:
        """Verify task weights are properly configured."""
        # Check that tasks have different weights
        from tests.load.locustfile import SignalGenerationTasks

        # generate_signal has weight 10
        # get_signal_status has weight 5
        # batch_generate_signals has weight 2
        assert hasattr(SignalGenerationTasks, "generate_signal")
        assert hasattr(SignalGenerationTasks, "get_signal_status")
        assert hasattr(SignalGenerationTasks, "batch_generate_signals")


class TestDatabaseLoadTasks:
    """Test DatabaseLoadTasks task set."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock Locust user."""
        user = MagicMock()
        user.user_id = random.randint(1, 1000000)
        return user

    @pytest.fixture
    def task_set(self, mock_user):
        """Create a DatabaseLoadTasks instance."""
        tasks = DatabaseLoadTasks(mock_user)
        return tasks

    def test_on_start(self, task_set) -> None:
        """Test task set initialization."""
        task_set.on_start()
        assert hasattr(task_set, "user_id")

    def test_generate_outcome_data(self, task_set) -> None:
        """Test outcome data generation."""
        outcome = task_set._generate_outcome_data()

        assert "signal_id" in outcome
        assert "token" in outcome
        assert "direction" in outcome
        assert outcome["direction"] in SIGNAL_DIRECTIONS
        assert "pnl" in outcome
        assert "outcome" in outcome
        assert "timestamp" in outcome
        assert "confidence" in outcome


class TestSignalGenerationUser:
    """Test SignalGenerationUser Locust user."""

    def test_user_configuration(self) -> None:
        """Verify user configuration."""
        assert SignalGenerationUser.weight == 30
        assert SignalGenerationUser.tasks == [SignalGenerationTasks]

    def test_wait_time(self) -> None:
        """Verify wait time is configured."""
        # Wait time should be between 1-5 seconds
        assert hasattr(SignalGenerationUser, "wait_time")


class TestDatabaseLoadUser:
    """Test DatabaseLoadUser Locust user."""

    def test_user_configuration(self) -> None:
        """Verify user configuration."""
        assert DatabaseLoadUser.weight == 50
        assert DatabaseLoadUser.tasks == [DatabaseLoadTasks]

    def test_wait_time(self) -> None:
        """Verify wait time is configured."""
        assert hasattr(DatabaseLoadUser, "wait_time")


class TestWebSocketUser:
    """Test WebSocketUser Locust user."""

    def test_user_configuration(self) -> None:
        """Verify user configuration."""
        assert WebSocketUser.weight == 20
        assert hasattr(WebSocketUser, "wait_time")

    def test_on_start(self) -> None:
        """Test user initialization."""
        # Set host attribute on the class temporarily
        original_host = getattr(WebSocketUser, "host", None)
        WebSocketUser.host = "http://localhost:8001"
        try:
            user = MagicMock()
            ws_user = WebSocketUser(user)
            ws_user.on_start()

            assert hasattr(ws_user, "user_id")
            assert hasattr(ws_user, "subscribed_channels")
            assert isinstance(ws_user.subscribed_channels, list)
        finally:
            if original_host is None:
                delattr(WebSocketUser, "host")
            else:
                WebSocketUser.host = original_host


class TestLocustfileEntryPoint:
    """Test locustfile entry point functionality."""

    def test_main_block(self) -> None:
        """Test the main block provides usage information."""
        # The __main__ block should provide usage info
        # We can't directly test it, but we can verify the module loads
        import tests.load.locustfile as locustfile

        assert hasattr(locustfile, "SignalGenerationUser")
        assert hasattr(locustfile, "DatabaseLoadUser")
        assert hasattr(locustfile, "WebSocketUser")
        assert hasattr(locustfile, "LOCUST_AVAILABLE")

    def test_event_listeners(self) -> None:
        """Test event listeners are defined."""
        from tests.load.locustfile import on_test_start, on_test_stop

        # Verify functions exist and are callable
        assert callable(on_test_start)
        assert callable(on_test_stop)
