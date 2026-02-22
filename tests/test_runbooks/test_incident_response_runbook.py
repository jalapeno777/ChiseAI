"""
Tests for the Incident Response Runbook (incident_response.md)

Part of ST-LAUNCH-021: Runbook Creation & Validation
"""

from pathlib import Path

import pytest


class TestIncidentResponseRunbookStructure:
    """Test structural requirements of the incident response runbook."""

    @pytest.fixture
    def runbook_content(self):
        """Load the incident response runbook content."""
        runbook_path = Path("docs/runbooks/incident_response.md")
        if not runbook_path.exists():
            pytest.skip("incident_response.md not found")
        return runbook_path.read_text()

    def test_on_call_schedule_documented(self, runbook_content):
        """Verify on-call schedule is documented."""
        assert (
            "On-Call Schedule" in runbook_content
            or "rotation" in runbook_content.lower()
        )

    def test_alert_acknowledgment_sla(self, runbook_content):
        """Verify alert acknowledgment SLA is documented."""
        assert (
            "15 minute" in runbook_content
            or "15-minute" in runbook_content
            or "15min" in runbook_content
        )

    def test_response_slas_documented(self, runbook_content):
        """Verify response SLAs are documented."""
        assert "Response SLAs" in runbook_content or "SLA" in runbook_content

    def test_handoff_procedures_documented(self, runbook_content):
        """Verify handoff procedures are documented."""
        assert "Handoff" in runbook_content

    def test_on_call_toolkit_documented(self, runbook_content):
        """Verify on-call toolkit is documented."""
        assert (
            "On-Call Toolkit" in runbook_content or "toolkit" in runbook_content.lower()
        )


class TestIncidentLifecycle:
    """Test incident lifecycle documentation."""

    @pytest.fixture
    def runbook_content(self):
        """Load the incident response runbook content."""
        runbook_path = Path("docs/runbooks/incident_response.md")
        if not runbook_path.exists():
            pytest.skip("incident_response.md not found")
        return runbook_path.read_text()

    def test_incident_states_documented(self, runbook_content):
        """Verify incident states are documented."""
        states = ["DETECTED", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "CLOSED"]
        assert any(state in runbook_content for state in states)

    def test_state_transitions_documented(self, runbook_content):
        """Verify state transitions are documented."""
        assert "State" in runbook_content or "transition" in runbook_content.lower()


class TestWarRoomProcedures:
    """Test war room procedures documentation."""

    @pytest.fixture
    def runbook_content(self):
        """Load the incident response runbook content."""
        runbook_path = Path("docs/runbooks/incident_response.md")
        if not runbook_path.exists():
            pytest.skip("incident_response.md not found")
        return runbook_path.read_text()

    def test_war_room_activation_documented(self, runbook_content):
        """Verify war room activation is documented."""
        assert (
            "War Room Activation" in runbook_content
            or "war room" in runbook_content.lower()
        )

    def test_war_room_roles_documented(self, runbook_content):
        """Verify war room roles are documented."""
        assert (
            "War Room Roles" in runbook_content
            or "Incident Commander" in runbook_content
        )

    def test_war_room_communication_documented(self, runbook_content):
        """Verify war room communication is documented."""
        assert "War Room Communication" in runbook_content


class TestIncidentResponseRelatedRunbooks:
    """Test related runbook links."""

    @pytest.fixture
    def runbook_content(self):
        """Load the incident response runbook content."""
        runbook_path = Path("docs/runbooks/incident_response.md")
        if not runbook_path.exists():
            pytest.skip("incident_response.md not found")
        return runbook_path.read_text()

    def test_related_runbooks_section(self, runbook_content):
        """Verify related runbooks section exists."""
        assert "Related Runbooks" in runbook_content or "## 9." in runbook_content

    def test_kill_switch_linked(self, runbook_content):
        """Verify kill switch runbook is linked."""
        assert (
            "kill-switch" in runbook_content.lower()
            or "kill switch" in runbook_content.lower()
        )

    def test_safety_runbook_linked(self, runbook_content):
        """Verify safety runbook is linked."""
        assert "launch_runbook" in runbook_content or "Safety" in runbook_content
