"""
Tests for governance_drift_guard.py

This module contains unit and integration tests for the governance drift
detection script. Tests cover parser functions and drift detection scenarios.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

# Load the module directly to bypass broken __init__.py imports
_module_path = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "validation"
    / "governance_drift_guard.py"
)
_spec = importlib.util.spec_from_file_location("governance_drift_guard", _module_path)
_governance_drift_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_governance_drift_guard)

# Export the functions for tests
parse_workflow_status = _governance_drift_guard.parse_workflow_status
extract_epic_status = _governance_drift_guard.extract_epic_status
parse_evidence_file = _governance_drift_guard.parse_evidence_file
extract_evidence_summary = _governance_drift_guard.extract_evidence_summary
detect_drift = _governance_drift_guard.detect_drift


class TestParseWorkflowStatus:
    """Tests for parse_workflow_status function."""

    def test_parse_valid_yaml(self, tmp_path):
        """Test parsing a valid YAML file."""
        yaml_content = {
            "epics": [
                {
                    "id": "EP-GOV-001",
                    "status": "completed",
                    "stories_completed": 10,
                    "stories_completed_verified": [
                        "ST-GOV-001",
                        "ST-GOV-002",
                    ],
                }
            ]
        }
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))

        result = parse_workflow_status(yaml_file)

        assert result["epics"][0]["id"] == "EP-GOV-001"
        assert result["epics"][0]["stories_completed"] == 10

    def test_file_not_found(self, tmp_path):
        """Test handling of missing file."""
        with pytest.raises(FileNotFoundError):
            parse_workflow_status(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml(self, tmp_path):
        """Test handling of invalid YAML."""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text("invalid: yaml: content: [")

        with pytest.raises(yaml.YAMLError):
            parse_workflow_status(yaml_file)


class TestExtractEpicStatus:
    """Tests for extract_epic_status function."""

    def test_epic_found(self):
        """Test extracting existing epic."""
        data = {
            "epics": [
                {
                    "id": "EP-GOV-001",
                    "status": "completed",
                    "stories_completed": 10,
                    "stories_completed_verified": ["ST-GOV-001"],
                    "story_count": 12,
                }
            ]
        }

        result = extract_epic_status(data, "EP-GOV-001")

        assert result is not None
        assert result["id"] == "EP-GOV-001"
        assert result["status"] == "completed"
        assert result["stories_completed"] == 10
        assert result["stories_completed_verified"] == ["ST-GOV-001"]
        assert result["story_count"] == 12

    def test_epic_not_found(self):
        """Test extracting non-existent epic."""
        data = {"epics": [{"id": "EP-OTHER-001"}]}

        result = extract_epic_status(data, "EP-GOV-001")

        assert result is None

    def test_empty_epics(self):
        """Test with empty epics list."""
        data = {"epics": []}

        result = extract_epic_status(data, "EP-GOV-001")

        assert result is None

    def test_missing_epics_key(self):
        """Test with missing epics key."""
        data = {}

        result = extract_epic_status(data, "EP-GOV-001")

        assert result is None

    def test_default_values(self):
        """Test default values for optional fields."""
        data = {
            "epics": [
                {
                    "id": "EP-GOV-001",
                    "status": "in_progress",
                }
            ]
        }

        result = extract_epic_status(data, "EP-GOV-001")

        assert result["stories_completed"] == 0
        assert result["stories_completed_verified"] == []
        assert result["story_count"] == 0


class TestParseEvidenceFile:
    """Tests for parse_evidence_file function."""

    def test_parse_single_story(self, tmp_path):
        """Test parsing evidence with single story."""
        md_content = """
# Evidence File

## Story Table

| Field | Value |
|-------|-------|
| **Story ID** | ST-GOV-002 |
| **Status** | completed |
"""
        md_file = tmp_path / "evidence.md"
        md_file.write_text(md_content)

        result = parse_evidence_file(md_file)

        assert result == ["ST-GOV-002"]

    def test_parse_multiple_stories(self, tmp_path):
        """Test parsing evidence with multiple stories."""
        md_content = """
### ST-GOV-002: Agent Constitution Artifact

| Field | Value |
|-------|-------|
| **Story ID** | ST-GOV-002 |
| **Status** | completed |

### ST-GOV-003: Task Decomposition Sentinel

| Field | Value |
|-------|-------|
| **Story ID** | ST-GOV-003 |
| **Status** | completed |
"""
        md_file = tmp_path / "evidence.md"
        md_file.write_text(md_content)

        result = parse_evidence_file(md_file)

        assert sorted(result) == ["ST-GOV-002", "ST-GOV-003"]

    def test_parse_no_stories(self, tmp_path):
        """Test parsing evidence with no stories."""
        md_content = """
# Evidence File

No stories here.
"""
        md_file = tmp_path / "evidence.md"
        md_file.write_text(md_content)

        result = parse_evidence_file(md_file)

        assert result == []

    def test_parse_duplicates_removed(self, tmp_path):
        """Test that duplicate story IDs are removed."""
        md_content = """
| **Story ID** | ST-GOV-002 |
| **Story ID** | ST-GOV-002 |
"""
        md_file = tmp_path / "evidence.md"
        md_file.write_text(md_content)

        result = parse_evidence_file(md_file)

        assert result == ["ST-GOV-002"]

    def test_file_not_found(self, tmp_path):
        """Test handling of missing file."""
        with pytest.raises(FileNotFoundError):
            parse_evidence_file(tmp_path / "nonexistent.md")


class TestExtractEvidenceSummary:
    """Tests for extract_evidence_summary function."""

    def test_extract_summary(self, tmp_path):
        """Test extracting evidence summary."""
        md_content = """
| **Story ID** | ST-GOV-002 |
| **Story ID** | ST-GOV-003 |
| **Story ID** | ST-GOV-005 |
"""
        md_file = tmp_path / "evidence.md"
        md_file.write_text(md_content)

        result = extract_evidence_summary(md_file)

        assert result["story_count"] == 3
        assert sorted(result["story_ids"]) == ["ST-GOV-002", "ST-GOV-003", "ST-GOV-005"]


class TestDetectDrift:
    """Tests for detect_drift function."""

    def test_no_drift_subset(self):
        """Test no drift when evidence is subset of workflow."""
        workflow_status = {
            "stories_completed": 10,
            "stories_completed_verified": [
                "ST-GOV-001",
                "ST-GOV-002",
                "ST-GOV-003",
                "ST-GOV-004",
                "ST-GOV-005",
            ],
        }
        evidence_summary = {
            "story_count": 3,
            "story_ids": ["ST-GOV-002", "ST-GOV-003", "ST-GOV-005"],
        }

        has_drift, messages = detect_drift(workflow_status, evidence_summary)

        assert not has_drift
        assert messages == []

    def test_drift_evidence_not_in_workflow(self):
        """Test drift when evidence has stories not in workflow."""
        workflow_status = {
            "stories_completed": 10,
            "stories_completed_verified": [
                "ST-GOV-001",
                "ST-GOV-002",
            ],
        }
        evidence_summary = {
            "story_count": 3,
            "story_ids": ["ST-GOV-002", "ST-GOV-003", "ST-GOV-005"],
        }

        has_drift, messages = detect_drift(workflow_status, evidence_summary)

        assert has_drift
        assert any("ST-GOV-003" in msg for msg in messages)
        assert any("ST-GOV-005" in msg for msg in messages)

    def test_drift_count_exceeded(self):
        """Test drift when evidence count exceeds workflow count."""
        workflow_status = {
            "stories_completed": 5,
            "stories_completed_verified": [
                "ST-GOV-001",
                "ST-GOV-002",
                "ST-GOV-003",
                "ST-GOV-004",
                "ST-GOV-005",
            ],
        }
        evidence_summary = {
            "story_count": 8,
            "story_ids": [
                "ST-GOV-001",
                "ST-GOV-002",
                "ST-GOV-003",
                "ST-GOV-004",
                "ST-GOV-005",
                "ST-GOV-006",
                "ST-GOV-007",
                "ST-GOV-008",
            ],
        }

        has_drift, messages = detect_drift(workflow_status, evidence_summary)

        assert has_drift
        assert any("exceeds" in msg.lower() for msg in messages)

    def test_no_drift_exact_match(self):
        """Test no drift when evidence exactly matches workflow."""
        workflow_status = {
            "stories_completed": 3,
            "stories_completed_verified": [
                "ST-GOV-002",
                "ST-GOV-003",
                "ST-GOV-005",
            ],
        }
        evidence_summary = {
            "story_count": 3,
            "story_ids": ["ST-GOV-002", "ST-GOV-003", "ST-GOV-005"],
        }

        has_drift, messages = detect_drift(workflow_status, evidence_summary)

        assert not has_drift
        assert messages == []

    def test_drift_null_workflow(self):
        """Test drift when workflow status is None."""
        has_drift, messages = detect_drift(None, {"story_count": 3, "story_ids": []})

        assert has_drift
        assert any("not found" in msg.lower() for msg in messages)

    def test_no_drift_empty_evidence(self):
        """Test no drift with empty evidence (edge case)."""
        workflow_status = {
            "stories_completed": 10,
            "stories_completed_verified": ["ST-GOV-001", "ST-GOV-002"],
        }
        evidence_summary = {
            "story_count": 0,
            "story_ids": [],
        }

        has_drift, messages = detect_drift(workflow_status, evidence_summary)

        assert not has_drift
        assert messages == []


class TestIntegration:
    """Integration tests using real file structure."""

    def test_with_real_files(self):
        """Test with actual repository files."""
        # These paths are relative to repo root
        workflow_path = Path("docs/bmm-workflow-status.yaml")
        evidence_path = Path("docs/evidence/GOVERNANCE_MERGE_EVIDENCE_2026-03-08.md")

        # Skip if files don't exist (e.g., in CI without full repo)
        if not workflow_path.exists() or not evidence_path.exists():
            pytest.skip("Real files not available")

        workflow_data = parse_workflow_status(workflow_path)
        epic_status = extract_epic_status(workflow_data, "EP-GOV-001")

        assert epic_status is not None
        assert epic_status["id"] == "EP-GOV-001"

        evidence_summary = extract_evidence_summary(evidence_path)

        # Evidence should have 8 stories
        assert evidence_summary["story_count"] == 8

        # All evidence stories should be in workflow
        has_drift, messages = detect_drift(epic_status, evidence_summary)

        # Current state: 8 evidence stories are subset of 10 workflow stories
        # This should pass (no drift)
        assert not has_drift, f"Unexpected drift: {messages}"

    def test_simulated_drift_remove_story(self, tmp_path):
        """Test drift detection when story removed from evidence."""
        # Create workflow with 3 stories
        workflow_content = {
            "epics": [
                {
                    "id": "EP-GOV-001",
                    "status": "completed",
                    "stories_completed": 3,
                    "stories_completed_verified": [
                        "ST-GOV-001",
                        "ST-GOV-002",
                        "ST-GOV-003",
                    ],
                }
            ]
        }
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(yaml.dump(workflow_content))

        # Create evidence with only 2 stories (simulating missing story)
        evidence_content = """
| **Story ID** | ST-GOV-001 |
| **Story ID** | ST-GOV-003 |
"""
        evidence_file = tmp_path / "evidence.md"
        evidence_file.write_text(evidence_content)

        workflow_data = parse_workflow_status(workflow_file)
        epic_status = extract_epic_status(workflow_data, "EP-GOV-001")
        evidence_summary = extract_evidence_summary(evidence_file)

        has_drift, messages = detect_drift(epic_status, evidence_summary)

        # No drift - evidence is still a valid subset
        assert not has_drift

    def test_simulated_drift_extra_story_in_evidence(self, tmp_path):
        """Test drift detection when extra story added to evidence."""
        # Create workflow with 2 stories
        workflow_content = {
            "epics": [
                {
                    "id": "EP-GOV-001",
                    "status": "completed",
                    "stories_completed": 2,
                    "stories_completed_verified": [
                        "ST-GOV-001",
                        "ST-GOV-002",
                    ],
                }
            ]
        }
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(yaml.dump(workflow_content))

        # Create evidence with 3 stories (one not in workflow)
        evidence_content = """
| **Story ID** | ST-GOV-001 |
| **Story ID** | ST-GOV-002 |
| **Story ID** | ST-GOV-099 |
"""
        evidence_file = tmp_path / "evidence.md"
        evidence_file.write_text(evidence_content)

        workflow_data = parse_workflow_status(workflow_file)
        epic_status = extract_epic_status(workflow_data, "EP-GOV-001")
        evidence_summary = extract_evidence_summary(evidence_file)

        has_drift, messages = detect_drift(epic_status, evidence_summary)

        # Should detect drift - ST-GOV-099 not in workflow
        assert has_drift
        assert any("ST-GOV-099" in msg for msg in messages)

    def test_simulated_drift_count_mismatch(self, tmp_path):
        """Test drift detection when counts don't match."""
        # Create workflow claiming 2 stories
        workflow_content = {
            "epics": [
                {
                    "id": "EP-GOV-001",
                    "status": "completed",
                    "stories_completed": 2,
                    "stories_completed_verified": [
                        "ST-GOV-001",
                        "ST-GOV-002",
                    ],
                }
            ]
        }
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(yaml.dump(workflow_content))

        # Create evidence with 5 stories (exceeds workflow count)
        evidence_content = """
| **Story ID** | ST-GOV-001 |
| **Story ID** | ST-GOV-002 |
| **Story ID** | ST-GOV-003 |
| **Story ID** | ST-GOV-004 |
| **Story ID** | ST-GOV-005 |
"""
        evidence_file = tmp_path / "evidence.md"
        evidence_file.write_text(evidence_content)

        workflow_data = parse_workflow_status(workflow_file)
        epic_status = extract_epic_status(workflow_data, "EP-GOV-001")
        evidence_summary = extract_evidence_summary(evidence_file)

        has_drift, messages = detect_drift(epic_status, evidence_summary)

        # Should detect drift - evidence count exceeds workflow
        assert has_drift
        assert any("exceeds" in msg.lower() for msg in messages)
