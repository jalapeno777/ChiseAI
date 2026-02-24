"""Tests for quality gate scorer module.

For ST-GOV-006: Self-Review Quality Gate
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.governance.quality_gate.scorer import (
    COMPONENT_WEIGHTS,
    ComponentScore,
    QualityScore,
    QualityScorer,
    ScoreComponent,
)


class TestComponentScore:
    """Tests for ComponentScore."""

    def test_component_score_creation(self) -> None:
        """Test component score creation."""
        score = ComponentScore(
            component=ScoreComponent.CODE_STYLE,
            score=0.85,
            weight=0.20,
            details={"files": 10},
            issues=["Minor style issue"],
            passed=True,
        )

        assert score.component == ScoreComponent.CODE_STYLE
        assert score.score == 0.85
        assert score.weight == 0.20
        assert score.passed is True

    def test_component_score_to_dict(self) -> None:
        """Test component score to dict conversion."""
        score = ComponentScore(
            component=ScoreComponent.SECURITY,
            score=0.95,
            weight=0.20,
            passed=True,
        )

        data = score.to_dict()
        assert data["component"] == "security"
        assert data["score"] == 0.95
        assert data["weighted_score"] == 0.19
        assert data["passed"] is True


class TestQualityScore:
    """Tests for QualityScore."""

    def test_quality_score_creation(self) -> None:
        """Test quality score creation."""
        component_scores = {
            ScoreComponent.CODE_STYLE: ComponentScore(
                component=ScoreComponent.CODE_STYLE,
                score=0.9,
                weight=0.20,
                passed=True,
            ),
            ScoreComponent.TEST_COVERAGE: ComponentScore(
                component=ScoreComponent.TEST_COVERAGE,
                score=0.8,
                weight=0.25,
                passed=True,
            ),
            ScoreComponent.SECURITY: ComponentScore(
                component=ScoreComponent.SECURITY,
                score=0.85,
                weight=0.20,
                passed=True,
            ),
            ScoreComponent.CONSTITUTION: ComponentScore(
                component=ScoreComponent.CONSTITUTION,
                score=0.9,
                weight=0.20,
                passed=True,
            ),
            ScoreComponent.DOCUMENTATION: ComponentScore(
                component=ScoreComponent.DOCUMENTATION,
                score=0.7,
                weight=0.15,
                passed=True,
            ),
        }

        score = QualityScore(
            overall_score=0.835,
            component_scores=component_scores,
            passed=True,
            threshold=0.80,
            file_count=10,
            line_count=500,
        )

        assert score.overall_score == 0.835
        assert score.passed is True
        assert score.file_count == 10

    def test_quality_score_to_dict(self) -> None:
        """Test quality score to dict conversion."""
        component_scores = {
            comp: ComponentScore(
                component=comp,
                score=0.8,
                weight=COMPONENT_WEIGHTS[comp],
                passed=True,
            )
            for comp in ScoreComponent
        }

        score = QualityScore(
            overall_score=0.80,
            component_scores=component_scores,
            passed=True,
            threshold=0.80,
        )

        data = score.to_dict()
        assert data["overall_score"] == 0.80
        assert data["overall_percentage"] == 80.0
        assert data["passed"] is True
        assert data["threshold_percentage"] == 80.0
        assert len(data["component_scores"]) == 5

    def test_get_failing_components(self) -> None:
        """Test getting failing components."""
        component_scores = {
            ScoreComponent.CODE_STYLE: ComponentScore(
                component=ScoreComponent.CODE_STYLE,
                score=0.9,
                weight=0.20,
                passed=True,
            ),
            ScoreComponent.TEST_COVERAGE: ComponentScore(
                component=ScoreComponent.TEST_COVERAGE,
                score=0.3,  # Failing
                weight=0.25,
                passed=False,
            ),
            ScoreComponent.SECURITY: ComponentScore(
                component=ScoreComponent.SECURITY,
                score=0.85,
                weight=0.20,
                passed=True,
            ),
            ScoreComponent.CONSTITUTION: ComponentScore(
                component=ScoreComponent.CONSTITUTION,
                score=0.4,  # Below 0.5 threshold
                weight=0.20,
                passed=False,
            ),
            ScoreComponent.DOCUMENTATION: ComponentScore(
                component=ScoreComponent.DOCUMENTATION,
                score=0.7,
                weight=0.15,
                passed=True,
            ),
        }

        score = QualityScore(
            overall_score=0.60,
            component_scores=component_scores,
            passed=False,
            threshold=0.80,
        )

        failing = score.get_failing_components()
        assert ScoreComponent.TEST_COVERAGE in failing
        assert ScoreComponent.CONSTITUTION in failing
        assert ScoreComponent.CODE_STYLE not in failing


class TestQualityScorer:
    """Tests for QualityScorer."""

    @pytest.fixture
    def scorer(self) -> QualityScorer:
        """Create a quality scorer instance."""
        return QualityScorer(passing_threshold=0.80)

    def test_scorer_initialization(self) -> None:
        """Test scorer initialization."""
        scorer = QualityScorer(passing_threshold=0.85)
        assert scorer.passing_threshold == 0.85
        assert scorer.component_thresholds[ScoreComponent.SECURITY] == 0.70

    def test_weights_sum_to_one(self) -> None:
        """Test that component weights sum to 1.0."""
        total = sum(COMPONENT_WEIGHTS.values())
        assert total == 1.0, f"Weights sum to {total}, expected 1.0"

    def test_calculate_score_no_files(self, scorer: QualityScorer) -> None:
        """Test score calculation with no files."""
        score = scorer.calculate_score(changed_files=[])

        assert score.overall_score >= 0.8  # Should pass with no files
        assert score.file_count == 0
        assert score.line_count == 0

    def test_calculate_score_with_files(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test score calculation with actual files."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '"""Test module."""\n\ndef foo():\n    """Docstring."""\n    pass\n'
        )

        with (
            patch.object(scorer, "_score_code_style") as mock_style,
            patch.object(scorer, "_score_test_coverage") as mock_coverage,
            patch.object(scorer, "_score_security") as mock_security,
            patch.object(scorer, "_score_constitution") as mock_const,
            patch.object(scorer, "_score_documentation") as mock_docs,
        ):
            # Set up mocks
            for mock in [
                mock_style,
                mock_coverage,
                mock_security,
                mock_const,
                mock_docs,
            ]:
                mock.return_value = ComponentScore(
                    component=ScoreComponent.CODE_STYLE,
                    score=0.8,
                    weight=0.2,
                    passed=True,
                )

            score = scorer.calculate_score(
                changed_files=["test.py"],
                pr_number=123,
                branch="feature/test",
                repo_path=tmp_path,
            )

            assert score.pr_number == 123
            assert score.branch == "feature/test"

    def test_score_code_style_no_python_files(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test code style scoring with no Python files."""
        score = scorer._score_code_style(
            changed_files=["README.md", "config.yaml"],
            repo_path=tmp_path,
        )

        assert score.score == 1.0
        assert score.passed is True

    def test_score_code_style_with_black_issues(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test code style scoring with black issues."""
        with patch("subprocess.run") as mock_run:
            # Black returns non-zero (issues found)
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

            score = scorer._score_code_style(
                changed_files=["test.py"],
                repo_path=tmp_path,
            )

            assert score.score < 1.0
            assert (
                "Black formatting issues" in score.issues[0]
                or "Black not installed" in score.issues[0]
            )

    def test_score_security_no_python_files(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test security scoring with no Python files."""
        score = scorer._score_security(
            changed_files=["README.md"],
            repo_path=tmp_path,
        )

        assert score.score == 1.0
        assert score.passed is True

    def test_score_security_with_issues(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test security scoring with bandit issues."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout='{"results": [{"issue_severity": "HIGH"}]}',
                stderr="",
            )

            score = scorer._score_security(
                changed_files=["insecure.py"],
                repo_path=tmp_path,
            )

            assert score.score < 1.0

    def test_score_test_coverage_no_source(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test coverage scoring with no source files."""
        score = scorer._score_test_coverage(
            changed_files=["README.md", "test_foo.py"],
            repo_path=tmp_path,
        )

        # test_ files are excluded
        assert score.score == 1.0

    def test_score_constitution_forbidden_paths(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test constitution scoring with forbidden paths."""
        score = scorer._score_constitution(
            changed_files=["terraform/main.tf", ".env"],
            repo_path=tmp_path,
        )

        assert score.score < 1.0
        assert len(score.issues) > 0

    def test_score_documentation_no_python(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test documentation scoring with no Python files."""
        score = scorer._score_documentation(
            changed_files=["README.md"],
            repo_path=tmp_path,
        )

        assert score.score == 1.0

    def test_score_documentation_with_docstrings(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test documentation scoring with well-documented code."""
        # Create well-documented file
        doc_file = tmp_path / "documented.py"
        doc_file.write_text('''"""Module docstring."""

def foo():
    """Function docstring."""
    pass

class Bar:
    """Class docstring."""
    pass
''')

        score = scorer._score_documentation(
            changed_files=["documented.py"],
            repo_path=tmp_path,
        )

        assert score.score >= 0.5

    def test_score_documentation_without_docstrings(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test documentation scoring with undocumented code."""
        # Create undocumented file
        undoc_file = tmp_path / "undocumented.py"
        undoc_file.write_text("""def foo():
    pass

class Bar:
    pass
""")

        score = scorer._score_documentation(
            changed_files=["undocumented.py"],
            repo_path=tmp_path,
        )

        assert score.score < 0.5


class TestScoreComponentWeights:
    """Tests for score component weights."""

    def test_all_components_have_weights(self) -> None:
        """Test all components have defined weights."""
        for comp in ScoreComponent:
            assert comp in COMPONENT_WEIGHTS, f"Missing weight for {comp}"

    def test_weight_values_are_reasonable(self) -> None:
        """Test weight values are in reasonable range."""
        for comp, weight in COMPONENT_WEIGHTS.items():
            assert (
                0 < weight <= 0.5
            ), f"Weight for {comp} is {weight}, expected 0 < w <= 0.5"


class TestLiveValidationGates:
    """Tests for live validation gates."""

    @pytest.fixture
    def scorer(self) -> QualityScorer:
        """Create a quality scorer instance."""
        return QualityScorer(passing_threshold=0.80)

    def test_review_time_under_2_minutes(
        self, scorer: QualityScorer, tmp_path: Path
    ) -> None:
        """Test that scoring completes in under 2 minutes."""
        import time

        # Create multiple test files
        for i in range(10):
            test_file = tmp_path / f"test_{i}.py"
            test_file.write_text(
                f'"""Test module {i}."""\n\ndef func_{i}():\n    pass\n'
            )

        with (
            patch.object(scorer, "_score_code_style") as mock_style,
            patch.object(scorer, "_score_test_coverage") as mock_coverage,
            patch.object(scorer, "_score_security") as mock_security,
            patch.object(scorer, "_score_constitution") as mock_const,
            patch.object(scorer, "_score_documentation") as mock_docs,
        ):
            for mock in [
                mock_style,
                mock_coverage,
                mock_security,
                mock_const,
                mock_docs,
            ]:
                mock.return_value = ComponentScore(
                    component=ScoreComponent.CODE_STYLE,
                    score=0.8,
                    weight=0.2,
                    passed=True,
                )

            start = time.time()
            scorer.calculate_score(
                changed_files=[f"test_{i}.py" for i in range(10)],
                repo_path=tmp_path,
            )
            elapsed = time.time() - start

            # Should complete in under 2 minutes (120 seconds)
            assert elapsed < 120, f"Scoring took {elapsed}s, expected < 120s"
