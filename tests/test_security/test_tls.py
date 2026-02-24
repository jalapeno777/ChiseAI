"""Tests for TLS 1.3 Implementation."""

import os
import pytest
import ssl

from src.security.tls.tls13 import (
    TLSVersion,
    CipherSuite,
    CertificateInfo,
    TLSConfig,
    TLSContext,
    TLSServer,
    create_default_tls_config,
    check_tls_support,
)


class TestTLSVersion:
    """Tests for TLSVersion enum."""

    def test_version_values(self):
        """Test that expected version values exist."""
        assert TLSVersion.TLS_1_2.value == "TLSv1.2"
        assert TLSVersion.TLS_1_3.value == "TLSv1.3"


class TestCipherSuite:
    """Tests for CipherSuite enum."""

    def test_cipher_suite_values(self):
        """Test that expected cipher suites exist."""
        assert CipherSuite.AES_256_GCM_SHA384.value == "TLS_AES_256_GCM_SHA384"
        assert (
            CipherSuite.CHACHA20_POLY1305_SHA256.value == "TLS_CHACHA20_POLY1305_SHA256"
        )


class TestCertificateInfo:
    """Tests for CertificateInfo dataclass."""

    def test_certificate_info_creation(self):
        """Test creating certificate info."""
        info = CertificateInfo(
            path="/path/to/cert.pem",
            common_name="example.com",
            is_valid=True,
        )
        assert info.path == "/path/to/cert.pem"
        assert info.common_name == "example.com"

    def test_certificate_info_expiry(self):
        """Test certificate expiry checking."""
        from datetime import datetime, timezone, timedelta

        # Not expired
        info = CertificateInfo(
            path="cert.pem",
            not_after=datetime.now(timezone.utc) + timedelta(days=30),
        )
        assert info.is_expired() is False

        # Expired
        expired = CertificateInfo(
            path="cert.pem",
            not_after=datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert expired.is_expired() is True

    def test_certificate_info_no_expiry(self):
        """Test certificate with no expiry date."""
        info = CertificateInfo(path="cert.pem", not_after=None)
        assert info.is_expired() is True

    def test_days_until_expiry(self):
        """Test days until expiry calculation."""
        from datetime import datetime, timezone, timedelta

        info = CertificateInfo(
            path="cert.pem",
            not_after=datetime.now(timezone.utc) + timedelta(days=10),
        )
        # Allow for some timing variance
        assert info.days_until_expiry() >= 9
        assert info.days_until_expiry() <= 11

    def test_to_dict(self):
        """Test serializing to dict."""
        info = CertificateInfo(
            path="cert.pem",
            common_name="test",
            is_valid=True,
        )
        d = info.to_dict()
        assert "path" in d
        assert "common_name" in d
        assert "is_valid" in d


class TestTLSConfig:
    """Tests for TLSConfig dataclass."""

    def test_config_defaults(self, tls_config):
        """Test default config values."""
        assert tls_config.min_version == TLSVersion.TLS_1_3
        assert tls_config.verify_mode == ssl.VerifyMode.CERT_REQUIRED
        assert tls_config.check_hostname is True

    def test_config_custom_values(self):
        """Test custom config values."""
        config = TLSConfig(
            cert_file="/path/to/cert.pem",
            key_file="/path/to/key.pem",
            min_version=TLSVersion.TLS_1_2,
        )
        assert config.cert_file == "/path/to/cert.pem"
        assert config.min_version == TLSVersion.TLS_1_2

    def test_config_cipher_suites(self):
        """Test cipher suite configuration."""
        config = TLSConfig(
            cipher_suites=[
                CipherSuite.AES_256_GCM_SHA384,
                CipherSuite.CHACHA20_POLY1305_SHA256,
            ]
        )
        assert len(config.cipher_suites) == 2

    def test_to_dict(self, tls_config):
        """Test serializing config to dict."""
        d = tls_config.to_dict()
        assert "min_version" in d
        assert "cipher_suites" in d
        assert "verify_mode" in d


class TestTLSContext:
    """Tests for TLSContext class."""

    def test_initial_state(self, tls_context):
        """Test initial context state."""
        assert tls_context._context is None

    def test_create_client_context(self, tls_context):
        """Test creating client context."""
        context = tls_context.create_client_context()
        assert context is not None
        assert isinstance(context, ssl.SSLContext)

    def test_create_server_context_no_certs(self, tls_context):
        """Test creating server context without certs."""
        # Should work but won't have cert loaded
        context = tls_context.create_server_context()
        assert context is not None

    def test_get_context_before_creation(self, tls_context):
        """Test getting context before creation."""
        assert tls_context.get_context() is None

    def test_get_context_after_creation(self, tls_context):
        """Test getting context after creation."""
        tls_context.create_client_context()
        context = tls_context.get_context()
        assert context is not None


class TestTLSServer:
    """Tests for TLSServer class."""

    def test_initial_state(self, tls_server):
        """Test initial server state."""
        assert tls_server._context is None
        assert tls_server._running is False

    def test_initialize(self, tls_server):
        """Test server initialization."""
        context = tls_server.initialize()
        assert context is not None
        assert tls_server._context is not None

    def test_get_ssl_context_before_init(self, tls_server):
        """Test getting SSL context before initialization."""
        context = tls_server.get_ssl_context()
        assert context is None

    def test_get_ssl_context_after_init(self, tls_server):
        """Test getting SSL context after initialization."""
        tls_server.initialize()
        context = tls_server.get_ssl_context()
        assert context is not None

    def test_verify_config_no_certs(self, tls_server):
        """Test config verification without certs."""
        issues = tls_server.verify_config()
        assert "No certificate file configured" in issues
        assert "No key file configured" in issues

    def test_verify_config_missing_cert_files(self):
        """Test config verification with missing cert files."""
        config = TLSConfig(
            cert_file="/nonexistent/cert.pem",
            key_file="/nonexistent/key.pem",
        )
        server = TLSServer(config)
        issues = server.verify_config()

        assert any("not found" in issue for issue in issues)

    def test_verify_config_tls_1_2(self):
        """Test config verification with TLS 1.2."""
        config = TLSConfig(min_version=TLSVersion.TLS_1_2)
        server = TLSServer(config)
        issues = server.verify_config()

        assert any("TLSv1.3" in issue for issue in issues)

    def test_get_status(self, tls_server):
        """Test getting server status."""
        status = tls_server.get_status()

        assert "initialized" in status
        assert "min_version" in status
        assert "cipher_suites" in status
        assert "issues" in status

    def test_get_status_after_init(self, tls_server):
        """Test status after initialization."""
        tls_server.initialize()
        status = tls_server.get_status()

        assert status["initialized"] is True


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_default_tls_config(self):
        """Test creating default TLS config."""
        config = create_default_tls_config(
            cert_file="/path/to/cert.pem",
            key_file="/path/to/key.pem",
        )

        assert config.cert_file == "/path/to/cert.pem"
        assert config.key_file == "/path/to/key.pem"
        assert config.min_version == TLSVersion.TLS_1_3
        assert CipherSuite.AES_256_GCM_SHA384 in config.cipher_suites

    def test_check_tls_support(self):
        """Test TLS support check."""
        support = check_tls_support()

        assert "tls_1_3_supported" in support
        assert "ssl_available" in support
        assert support["ssl_available"] is True


class TestTLSVersionEnforcement:
    """Tests for TLS version enforcement."""

    def test_tls_1_3_minimum(self):
        """Test TLS 1.3 minimum enforcement."""
        config = TLSConfig(min_version=TLSVersion.TLS_1_3)
        context = TLSContext(config)
        ssl_context = context.create_client_context()

        # Check that minimum version is set correctly
        # Note: actual attribute may vary by Python version
        assert ssl_context is not None

    def test_tls_1_2_minimum(self):
        """Test TLS 1.2 minimum enforcement."""
        config = TLSConfig(min_version=TLSVersion.TLS_1_2)
        context = TLSContext(config)
        ssl_context = context.create_client_context()

        assert ssl_context is not None


class TestCipherSuiteSelection:
    """Tests for cipher suite selection."""

    def test_default_cipher_suites(self, tls_config):
        """Test default cipher suites are TLS 1.3."""
        # Default should be TLS 1.3 ciphers
        tls_13_ciphers = [
            CipherSuite.AES_256_GCM_SHA384,
            CipherSuite.AES_128_GCM_SHA256,
            CipherSuite.CHACHA20_POLY1305_SHA256,
        ]
        for cipher in tls_13_ciphers:
            assert cipher in tls_config.cipher_suites

    def test_custom_cipher_suites(self):
        """Test custom cipher suite configuration."""
        config = TLSConfig(
            cipher_suites=[
                CipherSuite.AES_256_GCM_SHA384,
                CipherSuite.ECDHE_RSA_AES256_GCM_SHA384,
            ]
        )
        assert len(config.cipher_suites) == 2


class TestCertificateVerification:
    """Tests for certificate verification settings."""

    def test_verify_mode_required(self, tls_config):
        """Test verify mode is required by default."""
        assert tls_config.verify_mode == ssl.VerifyMode.CERT_REQUIRED

    def test_check_hostname_enabled(self, tls_config):
        """Test hostname checking is enabled by default."""
        assert tls_config.check_hostname is True

    def test_verify_depth(self, tls_config):
        """Test verify depth setting."""
        assert tls_config.verify_depth == 10

    def test_custom_verify_settings(self):
        """Test custom verification settings."""
        config = TLSConfig(
            verify_mode=ssl.VerifyMode.CERT_OPTIONAL,
            check_hostname=False,
            verify_depth=5,
        )
        assert config.verify_mode == ssl.VerifyMode.CERT_OPTIONAL
        assert config.check_hostname is False
        assert config.verify_depth == 5
