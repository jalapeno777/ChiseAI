"""LLM-enhanced confidence analysis for trading signals.

Provides LLMConfidenceEnhancer class that uses LLM APIs to analyze
base signals and provide enhanced confidence scores with rationale.

Uses LLMProviderChain for KIMI-first priority with automatic fallback:
KIMI Adapter → KIMI Direct → Z.ai (GLM-5)

Implements caching to avoid repeated calls for identical signal patterns.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)

# Import LLMProviderChain for centralized provider management
try:
    from llm.provider_chain import LLMProviderChain, LLMResponse

    PROVIDER_CHAIN_AVAILABLE = True
except ImportError:
    logger.debug("LLMProviderChain not available")
    PROVIDER_CHAIN_AVAILABLE = False


@dataclass
class LLMEnhancementResult:
    """Result of LLM confidence enhancement.

    Attributes:
        enhanced_confidence: LLM-adjusted confidence score (0-100)
        base_confidence: Original confidence score before enhancement
        rationale: Explanation of LLM's reasoning
        market_context: Market context interpretation from LLM
        risk_assessment: Risk assessment from LLM
        adjustment_recommendation: Confidence adjustment recommendation
        latency_ms: Time taken for LLM call (ms)
        llm_provider: Which LLM provider was used
        cached: Whether result was retrieved from cache
        fallback_reason: Reason for provider fallback (if applicable)
        timestamp: When enhancement was performed
    """

    enhanced_confidence: float
    base_confidence: float
    rationale: str
    market_context: str
    risk_assessment: str
    adjustment_recommendation: str
    latency_ms: float
    llm_provider: str
    cached: bool = False
    fallback_reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "enhanced_confidence": round(self.enhanced_confidence, 2),
            "base_confidence": round(self.base_confidence, 2),
            "rationale": self.rationale,
            "market_context": self.market_context,
            "risk_assessment": self.risk_assessment,
            "adjustment_recommendation": self.adjustment_recommendation,
            "latency_ms": round(self.latency_ms, 3),
            "llm_provider": self.llm_provider,
            "cached": self.cached,
            "fallback_reason": self.fallback_reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SignalInput:
    """Input data for LLM enhancement.

    Attributes:
        token: Trading pair/token
        direction: Signal direction (long/short/neutral)
        confidence: Base confidence score (0.0-1.0)
        base_score: Base confluence score (0-100)
        indicators: Dict of indicator values
        timeframe: Primary timeframe
        contributing_factors: List of contributing factors
    """

    token: str
    direction: str
    confidence: float
    base_score: float
    indicators: dict[str, Any] = field(default_factory=dict)
    timeframe: str = "1h"
    contributing_factors: list[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Convert to formatted string for LLM prompt."""
        lines = [
            f"Token: {self.token}",
            f"Direction: {self.direction.upper()}",
            f"Base Confidence: {self.confidence:.1%}",
            f"Confluence Score: {self.base_score:.1f}/100",
            f"Timeframe: {self.timeframe}",
        ]

        if self.indicators:
            lines.append("\nTechnical Indicators:")
            for name, value in self.indicators.items():
                lines.append(f"  - {name}: {value}")

        if self.contributing_factors:
            lines.append("\nContributing Factors:")
            for factor in self.contributing_factors[:5]:  # Top 5
                lines.append(f"  - {factor}")

        return "\n".join(lines)

    def to_cache_key(self) -> str:
        """Generate cache key for this signal input."""
        # Normalize for caching - ignore timestamp, focus on signal characteristics
        cache_data = {
            "token": self.token,
            "direction": self.direction,
            "confidence": round(self.confidence, 2),  # Round to reduce cache misses
            "base_score": round(self.base_score, 0),
            "timeframe": self.timeframe,
            # Include indicator names but not exact values (too granular)
            "indicators": sorted(self.indicators.keys()),
        }
        data_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]


class LLMCache:
    """Simple in-memory cache for LLM enhancement results.

    Uses LRU-style eviction with TTL support.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """Initialize cache.

        Args:
            max_size: Maximum number of cached entries
            ttl_seconds: Time-to-live for cache entries
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[LLMEnhancementResult, datetime]] = {}
        self._access_order: list[str] = []

    def get(self, key: str) -> LLMEnhancementResult | None:
        """Get cached result if not expired.

        Args:
            key: Cache key

        Returns:
            Cached result or None if not found/expired
        """
        if key not in self._cache:
            return None

        result, cached_at = self._cache[key]

        # Check TTL
        if (datetime.now(UTC) - cached_at).total_seconds() > self.ttl_seconds:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
            return None

        # Update access order (LRU)
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        # Mark as cached result
        result.cached = True
        return result

    def set(self, key: str, result: LLMEnhancementResult) -> None:
        """Cache a result.

        Args:
            key: Cache key
            result: Result to cache
        """
        # Evict oldest if at capacity
        if len(self._cache) >= self.max_size and self._access_order:
            oldest = self._access_order.pop(0)
            if oldest in self._cache:
                del self._cache[oldest]

        self._cache[key] = (result, datetime.now(UTC))
        self._access_order.append(key)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._access_order.clear()

    def get_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
        }


class LLMConfidenceEnhancer:
    """Enhances signal confidence using LLM analysis via ProviderChain.

    Features:
    - Uses LLMProviderChain with KIMI-first priority
    - Automatic fallback: KIMI Adapter → KIMI Direct → Z.ai
    - Captures fallback reasons in provider traces
    - Caches results to avoid redundant LLM calls
    - Logs all LLM interactions with timestamps
    - Configurable via USE_LLM_ENHANCEMENT env var

    The enhancement process:
    1. Extract signal characteristics
    2. Query LLM via ProviderChain (KIMI-first)
    3. Capture fallback chain with reasons
    4. Get risk assessment and confidence adjustment
    5. Blend: final = (base * 0.7) + (llm * 0.3)
    """

    # System prompt for confidence enhancement
    SYSTEM_PROMPT = """You are an expert quantitative trading analyst.
Your task is to analyze trading signals and provide:

1. Market Context Interpretation: What does the current technical setup
   suggest about market conditions?
2. Risk Assessment: Evaluate potential risks (market volatility,
   trend strength, support/resistance levels)
3. Confidence Adjustment: Recommend a confidence score (0-100)
   based on your analysis
4. Rationale: Brief explanation of your reasoning (2-3 sentences)

Respond in this exact format:
MARKET_CONTEXT: <your interpretation>
RISK_ASSESSMENT: <risk evaluation>
CONFIDENCE_SCORE: <number 0-100>
RATIONALE: <your reasoning>"""

    # Default provider order: KIMI Adapter → KIMI Direct → Z.ai
    DEFAULT_PROVIDER_ORDER = ["kimi_compat", "kimi", "zai"]

    def __init__(
        self,
        use_llm: bool | None = None,
        cache_size: int = 1000,
        cache_ttl: int = 3600,
        provider_order: list[str] | None = None,
    ):
        """Initialize LLM confidence enhancer.

        Args:
            use_llm: Whether to use LLM enhancement (from env if None)
            cache_size: Maximum cache entries
            cache_ttl: Cache TTL in seconds
            provider_order: Custom provider order (default: KIMI Adapter → KIMI Direct → Z.ai)
        """
        self.use_llm = self._resolve_use_llm(use_llm)
        self.cache = LLMCache(max_size=cache_size, ttl_seconds=cache_ttl)
        self._provider_order = provider_order or self.DEFAULT_PROVIDER_ORDER

        # Initialize LLMProviderChain
        self._provider_chain: LLMProviderChain | None = None
        self._successful_provider: str = "none"
        self._fallback_reason: str | None = None

        if self.use_llm and PROVIDER_CHAIN_AVAILABLE:
            self._init_provider_chain()

        self._interaction_log: list[dict[str, Any]] = []
        logger.info(
            f"LLMConfidenceEnhancer initialized: use_llm={self.use_llm}, "
            f"provider_order={self._provider_order}"
        )

    def _resolve_use_llm(self, override: bool | None) -> bool:
        """Resolve whether to use LLM from override or env var.

        Args:
            override: Optional override value

        Returns:
            True if LLM enhancement should be used
        """
        if override is not None:
            return override

        env_value = os.getenv("USE_LLM_ENHANCEMENT", "false").lower()
        return env_value in ("true", "1", "yes", "on")

    def _init_provider_chain(self) -> None:
        """Initialize LLMProviderChain with configured provider order."""
        try:
            self._provider_chain = LLMProviderChain(
                provider_order=self._provider_order,
                max_retries=3,
                retry_delay=1.0,
            )
            logger.info(
                f"LLMProviderChain initialized with provider order: {self._provider_order}"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize LLMProviderChain: {e}")
            self.use_llm = False

    def enhance(
        self,
        signal: Signal,
        indicators: dict[str, Any] | None = None,
    ) -> LLMEnhancementResult:
        """Enhance signal confidence using LLM analysis.

        Args:
            signal: The signal to enhance
            indicators: Optional technical indicator values

        Returns:
            LLMEnhancementResult with enhanced confidence and rationale
        """
        start_time = time.perf_counter()

        # Extract signal input
        signal_input = SignalInput(
            token=signal.token,
            direction=signal.direction.value,
            confidence=signal.confidence,
            base_score=signal.base_score,
            indicators=indicators or {},
            timeframe=signal.timeframe,
            contributing_factors=[
                f.get("name", str(f)) for f in signal.contributing_factors
            ],
        )

        # Check cache first
        cache_key = signal_input.to_cache_key()
        cached_result = self.cache.get(cache_key)
        if cached_result:
            latency_ms = (time.perf_counter() - start_time) * 1000
            cached_result.latency_ms = latency_ms  # Update latency for this call
            self._log_interaction(signal_input, cached_result, cache_hit=True)
            return cached_result

        # If LLM disabled or no provider chain, return base confidence
        if not self.use_llm or self._provider_chain is None:
            latency_ms = (time.perf_counter() - start_time) * 1000
            result = LLMEnhancementResult(
                enhanced_confidence=signal.confidence * 100,
                base_confidence=signal.confidence * 100,
                rationale="LLM enhancement disabled or unavailable",
                market_context="N/A",
                risk_assessment="N/A",
                adjustment_recommendation="Use base confidence",
                latency_ms=latency_ms,
                llm_provider="none",
                cached=False,
                fallback_reason=None,
            )
            self._log_interaction(signal_input, result, cache_hit=False)
            return result

        # Call LLM via ProviderChain for enhancement
        try:
            result = self._call_llm_with_chain(signal_input)
            # Cache the result
            self.cache.set(cache_key, result)
            self._log_interaction(signal_input, result, cache_hit=False)
            return result

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"LLM enhancement failed: {e}")
            # Return base confidence on failure
            result = LLMEnhancementResult(
                enhanced_confidence=signal.confidence * 100,
                base_confidence=signal.confidence * 100,
                rationale=f"LLM enhancement failed: {e}",
                market_context="Error",
                risk_assessment="Error",
                adjustment_recommendation="Use base confidence",
                latency_ms=latency_ms,
                llm_provider="none",
                cached=False,
                fallback_reason=str(e),
            )
            self._log_interaction(signal_input, result, cache_hit=False, error=str(e))
            return result

    def _call_llm_with_chain(self, signal_input: SignalInput) -> LLMEnhancementResult:
        """Call LLM via ProviderChain with fallback support.

        Args:
            signal_input: Signal data for analysis

        Returns:
            LLMEnhancementResult from LLM analysis
        """
        start_time = time.perf_counter()
        prompt = self._build_prompt(signal_input)

        # Run async query through ProviderChain
        async def _async_query():
            if self._provider_chain is None:
                raise RuntimeError("ProviderChain not initialized")
            return await self._provider_chain.query(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                providers=self._provider_order,
            )

        try:
            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already in async context, use nest_asyncio if available
                    try:
                        import nest_asyncio

                        nest_asyncio.apply()
                    except ImportError:
                        pass
                response = loop.run_until_complete(_async_query())
            except RuntimeError:
                # No event loop, create one
                response = asyncio.run(_async_query())

            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.success:
                # Track successful provider and any fallback
                self._successful_provider = response.provider
                fallback_reason = self._extract_fallback_reason(response)

                # Parse the content for structured fields
                parsed = self._parse_llm_response(response.content)

                return LLMEnhancementResult(
                    enhanced_confidence=parsed.get(
                        "confidence_score", response.confidence_score
                    ),
                    base_confidence=signal_input.confidence * 100,
                    rationale=parsed.get(
                        "rationale", response.rationale or "No rationale provided"
                    ),
                    market_context=parsed.get("market_context", ""),
                    risk_assessment=parsed.get("risk_assessment", ""),
                    adjustment_recommendation=f"Adjust to {parsed.get('confidence_score', response.confidence_score):.0f}%",
                    latency_ms=latency_ms,
                    llm_provider=response.provider,
                    cached=False,
                    fallback_reason=fallback_reason,
                )
            else:
                # Provider chain failed - construct fallback reason from error
                fallback_reason = self._format_fallback_reason(response)
                raise RuntimeError(f"All providers failed: {fallback_reason}")

        except Exception as e:
            logger.error(f"ProviderChain query failed: {e}")
            raise

    def _extract_fallback_reason(self, response: LLMResponse) -> str | None:
        """Extract fallback reason from response if provider fallback occurred.

        Args:
            response: LLMResponse from ProviderChain

        Returns:
            Fallback reason string or None if no fallback occurred
        """
        if response.error:
            return f"Fallback due to: {response.error.category.name if hasattr(response.error, 'category') else response.error.message}"
        return None

    def _format_fallback_reason(self, response: LLMResponse) -> str:
        """Format fallback reason for logging from failed response.

        Args:
            response: Failed LLMResponse

        Returns:
            Formatted fallback reason string
        """
        if response.error:
            error_info = response.error
            if hasattr(error_info, "category"):
                return f"{error_info.category.name}: {error_info.message}"
            return str(
                error_info.message if hasattr(error_info, "message") else error_info
            )
        return "Unknown error"

    def _build_prompt(self, signal_input: SignalInput) -> str:
        """Build the user prompt for LLM analysis.

        Args:
            signal_input: Signal data

        Returns:
            Formatted prompt string
        """
        return (
            f"Analyze this trading signal and provide your assessment:\n\n"
            f"{signal_input.to_prompt_context()}\n\n"
            f"Based on the technical indicators and signal characteristics, "
            f"provide your analysis in the requested format."
        )

    def _parse_llm_response(self, content: str) -> dict[str, Any]:
        """Parse LLM response into structured data.

        Args:
            content: Raw LLM response content

        Returns:
            Dictionary with parsed fields
        """
        result = {
            "market_context": "",
            "risk_assessment": "",
            "confidence_score": 50.0,  # Default neutral
            "rationale": "",
        }

        lines = content.strip().split("\n")
        current_field = None
        current_value = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for field headers
            if line.startswith("MARKET_CONTEXT:"):
                if current_field and current_value:
                    result[current_field.lower()] = " ".join(current_value).strip()
                current_field = "market_context"
                current_value = [line.replace("MARKET_CONTEXT:", "").strip()]
            elif line.startswith("RISK_ASSESSMENT:"):
                if current_field and current_value:
                    result[current_field.lower()] = " ".join(current_value).strip()
                current_field = "risk_assessment"
                current_value = [line.replace("RISK_ASSESSMENT:", "").strip()]
            elif line.startswith("CONFIDENCE_SCORE:"):
                if current_field and current_value:
                    result[current_field.lower()] = " ".join(current_value).strip()
                score_str = line.replace("CONFIDENCE_SCORE:", "").strip()
                try:
                    # Extract number from string (handle "85" or "85%" or "Score: 85")
                    import re

                    match = re.search(r"(\d+(?:\.\d+)?)", score_str)
                    if match:
                        result["confidence_score"] = float(match.group(1))
                except (ValueError, AttributeError):
                    logger.warning(f"Could not parse confidence score: {score_str}")
                current_field = None
                current_value = []
            elif line.startswith("RATIONALE:"):
                if current_field and current_value:
                    result[current_field.lower()] = " ".join(current_value).strip()
                current_field = "rationale"
                current_value = [line.replace("RATIONALE:", "").strip()]
            elif current_field:
                current_value.append(line)

        # Save last field
        if current_field and current_value:
            result[current_field.lower()] = " ".join(current_value).strip()

        # Ensure confidence score is in valid range
        result["confidence_score"] = max(0.0, min(100.0, result["confidence_score"]))

        return result

    def _log_interaction(
        self,
        signal_input: SignalInput,
        result: LLMEnhancementResult,
        cache_hit: bool,
        error: str | None = None,
    ) -> None:
        """Log LLM interaction for audit purposes.

        Args:
            signal_input: Input signal data
            result: Enhancement result
            cache_hit: Whether result was from cache
            error: Optional error message
        """
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "token": signal_input.token,
            "direction": signal_input.direction,
            "base_confidence": signal_input.confidence,
            "enhanced_confidence": result.enhanced_confidence
            / 100,  # Convert back to 0-1
            "llm_provider": result.llm_provider,
            "latency_ms": result.latency_ms,
            "cache_hit": cache_hit,
            "rationale": result.rationale[:200] if result.rationale else "",  # Truncate
        }

        if error:
            log_entry["error"] = error

        if result.fallback_reason:
            log_entry["fallback_reason"] = result.fallback_reason
            # Log provider trace with fallback reason
            logger.info(
                f"Provider fallback trace: {signal_input.token} - {result.fallback_reason}"
            )

        self._interaction_log.append(log_entry)

        # Also log to standard logger with provider info
        log_msg = (
            f"LLM Enhancement: {signal_input.token} "
            f"[{signal_input.direction}] "
            f"base={signal_input.confidence:.1%} -> "
            f"enhanced={result.enhanced_confidence:.0f}% "
            f"provider={result.llm_provider} "
            f"latency={result.latency_ms:.1f}ms "
            f"cached={cache_hit}"
        )
        if result.fallback_reason:
            log_msg += f" fallback='{result.fallback_reason[:50]}...'"
        logger.info(log_msg)

    def get_interaction_log(self) -> list[dict[str, Any]]:
        """Get all logged LLM interactions.

        Returns:
            List of interaction log entries
        """
        return self._interaction_log.copy()

    def clear_interaction_log(self) -> None:
        """Clear the interaction log."""
        self._interaction_log.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return self.cache.get_stats()

    def is_available(self) -> bool:
        """Check if LLM enhancement is available.

        Returns:
            True if LLM provider chain is configured and ready
        """
        return self.use_llm and self._provider_chain is not None

    def get_provider(self) -> str:
        """Get the last successful LLM provider name.

        Returns:
            Provider name (e.g., "KIMI K2.5", "GLM-5 (Z.ai)", "none")
        """
        return self._successful_provider

    def get_provider_order(self) -> list[str]:
        """Get the configured provider order.

        Returns:
            List of provider names in priority order
        """
        return self._provider_order.copy()

    def get_fallback_reason(self) -> str | None:
        """Get the fallback reason from the last enhancement call.

        Returns:
            Fallback reason string or None if no fallback occurred
        """
        return self._fallback_reason

    def calculate_blended_confidence(
        self, base_confidence: float, llm_confidence: float
    ) -> float:
        """Calculate blended confidence score.

        Formula: final = (base * 0.7) + (llm * 0.3)

        Args:
            base_confidence: Base confidence (0.0-1.0)
            llm_confidence: LLM confidence (0-100)

        Returns:
            Blended confidence (0.0-1.0)
        """
        llm_normalized = llm_confidence / 100.0  # Convert to 0-1
        blended = (base_confidence * 0.7) + (llm_normalized * 0.3)
        return max(0.0, min(1.0, blended))
