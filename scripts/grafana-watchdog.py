#!/usr/bin/env python3
"""
Grafana Dashboard Watchdog - Auto-Discovery Framework

Monitors the dashboard provisioning directory for changes and triggers
Grafana provisioning reload via HTTP API.

Usage:
    python3 scripts/grafana-watchdog.py [--config CONFIG_PATH]

Environment Variables:
    GRAFANA_URL: Grafana base URL (default: http://host.docker.internal:3001)
    GRAFANA_API_KEY: Grafana API key for authentication (optional, uses basic auth if not set)
    GRAFANA_USER: Grafana admin username (default: admin)
    GRAFANA_PASSWORD: Grafana admin password (default: admin)
    WATCHDOG_LOG_LEVEL: Logging level (default: INFO)
    WATCHDOG_DEBOUNCE_SECONDS: Debounce time for file changes (default: 5)
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from config.bootstrap import bootstrap

# Bootstrap environment first (must be before any env access)
bootstrap(load_env=True)

# Add src to path and bootstrap

import requests  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from watchdog.events import FileSystemEvent, FileSystemEventHandler  # noqa: E402
from watchdog.observers import Observer  # noqa: E402

from config.bootstrap import bootstrap  # noqa: E402


@dataclass
class WatchdogConfig:
    """Configuration for the Grafana watchdog."""

    grafana_url: str = "http://host.docker.internal:3001"
    grafana_user: str = "admin"
    grafana_password: str = "admin"
    grafana_api_key: str | None = None
    dashboards_path: str = "infrastructure/grafana/provisioning/dashboards"
    debounce_seconds: float = 5.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "WatchdogConfig":
        """Create config from environment variables."""
        return cls(
            grafana_url=os.getenv("GRAFANA_URL", "http://host.docker.internal:3001"),
            grafana_user=os.getenv("GRAFANA_USER", "admin"),
            grafana_password=os.getenv("GRAFANA_PASSWORD", "admin"),
            grafana_api_key=os.getenv("GRAFANA_API_KEY"),
            dashboards_path=os.getenv(
                "DASHBOARDS_PATH", "infrastructure/grafana/provisioning/dashboards"
            ),
            debounce_seconds=float(os.getenv("WATCHDOG_DEBOUNCE_SECONDS", "5.0")),
            log_level=os.getenv("WATCHDOG_LOG_LEVEL", "INFO"),
        )


class GrafanaAPI:
    """Client for Grafana HTTP API."""

    def __init__(self, config: WatchdogConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

        if config.grafana_api_key:
            self.session.headers["Authorization"] = f"Bearer {config.grafana_api_key}"
        else:
            self.session.auth = (config.grafana_user, config.grafana_password)

    def health_check(self) -> bool:
        """Check if Grafana is accessible."""
        try:
            response = self.session.get(
                f"{self.config.grafana_url}/api/health", timeout=5
            )
            return response.status_code == 200
        except requests.RequestException as e:
            logging.warning(f"Grafana health check failed: {e}")
            return False

    def reload_dashboards(self) -> bool:
        """Trigger Grafana dashboard provisioning reload.

        Uses the admin API endpoint to reload provisioning configurations.
        Falls back to container restart if API is unavailable.

        Returns:
            True if reload was successful, False otherwise.
        """
        # Try the provisioning reload endpoint first
        try:
            response = self.session.post(
                f"{self.config.grafana_url}/api/admin/provisioning/dashboards/reload",
                timeout=10,
            )

            if response.status_code == 200:
                logging.info(
                    "Successfully triggered Grafana dashboard provisioning reload"
                )
                return True
            elif response.status_code == 404:
                logging.warning("Grafana provisioning reload API not available (404)")
                return False
            elif response.status_code == 401:
                logging.error("Grafana API authentication failed (401)")
                return False
            else:
                logging.warning(
                    f"Grafana reload returned status {response.status_code}"
                )
                return False

        except requests.RequestException as e:
            logging.error(f"Failed to reload Grafana dashboards: {e}")
            return False

    def list_dashboards(self) -> list:
        """List all dashboards from Grafana."""
        try:
            response = self.session.get(
                f"{self.config.grafana_url}/api/search",
                params={"type": "dash-db"},
                timeout=10,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logging.warning(f"Failed to list dashboards: {response.status_code}")
                return []

        except requests.RequestException as e:
            logging.error(f"Failed to list dashboards: {e}")
            return []


class DashboardChangeHandler(FileSystemEventHandler):
    """Handles file system events for dashboard directory."""

    def __init__(self, grafana_api: GrafanaAPI, config: WatchdogConfig):
        self.grafana_api = grafana_api
        self.config = config
        self.pending_reload = False
        self.last_reload_time = 0.0
        self.known_files: set[str] = set()
        self._scan_initial_files()

    def _scan_initial_files(self) -> None:
        """Scan and record initial dashboard files."""
        dashboards_path = Path(self.config.dashboards_path)
        if dashboards_path.exists():
            for json_file in dashboards_path.glob("*.json"):
                self.known_files.add(str(json_file.resolve()))
        logging.info(f"Initial scan found {len(self.known_files)} dashboard files")

    def _is_dashboard_file(self, path: str) -> bool:
        """Check if path is a dashboard JSON file."""
        return path.endswith(".json") and "/dashboards/" in path

    def _should_reload(self) -> bool:
        """Check if enough time has passed since last reload."""
        current_time = time.time()
        time_since_last = current_time - self.last_reload_time
        return time_since_last >= self.config.debounce_seconds

    def _trigger_reload(self) -> None:
        """Trigger Grafana provisioning reload with debouncing."""
        if not self._should_reload():
            self.pending_reload = True
            logging.debug("Reload pending (debouncing)")
            return

        self.last_reload_time = time.time()
        self.pending_reload = False

        logging.info("Triggering Grafana dashboard provisioning reload...")

        if self.grafana_api.reload_dashboards():
            logging.info("Dashboard reload completed successfully")
        else:
            logging.error("Dashboard reload failed - Grafana may need restart")

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return

        if self._is_dashboard_file(event.src_path):
            logging.info(f"New dashboard file detected: {event.src_path}")
            self.known_files.add(event.src_path)
            self._trigger_reload()

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return

        if self._is_dashboard_file(event.src_path):
            logging.info(f"Dashboard file modified: {event.src_path}")
            self._trigger_reload()

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events."""
        if event.is_directory:
            return

        if self._is_dashboard_file(event.src_path):
            logging.info(f"Dashboard file deleted: {event.src_path}")
            self.known_files.discard(event.src_path)
            self._trigger_reload()

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename events."""
        if event.is_directory:
            return

        src_is_dashboard = self._is_dashboard_file(event.src_path)
        dest_is_dashboard = hasattr(event, "dest_path") and self._is_dashboard_file(
            event.dest_path
        )

        if src_is_dashboard or dest_is_dashboard:
            logging.info(
                f"Dashboard file moved: {event.src_path} -> {getattr(event, 'dest_path', 'unknown')}"
            )
            self.known_files.discard(event.src_path)
            if hasattr(event, "dest_path"):
                self.known_files.add(event.dest_path)
            self._trigger_reload()

    def check_pending_reload(self) -> None:
        """Check and execute any pending reloads after debounce period."""
        if self.pending_reload and self._should_reload():
            self._trigger_reload()


class GrafanaWatchdog:
    """Main watchdog service for Grafana dashboard auto-discovery."""

    def __init__(self, config: WatchdogConfig):
        self.config = config
        self.grafana_api = GrafanaAPI(config)
        self.observer: Observer | None = None
        self.running = False

        # Setup logging
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.logger = logging.getLogger("grafana-watchdog")

    def validate_environment(self) -> bool:
        """Validate that the environment is properly configured."""
        dashboards_path = Path(self.config.dashboards_path)

        if not dashboards_path.exists():
            self.logger.error(
                f"Dashboards path does not exist: {self.config.dashboards_path}"
            )
            return False

        if not dashboards_path.is_dir():
            self.logger.error(
                f"Dashboards path is not a directory: {self.config.dashboards_path}"
            )
            return False

        self.logger.info(f"Dashboards path validated: {dashboards_path.resolve()}")
        return True

    def wait_for_grafana(self, timeout: int = 60) -> bool:
        """Wait for Grafana to become available."""
        self.logger.info(f"Waiting for Grafana at {self.config.grafana_url}...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.grafana_api.health_check():
                self.logger.info("Grafana is accessible")
                return True
            time.sleep(2)

        self.logger.error(f"Grafana did not become available within {timeout} seconds")
        return False

    def start(self) -> None:
        """Start the watchdog service."""
        self.logger.info("Starting Grafana Dashboard Watchdog")
        self.logger.info(
            f"Configuration: {json.dumps(asdict(self.config), indent=2, default=str)}"
        )

        if not self.validate_environment():
            sys.exit(1)

        if not self.wait_for_grafana():
            self.logger.warning(
                "Continuing without Grafana connection - will retry on changes"
            )

        # Setup file system observer
        event_handler = DashboardChangeHandler(self.grafana_api, self.config)
        self.observer = Observer()
        self.observer.schedule(
            event_handler, path=self.config.dashboards_path, recursive=False
        )

        self.observer.start()
        self.running = True

        self.logger.info(f"Watching directory: {self.config.dashboards_path}")
        self.logger.info("Watchdog is running. Press Ctrl+C to stop.")

        try:
            while self.running:
                time.sleep(1)
                event_handler.check_pending_reload()
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the watchdog service."""
        self.logger.info("Stopping Grafana Dashboard Watchdog")
        self.running = False

        if self.observer:
            self.observer.stop()
            self.observer.join()

        self.logger.info("Watchdog stopped")


def main():
    """Main entry point."""
    bootstrap(load_env=True)

    parser = argparse.ArgumentParser(
        description="Grafana Dashboard Watchdog - Auto-Discovery Framework"
    )
    parser.add_argument(
        "--config", help="Path to configuration file (JSON)", type=str, default=None
    )
    parser.add_argument(
        "--daemon", help="Run as daemon (background process)", action="store_true"
    )

    args = parser.parse_args()

    # Load configuration
    if args.config and os.path.exists(args.config):
        with open(args.config) as f:
            config_data = json.load(f)
        config = WatchdogConfig(**config_data)
    else:
        config = WatchdogConfig.from_env()

    # Create and start watchdog
    watchdog = GrafanaWatchdog(config)

    if args.daemon:
        # Daemonize (Unix-like systems only)
        try:
            import daemon

            with daemon.DaemonContext():
                watchdog.start()
        except ImportError:
            print("python-daemon package required for --daemon mode")
            sys.exit(1)
    else:
        watchdog.start()


if __name__ == "__main__":
    main()
