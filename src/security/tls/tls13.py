"""TLS 1.3 Implementation for NFR-008 Security Hardening."""

import contextlib
import logging
import os
import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TLSVersion(Enum):
    TLS_1_2 = "TLSv1.2"
    TLS_1_3 = "TLSv1.3"


class CipherSuite(Enum):
    # TLS 1.3 cipher suites
    AES_256_GCM_SHA384 = "TLS_AES_256_GCM_SHA384"
    AES_128_GCM_SHA256 = "TLS_AES_128_GCM_SHA256"
    CHACHA20_POLY1305_SHA256 = "TLS_CHACHA20_POLY1305_SHA256"
    # TLS 1.2 cipher suites (for compatibility)
    ECDHE_RSA_AES256_GCM_SHA384 = "ECDHE-RSA-AES256-GCM-SHA384"
    ECDHE_ECDSA_AES256_GCM_SHA384 = "ECDHE-ECDSA-AES256-GCM-SHA384"


@dataclass
class CertificateInfo:
    """Information about a TLS certificate."""

    path: str
    common_name: str | None = None
    issuer: str | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None
    is_valid: bool = False
    serial_number: str | None = None

    def is_expired(self) -> bool:
        if self.not_after is None:
            return True
        return datetime.now(UTC) > self.not_after

    def days_until_expiry(self) -> int | None:
        if self.not_after is None:
            return None
        delta = self.not_after - datetime.now(UTC)
        return delta.days

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "common_name": self.common_name,
            "issuer": self.issuer,
            "not_before": self.not_before.isoformat() if self.not_before else None,
            "not_after": self.not_after.isoformat() if self.not_after else None,
            "is_valid": self.is_valid,
            "serial_number": self.serial_number,
            "days_until_expiry": self.days_until_expiry(),
        }


@dataclass
class TLSConfig:
    """TLS 1.3 Configuration."""

    cert_file: str | None = None
    key_file: str | None = None
    ca_file: str | None = None
    min_version: TLSVersion = TLSVersion.TLS_1_3
    cipher_suites: list[CipherSuite] = field(
        default_factory=lambda: [
            CipherSuite.AES_256_GCM_SHA384,
            CipherSuite.AES_128_GCM_SHA256,
            CipherSuite.CHACHA20_POLY1305_SHA256,
        ]
    )
    verify_mode: ssl.VerifyMode = ssl.VerifyMode.CERT_REQUIRED
    check_hostname: bool = True
    verify_depth: int = 10
    session_timeout: int = 86400  # 24 hours
    options: int = (
        ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
    )

    def to_dict(self) -> dict:
        return {
            "cert_file": self.cert_file,
            "key_file": self.key_file,
            "min_version": self.min_version.value,
            "cipher_suites": [cs.value for cs in self.cipher_suites],
            "verify_mode": self.verify_mode.name,
            "check_hostname": self.check_hostname,
            "session_timeout": self.session_timeout,
        }


class TLSContext:
    """Manages TLS/SSL context for secure connections."""

    def __init__(self, config: TLSConfig):
        self.config = config
        self._context: ssl.SSLContext | None = None
        self._cert_info: CertificateInfo | None = None

    def create_server_context(self) -> ssl.SSLContext:
        """Create SSL context for server-side connections."""
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._apply_config(context)

        if self.config.cert_file and self.config.key_file:
            context.load_cert_chain(
                self.config.cert_file,
                self.config.key_file,
            )
            self._cert_info = self._load_cert_info(self.config.cert_file)

        self._context = context
        return context

    def create_client_context(self) -> ssl.SSLContext:
        """Create SSL context for client-side connections."""
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._apply_config(context)
        context.check_hostname = self.config.check_hostname

        if self.config.ca_file:
            context.load_verify_locations(self.config.ca_file)
        else:
            context.load_default_certs(ssl.Purpose.SERVER_AUTH)

        self._context = context
        return context

    def _apply_config(self, context: ssl.SSLContext) -> None:
        """Apply configuration to SSL context."""
        # Set minimum version
        if self.config.min_version == TLSVersion.TLS_1_3:
            context.minimum_version = ssl.TLSVersion.TLSv1_3
        elif self.config.min_version == TLSVersion.TLS_1_2:
            context.minimum_version = ssl.TLSVersion.TLSv1_2

        # Set cipher suites - TLS 1.3 uses set_ciphersuites, TLS 1.2 uses set_ciphers
        tls13_ciphers = [
            cs.value for cs in self.config.cipher_suites if cs.value.startswith("TLS_")
        ]
        tls12_ciphers = [
            cs.value
            for cs in self.config.cipher_suites
            if not cs.value.startswith("TLS_")
        ]

        # Set TLS 1.3 ciphersuites if available
        if tls13_ciphers and hasattr(context, "set_ciphersuites"):
            with contextlib.suppress(ssl.SSLError):
                context.set_ciphersuites(":".join(tls13_ciphers))

        # Set TLS 1.2 ciphers
        if tls12_ciphers:
            with contextlib.suppress(ssl.SSLError):
                context.set_ciphers(":".join(tls12_ciphers))

        # Set verification
        context.verify_mode = self.config.verify_mode
        context.verify_flags = ssl.VERIFY_X509_STRICT

        # Set options
        context.options |= self.config.options

        # Session settings
        if hasattr(context, "session_timeout"):
            context.session_timeout = self.config.session_timeout

    def _load_cert_info(self, cert_path: str) -> CertificateInfo:
        """Load certificate information."""
        info = CertificateInfo(path=cert_path)

        try:
            # Try to load and parse the certificate
            # Use openssl command if available
            import subprocess
            from datetime import datetime

            result = subprocess.run(  # nosec B607
                [
                    "openssl",
                    "x509",
                    "-in",
                    cert_path,
                    "-noout",
                    "-subject",
                    "-issuer",
                    "-dates",
                    "-serial",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line.startswith("subject="):
                        info.common_name = (
                            line.split("CN=")[-1].split(",")[0].strip()
                            if "CN=" in line
                            else None
                        )
                    elif line.startswith("issuer="):
                        info.issuer = line.split("=", 1)[1].strip()
                    elif line.startswith("notBefore="):
                        # Parse date
                        date_str = line.split("=", 1)[1].strip()
                        try:
                            info.not_before = datetime.strptime(
                                date_str, "%b %d %H:%M:%S %Y %Z"
                            )
                            info.not_before = info.not_before.replace(tzinfo=UTC)
                        except ValueError:
                            pass
                    elif line.startswith("notAfter="):
                        date_str = line.split("=", 1)[1].strip()
                        try:
                            info.not_after = datetime.strptime(
                                date_str, "%b %d %H:%M:%S %Y %Z"
                            )
                            info.not_after = info.not_after.replace(tzinfo=UTC)
                        except ValueError:
                            pass
                    elif line.startswith("serial="):
                        info.serial_number = line.split("=", 1)[1].strip()

                info.is_valid = not info.is_expired()

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Could not parse certificate: {e}")

        return info

    def get_context(self) -> ssl.SSLContext | None:
        """Get the current SSL context."""
        return self._context

    def get_cert_info(self) -> CertificateInfo | None:
        """Get certificate information."""
        return self._cert_info


class TLSServer:
    """TLS Server implementation with TLS 1.3 support."""

    def __init__(self, config: TLSConfig):
        self.config = config
        self._context: TLSContext | None = None
        self._running = False

    def initialize(self) -> TLSContext:
        """Initialize TLS context."""
        self._context = TLSContext(self.config)
        self._context.create_server_context()
        logger.info("TLS server initialized with TLS 1.3")
        return self._context

    def get_ssl_context(self) -> ssl.SSLContext | None:
        """Get the underlying SSL context."""
        if self._context is None:
            return None
        return self._context.get_context()

    def wrap_socket(self, sock: Any, server_side: bool = True) -> Any:
        """Wrap a socket with TLS."""
        if self._context is None:
            self.initialize()

        ssl_context = self._context.get_context()
        if ssl_context is None:
            raise RuntimeError("Failed to create SSL context")

        return ssl_context.wrap_socket(sock, server_side=server_side)

    def get_cert_info(self) -> CertificateInfo | None:
        """Get certificate information."""
        if self._context is None:
            return None
        return self._context.get_cert_info()

    def verify_config(self) -> list[str]:
        """Verify the TLS configuration and return any issues."""
        issues = []

        if not self.config.cert_file:
            issues.append("No certificate file configured")
        elif not os.path.exists(self.config.cert_file):
            issues.append(f"Certificate file not found: {self.config.cert_file}")

        if not self.config.key_file:
            issues.append("No key file configured")
        elif not os.path.exists(self.config.key_file):
            issues.append(f"Key file not found: {self.config.key_file}")

        if self.config.min_version != TLSVersion.TLS_1_3:
            issues.append(
                f"Minimum TLS version is {self.config.min_version.value}, recommended: TLSv1.3"
            )

        # Check certificate expiry
        if self._context and self._context._cert_info:
            cert = self._context._cert_info
            if cert.is_expired():
                issues.append("Certificate has expired")
            elif cert.days_until_expiry() is not None and cert.days_until_expiry() < 30:
                issues.append(f"Certificate expires in {cert.days_until_expiry()} days")

        return issues

    def get_status(self) -> dict[str, Any]:
        """Get TLS server status."""
        cert_info = self.get_cert_info()
        return {
            "initialized": self._context is not None,
            "min_version": self.config.min_version.value,
            "cipher_suites": [cs.value for cs in self.config.cipher_suites],
            "certificate": cert_info.to_dict() if cert_info else None,
            "issues": self.verify_config(),
        }


def create_default_tls_config(
    cert_file: str, key_file: str, ca_file: str | None = None
) -> TLSConfig:
    """Create a default TLS 1.3 configuration."""
    return TLSConfig(
        cert_file=cert_file,
        key_file=key_file,
        ca_file=ca_file,
        min_version=TLSVersion.TLS_1_3,
        cipher_suites=[
            CipherSuite.AES_256_GCM_SHA384,
            CipherSuite.CHACHA20_POLY1305_SHA256,
            CipherSuite.AES_128_GCM_SHA256,
        ],
    )


def check_tls_support() -> dict[str, bool]:
    """Check TLS 1.3 support in the current Python installation."""
    return {
        "tls_1_3_supported": hasattr(ssl, "TLSVersion")
        and hasattr(ssl.TLSVersion, "TLSv1_3"),
        "ssl_available": True,
        "default_verify_paths": bool(ssl.get_default_verify_paths()),
    }
