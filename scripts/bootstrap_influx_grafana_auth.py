#!/usr/bin/env python3
"""
Bootstrap script for InfluxDB/Grafana authentication synchronization.

This script:
1. Waits for InfluxDB to be ready (health check)
2. Retrieves or creates admin token via InfluxDB API
3. Updates Grafana datasource via Grafana API
4. Verifies connection works

Usage:
    python3 scripts/bootstrap_influx_grafana_auth.py [--influx-url URL] [--grafana-url URL]

Environment Variables:
    INFLUXDB_TOKEN - Existing InfluxDB admin token (if available)
    INFLUXDB_ADMIN_USER - InfluxDB admin username (default: admin)
    INFLUXDB_ADMIN_PASSWORD - InfluxDB admin password
    GRAFANA_ADMIN_USER - Grafana admin username (default: admin)
    GRAFANA_ADMIN_PASSWORD - Grafana admin password (default: admin123)
    INFLUXDB_ORG - InfluxDB organization (default: chiseai)
    INFLUXDB_BUCKET - InfluxDB bucket (default: chiseai)

Exit codes:
    0 - Success
    1 - InfluxDB not reachable
    2 - Authentication failed
    3 - Grafana update failed
    4 - Verification failed
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any


class InfluxGrafanaBootstrap:
    """Handles InfluxDB/Grafana authentication bootstrapping."""

    def __init__(
        self,
        influx_url: str = "http://host.docker.internal:18087",
        grafana_url: str = "http://host.docker.internal:3001",
        influx_user: str = "admin",
        influx_pass: str = "change-me",
        influx_token: Optional[str] = None,
        grafana_user: str = "admin",
        grafana_pass: str = "admin123",
        org: str = "chiseai",
        bucket: str = "chiseai",
    ):
        self.influx_url = influx_url.rstrip("/")
        self.grafana_url = grafana_url.rstrip("/")
        self.influx_user = influx_user
        self.influx_pass = influx_pass
        self.influx_token = influx_token
        self.grafana_user = grafana_user
        self.grafana_pass = grafana_pass
        self.org = org
        self.bucket = bucket
        self.token: Optional[str] = influx_token

    def log(self, message: str, level: str = "INFO") -> None:
        """Print a log message."""
        print(f"[{level}] {message}")

    def _make_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[bytes] = None,
        timeout: int = 10,
    ) -> tuple:
        """Make an HTTP request and return (success, response_data, status_code)."""
        try:
            req = urllib.request.Request(url, method=method)
            if headers:
                for key, value in headers.items():
                    req.add_header(key, value)
            if data:
                req.data = data

            with urllib.request.urlopen(req, timeout=timeout) as response:
                return True, response.read().decode(), response.status
        except urllib.error.HTTPError as e:
            return False, e.read().decode(), e.code
        except Exception as e:
            return False, str(e), 0

    def wait_for_influxdb(self, timeout: int = 60, interval: int = 2) -> bool:
        """Wait for InfluxDB to be ready."""
        self.log(f"Waiting for InfluxDB at {self.influx_url}...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            success, _, status = self._make_request(
                f"{self.influx_url}/ping", timeout=5
            )
            if success and status == 204:
                self.log("InfluxDB is ready")
                return True
            time.sleep(interval)

        self.log(f"InfluxDB not ready after {timeout}s", "ERROR")
        return False

    def _get_influx_headers(self) -> Dict[str, str]:
        """Get headers for InfluxDB API requests."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        return headers

    def get_existing_tokens(self) -> List[Dict[str, Any]]:
        """Get list of existing tokens from InfluxDB."""
        if not self.token:
            self.log("No token available to list authorizations", "DEBUG")
            return []

        success, data, status = self._make_request(
            f"{self.influx_url}/api/v2/authorizations",
            headers=self._get_influx_headers(),
        )

        if success:
            return json.loads(data).get("authorizations", [])
        else:
            self.log(f"Failed to get tokens: {data}", "ERROR")
            return []

    def find_admin_token(self) -> Optional[str]:
        """Find existing admin token for the organization."""
        tokens = self.get_existing_tokens()

        for token in tokens:
            if token.get("org") == self.org:
                permissions = token.get("permissions", [])
                for perm in permissions:
                    if perm.get("resource", {}).get("type") == "buckets":
                        self.log(
                            f"Found existing token: {token.get('description', 'unnamed')}"
                        )
                        return token.get("token")

        return None

    def create_admin_token(self) -> Optional[str]:
        """Create a new admin token for InfluxDB."""
        if not self.token:
            self.log("No existing token to create new token", "ERROR")
            return None

        # First get the org ID
        success, data, status = self._make_request(
            f"{self.influx_url}/api/v2/orgs",
            headers=self._get_influx_headers(),
        )

        if not success:
            self.log(f"Failed to get orgs: {data}", "ERROR")
            return None

        org_id = None
        for org in json.loads(data).get("orgs", []):
            if org.get("name") == self.org:
                org_id = org.get("id")
                break

        if not org_id:
            self.log(f"Organization '{self.org}' not found", "ERROR")
            return None

        # Create token with full permissions
        token_request = {
            "description": f"Bootstrap admin token for {self.org}",
            "orgID": org_id,
            "permissions": [
                {"action": "read", "resource": {"type": "buckets"}},
                {"action": "write", "resource": {"type": "buckets"}},
                {"action": "read", "resource": {"type": "orgs"}},
                {"action": "write", "resource": {"type": "orgs"}},
            ],
        }

        success, data, status = self._make_request(
            f"{self.influx_url}/api/v2/authorizations",
            method="POST",
            headers=self._get_influx_headers(),
            data=json.dumps(token_request).encode(),
        )

        if success:
            token = json.loads(data).get("token")
            if token:
                self.log("Created new admin token")
                return token
        else:
            self.log(f"Failed to create token: {data}", "ERROR")

        return None

    def get_or_create_token(self) -> Optional[str]:
        """Get existing token or create a new one."""
        if self.token:
            self.log("Using provided token")
            # Verify the token works
            if self.verify_influxdb_connection():
                return self.token
            self.log("Provided token is invalid, trying to find another...")

        self.log("Checking for existing tokens...")

        # Try to find existing token
        existing = self.find_admin_token()
        if existing:
            self.token = existing
            return existing

        self.log("No existing token found, cannot create new one without auth", "ERROR")
        return None

    def _get_grafana_headers(self) -> Dict[str, str]:
        """Get headers for Grafana API requests."""
        credentials = base64.b64encode(
            f"{self.grafana_user}:{self.grafana_pass}".encode()
        ).decode()
        return {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

    def update_grafana_datasource(self) -> bool:
        """Update Grafana datasource with the token."""
        if not self.token:
            self.log("No token available to update Grafana", "ERROR")
            return False

        # First, get the datasource
        success, data, status = self._make_request(
            f"{self.grafana_url}/api/datasources/uid/chiseai-influxdb",
            headers=self._get_grafana_headers(),
        )

        ds_id = None
        ds_uid = "chiseai-influxdb"

        if success:
            ds_data = json.loads(data)
            ds_id = ds_data.get("id")
            self.log(f"Found existing datasource (ID: {ds_id})")
        elif status == 404:
            self.log("Datasource not found, will create new one", "WARN")
        else:
            self.log(f"Failed to get datasource: {data}", "ERROR")
            return False

        # Prepare datasource config
        # Always use the configured org/bucket to ensure consistency with InfluxDB
        json_data = {
            "version": "Flux",
            "organization": self.org,
            "defaultBucket": self.bucket,
            "tlsSkipVerify": True,
        }

        datasource_config = {
            "name": "ChiseAI InfluxDB",
            "type": "influxdb",
            "access": "proxy",
            "url": "http://chiseai-influxdb:18087",
            "isDefault": True,
            "editable": True,
            "uid": ds_uid,
            "jsonData": json_data,
            "secureJsonData": {"token": self.token},
        }

        if ds_id:
            # Update existing datasource
            datasource_config["id"] = ds_id
            success, data, status = self._make_request(
                f"{self.grafana_url}/api/datasources/{ds_id}",
                method="PUT",
                headers=self._get_grafana_headers(),
                data=json.dumps(datasource_config).encode(),
            )
            self.log(f"Updating existing datasource...")
        else:
            # Create new datasource
            success, data, status = self._make_request(
                f"{self.grafana_url}/api/datasources",
                method="POST",
                headers=self._get_grafana_headers(),
                data=json.dumps(datasource_config).encode(),
            )
            self.log("Creating new datasource...")

        if success and status in (200, 201):
            self.log("Grafana datasource updated successfully")
            return True
        else:
            self.log(f"Failed to update Grafana: {data}", "ERROR")
            return False

    def verify_influxdb_connection(self) -> bool:
        """Verify InfluxDB connection with token."""
        if not self.token:
            self.log("No token available for verification", "ERROR")
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
                self.log(
                    f"InfluxDB connection verified. Found {len(measurements)} measurements"
                )
                return True
            except Exception as e:
                self.log(f"Error parsing InfluxDB response: {e}", "ERROR")
                return False
        else:
            self.log(f"InfluxDB verification failed: {data}", "ERROR")
            return False

    def verify_grafana_connection(self) -> bool:
        """Verify Grafana datasource health."""
        success, data, status = self._make_request(
            f"{self.grafana_url}/api/datasources/uid/chiseai-influxdb/health",
            headers=self._get_grafana_headers(),
        )

        if success:
            try:
                result = json.loads(data)
                status_msg = result.get("status")
                message = result.get("message", "")

                if status_msg == "OK":
                    self.log(f"Grafana datasource healthy: {message}")
                    return True
                else:
                    self.log(f"Grafana datasource unhealthy: {message}", "ERROR")
                    return False
            except Exception as e:
                self.log(f"Error parsing Grafana response: {e}", "ERROR")
                return False
        else:
            self.log(f"Grafana verification failed: {data}", "ERROR")
            return False

    def run(self) -> int:
        """Run the full bootstrap process."""
        self.log("=" * 60)
        self.log("InfluxDB/Grafana Authentication Bootstrap")
        self.log("=" * 60)

        # Step 1: Wait for InfluxDB
        if not self.wait_for_influxdb():
            return 1

        # Step 2: Get or create token
        token = self.get_or_create_token()
        if not token:
            self.log("Failed to obtain InfluxDB token", "ERROR")
            return 2

        self.log(f"Token obtained (first 20 chars): {token[:20]}...")

        # Step 3: Update Grafana
        if not self.update_grafana_datasource():
            self.log("Failed to update Grafana datasource", "ERROR")
            return 3

        # Step 4: Verify connections
        self.log("\nVerifying connections...")
        influx_ok = self.verify_influxdb_connection()
        grafana_ok = self.verify_grafana_connection()

        if influx_ok and grafana_ok:
            self.log("\n" + "=" * 60)
            self.log("Bootstrap completed successfully!")
            self.log("=" * 60)
            self.log(f"\nToken: {self.token}")
            self.log("\nAdd this to your terraform.tfvars:")
            self.log(f'  influxdb_token = "{self.token}"')
            return 0
        else:
            self.log("\nVerification failed", "ERROR")
            return 4


def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap InfluxDB/Grafana authentication"
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
        "--influx-user",
        default=os.getenv("INFLUXDB_ADMIN_USER", "admin"),
        help="InfluxDB admin username (default: admin)",
    )
    parser.add_argument(
        "--influx-pass",
        default=os.getenv("INFLUXDB_ADMIN_PASSWORD", "change-me"),
        help="InfluxDB admin password",
    )
    parser.add_argument(
        "--influx-token",
        default=os.getenv("INFLUXDB_TOKEN"),
        help="Existing InfluxDB admin token",
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

    bootstrap = InfluxGrafanaBootstrap(
        influx_url=args.influx_url,
        grafana_url=args.grafana_url,
        influx_user=args.influx_user,
        influx_pass=args.influx_pass,
        influx_token=args.influx_token,
        grafana_user=args.grafana_user,
        grafana_pass=args.grafana_pass,
        org=args.org,
        bucket=args.bucket,
    )

    sys.exit(bootstrap.run())


if __name__ == "__main__":
    main()
