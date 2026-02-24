"""Tests for Dependency Checker module (ST-GOV-003)."""

import pytest
from src.governance.sentinel.dependency_checker import (
    Dependency,
    DependencyChecker,
    DependencyCheckResult,
    DependencyDeclaration,
    DependencyType,
)


class TestDependencyType:
    """Tests for DependencyType enum."""

    def test_dependency_types(self):
        """Test all dependency types are defined."""
        assert DependencyType.BLOCKS == "blocks"
        assert DependencyType.BLOCKED_BY == "blocked_by"
        assert DependencyType.DEPENDS_ON == "depends_on"
        assert DependencyType.REQUIRES == "requires"


class TestDependency:
    """Tests for Dependency dataclass."""

    def test_dependency_creation(self):
        """Test creating a Dependency."""
        dep = Dependency(
            task_id="ST-001",
            dependency_type=DependencyType.DEPENDS_ON,
            scope_globs=["src/api/**/*.py"],
            description="API dependency",
        )
        assert dep.task_id == "ST-001"
        assert dep.dependency_type == DependencyType.DEPENDS_ON
        assert dep.scope_globs == ["src/api/**/*.py"]
        assert dep.description == "API dependency"

    def test_dependency_defaults(self):
        """Test Dependency with default values."""
        dep = Dependency(
            task_id="ST-002",
            dependency_type=DependencyType.BLOCKS,
        )
        assert dep.scope_globs == []
        assert dep.description is None


class TestDependencyDeclaration:
    """Tests for DependencyDeclaration."""

    def test_from_dict(self):
        """Test creating DependencyDeclaration from dict."""
        data = {
            "task_id": "ST-001",
            "dependencies": [
                {
                    "task_id": "ST-000",
                    "type": "depends_on",
                    "scope_globs": ["src/core/**/*.py"],
                }
            ],
            "provides": ["src/api/routes.py"],
        }
        decl = DependencyDeclaration.from_dict(data)

        assert decl.task_id == "ST-001"
        assert len(decl.dependencies) == 1
        assert decl.dependencies[0].task_id == "ST-000"
        assert decl.provides == ["src/api/routes.py"]

    def test_from_dict_empty(self):
        """Test creating from empty dict."""
        decl = DependencyDeclaration.from_dict({})
        assert decl.task_id == ""
        assert decl.dependencies == []
        assert decl.provides == []

    def test_from_yaml(self):
        """Test parsing from YAML string."""
        yaml_str = """
task_id: ST-002
dependencies:
  - task_id: ST-001
    type: requires
provides:
  - src/api/client.py
"""
        decl = DependencyDeclaration.from_yaml(yaml_str)

        assert decl.task_id == "ST-002"
        assert len(decl.dependencies) == 1
        assert decl.dependencies[0].dependency_type == DependencyType.REQUIRES

    def test_from_json(self):
        """Test parsing from JSON string."""
        json_str = '{"task_id": "ST-003", "dependencies": [], "provides": []}'
        decl = DependencyDeclaration.from_json(json_str)

        assert decl.task_id == "ST-003"


class TestDependencyChecker:
    """Tests for DependencyChecker class."""

    def test_initialization(self):
        """Test checker initialization."""
        checker = DependencyChecker()
        assert checker.known_tasks == {}

    def test_register_task(self):
        """Test registering a task."""
        checker = DependencyChecker()
        decl = DependencyDeclaration(
            task_id="ST-001",
            dependencies=[],
            provides=[],
        )
        checker.register_task(decl)

        assert "ST-001" in checker.known_tasks

    def test_detect_no_circular_dependencies(self):
        """Test detection with no circular dependencies."""
        checker = DependencyChecker()
        declarations = [
            DependencyDeclaration(
                task_id="ST-001",
                dependencies=[
                    Dependency(
                        task_id="ST-000", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
            DependencyDeclaration(
                task_id="ST-002",
                dependencies=[
                    Dependency(
                        task_id="ST-001", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
        ]

        has_cycles, paths = checker.detect_circular_dependencies(declarations)
        assert has_cycles is False
        assert paths == []

    def test_detect_circular_dependencies(self):
        """Test detection of circular dependencies."""
        checker = DependencyChecker()
        declarations = [
            DependencyDeclaration(
                task_id="ST-A",
                dependencies=[
                    Dependency(
                        task_id="ST-B", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
            DependencyDeclaration(
                task_id="ST-B",
                dependencies=[
                    Dependency(
                        task_id="ST-A", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
        ]

        has_cycles, paths = checker.detect_circular_dependencies(declarations)
        assert has_cycles is True
        assert len(paths) > 0

    def test_detect_self_dependency(self):
        """Test detection of self-dependency."""
        checker = DependencyChecker()
        declarations = [
            DependencyDeclaration(
                task_id="ST-SELF",
                dependencies=[
                    Dependency(
                        task_id="ST-SELF", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
        ]

        has_cycles, paths = checker.detect_circular_dependencies(declarations)
        assert has_cycles is True

    def test_check_missing_dependencies(self):
        """Test checking for missing dependencies."""
        checker = DependencyChecker()

        # Register a known task
        checker.register_task(DependencyDeclaration(task_id="ST-KNOWN"))

        # Check a declaration with unknown dependency
        decl = DependencyDeclaration(
            task_id="ST-NEW",
            dependencies=[
                Dependency(
                    task_id="ST-KNOWN", dependency_type=DependencyType.DEPENDS_ON
                ),
                Dependency(
                    task_id="ST-UNKNOWN", dependency_type=DependencyType.DEPENDS_ON
                ),
            ],
        )

        missing = checker.check_missing_dependencies(decl)
        assert "ST-UNKNOWN" in missing
        assert "ST-KNOWN" not in missing

    def test_check_scope_completeness(self):
        """Test checking scope completeness."""
        checker = DependencyChecker()

        decl = DependencyDeclaration(
            task_id="ST-001",
            dependencies=[
                Dependency(
                    task_id="ST-000",
                    dependency_type=DependencyType.DEPENDS_ON,
                    scope_globs=["src/api/**/*.py"],
                )
            ],
        )

        # Required scope that matches declared
        undeclared = checker.check_scope_completeness(decl, ["src/api/routes.py"])
        assert undeclared == []

        # Required scope that doesn't match
        undeclared = checker.check_scope_completeness(decl, ["src/db/models.py"])
        assert "src/db/models.py" in undeclared

    def test_check_dependencies_comprehensive(self):
        """Test comprehensive dependency check."""
        checker = DependencyChecker()
        declarations = [
            DependencyDeclaration(
                task_id="ST-001",
                dependencies=[],
            ),
            DependencyDeclaration(
                task_id="ST-002",
                dependencies=[
                    Dependency(
                        task_id="ST-001", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
        ]

        result = checker.check_dependencies(declarations)

        assert isinstance(result, DependencyCheckResult)
        assert result.is_valid is True
        assert result.has_circular_dependencies is False
        assert result.missing_dependencies == []

    def test_check_dependencies_with_issues(self):
        """Test dependency check with issues."""
        checker = DependencyChecker()
        declarations = [
            DependencyDeclaration(
                task_id="ST-A",
                dependencies=[
                    Dependency(
                        task_id="ST-B", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
            DependencyDeclaration(
                task_id="ST-B",
                dependencies=[
                    Dependency(
                        task_id="ST-A", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
        ]

        result = checker.check_dependencies(declarations)

        assert result.is_valid is False
        assert result.has_circular_dependencies is True

    def test_get_execution_order(self):
        """Test getting execution order."""
        checker = DependencyChecker()
        declarations = [
            DependencyDeclaration(
                task_id="ST-FIRST",
                dependencies=[],
            ),
            DependencyDeclaration(
                task_id="ST-SECOND",
                dependencies=[
                    Dependency(
                        task_id="ST-FIRST", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
            DependencyDeclaration(
                task_id="ST-THIRD",
                dependencies=[
                    Dependency(
                        task_id="ST-SECOND", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
        ]

        # Register all
        for decl in declarations:
            checker.register_task(decl)

        order = checker.get_execution_order()
        assert len(order) == 3

    def test_get_execution_order_with_cycle(self):
        """Test execution order raises error with cycles."""
        checker = DependencyChecker()
        declarations = [
            DependencyDeclaration(
                task_id="ST-A",
                dependencies=[
                    Dependency(
                        task_id="ST-B", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
            DependencyDeclaration(
                task_id="ST-B",
                dependencies=[
                    Dependency(
                        task_id="ST-A", dependency_type=DependencyType.DEPENDS_ON
                    )
                ],
            ),
        ]

        checker.check_dependencies(declarations)

        with pytest.raises(ValueError, match="circular dependencies"):
            checker.get_execution_order()

    def test_clear(self):
        """Test clearing the checker."""
        checker = DependencyChecker()
        checker.register_task(DependencyDeclaration(task_id="ST-001"))

        assert len(checker.known_tasks) == 1

        checker.clear()
        assert len(checker.known_tasks) == 0


class TestDependencyCheckResult:
    """Tests for DependencyCheckResult."""

    def test_result_creation(self):
        """Test creating a result."""
        result = DependencyCheckResult(
            is_valid=True,
            has_circular_dependencies=False,
            missing_dependencies=[],
            circular_paths=[],
            undeclared_scopes=[],
            message="All dependencies valid",
        )
        assert result.is_valid is True
        assert result.has_circular_dependencies is False

    def test_result_with_issues(self):
        """Test result with issues."""
        result = DependencyCheckResult(
            is_valid=False,
            has_circular_dependencies=True,
            missing_dependencies=["ST-UNKNOWN"],
            circular_paths=[["ST-A", "ST-B", "ST-A"]],
            undeclared_scopes=["src/db/**/*.py"],
            message="Circular dependencies detected",
        )
        assert result.is_valid is False
        assert len(result.missing_dependencies) == 1
        assert len(result.circular_paths) == 1
