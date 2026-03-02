"""
InfluxDB Evidence Collector for G6-G7 Validation

Collects exact query strings and returned rows for forensic validation.
- G6: Orders and fills measurements
- G7: Canary deployment measurement

Requirements:
- InfluxDB at host.docker.internal:18087
- Token from env var INFLUXDB_TOKEN
- Database: chiseai
- Measurements: orders, fills, canary_deployment
"""

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp


@dataclass
class InfluxQueryEvidence:
    """
    Evidence from an InfluxDB query.

    Attributes:
        gate: The gate this evidence belongs to ("G6" or "G7")
        measurement: The measurement queried ("orders", "fills", "canary_deployment")
        query_string: The exact query executed
        timestamp_utc: ISO format UTC timestamp when query was executed
        row_count: Number of rows returned
        sample_rows: First 5 rows of the result
        has_data: Whether any data was returned (row_count > 0)
        error: Optional error message if query failed
    """

    gate: str
    measurement: str
    query_string: str
    timestamp_utc: str
    row_count: int
    sample_rows: list[dict[str, Any]]
    has_data: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert evidence to dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert evidence to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass
class GateResult:
    """
    Result of gate validation.

    Attributes:
        gate: Gate identifier ("G6" or "G7")
        status: "PASS" or "FAIL"
        evidence: List of evidence collected
        validation_errors: List of validation error messages
        evaluated_at: ISO format UTC timestamp
    """

    gate: str
    status: str  # "PASS" or "FAIL"
    evidence: list[InfluxQueryEvidence]
    validation_errors: list[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "gate": self.gate,
            "status": self.status,
            "evidence": [e.to_dict() for e in self.evidence],
            "validation_errors": self.validation_errors,
            "evaluated_at": self.evaluated_at,
        }


class InfluxEvidenceCollector:
    """
    Collects evidence from InfluxDB for G6-G7 validation.

    G6 Requirements:
        - Query orders measurement for recent points
        - Query fills measurement for recent points
        - Both must have non-empty recent points in same time window

    G7 Requirements:
        - Query canary_deployment measurement for recent points
        - Must have non-empty recent points

    Usage:
        collector = InfluxEvidenceCollector()
        orders = await collector.query_orders(since=hours_ago(1))
        fills = await collector.query_fills(since=hours_ago(1))
        result = collector.validate_g6(orders, fills)
    """

    def __init__(
        self,
        url: str = "http://host.docker.internal:18087",
        token: str | None = None,
        org: str = "chiseai",
        bucket: str = "chiseai",
    ):
        """
        Initialize the InfluxDB evidence collector.

        Args:
            url: InfluxDB URL (default: host.docker.internal:18087)
            token: Authentication token (default: from INFLUXDB_TOKEN env var)
            org: Organization name (default: chiseai)
            bucket: Bucket name (default: chiseai)
        """
        self.url = url.rstrip("/")
        self.token = token or os.getenv("INFLUXDB_TOKEN")
        self.org = org
        self.bucket = bucket

        if not self.token:
            raise ValueError(
                "InfluxDB token required. Set INFLUXDB_TOKEN environment variable "
                "or pass token parameter."
            )

    def _build_query(
        self,
        measurement: str,
        since: datetime,
        limit: int = 5,
        fields: list[str] | None = None,
    ) -> str:
        """
        Build an InfluxDB Flux query string.

        Args:
            measurement: Measurement name to query
            since: Start time for the query
            limit: Maximum number of rows to return
            fields: Optional list of fields to select

        Returns:
            Flux query string
        """
        # Convert datetime to RFC3339 format for Flux
        start_time = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        if fields:
            predicates = " or ".join([f'r._field == "{name}"' for name in fields])
            field_filter = f"|> filter(fn: (r) => {predicates})"
        else:
            field_filter = ""

        query = f"""from(bucket: "{self.bucket}")
  |> range(start: {start_time})
  |> filter(fn: (r) => r._measurement == "{measurement}")
  {field_filter}
  |> limit(n: {limit})"""

        return query.strip()

    async def _execute_query(self, query: str) -> dict[str, Any]:
        """
        Execute a Flux query against InfluxDB.

        Args:
            query: Flux query string

        Returns:
            Dictionary with 'results' (list of rows) and 'error' (if any)
        """
        api_url = f"{self.url}/api/v2/query"
        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/vnd.flux",
            "Accept": "application/csv",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    headers=headers,
                    data=query,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        return {
                            "results": [],
                            "error": f"InfluxDB query failed with status {response.status}: {text}",
                        }

                    csv_data = await response.text()
                    rows = self._parse_csv_response(csv_data)
                    return {"results": rows, "error": None}

        except TimeoutError:
            return {"results": [], "error": "InfluxDB query timed out"}
        except aiohttp.ClientError as e:
            return {"results": [], "error": f"InfluxDB connection error: {str(e)}"}
        except Exception as e:
            return {"results": [], "error": f"Unexpected error: {str(e)}"}

    def _parse_csv_response(self, csv_data: str) -> list[dict[str, Any]]:
        """
        Parse InfluxDB CSV response into list of dictionaries.

        InfluxDB returns annotated CSV with multiple tables.
        This method extracts the data rows into simplified dictionaries.

        Args:
            csv_data: Raw CSV response from InfluxDB

        Returns:
            List of row dictionaries
        """
        rows: list[dict[str, Any]] = []
        lines = csv_data.strip().split("\n")

        if not lines:
            return rows

        # Find header line (starts with #datatype)
        header_idx = None
        for i, line in enumerate(lines):
            if line.startswith("#datatype"):
                # The next line after #datatype should be the header
                if i + 1 < len(lines) and not lines[i + 1].startswith("#"):
                    header_idx = i + 1
                    break

        if header_idx is None:
            # Try to find regular header
            for i, line in enumerate(lines):
                if not line.startswith("#") and "," in line:
                    header_idx = i
                    break

        if header_idx is None:
            return rows

        headers = lines[header_idx].split(",")

        # Parse data rows
        for line in lines[header_idx + 1 :]:
            if line.startswith("#") or not line.strip():
                continue

            values = line.split(",")
            if len(values) >= len(headers):
                row = {}
                for j, header in enumerate(headers):
                    if j < len(values):
                        row[header.strip()] = values[j].strip()
                if row:
                    rows.append(row)

        return rows

    async def query_orders(
        self, since: datetime, limit: int = 5
    ) -> InfluxQueryEvidence:
        """
        Query orders measurement for G6 validation.

        Args:
            since: Start time for the query window
            limit: Maximum number of rows to return (default: 5)

        Returns:
            InfluxQueryEvidence with query results
        """
        timestamp_utc = datetime.now(UTC).isoformat()
        query = self._build_query("orders", since, limit)

        result = await self._execute_query(query)
        rows = result["results"]
        error = result.get("error")

        return InfluxQueryEvidence(
            gate="G6",
            measurement="orders",
            query_string=query,
            timestamp_utc=timestamp_utc,
            row_count=len(rows),
            sample_rows=rows[:limit],
            has_data=len(rows) > 0,
            error=error,
        )

    async def query_fills(self, since: datetime, limit: int = 5) -> InfluxQueryEvidence:
        """
        Query fills measurement for G6 validation.

        Args:
            since: Start time for the query window
            limit: Maximum number of rows to return (default: 5)

        Returns:
            InfluxQueryEvidence with query results
        """
        timestamp_utc = datetime.now(UTC).isoformat()
        query = self._build_query("fills", since, limit)

        result = await self._execute_query(query)
        rows = result["results"]
        error = result.get("error")

        return InfluxQueryEvidence(
            gate="G6",
            measurement="fills",
            query_string=query,
            timestamp_utc=timestamp_utc,
            row_count=len(rows),
            sample_rows=rows[:limit],
            has_data=len(rows) > 0,
            error=error,
        )

    async def query_canary(
        self, since: datetime, limit: int = 5
    ) -> InfluxQueryEvidence:
        """
        Query canary_deployment measurement for G7 validation.

        Args:
            since: Start time for the query window
            limit: Maximum number of rows to return (default: 5)

        Returns:
            InfluxQueryEvidence with query results
        """
        timestamp_utc = datetime.now(UTC).isoformat()
        query = self._build_query("canary_deployment", since, limit)

        result = await self._execute_query(query)
        rows = result["results"]
        error = result.get("error")

        return InfluxQueryEvidence(
            gate="G7",
            measurement="canary_deployment",
            query_string=query,
            timestamp_utc=timestamp_utc,
            row_count=len(rows),
            sample_rows=rows[:limit],
            has_data=len(rows) > 0,
            error=error,
        )

    def validate_g6(
        self, orders: InfluxQueryEvidence, fills: InfluxQueryEvidence
    ) -> GateResult:
        """
        Validate G6: Orders and fills must have non-empty recent points.

        G6 passes when:
        1. Orders query returned at least one row
        2. Fills query returned at least one row
        3. Both queries executed without errors

        Args:
            orders: Evidence from orders query
            fills: Evidence from fills query

        Returns:
            GateResult with PASS or FAIL status
        """
        errors = []

        # Check for query errors
        if orders.error:
            errors.append(f"Orders query error: {orders.error}")
        if fills.error:
            errors.append(f"Fills query error: {fills.error}")

        # Check for data presence
        if not orders.has_data:
            errors.append(
                f"G6 FAIL: Orders measurement has no recent points "
                f"(row_count=0, query='{orders.query_string[:50]}...')"
            )
        if not fills.has_data:
            errors.append(
                f"G6 FAIL: Fills measurement has no recent points "
                f"(row_count=0, query='{fills.query_string[:50]}...')"
            )

        status = "PASS" if not errors else "FAIL"

        return GateResult(
            gate="G6", status=status, evidence=[orders, fills], validation_errors=errors
        )

    def validate_g7(self, canary: InfluxQueryEvidence) -> GateResult:
        """
        Validate G7: Canary deployment must have non-empty recent points.

        G7 passes when:
        1. Canary query returned at least one row
        2. Query executed without errors

        Args:
            canary: Evidence from canary_deployment query

        Returns:
            GateResult with PASS or FAIL status
        """
        errors = []

        # Check for query errors
        if canary.error:
            errors.append(f"Canary query error: {canary.error}")

        # Check for data presence
        if not canary.has_data:
            errors.append(
                f"G7 FAIL: Canary deployment measurement has no recent points "
                f"(row_count=0, query='{canary.query_string[:50]}...')"
            )

        status = "PASS" if not errors else "FAIL"

        return GateResult(
            gate="G7", status=status, evidence=[canary], validation_errors=errors
        )

    async def collect_all_evidence(
        self, since: datetime, limit: int = 5
    ) -> dict[str, InfluxQueryEvidence]:
        """
        Collect all evidence for G6-G7 validation.

        Args:
            since: Start time for all query windows
            limit: Maximum rows per query

        Returns:
            Dictionary mapping measurement names to evidence
        """
        orders_task = self.query_orders(since, limit)
        fills_task = self.query_fills(since, limit)
        canary_task = self.query_canary(since, limit)

        orders, fills, canary = await asyncio.gather(
            orders_task, fills_task, canary_task
        )

        return {
            "orders": orders,
            "fills": fills,
            "canary_deployment": canary,
        }

    async def validate_g6_g7(
        self, since: datetime, limit: int = 5
    ) -> dict[str, GateResult]:
        """
        Collect evidence and validate both G6 and G7.

        Args:
            since: Start time for all query windows
            limit: Maximum rows per query

        Returns:
            Dictionary with G6 and G7 GateResult
        """
        evidence = await self.collect_all_evidence(since, limit)

        g6_result = self.validate_g6(evidence["orders"], evidence["fills"])
        g7_result = self.validate_g7(evidence["canary_deployment"])

        return {
            "G6": g6_result,
            "G7": g7_result,
        }


# Convenience functions


def hours_ago(hours: int) -> datetime:
    """Get datetime N hours ago in UTC."""
    return datetime.now(UTC) - timedelta(hours=hours)


def minutes_ago(minutes: int) -> datetime:
    """Get datetime N minutes ago in UTC."""
    return datetime.now(UTC) - timedelta(minutes=minutes)


async def quick_validate_g6_g7(window_hours: int = 1, limit: int = 5) -> dict[str, Any]:
    """
    Quick validation of G6 and G7 gates.

    Args:
        window_hours: Time window in hours (default: 1)
        limit: Max rows per query (default: 5)

    Returns:
        Dictionary with validation results and evidence
    """
    collector = InfluxEvidenceCollector()
    since = hours_ago(window_hours)

    results = await collector.validate_g6_g7(since, limit)

    return {
        "G6": results["G6"].to_dict(),
        "G7": results["G7"].to_dict(),
        "window_start": since.isoformat(),
        "window_end": datetime.now(UTC).isoformat(),
    }


if __name__ == "__main__":
    # Example usage
    async def example():
        """Example of using the InfluxDB evidence collector."""
        try:
            collector = InfluxEvidenceCollector()

            # Query last hour of data
            since = hours_ago(1)

            print("Collecting G6-G7 evidence...")
            print(f"Time window: {since.isoformat()} to now")
            print()

            # Collect evidence
            orders = await collector.query_orders(since)
            fills = await collector.query_fills(since)
            canary = await collector.query_canary(since)

            print(f"Orders: {orders.row_count} rows, has_data={orders.has_data}")
            print(f"  Query: {orders.query_string[:80]}...")
            print()

            print(f"Fills: {fills.row_count} rows, has_data={fills.has_data}")
            print(f"  Query: {fills.query_string[:80]}...")
            print()

            print(f"Canary: {canary.row_count} rows, has_data={canary.has_data}")
            print(f"  Query: {canary.query_string[:80]}...")
            print()

            # Validate gates
            g6_result = collector.validate_g6(orders, fills)
            g7_result = collector.validate_g7(canary)

            print(f"G6 Result: {g6_result.status}")
            if g6_result.validation_errors:
                for err in g6_result.validation_errors:
                    print(f"  - {err}")

            print(f"G7 Result: {g7_result.status}")
            if g7_result.validation_errors:
                for err in g7_result.validation_errors:
                    print(f"  - {err}")

            # Show sample evidence structure
            print("\n--- Sample Evidence Structure ---")
            print(orders.to_json())

        except ValueError as e:
            print(f"Configuration error: {e}")
            print("Set INFLUXDB_TOKEN environment variable before running.")
        except Exception as e:
            print(f"Error: {e}")

    asyncio.run(example())
