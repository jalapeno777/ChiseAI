#!/usr/bin/env python3
"""Secret pattern detection for Terraform and config files.

This script detects common secret patterns in Terraform files (.tf, .tfvars,
.tfvars.template) and config files (.yaml, .yml, .json, .env). It supports
configurable severity levels and can be integrated into CI pipelines.

Usage:
    python detect_secrets.py [options] [files...]

Examples:
    # Scan specific files
    python detect_secrets.py infrastructure/terraform/*.tf

    # Scan all supported files in a directory
    python detect_secrets.py --scan-dir infrastructure/terraform/

    # Run in test mode with sample secrets
    python detect_secrets.py --test-mode

    # Output results as JSON
    python detect_secrets.py --format json infrastructure/terraform/

Exit Codes:
    0 - No secrets detected
    1 - Secrets detected (ERROR or WARN level)
    2 - Configuration or runtime error

Story: TF-SECRETS-003
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(Enum):
    """Severity levels for secret detection findings."""

    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"


@dataclass
class Finding:
    """A secret detection finding."""

    file_path: Path
    line_number: int
    column: int
    pattern_name: str
    severity: Severity
    matched_text: str
    line_content: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        """Convert finding to dictionary."""
        return {
            "file_path": str(self.file_path),
            "line_number": self.line_number,
            "column": self.column,
            "pattern_name": self.pattern_name,
            "severity": self.severity.value,
            "matched_text": self.matched_text,
            "line_content": self.line_content.strip(),
            "description": self.description,
        }


class SecretDetector:
    """Detects secrets in files using configurable patterns."""

    # File extensions supported for scanning
    SUPPORTED_EXTENSIONS = {
        ".tf",
        ".tfvars",
        ".tfvars.template",
        ".yaml",
        ".yml",
        ".json",
        ".env",
        ".properties",
        ".conf",
        ".config",
        ".ini",
        ".toml",
    }

    # Default allow markers (comments that indicate intentional non-secrets)
    DEFAULT_ALLOW_MARKERS = (
        "# nosec",
        "# nosecret",
        "# allow-secret",
        "# example",
        "# dummy",
        "# sample",
        "# test",
        "# placeholder",
        "# fake",
        "# mock",
        "# noqa",
        "# skip-secret-check",
    )

    def __init__(self, min_severity: Severity = Severity.INFO):
        """Initialize the detector with patterns and configuration."""
        self.min_severity = min_severity
        self.patterns: list[dict] = []
        self.findings: list[Finding] = []
        self._register_default_patterns()

    def _register_default_patterns(self) -> None:
        """Register default secret detection patterns."""
        # AWS Access Key ID
        self.patterns.append(
            {
                "name": "aws_access_key_id",
                "regex": re.compile(r"AKIA[0-9A-Z]{16}"),
                "severity": Severity.ERROR,
                "description": "AWS Access Key ID detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # AWS Secret Access Key
        self.patterns.append(
            {
                "name": "aws_secret_access_key",
                "regex": re.compile(r"[0-9a-zA-Z/+=]{40}"),
                "severity": Severity.ERROR,
                "description": "Potential AWS Secret Access Key detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # Generic API keys
        self.patterns.append(
            {
                "name": "api_key_generic",
                "regex": re.compile(
                    r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?"
                ),
                "severity": Severity.ERROR,
                "description": "Generic API key detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # Private keys
        self.patterns.append(
            {
                "name": "private_key",
                "regex": re.compile(
                    r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
                ),
                "severity": Severity.ERROR,
                "description": "Private key detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                    ".pem",
                },
            }
        )

        # GitHub tokens
        self.patterns.append(
            {
                "name": "github_token",
                "regex": re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
                "severity": Severity.ERROR,
                "description": "GitHub token detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # Slack tokens
        self.patterns.append(
            {
                "name": "slack_token",
                "regex": re.compile(r"xox[baprs]-[0-9a-zA-Z\-]+"),
                "severity": Severity.ERROR,
                "description": "Slack token detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # Discord webhooks
        self.patterns.append(
            {
                "name": "discord_webhook",
                "regex": re.compile(
                    r"https://(?:discord(?:app)?\.com)/api/webhooks/[0-9]+/[a-zA-Z0-9_-]+"
                ),
                "severity": Severity.WARN,
                "description": "Discord webhook URL detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # Slack webhooks
        self.patterns.append(
            {
                "name": "slack_webhook",
                "regex": re.compile(
                    r"https://hooks\.slack\.com/services/[A-Za-z0-9/_\-]+"
                ),
                "severity": Severity.WARN,
                "description": "Slack webhook URL detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # Password patterns
        self.patterns.append(
            {
                "name": "password_assignment",
                "regex": re.compile(
                    r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]([^'\"]{8,})['\"]"
                ),
                "severity": Severity.ERROR,
                "description": "Password assignment detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # Database connection strings with passwords
        self.patterns.append(
            {
                "name": "database_connection_string",
                "regex": re.compile(
                    r"(?i)(postgres|mysql|mongodb|redis)://[^:]+:[^@]+@"
                ),
                "severity": Severity.ERROR,
                "description": "Database connection string with password detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # JWT tokens
        self.patterns.append(
            {
                "name": "jwt_token",
                "regex": re.compile(
                    r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*"
                ),
                "severity": Severity.WARN,
                "description": "JWT token detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # Bearer tokens
        self.patterns.append(
            {
                "name": "bearer_token",
                "regex": re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.=]{20,}"),
                "severity": Severity.WARN,
                "description": "Bearer token detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

        # Generic secret/token patterns
        self.patterns.append(
            {
                "name": "generic_secret",
                "regex": re.compile(
                    r"(?i)(secret|token|key)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{20,}['\"]"
                ),
                "severity": Severity.WARN,
                "description": "Generic secret/token pattern detected",
                "extensions": {
                    ".tf",
                    ".tfvars",
                    ".tfvars.template",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".env",
                },
            }
        )

    def _is_allowed_line(self, line: str) -> bool:
        """Check if line contains an allow marker."""
        line_lower = line.lower()
        return any(
            marker.lower() in line_lower for marker in self.DEFAULT_ALLOW_MARKERS
        )

    def _should_scan_file(self, file_path: Path) -> bool:
        """Check if file should be scanned based on extension."""
        if file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
            return True
        if file_path.name.endswith(".tfvars.template"):
            return True
        if file_path.name.startswith(".") and "env" in file_path.name.lower():
            return True
        return False

    def _is_placeholder(self, text: str) -> bool:
        """Check if text is a placeholder/example value."""
        text_lower = text.lower()

        # Check for explicit placeholder patterns
        explicit_placeholders = [
            "<your_",
            "<",
            ">",
            "${",
            "{{",
            "xxxx",
            "****",
        ]
        for indicator in explicit_placeholders:
            if indicator in text_lower:
                return True

        # Check for placeholder words
        placeholder_indicators = [
            "example",
            "placeholder",
            "dummy",
            "fake",
            "test",
            "sample",
            "mock",
        ]
        for indicator in placeholder_indicators:
            if indicator in text_lower:
                return True

        return False

    def scan_file(self, file_path: Path) -> list[Finding]:
        """Scan a single file for secrets."""
        findings: list[Finding] = []

        if not file_path.exists():
            return findings

        if not self._should_scan_file(file_path):
            return findings

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
        except (OSError, UnicodeDecodeError):
            return findings

        file_ext = file_path.suffix.lower()
        if file_path.name.endswith(".tfvars.template"):
            file_ext = ".tfvars.template"

        severity_order = {Severity.ERROR: 3, Severity.WARN: 2, Severity.INFO: 1}

        for line_num, line in enumerate(lines, 1):
            if self._is_allowed_line(line):
                continue

            for pattern in self.patterns:
                if pattern["extensions"] and file_ext not in pattern["extensions"]:
                    continue

                if (
                    severity_order[pattern["severity"]]
                    < severity_order[self.min_severity]
                ):
                    continue

                for match in pattern["regex"].finditer(line):
                    matched_text = match.group(0)
                    if self._is_placeholder(matched_text):
                        continue

                    finding = Finding(
                        file_path=file_path,
                        line_number=line_num,
                        column=match.start() + 1,
                        pattern_name=pattern["name"],
                        severity=pattern["severity"],
                        matched_text=matched_text[:50] + "..."
                        if len(matched_text) > 50
                        else matched_text,
                        line_content=line,
                        description=pattern["description"],
                    )
                    findings.append(finding)

        return findings

    def scan_directory(self, directory: Path, recursive: bool = True) -> list[Finding]:
        """Scan a directory for secrets."""
        findings: list[Finding] = []

        if not directory.exists():
            return findings

        if recursive:
            files = directory.rglob("*")
        else:
            files = directory.iterdir()

        for file_path in files:
            if file_path.is_file():
                findings.extend(self.scan_file(file_path))

        return findings

    def scan_paths(self, paths: list[Path]) -> list[Finding]:
        """Scan multiple paths (files or directories)."""
        findings: list[Finding] = []

        for path in paths:
            if path.is_file():
                findings.extend(self.scan_file(path))
            elif path.is_dir():
                findings.extend(self.scan_directory(path))

        return findings

    def get_summary(self) -> dict[str, Any]:
        """Get summary of findings."""
        severity_counts: dict[str, int] = {
            "ERROR": 0,
            "WARN": 0,
            "INFO": 0,
        }

        for finding in self.findings:
            severity_counts[finding.severity.value] += 1

        return {
            "total_findings": len(self.findings),
            "error_count": severity_counts["ERROR"],
            "warn_count": severity_counts["WARN"],
            "info_count": severity_counts["INFO"],
            "files_scanned": len(set(f.file_path for f in self.findings)),
        }


def create_test_files(test_dir: Path) -> None:
    """Create test files with sample secrets for testing."""
    test_dir.mkdir(parents=True, exist_ok=True)

    # Terraform file with secrets
    tf_content = """# Test Terraform file with secrets
variable "aws_access_key" {
  default = "AKIAIOSFODNN7EXAMPLE"
}

locals {
  secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
}

resource "aws_db_instance" "example" {
  password = "SuperSecretPassword123!"
}

variable "api_key" {
  default = "sk_live_abcdefghijklmnopqrstuvwxyz123456"
}

variable "dummy_key" {
  default = "AKIAIOSFODNN7EXAMPLE"
}
"""
    (test_dir / "test_secrets.tf").write_text(tf_content)

    # YAML file with secrets
    yaml_content = """# Test YAML file with secrets
database:
  host: localhost
  password: "db_secret_password_123"

api:
  key: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

slack:
  webhook_url: "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"

placeholder_key: "<YOUR_API_KEY_HERE>"
"""
    (test_dir / "test_secrets.yaml").write_text(yaml_content)

    # JSON file with secrets
    json_content = """{
  "aws": {
    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
  },
  "database": {
    "connection_string": "postgres://user:password123@localhost:5432/db"
  },
  "api_token": "xoxb-1234567890123-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx"
}
"""
    (test_dir / "test_secrets.json").write_text(json_content)

    # .env file with secrets
    env_content = """# Test .env file
DATABASE_URL=postgres://admin:secretpass@db.example.com:5432/production
API_KEY=sk_live_abcdefghijklmnopqrstuvwxyz
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
SLACK_TOKEN=xoxb-1234567890123-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx

PLACEHOLDER_KEY=<YOUR_KEY_HERE>
"""
    (test_dir / "test_secrets.env").write_text(env_content)

    # Clean Terraform file (should have no findings)
    clean_tf_content = """# Clean Terraform file - no secrets
variable "region" {
  default = "us-west-2"
}

resource "aws_instance" "example" {
  ami           = "ami-12345678"
  instance_type = "t2.micro"
}

variable "api_key" {
  default = "${API_KEY}"
}
"""
    (test_dir / "clean.tf").write_text(clean_tf_content)


def run_test_mode() -> int:
    """Run the detector in test mode with sample files."""
    import tempfile

    print("=" * 60)
    print("Secret Detection Test Mode")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "test_secrets"
        create_test_files(test_dir)

        print(f"\nCreated test files in: {test_dir}")
        print("\nTest files created:")
        for f in test_dir.iterdir():
            print(f"  - {f.name}")

        detector = SecretDetector(min_severity=Severity.INFO)
        findings = detector.scan_directory(test_dir)
        detector.findings = findings

        print("\n" + "=" * 60)
        print("Detection Results")
        print("=" * 60)

        if not findings:
            print("\nNo secrets detected (this is unexpected in test mode)")
            return 1

        by_file: dict[Path, list[Finding]] = {}
        for finding in findings:
            by_file.setdefault(finding.file_path, []).append(finding)

        for file_path, file_findings in sorted(by_file.items()):
            print(f"\n📄 {file_path.name}")
            print("-" * 40)
            for finding in sorted(file_findings, key=lambda f: f.line_number):
                severity_icon = {
                    Severity.ERROR: "❌",
                    Severity.WARN: "⚠️",
                    Severity.INFO: "ℹ️",
                }.get(finding.severity, "•")

                print(
                    f"  {severity_icon} Line {finding.line_number}: {finding.pattern_name}"
                )
                print(f"     Severity: {finding.severity.value}")
                print(f"     Match: {finding.matched_text}")

        summary = detector.get_summary()
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"Total findings: {summary['total_findings']}")
        print(f"  ERROR: {summary['error_count']}")
        print(f"  WARN:  {summary['warn_count']}")
        print(f"  INFO:  {summary['info_count']}")

        expected_files = {
            "test_secrets.tf": True,
            "test_secrets.yaml": True,
            "test_secrets.json": True,
            "test_secrets.env": True,
            "clean.tf": False,
        }

        all_passed = True
        for filename, should_have_findings in expected_files.items():
            file_path = test_dir / filename
            has_findings = any(f.file_path == file_path for f in findings)

            if has_findings == should_have_findings:
                status = "✅ PASS"
            else:
                status = "❌ FAIL"
                all_passed = False

            expected = "should have" if should_have_findings else "should NOT have"
            print(f"  {status} {filename}: {expected} findings")

        print("\n" + "=" * 60)
        if all_passed:
            print("✅ All tests passed!")
            return 0
        else:
            print("❌ Some tests failed")
            return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect secrets in Terraform and config files",
    )

    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to scan",
    )

    parser.add_argument(
        "--scan-dir",
        type=Path,
        metavar="DIR",
        help="Scan a directory recursively",
    )

    parser.add_argument(
        "--min-severity",
        choices=["ERROR", "WARN", "INFO"],
        default="INFO",
        help="Minimum severity level to report (default: INFO)",
    )

    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run in test mode with sample files",
    )

    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="Exit with code 0 even if secrets found",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    args = parser.parse_args()

    if args.test_mode:
        return run_test_mode()

    paths: list[Path] = []
    if args.scan_dir:
        paths.append(args.scan_dir)
    if args.paths:
        paths.extend(args.paths)

    if not paths:
        parser.error(
            "No paths specified. Use --scan-dir or provide paths as arguments."
        )

    for path in paths:
        if not path.exists():
            print(f"Error: Path does not exist: {path}", file=sys.stderr)
            return 2

    min_severity = Severity[args.min_severity]
    detector = SecretDetector(min_severity=min_severity)
    findings = detector.scan_paths(paths)
    detector.findings = findings

    if args.format == "json":
        output = {
            "findings": [f.to_dict() for f in findings],
            "summary": detector.get_summary(),
        }
        print(json.dumps(output, indent=2))
    else:
        if not findings:
            print("✅ No secrets detected")
            return 0

        by_severity: dict[Severity, list[Finding]] = {
            Severity.ERROR: [],
            Severity.WARN: [],
            Severity.INFO: [],
        }
        for finding in findings:
            by_severity[finding.severity].append(finding)

        for severity in [Severity.ERROR, Severity.WARN, Severity.INFO]:
            severity_findings = by_severity[severity]
            if not severity_findings:
                continue

            icon = {"ERROR": "❌", "WARN": "⚠️", "INFO": "ℹ️"}.get(severity.value, "•")
            print(f"\n{icon} {severity.value} ({len(severity_findings)} findings)")
            print("-" * 60)

            by_file: dict[Path, list[Finding]] = {}
            for finding in severity_findings:
                by_file.setdefault(finding.file_path, []).append(finding)

            for file_path, file_findings in sorted(by_file.items()):
                print(f"\n  {file_path}:")
                for finding in sorted(file_findings, key=lambda f: f.line_number):
                    print(
                        f"    Line {finding.line_number}:{finding.column}: {finding.pattern_name}"
                    )
                    print(f"      {finding.description}")
                    print(f"      Match: {finding.matched_text}")

        summary = detector.get_summary()
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"Total findings: {summary['total_findings']}")
        print(f"  ERROR: {summary['error_count']}")
        print(f"  WARN:  {summary['warn_count']}")
        print(f"  INFO:  {summary['info_count']}")

    if args.exit_zero:
        return 0

    error_count = sum(1 for f in findings if f.severity == Severity.ERROR)
    warn_count = sum(1 for f in findings if f.severity == Severity.WARN)

    if error_count > 0 or warn_count > 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
