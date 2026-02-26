#!/usr/bin/env python3
"""Tests for agent onboarding module.

This module tests the agent onboarding functionality including:
- Onboarding validation
- Capability assessment
- Checklist validation
- CLI commands
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts to path
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "scripts" / "pr_lifecycle")
)

from agent_onboarding import (
    AgentCapabilities,
    AgentOnboarding,
    CapabilityLevel,
    OnboardingChecklist,
    OnboardingResult,
    OnboardingStatus,
    main,
)


class TestAgentCapabilities:
    """Tests for AgentCapabilities class."""

    def test_overall_score_calculation(self):
        """Test overall score calculation."""
        caps = AgentCapabilities(
            git_proficiency=8,
            testing_experience=7,
            ci_cd_familiarity=6,
            python_skill=9,
            documentation_skill=7,
        )
        assert caps.overall_score() == 7.4  # (8+7+6+9+7)/5

    def test_overall_score_with_zeros(self):
        """Test overall score with zero values."""
        caps = AgentCapabilities()
        assert caps.overall_score() == 0.0

    def test_capability_level_expert(self):
        """Test expert level determination."""
        caps = AgentCapabilities(
            git_proficiency=9,
            testing_experience=8,
            ci_cd_familiarity=8,
            python_skill=9,
            documentation_skill=8,
        )
        assert caps.level() == CapabilityLevel.EXPERT

    def test_capability_level_intermediate(self):
        """Test intermediate level determination."""
        caps = AgentCapabilities(
            git_proficiency=6,
            testing_experience=5,
            ci_cd_familiarity=4,
            python_skill=6,
            documentation_skill=5,
        )
        assert caps.level() == CapabilityLevel.INTERMEDIATE

    def test_capability_level_novice(self):
        """Test novice level determination."""
        caps = AgentCapabilities(
            git_proficiency=2,
            testing_experience=3,
            ci_cd_familiarity=2,
            python_skill=4,
            documentation_skill=3,
        )
        assert caps.level() == CapabilityLevel.NOVICE


class TestOnboardingChecklist:
    """Tests for OnboardingChecklist class."""

    def test_empty_checklist(self):
        """Test empty checklist has 0% completion."""
        checklist = OnboardingChecklist()
        assert checklist.completion_percentage() == 0.0
        assert not checklist.is_complete()

    def test_complete_checklist(self):
        """Test complete checklist has 100% completion."""
        checklist = OnboardingChecklist(
            read_agents_md=True,
            read_git_workflow=True,
            read_pr_paths=True,
            read_best_practices=True,
            git_configured=True,
            redis_accessible=True,
            test_environment_working=True,
            completed_first_session=True,
            validated_tooling=True,
            understood_scope_ownership=True,
        )
        assert checklist.completion_percentage() == 100.0
        assert checklist.is_complete()

    def test_partial_checklist(self):
        """Test partial completion."""
        checklist = OnboardingChecklist(
            read_agents_md=True,
            git_configured=True,
            test_environment_working=True,
        )
        assert checklist.completion_percentage() == 30.0
        assert not checklist.is_complete()

    def test_missing_items(self):
        """Test missing items list."""
        checklist = OnboardingChecklist(
            read_agents_md=True,
            git_configured=True,
        )
        missing = checklist.missing_items()
        assert len(missing) == 8  # 10 total - 2 complete
        assert any("read_git_workflow" in item for item in missing)
        assert any("redis_accessible" in item for item in missing)


class TestOnboardingResult:
    """Tests for OnboardingResult class."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        caps = AgentCapabilities(git_proficiency=8)
        checklist = OnboardingChecklist(read_agents_md=True)
        result = OnboardingResult(
            agent_id="test-agent",
            status=OnboardingStatus.IN_PROGRESS,
            capabilities=caps,
            checklist=checklist,
            messages=["Test message"],
            recommendations=["Test recommendation"],
        )

        data = result.to_dict()
        assert data["agent_id"] == "test-agent"
        assert data["status"] == "in_progress"
        assert data["capabilities"]["git_proficiency"] == 8
        # Overall score is average of all 5 capabilities (8+0+0+0+0)/5 = 1.6
        assert data["capabilities"]["overall_score"] == 1.6
        assert data["capabilities"]["level"] == "novice"
        assert data["checklist"]["completion_percentage"] == 10.0
        assert len(data["messages"]) == 1
        assert len(data["recommendations"]) == 1


class TestAgentOnboarding:
    """Tests for AgentOnboarding class."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            # Create basic structure
            (repo_root / "AGENTS.md").write_text("# Agents")
            (repo_root / ".opencode" / "skills" / "chiseai-git-workflow").mkdir(
                parents=True
            )
            (
                repo_root / ".opencode" / "skills" / "chiseai-git-workflow" / "SKILL.md"
            ).write_text("# Git Workflow")
            (repo_root / "docs" / "guides").mkdir(parents=True)
            (repo_root / "docs" / "guides" / "pr-pipeline-quickstart.md").write_text(
                "# Quick Start"
            )
            (
                repo_root / "docs" / "guides" / "pr-pipeline-best-practices.md"
            ).write_text("# Best Practices")

            # Initialize git
            subprocess.run(
                ["git", "init"],
                cwd=repo_root,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_root,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=repo_root,
                capture_output=True,
                check=True,
            )

            yield repo_root

    @pytest.fixture
    def onboarding(self, temp_repo):
        """Create AgentOnboarding instance."""
        return AgentOnboarding(agent_id="test-agent", repo_root=str(temp_repo))

    def test_init(self, onboarding):
        """Test initialization."""
        assert onboarding.agent_id == "test-agent"
        assert onboarding.repo_root.exists()

    def test_check_file_exists(self, onboarding, temp_repo):
        """Test file existence check."""
        assert onboarding._check_file_exists("AGENTS.md")
        assert not onboarding._check_file_exists("NONEXISTENT.md")

    def test_check_git_configured(self, onboarding):
        """Test git configuration check."""
        # Should be configured from fixture
        assert onboarding._check_git_configured()

    def test_assess_capabilities(self, onboarding):
        """Test capability assessment."""
        caps = onboarding.assess_capabilities()
        assert isinstance(caps, AgentCapabilities)
        assert 0 <= caps.git_proficiency <= 10
        assert 0 <= caps.testing_experience <= 10

    def test_assess_capabilities_with_values(self, onboarding):
        """Test capability assessment with provided values."""
        caps = onboarding.assess_capabilities(
            git_proficiency=9,
            testing_experience=8,
        )
        assert caps.git_proficiency == 9
        assert caps.testing_experience == 8

    def test_validate_checklist(self, onboarding):
        """Test checklist validation."""
        checklist = onboarding.validate_checklist()
        assert isinstance(checklist, OnboardingChecklist)
        # From fixture, some files should exist
        assert checklist.read_agents_md
        assert checklist.git_configured

    def test_validate_readiness(self, onboarding):
        """Test readiness validation."""
        result = onboarding.validate_readiness()
        assert isinstance(result, OnboardingResult)
        assert result.agent_id == "test-agent"
        assert result.status in OnboardingStatus
        assert len(result.messages) > 0

    def test_get_first_pr_guidance(self, onboarding):
        """Test first PR guidance."""
        guidance = onboarding.get_first_pr_guidance("ST-TEST-001")
        assert guidance["story_id"] == "ST-TEST-001"
        assert guidance["pr_path"] == "SAFE"
        assert len(guidance["steps"]) > 0
        assert len(guidance["tips"]) > 0
        assert len(guidance["common_mistakes"]) > 0

    def test_get_required_reading(self, onboarding):
        """Test required reading list."""
        reading = onboarding.get_required_reading()
        assert len(reading) > 0
        assert all("path" in item for item in reading)
        assert all("description" in item for item in reading)
        assert all("priority" in item for item in reading)


class TestAgentOnboardingCLI:
    """Tests for CLI functionality."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            # Create basic structure
            (repo_root / "AGENTS.md").write_text("# Agents")
            (repo_root / ".opencode" / "skills" / "chiseai-git-workflow").mkdir(
                parents=True
            )
            (
                repo_root / ".opencode" / "skills" / "chiseai-git-workflow" / "SKILL.md"
            ).write_text("# Git Workflow")

            # Initialize git
            subprocess.run(
                ["git", "init"],
                cwd=repo_root,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_root,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=repo_root,
                capture_output=True,
                check=True,
            )

            # Change to repo for tests
            old_cwd = os.getcwd()
            os.chdir(repo_root)
            yield repo_root
            os.chdir(old_cwd)

    def test_cli_help(self):
        """Test CLI help output."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["agent_onboarding.py", "--help"]):
                main()
        assert exc_info.value.code == 0

    def test_cli_validate(self, temp_repo, capsys):
        """Test CLI validate command."""
        with patch(
            "sys.argv",
            [
                "agent_onboarding.py",
                "--agent-id",
                "test-agent",
                "--validate",
            ],
        ):
            result = main()
        assert result is None or result == 0

        captured = capsys.readouterr()
        assert "Agent Onboarding Status" in captured.out

    def test_cli_reading_list(self, temp_repo, capsys):
        """Test CLI reading list command."""
        with patch(
            "sys.argv",
            [
                "agent_onboarding.py",
                "--agent-id",
                "test-agent",
                "--reading-list",
            ],
        ):
            result = main()
        assert result is None or result == 0

        captured = capsys.readouterr()
        assert "Required Reading List" in captured.out

    def test_cli_first_pr(self, temp_repo, capsys):
        """Test CLI first PR command."""
        with patch(
            "sys.argv",
            [
                "agent_onboarding.py",
                "--agent-id",
                "test-agent",
                "--first-pr",
                "ST-TEST-001",
            ],
        ):
            result = main()
        assert result is None or result == 0

        captured = capsys.readouterr()
        assert "First PR Guidance" in captured.out
        assert "ST-TEST-001" in captured.out

    def test_cli_json_output(self, temp_repo, capsys):
        """Test CLI JSON output."""
        with patch(
            "sys.argv",
            [
                "agent_onboarding.py",
                "--agent-id",
                "test-agent",
                "--validate",
                "--json",
            ],
        ):
            result = main()
        assert result is None or result == 0

        captured = capsys.readouterr()
        # Should be valid JSON
        import json

        data = json.loads(captured.out)
        assert "agent_id" in data
        assert "status" in data


class TestIntegration:
    """Integration tests for the full onboarding flow."""

    @pytest.fixture
    def temp_repo(self):
        """Create a complete temporary repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            # Create complete structure
            (repo_root / "AGENTS.md").write_text("# Agents Guide")
            (repo_root / ".opencode" / "skills" / "chiseai-git-workflow").mkdir(
                parents=True
            )
            (
                repo_root / ".opencode" / "skills" / "chiseai-git-workflow" / "SKILL.md"
            ).write_text("Git workflow skill")
            (repo_root / ".opencode" / "skills" / "chiseai-parallel-safety").mkdir(
                parents=True
            )
            (
                repo_root
                / ".opencode"
                / "skills"
                / "chiseai-parallel-safety"
                / "SKILL.md"
            ).write_text("Parallel safety skill")
            (repo_root / "docs" / "guides").mkdir(parents=True)
            (repo_root / "docs" / "guides" / "pr-pipeline-quickstart.md").write_text(
                "Quick start"
            )
            (
                repo_root / "docs" / "guides" / "pr-pipeline-best-practices.md"
            ).write_text("Best practices")

            # Initialize git
            subprocess.run(
                ["git", "init"],
                cwd=repo_root,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_root,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_root,
                capture_output=True,
                check=True,
            )

            yield repo_root

    def test_full_onboarding_flow(self, temp_repo):
        """Test complete onboarding flow."""
        onboarding = AgentOnboarding(
            agent_id="integration-test", repo_root=str(temp_repo)
        )

        # 1. Check required reading
        reading = onboarding.get_required_reading()
        assert len(reading) >= 4

        # 2. Assess capabilities
        caps = onboarding.assess_capabilities()
        assert caps.level() in [
            CapabilityLevel.NOVICE,
            CapabilityLevel.INTERMEDIATE,
            CapabilityLevel.EXPERT,
        ]

        # 3. Validate checklist
        checklist = onboarding.validate_checklist()
        assert checklist.read_agents_md  # Should exist from fixture
        assert checklist.git_configured  # Should be configured from fixture

        # 4. Get readiness result
        result = onboarding.validate_readiness(caps)
        assert result.agent_id == "integration-test"
        assert result.status in OnboardingStatus
        assert len(result.messages) > 0

        # 5. Get first PR guidance
        guidance = onboarding.get_first_pr_guidance("ST-INTEGRATION-001")
        assert guidance["story_id"] == "ST-INTEGRATION-001"
        assert len(guidance["steps"]) >= 5

    def test_capability_levels(self, temp_repo):
        """Test all capability levels."""
        onboarding = AgentOnboarding(agent_id="test", repo_root=str(temp_repo))

        # Novice
        novice_caps = AgentCapabilities(
            git_proficiency=2,
            testing_experience=2,
            ci_cd_familiarity=2,
            python_skill=3,
            documentation_skill=3,
        )
        assert novice_caps.level() == CapabilityLevel.NOVICE
        result = onboarding.validate_readiness(novice_caps)
        assert any("Git proficiency is low" in rec for rec in result.recommendations)

        # Expert
        expert_caps = AgentCapabilities(
            git_proficiency=9,
            testing_experience=9,
            ci_cd_familiarity=8,
            python_skill=9,
            documentation_skill=8,
        )
        assert expert_caps.level() == CapabilityLevel.EXPERT
        result = onboarding.validate_readiness(expert_caps)
        assert not any(
            "Git proficiency is low" in rec for rec in result.recommendations
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
