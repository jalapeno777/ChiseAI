# ST-NS-022: Configurable Alert Thresholds - Technical Implementation Plan

**Story ID:** ST-NS-022  
**Epic:** EP-NS-005 (User Experience & Interface)  
**Priority:** P1-HIGH  
**Story Points:** 6  
**FR Coverage:** FR-022  
**Status:** Planned → Ready for Implementation

---

## Executive Summary

This document provides a comprehensive implementation plan for ST-NS-022: Configurable Alert Thresholds. The feature enables users to customize their alert notification preferences through a dashboard UI, with changes persisted to PostgreSQL and taking effect immediately across the Discord alert system.

**Key Design Principles:**
- **Immediate Effect:** Changes apply instantly without restart
- **Validation First:** Prevent invalid threshold combinations at API and UI layers
- **Per-User Scope:** Each user maintains independent alert preferences
- **Backward Compatible:** System works with defaults when no preferences exist

---

## 1. Architecture Overview

### 1.1 System Context Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           User Interaction Layer                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────┐  │
│  │  Dashboard UI   │    │ Threshold Config │    │ Signal List Panel      │  │
│  │  (Streamlit)    │◄──►│   Component     │◄──►│ (with threshold info)  │  │
│  └─────────────────┘    └─────────────────┘    └─────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ HTTP/WebSocket
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API Layer (FastAPI)                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    User Preferences Router (/api/v1/user)               │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │ │
│  │  │ GET /alerts  │ │PUT /alerts   │ │GET /validate │ │GET /defaults │   │ │
│  │  │  (get prefs) │ │ (update)     │ │ (validate)   │ │  (defaults)  │   │ │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Service Layer                                      │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐ │
│  │ UserPreferenceService│  │ ValidationService    │  │ EventEmitter       │ │
│  │  (CRUD + caching)    │  │ (threshold rules)    │  │ (config changes)   │ │
│  └──────────────────────┘  └──────────────────────┘  └────────────────────┘ │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Data Layer                                           │
│  ┌──────────────────────────┐    ┌─────────────────────────────────────────┐ │
│  │    PostgreSQL            │    │     Redis (cache + pub/sub)             │ │
│  │  user_alert_preferences  │    │  user:{id}:alert_prefs (TTL: 5min)      │ │
│  └──────────────────────────┘    │  pubsub: prefs:updated (real-time)      │ │
│                                  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼ (Event: prefs:updated)
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Alert Delivery Layer                                    │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                    Discord Alert System                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │  │
│  │  │AlertSender   │  │AlertFormatter│  │ RateLimiter  │  │ConfigLoader│ │  │
│  │  │ (receives    │  │ (formats     │  │ (applies user│  │ (reloads on│ │  │
│  │  │  updates)    │  │  per prefs)  │  │  freq limit) │  │  change)    │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘ │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Interaction Flow

```
User adjusts threshold in UI
         │
         ▼
┌────────────────────┐
│ UI validates input │──► Show validation errors inline
└────────┬───────────┘
         │ (valid input)
         ▼
┌────────────────────┐
│ PUT /api/v1/user/  │
│   alert-preferences│
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ ValidationService  │──► Validate business rules
│   validates        │    (e.g., min < max, etc.)
└────────┬───────────┘
         │ (valid)
         ▼
┌────────────────────┐
│ Update PostgreSQL  │
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ Invalidate Redis   │
│   cache            │
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ Publish event      │──► prefs:updated channel
│   prefs:updated    │    (AlertSender subscribes)
└────────────────────┘
         │
         ▼
┌────────────────────┐
│ AlertSender reloads│──► Applies new thresholds
│   configuration    │    immediately
└────────────────────┘
```

---

## 2. API Endpoint Design

### 2.1 Endpoint Specification

#### Base Path: `/api/v1/user/alert-preferences`

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/v1/user/alert-preferences` | Get current user's alert preferences | Yes |
| PUT | `/api/v1/user/alert-preferences` | Update alert preferences | Yes |
| POST | `/api/v1/user/alert-preferences/validate` | Validate proposed preferences | Yes |
| GET | `/api/v1/user/alert-preferences/defaults` | Get system default values | No |
| GET | `/api/v1/user/alert-preferences/schema` | Get validation schema | No |

### 2.2 Request/Response Models

#### AlertPreferences (Response Model)

```python
class AlertPreferencesResponse(BaseModel):
    """User alert preferences response."""
    
    # Confidence threshold for Discord alerts (default 40%, range 20-80%)
    confidence_threshold_pct: float = Field(
        default=40.0,
        ge=20.0,
        le=80.0,
        description="Minimum confidence % for Discord alerts (20-80)"
    )
    
    # Signal frequency limit (max alerts per hour)
    max_alerts_per_hour: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Maximum alerts per hour (1-60)"
    )
    
    # Risk threshold for notifications
    risk_threshold_pct: float = Field(
        default=75.0,
        ge=50.0,
        le=95.0,
        description="Risk threshold % for notifications (50-95)"
    )
    
    # Watchlist threshold (40-74% range)
    watchlist_threshold_pct: float = Field(
        default=40.0,
        ge=20.0,
        le=74.0,
        description="Minimum confidence % for watchlist alerts (20-74)"
    )
    
    # Enable/disable different alert types
    enable_actionable_alerts: bool = Field(
        default=True,
        description="Enable 75%+ actionable alerts"
    )
    enable_watchlist_alerts: bool = Field(
        default=True,
        description="Enable 40-74% watchlist alerts"
    )
    enable_risk_alerts: bool = Field(
        default=True,
        description="Enable risk threshold breach alerts"
    )
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    version: int = Field(default=1, description="Schema version for migrations")
```

#### Update Request (PUT)

```python
class UpdateAlertPreferencesRequest(BaseModel):
    """Request to update alert preferences."""
    
    confidence_threshold_pct: float | None = None
    max_alerts_per_hour: int | None = None
    risk_threshold_pct: float | None = None
    watchlist_threshold_pct: float | None = None
    enable_actionable_alerts: bool | None = None
    enable_watchlist_alerts: bool | None = None
    enable_risk_alerts: bool | None = None
    
    @model_validator(mode='after')
    def validate_thresholds(self):
        """Cross-field validation."""
        if (self.confidence_threshold_pct is not None and 
            self.watchlist_threshold_pct is not None):
            if self.confidence_threshold_pct <= self.watchlist_threshold_pct:
                raise ValueError(
                    "confidence_threshold must be greater than watchlist_threshold"
                )
        return self
```

### 2.3 Validation Rules

| Rule | Error Message | HTTP Status |
|------|---------------|-------------|
| `confidence_threshold_pct` must be > `watchlist_threshold_pct` | "Confidence threshold must be greater than watchlist threshold" | 400 |
| `confidence_threshold_pct` ∈ [20, 80] | "Confidence threshold must be between 20% and 80%" | 400 |
| `watchlist_threshold_pct` ∈ [20, 74] | "Watchlist threshold must be between 20% and 74%" | 400 |
| `max_alerts_per_hour` ∈ [1, 60] | "Max alerts per hour must be between 1 and 60" | 400 |
| `risk_threshold_pct` ∈ [50, 95] | "Risk threshold must be between 50% and 95%" | 400 |

### 2.4 Error Response Format

```json
{
  "detail": "Validation failed",
  "errors": [
    {
      "field": "confidence_threshold_pct",
      "message": "Confidence threshold must be between 20% and 80%",
      "received": 85.0,
      "allowed_range": [20.0, 80.0]
    }
  ],
  "timestamp": "2026-02-20T21:30:00Z"
}
```

---

## 3. Database Schema Design

### 3.1 PostgreSQL Schema

```sql
-- User alert preferences table
CREATE TABLE user_alert_preferences (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    
    -- Alert thresholds
    confidence_threshold_pct DECIMAL(5, 2) NOT NULL DEFAULT 40.00 
        CONSTRAINT chk_confidence_range CHECK (confidence_threshold_pct BETWEEN 20.00 AND 80.00),
    
    watchlist_threshold_pct DECIMAL(5, 2) NOT NULL DEFAULT 40.00
        CONSTRAINT chk_watchlist_range CHECK (watchlist_threshold_pct BETWEEN 20.00 AND 74.00),
    
    max_alerts_per_hour INTEGER NOT NULL DEFAULT 10
        CONSTRAINT chk_max_alerts_range CHECK (max_alerts_per_hour BETWEEN 1 AND 60),
    
    risk_threshold_pct DECIMAL(5, 2) NOT NULL DEFAULT 75.00
        CONSTRAINT chk_risk_range CHECK (risk_threshold_pct BETWEEN 50.00 AND 95.00),
    
    -- Alert type toggles
    enable_actionable_alerts BOOLEAN NOT NULL DEFAULT TRUE,
    enable_watchlist_alerts BOOLEAN NOT NULL DEFAULT TRUE,
    enable_risk_alerts BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Cross-field validation constraint
    CONSTRAINT chk_threshold_order CHECK (confidence_threshold_pct > watchlist_threshold_pct),
    
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Audit
    updated_by VARCHAR(255)
);

-- Indexes for efficient lookups
CREATE INDEX idx_user_prefs_user_id ON user_alert_preferences(user_id);
CREATE INDEX idx_user_prefs_updated_at ON user_alert_preferences(updated_at);

-- Audit log for preference changes
CREATE TABLE user_alert_preferences_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by VARCHAR(255),
    
    -- Old values
    old_confidence_threshold_pct DECIMAL(5, 2),
    old_watchlist_threshold_pct DECIMAL(5, 2),
    old_max_alerts_per_hour INTEGER,
    old_risk_threshold_pct DECIMAL(5, 2),
    
    -- New values
    new_confidence_threshold_pct DECIMAL(5, 2),
    new_watchlist_threshold_pct DECIMAL(5, 2),
    new_max_alerts_per_hour INTEGER,
    new_risk_threshold_pct DECIMAL(5, 2),
    
    change_reason TEXT
);

CREATE INDEX idx_prefs_history_user_id ON user_alert_preferences_history(user_id);
CREATE INDEX idx_prefs_history_changed_at ON user_alert_preferences_history(changed_at);

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_user_prefs_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_user_prefs_timestamp
    BEFORE UPDATE ON user_alert_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_user_prefs_timestamp();

-- Trigger to log changes to history table
CREATE OR REPLACE FUNCTION log_user_prefs_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.confidence_threshold_pct IS DISTINCT FROM NEW.confidence_threshold_pct OR
        OLD.watchlist_threshold_pct IS DISTINCT FROM NEW.watchlist_threshold_pct OR
        OLD.max_alerts_per_hour IS DISTINCT FROM NEW.max_alerts_per_hour OR
        OLD.risk_threshold_pct IS DISTINCT FROM NEW.risk_threshold_pct) THEN
        
        INSERT INTO user_alert_preferences_history (
            user_id, changed_by,
            old_confidence_threshold_pct, new_confidence_threshold_pct,
            old_watchlist_threshold_pct, new_watchlist_threshold_pct,
            old_max_alerts_per_hour, new_max_alerts_per_hour,
            old_risk_threshold_pct, new_risk_threshold_pct
        ) VALUES (
            NEW.user_id, NEW.updated_by,
            OLD.confidence_threshold_pct, NEW.confidence_threshold_pct,
            OLD.watchlist_threshold_pct, NEW.watchlist_threshold_pct,
            OLD.max_alerts_per_hour, NEW.max_alerts_per_hour,
            OLD.risk_threshold_pct, NEW.risk_threshold_pct
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_log_user_prefs_changes
    AFTER UPDATE ON user_alert_preferences
    FOR EACH ROW
    EXECUTE FUNCTION log_user_prefs_changes();
```

### 3.2 Redis Cache Schema

```
Key Pattern: user:{user_id}:alert_prefs
Type: Hash
TTL: 300 seconds (5 minutes)

Fields:
  - confidence_threshold_pct: "40.0"
  - watchlist_threshold_pct: "40.0"
  - max_alerts_per_hour: "10"
  - risk_threshold_pct: "75.0"
  - enable_actionable_alerts: "true"
  - enable_watchlist_alerts: "true"
  - enable_risk_alerts: "true"
  - updated_at: "2026-02-20T21:30:00Z"

Pub/Sub Channel: prefs:updated
Message Format: {"user_id": "...", "timestamp": "...", "changed_fields": [...]}
```

---

## 4. UI/UX Component Structure

### 4.1 Dashboard Component Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ChiseAI Dashboard                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Navigation: [Signals] [Portfolio] [Settings ▼] [Help]              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  ⚙️ Alert Configuration                                  [Save] [Reset] ││
│  ├─────────────────────────────────────────────────────────────────────────┤│
│  │                                                                         ││
│  │  ┌───────────────────────────────────────────────────────────────────┐ ││
│  │  │ 📊 Confidence Thresholds                                          │ ││
│  │  │                                                                   │ ││
│  │  │  Watchlist Alerts (40-74%)               [===============●====]  │ ││
│  │  │  Min: 40% ──────────────────────────────────────●───────────── 74%│ ││
│  │  │  Current: 40%                              ▲                    │ ││
│  │  │                                            Range: 20-74%        │ ││
│  │  │                                                                   │ ││
│  │  │  Actionable Alerts (75%+)                [==================●=]  │ ││
│  │  │  Current: 75%                              (Fixed threshold)    │ ││
│  │  │                                                                   │ ││
│  │  │  Discord Alert Threshold                 [=========●==========]  │ ││
│  │  │  Min: 40% ─────────────────────────────●───────────────────── 80%│ ││
│  │  │  Current: 40%                                                    │ ││
│  │  │  ℹ️ Alerts at or above this confidence will be sent to Discord  │ ││
│  │  └───────────────────────────────────────────────────────────────────┘ ││
│  │                                                                         ││
│  │  ┌───────────────────────────────────────────────────────────────────┐ ││
│  │  │ 🔔 Signal Frequency                                               │ ││
│  │  │                                                                   │ ││
│  │  │  Maximum alerts per hour                 [=========●==========]  │ ││
│  │  │  Current: 10                            1 ───────●─────────── 60 │ ││
│  │  │                                                                   │ ││
│  │  │  ℹ️ Rate limiting prevents alert spam. Excess signals queued.    │ ││
│  │  └───────────────────────────────────────────────────────────────────┘ ││
│  │                                                                         ││
│  │  ┌───────────────────────────────────────────────────────────────────┐ ││
│  │  │ ⚠️ Risk Notifications                                             │ ││
│  │  │                                                                   │ ││
│  │  │  Risk threshold for notifications        [================●===]  │ ││
│  │  │  Current: 75%                          50% ────────────●──── 95%│ ││
│  │  │                                                                   │ ││
│  │  │  [✓] Enable risk threshold alerts                               │ ││
│  │  │  [✓] Enable actionable signal alerts                            │ ││
│  │  │  [✓] Enable watchlist alerts                                    │ ││
│  │  └───────────────────────────────────────────────────────────────────┘ ││
│  │                                                                         ││
│  │  ┌───────────────────────────────────────────────────────────────────┐ ││
│  │  │ 📝 Current Settings Summary                                       │ ││
│  │  │                                                                   │ ││
│  │  │  • Discord alerts: ≥40% confidence                              │ ││
│  │  │  • Max frequency: 10 alerts/hour                                │ ││
│  │  │  • Risk notifications: ≥75% threshold                           │ ││
│  │  │  • Watchlist: 40-74% range enabled                              │ ││
│  │  │                                                                   │ ││
│  │  │  Last updated: 2026-02-20 21:30 UTC                             │ ││
│  │  └───────────────────────────────────────────────────────────────────┘ ││
│  │                                                                         ││
│  │  ⚠️ Validation Error: Confidence threshold must be greater than        ││
│  │     watchlist threshold                                                ││
│  │                                                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Component Hierarchy

```
dashboard/
├── components/
│   └── alert_config/
│       ├── __init__.py
│       ├── alert_config_panel.py      # Main container
│       ├── confidence_thresholds.py    # Confidence slider group
│       ├── signal_frequency.py         # Alerts/hour control
│       ├── risk_notifications.py       # Risk threshold + toggles
│       ├── settings_summary.py         # Read-only summary card
│       ├── validation_display.py       # Error message component
│       └── threshold_slider.py         # Reusable slider component
├── services/
│   └── alert_preferences_service.py    # API client
├── models/
│   └── alert_preferences.py            # Pydantic models
└── validators/
    └── threshold_validator.py          # Client-side validation
```

### 4.3 Key UI Components

#### ThresholdSlider Component

```python
class ThresholdSlider:
    """Reusable threshold slider with validation.
    
    Props:
        label: str                    # Display label
        value: float                  # Current value
        min_value: float              # Minimum allowed
        max_value: float              # Maximum allowed
        step: float = 1.0             # Step increment
        unit: str = "%"               # Unit suffix
        help_text: str | None = None  # Tooltip/help text
        on_change: Callable           # Change callback
        disabled: bool = False        # Disable interaction
    """
```

#### ValidationDisplay Component

```python
class ValidationDisplay:
    """Inline validation error display.
    
    Props:
        errors: list[ValidationError]  # List of errors
        field_mapping: dict[str, str]  # Field name mapping
    
    Behavior:
        - Shows inline below relevant fields
        - Highlights invalid fields in red
        - Prevents form submission until resolved
    """
```

---

## 5. Implementation Tasks Breakdown

### Phase 1: Data Layer (Story Points: 1.5)

| Task | File(s) | Description | Est. Hours |
|------|---------|-------------|------------|
| 1.1 | `src/user_preferences/models.py` | Create Pydantic models for preferences | 1 |
| 1.2 | `src/user_preferences/storage/postgres.py` | PostgreSQL storage implementation | 2 |
| 1.3 | `src/user_preferences/storage/cache.py` | Redis caching layer | 1.5 |
| 1.4 | `scripts/migrations/001_create_user_alert_preferences.sql` | Database migration | 0.5 |
| 1.5 | `tests/test_user_preferences/test_storage.py` | Storage layer unit tests | 2 |

### Phase 2: Service Layer (Story Points: 1.5)

| Task | File(s) | Description | Est. Hours |
|------|---------|-------------|------------|
| 2.1 | `src/user_preferences/service.py` | Business logic service | 2 |
| 2.2 | `src/user_preferences/validation.py` | Validation rules engine | 1.5 |
| 2.3 | `src/user_preferences/events.py` | Event emitter for changes | 1 |
| 2.4 | `tests/test_user_preferences/test_service.py` | Service layer tests | 2 |
| 2.5 | `tests/test_user_preferences/test_validation.py` | Validation tests | 1.5 |

### Phase 3: API Layer (Story Points: 1.5)

| Task | File(s) | Description | Est. Hours |
|------|---------|-------------|------------|
| 3.1 | `src/api/user_preferences_router.py` | FastAPI router endpoints | 2 |
| 3.2 | `src/api/dependencies.py` | Auth & service dependencies | 1 |
| 3.3 | `src/main.py` | Register new router | 0.5 |
| 3.4 | `tests/test_api/test_user_preferences.py` | API integration tests | 2 |

### Phase 4: Alert System Integration (Story Points: 1)

| Task | File(s) | Description | Est. Hours |
|------|---------|-------------|------------|
| 4.1 | `src/discord_alerts/user_config_loader.py` | Load user-specific config | 1 |
| 4.2 | `src/discord_alerts/alert_sender.py` | Integrate with user prefs | 1.5 |
| 4.3 | `src/discord_alerts/config.py` | Add user preference support | 1 |
| 4.4 | `tests/test_discord_alerts/test_user_config.py` | Integration tests | 1.5 |

### Phase 5: Dashboard UI (Story Points: 2.5)

| Task | File(s) | Description | Est. Hours |
|------|---------|-------------|------------|
| 5.1 | `src/dashboard/components/alert_config/` | UI components directory | 0.5 |
| 5.2 | `src/dashboard/components/alert_config/threshold_slider.py` | Slider component | 1.5 |
| 5.3 | `src/dashboard/components/alert_config/alert_config_panel.py` | Main panel | 2 |
| 5.4 | `src/dashboard/services/alert_preferences_service.py` | API client | 1 |
| 5.5 | `src/dashboard/pages/settings.py` | Settings page integration | 1.5 |
| 5.6 | `tests/test_dashboard/test_alert_config.py` | UI tests | 2 |

### Phase 6: Documentation & Deployment (Story Points: 0.5)

| Task | File(s) | Description | Est. Hours |
|------|---------|-------------|------------|
| 6.1 | `docs/api/user-preferences.md` | API documentation | 1 |
| 6.2 | `docs/runbooks/alert-configuration.md` | Operator runbook | 0.5 |
| 6.3 | Update `.env.example` | Add new env vars | 0.5 |
| 6.4 | `infrastructure/terraform/` | DB schema provisioning | 1 |

### Summary

| Phase | Story Points | Files Created | Est. Hours |
|-------|--------------|---------------|------------|
| Phase 1: Data Layer | 1.5 | 5 | 7 |
| Phase 2: Service Layer | 1.5 | 5 | 8 |
| Phase 3: API Layer | 1.5 | 4 | 5.5 |
| Phase 4: Alert Integration | 1 | 4 | 5 |
| Phase 5: Dashboard UI | 2.5 | 6 | 8.5 |
| Phase 6: Documentation | 0.5 | 4 | 3 |
| **Total** | **6** | **28** | **37** |

---

## 6. Test Strategy

### 6.1 Test Pyramid

```
                    ┌─────────────┐
                    │   E2E Tests │  (3 tests)
                    │  (Playwright)│
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │ Integration │  (12 tests)
                    │    Tests    │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │      Unit Tests         │  (45 tests)
              │  (Service, Validation,  │
              │   Storage, API)         │
              └─────────────────────────┘
```

### 6.2 Test Coverage Requirements

| Component | Target Coverage | Critical Paths |
|-----------|-----------------|----------------|
| Storage Layer | 90%+ | CRUD operations, caching, error handling |
| Validation Service | 95%+ | All validation rules, edge cases |
| API Router | 85%+ | All endpoints, error responses |
| Alert Integration | 80%+ | Config reload, user preference application |
| UI Components | 70%+ | Form validation, state management |

### 6.3 Key Test Cases

#### Unit Tests (45 tests)

**Validation Tests (15 tests):**
- `test_confidence_threshold_range`: Validates 20-80% range
- `test_watchlist_threshold_range`: Validates 20-74% range
- `test_confidence_gt_watchlist`: Cross-field validation
- `test_max_alerts_per_hour_range`: Validates 1-60 range
- `test_risk_threshold_range`: Validates 50-95% range
- `test_edge_cases`: Boundary values (20.0, 80.0, etc.)
- `test_invalid_combinations`: Error message quality

**Storage Tests (15 tests):**
- `test_create_preferences`: New user preferences
- `test_get_preferences`: Retrieval with caching
- `test_update_preferences`: Update with history log
- `test_cache_invalidation`: Redis cache clearing
- `test_concurrent_updates`: Race condition handling
- `test_default_values`: Fallback when no preferences

**Service Tests (15 tests):**
- `test_get_user_preferences`: Service layer retrieval
- `test_update_with_validation`: Valid update flow
- `test_update_invalid_data`: Rejection handling
- `test_event_publication`: prefs:updated events
- `test_audit_logging`: History table logging

#### Integration Tests (12 tests)

**API Integration (6 tests):**
- `test_get_preferences_endpoint`: GET /api/v1/user/alert-preferences
- `test_update_preferences_endpoint`: PUT endpoint
- `test_validation_endpoint`: POST /validate
- `test_unauthorized_access`: 401/403 responses
- `test_rate_limiting`: API rate limits
- `test_invalid_json_handling`: Malformed request bodies

**Alert System Integration (6 tests):**
- `test_config_reload_on_change`: Real-time config update
- `test_user_specific_thresholds`: Different users, different thresholds
- `test_alert_suppression_by_frequency`: Max alerts/hour enforcement
- `test_confidence_filtering`: Discord alert filtering
- `test_risk_alert_thresholds`: Risk notification thresholds

#### E2E Tests (3 tests)

- `test_complete_user_workflow`: User changes threshold → sees effect
- `test_validation_prevents_save`: Invalid combination blocked
- `test_multiple_users_isolation`: User A's changes don't affect User B

### 6.4 Test Files Structure

```
tests/
├── test_user_preferences/
│   ├── __init__.py
│   ├── conftest.py                    # Shared fixtures
│   ├── test_models.py                 # Pydantic model tests
│   ├── test_validation.py             # Validation logic tests
│   ├── test_service.py                # Service layer tests
│   └── test_storage/
│       ├── __init__.py
│       ├── test_postgres.py           # PostgreSQL tests
│       └── test_cache.py              # Redis cache tests
├── test_api/
│   └── test_user_preferences.py       # API endpoint tests
├── test_discord_alerts/
│   └── test_user_config.py            # Alert integration tests
└── test_dashboard/
    └── test_alert_config.py           # UI component tests
```

### 6.5 Test Fixtures

```python
# tests/test_user_preferences/conftest.py

@pytest.fixture
def sample_preferences() -> AlertPreferences:
    """Sample valid alert preferences."""
    return AlertPreferences(
        user_id="user_123",
        confidence_threshold_pct=40.0,
        watchlist_threshold_pct=35.0,
        max_alerts_per_hour=10,
        risk_threshold_pct=75.0,
        enable_actionable_alerts=True,
        enable_watchlist_alerts=True,
        enable_risk_alerts=True
    )

@pytest.fixture
async def postgres_storage(postgres_config):
    """PostgreSQL storage fixture with cleanup."""
    storage = PostgresUserPreferenceStorage(postgres_config)
    await storage.initialize()
    yield storage
    # Cleanup
    await storage.delete_all_test_data()
    await storage.close()

@pytest.fixture
async def redis_cache():
    """Redis cache fixture."""
    cache = RedisPreferenceCache()
    await cache.clear_test_keys()
    yield cache
    await cache.clear_test_keys()
```

---

## 7. File Changes Summary

### New Files (28 files)

```
src/
├── user_preferences/
│   ├── __init__.py
│   ├── models.py                      # Pydantic models
│   ├── service.py                     # Business logic
│   ├── validation.py                  # Validation rules
│   ├── events.py                      # Event emitter
│   └── storage/
│       ├── __init__.py
│       ├── postgres.py                # PostgreSQL storage
│       └── cache.py                   # Redis caching
├── api/
│   └── user_preferences_router.py     # FastAPI endpoints
└── dashboard/
    ├── services/
    │   └── alert_preferences_service.py
    └── components/
        └── alert_config/
            ├── __init__.py
            ├── alert_config_panel.py
            ├── confidence_thresholds.py
            ├── signal_frequency.py
            ├── risk_notifications.py
            ├── settings_summary.py
            ├── validation_display.py
            └── threshold_slider.py

scripts/
└── migrations/
    └── 001_create_user_alert_preferences.sql

docs/
├── api/
│   └── user-preferences.md
└── runbooks/
    └── alert-configuration.md

tests/
├── test_user_preferences/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_validation.py
│   ├── test_service.py
│   └── test_storage/
│       ├── __init__.py
│       ├── test_postgres.py
│       └── test_cache.py
├── test_api/
│   └── test_user_preferences.py
├── test_discord_alerts/
│   └── test_user_config.py
└── test_dashboard/
    └── test_alert_config.py
```

### Modified Files (4 files)

```
src/
├── main.py                            # Register new router
├── discord_alerts/
│   ├── config.py                      # Add user preference support
│   └── alert_sender.py                # Load user-specific thresholds
└── dashboard/
    └── pages/
        └── settings.py                # Add alert config panel

infrastructure/
└── terraform/
    └── postgres_schema.tf             # Add user preferences table
```

---

## 8. Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Cache invalidation failures | Medium | High | Implement TTL + explicit invalidation; health checks |
| Database migration conflicts | Low | High | Use backward-compatible migrations; test in staging |
| Cross-user data leakage | Low | Critical | Strict user_id filtering in all queries; integration tests |
| Validation bypass via API | Low | Critical | Server-side validation mandatory; never trust client |
| Performance degradation | Medium | Medium | Redis caching; connection pooling; query optimization |
| Alert system disruption | Low | High | Feature flags; gradual rollout; rollback plan |

---

## 9. Deployment Plan

### Pre-Deployment
1. Run database migration: `psql -f scripts/migrations/001_create_user_alert_preferences.sql`
2. Deploy infrastructure changes: `terraform apply`
3. Verify Redis connectivity and pub/sub functionality

### Deployment Steps
1. Deploy API changes (Phase 1-3)
2. Deploy alert system integration (Phase 4)
3. Deploy dashboard UI (Phase 5)
4. Enable feature flag for 10% of users
5. Monitor for 24 hours
6. Gradual rollout to 100%

### Rollback Plan
1. Disable feature flag immediately
2. Alert system falls back to default thresholds
3. Database schema remains (backward compatible)
4. Investigate and fix issues
5. Re-deploy when resolved

---

## 10. Acceptance Criteria Verification

| AC | Verification Method | Test Location |
|----|---------------------|---------------|
| Alert thresholds configurable per user preference | E2E test: user changes threshold, verifies in DB | `test_complete_user_workflow` |
| UI allows adjustment of confidence threshold (default 40%, range 20-80%) | Unit test: validation accepts/rejects values | `test_validation.py` |
| UI allows adjustment of signal frequency (max alerts per hour) | Integration test: API accepts valid values | `test_update_preferences_endpoint` |
| UI allows adjustment of risk threshold for notifications | Component test: slider updates state correctly | `test_alert_config.py` |
| Changes are persisted and take effect immediately | Integration test: Redis pub/sub + alert reload | `test_config_reload_on_change` |
| Configuration is validated (prevents invalid combinations) | Unit test: validation rejects invalid combos | `test_invalid_combinations` |

---

## 11. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| API response time (p95) | <100ms | APM monitoring |
| Cache hit rate | >80% | Redis metrics |
| Test coverage | >80% | pytest-cov |
| UI load time | <1s | Browser profiling |
| User preference adoption | >50% in 30 days | Analytics |

---

**Document Version:** 1.0  
**Created:** 2026-02-20  
**Author:** Implementation Team  
**Status:** Ready for Implementation
