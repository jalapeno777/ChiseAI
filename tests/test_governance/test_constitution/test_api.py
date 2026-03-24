"""Tests for Constitution API (ST-GOV-002)."""

from unittest.mock import MagicMock, patch

import pytest


class TestHealthEndpoint:
    """Tests for health endpoint."""

    def test_health_endpoint_structure(self):
        """Test that health endpoint returns expected structure."""
        try:
            from src.governance.constitution.api import HealthResponse

            response = HealthResponse(
                status="healthy",
                version="1.0.0",
                loaded_at="2026-02-22T00:00:00",
                invariant_count=5,
                violation_rule_count=5,
            )

            assert response.status == "healthy"
            assert response.version == "1.0.0"
            assert response.invariant_count == 5
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestConstitutionResponse:
    """Tests for constitution response models."""

    def test_constitution_response_model(self):
        """Test ConstitutionResponse model."""
        try:
            from src.governance.constitution.api import ConstitutionResponse

            response = ConstitutionResponse(
                success=True,
                data={"version": "1.0.0"},
                health={"status": "healthy"},
                latency_ms=25.5,
            )

            assert response.success is True
            assert response.latency_ms == 25.5
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestValidateResponse:
    """Tests for validate response model."""

    def test_validate_response_model(self):
        """Test ValidateResponse model."""
        try:
            from src.governance.constitution.api import ValidateResponse

            response = ValidateResponse(
                success=True,
                version="1.0.0",
                valid=True,
                errors=[],
                warnings=["No principles defined"],
            )

            assert response.valid is True
            assert len(response.errors) == 0
            assert len(response.warnings) == 1
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestCheckViolationResponse:
    """Tests for check violation response model."""

    def test_check_violation_response_model(self):
        """Test CheckViolationResponse model."""
        try:
            from src.governance.constitution.api import (
                CheckViolationResponse,
                ViolationDetail,
            )

            response = CheckViolationResponse(
                success=True,
                has_violations=True,
                violations=[
                    ViolationDetail(
                        id="VR-001",
                        name="Test Rule",
                        pattern="test.*pattern",
                        severity="P1",
                    )
                ],
                requires_approval=False,
                approval_level=None,
            )

            assert response.has_violations is True
            assert len(response.violations) == 1
            assert response.violations[0].severity == "P1"
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestOverrideResponse:
    """Tests for override response model."""

    def test_override_response_model(self):
        """Test OverrideResponse model."""
        try:
            from src.governance.constitution.api import OverrideResponse

            response = OverrideResponse(
                success=True,
                override_id="test-uuid",
                status="pending",
                message="Override request created",
            )

            assert response.success is True
            assert response.override_id == "test-uuid"
            assert response.status == "pending"
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestAuditLogResponse:
    """Tests for audit log response model."""

    def test_audit_log_response_model(self):
        """Test AuditLogResponse model."""
        try:
            from src.governance.constitution.api import AuditLogEntry, AuditLogResponse

            response = AuditLogResponse(
                success=True,
                entries=[
                    AuditLogEntry(
                        event="override_requested",
                        timestamp="2026-02-22T00:00:00",
                        override_id="test-uuid",
                        details={},
                    )
                ],
                count=1,
            )

            assert response.success is True
            assert len(response.entries) == 1
            assert response.entries[0].event == "override_requested"
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestOverrideRequestModel:
    """Tests for override request model."""

    def test_override_request_model(self):
        """Test OverrideRequestModel."""
        try:
            from src.governance.constitution.api import OverrideRequestModel

            request = OverrideRequestModel(
                requester="operator-1",
                justification="This is a test justification that is at least 50 characters long",
                risk_assessment="medium",
                affected_systems=["system1", "system2"],
                rollback_plan="Rollback plan description",
                expiration_hours=24,
            )

            assert request.requester == "operator-1"
            assert len(request.justification) >= 50
            assert len(request.affected_systems) == 2
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestCheckViolationRequest:
    """Tests for check violation request model."""

    def test_check_violation_request_model(self):
        """Test CheckViolationRequest model."""
        try:
            from src.governance.constitution.api import CheckViolationRequest

            request = CheckViolationRequest(
                action="test action",
                context={"key": "value"},
            )

            assert request.action == "test action"
            assert request.context == {"key": "value"}
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestApproveOverrideRequest:
    """Tests for approve override request model."""

    def test_approve_override_request_model(self):
        """Test ApproveOverrideRequest model."""
        try:
            from src.governance.constitution.api import ApproveOverrideRequest

            request = ApproveOverrideRequest(
                approver="admin-1",
            )

            assert request.approver == "admin-1"
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestGetConstitutionEndpoint:
    """Tests for get constitution endpoint."""

    @pytest.fixture
    def mock_constitution(self):
        """Create a mock constitution."""
        mock = MagicMock()
        mock.version = MagicMock()
        mock.version.__str__ = MagicMock(return_value="1.0.0")
        mock.to_dict.return_value = {"version": "1.0.0"}
        mock.get_health_status.return_value = {"status": "healthy"}
        return mock

    def test_get_constitution_success(self, mock_constitution):
        """Test successful constitution retrieval."""
        with patch(
            "src.governance.constitution.api.get_constitution",
            return_value=mock_constitution,
        ):
            try:
                import asyncio

                from src.governance.constitution.api import get_constitution_endpoint

                result = asyncio.run(get_constitution_endpoint(version=None))

                assert result["success"] is True
                assert "data" in result
                assert "health" in result
                assert "latency_ms" in result
            except ImportError:
                pytest.skip("FastAPI not installed")


class TestValidateConstitutionEndpoint:
    """Tests for validate constitution endpoint."""

    @pytest.fixture
    def mock_constitution(self):
        """Create a mock constitution."""
        mock = MagicMock()
        mock.version = MagicMock()
        mock.version.__str__ = MagicMock(return_value="1.0.0")
        mock.governed_by = "ST-GOV-002"
        mock.principles = {"core_values": []}
        mock.decision_boundaries = {
            "autonomous": [],
            "conditional": [],
            "restricted": [],
        }
        mock.safety_invariants = {"hard_constraints": []}
        mock.violation_categories = {"detection_rules": []}
        return mock

    def test_validate_constitution_success(self, mock_constitution):
        """Test successful constitution validation."""
        with patch(
            "src.governance.constitution.api.ConstitutionLoader.load",
            return_value=mock_constitution,
        ):
            try:
                import asyncio

                from src.governance.constitution.api import validate_constitution

                result = asyncio.run(validate_constitution(version=None))

                assert result.success is True
                assert result.valid is True
                assert result.version == "1.0.0"
            except ImportError:
                pytest.skip("FastAPI not installed")


class TestCheckViolationEndpoint:
    """Tests for check violation endpoint."""

    @pytest.fixture
    def mock_constitution(self):
        """Create a mock constitution."""
        mock = MagicMock()
        mock.check_violation.return_value = []
        mock.validate_action.return_value = {
            "valid": True,
            "requires_approval": False,
            "approval_level": None,
        }
        return mock

    def test_check_violation_no_violations(self, mock_constitution):
        """Test violation check with no violations."""
        with patch(
            "src.governance.constitution.api.get_constitution",
            return_value=mock_constitution,
        ):
            try:
                import asyncio

                from src.governance.constitution.api import (
                    CheckViolationRequest,
                    check_violation,
                )

                request = CheckViolationRequest(action="test action")
                result = asyncio.run(check_violation(request))

                assert result.success is True
                assert result.has_violations is False
                assert len(result.violations) == 0
            except ImportError:
                pytest.skip("FastAPI not installed")


class TestCreateOverrideEndpoint:
    """Tests for create override endpoint."""

    @pytest.fixture
    def mock_audit_logger(self):
        """Create a mock audit logger."""
        mock = MagicMock()
        mock_request = MagicMock()
        mock_request.override_id = "test-uuid"
        mock_request.status = MagicMock()
        mock_request.status.value = "pending"
        mock.create_request.return_value = mock_request
        return mock

    def test_create_override_success(self, mock_audit_logger):
        """Test successful override creation."""
        with patch(
            "src.governance.constitution.api.get_audit_logger",
            return_value=mock_audit_logger,
        ):
            try:
                import asyncio

                from src.governance.constitution.api import (
                    OverrideRequestModel,
                    create_override,
                )

                request = OverrideRequestModel(
                    requester="operator-1",
                    justification="This is a test justification that is at least 50 characters long for testing",
                    risk_assessment="medium",
                    affected_systems=["system1"],
                    rollback_plan="Test rollback plan",
                )
                result = asyncio.run(create_override(request))

                assert result.success is True
                assert result.override_id == "test-uuid"
                assert result.status == "pending"
            except ImportError:
                pytest.skip("FastAPI not installed")


class TestApproveOverrideEndpoint:
    """Tests for approve override endpoint."""

    @pytest.fixture
    def mock_audit_logger(self):
        """Create a mock audit logger."""
        mock = MagicMock()
        mock_request = MagicMock()
        mock_request.status = MagicMock()
        mock_request.status.value = "approved"
        mock.approve_request.return_value = mock_request
        return mock

    def test_approve_override_success(self, mock_audit_logger):
        """Test successful override approval."""
        with patch(
            "src.governance.constitution.api.get_audit_logger",
            return_value=mock_audit_logger,
        ):
            try:
                import asyncio

                from src.governance.constitution.api import (
                    ApproveOverrideRequest,
                    approve_override,
                )

                request = ApproveOverrideRequest(approver="admin-1")
                result = asyncio.run(approve_override("test-uuid", request))

                assert result.success is True
                assert result.status == "approved"
            except ImportError:
                pytest.skip("FastAPI not installed")


class TestGetAuditLogEndpoint:
    """Tests for get audit log endpoint."""

    @pytest.fixture
    def mock_audit_logger(self):
        """Create a mock audit logger."""
        mock = MagicMock()
        mock.get_audit_trail.return_value = [
            {
                "event": "override_requested",
                "timestamp": "2026-02-22T00:00:00",
                "override_id": "test-uuid",
                "request": {},
            }
        ]
        return mock

    def test_get_audit_log_success(self, mock_audit_logger):
        """Test successful audit log retrieval."""
        with patch(
            "src.governance.constitution.api.get_audit_logger",
            return_value=mock_audit_logger,
        ):
            try:
                import asyncio

                from src.governance.constitution.api import get_audit_log

                result = asyncio.run(get_audit_log())

                assert result.success is True
                assert result.count == 1
                assert len(result.entries) == 1
            except ImportError:
                pytest.skip("FastAPI not installed")


class TestListVersionsEndpoint:
    """Tests for list versions endpoint."""

    def test_list_versions_success(self):
        """Test successful version listing."""
        with patch(
            "src.governance.constitution.api.ConstitutionLoader.list_versions",
            return_value=[
                MagicMock(__str__=MagicMock(return_value="2.0.0")),
                MagicMock(__str__=MagicMock(return_value="1.0.0")),
            ],
        ):
            try:
                import asyncio

                from src.governance.constitution.api import list_versions

                result = asyncio.run(list_versions())

                assert result["success"] is True
                assert result["data"]["count"] == 2
                assert result["data"]["latest"] == "2.0.0"
            except ImportError:
                pytest.skip("FastAPI not installed")


class TestGetInvariantsEndpoint:
    """Tests for get invariants endpoint."""

    @pytest.fixture
    def mock_constitution(self):
        """Create a mock constitution."""
        mock = MagicMock()
        mock.safety_invariants = {
            "hard_constraints": [
                MagicMock(to_dict=MagicMock(return_value={"id": "INV-001"}))
            ]
        }
        mock.conditional_invariants = [
            MagicMock(to_dict=MagicMock(return_value={"id": "CINV-001"}))
        ]
        return mock

    def test_get_invariants_success(self, mock_constitution):
        """Test successful invariants retrieval."""
        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_constitution
        with patch(
            "src.governance.constitution.api.get_loader",
            return_value=mock_loader,
        ):
            try:
                import asyncio

                from src.governance.constitution.api import get_invariants

                result = asyncio.run(get_invariants())

                assert result["success"] is True
                assert "data" in result
            except ImportError:
                pytest.skip("FastAPI not installed")


class TestRouter:
    """Tests for API router."""

    def test_router_creation(self):
        """Test router creation."""
        try:
            from src.governance.constitution.api import create_router

            router = create_router()
            assert router is not None
            assert router.prefix == "/api/v1/constitution"
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestErrorHandling:
    """Tests for error handling."""

    def test_http_exception_handler(self):
        """Test HTTP exception handler."""
        try:
            from fastapi import HTTPException
            from fastapi.responses import JSONResponse
            from src.governance.constitution.api import http_exception_handler

            # Create a mock request
            mock_request = MagicMock()
            exc = HTTPException(status_code=404, detail="Not found")

            import asyncio

            result = asyncio.run(http_exception_handler(mock_request, exc))

            assert isinstance(result, JSONResponse)
            assert result.status_code == 404
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_general_exception_handler(self):
        """Test general exception handler."""
        try:
            from fastapi.responses import JSONResponse
            from src.governance.constitution.api import general_exception_handler

            # Create a mock request
            mock_request = MagicMock()
            exc = Exception("Test error")

            import asyncio

            result = asyncio.run(general_exception_handler(mock_request, exc))

            assert isinstance(result, JSONResponse)
            assert result.status_code == 500
        except ImportError:
            pytest.skip("FastAPI not installed")
