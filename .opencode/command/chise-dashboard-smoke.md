---
name: "chise-dashboard-smoke"
description: "ChiseAI: dashboard smoke checks (Playwright runbook and connectivity rules)"
disable-model-invocation: true
---

Run the dashboard smoke check and report what worked and what failed.

1. Connectivity rule (container vs host)
   - From a container: use `http://host.docker.internal:8502`
   - From the host: use `http://localhost:8502`

2. Health endpoint
   - Check: `/_stcore/health`

3. UI regression scan (Playwright MCP if available)
   - Load the page.
   - Iterate all tabs.
   - Open System Health.
   - Verify key panels render.
   - Capture screenshots under `screenshots/` on failure.

