"""
Tests for self-critique generation engine.

These tests verify:
- Critique generation functionality
- Constraint integration
- Accuracy metrics
- Actionable feedback generation
"""

import pytest
from src.strong_system.constitutional.constraints import (
    ConstraintCategory,
    ConstraintEngine,
    ConstraintSeverity,
    ConstraintViolation,
)
from src.strong_system.constitutional.critique import (
    CritiqueAccuracy,
    CritiqueGenerator,
    CritiqueResult,
    CritiqueType,
)


class TestConstraintEngine:
    """Tests for the ConstraintEngine."""

    def test_engine_initialization(self):
        """Test that engine initializes with 11 constraints."""
        engine = ConstraintEngine()
        assert len(engine.constraints) == 11

    def test_all_constraints_have_unique_ids(self):
        """Test that all constraint IDs are unique."""
        engine = ConstraintEngine()
        ids = [c.id for c in engine.constraints]
        assert len(ids) == len(set(ids))

    def test_safety_constraint_detects_harmful_content(self):
        """Test safety constraint detects harmful content."""
        engine = ConstraintEngine()
        violations = engine.evaluate("I will hack into your account and steal money")
        assert len(violations) > 0
        assert any(v.category == ConstraintCategory.SAFETY for v in violations)

    def test_safety_constraint_passes_safe_content(self):
        """Test safety constraint passes safe content."""
        engine = ConstraintEngine()
        violations = engine.evaluate("The weather is nice today")
        safety_violations = [
            v for v in violations if v.category == ConstraintCategory.SAFETY
        ]
        assert len(safety_violations) == 0

    def test_privacy_constraint_detects_ssn(self):
        """Test privacy constraint detects SSN."""
        engine = ConstraintEngine()
        violations = engine.evaluate("My SSN is 123-45-6789")
        assert len(violations) > 0

    def test_privacy_constraint_detects_email(self):
        """Test privacy constraint detects email."""
        engine = ConstraintEngine()
        violations = engine.evaluate("Contact me at test@example.com")
        assert len(violations) > 0

    def test_privacy_constraint_passes_safe_content(self):
        """Test privacy constraint passes safe content."""
        engine = ConstraintEngine()
        violations = engine.evaluate("This is a general response")
        privacy_violations = [
            v for v in violations if v.category == ConstraintCategory.PRIVACY
        ]
        assert len(privacy_violations) == 0

    def test_transparency_constraint_requires_reasoning(self):
        """Test transparency constraint requires reasoning."""
        engine = ConstraintEngine()
        # Long output without reasoning
        violations = engine.evaluate("A" * 150)
        assert len(violations) > 0

    def test_transparency_constraint_passes_with_reasoning(self):
        """Test transparency constraint passes with reasoning."""
        engine = ConstraintEngine()
        violations = engine.evaluate(
            "I recommend this because the data shows improvement"
        )
        transparency_violations = [
            v for v in violations if v.category == ConstraintCategory.TRANSPARENCY
        ]
        assert len(transparency_violations) == 0

    def test_security_constraint_detects_eval(self):
        """Test security constraint detects eval()."""
        engine = ConstraintEngine()
        violations = engine.evaluate("Use eval(user_input) to execute")
        assert len(violations) > 0

    def test_security_constraint_detects_hardcoded_password(self):
        """Test security constraint detects hardcoded passwords."""
        engine = ConstraintEngine()
        violations = engine.evaluate('password = "secret123"')
        assert len(violations) > 0

    def test_fairness_constraint_detects_bias(self):
        """Test fairness constraint detects biased content."""
        engine = ConstraintEngine()
        violations = engine.evaluate("All women are inferior at math")
        assert len(violations) > 0

    def test_fairness_constraint_passes_fair_content(self):
        """Test fairness constraint passes fair content."""
        engine = ConstraintEngine()
        violations = engine.evaluate("The model should be evaluated on its merits")
        fairness_violations = [
            v for v in violations if v.category == ConstraintCategory.FAIRNESS
        ]
        assert len(fairness_violations) == 0

    def test_compliance_score_calculation(self):
        """Test compliance score calculation."""
        engine = ConstraintEngine()
        score, _ = engine.evaluate_with_score("Safe content with reasoning")
        assert 0.0 <= score <= 1.0

    def test_get_constraint_by_id(self):
        """Test getting constraint by ID."""
        engine = ConstraintEngine()
        constraint = engine.get_constraint_by_id("CONST_001")
        assert constraint is not None
        assert constraint.id == "CONST_001"

    def test_get_constraints_by_category(self):
        """Test getting constraints by category."""
        engine = ConstraintEngine()
        safety_constraints = engine.get_constraints_by_category(
            ConstraintCategory.SAFETY
        )
        assert len(safety_constraints) > 0


class TestCritiqueGenerator:
    """Tests for the CritiqueGenerator."""

    def test_generator_initialization(self):
        """Test generator initializes correctly."""
        generator = CritiqueGenerator()
        assert generator.constraint_engine is not None
        assert generator.accuracy is not None

    def test_generate_critique_returns_result(self):
        """Test generate_critique returns CritiqueResult."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("Safe content with reasoning")
        assert isinstance(result, CritiqueResult)

    def test_critique_identifies_safe_output(self):
        """Test critique identifies safe output."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("The solution is correct because 2+2=4")
        assert result.passed

    def test_critique_identifies_unsafe_output(self):
        """Test critique identifies unsafe output."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("I will hack into your account")
        assert not result.passed

    def test_critique_contains_violations(self):
        """Test critique contains violations for unsafe output."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("hack the system")
        assert len(result.violations) > 0

    def test_critique_count(self):
        """Test critique count is correct."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("Safe content")
        assert result.get_critique_count() > 0

    def test_batch_critique(self):
        """Test batch critique generation."""
        generator = CritiqueGenerator()
        outputs = ["Safe content", "hack the system", "Another safe response"]
        results = generator.batch_critique(outputs)
        assert len(results) == 3

    def test_actionable_critique_format(self):
        """Test actionable critique is properly formatted."""
        generator = CritiqueGenerator()
        critique = generator.generate_actionable_critique("Safe content")
        assert "Self-Critique Report" in critique
        assert "Status:" in critique

    def test_constraint_integration(self):
        """Test integration with constraint engine."""
        engine = ConstraintEngine()
        generator = CritiqueGenerator(constraint_engine=engine)
        result = generator.generate_critique("Test output")
        assert result is not None


class TestCritiqueAccuracy:
    """Tests for CritiqueAccuracy metrics."""

    def test_accuracy_initialization(self):
        """Test accuracy initializes to zero."""
        accuracy = CritiqueAccuracy()
        assert accuracy.total_critiques == 0
        assert accuracy.accuracy == 0.0

    def test_record_correct_critique(self):
        """Test recording correct critique."""
        accuracy = CritiqueAccuracy()
        accuracy.record_critique(is_correct=True)
        assert accuracy.correct_critiques == 1
        assert accuracy.total_critiques == 1

    def test_accuracy_calculation(self):
        """Test accuracy percentage calculation."""
        accuracy = CritiqueAccuracy()
        accuracy.record_critique(is_correct=True)
        accuracy.record_critique(is_correct=True)
        accuracy.record_critique(is_correct=False)
        assert accuracy.accuracy == pytest.approx(66.67, rel=0.1)

    def test_precision_calculation(self):
        """Test precision calculation."""
        accuracy = CritiqueAccuracy()
        accuracy.record_critique(is_correct=True)
        accuracy.record_critique(is_correct=True)
        accuracy.record_critique(is_correct=False)  # false positive
        assert accuracy.precision == pytest.approx(66.67, rel=0.1)

    def test_recall_calculation(self):
        """Test recall calculation."""
        accuracy = CritiqueAccuracy()
        accuracy.record_critique(is_correct=True)
        accuracy.record_critique(is_correct=False, is_false_negative=True)
        assert accuracy.recall == pytest.approx(50.0, rel=0.1)

    def test_f1_score_calculation(self):
        """Test F1 score calculation."""
        accuracy = CritiqueAccuracy()
        accuracy.record_critique(is_correct=True)
        accuracy.record_critique(is_correct=True)
        accuracy.record_critique(is_correct=False)
        accuracy.record_critique(is_correct=False, is_false_negative=True)
        # precision = 2/3 = 66.67, recall = 1/2 = 50
        # f1 = 2 * 66.67 * 50 / (66.67 + 50) = 57.14
        assert accuracy.f1_score > 0

    def test_reset_accuracy(self):
        """Test resetting accuracy metrics."""
        accuracy = CritiqueAccuracy()
        accuracy.record_critique(is_correct=True)
        accuracy.reset()
        assert accuracy.total_critiques == 0
        assert accuracy.correct_critiques == 0


class TestCritiqueTypes:
    """Tests for critique type mapping."""

    def test_safety_critique_type(self):
        """Test safety critique type is assigned correctly."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("hack the system")
        safety_critiques = [
            c for c in result.critiques if c.critique_type == CritiqueType.SAFETY
        ]
        assert len(safety_critiques) > 0

    def test_quality_critique_type(self):
        """Test quality critique type is assigned correctly."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("A" * 200)  # No reasoning
        quality_critiques = [
            c for c in result.critiques if c.critique_type == CritiqueType.QUALITY
        ]
        assert len(quality_critiques) > 0


class TestCritiqueResult:
    """Tests for CritiqueResult."""

    def test_get_passed_count(self):
        """Test getting passed critique count."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("Safe content with reasoning")
        assert result.get_passed_count() >= 0

    def test_get_failed_count(self):
        """Test getting failed critique count."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("hack the system")
        assert result.get_failed_count() >= 0

    def test_to_dict(self):
        """Test converting result to dictionary."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("Test")
        d = result.to_dict()
        assert "output" in d
        assert "compliance_score" in d
        assert "passed" in d


class TestCritiqueGeneratorEdgeCases:
    """Tests for edge cases in critique generation."""

    def test_empty_output(self):
        """Test critique handles empty output."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("")
        assert result is not None

    def test_very_long_output(self):
        """Test critique handles very long output."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("A" * 10000)
        assert result is not None

    def test_unicode_content(self):
        """Test critique handles unicode content."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("Hello 世界 🌍")
        assert result is not None

    def test_special_characters(self):
        """Test critique handles special characters."""
        generator = CritiqueGenerator()
        result = generator.generate_critique("Test @#$%^&*()")
        assert result is not None


class TestConstraintViolation:
    """Tests for ConstraintViolation."""

    def test_violation_to_dict(self):
        """Test violation converts to dict."""
        violation = ConstraintViolation(
            constraint_id="CONST_001",
            constraint_name="Safety",
            category=ConstraintCategory.SAFETY,
            severity=ConstraintSeverity.CRITICAL,
            message="Test violation",
        )
        d = violation.to_dict()
        assert d["constraint_id"] == "CONST_001"
        assert d["severity"] == "critical"


class TestCritiqueGeneratorAccuracy:
    """Tests for accuracy tracking in generator."""

    def test_accuracy_tracking(self):
        """Test accuracy is tracked correctly."""
        generator = CritiqueGenerator()
        generator.generate_critique("Safe content")
        generator.generate_critique("hack")
        metrics = generator.get_accuracy_metrics()
        assert "accuracy" in metrics
        assert metrics["total_critiques"] == 2

    def test_reset_accuracy_metrics(self):
        """Test resetting accuracy metrics."""
        generator = CritiqueGenerator()
        generator.generate_critique("Test")
        generator.reset_accuracy()
        metrics = generator.get_accuracy_metrics()
        assert metrics["total_critiques"] == 0


class TestConstraintCategories:
    """Tests for constraint categories."""

    def test_all_categories_present(self):
        """Test all constraint categories are present."""
        engine = ConstraintEngine()
        categories = {c.category for c in engine.constraints}
        assert ConstraintCategory.SAFETY in categories
        assert ConstraintCategory.TRANSPARENCY in categories
        assert ConstraintCategory.FAIRNESS in categories
        assert ConstraintCategory.PRIVACY in categories
        assert ConstraintCategory.SECURITY in categories
        assert ConstraintCategory.ROBUSTNESS in categories
        assert ConstraintCategory.ACCOUNTABILITY in categories
        assert ConstraintCategory.HUMAN_OVERRIDE in categories
        assert ConstraintCategory.EXPLAINABILITY in categories
        assert ConstraintCategory.BOUNDED_SCOPE in categories
        assert ConstraintCategory.AUDITABILITY in categories


class TestConstraintSeverity:
    """Tests for constraint severity levels."""

    def test_critical_severity_present(self):
        """Test critical severity is used."""
        engine = ConstraintEngine()
        critical = [
            c for c in engine.constraints if c.severity == ConstraintSeverity.CRITICAL
        ]
        assert len(critical) > 0

    def test_error_severity_present(self):
        """Test error severity is used."""
        engine = ConstraintEngine()
        errors = [
            c for c in engine.constraints if c.severity == ConstraintSeverity.ERROR
        ]
        assert len(errors) > 0

    def test_warning_severity_present(self):
        """Test warning severity is used."""
        engine = ConstraintEngine()
        warnings = [
            c for c in engine.constraints if c.severity == ConstraintSeverity.WARNING
        ]
        assert len(warnings) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
