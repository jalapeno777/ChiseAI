"""Promotion workflow with human approval for ChiseAI.

This module provides the promotion workflow that requires human approval
after validation is complete. It integrates with the validation gate,
model registry, and rollback systems.

Acceptance Criteria:
- Human approval required for promotion after validation
- Integration with validation gate and rollback systems
- Full evidence logging for audit trail

Example:
    >>> from ml.validation.promotion import PromotionWorkflow
    >>> workflow = PromotionWorkflow(registry=registry, gate=gate, rollback=rollback)
    >>>
    >>> # Submit for promotion after validation
    >>> request = await workflow.submit_for_promotion(
    ...     version_id="grid_btc_1h_v2_20260222_120000",
    ...     validation_run_id="val_20260222_120000"
    ... )
    >>> # Approve promotion (human action)
    >>> result = await workflow.approve_promotion(request.request_id, approver="admin")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any

from ml.model_registry.registry import (
    ModelRegistry,
    ModelStatus,
    ModelType,
    ModelVersion,
    PromotionCriteria,
)
from ml.rollback.automatic import RollbackManager, RollbackReason
from ml.validation.gate import ValidationGate, ValidationRun, ValidationState

logger = logging.getLogger(__name__)


class PromotionRequestStatus(Enum):
    """Status of promotion requests."""

    PENDING_VALIDATION = "pending_validation"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    PENDING_APPROVAL = "pending_approval"  # AC7: Human approval required
    APPROVED = "approved"
    REJECTED = "rejected"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class PromotionRequest:
    """Request for model promotion.

    Attributes:
        request_id: Unique request identifier
        version_id: Model version to promote
        validation_run_id: Associated validation run
        status: Current status
        submitted_at: When request was submitted
        submitted_by: Who submitted the request
        approved_at: When approved (if applicable)
        approved_by: Who approved (if applicable)
        promotion_criteria: Criteria used for evaluation
        evidence: Full evidence log
    """

    request_id: str
    version_id: str
    validation_run_id: str
    status: PromotionRequestStatus
    submitted_at: datetime
    submitted_by: str
    approved_at: datetime | None = None
    approved_by: str | None = None
    promotion_criteria: PromotionCriteria = field(default_factory=PromotionCriteria)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "version_id": self.version_id,
            "validation_run_id": self.validation_run_id,
            "status": self.status.value,
            "submitted_at": self.submitted_at.isoformat(),
            "submitted_by": self.submitted_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approved_by": self.approved_by,
            "promotion_criteria": {
                "min_accuracy": self.promotion_criteria.min_accuracy,
                "min_precision": self.promotion_criteria.min_precision,
                "min_recall": self.promotion_criteria.min_recall,
                "min_f1": self.promotion_criteria.min_f1,
                "max_ece": self.promotion_criteria.max_ece,
                "require_human_approval": self.promotion_criteria.require_human_approval,
            },
            "evidence": self.evidence,
        }


@dataclass
class PromotionResult:
    """Result of promotion operation.

    Attributes:
        success: Whether promotion succeeded
        request_id: Promotion request ID
        version_id: Version that was promoted
        previous_champion_id: Previous champion (if any)
        promoted_at: When promotion occurred
        message: Human-readable message
        evidence: Full evidence log
    """

    success: bool
    request_id: str
    version_id: str
    previous_champion_id: str | None
    promoted_at: datetime
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "request_id": self.request_id,
            "version_id": self.version_id,
            "previous_champion_id": self.previous_champion_id,
            "promoted_at": self.promoted_at.isoformat(),
            "message": self.message,
            "evidence": self.evidence,
        }


class PromotionWorkflow:
    """Workflow for model promotion with human approval.

    AC7: Human approval required for promotion after validation.

    This workflow manages the promotion lifecycle:
    1. Submit model for promotion after validation
    2. Check validation results
    3. Request human approval
    4. Execute promotion or rollback
    5. Log full evidence
    """

    def __init__(
        self,
        registry: ModelRegistry,
        gate: ValidationGate,
        rollback: RollbackManager,
    ):
        """Initialize promotion workflow.

        Args:
            registry: Model registry
            gate: Validation gate
            rollback: Rollback manager
        """
        self._registry = registry
        self._gate = gate
        self._rollback = rollback
        self._requests: dict[str, PromotionRequest] = {}

        logger.info("PromotionWorkflow initialized")

    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        return f"promo_{timestamp}"

    async def submit_for_promotion(
        self,
        version_id: str,
        validation_run_id: str,
        submitted_by: str = "system",
    ) -> PromotionRequest:
        """Submit a model version for promotion.

        Args:
            version_id: Model version to promote
            validation_run_id: Associated validation run ID
            submitted_by: Who is submitting the request

        Returns:
            PromotionRequest record

        Raises:
            ValueError: If version or validation run not found
        """
        # Verify version exists
        version = self._registry.get_version(version_id)
        if not version:
            raise ValueError(f"Version not found: {version_id}")

        # Verify validation run exists
        validation_run = self._gate.get_validation_run(validation_run_id)
        if not validation_run:
            raise ValueError(f"Validation run not found: {validation_run_id}")

        request_id = self._generate_request_id()

        # Determine initial status based on validation
        if validation_run.state == ValidationState.COMPLETED:
            passed, failures = self._gate.evaluate_validation_result(validation_run_id)
            if passed:
                status = (
                    PromotionRequestStatus.PENDING_APPROVAL
                )  # AC7: Awaiting approval
            else:
                status = PromotionRequestStatus.VALIDATION_FAILED
        else:
            status = PromotionRequestStatus.PENDING_VALIDATION

        request = PromotionRequest(
            request_id=request_id,
            version_id=version_id,
            validation_run_id=validation_run_id,
            status=status,
            submitted_at=datetime.now(UTC),
            submitted_by=submitted_by,
            promotion_criteria=self._registry._promotion_criteria,
            evidence={
                "validation_run": validation_run.to_dict(),
                "initial_status": status.value,
            },
        )

        self._requests[request_id] = request

        logger.info(
            f"Promotion request submitted: {request_id} for {version_id}, "
            f"status={status.value}"
        )

        # If validation failed, trigger rollback
        if status == PromotionRequestStatus.VALIDATION_FAILED:
            await self._handle_validation_failure(request)

        return request

    async def _handle_validation_failure(self, request: PromotionRequest) -> None:
        """Handle validation failure by triggering rollback.

        Args:
            request: Failed promotion request
        """
        logger.warning(
            f"Validation failed for {request.version_id}, triggering rollback"
        )

        rollback_result = await self._rollback.rollback_on_failure(
            failed_version_id=request.version_id,
            reason=RollbackReason.VALIDATION_FAILED,
            details="Validation criteria not met",
        )

        # Update request status
        if rollback_result.success:
            updated_request = PromotionRequest(
                request_id=request.request_id,
                version_id=request.version_id,
                validation_run_id=request.validation_run_id,
                status=PromotionRequestStatus.ROLLED_BACK,
                submitted_at=request.submitted_at,
                submitted_by=request.submitted_by,
                promotion_criteria=request.promotion_criteria,
                evidence={
                    **request.evidence,
                    "rollback": rollback_result.to_dict(),
                },
            )
            self._requests[request.request_id] = updated_request
            logger.info(f"Rollback completed for {request.version_id}")
        else:
            logger.error(f"Rollback failed for {request.version_id}")

    async def approve_promotion(
        self,
        request_id: str,
        approver: str,
    ) -> PromotionResult:
        """Approve and execute promotion.

        AC7: Human approval required for promotion after validation.

        Args:
            request_id: Promotion request ID
            approver: Who is approving

        Returns:
            PromotionResult

        Raises:
            ValueError: If request not found or not in correct state
        """
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"Promotion request not found: {request_id}")

        if request.status != PromotionRequestStatus.PENDING_APPROVAL:
            return PromotionResult(
                success=False,
                request_id=request_id,
                version_id=request.version_id,
                previous_champion_id=None,
                promoted_at=datetime.now(UTC),
                message=f"Cannot approve: status is {request.status.value}, expected PENDING_APPROVAL",
                evidence={"request": request.to_dict()},
            )

        # Update request to approved
        approved_request = PromotionRequest(
            request_id=request.request_id,
            version_id=request.version_id,
            validation_run_id=request.validation_run_id,
            status=PromotionRequestStatus.APPROVED,
            submitted_at=request.submitted_at,
            submitted_by=request.submitted_by,
            approved_at=datetime.now(UTC),
            approved_by=approver,
            promotion_criteria=request.promotion_criteria,
            evidence=request.evidence,
        )
        self._requests[request_id] = approved_request

        logger.info(f"Promotion approved by {approver}: {request_id}")

        # Execute promotion
        return await self._execute_promotion(approved_request)

    async def reject_promotion(
        self,
        request_id: str,
        rejected_by: str,
        reason: str = "",
    ) -> PromotionRequest:
        """Reject promotion request.

        Args:
            request_id: Promotion request ID
            rejected_by: Who is rejecting
            reason: Rejection reason

        Returns:
            Updated PromotionRequest
        """
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"Promotion request not found: {request_id}")

        if request.status != PromotionRequestStatus.PENDING_APPROVAL:
            raise ValueError(
                f"Cannot reject: status is {request.status.value}, expected PENDING_APPROVAL"
            )

        updated_request = PromotionRequest(
            request_id=request.request_id,
            version_id=request.version_id,
            validation_run_id=request.validation_run_id,
            status=PromotionRequestStatus.REJECTED,
            submitted_at=request.submitted_at,
            submitted_by=request.submitted_by,
            approved_at=datetime.now(UTC),
            approved_by=rejected_by,
            promotion_criteria=request.promotion_criteria,
            evidence={
                **request.evidence,
                "rejection_reason": reason,
            },
        )
        self._requests[request_id] = updated_request

        # Trigger rollback
        await self._rollback.rollback_on_failure(
            failed_version_id=request.version_id,
            reason=RollbackReason.VALIDATION_FAILED,
            details=f"Promotion rejected by {rejected_by}: {reason}",
        )

        logger.info(
            f"Promotion rejected by {rejected_by}: {request_id}, reason={reason}"
        )

        return updated_request

    async def _execute_promotion(self, request: PromotionRequest) -> PromotionResult:
        """Execute the promotion.

        Args:
            request: Approved promotion request

        Returns:
            PromotionResult
        """
        version_id = request.version_id

        try:
            # Get version info
            version = self._registry.get_version(version_id)
            if not version:
                return PromotionResult(
                    success=False,
                    request_id=request.request_id,
                    version_id=version_id,
                    previous_champion_id=None,
                    promoted_at=datetime.now(UTC),
                    message=f"Version not found: {version_id}",
                    evidence={"request": request.to_dict()},
                )

            # Get current champion
            current_champion = self._registry.get_champion(version.model_type)
            previous_champion_id = (
                current_champion.version_id if current_champion else None
            )

            # Promote to challenger first
            self._registry.promote_to_challenger(version_id)

            # Then promote to champion
            new_champion, old_champion = self._registry.promote_to_champion(version_id)

            # Update request status
            promoted_request = PromotionRequest(
                request_id=request.request_id,
                version_id=request.version_id,
                validation_run_id=request.validation_run_id,
                status=PromotionRequestStatus.PROMOTED,
                submitted_at=request.submitted_at,
                submitted_by=request.submitted_by,
                approved_at=request.approved_at,
                approved_by=request.approved_by,
                promotion_criteria=request.promotion_criteria,
                evidence={
                    **request.evidence,
                    "promotion": {
                        "new_champion": new_champion.to_dict(),
                        "old_champion": (
                            old_champion.to_dict() if old_champion else None
                        ),
                    },
                },
            )
            self._requests[request.request_id] = promoted_request

            logger.info(
                f"Promotion completed: {version_id} is now CHAMPION, "
                f"previous={previous_champion_id}"
            )

            return PromotionResult(
                success=True,
                request_id=request.request_id,
                version_id=version_id,
                previous_champion_id=previous_champion_id,
                promoted_at=datetime.now(UTC),
                message=f"Successfully promoted {version_id} to champion",
                evidence={"request": promoted_request.to_dict()},
            )

        except Exception as e:
            logger.exception(f"Promotion failed: {e}")

            # Trigger rollback on promotion failure
            await self._rollback.rollback_on_failure(
                failed_version_id=version_id,
                reason=RollbackReason.SYSTEM_ERROR,
                details=f"Promotion execution failed: {e}",
            )

            return PromotionResult(
                success=False,
                request_id=request.request_id,
                version_id=version_id,
                previous_champion_id=None,
                promoted_at=datetime.now(UTC),
                message=f"Promotion failed: {e}",
                evidence={
                    "request": request.to_dict(),
                    "error": str(e),
                },
            )

    def get_request(self, request_id: str) -> PromotionRequest | None:
        """Get promotion request by ID.

        Args:
            request_id: Request identifier

        Returns:
            PromotionRequest or None
        """
        return self._requests.get(request_id)

    def list_requests(
        self,
        status: PromotionRequestStatus | None = None,
    ) -> list[PromotionRequest]:
        """List promotion requests.

        Args:
            status: Optional status filter

        Returns:
            List of promotion requests
        """
        requests = list(self._requests.values())

        if status:
            requests = [r for r in requests if r.status == status]

        return sorted(requests, key=lambda r: r.submitted_at, reverse=True)

    def get_pending_approvals(self) -> list[PromotionRequest]:
        """Get all pending approval requests.

        Returns:
            List of requests awaiting approval
        """
        return self.list_requests(status=PromotionRequestStatus.PENDING_APPROVAL)
