#!/usr/bin/env python3
"""Position Safety Hotfix - Close E2E Test Positions on Bybit Demo.

This script inspects the Bybit demo account for any open positions left by
E2E tests and force-closes them immediately.

For SAFETY-001: Position Safety Hotfix
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add src and repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "src"))


class PositionSafetyHotfix:
    """Position safety hotfix executor."""

    # Test symbols to check
    TEST_SYMBOLS = ["BTCUSDT", "ETHUSDT"]

    def __init__(self) -> None:
        """Initialize the hotfix executor."""
        self.hotfix_id = f"SAFETY-001-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        self.start_time = datetime.now(UTC)
        self.evidence: dict[str, Any] = {
            "hotfix_id": self.hotfix_id,
            "start_time": self.start_time.isoformat(),
            "inspection": {
                "symbols_checked": [],
                "open_positions_found": [],
            },
            "close_execution": {
                "orders_placed": [],
                "close_results": [],
            },
            "verification": {
                "positions_after_close": [],
                "account_flat": False,
                "verification_timestamp": None,
            },
            "discord": {
                "channel": "#trading",
                "message_id": None,
                "timestamp": None,
                "content_summary": None,
            },
            "errors": [],
        }
        self.demo_connector = None

    async def run(self) -> dict[str, Any]:
        """Run the position safety hotfix.

        Returns:
            Evidence dictionary with all results
        """
        logger.info(f"=== Starting Position Safety Hotfix: {self.hotfix_id} ===")

        try:
            # Step 1: Initialize Bybit demo connector
            await self._initialize_connector()

            # Step 2: Inspect positions
            await self._inspect_positions()

            # Step 3: Close any open positions
            open_positions = self.evidence["inspection"]["open_positions_found"]
            if open_positions:
                logger.warning(
                    f"Found {len(open_positions)} open position(s) - closing immediately"
                )
                for position in open_positions:
                    await self._close_position(position)
            else:
                logger.info("No open positions found - account is already flat")

            # Step 4: Verify account is flat
            await self._verify_flat()

            # Step 5: Send Discord notification
            await self._send_discord_notification()

            # Mark hotfix as successful
            self.evidence["status"] = "SUCCESS"
            self.evidence["end_time"] = datetime.now(UTC).isoformat()

        except Exception as e:
            logger.error(f"Position safety hotfix failed: {e}", exc_info=True)
            self.evidence["status"] = "FAILED"
            self.evidence["errors"].append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": str(e),
                    "type": type(e).__name__,
                }
            )

        finally:
            # Cleanup
            await self._cleanup()
            # Save evidence
            await self._save_evidence()

        logger.info(
            f"=== Position Safety Hotfix Complete: {self.evidence['status']} ==="
        )
        return self.evidence

    async def _initialize_connector(self) -> None:
        """Initialize Bybit demo connector."""
        logger.info("Initializing Bybit demo connector...")

        from data.exchange.bybit_connector import BybitConfig, BybitConnector
        from execution.connectors.bybit_demo_connector import BybitDemoConnector

        # Check for demo credentials
        demo_api_key = os.environ.get("BYBIT_DEMO_API_KEY")
        demo_api_secret = os.environ.get("BYBIT_DEMO_API_SECRET")

        if not demo_api_key or not demo_api_secret:
            raise ValueError(
                "BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET must be set in environment"
            )

        # Create config with demo mode
        config = BybitConfig(
            api_key=demo_api_key,
            api_secret=demo_api_secret,
            demo=True,
            testnet=False,
        )

        # Create connector
        connector = BybitConnector(config)
        await connector.connect()

        # Create demo connector
        self.demo_connector = BybitDemoConnector(connector)

        # Verify connection with a simple API call (don't require WebSocket for safety hotfix)
        try:
            ticker = await self.demo_connector.connector.get_ticker("BTCUSDT")
            if not ticker or ticker.get("retCode") != 0:
                raise ConnectionError(f"Bybit demo API test failed: {ticker}")
        except Exception as e:
            raise ConnectionError(f"Bybit demo connection failed: {e}")

        logger.info(
            f"✓ Bybit demo connector initialized - "
            f"endpoint={self.demo_connector.provenance.endpoint}, "
            f"api_key={self.demo_connector.provenance.api_key_prefix}..."
        )

        self.evidence["connector"] = {
            "initialized": True,
            "endpoint": self.demo_connector.provenance.endpoint,
            "api_key_prefix": self.demo_connector.provenance.api_key_prefix,
            "healthy": True,
        }

    async def _inspect_positions(self) -> None:
        """Inspect Bybit demo account for open positions."""
        logger.info("Inspecting positions...")

        self.evidence["inspection"]["symbols_checked"] = self.TEST_SYMBOLS.copy()

        for symbol in self.TEST_SYMBOLS:
            try:
                # Get position info from Bybit API
                positions_data = await self.demo_connector.connector.get_positions(
                    symbol=symbol
                )

                # Parse position data
                result = positions_data.get("result", {})
                position_list = result.get("list", [])

                for position in position_list:
                    size = position.get("size", "0")
                    side = position.get("side", "")

                    # Check if position is open (size != 0)
                    if size and float(size) != 0:
                        position_info = {
                            "symbol": symbol,
                            "position_size": float(size),
                            "side": side.lower(),
                            "entry_price": float(position.get("avgPrice", 0)),
                            "unrealized_pnl": float(position.get("unrealisedPnl", 0)),
                            "leverage": position.get("leverage", "1"),
                            "position_value": float(position.get("positionValue", 0)),
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                        self.evidence["inspection"]["open_positions_found"].append(
                            position_info
                        )
                        logger.warning(
                            f"Found open position: {symbol} {side} {size} "
                            f"@ {position.get('avgPrice', 'N/A')}"
                        )

            except Exception as e:
                logger.error(f"Error inspecting position for {symbol}: {e}")
                self.evidence["errors"].append(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "symbol": symbol,
                        "error": f"Inspection failed: {str(e)}",
                    }
                )

        open_count = len(self.evidence["inspection"]["open_positions_found"])
        logger.info(f"Inspection complete - {open_count} open position(s) found")

    async def _close_position(self, position: dict[str, Any]) -> None:
        """Close an open position.

        Args:
            position: Position dictionary with symbol, side, position_size
        """
        symbol = position["symbol"]
        side = position["side"]
        size = position["position_size"]

        logger.info(f"Closing position: {symbol} {side} {size}")

        # Determine close side (opposite of position side)
        close_side = "sell" if side == "buy" or side == "long" else "buy"

        try:
            # Place market order to close position
            close_result = await self.demo_connector.connector.close_position_market(
                symbol=symbol,
                side=close_side,
                quantity=abs(size),
            )

            # Record order placement
            order_info = {
                "order_id": close_result.get("order_id"),
                "symbol": symbol,
                "side": close_side,
                "quantity": abs(size),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self.evidence["close_execution"]["orders_placed"].append(order_info)

            # Record close result
            close_info = {
                "order_id": close_result.get("order_id"),
                "symbol": symbol,
                "status": close_result.get("status"),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self.evidence["close_execution"]["close_results"].append(close_info)

            logger.info(
                f"✓ Position closed: Order {close_result.get('order_id')} - "
                f"Status: {close_result.get('status')}"
            )

        except Exception as e:
            error_msg = f"Failed to close position {symbol}: {e}"
            logger.error(error_msg)
            self.evidence["errors"].append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "symbol": symbol,
                    "error": error_msg,
                }
            )
            raise

    async def _verify_flat(self) -> None:
        """Verify account is flat (no open positions)."""
        logger.info("Verifying account is flat...")

        all_flat = True
        verification_timestamp = datetime.now(UTC).isoformat()

        for symbol in self.TEST_SYMBOLS:
            try:
                positions_data = await self.demo_connector.connector.get_positions(
                    symbol=symbol
                )
                result = positions_data.get("result", {})
                position_list = result.get("list", [])

                for position in position_list:
                    size = position.get("size", "0")
                    size_float = float(size) if size else 0.0

                    position_after = {
                        "symbol": symbol,
                        "position_size": size_float,
                        "verified_flat": size_float == 0,
                        "timestamp": verification_timestamp,
                    }
                    self.evidence["verification"]["positions_after_close"].append(
                        position_after
                    )

                    if size_float != 0:
                        all_flat = False
                        logger.error(f"Position still open: {symbol} size={size}")

            except Exception as e:
                logger.error(f"Error verifying position for {symbol}: {e}")
                all_flat = False

        self.evidence["verification"]["account_flat"] = all_flat
        self.evidence["verification"]["verification_timestamp"] = verification_timestamp

        if all_flat:
            logger.info("✓ Account verified flat - no open positions")
        else:
            logger.error("✗ Account NOT flat - some positions still open")

    async def _send_discord_notification(self) -> None:
        """Send Discord notification about position close."""
        logger.info("Sending Discord notification...")

        webhook_url = os.environ.get("DISCORD_TRADING_WEBHOOK_URL") or os.environ.get(
            "DISCORD_WEBHOOK_URL"
        )

        if not webhook_url:
            logger.warning("Discord webhook not configured - skipping notification")
            self.evidence["discord"]["error"] = "Webhook not configured"
            return

        try:
            import aiohttp

            # Build notification content
            open_positions = self.evidence["inspection"]["open_positions_found"]
            orders_placed = self.evidence["close_execution"]["orders_placed"]
            account_flat = self.evidence["verification"]["account_flat"]

            if open_positions:
                positions_text = "\n".join(
                    [
                        f"• {p['symbol']} {p['side']} {p['position_size']}"
                        for p in open_positions
                    ]
                )
                orders_text = "\n".join(
                    [f"• {o['order_id']} ({o['symbol']})" for o in orders_placed]
                )
                description = (
                    f"**Positions Closed:**\n{positions_text}\n\n"
                    f"**Close Orders:**\n{orders_text}\n\n"
                    f"**Account Flat:** {'✓ Yes' if account_flat else '✗ No'}\n"
                    f"**Reason:** E2E test cleanup"
                )
                title = "🛡️ Position Safety Hotfix - Positions Closed"
                color = 0x00FF00 if account_flat else 0xFF0000
            else:
                description = "No open positions found. Account was already flat."
                title = "🛡️ Position Safety Hotfix - No Action Needed"
                color = 0x00FF00

            embed = {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.now(UTC).isoformat(),
                "footer": {"text": f"Hotfix ID: {self.hotfix_id}"},
                "fields": [
                    {"name": "Hotfix ID", "value": self.hotfix_id, "inline": True},
                    {
                        "name": "Symbols Checked",
                        "value": ", ".join(self.TEST_SYMBOLS),
                        "inline": True,
                    },
                ],
            }

            payload = {"embeds": [embed]}

            # Send webhook with wait=true to get message ID
            if "?" in webhook_url:
                webhook_url_with_wait = f"{webhook_url}&wait=true"
            else:
                webhook_url_with_wait = f"{webhook_url}?wait=true"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url_with_wait, json=payload
                ) as response:
                    timestamp = datetime.now(UTC).isoformat()

                    if response.status in (200, 204):
                        message_id = None
                        if response.status == 200:
                            try:
                                response_data = await response.json()
                                message_id = response_data.get("id")
                            except Exception:
                                pass

                        self.evidence["discord"]["message_id"] = (
                            str(message_id) if message_id else "sent"
                        )
                        self.evidence["discord"]["timestamp"] = timestamp
                        self.evidence["discord"]["content_summary"] = title

                        logger.info(
                            f"✓ Discord notification sent: message_id={message_id}"
                        )
                    else:
                        error_text = await response.text()
                        self.evidence["discord"]["error"] = (
                            f"HTTP {response.status}: {error_text[:200]}"
                        )
                        logger.warning(
                            f"Discord notification failed: HTTP {response.status}"
                        )

        except Exception as e:
            error_msg = f"Failed to send Discord notification: {e}"
            logger.error(error_msg)
            self.evidence["discord"]["error"] = error_msg

    async def _cleanup(self) -> None:
        """Cleanup resources."""
        if self.demo_connector:
            try:
                await self.demo_connector.close()
                logger.info("✓ Bybit demo connector closed")
            except Exception as e:
                logger.error(f"Error closing connector: {e}")

    async def _save_evidence(self) -> None:
        """Save evidence to file."""
        evidence_dir = Path(__file__).parent.parent / "docs" / "validation" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        evidence_file = (
            evidence_dir / f"SAFETY-001-{self.hotfix_id.split('-')[-1]}-evidence.json"
        )

        with open(evidence_file, "w") as f:
            json.dump(self.evidence, f, indent=2, default=str)

        logger.info(f"Evidence saved to: {evidence_file}")


def format_evidence_yaml(evidence: dict[str, Any]) -> str:
    """Format evidence as YAML-like string for reporting.

    Args:
        evidence: Evidence dictionary

    Returns:
        Formatted YAML string
    """
    lines = [
        "position_safety_hotfix:",
        "  inspection:",
        f"    symbols_checked: {evidence['inspection']['symbols_checked']}",
        "    open_positions_found:",
    ]

    for pos in evidence["inspection"]["open_positions_found"]:
        lines.append(f"      - symbol: {pos['symbol']}")
        lines.append(f"        side: {pos['side']}")
        lines.append(f"        size: {pos['position_size']}")
        lines.append(f"        entry_price: {pos['entry_price']}")
        lines.append(f"        unrealized_pnl: {pos['unrealized_pnl']}")

    if not evidence["inspection"]["open_positions_found"]:
        lines.append("      []")

    lines.extend(
        [
            "  close_execution:",
            "    orders_placed:",
        ]
    )

    for order in evidence["close_execution"]["orders_placed"]:
        lines.append(f"      - order_id: {order['order_id']}")
        lines.append(f"        symbol: {order['symbol']}")
        lines.append(f"        side: {order['side']}")
        lines.append(f"        quantity: {order['quantity']}")
        lines.append(f"        timestamp: {order['timestamp']}")

    if not evidence["close_execution"]["orders_placed"]:
        lines.append("      []")

    lines.extend(
        [
            "    close_results:",
        ]
    )

    for result in evidence["close_execution"]["close_results"]:
        lines.append(f"      - order_id: {result['order_id']}")
        lines.append(f"        status: {result['status']}")
        lines.append(f"        timestamp: {result['timestamp']}")

    if not evidence["close_execution"]["close_results"]:
        lines.append("      []")

    lines.extend(
        [
            "  verification:",
            "    positions_after_close:",
        ]
    )

    for pos in evidence["verification"]["positions_after_close"]:
        lines.append(f"      - symbol: {pos['symbol']}")
        lines.append(f"        size: {pos['position_size']}")
        lines.append(f"        flat: {pos['verified_flat']}")

    if not evidence["verification"]["positions_after_close"]:
        lines.append("      []")

    lines.extend(
        [
            f"    account_flat: {evidence['verification']['account_flat']}",
            f"    verification_timestamp: {evidence['verification']['verification_timestamp']}",
            "  discord:",
            f"    channel: {evidence['discord']['channel']}",
            f"    message_id: {evidence['discord']['message_id']}",
            f"    timestamp: {evidence['discord']['timestamp']}",
            f"    content_summary: {evidence['discord']['content_summary']}",
        ]
    )

    return "\n".join(lines)


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    hotfix = PositionSafetyHotfix()
    evidence = await hotfix.run()

    # Print summary
    print("\n" + "=" * 70)
    print("POSITION SAFETY HOTFIX SUMMARY")
    print("=" * 70)
    print(f"Hotfix ID: {evidence['hotfix_id']}")
    print(f"Status: {evidence['status']}")
    print(f"Start Time: {evidence['start_time']}")
    print(f"End Time: {evidence.get('end_time', 'N/A')}")

    print("\n" + "-" * 70)
    print("EVIDENCE PACKET (YAML)")
    print("-" * 70)
    print(format_evidence_yaml(evidence))

    print("\n" + "-" * 70)
    print("DETAILED RESULTS")
    print("-" * 70)

    open_positions = evidence["inspection"]["open_positions_found"]
    if open_positions:
        print(f"\nOpen Positions Found: {len(open_positions)}")
        for pos in open_positions:
            print(
                f"  - {pos['symbol']} {pos['side']} {pos['position_size']} "
                f"@ ${pos['entry_price']:,.2f} (PnL: ${pos['unrealized_pnl']:,.4f})"
            )
    else:
        print("\n✓ No open positions found")

    orders = evidence["close_execution"]["orders_placed"]
    if orders:
        print(f"\nClose Orders Placed: {len(orders)}")
        for order in orders:
            print(f"  - Order ID: {order['order_id']}")
            print(f"    Symbol: {order['symbol']}")
            print(f"    Side: {order['side']}")
            print(f"    Quantity: {order['quantity']}")

    print(
        f"\nAccount Flat: {'✓ Yes' if evidence['verification']['account_flat'] else '✗ No'}"
    )
    print(f"Discord Message ID: {evidence['discord'].get('message_id', 'N/A')}")

    if evidence.get("errors"):
        print(f"\nErrors: {len(evidence['errors'])}")
        for err in evidence["errors"]:
            print(f"  - {err.get('error', 'Unknown')}")

    print("\n" + "=" * 70)

    return 0 if evidence["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
