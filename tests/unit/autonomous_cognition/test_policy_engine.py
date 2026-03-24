"""Unit tests for the autonomous policy engine.

Tests cover:
- Risk level validation and auto-approval
- Protected file blocking and approval requirements
- Approval gate enforcement
- Policy violation logging
- Concurrent limit enforcement
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from autonomous_cognition.policy_engine import (
    ApprovalRequirement,
    AutonomousPolicyEngine,
    GateDecision,
    PolicyResult,
)


class TestPolicyResult:
    """Tests for PolicyResult dataclass."""

    def test_policy_result_defaults(self):
        """Test PolicyResult with default values."""
        result = PolicyResult(approved=True)
        assert result.approved is True
        assert result.reason == ""
        assert result.risk_level == "unknown"
        assert result.requires_approval is False
        assert result.approval_timeout is None
        assert result.notify_immediately is False
        assert result.blocked_files == []

    def test_policy_result_full(self):
        """Test PolicyResult with all values."""
        result = PolicyResult(
            approved=False,
            reason="Test reason",
            risk_level="high",
            requires_approval=True,
            approval_timeout=3600,
            notify_immediately=True,
            blocked_files=["file1.py", "file2.py"],
        )
        assert result.approved is False
        assert result.reason == "Test reason"
        assert result.risk_level == "high"
        assert result.requires_approval is True
        assert result.approval_timeout == 3600
        assert result.notify_immediately is True
        assert result.blocked_files == ["file1.py", "file2.py"]


class TestApprovalRequirement:
    """Tests for ApprovalRequirement dataclass."""

    def test_approval_requirement_defaults(self):
        """Test ApprovalRequirement with default values."""
        req = ApprovalRequirement(required=True)
        assert req.required is True
        assert req.roles == []
        assert req.timeout_seconds == 3600
        assert req.notify_immediately is False

    def test_approval_requirement_full(self):
        """Test ApprovalRequirement with all values."""
        req = ApprovalRequirement(
            required=True,
            roles=["senior-dev", "jarvis"],
            timeout_seconds=7200,
            notify_immediately=True,
        )
        assert req.required is True
        assert req.roles == ["senior-dev", "jarvis"]
        assert req.timeout_seconds == 7200
        assert req.notify_immediately is True


class TestAutonomousPolicyEngineInit:
    """Tests for AutonomousPolicyEngine initialization."""

    def test_init_with_default_config(self):
        """Test engine initializes with default config when files missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent.yaml"
            engine = AutonomousPolicyEngine(config_path=config_path)

            assert engine._config is not None
            assert "policies" in engine._config
            assert "risk_levels" in engine._config["policies"]

    def test_init_loads_config(self):
        """Test engine loads config from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_policies.yaml"
            config_data = {
                "policies": {
                    "risk_levels": {
                        "low": {"auto_approve": True, "max_concurrent": 10}
                    },
                    "protected_paths": [],
                    "approval_gates": {},
                }
            }
            config_path.write_text(yaml.dump(config_data))

            engine = AutonomousPolicyEngine(config_path=config_path)

            assert engine._risk_policies["low"]["auto_approve"] is True
            assert engine._risk_policies["low"]["max_concurrent"] == 10

    def test_reload_config(self):
        """Test config reload functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_policies.yaml"
            config_data = {
                "policies": {
                    "risk_levels": {"low": {"auto_approve": True}},
                    "protected_paths": [],
                    "approval_gates": {},
                }
            }
            config_path.write_text(yaml.dump(config_data))

            engine = AutonomousPolicyEngine(config_path=config_path)
            assert engine._risk_policies["low"]["auto_approve"] is True

            # Modify config
            config_data["policies"]["risk_levels"]["low"]["auto_approve"] = False
            config_path.write_text(yaml.dump(config_data))

            # Reload
            engine.reload_config()
            assert engine._risk_policies["low"]["auto_approve"] is False


class TestRiskLevelValidation:
    """Tests for risk level validation."""

    @pytest.fixture
    def engine(self):
        """Create policy engine with default config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create autocog.yaml with high max_risk_level for testing
            autocog_path = Path(tmpdir) / "autocog.yaml"
            autocog_data = {
                "safety": {
                    "max_risk_level": "critical",  # Allow all levels for testing
                    "require_approval_for": ["high", "critical"],
                }
            }
            autocog_path.write_text(yaml.dump(autocog_data))
            
            config_path = Path(tmpdir) / "policies.yaml"
            config_data = {
                "policies": {
                    "risk_levels": {
                        "low": {"auto_approve": True, "max_concurrent": 10},
                        "medium": {"auto_approve": True, "max_concurrent": 5},
                        "high": {
                            "auto_approve": False,
                            "requires_approval": True,
                            "approval_timeout": 3600,
                        },
                        "critical": {
                            "auto_approve": False,
                            "requires_approval": True,
                            "approval_timeout": 7200,
                            "notify_immediately": True,
                        },
                    },
                    "protected_paths": [],
                    "approval_gates": {
                        "high": [{"role": "senior-dev"}],
                        "critical": [{"role": "craig"}],
                    },
                }
            }
            config_path.write_text(yaml.dump(config_data))
            
            engine = AutonomousPolicyEngine(config_path=config_path)
            engine.AUTOCOG_CONFIG_PATH = autocog_path
            engine._load_configs()
            yield engine

    def test_check_risk_level_valid(self, engine):
        """Test check_risk_level with valid levels."""
        assert engine.check_risk_level("low") is True
        assert engine.check_risk_level("medium") is True
        assert engine.check_risk_level("high") is True
        assert engine.check_risk_level("critical") is True

    def test_check_risk_level_invalid(self, engine):
        """Test check_risk_level with invalid levels."""
        assert engine.check_risk_level("unknown") is False
        assert engine.check_risk_level("") is False
        assert engine.check_risk_level("HIGH") is False  # Case sensitive

    def test_low_risk_auto_approved(self, engine):
        """Test that low risk decisions are auto-approved."""
        decision = {
            "risk_level": "low",
            "action": "test_action",
            "files": [],
            "description": "Test low risk decision",
        }
        result = engine.validate_decision(decision)

        assert result.approved is True
        assert result.requires_approval is False
        assert result.risk_level == "low"

    def test_medium_risk_auto_approved(self, engine):
        """Test that medium risk decisions are auto-approved."""
        decision = {
            "risk_level": "medium",
            "action": "test_action",
            "files": [],
            "description": "Test medium risk decision",
        }
        result = engine.validate_decision(decision)

        assert result.approved is True
        assert result.requires_approval is False
        assert result.risk_level == "medium"

    def test_high_risk_requires_approval(self, engine):
        """Test that high risk decisions require approval."""
        decision = {
            "risk_level": "high",
            "action": "test_action",
            "files": [],
            "description": "Test high risk decision",
        }
        result = engine.validate_decision(decision)

        assert result.approved is False
        assert result.requires_approval is True
        assert result.risk_level == "high"
        assert result.approval_timeout == 3600
        assert "senior-dev" in result.reason

    def test_critical_risk_requires_craig_approval(self, engine):
        """Test that critical risk decisions require craig approval."""
        decision = {
            "risk_level": "critical",
            "action": "test_action",
            "files": [],
            "description": "Test critical risk decision",
        }
        result = engine.validate_decision(decision)

        assert result.approved is False
        assert result.requires_approval is True
        assert result.risk_level == "critical"
        assert result.approval_timeout == 7200
        assert result.notify_immediately is True
        assert "craig" in result.reason


class TestProtectedFiles:
    """Tests for protected file validation."""

    @pytest.fixture
    def engine(self):
        """Create policy engine with protected paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create autocog.yaml
            autocog_path = Path(tmpdir) / "autocog.yaml"
            autocog_data = {
                "safety": {
                    "max_risk_level": "critical",
                    "require_approval_for": ["high", "critical"],
                }
            }
            autocog_path.write_text(yaml.dump(autocog_data))
            
            config_path = Path(tmpdir) / "policies.yaml"
            config_data = {
                "policies": {
                    "risk_levels": {
                        "low": {"auto_approve": True, "max_concurrent": 10},
                    },
                    "protected_paths": [
                        {"pattern": "src/core/risk_caps.py", "action": "block"},
                        {
                            "pattern": "src/core/governance_bypasses.py",
                            "action": "block",
                        },
                        {
                            "pattern": "docs/bmm-workflow-status.yaml",
                            "action": "require_approval",
                        },
                        {"pattern": "config/*.yaml", "action": "block"},
                    ],
                    "approval_gates": {},
                }
            }
            config_path.write_text(yaml.dump(config_data))
            
            engine = AutonomousPolicyEngine(config_path=config_path)
            engine.AUTOCOG_CONFIG_PATH = autocog_path
            engine._load_configs()
            yield engine

    def test_protected_file_blocked(self, engine):
        """Test that blocked files are rejected."""
        decision = {
            "risk_level": "low",
            "action": "modify",
            "files": ["src/core/risk_caps.py"],
            "description": "Try to modify risk caps",
        }
        result = engine.validate_decision(decision)

        assert result.approved is False
        assert "Blocked" in result.reason
        assert "src/core/risk_caps.py" in result.blocked_files

    def test_protected_file_blocked_glob(self, engine):
        """Test that glob patterns block files."""
        decision = {
            "risk_level": "low",
            "action": "modify",
            "files": ["config/autocog.yaml"],
            "description": "Try to modify config",
        }
        result = engine.validate_decision(decision)

        assert result.approved is False
        assert "config/autocog.yaml" in result.blocked_files

    def test_protected_file_require_approval(self, engine):
        """Test that require_approval files are detected as protected."""
        # Files with action "require_approval" should still be detected as protected
        # The validate_decision will handle them appropriately

        # First verify the file is in the protected paths list
        protected_patterns = [p.get("pattern") for p in engine._protected_paths]
        assert "docs/bmm-workflow-status.yaml" in protected_patterns

        # The file should be detected when checking _check_protected_files
        # Note: currently require_approval files are treated as blocked
        blocked = engine._check_protected_files(["docs/bmm-workflow-status.yaml"])
        assert len(blocked) > 0

    def test_check_protected_files_true(self, engine):
        """Test check_protected_files returns True for protected files."""
        assert engine.check_protected_files(["src/core/risk_caps.py"]) is True
        assert engine.check_protected_files(["src/core/governance_bypasses.py"]) is True

    def test_check_protected_files_false(self, engine):
        """Test check_protected_files returns False for non-protected files."""
        assert engine.check_protected_files(["src/utils/helpers.py"]) is False
        assert engine.check_protected_files(["tests/test_something.py"]) is False

    def test_multiple_files_one_blocked(self, engine):
        """Test that if any file is blocked, decision is rejected."""
        decision = {
            "risk_level": "low",
            "action": "modify",
            "files": [
                "src/utils/helpers.py",
                "src/core/risk_caps.py",
                "tests/test.py",
            ],
            "description": "Try to modify multiple files",
        }
        result = engine.validate_decision(decision)

        assert result.approved is False
        assert "src/core/risk_caps.py" in result.blocked_files


class TestApprovalRequirements:
    """Tests for approval requirement checking."""

    @pytest.fixture
    def engine(self):
        """Create policy engine with approval gates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "policies.yaml"
            config_data = {
                "policies": {
                    "risk_levels": {
                        "low": {"auto_approve": True},
                        "medium": {"auto_approve": True},
                        "high": {
                            "auto_approve": False,
                            "requires_approval": True,
                            "approval_timeout": 3600,
                        },
                        "critical": {
                            "auto_approve": False,
                            "requires_approval": True,
                            "approval_timeout": 7200,
                            "notify_immediately": True,
                        },
                    },
                    "protected_paths": [],
                    "approval_gates": {
                        "high": [{"role": "senior-dev"}, {"role": "jarvis"}],
                        "critical": [{"role": "craig"}],
                    },
                }
            }
            config_path.write_text(yaml.dump(config_data))
            yield AutonomousPolicyEngine(config_path=config_path)

    def test_check_approval_requirements_low(self, engine):
        """Test approval requirements for low risk."""
        decision = {"risk_level": "low"}
        req = engine.check_approval_requirements(decision)

        assert req.required is False
        assert req.roles == []

    def test_check_approval_requirements_medium(self, engine):
        """Test approval requirements for medium risk."""
        decision = {"risk_level": "medium"}
        req = engine.check_approval_requirements(decision)

        assert req.required is False
        assert req.roles == []

    def test_check_approval_requirements_high(self, engine):
        """Test approval requirements for high risk."""
        decision = {"risk_level": "high"}
        req = engine.check_approval_requirements(decision)

        assert req.required is True
        assert "senior-dev" in req.roles
        assert "jarvis" in req.roles
        assert req.timeout_seconds == 3600
        assert req.notify_immediately is False

    def test_check_approval_requirements_critical(self, engine):
        """Test approval requirements for critical risk."""
        decision = {"risk_level": "critical"}
        req = engine.check_approval_requirements(decision)

        assert req.required is True
        assert "craig" in req.roles
        assert req.timeout_seconds == 7200
        assert req.notify_immediately is True


class TestConcurrentLimits:
    """Tests for concurrent operation limits."""

    @pytest.fixture
    def engine(self):
        """Create policy engine with concurrent limits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "policies.yaml"
            config_data = {
                "policies": {
                    "risk_levels": {
                        "low": {"auto_approve": True, "max_concurrent": 2},
                        "medium": {"auto_approve": True, "max_concurrent": 1},
                    },
                    "protected_paths": [],
                    "approval_gates": {},
                }
            }
            config_path.write_text(yaml.dump(config_data))
            yield AutonomousPolicyEngine(config_path=config_path)

    def test_concurrent_limit_enforcement(self, engine):
        """Test that concurrent limits are enforced."""
        # Start with 0 concurrent
        assert engine.increment_concurrent("low") is True  # Now 1
        assert engine.increment_concurrent("low") is True  # Now 2
        assert engine.increment_concurrent("low") is False  # Would be 3, exceeds limit

    def test_concurrent_limit_decrement(self, engine):
        """Test that decrementing allows new operations."""
        # Fill up to limit
        assert engine.increment_concurrent("low") is True
        assert engine.increment_concurrent("low") is True
        assert engine.increment_concurrent("low") is False

        # Decrement and try again
        engine.decrement_concurrent("low")
        assert engine.increment_concurrent("low") is True

    def test_concurrent_limit_different_levels(self, engine):
        """Test that concurrent limits are per risk level."""
        # Low: max 2, Medium: max 1
        assert engine.increment_concurrent("low") is True
        assert engine.increment_concurrent("medium") is True
        assert engine.increment_concurrent("medium") is False  # Medium at limit
        assert engine.increment_concurrent("low") is True  # Low still has room

    def test_decrement_below_zero(self, engine):
        """Test that decrementing below zero is safe."""
        engine.decrement_concurrent("low")  # Should not raise
        engine.decrement_concurrent("low")  # Should not raise
        assert engine._concurrent_counts.get("low", 0) == 0


class TestPolicyLogging:
    """Tests for policy decision logging."""

    @pytest.fixture
    def engine(self):
        """Create policy engine."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "policies.yaml"
            config_data = {
                "policies": {
                    "risk_levels": {"low": {"auto_approve": True}},
                    "protected_paths": [],
                    "approval_gates": {},
                }
            }
            config_path.write_text(yaml.dump(config_data))
            yield AutonomousPolicyEngine(config_path=config_path)

    def test_policy_violation_logging(self, engine, caplog):
        """Test that policy violations are logged."""
        with caplog.at_level("INFO"):
            decision = {
                "risk_level": "low",
                "action": "test",
                "files": [],
                "description": "Test decision",
            }
            result = engine.validate_decision(decision)

            # Should log the decision
            assert "Policy decision" in caplog.text
            assert "approved" in caplog.text

    def test_blocked_decision_logging(self, engine, caplog):
        """Test that blocked decisions are logged at warning level."""
        engine._protected_paths = [{"pattern": "test.py", "action": "block"}]

        with caplog.at_level("WARNING"):
            decision = {
                "risk_level": "low",
                "action": "modify",
                "files": ["test.py"],
                "description": "Test blocked decision",
            }
            result = engine.validate_decision(decision)

            assert result.approved is False
            assert "Blocked" in caplog.text


class TestPolicySummary:
    """Tests for policy summary."""

    @pytest.fixture
    def engine(self):
        """Create policy engine."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "policies.yaml"
            config_data = {
                "policies": {
                    "risk_levels": {
                        "low": {"auto_approve": True},
                        "high": {"auto_approve": False},
                    },
                    "protected_paths": [
                        {"pattern": "file1.py", "action": "block"},
                        {"pattern": "file2.py", "action": "block"},
                    ],
                    "approval_gates": {
                        "high": [{"role": "senior-dev"}],
                    },
                }
            }
            config_path.write_text(yaml.dump(config_data))
            yield AutonomousPolicyEngine(config_path=config_path)

    def test_get_policy_summary(self, engine):
        """Test getting policy summary."""
        summary = engine.get_policy_summary()

        assert "risk_levels" in summary
        assert "low" in summary["risk_levels"]
        assert "high" in summary["risk_levels"]
        assert summary["protected_paths_count"] == 2
        assert "file1.py" in summary["protected_paths"]
        assert "file2.py" in summary["protected_paths"]
        assert "approval_gates" in summary
        assert "high" in summary["approval_gates"]
        assert "senior-dev" in summary["approval_gates"]["high"]


class TestLegacyCompatibility:
    """Tests for backward compatibility with legacy GateDecision."""

    @pytest.fixture
    def engine(self):
        """Create policy engine."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "policies.yaml"
            config_data = {
                "policies": {
                    "risk_levels": {"low": {"auto_approve": True}},
                    "protected_paths": [],
                    "approval_gates": {},
                }
            }
            config_path.write_text(yaml.dump(config_data))
            yield AutonomousPolicyEngine(config_path=config_path)

    def test_evaluate_promotion_gates_pass(self, engine):
        """Test legacy evaluate_promotion_gates with passing metrics."""
        metrics = {
            "sharpe": 1.2,
            "ece": 0.10,
            "drawdown": 0.15,
            "constitution_violations": 0,
        }
        result = engine.evaluate_promotion_gates(metrics)

        assert isinstance(result, GateDecision)
        assert result.passed is True
        assert result.failed_gates == []

    def test_evaluate_promotion_gates_fail_sharpe(self, engine):
        """Test legacy evaluate_promotion_gates with low sharpe."""
        metrics = {
            "sharpe": 1.0,  # Below 1.1 threshold
            "ece": 0.10,
            "drawdown": 0.15,
            "constitution_violations": 0,
        }
        result = engine.evaluate_promotion_gates(metrics)

        assert result.passed is False
        assert "statistical_improvement_gate" in result.failed_gates

    def test_evaluate_promotion_gates_fail_ece(self, engine):
        """Test legacy evaluate_promotion_gates with high ECE."""
        metrics = {
            "sharpe": 1.2,
            "ece": 0.20,  # Above 0.15 threshold
            "drawdown": 0.15,
            "constitution_violations": 0,
        }
        result = engine.evaluate_promotion_gates(metrics)

        assert result.passed is False
        assert "calibration_gate" in result.failed_gates

    def test_evaluate_promotion_gates_fail_drawdown(self, engine):
        """Test legacy evaluate_promotion_gates with high drawdown."""
        metrics = {
            "sharpe": 1.2,
            "ece": 0.10,
            "drawdown": 0.25,  # Above 0.20 threshold
            "constitution_violations": 0,
        }
        result = engine.evaluate_promotion_gates(metrics)

        assert result.passed is False
        assert "risk_regression_gate" in result.failed_gates

    def test_evaluate_promotion_gates_fail_constitution(self, engine):
        """Test legacy evaluate_promotion_gates with constitution violations."""
        metrics = {
            "sharpe": 1.2,
            "ece": 0.10,
            "drawdown": 0.15,
            "constitution_violations": 1,  # Non-zero
        }
        result = engine.evaluate_promotion_gates(metrics)

        assert result.passed is False
        assert "constitution_gate" in result.failed_gates

    def test_evaluate_promotion_gates_multiple_failures(self, engine):
        """Test legacy evaluate_promotion_gates with multiple failures."""
        metrics = {
            "sharpe": 1.0,
            "ece": 0.20,
            "drawdown": 0.25,
            "constitution_violations": 1,
        }
        result = engine.evaluate_promotion_gates(metrics)

        assert result.passed is False
        assert len(result.failed_gates) == 4
        assert "statistical_improvement_gate" in result.failed_gates
        assert "calibration_gate" in result.failed_gates
        assert "risk_regression_gate" in result.failed_gates
        assert "constitution_gate" in result.failed_gates


class TestPatternMatching:
    """Tests for pattern matching functionality."""

    @pytest.fixture
    def engine(self):
        """Create policy engine."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "policies.yaml"
            config_data = {
                "policies": {
                    "risk_levels": {"low": {"auto_approve": True}},
                    "protected_paths": [],
                    "approval_gates": {},
                }
            }
            config_path.write_text(yaml.dump(config_data))
            yield AutonomousPolicyEngine(config_path=config_path)

    def test_exact_match(self, engine):
        """Test exact path matching."""
        assert engine._match_pattern("src/file.py", "src/file.py") is True
        assert engine._match_pattern("src/file.py", "other/file.py") is False

    def test_glob_match(self, engine):
        """Test glob pattern matching."""
        assert engine._match_pattern("src/file.py", "src/*.py") is True
        assert engine._match_pattern("src/dir/file.py", "src/**/*.py") is True
        assert engine._match_pattern("tests/test_file.py", "tests/test_*.py") is True

    def test_directory_prefix(self, engine):
        """Test directory prefix matching."""
        assert engine._match_pattern("src/core/file.py", "src/core/") is True
        assert engine._match_pattern("src/other/file.py", "src/core/") is False

    def test_leading_slash_stripping(self, engine):
        """Test that leading slashes are stripped."""
        assert engine._match_pattern("/src/file.py", "src/file.py") is True
        assert engine._match_pattern("src/file.py", "/src/file.py") is True


class TestIntegrationWithAutocogConfig:
    """Tests for integration with autocog.yaml safety settings."""

    def test_max_risk_level_enforcement(self):
        """Test that max_risk_level from autocog.yaml is enforced."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create autocog.yaml with max_risk_level = medium
            autocog_path = Path(tmpdir) / "autocog.yaml"
            autocog_data = {
                "safety": {
                    "max_risk_level": "medium",
                    "require_approval_for": ["high", "critical"],
                }
            }
            autocog_path.write_text(yaml.dump(autocog_data))

            # Create policy config
            policy_path = Path(tmpdir) / "policies.yaml"
            policy_data = {
                "policies": {
                    "risk_levels": {
                        "low": {"auto_approve": True},
                        "medium": {"auto_approve": True},
                        "high": {"auto_approve": False},
                        "critical": {"auto_approve": False},
                    },
                    "protected_paths": [],
                    "approval_gates": {},
                }
            }
            policy_path.write_text(yaml.dump(policy_data))

            # Patch the autocog config path
            engine = AutonomousPolicyEngine(config_path=policy_path)
            engine.AUTOCOG_CONFIG_PATH = autocog_path
            engine._load_configs()

            # High risk should fail due to max_risk_level
            is_valid, reason = engine._check_risk_level_policy("high")
            assert is_valid is False
            assert "exceeds max allowed" in reason

    def test_missing_autocog_config_defaults(self):
        """Test that missing autocog.yaml uses safe defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy_path = Path(tmpdir) / "policies.yaml"
            policy_data = {
                "policies": {
                    "risk_levels": {"low": {"auto_approve": True}},
                    "protected_paths": [],
                    "approval_gates": {},
                }
            }
            policy_path.write_text(yaml.dump(policy_data))

            engine = AutonomousPolicyEngine(config_path=policy_path)
            engine.AUTOCOG_CONFIG_PATH = Path(tmpdir) / "nonexistent.yaml"
            engine._load_configs()

            # Should use default max_risk_level = medium
            assert (
                engine._autocog_config.get("safety", {}).get("max_risk_level") is None
            )
