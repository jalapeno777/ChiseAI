"""LLM integration module for ChiseAI.

Provides a universal LLM provider chain interface with automatic fallback
between providers (KIMI, Z.ai, Zhipu, MiniMax).

ARCHITECTURAL NOTE: Production code MUST use LLMProviderChain as the
universal interface. Direct client imports are for testing/diagnostics only.
See src/governance/reflection/llm_integration.py as the canonical example.
"""

from llm.errors import (
    AuthError,
    LLMError,
    NetworkError,
    ProviderUnavailableError,
    QuotaError,
    RateLimitError,
    ScopeError,
    ServerError,
    ValidationError,
    classify_error,
    get_fallback_delay,
    should_retry,
)
from llm.provider_chain import (
    ErrorCategory,
    LLMProviderChain,
    LLMResponse,
    ProviderError,
)

__all__ = [
    # Provider chain (universal interface)
    "LLMProviderChain",
    "LLMResponse",
    "ProviderError",
    "ErrorCategory",
    # Error handling (allowed for direct use)
    "LLMError",
    "AuthError",
    "QuotaError",
    "RateLimitError",
    "ScopeError",
    "NetworkError",
    "ServerError",
    "ValidationError",
    "ProviderUnavailableError",
    # Error classification functions
    "classify_error",
    "should_retry",
    "get_fallback_delay",
]
