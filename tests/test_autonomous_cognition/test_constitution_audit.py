"""Tests for ConstitutionAuditEngine."""

from __future__ import annotations

from autonomous_cognition.constitution_audit import (
    AuditMetrics,
    ConstitutionAuditEngine,
    ConstitutionAuditResult,
    ConstitutionViolation,
    ViolationEnforcement,
    ViolationSeverity,
)


class TestConstitutionViolation:
    """Tests for ConstitutionViolation dataclass."""

    def test_violation_creation(self):
        """Violations can be created with all fields."""
        violation = ConstitutionViolation(
            rule_id="VR-001",
            name="Unauthorized Scope Access",
            severity=ViolationSeverity.P1,
            enforcement=ViolationEnforcement.BLOCK,
            description="Agent accessed path outside SCOPE_GLOBS",
            evidence={"file": "forbidden.py"},
        )

        assert violation.rule_id == "VR-001"
        assert violation.severity == ViolationSeverity.P1
        assert violation.enforcement == ViolationEnforcement.BLOCK
        assert violation.evidence["file"] == "forbidden.py"

    def test_violation_defaults(self):
        """Violations have sensible defaults."""
        violation = ConstitutionViolation(
            rule_id="VR-001",
            name="Test",
            severity=ViolationSeverity.P2,
            enforcement=ViolationEnforcement.ALERT,
            description="Test violation",
        )

        assert violation.auto_detect is True
        assert violation.detection_sla_seconds == 300


class TestAuditMetrics:
    """Tests for AuditMetrics dataclass."""

    def test_severity_breakdown(self):
        """Metrics can compute severity breakdown."""
        metrics = AuditMetrics(
            total_actions=10,
            violations_found=3,
            critical_count=1,
            high_count=1,
            medium_count=1,
        )

        breakdown = metrics.severity_breakdown
        assert breakdown["P0"] == 1
        assert breakdown["P1"] == 1
        assert breakdown["P2"] == 1
        assert breakdown["P3"] == 0


class TestConstitutionAuditEngine:
    """Tests for ConstitutionAuditEngine class."""

    def test_default_initialization(self):
        """Engine initializes with constitution defaults."""
        engine = ConstitutionAuditEngine()

        summary = engine.get_violation_summary()
        assert summary["violation_rules_count"] == 5
        assert summary["invariants_count"] == 5

    def test_empty_actions_compliant(self):
        """Empty action list is always compliant."""
        engine = ConstitutionAuditEngine()
        result = engine.run(actions=[], context={})

        assert result.is_compliant is True
        assert result.critical_count == 0
        assert len(result.violations) == 0

    def test_compliant_git_commit_to_feature_branch(self):
        """Git commit to feature branch is compliant."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "git_commit",
                    "details": {"branch": "feature/test"},
                }
            ],
            context={},
        )

        assert result.is_compliant is True

    def test_violation_main_branch_commit(self):
        """Direct commit to main without override is a P0 violation."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "git_commit",
                    "details": {"branch": "main"},
                }
            ],
            context={},
        )

        assert result.is_compliant is False
        assert result.critical_count == 1
        assert result.metrics.critical_count == 1

    def test_main_branch_commit_with_override(self):
        """Direct commit to main with Captain Craig override is allowed."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "git_commit",
                    "details": {"branch": "main"},
                }
            ],
            context={
                "override": {"approved_by": "captain_craig"},
            },
        )

        assert result.is_compliant is True

    def test_unvalidated_trading_execution(self):
        """Trading without backtest/paper validation is a P0 violation."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "trading_execute",
                    "details": {
                        "backtest_passed": False,
                        "paper_passed": False,
                    },
                }
            ],
            context={},
        )

        assert result.is_compliant is False
        assert result.critical_count == 1
        assert result.metrics.critical_count == 1

    def test_validated_trading_execution(self):
        """Trading with backtest and paper passed is compliant."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "trading_execute",
                    "details": {
                        "backtest_passed": True,
                        "paper_passed": True,
                    },
                }
            ],
            context={},
        )

        assert result.is_compliant is True

    def test_protected_container_modification(self):
        """Modifying protected container without approval is P0."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "container_modify",
                    "details": {"container": "tradedev"},
                }
            ],
            context={},
        )

        assert result.is_compliant is False
        assert result.critical_count == 1

    def test_protected_container_with_approval(self):
        """Modifying protected container with Captain Craig approval is allowed."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "container_modify",
                    "details": {"container": "tradedev"},
                }
            ],
            context={
                "override": {"approved_by": "captain_craig"},
            },
        )

        assert result.is_compliant is True

    def test_rate_limit_exceeded(self):
        """API call exceeding rate limit is P1 violation."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "api_call",
                    "details": {"rate_limit_exceeded": True},
                }
            ],
            context={},
        )

        assert result.is_compliant is False
        assert result.metrics.high_count == 1

    def test_scope_compliance(self):
        """Actions within scope globs are compliant."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "edit",
                    "details": {"files": ["src/autonomous_cognition/test.py"]},
                }
            ],
            context={
                "scope_globs": ["src/autonomous_cognition/**"],
            },
        )

        assert result.is_compliant is True

    def test_scope_violation(self):
        """Actions outside scope globs are a P1 violation."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "edit",
                    "details": {"files": ["forbidden.py"]},
                }
            ],
            context={
                "scope_globs": ["src/**"],
            },
        )

        assert result.is_compliant is False
        assert result.metrics.high_count == 1

    def test_multiple_violations(self):
        """Multiple violations are all recorded."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {"type": "git_commit", "details": {"branch": "main"}},
                {"type": "api_call", "details": {"rate_limit_exceeded": True}},
                {"type": "api_call", "details": {"rate_limit_exceeded": True}},
            ],
            context={},
        )

        # INV-001 (main branch) + INV-005 (rate limit) = 2 violations
        # INV invariants are checked per-invariant, not per-action
        assert result.is_compliant is False
        assert len(result.violations) == 2
        assert result.critical_count == 1  # INV-001 is P0

    def test_escalation_required(self):
        """Violations correctly trigger escalation."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "git_commit",
                    "details": {"branch": "main"},
                }
            ],
            context={},
        )

        assert result.requires_escalation is True
        assert result.escalation_severity == "P0"

    def test_recommendations_generated(self):
        """Recommendations are generated for violations."""
        engine = ConstitutionAuditEngine()
        result = engine.run(
            actions=[
                {
                    "type": "git_commit",
                    "details": {"branch": "main"},
                }
            ],
            context={},
        )

        assert len(result.recommendations) > 0
        assert any("CRITICAL" in r for r in result.recommendations)

    def test_audit_history(self):
        """Engine records audit history."""
        engine = ConstitutionAuditEngine()

        engine.run(actions=[], context={})
        engine.run(
            actions=[{"type": "git_commit", "details": {"branch": "main"}}], context={}
        )

        history = engine.get_audit_history()
        assert len(history) == 2

    def test_clear_history(self):
        """History can be cleared."""
        engine = ConstitutionAuditEngine()

        engine.run(actions=[], context={})
        assert len(engine.get_audit_history()) == 1

        engine.clear_history()
        assert len(engine.get_audit_history()) == 0

    def test_validate_constitution_doc(self):
        """Engine validates its own structure."""
        engine = ConstitutionAuditEngine()
        is_valid, errors = engine.validate_constitution_doc()

        assert is_valid is True
        assert len(errors) == 0

    def test_custom_violation_rules(self):
        """Engine can accept custom violation rules."""
        custom_rules = [
            {
                "id": "CUSTOM-001",
                "name": "Custom Violation",
                "pattern": r"custom_pattern",
                "severity": ViolationSeverity.P2,
                "enforcement": ViolationEnforcement.ALERT,
                "auto_detect": True,
            },
        ]

        engine = ConstitutionAuditEngine(violation_rules=custom_rules)
        summary = engine.get_violation_summary()

        assert summary["violation_rules_count"] == 1
        assert summary["violation_rules"][0]["id"] == "CUSTOM-001"


class TestConstitutionAuditResult:
    """Tests for ConstitutionAuditResult dataclass."""

    def test_is_compliant_property(self):
        """is_compliant reflects metrics."""
        metrics = AuditMetrics(total_actions=5, violations_found=0)
        result = ConstitutionAuditResult(
            violations=[],
            metrics=metrics,
        )

        assert result.is_compliant is True

    def test_critical_count_property(self):
        """critical_count delegates to metrics."""
        metrics = AuditMetrics(total_actions=5, violations_found=2, critical_count=1)
        result = ConstitutionAuditResult(
            violations=[],
            metrics=metrics,
        )

        assert result.critical_count == 1
