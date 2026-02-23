"""Gitea API client for GitReviewBot."""

import os
import re
from datetime import datetime
from typing import Any, cast

import aiohttp

from .models import Decision, DecisionType, PRDetails


class GiteaClient:
    """Client for interacting with Gitea API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ):
        self.base_url: str = base_url or os.getenv("GITEA_URL", "http://localhost:3000")
        self.token = token or os.getenv("GITEA_TOKEN", "")
        self.owner = owner or os.getenv("GITEA_OWNER", "chiseai")
        self.repo = repo or os.getenv("GITEA_REPO", "chiseai")
        self.bot_username = os.getenv("GITREVIEWBOT_USER", "GitReviewBot")

        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                "Authorization": f"token {self.token}",
                "Content-Type": "application/json",
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _api_url(self, endpoint: str) -> str:
        """Build API URL."""
        base = self.base_url.rstrip("/")
        return f"{base}/api/v1{endpoint}"

    async def get_pr(self, pr_number: int) -> PRDetails:
        """Get PR details from Gitea."""
        session = await self._get_session()
        url = self._api_url(f"/repos/{self.owner}/{self.repo}/pulls/{pr_number}")

        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

        # Get files changed
        files = await self.get_pr_files(pr_number)

        return PRDetails(
            number=data["number"],
            title=data["title"],
            body=data.get("body", ""),
            author=data["user"]["login"],
            branch=data["head"]["ref"],
            base_branch=data["base"]["ref"],
            state=data["state"],
            created_at=datetime.fromisoformat(
                data["created_at"].replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"].replace("Z", "+00:00")
            ),
            files_changed=[f["filename"] for f in files],
            labels=[label["name"] for label in data.get("labels", [])],
        )

    async def get_pr_files(self, pr_number: int) -> list[dict[str, Any]]:
        """Get list of files changed in PR."""
        session = await self._get_session()
        url = self._api_url(f"/repos/{self.owner}/{self.repo}/pulls/{pr_number}/files")

        files = []
        page = 1
        while True:
            async with session.get(
                url, params={"page": page, "limit": 100}
            ) as response:
                response.raise_for_status()
                page_data = await response.json()
                if not page_data:
                    break
                files.extend(page_data)
                page += 1

        return files

    async def get_pr_diff(self, pr_number: int) -> str:
        """Get PR diff content."""
        session = await self._get_session()
        url = self._api_url(f"/repos/{self.owner}/{self.repo}/pulls/{pr_number}.diff")

        async with session.get(url) as response:
            response.raise_for_status()
            return await response.text()

    async def post_review(
        self,
        pr_number: int,
        decision: Decision,
        commit_id: str | None = None,
    ) -> dict[str, Any]:
        """Post a review to the PR."""
        session = await self._get_session()
        url = self._api_url(
            f"/repos/{self.owner}/{self.repo}/pulls/{pr_number}/reviews"
        )

        # Build review body
        body = self._format_review_body(decision)

        # Map decision to Gitea review state
        state_map = {
            DecisionType.APPROVE: "APPROVE",
            DecisionType.COMMENT: "COMMENT",
            DecisionType.REQUEST_CHANGES: "REQUEST_CHANGES",
        }

        payload = {
            "body": body,
            "event": state_map[decision.decision],
        }

        if commit_id:
            payload["commit_id"] = commit_id

        # Add file-level comments
        comments = self._build_file_comments(decision)
        if comments:
            payload["comments"] = comments

        async with session.post(url, json=payload) as response:
            response.raise_for_status()
            return cast(dict[str, Any], await response.json())

    def _format_review_body(self, decision: Decision) -> str:
        """Format the review body markdown."""
        lines = [
            "## 🤖 GitReviewBot Analysis",
            "",
            f"**Decision:** {decision.decision.value}",
            f"**Confidence:** {decision.confidence:.1f}%",
            f"- SeniorDev: {decision.senior_dev_confidence:.1f}%",
            f"- Critic: {decision.critic_confidence:.1f}%",
            "",
            f"**Summary:** {decision.summary}",
            "",
        ]

        if decision.blockers:
            lines.extend(
                [
                    "### 🚫 Blockers",
                    "",
                ]
            )
            for blocker in decision.blockers:
                lines.append(f"- {blocker}")
            lines.append("")

        if decision.findings:
            lines.extend(
                [
                    "### 📋 Technical Findings",
                    "",
                ]
            )
            for finding in decision.findings[:10]:  # Limit to 10
                emoji = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(
                    finding.severity, "•"
                )
                lines.append(f"{emoji} **{finding.file}**")
                if finding.line:
                    lines.append(f"   Line {finding.line}: {finding.message}")
                else:
                    lines.append(f"   {finding.message}")
                if finding.suggestion:
                    lines.append(f"   💡 {finding.suggestion}")
                lines.append("")

        if decision.violations:
            lines.extend(
                [
                    "### ⚖️ Compliance Violations",
                    "",
                ]
            )
            for violation in decision.violations[:10]:  # Limit to 10
                emoji = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(
                    violation.severity, "•"
                )
                lines.append(f"{emoji} **{violation.rule}**: {violation.message}")
            lines.append("")

        if decision.auto_merge_eligible:
            lines.extend(
                [
                    "---",
                    "✅ **Auto-merge eligible** - This PR meets high-confidence criteria",
                    "",
                ]
            )

        lines.extend(
            [
                "---",
                "*Reviewed by GitReviewBot*",
                "👍 / 👎 to provide feedback on this review",
            ]
        )

        return "\n".join(lines)

    def _build_file_comments(self, decision: Decision) -> list[dict[str, Any]]:
        """Build file-level comments for the review."""
        comments = []

        # Add comments for findings with line numbers
        for finding in decision.findings:
            if finding.line and finding.severity in ("error", "warning"):
                comments.append(
                    {
                        "path": finding.file,
                        "position": finding.line,
                        "body": f"**{finding.severity.upper()}**: {finding.message}",
                    }
                )

        return comments

    async def update_labels(self, pr_number: int, labels: list[str]) -> None:
        """Update PR labels."""
        session = await self._get_session()
        url = self._api_url(
            f"/repos/{self.owner}/{self.repo}/issues/{pr_number}/labels"
        )

        async with session.put(url, json={"labels": labels}) as response:
            response.raise_for_status()

    async def add_labels(self, pr_number: int, labels: list[str]) -> None:
        """Add labels to PR."""
        session = await self._get_session()
        url = self._api_url(
            f"/repos/{self.owner}/{self.repo}/issues/{pr_number}/labels"
        )

        for label in labels:
            async with session.post(url, json={"labels": [label]}) as response:
                if response.status != 422:  # 422 = already exists
                    response.raise_for_status()

    async def remove_label(self, pr_number: int, label: str) -> None:
        """Remove a label from PR."""
        session = await self._get_session()
        url = self._api_url(
            f"/repos/{self.owner}/{self.repo}/issues/{pr_number}/labels/{label}"
        )

        async with session.delete(url) as response:
            if response.status != 404:  # 404 = label didn't exist
                response.raise_for_status()

    async def get_pr_comments(self, pr_number: int) -> list[dict[str, Any]]:
        """Get PR comments."""
        session = await self._get_session()
        url = self._api_url(
            f"/repos/{self.owner}/{self.repo}/issues/{pr_number}/comments"
        )

        async with session.get(url) as response:
            response.raise_for_status()
            return cast(list[dict[str, Any]], await response.json())

    async def post_comment(self, pr_number: int, body: str) -> dict[str, Any]:
        """Post a comment to the PR."""
        session = await self._get_session()
        url = self._api_url(
            f"/repos/{self.owner}/{self.repo}/issues/{pr_number}/comments"
        )

        async with session.post(url, json={"body": body}) as response:
            response.raise_for_status()
            return cast(dict[str, Any], await response.json())

    async def merge_pr(
        self,
        pr_number: int,
        merge_method: str = "merge",
        delete_branch: bool = False,
    ) -> dict[str, Any]:
        """Merge a PR."""
        session = await self._get_session()
        url = self._api_url(f"/repos/{self.owner}/{self.repo}/pulls/{pr_number}/merge")

        payload = {
            "Do": merge_method,
            "delete_branch_after_merge": delete_branch,
        }

        async with session.post(url, json=payload) as response:
            response.raise_for_status()
            return cast(dict[str, Any], await response.json())

    async def get_check_runs(self, pr_number: int) -> list[dict[str, Any]]:
        """Get CI check runs for PR."""
        # First get the PR to get the head SHA
        pr = await self.get_pr(pr_number)

        session = await self._get_session()
        url = self._api_url(
            f"/repos/{self.owner}/{self.repo}/commits/{pr.branch}/status"
        )

        async with session.get(url) as response:
            if response.status == 404:
                return []
            response.raise_for_status()
            data = cast(dict[str, Any], await response.json())
            return cast(list[dict[str, Any]], data.get("statuses", []))

    def extract_story_id(self, pr_title: str) -> str | None:
        """Extract story ID from PR title."""
        patterns = [
            r"(BRANCH-\d+)",
            r"(PAPER-\d+)",
            r"(RECON-\d+)",
            r"(REWARD-\d+)",
            r"(SAFETY-\d+)",
            r"(REPO-\d+)",
            r"(ST-\d+)",
            r"(CH-\d+)",
            r"(FT-\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, pr_title, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return None
