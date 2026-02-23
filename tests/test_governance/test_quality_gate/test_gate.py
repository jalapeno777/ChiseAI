"""Tests for quality gate module.

For ST-GOV-006: Self-Review Quality Gate
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from src.governance.quality_gate.gate import (
    BlockReason,
    QualityGate,
    QualityGateResult,
)
from src.governance.quality_gate.override import (
    HumanOverride,
    OverrideManager,
    OverrideStatus,
    RiskLevel,
)
from src.governance.quality_gate.scorer import (
    ComponentScore,
    QualityScore,
    QualityScorer,
    ScoreComponent,
    COMPONENT_WEIGHTS,
)


class TestBlockReason:
    """Tests for BlockReason enum."""

    def test_block_reasons_exist(self) -> None:
        """Test all expected block reasons exist."""
        expected = [
            "low_quality_score",
            "security_issues",
            "missing_tests",
            "scope_violation",
            "constitution_violation",
            "pending_review",
        ]
        for reason in expected:
            assert BlockReason(reason) is not None


class TestQualityGateResult:
    """Tests for QualityGateResult."""

    def test_result_creation(self) -> None:
        """Test quality gate result creation."""
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

        result = QualityGateResult(
            passed=True,
            score=score,
            blocked=False,
            block_reasons=[],
            review_time_seconds=1.5,
        )

        assert result.passed is True
        assert result.blocked is False
        assert result.review_time_seconds == 1.5

    def test_result_to_dict(self) -> None:
        """Test result to dict conversion."""
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
            overall_score=0.75,
            component_scores=component_scores,
            passed=False,
            threshold=0.80,
        )

        result = QualityGateResult(
            passed=False,
            score=score,
            blocked=True,
            block_reasons=[BlockReason.LOW_QUALITY_SCORE],
            override_active=False,
            recommendations=["Add more tests"],
        )

        data = result.to_dict()
        assert data["passed"] is False
        assert data["blocked"] is True
        assert data["block_reasons"] == ["low_quality_score"]
        assert "recommendations" in data


class TestQualityGate:
    """Tests for QualityGate."""

    @pytest.fixture
    def gate(self) -> QualityGate:
        """Create a quality gate instance."""
        scorer = QualityScorer(passing_threshold=0.80)
        return QualityGate(
            scorer=scorer,
            blocking_threshold=0.80,
            enable_blocking=True,
        )

    def test_gate_initialization(self) -> None:
        """Test gate initialization."""
        gate = QualityGate(
            blocking_threshold=0.75,
            security_threshold=0.60,
            enable_blocking=False,
        )

        assert gate.blocking_threshold == 0.75
        assert gate.security_threshold == 0.60
        assert gate.enable_blocking is False

    def test_evaluate_passing_pr(self, gate: QualityGate, tmp_path) -> None:
        """Test evaluation of a passing PR."""
        with patch.object(gate.scorer, "calculate_score") as mock_score:
            # Set up passing score
            component_scores = {
                comp: ComponentScore(
                    component=comp,
                    score=0.85,
                    weight=COMPONENT_WEIGHTS[comp],
                    passed=True,
                )
                for comp in ScoreComponent
            }

            mock_score.return_value = QualityScore(
                overall_score=0.85,
                component_scores=component_scores,
                passed=True,
                threshold=0.80,
            )

            result = gate.evaluate(
                pr_number=123,
                changed_files=["src/test.py"],
                branch="feature/test",
                repo_path=str(tmp_path),
            )

            assert result.passed is True
            assert result.blocked is False
            assert len(result.block_reasons) == 0

    def test_evaluate_blocking_pr(self, gate: QualityGate, tmp_path) -> None:
        """Test evaluation of a blocking PR."""
        with patch.object(gate.scorer, "calculate_score") as mock_score:
            # Set up failing score
            component_scores = {
                comp: ComponentScore(
                    component=comp,
                    score=0.50,
                    weight=COMPONENT_WEIGHTS[comp],
                    passed=comp != ScoreComponent.SECURITY,
                )
                for comp in ScoreComponent
            }

            mock_score.return_value = QualityScore(
                overall_score=0.50,
                component_scores=component_scores,
                passed=False,
                threshold=0.80,
            )

            result = gate.evaluate(
                pr_number=124,
                changed_files=["src/test.py"],
                branch="feature/test",
                repo_path=str(tmp_path),
            )

            assert result.passed is False
            assert result.blocked is True
            assert BlockReason.LOW_QUALITY_SCORE in result.block_reasons

    def test_evaluate_security_issues(self, gate: QualityGate, tmp_path) -> None:
        """Test evaluation blocks on security issues."""
        with patch.object(gate.scorer, "calculate_score") as mock_score:
            component_scores = {
                ScoreComponent.CODE_STYLE: ComponentScore(
                    component=ScoreComponent.CODE_STYLE,
                    score=0.9,
                    weight=COMPONENT_WEIGHTS[ScoreComponent.CODE_STYLE],
                    passed=True,
                ),
                ScoreComponent.TEST_COVERAGE: ComponentScore(
                    component=ScoreComponent.TEST_COVERAGE,
                    score=0.9,
                    weight=COMPONENT_WEIGHTS[ScoreComponent.TEST_COVERAGE],
                    passed=True,
                ),
                ScoreComponent.SECURITY: ComponentScore(
                    component=ScoreComponent.SECURITY,
                    score=0.50,  # Below security threshold (0.70)
                    weight=COMPONENT_WEIGHTS[ScoreComponent.SECURITY],
                    passed=False,
                ),
                ScoreComponent.CONSTITUTION: ComponentScore(
                    component=ScoreComponent.CONSTITUTION,
                    score=0.9,
                    weight=COMPONENT_WEIGHTS[ScoreComponent.CONSTITUTION],
                    passed=True,
                ),
                ScoreComponent.DOCUMENTATION: ComponentScore(
                    component=ScoreComponent.DOCUMENTATION,
                    score=0.9,
                    weight=COMPONENT_WEIGHTS[ScoreComponent.DOCUMENTATION],
                    passed=True,
                ),
            }

            mock_score.return_value = QualityScore(
                overall_score=0.82,  # Overall passing
                component_scores=component_scores,
                passed=True,
                threshold=0.80,
            )

            result = gate.evaluate(
                pr_number=125,
                changed_files=["src/test.py"],
                branch="feature/test",
                repo_path=str(tmp_path),
            )

            # Should block due to security issues even if overall score passes
            assert BlockReason.SECURITY_ISSUES in result.block_reasons

    def test_evaluate_with_override(self, gate: QualityGate, tmp_path) -> None:
        """Test evaluation respects active override."""
        # Create and activate an override
        override = gate.override_manager.create_request(
            pr_number=126,
            requester="test-user",
            justification="This is a justified override for testing purposes with sufficient length",
            risk_assessment="low",
            rollback_plan="git revert",
        )
        gate.override_manager.approve_request(override.id, "approver")
        gate.override_manager.activate_override(override.id)

        with patch.object(gate.scorer, "calculate_score") as mock_score:
            component_scores = {
                comp: ComponentScore(
                    component=comp,
                    score=0.50,
                    weight=COMPONENT_WEIGHTS[comp],
                    passed=True,
                )
                for comp in ScoreComponent
            }

            mock_score.return_value = QualityScore(
                overall_score=0.50,
                component_scores=component_scores,
                passed=False,
                threshold=0.80,
            )

            result = gate.evaluate(
                pr_number=126,
                changed_files=["src/test.py"],
                branch="feature/test",
                repo_path=str(tmp_path),
            )

            # Should not be blocked due to override
            assert result.override_active is True
            assert result.blocked is False

    def test_evaluate_no_blocking_when_disabled(self, tmp_path) -> None:
        """Test evaluation doesn't block when blocking is disabled."""
        gate = QualityGate(enable_blocking=False)

        with patch.object(gate.scorer, "calculate_score") as mock_score:
            component_scores = {
                comp: ComponentScore(
                    component=comp,
                    score=0.50,
                    weight=COMPONENT_WEIGHTS[comp],
                    passed=True,
                )
                for comp in ScoreComponent
            }

            mock_score.return_value = QualityScore(
                overall_score=0.50,
                component_scores=component_scores,
                passed=False,
                threshold=0.80,
            )

            result = gate.evaluate(
                pr_number=127,
                changed_files=["src/test.py"],
                branch="feature/test",
                repo_path=str(tmp_path),
            )

            # Should have reasons but not actually block
            assert len(result.block_reasons) > 0
            assert result.blocked is False

    def test_generate_recommendations(self, gate: QualityGate) -> None:
        """Test recommendation generation."""
        component_scores = {
            comp: ComponentScore(
                component=comp,
                score=0.50,
                weight=COMPONENT_WEIGHTS[comp],
                passed=comp
                not in [ScoreComponent.SECURITY, ScoreComponent.TEST_COVERAGE],
            )
            for comp in ScoreComponent
        }

        score = QualityScore(
            overall_score=0.50,
            component_scores=component_scores,
            passed=False,
            threshold=0.80,
        )

        reasons = [
            BlockReason.LOW_QUALITY_SCORE,
            BlockReason.SECURITY_ISSUES,
            BlockReason.MISSING_TESTS,
        ]

        recommendations = gate._generate_recommendations(score, reasons)

        assert len(recommendations) > 0
        assert any("security" in r.lower() for r in recommendations)
        assert any("test" in r.lower() for r in recommendations)

    def test_request_override(self, gate: QualityGate) -> None:
        """Test requesting an override."""
        override_id = gate.request_override(
            pr_number=128,
            requester="test-user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="medium",
            rollback_plan="git revert",
        )

        assert override_id is not None
        assert override_id.startswith("override-")

    def test_approve_override(self, gate: QualityGate) -> None:
        """Test approving an override."""
        override_id = gate.request_override(
            pr_number=129,
            requester="test-user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="git revert",
        )

        result = gate.approve_override(override_id, "approver-user")
        assert result is True

    def test_get_stats(self, gate: QualityGate, tmp_path) -> None:
        """Test getting gate statistics."""
        with patch.object(gate.scorer, "calculate_score") as mock_score:
            component_scores = {
                comp: ComponentScore(
                    component=comp,
                    score=0.85,
                    weight=COMPONENT_WEIGHTS[comp],
                    passed=True,
                )
                for comp in ScoreComponent
            }

            mock_score.return_value = QualityScore(
                overall_score=0.85,
                component_scores=component_scores,
                passed=True,
                threshold=0.80,
            )

            # Run a few evaluations
            for i in range(3):
                gate.evaluate(
                    pr_number=100 + i,
                    changed_files=["src/test.py"],
                    branch="feature/test",
                    repo_path=str(tmp_path),
                )

            stats = gate.get_stats()

            assert stats["total_reviews"] == 3
            assert stats["avg_review_time_seconds"] >= 0
            assert "validation_gates" in stats

    def test_record_validation_result(self, gate: QualityGate) -> None:
        """Test recording validation results."""
        gate.record_validation_result(was_false_positive=True)
        gate.record_validation_result(was_false_negative=True)

        stats = gate.get_stats()
        assert stats["false_positives"] == 1
        assert stats["false_negatives"] == 1


class TestQualityGateLiveValidation:
    """Tests for live validation gates."""

    def test_false_negative_rate_under_5_percent(self, tmp_path) -> None:
        """Test false negative rate is under 5%."""
        gate = QualityGate()

        # Simulate validation results
        for _ in range(100):
            gate.record_validation_result(was_false_negative=False)
        for _ in range(4):  # 4% false negative rate
            gate.record_validation_result(was_false_negative=True)

        stats = gate.get_stats()
        assert stats["false_negative_rate"] < 0.05
        assert stats["validation_gates"]["false_negative_rate_pass"] is True

    def test_false_positive_rate_under_10_percent(self, tmp_path) -> None:
        """Test false positive rate is under 10%."""
        gate = QualityGate()

        # Simulate validation results
        for _ in range(100):
            gate.record_validation_result(was_false_positive=False)
        for _ in range(9):  # 9% false positive rate
            gate.record_validation_result(was_false_positive=True)

        stats = gate.get_stats()
        assert stats["false_positive_rate"] < 0.10
        assert stats["validation_gates"]["false_positive_rate_pass"] is True

    def test_review_time_under_2_minutes(self, tmp_path) -> None:
        """Test review time is under 2 minutes."""
        scorer = QualityScorer(passing_threshold=0.80)
        gate = QualityGate(scorer=scorer)

        with patch.object(gate.scorer, "calculate_score") as mock_score:
            component_scores = {
                comp: ComponentScore(
                    component=comp,
                    score=0.85,
                    weight=COMPONENT_WEIGHTS[comp],
                    passed=True,
                )
                for comp in ScoreComponent
            }

            mock_score.return_value = QualityScore(
                overall_score=0.85,
                component_scores=component_scores,
                passed=True,
                threshold=0.80,
            )

            result = gate.evaluate(
                pr_number=200,
                changed_files=["src/test.py"],
                branch="feature/test",
                repo_path=str(tmp_path),
            )

            assert result.review_time_seconds < 120  # 2 minutes = 120 seconds

            stats = gate.get_stats()
            assert stats["validation_gates"]["review_time_pass"] is True
