#!/usr/bin/env python3
"""Phase 1: Orphan Position Remediation for PAPER-LLM-TIMEOUT-001.

Queries current open Bybit positions/orders and closes any orphan/open test positions safely.
Saves evidence to docs/tempmemories/PAPER-LLM-TIMEOUT-001-remediation.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from data.exchange.bybit_connector import BybitConnector


class PositionRemediation:
    """Remediates orphan positions on Bybit demo environment."""

    def __init__(self) -> None:
        """Initialize remediation tracker."""
        self.remediation_id = (
            f"PAPER-LLM-TIMEOUT-001-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        )
        self.evidence: dict[str, Any] = {
            "remediation_id": self.remediation_id,
            "story_id": "PAPER-LLM-TIMEOUT-001",
            "timestamp_start": datetime.now(UTC).isoformat(),
            "before_snapshot": {},
            "actions_taken": [],
            "after_snapshot": {},
            "errors": [],
        }
        self.connector: BybitConnector | None = None

    async def run(self) -> dict[str, Any]:
        """Execute full remediation workflow."""
        logger.info(f"=== Position Remediation Started: {self.remediation_id} ===")

        try:
            # Initialize connector with demo credentials
            self.connector = BybitConnector.from_env(load_env=True)
            await self.connector.connect()
            logger.info("Bybit connector initialized (demo mode)")

            # Phase 1a: Capture before snapshot
            await self._capture_before_snapshot()

            # Phase 1b: Close any open positions
            await self._close_open_positions()

            # Phase 1c: Capture after snapshot
            await self._capture_after_snapshot()

        except Exception as e:
            logger.error(f"Remediation failed: {e}")
            self.evidence["errors"].append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": str(e),
                    "type": type(e).__name__,
                }
            )
            raise
        finally:
            if self.connector:
                await self.connector.close()
                logger.info("Bybit connector closed")

        # Save evidence
        self.evidence["timestamp_end"] = datetime.now(UTC).isoformat()
        await self._save_evidence()

        logger.info(f"=== Position Remediation Complete: {self.remediation_id} ===")
        return self.evidence

    async def _capture_before_snapshot(self) -> None:
        """Capture snapshot of positions and orders before remediation."""
        logger.info("Capturing BEFORE snapshot...")

        try:
            # Get positions (need to specify settleCoin to get all positions)
            positions_response = await self.connector.get_positions(settle_coin="USDT")
            positions = positions_response.get("result", {}).get("list", [])

            # Get wallet balance
            balance_response = await self.connector.get_wallet_balance()

            self.evidence["before_snapshot"] = {
                "position_count": len(positions),
                "positions": [
                    {
                        "symbol": p.get("symbol"),
                        "side": p.get("side"),
                        "size": p.get("size"),
                        "entry_price": p.get("avgPrice"),
                        "unrealised_pnl": p.get("unrealisedPnl"),
                        "leverage": p.get("leverage"),
                        "position_value": p.get("positionValue"),
                    }
                    for p in positions
                    if float(p.get("size", 0)) != 0
                ],
                "wallet": {
                    "total_equity": balance_response.get("total_equity"),
                    "available_balance": balance_response.get("available_balance"),
                    "unrealized_pnl": balance_response.get("unrealized_pnl"),
                },
                "timestamp": datetime.now(UTC).isoformat(),
            }

            open_position_count = len(self.evidence["before_snapshot"]["positions"])
            logger.info(f"BEFORE: {open_position_count} open positions")

            for p in self.evidence["before_snapshot"]["positions"]:
                logger.info(
                    f"  - {p['symbol']} {p['side']}: size={p['size']}, pnl={p['unrealised_pnl']}"
                )

        except Exception as e:
            logger.error(f"Failed to capture before snapshot: {e}")
            self.evidence["errors"].append(
                {
                    "phase": "before_snapshot",
                    "error": str(e),
                }
            )
            raise

    async def _close_open_positions(self) -> None:
        """Close any open positions safely."""
        positions = self.evidence["before_snapshot"].get("positions", [])

        if not positions:
            logger.info("No open positions to close")
            self.evidence["actions_taken"].append(
                {
                    "action": "none",
                    "reason": "no_open_positions",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            return

        logger.info(f"Closing {len(positions)} open position(s)...")

        for position in positions:
            symbol = position.get("symbol")
            side = position.get("side")  # "Buy" = long, "Sell" = short
            size = float(position.get("size", 0))

            if size == 0:
                continue

            try:
                # Determine close side (opposite of position side)
                close_side = "Sell" if side == "Buy" else "Buy"

                logger.info(f"Closing {symbol} {side} position (size={size})...")

                result = await self.connector.close_position_market(
                    symbol=symbol,
                    side=close_side,
                    quantity=size,
                )

                self.evidence["actions_taken"].append(
                    {
                        "action": "close_position",
                        "symbol": symbol,
                        "original_side": side,
                        "close_side": close_side,
                        "size": size,
                        "order_id": result.get("order_id"),
                        "timestamp": datetime.now(UTC).isoformat(),
                        "status": "success",
                    }
                )

                logger.info(f"  Closed: order_id={result.get('order_id')}")

                # Small delay between closes
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Failed to close {symbol} position: {e}")
                self.evidence["actions_taken"].append(
                    {
                        "action": "close_position",
                        "symbol": symbol,
                        "original_side": side,
                        "size": size,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "status": "failed",
                        "error": str(e),
                    }
                )
                self.evidence["errors"].append(
                    {
                        "phase": "close_position",
                        "symbol": symbol,
                        "error": str(e),
                    }
                )

    async def _capture_after_snapshot(self) -> None:
        """Capture snapshot after remediation."""
        logger.info("Capturing AFTER snapshot...")

        try:
            # Get positions (need to specify settleCoin to get all positions)
            positions_response = await self.connector.get_positions(settle_coin="USDT")
            positions = positions_response.get("result", {}).get("list", [])

            # Filter to only non-zero positions
            open_positions = [p for p in positions if float(p.get("size", 0)) != 0]

            self.evidence["after_snapshot"] = {
                "position_count": len(open_positions),
                "positions": [
                    {
                        "symbol": p.get("symbol"),
                        "side": p.get("side"),
                        "size": p.get("size"),
                        "entry_price": p.get("avgPrice"),
                    }
                    for p in open_positions
                ],
                "timestamp": datetime.now(UTC).isoformat(),
            }

            logger.info(f"AFTER: {len(open_positions)} open positions remaining")

            if open_positions:
                logger.warning("WARNING: Some positions could not be closed:")
                for p in open_positions:
                    logger.warning(
                        f"  - {p.get('symbol')} {p.get('side')}: size={p.get('size')}"
                    )

        except Exception as e:
            logger.error(f"Failed to capture after snapshot: {e}")
            self.evidence["errors"].append(
                {
                    "phase": "after_snapshot",
                    "error": str(e),
                }
            )

    async def _save_evidence(self) -> None:
        """Save evidence to file."""
        evidence_path = Path("docs/tempmemories/PAPER-LLM-TIMEOUT-001-remediation.json")
        evidence_path.parent.mkdir(parents=True, exist_ok=True)

        with open(evidence_path, "w") as f:
            json.dump(self.evidence, f, indent=2)

        logger.info(f"Evidence saved to: {evidence_path}")


async def main() -> int:
    """Main entry point."""
    try:
        remediation = PositionRemediation()
        evidence = await remediation.run()

        # Print summary
        print("\n" + "=" * 60)
        print("POSITION REMEDIATION SUMMARY")
        print("=" * 60)
        print(f"Remediation ID: {evidence['remediation_id']}")
        print("\nBEFORE:")
        print(
            f"  Open positions: {evidence['before_snapshot'].get('position_count', 0)}"
        )
        print(f"  Open orders: {evidence['before_snapshot'].get('order_count', 0)}")
        print("\nAFTER:")
        print(
            f"  Open positions: {evidence['after_snapshot'].get('position_count', 0)}"
        )
        print(f"\nActions taken: {len(evidence['actions_taken'])}")

        for action in evidence["actions_taken"]:
            if action.get("action") == "close_position":
                print(
                    f"  - Closed {action['symbol']} {action['original_side']}: {action.get('order_id', 'N/A')}"
                )

        if evidence["errors"]:
            print(f"\nErrors: {len(evidence['errors'])}")
            for err in evidence["errors"]:
                print(
                    f"  - {err.get('phase', 'unknown')}: {err.get('error', 'unknown')}"
                )

        print(
            "\nEvidence saved to: docs/tempmemories/PAPER-LLM-TIMEOUT-001-remediation.json"
        )
        print("=" * 60)

        # Return 0 if flat, 1 if positions remain
        remaining = evidence["after_snapshot"].get("position_count", 0)
        return 0 if remaining == 0 else 1

    except Exception as e:
        logger.error(f"Remediation failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
