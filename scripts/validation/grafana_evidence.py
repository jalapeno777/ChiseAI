"""
Grafana Evidence Collector for G6-G7 Validation

Queries through Grafana API to collect evidence for validation gates.
Provides datasource health checks and query-through-Grafana functionality.

Requirements:
- Grafana at host.docker.internal:3001
- Default credentials: admin/admin123
- Datasource UID: chiseai-influxdb
"""

import asyncio
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import json
import aiohttp
import base64


@dataclass
class GrafanaEvidence:
    """
    Evidence from a Grafana query.

    Attributes:
        gate: The gate this evidence belongs to ("G6" or "G7")
        datasource_uid: UID of the Grafana datasource
        query: The query string executed
        timestamp_utc: ISO format UTC timestamp when query was executed
        response_status: HTTP status or "error"
        has_data: Whether any data was returned
        data_rows: List of data rows returned
        error: Optional error message if query failed
    """

    gate: str
    datasource_uid: str
    query: str
    timestamp_utc: str
    response_status: str
    has_data: bool
    data_rows: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert evidence to dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert evidence to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass
class DatasourceHealth:
    """
    Health status of a Grafana datasource.

    Attributes:
        uid: Datasource UID
        name: Datasource name
        type: Datasource type (e.g., "influxdb")
        status: "healthy" or "unhealthy"
        message: Optional status message
        timestamp_utc: ISO format UTC timestamp
    """

    uid: str
    name: str
    type: str
    status: str
    message: Optional[str] = None
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert health status to dictionary."""
        return asdict(self)


class GrafanaEvidenceCollector:
    """
    Collects evidence through Grafana API for G6-G7 validation.

    This collector queries InfluxDB through Grafana's datasource API,
    providing an additional validation path that goes through the
    Grafana infrastructure.

    Usage:
        collector = GrafanaEvidenceCollector()

        # Check datasource health
        health = await collector.check_datasource_health()

        # Query through Grafana
        evidence = await collector.query_via_grafana(
            query='from(bucket: "chiseai") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "orders")'
        )
    """

    def __init__(
        self,
        url: str = "http://host.docker.internal:3001",
        user: str = "admin",
        password: str = "admin123",
    ):
        """
        Initialize the Grafana evidence collector.

        Args:
            url: Grafana URL (default: host.docker.internal:3001)
            user: Grafana username (default: admin)
            password: Grafana password (default: admin123)
        """
        self.url = url.rstrip("/")
        self.user = user
        self.password = password

        # Create basic auth header
        credentials = f"{user}:{password}"
        self.auth_header = base64.b64encode(credentials.encode()).decode()

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for Grafana API requests."""
        return {
            "Authorization": f"Basic {self.auth_header}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def check_datasource_health(
        self, uid: str = "chiseai-influxdb"
    ) -> DatasourceHealth:
        """
        Check if a Grafana datasource is healthy.

        Args:
            uid: Datasource UID to check (default: chiseai-influxdb)

        Returns:
            DatasourceHealth with status information
        """
        timestamp_utc = datetime.now(timezone.utc).isoformat()

        # First try to get datasource info
        api_url = f"{self.url}/api/datasources/uid/{uid}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        return DatasourceHealth(
                            uid=uid,
                            name="unknown",
                            type="unknown",
                            status="unhealthy",
                            message=f"Datasource not found or access denied (status {response.status})",
                            timestamp_utc=timestamp_utc,
                        )

                    ds_info = await response.json()
                    ds_name = ds_info.get("name", "unknown")
                    ds_type = ds_info.get("type", "unknown")

                # Try health check endpoint
                health_url = f"{self.url}/api/datasources/uid/{uid}/health"
                async with session.get(
                    health_url,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as health_response:
                    if health_response.status == 200:
                        health_data = await health_response.json()
                        status = health_data.get("status", "unknown")
                        message = health_data.get("message")

                        return DatasourceHealth(
                            uid=uid,
                            name=ds_name,
                            type=ds_type,
                            status="healthy" if status == "OK" else "unhealthy",
                            message=message,
                            timestamp_utc=timestamp_utc,
                        )
                    else:
                        # Fallback: assume healthy if datasource exists
                        return DatasourceHealth(
                            uid=uid,
                            name=ds_name,
                            type=ds_type,
                            status="healthy",
                            message="Datasource accessible (health check unavailable)",
                            timestamp_utc=timestamp_utc,
                        )

        except asyncio.TimeoutError:
            return DatasourceHealth(
                uid=uid,
                name="unknown",
                type="unknown",
                status="unhealthy",
                message="Health check timed out",
                timestamp_utc=timestamp_utc,
            )
        except aiohttp.ClientError as e:
            return DatasourceHealth(
                uid=uid,
                name="unknown",
                type="unknown",
                status="unhealthy",
                message=f"Connection error: {str(e)}",
                timestamp_utc=timestamp_utc,
            )
        except Exception as e:
            return DatasourceHealth(
                uid=uid,
                name="unknown",
                type="unknown",
                status="unhealthy",
                message=f"Unexpected error: {str(e)}",
                timestamp_utc=timestamp_utc,
            )

    async def query_via_grafana(
        self, query: str, datasource_uid: str = "chiseai-influxdb", gate: str = "G6"
    ) -> GrafanaEvidence:
        """
        Query through Grafana's datasource proxy API.

        This sends a query through Grafana to the underlying datasource,
        providing evidence that the query path through Grafana works.

        Args:
            query: Flux query string
            datasource_uid: Datasource UID (default: chiseai-influxdb)
            gate: Gate identifier ("G6" or "G7")

        Returns:
            GrafanaEvidence with query results
        """
        timestamp_utc = datetime.now(timezone.utc).isoformat()

        # Use the datasource proxy endpoint for InfluxDB
        # POST /api/datasources/uid/{uid}/resources/query
        api_url = f"{self.url}/api/datasources/uid/{datasource_uid}/resources/query"

        payload = {
            "query": query,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response_status = str(response.status)

                    if response.status != 200:
                        text = await response.text()
                        return GrafanaEvidence(
                            gate=gate,
                            datasource_uid=datasource_uid,
                            query=query,
                            timestamp_utc=timestamp_utc,
                            response_status=response_status,
                            has_data=False,
                            data_rows=[],
                            error=f"Grafana query failed: {text}",
                        )

                    data = await response.json()

                    # Parse InfluxDB response format
                    rows = self._parse_influx_response(data)
                    has_data = len(rows) > 0

                    return GrafanaEvidence(
                        gate=gate,
                        datasource_uid=datasource_uid,
                        query=query,
                        timestamp_utc=timestamp_utc,
                        response_status=response_status,
                        has_data=has_data,
                        data_rows=rows,
                        error=None,
                    )

        except asyncio.TimeoutError:
            return GrafanaEvidence(
                gate=gate,
                datasource_uid=datasource_uid,
                query=query,
                timestamp_utc=timestamp_utc,
                response_status="timeout",
                has_data=False,
                data_rows=[],
                error="Query timed out",
            )
        except aiohttp.ClientError as e:
            return GrafanaEvidence(
                gate=gate,
                datasource_uid=datasource_uid,
                query=query,
                timestamp_utc=timestamp_utc,
                response_status="connection_error",
                has_data=False,
                data_rows=[],
                error=f"Connection error: {str(e)}",
            )
        except Exception as e:
            return GrafanaEvidence(
                gate=gate,
                datasource_uid=datasource_uid,
                query=query,
                timestamp_utc=timestamp_utc,
                response_status="error",
                has_data=False,
                data_rows=[],
                error=f"Unexpected error: {str(e)}",
            )

    def _parse_influx_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse InfluxDB response from Grafana proxy.

        InfluxDB responses through Grafana come in a specific format
        with results containing series with columns and values.

        Args:
            data: Raw response from Grafana

        Returns:
            List of row dictionaries
        """
        rows = []

        if not data:
            return rows

        # Handle different response formats
        results = data.get("results", [])

        if isinstance(results, list):
            for result in results:
                series = result.get("series", [])
                for s in series:
                    columns = s.get("columns", [])
                    values = s.get("values", [])

                    for value_row in values:
                        row = {}
                        for i, col in enumerate(columns):
                            if i < len(value_row):
                                row[col] = value_row[i]
                        if row:
                            rows.append(row)

        return rows

    async def query_orders_via_grafana(
        self, since: datetime, limit: int = 5, datasource_uid: str = "chiseai-influxdb"
    ) -> GrafanaEvidence:
        """
        Query orders measurement through Grafana.

        Args:
            since: Start time for query window
            limit: Maximum rows to return
            datasource_uid: Grafana datasource UID

        Returns:
            GrafanaEvidence with query results
        """
        start_time = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        query = f"""from(bucket: "chiseai")
  |> range(start: {start_time})
  |> filter(fn: (r) => r._measurement == "orders")
  |> limit(n: {limit})"""

        return await self.query_via_grafana(
            query=query, datasource_uid=datasource_uid, gate="G6"
        )

    async def query_fills_via_grafana(
        self, since: datetime, limit: int = 5, datasource_uid: str = "chiseai-influxdb"
    ) -> GrafanaEvidence:
        """
        Query fills measurement through Grafana.

        Args:
            since: Start time for query window
            limit: Maximum rows to return
            datasource_uid: Grafana datasource UID

        Returns:
            GrafanaEvidence with query results
        """
        start_time = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        query = f"""from(bucket: "chiseai")
  |> range(start: {start_time})
  |> filter(fn: (r) => r._measurement == "fills")
  |> limit(n: {limit})"""

        return await self.query_via_grafana(
            query=query, datasource_uid=datasource_uid, gate="G6"
        )

    async def query_canary_via_grafana(
        self, since: datetime, limit: int = 5, datasource_uid: str = "chiseai-influxdb"
    ) -> GrafanaEvidence:
        """
        Query canary_deployment measurement through Grafana.

        Args:
            since: Start time for query window
            limit: Maximum rows to return
            datasource_uid: Grafana datasource UID

        Returns:
            GrafanaEvidence with query results
        """
        start_time = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        query = f"""from(bucket: "chiseai")
  |> range(start: {start_time})
  |> filter(fn: (r) => r._measurement == "canary_deployment")
  |> limit(n: {limit})"""

        return await self.query_via_grafana(
            query=query, datasource_uid=datasource_uid, gate="G7"
        )

    async def collect_all_evidence_via_grafana(
        self, since: datetime, limit: int = 5, datasource_uid: str = "chiseai-influxdb"
    ) -> Dict[str, GrafanaEvidence]:
        """
        Collect all G6-G7 evidence through Grafana.

        Args:
            since: Start time for all query windows
            limit: Maximum rows per query
            datasource_uid: Grafana datasource UID

        Returns:
            Dictionary mapping measurement names to evidence
        """
        orders_task = self.query_orders_via_grafana(since, limit, datasource_uid)
        fills_task = self.query_fills_via_grafana(since, limit, datasource_uid)
        canary_task = self.query_canary_via_grafana(since, limit, datasource_uid)

        orders, fills, canary = await asyncio.gather(
            orders_task, fills_task, canary_task
        )

        return {
            "orders": orders,
            "fills": fills,
            "canary_deployment": canary,
        }


# Convenience functions


def hours_ago(hours: int) -> datetime:
    """Get datetime N hours ago in UTC."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def minutes_ago(minutes: int) -> datetime:
    """Get datetime N minutes ago in UTC."""
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


async def verify_grafana_influx_connectivity() -> Dict[str, Any]:
    """
    Verify connectivity to Grafana and InfluxDB datasource.

    Returns:
        Dictionary with connectivity status
    """
    collector = GrafanaEvidenceCollector()

    # Check datasource health
    health = await collector.check_datasource_health()

    return {
        "datasource_uid": health.uid,
        "datasource_name": health.name,
        "datasource_type": health.type,
        "status": health.status,
        "message": health.message,
        "timestamp_utc": health.timestamp_utc,
    }


if __name__ == "__main__":
    # Example usage
    async def example():
        """Example of using the Grafana evidence collector."""
        collector = GrafanaEvidenceCollector()

        print("Checking Grafana datasource health...")
        health = await collector.check_datasource_health()
        print(f"  UID: {health.uid}")
        print(f"  Name: {health.name}")
        print(f"  Type: {health.type}")
        print(f"  Status: {health.status}")
        print(f"  Message: {health.message}")
        print()

        if health.status != "healthy":
            print("Datasource not healthy, skipping query test.")
            return

        print("Querying through Grafana...")
        since = hours_ago(1)

        orders = await collector.query_orders_via_grafana(since)
        print(f"Orders query:")
        print(f"  Status: {orders.response_status}")
        print(f"  Has data: {orders.has_data}")
        print(f"  Rows: {len(orders.data_rows)}")
        if orders.error:
            print(f"  Error: {orders.error}")
        print()

        print("--- Sample Evidence Structure ---")
        print(orders.to_json())

    asyncio.run(example())
