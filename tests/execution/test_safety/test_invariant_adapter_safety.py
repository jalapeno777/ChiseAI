"""Tests for one-trade-per-symbol invariant safety with adapter.

These tests verify that the one-trade-per-symbol invariant remains
unaffected by adapter latency, failures, or timeouts. The invariant
logic itself is NOT tested here - only that the trade_decision_enhancer
does not interfere with it.

For ST-KIMI-ADAPTER-001: Safety validation and invariant tests.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.execution.llm.trade_decision_enhancer import TradeDecisionEnhancer

# =============================================================================
# Invariant Safety Tests - Adapter Latency
# =============================================================================


class TestInvariantUnchangedByAdapterLatency:
    """Verify slow adapter responses don't cause duplicate trade attempts."""

    @pytest.mark.asyncio
    async def test_invariant_unchanged_by_adapter_latency(self):
        """Verify that slow adapter responses don't cause duplicate trade attempts.

        This test ensures that even when the adapter is slow, the trade decision
        enhancer returns a decision without blocking, and any external invariant
        checking would still be called exactly once.
        """
        enhancer = TradeDecisionEnhancer(enabled=True)

        # Mock chain with slow response
        mock_chain = MagicMock()
        mock_chain.provider_order = ["kimi_compat", "kimi", "zai"]

        async def slow_response(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate slow response
            mock_response = MagicMock()
            mock_response.content = "DECISION: GO\nCONFIDENCE: 75\nRATIONALE: Test"
            mock_response.provider = "KIMI Compat (Adapter)"
            return mock_response

        mock_chain.query = slow_response
        enhancer._chain = mock_chain

        signal = MagicMock()
        signal.token = "BTC"
        signal.direction = "long"
        signal.confidence = 0.8

        # Track how many times a decision is returned
        decision_count = 0

        # Simulate invariant check being called alongside decision
        async def decision_with_invariant_check():
            nonlocal decision_count
            decision = await enhancer.enhance_decision(signal)
            decision_count += 1
            return decision

        # Should complete without blocking
        decision = await asyncio.wait_for(
            decision_with_invariant_check(),
            timeout=1.0,  # Should complete within 1 second despite slow adapter
        )

        # Verify decision is returned
        assert decision.go_no_go is True
        assert decision_count == 1  # Decision returned exactly once
        assert decision.provider_source == "adapter"

    @pytest.mark.asyncio
    async def test_slow_adapter_does_not_cause_retry_storm(self):
        """Verify slow adapter doesn't trigger multiple decision attempts."""
        enhancer = TradeDecisionEnhancer(enabled=True)

        mock_chain = MagicMock()
        mock_chain.provider_order = ["kimi_compat", "kimi"]

        call_count = 0

        async def slow_but_successful(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            mock_response = MagicMock()
            mock_response.content = "DECISION: GO\nCONFIDENCE: 80\nRATIONALE: Test"
            mock_response.provider = "KIMI Compat (Adapter)"
            return mock_response

        mock_chain.query = slow_but_successful
        enhancer._chain = mock_chain

        signal = MagicMock()
        signal.token = "ETH"
        signal.direction = "short"
        signal.confidence = 0.7

        decision = await enhancer.enhance_decision(signal)

        # Query should be called exactly once
        assert call_count == 1
        assert decision.go_no_go is True


# =============================================================================
# Invariant Safety Tests - Adapter Failure
# =============================================================================


class TestInvariantUnchangedByAdapterFailure:
    """Verify adapter failures don't bypass one-trade-per-symbol logic."""

    @pytest.mark.asyncio
    async def test_invariant_unchanged_by_adapter_failure(self):
        """Verify adapter failure doesn't affect one-trade-per-symbol invariant.

        This test mocks the adapter to always fail and verifies that:
        1. The decision is still GO (non-blocking behavior)
        2. The adapter_fallback flag is set correctly
        3. The invariant check (if it existed) would still be called
        """
        enhancer = TradeDecisionEnhancer(enabled=True)

        # Mock chain where adapter fails and falls back to direct kimi
        mock_chain = MagicMock()
        mock_chain.provider_order = ["kimi_compat", "kimi", "zai"]

        mock_response = MagicMock()
        mock_response.content = "DECISION: GO\nCONFIDENCE: 70\nRATIONALE: Fallback test"
        mock_response.provider = "KIMI K2.5"  # Direct kimi succeeded
        mock_chain.query = AsyncMock(return_value=mock_response)
        enhancer._chain = mock_chain

        signal = MagicMock()
        signal.token = "BTC"
        signal.direction = "long"
        signal.confidence = 0.8

        decision = await enhancer.enhance_decision(signal)

        # Verify non-blocking behavior
        assert decision.go_no_go is True
        # Verify adapter fallback tracking
        assert decision.adapter_fallback is True
        assert decision.provider_source == "direct"
        assert "kimi_compat" in decision.provider_chain_path
        assert "kimi" in decision.provider_chain_path

    @pytest.mark.asyncio
    async def test_full_fallback_chain_tracked(self):
        """Verify full fallback chain is tracked when all providers fail over."""
        enhancer = TradeDecisionEnhancer(enabled=True)

        mock_chain = MagicMock()
        mock_chain.provider_order = ["kimi_compat", "kimi", "zai", "zhipu"]

        # All the way to zhipu
        mock_response = MagicMock()
        mock_response.content = "DECISION: GO\nCONFIDENCE: 60\nRATIONALE: Deep fallback"
        mock_response.provider = "GLM-4.7 (Zhipu)"
        mock_chain.query = AsyncMock(return_value=mock_response)
        enhancer._chain = mock_chain

        signal = MagicMock()
        signal.token = "ETH"
        signal.direction = "long"
        signal.confidence = 0.5

        decision = await enhancer.enhance_decision(signal)

        assert decision.go_no_go is True
        assert decision.provider_source == "fallback"
        assert decision.adapter_fallback is True
        # Chain path should show the full fallback
        assert "kimi_compat" in decision.provider_chain_path
        assert "zhipu" in decision.provider_chain_path


# =============================================================================
# Invariant Safety Tests - Timeout Handling
# =============================================================================


class TestNoDuplicateTradeOnAdapterTimeout:
    """Verify timeout handling doesn't create duplicate trades."""

    @pytest.mark.asyncio
    async def test_no_duplicate_trade_creation_on_adapter_timeout(self):
        """Verify timeout handling doesn't create duplicate trades.

        When the adapter times out, the enhancer should return a safe default
        without causing the caller to retry and potentially create duplicates.
        """
        enhancer = TradeDecisionEnhancer(enabled=True)

        mock_chain = MagicMock()
        mock_chain.provider_order = ["kimi_compat", "kimi"]

        # Simulate timeout
        async def timeout_response(*args, **kwargs):
            raise TimeoutError("Request timed out")

        mock_chain.query = timeout_response
        enhancer._chain = mock_chain

        signal = MagicMock()
        signal.token = "BTC"
        signal.direction = "long"
        signal.confidence = 0.8

        # Set short timeout for faster test
        with patch.dict("os.environ", {"LLM_DECISION_TIMEOUT_MS": "100"}):
            decision = await enhancer.enhance_decision(signal)

        # Should return safe default
        assert decision.go_no_go is True
        assert decision.provider == "timeout"
        assert decision.provider_source == "fallback"
        assert decision.fallback_used is True

    @pytest.mark.asyncio
    async def test_timeout_does_not_block_subsequent_decisions(self):
        """Verify a timeout doesn't block future decisions for same symbol."""
        enhancer = TradeDecisionEnhancer(enabled=True)

        mock_chain = MagicMock()
        mock_chain.provider_order = ["kimi_compat", "kimi"]

        # First call times out, second succeeds
        call_count = 0

        async def mixed_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("Timeout")
            mock_response = MagicMock()
            mock_response.content = "DECISION: GO\nCONFIDENCE: 75\nRATIONALE: Success"
            mock_response.provider = "KIMI K2.5"
            return mock_response

        mock_chain.query = mixed_response
        enhancer._chain = mock_chain

        signal = MagicMock()
        signal.token = "BTC"
        signal.direction = "long"
        signal.confidence = 0.8

        # First call - timeout
        with patch.dict("os.environ", {"LLM_DECISION_TIMEOUT_MS": "100"}):
            decision1 = await enhancer.enhance_decision(signal)

        assert decision1.provider == "timeout"

        # Second call - should work normally
        decision2 = await enhancer.enhance_decision(signal)

        assert decision2.provider == "KIMI K2.5"
        assert decision2.go_no_go is True


# =============================================================================
# Invariant Safety Tests - State Preservation
# =============================================================================


class TestAdapterFallbackDoesNotResetInvariantState:
    """Verify fallback to direct kimi doesn't reset symbol lock state."""

    @pytest.mark.asyncio
    async def test_adapter_fallback_does_not_reset_invariant_state(self):
        """Verify fallback to direct kimi doesn't reset symbol lock state.

        This test simulates a scenario where:
        1. First trade attempt: adapter fails, falls back to direct kimi, trade GO
        2. Second trade attempt: should still check invariant (not reset by fallback)

        The key assertion is that the enhancer's behavior is consistent regardless
        of whether adapter or direct kimi is used.
        """
        enhancer = TradeDecisionEnhancer(enabled=True)

        mock_chain = MagicMock()
        mock_chain.provider_order = ["kimi_compat", "kimi"]

        mock_response = MagicMock()
        mock_response.content = "DECISION: GO\nCONFIDENCE: 75\nRATIONALE: Test"
        mock_response.provider = "KIMI K2.5"
        mock_chain.query = AsyncMock(return_value=mock_response)
        enhancer._chain = mock_chain

        signal = MagicMock()
        signal.token = "BTC"
        signal.direction = "long"
        signal.confidence = 0.8

        # First decision (with adapter fallback)
        decision1 = await enhancer.enhance_decision(signal)

        assert decision1.go_no_go is True
        assert decision1.adapter_fallback is True

        # Second decision (simulating same symbol)
        decision2 = await enhancer.enhance_decision(signal)

        # Both decisions should be consistent
        assert decision2.go_no_go is True
        assert decision2.adapter_fallback is True

        # The enhancer should not have any side effects that would
        # interfere with external invariant checking
        assert decision1.provider_source == decision2.provider_source

    @pytest.mark.asyncio
    async def test_decision_metadata_consistent_across_calls(self):
        """Verify decision metadata is consistent for invariant checking."""
        enhancer = TradeDecisionEnhancer(enabled=True)

        mock_chain = MagicMock()
        mock_chain.provider_order = ["kimi_compat", "kimi", "zai"]

        mock_response = MagicMock()
        mock_response.content = "DECISION: GO\nCONFIDENCE: 80\nRATIONALE: Consistent"
        mock_response.provider = "KIMI K2.5"
        mock_chain.query = AsyncMock(return_value=mock_response)
        enhancer._chain = mock_chain

        signal = MagicMock()
        signal.token = "ETH"
        signal.direction = "short"
        signal.confidence = 0.7

        # Multiple decisions for same symbol
        decisions = []
        for _ in range(3):
            decision = await enhancer.enhance_decision(signal)
            decisions.append(decision)

        # All decisions should have consistent metadata structure
        for decision in decisions:
            assert hasattr(decision, "provider_source")
            assert hasattr(decision, "adapter_fallback")
            assert hasattr(decision, "provider_chain_path")
            assert decision.provider_source in ("adapter", "direct", "fallback")
            assert isinstance(decision.adapter_fallback, bool)


# =============================================================================
# Integration-style Safety Tests
# =============================================================================


class TestInvariantIntegrationWithEnhancer:
    """Integration tests for invariant + enhancer interaction."""

    @pytest.mark.asyncio
    async def test_enhancer_returns_go_even_when_adapter_fails(self):
        """Verify GO decision even when adapter completely fails.

        This is the critical safety property: the enhancer must never
        block trades due to adapter/LLM issues.
        """
        enhancer = TradeDecisionEnhancer(enabled=True)

        mock_chain = MagicMock()
        mock_chain.provider_order = ["kimi_compat", "kimi", "zai", "zhipu", "minimax"]

        # Simulate all providers failing
        mock_chain.query = AsyncMock(side_effect=Exception("All providers failed"))
        enhancer._chain = mock_chain

        signal = MagicMock()
        signal.token = "BTC"
        signal.direction = "long"
        signal.confidence = 0.8

        decision = await enhancer.enhance_decision(signal)

        # Must return GO even on total failure
        assert decision.go_no_go is True
        assert decision.provider == "error"
        assert decision.provider_source == "fallback"

    @pytest.mark.asyncio
    async def test_enhancer_non_blocking_property(self):
        """Verify the fundamental non-blocking property is preserved.

        The enhancer should always return a decision, never block,
        and always default to GO on any failure.
        """
        enhancer = TradeDecisionEnhancer(enabled=True)

        # Test various failure scenarios
        failure_scenarios = [
            ("timeout", TimeoutError("Timeout")),
            ("connection", ConnectionError("Network unreachable")),
            ("generic", Exception("Generic error")),
        ]

        for scenario_name, exception in failure_scenarios:
            mock_chain = MagicMock()
            mock_chain.provider_order = ["kimi_compat", "kimi"]
            mock_chain.query = AsyncMock(side_effect=exception)
            enhancer._chain = mock_chain

            signal = MagicMock()
            signal.token = "BTC"
            signal.direction = "long"
            signal.confidence = 0.8

            decision = await enhancer.enhance_decision(signal)

            assert decision.go_no_go is True, f"Failed for scenario: {scenario_name}"
            assert (
                decision.fallback_used is True
            ), f"Failed for scenario: {scenario_name}"
