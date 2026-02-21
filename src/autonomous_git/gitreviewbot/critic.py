"""Critic role - compliance and workflow review."""

import os
import re
import json
import asyncio
from typing import List, Optional, Dict, Any, Set
from datetime import datetime

from .models import ReviewResult, Violation, Severity


class CriticReviewer:
    """Compliance Critic role for workflow and standards review."""

    # Forbidden patterns
    FORBIDDEN_PATTERNS = {
        "hardcoded_secret": re.compile(
            r'(password|secret|token|key)\s*=\s*["\'][^"\']+["\']',
            re.IGNORECASE,
        ),
        "debug_code": re.compile(
            r"(debugger|breakpoint|pdb\.set_trace|console\.log)",
            re.IGNORECASE,
        ),
        "todo_without_ticket": re.compile(
            r"TODO(?!.*ST-|CH-|FT-|REWARD-|REPO-|SAFETY-|BRANCH-|PAPER-|RECON-)",
            re.IGNORECASE,
        ),
    }

    # Required story ID patterns
    STORY_ID_PATTERNS = [
        re.compile(r"ST-\d+", re.IGNORECASE),
        re.compile(r"CH-\d+", re.IGNORECASE),
        re.compile(r"FT-\d+", re.IGNORECASE),
        re.compile(r"REWARD-\d+", re.IGNORECASE),
        re.compile(r"REPO-\d+", re.IGNORECASE),
        re.compile(r"SAFETY-\d+", re.IGNORECASE),
        re.compile(r"BRANCH-\d+", re.IGNORECASE),
        re.compile(r"PAPER-\d+", re.IGNORECASE),
        re.compile(r"RECON-\d+", re.IGNORECASE),
    ]

    def __init__(
        self,
        llm_client=None,
        prompt_path: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        self.llm_client = llm_client
        self.timeout_seconds = timeout_seconds
        self.prompt_path = prompt_path or self._default_prompt_path()
        self._prompt_template: Optional[str] = None

    def _default_prompt_path(self) -> str:
        """Get default path to prompt file."""
        module_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(module_dir, "prompts", "critic_review.txt")

    async def _load_prompt(self) -> str:
        """Load prompt template from file."""
        if self._prompt_template is None:
            try:
                with open(self.prompt_path, "r") as f:
                    self._prompt_template = f.read()
            except FileNotFoundError:
                self._prompt_template = self._default_prompt()
        return self._prompt_template

    def _default_prompt(self) -> str:
        """Default Critic prompt template."""
        return """You are a Compliance Critic reviewing PR adherence to standards.

PR: {pr_title}
Story ID: {story_id}
Files: {files}

Check for:
1. PR title contains valid story ID (ST-*, CH-*, FT-*, etc.)
2. No forbidden patterns (secrets, debug code, TODOs without tickets)
3. Documentation updated if needed (README, docs/, etc.)
4. Safety invariants preserved (no changes to protected files)
5. Workflow compliance (branch naming, commit messages)

Output JSON:
{{
  "violations": [
    {{
      "rule": "rule_name",
      "severity": "error|warning",
      "message": "Description",
      "file": "optional/file/path"
    }}
  ],
  "compliance_score": 92,
  "blockers": ["Blocking violations"]
}}

Guidelines:
- Use "error" for missing story ID, secrets, or safety violations
- Use "warning" for style issues or missing documentation
- Compliance score should be 0-100 based on standards adherence"""

    async def review(
        self,
        pr_title: str,
        story_id: Optional[str],
        diff: str,
        files: List[str],
    ) -> ReviewResult:
        """Perform Critic review of PR."""
        start_time = datetime.utcnow()

        violations: List[Violation] = []
        blockers: List[str] = []

        try:
            # Run static checks
            static_violations, static_blockers = self._run_static_checks(
                pr_title, story_id, diff, files
            )
            violations.extend(static_violations)
            blockers.extend(static_blockers)

            # Run LLM review if available
            if self.llm_client:
                llm_violations = await asyncio.wait_for(
                    self._llm_review(pr_title, story_id, diff, files),
                    timeout=self.timeout_seconds,
                )
                violations.extend(llm_violations)

            # Calculate compliance score
            compliance_score = self._calculate_compliance_score(violations)

            summary = self._generate_summary(violations, compliance_score)

        except asyncio.TimeoutError:
            violations.append(
                Violation(
                    rule="review_timeout",
                    severity=Severity.WARNING,
                    message="Critic review timed out - manual review required",
                )
            )
            compliance_score = 50.0
            summary = "Critic review timed out"
            blockers.append("Review timeout")
        except Exception as e:
            violations.append(
                Violation(
                    rule="review_error",
                    severity=Severity.WARNING,
                    message=f"Review error: {str(e)}",
                )
            )
            compliance_score = 0.0
            summary = f"Review error: {str(e)}"
            blockers.append(f"Review failed: {str(e)}")

        duration = (datetime.utcnow() - start_time).total_seconds() * 1000

        return ReviewResult(
            role="Critic",
            violations=violations,
            summary=summary,
            confidence=compliance_score,
            blockers=blockers,
            duration_ms=int(duration),
        )

    def _run_static_checks(
        self,
        pr_title: str,
        story_id: Optional[str],
        diff: str,
        files: List[str],
    ) -> tuple[List[Violation], List[str]]:
        """Run static compliance checks."""
        violations = []
        blockers = []

        # Check for story ID in PR title
        if not story_id:
            violations.append(
                Violation(
                    rule="missing_story_id",
                    severity=Severity.ERROR,
                    message="PR title missing valid story ID (ST-*, CH-*, FT-*, etc.)",
                )
            )
            blockers.append("Missing story ID")

        # Check for forbidden patterns in diff
        for pattern_name, pattern in self.FORBIDDEN_PATTERNS.items():
            matches = pattern.findall(diff)
            if matches:
                if pattern_name == "hardcoded_secret":
                    violations.append(
                        Violation(
                            rule="potential_secret",
                            severity=Severity.ERROR,
                            message=f"Potential hardcoded secret detected ({len(matches)} occurrence(s))",
                        )
                    )
                    blockers.append("Potential secrets in code")
                elif pattern_name == "debug_code":
                    violations.append(
                        Violation(
                            rule="debug_code",
                            severity=Severity.WARNING,
                            message=f"Debug code detected ({len(matches)} occurrence(s))",
                        )
                    )
                elif pattern_name == "todo_without_ticket":
                    violations.append(
                        Violation(
                            rule="todo_without_ticket",
                            severity=Severity.WARNING,
                            message=f"TODO without ticket reference ({len(matches)} occurrence(s))",
                        )
                    )

        # Check for protected file modifications
        protected_patterns = [
            r"\.woodpecker\.ya?ml$",
            r"docs/bmm-workflow-status\.yaml$",
            r"infrastructure/terraform/",
            r"AGENTS\.md$",
        ]
        for file in files:
            for pattern in protected_patterns:
                if re.search(pattern, file):
                    violations.append(
                        Violation(
                            rule="protected_file_modified",
                            severity=Severity.ERROR,
                            message=f"Modified protected file: {file}",
                            file=file,
                        )
                    )
                    blockers.append(f"Modified protected file: {file}")

        return violations, blockers

    async def _llm_review(
        self,
        pr_title: str,
        story_id: Optional[str],
        diff: str,
        files: List[str],
    ) -> List[Violation]:
        """Run LLM-based compliance review."""
        prompt_template = await self._load_prompt()

        prompt = prompt_template.format(
            pr_title=pr_title,
            story_id=story_id or "N/A",
            files=", ".join(files[:20]),  # Limit file list
        )

        response = await self._call_llm(prompt)
        return self._parse_llm_response(response)

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt."""
        if self.llm_client:
            return await self.llm_client.complete(prompt)
        return "{}"

    def _parse_llm_response(self, response: str) -> List[Violation]:
        """Parse LLM response into violations."""
        violations = []

        try:
            # Extract JSON
            json_match = self._extract_json(response)
            if json_match:
                data = json.loads(json_match)

                for v in data.get("violations", []):
                    violations.append(
                        Violation(
                            rule=v.get("rule", "unknown"),
                            severity=Severity(v.get("severity", "warning")),
                            message=v.get("message", ""),
                            file=v.get("file"),
                        )
                    )
        except Exception:
            pass

        return violations

    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from text."""
        import re

        pattern = r"```(?:json)?\s*([\s\S]*?)```"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

        pattern = r"(\{[\s\S]*\})"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

        return None

    def _calculate_compliance_score(self, violations: List[Violation]) -> float:
        """Calculate compliance score from violations."""
        base_score = 100.0

        for v in violations:
            if v.severity == Severity.ERROR:
                base_score -= 15.0
            elif v.severity == Severity.WARNING:
                base_score -= 5.0
            elif v.severity == Severity.INFO:
                base_score -= 1.0

        return max(0.0, min(100.0, base_score))

    def _generate_summary(self, violations: List[Violation], score: float) -> str:
        """Generate review summary."""
        error_count = sum(1 for v in violations if v.severity == Severity.ERROR)
        warning_count = sum(1 for v in violations if v.severity == Severity.WARNING)

        if error_count == 0 and warning_count == 0:
            return f"All compliance checks passed. Score: {score:.1f}%"

        parts = []
        if error_count > 0:
            parts.append(f"{error_count} error(s)")
        if warning_count > 0:
            parts.append(f"{warning_count} warning(s)")

        return f"Compliance review found {', '.join(parts)}. Score: {score:.1f}%"
