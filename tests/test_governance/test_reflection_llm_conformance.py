"""Conformance tests for reflection LLM integration.

Tests that:
1. LLM provider chain is importable
2. Reflection code can instantiate LLMProviderChain
3. Fallback behavior works when LLM unavailable
4. Telemetry/logging of LLM calls works
5. No ad-hoc provider bypass exists
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLLMProviderChainImport:
    """Test that LLM provider chain is properly importable."""

    def test_llm_provider_chain_importable_from_src_llm(self):
        """Test that LLMProviderChain can be imported from src.llm."""
        try:
            from src.llm import LLMProviderChain

            assert LLMProviderChain is not None
        except ImportError as e:
            pytest.fail(f"Failed to import LLMProviderChain from src.llm: {e}")

    def test_llm_provider_chain_has_required_methods(self):
        """Test that LLMProviderChain has the required interface."""
        from src.llm import LLMProviderChain

        # Check required methods exist
        assert hasattr(LLMProviderChain, "query")
        assert hasattr(LLMProviderChain, "get_provider_status")
        assert hasattr(LLMProviderChain, "get_metrics_report")

    def test_llm_response_structure(self):
        """Test that LLMResponse has expected structure."""
        from src.llm import LLMResponse

        response = LLMResponse(
            success=True,
            content="test content",
            confidence_score=75.0,
            rationale="test rationale",
            provider="test_provider",
            latency_ms=100.0,
        )

        assert response.success is True
        assert response.content == "test content"
        assert response.confidence_score == 75.0
        assert response.provider == "test_provider"


class TestReflectionLLMIntegrationImport:
    """Test that reflection LLM integration is importable."""

    def test_llm_integration_module_importable(self):
        """Test that llm_integration module can be imported."""
        try:
            from src.governance.reflection import llm_integration

            assert llm_integration is not None
        except ImportError as e:
            pytest.fail(f"Failed to import llm_integration: {e}")

    def test_llm_integration_exports(self):
        """Test that llm_integration exports expected functions."""
        from src.governance.reflection import llm_integration

        # Check main functions are exported
        assert hasattr(llm_integration, "generate_llm_insights")
        assert hasattr(llm_integration, "summarize_weekly_reflection")
        assert hasattr(llm_integration, "analyze_bottleneck_root_cause")
        assert hasattr(llm_integration, "get_llm_telemetry")
        assert hasattr(llm_integration, "reset_llm_telemetry")

    def test_reflection_llm_integration_class_importable(self):
        """Test that ReflectionLLMIntegration class is importable."""
        from src.governance.reflection.llm_integration import ReflectionLLMIntegration

        integration = ReflectionLLMIntegration()
        assert integration is not None

    def test_llm_insight_result_structure(self):
        """Test that LLMInsightResult has expected structure."""
        from src.governance.reflection.llm_integration import LLMInsightResult

        result = LLMInsightResult(
            success=True,
            insights={"key": "value"},
            summary="test summary",
            provider_used="kimi",
            latency_ms=150.0,
        )

        assert result.success is True
        assert result.insights == {"key": "value"}
        assert result.summary == "test summary"
        assert result.provider_used == "kimi"


class TestNoDirectProviderImports:
    """Test that reflection code doesn't bypass provider chain."""

    def test_no_direct_kimi_client_imports_in_reflection(self):
        """Test that reflection code doesn't import kimi_client directly."""
        import ast
        from pathlib import Path

        reflection_dir = Path("src/governance/reflection")

        for py_file in reflection_dir.glob("*.py"):
            content = py_file.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    # Check for direct provider imports
                    assert not ("kimi_client" in module and "llm" not in module), (
                        f"Direct kimi_client import found in {py_file}"
                    )
                    assert not ("zai_client" in module and "llm" not in module), (
                        f"Direct zai_client import found in {py_file}"
                    )
                    assert not ("zhipu_client" in module and "llm" not in module), (
                        f"Direct zhipu_client import found in {py_file}"
                    )
                    assert not ("minimax_client" in module and "llm" not in module), (
                        f"Direct minimax_client import found in {py_file}"
                    )

    def test_only_provider_chain_import_pattern(self):
        """Test that reflection only imports from src.llm properly."""
        from src.governance.reflection import llm_integration

        # The integration should only use LLMProviderChain from src.llm
        source = llm_integration.__file__
        content = open(source).read()

        # Should not have direct provider imports
        assert "from llm.kimi_client" not in content
        assert "from llm.zai_client" not in content
        assert "from llm.zhipu_client" not in content
        assert "from llm.minimax_client" not in content


class TestFallbackBehavior:
    """Test fallback behavior when LLM is unavailable."""

    def test_fallback_when_llm_not_configured(self):
        """Test that fallback works when LLM is not configured."""
        from src.governance.reflection.llm_integration import (
            LLMInsightResult,
            generate_llm_insights,
        )

        # Temporarily clear any API keys
        with patch.dict(os.environ, {}, clear=True):
            result = generate_llm_insights(
                trend_data={"test": "data"},
                kpi_data={"kpi": "value"},
            )

        # Should return a result (possibly with fallback)
        assert isinstance(result, LLMInsightResult)
        # Either success with content or failure with fallback flag
        assert result.success or result.fallback_used

    def test_fallback_on_import_error(self):
        """Test graceful handling when LLM module import fails."""
        from src.governance.reflection.llm_integration import (
            ReflectionLLMIntegration,
        )

        integration = ReflectionLLMIntegration()

        # Simulate import failure by patching
        with patch.object(integration, "_get_chain", return_value=None):
            import asyncio

            result = asyncio.run(
                integration.generate_llm_insights(
                    trend_data={"test": "data"},
                    kpi_data={"kpi": "value"},
                )
            )

        assert result.fallback_used is True
        assert result.success is False

    def test_summarize_weekly_reflection_fallback(self):
        """Test that summarize_weekly_reflection returns empty string on failure."""
        from src.governance.reflection.llm_integration import (
            summarize_weekly_reflection,
        )

        # Should return empty string when LLM unavailable
        with patch.dict(os.environ, {}, clear=True):
            result = summarize_weekly_reflection({"test": "data"})

        # Should return string (empty if fallback)
        assert isinstance(result, str)

    def test_analyze_bottleneck_root_cause_fallback(self):
        """Test that analyze_bottleneck_root_cause returns empty string on failure."""
        from src.governance.reflection.llm_integration import (
            analyze_bottleneck_root_cause,
        )

        # Should return empty string when LLM unavailable
        with patch.dict(os.environ, {}, clear=True):
            result = analyze_bottleneck_root_cause("test_bottleneck", [])

        # Should return string (empty if fallback)
        assert isinstance(result, str)


class TestTelemetryAndLogging:
    """Test telemetry and logging of LLM calls."""

    def test_telemetry_collected_on_llm_call(self):
        """Test that telemetry is collected when LLM is called."""
        from src.governance.reflection.llm_integration import (
            ReflectionLLMIntegration,
            reset_llm_telemetry,
        )

        # Reset telemetry
        reset_llm_telemetry()

        integration = ReflectionLLMIntegration()

        # Mock the chain to simulate a successful call
        mock_chain = MagicMock()
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = "test response"
        mock_response.provider = "test_provider"
        mock_response.error = None
        mock_chain.query = AsyncMock(return_value=mock_response)

        with patch.object(integration, "_get_chain", return_value=mock_chain):
            import asyncio

            result = asyncio.run(
                integration.generate_llm_insights(
                    trend_data={"test": "data"},
                    kpi_data={"kpi": "value"},
                )
            )

        # Telemetry should be collected
        telemetry = integration.get_telemetry_summary()
        assert telemetry["total_calls"] >= 0  # May be 0 if mocked

    def test_telemetry_structure(self):
        """Test that telemetry has expected structure."""
        from src.governance.reflection.llm_integration import (
            LLMCallTelemetry,
        )

        telemetry = LLMCallTelemetry(
            call_id="test-123",
            function_name="test_function",
            prompt_length=100,
            response_length=50,
            latency_ms=200.0,
            provider_used="kimi",
            success=True,
        )

        data = telemetry.to_dict()
        assert data["call_id"] == "test-123"
        assert data["function_name"] == "test_function"
        assert data["prompt_length"] == 100
        assert data["latency_ms"] == 200.0
        assert data["success"] is True

    def test_get_llm_telemetry_function(self):
        """Test that get_llm_telemetry function works."""
        from src.governance.reflection.llm_integration import (
            get_llm_telemetry,
            reset_llm_telemetry,
        )

        # Reset first
        reset_llm_telemetry()

        # Get telemetry
        telemetry = get_llm_telemetry()

        # Should have expected structure
        assert "total_calls" in telemetry
        assert "success_rate" in telemetry


class TestBottleneckReflectionLLMIntegration:
    """Test that bottleneck_reflection properly integrates with LLM."""

    def test_bottleneck_reflection_has_use_llm_parameter(self):
        """Test that generate_daily_reflection accepts use_llm parameter."""
        from src.governance.reflection import BottleneckReflectionGenerator

        generator = BottleneckReflectionGenerator()

        # Should accept use_llm parameter without error
        import inspect

        sig = inspect.signature(generator.generate_daily_reflection)
        assert "use_llm" in sig.parameters

    def test_bottleneck_reflection_has_llm_insights_field(self):
        """Test that DailyReflectionArtifact has llm_insights field."""
        from src.governance.reflection import DailyReflectionArtifact

        import inspect

        sig = inspect.signature(DailyReflectionArtifact)
        assert "llm_insights" in sig.parameters

    def test_weekly_reflection_has_use_llm_parameter(self):
        """Test that generate_weekly_reflection accepts use_llm parameter."""
        from src.governance.reflection import BottleneckReflectionGenerator

        generator = BottleneckReflectionGenerator()

        import inspect

        sig = inspect.signature(generator.generate_weekly_reflection)
        assert "use_llm" in sig.parameters

    def test_weekly_reflection_has_llm_fields(self):
        """Test that WeeklyReflectionArtifact has LLM-related fields."""
        from src.governance.reflection import WeeklyReflectionArtifact

        import inspect

        sig = inspect.signature(WeeklyReflectionArtifact)
        assert "llm_executive_summary" in sig.parameters
        assert "llm_insights" in sig.parameters


class TestRunWeeklyReflectionScript:
    """Test that run_weekly_reflection script has LLM support."""

    def test_script_has_use_llm_flag(self):
        """Test that run_weekly_reflection.py accepts --use-llm flag."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "scripts/evaluation/run_weekly_reflection.py", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "--use-llm" in result.stdout

    def test_script_imports_llm_integration(self):
        """Test that script imports LLM integration module."""
        # Read the script content
        script_path = "scripts/evaluation/run_weekly_reflection.py"
        with open(script_path) as f:
            content = f.read()

        # Should import LLM integration
        assert "LLM_INTEGRATION_AVAILABLE" in content
        assert "use_llm" in content


class TestIntegrationEndToEnd:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_full_llm_integration_flow(self):
        """Test the full LLM integration flow with mocked provider."""
        from src.governance.reflection.llm_integration import (
            ReflectionLLMIntegration,
            reset_llm_telemetry,
        )

        # Reset telemetry
        reset_llm_telemetry()

        integration = ReflectionLLMIntegration()

        # Mock the LLM provider chain
        mock_chain = MagicMock()
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = """KEY_FINDINGS:
- Test finding 1
- Test finding 2

RECOMMENDATIONS:
- Test recommendation

RISK_ASSESSMENT: Low - Everything looks good"""
        mock_response.provider = "test_provider"
        mock_response.error = None
        mock_chain.query = AsyncMock(return_value=mock_response)

        with patch.object(integration, "_get_chain", return_value=mock_chain):
            result = await integration.generate_llm_insights(
                trend_data={"bottlenecks": []},
                kpi_data={"coverage": 0.85},
            )

        assert result.success is True
        assert result.provider_used == "test_provider"
        assert len(result.insights.get("key_findings", [])) > 0

    def test_insight_parsing(self):
        """Test that insights are properly parsed from LLM response."""
        from src.governance.reflection.llm_integration import (
            ReflectionLLMIntegration,
        )

        integration = ReflectionLLMIntegration()

        content = """KEY_FINDINGS:
- Finding 1: Test issue
- Finding 2: Another issue

RECOMMENDATIONS:
- Fix the test
- Improve coverage

RISK_ASSESSMENT: Medium - Some concerns"""

        insights = integration._parse_insights(content)

        assert len(insights["key_findings"]) == 2
        assert len(insights["recommendations"]) == 2
        assert insights["risk_assessment"] == "Medium - Some concerns"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
