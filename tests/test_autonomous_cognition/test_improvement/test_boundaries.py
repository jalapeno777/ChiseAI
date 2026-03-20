"""Tests for boundary enforcement in autonomous improvement cycles."""

from __future__ import annotations

from autonomous_cognition.improvement.boundaries import (
    BoundaryConfig,
    BoundaryEnforcer,
    RiskLevel,
)


class TestBoundaryConfig:
    """Tests for BoundaryConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BoundaryConfig()

        assert config.max_files_per_cycle == 10
        assert config.max_lines_per_file == 500
        assert config.max_risk_level == RiskLevel.MEDIUM
        assert config.emergency_stop is False
        assert ".woodpecker.yml" in config.blocked_paths

    def test_custom_config(self):
        """Test custom configuration."""
        config = BoundaryConfig(
            allowed_paths=["src/custom/"],
            blocked_paths=["secrets.yaml"],
            max_files_per_cycle=5,
            max_risk_level=RiskLevel.HIGH,
        )

        assert config.max_files_per_cycle == 5
        assert config.max_risk_level == RiskLevel.HIGH
        assert "secrets.yaml" in config.blocked_paths


class TestBoundaryEnforcer:
    """Tests for BoundaryEnforcer."""

    def test_safe_proposal(self):
        """Test that a safe proposal has no violations."""
        enforcer = BoundaryEnforcer()

        proposal = {
            "files": ["src/autonomous_cognition/improvement/test.py"],
            "risk_level": "low",
            "changes": {"src/autonomous_cognition/improvement/test.py": 50},
        }

        violations = enforcer.check_proposal(proposal)
        assert len(violations) == 0

    def test_blocked_path_violation(self):
        """Test that blocked paths generate violations."""
        enforcer = BoundaryEnforcer()

        proposal = {
            "files": [".woodpecker.yml"],
            "risk_level": "low",
            "changes": {},
        }

        violations = enforcer.check_proposal(proposal)
        assert len(violations) >= 1
        assert any(v.violation_type == "blocked_path" for v in violations)

    def test_outside_scope_violation(self):
        """Test that files outside allowed paths generate violations."""
        enforcer = BoundaryEnforcer()

        proposal = {
            "files": ["src/other_module/file.py"],
            "risk_level": "low",
            "changes": {},
        }

        violations = enforcer.check_proposal(proposal)
        assert len(violations) >= 1
        assert any(v.violation_type == "outside_scope" for v in violations)

    def test_scope_exceeded_violation(self):
        """Test that exceeding max files generates violation."""
        config = BoundaryConfig(max_files_per_cycle=2)
        enforcer = BoundaryEnforcer(config)

        proposal = {
            "files": [
                "src/autonomous_cognition/a.py",
                "src/autonomous_cognition/b.py",
                "src/autonomous_cognition/c.py",
            ],
            "risk_level": "low",
            "changes": {},
        }

        violations = enforcer.check_proposal(proposal)
        assert any(v.violation_type == "scope_exceeded" for v in violations)

    def test_lines_exceeded_violation(self):
        """Test that exceeding max lines generates violation."""
        config = BoundaryConfig(max_lines_per_file=100)
        enforcer = BoundaryEnforcer(config)

        proposal = {
            "files": ["src/autonomous_cognition/big.py"],
            "risk_level": "low",
            "changes": {"src/autonomous_cognition/big.py": 200},
        }

        violations = enforcer.check_proposal(proposal)
        assert any(v.violation_type == "lines_exceeded" for v in violations)

    def test_risk_exceeded_violation(self):
        """Test that exceeding risk level generates violation."""
        config = BoundaryConfig(max_risk_level=RiskLevel.LOW)
        enforcer = BoundaryEnforcer(config)

        proposal = {
            "files": ["src/autonomous_cognition/test.py"],
            "risk_level": "high",
            "changes": {},
        }

        violations = enforcer.check_proposal(proposal)
        assert any(v.violation_type == "risk_exceeded" for v in violations)

    def test_emergency_stop_blocks_all(self):
        """Test that emergency stop blocks all proposals."""
        enforcer = BoundaryEnforcer()
        enforcer.activate_emergency_stop("testing")

        proposal = {
            "files": ["src/autonomous_cognition/test.py"],
            "risk_level": "low",
            "changes": {},
        }

        violations = enforcer.check_proposal(proposal)
        assert len(violations) == 1
        assert violations[0].violation_type == "emergency_stop"
        assert violations[0].severity == "critical"

    def test_emergency_stop_deactivate(self):
        """Test deactivating emergency stop."""
        enforcer = BoundaryEnforcer()

        enforcer.activate_emergency_stop()
        assert enforcer.emergency_stop_active is True

        enforcer.deactivate_emergency_stop()
        assert enforcer.emergency_stop_active is False

        # Now proposals should work
        proposal = {
            "files": ["src/autonomous_cognition/test.py"],
            "risk_level": "low",
            "changes": {},
        }

        violations = enforcer.check_proposal(proposal)
        assert len(violations) == 0

    def test_is_safe(self):
        """Test is_safe convenience method."""
        enforcer = BoundaryEnforcer()

        safe_proposal = {
            "files": ["src/autonomous_cognition/test.py"],
            "risk_level": "low",
            "changes": {},
        }
        assert enforcer.is_safe(safe_proposal) is True

        unsafe_proposal = {
            "files": [".woodpecker.yml"],
            "risk_level": "low",
            "changes": {},
        }
        assert enforcer.is_safe(unsafe_proposal) is False

    def test_violation_history(self):
        """Test violation recording and clearing."""
        enforcer = BoundaryEnforcer()

        proposal = {
            "files": [".woodpecker.yml"],
            "risk_level": "low",
            "changes": {},
        }

        enforcer.check_proposal(proposal)
        violations = enforcer.get_violations()
        assert len(violations) >= 1

        enforcer.clear_violations()
        assert len(enforcer.get_violations()) == 0
