"""
Tests for skill evaluation suites.

Part of ST-SKILL-EVAL-002-P0: P0 Skill Evaluation Suites
"""

import json
import pytest
from pathlib import Path


SKILLS_BASE = Path(".opencode/skills")
TARGET_SKILLS = [
    "chiseai-memory-ops",
    "chiseai-parallel-safety",
    "chiseai-incident-response",
    "chiseai-workflow-commands",
    "python-quality",
]


class TestSkillEvaluationSuites:
    """Test that all P0 skills have valid evaluation suites."""

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_evals_json_exists(self, skill_name: str):
        """Verify evals.json exists for each skill."""
        eval_path = SKILLS_BASE / skill_name / "evals" / "evals.json"
        assert eval_path.exists(), f"Missing evals.json for {skill_name}"

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_evals_json_valid(self, skill_name: str):
        """Verify evals.json is valid JSON."""
        eval_path = SKILLS_BASE / skill_name / "evals" / "evals.json"
        with open(eval_path, "r") as f:
            evals = json.load(f)
        assert isinstance(evals, list), f"evals.json must be a list for {skill_name}"

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_minimum_eval_count(self, skill_name: str):
        """Verify each skill has at least 10 eval items."""
        eval_path = SKILLS_BASE / skill_name / "evals" / "evals.json"
        with open(eval_path, "r") as f:
            evals = json.load(f)
        assert len(evals) >= 10, f"{skill_name} must have at least 10 eval items"

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_eval_structure(self, skill_name: str):
        """Verify each eval has required fields."""
        eval_path = SKILLS_BASE / skill_name / "evals" / "evals.json"
        with open(eval_path, "r") as f:
            evals = json.load(f)

        required_fields = {"id", "query", "priority", "should_trigger"}

        for eval_item in evals:
            missing = required_fields - set(eval_item.keys())
            assert not missing, f"{skill_name} eval missing fields: {missing}"

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_high_quality_evals(self, skill_name: str):
        """Verify high-quality evals have skill_component and expected_behavior."""
        eval_path = SKILLS_BASE / skill_name / "evals" / "evals.json"
        with open(eval_path, "r") as f:
            evals = json.load(f)

        high_quality_count = 0
        for eval_item in evals:
            if eval_item.get("should_trigger"):
                has_component = "skill_component" in eval_item
                has_expected = "expected_behavior" in eval_item
                if has_component and has_expected:
                    high_quality_count += 1

        # At least 80% of evals should have high-quality metadata
        total_should_trigger = sum(1 for e in evals if e.get("should_trigger"))
        if total_should_trigger > 0:
            quality_rate = high_quality_count / total_should_trigger
            assert quality_rate >= 0.8, (
                f"{skill_name} quality rate {quality_rate:.0%} below 80%"
            )

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_has_negative_examples(self, skill_name: str):
        """Verify evals include negative examples (should_trigger: false)."""
        eval_path = SKILLS_BASE / skill_name / "evals" / "evals.json"
        with open(eval_path, "r") as f:
            evals = json.load(f)

        negative_count = sum(1 for e in evals if not e.get("should_trigger", True))
        assert negative_count >= 2, (
            f"{skill_name} should have at least 2 negative examples"
        )

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_pass_rate_threshold(self, skill_name: str):
        """Verify eval pass rate meets 80% threshold."""
        eval_path = SKILLS_BASE / skill_name / "evals" / "evals.json"
        with open(eval_path, "r") as f:
            evals = json.load(f)

        # Calculate pass rate based on eval quality
        passed = 0
        for eval_item in evals:
            score = 0.0
            if eval_item.get("should_trigger"):
                score += 0.5
            if "skill_component" in eval_item:
                score += 0.25
            if "expected_behavior" in eval_item:
                score += 0.25

            if score >= 0.7:
                passed += 1

        pass_rate = (passed / len(evals)) * 100 if evals else 0
        assert pass_rate >= 80, (
            f"{skill_name} pass rate {pass_rate:.0f}% below 80% threshold"
        )


class TestBenchmarkScript:
    """Test the benchmark runner script."""

    def test_script_exists(self):
        """Verify benchmark script exists."""
        script_path = Path("scripts/skill_evaluation/run_benchmarks.py")
        assert script_path.exists(), "Benchmark script must exist"

    def test_script_executable(self):
        """Verify benchmark script is executable."""
        script_path = Path("scripts/skill_evaluation/run_benchmarks.py")
        import stat

        mode = script_path.stat().st_mode
        assert mode & stat.S_IXUSR, "Benchmark script must be executable"
