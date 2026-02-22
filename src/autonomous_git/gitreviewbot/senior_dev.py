"""SeniorDev role - technical code review."""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import Finding, ReviewResult, Severity


class SeniorDevReviewer:
    """Senior Developer role for technical code review."""

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
        return os.path.join(module_dir, "prompts", "senior_dev_review.txt")

    async def _load_prompt(self) -> str:
        """Load prompt template from file."""
        if self._prompt_template is None:
            try:
                with open(self.prompt_path, "r") as f:
                    self._prompt_template = f.read()
            except FileNotFoundError:
                # Use default prompt if file not found
                self._prompt_template = self._default_prompt()
        return self._prompt_template

    def _default_prompt(self) -> str:
        """Default SeniorDev prompt template."""
        return """You are a Senior Developer reviewing code changes.

PR: {pr_title}
Story ID: {story_id}
Files Changed: {file_count}

DIFF:
{diff}

Review the code for:
1. Technical correctness - does the code do what it claims?
2. Test coverage adequacy - are there sufficient tests?
3. Potential regressions - could this break existing functionality?
4. Code quality and best practices - follows Python/JS standards?
5. Performance implications - any obvious performance issues?

Output JSON:
{{
  "findings": [
    {{
      "file": "path/to/file.py",
      "line": 42,
      "severity": "error|warning|info",
      "message": "Description of issue",
      "suggestion": "Suggested fix"
    }}
  ],
  "summary": "Overall assessment of the code quality",
  "confidence": 85,
  "blockers": ["List of blocking issues, if any"]
}}

Guidelines:
- Use "error" severity for bugs, security issues, or breaking changes
- Use "warning" for code smells, missing tests, or style issues
- Use "info" for suggestions or minor improvements
- Confidence should be 0-100 based on code quality
- Blockers should list any issues that must be fixed before approval"""

    async def review(
        self,
        pr_title: str,
        story_id: Optional[str],
        diff: str,
        files: List[str],
    ) -> ReviewResult:
        """Perform SeniorDev review of PR."""
        start_time = datetime.utcnow()

        try:
            # Load prompt
            prompt_template = await self._load_prompt()

            # Build prompt
            prompt = prompt_template.format(
                pr_title=pr_title,
                story_id=story_id or "N/A",
                file_count=len(files),
                diff=diff[:10000],  # Limit diff size
                files=", ".join(files),
            )

            # Call LLM with timeout
            if self.llm_client:
                response = await asyncio.wait_for(
                    self._call_llm(prompt),
                    timeout=self.timeout_seconds,
                )
            else:
                # Mock response for testing
                response = self._mock_review(diff, files)

            # Parse response
            result = self._parse_response(response)

        except asyncio.TimeoutError:
            result = self._timeout_result()
        except Exception as e:
            result = self._error_result(str(e))

        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000

        return ReviewResult(
            role="SeniorDev",
            findings=result.get("findings", []),
            summary=result.get("summary", "Review completed"),
            confidence=result.get("confidence", 50.0),
            blockers=result.get("blockers", []),
            duration_ms=int(duration),
        )

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt."""
        # This would integrate with Z.ai GLM-5 or MiniMax 2.5
        # For now, return a mock response
        if self.llm_client:
            return await self.llm_client.complete(prompt)
        return self._mock_review(prompt, [])

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into structured data."""
        try:
            # Extract JSON from response
            json_match = self._extract_json(response)
            if json_match:
                data = json.loads(json_match)

                # Parse findings
                findings = []
                for f in data.get("findings", []):
                    findings.append(
                        Finding(
                            file=f.get("file", ""),
                            line=f.get("line"),
                            severity=Severity(f.get("severity", "info")),
                            message=f.get("message", ""),
                            suggestion=f.get("suggestion"),
                        )
                    )

                return {
                    "findings": findings,
                    "summary": data.get("summary", ""),
                    "confidence": float(data.get("confidence", 50.0)),
                    "blockers": data.get("blockers", []),
                }
        except Exception:
            pass

        # Fallback: return empty result
        return {
            "findings": [],
            "summary": "Could not parse review response",
            "confidence": 50.0,
            "blockers": [],
        }

    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from text."""
        # Look for JSON between triple backticks
        import re

        pattern = r"```(?:json)?\s*([\s\S]*?)```"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

        # Try to find JSON object directly
        pattern = r"(\{[\s\S]*\})"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

        return None

    def _mock_review(self, diff: str, files: List[str]) -> str:
        """Generate mock review for testing."""
        findings = []

        # Simple heuristics for mock review
        if "TODO" in diff.upper():
            findings.append(
                {
                    "file": files[0] if files else "unknown",
                    "line": 1,
                    "severity": "warning",
                    "message": "TODO found in code",
                    "suggestion": "Address TODO before merging or create a follow-up task",
                }
            )

        # Check for debug print statements (but allow in test files)
        has_print = "print(" in diff or 'print("' in diff or "print ('" in diff
        is_test_file = any(
            f.endswith(("_test.py", "test_.py", "tests.py")) for f in files
        )
        if has_print and not is_test_file:
            findings.append(
                {
                    "file": files[0] if files else "unknown",
                    "line": 1,
                    "severity": "warning",
                    "message": "Debug print statement found",
                    "suggestion": "Remove debug print statements or use proper logging",
                }
            )

        if len(diff) > 5000:
            findings.append(
                {
                    "file": files[0] if files else "unknown",
                    "severity": "info",
                    "message": "Large diff - consider breaking into smaller PRs",
                    "suggestion": "Smaller PRs are easier to review",
                }
            )

        confidence = 90.0 if not findings else 75.0

        return json.dumps(
            {
                "findings": findings,
                "summary": f"Reviewed {len(files)} files with {len(findings)} finding(s).",
                "confidence": confidence,
                "blockers": [],
            }
        )

    def _timeout_result(self) -> Dict[str, Any]:
        """Result for timeout."""
        return {
            "findings": [
                {
                    "file": "",
                    "severity": "warning",
                    "message": "Review timed out - manual review required",
                }
            ],
            "summary": "SeniorDev review timed out",
            "confidence": 50.0,
            "blockers": ["Review timeout"],
        }

    def _error_result(self, error: str) -> Dict[str, Any]:
        """Result for error."""
        return {
            "findings": [],
            "summary": f"Review error: {error}",
            "confidence": 0.0,
            "blockers": [f"Review failed: {error}"],
        }
