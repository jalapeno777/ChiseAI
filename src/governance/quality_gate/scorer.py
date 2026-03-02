"""Quality Scoring Algorithm for Self-Review.

Implements a weighted scoring system for code quality assessment.

Quality Score Components:
- Code style (black/ruff compliance) - 20%
- Test coverage - 25%
- Security scan (bandit) - 20%
- Constitution alignment - 20%
- Documentation completeness - 15%

For ST-GOV-006: Self-Review Quality Gate
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ScoreComponent(str, Enum):
    """Quality score component identifiers."""

    CODE_STYLE = "code_style"
    TEST_COVERAGE = "test_coverage"
    SECURITY = "security"
    CONSTITUTION = "constitution"
    DOCUMENTATION = "documentation"


# Component weights (must sum to 1.0)
COMPONENT_WEIGHTS: dict[ScoreComponent, float] = {
    ScoreComponent.CODE_STYLE: 0.20,
    ScoreComponent.TEST_COVERAGE: 0.25,
    ScoreComponent.SECURITY: 0.20,
    ScoreComponent.CONSTITUTION: 0.20,
    ScoreComponent.DOCUMENTATION: 0.15,
}


@dataclass
class ComponentScore:
    """Score for an individual component."""

    component: ScoreComponent
    score: float  # 0.0 to 1.0
    weight: float
    details: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "component": self.component.value,
            "score": self.score,
            "weight": self.weight,
            "weighted_score": self.score * self.weight,
            "details": self.details,
            "issues": self.issues,
            "passed": self.passed,
        }


@dataclass
class QualityScore:
    """Aggregated quality score result."""

    overall_score: float  # 0.0 to 1.0
    component_scores: dict[ScoreComponent, ComponentScore]
    passed: bool
    threshold: float
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    file_count: int = 0
    line_count: int = 0
    pr_number: int | None = None
    branch: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "overall_score": round(self.overall_score, 4),
            "overall_percentage": round(self.overall_score * 100, 2),
            "passed": self.passed,
            "threshold": self.threshold,
            "threshold_percentage": round(self.threshold * 100, 2),
            "calculated_at": self.calculated_at.isoformat(),
            "file_count": self.file_count,
            "line_count": self.line_count,
            "pr_number": self.pr_number,
            "branch": self.branch,
            "component_scores": {
                k.value: v.to_dict() for k, v in self.component_scores.items()
            },
        }

    def get_failing_components(self) -> list[ScoreComponent]:
        """Get list of components that are below acceptable threshold."""
        return [
            comp
            for comp, score in self.component_scores.items()
            if not score.passed or score.score < 0.5
        ]


class QualityScorer:
    """Calculates quality scores for code changes."""

    def __init__(
        self,
        passing_threshold: float = 0.80,
        component_thresholds: dict[ScoreComponent, float] | None = None,
    ):
        """Initialize the quality scorer.

        Args:
            passing_threshold: Overall threshold for passing (default 80%)
            component_thresholds: Per-component thresholds (default 50% each)
        """
        self.passing_threshold = passing_threshold
        self.component_thresholds = component_thresholds or {
            comp: 0.50 for comp in ScoreComponent
        }
        # Security has higher minimum threshold
        self.component_thresholds[ScoreComponent.SECURITY] = 0.70

    def calculate_score(
        self,
        changed_files: list[str],
        pr_number: int | None = None,
        branch: str | None = None,
        repo_path: str | Path = ".",
    ) -> QualityScore:
        """Calculate the overall quality score.

        Args:
            changed_files: List of changed file paths
            pr_number: Optional PR number
            branch: Optional branch name
            repo_path: Path to repository root

        Returns:
            QualityScore with overall and component scores
        """
        repo_path = Path(repo_path)

        # Calculate file/line counts
        file_count, line_count = self._count_changes(changed_files, repo_path)

        # Calculate each component score
        component_scores: dict[ScoreComponent, ComponentScore] = {}

        component_scores[ScoreComponent.CODE_STYLE] = self._score_code_style(
            changed_files, repo_path
        )
        component_scores[ScoreComponent.TEST_COVERAGE] = self._score_test_coverage(
            changed_files, repo_path
        )
        component_scores[ScoreComponent.SECURITY] = self._score_security(
            changed_files, repo_path
        )
        component_scores[ScoreComponent.CONSTITUTION] = self._score_constitution(
            changed_files, repo_path
        )
        component_scores[ScoreComponent.DOCUMENTATION] = self._score_documentation(
            changed_files, repo_path
        )

        # Calculate weighted overall score
        overall_score = sum(
            score.score * COMPONENT_WEIGHTS[comp]
            for comp, score in component_scores.items()
        )

        # Determine pass/fail
        passed = overall_score >= self.passing_threshold

        return QualityScore(
            overall_score=overall_score,
            component_scores=component_scores,
            passed=passed,
            threshold=self.passing_threshold,
            file_count=file_count,
            line_count=line_count,
            pr_number=pr_number,
            branch=branch,
        )

    def _count_changes(
        self, changed_files: list[str], repo_path: Path
    ) -> tuple[int, int]:
        """Count files and lines changed."""
        file_count = len(changed_files)
        line_count = 0

        for file_path in changed_files:
            full_path = repo_path / file_path
            if full_path.exists() and full_path.is_file():
                try:
                    with open(full_path) as f:
                        line_count += sum(1 for _ in f)
                except Exception:
                    pass

        return file_count, line_count

    def _score_code_style(
        self, changed_files: list[str], repo_path: Path
    ) -> ComponentScore:
        """Score code style compliance (black/ruff)."""
        python_files = [f for f in changed_files if f.endswith(".py")]

        if not python_files:
            return ComponentScore(
                component=ScoreComponent.CODE_STYLE,
                score=1.0,
                weight=COMPONENT_WEIGHTS[ScoreComponent.CODE_STYLE],
                details={"message": "No Python files to check"},
                passed=True,
            )

        issues: list[str] = []
        score = 1.0

        # Check black compliance
        try:
            result = subprocess.run(  # nosec B607
                ["black", "--check", *python_files],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=60,
            )
            if result.returncode != 0:
                issues.append("Black formatting issues detected")
                score -= 0.3
        except FileNotFoundError:
            issues.append("Black not installed - skipping check")
        except subprocess.TimeoutExpired:
            issues.append("Black check timed out")
            score -= 0.1
        except Exception as e:
            logger.warning(f"Black check failed: {e}")

        # Check ruff compliance
        try:
            result = subprocess.run(  # nosec B607
                ["ruff", "check", *python_files],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=60,
            )
            if result.returncode != 0:
                # Count issues for scoring
                issue_count = len(result.stdout.strip().split("\n"))
                penalty = min(0.5, issue_count * 0.05)
                score -= penalty
                issues.append(f"Ruff found {issue_count} linting issues")
        except FileNotFoundError:
            issues.append("Ruff not installed - skipping check")
        except subprocess.TimeoutExpired:
            issues.append("Ruff check timed out")
            score -= 0.1
        except Exception as e:
            logger.warning(f"Ruff check failed: {e}")

        score = max(0.0, score)
        passed = score >= self.component_thresholds[ScoreComponent.CODE_STYLE]

        return ComponentScore(
            component=ScoreComponent.CODE_STYLE,
            score=score,
            weight=COMPONENT_WEIGHTS[ScoreComponent.CODE_STYLE],
            details={
                "files_checked": len(python_files),
            },
            issues=issues,
            passed=passed,
        )

    def _score_test_coverage(
        self, changed_files: list[str], repo_path: Path
    ) -> ComponentScore:
        """Score test coverage."""
        python_files = [
            f for f in changed_files if f.endswith(".py") and "test_" not in f
        ]

        if not python_files:
            return ComponentScore(
                component=ScoreComponent.TEST_COVERAGE,
                score=1.0,
                weight=COMPONENT_WEIGHTS[ScoreComponent.TEST_COVERAGE],
                details={"message": "No source files to check coverage"},
                passed=True,
            )

        issues: list[str] = []
        score = 0.0

        # Check if corresponding test files exist
        tested_files = 0
        for src_file in python_files:
            # Derive test file path
            test_file = src_file.replace("src/", "tests/").replace(".py", "_test.py")
            alt_test_file = src_file.replace("src/", "tests/test_").replace(
                ".py", ".py"
            )

            if (repo_path / test_file).exists() or (repo_path / alt_test_file).exists():
                tested_files += 1

        coverage_ratio = tested_files / len(python_files) if python_files else 1.0

        # Try running pytest coverage if available
        try:
            result = subprocess.run(  # nosec B607
                ["pytest", "--cov=src", "--cov-report=json", "-q"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=120,
            )
            if result.returncode == 0 or "coverage" in result.stdout.lower():
                # Parse coverage from JSON report
                cov_file = repo_path / "coverage.json"
                if cov_file.exists():
                    try:
                        with open(cov_file) as f:
                            cov_data = json.load(f)
                            score = (
                                cov_data.get("totals", {}).get("percent_covered", 0)
                                / 100
                            )
                    except Exception:
                        score = coverage_ratio * 0.8
                else:
                    score = coverage_ratio * 0.8
            else:
                score = coverage_ratio * 0.6
                issues.append("Test suite has failures")
        except FileNotFoundError:
            # Pytest not available, use heuristic
            score = coverage_ratio * 0.7
            issues.append("Pytest not available - using heuristic coverage")
        except subprocess.TimeoutExpired:
            score = coverage_ratio * 0.5
            issues.append("Test coverage check timed out")
        except Exception as e:
            logger.warning(f"Coverage check failed: {e}")
            score = coverage_ratio * 0.5

        score = max(0.0, min(1.0, score))
        passed = score >= self.component_thresholds[ScoreComponent.TEST_COVERAGE]

        return ComponentScore(
            component=ScoreComponent.TEST_COVERAGE,
            score=score,
            weight=COMPONENT_WEIGHTS[ScoreComponent.TEST_COVERAGE],
            details={
                "source_files": len(python_files),
                "files_with_tests": tested_files,
                "heuristic_coverage": round(coverage_ratio * 100, 1),
            },
            issues=issues,
            passed=passed,
        )

    def _score_security(
        self, changed_files: list[str], repo_path: Path
    ) -> ComponentScore:
        """Score security compliance (bandit)."""
        python_files = [f for f in changed_files if f.endswith(".py")]

        if not python_files:
            return ComponentScore(
                component=ScoreComponent.SECURITY,
                score=1.0,
                weight=COMPONENT_WEIGHTS[ScoreComponent.SECURITY],
                details={"message": "No Python files to check"},
                passed=True,
            )

        issues: list[str] = []
        score = 1.0

        # Run bandit security check
        try:
            result = subprocess.run(  # nosec B607
                ["bandit", "-r", "-f", "json", *python_files],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=60,
            )

            if result.returncode != 0:
                try:
                    findings = json.loads(result.stdout)
                    high_severity = len(
                        [
                            r
                            for r in findings.get("results", [])
                            if r.get("issue_severity") == "HIGH"
                        ]
                    )
                    medium_severity = len(
                        [
                            r
                            for r in findings.get("results", [])
                            if r.get("issue_severity") == "MEDIUM"
                        ]
                    )

                    # Deduct points for issues
                    score -= high_severity * 0.3
                    score -= medium_severity * 0.1

                    if high_severity > 0:
                        issues.append(
                            f"Bandit found {high_severity} HIGH severity issues"
                        )
                    if medium_severity > 0:
                        issues.append(
                            f"Bandit found {medium_severity} MEDIUM severity issues"
                        )
                except json.JSONDecodeError:
                    issues.append("Failed to parse bandit output")
                    score -= 0.2
        except FileNotFoundError:
            issues.append("Bandit not installed - skipping security check")
        except subprocess.TimeoutExpired:
            issues.append("Security scan timed out")
            score -= 0.2
        except Exception as e:
            logger.warning(f"Security check failed: {e}")

        score = max(0.0, score)
        passed = score >= self.component_thresholds[ScoreComponent.SECURITY]

        return ComponentScore(
            component=ScoreComponent.SECURITY,
            score=score,
            weight=COMPONENT_WEIGHTS[ScoreComponent.SECURITY],
            details={
                "files_scanned": len(python_files),
            },
            issues=issues,
            passed=passed,
        )

    def _score_constitution(
        self, changed_files: list[str], repo_path: Path
    ) -> ComponentScore:
        """Score constitution alignment."""
        score = 1.0
        issues: list[str] = []

        # Check for scope violations
        for file_path in changed_files:
            # Check for forbidden paths
            if any(
                forbidden in file_path
                for forbidden in [".woodpecker.yml", "terraform/", "secrets/", ".env"]
            ):
                score -= 0.3
                issues.append(f"File may violate scope boundaries: {file_path}")

        # Check for proper module structure
        src_files = [f for f in changed_files if f.startswith("src/")]
        if src_files:
            proper_structure = all("/" in f[len("src/") :] for f in src_files)
            if not proper_structure:
                score -= 0.1
                issues.append("Some files may not follow module structure")

        score = max(0.0, score)
        passed = score >= self.component_thresholds[ScoreComponent.CONSTITUTION]

        return ComponentScore(
            component=ScoreComponent.CONSTITUTION,
            score=score,
            weight=COMPONENT_WEIGHTS[ScoreComponent.CONSTITUTION],
            details={
                "files_checked": len(changed_files),
            },
            issues=issues,
            passed=passed,
        )

    def _score_documentation(
        self, changed_files: list[str], repo_path: Path
    ) -> ComponentScore:
        """Score documentation completeness."""
        python_files = [f for f in changed_files if f.endswith(".py")]

        if not python_files:
            return ComponentScore(
                component=ScoreComponent.DOCUMENTATION,
                score=1.0,
                weight=COMPONENT_WEIGHTS[ScoreComponent.DOCUMENTATION],
                details={"message": "No Python files to check"},
                passed=True,
            )

        issues: list[str] = []
        doc_score = 0.0

        for file_path in python_files:
            full_path = repo_path / file_path
            if not full_path.exists():
                continue

            try:
                with open(full_path) as f:
                    content = f.read()

                file_score = 0.0

                # Check for module docstring
                if '"""' in content[:100] or "'''" in content[:100]:
                    file_score += 0.3

                # Check for function/class docstrings
                import re

                docstrings = len(
                    re.findall(r'(def|class)\s+\w+[^:]*:\s*\n\s*"""', content)
                )
                definitions = len(re.findall(r"(def|class)\s+\w+", content))

                if definitions > 0:
                    file_score += 0.7 * (docstrings / definitions)

                doc_score += file_score
            except Exception as e:
                logger.warning(f"Failed to check documentation for {file_path}: {e}")

        avg_score = doc_score / len(python_files) if python_files else 1.0
        passed = avg_score >= self.component_thresholds[ScoreComponent.DOCUMENTATION]

        if avg_score < 0.5:
            issues.append("Documentation coverage below 50%")

        return ComponentScore(
            component=ScoreComponent.DOCUMENTATION,
            score=avg_score,
            weight=COMPONENT_WEIGHTS[ScoreComponent.DOCUMENTATION],
            details={
                "files_checked": len(python_files),
            },
            issues=issues,
            passed=passed,
        )
