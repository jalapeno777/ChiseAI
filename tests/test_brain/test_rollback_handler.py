"""Tests for rollback handler functionality."""

import json
import pytest
from datetime import datetime
from typing import List

from src.brain.rollback_handler import (
    PostmortemReport,
    RollbackHandler,
    RollbackResult,
    RollbackStep,
    RollbackTrigger,
)


class TestRollbackTrigger:
    """Tests for RollbackTrigger enum."""

    def test_trigger_enum_values(self):
        """Test that all expected triggers exist."""
        assert RollbackTrigger.ECE_DEGRADATION is not None
        assert RollbackTrigger.WIN_RATE_DROP is not None
        assert RollbackTrigger.MAX_DRAWDOWN_BREACH is not None
        assert RollbackTrigger.SAFETY_VIOLATION is not None
        assert RollbackTrigger.HUMAN_REQUEST is not None

    def test_trigger_enum_count(self):
        """Test that there are exactly 5 triggers."""
        assert len(RollbackTrigger) == 5

    def test_trigger_names(self):
        """Test trigger names are correct."""
        names = [t.name for t in RollbackTrigger]
        assert "ECE_DEGRADATION" in names
        assert "WIN_RATE_DROP" in names
        assert "MAX_DRAWDOWN_BREACH" in names
        assert "SAFETY_VIOLATION" in names
        assert "HUMAN_REQUEST" in names


class TestRollbackStep:
    """Tests for RollbackStep dataclass."""

    def test_step_creation(self):
        """Test creating a rollback step."""
        step = RollbackStep(
            step_number=1,
            description="Test step",
            verification_command="echo test",
            expected_result="test",
        )
        assert step.step_number == 1
        assert step.description == "Test step"
        assert step.verification_command == "echo test"
        assert step.expected_result == "test"
        assert step.completed is False

    def test_step_default_completed(self):
        """Test that completed defaults to False."""
        step = RollbackStep(
            step_number=1,
            description="Test",
            verification_command="cmd",
            expected_result="result",
        )
        assert step.completed is False

    def test_step_completed_true(self):
        """Test creating a step with completed=True."""
        step = RollbackStep(
            step_number=1,
            description="Test",
            verification_command="cmd",
            expected_result="result",
            completed=True,
        )
        assert step.completed is True


class TestRollbackResult:
    """Tests for RollbackResult dataclass."""

    def test_result_creation(self):
        """Test creating a rollback result."""
        result = RollbackResult(
            success=True,
            target_version="v1.0.0",
            steps_completed=5,
            total_steps=5,
        )
        assert result.success is True
        assert result.target_version == "v1.0.0"
        assert result.steps_completed == 5
        assert result.total_steps == 5
        assert result.error_message is None
        assert isinstance(result.timestamp, datetime)
        assert result.duration_seconds == 0.0

    def test_result_with_error(self):
        """Test creating a result with error."""
        result = RollbackResult(
            success=False,
            target_version="v1.0.0",
            steps_completed=2,
            total_steps=5,
            error_message="Step 3 failed",
            duration_seconds=10.5,
        )
        assert result.success is False
        assert result.error_message == "Step 3 failed"
        assert result.duration_seconds == 10.5


class TestPostmortemReport:
    """Tests for PostmortemReport dataclass."""

    @pytest.fixture
    def sample_result(self):
        """Create a sample rollback result."""
        return RollbackResult(
            success=True,
            target_version="v1.0.0",
            steps_completed=5,
            total_steps=5,
            duration_seconds=120.0,
        )

    @pytest.fixture
    def sample_report(self, sample_result):
        """Create a sample post-mortem report."""
        return PostmortemReport(
            trigger=RollbackTrigger.ECE_DEGRADATION,
            timeline=[
                {"timestamp": "2026-01-01T00:00:00Z", "description": "Start"},
            ],
            steps_executed=[
                {"step_number": 1, "description": "Step 1", "completed": True},
            ],
            outcome=sample_result,
            root_cause_analysis="Test analysis",
            metadata={"key": "value"},
        )

    def test_report_creation(self, sample_report):
        """Test creating a post-mortem report."""
        assert sample_report.trigger == RollbackTrigger.ECE_DEGRADATION
        assert len(sample_report.timeline) == 1
        assert len(sample_report.steps_executed) == 1
        assert sample_report.root_cause_analysis == "Test analysis"
        assert sample_report.metadata == {"key": "value"}

    def test_report_to_json(self, sample_report):
        """Test JSON export of report."""
        json_str = sample_report.to_json()
        data = json.loads(json_str)

        assert data["trigger"] == "ECE_DEGRADATION"
        assert data["root_cause_analysis"] == "Test analysis"
        assert data["outcome"]["success"] is True
        assert data["outcome"]["target_version"] == "v1.0.0"
        assert data["metadata"]["key"] == "value"

    def test_report_to_markdown(self, sample_report):
        """Test Markdown export of report."""
        md = sample_report.to_markdown()

        assert "# Rollback Post-Mortem Report" in md
        assert "ECE_DEGRADATION" in md
        assert "Test analysis" in md
        assert "v1.0.0" in md
        assert "✅" in md  # Checkmark for completed step

    def test_report_to_markdown_with_error(self):
        """Test Markdown export with failed outcome."""
        result = RollbackResult(
            success=False,
            target_version="v1.0.0",
            steps_completed=2,
            total_steps=5,
            error_message="Step failed",
        )
        report = PostmortemReport(
            trigger=RollbackTrigger.WIN_RATE_DROP,
            timeline=[],
            steps_executed=[
                {"step_number": 1, "description": "Step 1", "completed": True},
                {"step_number": 2, "description": "Step 2", "completed": True},
                {"step_number": 3, "description": "Step 3", "completed": False},
            ],
            outcome=result,
            root_cause_analysis="Analysis",
        )
        md = report.to_markdown()

        assert "❌" in md  # X mark for failed step
        assert "Step failed" in md


class TestRollbackHandlerInitialization:
    """Tests for RollbackHandler initialization."""

    def test_default_initialization(self):
        """Test handler with default parameters."""
        handler = RollbackHandler()
        assert handler.ece_threshold == 0.15
        assert handler.win_rate_threshold is None
        assert handler.max_drawdown_threshold is None
        assert handler.active_trades_check is True
        assert handler.version_registry == []

    def test_custom_initialization(self):
        """Test handler with custom parameters."""
        handler = RollbackHandler(
            ece_threshold=0.20,
            win_rate_threshold=0.10,
            max_drawdown_threshold=0.25,
            active_trades_check=False,
            version_registry=["v1.0.0", "v1.1.0"],
        )
        assert handler.ece_threshold == 0.20
        assert handler.win_rate_threshold == 0.10
        assert handler.max_drawdown_threshold == 0.25
        assert handler.active_trades_check is False
        assert handler.version_registry == ["v1.0.0", "v1.1.0"]


class TestRollbackHandlerTriggerChecking:
    """Tests for trigger checking functionality."""

    @pytest.fixture
    def handler(self):
        """Create a handler with default settings."""
        return RollbackHandler(
            ece_threshold=0.15,
            win_rate_threshold=0.05,
            max_drawdown_threshold=0.20,
        )

    def test_no_triggers(self, handler):
        """Test with no metrics - no triggers."""
        triggers = handler.check_triggers()
        assert triggers == []

    def test_ece_degradation_trigger(self, handler):
        """Test ECE degradation trigger detection."""
        handler.update_metrics({"ece": 0.20})
        triggers = handler.check_triggers()
        assert RollbackTrigger.ECE_DEGRADATION in triggers

    def test_ece_below_threshold(self, handler):
        """Test ECE below threshold - no trigger."""
        handler.update_metrics({"ece": 0.10})
        triggers = handler.check_triggers()
        assert RollbackTrigger.ECE_DEGRADATION not in triggers

    def test_ece_at_threshold(self, handler):
        """Test ECE at threshold - no trigger (must exceed)."""
        handler.update_metrics({"ece": 0.15})
        triggers = handler.check_triggers()
        assert RollbackTrigger.ECE_DEGRADATION not in triggers

    def test_win_rate_drop_trigger(self, handler):
        """Test win rate drop trigger detection."""
        handler.update_metrics(
            {
                "win_rate": 0.70,
                "baseline_win_rate": 0.80,
            }
        )
        triggers = handler.check_triggers()
        assert RollbackTrigger.WIN_RATE_DROP in triggers

    def test_win_rate_no_drop(self, handler):
        """Test win rate within threshold - no trigger."""
        handler.update_metrics(
            {
                "win_rate": 0.78,
                "baseline_win_rate": 0.80,
            }
        )
        triggers = handler.check_triggers()
        assert RollbackTrigger.WIN_RATE_DROP not in triggers

    def test_max_drawdown_trigger(self, handler):
        """Test max drawdown breach trigger detection."""
        handler.update_metrics({"max_drawdown": 0.25})
        triggers = handler.check_triggers()
        assert RollbackTrigger.MAX_DRAWDOWN_BREACH in triggers

    def test_max_drawdown_no_breach(self, handler):
        """Test max drawdown within threshold - no trigger."""
        handler.update_metrics({"max_drawdown": 0.15})
        triggers = handler.check_triggers()
        assert RollbackTrigger.MAX_DRAWDOWN_BREACH not in triggers

    def test_safety_violation_trigger(self, handler):
        """Test safety violation trigger detection."""
        handler.update_metrics({"safety_violations": 1})
        triggers = handler.check_triggers()
        assert RollbackTrigger.SAFETY_VIOLATION in triggers

    def test_safety_violation_zero(self, handler):
        """Test zero safety violations - no trigger."""
        handler.update_metrics({"safety_violations": 0})
        triggers = handler.check_triggers()
        assert RollbackTrigger.SAFETY_VIOLATION not in triggers

    def test_multiple_triggers(self, handler):
        """Test multiple triggers active simultaneously."""
        handler.update_metrics(
            {
                "ece": 0.20,
                "win_rate": 0.70,
                "baseline_win_rate": 0.80,
                "max_drawdown": 0.25,
                "safety_violations": 1,
            }
        )
        triggers = handler.check_triggers()
        assert len(triggers) == 4
        assert RollbackTrigger.ECE_DEGRADATION in triggers
        assert RollbackTrigger.WIN_RATE_DROP in triggers
        assert RollbackTrigger.MAX_DRAWDOWN_BREACH in triggers
        assert RollbackTrigger.SAFETY_VIOLATION in triggers


class TestRollbackHandlerPreRollbackValidation:
    """Tests for pre-rollback state validation."""

    @pytest.fixture
    def handler(self):
        """Create a handler with version registry."""
        return RollbackHandler(
            version_registry=["v1.0.0", "v1.1.0"],
        )

    def test_validation_passes(self, handler):
        """Test validation passes with valid state."""
        handler.update_metrics(
            {
                "active_trades": 0,
                "data_consistent": True,
            }
        )
        assert handler.validate_pre_rollback_state("v1.0.0") is True

    def test_validation_fails_active_trades(self, handler):
        """Test validation fails with active trades."""
        handler.update_metrics(
            {
                "active_trades": 5,
                "data_consistent": True,
            }
        )
        assert handler.validate_pre_rollback_state("v1.0.0") is False

    def test_validation_fails_data_inconsistent(self, handler):
        """Test validation fails with inconsistent data."""
        handler.update_metrics(
            {
                "active_trades": 0,
                "data_consistent": False,
            }
        )
        assert handler.validate_pre_rollback_state("v1.0.0") is False

    def test_validation_fails_version_not_found(self, handler):
        """Test validation fails with unknown version."""
        handler.update_metrics(
            {
                "active_trades": 0,
                "data_consistent": True,
            }
        )
        assert handler.validate_pre_rollback_state("v2.0.0") is False

    def test_validation_disabled_active_trades_check(self):
        """Test validation passes when active trades check disabled."""
        handler = RollbackHandler(
            active_trades_check=False,
            version_registry=["v1.0.0"],
        )
        handler.update_metrics(
            {
                "active_trades": 5,
                "data_consistent": True,
            }
        )
        assert handler.validate_pre_rollback_state("v1.0.0") is True


class TestRollbackHandlerExecution:
    """Tests for rollback execution."""

    @pytest.fixture
    def handler(self):
        """Create a handler with version registry."""
        return RollbackHandler(
            version_registry=["v1.0.0", "v1.1.0"],
        )

    @pytest.fixture
    def sample_steps(self) -> List[RollbackStep]:
        """Create sample rollback steps."""
        return [
            RollbackStep(
                step_number=1,
                description="Stop trading",
                verification_command="stop",
                expected_result="stopped",
            ),
            RollbackStep(
                step_number=2,
                description="Backup state",
                verification_command="backup",
                expected_result="backed up",
            ),
            RollbackStep(
                step_number=3,
                description="Switch version",
                verification_command="switch",
                expected_result="switched",
            ),
        ]

    def test_successful_rollback(self, handler, sample_steps):
        """Test successful rollback execution."""
        handler.update_metrics(
            {
                "active_trades": 0,
                "data_consistent": True,
            }
        )
        result = handler.execute_rollback("v1.0.0", sample_steps)

        assert result.success is True
        assert result.target_version == "v1.0.0"
        assert result.steps_completed == 3
        assert result.total_steps == 3
        assert result.error_message is None
        assert result.duration_seconds >= 0

    def test_rollback_fails_validation(self, handler, sample_steps):
        """Test rollback fails when validation fails."""
        handler.update_metrics(
            {
                "active_trades": 5,
                "data_consistent": True,
            }
        )
        result = handler.execute_rollback("v1.0.0", sample_steps)

        assert result.success is False
        assert result.steps_completed == 0
        assert "Pre-rollback state validation failed" in result.error_message

    def test_rollback_tracks_history(self, handler, sample_steps):
        """Test that rollback history is tracked."""
        handler.update_metrics(
            {
                "active_trades": 0,
                "data_consistent": True,
            }
        )
        handler.execute_rollback("v1.0.0", sample_steps)

        history = handler.get_rollback_history()
        assert len(history) == 1
        assert history[0].target_version == "v1.0.0"

    def test_empty_steps(self, handler):
        """Test rollback with empty steps list."""
        handler.update_metrics(
            {
                "active_trades": 0,
                "data_consistent": True,
            }
        )
        result = handler.execute_rollback("v1.0.0", [])

        assert result.success is True
        assert result.steps_completed == 0
        assert result.total_steps == 0


class TestRollbackHandlerEmergencyRollback:
    """Tests for emergency rollback functionality."""

    @pytest.fixture
    def handler(self):
        """Create a handler with version registry."""
        return RollbackHandler(
            version_registry=["v1.0.0", "v1.1.0"],
        )

    def test_emergency_rollback_no_force(self, handler):
        """Test emergency rollback without force (normal path)."""
        handler.update_metrics(
            {
                "active_trades": 0,
                "data_consistent": True,
            }
        )
        result = handler.emergency_rollback("v1.0.0", force=False)

        assert result.success is True
        assert result.target_version == "v1.0.0"

    def test_emergency_rollback_with_force(self, handler):
        """Test emergency rollback with force flag."""
        handler.update_metrics(
            {
                "active_trades": 5,  # Would normally block
                "data_consistent": True,
            }
        )
        result = handler.emergency_rollback("v1.0.0", force=True)

        assert result.success is True
        assert result.target_version == "v1.0.0"

    def test_force_does_not_bypass_version_check(self, handler):
        """Test that force doesn't bypass version existence check."""
        result = handler.emergency_rollback("v2.0.0", force=True)

        assert result.success is False
        assert "not in registry" in result.error_message

    def test_force_with_active_trades_logs_warning(self, handler, caplog):
        """Test that force rollback with active trades logs warning."""
        handler.update_metrics(
            {
                "active_trades": 3,
                "data_consistent": True,
            }
        )

        with caplog.at_level("WARNING"):
            handler.emergency_rollback("v1.0.0", force=True)

        assert "active trades" in caplog.text.lower()


class TestRollbackHandlerPauseResume:
    """Tests for pause/resume functionality."""

    @pytest.fixture
    def handler(self):
        """Create a handler with version registry."""
        return RollbackHandler(
            version_registry=["v1.0.0"],
        )

    @pytest.fixture
    def failing_steps(self) -> List[RollbackStep]:
        """Create steps where step 2 will fail."""

        class FailingStep(RollbackStep):
            def __post_init__(self):
                pass

        # Create a mock that will fail on step 2
        steps = [
            RollbackStep(1, "Step 1", "cmd1", "ok"),
            RollbackStep(2, "Step 2", "cmd2", "fail"),
            RollbackStep(3, "Step 3", "cmd3", "ok"),
        ]
        return steps

    def test_get_paused_step_initially_none(self, handler):
        """Test that paused step is initially None."""
        assert handler.get_paused_step() is None

    def test_clear_paused_state(self, handler):
        """Test clearing paused state."""
        # Simulate paused state
        handler._paused_step = 2
        assert handler.get_paused_step() == 2

        handler.clear_paused_state()
        assert handler.get_paused_step() is None


class TestRollbackHandlerPostmortem:
    """Tests for post-mortem report generation."""

    @pytest.fixture
    def handler(self):
        """Create a handler."""
        return RollbackHandler()

    @pytest.fixture
    def sample_result(self):
        """Create a sample rollback result."""
        return RollbackResult(
            success=True,
            target_version="v1.0.0",
            steps_completed=5,
            total_steps=5,
            duration_seconds=120.0,
        )

    def test_generate_postmortem(self, handler, sample_result):
        """Test generating post-mortem report."""
        report = handler.generate_postmortem(
            trigger=RollbackTrigger.ECE_DEGRADATION,
            result=sample_result,
            root_cause_analysis="Test analysis",
            metadata={"key": "value"},
        )

        assert report.trigger == RollbackTrigger.ECE_DEGRADATION
        assert report.root_cause_analysis == "Test analysis"
        assert report.metadata == {"key": "value"}
        assert report.outcome == sample_result

    def test_generate_postmortem_default_analysis(self, handler, sample_result):
        """Test post-mortem with default analysis."""
        report = handler.generate_postmortem(
            trigger=RollbackTrigger.WIN_RATE_DROP,
            result=sample_result,
        )

        assert report.root_cause_analysis == "Analysis pending"

    def test_generate_postmortem_failed_result(self, handler):
        """Test post-mortem with failed result."""
        result = RollbackResult(
            success=False,
            target_version="v1.0.0",
            steps_completed=2,
            total_steps=5,
            error_message="Step 3 failed",
        )

        report = handler.generate_postmortem(
            trigger=RollbackTrigger.SAFETY_VIOLATION,
            result=result,
        )

        assert report.outcome.success is False
        assert len(report.steps_executed) == 3  # 2 completed + 1 failed


class TestRollbackHandlerEdgeCases:
    """Tests for edge cases."""

    def test_no_triggers_with_empty_metrics(self):
        """Test no triggers with empty metrics."""
        handler = RollbackHandler()
        triggers = handler.check_triggers()
        assert triggers == []

    def test_all_triggers_simultaneously(self):
        """Test all possible triggers at once."""
        handler = RollbackHandler(
            ece_threshold=0.15,
            win_rate_threshold=0.05,
            max_drawdown_threshold=0.20,
        )
        handler.update_metrics(
            {
                "ece": 0.20,
                "win_rate": 0.70,
                "baseline_win_rate": 0.80,
                "max_drawdown": 0.25,
                "safety_violations": 1,
            }
        )
        triggers = handler.check_triggers()
        assert len(triggers) == 4

    def test_force_bypasses_safety_checks(self):
        """Test that force flag bypasses safety checks."""
        handler = RollbackHandler(
            version_registry=["v1.0.0"],
            active_trades_check=True,
        )
        handler.update_metrics(
            {
                "active_trades": 10,
                "data_consistent": False,  # Would also fail validation
            }
        )

        # Without force - should fail
        result_normal = handler.emergency_rollback("v1.0.0", force=False)
        assert result_normal.success is False

        # With force - should succeed
        result_force = handler.emergency_rollback("v1.0.0", force=True)
        assert result_force.success is True

    def test_version_registry_isolation(self):
        """Test that version registry is isolated between handlers."""
        handler1 = RollbackHandler(version_registry=["v1.0.0"])
        handler2 = RollbackHandler(version_registry=["v2.0.0"])

        assert handler1.version_registry == ["v1.0.0"]
        assert handler2.version_registry == ["v2.0.0"]

    def test_metrics_update_accumulates(self):
        """Test that metrics update accumulates values."""
        handler = RollbackHandler()
        handler.update_metrics({"ece": 0.20})
        handler.update_metrics({"win_rate": 0.70})

        assert handler._current_metrics["ece"] == 0.20
        assert handler._current_metrics["win_rate"] == 0.70

    def test_rollback_history_isolation(self):
        """Test that rollback history is isolated."""
        handler = RollbackHandler(version_registry=["v1.0.0"])
        handler.update_metrics(
            {
                "active_trades": 0,
                "data_consistent": True,
            }
        )

        steps = [RollbackStep(1, "Test", "cmd", "ok")]
        handler.execute_rollback("v1.0.0", steps)

        history = handler.get_rollback_history()
        assert len(history) == 1

        # Modifying returned history shouldn't affect internal state
        history.clear()
        assert len(handler.get_rollback_history()) == 1


class TestRollbackStepEdgeCases:
    """Tests for RollbackStep edge cases."""

    def test_step_with_empty_strings(self):
        """Test step creation with empty strings."""
        step = RollbackStep(
            step_number=1,
            description="",
            verification_command="",
            expected_result="",
        )
        assert step.description == ""
        assert step.verification_command == ""
        assert step.expected_result == ""

    def test_step_with_large_step_number(self):
        """Test step with large step number."""
        step = RollbackStep(
            step_number=999999,
            description="Test",
            verification_command="cmd",
            expected_result="ok",
        )
        assert step.step_number == 999999

    def test_step_mutation(self):
        """Test that step completed status can be mutated."""
        step = RollbackStep(
            step_number=1,
            description="Test",
            verification_command="cmd",
            expected_result="ok",
            completed=False,
        )
        assert step.completed is False

        step.completed = True
        assert step.completed is True


class TestRollbackResultEdgeCases:
    """Tests for RollbackResult edge cases."""

    def test_result_with_zero_steps(self):
        """Test result with zero steps."""
        result = RollbackResult(
            success=True,
            target_version="v1.0.0",
            steps_completed=0,
            total_steps=0,
        )
        assert result.steps_completed == 0
        assert result.total_steps == 0

    def test_result_with_negative_duration(self):
        """Test result with negative duration (edge case)."""
        result = RollbackResult(
            success=True,
            target_version="v1.0.0",
            steps_completed=1,
            total_steps=1,
            duration_seconds=-1.0,
        )
        assert result.duration_seconds == -1.0

    def test_result_timestamp_is_datetime(self):
        """Test that result timestamp is datetime object."""
        result = RollbackResult(
            success=True,
            target_version="v1.0.0",
            steps_completed=1,
            total_steps=1,
        )
        assert isinstance(result.timestamp, datetime)


class TestPostmortemReportEdgeCases:
    """Tests for PostmortemReport edge cases."""

    def test_empty_timeline(self):
        """Test report with empty timeline."""
        result = RollbackResult(
            success=True,
            target_version="v1.0.0",
            steps_completed=1,
            total_steps=1,
        )
        report = PostmortemReport(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            timeline=[],
            steps_executed=[],
            outcome=result,
            root_cause_analysis="Test",
        )

        json_str = report.to_json()
        data = json.loads(json_str)
        assert data["timeline"] == []

    def test_empty_steps_executed(self):
        """Test report with empty steps executed."""
        result = RollbackResult(
            success=True,
            target_version="v1.0.0",
            steps_completed=0,
            total_steps=0,
        )
        report = PostmortemReport(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            timeline=[],
            steps_executed=[],
            outcome=result,
            root_cause_analysis="Test",
        )

        md = report.to_markdown()
        assert "Steps Executed" in md

    def test_empty_metadata(self):
        """Test report with empty metadata."""
        result = RollbackResult(
            success=True,
            target_version="v1.0.0",
            steps_completed=1,
            total_steps=1,
        )
        report = PostmortemReport(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            timeline=[],
            steps_executed=[],
            outcome=result,
            root_cause_analysis="Test",
            metadata={},
        )

        json_str = report.to_json()
        data = json.loads(json_str)
        assert data["metadata"] == {}
