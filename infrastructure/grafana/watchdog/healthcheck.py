#!/usr/bin/env python3
"""Health check script for grafana-watchdog that reads GRAFANA_URL dynamically."""

import os
import sys

import requests

grafana_url = os.environ.get("GRAFANA_URL", "http://host.docker.internal:3001")
health_url = f"{grafana_url.rstrip('/')}/api/health"

try:
    response = requests.get(health_url, timeout=5)
    if response.status_code == 200:
        sys.exit(0)
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
