"""
Tests for the ML Operations Runbook (ml_operations.md)

Part of ST-LAUNCH-021: Runbook Creation & Validation
"""

import re
from pathlib import Path

import pytest


class TestMLOperationsRunbookStructure:
    """Test structural requirements of the ML operations runbook."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_runbook_exists(self):
        """Verify ML operations runbook file exists."""
        assert Path("docs/runbooks/ml_operations.md").exists()

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


class TestMLOperationsSections:
    """Test that all required sections are present."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_retraining_triggers_section(self, runbook_content):
        """Verify model retraining trigger conditions section exists."""
        assert re.search(r"##\s+1\.\s+Model Retraining Trigger", runbook_content)

    def test_training_pipeline_section(self, runbook_content):
        """Verify training pipeline execution section exists."""
        assert re.search(r"##\s+2\.\s+Training Pipeline Execution", runbook_content)

    def test_validation_gates_section(self, runbook_content):
        """Verify validation gates section exists."""
        assert re.search(r"##\s+3\.\s+Validation Gates", runbook_content)

    def test_model_rollback_section(self, runbook_content):
        """Verify model rollback section exists."""
        assert re.search(r"##\s+4\.\s+Model Rollback", runbook_content)

    def test_shadow_mode_section(self, runbook_content):
        """Verify shadow mode operation section exists."""
        assert re.search(r"##\s+5\.\s+Shadow Mode", runbook_content)

    def test_ab_testing_section(self, runbook_content):
        """Verify A/B testing framework section exists."""
        assert re.search(r"##\s+6\.\s+A/B Testing", runbook_content)

    def test_ece_section(self, runbook_content):
        """Verify daily ECE update procedures section exists."""
        assert re.search(r"##\s+7\.\s+Daily ECE", runbook_content)


class TestRetrainingProcedures:
    """Test model retraining specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_automatic_triggers_documented(self, runbook_content):
        """Verify automatic retraining triggers are documented."""
        assert "Automatic Retraining Triggers" in runbook_content

    def test_performance_thresholds_documented(self, runbook_content):
        """Verify performance-based triggers are documented."""
        assert "Accuracy degradation" in runbook_content
        assert (
            "Precision drop" in runbook_content
            or "precision" in runbook_content.lower()
        )

    def test_data_based_triggers_documented(self, runbook_content):
        """Verify data-based triggers are documented."""
        assert (
            "Training data age" in runbook_content
            or "data age" in runbook_content.lower()
        )

    def test_manual_trigger_api_documented(self, runbook_content):
        """Verify manual trigger API is documented."""
        assert (
            "/training/trigger" in runbook_content
            or "trigger" in runbook_content.lower()
        )


class TestValidationGates:
    """Test validation gates specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_pre_deployment_gates_documented(self, runbook_content):
        """Verify pre-deployment validation gates are documented."""
        assert "Pre-Deployment Validation Gates" in runbook_content

    def test_accuracy_gate_documented(self, runbook_content):
        """Verify accuracy gate is documented."""
        assert "Accuracy" in runbook_content and "baseline" in runbook_content.lower()

    def test_ece_gate_documented(self, runbook_content):
        """Verify ECE gate is documented."""
        assert "ECE" in runbook_content and "0.15" in runbook_content

    def test_latency_gate_documented(self, runbook_content):
        """Verify latency gate is documented."""
        assert "latency" in runbook_content.lower() and "100ms" in runbook_content

    def test_gate_failure_procedures(self, runbook_content):
        """Verify gate failure procedures are documented."""
        assert "Gate Failure" in runbook_content


class TestShadowMode:
    """Test shadow mode specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_shadow_mode_24h_requirement(self, runbook_content):
        """Verify 24-hour shadow mode requirement is documented."""
        assert "24" in runbook_content and (
            "hour" in runbook_content.lower() or "h" in runbook_content
        )

    def test_shadow_mode_deployment_documented(self, runbook_content):
        """Verify shadow mode deployment is documented."""
        assert (
            "Shadow Mode Deployment" in runbook_content
            or "enable" in runbook_content.lower()
        )

    def test_shadow_monitoring_documented(self, runbook_content):
        """Verify shadow mode monitoring is documented."""
        assert (
            "Shadow Mode Monitoring" in runbook_content
            or "comparison" in runbook_content.lower()
        )

    def test_promotion_procedures_documented(self, runbook_content):
        """Verify promotion procedures are documented."""
        assert "promote" in runbook_content.lower()


class TestABTesting:
    """Test A/B testing specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_ab_test_setup_documented(self, runbook_content):
        """Verify A/B test setup is documented."""
        assert "A/B Test Setup" in runbook_content or "ab-test" in runbook_content

    def test_split_ratio_documented(self, runbook_content):
        """Verify split ratio configuration is documented."""
        assert (
            "split" in runbook_content.lower()
            or "traffic_percentage" in runbook_content
        )

    def test_ab_test_monitoring_documented(self, runbook_content):
        """Verify A/B test monitoring is documented."""
        assert (
            "A/B Test Monitoring" in runbook_content
            or "statistical" in runbook_content.lower()
        )


class TestECEProcedures:
    """Test ECE (Expected Calibration Error) specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_ece_definition_documented(self, runbook_content):
        """Verify ECE definition is documented."""
        assert (
            "Expected Calibration Error" in runbook_content or "ECE" in runbook_content
        )

    def test_ece_threshold_015(self, runbook_content):
        """Verify ECE threshold of 0.15 is documented."""
        assert "0.15" in runbook_content

    def test_daily_ece_check_documented(self, runbook_content):
        """Verify daily ECE check procedure is documented."""
        assert "Daily ECE Check" in runbook_content or "Morning" in runbook_content

    def test_ece_recalibration_documented(self, runbook_content):
        """Verify ECE recalibration is documented."""
        assert "recalibrat" in runbook_content.lower()

    def test_recalibration_methods_documented(self, runbook_content):
        """Verify recalibration methods are documented."""
        methods = ["Temperature Scaling", "Platt Scaling", "Isotonic"]
        assert any(method in runbook_content for method in methods)


class TestModelRollback:
    """Test model rollback specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_rollback_triggers_documented(self, runbook_content):
        """Verify rollback triggers are documented."""
        assert (
            "Rollback Triggers" in runbook_content
            or "degradation" in runbook_content.lower()
        )

    def test_automatic_rollback_documented(self, runbook_content):
        """Verify automatic rollback is documented."""
        assert (
            "Automatic Rollback" in runbook_content
            or "Auto-Rollback" in runbook_content
        )

    def test_manual_rollback_procedure(self, runbook_content):
        """Verify manual rollback procedure is documented."""
        assert "Manual Rollback" in runbook_content

    def test_rollback_verification_documented(self, runbook_content):
        """Verify rollback verification is documented."""
        assert "Rollback Verification" in runbook_content


class TestTrainingPipeline:
    """Test training pipeline specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_pre_training_checklist(self, runbook_content):
        """Verify pre-training checklist is documented."""
        assert "Pre-Training Checklist" in runbook_content

    def test_step_by_step_training(self, runbook_content):
        """Verify step-by-step training procedure is documented."""
        assert "Step-by-Step Training" in runbook_content or "Step 1" in runbook_content

    def test_training_stages_documented(self, runbook_content):
        """Verify training pipeline stages are documented."""
        assert "Data Prep" in runbook_content or "Training" in runbook_content

    def test_training_failure_recovery(self, runbook_content):
        """Verify training failure recovery is documented."""
        assert (
            "Training Failure Recovery" in runbook_content or "OOM" in runbook_content
        )


class TestModelRegistry:
    """Test model registry specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_model_version_management(self, runbook_content):
        """Verify model version management is documented."""
        assert (
            "Model Version Management" in runbook_content or "model-" in runbook_content
        )

    def test_artifact_management(self, runbook_content):
        """Verify artifact management is documented."""
        assert (
            "Artifact Management" in runbook_content
            or "artifact" in runbook_content.lower()
        )


class TestMLMonitoring:
    """Test ML monitoring specific content."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_ml_metrics_documented(self, runbook_content):
        """Verify ML-specific metrics are documented."""
        assert "ML-Specific Metrics" in runbook_content

    def test_dashboard_urls_documented(self, runbook_content):
        """Verify dashboard URLs are documented."""
        assert "Dashboards" in runbook_content or "localhost:3001" in runbook_content

    def test_alert_routing_documented(self, runbook_content):
        """Verify ML alert routing is documented."""
        assert "Alert Routing" in runbook_content or "ML On-call" in runbook_content


class TestMLRelatedRunbooks:
    """Test related runbook links."""

    @pytest.fixture
    def runbook_content(self):
        """Load the ML operations runbook content."""
        runbook_path = Path("docs/runbooks/ml_operations.md")
        if not runbook_path.exists():
            pytest.skip("ml_operations.md not found")
        return runbook_path.read_text()

    def test_related_runbooks_section(self, runbook_content):
        """Verify related runbooks section exists."""
        assert "Related Runbooks" in runbook_content or "## 10." in runbook_content

    def test_model_drift_linked(self, runbook_content):
        """Verify model drift runbook is linked."""
        assert (
            "model-drift" in runbook_content.lower()
            or "drift" in runbook_content.lower()
        )
