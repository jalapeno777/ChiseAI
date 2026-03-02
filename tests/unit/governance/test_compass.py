"""
Unit tests for the Soul-Guided Compass Framework

Tests for compass_gate.py and compass_apply.py
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "scripts" / "ci"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "scripts" / "ops"))

import compass_apply
import compass_gate


class TestCompassGate:
    """Tests for the compass_gate module."""

    def test_load_compass_config_exists(self, tmp_path):
        """Test loading compass config when file exists."""
        # Create a temporary config
        config_content = """
veto_principles:
  - execution_safety
veto_paths:
  execution:
    - "src/execution/**/*.py"
"""
        config_file = tmp_path / "compass.yaml"
        config_file.write_text(config_content)

        with patch.object(compass_gate, "COMPASS_CONFIG_PATH", config_file):
            config = compass_gate.load_compass_config()
            assert config is not None
            assert "veto_principles" in config
            assert "execution_safety" in config["veto_principles"]

    def test_load_compass_config_not_found(self, tmp_path):
        """Test loading compass config when file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.yaml"

        with patch.object(compass_gate, "COMPASS_CONFIG_PATH", nonexistent):
            with pytest.raises(compass_gate.CompassGateError):
                compass_gate.load_compass_config()

    def test_match_glob_patterns(self):
        """Test glob pattern matching."""
        patterns = ["src/execution/**/*.py", "src/risk/**/*.py"]

        assert compass_gate.match_glob_patterns("src/execution/order.py", patterns)
        assert compass_gate.match_glob_patterns("src/risk/manager.py", patterns)
        assert not compass_gate.match_glob_patterns("src/strategy/engine.py", patterns)
        assert not compass_gate.match_glob_patterns("docs/readme.md", patterns)

    def test_get_veto_patterns(self):
        """Test extracting veto patterns from config."""
        config = {
            "veto_paths": {
                "execution": ["src/execution/**/*.py"],
                "risk": ["src/risk/**/*.py"],
                "secrets": ["**/*secret*"],
            }
        }

        patterns = compass_gate.get_veto_patterns(config)

        assert "src/execution/**/*.py" in patterns
        assert "src/risk/**/*.py" in patterns
        assert "**/*secret*" in patterns

    def test_check_sensitive_paths_no_match(self):
        """Test checking files that don't match sensitive paths."""
        files = ["docs/readme.md", "tests/test_utils.py"]

        with patch.object(compass_gate, "load_compass_config") as mock_load:
            mock_load.return_value = {
                "veto_paths": {"execution": ["src/execution/**/*.py"]}
            }
            with patch.object(compass_gate, "load_human_approval_config") as mock_load2:
                mock_load2.return_value = {
                    "sensitive_paths": {
                        "critical_execution": {
                            "paths": ["src/execution/order_manager.py"]
                        }
                    }
                }

                has_sensitive, veto_matches, sensitive_matches = (
                    compass_gate.check_sensitive_paths(files)
                )

                assert not has_sensitive
                assert len(veto_matches) == 0
                assert len(sensitive_matches) == 0

    def test_check_sensitive_paths_with_match(self):
        """Test checking files that match sensitive paths."""
        files = ["src/execution/order_manager.py", "docs/readme.md"]

        with patch.object(compass_gate, "load_compass_config") as mock_load:
            mock_load.return_value = {
                "veto_paths": {"execution": ["src/execution/**/*.py"]}
            }
            with patch.object(compass_gate, "load_human_approval_config") as mock_load2:
                mock_load2.return_value = {
                    "sensitive_paths": {
                        "critical_execution": {
                            "paths": ["src/execution/order_manager.py"]
                        }
                    }
                }

                has_sensitive, veto_matches, sensitive_matches = (
                    compass_gate.check_sensitive_paths(files)
                )

                assert has_sensitive
                assert len(veto_matches) == 1
                assert "src/execution/order_manager.py" in veto_matches

    def test_check_pr_labels_from_env(self):
        """Test checking PR labels from environment variable."""
        with patch.dict(os.environ, {"CI_PR_LABELS": "COMPASS-VETO,bugfix"}):
            has_veto, has_approved = compass_gate.check_pr_labels(123)

            assert has_veto is True
            assert has_approved is False

        with patch.dict(os.environ, {"CI_PR_LABELS": "HUMAN-APPROVED,enhancement"}):
            has_veto, has_approved = compass_gate.check_pr_labels(123)

            assert has_veto is False
            assert has_approved is True

    def test_run_gate_check_passes_no_sensitive(self):
        """Test gate check passes when no sensitive files."""
        files = ["docs/readme.md"]

        with patch.object(compass_gate, "load_compass_config") as mock_load:
            mock_load.return_value = {
                "veto_paths": {"execution": ["src/execution/**/*.py"]},
                "ci_gate": {"fail_on": ["compass_veto_present_without_approval"]},
            }
            with patch.object(compass_gate, "load_human_approval_config") as mock_load2:
                mock_load2.return_value = {"sensitive_paths": {}}

                result = compass_gate.run_gate_check(files, 123)

                assert result is True

    def test_run_gate_check_fails_veto_without_approval(self):
        """Test gate check fails when COMPASS-VETO without HUMAN-APPROVED."""
        files = ["src/execution/order.py"]

        with patch.object(compass_gate, "load_compass_config") as mock_load:
            mock_load.return_value = {
                "veto_paths": {"execution": ["src/execution/**/*.py"]},
                "ci_gate": {"fail_on": ["compass_veto_present_without_approval"]},
            }
            with patch.object(compass_gate, "load_human_approval_config") as mock_load2:
                mock_load2.return_value = {"sensitive_paths": {}}
                with patch.dict(os.environ, {"CI_PR_LABELS": "COMPASS-VETO"}):
                    result = compass_gate.run_gate_check(files, 123)

                    assert result is False


class TestCompassApply:
    """Tests for the compass_apply module."""

    def test_detect_sensitive_changes_no_match(self):
        """Test detecting changes when no sensitive paths match."""
        files = ["docs/readme.md", "tests/test_utils.py"]

        with patch.object(compass_apply, "load_compass_config") as mock_load:
            mock_load.return_value = {
                "veto_paths": {
                    "execution": ["src/execution/**/*.py"],
                    "risk": ["src/risk/**/*.py"],
                }
            }

            matches = compass_apply.detect_sensitive_changes(files)

            assert len(matches) == 0

    def test_detect_sensitive_changes_with_match(self):
        """Test detecting changes when sensitive paths match."""
        files = ["src/execution/order.py", "src/risk/manager.py", "docs/readme.md"]

        with patch.object(compass_apply, "load_compass_config") as mock_load:
            mock_load.return_value = {
                "veto_paths": {
                    "execution": ["src/execution/**/*.py"],
                    "risk": ["src/risk/**/*.py"],
                }
            }

            matches = compass_apply.detect_sensitive_changes(files)

            assert "execution" in matches
            assert "risk" in matches
            assert "src/execution/order.py" in matches["execution"]
            assert "src/risk/manager.py" in matches["risk"]

    def test_apply_label_already_present(self):
        """Test applying label when already present."""
        with patch.dict(os.environ, {"CI_PR_LABELS": "COMPASS-VETO,bugfix"}):
            result = compass_apply.apply_label(123, "COMPASS-VETO", dry_run=False)

            assert result is False  # Label already present

    def test_apply_label_new(self):
        """Test applying new label."""
        with patch.dict(os.environ, {"CI_PR_LABELS": "bugfix"}):
            result = compass_apply.apply_label(123, "COMPASS-VETO", dry_run=True)

            assert result is True  # Would be applied

    def test_run_apply_no_sensitive(self):
        """Test apply when no sensitive files."""
        files = ["docs/readme.md"]

        with patch.object(compass_apply, "load_compass_config") as mock_load:
            mock_load.return_value = {
                "auto_label": {"enabled": True, "label_name": "COMPASS-VETO"},
                "veto_paths": {"execution": ["src/execution/**/*.py"]},
            }

            result = compass_apply.run_apply(files, 123, dry_run=True)

            assert result["label_applied"] is False
            assert len(result["sensitive_matches"]) == 0

    def test_run_apply_with_sensitive(self):
        """Test apply when sensitive files detected."""
        files = ["src/execution/order.py"]

        with patch.object(compass_apply, "load_compass_config") as mock_load:
            mock_load.return_value = {
                "auto_label": {"enabled": True, "label_name": "COMPASS-VETO"},
                "veto_paths": {"execution": ["src/execution/**/*.py"]},
            }
            with patch.dict(os.environ, {"CI_PR_LABELS": ""}):
                result = compass_apply.run_apply(files, 123, dry_run=True)

                assert "execution" in result["sensitive_matches"]
                assert result["would_apply_label"] is True


class TestIntegration:
    """Integration tests for compass gate and apply working together."""

    def test_full_workflow_sensitive_change(self):
        """Test full workflow when sensitive files are changed."""
        files = ["src/execution/order_manager.py"]

        # Apply detects sensitive changes
        with patch.object(compass_apply, "load_compass_config") as mock_apply_load:
            mock_apply_load.return_value = {
                "auto_label": {"enabled": True, "label_name": "COMPASS-VETO"},
                "veto_paths": {
                    "execution": ["src/execution/**/*.py"],
                    "risk": ["src/risk/**/*.py"],
                },
            }
            with patch.dict(os.environ, {"CI_PR_LABELS": ""}):
                apply_result = compass_apply.run_apply(files, 123, dry_run=True)

                assert apply_result["would_apply_label"] is True

        # Gate blocks without HUMAN-APPROVED
        with patch.object(compass_gate, "load_compass_config") as mock_gate_load:
            mock_gate_load.return_value = {
                "veto_paths": {"execution": ["src/execution/**/*.py"]},
                "ci_gate": {
                    "fail_on": [
                        "compass_veto_present_without_approval",
                        "sensitive_path_changed_without_label",
                    ]
                },
            }
            with patch.object(compass_gate, "load_human_approval_config") as mock_load2:
                mock_load2.return_value = {"sensitive_paths": {}}
                with patch.dict(os.environ, {"CI_PR_LABELS": "COMPASS-VETO"}):
                    gate_result = compass_gate.run_gate_check(files, 123)

                    assert gate_result is False  # Blocked without HUMAN-APPROVED

    def test_full_workflow_approved(self):
        """Test full workflow when change is approved."""
        files = ["src/execution/order_manager.py"]

        # Gate passes with HUMAN-APPROVED
        with patch.object(compass_gate, "load_compass_config") as mock_gate_load:
            mock_gate_load.return_value = {
                "veto_paths": {"execution": ["src/execution/**/*.py"]},
                "ci_gate": {
                    "fail_on": [
                        "compass_veto_present_without_approval",
                        "sensitive_path_changed_without_label",
                    ]
                },
            }
            with patch.object(compass_gate, "load_human_approval_config") as mock_load2:
                mock_load2.return_value = {"sensitive_paths": {}}
                with patch.dict(
                    os.environ, {"CI_PR_LABELS": "COMPASS-VETO,HUMAN-APPROVED"}
                ):
                    gate_result = compass_gate.run_gate_check(files, 123)

                    assert gate_result is True  # Passes with approval


class TestConfigValidation:
    """Tests for validating the compass and human approval configs."""

    def test_compass_config_structure(self):
        """Test that compass.yaml has required structure."""
        config_path = (
            Path(__file__).parent.parent.parent.parent.parent
            / "docs"
            / "policy"
            / "compass.yaml"
        )

        if config_path.exists():
            import yaml

            with open(config_path) as f:
                config = yaml.safe_load(f)

            # Check required top-level keys
            assert "version" in config
            assert "veto_principles" in config
            assert "veto_paths" in config
            assert "approval_requirements" in config
            assert "ci_gate" in config
            assert "auto_label" in config

            # Check veto_paths categories
            veto_paths = config["veto_paths"]
            assert "execution" in veto_paths
            assert "risk" in veto_paths
            assert "infrastructure" in veto_paths
            assert "secrets" in veto_paths
            assert "invariants" in veto_paths

            # Check approval requirements
            approval = config["approval_requirements"]
            assert "compass_veto_override" in approval
            assert "appeal_workflow" in approval

            # Check appeal workflow
            appeal = approval["appeal_workflow"]
            assert appeal["enabled"] is True
            assert appeal["consensus_required"] == 3
            assert "critic" in appeal["agents"]
            assert "senior-dev" in appeal["agents"]
            assert "merlin" in appeal["agents"]

    def test_human_approval_config_structure(self):
        """Test that human_approval.yaml has required structure."""
        config_path = (
            Path(__file__).parent.parent.parent.parent.parent
            / "docs"
            / "policy"
            / "human_approval.yaml"
        )

        if config_path.exists():
            import yaml

            with open(config_path) as f:
                config = yaml.safe_load(f)

            # Check required keys
            assert "version" in config
            assert "sensitive_paths" in config
            assert "workflow" in config

            # Check sensitive paths categories
            sensitive = config["sensitive_paths"]
            assert "critical_execution" in sensitive
            assert "risk_limits" in sensitive
            assert "infrastructure" in sensitive
            assert "secrets" in sensitive

            # Check workflow
            workflow = config["workflow"]
            assert "steps" in workflow
            assert "escalation" in workflow
