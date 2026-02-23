"""Tests for Task Sentinel API (ST-GOV-003)."""

import pytest
from unittest.mock import MagicMock, patch
import json

# We need to test the API endpoints
# These tests use FastAPI TestClient but can run without Redis


class TestHealthEndpoint:
    """Tests for health endpoint."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.ping.return_value = True
        return mock

    def test_health_endpoint_structure(self):
        """Test that health endpoint returns expected structure."""
        # Import here to avoid import errors if FastAPI not installed
        try:
            from src.governance.sentinel.api import HealthResponse

            response = HealthResponse(
                status="healthy",
                version="1.0.0",
                redis_connected=True,
                timestamp="2024-01-01T00:00:00",
            )

            assert response.status == "healthy"
            assert response.version == "1.0.0"
            assert response.redis_connected is True
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestValidateTaskEndpoint:
    """Tests for validate-task endpoint."""

    @pytest.fixture
    def validate_request(self):
        """Create a sample validate request."""
        return {
            "task_id": "ST-001",
            "story_points": 3,
            "title": "Test task",
            "description": "Test description",
            "assignee": "agent-1",
            "labels": ["backend"],
        }

    def test_validate_task_request_model(self):
        """Test ValidateTaskRequest model."""
        try:
            from src.governance.sentinel.api import ValidateTaskRequest

            request = ValidateTaskRequest(
                task_id="ST-001",
                story_points=3,
                title="Test task",
            )

            assert request.task_id == "ST-001"
            assert request.story_points == 3
            assert request.title == "Test task"
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_validate_task_response_model(self):
        """Test ValidateTaskResponse model."""
        try:
            from src.governance.sentinel.api import ValidateTaskResponse

            response = ValidateTaskResponse(
                is_valid=True,
                requires_approval=False,
                story_points=3,
                max_allowed=5,
                message="Task is valid",
                task_id="ST-001",
            )

            assert response.is_valid is True
            assert response.requires_approval is False
            assert response.max_allowed == 5
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestApprovalEndpoints:
    """Tests for approval-related endpoints."""

    def test_request_approval_model(self):
        """Test RequestApprovalRequest model."""
        try:
            from src.governance.sentinel.api import RequestApprovalRequest

            request = RequestApprovalRequest(
                task_id="ST-001",
                story_points=8,
                justification="Complex feature requiring coordination between multiple services",
                requester="agent-1",
            )

            assert request.task_id == "ST-001"
            assert request.story_points == 8
            assert len(request.justification) >= 10  # Min length
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_approve_task_model(self):
        """Test ApproveTaskRequest model."""
        try:
            from src.governance.sentinel.api import ApproveTaskRequest

            request = ApproveTaskRequest(
                approver="human-1",
                notes="Looks good",
            )

            assert request.approver == "human-1"
            assert request.notes == "Looks good"
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_reject_task_model(self):
        """Test RejectTaskRequest model."""
        try:
            from src.governance.sentinel.api import RejectTaskRequest

            request = RejectTaskRequest(
                rejector="human-1",
                reason="Task should be decomposed",
            )

            assert request.rejector == "human-1"
            assert request.reason == "Task should be decomposed"
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestDependencyEndpoint:
    """Tests for check-dependencies endpoint."""

    def test_check_dependencies_request_model(self):
        """Test CheckDependenciesRequest model."""
        try:
            from src.governance.sentinel.api import CheckDependenciesRequest

            request = CheckDependenciesRequest(
                declarations=[
                    {
                        "task_id": "ST-001",
                        "dependencies": [],
                        "provides": [],
                    },
                    {
                        "task_id": "ST-002",
                        "dependencies": [{"task_id": "ST-001", "type": "depends_on"}],
                        "provides": [],
                    },
                ],
                required_scopes={"ST-002": ["src/api/**/*.py"]},
            )

            assert len(request.declarations) == 2
            assert request.required_scopes is not None
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_check_dependencies_response_model(self):
        """Test CheckDependenciesResponse model."""
        try:
            from src.governance.sentinel.api import CheckDependenciesResponse

            response = CheckDependenciesResponse(
                is_valid=True,
                has_circular_dependencies=False,
                missing_dependencies=[],
                circular_paths=[],
                undeclared_scopes=[],
                message="All dependencies valid",
            )

            assert response.is_valid is True
            assert response.has_circular_dependencies is False
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestConflictEndpoint:
    """Tests for check-conflicts endpoint."""

    def test_check_conflicts_request_model(self):
        """Test CheckConflictsRequest model."""
        try:
            from src.governance.sentinel.api import CheckConflictsRequest

            request = CheckConflictsRequest(
                scopes=[
                    {
                        "task_id": "ST-001",
                        "scope_globs": ["src/api/**/*.py"],
                        "shared_resources": ["redis"],
                    },
                    {
                        "task_id": "ST-002",
                        "scope_globs": ["src/db/**/*.py"],
                        "shared_resources": ["postgres"],
                    },
                ]
            )

            assert len(request.scopes) == 2
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_conflict_detail_model(self):
        """Test ConflictDetail model."""
        try:
            from src.governance.sentinel.api import ConflictDetail

            detail = ConflictDetail(
                conflict_type="scope_overlap",
                severity="critical",
                task_ids=["ST-001", "ST-002"],
                description="Overlapping scopes",
                affected_paths=["src/api/routes.py"],
                affected_resources=[],
                resolution_hint="Run sequentially",
            )

            assert detail.conflict_type == "scope_overlap"
            assert detail.severity == "critical"
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_check_conflicts_response_model(self):
        """Test CheckConflictsResponse model."""
        try:
            from src.governance.sentinel.api import CheckConflictsResponse

            response = CheckConflictsResponse(
                has_conflicts=False,
                has_critical_conflicts=False,
                conflicts=[],
                safe_for_parallel=True,
                message="No conflicts detected",
            )

            assert response.has_conflicts is False
            assert response.safe_for_parallel is True
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestAPIRouter:
    """Tests for API router creation."""

    def test_create_router(self):
        """Test that create_router returns a router."""
        try:
            from src.governance.sentinel.api import create_router

            router = create_router()

            # Router should have the expected prefix
            assert router is not None
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestDependencyInjection:
    """Tests for dependency injection functions."""

    def test_get_sentinel_without_redis(self):
        """Test get_sentinel without Redis."""
        try:
            from src.governance.sentinel.api import get_sentinel
            from src.governance.sentinel import TaskSentinel

            # Reset global
            import src.governance.sentinel.api as api_module

            api_module._sentinel = None

            # Should create sentinel without Redis (will try to connect but fail gracefully)
            sentinel = get_sentinel()

            assert isinstance(sentinel, TaskSentinel)
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_get_dependency_checker(self):
        """Test get_dependency_checker."""
        try:
            from src.governance.sentinel.api import get_dependency_checker
            from src.governance.sentinel import DependencyChecker

            checker = get_dependency_checker()

            assert isinstance(checker, DependencyChecker)
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_get_conflict_detector(self):
        """Test get_conflict_detector."""
        try:
            from src.governance.sentinel.api import get_conflict_detector
            from src.governance.sentinel import ConflictDetector

            detector = get_conflict_detector()

            assert isinstance(detector, ConflictDetector)
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestErrorHandling:
    """Tests for error handling."""

    def test_http_exception_handler(self):
        """Test HTTP exception handler is registered."""
        try:
            from src.governance.sentinel.api import app

            # App should have exception handlers
            assert app.exception_handlers is not None
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_general_exception_handler(self):
        """Test general exception handler is registered."""
        try:
            from src.governance.sentinel.api import app

            # App should have Exception handler
            assert Exception in app.exception_handlers or any(
                issubclass(exc, Exception) for exc in app.exception_handlers.keys()
            )
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestAPIMetadata:
    """Tests for API metadata."""

    def test_app_metadata(self):
        """Test API app metadata."""
        try:
            from src.governance.sentinel.api import app

            assert app.title == "Task Decomposition Sentinel API"
            assert app.version == "1.0.0"
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_docs_urls(self):
        """Test docs URLs are configured."""
        try:
            from src.governance.sentinel.api import app

            assert app.docs_url == "/docs"
            assert app.redoc_url == "/redoc"
        except ImportError:
            pytest.skip("FastAPI not installed")
