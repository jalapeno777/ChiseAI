# Control Plane Dashboard Architecture

## Overview

The Control Plane Dashboard provides real-time visibility into the Autonomous Control Plane (ACP) with visualization, alerting, and operational controls. This document describes the architecture and design decisions.

## Components

### 1. Dashboard Backend API (`src/autonomous_control_plane/dashboard/api.py`)

The DashboardAPI class provides REST API endpoints for dashboard data:

- **Endpoints**:
  - `GET /api/v1/dashboard/health` - API health status
  - `GET /api/v1/dashboard/state` - Complete dashboard state
  - `GET /api/v1/dashboard/panels/{panel}` - Individual panel data
  - `POST /api/v1/dashboard/incidents/{id}/acknowledge` - Acknowledge incident
  - `POST /api/v1/dashboard/rollbacks/trigger` - Trigger rollback

- **Performance**: All endpoints respond in <200ms
- **Aggregation**: Pulls data from circuit breaker registry, incident manager, automation controller, and rollback coordinator

### 2. Dashboard Frontend Components (`src/autonomous_control_plane/dashboard/components/`)

Individual panel components for each ACP subsystem:

#### CircuitBreakerPanel
- Real-time circuit breaker states
- Filter by group
- Interactive controls: force_open, force_close, reset

#### IncidentPanel
- Incident timeline with filtering
- Search by title/description
- Severity and status filtering
- Acknowledge and resolve operations

#### SelfHealingPanel
- Healing attempt statistics
- Success/failure rates
- Active workflow tracking
- Pattern-based success rate analysis

#### RollbackPanel
- Rollback history
- Success rate tracking
- In-progress rollback monitoring
- Service-level statistics

#### SystemHealthPanel
- Overall health score calculation
- Component breakdown (25% weight each):
  - Circuit breakers
  - Incidents
  - Self-healing
  - Rollbacks
- Active alerts aggregation

### 3. Visualization Layer (`src/autonomous_control_plane/dashboard/visualization.py`)

Chart data generation for various visualization types:

- **Incident Trend Chart**: Line chart showing created/resolved incidents over time
- **Health Gauge**: Gauge chart showing overall system health
- **CB Status Chart**: Doughnut chart showing circuit breaker state distribution
- **Self-Healing Chart**: Bar chart showing healing success/failure
- **Severity Distribution**: Pie chart showing incident severity breakdown

### 4. Dashboard Server (`src/autonomous_control_plane/dashboard/server.py`)

FastAPI-based server providing:

- REST API endpoints
- WebSocket endpoint for real-time updates
- Static file serving
- CORS support

**Configuration**:
- HTTP Port: 8080 (default)
- WebSocket Port: 8765 (default)
- Update Interval: 5 seconds

### 5. Dashboard Client (`src/autonomous_control_plane/dashboard/client.py`)

WebSocket client for receiving real-time updates:

- WebSocket connection to dashboard server
- Automatic fallback to HTTP polling
- Async generator for state updates
- Ping/keep-alive support

### 6. Dashboard Scripts (`scripts/dashboard/`)

#### launch_dashboard.py
- Start dashboard server with configurable options
- Test mode with mock data
- Graceful shutdown handling

#### dashboard_cli.py
- CLI for querying dashboard data
- Health, state, panels, charts commands
- Incident search functionality

## Data Models

### HealthScore
- `overall_score`: Weighted average (0-100)
- `status`: HEALTHY, DEGRADED, UNHEALTHY, CRITICAL
- Component scores: circuit_breaker_score, incident_score, healing_score, rollback_score

### DashboardState
- Timestamp
- CircuitBreakerPanelData
- IncidentPanelData
- SelfHealingPanelData
- RollbackPanelData
- SystemHealthPanelData

### Panel Data Models
All panel data models support:
- `to_dict()` serialization
- Default empty state handling
- Metric aggregation

## Integration Points

### Circuit Breaker Registry
- `get_all_states_dict()` - Get all CB states
- `get_health()` - Get CB health metrics
- `force_open/force_close/reset()` - Manual controls

### Incident Manager
- `list_incidents()` - Query incidents
- `get_metrics()` - Incident statistics
- `transition_status()` - Update incident status

### Automation Controller
- `get_status()` - Controller status and stats
- `get_active_workflows()` - Active remediation workflows
- `get_all_workflows()` - Workflow history

### Rollback Coordinator
- `get_rollback_history()` - Rollback records
- `initiate_rollback()` - Trigger new rollback

## WebSocket Protocol

### Connection
- Endpoint: `ws://host:8765/acp-dashboard` or `/api/v1/dashboard/ws`
- Initial state sent on connection
- Updates every 5 seconds

### Message Format
```json
{
  "timestamp": "2026-03-12T10:00:00Z",
  "circuit_breakers": {...},
  "incidents": {...},
  "self_healing": {...},
  "rollbacks": {...},
  "system_health": {...}
}
```

### Client Messages
- `{"type": "refresh"}` - Request immediate refresh
- `{"type": "ping"}` - Keep-alive ping

## Testing

### Unit Tests
- Model serialization/deserialization
- Panel data aggregation
- Health score calculation
- Chart data generation

### Integration Tests
- API endpoint testing
- Component integration
- Mock ACP component testing

### E2E Tests
- Full dashboard state retrieval
- WebSocket connectivity
- Response time validation (<200ms)

## Performance Requirements

- REST API response time: <200ms
- WebSocket update interval: 5 seconds
- Test coverage: >80%
- Concurrent dashboard clients: 50+

## Deployment

### Requirements
- Python 3.11+
- FastAPI
- WebSockets (optional, with polling fallback)
- Uvicorn

### Configuration
```bash
# Start dashboard
python3 scripts/dashboard/launch_dashboard.py

# With custom ports
python3 scripts/dashboard/launch_dashboard.py --port 8080 --ws-port 8765

# Test mode
python3 scripts/dashboard/launch_dashboard.py --test-mode
```

### Docker
```yaml
services:
  dashboard:
    image: chiseai-dashboard
    ports:
      - "8080:8080"
      - "8765:8765"
    environment:
      - ACP_TRADING_MODE=paper
```

## Security

- Authentication hooks in DashboardServer
- CORS configuration for cross-origin requests
- Input validation on all endpoints
- Rate limiting (to be implemented)

## Future Enhancements

1. **Authentication**: JWT-based authentication
2. **Authorization**: Role-based access control
3. **Audit Logging**: All dashboard actions logged
4. **Alerting**: Email/Slack notifications for critical events
5. **Historical Data**: Time-series database integration
6. **Custom Dashboards**: User-configurable panels
7. **Mobile Support**: Responsive UI design

## References

- ST-CONTROL-003: Control Plane Dashboard
- ST-CONTROL-001: Telemetry Pipeline (dependency)
- ST-CONTROL-002: Self-Healing Automation (dependency)
