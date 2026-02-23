"""LLM provider error classification for deterministic fallback decisions.

This module provides standardized error types for all LLM providers,
enabling deterministic fallback behavior based on error classification.

Error Classification Strategy:
- AuthError (401): Invalid credentials → fallback to next provider
- QuotaError (403 with quota message): Quota exhausted → fallback to next provider
- RateLimitError (429): Rate limited → retry with backoff, then fallback
- ScopeError (403 with scope message): Model not accessible → fallback to next provider
- NetworkError: Connection issues → retry with backoff, then fallback
- ServerError (5xx): Provider server error → retry with backoff, then fallback
- ValidationError (400, 422): Invalid request → don't retry (code error)

For CH-LLM-FALLBACK-002: Harden fallback chain reliability
"""

from __future__ import annotations

from typing import cast


class LLMError(Exception):
    """Base exception for all LLM provider errors."""

    def __init__(
        self, message: str, provider: str | None = None, status_code: int | None = None
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code

    def __str__(self) -> str:
        provider_info = f" [{self.provider}]" if self.provider else ""
        status_info = f" (HTTP {self.status_code})" if self.status_code else ""
        return f"{self.message}{provider_info}{status_info}"


class AuthError(LLMError):
    """Authentication error (401): Invalid API key or credentials.

    Action: Fallback to next provider immediately.
    Retry: No (credentials won't change between retries).
    """

    def __init__(self, message: str, provider: str | None = None):
        super().__init__(message, provider, status_code=401)


class QuotaError(LLMError):
    """Quota exhausted error (403 with quota message).

    Action: Fallback to next provider immediately.
    Retry: No (quota won't reset immediately).
    """

    def __init__(self, message: str, provider: str | None = None):
        super().__init__(message, provider, status_code=403)


class ScopeError(LLMError):
    """Model scope/access error (403 with scope/permission message).

    Action: Fallback to next provider immediately.
    Retry: No (permissions won't change between retries).
    """

    def __init__(self, message: str, provider: str | None = None):
        super().__init__(message, provider, status_code=403)


class RateLimitError(LLMError):
    """Rate limit exceeded error (429).

    Action: Retry with exponential backoff, then fallback.
    Retry: Yes (rate limit will reset).
    """

    def __init__(
        self, message: str, provider: str | None = None, retry_after: int | None = None
    ):
        super().__init__(message, provider, status_code=429)
        self.retry_after = retry_after  # Seconds to wait before retry


class NetworkError(LLMError):
    """Network connectivity error.

    Action: Retry with exponential backoff, then fallback.
    Retry: Yes (network may recover).
    """

    def __init__(self, message: str, provider: str | None = None):
        super().__init__(message, provider, status_code=None)


class ServerError(LLMError):
    """Provider server error (5xx).

    Action: Retry with exponential backoff, then fallback.
    Retry: Yes (server may recover).
    """

    def __init__(
        self, message: str, provider: str | None = None, status_code: int = 500
    ):
        super().__init__(message, provider, status_code=status_code)


class ValidationError(LLMError):
    """Request validation error (400, 422).

    Action: Don't retry (indicates a code bug).
    Retry: No (request is invalid).
    """

    def __init__(
        self, message: str, provider: str | None = None, status_code: int = 400
    ):
        super().__init__(message, provider, status_code=status_code)


class ProviderUnavailableError(LLMError):
    """All providers failed, no fallback available.

    Action: Return degraded mode result.
    """

    def __init__(self, message: str = "All LLM providers unavailable"):
        super().__init__(message, provider=None, status_code=None)


def classify_error(
    error: Exception,
    provider: str,
    status_code: int | None = None,
    response_body: str | None = None,
) -> LLMError:
    """Classify an exception into a standardized LLMError type.

    This function analyzes the error type, HTTP status code, and response body
    to determine the appropriate error classification for fallback decisions.

    Args:
        error: The original exception
        provider: Provider name (e.g., "KIMI", "GLM-5", "GLM-4.7", "MiniMax")
        status_code: HTTP status code if available
        response_body: Response body text if available

    Returns:
        Classified LLMError instance
    """
    response_lower = (response_body or "").lower()

    # Check for rate limiting first (highest priority for retry logic)
    if status_code == 429:
        # Try to extract Retry-After header value from response
        retry_after = None
        return RateLimitError(
            f"Rate limit exceeded for {provider}",
            provider=provider,
            retry_after=retry_after,
        )

    # Check for authentication errors
    if status_code == 401:
        return AuthError(f"Authentication failed for {provider}", provider=provider)

    # Check for quota/scope errors (403)
    if status_code == 403:
        # Check for quota-related keywords
        quota_keywords = ["quota", "limit exceeded", "insufficient quota", "billing"]
        if any(keyword in response_lower for keyword in quota_keywords):
            return QuotaError(f"Quota exhausted for {provider}", provider=provider)

        # Check for scope/permission keywords
        scope_keywords = [
            "scope",
            "permission",
            "access denied",
            "not accessible",
            "forbidden",
        ]
        if any(keyword in response_lower for keyword in scope_keywords):
            return ScopeError(f"Model not accessible for {provider}", provider=provider)

        # Generic 403
        return ScopeError(f"Access denied for {provider}", provider=provider)

    # Check for validation errors
    if status_code in (400, 422):
        return ValidationError(
            f"Request validation failed for {provider}: {error}",
            provider=provider,
            status_code=status_code,
        )

    # Check for server errors
    if status_code and status_code >= 500:
        return ServerError(
            f"Server error from {provider}: {error}",
            provider=provider,
            status_code=status_code,
        )

    # Check for network-related errors
    error_str = str(error).lower()
    network_keywords = [
        "connection",
        "timeout",
        "network",
        "unreachable",
        "refused",
        "reset",
        "dns",
        "ssl",
        "certificate",
    ]
    if any(keyword in error_str for keyword in network_keywords):
        return NetworkError(
            f"Network error with {provider}: {error}", provider=provider
        )

    # Default: wrap as generic LLMError
    return LLMError(str(error), provider=provider, status_code=status_code)


def should_retry(error: LLMError, attempt: int, max_retries: int = 3) -> bool:
    """Determine if an error should trigger a retry.

    Args:
        error: The classified LLMError
        attempt: Current attempt number (0-indexed)
        max_retries: Maximum number of retry attempts

    Returns:
        True if the request should be retried
    """
    if attempt >= max_retries - 1:
        return False

    # These errors should NOT be retried
    if isinstance(error, (AuthError, QuotaError, ScopeError, ValidationError)):
        return False

    # These errors SHOULD be retried
    return isinstance(error, (RateLimitError, NetworkError, ServerError))


def get_fallback_delay(error: LLMError, attempt: int, base_delay: float = 1.0) -> float:
    """Calculate delay before retry based on error type.

    Args:
        error: The classified LLMError
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds

    Returns:
        Delay in seconds before next retry
    """
    if isinstance(error, RateLimitError):
        # Use Retry-After header if available, otherwise exponential backoff
        if error.retry_after is not None:
            return float(error.retry_after)
        # Rate limits get longer delays
        return cast(float, base_delay * (2 ** (attempt + 1)))

    if isinstance(error, (NetworkError, ServerError)):
        # Standard exponential backoff
        return cast(float, base_delay * (2**attempt))

    return base_delay


__all__ = [
    # Error classes
    "LLMError",
    "AuthError",
    "QuotaError",
    "ScopeError",
    "RateLimitError",
    "NetworkError",
    "ServerError",
    "ValidationError",
    "ProviderUnavailableError",
    # Functions
    "classify_error",
    "should_retry",
    "get_fallback_delay",
]
