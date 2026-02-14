#!/usr/bin/env python3
"""
Configure Grafana InfluxDB datasource via API.
This script creates the InfluxDB datasource in Grafana when provisioning
is not available.
"""

import json
import os
import sys
import urllib.error
import urllib.request

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://host.docker.internal:3001")
GRAFANA_ADMIN_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_ADMIN_PASSWORD = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin")
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://chiseai-influxdb:18087")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "chiseai")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "chiseai")


def create_datasource():
    """Create InfluxDB datasource in Grafana via API."""

    datasource_config = {
        "name": "ChiseAI InfluxDB",
        "type": "influxdb",
        "access": "proxy",
        "url": INFLUXDB_URL,
        "isDefault": True,
        "jsonData": {
            "version": "Flux",
            "organization": INFLUXDB_ORG,
            "defaultBucket": INFLUXDB_BUCKET,
            "tlsSkipVerify": True,
        },
        "secureJsonData": {"token": INFLUXDB_TOKEN},
        "uid": "chiseai-influxdb",
    }

    req = urllib.request.Request(
        f"{GRAFANA_URL}/api/datasources",
        data=json.dumps(datasource_config).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    # Add basic auth
    import base64

    credentials = base64.b64encode(
        f"{GRAFANA_ADMIN_USER}:{GRAFANA_ADMIN_PASSWORD}".encode()
    ).decode()
    req.add_header("Authorization", f"Basic {credentials}")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"SUCCESS: Datasource created with ID: {result.get('id')}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        if e.code == 409:
            print("INFO: Datasource already exists (409 Conflict)")
            return True
        print(f"ERROR: HTTP {e.code}: {error_body}")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_datasource():
    """Test the datasource health."""

    req = urllib.request.Request(
        f"{GRAFANA_URL}/api/datasources/uid/chiseai-influxdb/health", method="GET"
    )

    import base64

    credentials = base64.b64encode(
        f"{GRAFANA_ADMIN_USER}:{GRAFANA_ADMIN_PASSWORD}".encode()
    ).decode()
    req.add_header("Authorization", f"Basic {credentials}")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"Datasource health: {result}")
            return result.get("status") == "OK"
    except Exception as e:
        print(f"Health check failed: {e}")
        return False


def list_datasources():
    """List all datasources."""

    req = urllib.request.Request(f"{GRAFANA_URL}/api/datasources", method="GET")

    import base64

    credentials = base64.b64encode(
        f"{GRAFANA_ADMIN_USER}:{GRAFANA_ADMIN_PASSWORD}".encode()
    ).decode()
    req.add_header("Authorization", f"Basic {credentials}")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"Current datasources: {json.dumps(result, indent=2)}")
            return result
    except Exception as e:
        print(f"List datasources failed: {e}")
        return []


if __name__ == "__main__":
    print("=== Grafana InfluxDB Datasource Configuration ===")
    print(f"Grafana URL: {GRAFANA_URL}")
    print(f"InfluxDB URL: {INFLUXDB_URL}")
    print(f"InfluxDB Org: {INFLUXDB_ORG}")
    print(f"InfluxDB Bucket: {INFLUXDB_BUCKET}")
    print(f"Token set: {'Yes' if INFLUXDB_TOKEN else 'No (will fail)'}")
    print()

    if not INFLUXDB_TOKEN:
        print("ERROR: INFLUXDB_TOKEN environment variable is required")
        sys.exit(1)

    print("Creating datasource...")
    if create_datasource():
        print("\nListing datasources...")
        list_datasources()
        print("\nTesting datasource health...")
        if test_datasource():
            print("\n✓ Datasource is healthy and ready to use")
            sys.exit(0)
        else:
            print("\n⚠ Datasource created but health check failed")
            sys.exit(1)
    else:
        print("\n✗ Failed to create datasource")
        sys.exit(1)
