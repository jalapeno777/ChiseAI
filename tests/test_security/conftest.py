"""Shared fixtures for security tests."""

import os
import tempfile

import pytest
from src.security.encryption.aes256 import AES256Encryptor, KeyManager
from src.security.tls.tls13 import (
    TLSConfig,
    TLSContext,
    TLSServer,
    TLSVersion,
)


@pytest.fixture
def key_manager():
    """Basic key manager instance."""
    return KeyManager()


@pytest.fixture
def encryptor():
    """Basic encryptor instance."""
    return AES256Encryptor()


@pytest.fixture
def sample_key():
    """Sample 32-byte key for testing."""
    return os.urandom(32)


@pytest.fixture
def sample_plaintext():
    """Sample plaintext for encryption tests."""
    return b"Hello, World! This is a secret message."


@pytest.fixture
def tls_config():
    """Basic TLS configuration."""
    return TLSConfig(
        cert_file=None,
        key_file=None,
        min_version=TLSVersion.TLS_1_3,
    )


@pytest.fixture
def tls_context(tls_config):
    """Basic TLS context."""
    return TLSContext(tls_config)


@pytest.fixture
def tls_server(tls_config):
    """Basic TLS server."""
    return TLSServer(tls_config)


@pytest.fixture
def temp_cert_files():
    """Create temporary certificate files for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = os.path.join(tmpdir, "test.crt")
        key_path = os.path.join(tmpdir, "test.key")

        # Create dummy files (not valid certs, just for path testing)
        with open(cert_path, "w") as f:
            f.write("-----BEGIN CERTIFICATE-----\n")
            f.write(
                "MIIBkTCB+wIJAKHHCgVZU2jAMA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBnRl\n"
            )
            f.write(
                "c3RDQTAeFw0yNDAxMDEwMDAwMDBaFw0yNTAxMDEwMDAwMDBaMBExDzANBgNVBAMM\n"
            )
            f.write(
                "BnRlc3RDQTCBnzANBgkqhkiG9w0BAQEFAAOBjQAwgYkCgYEAwT8kqCEm4Y5lqZ3a\n"
            )
            f.write("-----END CERTIFICATE-----\n")

        with open(key_path, "w") as f:
            f.write("-----BEGIN PRIVATE KEY-----\n")
            f.write("MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDB\n")
            f.write("-----END PRIVATE KEY-----\n")

        yield {"cert": cert_path, "key": key_path}
