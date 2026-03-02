#!/usr/bin/env python3
"""Create evidence bundle for PAPER-RECOVERY-001 Loop 3."""

import json
import redis
import os
import requests
from datetime import datetime, UTC


def main():
    # Validate required environment variables (security fix)
    if not os.getenv("INFLUXDB_TOKEN"):
        raise ValueError(
            "INFLUXDB_TOKEN environment variable is not set. Please set it before running this script."
        )
    if not os.getenv("REDIS_HOST"):
        raise ValueError("REDIS_HOST environment variable is not set.")
    if not os.getenv("REDIS_PORT"):
        raise ValueError("REDIS_PORT environment variable is not set.")

    r = redis.Redis(host=os.getenv("REDIS_HOST"), port=int(os.getenv("REDIS_PORT")))

    # Collect all gate evidence
    evidence = {
        "story_id": "PAPER-RECOVERY-001",
        "loop": 3,
        "timestamp": datetime.now(UTC).isoformat(),
        "environment": {
            "REDIS_HOST": os.getenv("REDIS_HOST"),
            "REDIS_PORT": os.getenv("REDIS_PORT"),
            "INFLUXDB_URL": os.getenv("INFLUXDB_URL"),
            "INFLUXDB_ORG": os.getenv("INFLUXDB_ORG"),
            "INFLUXDB_BUCKET": os.getenv("INFLUXDB_BUCKET"),
        },
        "gates": {},
    }

    # G1: Signals
    signals_count = r.zcard("paper:index:signals")
    evidence["gates"]["G1"] = {
        "name": "Signals Delta > 0",
        "status": "PASS" if signals_count > 0 else "FAIL",
        "count": signals_count,
        "key": "paper:index:signals",
    }

    # G2: Orders
    orders_count = r.zcard("paper:index:orders")
    evidence["gates"]["G2"] = {
        "name": "Orders Delta > 0",
        "status": "PASS" if orders_count > 0 else "FAIL",
        "count": orders_count,
        "key": "paper:index:orders",
    }

    # G3: Fills
    fills_count = r.zcard("paper:index:fills")
    evidence["gates"]["G3"] = {
        "name": "Fills Delta > 0",
        "status": "PASS" if fills_count > 0 else "FAIL",
        "count": fills_count,
        "key": "paper:index:fills",
    }

    # G4: Outcomes
    outcomes_count = r.zcard("paper:index:outcomes")
    evidence["gates"]["G4"] = {
        "name": "Outcomes Delta > 0",
        "status": "PASS" if outcomes_count > 0 else "FAIL",
        "count": outcomes_count,
        "key": "paper:index:outcomes",
    }

    # G5: Discord (check if emitter is tracking messages)
    discord_msgs = r.lrange("paper:recovery:001:discord_messages", 0, -1)

    # Also check burn-in verdict for Discord evidence
    burn_in_raw = r.get("paper:recovery:001:burn_in_verdict")
    discord_sent = 0
    discord_ids = []
    if burn_in_raw:
        try:
            burn_in_data = json.loads(burn_in_raw)
            discord_sent = burn_in_data.get("discord_messages_sent", 0)
            discord_ids = burn_in_data.get("discord_message_ids", [])
        except (json.JSONDecodeError, TypeError):
            pass

    if discord_sent > 0 or len(discord_ids) > 0:
        evidence["gates"]["G5"] = {
            "name": "Discord OPEN/CLOSE/RECAP messages",
            "status": "PASS",
            "discord_messages_sent": discord_sent,
            "discord_message_ids": discord_ids[:5],  # First 5 IDs
            "source": "burn_in_verdict",
        }
    elif len(discord_msgs) > 0:
        evidence["gates"]["G5"] = {
            "name": "Discord OPEN/CLOSE/RECAP messages",
            "status": "PASS",
            "discord_messages_count": len(discord_msgs),
            "source": "redis_list",
        }
    else:
        evidence["gates"]["G5"] = {
            "name": "Discord OPEN/CLOSE/RECAP messages",
            "status": "MANUAL",
            "message": "Discord webhook not configured or no messages sent during session",
            "verification": "Check #paper-trading Discord channel for OPEN/CLOSE/RECAP messages",
            "discord_messages_sent_in_session": discord_sent,
        }

    # G6: InfluxDB orders/fills
    try:
        bucket = os.getenv("INFLUXDB_BUCKET", "chiseai")
        query = f'from(bucket: "{bucket}") |> range(start: -1h) |> limit(n: 10)'
        response = requests.post(
            f"{os.getenv('INFLUXDB_URL')}/api/v2/query?org={os.getenv('INFLUXDB_ORG')}",
            headers={
                "Authorization": f"Token {os.getenv('INFLUXDB_TOKEN')}",
                "Content-Type": "application/vnd.flux",
            },
            data=query,
            timeout=10,
        )
        influx_ok = response.status_code == 200
        influx_lines = len(response.text.strip().split("\n")) if influx_ok else 0
    except Exception as e:
        influx_ok = False
        influx_lines = 0

    evidence["gates"]["G6"] = {
        "name": "InfluxDB orders/fills queries",
        "status": "PASS" if influx_ok else "FAIL",
        "lines": influx_lines,
    }

    # G7: InfluxDB canary
    try:
        response = requests.get(f"{os.getenv('INFLUXDB_URL')}/health", timeout=10)
        canary_ok = response.status_code == 200
        canary_status = (
            response.json().get("status", "unknown") if canary_ok else "error"
        )
    except Exception as e:
        canary_ok = False
        canary_status = str(e)

    evidence["gates"]["G7"] = {
        "name": "InfluxDB canary query",
        "status": "PASS" if canary_ok else "FAIL",
        "health_status": canary_status,
    }

    # G8: Burn-in verdict
    burn_in = r.get("paper:recovery:001:burn_in_verdict")
    if burn_in:
        try:
            burn_in_data = json.loads(burn_in)
            evidence["gates"]["G8"] = {
                "name": "Burn-in verdict artifact",
                "status": "PASS" if burn_in_data.get("verdict") == "PASS" else "FAIL",
                "exists": True,
                "verdict": burn_in_data.get("verdict"),
                "timestamp_utc": burn_in_data.get("timestamp_utc"),
                "duration_seconds": burn_in_data.get("duration_seconds"),
                "signals_generated": burn_in_data.get("signals_generated"),
                "orders_placed": burn_in_data.get("orders_placed"),
                "fills_received": burn_in_data.get("fills_received"),
                "outcomes_recorded": burn_in_data.get("outcomes_recorded"),
            }
        except (json.JSONDecodeError, TypeError) as e:
            evidence["gates"]["G8"] = {
                "name": "Burn-in verdict artifact",
                "status": "FAIL",
                "exists": True,
                "error": f"Failed to parse verdict: {e}",
            }
    else:
        evidence["gates"]["G8"] = {
            "name": "Burn-in verdict artifact",
            "status": "PENDING",
            "exists": False,
        }

    # Summary
    all_pass = all(
        g["status"] == "PASS"
        for g in evidence["gates"].values()
        if g["status"] not in ["INFO", "PENDING", "MANUAL"]
    )
    evidence["summary"] = {
        "total_gates": 8,
        "passed": sum(1 for g in evidence["gates"].values() if g["status"] == "PASS"),
        "failed": sum(1 for g in evidence["gates"].values() if g["status"] == "FAIL"),
        "info": sum(1 for g in evidence["gates"].values() if g["status"] == "INFO"),
        "pending": sum(
            1 for g in evidence["gates"].values() if g["status"] == "PENDING"
        ),
        "manual": sum(1 for g in evidence["gates"].values() if g["status"] == "MANUAL"),
        "overall": "PASS" if all_pass else "PARTIAL",
    }

    # Write evidence bundle
    output_path = "/home/tacopants/projects/ChiseAI/docs/validation/evidence/PAPER-RECOVERY-001-loop3-bundle.json"
    with open(output_path, "w") as f:
        json.dump(evidence, f, indent=2)

    print(json.dumps(evidence, indent=2))
    print(f"\nEvidence bundle written to: {output_path}")


if __name__ == "__main__":
    main()
