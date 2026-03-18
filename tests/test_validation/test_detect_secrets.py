"""Tests for the secret detection script.

Story: TF-SECRETS-003
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from detect_secrets import (
    Finding,
    SecretDetector,
    Severity,
    create_test_files,
    main,
    run_test_mode,
)


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert Severity.ERROR.value == "ERROR"
        assert Severity.WARN.value == "WARN"
        assert Severity.INFO.value == "INFO"


class TestFinding:
    """Tests for Finding dataclass."""

    def test_finding_creation(self):
        """Test creating a finding."""
        finding = Finding(
            file_path=Path("/test/file.tf"),
            line_number=10,
            column=5,
            pattern_name="test_pattern",
            severity=Severity.ERROR,
            matched_text="secret123",
            line_content="password = secret123",
            description="Test finding",
        )

        assert finding.file_path == Path("/test/file.tf")
        assert finding.line_number == 10
        assert finding.column == 5
        assert finding.severity == Severity.ERROR

    def test_finding_to_dict(self):
        """Test converting finding to dictionary."""
        finding = Finding(
            file_path=Path("/test/file.tf"),
            line_number=10,
            column=5,
            pattern_name="test_pattern",
            severity=Severity.ERROR,
            matched_text="secret123",
            line_content="password = secret123",
            description="Test finding",
        )

        result = finding.to_dict()
        assert result["file_path"] == "/test/file.tf"
        assert result["line_number"] == 10
        assert result["severity"] == "ERROR"
        assert result["pattern_name"] == "test_pattern"


class TestSecretDetectorInitialization:
    """Tests for SecretDetector initialization."""

    def test_default_initialization(self):
        """Test default detector initialization."""
        detector = SecretDetector()
        assert detector.min_severity == Severity.INFO
        assert len(detector.patterns) > 0
        assert len(detector.findings) == 0

    def test_custom_min_severity(self):
        """Test initialization with custom severity."""
        detector = SecretDetector(min_severity=Severity.ERROR)
        assert detector.min_severity == Severity.ERROR

    def test_default_patterns_registered(self):
        """Test that default patterns are registered."""
        detector = SecretDetector()
        pattern_names = {p["name"] for p in detector.patterns}

        expected_patterns = {
            "aws_access_key_id",
            "aws_secret_access_key",
            "api_key_generic",
            "private_key",
            "github_token",
            "slack_token",
            "password_assignment",
            "database_connection_string",
        }

        for expected in expected_patterns:
            assert expected in pattern_names, f"Pattern {expected} not found"


class TestSecretDetectorFileSupport:
    """Tests for file extension support."""

    def test_supported_extensions(self):
        """Test supported file extensions."""
        detector = SecretDetector()
        supported = detector.SUPPORTED_EXTENSIONS

        assert ".tf" in supported
        assert ".tfvars" in supported
        assert ".yaml" in supported
        assert ".yml" in supported
        assert ".json" in supported
        assert ".env" in supported

    def test_should_scan_tf_file(self):
        """Test that .tf files are scanned."""
        detector = SecretDetector()
        assert detector._should_scan_file(Path("test.tf"))

    def test_should_scan_tfvars_file(self):
        """Test that .tfvars files are scanned."""
        detector = SecretDetector()
        assert detector._should_scan_file(Path("test.tfvars"))

    def test_should_scan_tfvars_template(self):
        """Test that .tfvars.template files are scanned."""
        detector = SecretDetector()
        assert detector._should_scan_file(Path("test.tfvars.template"))

    def test_should_scan_yaml_file(self):
        """Test that .yaml files are scanned."""
        detector = SecretDetector()
        assert detector._should_scan_file(Path("test.yaml"))

    def test_should_scan_json_file(self):
        """Test that .json files are scanned."""
        detector = SecretDetector()
        assert detector._should_scan_file(Path("test.json"))

    def test_should_scan_env_file(self):
        """Test that .env files are scanned."""
        detector = SecretDetector()
        assert detector._should_scan_file(Path(".env"))

    def test_should_not_scan_binary_file(self):
        """Test that binary files are not scanned."""
        detector = SecretDetector()
        assert not detector._should_scan_file(Path("test.png"))


class TestSecretDetectorAllowMarkers:
    """Tests for allow marker detection."""

    def test_nosec_marker(self):
        """Test # nosec marker."""
        detector = SecretDetector()
        assert detector._is_allowed_line("password = secret  # nosec")

    def test_example_marker(self):
        """Test # example marker."""
        detector = SecretDetector()
        assert detector._is_allowed_line("api_key = xxx  # example")

    def test_dummy_marker(self):
        """Test # dummy marker."""
        detector = SecretDetector()
        assert detector._is_allowed_line("token = abc  # dummy")

    def test_no_marker(self):
        """Test line without marker."""
        detector = SecretDetector()
        assert not detector._is_allowed_line("password = secret123")


class TestSecretDetectorPlaceholderDetection:
    """Tests for placeholder detection."""

    def test_placeholder_with_angle_brackets(self):
        """Test placeholder with angle brackets."""
        detector = SecretDetector()
        assert detector._is_placeholder("<YOUR_API_KEY>")

    def test_placeholder_with_example(self):
        """Test placeholder containing 'example'."""
        detector = SecretDetector()
        assert detector._is_placeholder("example_key_123")

    def test_placeholder_with_dummy(self):
        """Test placeholder containing 'dummy'."""
        detector = SecretDetector()
        assert detector._is_placeholder("dummy_token")

    def test_real_secret_not_placeholder(self):
        """Test that real secrets are not marked as placeholders."""
        detector = SecretDetector()
        # Use real-looking secrets without placeholder words
        assert not detector._is_placeholder("SuperSecretPassword123!")
        assert not detector._is_placeholder("sk_live_abcdefghijklmnopqrstuvwxyz")


class TestPatternDetection:
    """Tests for individual pattern detection."""

    @pytest.fixture
    def detector(self):
        """Create a detector for testing."""
        return SecretDetector(min_severity=Severity.INFO)

    def test_password_detection(self, detector, tmp_path):
        """Test password detection."""
        test_file = tmp_path / "test.tf"
        test_file.write_text('password = "SuperSecret123!"')

        findings = detector.scan_file(test_file)
        password_findings = [
            f for f in findings if "password" in f.pattern_name.lower()
        ]
        assert len(password_findings) > 0

    def test_aws_access_key_detection(self, detector, tmp_path):
        """Test AWS access key detection."""
        test_file = tmp_path / "test.tf"
        # Use a key without placeholder words like "EXAMPLE"
        test_file.write_text('aws_access_key = "AKIAIOSFODNN7ABCD123"')

        findings = detector.scan_file(test_file)
        aws_findings = [f for f in findings if "aws" in f.pattern_name.lower()]
        assert len(aws_findings) > 0

    def test_private_key_detection(self, detector, tmp_path):
        """Test private key detection."""
        test_file = tmp_path / "test.tf"
        test_file.write_text("-----BEGIN RSA PRIVATE KEY-----")

        findings = detector.scan_file(test_file)
        key_findings = [f for f in findings if "private_key" in f.pattern_name.lower()]
        assert len(key_findings) > 0

    def test_github_token_detection(self, detector, tmp_path):
        """Test GitHub token detection."""
        test_file = tmp_path / "test.tf"
        # Use a token without placeholder patterns
        test_file.write_text(
            'github_token = "ghp_1234567890abcdef1234567890abcdef123456"'
        )

        findings = detector.scan_file(test_file)
        github_findings = [f for f in findings if "github" in f.pattern_name.lower()]
        assert len(github_findings) > 0


class TestSecretDetectorScanning:
    """Tests for file and directory scanning."""

    @pytest.fixture
    def detector(self):
        """Create a detector for testing."""
        return SecretDetector(min_severity=Severity.INFO)

    def test_scan_nonexistent_file(self, detector):
        """Test scanning nonexistent file."""
        findings = detector.scan_file(Path("/nonexistent/file.tf"))
        assert len(findings) == 0

    def test_scan_empty_file(self, detector, tmp_path):
        """Test scanning empty file."""
        test_file = tmp_path / "empty.tf"
        test_file.write_text("")

        findings = detector.scan_file(test_file)
        assert len(findings) == 0

    def test_scan_file_with_no_secrets(self, detector, tmp_path):
        """Test scanning file with no secrets."""
        test_file = tmp_path / "clean.tf"
        test_file.write_text('variable "region" { default = "us-west-2" }')

        findings = detector.scan_file(test_file)
        assert len(findings) == 0

    def test_scan_directory(self, detector, tmp_path):
        """Test scanning directory."""
        (tmp_path / "file1.tf").write_text('password = "secret123"')
        (tmp_path / "file2.tf").write_text('api_key = "key123"')

        findings = detector.scan_directory(tmp_path)
        assert len(findings) > 0


class TestSecretDetectorSeverityFiltering:
    """Tests for severity level filtering."""

    def test_min_severity_error(self, tmp_path):
        """Test filtering with ERROR minimum severity."""
        detector = SecretDetector(min_severity=Severity.ERROR)

        test_file = tmp_path / "test.tf"
        test_file.write_text('password = "SuperSecret123!"')

        findings = detector.scan_file(test_file)
        for finding in findings:
            assert finding.severity == Severity.ERROR


class TestSecretDetectorSummary:
    """Tests for summary generation."""

    def test_empty_summary(self):
        """Test summary with no findings."""
        detector = SecretDetector()
        summary = detector.get_summary()

        assert summary["total_findings"] == 0
        assert summary["error_count"] == 0
        assert summary["warn_count"] == 0
        assert summary["info_count"] == 0

    def test_summary_with_findings(self, tmp_path):
        """Test summary with findings."""
        detector = SecretDetector(min_severity=Severity.INFO)

        test_file = tmp_path / "test.tf"
        test_file.write_text('password = "SuperSecret123!"')

        detector.findings = detector.scan_file(test_file)
        summary = detector.get_summary()

        assert summary["total_findings"] > 0
        assert summary["files_scanned"] == 1


class TestCreateTestFiles:
    """Tests for test file creation."""

    def test_create_test_files(self, tmp_path):
        """Test creating test files."""
        create_test_files(tmp_path)

        assert (tmp_path / "test_secrets.tf").exists()
        assert (tmp_path / "test_secrets.yaml").exists()
        assert (tmp_path / "test_secrets.json").exists()
        assert (tmp_path / "test_secrets.env").exists()
        assert (tmp_path / "clean.tf").exists()


class TestRunTestMode:
    """Tests for test mode execution."""

    def test_test_mode_runs(self):
        """Test that test mode runs successfully."""
        result = run_test_mode()
        assert result == 0


class TestMainFunction:
    """Tests for main function."""

    def test_main_no_args(self):
        """Test main with no arguments."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["detect_secrets.py"]):
                main()
        assert exc_info.value.code == 2

    def test_main_help(self):
        """Test main with --help."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["detect_secrets.py", "--help"]):
                main()
        assert exc_info.value.code == 0

    def test_main_test_mode(self):
        """Test main with --test-mode."""
        with patch("sys.argv", ["detect_secrets.py", "--test-mode"]):
            result = main()
        assert result == 0

    def test_main_scan_clean_file(self, tmp_path):
        """Test main scanning clean file."""
        test_file = tmp_path / "clean.tf"
        test_file.write_text('variable "region" { default = "us-west-2" }')

        with patch("sys.argv", ["detect_secrets.py", str(test_file)]):
            result = main()
        assert result == 0

    def test_main_scan_file_with_secrets(self, tmp_path):
        """Test main scanning file with secrets."""
        test_file = tmp_path / "secrets.tf"
        test_file.write_text('password = "SuperSecret123!"')

        with patch("sys.argv", ["detect_secrets.py", str(test_file)]):
            result = main()
        assert result == 1

    def test_main_exit_zero(self, tmp_path):
        """Test main with --exit-zero flag."""
        test_file = tmp_path / "secrets.tf"
        test_file.write_text('password = "SuperSecret123!"')

        with patch("sys.argv", ["detect_secrets.py", "--exit-zero", str(test_file)]):
            result = main()
        assert result == 0

    def test_main_json_format(self, tmp_path):
        """Test main with JSON format output."""
        test_file = tmp_path / "clean.tf"
        test_file.write_text('variable "region" { default = "us-west-2" }')

        with patch(
            "sys.argv", ["detect_secrets.py", "--format", "json", str(test_file)]
        ):
            result = main()
        assert result == 0


class TestIntegration:
    """Integration tests for the complete workflow."""

    def test_full_workflow_with_test_files(self, tmp_path):
        """Test full workflow with generated test files."""
        create_test_files(tmp_path)

        detector = SecretDetector(min_severity=Severity.INFO)
        findings = detector.scan_directory(tmp_path)

        assert len(findings) > 0

        file_names = {f.file_path.name for f in findings}
        assert "test_secrets.tf" in file_names
        assert "test_secrets.yaml" in file_names

        clean_findings = [f for f in findings if f.file_path.name == "clean.tf"]
        assert len(clean_findings) == 0

    def test_summary_accuracy(self, tmp_path):
        """Test that summary accurately reflects findings."""
        create_test_files(tmp_path)

        detector = SecretDetector(min_severity=Severity.INFO)
        detector.findings = detector.scan_directory(tmp_path)
        summary = detector.get_summary()

        assert summary["total_findings"] > 0
        assert summary["files_scanned"] > 0

        total = summary["error_count"] + summary["warn_count"] + summary["info_count"]
        assert total == summary["total_findings"]


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def detector(self):
        """Create a detector for testing."""
        return SecretDetector(min_severity=Severity.INFO)

    def test_binary_file_handling(self, detector, tmp_path):
        """Test handling of binary files."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03")

        findings = detector.scan_file(test_file)
        assert len(findings) == 0

    def test_unicode_file_handling(self, detector, tmp_path):
        """Test handling of files with unicode."""
        test_file = tmp_path / "test.tf"
        test_file.write_text('password = "日本語パスワード123"', encoding="utf-8")

        findings = detector.scan_file(test_file)
        assert len(findings) > 0

    def test_very_long_line(self, detector, tmp_path):
        """Test handling of very long lines."""
        test_file = tmp_path / "test.tf"
        long_secret = "A" * 1000
        test_file.write_text(f'password = "{long_secret}"')

        findings = detector.scan_file(test_file)
        assert len(findings) > 0
        for finding in findings:
            assert len(finding.matched_text) <= 53

    def test_multiple_secrets_same_line(self, detector, tmp_path):
        """Test multiple secrets on same line."""
        test_file = tmp_path / "test.tf"
        test_file.write_text('config = { password = "secret123", api_key = "key456" }')

        findings = detector.scan_file(test_file)
        assert len(findings) > 0

    def test_empty_password(self, detector, tmp_path):
        """Test empty password not detected."""
        test_file = tmp_path / "test.tf"
        test_file.write_text('password = ""')

        findings = detector.scan_file(test_file)
        password_findings = [
            f for f in findings if "password" in f.pattern_name.lower()
        ]
        assert len(password_findings) == 0

    def test_short_password(self, detector, tmp_path):
        """Test short password not detected."""
        test_file = tmp_path / "test.tf"
        test_file.write_text('password = "123"')

        findings = detector.scan_file(test_file)
        password_findings = [
            f for f in findings if "password" in f.pattern_name.lower()
        ]
        assert len(password_findings) == 0


class TestFalsePositives:
    """Tests for false positive handling."""

    @pytest.fixture
    def detector(self):
        """Create a detector for testing."""
        return SecretDetector(min_severity=Severity.INFO)

    def test_placeholder_not_detected(self, detector, tmp_path):
        """Test that placeholders are not detected."""
        test_file = tmp_path / "test.tf"
        test_file.write_text("""
password = "<YOUR_PASSWORD_HERE>"
api_key = "{{API_KEY}}"
""")

        findings = detector.scan_file(test_file)
        assert len(findings) == 0

    def test_example_values_not_detected(self, detector, tmp_path):
        """Test that example values are not detected."""
        test_file = tmp_path / "test.tf"
        test_file.write_text("""
# example values
password = "example_password"
""")

        findings = detector.scan_file(test_file)
        assert len(findings) == 0
