"""Tests for rollback handler."""

from execution.canary.models import (
    CanaryStatus,
    create_canary_deployment,
)
from execution.canary.rollback import (
    RollbackHandler,
    RollbackResult,
    RollbackStatus,
    create_rollback_handler,
)


class TestRollbackHandler:
    """Test RollbackHandler class."""

    def test_init_without_callback(self):
        """Test initialization without callback."""
        handler = RollbackHandler()
        assert handler.rollback_callback is None
        assert len(handler._rollback_history) == 0

    def test_init_with_callback(self):
        """Test initialization with callback."""

        def callback(canary_id, champion_id):
            return True

        handler = RollbackHandler(rollback_callback=callback)
        assert handler.rollback_callback is not None

    def test_execute_rollback_success(self):
        """Test successful rollback execution."""
        handler = RollbackHandler()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.FAILED

        result = handler.execute_rollback(canary, "Drawdown exceeded")

        assert result.success is True
        assert result.status == RollbackStatus.COMPLETED
        assert result.canary_id == "test-001"
        assert result.champion_strategy_id == "strategy-v1"
        assert canary.status == CanaryStatus.ROLLED_BACK

    def test_execute_rollback_no_champion(self):
        """Test rollback without champion strategy."""
        handler = RollbackHandler()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            # No champion_strategy_id
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.FAILED

        result = handler.execute_rollback(canary, "Drawdown exceeded")

        assert result.success is False
        assert result.status == RollbackStatus.FAILED
        assert "no champion strategy available" in result.message

    def test_execute_rollback_not_needed(self):
        """Test rollback when not needed."""
        handler = RollbackHandler()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        # Status is RUNNING, not FAILED

        result = handler.execute_rollback(canary, "Some reason")

        assert result.success is False
        assert "Rollback not needed" in result.message

    def test_execute_rollback_forced(self):
        """Test forced rollback."""
        handler = RollbackHandler()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        # Status is RUNNING, but we force rollback

        result = handler.execute_rollback(canary, "Forced rollback", force=True)

        assert result.success is True
        assert result.status == RollbackStatus.COMPLETED

    def test_execute_rollback_with_callback_success(self):
        """Test rollback with successful callback."""

        def callback(canary_id, champion_id):
            return True

        handler = RollbackHandler(rollback_callback=callback)
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.FAILED

        result = handler.execute_rollback(canary, "Test failure")

        assert result.success is True
        assert result.status == RollbackStatus.COMPLETED

    def test_execute_rollback_with_callback_failure(self):
        """Test rollback with failing callback."""

        def callback(canary_id, champion_id):
            return False

        handler = RollbackHandler(rollback_callback=callback)
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.FAILED

        result = handler.execute_rollback(canary, "Test failure")

        assert result.success is False
        assert result.status == RollbackStatus.FAILED
        assert "callback returned False" in result.message

    def test_execute_rollback_callback_exception(self):
        """Test rollback when callback raises exception."""

        def callback(canary_id, champion_id):
            raise ValueError("Callback error")

        handler = RollbackHandler(rollback_callback=callback)
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.FAILED

        result = handler.execute_rollback(canary, "Test failure")

        assert result.success is False
        assert result.status == RollbackStatus.FAILED
        assert "Callback error" in result.message

    def test_check_and_rollback_with_failures(self):
        """Test check_and_rollback with failure reasons."""
        handler = RollbackHandler()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)

        result = handler.check_and_rollback(canary, ["Drawdown exceeded"])

        assert result is not None
        assert result.success is True
        assert canary.status == CanaryStatus.ROLLED_BACK

    def test_check_and_rollback_no_failures(self):
        """Test check_and_rollback without failure reasons."""
        handler = RollbackHandler()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)

        result = handler.check_and_rollback(canary, [])

        assert result is None

    def test_get_rollback_history(self):
        """Test getting rollback history."""
        handler = RollbackHandler()

        # Execute some rollbacks (first one has no champion, so it will fail)
        for i in range(3):
            canary = create_canary_deployment(
                canary_id=f"test-{i:03d}",
                strategy_id=f"strategy-v{i}",
                champion_strategy_id=f"strategy-v{i - 1}" if i > 0 else "champion",
            )
            canary.start(initial_equity=10000.0)
            canary.status = CanaryStatus.FAILED
            handler.execute_rollback(canary, f"Failure {i}")

        # Get all history (all 3 should be recorded, even the failed ones)
        history = handler.get_rollback_history()
        assert len(history) == 3

        # Get history for specific canary
        history = handler.get_rollback_history("test-001")
        assert len(history) == 1
        assert history[0].canary_id == "test-001"

    def test_clear_history(self):
        """Test clearing rollback history."""
        handler = RollbackHandler()
        canary = create_canary_deployment(
            canary_id="test-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.FAILED
        handler.execute_rollback(canary, "Test")

        assert len(handler._rollback_history) == 1

        handler.clear_history()
        assert len(handler._rollback_history) == 0


class TestRollbackResult:
    """Test RollbackResult class."""

    def test_to_dict(self):
        """Test serialization to dict."""
        result = RollbackResult(
            canary_id="test-001",
            champion_strategy_id="strategy-v1",
            status=RollbackStatus.COMPLETED,
            success=True,
            message="Rollback successful",
        )

        data = result.to_dict()
        assert data["canary_id"] == "test-001"
        assert data["champion_strategy_id"] == "strategy-v1"
        assert data["status"] == "completed"
        assert data["success"] is True
        assert data["message"] == "Rollback successful"


class TestCreateRollbackHandler:
    """Test create_rollback_handler factory function."""

    def test_create_without_callback(self):
        """Test creating handler without callback."""
        handler = create_rollback_handler()
        assert isinstance(handler, RollbackHandler)
        assert handler.rollback_callback is None

    def test_create_with_callback(self):
        """Test creating handler with callback."""

        def callback(canary_id, champion_id):
            return True

        handler = create_rollback_handler(rollback_callback=callback)
        assert handler.rollback_callback is not None
