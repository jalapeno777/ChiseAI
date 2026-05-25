#!/usr/bin/env python3
"""Manual test script for pipeline alerting.

Simulates stale pipeline state and verifies alerts trigger correctly.
Usage: python3 test_stale_alert_simulation.py [--webhook-url URL]
"""

import os
import sys
from datetime import UTC, datetime
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, "/home/tacopants/projects/ChiseAI")

from scripts.monitoring.pipeline_alerts import AlertSeverity, PipelineAlertManager


def simulate_stale_pipeline():
    """Simulate a stale pipeline scenario and verify alerts."""
    print("=" * 60)
    print("PIPELINE ALERT SIMULATION TEST")
    print("=" * 60)

    # Create mock Redis
    mock_redis = Mock()

    # Test 1: Stale pipeline alert
    print("\n[TEST 1] Stale Pipeline Alert")
    print("-" * 40)

    mock_redis.hgetall.return_value = {
        "pipeline_status": "stale",
        "signals_15m": "0",
        "consumer_backlog": "0",
        "latest_signal_age_m": "10.5",
    }

    manager = PipelineAlertManager(redis_client=mock_redis)
    alerts_sent = []

    def capture_alert(severity, title, message, fields):
        alerts_sent.append(
            {"severity": severity, "title": title, "message": message, "fields": fields}
        )
        print(f"✓ ALERT SENT: [{severity.value.upper()}] {title}")
        print(f"  Message: {message}")
        print(f"  Fields: {fields}")

    with patch.object(manager, "_send_alert", side_effect=capture_alert):
        manager.check_and_alert()

    assert len(alerts_sent) == 1, "Expected 1 stale alert"
    assert alerts_sent[0]["severity"] == AlertSeverity.CRITICAL
    assert "Stale" in alerts_sent[0]["title"]
    print("  ✓ Stale pipeline alert triggered correctly")

    # Test 2: Recovery alert
    print("\n[TEST 2] Recovery Alert")
    print("-" * 40)

    # Reset and simulate recovery
    alerts_sent.clear()
    mock_redis.hgetall.side_effect = [
        {  # heartbeat - now healthy
            "pipeline_status": "healthy",
            "signals_15m": "12",
            "consumer_backlog": "0",
            "latest_signal_age_m": "2.0",
        },
        {  # last alert state - was stale
            "last_alert_type": "stale_pipeline",
            "last_alert_time": (
                datetime.now(UTC) - __import__("datetime").timedelta(minutes=10)
            ).isoformat(),
        },
    ]

    manager = PipelineAlertManager(redis_client=mock_redis)

    with patch.object(manager, "_send_alert", side_effect=capture_alert):
        manager.check_and_alert()

    assert len(alerts_sent) == 1, "Expected 1 recovery alert"
    assert alerts_sent[0]["severity"] == AlertSeverity.INFO
    assert "Recovered" in alerts_sent[0]["title"]
    print("  ✓ Recovery alert triggered correctly")

    # Test 3: High backlog alert
    print("\n[TEST 3] High Backlog Alert")
    print("-" * 40)

    alerts_sent.clear()
    mock_redis2 = Mock()
    mock_redis2.hgetall.return_value = {
        "pipeline_status": "healthy",
        "signals_15m": "5",
        "consumer_backlog": "15",  # Above threshold of 10
        "latest_signal_age_m": "2.0",
    }

    manager = PipelineAlertManager(redis_client=mock_redis2)

    with patch.object(manager, "_send_alert", side_effect=capture_alert):
        manager.check_and_alert()

    assert len(alerts_sent) == 1, "Expected 1 backlog alert"
    assert alerts_sent[0]["severity"] == AlertSeverity.WARNING
    assert "Backlog" in alerts_sent[0]["title"]
    print("  ✓ Backlog alert triggered correctly")

    # Test 4: Cooldown prevents spam
    print("\n[TEST 4] Alert Cooldown")
    print("-" * 40)

    alerts_sent.clear()
    mock_redis3 = Mock()
    mock_redis3.hgetall.return_value = {
        "pipeline_status": "stale",
        "signals_15m": "0",
        "consumer_backlog": "0",
        "latest_signal_age_m": "12.0",
    }

    manager = PipelineAlertManager(redis_client=mock_redis3)
    manager.last_alert_time = datetime.now(UTC) - __import__("datetime").timedelta(
        minutes=5
    )

    with patch.object(manager, "_send_alert", side_effect=capture_alert):
        manager.check_and_alert()

    assert len(alerts_sent) == 0, "Expected no alerts due to cooldown"
    print("  ✓ Cooldown prevented duplicate alerts")

    # Test 5: Threshold respected
    print("\n[TEST 5] Stale Threshold (5 minutes)")
    print("-" * 40)

    alerts_sent.clear()
    mock_redis4 = Mock()
    mock_redis4.hgetall.return_value = {
        "pipeline_status": "stale",
        "signals_15m": "0",
        "consumer_backlog": "0",
        "latest_signal_age_m": "3.0",  # Below 5 minute threshold
    }

    manager = PipelineAlertManager(redis_client=mock_redis4)
    manager.last_alert_time = None  # Reset cooldown

    with patch.object(manager, "_send_alert", side_effect=capture_alert):
        manager.check_and_alert()

    assert len(alerts_sent) == 0, "Expected no alerts below threshold"
    print("  ✓ Stale threshold respected (no alert at 3 min)")

    print("\n" + "=" * 60)
    print("ALL SIMULATION TESTS PASSED ✓")
    print("=" * 60)

    return True


def test_discord_webhook():
    """Test Discord webhook integration if URL provided."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        print("\n[SKIP] Discord webhook test - no DISCORD_WEBHOOK_URL set")
        return

    print("\n[TEST 6] Discord Webhook Integration")
    print("-" * 40)

    import requests

    payload = {
        "embeds": [
            {
                "title": "🧪 Pipeline Alert Test",
                "description": "This is a test message from pipeline_alerts.py simulation",
                "color": 0x00FF00,
                "fields": [
                    {"name": "Status", "value": "healthy", "inline": True},
                    {
                        "name": "Test",
                        "value": "Discord webhook integration",
                        "inline": True,
                    },
                ],
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ]
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        print("  ✓ Discord webhook test message sent successfully")
    except Exception as e:
        print(f"  ✗ Discord webhook failed: {e}")


if __name__ == "__main__":
    try:
        success = simulate_stale_pipeline()
        test_discord_webhook()

        if success:
            print("\n✓ Manual simulation completed successfully")
            sys.exit(0)
        else:
            print("\n✗ Manual simulation failed")
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error during simulation: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
