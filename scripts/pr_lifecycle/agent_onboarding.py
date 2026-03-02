#!/usr/bin/env python3
"""Agent Onboarding - Helper for AI agents to onboard to the PR pipeline.

This module provides:
- Agent registration and capability assessment
- Onboarding checklist validation
- First PR guidance
- Scope reservation helpers

Usage:
    from scripts.pr_lifecycle.agent_onboarding import AgentOnboarding

    # Create onboarding helper
    onboarding = AgentOnboarding(agent_id="senior-dev")

    # Validate onboarding readiness
    result = onboarding.validate_readiness()

    # Get first PR guidance
    guidance = onboarding.get_first_pr_guidance(story_id="ST-001")
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "src" if __file__ else ".")
)
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)


class OnboardingStatus(Enum):
    """Status of agent onboarding."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    CHECKLIST_PENDING = "checklist_pending"
    READY = "ready"
    COMPLETED = "completed"


class CapabilityLevel(Enum):
    """Capability level for an agent."""

    NOVICE = "novice"  # First-time agent
    INTERMEDIATE = "intermediate"  # Some experience
    EXPERT = "expert"  # Experienced with PR pipeline


@dataclass
class AgentCapabilities:
    """Capabilities assessment for an agent."""

    git_proficiency: int = 0  # 0-10
    testing_experience: int = 0  # 0-10
    ci_cd_familiarity: int = 0  # 0-10
    python_skill: int = 0  # 0-10
    documentation_skill: int = 0  # 0-10

    def overall_score(self) -> float:
        """Calculate overall capability score."""
        return (
            sum(
                [
                    self.git_proficiency,
                    self.testing_experience,
                    self.ci_cd_familiarity,
                    self.python_skill,
                    self.documentation_skill,
                ]
            )
            / 5.0
        )

    def level(self) -> CapabilityLevel:
        """Determine capability level based on score."""
        score = self.overall_score()
        if score >= 7.5:
            return CapabilityLevel.EXPERT
        elif score >= 4.0:
            return CapabilityLevel.INTERMEDIATE
        return CapabilityLevel.NOVICE


@dataclass
class OnboardingChecklist:
    """Checklist for agent onboarding."""

    # Required reading
    read_agents_md: bool = False
    read_git_workflow: bool = False
    read_pr_paths: bool = False
    read_best_practices: bool = False

    # Setup verification
    git_configured: bool = False
    redis_accessible: bool = False
    test_environment_working: bool = False

    # First steps
    completed_first_session: bool = False
    validated_tooling: bool = False
    understood_scope_ownership: bool = False

    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        items = [
            self.read_agents_md,
            self.read_git_workflow,
            self.read_pr_paths,
            self.read_best_practices,
            self.git_configured,
            self.redis_accessible,
            self.test_environment_working,
            self.completed_first_session,
            self.validated_tooling,
            self.understood_scope_ownership,
        ]
        return (sum(items) / len(items)) * 100

    def is_complete(self) -> bool:
        """Check if all items are complete."""
        return self.completion_percentage() == 100

    def missing_items(self) -> list[str]:
        """Get list of missing checklist items."""
        missing = []
        if not self.read_agents_md:
            missing.append("read_agents_md: Read AGENTS.md")
        if not self.read_git_workflow:
            missing.append("read_git_workflow: Read git workflow skill")
        if not self.read_pr_paths:
            missing.append("read_pr_paths: Read PR path documentation")
        if not self.read_best_practices:
            missing.append("read_best_practices: Read best practices")
        if not self.git_configured:
            missing.append("git_configured: Verify git configuration")
        if not self.redis_accessible:
            missing.append("redis_accessible: Verify Redis connectivity")
        if not self.test_environment_working:
            missing.append("test_environment_working: Verify test environment")
        if not self.completed_first_session:
            missing.append("completed_first_session: Complete first swarm session")
        if not self.validated_tooling:
            missing.append("validated_tooling: Validate linting and testing tools")
        if not self.understood_scope_ownership:
            missing.append("understood_scope_ownership: Understand scope ownership")
        return missing


@dataclass
class OnboardingResult:
    """Result of onboarding validation."""

    agent_id: str
    status: OnboardingStatus
    capabilities: AgentCapabilities
    checklist: OnboardingChecklist
    messages: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "capabilities": {
                "git_proficiency": self.capabilities.git_proficiency,
                "testing_experience": self.capabilities.testing_experience,
                "ci_cd_familiarity": self.capabilities.ci_cd_familiarity,
                "python_skill": self.capabilities.python_skill,
                "documentation_skill": self.capabilities.documentation_skill,
                "overall_score": self.capabilities.overall_score(),
                "level": self.capabilities.level().value,
            },
            "checklist": {
                "completion_percentage": self.checklist.completion_percentage(),
                "is_complete": self.checklist.is_complete(),
                "missing_items": self.checklist.missing_items(),
            },
            "messages": self.messages,
            "recommendations": self.recommendations,
        }


class AgentOnboarding:
    """Helper for agent onboarding to the PR pipeline."""

    # Required reading files
    REQUIRED_READING = [
        "AGENTS.md",
        ".opencode/skills/chiseai-git-workflow/SKILL.md",
        ".opencode/skills/chiseai-parallel-safety/SKILL.md",
        ".opencode/skills/chiseai-memory-ops/SKILL.md",
        ".opencode/command/chise-iterloop-start.md",
        ".opencode/command/chise-precommit-gates.md",
    ]

    # PR path documentation
    PR_PATH_DOCS = [
        "docs/guides/pr-pipeline-quickstart.md",
        "docs/guides/pr-pipeline-best-practices.md",
        "docs/guides/pr-pipeline-troubleshooting.md",
    ]

    def __init__(self, agent_id: str, repo_root: str | None = None):
        """Initialize onboarding helper.

        Args:
            agent_id: Unique identifier for the agent
            repo_root: Path to repository root (auto-detected if None)
        """
        self.agent_id = agent_id
        self.repo_root = Path(repo_root) if repo_root else self._find_repo_root()

    def _find_repo_root(self) -> Path:
        """Find repository root from current location."""
        try:
            result = subprocess.run(  # nosec B607
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            return Path(result.stdout.strip())
        except subprocess.CalledProcessError:
            # Fallback to current directory
            return Path.cwd()

    def _check_file_exists(self, relative_path: str) -> bool:
        """Check if a file exists in the repo."""
        return (self.repo_root / relative_path).exists()

    def _check_git_configured(self) -> bool:
        """Check if git is configured."""
        try:
            subprocess.run(  # nosec B607
                ["git", "config", "user.name"],
                capture_output=True,
                check=True,
            )
            subprocess.run(  # nosec B607
                ["git", "config", "user.email"],
                capture_output=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def _check_redis_accessible(self) -> bool:
        """Check if Redis is accessible."""
        try:
            # Try to ping Redis using redis-cli
            import subprocess

            result = subprocess.run(  # nosec B607
                ["redis-cli", "-h", "host.docker.internal", "-p", "6380", "PING"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "PONG" in result.stdout
        except Exception:
            return False

    def _check_test_environment(self) -> bool:
        """Check if test environment is working."""
        try:
            # Check if pytest is available
            result = subprocess.run(  # nosec B607
                ["python3", "-m", "pytest", "--version"],
                capture_output=True,
                cwd=self.repo_root,
            )
            if result.returncode != 0:
                return False

            # Check if ruff is available
            result = subprocess.run(  # nosec B607
                ["python3", "-m", "ruff", "--version"],
                capture_output=True,
                cwd=self.repo_root,
            )
            return result.returncode == 0
        except Exception:
            return False

    def assess_capabilities(
        self,
        git_proficiency: int | None = None,
        testing_experience: int | None = None,
        ci_cd_familiarity: int | None = None,
        python_skill: int | None = None,
        documentation_skill: int | None = None,
    ) -> AgentCapabilities:
        """Assess agent capabilities.

        If any parameter is None, it will be auto-assessed based on environment.

        Args:
            git_proficiency: Git proficiency (0-10)
            testing_experience: Testing experience (0-10)
            ci_cd_familiarity: CI/CD familiarity (0-10)
            python_skill: Python skill (0-10)
            documentation_skill: Documentation skill (0-10)

        Returns:
            AgentCapabilities object
        """
        capabilities = AgentCapabilities()

        # Auto-assess git proficiency
        if git_proficiency is None:
            if self._check_git_configured():
                # Check for advanced git features
                try:
                    subprocess.run(  # nosec B607
                        ["git", "worktree", "list"],
                        capture_output=True,
                        check=True,
                    )
                    capabilities.git_proficiency = 8
                except subprocess.CalledProcessError:
                    capabilities.git_proficiency = 5
            else:
                capabilities.git_proficiency = 2
        else:
            capabilities.git_proficiency = git_proficiency

        # Auto-assess testing experience
        if testing_experience is None:
            if self._check_test_environment():
                capabilities.testing_experience = 7
            else:
                capabilities.testing_experience = 3
        else:
            capabilities.testing_experience = testing_experience

        # Auto-assess CI/CD familiarity
        if ci_cd_familiarity is None:
            # Check for CI config knowledge
            if (self.repo_root / ".woodpecker.yml").exists():
                capabilities.ci_cd_familiarity = 6
            else:
                capabilities.ci_cd_familiarity = 4
        else:
            capabilities.ci_cd_familiarity = ci_cd_familiarity

        # Auto-assess Python skill
        if python_skill is None:
            # Check Python version and available tools
            try:
                subprocess.run(  # nosec B607
                    ["python3", "--version"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                capabilities.python_skill = 7
            except subprocess.CalledProcessError:
                capabilities.python_skill = 4
        else:
            capabilities.python_skill = python_skill

        # Auto-assess documentation skill
        if documentation_skill is None:
            # Check for documentation tools
            if (self.repo_root / "docs").exists():
                capabilities.documentation_skill = 6
            else:
                capabilities.documentation_skill = 4
        else:
            capabilities.documentation_skill = documentation_skill

        return capabilities

    def validate_checklist(self) -> OnboardingChecklist:
        """Validate onboarding checklist.

        Returns:
            OnboardingChecklist with current status
        """
        checklist = OnboardingChecklist()

        # Check required reading
        checklist.read_agents_md = self._check_file_exists("AGENTS.md")
        checklist.read_git_workflow = self._check_file_exists(
            ".opencode/skills/chiseai-git-workflow/SKILL.md"
        )
        checklist.read_pr_paths = self._check_file_exists(
            "docs/guides/pr-pipeline-quickstart.md"
        )
        checklist.read_best_practices = self._check_file_exists(
            "docs/guides/pr-pipeline-best-practices.md"
        )

        # Check setup
        checklist.git_configured = self._check_git_configured()
        checklist.redis_accessible = self._check_redis_accessible()
        checklist.test_environment_working = self._check_test_environment()

        # Check first steps (these would be set externally)
        # For now, assume they need to be done
        checklist.completed_first_session = False
        checklist.validated_tooling = checklist.test_environment_working
        checklist.understood_scope_ownership = False

        return checklist

    def validate_readiness(
        self,
        capabilities: AgentCapabilities | None = None,
    ) -> OnboardingResult:
        """Validate agent readiness for PR pipeline.

        Args:
            capabilities: Optional pre-assessed capabilities

        Returns:
            OnboardingResult with status and recommendations
        """
        if capabilities is None:
            capabilities = self.assess_capabilities()

        checklist = self.validate_checklist()
        messages = []
        recommendations = []

        # Determine status
        if checklist.is_complete():
            status = OnboardingStatus.READY
            messages.append("✓ Onboarding complete! Agent is ready for PR pipeline.")
        elif checklist.completion_percentage() >= 50:
            status = OnboardingStatus.CHECKLIST_PENDING
            messages.append(
                f"⚠ Onboarding {checklist.completion_percentage():.0f}% complete. "
                "Some items pending."
            )
        elif checklist.completion_percentage() > 0:
            status = OnboardingStatus.IN_PROGRESS
            messages.append(
                f"⏳ Onboarding in progress ({checklist.completion_percentage():.0f}%)."
            )
        else:
            status = OnboardingStatus.NOT_STARTED
            messages.append("📋 Onboarding not started. Please complete checklist.")

        # Generate recommendations based on missing items
        missing = checklist.missing_items()
        if missing:
            recommendations.append("Complete these items to finish onboarding:")
            for item in missing[:5]:  # Show first 5
                recommendations.append(f"  - {item}")
            if len(missing) > 5:
                recommendations.append(f"  ... and {len(missing) - 5} more")

        # Capability-based recommendations
        if capabilities.git_proficiency < 5:
            recommendations.append(
                "💡 Git proficiency is low. Review git workflow skill before starting."
            )
        if capabilities.testing_experience < 5:
            recommendations.append(
                "💡 Testing experience is low. Start with simple test files first."
            )
        if capabilities.ci_cd_familiarity < 5:
            recommendations.append(
                "💡 CI/CD familiarity is low. Review .woodpecker.yml configuration."
            )

        return OnboardingResult(
            agent_id=self.agent_id,
            status=status,
            capabilities=capabilities,
            checklist=checklist,
            messages=messages,
            recommendations=recommendations,
        )

    def get_first_pr_guidance(self, story_id: str) -> dict[str, Any]:
        """Get guidance for first PR.

        Args:
            story_id: The story ID for the first PR

        Returns:
            Dictionary with guidance information
        """
        return {
            "story_id": story_id,
            "pr_path": "SAFE",  # First PR should use SAFE path
            "steps": [
                {
                    "step": 1,
                    "action": "Start swarm session",
                    "command": f"python3 scripts/swarm/session.py start --story-id={story_id} --agent={self.agent_id} --branch=feature/{story_id}-first-pr",
                },
                {
                    "step": 2,
                    "action": "Claim scope ownership",
                    "command": f"python3 .opencode/command/chise-claim-ownership.md --story-id={story_id} --scopes='src/example/'",
                },
                {
                    "step": 3,
                    "action": "Make minimal changes",
                    "details": "Start with documentation or simple fixes",
                },
                {
                    "step": 4,
                    "action": "Run pre-commit gates",
                    "command": "python3 .opencode/command/chise-precommit-gates.md",
                },
                {
                    "step": 5,
                    "action": "Handoff to Jarvis",
                    "details": "Report completion, do NOT open PR yourself",
                },
            ],
            "tips": [
                "Start with a SAFE path PR (documentation or simple fixes)",
                "Keep changes small (<100 lines)",
                "Focus on learning the workflow, not complex features",
                "Ask for help if stuck - don't struggle alone",
                "Document what you learn for future agents",
            ],
            "common_mistakes": [
                "Trying to do too much in first PR",
                "Not running pre-commit gates before handoff",
                "Opening PR directly instead of handing off to Jarvis",
                "Not claiming scope ownership before editing",
                "Working on main branch instead of feature branch",
            ],
        }

    def get_required_reading(self) -> list[dict[str, str]]:
        """Get list of required reading materials.

        Returns:
            List of reading materials with paths and descriptions
        """
        return [
            {
                "path": "AGENTS.md",
                "description": "Essential reading for all agents - Git safety, Docker connectivity, and workflow basics",
                "priority": "CRITICAL",
                "estimated_time": "10 minutes",
            },
            {
                "path": ".opencode/skills/chiseai-git-workflow/SKILL.md",
                "description": "Git workflow skill - branching, PR workflow, merge authority",
                "priority": "CRITICAL",
                "estimated_time": "15 minutes",
            },
            {
                "path": ".opencode/skills/chiseai-parallel-safety/SKILL.md",
                "description": "Parallel safety - scope ownership, conflict prevention",
                "priority": "HIGH",
                "estimated_time": "10 minutes",
            },
            {
                "path": ".opencode/skills/chiseai-memory-ops/SKILL.md",
                "description": "Memory operations - Redis and Qdrant usage patterns",
                "priority": "HIGH",
                "estimated_time": "10 minutes",
            },
            {
                "path": ".opencode/command/chise-iterloop-start.md",
                "description": "Iteration start command reference",
                "priority": "MEDIUM",
                "estimated_time": "5 minutes",
            },
            {
                "path": ".opencode/command/chise-precommit-gates.md",
                "description": "Pre-commit validation gates",
                "priority": "MEDIUM",
                "estimated_time": "5 minutes",
            },
        ]


def main():
    """CLI entry point for agent onboarding."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Agent Onboarding - Validate readiness for PR pipeline"
    )
    parser.add_argument(
        "--agent-id",
        default=os.getenv("AGENT_ID", "unknown"),
        help="Agent identifier",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate onboarding readiness",
    )
    parser.add_argument(
        "--first-pr",
        metavar="STORY_ID",
        help="Get guidance for first PR with given story ID",
    )
    parser.add_argument(
        "--reading-list",
        action="store_true",
        help="Show required reading list",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    onboarding = AgentOnboarding(agent_id=args.agent_id)

    if args.reading_list:
        reading = onboarding.get_required_reading()
        if args.json:
            print(json.dumps(reading, indent=2))
        else:
            print("\n📚 Required Reading List\n")
            for item in reading:
                status = "✓" if onboarding._check_file_exists(item["path"]) else "○"
                print(f"{status} [{item['priority']}] {item['path']}")
                print(f"   {item['description']}")
                print(f"   Estimated time: {item['estimated_time']}\n")

    elif args.first_pr:
        guidance = onboarding.get_first_pr_guidance(args.first_pr)
        if args.json:
            print(json.dumps(guidance, indent=2))
        else:
            print(f"\n🎯 First PR Guidance for {args.first_pr}\n")
            print(f"Recommended Path: {guidance['pr_path']}\n")
            print("Steps:")
            for step in guidance["steps"]:
                print(f"  {step['step']}. {step['action']}")
                if "command" in step:
                    print(f"     Command: {step['command']}")
                if "details" in step:
                    print(f"     {step['details']}")
            print("\nTips:")
            for tip in guidance["tips"]:
                print(f"  • {tip}")
            print("\nCommon Mistakes to Avoid:")
            for mistake in guidance["common_mistakes"]:
                print(f"  ✗ {mistake}")

    elif args.validate:
        result = onboarding.validate_readiness()
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"\n🤖 Agent Onboarding Status: {result.agent_id}\n")
            for msg in result.messages:
                print(msg)
            print()
            print(f"Capability Level: {result.capabilities.level().value.upper()}")
            print(f"Overall Score: {result.capabilities.overall_score():.1f}/10")
            print()
            if result.recommendations:
                print("Recommendations:")
                for rec in result.recommendations:
                    print(f"  {rec}")
            print()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
