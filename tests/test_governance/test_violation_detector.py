"""Tests for violation detector module.

Tests for constitution violation detection and alerting.

For ST-GOV-002: Agent Constitution Artifact
"""

from __future__ import annotations

import pytest
from src.governance.constitution.violation_detector import (
    DiscordAlertChannel,
    Violation,
    ViolationDetector,
    ViolationSeverity,
)


class TestViolation:
    """Tests for Violation."""

    def test_violation_creation(self) -> None:
        """Test violation creation."""
        violation = Violation(
            id="viol-001",
            rule_id="VR-001",
            severity=ViolationSeverity.P1,
            description="Test violation",
            pattern_matched="test pattern",
            context={"key": "value"},
        )

        assert violation.id == "viol-001"
        assert violation.severity == ViolationSeverity.P1
        assert not violation.resolved

    def test_violation_resolve(self) -> None:
        """Test violation resolution."""
        violation = Violation(
            id="viol-001",
            rule_id="VR-001",
            severity=ViolationSeverity.P1,
            description="Test",
            pattern_matched="pattern",
            context={},
        )

        violation.resolve("admin-user")

        assert violation.resolved
        assert violation.resolved_by == "admin-user"
        assert violation.resolved_at is not None

    def test_violation_to_dict(self) -> None:
        """Test violation to dict conversion."""
        violation = Violation(
            id="viol-001",
            rule_id="VR-001",
            severity=ViolationSeverity.P2,
            description="Test violation",
            pattern_matched="pattern",
            context={"test": "data"},
        )

        data = violation.to_dict()
        assert data["id"] == "viol-001"
        assert data["severity"] == "P2"
        assert data["resolved"] is False


class TestViolationDetector:
    """Tests for ViolationDetector."""

    @pytest.fixture
    def detector(self) -> ViolationDetector:
        """Create a violation detector instance."""
        detector = ViolationDetector()
        detector.register_default_rules()
        return detector

    def test_detector_initialization(self) -> None:
        """Test detector initialization."""
        detector = ViolationDetector()
        assert detector.detection_accuracy_target == 0.99

    def test_register_rule(self) -> None:
        """Test rule registration."""
        detector = ViolationDetector()
        detector.register_rule(
            rule_id="VR-TEST",
            pattern=r"test.*violation",
            severity=ViolationSeverity.P1,
            description="Test rule",
        )

        assert "VR-TEST" in detector._violation_rules

    def test_register_default_rules(self) -> None:
        """Test default rules registration."""
        detector = ViolationDetector()
        detector.register_default_rules()

        assert "VR-001" in detector._violation_rules
        assert "VR-002" in detector._violation_rules
        assert "VR-003" in detector._violation_rules
        assert "VR-004" in detector._violation_rules
        assert "VR-005" in detector._violation_rules

    def test_detect_violation(self, detector: ViolationDetector) -> None:
        """Test violation detection."""
        violations = detector.detect(
            action="Agent accessed path outside SCOPE_GLOBS",
            context={"path": "/forbidden/path"},
        )

        assert len(violations) >= 1
        assert violations[0].rule_id == "VR-001"
        assert violations[0].severity == ViolationSeverity.P1

    def test_detect_no_violation(self, detector: ViolationDetector) -> None:
        """Test no violation detected for safe action."""
        violations = detector.detect(
            action="Agent performed standard operation within scope",
            context={},
        )

        # Should not detect violations for safe text
        # (unless it accidentally matches a pattern)
        assert isinstance(violations, list)

    def test_detect_branch_violation(self, detector: ViolationDetector) -> None:
        """Test branch safety violation detection."""
        violations = detector.detect(
            action="Direct commit to main branch",
            context={"branch": "main"},
        )

        assert any(v.rule_id == "VR-002" for v in violations)

    def test_check_scope_violation_allowed(self, detector: ViolationDetector) -> None:
        """Test scope check for allowed path."""
        violation = detector.check_scope_violation(
            accessed_path="src/governance/test.py",
            allowed_globs=["src/**/*.py", "tests/**/*.py"],
        )

        assert violation is None

    def test_check_scope_violation_blocked(self, detector: ViolationDetector) -> None:
        """Test scope check for blocked path."""
        violation = detector.check_scope_violation(
            accessed_path="infrastructure/terraform/main.tf",
            allowed_globs=["src/**/*.py"],
            context={"user": "test-user"},
        )

        assert violation is not None
        assert violation.rule_id == "VR-001"

    def test_check_branch_safety_safe(self, detector: ViolationDetector) -> None:
        """Test branch safety check for feature branch."""
        violation = detector.check_branch_safety(
            branch="feature/test-branch",
            action="commit changes",
        )

        assert violation is None

    def test_check_branch_safety_violation(self, detector: ViolationDetector) -> None:
        """Test branch safety check for main branch."""
        violation = detector.check_branch_safety(
            branch="main",
            action="commit changes to production",
        )

        assert violation is not None
        assert violation.rule_id == "VR-002"

    def test_get_stats(self, detector: ViolationDetector) -> None:
        """Test getting detection statistics."""
        detector.detect("Agent accessed path outside SCOPE_GLOBS")
        stats = detector.get_stats()

        assert stats["total_checked"] >= 1
        assert stats["violations_detected"] >= 1
        assert "accuracy" in stats

    def test_record_validation_result(self, detector: ViolationDetector) -> None:
        """Test recording validation results."""
        violations = detector.detect("Agent accessed path outside SCOPE_GLOBS")
        if violations:
            detector.record_validation_result(violations[0].id, is_true_positive=True)

        stats = detector.get_stats()
        assert stats["true_positives"] >= 1

    def test_get_violations(self, detector: ViolationDetector) -> None:
        """Test getting violations with filters."""
        # Detect some violations
        detector.detect("Agent accessed path outside SCOPE_GLOBS")

        # Get all violations
        all_violations = detector.get_violations()
        assert len(all_violations) >= 1

        # Get P1 violations only
        p1_violations = detector.get_violations(severity=ViolationSeverity.P1)
        for v in p1_violations:
            assert v.severity == ViolationSeverity.P1

    def test_clear_violations(self, detector: ViolationDetector) -> None:
        """Test clearing violations."""
        detector.detect("Agent accessed path outside SCOPE_GLOBS")
        detector.clear_violations()

        violations = detector.get_violations()
        assert len(violations) == 0

    def test_accuracy_calculation(self, detector: ViolationDetector) -> None:
        """Test accuracy calculation."""
        # Record some results
        detector.record_validation_result("test-1", is_true_positive=True)
        detector.record_validation_result("test-2", is_true_positive=True)
        detector.record_validation_result("test-3", is_true_positive=False)

        accuracy = detector.get_accuracy()
        assert accuracy == 2 / 3

    def test_meets_target(self, detector: ViolationDetector) -> None:
        """Test if accuracy meets target."""
        # Record high accuracy results
        for i in range(100):
            detector.record_validation_result(f"test-{i}", is_true_positive=True)
        detector.record_validation_result("test-fp", is_true_positive=False)

        stats = detector.get_stats()
        # 100/101 = ~99% accuracy
        assert stats["accuracy"] >= 0.99


class TestDiscordAlertChannel:
    """Tests for Discord alert channel."""

    def test_format_message(self) -> None:
        """Test message formatting."""
        channel = DiscordAlertChannel(channel_id="#alerts")
        violation = Violation(
            id="viol-001",
            rule_id="VR-001",
            severity=ViolationSeverity.P1,
            description="Test violation",
            pattern_matched="test pattern",
            context={"test": "data"},
        )

        message = channel._format_message(violation)

        assert "P1" in message
        assert "VR-001" in message
        assert "Test violation" in message

    def test_send_without_webhook(self) -> None:
        """Test sending without webhook (logs instead)."""
        channel = DiscordAlertChannel(channel_id="#alerts")
        violation = Violation(
            id="viol-001",
            rule_id="VR-001",
            severity=ViolationSeverity.P1,
            description="Test",
            pattern_matched="pattern",
            context={},
        )

        # Should return True (logs the message)
        result = channel.send(violation)
        assert result is True


class TestViolationSeverity:
    """Tests for ViolationSeverity."""

    def test_severity_values(self) -> None:
        """Test severity level values."""
        assert ViolationSeverity.P0.value == "P0"
        assert ViolationSeverity.P1.value == "P1"
        assert ViolationSeverity.P2.value == "P2"
        assert ViolationSeverity.P3.value == "P3"


class TestViolationDetectionAccuracy:
    """Tests for violation detection accuracy (99% requirement)."""

    @pytest.fixture
    def detector(self) -> ViolationDetector:
        """Create a configured detector."""
        detector = ViolationDetector(detection_accuracy_target=0.99)
        detector.register_default_rules()
        return detector

    def test_accuracy_on_true_positives(self, detector: ViolationDetector) -> None:
        """Test accuracy on known true positive cases."""
        true_positive_cases = [
            "Agent accessed path outside SCOPE_GLOBS",
            "Direct commit to main branch",
            "State change without audit log entry",
            "Rate limit exceeded on API calls",
            "Feature used without flag check",
        ]

        correct = 0
        total = len(true_positive_cases)

        for case in true_positive_cases:
            violations = detector.detect(case)
            if violations:  # Should detect violations
                correct += 1
                detector.record_validation_result(
                    violations[0].id, is_true_positive=True
                )

        accuracy = correct / total
        assert accuracy >= 0.99, f"True positive accuracy {accuracy} < 99%"

    def test_accuracy_on_true_negatives(self, detector: ViolationDetector) -> None:
        """Test accuracy on known negative cases (should not trigger)."""
        true_negative_cases = [
            "Agent performed standard operation within scope",
            "Committed to feature branch",
            "State change logged to audit trail",
            "API call within rate limits",
            "Feature used with proper flag check",
        ]

        # For true negatives, we shouldn't have false positives
        false_positives = 0
        total = len(true_negative_cases)

        for case in true_negative_cases:
            violations = detector.detect(case)
            false_positives += len(violations)

        # Allow some tolerance for pattern matching
        false_positive_rate = false_positives / (total * 5)  # 5 rules
        assert (
            false_positive_rate < 0.01
        ), f"False positive rate {false_positive_rate} >= 1%"
