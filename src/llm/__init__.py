"""LLM integration module for ChiseAI.

Provides clients for various LLM APIs including MiniMax, Z.ai, and KIMI.
Also includes provider chain for automatic fallback between providers.
"""

from config.env_loader import EnvLoader, kimi_loader, load_kimi_config
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
    "KimiClient",
    "KimiConfig",
    "KimiMessage",
    "KimiResponse",
    "EnvLoader",
    "kimi_loader",
    "load_kimi_config",
    "MiniMaxClient",
    "MiniMaxConfig",
    "MiniMaxMessage",
    "MiniMaxResponse",
    "ZaiClient",
    "ZaiConfig",
    "ZaiMessage",
    "ZaiResponse",
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
