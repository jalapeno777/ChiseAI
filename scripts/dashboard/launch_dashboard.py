#!/usr/bin/env python3
"""Launch dashboard server.

Starts the control plane dashboard server with configurable options.

Usage:
    python3 scripts/dashboard/launch_dashboard.py
    python3 scripts/dashboard/launch_dashboard.py --port 8080 --ws-port 8765
    python3 scripts/dashboard/launch_dashboard.py --test-mode

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def start_dashboard(
    host: str = "0.0.0.0",
    port: int = 8080,
    ws_port: int = 8765,
    test_mode: bool = False,
) -> None:
    """Start the dashboard server.

    Args:
        host: Host to bind
        port: HTTP port
        ws_port: WebSocket port
        test_mode: Run in test mode with mock data
    """
    from autonomous_control_plane.dashboard.server import DashboardServer

    if test_mode:
        logger.info("Starting dashboard in TEST MODE with mock data")
        # In test mode, we don't pass any components - server will use empty data
        server = DashboardServer(
            host=host,
            port=port,
            ws_port=ws_port,
        )
    else:
        logger.info("Starting dashboard with ACP components")
        # Import ACP components
        try:
            from autonomous_control_plane.components.circuit_breaker_registry import (
                CircuitBreakerRegistry,
            )
            from autonomous_control_plane.components.incident_manager import (
                IncidentManager,
            )
            from autonomous_control_plane.automation.controller import (
                AutomationController,
            )

            # Initialize components
            cb_registry = CircuitBreakerRegistry()
            incident_manager = IncidentManager()
            controller = AutomationController(trading_mode="paper")

            server = DashboardServer(
                host=host,
                port=port,
                ws_port=ws_port,
                circuit_breaker_registry=cb_registry,
                incident_manager=incident_manager,
                automation_controller=controller,
            )
        except Exception as e:
            logger.warning(f"Could not initialize ACP components: {e}")
            logger.info("Starting dashboard in fallback mode")
            server = DashboardServer(
                host=host,
                port=port,
                ws_port=ws_port,
            )

    # Start server
    await server.start()

    logger.info(f"Dashboard running at http://{host}:{port}")
    logger.info(f"WebSocket endpoint at ws://{host}:{ws_port}/acp-dashboard")
    logger.info("Press Ctrl+C to stop")

    # Wait for shutdown signal
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    await shutdown_event.wait()

    # Stop server
    await server.stop()
    logger.info("Dashboard stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Launch ChiseAI Control Plane Dashboard",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="HTTP port (default: 8080)",
    )
    parser.add_argument(
        "--ws-port",
        type=int,
        default=8765,
        help="WebSocket port (default: 8765)",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run in test mode with mock data",
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            start_dashboard(
                host=args.host,
                port=args.port,
                ws_port=args.ws_port,
                test_mode=args.test_mode,
            )
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error starting dashboard: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
