"""Tests for LLM error classification system.

This module tests the error classification functionality for deterministic
fallback behavior in the LLM provider chain.

CH-LLM-FALLBACK-002: Error classification tests
"""

import pytest

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


class TestErrorClasses:
    """Test suite for error class initialization and attributes."""

    def test_auth_error(self):
        """Test AuthError initialization."""
        error = AuthError("Invalid API key", provider="KIMI")
        assert error.message == "Invalid API key"
        assert error.provider == "KIMI"
        assert error.status_code == 401
        assert "KIMI" in str(error)
        assert "401" in str(error)

    def test_quota_error(self):
        """Test QuotaError initialization."""
        error = QuotaError("Quota exhausted", provider="ZAI")
        assert error.message == "Quota exhausted"
        assert error.provider == "ZAI"
        assert error.status_code == 403

    def test_scope_error(self):
        """Test ScopeError initialization."""
        error = ScopeError("Model not accessible", provider="ZHIPU")
        assert error.message == "Model not accessible"
        assert error.provider == "ZHIPU"
        assert error.status_code == 403

    def test_rate_limit_error(self):
        """Test RateLimitError initialization."""
        error = RateLimitError(
            "Rate limit exceeded", provider="MINIMAX", retry_after=60
        )
        assert error.message == "Rate limit exceeded"
        assert error.provider == "MINIMAX"
        assert error.status_code == 429
        assert error.retry_after == 60

    def test_rate_limit_error_without_retry_after(self):
        """Test RateLimitError without retry_after."""
        error = RateLimitError("Rate limit exceeded", provider="KIMI")
        assert error.retry_after is None

    def test_network_error(self):
        """Test NetworkError initialization."""
        error = NetworkError("Connection timeout", provider="ZAI")
        assert error.message == "Connection timeout"
        assert error.provider == "ZAI"
        assert error.status_code is None

    def test_server_error(self):
        """Test ServerError initialization."""
        error = ServerError("Internal server error", provider="KIMI", status_code=500)
        assert error.message == "Internal server error"
        assert error.provider == "KIMI"
        assert error.status_code == 500

    def test_validation_error(self):
        """Test ValidationError initialization."""
        error = ValidationError("Invalid request", provider="ZHIPU", status_code=400)
        assert error.message == "Invalid request"
        assert error.provider == "ZHIPU"
        assert error.status_code == 400

    def test_provider_unavailable_error(self):
        """Test ProviderUnavailableError initialization."""
        error = ProviderUnavailableError()
        assert error.message == "All LLM providers unavailable"
        assert error.provider is None
        assert error.status_code is None

    def test_base_llm_error(self):
        """Test base LLMError initialization."""
        error = LLMError("Generic error", provider="TEST", status_code=418)
        assert error.message == "Generic error"
        assert error.provider == "TEST"
        assert error.status_code == 418

    def test_error_str_without_provider(self):
        """Test error string representation without provider."""
        error = LLMError("Generic error")
        assert str(error) == "Generic error"


class TestClassifyError:
    """Test suite for classify_error function."""

    def test_classify_401_as_auth_error(self):
        """Test that 401 status code is classified as AuthError."""
        original = Exception("Unauthorized")
        error = classify_error(original, "KIMI", status_code=401)
        assert isinstance(error, AuthError)
        assert error.provider == "KIMI"
        assert error.status_code == 401

    def test_classify_429_as_rate_limit_error(self):
        """Test that 429 status code is classified as RateLimitError."""
        original = Exception("Too many requests")
        error = classify_error(original, "ZAI", status_code=429)
        assert isinstance(error, RateLimitError)
        assert error.provider == "ZAI"
        assert error.status_code == 429
        assert error.retry_after is None

    def test_classify_403_quota_as_quota_error(self):
        """Test that 403 with quota message is classified as QuotaError."""
        original = Exception("Forbidden")
        error = classify_error(
            original, "MINIMAX", status_code=403, response_body="Quota exceeded"
        )
        assert isinstance(error, QuotaError)
        assert error.provider == "MINIMAX"

    def test_classify_403_scope_as_scope_error(self):
        """Test that 403 with scope message is classified as ScopeError."""
        original = Exception("Forbidden")
        error = classify_error(
            original, "ZHIPU", status_code=403, response_body="Access denied"
        )
        assert isinstance(error, ScopeError)
        assert error.provider == "ZHIPU"

    def test_classify_403_generic_as_scope_error(self):
        """Test that generic 403 is classified as ScopeError."""
        original = Exception("Forbidden")
        error = classify_error(original, "KIMI", status_code=403)
        assert isinstance(error, ScopeError)

    def test_classify_400_as_validation_error(self):
        """Test that 400 status code is classified as ValidationError."""
        original = Exception("Bad request")
        error = classify_error(original, "ZAI", status_code=400)
        assert isinstance(error, ValidationError)
        assert error.provider == "ZAI"
        assert error.status_code == 400

    def test_classify_422_as_validation_error(self):
        """Test that 422 status code is classified as ValidationError."""
        original = Exception("Unprocessable")
        error = classify_error(original, "KIMI", status_code=422)
        assert isinstance(error, ValidationError)
        assert error.status_code == 422

    def test_classify_500_as_server_error(self):
        """Test that 500 status code is classified as ServerError."""
        original = Exception("Server error")
        error = classify_error(original, "MINIMAX", status_code=500)
        assert isinstance(error, ServerError)
        assert error.provider == "MINIMAX"
        assert error.status_code == 500

    def test_classify_502_as_server_error(self):
        """Test that 502 status code is classified as ServerError."""
        original = Exception("Bad gateway")
        error = classify_error(original, "ZAI", status_code=502)
        assert isinstance(error, ServerError)
        assert error.status_code == 502

    def test_classify_503_as_server_error(self):
        """Test that 503 status code is classified as ServerError."""
        original = Exception("Service unavailable")
        error = classify_error(original, "KIMI", status_code=503)
        assert isinstance(error, ServerError)
        assert error.status_code == 503

    def test_classify_connection_error_as_network_error(self):
        """Test that connection errors are classified as NetworkError."""
        original = Exception("Connection timeout")
        error = classify_error(original, "ZHIPU")
        assert isinstance(error, NetworkError)
        assert error.provider == "ZHIPU"

    def test_classify_timeout_as_network_error(self):
        """Test that timeout errors are classified as NetworkError."""
        original = Exception("Request timeout")
        error = classify_error(original, "MINIMAX")
        assert isinstance(error, NetworkError)

    def test_classify_dns_error_as_network_error(self):
        """Test that DNS errors are classified as NetworkError."""
        original = Exception("DNS lookup failed")
        error = classify_error(original, "KIMI")
        assert isinstance(error, NetworkError)

    def test_classify_unknown_error_as_generic(self):
        """Test that unknown errors are classified as generic LLMError."""
        original = Exception("Unknown error")
        error = classify_error(original, "ZAI", status_code=418)
        assert type(error) == LLMError  # Exact type, not subclass
        assert error.provider == "ZAI"
        assert error.status_code == 418


class TestShouldRetry:
    """Test suite for should_retry function."""

    def test_auth_error_should_not_retry(self):
        """Test AuthError should not trigger retry."""
        error = AuthError("Invalid key", provider="KIMI")
        assert should_retry(error, attempt=0, max_retries=3) is False
        assert should_retry(error, attempt=1, max_retries=3) is False

    def test_quota_error_should_not_retry(self):
        """Test QuotaError should not trigger retry."""
        error = QuotaError("Quota exceeded", provider="ZAI")
        assert should_retry(error, attempt=0, max_retries=3) is False

    def test_scope_error_should_not_retry(self):
        """Test ScopeError should not trigger retry."""
        error = ScopeError("Access denied", provider="MINIMAX")
        assert should_retry(error, attempt=0, max_retries=3) is False

    def test_validation_error_should_not_retry(self):
        """Test ValidationError should not trigger retry."""
        error = ValidationError("Bad request", provider="KIMI")
        assert should_retry(error, attempt=0, max_retries=3) is False

    def test_rate_limit_error_should_retry(self):
        """Test RateLimitError should trigger retry."""
        error = RateLimitError("Rate limited", provider="ZAI")
        assert should_retry(error, attempt=0, max_retries=3) is True
        assert should_retry(error, attempt=1, max_retries=3) is True
        assert (
            should_retry(error, attempt=2, max_retries=3) is False
        )  # Max retries reached

    def test_server_error_should_retry(self):
        """Test ServerError should trigger retry."""
        error = ServerError("Server error", provider="MINIMAX")
        assert should_retry(error, attempt=0, max_retries=3) is True
        assert should_retry(error, attempt=1, max_retries=3) is True
        assert should_retry(error, attempt=2, max_retries=3) is False

    def test_network_error_should_retry(self):
        """Test NetworkError should trigger retry."""
        error = NetworkError("Connection failed", provider="KIMI")
        assert should_retry(error, attempt=0, max_retries=3) is True
        assert should_retry(error, attempt=1, max_retries=3) is True
        assert should_retry(error, attempt=2, max_retries=3) is False

    def test_generic_error_should_not_retry(self):
        """Test generic LLMError should not trigger retry (safe default)."""
        error = LLMError("Unknown error", provider="ZHIPU")
        assert should_retry(error, attempt=0, max_retries=3) is False

    def test_max_retries_zero_should_not_retry(self):
        """Test that max_retries=0 prevents any retries."""
        error = RateLimitError("Rate limited", provider="KIMI")
        assert should_retry(error, attempt=0, max_retries=1) is False


class TestGetFallbackDelay:
    """Test suite for get_fallback_delay function."""

    def test_rate_limit_delay_with_retry_after(self):
        """Test RateLimitError uses Retry-After header when available."""
        error = RateLimitError("Rate limited", provider="KIMI", retry_after=60)
        delay = get_fallback_delay(error, attempt=0)
        assert delay == 60.0

    def test_rate_limit_delay_exponential_backoff(self):
        """Test RateLimitError exponential backoff when no Retry-After."""
        error = RateLimitError("Rate limited", provider="ZAI")

        # Attempt 0: base_delay * 2^(0+1) = 1 * 2 = 2
        delay_0 = get_fallback_delay(error, attempt=0, base_delay=1.0)
        assert delay_0 == 2.0

        # Attempt 1: base_delay * 2^(1+1) = 1 * 4 = 4
        delay_1 = get_fallback_delay(error, attempt=1, base_delay=1.0)
        assert delay_1 == 4.0

        # Attempt 2: base_delay * 2^(2+1) = 1 * 8 = 8
        delay_2 = get_fallback_delay(error, attempt=2, base_delay=1.0)
        assert delay_2 == 8.0

    def test_network_error_exponential_backoff(self):
        """Test NetworkError exponential backoff."""
        error = NetworkError("Connection failed", provider="MINIMAX")

        # Attempt 0: base_delay * 2^0 = 1 * 1 = 1
        delay_0 = get_fallback_delay(error, attempt=0, base_delay=1.0)
        assert delay_0 == 1.0

        # Attempt 1: base_delay * 2^1 = 1 * 2 = 2
        delay_1 = get_fallback_delay(error, attempt=1, base_delay=1.0)
        assert delay_1 == 2.0

        # Attempt 2: base_delay * 2^2 = 1 * 4 = 4
        delay_2 = get_fallback_delay(error, attempt=2, base_delay=1.0)
        assert delay_2 == 4.0

    def test_server_error_exponential_backoff(self):
        """Test ServerError exponential backoff."""
        error = ServerError("Server error", provider="KIMI")

        delay_0 = get_fallback_delay(error, attempt=0, base_delay=1.0)
        assert delay_0 == 1.0

        delay_1 = get_fallback_delay(error, attempt=1, base_delay=1.0)
        assert delay_1 == 2.0

    def test_non_retryable_error_returns_base_delay(self):
        """Test that non-retryable errors return base delay."""
        error = AuthError("Invalid key", provider="ZAI")
        delay = get_fallback_delay(error, attempt=0, base_delay=2.5)
        assert delay == 2.5

    def test_different_base_delays(self):
        """Test that different base delays work correctly."""
        error = NetworkError("Timeout", provider="KIMI")

        delay_0 = get_fallback_delay(error, attempt=0, base_delay=0.5)
        assert delay_0 == 0.5

        delay_1 = get_fallback_delay(error, attempt=1, base_delay=0.5)
        assert delay_1 == 1.0

        delay_0_long = get_fallback_delay(error, attempt=0, base_delay=5.0)
        assert delay_0_long == 5.0


class TestQuotaKeywords:
    """Test suite for quota keyword detection in classify_error."""

    @pytest.mark.parametrize(
        "keyword",
        [
            "quota",
            "Quota exceeded",
            "LIMIT EXCEEDED",
            "insufficient quota",
            "billing limit reached",
        ],
    )
    def test_quota_keywords_detection(self, keyword):
        """Test various quota-related keywords."""
        original = Exception("Error")
        error = classify_error(original, "KIMI", status_code=403, response_body=keyword)
        assert isinstance(error, QuotaError)


class TestScopeKeywords:
    """Test suite for scope keyword detection in classify_error."""

    @pytest.mark.parametrize(
        "keyword",
        [
            "scope",
            "permission denied",
            "ACCESS DENIED",
            "not accessible",
            "forbidden",
        ],
    )
    def test_scope_keywords_detection(self, keyword):
        """Test various scope-related keywords."""
        original = Exception("Error")
        error = classify_error(original, "ZAI", status_code=403, response_body=keyword)
        assert isinstance(error, ScopeError)


class TestNetworkKeywords:
    """Test suite for network keyword detection in classify_error."""

    @pytest.mark.parametrize(
        "keyword",
        [
            "connection refused",
            "timeout",
            "network unreachable",
            "connection reset",
            "DNS lookup failed",
            "SSL certificate",
        ],
    )
    def test_network_keywords_detection(self, keyword):
        """Test various network-related keywords."""
        original = Exception(keyword)
        error = classify_error(original, "MINIMAX")
        assert isinstance(error, NetworkError)
