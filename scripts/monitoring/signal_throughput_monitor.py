#!/usr/bin/env python3
"""Signal throughput monitor CLI tool.

Displays current throughput metrics, alerts on threshold violations,
and exports metrics for Grafana.

Usage:
    python3 signal_throughput_monitor.py --help
    python3 signal_throughput_monitor.py status
    python3 signal_throughput_monitor.py watch --interval 5
    python3 signal_throughput_monitor.py export --format json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any, TextIO

# Add src to path for imports
sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

from execution.signal_delivery.throughput_tracker import (
    ThroughputTracker,
    create_tracker,
)

logger = logging.getLogger(__name__)


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"


class ThroughputMonitorCLI:
    """CLI for monitoring signal throughput."""

    def __init__(
        self,
        tracker: ThroughputTracker | None = None,
        output: TextIO = sys.stdout,
        use_colors: bool = True,
    ):
        """Initialize CLI.

        Args:
            tracker: Throughput tracker instance
            output: Output stream
            use_colors: Whether to use ANSI colors
        """
        self.tracker = tracker or create_tracker()
        self.output = output
        self.use_colors = use_colors and sys.stdout.isatty()

    def _color(self, text: str, color: str) -> str:
        """Apply color to text if enabled.

        Args:
            text: Text to color
            color: Color code

        Returns:
            Colored text or plain text
        """
        if self.use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text

    def _print(self, text: str = "") -> None:
        """Print to output stream.

        Args:
            text: Text to print
        """
        self.output.write(text + "\n")

    def _format_throughput(self, spm: float) -> str:
        """Format throughput value with color.

        Args:
            spm: Signals per minute

        Returns:
            Formatted string
        """
        if spm < 1:
            return self._color(f"{spm:.2f}", Colors.RED)
        elif spm < 5:
            return self._color(f"{spm:.2f}", Colors.YELLOW)
        else:
            return self._color(f"{spm:.2f}", Colors.GREEN)

    def _format_latency(self, latency_ms: float, threshold: float = 500) -> str:
        """Format latency value with color.

        Args:
            latency_ms: Latency in milliseconds
            threshold: Threshold for coloring

        Returns:
            Formatted string
        """
        if latency_ms > threshold * 2:
            return self._color(f"{latency_ms:.2f}", Colors.RED)
        elif latency_ms > threshold:
            return self._color(f"{latency_ms:.2f}", Colors.YELLOW)
        else:
            return self._color(f"{latency_ms:.2f}", Colors.GREEN)

    def status(self, window: str = "5min") -> int:
        """Display current status.

        Args:
            window: Time window to display

        Returns:
            Exit code (0 = healthy, 1 = degraded, 2 = alert)
        """
        self._print(self._color("Signal Throughput Monitor", Colors.BOLD + Colors.CYAN))
        self._print("=" * 50)
        self._print()

        # Get metrics
        metrics = self.tracker.get_metrics(window)
        latencies = self.tracker.get_latency_percentiles(window)

        # Display throughput
        self._print(self._color(f"Throughput ({window})", Colors.BOLD))
        self._print(f"  Signals: {metrics.signals_count}")
        self._print(
            f"  Rate: {self._format_throughput(metrics.signals_per_minute)} signals/min"
        )
        self._print()

        # Display latency
        self._print(self._color(f"Latency ({window})", Colors.BOLD))
        self._print(f"  P50: {self._format_latency(latencies.p50_ms)} ms")
        self._print(f"  P95: {self._format_latency(latencies.p95_ms)} ms")
        self._print(f"  P99: {self._format_latency(latencies.p99_ms)} ms")
        self._print(f"  Min: {latencies.min_ms:.2f} ms")
        self._print(f"  Max: {latencies.max_ms:.2f} ms")
        self._print(f"  Avg: {latencies.avg_ms:.2f} ms")
        self._print(f"  Count: {latencies.count}")
        self._print()

        # Determine status
        if metrics.signals_per_minute < 1 or latencies.p95_ms > 1000:
            status_code = 2
            status_text = self._color("ALERT", Colors.RED)
        elif metrics.signals_per_minute < 5 or latencies.p95_ms > 500:
            status_code = 1
            status_text = self._color("DEGRADED", Colors.YELLOW)
        else:
            status_code = 0
            status_text = self._color("HEALTHY", Colors.GREEN)

        self._print(f"Status: {status_text}")

        return status_code

    def watch(
        self,
        interval: int = 5,
        window: str = "1min",
        threshold_spm: float = 1.0,
        threshold_p95_ms: float = 500.0,
    ) -> None:
        """Watch mode - continuously display metrics.

        Args:
            interval: Update interval in seconds
            window: Time window to display
            threshold_spm: Throughput threshold for alerts
            threshold_p95_ms: Latency threshold for alerts
        """
        self._print(
            self._color(
                "Signal Throughput Monitor - Watch Mode", Colors.BOLD + Colors.CYAN
            )
        )
        self._print(f"Interval: {interval}s | Window: {window}")
        self._print(f"Thresholds: {threshold_spm} spm / {threshold_p95_ms}ms p95")
        self._print("=" * 50)
        self._print()

        try:
            while True:
                # Clear screen
                if sys.stdout.isatty():
                    self._print("\033[2J\033[H")

                # Get metrics
                metrics = self.tracker.get_metrics(window)
                latencies = self.tracker.get_latency_percentiles(window)

                # Check thresholds
                throughput_check = self.tracker.check_throughput_threshold(
                    window, threshold_spm
                )
                latency_check = self.tracker.check_latency_threshold(
                    window, threshold_p95_ms
                )

                # Display header
                now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
                self._print(
                    self._color(
                        f"[{now}] Signal Throughput Monitor", Colors.BOLD + Colors.CYAN
                    )
                )
                self._print()

                # Display throughput
                self._print(self._color("Throughput", Colors.BOLD))
                self._print(f"  Signals: {metrics.signals_count}")
                self._print(
                    f"  Rate: {self._format_throughput(metrics.signals_per_minute)} signals/min"
                )
                if not throughput_check["passed"]:
                    self._print(
                        self._color(
                            f"  ⚠ ALERT: {throughput_check['message']}", Colors.RED
                        )
                    )
                self._print()

                # Display latency
                self._print(self._color("Latency", Colors.BOLD))
                self._print(f"  P50: {self._format_latency(latencies.p50_ms)} ms")
                self._print(
                    f"  P95: {self._format_latency(latencies.p95_ms, threshold_p95_ms)} ms"
                )
                self._print(f"  P99: {self._format_latency(latencies.p99_ms)} ms")
                if not latency_check["passed"]:
                    self._print(
                        self._color(
                            f"  ⚠ ALERT: {latency_check['message']}", Colors.RED
                        )
                    )
                self._print()

                # Status line
                if throughput_check["passed"] and latency_check["passed"]:
                    status = self._color("● HEALTHY", Colors.GREEN)
                elif not throughput_check["passed"] and not latency_check["passed"]:
                    status = self._color("● CRITICAL", Colors.RED)
                else:
                    status = self._color("● WARNING", Colors.YELLOW)

                self._print(f"Status: {status}")
                self._print()
                self._print(f"Refreshing in {interval}s... (Ctrl+C to exit)")

                time.sleep(interval)

        except KeyboardInterrupt:
            self._print()
            self._print("\nWatch mode stopped.")

    def export(
        self,
        format: str = "json",
        window: str | None = None,
    ) -> str:
        """Export metrics in specified format.

        Args:
            format: Export format (json, prometheus)
            window: Specific window to export (None = all)

        Returns:
            Exported data as string
        """
        if window:
            data = {
                "timestamp": datetime.now(UTC).isoformat(),
                "window": window,
                "throughput": self.tracker.get_metrics(window).to_dict(),
                "latency": self.tracker.get_latency_percentiles(window).to_dict(),
            }
        else:
            data = self.tracker.get_summary()

        if format == "json":
            return json.dumps(data, indent=2)
        elif format == "prometheus":
            return self._to_prometheus_format(data)
        else:
            raise ValueError(f"Unknown format: {format}")

    def _to_prometheus_format(self, data: dict[str, Any]) -> str:
        """Convert data to Prometheus exposition format.

        Args:
            data: Metrics data

        Returns:
            Prometheus format string
        """
        lines = []
        data.get("timestamp", datetime.now(UTC).isoformat())

        # Throughput metrics
        if "throughput" in data:
            for window, metrics in data["throughput"].items():
                lines.append(
                    f"# HELP chise_signal_throughput Signals per minute ({window})"
                )
                lines.append("# TYPE chise_signal_throughput gauge")
                lines.append(
                    f'chise_signal_throughput{{window="{window}"}} {metrics["signals_per_minute"]}'
                )
                lines.append(
                    f'chise_signal_count{{window="{window}"}} {metrics["signals_count"]}'
                )

        # Latency metrics
        if "latency" in data:
            for window, latencies in data["latency"].items():
                lines.append(
                    f"# HELP chise_signal_latency_ms Signal latency in ms ({window})"
                )
                lines.append("# TYPE chise_signal_latency_ms summary")
                lines.append(
                    f'chise_signal_latency_ms{{window="{window}",quantile="0.5"}} {latencies["p50_ms"]}'
                )
                lines.append(
                    f'chise_signal_latency_ms{{window="{window}",quantile="0.95"}} {latencies["p95_ms"]}'
                )
                lines.append(
                    f'chise_signal_latency_ms{{window="{window}",quantile="0.99"}} {latencies["p99_ms"]}'
                )
                lines.append(
                    f'chise_signal_latency_ms_count{{window="{window}"}} {latencies["count"]}'
                )

        return "\n".join(lines)

    def alert_check(
        self,
        window: str = "5min",
        min_spm: float = 1.0,
        max_p95_ms: float = 500.0,
    ) -> dict[str, Any]:
        """Check for alert conditions.

        Args:
            window: Time window to check
            min_spm: Minimum signals per minute
            max_p95_ms: Maximum p95 latency

        Returns:
            Alert status dictionary
        """
        throughput_check = self.tracker.check_throughput_threshold(window, min_spm)
        latency_check = self.tracker.check_latency_threshold(window, max_p95_ms)

        alerts = []
        if not throughput_check["passed"]:
            alerts.append(
                {
                    "type": "throughput_low",
                    "severity": "warning",
                    "message": throughput_check["message"],
                }
            )

        if not latency_check["passed"]:
            alerts.append(
                {
                    "type": "latency_high",
                    "severity": (
                        "warning"
                        if latency_check["actual_p95_ms"] < max_p95_ms * 2
                        else "critical"
                    ),
                    "message": latency_check["message"],
                }
            )

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "window": window,
            "alerts": alerts,
            "alert_count": len(alerts),
            "status": "alert" if alerts else "healthy",
        }


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command line arguments

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog="signal_throughput_monitor",
        description="Monitor signal throughput and latency",
    )

    parser.add_argument(
        "--redis-host",
        default="localhost",
        help="Redis host (default: localhost)",
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=6379,
        help="Redis port (default: 6379)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show current status")
    status_parser.add_argument(
        "--window",
        default="5min",
        choices=["1min", "5min", "15min"],
        help="Time window (default: 5min)",
    )

    # Watch command
    watch_parser = subparsers.add_parser("watch", help="Watch mode")
    watch_parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Update interval in seconds (default: 5)",
    )
    watch_parser.add_argument(
        "--window",
        default="1min",
        choices=["1min", "5min", "15min"],
        help="Time window (default: 1min)",
    )
    watch_parser.add_argument(
        "--threshold-spm",
        type=float,
        default=1.0,
        help="Throughput threshold in signals/min (default: 1.0)",
    )
    watch_parser.add_argument(
        "--threshold-p95",
        type=float,
        default=500.0,
        help="Latency threshold in ms (default: 500.0)",
    )

    # Export command
    export_parser = subparsers.add_parser("export", help="Export metrics")
    export_parser.add_argument(
        "--format",
        default="json",
        choices=["json", "prometheus"],
        help="Export format (default: json)",
    )
    export_parser.add_argument(
        "--window",
        choices=["1min", "5min", "15min"],
        help="Specific window to export (default: all)",
    )

    # Alert command
    alert_parser = subparsers.add_parser("alert", help="Check alert conditions")
    alert_parser.add_argument(
        "--window",
        default="5min",
        choices=["1min", "5min", "15min"],
        help="Time window (default: 5min)",
    )
    alert_parser.add_argument(
        "--min-spm",
        type=float,
        default=1.0,
        help="Minimum signals per minute (default: 1.0)",
    )
    alert_parser.add_argument(
        "--max-p95",
        type=float,
        default=500.0,
        help="Maximum p95 latency in ms (default: 500.0)",
    )

    args = parser.parse_args(argv)

    # Setup logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Create tracker
    tracker = create_tracker(
        redis_host=args.redis_host,
        redis_port=args.redis_port,
    )

    # Create CLI
    cli = ThroughputMonitorCLI(
        tracker=tracker,
        use_colors=not args.no_color,
    )

    # Execute command
    if args.command == "status":
        return cli.status(window=args.window)
    elif args.command == "watch":
        cli.watch(
            interval=args.interval,
            window=args.window,
            threshold_spm=args.threshold_spm,
            threshold_p95_ms=args.threshold_p95,
        )
        return 0
    elif args.command == "export":
        output = cli.export(format=args.format, window=args.window)
        print(output)
        return 0
    elif args.command == "alert":
        result = cli.alert_check(
            window=args.window,
            min_spm=args.min_spm,
            max_p95_ms=args.max_p95,
        )
        print(json.dumps(result, indent=2))
        return 1 if result["alert_count"] > 0 else 0
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
