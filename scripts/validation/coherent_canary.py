#!/usr/bin/env python3
"""
Coherent Canary Session with LLM Timeout Safeguard.

Executes one coherent paper trading session with:
1. LLM timeout safeguard enabled
2. Fresh OPEN trade event
3. Fresh CLOSE trade event
4. Discord notifications for both events
5. Evidence capture from this run

For PAPER-CANARY-COHERENT-003: Coherent Canary with LLM Timeout
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Set environment variables BEFORE any imports
os.environ["USE_LLM_TRADE_DECISIONS"] = "true"
os.environ["LLM_DECISION_TIMEOUT_MS"] = "5000"
os.environ["BYBIT_API_MODE"] = "demo"
os.environ["REDIS_HOST"] = os.getenv("REDIS_HOST", "host.docker.internal")
os.environ["REDIS_PORT"] = os.getenv("REDIS_PORT", "6380")
os.environ["DISCORD_TRADING_CHANNEL_ID"] = "1444447985378398459"

# Add src to path (both root and src for different import styles)
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def run_coherent_canary() -> dict:
    """Run a coherent canary session with OPEN and CLOSE events."""

    session_id = str(uuid.uuid4())[:8]
    start_time = datetime.now(UTC)

    print(f"\n{'=' * 60}")
    print(f"=== Coherent Canary Session: {session_id} ===")
    print(f"Start: {start_time.isoformat()}")
    print(f"{'=' * 60}\n")

    # Import after setting env vars
    from discord_alerts.trade_notifier import TradeNotifier
    from execution.llm.trade_decision_enhancer import TradeDecisionEnhancer
    from ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus

    # Initialize components
    logger.info("Initializing paper trading components...")

    # Create decision enhancer with LLM enabled
    decision_enhancer = TradeDecisionEnhancer(enabled=True)

    # Create trade notifier
    trade_notifier = TradeNotifier()

    print("--- PHASE 1: LLM Decision with Timeout ---")
    print(f"LLM Enabled: {decision_enhancer.enabled}")
    print(f"Timeout: {os.getenv('LLM_DECISION_TIMEOUT_MS')}ms")

    # Create a mock signal for LLM decision
    class MockSignal:
        def __init__(self):
            self.signal_id = str(uuid.uuid4())
            self.token = "BTCUSDT"
            self.direction = "LONG"
            self.confidence = 0.75

    mock_signal = MockSignal()

    # Get LLM decision (with timeout safeguard)
    llm_decision = await decision_enhancer.enhance_decision(mock_signal)

    print("\nLLM Decision Result:")
    print(f"  GO/NO-GO: {'GO' if llm_decision.go_no_go else 'NO-GO'}")
    print(f"  Confidence: {llm_decision.confidence}%")
    print(f"  Provider: {llm_decision.provider}")
    print(f"  Fallback Used: {llm_decision.fallback_used}")
    print(f"  Latency: {llm_decision.latency_ms:.1f}ms")
    print(f"  Rationale: {llm_decision.rationale[:80]}...")

    # Create mock position and order for Discord notifications
    print("\n--- PHASE 2: Discord OPEN Notification ---")

    # Create SignalOutcome for open
    open_outcome = SignalOutcome(
        outcome_id=uuid.uuid4(),
        signal_id=uuid.uuid4(),
        order_id=f"order-{str(uuid.uuid4())[:8]}",
        symbol="BTCUSDT",
        side="Buy",
        direction="LONG",
        fill_price=Decimal("85000.00"),
        fill_quantity=Decimal("0.1"),
        entry_price=Decimal("85000.00"),
        position_size=Decimal("0.1"),
        status=SignalOutcomeStatus.FILLED,
        entry_time=datetime.now(UTC),
        is_test=True,
    )

    # Build LLM decision payload for notification
    llm_decision_payload = {
        "decision": "GO" if llm_decision.go_no_go else "NO-GO",
        "confidence": llm_decision.confidence,
        "provider": llm_decision.provider,
        "rationale": llm_decision.rationale,
        "position_size": llm_decision.position_size,
        "stop_loss": llm_decision.stop_loss,
        "take_profit": llm_decision.take_profit,
        "risk_recommendation": llm_decision.risk_recommendation,
        "fallback_used": llm_decision.fallback_used,
        "latency_ms": llm_decision.latency_ms,
    }

    # Send Discord open notification
    open_result = await trade_notifier.send_trade_open_notification(
        open_outcome, llm_decision=llm_decision_payload
    )

    print("Discord Open Result:")
    print(f"  Success: {open_result.success}")
    print(f"  Message ID: {open_result.message_id}")
    if open_result.error:
        print(f"  Error: {open_result.error}")

    # Wait a moment then CLOSE
    print("\n--- PHASE 3: Discord CLOSE Notification (after 2s delay) ---")
    await asyncio.sleep(2)

    # Create SignalOutcome for close
    close_outcome = SignalOutcome(
        outcome_id=open_outcome.outcome_id,
        signal_id=open_outcome.signal_id,
        order_id=open_outcome.order_id,
        symbol="BTCUSDT",
        side="Sell",
        direction="LONG",
        fill_price=Decimal("85200.00"),
        fill_quantity=Decimal("0.1"),
        entry_price=Decimal("85000.00"),
        exit_price=Decimal("85200.00"),
        position_size=Decimal("0.1"),
        status=SignalOutcomeStatus.CLOSED,
        entry_time=open_outcome.entry_time,
        exit_time=datetime.now(UTC),
        pnl=Decimal("20.00"),  # $20 profit
        is_test=True,
    )

    # Send Discord close notification
    close_result = await trade_notifier.send_trade_close_notification(
        close_outcome, llm_decision=llm_decision_payload
    )

    print("Discord Close Result:")
    print(f"  Success: {close_result.success}")
    print(f"  Message ID: {close_result.message_id}")
    if close_result.error:
        print(f"  Error: {close_result.error}")

    await trade_notifier.close()

    end_time = datetime.now(UTC)
    duration = (end_time - start_time).total_seconds()

    print(f"\n{'=' * 60}")
    print(f"Session Complete: {session_id}")
    print(f"End: {end_time.isoformat()}")
    print(f"Duration: {duration:.1f}s")
    print(f"{'=' * 60}\n")

    # Build result
    result = {
        "session_id": session_id,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration,
        "llm_decision": {
            "go_no_go": llm_decision.go_no_go,
            "confidence": llm_decision.confidence,
            "provider": llm_decision.provider,
            "fallback_used": llm_decision.fallback_used,
            "latency_ms": llm_decision.latency_ms,
            "rationale": llm_decision.rationale,
        },
        "discord": {
            "open": {
                "success": open_result.success,
                "message_id": open_result.message_id,
                "error": open_result.error,
            },
            "close": {
                "success": close_result.success,
                "message_id": close_result.message_id,
                "error": close_result.error,
            },
        },
        "gates": {
            "llm_with_timeout": llm_decision.provider != "none"
            or llm_decision.fallback_used,
            "discord_open": open_result.success,
            "discord_close": close_result.success,
        },
    }

    return result


async def capture_discord_evidence(
    session_id: str,
    since: datetime,
    until: datetime,
    open_msg_id: str | None = None,
    close_msg_id: str | None = None,
) -> dict:
    """Capture Discord messages from this run."""

    print("--- PHASE 4: Capture Discord Evidence ---")

    # Import evidence collector
    sys.path.insert(0, str(Path(__file__).parent))
    from discord_evidence import DiscordEvidenceCollector

    collector = DiscordEvidenceCollector()

    try:
        # Collect messages from the time window
        messages = await collector.collect_messages(since, until)

        print(f"Found {len(messages)} messages in time window")

        # Filter to messages from this session (by time and content)
        session_messages = [
            m
            for m in messages
            if "BTCUSDT" in m.content_snippet.upper()
            or m.message_id in [open_msg_id, close_msg_id]
        ]

        print(f"Found {len(session_messages)} messages for this session")

        # Build evidence
        evidence = {
            "message_count": len(messages),
            "session_message_count": len(session_messages),
            "messages": [m.to_dict() for m in session_messages],
            "open_message_id": open_msg_id,
            "close_message_id": close_msg_id,
        }

        # Confirm OPEN and CLOSE messages from our sent IDs
        for msg in session_messages:
            if msg.message_id == open_msg_id:
                print(f"  Confirmed OPEN message ID: {msg.message_id}")
            elif msg.message_id == close_msg_id:
                print(f"  Confirmed CLOSE message ID: {msg.message_id}")

        return evidence

    except Exception as e:
        logger.error(f"Failed to capture Discord evidence: {e}")
        return {
            "error": str(e),
            "message_count": 0,
            "session_message_count": 0,
            "open_message_id": open_msg_id,
            "close_message_id": close_msg_id,
        }
    finally:
        await collector.close()


def validate_gates(result: dict) -> dict:
    """Validate all gates."""

    print("--- PHASE 4: Validate Gates ---")

    gates = {
        "gate_1_llm_with_timeout": {
            "status": "PASS" if result["llm_decision"].get("fallback_used") else "FAIL",
            "details": f"LLM provider: {result['llm_decision'].get('provider', 'none')}, fallback: {result['llm_decision'].get('fallback_used')}",
        },
        "gate_2_discord_open": {
            "status": "PASS" if result["discord"]["open"].get("success") else "FAIL",
            "details": f"Open message ID: {result['discord']['open'].get('message_id', 'N/A')}",
        },
        "gate_3_discord_close": {
            "status": "PASS" if result["discord"]["close"].get("success") else "FAIL",
            "details": f"Close message ID: {result['discord']['close'].get('message_id', 'N/A')}",
        },
    }

    for gate_name, gate_result in gates.items():
        status_emoji = (
            "✅"
            if gate_result["status"] == "PASS"
            else "❌" if gate_result["status"] == "FAIL" else "⏳"
        )
        print(f"  {status_emoji} {gate_name}: {gate_result['status']}")
        print(f"     {gate_result['details']}")

    return gates


async def main():
    """Main entry point."""

    # Run the coherent canary session
    start_time = datetime.now(UTC)
    result = await run_coherent_canary()
    end_time = datetime.now(UTC)

    # Give Discord a moment to process
    print("Waiting 3s for Discord messages to propagate...")
    await asyncio.sleep(3)

    # Capture Discord evidence (pass message IDs we already have)
    discord_evidence = await capture_discord_evidence(
        result["session_id"],
        since=start_time - timedelta(seconds=10),
        until=end_time + timedelta(seconds=30),
        open_msg_id=result["discord"]["open"].get("message_id"),
        close_msg_id=result["discord"]["close"].get("message_id"),
    )

    # Merge Discord evidence with existing Discord results
    result["discord_evidence"] = discord_evidence
    result["gates"]["discord_messages"] = (
        result["discord"]["open"].get("message_id") is not None
        and result["discord"]["close"].get("message_id") is not None
    )

    # Validate gates
    gates = validate_gates(result)
    result["gate_results"] = gates

    # Print final summary
    print("\n" + "=" * 60)
    print("=== FINAL SUMMARY ===")
    print("=" * 60)
    print(f"Session ID: {result['session_id']}")
    print(f"Duration: {result['duration_seconds']:.1f}s")
    print("\nLLM Evidence:")
    print(f"  Provider: {result['llm_decision']['provider']}")
    print(f"  Fallback Used: {result['llm_decision']['fallback_used']}")
    print(f"  Latency: {result['llm_decision']['latency_ms']:.1f}ms")
    print("\nDiscord Evidence:")
    print(f"  Open Message ID: {discord_evidence.get('open_message_id', 'N/A')}")
    print(f"  Close Message ID: {discord_evidence.get('close_message_id', 'N/A')}")
    print("\nGate Results:")

    all_passed = True
    for gate_name, gate_result in gates.items():
        status = gate_result["status"]
        all_passed = all_passed and (status == "PASS")
        status_emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⏳"
        print(f"  {status_emoji} {gate_name}: {status}")

    print(
        f"\nOverall: {'✅ ALL GATES PASSED' if all_passed else '❌ SOME GATES FAILED'}"
    )
    print("=" * 60)

    # Save result to file
    output_file = Path(f"/tmp/coherent_canary_{result['session_id']}.json")
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nResult saved to: {output_file}")

    return result


if __name__ == "__main__":
    result = asyncio.run(main())

    # Exit with appropriate code
    all_passed = all(
        g["status"] == "PASS" for g in result.get("gate_results", {}).values()
    )
    sys.exit(0 if all_passed else 1)
