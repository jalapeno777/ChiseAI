"""Tests for automatic rollback."""

import pytest
import asyncio
from datetime import datetime, UTC

from ml.model_registry.registry import ModelRegistry, ModelStatus, ModelType
from ml.rollback.automatic import (
    RollbackManager,
    RollbackConfig,
    RollbackReason,
    RollbackResult,
    RollbackState,
)


class TestRollbackResult:
    """Tests for RollbackResult."""

    def test_rollback_result_creation(self):
        """Test creating rollback result."""
        result = RollbackResult(
            success=True,
            rollback_id="rollback_20260222_120000",
            failed_version_id="failed_v1",
            target_version_id="target_v1",
            state=RollbackState.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            duration_seconds=5.0,
            reason=RollbackReason.VALIDATION_FAILED,
            message="Rollback successful",
        )

        assert result.success is True
        assert result.state == RollbackState.COMPLETED
        assert result.reason == RollbackReason.VALIDATION_FAILED

    def test_rollback_result_to_dict(self):
        """Test converting rollback result to dict."""
        result = RollbackResult(
            success=True,
            rollback_id="rollback_20260222_120000",
            failed_version_id="failed_v1",
            target_version_id="target_v1",
            state=RollbackState.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            duration_seconds=5.0,
            reason=RollbackReason.VALIDATION_FAILED,
            message="Rollback successful",
        )

        data = result.to_dict()
        assert data["success"] is True
        assert data["rollback_id"] == "rollback_20260222_120000"
        assert data["reason"] == "validation_failed"


class TestRollbackConfig:
    """Tests for RollbackConfig."""

    def test_default_config(self):
        """Test default rollback configuration."""
        config = RollbackConfig()

        # AC5: Rollback completes in <60 seconds
        assert config.max_rollback_time_seconds == 60.0
        assert config.auto_rollback_enabled is True
        assert config.require_confirmation is False


class TestRollbackManager:
    """Tests for RollbackManager."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry."""
        return ModelRegistry()

    @pytest.fixture
    def rollback(self, registry):
        """Create a rollback manager."""
        config = RollbackConfig(auto_rollback_enabled=True)
        return RollbackManager(registry=registry, config=config)

    @pytest.mark.asyncio
    async def test_rollback_on_validation_failure(self, rollback, registry):
        """Test rollback on validation failure."""
        # Create initial champion
        v1 = registry.register_model(
            model_id="test_model",
            model_path="/models/v1.pkl",
            metrics={"f1": 0.80},
        )
        registry.promote_to_candidate(v1.version_id)
        registry.promote_to_challenger(v1.version_id)
        registry.promote_to_champion(v1.version_id, force=True)

        # Create new version that fails
        v2 = registry.register_model(
            model_id="test_model",
            model_path="/models/v2.pkl",
            metrics={"f1": 0.75},
        )
        registry.promote_to_candidate(v2.version_id)
        registry.promote_to_challenger(v2.version_id)
        registry.promote_to_champion(v2.version_id, force=True)

        # Trigger rollback
        result = await rollback.rollback_on_failure(
            failed_version_id=v2.version_id,
            reason=RollbackReason.VALIDATION_FAILED,
            details="Validation failed: accuracy too low",
        )

        # AC4: Automatic rollback triggers on validation failure
        assert result.success is True
        assert result.state == RollbackState.COMPLETED
        assert result.failed_version_id == v2.version_id
        assert result.target_version_id == v1.version_id

        # AC5: Rollback completes in <60 seconds
        assert result.duration_seconds < 60.0

        # Verify v1 is champion again
        champion = registry.get_champion(ModelType.SIGNAL_PREDICTOR)
        assert champion.version_id == v1.version_id
        assert champion.status == ModelStatus.CHAMPION

        # Verify v2 is deprecated (was champion, then marked failed, then deprecated when v1 promoted)
        failed = registry.get_version(v2.version_id)
        assert failed.status == ModelStatus.DEPRECATED
        assert "failure_reason" in failed.metadata

    @pytest.mark.asyncio
    async def test_rollback_disabled(self, registry):
        """Test rollback when auto-rollback is disabled."""
        config = RollbackConfig(auto_rollback_enabled=False)
        rollback = RollbackManager(registry=registry, config=config)

        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )

        result = await rollback.rollback_on_failure(
            failed_version_id=version.version_id,
            reason=RollbackReason.VALIDATION_FAILED,
        )

        assert result.success is False
        assert result.state == RollbackState.CANCELLED
        assert "disabled" in result.message.lower()

    @pytest.mark.asyncio
    async def test_rollback_no_target(self, rollback, registry):
        """Test rollback when no rollback target exists."""
        # Create version but don't promote to champion
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )

        result = await rollback.rollback_on_failure(
            failed_version_id=version.version_id,
            reason=RollbackReason.VALIDATION_FAILED,
        )

        assert result.success is False
        assert result.state == RollbackState.FAILED
        assert "no rollback target" in result.message.lower()

    @pytest.mark.asyncio
    async def test_rollback_version_not_found(self, rollback):
        """Test rollback when version not found."""
        result = await rollback.rollback_on_failure(
            failed_version_id="nonexistent",
            reason=RollbackReason.VALIDATION_FAILED,
        )

        assert result.success is False
        assert result.state == RollbackState.FAILED
        assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_manual_rollback(self, rollback, registry):
        """Test manual rollback."""
        # Create versions
        v1 = registry.register_model(
            model_id="test_model",
            model_path="/models/v1.pkl",
            metrics={"f1": 0.80},
        )
        registry.promote_to_candidate(v1.version_id)
        registry.promote_to_challenger(v1.version_id)
        registry.promote_to_champion(v1.version_id, force=True)

        v2 = registry.register_model(
            model_id="test_model",
            model_path="/models/v2.pkl",
            metrics={"f1": 0.82},
        )
        registry.promote_to_candidate(v2.version_id)
        registry.promote_to_challenger(v2.version_id)
        registry.promote_to_champion(v2.version_id, force=True)

        # Manual rollback to v1
        result = await rollback.manual_rollback(
            target_version_id=v1.version_id,
            reason="Manual rollback for testing",
        )

        assert result.success is True
        assert result.target_version_id == v1.version_id
        assert result.reason == RollbackReason.MANUAL

        # Verify v1 is champion
        champion = registry.get_champion(ModelType.SIGNAL_PREDICTOR)
        assert champion.version_id == v1.version_id

    @pytest.mark.asyncio
    async def test_manual_rollback_target_not_found(self, rollback):
        """Test manual rollback when target not found."""
        result = await rollback.manual_rollback(
            target_version_id="nonexistent",
            reason="Test",
        )

        assert result.success is False
        assert result.state == RollbackState.FAILED
        assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_get_rollback_history(self, rollback, registry):
        """Test getting rollback history."""
        # Create and rollback
        v1 = registry.register_model(
            model_id="test_model",
            model_path="/models/v1.pkl",
            metrics={"f1": 0.80},
        )
        registry.promote_to_candidate(v1.version_id)
        registry.promote_to_challenger(v1.version_id)
        registry.promote_to_champion(v1.version_id, force=True)

        v2 = registry.register_model(
            model_id="test_model",
            model_path="/models/v2.pkl",
            metrics={"f1": 0.75},
        )
        registry.promote_to_candidate(v2.version_id)
        registry.promote_to_challenger(v2.version_id)
        registry.promote_to_champion(v2.version_id, force=True)

        await rollback.rollback_on_failure(
            failed_version_id=v2.version_id,
            reason=RollbackReason.VALIDATION_FAILED,
        )

        history = rollback.get_rollback_history()
        assert len(history) == 1
        assert history[0].failed_version_id == v2.version_id

    def test_enable_disable_auto_rollback(self, rollback):
        """Test enabling and disabling auto-rollback."""
        assert rollback.is_auto_rollback_enabled() is True

        rollback.disable_auto_rollback()
        assert rollback.is_auto_rollback_enabled() is False

        rollback.enable_auto_rollback()
        assert rollback.is_auto_rollback_enabled() is True

    @pytest.mark.asyncio
    async def test_rollback_with_force(self, rollback, registry):
        """Test rollback with force flag."""
        # Create version
        v1 = registry.register_model(
            model_id="test_model",
            model_path="/models/v1.pkl",
            metrics={"f1": 0.80},
        )
        registry.promote_to_candidate(v1.version_id)
        registry.promote_to_challenger(v1.version_id)
        registry.promote_to_champion(v1.version_id, force=True)

        v2 = registry.register_model(
            model_id="test_model",
            model_path="/models/v2.pkl",
            metrics={"f1": 0.75},
        )
        registry.promote_to_candidate(v2.version_id)
        registry.promote_to_challenger(v2.version_id)
        registry.promote_to_champion(v2.version_id, force=True)

        # Disable auto-rollback
        rollback.disable_auto_rollback()

        # Force rollback
        result = await rollback.rollback_on_failure(
            failed_version_id=v2.version_id,
            reason=RollbackReason.VALIDATION_FAILED,
            force=True,
        )

        assert result.success is True  # Should succeed with force
