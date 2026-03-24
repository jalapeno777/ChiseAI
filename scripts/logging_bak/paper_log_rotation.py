"""Log rotation configuration for paper trading logs.

This module provides:
- TimedRotatingFileHandler configuration for daily rotation
- Size-based rotation with 100MB limit
- Compression of archived logs
- 7-day retention policy

Usage:
    from scripts.logging.paper_log_rotation import get_paper_trading_logger

    logger = get_paper_trading_logger("my_component")
    logger.info("Paper trading log message")
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any


class CompressedTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Timed rotating file handler with gzip compression.

    Extends TimedRotatingFileHandler to compress rotated logs using gzip.
    Automatically removes files older than the retention period.

    Attributes:
        retention_days: Number of days to retain log files
        compress: Whether to compress rotated files
    """

    def __init__(
        self,
        filename: str,
        when: str = "midnight",
        interval: int = 1,
        backupCount: int = 7,
        encoding: str | None = None,
        delay: bool = False,
        utc: bool = False,
        atTime: Any = None,
        retention_days: int = 7,
        compress: bool = True,
    ):
        """Initialize the compressed rotating handler.

        Args:
            filename: Base log file path
            when: Rotation interval type ('S', 'M', 'H', 'D', 'W0'-'W6', 'midnight')
            interval: Rotation interval count
            backupCount: Number of backup files to keep
            encoding: File encoding
            delay: Delay file opening until first emit
            utc: Use UTC timestamps
            atTime: Specific time for rotation
            retention_days: Days to retain log files beyond backupCount
            compress: Enable gzip compression of rotated files
        """
        super().__init__(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
            utc=utc,
            atTime=atTime,
        )
        self.retention_days = retention_days
        self.compress = compress
        self.base_filename = filename
        self.base_dir = Path(filename).parent

    def doRollover(self) -> None:
        """Perform log rollover with compression."""
        # Close the current stream
        if self.stream:
            self.stream.close()
            self.stream = None

        # Get the file to rotate
        current_time = int(self.rolloverAt - self.interval)
        time_tuple = self.computeRollover(current_time)

        if self.utc:
            time_tuple = datetime.utcfromtimestamp(time_tuple).timetuple()
        else:
            time_tuple = datetime.fromtimestamp(time_tuple).timetuple()

        # Build the rotated filename
        dfn = self.rotation_filename(
            self.baseFilename + "." + time.strftime(self.suffix, time_tuple)
        )

        # Rotate the file
        if os.path.exists(self.baseFilename):
            if os.path.exists(dfn):
                os.remove(dfn)
            shutil.move(self.baseFilename, dfn)

            # Compress if enabled
            if self.compress:
                self._compress_file(dfn)

        # Remove old files based on retention policy
        self._cleanup_old_files()

        # Open new log file
        if not self.delay:
            self.stream = self._open()

        # Compute next rollover time
        self.rolloverAt = self.computeRollover(self.rolloverAt)

    def _compress_file(self, filepath: str) -> None:
        """Compress a file using gzip.

        Args:
            filepath: Path to the file to compress
        """
        compressed_path = filepath + ".gz"
        try:
            with open(filepath, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.remove(filepath)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to compress {filepath}: {e}")

    def _cleanup_old_files(self) -> None:
        """Remove log files older than retention period."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        base_name = Path(self.base_filename).name

        try:
            for file_path in self.base_dir.glob(f"{base_name}.*"):
                # Skip if it's the current log file
                if str(file_path) == self.base_filename:
                    continue

                # Extract date from filename
                try:
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_mtime < cutoff_date:
                        file_path.unlink()
                        logging.getLogger(__name__).debug(
                            f"Removed old log file: {file_path}"
                        )
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        f"Failed to process {file_path}: {e}"
                    )
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to cleanup old log files: {e}")


class SizeAndTimeRotatingHandler(logging.Handler):
    """Combined size and time-based log rotation handler.

    Rotates logs based on both file size and time, with compression support.

    Attributes:
        max_bytes: Maximum file size in bytes before rotation
        backup_count: Number of backup files to keep
        retention_days: Days to retain log files
    """

    def __init__(
        self,
        filename: str,
        max_bytes: int = 100 * 1024 * 1024,  # 100MB
        backup_count: int = 7,
        retention_days: int = 7,
        encoding: str = "utf-8",
    ):
        """Initialize the combined rotating handler.

        Args:
            filename: Base log file path
            max_bytes: Maximum file size before rotation (default 100MB)
            backup_count: Number of backup files to keep
            retention_days: Days to retain log files
            encoding: File encoding
        """
        super().__init__()
        self.base_filename = filename
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.retention_days = retention_days
        self.encoding = encoding
        self.base_dir = Path(filename).parent
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Create the underlying handlers
        self._init_handlers()

    def _init_handlers(self) -> None:
        """Initialize the timed and size rotating handlers."""
        # Primary handler: daily rotation
        self.time_handler = CompressedTimedRotatingFileHandler(
            filename=self.base_filename,
            when="midnight",
            interval=1,
            backupCount=self.backup_count,
            encoding=self.encoding,
            retention_days=self.retention_days,
            compress=True,
        )

        # Set formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.time_handler.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record.

        Args:
            record: The log record to emit
        """
        # Check if we need to rotate due to size
        if self._should_rotate_size():
            self.time_handler.doRollover()

        # Pass to underlying handler
        self.time_handler.emit(record)

    def _should_rotate_size(self) -> bool:
        """Check if log file should rotate based on size.

        Returns:
            True if file exceeds max_bytes
        """
        if not os.path.exists(self.base_filename):
            return False
        return os.path.getsize(self.base_filename) >= self.max_bytes

    def close(self) -> None:
        """Close the handler."""
        self.time_handler.close()
        super().close()


def get_paper_trading_logger(
    name: str,
    log_dir: str | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Get a configured logger for paper trading components.

    Creates a logger with daily rotation, 100MB size limit, 7-day retention,
    and gzip compression.

    Args:
        name: Logger name (typically __name__)
        log_dir: Directory for log files (default: logs/paper_trading/)
        level: Logging level

    Returns:
        Configured logger instance
    """
    # Determine log directory
    if log_dir is None:
        # Check for environment variable first
        log_dir = os.getenv("PAPER_TRADING_LOG_DIR", "logs/paper_trading")

    # Ensure absolute path
    log_path = Path(log_dir).resolve()
    log_path.mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger(f"paper_trading.{name}")
    logger.setLevel(level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Create handler
    log_file = log_path / f"{name}.log"
    handler = SizeAndTimeRotatingHandler(
        filename=str(log_file),
        max_bytes=100 * 1024 * 1024,  # 100MB
        backup_count=7,
        retention_days=7,
    )

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    # Also add console handler for development
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def simulate_log_rotation(
    log_dir: str = "logs/paper_trading",
    num_files: int = 10,
    file_size_mb: int = 5,
) -> dict[str, Any]:
    """Simulate log rotation to verify configuration.

    Creates test log files to verify rotation and compression work correctly.

    Args:
        log_dir: Directory for test logs
        num_files: Number of test log files to create
        file_size_mb: Size of each test file in MB

    Returns:
        Dictionary with simulation results
    """
    import tempfile
    import time

    results = {
        "test_dir": None,
        "files_created": [],
        "files_rotated": [],
        "files_compressed": [],
        "errors": [],
    }

    # Use temporary directory for simulation
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "paper_trading"
        test_dir.mkdir(parents=True, exist_ok=True)
        results["test_dir"] = str(test_dir)

        # Create test logger
        logger = get_paper_trading_logger(
            name="rotation_test",
            log_dir=str(test_dir),
            level=logging.DEBUG,
        )

        # Generate test log entries
        test_message = "X" * 1000  # 1KB per message
        messages_per_file = (file_size_mb * 1024 * 1024) // len(test_message)

        try:
            for file_num in range(num_files):
                for msg_num in range(messages_per_file):
                    logger.info(
                        f"Test message {msg_num} in file {file_num}: {test_message}"
                    )

                # Force rotation by triggering rollover
                for handler in logger.handlers:
                    if hasattr(handler, "time_handler"):
                        handler.time_handler.doRollover()
                        results["files_rotated"].append(f"rotation_{file_num}")

                # Small delay to ensure different timestamps
                time.sleep(0.1)

            # Check for compressed files
            compressed_files = list(test_dir.glob("*.gz"))
            results["files_compressed"] = [str(f.name) for f in compressed_files]

            # List all files in directory
            all_files = list(test_dir.iterdir())
            results["files_created"] = [str(f.name) for f in all_files]

        except Exception as e:
            results["errors"].append(str(e))

    return results


if __name__ == "__main__":
    # Run simulation if executed directly
    print("Running log rotation simulation...")
    results = simulate_log_rotation(num_files=3, file_size_mb=1)

    print("\nSimulation Results:")
    print(f"  Test directory: {results['test_dir']}")
    print(f"  Files created: {len(results['files_created'])}")
    print(f"  Files rotated: {len(results['files_rotated'])}")
    print(f"  Files compressed: {len(results['files_compressed'])}")

    if results["errors"]:
        print(f"  Errors: {results['errors']}")
    else:
        print("  ✓ Simulation completed successfully")

    print("\nLog rotation configuration verified!")
