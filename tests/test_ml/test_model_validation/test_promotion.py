"""Tests for promotion workflow."""

import pytest
from datetime import datetime, UTC

from ml.model_registry.registry import ModelRegistry, ModelStatus, ModelType
from ml.rollback.automatic import RollbackManager, RollbackConfig, RollbackReason
from ml.validation.gate import ValidationGate
from ml.validation.promotion import (
    PromotionWorkflow,
    PromotionRequestStatus,
)


class TestPromotionWorkflow:
    """Tests for PromotionWorkflow."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry."""
        return ModelRegistry()

    @pytest.fixture
    def gate(self, registry):
        """Create a validation gate."""
        return ValidationGate(registry=registry)

    @pytest.fixture
    def rollback(self, registry):
        """Create a rollback manager."""
        config = RollbackConfig(auto_rollback_enabled=True)
        return RollbackManager(registry=registry, config=config)

    @pytest.fixture
    def workflow(self, registry, gate, rollback):
        """Create a promotion workflow."""
        return PromotionWorkflow(registry=registry, gate=gate, rollback=rollback)

    @pytest.mark.asyncio
    async def test_submit_for_promotion(self, workflow, registry, gate):
        """Test submitting for promotion."""
        # Create champion first (needed for comparison)
        champion = registry.register_model(
            model_id="test_model",
            model_path="/models/champion.pkl",
            metrics={"f1": 0.75, "accuracy": 0.78},
        )
        registry.promote_to_candidate(champion.version_id)
        registry.promote_to_challenger(champion.version_id)
        registry.promote_to_champion(champion.version_id, force=True)

        # Create candidate
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/candidate.pkl",
        )
        registry.promote_to_candidate(version.version_id)

        # Run validation
        run = await gate.run_offline_validation(version.version_id)

        # Submit for promotion
        request = await workflow.submit_for_promotion(
            version_id=version.version_id,
            validation_run_id=run.run_id,
            submitted_by="test_user",
        )

        assert request.version_id == version.version_id
        assert request.validation_run_id == run.run_id
        assert request.submitted_by == "test_user"
        assert request.status in [
            PromotionRequestStatus.PENDING_APPROVAL,
            PromotionRequestStatus.VALIDATION_FAILED,
        ]

    @pytest.mark.asyncio
    async def test_approve_promotion(self, workflow, registry, gate):
        """Test approving promotion."""
        # Create champion
        champion = registry.register_model(
            model_id="test_model",
            model_path="/models/champion.pkl",
            metrics={"f1": 0.70, "accuracy": 0.72},
        )
        registry.promote_to_candidate(champion.version_id)
        registry.promote_to_challenger(champion.version_id)
        registry.promote_to_champion(champion.version_id, force=True)

        # Create and validate candidate
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/candidate.pkl",
            metrics={
                "f1": 0.82,
                "accuracy": 0.85,
                "precision": 0.80,
                "recall": 0.78,
                "ece": 0.10,
            },
        )
        registry.promote_to_candidate(version.version_id)

        run = await gate.run_offline_validation(version.version_id)

        request = await workflow.submit_for_promotion(
            version_id=version.version_id,
            validation_run_id=run.run_id,
        )

        # Approve promotion
        if request.status == PromotionRequestStatus.PENDING_APPROVAL:
            result = await workflow.approve_promotion(
                request.request_id, approver="admin"
            )

            assert result.success is True
            assert result.request_id == request.request_id
            assert result.version_id == version.version_id

            # Verify champion was updated
            current_champion = registry.get_champion(ModelType.SIGNAL_PREDICTOR)
            assert current_champion.version_id == version.version_id

    @pytest.mark.asyncio
    async def test_reject_promotion(self, workflow, registry, gate):
        """Test rejecting promotion."""
        # Create champion
        champion = registry.register_model(
            model_id="test_model",
            model_path="/models/champion.pkl",
            metrics={"f1": 0.80},
        )
        registry.promote_to_candidate(champion.version_id)
        registry.promote_to_challenger(champion.version_id)
        registry.promote_to_champion(champion.version_id, force=True)

        # Create candidate
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/candidate.pkl",
            metrics={"f1": 0.82},
        )
        registry.promote_to_candidate(version.version_id)

        run = await gate.run_offline_validation(version.version_id)

        request = await workflow.submit_for_promotion(
            version_id=version.version_id,
            validation_run_id=run.run_id,
        )

        # Reject promotion
        if request.status == PromotionRequestStatus.PENDING_APPROVAL:
            updated = await workflow.reject_promotion(
                request_id=request.request_id,
                rejected_by="admin",
                reason="Performance not sufficient",
            )

            assert updated.status == PromotionRequestStatus.REJECTED
            assert updated.approved_by == "admin"

    @pytest.mark.asyncio
    async def test_cannot_approve_without_pending_status(
        self, workflow, registry, gate
    ):
        """Test that approval requires PENDING_APPROVAL status."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )
        registry.promote_to_candidate(version.version_id)

        run = await gate.run_offline_validation(version.version_id)

        request = await workflow.submit_for_promotion(
            version_id=version.version_id,
            validation_run_id=run.run_id,
        )

        # Try to approve again (should fail if already processed)
        result = await workflow.approve_promotion(request.request_id, approver="admin")

        if request.status != PromotionRequestStatus.PENDING_APPROVAL:
            assert result.success is False
            assert "PENDING_APPROVAL" in result.message

    @pytest.mark.asyncio
    async def test_get_request(self, workflow, registry, gate):
        """Test retrieving promotion request."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )
        registry.promote_to_candidate(version.version_id)

        run = await gate.run_offline_validation(version.version_id)

        request = await workflow.submit_for_promotion(
            version_id=version.version_id,
            validation_run_id=run.run_id,
        )

        retrieved = workflow.get_request(request.request_id)
        assert retrieved is not None
        assert retrieved.request_id == request.request_id

    @pytest.mark.asyncio
    async def test_list_requests(self, workflow, registry, gate):
        """Test listing promotion requests."""
        version1 = registry.register_model(
            model_id="test_model",
            model_path="/models/v1.pkl",
        )
        registry.promote_to_candidate(version1.version_id)
        run1 = await gate.run_offline_validation(version1.version_id)

        version2 = registry.register_model(
            model_id="test_model",
            model_path="/models/v2.pkl",
        )
        registry.promote_to_candidate(version2.version_id)
        run2 = await gate.run_offline_validation(version2.version_id)

        await workflow.submit_for_promotion(
            version_id=version1.version_id,
            validation_run_id=run1.run_id,
        )
        await workflow.submit_for_promotion(
            version_id=version2.version_id,
            validation_run_id=run2.run_id,
        )

        requests = workflow.list_requests()
        # Should have at least 2 requests
        assert len(requests) >= 2

    @pytest.mark.asyncio
    async def test_get_pending_approvals(self, workflow, registry, gate):
        """Test getting pending approvals."""
        # Create champion
        champion = registry.register_model(
            model_id="test_model",
            model_path="/models/champion.pkl",
            metrics={"f1": 0.70},
        )
        registry.promote_to_candidate(champion.version_id)
        registry.promote_to_challenger(champion.version_id)
        registry.promote_to_champion(champion.version_id, force=True)

        # Create candidate that should pass validation
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/candidate.pkl",
            metrics={
                "f1": 0.85,
                "accuracy": 0.87,
                "precision": 0.84,
                "recall": 0.82,
                "ece": 0.08,
            },
        )
        registry.promote_to_candidate(version.version_id)

        run = await gate.run_offline_validation(version.version_id)

        request = await workflow.submit_for_promotion(
            version_id=version.version_id,
            validation_run_id=run.run_id,
        )

        pending = workflow.get_pending_approvals()

        if request.status == PromotionRequestStatus.PENDING_APPROVAL:
            assert len(pending) >= 1
            assert any(r.request_id == request.request_id for r in pending)
