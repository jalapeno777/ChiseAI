"""LLM integration module for ChiseAI.

Provides clients for various LLM APIs including MiniMax, Z.ai, and KIMI.
Also includes provider chain for automatic fallback between providers.
"""

from config.env_loader import EnvLoader, kimi_loader, load_kimi_config
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
from llm.kimi_client import (
    KimiClient,
    KimiConfig,
    KimiMessage,
    KimiResponse,
)
from llm.minimax_client import (
    MiniMaxClient,
    MiniMaxConfig,
    MiniMaxMessage,
    MiniMaxResponse,
)
from llm.provider_chain import (
    ErrorCategory,
    LLMProviderChain,
    LLMResponse,
    ProviderError,
    classify_error,
)
from llm.zai_client import (
    ZaiClient,
    ZaiConfig,
    ZaiMessage,
    ZaiResponse,
)
from llm.zhipu_client import (
    ZaiAuthError,
    ZaiError,
    ZaiRateLimitError,
    ZaiServerError,
    ZaiTimeoutError,
    ZhipuClient,
)

__all__ = [
    # Error classes (CH-LLM-FALLBACK-002)
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
    # KIMI
    "KimiClient",
    "KimiConfig",
    "KimiMessage",
    "KimiResponse",
    # Config
    "EnvLoader",
    "kimi_loader",
    "load_kimi_config",
    # MiniMax
    "MiniMaxClient",
    "MiniMaxConfig",
    "MiniMaxMessage",
    "MiniMaxResponse",
    # Z.ai
    "ZaiClient",
    "ZaiConfig",
    "ZaiMessage",
    "ZaiResponse",
    # Zhipu
    "ZhipuClient",
    "ZaiError",
    "ZaiAuthError",
    "ZaiRateLimitError",
    "ZaiServerError",
    "ZaiTimeoutError",
    # Provider chain exports
    "LLMProviderChain",
    "LLMResponse",
    "ProviderError",
    "ErrorCategory",
    "classify_error",
]
