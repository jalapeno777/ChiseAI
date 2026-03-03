"""LLM integration module for reflection artifacts.

Provides LLM-powered insights for reflection analysis with graceful
degradation to deterministic approaches when LLM is unavailable.

This module follows the LLM structure conformance pattern:
- Uses only LLMProviderChain from src.llm (no direct provider imports)
- Implements proper error handling with fallback
- Includes telemetry/logging for all LLM calls
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.llm import LLMProviderChain

logger = logging.getLogger(__name__)


@dataclass
class LLMInsightResult:
    """Result from LLM insight generation."""

    success: bool
    insights: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    provider_used: str = "none"
    latency_ms: float = 0.0
    error_message: str | None = None
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "insights": self.insights,
            "summary": self.summary,
            "provider_used": self.provider_used,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
            "fallback_used": self.fallback_used,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }


@dataclass
class LLMCallTelemetry:
    """Telemetry data for LLM calls."""

    call_id: str
    function_name: str
    prompt_length: int
    response_length: int
    latency_ms: float
    provider_used: str
    success: bool
    error_category: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "call_id": self.call_id,
            "function_name": self.function_name,
            "prompt_length": self.prompt_length,
            "response_length": self.response_length,
            "latency_ms": self.latency_ms,
            "provider_used": self.provider_used,
            "success": self.success,
            "error_category": self.error_category,
            "timestamp": self.timestamp,
        }


class ReflectionLLMIntegration:
    """Integration layer between reflection system and LLM provider chain."""

    def __init__(self, enable_telemetry: bool = True):
        """Initialize the LLM integration.

        Args:
            enable_telemetry: Whether to collect telemetry on LLM calls
        """
        self._chain: LLMProviderChain | None = None
        self._enable_telemetry = enable_telemetry
        self._telemetry_log: list[LLMCallTelemetry] = []
        self._call_counter = 0

    def _get_chain(self) -> LLMProviderChain | None:
        """Lazy initialization of LLM provider chain.

        Returns:
            LLMProviderChain instance or None if import fails
        """
        if self._chain is None:
            try:
                from src.llm import LLMProviderChain

                self._chain = LLMProviderChain(enable_metrics=self._enable_telemetry)
                logger.info("LLMProviderChain initialized successfully")
            except ImportError as e:
                logger.warning(f"Failed to import LLMProviderChain: {e}")
                return None
            except Exception as e:
                logger.error(f"Failed to initialize LLMProviderChain: {e}")
                return None
        return self._chain

    def _log_telemetry(self, telemetry: LLMCallTelemetry) -> None:
        """Log telemetry data.

        Args:
            telemetry: Telemetry data to log
        """
        self._telemetry_log.append(telemetry)
        logger.debug(
            f"LLM call telemetry: {telemetry.function_name} "
            f"(provider={telemetry.provider_used}, "
            f"latency={telemetry.latency_ms:.1f}ms, "
            f"success={telemetry.success})"
        )

    def get_telemetry_summary(self) -> dict[str, Any]:
        """Get summary of all LLM call telemetry.

        Returns:
            Dictionary with telemetry summary
        """
        if not self._telemetry_log:
            return {"total_calls": 0, "success_rate": 0.0}

        total_calls = len(self._telemetry_log)
        successful_calls = sum(1 for t in self._telemetry_log if t.success)
        avg_latency = sum(t.latency_ms for t in self._telemetry_log) / total_calls

        # Provider usage breakdown
        provider_counts: dict[str, int] = {}
        for t in self._telemetry_log:
            provider_counts[t.provider_used] = (
                provider_counts.get(t.provider_used, 0) + 1
            )

        return {
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "success_rate": successful_calls / total_calls,
            "average_latency_ms": round(avg_latency, 2),
            "provider_usage": provider_counts,
            "calls": [t.to_dict() for t in self._telemetry_log[-10:]],  # Last 10 calls
        }

    async def _call_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        function_name: str = "unknown",
    ) -> LLMInsightResult:
        """Call LLM with telemetry and error handling.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            function_name: Name of the calling function for telemetry

        Returns:
            LLMInsightResult with response or error
        """
        self._call_counter += 1
        call_id = f"{function_name}-{self._call_counter}"

        chain = self._get_chain()
        if chain is None:
            telemetry = LLMCallTelemetry(
                call_id=call_id,
                function_name=function_name,
                prompt_length=len(prompt),
                response_length=0,
                latency_ms=0.0,
                provider_used="none",
                success=False,
                error_category="NOT_CONFIGURED",
            )
            self._log_telemetry(telemetry)
            return LLMInsightResult(
                success=False,
                error_message="LLM provider chain not available",
                fallback_used=True,
            )

        import time

        start_time = time.time()
        try:
            response = await chain.query(
                prompt=prompt,
                system_prompt=system_prompt,
            )
            latency_ms = (time.time() - start_time) * 1000

            telemetry = LLMCallTelemetry(
                call_id=call_id,
                function_name=function_name,
                prompt_length=len(prompt),
                response_length=len(response.content) if response.success else 0,
                latency_ms=latency_ms,
                provider_used=response.provider,
                success=response.success,
                error_category=response.error.category.name if response.error else None,
            )
            self._log_telemetry(telemetry)

            if response.success:
                return LLMInsightResult(
                    success=True,
                    summary=response.content,
                    provider_used=response.provider,
                    latency_ms=latency_ms,
                    fallback_used=False,
                )
            else:
                return LLMInsightResult(
                    success=False,
                    error_message=response.error.message
                    if response.error
                    else "Unknown error",
                    provider_used=response.provider,
                    latency_ms=latency_ms,
                    fallback_used=True,
                )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            telemetry = LLMCallTelemetry(
                call_id=call_id,
                function_name=function_name,
                prompt_length=len(prompt),
                response_length=0,
                latency_ms=latency_ms,
                provider_used="none",
                success=False,
                error_category="EXCEPTION",
            )
            self._log_telemetry(telemetry)

            logger.error(f"LLM call failed in {function_name}: {e}")
            return LLMInsightResult(
                success=False,
                error_message=str(e),
                fallback_used=True,
            )

    async def generate_llm_insights(
        self,
        trend_data: dict[str, Any],
        kpi_data: dict[str, Any],
    ) -> LLMInsightResult:
        """Generate LLM-powered insights from trend and KPI data.

        Args:
            trend_data: Trend analysis data
            kpi_data: KPI snapshot data

        Returns:
            LLMInsightResult with generated insights
        """
        system_prompt = """You are an expert software engineering analyst specializing in 
CI/CD metrics, code quality trends, and development workflow optimization. 
Provide concise, actionable insights based on the data provided.

Format your response as:
KEY_FINDINGS:
- [Finding 1]
- [Finding 2]

RECOMMENDATIONS:
- [Recommendation 1]
- [Recommendation 2]

RISK_ASSESSMENT: [Low/Medium/High] - [Brief explanation]"""

        prompt = f"""Analyze the following development metrics and provide insights:

TREND DATA:
{json.dumps(trend_data, indent=2, default=str)}

KPI DATA:
{json.dumps(kpi_data, indent=2, default=str)}

Based on this data:
1. Identify the most significant trends
2. Highlight potential risks or concerns
3. Suggest 2-3 specific, actionable improvements
4. Provide an overall risk assessment

Keep your response concise and focused on actionable insights."""

        result = await self._call_llm(
            prompt=prompt,
            system_prompt=system_prompt,
            function_name="generate_llm_insights",
        )

        if result.success:
            # Parse insights from the response
            result.insights = self._parse_insights(result.summary)

        return result

    async def summarize_weekly_reflection(
        self,
        artifact_data: dict[str, Any],
    ) -> LLMInsightResult:
        """Generate LLM-powered summary for weekly reflection.

        Args:
            artifact_data: Weekly reflection artifact data

        Returns:
            LLMInsightResult with generated summary
        """
        system_prompt = """You are a technical project manager summarizing weekly 
development team performance. Create an executive summary that highlights:
- Key achievements
- Areas of concern
- Action items for next week

Keep the tone professional and constructive."""

        prompt = f"""Generate an executive summary for this weekly reflection:

{json.dumps(artifact_data, indent=2, default=str)}

Provide:
1. A 2-3 sentence overview of the week
2. Key achievements (bullet points)
3. Areas needing attention (bullet points)
4. Top 3 priorities for next week

Format for easy reading by engineering leadership."""

        result = await self._call_llm(
            prompt=prompt,
            system_prompt=system_prompt,
            function_name="summarize_weekly_reflection",
        )

        return result

    async def analyze_bottleneck_root_cause(
        self,
        bottleneck_type: str,
        occurrences: list[dict[str, Any]],
    ) -> LLMInsightResult:
        """Analyze root cause of a specific bottleneck type.

        Args:
            bottleneck_type: Type of bottleneck (e.g., "ci_failures")
            occurrences: List of occurrence data

        Returns:
            LLMInsightResult with root cause analysis
        """
        system_prompt = """You are a root cause analysis expert. Analyze the provided 
bottleneck data to identify underlying causes and suggest preventive measures.

Format your response as:
ROOT_CAUSE: [Primary root cause]
CONTRIBUTING_FACTORS:
- [Factor 1]
- [Factor 2]

PREVENTIVE_MEASURES:
- [Measure 1]
- [Measure 2]"""

        prompt = f"""Analyze the root cause of this bottleneck:

BOTTLENECK TYPE: {bottleneck_type}

OCCURRENCES:
{json.dumps(occurrences, indent=2, default=str)}

Provide:
1. Primary root cause hypothesis
2. Contributing factors
3. Specific preventive measures
4. Estimated impact of implementing fixes"""

        result = await self._call_llm(
            prompt=prompt,
            system_prompt=system_prompt,
            function_name="analyze_bottleneck_root_cause",
        )

        if result.success:
            result.insights = {"root_cause_analysis": result.summary}

        return result

    def _parse_insights(self, content: str) -> dict[str, Any]:
        """Parse structured insights from LLM response.

        Args:
            content: Raw LLM response content

        Returns:
            Dictionary of parsed insights
        """
        insights: dict[str, Any] = {
            "raw_response": content,
            "key_findings": [],
            "recommendations": [],
            "risk_assessment": None,
        }

        lines = content.split("\n")
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect sections
            if line.upper().startswith("KEY_FINDINGS:"):
                current_section = "key_findings"
                continue
            elif line.upper().startswith("RECOMMENDATIONS:"):
                current_section = "recommendations"
                continue
            elif line.upper().startswith("RISK_ASSESSMENT:"):
                current_section = "risk_assessment"
                insights["risk_assessment"] = (
                    line.split(":", 1)[1].strip() if ":" in line else line
                )
                continue

            # Collect bullet points
            if line.startswith("-") or line.startswith("*"):
                item = line[1:].strip()
                if current_section == "key_findings":
                    insights["key_findings"].append(item)
                elif current_section == "recommendations":
                    insights["recommendations"].append(item)

        return insights


# Module-level functions for convenient access
_integration_instance: ReflectionLLMIntegration | None = None


def _get_integration() -> ReflectionLLMIntegration:
    """Get or create the singleton integration instance."""
    global _integration_instance
    if _integration_instance is None:
        _integration_instance = ReflectionLLMIntegration()
    return _integration_instance


def generate_llm_insights(
    trend_data: dict[str, Any],
    kpi_data: dict[str, Any],
) -> LLMInsightResult:
    """Generate LLM-powered insights from trend and KPI data.

    This is a synchronous wrapper around the async method.

    Args:
        trend_data: Trend analysis data
        kpi_data: KPI snapshot data

    Returns:
        LLMInsightResult with generated insights
    """
    integration = _get_integration()
    try:
        return asyncio.run(integration.generate_llm_insights(trend_data, kpi_data))
    except Exception as e:
        logger.error(f"Failed to generate LLM insights: {e}")
        return LLMInsightResult(
            success=False,
            error_message=str(e),
            fallback_used=True,
        )


def summarize_weekly_reflection(artifact_data: dict[str, Any]) -> str:
    """Generate LLM-powered summary for weekly reflection.

    This is a synchronous wrapper around the async method.

    Args:
        artifact_data: Weekly reflection artifact data

    Returns:
        Generated summary string (or empty string on failure)
    """
    integration = _get_integration()
    try:
        result = asyncio.run(integration.summarize_weekly_reflection(artifact_data))
        if result.success:
            return result.summary
        else:
            logger.warning(f"LLM summary generation failed: {result.error_message}")
            return ""
    except Exception as e:
        logger.error(f"Failed to generate weekly summary: {e}")
        return ""


def analyze_bottleneck_root_cause(
    bottleneck_type: str,
    occurrences: list[dict[str, Any]],
) -> str:
    """Analyze root cause of a specific bottleneck type.

    This is a synchronous wrapper around the async method.

    Args:
        bottleneck_type: Type of bottleneck
        occurrences: List of occurrence data

    Returns:
        Root cause analysis string (or empty string on failure)
    """
    integration = _get_integration()
    try:
        result = asyncio.run(
            integration.analyze_bottleneck_root_cause(bottleneck_type, occurrences)
        )
        if result.success:
            return result.summary
        else:
            logger.warning(f"Root cause analysis failed: {result.error_message}")
            return ""
    except Exception as e:
        logger.error(f"Failed to analyze bottleneck root cause: {e}")
        return ""


def get_llm_telemetry() -> dict[str, Any]:
    """Get telemetry summary for LLM calls.

    Returns:
        Dictionary with telemetry summary
    """
    integration = _get_integration()
    return integration.get_telemetry_summary()


def reset_llm_telemetry() -> None:
    """Reset the telemetry log."""
    global _integration_instance
    _integration_instance = None
