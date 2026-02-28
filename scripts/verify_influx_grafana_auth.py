#!/usr/bin/env python3
"""
Verification script for InfluxDB/Grafana authentication.

This script performs the verification steps required for G6/G7 evidence collection:
1. Verifies InfluxDB token authentication works
2. Verifies Grafana datasource health
3. Verifies InfluxDB queries return data

Usage:
    python3 scripts/verify_influx_grafana_auth.py [--token TOKEN]

Exit codes:
    0 - All verifications passed
    1 - InfluxDB ping failed
    2 - Grafana datasource health check failed
    3 - InfluxDB query failed
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Optional, Tuple


class AuthVerifier:
    """Verifies InfluxDB/Grafana authentication configuration."""

    def __init__(
        self,
        influx_url: str = "http://host.docker.internal:18087",
        grafana_url: str = "http://host.docker.internal:3001",
        token: Optional[str] = None,
        grafana_user: str = "admin",
        grafana_pass: str = "admin123",
        org: str = "chiseai",
        bucket: str = "chiseai",
    ):
        self.influx_url = influx_url.rstrip("/")
        self.grafana_url = grafana_url.rstrip("/")
        self.token = token
        self.grafana_user = grafana_user
        self.grafana_pass = grafana_pass
        self.org = org
        self.bucket = bucket

    def log(self, message: str, level: str = "INFO") -> None:
        """Print a log message."""
        print(f"[{level}] {message}")

    def _make_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        timeout: int = 10,
    ) -> Tuple[bool, str, int]:
        """Make an HTTP request and return (success, response_data, status_code)."""
        try:
            req = urllib.request.Request(url, method=method)
            if headers:
                for key, value in headers.items():
                    req.add_header(key, value)

            with urllib.request.urlopen(req, timeout=timeout) as response:
                return True, response.read().decode(), response.status
        except urllib.error.HTTPError as e:
            return False, e.read().decode(), e.code
        except Exception as e:
            return False, str(e), 0

    def verify_influxdb_ping(self) -> bool:
        """
        Verify InfluxDB ping with token.

        Expected: HTTP 204
        Command equivalent:
            curl -H "Authorization: Token $INFLUXDB_TOKEN" http://host.docker.internal:18087/ping
        """
        self.log("=" * 60)
        self.log("Verification 1: InfluxDB Ping with Token")
        self.log("=" * 60)

        if not self.token:
            self.log("No INFLUXDB_TOKEN provided", "ERROR")
            return False

        success, data, status = self._make_request(
            f"{self.influx_url}/ping",
            headers={"Authorization": f"Token {self.token}"},
        )

        if success and status == 204:
            self.log(f"✓ InfluxDB ping successful (HTTP {status})")
            return True
        else:
            self.log(f"✗ InfluxDB ping failed (HTTP {status}): {data}", "ERROR")
            return False

    def verify_grafana_health(self) -> bool:
        """
        Verify Grafana datasource health.

        Expected: {"status": "OK", "message": "..."}
        Command equivalent:
            curl -u admin:admin123 http://host.docker.internal:3001/api/datasources/uid/chiseai-influxdb/health
        """
        self.log("\n" + "=" * 60)
        self.log("Verification 2: Grafana Datasource Health")
        self.log("=" * 60)

        import base64

        credentials = base64.b64encode(
            f"{self.grafana_user}:{self.grafana_pass}".encode()
        ).decode()

        success, data, status = self._make_request(
            f"{self.grafana_url}/api/datasources/uid/chiseai-influxdb/health",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
        )

        if success:
            try:
                result = json.loads(data)
                status_msg = result.get("status")
                message = result.get("message", "")

                if status_msg == "OK":
                    self.log(f"✓ Grafana datasource healthy: {message}")
                    return True
                else:
                    self.log(f"✗ Grafana datasource unhealthy: {message}", "ERROR")
                    return False
            except json.JSONDecodeError:
                self.log(f"✗ Invalid JSON response: {data}", "ERROR")
                return False
        else:
            self.log(f"✗ Grafana health check failed (HTTP {status}): {data}", "ERROR")
            return False

    def verify_influxdb_query(self) -> bool:
        """
        Verify InfluxDB query returns data.

        Expected: JSON with measurements list
        Command equivalent:
            curl -H "Authorization: Token $TOKEN" "http://host.docker.internal:18087/query?db=chiseai&q=SHOW+MEASUREMENTS"
        """
        self.log("\n" + "=" * 60)
        self.log("Verification 3: InfluxDB Query")
        self.log("=" * 60)

        if not self.token:
            self.log("No INFLUXDB_TOKEN provided", "ERROR")
            return False

        success, data, status = self._make_request(
            f"{self.influx_url}/query?db={self.bucket}&q=SHOW+MEASUREMENTS",
            headers={"Authorization": f"Token {self.token}"},
        )

        if success and status == 200:
            try:
                result = json.loads(data)
                measurements = (
                    result.get("results", [{}])[0]
                    .get("series", [{}])[0]
                    .get("values", [])
                )

                self.log(f"✓ InfluxDB query successful")
                self.log(f"  Found {len(measurements)} measurements:")
                for measurement in measurements[:10]:  # Show first 10
                    self.log(f"    - {measurement[0]}")
                if len(measurements) > 10:
                    self.log(f"    ... and {len(measurements) - 10} more")
                return True
            except (json.JSONDecodeError, IndexError) as e:
                self.log(f"✗ Error parsing response: {e}", "ERROR")
                return False
        else:
            self.log(f"✗ InfluxDB query failed (HTTP {status}): {data}", "ERROR")
            return False

    def run(self) -> int:
        """Run all verifications."""
        self.log("\n" + "=" * 60)
        self.log("InfluxDB/Grafana Authentication Verification")
        self.log("=" * 60)
        self.log(f"InfluxDB URL: {self.influx_url}")
        self.log(f"Grafana URL: {self.grafana_url}")
        self.log(f"Organization: {self.org}")
        self.log(f"Bucket: {self.bucket}")
        if self.token:
            self.log(f"Token: {self.token[:20]}...")
        else:
            self.log("Token: NOT PROVIDED", "WARN")

        results = []

        # Verification 1: InfluxDB Ping
        results.append(("InfluxDB Ping", self.verify_influxdb_ping()))

        # Verification 2: Grafana Health
        results.append(("Grafana Health", self.verify_grafana_health()))

        # Verification 3: InfluxDB Query
        results.append(("InfluxDB Query", self.verify_influxdb_query()))

        # Summary
        self.log("\n" + "=" * 60)
        self.log("Verification Summary")
        self.log("=" * 60)

        all_passed = True
        for name, passed in results:
            status = "✓ PASS" if passed else "✗ FAIL"
            self.log(f"{name}: {status}")
            if not passed:
                all_passed = False

        if all_passed:
            self.log("\n✓ All verifications passed!")
            return 0
        else:
            self.log("\n✗ Some verifications failed", "ERROR")
            return 1


def main():
    parser = argparse.ArgumentParser(
        description="Verify InfluxDB/Grafana authentication"
    )
    parser.add_argument(
        "--influx-url",
        default=os.getenv("INFLUXDB_URL", "http://host.docker.internal:18087"),
        help="InfluxDB URL (default: http://host.docker.internal:18087)",
    )
    parser.add_argument(
        "--grafana-url",
        default=os.getenv("GRAFANA_URL", "http://host.docker.internal:3001"),
        help="Grafana URL (default: http://host.docker.internal:3001)",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("INFLUXDB_TOKEN"),
        help="InfluxDB token (default: from INFLUXDB_TOKEN env var)",
    )
    parser.add_argument(
        "--grafana-user",
        default=os.getenv("GRAFANA_ADMIN_USER", "admin"),
        help="Grafana admin username (default: admin)",
    )
    parser.add_argument(
        "--grafana-pass",
        default=os.getenv("GRAFANA_ADMIN_PASSWORD", "admin123"),
        help="Grafana admin password",
    )
    parser.add_argument(
        "--org",
        default=os.getenv("INFLUXDB_ORG", "chiseai"),
        help="InfluxDB organization (default: chiseai)",
    )
    parser.add_argument(
        "--bucket",
        default=os.getenv("INFLUXDB_BUCKET", "chiseai"),
        help="InfluxDB bucket (default: chiseai)",
    )

    args = parser.parse_args()

    verifier = AuthVerifier(
        influx_url=args.influx_url,
        grafana_url=args.grafana_url,
        token=args.token,
        grafana_user=args.grafana_user,
        grafana_pass=args.grafana_pass,
        org=args.org,
        bucket=args.bucket,
    )

    sys.exit(verifier.run())


if __name__ == "__main__":
    main()
