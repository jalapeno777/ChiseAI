"""
Unit tests for bottleneck reflection generator.
"""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from governance.reflection.artifacts import Priority
from governance.reflection.bottleneck_reflection import (
    BottleneckKPI,
    BottleneckReflectionGenerator,
    DailyReflectionArtifact,
    FrameworkImprovement,
    ImpactScore,
    RemediationAction,
    TrendDelta,
    WeeklyReflectionArtifact,
    create_daily_reflection,
    create_weekly_reflection,
)


class TestImpactScore:
    """Tests for ImpactScore dataclass."""

    def test_default_values(self):
        """Test default impact scores are all 1."""
        impact = ImpactScore()
        assert impact.throughput == 1
        assert impact.efficiency == 1
        assert impact.accuracy == 1
        assert impact.reliability == 1

    def test_custom_values(self):
        """Test custom impact scores."""
        impact = ImpactScore(throughput=4, efficiency=3, accuracy=2, reliability=5)
        assert impact.throughput == 4
        assert impact.efficiency == 3
        assert impact.accuracy == 2
        assert impact.reliability == 5

    def test_validation_below_range(self):
        """Test that scores below 1 raise ValueError."""
        with pytest.raises(ValueError, match="throughput must be between 1 and 5"):
            ImpactScore(throughput=0)

    def test_validation_above_range(self):
        """Test that scores above 5 raise ValueError."""
        with pytest.raises(ValueError, match="efficiency must be between 1 and 5"):
            ImpactScore(efficiency=6)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        impact = ImpactScore(throughput=3, efficiency=4, accuracy=2, reliability=5)
        result = impact.to_dict()
        assert result == {
            "throughput": 3,
            "efficiency": 4,
            "accuracy": 2,
            "reliability": 5,
        }

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {"throughput": 2, "efficiency": 3, "accuracy": 4, "reliability": 1}
        impact = ImpactScore.from_dict(data)
        assert impact.throughput == 2
        assert impact.efficiency == 3
        assert impact.accuracy == 4
        assert impact.reliability == 1


class TestBottleneckKPI:
    """Tests for BottleneckKPI dataclass."""

    def test_default_values(self):
        """Test default values."""
        bn = BottleneckKPI(
            bottleneck_type="test",
            occurrence_count=5,
            avg_impact_score=3.5,
        )
        assert bn.affected_stories == []
        assert bn.trend_direction == "stable"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        bn = BottleneckKPI(
            bottleneck_type="ci_failures",
            occurrence_count=10,
            avg_impact_score=4.2,
            affected_stories=["ST-001", "ST-002"],
            trend_direction="improving",
        )
        result = bn.to_dict()
        assert result["bottleneck_type"] == "ci_failures"
        assert result["occurrence_count"] == 10
        assert result["avg_impact_score"] == 4.2
        assert result["affected_stories"] == ["ST-001", "ST-002"]
        assert result["trend_direction"] == "improving"


class TestRemediationAction:
    """Tests for RemediationAction dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        action = RemediationAction(
            action="Fix CI pipeline",
            priority=Priority.HIGH,
            owner_placeholder="OWNER_TBD: devops",
            estimated_effort="2-4 hours",
            impact_score=ImpactScore(
                throughput=4, efficiency=3, accuracy=2, reliability=4
            ),
        )
        result = action.to_dict()
        assert result["action"] == "Fix CI pipeline"
        assert result["priority"] == "high"
        assert result["owner_placeholder"] == "OWNER_TBD: devops"
        assert result["estimated_effort"] == "2-4 hours"
        assert result["impact_score"]["throughput"] == 4


class TestTrendDelta:
    """Tests for TrendDelta dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        delta = TrendDelta(
            kpi_name="coverage",
            current_value=0.85,
            previous_value=0.80,
            delta=0.05,
            delta_percent=6.25,
            direction="improved",
        )
        result = delta.to_dict()
        assert result["kpi_name"] == "coverage"
        assert result["current_value"] == 0.85
        assert result["delta_percent"] == 6.25
        assert result["direction"] == "improved"


class TestFrameworkImprovement:
    """Tests for FrameworkImprovement dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        improvement = FrameworkImprovement(
            improvement="Add auto-retry",
            priority=Priority.HIGH,
            owner_placeholder="OWNER_TBD: senior-dev",
            rationale="CI failures increasing",
            estimated_impact="30% reduction",
        )
        result = improvement.to_dict()
        assert result["improvement"] == "Add auto-retry"
        assert result["priority"] == "high"
        assert result["owner_placeholder"] == "OWNER_TBD: senior-dev"


class TestDailyReflectionArtifact:
    """Tests for DailyReflectionArtifact."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        artifact = DailyReflectionArtifact(
            date="2026-03-02",
            timestamp="2026-03-02T12:00:00Z",
            provenance="test",
            top_bottlenecks=[
                BottleneckKPI("ci_failures", 5, 4.0),
            ],
            impact_scores=ImpactScore(3, 3, 2, 4),
            remediation_actions=[],
            summary="Test summary",
        )
        result = artifact.to_dict()
        assert result["date"] == "2026-03-02"
        assert result["provenance"] == "test"
        assert len(result["top_bottlenecks"]) == 1

    def test_to_json(self):
        """Test JSON serialization."""
        artifact = DailyReflectionArtifact(
            date="2026-03-02",
            timestamp="2026-03-02T12:00:00Z",
            provenance="test",
            top_bottlenecks=[],
            impact_scores=ImpactScore(),
            remediation_actions=[],
            summary="Test",
        )
        json_str = artifact.to_json()
        data = json.loads(json_str)
        assert data["date"] == "2026-03-02"


class TestWeeklyReflectionArtifact:
    """Tests for WeeklyReflectionArtifact."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        artifact = WeeklyReflectionArtifact(
            week_start="2026-02-24",
            week_end="2026-03-02",
            timestamp="2026-03-02T12:00:00Z",
            provenance="test",
            trend_deltas=[],
            improvements=["coverage"],
            regressions=["cycle_time_hours"],
            framework_improvements=[],
            summary="Test",
        )
        result = artifact.to_dict()
        assert result["week_start"] == "2026-02-24"
        assert result["week_end"] == "2026-03-02"
        assert result["improvements"] == ["coverage"]
        assert result["regressions"] == ["cycle_time_hours"]


class TestBottleneckReflectionGenerator:
    """Tests for BottleneckReflectionGenerator."""

    @pytest.fixture
    def generator(self):
        """Create a generator with temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield BottleneckReflectionGenerator(output_dir=tmpdir)

    @pytest.fixture
    def sample_trend_rollups(self):
        """Sample trend rollup data."""
        return [
            {
                "ci_failures": 3,
                "test_failures": 2,
                "story_id": "ST-001",
                "kpi_snapshot": {
                    "ci_pass_rate": 0.92,
                    "coverage": 0.78,
                    "cycle_time_hours": 4.5,
                    "test_count": 15,
                    "lines_changed": 120,
                },
            },
            {
                "ci_failures": 2,
                "merge_conflicts": 1,
                "story_id": "ST-002",
                "kpi_snapshot": {
                    "ci_pass_rate": 0.88,
                    "coverage": 0.82,
                    "cycle_time_hours": 3.2,
                    "test_count": 8,
                    "lines_changed": 45,
                },
            },
        ]

    def test_init_default_output_dir(self):
        """Test default output directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                gen = BottleneckReflectionGenerator()
                expected = Path("_bmad-output/brain-eval/reflections")
                assert gen.output_dir == expected
            finally:
                os.chdir(old_cwd)

    def test_init_custom_output_dir(self):
        """Test custom output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = BottleneckReflectionGenerator(output_dir=tmpdir)
            assert gen.output_dir == Path(tmpdir)

    def test_generate_daily_reflection(self, generator, sample_trend_rollups):
        """Test daily reflection generation."""
        artifact = generator.generate_daily_reflection(sample_trend_rollups)

        assert isinstance(artifact, DailyReflectionArtifact)
        assert artifact.date == datetime.now(UTC).strftime("%Y-%m-%d")
        assert len(artifact.top_bottlenecks) <= 3
        assert isinstance(artifact.impact_scores, ImpactScore)
        assert (
            artifact.provenance == "bottleneck_reflection.BottleneckReflectionGenerator"
        )

    def test_generate_daily_reflection_with_date(self, generator, sample_trend_rollups):
        """Test daily reflection with specific date."""
        date = datetime(2026, 3, 1, tzinfo=UTC)
        artifact = generator.generate_daily_reflection(sample_trend_rollups, date=date)

        assert artifact.date == "2026-03-01"

    def test_generate_daily_reflection_empty_rollups(self, generator):
        """Test daily reflection with no data."""
        artifact = generator.generate_daily_reflection([])

        assert len(artifact.top_bottlenecks) == 0
        assert artifact.impact_scores == ImpactScore()

    def test_generate_weekly_reflection(self, generator, sample_trend_rollups):
        """Test weekly reflection generation."""
        artifact = generator.generate_weekly_reflection(sample_trend_rollups)

        assert isinstance(artifact, WeeklyReflectionArtifact)
        assert len(artifact.trend_deltas) == 5  # 5 KPIs
        assert (
            artifact.provenance == "bottleneck_reflection.BottleneckReflectionGenerator"
        )

    def test_generate_weekly_reflection_with_comparison(
        self, generator, sample_trend_rollups
    ):
        """Test weekly reflection with previous week comparison."""
        previous_rollups = [
            {
                "kpi_snapshot": {
                    "ci_pass_rate": 0.85,
                    "coverage": 0.75,
                    "cycle_time_hours": 5.0,
                    "test_count": 10,
                    "lines_changed": 100,
                },
            }
        ]

        artifact = generator.generate_weekly_reflection(
            sample_trend_rollups, previous_week_rollups=previous_rollups
        )

        # Should have calculated deltas
        assert len(artifact.trend_deltas) == 5
        # CI pass rate should show improvement (0.85 -> 0.90)
        ci_delta = next(
            d for d in artifact.trend_deltas if d.kpi_name == "ci_pass_rate"
        )
        assert ci_delta.direction == "improved"

    def test_generate_weekly_reflection_with_week_start(
        self, generator, sample_trend_rollups
    ):
        """Test weekly reflection with specific week start."""
        week_start = datetime(2026, 2, 24, tzinfo=UTC)
        artifact = generator.generate_weekly_reflection(
            sample_trend_rollups, week_start=week_start
        )

        assert artifact.week_start == "2026-02-24"
        assert artifact.week_end == "2026-03-02"

    def test_export_reflection_artifact_daily(self, generator, sample_trend_rollups):
        """Test exporting daily reflection."""
        artifact = generator.generate_daily_reflection(sample_trend_rollups)
        filepath = generator.export_reflection_artifact(artifact)

        assert filepath.exists()
        assert filepath.name.startswith("daily-")
        assert filepath.suffix == ".json"

        # Verify content
        with open(filepath) as f:
            data = json.load(f)
        assert data["date"] == artifact.date

    def test_export_reflection_artifact_weekly(self, generator, sample_trend_rollups):
        """Test exporting weekly reflection."""
        artifact = generator.generate_weekly_reflection(sample_trend_rollups)
        filepath = generator.export_reflection_artifact(artifact)

        assert filepath.exists()
        assert filepath.name.startswith("weekly-")
        assert filepath.suffix == ".json"

    def test_export_reflection_artifact_custom_path(
        self, generator, sample_trend_rollups
    ):
        """Test exporting to custom path."""
        artifact = generator.generate_daily_reflection(sample_trend_rollups)
        custom_path = Path(generator.output_dir) / "custom" / "test.json"
        filepath = generator.export_reflection_artifact(artifact, filepath=custom_path)

        assert filepath == custom_path
        assert filepath.exists()

    def test_extract_bottlenecks(self, generator):
        """Test bottleneck extraction from rollups."""
        rollups = [
            {"ci_failures": 3, "test_failures": 2, "story_id": "ST-001"},
            {"ci_failures": 1, "merge_conflicts": 2, "story_id": "ST-002"},
        ]

        bottlenecks = generator._extract_bottlenecks(rollups)

        assert len(bottlenecks) == 3
        # CI failures should have 4 occurrences total
        ci_bn = next(b for b in bottlenecks if b.bottleneck_type == "ci_failures")
        assert ci_bn.occurrence_count == 4

    def test_extract_bottlenecks_with_bottlenecks_key(self, generator):
        """Test extraction with 'bottlenecks' key format."""
        rollups = [
            {
                "bottlenecks": [
                    {"type": "ci_failures", "count": 3, "impact_score": 4},
                    {"type": "test_failures", "count": 2, "impact_score": 3},
                ]
            }
        ]

        bottlenecks = generator._extract_bottlenecks(rollups)

        assert len(bottlenecks) == 2
        ci_bn = next(b for b in bottlenecks if b.bottleneck_type == "ci_failures")
        assert ci_bn.occurrence_count == 3
        assert ci_bn.avg_impact_score == 4.0

    def test_calculate_aggregate_impact(self, generator):
        """Test aggregate impact calculation."""
        bottlenecks = [
            BottleneckKPI("ci_failures", 5, 4.0),
            BottleneckKPI("test_failures", 3, 3.0),
        ]

        impact = generator._calculate_aggregate_impact(bottlenecks)

        assert isinstance(impact, ImpactScore)
        # Values should be weighted averages
        assert 1 <= impact.throughput <= 5
        assert 1 <= impact.efficiency <= 5

    def test_generate_remediation_actions(self, generator):
        """Test remediation action generation."""
        bottlenecks = [
            BottleneckKPI("ci_failures", 5, 4.0),
            BottleneckKPI("test_failures", 3, 3.0),
        ]

        actions = generator._generate_remediation_actions(bottlenecks)

        assert len(actions) <= 3
        # Should be sorted by priority
        if len(actions) > 1:
            priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
            for i in range(len(actions) - 1):
                assert (
                    priority_order[actions[i].priority]
                    <= priority_order[actions[i + 1].priority]
                )

    def test_calculate_trend_deltas_improvement(self, generator):
        """Test trend delta calculation for improvements."""
        current = [{"ci_pass_rate": 0.95}]
        previous = [{"ci_pass_rate": 0.85}]

        deltas = generator._calculate_trend_deltas(current, previous)

        ci_delta = next(d for d in deltas if d.kpi_name == "ci_pass_rate")
        assert ci_delta.direction == "improved"
        assert ci_delta.delta == pytest.approx(0.10, rel=0.01)

    def test_calculate_trend_deltas_regression(self, generator):
        """Test trend delta calculation for regressions."""
        current = [{"coverage": 0.75}]
        previous = [{"coverage": 0.85}]

        deltas = generator._calculate_trend_deltas(current, previous)

        coverage_delta = next(d for d in deltas if d.kpi_name == "coverage")
        assert coverage_delta.direction == "regressed"

    def test_calculate_trend_deltas_cycle_time_improvement(self, generator):
        """Test that lower cycle time is considered improvement."""
        current = [{"cycle_time_hours": 3.0}]
        previous = [{"cycle_time_hours": 5.0}]

        deltas = generator._calculate_trend_deltas(current, previous)

        ct_delta = next(d for d in deltas if d.kpi_name == "cycle_time_hours")
        assert ct_delta.direction == "improved"

    def test_generate_framework_improvements_with_regressions(self, generator):
        """Test framework improvement generation with regressions."""
        deltas = [
            TrendDelta("ci_pass_rate", 0.85, 0.95, -0.10, -10.5, "regressed"),
            TrendDelta("coverage", 0.90, 0.85, 0.05, 5.9, "improved"),
        ]

        improvements = generator._generate_framework_improvements(deltas, [])

        assert len(improvements) > 0
        # Should include CI-related improvement
        ci_improvement = next((i for i in improvements if "CI" in i.improvement), None)
        assert ci_improvement is not None
        assert ci_improvement.priority == Priority.HIGH

    def test_generate_framework_improvements_stable(self, generator):
        """Test framework improvement generation when stable."""
        deltas = [
            TrendDelta("ci_pass_rate", 0.90, 0.90, 0.0, 0.0, "stable"),
        ]

        improvements = generator._generate_framework_improvements(deltas, [])

        assert len(improvements) == 1
        assert improvements[0].priority == Priority.LOW

    def test_generate_daily_summary(self, generator):
        """Test daily summary generation."""
        bottlenecks = [
            BottleneckKPI("ci_failures", 5, 4.0, ["ST-001"], "worsening"),
        ]
        impact = ImpactScore(4, 3, 2, 4)

        summary = generator._generate_daily_summary("2026-03-02", bottlenecks, impact)

        assert "2026-03-02" in summary
        assert "ci_failures" in summary
        assert "Throughput: 4" in summary

    def test_generate_weekly_summary(self, generator):
        """Test weekly summary generation."""
        deltas = [
            TrendDelta("coverage", 0.85, 0.80, 0.05, 6.25, "improved"),
        ]

        summary = generator._generate_weekly_summary(
            "2026-02-24", "2026-03-02", deltas, ["coverage"], []
        )

        assert "2026-02-24" in summary
        assert "2026-03-02" in summary
        assert "coverage" in summary


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_daily_reflection(self):
        """Test create_daily_reflection convenience function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rollups = [{"ci_failures": 2}]
            artifact, filepath = create_daily_reflection(rollups, output_dir=tmpdir)

            assert isinstance(artifact, DailyReflectionArtifact)
            assert filepath.exists()

    def test_create_weekly_reflection(self):
        """Test create_weekly_reflection convenience function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rollups = [{"ci_pass_rate": 0.90}]
            artifact, filepath = create_weekly_reflection(rollups, output_dir=tmpdir)

            assert isinstance(artifact, WeeklyReflectionArtifact)
            assert filepath.exists()


class TestIntegration:
    """Integration tests for the complete workflow."""

    def test_full_workflow(self):
        """Test complete workflow from rollups to exported artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = BottleneckReflectionGenerator(output_dir=tmpdir)

            # Sample data representing a day's worth of rollups
            rollups = [
                {
                    "ci_failures": 3,
                    "test_failures": 2,
                    "story_id": "ST-001",
                    "kpi_snapshot": {
                        "ci_pass_rate": 0.92,
                        "coverage": 0.78,
                        "cycle_time_hours": 4.5,
                    },
                },
                {
                    "ci_failures": 2,
                    "merge_conflicts": 1,
                    "story_id": "ST-002",
                    "kpi_snapshot": {
                        "ci_pass_rate": 0.88,
                        "coverage": 0.82,
                        "cycle_time_hours": 3.2,
                    },
                },
                {
                    "timeout_issues": 1,
                    "story_id": "ST-003",
                    "kpi_snapshot": {
                        "ci_pass_rate": 0.95,
                        "coverage": 0.85,
                        "cycle_time_hours": 2.8,
                    },
                },
            ]

            # Generate and export daily reflection
            daily = generator.generate_daily_reflection(rollups)
            daily_path = generator.export_reflection_artifact(daily)

            # Generate and export weekly reflection
            previous_week = [
                {
                    "kpi_snapshot": {
                        "ci_pass_rate": 0.85,
                        "coverage": 0.75,
                        "cycle_time_hours": 5.0,
                    },
                }
            ]
            weekly = generator.generate_weekly_reflection(
                rollups, previous_week_rollups=previous_week
            )
            weekly_path = generator.export_reflection_artifact(weekly)

            # Verify files exist and are valid JSON
            assert daily_path.exists()
            assert weekly_path.exists()

            with open(daily_path) as f:
                daily_data = json.load(f)
            assert "top_bottlenecks" in daily_data
            assert "remediation_actions" in daily_data

            with open(weekly_path) as f:
                weekly_data = json.load(f)
            assert "trend_deltas" in weekly_data
            assert "framework_improvements" in weekly_data

    def test_idempotent_export(self):
        """Test that export is idempotent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = BottleneckReflectionGenerator(output_dir=tmpdir)

            rollups = [{"ci_failures": 1}]
            artifact = generator.generate_daily_reflection(rollups)

            # Export twice
            path1 = generator.export_reflection_artifact(artifact)
            path2 = generator.export_reflection_artifact(artifact)

            assert path1 == path2
            assert path1.exists()


class TestOwnerPlaceholders:
    """Tests for owner placeholder requirements."""

    def test_remediation_has_owner_placeholder(self):
        """Test that remediation actions have explicit owner placeholders."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = BottleneckReflectionGenerator(output_dir=tmpdir)

            rollups = [{"ci_failures": 5, "test_failures": 3}]
            artifact = generator.generate_daily_reflection(rollups)

            for action in artifact.remediation_actions:
                assert action.owner_placeholder.startswith("OWNER_TBD:")
                assert len(action.owner_placeholder.split(":")) == 2

    def test_framework_improvement_has_owner_placeholder(self):
        """Test that framework improvements have explicit owner placeholders."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = BottleneckReflectionGenerator(output_dir=tmpdir)

            current = [{"ci_pass_rate": 0.85}]
            previous = [{"ci_pass_rate": 0.95}]
            artifact = generator.generate_weekly_reflection(
                current, previous_week_rollups=previous
            )

            for improvement in artifact.framework_improvements:
                assert improvement.owner_placeholder.startswith("OWNER_TBD:")
                assert len(improvement.owner_placeholder.split(":")) == 2


class TestImpactScoring:
    """Tests for impact scoring requirements."""

    def test_impact_scores_in_range(self):
        """Test that all impact scores are in 1-5 range."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = BottleneckReflectionGenerator(output_dir=tmpdir)

            rollups = [
                {"ci_failures": 5},
                {"test_failures": 3},
                {"merge_conflicts": 2},
            ]
            artifact = generator.generate_daily_reflection(rollups)

            impact = artifact.impact_scores
            assert 1 <= impact.throughput <= 5
            assert 1 <= impact.efficiency <= 5
            assert 1 <= impact.accuracy <= 5
            assert 1 <= impact.reliability <= 5

    def test_remediation_impact_scores(self):
        """Test that remediation actions include impact scores."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = BottleneckReflectionGenerator(output_dir=tmpdir)

            rollups = [{"ci_failures": 5}]
            artifact = generator.generate_daily_reflection(rollups)

            for action in artifact.remediation_actions:
                if action.impact_score is not None:
                    assert 1 <= action.impact_score.throughput <= 5
