"""Trade Decision Enhancer using LLM provider chain.

Enhances trade decisions with LLM analysis while maintaining
fallback behavior when LLM providers are unavailable.

For PAPER-EXEC-001: LLM-enhanced trade decisions with fallback.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TradeDecision:
    """Enhanced trade decision with LLM analysis."""

    go_no_go: bool  # True = GO, False = NO-GO
    confidence: float  # 0.0 to 100.0
    rationale: str  # LLM reasoning
    provider: str  # Which LLM provider was used
    fallback_used: bool  # True if fallback was used
    latency_ms: float  # Response time
    position_size: float | None = None  # Recommended position size
    stop_loss: float | None = None  # Recommended stop-loss price
    take_profit: float | None = None  # Recommended take-profit price
    risk_recommendation: str = ""  # Risk management guidance


class TradeDecisionEnhancer:
    """Enhances trade decisions using LLM provider chain.

    Uses the existing LLM provider chain with automatic fallback
    between providers. If all providers fail, returns a safe
    default decision (GO with warning) to avoid blocking trades.

    Feature flag: USE_LLM_TRADE_DECISIONS (default: False)
    """

    def __init__(
        self, enabled: bool | None = None, timeout_ms: int | None = None
    ) -> None:
        """Initialize the trade decision enhancer.

        Args:
            enabled: Override feature flag. If None, reads from env.
            timeout_ms: Override timeout in milliseconds. If None, reads from env.
                        Default is 60000ms (60s), can be overridden via
                        LLM_DECISION_TIMEOUT_MS env var (max 120000ms / 120s).
        """
        if enabled is None:
            enabled = os.getenv("USE_LLM_TRADE_DECISIONS", "false").lower() == "true"
        self.enabled = enabled

        # Set timeout (default 60s, override via env)
        if timeout_ms is not None:
            self.timeout_ms = timeout_ms
        else:
            self.timeout_ms = int(os.getenv("LLM_DECISION_TIMEOUT_MS", "60000"))

        # Clamp timeout to reasonable range (1s min, 120s max)
        self.timeout_ms = max(1000, min(self.timeout_ms, 120000))

        logger.info(f"TradeDecisionEnhancer: timeout={self.timeout_ms}ms")

        self._chain = None

        if self.enabled:
            self._init_chain()

    def _init_chain(self) -> None:
        """Initialize LLM provider chain."""
        try:
            from src.llm.provider_chain import LLMProviderChain

            self._chain = LLMProviderChain(enable_metrics=True)
            logger.info(
                f"TradeDecisionEnhancer: LLM provider chain initialized successfully "
                f"(providers: {self._chain.provider_order})"
            )
        except Exception as e:
            logger.warning(
                f"TradeDecisionEnhancer: Failed to initialize LLM chain: {e}",
                exc_info=True,
            )
            self._chain = None

    async def enhance_decision(
        self,
        signal: Any,
        market_context: dict[str, Any] | None = None,
    ) -> TradeDecision:
        """Enhance a trade decision with LLM analysis.

        Args:
            signal: Trading signal to evaluate
            market_context: Optional market context (prices, trends, etc.)

        Returns:
            TradeDecision with GO/NO-GO and rationale
        """
        start_time = time.time()

        logger.debug(
            f"enhance_decision called: enabled={self.enabled}, chain={self._chain is not None}"
        )

        # If disabled or chain unavailable, return safe default
        if not self.enabled or self._chain is None:
            logger.info(
                f"LLM enhancement skipped: enabled={self.enabled}, chain_available={self._chain is not None}"
            )
            return TradeDecision(
                go_no_go=True,  # Default to GO when disabled
                confidence=50.0,
                rationale="LLM enhancement disabled or unavailable",
                provider="none",
                fallback_used=True,
                latency_ms=0.0,
            )

        # Build prompt for LLM
        prompt = self._build_prompt(signal, market_context)

        try:
            # Query LLM provider chain with fallback and timeout
            timeout_seconds = self.timeout_ms / 1000.0
            response = await asyncio.wait_for(
                self._chain.query(prompt), timeout=timeout_seconds
            )

            latency_ms = (time.time() - start_time) * 1000

            # Parse response
            (
                go_no_go,
                confidence,
                rationale,
                position_size,
                stop_loss,
                take_profit,
                risk_recommendation,
            ) = self._parse_response(response.content)

            return TradeDecision(
                go_no_go=go_no_go,
                confidence=confidence,
                rationale=rationale,
                provider=response.provider,
                fallback_used=response.provider != "kimi",  # Primary is KIMI
                latency_ms=latency_ms,
                position_size=position_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_recommendation=risk_recommendation,
            )

        except TimeoutError:
            logger.error(
                f"TradeDecisionEnhancer: LLM query timed out after {self.timeout_ms}ms"
            )
            latency_ms = (time.time() - start_time) * 1000

            # Extract signal context for enriched fallback
            ctx = self._extract_signal_context(signal)

            # Build enriched rationale
            rationale = (
                f"LLM enhancement timed out after {self.timeout_ms}ms. "
                f"Proceeding with BASE SIGNAL: {ctx['direction']} {ctx['symbol']} "
                f"(confidence: {ctx['confidence']:.1%}, score: {ctx['base_score']}). "
                f"Signal basis: {ctx['factor_summary']}. "
                f"Trade executed per base signal policy."
            )

            # Return safe default - don't block trades on timeout
            return TradeDecision(
                go_no_go=True,  # Safe default: allow trade
                confidence=50.0,
                rationale=rationale,
                provider="timeout",
                fallback_used=True,
                latency_ms=latency_ms,
            )

        except Exception as e:
            logger.error(f"TradeDecisionEnhancer: LLM query failed: {e}")
            latency_ms = (time.time() - start_time) * 1000

            # Extract signal context for enriched fallback
            ctx = self._extract_signal_context(signal)

            # Build enriched rationale
            rationale = (
                f"LLM enhancement failed after {self.timeout_ms}ms: {str(e)[:80]}. "
                f"Proceeding with BASE SIGNAL: {ctx['direction']} {ctx['symbol']} "
                f"(confidence: {ctx['confidence']:.1%}, score: {ctx['base_score']}). "
                f"Signal basis: {ctx['factor_summary']}. "
                f"Trade executed per base signal policy."
            )

            # Return safe default - don't block trades on LLM failure
            return TradeDecision(
                go_no_go=True,  # Safe default: allow trade
                confidence=50.0,
                rationale=rationale,
                provider="error",
                fallback_used=True,
                latency_ms=latency_ms,
            )

    def _extract_signal_context(self, signal: Any) -> dict[str, Any]:
        """Extract key signal information for fallback rationale.

        Args:
            signal: Trading signal to extract context from

        Returns:
            Dict with symbol, direction, confidence, base_score, factor_summary
        """
        factors = getattr(signal, "contributing_factors", [])
        factor_summary = (
            ", ".join(
                [
                    f"{f.get('name', 'unknown')}({f.get('score', 0)})"
                    for f in factors[:3]  # Top 3 factors
                ]
            )
            if factors
            else "technical analysis"
        )

        return {
            "symbol": getattr(signal, "token", getattr(signal, "symbol", "UNKNOWN")),
            "direction": getattr(signal, "direction", "unknown"),
            "confidence": getattr(signal, "confidence", 0.0),
            "base_score": getattr(signal, "base_score", 0.0),
            "factor_summary": factor_summary,
        }

    def _build_prompt(
        self,
        signal: Any,
        market_context: dict[str, Any] | None = None,
    ) -> str:
        """Build prompt for LLM analysis."""
        symbol = getattr(signal, "token", getattr(signal, "symbol", "UNKNOWN"))
        direction = getattr(signal, "direction", "unknown")
        confidence = getattr(signal, "confidence", 0.5)

        prompt = f"""Analyze this trade signal and provide a GO/NO-GO decision.

Signal Details:
- Symbol: {symbol}
- Direction: {direction}
- Base Confidence: {confidence:.2%}
"""

        if market_context:
            prompt += f"""
Market Context:
- Current Price: {market_context.get("price", "N/A")}
- 24h Change: {market_context.get("change_24h", "N/A")}
- Volume: {market_context.get("volume", "N/A")}
"""

        prompt += """
Respond in this exact format:
DECISION: [GO or NO-GO]
CONFIDENCE: [0-100]
RATIONALE: [Brief reasoning in 1-2 sentences]
POSITION_SIZE: [recommended position size as % of portfolio, 0-100]
STOP_LOSS: [recommended stop-loss price]
TAKE_PROFIT: [recommended take-profit price]
RISK_RECOMMENDATION: [brief risk management guidance]
"""

        return prompt

    def _parse_response(
        self, content: str
    ) -> tuple[bool, float, str, float | None, float | None, float | None, str]:
        """Parse LLM response into structured decision.

        Args:
            content: Raw LLM response text

        Returns:
            Tuple of (go_no_go, confidence, rationale, position_size,
                     stop_loss, take_profit, risk_recommendation)
        """
        go_no_go = True  # Default to GO
        confidence = 50.0
        rationale = "No rationale provided"
        position_size: float | None = None
        stop_loss: float | None = None
        take_profit: float | None = None
        risk_recommendation = ""

        lines = content.strip().split("\n")

        for line in lines:
            line = line.strip()
            if line.startswith("DECISION:"):
                decision = line.split(":", 1)[1].strip().upper()
                go_no_go = decision == "GO"
            elif line.startswith("CONFIDENCE:"):
                try:
                    conf_str = line.split(":", 1)[1].strip()
                    confidence = float(conf_str.replace("%", ""))
                except (ValueError, IndexError):
                    confidence = 50.0
            elif line.startswith("RATIONALE:"):
                rationale = line.split(":", 1)[1].strip()
            elif line.startswith("POSITION_SIZE:"):
                try:
                    size_str = line.split(":", 1)[1].strip()
                    position_size = float(size_str.replace("%", ""))
                except (ValueError, IndexError):
                    position_size = None
            elif line.startswith("STOP_LOSS:"):
                try:
                    stop_loss = float(line.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    stop_loss = None
            elif line.startswith("TAKE_PROFIT:"):
                try:
                    take_profit = float(line.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    take_profit = None
            elif line.startswith("RISK_RECOMMENDATION:"):
                risk_recommendation = line.split(":", 1)[1].strip()

        return (
            go_no_go,
            confidence,
            rationale,
            position_size,
            stop_loss,
            take_profit,
            risk_recommendation,
        )

    def get_health(self) -> dict[str, Any]:
        """Get health status of the enhancer."""
        return {
            "enabled": self.enabled,
            "chain_initialized": self._chain is not None,
            "provider_chain_available": self._chain is not None,
            "timeout_ms": self.timeout_ms,
        }
