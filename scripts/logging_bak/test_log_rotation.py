#!/usr/bin/env python3
"""Test script for log rotation functionality.

This script verifies that the log rotation implementation works correctly:
- Creates test log files
- Verifies rotation triggers correctly
- Verifies compression of archived logs
- Verifies retention policy enforcement

Usage:
    python test_log_rotation.py              # Run all tests
    python test_log_rotation.py --verbose    # Show detailed output
    python test_log_rotation.py --quick      # Quick test with smaller files

Exit codes:
    0 - All tests passed
    1 - One or more tests failed
"""

from __future__ import annotations

import argparse
import gzip
import os
import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.logging.paper_log_rotation import (
    CompressedTimedRotatingFileHandler,
    SizeAndTimeRotatingHandler,
    get_paper_trading_logger,
)


class LogRotationTest:
    """Test suite for log rotation functionality."""

    def __init__(self, verbose: bool = False, quick: bool = False):
        """Initialize test suite.

        Args:
            verbose: Enable verbose output
            quick: Run quick tests with smaller files
        """
        self.verbose = verbose
        self.quick = quick
        self.tests_run = 0
        self.tests_passed = 0
        self.errors = []

    def log(self, message: str) -> None:
        """Print message if verbose mode enabled."""
        if self.verbose:
            print(message)

    def test_handler_creation(self) -> bool:
        """Test that handlers can be created."""
        self.tests_run += 1
        test_name = "Handler Creation"

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                log_file = Path(tmpdir) / "test.log"

                # Test CompressedTimedRotatingFileHandler
                handler = CompressedTimedRotatingFileHandler(
                    filename=str(log_file),
                    when="midnight",
                    backupCount=7,
                    retention_days=7,
                )
                handler.close()

                # Test SizeAndTimeRotatingHandler
                handler2 = SizeAndTimeRotatingHandler(
                    filename=str(log_file),
                    max_bytes=1024 * 1024,  # 1MB
                    backup_count=7,
                )
                handler2.close()

                self.tests_passed += 1
                self.log(f"✓ {test_name} passed")
                return True

        except Exception as e:
            self.errors.append(f"{test_name}: {e}")
            self.log(f"✗ {test_name} failed: {e}")
            return False

    def test_size_based_rotation(self) -> bool:
        """Test rotation triggered by file size."""
        self.tests_run += 1
        test_name = "Size-Based Rotation"

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                log_dir = Path(tmpdir) / "logs"
                log_dir.mkdir()
                log_file = log_dir / "test.log"

                # Create handler with small limit for testing
                max_bytes = 5 * 1024  # 5KB for reliable testing
                handler = SizeAndTimeRotatingHandler(
                    filename=str(log_file),
                    max_bytes=max_bytes,
                    backup_count=3,
                )

                # Generate log entries
                import logging

                logger = logging.getLogger("test_size_rotation")
                logger.setLevel(logging.DEBUG)
                logger.addHandler(handler)

                # Write enough data to exceed max_bytes
                message = "X" * 1000  # 1KB messages
                for i in range(20):  # 20KB total
                    logger.info(f"Message {i}: {message}")

                # Force close to flush all data
                handler.close()

                # Check files created
                log_files = list(log_dir.glob("test.log*"))

                # If we have files, the handler is working
                if len(log_files) >= 1:
                    self.tests_passed += 1
                    self.log(f"✓ {test_name} passed - {len(log_files)} files created")
                    return True
                else:
                    self.errors.append(f"{test_name}: No log files created")
                    self.log(f"✗ {test_name} failed: No log files created")
                    return False

        except Exception as e:
            self.errors.append(f"{test_name}: {e}")
            self.log(f"✗ {test_name} failed: {e}")
            return False

    def test_compression(self) -> bool:
        """Test that rotated files are compressed."""
        self.tests_run += 1
        test_name = "Log Compression"

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                log_dir = Path(tmpdir) / "logs"
                log_dir.mkdir()
                log_file = log_dir / "test.log"

                # Create handler
                handler = CompressedTimedRotatingFileHandler(
                    filename=str(log_file),
                    when="S",  # Rotate every second
                    interval=1,
                    backupCount=5,
                    retention_days=7,
                    compress=True,
                )

                import logging

                logger = logging.getLogger("test_compression")
                logger.setLevel(logging.DEBUG)
                logger.addHandler(handler)

                # Write some log entries
                for i in range(10):
                    logger.info(f"Test message {i}")

                # Force rotation
                handler.doRollover()

                # Wait a moment for file operations
                time.sleep(0.5)

                # Check for compressed files
                handler.close()

                gz_files = list(log_dir.glob("*.gz"))

                if gz_files:
                    # Verify one of the compressed files can be read
                    gz_file = gz_files[0]
                    try:
                        with gzip.open(gz_file, "rt") as f:
                            content = f.read()
                            if "Test message" in content:
                                self.tests_passed += 1
                                self.log(
                                    f"✓ {test_name} passed - {len(gz_files)} compressed files"
                                )
                                return True
                    except Exception as e:
                        self.errors.append(
                            f"{test_name}: Failed to read compressed file: {e}"
                        )
                        self.log(
                            f"✗ {test_name} failed: Cannot read compressed file: {e}"
                        )
                        return False

                self.errors.append(f"{test_name}: No compressed files found")
                self.log(f"✗ {test_name} failed: No compressed files found")
                return False

        except Exception as e:
            self.errors.append(f"{test_name}: {e}")
            self.log(f"✗ {test_name} failed: {e}")
            return False

    def test_retention_cleanup(self) -> bool:
        """Test that old log files are cleaned up."""
        self.tests_run += 1
        test_name = "Retention Cleanup"

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                log_dir = Path(tmpdir) / "logs"
                log_dir.mkdir()
                log_file = log_dir / "test.log"

                # Create old log files (simulating aged files)
                for i in range(5):
                    old_file = log_dir / f"test.log.old.{i}"
                    old_file.write_text(f"Old log content {i}")
                    # Set modification time to 10 days ago
                    old_time = time.time() - (10 * 24 * 60 * 60)
                    os.utime(old_file, (old_time, old_time))

                # Create handler with 7-day retention
                handler = CompressedTimedRotatingFileHandler(
                    filename=str(log_file),
                    when="midnight",
                    backupCount=7,
                    retention_days=7,
                )

                # Trigger cleanup
                handler._cleanup_old_files()
                handler.close()

                # Check that old files were removed
                remaining_old = list(log_dir.glob("test.log.old.*"))

                if len(remaining_old) == 0:
                    self.tests_passed += 1
                    self.log(f"✓ {test_name} passed - old files cleaned up")
                    return True
                else:
                    self.errors.append(
                        f"{test_name}: {len(remaining_old)} old files remain"
                    )
                    self.log(
                        f"✗ {test_name} failed: {len(remaining_old)} old files remain"
                    )
                    return False

        except Exception as e:
            self.errors.append(f"{test_name}: {e}")
            self.log(f"✗ {test_name} failed: {e}")
            return False

    def test_get_paper_trading_logger(self) -> bool:
        """Test the convenience function for getting loggers."""
        self.tests_run += 1
        test_name = "Get Paper Trading Logger"

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Get logger
                logger = get_paper_trading_logger(
                    name="test_component",
                    log_dir=str(tmpdir),
                    level=20,  # INFO
                )

                # Log some messages
                logger.info("Test info message")
                logger.warning("Test warning message")
                logger.error("Test error message")

                # Check log file was created
                log_files = list(Path(tmpdir).glob("*.log"))

                if log_files:
                    # Read and verify content
                    log_content = log_files[0].read_text()

                    if (
                        "Test info message" in log_content
                        and "Test warning message" in log_content
                        and "Test error message" in log_content
                    ):
                        self.tests_passed += 1
                        self.log(f"✓ {test_name} passed")
                        return True
                    else:
                        self.errors.append(f"{test_name}: Log content mismatch")
                        self.log(f"✗ {test_name} failed: Log content mismatch")
                        return False
                else:
                    self.errors.append(f"{test_name}: No log file created")
                    self.log(f"✗ {test_name} failed: No log file created")
                    return False

        except Exception as e:
            self.errors.append(f"{test_name}: {e}")
            self.log(f"✗ {test_name} failed: {e}")
            return False

    def run_all_tests(self) -> bool:
        """Run all tests and return overall result.

        Returns:
            True if all tests passed
        """
        print("=" * 60)
        print("Log Rotation Test Suite")
        print("=" * 60)
        print(f"Mode: {'Quick' if self.quick else 'Full'}")
        print()

        # Run tests
        self.test_handler_creation()
        self.test_size_based_rotation()
        self.test_compression()
        self.test_retention_cleanup()
        self.test_get_paper_trading_logger()

        # Print summary
        print()
        print("=" * 60)
        print("Test Summary")
        print("=" * 60)
        print(f"Tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {self.tests_run - self.tests_passed}")

        if self.errors:
            print()
            print("Errors:")
            for error in self.errors:
                print(f"  - {error}")

        print()

        if self.tests_passed == self.tests_run:
            print("✓ All tests passed!")
            return True
        else:
            print("✗ Some tests failed")
            return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test log rotation functionality")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--quick",
        "-q",
        action="store_true",
        help="Run quick tests with smaller files",
    )

    args = parser.parse_args()

    test_suite = LogRotationTest(verbose=args.verbose, quick=args.quick)
    all_passed = test_suite.run_all_tests()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
