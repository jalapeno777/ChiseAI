# Sprint Summary: Confidence Scoring & ECE

## Sprint Information

| Field | Value |
|-------|-------|
| **Sprint ID** | p0-3 |
| **Sprint Name** | Confidence Scoring & ECE |
| **Phase** | Phase 1 (Foundation) |
| **Status** | planned |
| **Start Date** | 2026-02-08 |
| **Target Finish** | 2026-05-09 (90-day window) |

## Epics Covered

| Epic ID | Epic Name | Stories | Points |
|---------|-----------|---------|--------|
| EP-CONF-001 | Confidence Scoring - ECE/Thresholds | 3 | 10 |

## Stories

### EP-CONF-001: Confidence Scoring - ECE/Thresholds (3 stories, 10 points)

| Story ID | Title | Points | Priority | Status |
|----------|-------|--------|----------|--------|
| ST-CONF-001 | ECE Calculation per Strategy/Signal Type | 4 | P0-CRITICAL | planned |
| ST-CONF-002 | Confidence Threshold Calibration - Dynamic vs Fixed | 3 | P1-HIGH | planned |
| ST-CONF-003 | Confidence Threshold Enforcement - <40% Filter | 3 | P0-CRITICAL | planned |

## Summary Statistics

| Metric | Value |
|--------|-------|
| **Total Stories** | 3 |
| **Total Story Points** | 10 |
| **P0-CRITICAL Stories** | 2 |
| **P1-HIGH Stories** | 1 |

## Dependencies

### Internal Dependencies
- ST-CONF-001 (ECE Calculation) must complete before ST-CONF-002 (Threshold Calibration)
- ST-CONF-002 must complete before ST-CONF-003 (Threshold Enforcement)
- Requires backtest data from Sprint p0-2 for ECE calculation

### External Dependencies
- InfluxDB for storing ECE time-series data
- Grafana for ECE visualization
- Discord webhook for filtered signal logging

### Sprint Dependencies
- Sprint p0-2 (Data & Backtesting) should complete before starting this sprint
- Historical prediction-outcome pairs needed from backtest runner

## Success Criteria

1. **All P0-CRITICAL stories completed** (2 stories)
2. **ECE calculation operational** - 10-bin calibration per signal type
3. **Threshold calibration working** - Dynamic and fixed modes functional
4. **Discord filter active** - No alerts below 40% confidence (default)
5. **ECE trending visible** - Historical calibration tracked in Grafana
6. **Filter statistics available** - Filtered count, rate, and trends visible

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Insufficient historical data | High | Require minimum 100 predictions per signal type |
| ECE calculation performance | Low | Cache ECE values, update daily |
| Threshold tuning complexity | Medium | Start with fixed threshold, add dynamic later |

## Notes

- This is a focused sprint on calibration and confidence scoring
- ECE (Expected Calibration Error) is critical for trustworthy predictions
- The 40% confidence filter prevents low-quality signals from reaching Discord
- Dynamic threshold calibration adapts to changing market conditions
