#!/usr/bin/env python3
"""
Grafana Dashboard Manager for AUTOCOG

CLI tool to manage Grafana dashboards - import, export, validate, and list.

Usage:
    python3 grafana_dashboard_manager.py --list
    python3 grafana_dashboard_manager.py --validate
    python3 grafana_dashboard_manager.py --import-dashboard cycle_overview.json
    python3 grafana_dashboard_manager.py --export-dashboard autocog-cycle-overview
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error


# Configuration
DEFAULT_DASHBOARDS_DIR = Path(
    "/home/tacopants/projects/ChiseAI/infrastructure/grafana/dashboards/autocog"
)
DEFAULT_GRAFANA_URL = os.getenv("GRAFANA_URL", "http://host.docker.internal:3001")
DEFAULT_GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY", "")

# Required dashboard fields
REQUIRED_FIELDS = ["title", "uid", "panels", "schemaVersion"]
REQUIRED_PANEL_FIELDS = ["title", "type"]


def get_dashboard_files(directory: Path) -> List[Path]:
    """Get all JSON dashboard files from directory."""
    if not directory.exists():
        print(f"Error: Directory not found: {directory}")
        return []
    return sorted([f for f in directory.glob("*.json") if f.is_file()])


def validate_dashboard_json(file_path: Path) -> Dict[str, Any]:
    """Validate a single dashboard JSON file."""
    result = {
        "file": str(file_path),
        "valid": False,
        "errors": [],
        "warnings": [],
        "info": {},
    }

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        result["errors"].append(f"Cannot read file: {e}")
        return result

    # Check JSON syntax
    try:
        dashboard = json.loads(content)
    except json.JSONDecodeError as e:
        result["errors"].append(f"Invalid JSON: {e}")
        return result

    result["info"]["title"] = dashboard.get("title", "N/A")
    result["info"]["uid"] = dashboard.get("uid", "N/A")
    result["info"]["schema_version"] = dashboard.get("schemaVersion", "N/A")

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in dashboard:
            result["errors"].append(f"Missing required field: {field}")

    # Check panels
    panels = dashboard.get("panels", [])
    if not panels:
        result["errors"].append("No panels found in dashboard")
    else:
        result["info"]["panel_count"] = len(panels)

        for i, panel in enumerate(panels):
            if not isinstance(panel, dict):
                result["errors"].append(f"Panel {i} is not an object")
                continue

            for field in REQUIRED_PANEL_FIELDS:
                if field not in panel:
                    result["errors"].append(
                        f"Panel {i} missing required field: {field}"
                    )

    # Check datasource references
    datasources = set()
    for panel in panels:
        if isinstance(panel, dict) and "datasource" in panel:
            ds = panel.get("datasource", {})
            if isinstance(ds, dict):
                ds_type = ds.get("type", "unknown")
                ds_uid = ds.get("uid", "unknown")
                datasources.add(f"{ds_type}({ds_uid})")

    result["info"]["datasources"] = list(datasources)

    # Check for InfluxDB queries
    influxdb_count = 0
    for panel in panels:
        if isinstance(panel, dict) and "targets" in panel:
            for target in panel.get("targets", []):
                if (
                    isinstance(target, dict)
                    and target.get("datasource", {}).get("type") == "influxdb"
                ):
                    influxdb_count += 1

    result["info"]["influxdb_panels"] = influxdb_count

    # Warnings
    if not dashboard.get("description"):
        result["warnings"].append("Dashboard missing description")

    if not dashboard.get("tags"):
        result["warnings"].append("Dashboard has no tags")

    # Check refresh setting
    refresh = dashboard.get("refresh")
    if not refresh:
        result["warnings"].append("Dashboard has no auto-refresh set")

    # Validate time range
    time_config = dashboard.get("time", {})
    if not time_config.get("from") or not time_config.get("to"):
        result["warnings"].append("Dashboard time range not properly configured")

    result["valid"] = len(result["errors"]) == 0
    return result


def validate_all_dashboards(directory: Path) -> bool:
    """Validate all dashboard files in directory."""
    files = get_dashboard_files(directory)

    if not files:
        print(f"No dashboard files found in {directory}")
        return False

    print(f"\nValidating {len(files)} dashboard(s) in {directory}\n")
    print("=" * 80)

    all_valid = True
    for file_path in files:
        result = validate_dashboard_json(file_path)

        status = "✓ PASS" if result["valid"] else "✗ FAIL"
        print(f"\n{status} {file_path.name}")
        print(f"  Title: {result['info'].get('title', 'N/A')}")
        print(f"  UID: {result['info'].get('uid', 'N/A')}")
        print(f"  Panels: {result['info'].get('panel_count', 0)}")
        print(f"  InfluxDB Panels: {result['info'].get('influxdb_panels', 0)}")
        print(f"  Datasources: {', '.join(result['info'].get('datasources', []))}")

        if result["errors"]:
            print(f"  Errors:")
            for error in result["errors"]:
                print(f"    ✗ {error}")

        if result["warnings"]:
            print(f"  Warnings:")
            for warning in result["warnings"]:
                print(f"    ⚠ {warning}")

        if not result["valid"]:
            all_valid = False

    print("\n" + "=" * 80)
    if all_valid:
        print(f"\n✓ All {len(files)} dashboard(s) validated successfully!")
    else:
        print(f"\n✗ Validation failed for some dashboards")

    return all_valid


def list_dashboards(directory: Path) -> None:
    """List all available dashboards."""
    files = get_dashboard_files(directory)

    if not files:
        print(f"No dashboard files found in {directory}")
        return

    print(f"\nFound {len(files)} dashboard(s) in {directory}\n")
    print(f"{'File':<40} {'Title':<35} {'UID':<30} {'Panels':<10}")
    print("-" * 115)

    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                dashboard = json.load(f)

            title = dashboard.get("title", "N/A")[:34]
            uid = dashboard.get("uid", "N/A")[:29]
            panels = len(dashboard.get("panels", []))

            print(f"{file_path.name:<40} {title:<35} {uid:<30} {panels:<10}")
        except Exception as e:
            print(f"{file_path.name:<40} ERROR: {e}")


def import_dashboard(file_path: Path, grafana_url: str, api_key: str) -> bool:
    """Import a dashboard to Grafana via API."""
    if not api_key:
        print("Error: GRAFANA_API_KEY environment variable not set")
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            dashboard = json.load(f)
    except Exception as e:
        print(f"Error reading dashboard file: {e}")
        return False

    # Prepare API payload
    payload = {
        "dashboard": dashboard,
        "overwrite": True,
        "message": f"Imported via grafana_dashboard_manager.py",
    }

    url = f"{grafana_url}/api/dashboards/db"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

            if result.get("status") == "success":
                print(f"✓ Dashboard imported successfully")
                print(f"  UID: {result.get('uid')}")
                print(f"  URL: {result.get('url')}")
                print(f"  Version: {result.get('version')}")
                return True
            else:
                print(f"✗ Import failed: {result}")
                return False

    except urllib.error.HTTPError as e:
        print(f"✗ HTTP Error {e.code}: {e.reason}")
        try:
            body = e.read().decode("utf-8")
            print(f"  Response: {body}")
        except:
            pass
        return False
    except Exception as e:
        print(f"✗ Import error: {e}")
        return False


def export_dashboard(
    uid: str, grafana_url: str, api_key: str, output_dir: Path
) -> bool:
    """Export a dashboard from Grafana via API."""
    if not api_key:
        print("Error: GRAFANA_API_KEY environment variable not set")
        return False

    url = f"{grafana_url}/api/dashboards/uid/{uid}"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    try:
        req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

            if "dashboard" in result:
                dashboard = result["dashboard"]
                title = dashboard.get("title", uid).replace(" ", "_").lower()
                file_name = f"{title}.json"
                file_path = output_dir / file_name

                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(dashboard, f, indent=2)

                print(f"✓ Dashboard exported to {file_path}")
                print(f"  Title: {dashboard.get('title')}")
                print(f"  UID: {dashboard.get('uid')}")
                print(f"  Version: {dashboard.get('version')}")
                return True
            else:
                print(f"✗ Export failed: {result}")
                return False

    except urllib.error.HTTPError as e:
        print(f"✗ HTTP Error {e.code}: {e.reason}")
        return False
    except Exception as e:
        print(f"✗ Export error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Grafana Dashboard Manager for AUTOCOG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  GRAFANA_URL      Grafana base URL (default: http://host.docker.internal:3001)
  GRAFANA_API_KEY  Grafana API key for import/export operations

Examples:
  # List all dashboards
  python3 grafana_dashboard_manager.py --list

  # Validate all dashboards
  python3 grafana_dashboard_manager.py --validate

  # Import a specific dashboard
  python3 grafana_dashboard_manager.py --import-dashboard cycle_overview.json

  # Export a dashboard from Grafana
  python3 grafana_dashboard_manager.py --export-dashboard autocog-cycle-overview
        """,
    )

    parser.add_argument(
        "--dashboards-dir",
        type=Path,
        default=DEFAULT_DASHBOARDS_DIR,
        help=f"Directory containing dashboard JSON files (default: {DEFAULT_DASHBOARDS_DIR})",
    )

    parser.add_argument(
        "--grafana-url",
        default=DEFAULT_GRAFANA_URL,
        help=f"Grafana base URL (default: {DEFAULT_GRAFANA_URL})",
    )

    parser.add_argument(
        "--list", action="store_true", help="List all available dashboards"
    )

    parser.add_argument(
        "--validate", action="store_true", help="Validate all dashboard JSON files"
    )

    parser.add_argument(
        "--import-dashboard", metavar="FILE", help="Import a dashboard file to Grafana"
    )

    parser.add_argument(
        "--export-dashboard",
        metavar="UID",
        help="Export a dashboard from Grafana by UID",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DASHBOARDS_DIR,
        help="Output directory for export (default: dashboards directory)",
    )

    args = parser.parse_args()

    # Execute command
    if args.list:
        list_dashboards(args.dashboards_dir)
        return 0

    elif args.validate:
        success = validate_all_dashboards(args.dashboards_dir)
        return 0 if success else 1

    elif args.import_dashboard:
        file_path = args.dashboards_dir / args.import_dashboard
        if not file_path.exists():
            print(f"Error: File not found: {file_path}")
            return 1
        success = import_dashboard(file_path, args.grafana_url, DEFAULT_GRAFANA_API_KEY)
        return 0 if success else 1

    elif args.export_dashboard:
        success = export_dashboard(
            args.export_dashboard,
            args.grafana_url,
            DEFAULT_GRAFANA_API_KEY,
            args.output_dir,
        )
        return 0 if success else 1

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
