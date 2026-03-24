"""Tests for Constitution core class (ST-GOV-002)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from src.governance.constitution.constitution import (
    ConditionalInvariant,
    Constitution,
    ConstitutionStatus,
    ConstitutionVersion,
    DecisionBoundary,
    EnforcementAction,
    EscalationPath,
    EscalationStep,
    EscalationTrigger,
    Invariant,
    SeverityLevel,
    ViolationRule,
    ViolationSeverity,
)


class TestConstitutionVersion:
    """Tests for ConstitutionVersion class."""

    def test_parse_valid_version(self):
        """Test parsing a valid version string."""
        version = ConstitutionVersion.parse("1.2.3")
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3

    def test_parse_invalid_version(self):
        """Test parsing an invalid version string."""
        with pytest.raises(ValueError, match="Invalid version string"):
            ConstitutionVersion.parse("1.2")

        with pytest.raises(ValueError, match="Invalid version string"):
            ConstitutionVersion.parse("v1.0.0")

    def test_version_comparison(self):
        """Test version comparison."""
        v1 = ConstitutionVersion(1, 0, 0)
        v2 = ConstitutionVersion(1, 1, 0)
        v3 = ConstitutionVersion(2, 0, 0)

        assert v1 < v2
        assert v2 < v3
        assert v1 < v3
        assert v1 <= v1
        assert v1 <= v2

    def test_version_string(self):
        """Test version string representation."""
        version = ConstitutionVersion(1, 2, 3)
        assert str(version) == "1.2.3"


class TestConstitutionLoad:
    """Tests for Constitution loading."""

    @pytest.fixture
    def sample_constitution_data(self):
        """Create sample constitution data."""
        return {
            "version": "1.0.0",
            "effective_date": "2026-02-22T00:00:00Z",
            "status": "active",
            "governed_by": "ST-GOV-002",
            "principles": {
                "core_values": [
                    {
                        "name": "Safety First",
                        "description": "Test description",
                        "rules": ["Rule 1", "Rule 2"],
                    }
                ]
            },
            "decision_boundaries": {
                "autonomous": [
                    {
                        "category": "Monitoring",
                        "action": "Health checks",
                        "constraints": ["Read-only"],
                    }
                ],
                "conditional": [],
                "restricted": [],
            },
            "safety_invariants": {
                "hard_constraints": [
                    {
                        "id": "INV-001",
                        "name": "Test Invariant",
                        "description": "Test description",
                        "enforcement": "BLOCK",
                        "exception": None,
                    }
                ],
                "conditional": [
                    {
                        "id": "CINV-001",
                        "name": "Test Conditional",
                        "description": "Test description",
                        "trigger": "Test trigger",
                        "enforcement": "ALERT",
                        "resolution": "Test resolution",
                    }
                ],
            },
            "escalation_criteria": {
                "triggers": [
                    {
                        "trigger": "Test trigger",
                        "severity": "P1",
                        "escalation_path": "default",
                        "response_sla": "5 minutes",
                    }
                ],
                "paths": [
                    {
                        "path": "default",
                        "steps": [
                            {
                                "level": 1,
                                "target": "#alerts",
                                "channel": "discord",
                                "auto": True,
                                "delay_minutes": 0,
                            }
                        ],
                    }
                ],
            },
            "violation_categories": {
                "severity_levels": [
                    {
                        "level": "P0",
                        "name": "Critical",
                        "description": "Critical issue",
                        "detection_sla_seconds": 60,
                        "response_sla_minutes": 5,
                        "requires_human_intervention": True,
                    }
                ],
                "detection_rules": [
                    {
                        "id": "VR-001",
                        "name": "Test Rule",
                        "pattern": "test.*pattern",
                        "severity": "P1",
                        "auto_detect": True,
                    }
                ],
            },
            "override_protocol": {
                "requirements": {"required_fields": ["override_id"]},
                "approval_flow": [],
                "rollback": {
                    "window_hours": 24,
                    "automatic_rollback": False,
                    "requires_confirmation": True,
                },
            },
            "compliance_metrics": {
                "kpis": [],
                "reporting": [],
            },
            "version_history": [
                {
                    "version": "1.0.0",
                    "date": "2026-02-22",
                    "changes": "Initial",
                    "author": "ST-GOV-002",
                }
            ],
        }

    def test_from_dict(self, sample_constitution_data):
        """Test creating Constitution from dictionary."""
        constitution = Constitution._from_dict(sample_constitution_data)

        assert constitution.version.major == 1
        assert constitution.version.minor == 0
        assert constitution.version.patch == 0
        assert constitution.status == ConstitutionStatus.ACTIVE
        assert constitution.governed_by == "ST-GOV-002"

    def test_to_dict(self, sample_constitution_data):
        """Test converting Constitution to dictionary."""
        constitution = Constitution._from_dict(sample_constitution_data)
        result = constitution.to_dict()

        assert result["version"] == "1.0.0"
        assert result["status"] == "active"
        assert result["governed_by"] == "ST-GOV-002"
        assert "principles" in result

    def test_get_invariant(self, sample_constitution_data):
        """Test getting an invariant by ID."""
        constitution = Constitution._from_dict(sample_constitution_data)

        invariant = constitution.get_invariant("INV-001")
        assert invariant is not None
        assert invariant.name == "Test Invariant"
        assert invariant.enforcement == EnforcementAction.BLOCK

        # Non-existent invariant
        assert constitution.get_invariant("INV-999") is None

    def test_get_conditional_invariant(self, sample_constitution_data):
        """Test getting a conditional invariant by ID."""
        constitution = Constitution._from_dict(sample_constitution_data)

        invariant = constitution.get_conditional_invariant("CINV-001")
        assert invariant is not None
        assert invariant.name == "Test Conditional"
        assert invariant.trigger == "Test trigger"

        # Non-existent invariant
        assert constitution.get_conditional_invariant("CINV-999") is None

    def test_get_violation_rule(self, sample_constitution_data):
        """Test getting a violation rule by ID."""
        constitution = Constitution._from_dict(sample_constitution_data)

        rule = constitution.get_violation_rule("VR-001")
        assert rule is not None
        assert rule.name == "Test Rule"
        assert rule.severity == ViolationSeverity.P1

        # Non-existent rule
        assert constitution.get_violation_rule("VR-999") is None

    def test_check_violation(self, sample_constitution_data):
        """Test checking for violations."""
        constitution = Constitution._from_dict(sample_constitution_data)

        # Should match VR-001 pattern "test.*pattern"
        violations = constitution.check_violation("this is a test pattern")
        assert len(violations) == 1
        assert violations[0].id == "VR-001"

        # Should not match
        violations = constitution.check_violation("this is clean")
        assert len(violations) == 0

    def test_check_decision_boundary(self, sample_constitution_data):
        """Test checking decision boundaries."""
        constitution = Constitution._from_dict(sample_constitution_data)

        boundary = constitution.check_decision_boundary("autonomous", "Health checks")
        assert boundary is not None
        assert boundary.category == "Monitoring"

        # Non-existent boundary
        assert (
            constitution.check_decision_boundary("autonomous", "Unknown action") is None
        )

    def test_get_escalation_path(self, sample_constitution_data):
        """Test getting escalation path."""
        constitution = Constitution._from_dict(sample_constitution_data)

        path = constitution.get_escalation_path("default")
        assert path is not None
        assert path.path == "default"
        assert len(path.steps) == 1

        # Non-existent path
        assert constitution.get_escalation_path("unknown") is None

    def test_get_escalation_triggers(self, sample_constitution_data):
        """Test getting escalation triggers."""
        constitution = Constitution._from_dict(sample_constitution_data)

        triggers = constitution.get_escalation_triggers()
        assert len(triggers) == 1
        assert triggers[0].trigger == "Test trigger"

        # Filter by severity
        triggers = constitution.get_escalation_triggers(ViolationSeverity.P1)
        assert len(triggers) == 1

        triggers = constitution.get_escalation_triggers(ViolationSeverity.P0)
        assert len(triggers) == 0

    def test_get_severity_level(self, sample_constitution_data):
        """Test getting severity level."""
        constitution = Constitution._from_dict(sample_constitution_data)

        level = constitution.get_severity_level("P0")
        assert level is not None
        assert level.name == "Critical"
        assert level.requires_human_intervention is True

        # Non-existent level
        assert constitution.get_severity_level("P5") is None

    def test_validate_action(self, sample_constitution_data):
        """Test validating an action."""
        constitution = Constitution._from_dict(sample_constitution_data)

        result = constitution.validate_action("Health checks")
        assert result["valid"] is True
        assert result["requires_approval"] is False

    def test_get_health_status(self, sample_constitution_data):
        """Test getting health status."""
        constitution = Constitution._from_dict(sample_constitution_data)

        health = constitution.get_health_status()
        assert health["status"] == "healthy"
        assert health["version"] == "1.0.0"
        assert health["invariant_count"] == 1

    def test_get_compliance_summary(self, sample_constitution_data):
        """Test getting compliance summary."""
        constitution = Constitution._from_dict(sample_constitution_data)

        summary = constitution.get_compliance_summary()
        assert summary["total_kpis"] == 0
        assert summary["reporting_schedules"] == 0


class TestConstitutionVersionManagement:
    """Tests for version management."""

    @patch("pathlib.Path.glob")
    @patch("pathlib.Path.exists")
    def test_list_versions(self, mock_exists, mock_glob):
        """Test listing versions."""
        mock_exists.return_value = True
        mock_glob.return_value = [
            Path("v1.0.0.json"),
            Path("v1.1.0.json"),
            Path("v2.0.0.json"),
        ]

        versions = Constitution.list_versions()
        assert len(versions) == 3
        assert str(versions[0]) == "2.0.0"  # Sorted newest first
        assert str(versions[1]) == "1.1.0"
        assert str(versions[2]) == "1.0.0"

    @patch("pathlib.Path.glob")
    @patch("pathlib.Path.exists")
    def test_get_latest_version(self, mock_exists, mock_glob):
        """Test getting latest version."""
        mock_exists.return_value = True
        mock_glob.return_value = [
            Path("v1.0.0.json"),
            Path("v2.0.0.json"),
        ]

        latest = Constitution.get_latest_version()
        assert latest is not None
        assert str(latest) == "2.0.0"

    @patch("pathlib.Path.exists")
    def test_get_latest_version_no_versions(self, mock_exists):
        """Test getting latest version when none exist."""
        mock_exists.return_value = False

        latest = Constitution.get_latest_version()
        assert latest is None


class TestConstitutionValidation:
    """Tests for constitution validation."""

    def test_validate_against_schema_no_jsonschema(self):
        """Test validation when jsonschema not available."""
        with patch("src.governance.constitution.constitution.HAS_JSONSCHEMA", False):
            # Should not raise
            Constitution._validate_against_schema({"version": "1.0.0"})

    def test_validate_against_schema_no_schema_file(self):
        """Test validation when schema file doesn't exist."""
        with patch("src.governance.constitution.constitution.HAS_JSONSCHEMA", True):
            with patch("pathlib.Path.exists", return_value=False):
                # Should not raise
                Constitution._validate_against_schema({"version": "1.0.0"})


class TestInvariant:
    """Tests for Invariant class."""

    def test_to_dict(self):
        """Test converting Invariant to dictionary."""
        invariant = Invariant(
            id="INV-001",
            name="Test Invariant",
            description="Test description",
            enforcement=EnforcementAction.BLOCK,
            exception="Test exception",
        )

        result = invariant.to_dict()
        assert result["id"] == "INV-001"
        assert result["name"] == "Test Invariant"
        assert result["enforcement"] == "BLOCK"
        assert result["exception"] == "Test exception"


class TestConditionalInvariant:
    """Tests for ConditionalInvariant class."""

    def test_to_dict(self):
        """Test converting ConditionalInvariant to dictionary."""
        invariant = ConditionalInvariant(
            id="CINV-001",
            name="Test Conditional",
            description="Test description",
            trigger="Test trigger",
            enforcement=EnforcementAction.ALERT,
            resolution="Test resolution",
        )

        result = invariant.to_dict()
        assert result["id"] == "CINV-001"
        assert result["trigger"] == "Test trigger"
        assert result["resolution"] == "Test resolution"


class TestViolationRule:
    """Tests for ViolationRule class."""

    def test_to_dict(self):
        """Test converting ViolationRule to dictionary."""
        rule = ViolationRule(
            id="VR-001",
            name="Test Rule",
            pattern="test.*pattern",
            severity=ViolationSeverity.P1,
            auto_detect=True,
        )

        result = rule.to_dict()
        assert result["id"] == "VR-001"
        assert result["pattern"] == "test.*pattern"
        assert result["severity"] == "P1"
        assert result["auto_detect"] is True


class TestDecisionBoundary:
    """Tests for DecisionBoundary class."""

    def test_to_dict_with_approval(self):
        """Test converting DecisionBoundary with approval to dictionary."""
        boundary = DecisionBoundary(
            category="Security",
            action="Credential rotation",
            constraints=["Admin approval required"],
            approval_required="Admin + audit log",
        )

        result = boundary.to_dict()
        assert result["category"] == "Security"
        assert result["approval_required"] == "Admin + audit log"

    def test_to_dict_without_approval(self):
        """Test converting DecisionBoundary without approval to dictionary."""
        boundary = DecisionBoundary(
            category="Monitoring",
            action="Health checks",
            constraints=["Read-only"],
            approval_required=None,
        )

        result = boundary.to_dict()
        assert "approval_required" not in result


class TestSeverityLevel:
    """Tests for SeverityLevel class."""

    def test_to_dict(self):
        """Test converting SeverityLevel to dictionary."""
        level = SeverityLevel(
            level="P0",
            name="Critical",
            description="Critical issue",
            detection_sla_seconds=60,
            response_sla_minutes=5,
            requires_human_intervention=True,
        )

        result = level.to_dict()
        assert result["level"] == "P0"
        assert result["requires_human_intervention"] is True


class TestEscalationStep:
    """Tests for EscalationStep class."""

    def test_to_dict_with_delay_seconds(self):
        """Test converting EscalationStep with delay_seconds."""
        step = EscalationStep(
            level=1,
            target="#alerts",
            channel="discord",
            auto=True,
            delay_minutes=0,
            delay_seconds=30,
        )

        result = step.to_dict()
        assert result["delay_seconds"] == 30

    def test_to_dict_without_delay_seconds(self):
        """Test converting EscalationStep without delay_seconds."""
        step = EscalationStep(
            level=1,
            target="#alerts",
            channel="discord",
            auto=True,
            delay_minutes=0,
        )

        result = step.to_dict()
        assert "delay_seconds" not in result


class TestEscalationPath:
    """Tests for EscalationPath class."""

    def test_to_dict(self):
        """Test converting EscalationPath to dictionary."""
        step = EscalationStep(
            level=1,
            target="#alerts",
            channel="discord",
            auto=True,
            delay_minutes=0,
        )
        path = EscalationPath(
            path="default",
            steps=[step],
        )

        result = path.to_dict()
        assert result["path"] == "default"
        assert len(result["steps"]) == 1


class TestEscalationTrigger:
    """Tests for EscalationTrigger class."""

    def test_to_dict(self):
        """Test converting EscalationTrigger to dictionary."""
        trigger = EscalationTrigger(
            trigger="Test trigger",
            severity=ViolationSeverity.P1,
            escalation_path="default",
            response_sla="5 minutes",
        )

        result = trigger.to_dict()
        assert result["trigger"] == "Test trigger"
        assert result["severity"] == "P1"
