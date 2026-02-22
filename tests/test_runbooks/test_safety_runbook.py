"""
Tests for the Safety Runbook (launch_runbook.md)

Part of ST-LAUNCH-021: Runbook Creation & Validation
"""

import re
from pathlib import Path

import pytest


class TestSafetyRunbookStructure:
    """Test structural requirements of the safety runbook."""

    @pytest.fixture
    def runbook_content(self):
        """Load the safety runbook content."""
        runbook_path = Path("docs/runbooks/launch_runbook.md")
        if not runbook_path.exists():
            pytest.skip("launch_runbook.md not found")
        return runbook_path.read_text()

    def test_runbook_exists(self):
        """Verify safety runbook file exists."""
        assert Path("docs/runbooks/launch_runbook.md").exists()

    def test_frontmatter_present(self, runbook_content):
        """Verify YAML frontmatter exists."""
        assert runbook_content.startswith("---")
        assert "title:" in runbook_content
        assert "story_id: ST-LAUNCH-021" in runbook_content

    def test_required_frontmatter_fields(self, runbook_content):
        """Verify all required frontmatter fields exist."""
        required_fields = [
            "title:",
            "category:",
            "severity:",
            "last_updated:",
            "maintainers:",
            "story_id:",
            "executable:",
        ]
        for field in required_fields:
            assert field in runbook_content, f"Missing field: {field}"

    def test_executable_steps_present(self, runbook_content):
        """Verify executable steps are defined in frontmatter."""
        assert "executable: true" in runbook_content
        assert "steps:" in runbook_content


class TestSafetyRunbookSections:
    """Test that all required sections are present."""

    @pytest.fixture
    def runbook_content(self):
        """Load the safety runbook content."""
        runbook_path = Path("docs/runbooks/launch_runbook.md")
        if not runbook_path.exists():
            pytest.skip("launch_runbook.md not found")
        return runbook_path.read_text()

    def test_kill_switch_section(self, runbook_content):
        """Verify kill switch procedures section exists."""
        assert re.search(r"##\s+1\.\s+Kill Switch Procedures", runbook_content)

    def test_circuit_breaker_section(self, runbook_content):
        """Verify circuit breaker management section exists."""
        assert re.search(r"##\s+2\.\s+Circuit Breaker Management", runbook_content)

    def test_idempotency_section(self, runbook_content):
        """Verify order idempotency verification section exists."""
        assert re.search(r"##\s+3\.\s+Order Idempotency", runbook_content)

    def test_rollback_section(self, runbook_content):
        """Verify safety rollback procedures section exists."""
        assert re.search(r"##\s+4\.\s+Safety Rollback", runbook_content)

    def test_pre_launch_checklist_section(self, runbook_content):
        """Verify pre-launch safety checklist section exists."""
        assert re.search(r"##\s+5\.\s+Pre-Launch Safety Checklist", runbook_content)

    def test_post_incident_section(self, runbook_content):
        """Verify post-incident safety verification section exists."""
        assert re.search(r"##\s+6\.\s+Post-Incident Safety", runbook_content)

    def test_monitoring_section(self, runbook_content):
        """Verify monitoring and alerting section exists."""
        assert re.search(r"##\s+7\.\s+Monitoring", runbook_content)


class TestKillSwitchProcedures:
    """Test kill switch specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the safety runbook content."""
        runbook_path = Path("docs/runbooks/launch_runbook.md")
        if not runbook_path.exists():
            pytest.skip("launch_runbook.md not found")
        return runbook_path.read_text()

    def test_kill_switch_triggers_documented(self, runbook_content):
        """Verify kill switch trigger conditions are documented."""
        assert "When to Trigger" in runbook_content
        assert "Critical margin utilization" in runbook_content

    def test_kill_switch_trigger_api(self, runbook_content):
        """Verify kill switch trigger API is documented."""
        assert "/kill-switch/trigger" in runbook_content

    def test_kill_switch_verification_steps(self, runbook_content):
        """Verify kill switch verification steps are documented."""
        assert "Kill Switch Verification Steps" in runbook_content

    def test_kill_switch_states_documented(self, runbook_content):
        """Verify kill switch states are documented."""
        assert "ARMED" in runbook_content
        assert "TRIGGERED" in runbook_content


class TestCircuitBreakerProcedures:
    """Test circuit breaker specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the safety runbook content."""
        runbook_path = Path("docs/runbooks/launch_runbook.md")
        if not runbook_path.exists():
            pytest.skip("launch_runbook.md not found")
        return runbook_path.read_text()

    def test_circuit_breaker_states_documented(self, runbook_content):
        """Verify all circuit breaker states are documented."""
        assert "CLOSED" in runbook_content
        assert "OPEN" in runbook_content
        assert "HALF_OPEN" in runbook_content

    def test_state_transitions_documented(self, runbook_content):
        """Verify state transition procedures are documented."""
        assert "State Transitions" in runbook_content

    def test_manual_override_documented(self, runbook_content):
        """Verify manual override procedures are documented."""
        assert "Manual Override" in runbook_content


class TestIdempotencyProcedures:
    """Test order idempotency specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the safety runbook content."""
        runbook_path = Path("docs/runbooks/launch_runbook.md")
        if not runbook_path.exists():
            pytest.skip("launch_runbook.md not found")
        return runbook_path.read_text()

    def test_duplicate_detection_documented(self, runbook_content):
        """Verify duplicate detection is documented."""
        assert "Duplicate Detection" in runbook_content

    def test_replay_protection_documented(self, runbook_content):
        """Verify replay protection is documented."""
        assert "Replay Protection" in runbook_content

    def test_idempotency_keys_documented(self, runbook_content):
        """Verify idempotency key usage is documented."""
        assert "idempotency_key" in runbook_content


class TestRollbackProcedures:
    """Test rollback specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the safety runbook content."""
        runbook_path = Path("docs/runbooks/launch_runbook.md")
        if not runbook_path.exists():
            pytest.skip("launch_runbook.md not found")
        return runbook_path.read_text()

    def test_rollback_sla_documented(self, runbook_content):
        """Verify rollback SLA is documented."""
        assert (
            "5-Minute SLA" in runbook_content or "5 minute" in runbook_content.lower()
        )

    def test_step_by_step_rollback(self, runbook_content):
        """Verify step-by-step rollback is documented."""
        assert "Step-by-Step Rollback" in runbook_content

    def test_rollback_triggers_documented(self, runbook_content):
        """Verify rollback triggers are documented."""
        assert "Rollback Triggers" in runbook_content


class TestPreLaunchChecklist:
    """Test pre-launch checklist content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the safety runbook content."""
        runbook_path = Path("docs/runbooks/launch_runbook.md")
        if not runbook_path.exists():
            pytest.skip("launch_runbook.md not found")
        return runbook_path.read_text()

    def test_checklist_has_11_items(self, runbook_content):
        """Verify checklist has at least 11 items."""
        # Look for table rows with numbered items
        # Use ^## to match only level-2 headers, not ### subheaders
        checklist_section = re.search(
            r"##\s+5\.\s+Pre-Launch Safety Checklist.*?(?=^##\s+\d|\Z)",
            runbook_content,
            re.DOTALL | re.MULTILINE,
        )
        if checklist_section:
            items = re.findall(r"\|\s*\d+\s*\|", checklist_section.group())
            assert len(items) >= 11, f"Expected 11+ checklist items, found {len(items)}"
        else:
            pytest.skip("Checklist section not found")

    def test_checklist_includes_kill_switch_check(self, runbook_content):
        """Verify checklist includes kill switch verification."""
        # Use ^## to match only level-2 headers, not ### subheaders
        checklist_section = re.search(
            r"##\s+5\.\s+Pre-Launch Safety Checklist.*?(?=^##\s+\d|\Z)",
            runbook_content,
            re.DOTALL | re.MULTILINE,
        )
        if checklist_section:
            assert "kill switch" in checklist_section.group().lower()


class TestApiDocumentation:
    """Test that API examples are present and valid."""

    @pytest.fixture
    def runbook_content(self):
        """Load the safety runbook content."""
        runbook_path = Path("docs/runbooks/launch_runbook.md")
        if not runbook_path.exists():
            pytest.skip("launch_runbook.md not found")
        return runbook_path.read_text()

    def test_api_examples_present(self, runbook_content):
        """Verify API examples are documented."""
        assert "curl" in runbook_content
        assert "http://localhost:8001" in runbook_content

    def test_json_examples_present(self, runbook_content):
        """Verify JSON request/response examples are documented."""
        assert "```json" in runbook_content or '{"' in runbook_content


class TestRelatedRunbooks:
    """Test related runbook links."""

    @pytest.fixture
    def runbook_content(self):
        """Load the safety runbook content."""
        runbook_path = Path("docs/runbooks/launch_runbook.md")
        if not runbook_path.exists():
            pytest.skip("launch_runbook.md not found")
        return runbook_path.read_text()

    def test_related_runbooks_section(self, runbook_content):
        """Verify related runbooks are linked."""
        assert "Related Runbooks" in runbook_content or "## 8." in runbook_content

    def test_incident_response_linked(self, runbook_content):
        """Verify incident response runbook is linked."""
        assert (
            "incident_response.md" in runbook_content
            or "Incident Response" in runbook_content
        )


class TestRevisionHistory:
    """Test revision history section."""

    @pytest.fixture
    def runbook_content(self):
        """Load the safety runbook content."""
        runbook_path = Path("docs/runbooks/launch_runbook.md")
        if not runbook_path.exists():
            pytest.skip("launch_runbook.md not found")
        return runbook_path.read_text()

    def test_revision_history_present(self, runbook_content):
        """Verify revision history is documented."""
        assert "Revision History" in runbook_content or "## 9." in runbook_content

    def test_initial_version_documented(self, runbook_content):
        """Verify initial version is documented."""
        assert "1.0" in runbook_content or "Initial" in runbook_content
