"""Tests for Conflict Detector module (ST-GOV-003)."""

from unittest.mock import MagicMock

from src.governance.sentinel.conflict_detector import (
    Conflict,
    ConflictCheckResult,
    ConflictDetector,
    ConflictSeverity,
    ConflictType,
    ScopeDeclaration,
)


class TestConflictType:
    """Tests for ConflictType enum."""

    def test_conflict_types(self):
        """Test all conflict types are defined."""
        assert ConflictType.SCOPE_OVERLAP == "scope_overlap"
        assert ConflictType.SHARED_RESOURCE == "shared_resource"
        assert ConflictType.DATA_RACE == "data_race"
        assert ConflictType.DEPENDENCY_CONFLICT == "dependency_conflict"
        assert ConflictType.GLOBAL_LOCK == "global_lock"


class TestConflictSeverity:
    """Tests for ConflictSeverity enum."""

    def test_severity_levels(self):
        """Test all severity levels are defined."""
        assert ConflictSeverity.CRITICAL == "critical"
        assert ConflictSeverity.WARNING == "warning"
        assert ConflictSeverity.INFO == "info"


class TestScopeDeclaration:
    """Tests for ScopeDeclaration dataclass."""

    def test_scope_declaration_creation(self):
        """Test creating a ScopeDeclaration."""
        scope = ScopeDeclaration(
            task_id="ST-001",
            scope_globs=["src/api/**/*.py"],
            read_only_globs=["src/core/config.py"],
            forbidden_globs=["src/db/migrations/"],
            shared_resources=["redis"],
            global_locks=["main-merge"],
        )

        assert scope.task_id == "ST-001"
        assert scope.scope_globs == ["src/api/**/*.py"]
        assert scope.read_only_globs == ["src/core/config.py"]
        assert scope.forbidden_globs == ["src/db/migrations/"]
        assert scope.shared_resources == ["redis"]
        assert scope.global_locks == ["main-merge"]

    def test_scope_declaration_defaults(self):
        """Test ScopeDeclaration with default values."""
        scope = ScopeDeclaration(task_id="ST-002")

        assert scope.scope_globs == []
        assert scope.read_only_globs == []
        assert scope.forbidden_globs == []
        assert scope.shared_resources == []
        assert scope.global_locks == []


class TestConflict:
    """Tests for Conflict dataclass."""

    def test_conflict_creation(self):
        """Test creating a Conflict."""
        conflict = Conflict(
            conflict_type=ConflictType.SCOPE_OVERLAP,
            severity=ConflictSeverity.CRITICAL,
            task_ids=["ST-001", "ST-002"],
            description="Overlapping scopes",
            affected_paths=["src/api/routes.py"],
            affected_resources=[],
            resolution_hint="Run sequentially",
        )

        assert conflict.conflict_type == ConflictType.SCOPE_OVERLAP
        assert conflict.severity == ConflictSeverity.CRITICAL
        assert len(conflict.task_ids) == 2


class TestConflictDetector:
    """Tests for ConflictDetector class."""

    def test_initialization(self):
        """Test detector initialization."""
        detector = ConflictDetector()
        assert detector.redis_client is None
        assert detector._registered_scopes == {}

    def test_initialization_with_redis(self):
        """Test detector with Redis client."""
        mock_redis = MagicMock()
        detector = ConflictDetector(redis_client=mock_redis)
        assert detector.redis_client == mock_redis

    def test_register_scope(self):
        """Test registering a scope."""
        detector = ConflictDetector()
        scope = ScopeDeclaration(task_id="ST-001", scope_globs=["src/a/**/*.py"])
        detector.register_scope(scope)

        assert "ST-001" in detector._registered_scopes

    def test_detect_no_conflicts(self):
        """Test detecting no conflicts between separate scopes."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", scope_globs=["src/a/**/*.py"]),
            ScopeDeclaration(task_id="ST-002", scope_globs=["src/b/**/*.py"]),
        ]

        result = detector.detect_conflicts(scopes)

        assert isinstance(result, ConflictCheckResult)
        assert result.has_conflicts is False
        assert result.has_critical_conflicts is False
        assert result.safe_for_parallel is True

    def test_detect_scope_overlap_same_file(self):
        """Test detecting overlap with same file."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", scope_globs=["src/api/routes.py"]),
            ScopeDeclaration(task_id="ST-002", scope_globs=["src/api/routes.py"]),
        ]

        result = detector.detect_conflicts(scopes)

        assert result.has_conflicts is True
        assert result.has_critical_conflicts is True
        assert result.safe_for_parallel is False
        assert any(
            c.conflict_type == ConflictType.SCOPE_OVERLAP for c in result.conflicts
        )

    def test_detect_scope_overlap_glob_pattern(self):
        """Test detecting overlap with glob patterns."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", scope_globs=["src/api/**/*.py"]),
            ScopeDeclaration(task_id="ST-002", scope_globs=["src/api/routes.py"]),
        ]

        result = detector.detect_conflicts(scopes)

        assert result.has_conflicts is True
        assert result.has_critical_conflicts is True

    def test_detect_shared_resource_conflict(self):
        """Test detecting shared resource conflicts."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", shared_resources=["redis", "postgres"]),
            ScopeDeclaration(task_id="ST-002", shared_resources=["redis"]),
        ]

        result = detector.detect_conflicts(scopes)

        assert result.has_conflicts is True
        assert any(
            c.conflict_type == ConflictType.SHARED_RESOURCE for c in result.conflicts
        )

    def test_detect_global_lock_conflict(self):
        """Test detecting global lock conflicts."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", global_locks=["main-merge"]),
            ScopeDeclaration(task_id="ST-002", global_locks=["main-merge"]),
        ]

        result = detector.detect_conflicts(scopes)

        assert result.has_conflicts is True
        assert result.has_critical_conflicts is True
        assert any(
            c.conflict_type == ConflictType.GLOBAL_LOCK for c in result.conflicts
        )

    def test_detect_forbidden_scope_violation(self):
        """Test detecting forbidden scope violation."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", scope_globs=["src/db/models.py"]),
            ScopeDeclaration(
                task_id="ST-002",
                scope_globs=["src/api/**/*.py"],
                forbidden_globs=["src/db/models.py"],
            ),
        ]

        result = detector.detect_conflicts(scopes)

        # ST-001 touches ST-002's forbidden scope
        assert result.has_conflicts is True

    def test_paths_overlap_direct_match(self):
        """Test path overlap with direct match."""
        detector = ConflictDetector()

        assert detector._paths_overlap("src/api/routes.py", "src/api/routes.py") is True

    def test_paths_overlap_glob(self):
        """Test path overlap with glob pattern."""
        detector = ConflictDetector()

        assert detector._paths_overlap("src/api/routes.py", "src/api/**/*.py") is True
        assert detector._paths_overlap("src/api/**/*.py", "src/api/routes.py") is True

    def test_paths_no_overlap(self):
        """Test paths that don't overlap."""
        detector = ConflictDetector()

        assert detector._paths_overlap("src/a/file.py", "src/b/file.py") is False
        assert detector._paths_overlap("src/api/**/*.py", "src/db/**/*.py") is False

    def test_get_suggested_order_no_conflicts(self):
        """Test suggested order with no conflicts."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", scope_globs=["src/a/**/*.py"]),
            ScopeDeclaration(task_id="ST-002", scope_globs=["src/b/**/*.py"]),
        ]

        order = detector.get_suggested_order(scopes)
        assert len(order) == 2

    def test_get_suggested_order_with_conflicts(self):
        """Test suggested order with conflicts."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", scope_globs=["src/api/routes.py"]),
            ScopeDeclaration(task_id="ST-002", scope_globs=["src/api/routes.py"]),
        ]

        order = detector.get_suggested_order(scopes)
        assert len(order) == 2  # Both still in order, just sequential

    def test_check_redis_ownership_without_redis(self):
        """Test ownership check without Redis."""
        detector = ConflictDetector()

        ownership = detector.check_redis_ownership(["src/api/**/*.py"])
        assert ownership == {}

    def test_check_redis_ownership_with_redis(self):
        """Test ownership check with Redis."""
        mock_redis = MagicMock()
        mock_redis.hget.return_value = b"ST-OTHER/agent/2024-01-01T00:00:00Z"
        detector = ConflictDetector(redis_client=mock_redis)

        ownership = detector.check_redis_ownership(["src/api/routes.py"])

        assert "src/api/routes.py" in ownership
        assert "ST-OTHER" in ownership["src/api/routes.py"]

    def test_check_redis_ownership_no_owner(self):
        """Test ownership check when no owner exists."""
        mock_redis = MagicMock()
        mock_redis.hget.return_value = None
        detector = ConflictDetector(redis_client=mock_redis)

        ownership = detector.check_redis_ownership(["src/api/**/*.py"])
        assert ownership == {}

    def test_clear(self):
        """Test clearing the detector."""
        detector = ConflictDetector()
        detector.register_scope(ScopeDeclaration(task_id="ST-001"))

        assert len(detector._registered_scopes) == 1

        detector.clear()
        assert len(detector._registered_scopes) == 0


class TestConflictCheckResult:
    """Tests for ConflictCheckResult."""

    def test_result_creation(self):
        """Test creating a result."""
        result = ConflictCheckResult(
            has_conflicts=False,
            has_critical_conflicts=False,
            conflicts=[],
            safe_for_parallel=True,
            message="No conflicts detected",
        )
        assert result.has_conflicts is False
        assert result.safe_for_parallel is True

    def test_result_with_conflicts(self):
        """Test result with conflicts."""
        conflict = Conflict(
            conflict_type=ConflictType.SCOPE_OVERLAP,
            severity=ConflictSeverity.CRITICAL,
            task_ids=["ST-001", "ST-002"],
            description="Overlapping scopes",
            affected_paths=["src/api/routes.py"],
            affected_resources=[],
        )

        result = ConflictCheckResult(
            has_conflicts=True,
            has_critical_conflicts=True,
            conflicts=[conflict],
            safe_for_parallel=False,
            message="1 conflict(s), 1 critical",
        )

        assert result.has_conflicts is True
        assert result.has_critical_conflicts is True
        assert len(result.conflicts) == 1
        assert result.safe_for_parallel is False


class TestDockerGovernanceIntegration:
    """Tests for Docker governance integration."""

    def test_docker_resource_conflict_critical(self):
        """Test that Docker conflicts are critical."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", shared_resources=["docker"]),
            ScopeDeclaration(task_id="ST-002", shared_resources=["docker"]),
        ]

        result = detector.detect_conflicts(scopes)

        docker_conflicts = [
            c for c in result.conflicts if "docker" in c.affected_resources
        ]
        assert len(docker_conflicts) > 0
        assert all(c.severity == ConflictSeverity.CRITICAL for c in docker_conflicts)

    def test_kubernetes_resource_conflict_critical(self):
        """Test that Kubernetes conflicts are critical."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", shared_resources=["kubernetes"]),
            ScopeDeclaration(task_id="ST-002", shared_resources=["kubernetes"]),
        ]

        result = detector.detect_conflicts(scopes)

        k8s_conflicts = [
            c for c in result.conflicts if "kubernetes" in c.affected_resources
        ]
        assert len(k8s_conflicts) > 0
        assert all(c.severity == ConflictSeverity.CRITICAL for c in k8s_conflicts)

    def test_redis_postgres_warning_only(self):
        """Test that Redis/Postgres conflicts are warnings."""
        detector = ConflictDetector()
        scopes = [
            ScopeDeclaration(task_id="ST-001", shared_resources=["redis"]),
            ScopeDeclaration(task_id="ST-002", shared_resources=["redis"]),
        ]

        result = detector.detect_conflicts(scopes)

        redis_conflicts = [
            c for c in result.conflicts if "redis" in c.affected_resources
        ]
        # Redis conflicts are warnings, not critical
        assert all(c.severity == ConflictSeverity.WARNING for c in redis_conflicts)
        # Safe for parallel is True because no critical conflicts
        assert result.safe_for_parallel is True
