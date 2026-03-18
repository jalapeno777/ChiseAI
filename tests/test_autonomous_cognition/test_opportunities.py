"""Tests for the opportunity detection engine.

Covers all 10+ opportunity types with mocked detection contexts,
scoring, configuration enablement, and the orchestrator.
"""

from __future__ import annotations

import asyncio

import pytest

from autonomous_cognition.opportunity_detection import (
    CIBottleneckDetector,
    ConfigurationDriftDetector,
    DependencyVulnerabilityDetector,
    DetectionConfig,
    DetectionResult,
    DocumentationGapDetector,
    HighErrorRateDetector,
    LowTestCoverageDetector,
    MemoryAnomalyDetector,
    Opportunity,
    OpportunityCategory,
    OpportunityDetector,
    OpportunitySeverity,
    PerformanceRegressionDetector,
    SlowApiEndpointDetector,
    UnusedCodeDetector,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_config():
    """Default detection config."""
    return DetectionConfig()


@pytest.fixture
def selective_config():
    """Config with only a few types enabled."""
    return DetectionConfig(
        enabled_types={"low_test_coverage", "high_error_rate"},
        min_confidence=0.5,
    )


@pytest.fixture
def detector(default_config):
    """Full OpportunityDetector with default config."""
    return OpportunityDetector(default_config)


# ---------------------------------------------------------------------------
# Opportunity dataclass tests
# ---------------------------------------------------------------------------


class TestOpportunity:
    """Tests for the Opportunity data model."""

    def test_to_dict_contains_all_fields(self):
        opp = Opportunity(
            type="test_type",
            title="Test Title",
            description="Test description",
            severity=OpportunitySeverity.HIGH,
            category=OpportunityCategory.PERFORMANCE,
            confidence=0.9,
            score=0.8,
            source="unit_test",
            file_path="/src/foo.py",
            suggestion="Fix it.",
        )
        d = opp.to_dict()
        assert d["type"] == "test_type"
        assert d["title"] == "Test Title"
        assert d["severity"] == "HIGH"
        assert d["category"] == "performance"
        assert d["confidence"] == 0.9
        assert d["score"] == 0.8
        assert d["source"] == "unit_test"
        assert d["file_path"] == "/src/foo.py"
        assert d["suggestion"] == "Fix it."
        assert "id" in d
        assert "timestamp" in d

    def test_defaults_are_sensible(self):
        opp = Opportunity()
        assert opp.type == ""
        assert opp.severity == OpportunitySeverity.MEDIUM
        assert opp.category == OpportunityCategory.CODE_QUALITY
        assert 0.0 <= opp.confidence <= 1.0
        assert 0.0 <= opp.score <= 1.0
        assert opp.timestamp > 0


# ---------------------------------------------------------------------------
# Detector 1: Low test coverage
# ---------------------------------------------------------------------------


class TestLowTestCoverageDetector:
    """Tests for low test coverage detection."""

    @pytest.mark.asyncio
    async def test_detects_files_below_threshold(self):
        det = LowTestCoverageDetector()
        ctx = {
            "coverage_data": {
                "src/foo.py": 45.0,
                "src/bar.py": 20.0,
                "src/baz.py": 85.0,
            },
            "coverage_threshold": 80.0,
        }
        opps = await det.detect(ctx)
        types = {o.file_path for o in opps}
        assert "src/foo.py" in types
        assert "src/bar.py" in types
        assert "src/baz.py" not in types

    @pytest.mark.asyncio
    async def test_severity_levels(self):
        det = LowTestCoverageDetector()
        ctx = {
            "coverage_data": {
                "critical.py": 10.0,
                "high.py": 40.0,
                "medium.py": 60.0,
            },
            "coverage_threshold": 80.0,
        }
        opps = await det.detect(ctx)
        by_path = {o.file_path: o.severity for o in opps}
        assert by_path["critical.py"] == OpportunitySeverity.CRITICAL
        assert by_path["high.py"] == OpportunitySeverity.HIGH
        assert by_path["medium.py"] == OpportunitySeverity.MEDIUM

    @pytest.mark.asyncio
    async def test_no_opportunities_when_all_above_threshold(self):
        det = LowTestCoverageDetector()
        ctx = {"coverage_data": {"a.py": 95.0, "b.py": 100.0}}
        opps = await det.detect(ctx)
        assert len(opps) == 0

    def test_score_inversely_proportional(self):
        det = LowTestCoverageDetector()
        opp_low = Opportunity(metadata={"coverage_percent": 10.0})
        opp_high = Opportunity(metadata={"coverage_percent": 70.0})
        assert det.score(opp_low) > det.score(opp_high)

    @pytest.mark.asyncio
    async def test_disabled_when_not_in_enabled_types(self):
        cfg = DetectionConfig(enabled_types={"other_type"})
        det = LowTestCoverageDetector(cfg)
        assert not det.is_enabled()
        opps = await det.detect({"coverage_data": {"a.py": 10.0}})
        assert len(opps) == 0


# ---------------------------------------------------------------------------
# Detector 2: Slow API endpoints
# ---------------------------------------------------------------------------


class TestSlowApiEndpointDetector:
    """Tests for slow API endpoint detection."""

    @pytest.mark.asyncio
    async def test_detects_slow_endpoints(self):
        det = SlowApiEndpointDetector()
        ctx = {
            "endpoint_metrics": [
                {
                    "path": "/api/fast",
                    "method": "GET",
                    "avg_latency_ms": 50,
                    "p95_latency_ms": 100,
                },
                {
                    "path": "/api/slow",
                    "method": "POST",
                    "avg_latency_ms": 2000,
                    "p95_latency_ms": 5000,
                },
            ],
            "latency_threshold_ms": 1000.0,
        }
        opps = await det.detect(ctx)
        paths = {o.file_path or o.title for o in opps}
        assert any("slow" in p for p in paths)
        assert not any("fast" in p for p in paths)

    @pytest.mark.asyncio
    async def test_falls_back_to_avg_latency(self):
        det = SlowApiEndpointDetector()
        ctx = {
            "endpoint_metrics": [
                {"path": "/api/avg_only", "method": "GET", "avg_latency_ms": 2000},
            ],
            "latency_threshold_ms": 1000.0,
        }
        opps = await det.detect(ctx)
        assert len(opps) == 1

    def test_score_scales_with_latency(self):
        det = SlowApiEndpointDetector()
        opp_slow = Opportunity(metadata={"p95_latency_ms": 10000, "threshold_ms": 1000})
        opp_mild = Opportunity(metadata={"p95_latency_ms": 1500, "threshold_ms": 1000})
        assert det.score(opp_slow) > det.score(opp_mild)


# ---------------------------------------------------------------------------
# Detector 3: High error rate
# ---------------------------------------------------------------------------


class TestHighErrorRateDetector:
    """Tests for high error rate detection."""

    @pytest.mark.asyncio
    async def test_detects_high_error_services(self):
        det = HighErrorRateDetector()
        ctx = {
            "error_metrics": [
                {"service": "healthy-svc", "error_rate": 0.01, "error_types": []},
                {
                    "service": "failing-svc",
                    "error_rate": 0.15,
                    "error_types": ["TimeoutError"],
                },
            ],
            "error_rate_threshold": 0.05,
        }
        opps = await det.detect(ctx)
        services = [o.title for o in opps]
        assert any("failing-svc" in s for s in services)
        assert not any("healthy-svc" in s for s in services)

    @pytest.mark.asyncio
    async def test_critical_for_very_high_rate(self):
        det = HighErrorRateDetector()
        ctx = {
            "error_metrics": [
                {
                    "service": "down-svc",
                    "error_rate": 0.5,
                    "error_types": ["ConnectionError"],
                },
            ],
        }
        opps = await det.detect(ctx)
        assert len(opps) == 1
        assert opps[0].severity == OpportunitySeverity.CRITICAL

    def test_score_scales_with_error_rate(self):
        det = HighErrorRateDetector()
        opp_high = Opportunity(metadata={"error_rate": 0.5})
        opp_low = Opportunity(metadata={"error_rate": 0.05})
        assert det.score(opp_high) > det.score(opp_low)


# ---------------------------------------------------------------------------
# Detector 4: Unused code
# ---------------------------------------------------------------------------


class TestUnusedCodeDetector:
    """Tests for unused code detection."""

    @pytest.mark.asyncio
    async def test_detects_zero_reference_symbols(self):
        det = UnusedCodeDetector()
        ctx = {
            "code_references": {
                "OldClass": 0,
                "UsedClass": 10,
                "maybe_unused": 1,
            }
        }
        opps = await det.detect(ctx)
        names = [o.title for o in opps]
        assert any("OldClass" in n for n in names)
        assert any("maybe_unused" in n for n in names)
        assert not any("UsedClass" in n for n in names)

    def test_score_higher_for_fewer_references(self):
        det = UnusedCodeDetector()
        opp_zero = Opportunity(metadata={"reference_count": 0})
        opp_some = Opportunity(metadata={"reference_count": 3})
        assert det.score(opp_zero) > det.score(opp_some)


# ---------------------------------------------------------------------------
# Detector 5: Configuration drift
# ---------------------------------------------------------------------------


class TestConfigurationDriftDetector:
    """Tests for configuration drift detection."""

    @pytest.mark.asyncio
    async def test_detects_config_differences(self):
        det = ConfigurationDriftDetector()
        ctx = {
            "config_diffs": [
                {
                    "key": "DB_HOST",
                    "env_a": "staging",
                    "env_b": "prod",
                    "value_a": "localhost",
                    "value_b": "db.prod.internal",
                },
            ]
        }
        opps = await det.detect(ctx)
        assert len(opps) == 1
        assert "DB_HOST" in opps[0].title

    @pytest.mark.asyncio
    async def test_empty_diffs_no_opportunities(self):
        det = ConfigurationDriftDetector()
        opps = await det.detect({"config_diffs": []})
        assert len(opps) == 0

    def test_score_is_fixed(self):
        det = ConfigurationDriftDetector()
        opp = Opportunity()
        assert det.score(opp) == 0.6


# ---------------------------------------------------------------------------
# Detector 6: Memory anomaly
# ---------------------------------------------------------------------------


class TestMemoryAnomalyDetector:
    """Tests for memory anomaly detection."""

    @pytest.mark.asyncio
    async def test_detects_high_usage(self):
        det = MemoryAnomalyDetector()
        ctx = {
            "memory_metrics": [
                {
                    "service": "api",
                    "current_mb": 7600,
                    "peak_mb": 8000,
                    "limit_mb": 8000,
                    "growth_rate_mb_per_hr": 0,
                },
            ]
        }
        opps = await det.detect(ctx)
        assert len(opps) == 1
        assert "api" in opps[0].title

    @pytest.mark.asyncio
    async def test_detects_growth_anomaly(self):
        det = MemoryAnomalyDetector()
        ctx = {
            "memory_metrics": [
                {
                    "service": "worker",
                    "current_mb": 500,
                    "peak_mb": 600,
                    "limit_mb": 8000,
                    "growth_rate_mb_per_hr": 200,
                },
            ],
            "memory_growth_threshold_mb_hr": 100.0,
        }
        opps = await det.detect(ctx)
        assert len(opps) == 1

    @pytest.mark.asyncio
    async def test_healthy_service_no_opportunity(self):
        det = MemoryAnomalyDetector()
        ctx = {
            "memory_metrics": [
                {
                    "service": "healthy",
                    "current_mb": 200,
                    "peak_mb": 300,
                    "limit_mb": 8000,
                    "growth_rate_mb_per_hr": 5,
                },
            ]
        }
        opps = await det.detect(ctx)
        assert len(opps) == 0

    def test_score_combines_usage_and_growth(self):
        det = MemoryAnomalyDetector()
        opp_high = Opportunity(
            metadata={"usage_ratio": 0.95, "growth_rate_mb_per_hr": 300}
        )
        opp_low = Opportunity(
            metadata={"usage_ratio": 0.3, "growth_rate_mb_per_hr": 10}
        )
        assert det.score(opp_high) > det.score(opp_low)


# ---------------------------------------------------------------------------
# Detector 7: CI bottleneck
# ---------------------------------------------------------------------------


class TestCIBottleneckDetector:
    """Tests for CI bottleneck detection."""

    @pytest.mark.asyncio
    async def test_detects_slow_stage(self):
        det = CIBottleneckDetector()
        ctx = {
            "ci_stages": [
                {
                    "name": "fast-test",
                    "avg_duration_seconds": 30,
                    "failure_rate": 0.0,
                    "run_count": 100,
                },
                {
                    "name": "slow-build",
                    "avg_duration_seconds": 600,
                    "failure_rate": 0.0,
                    "run_count": 100,
                },
            ],
            "ci_duration_threshold_seconds": 300.0,
        }
        opps = await det.detect(ctx)
        names = [o.title for o in opps]
        assert any("slow-build" in n for n in names)
        assert not any("fast-test" in n for n in names)

    @pytest.mark.asyncio
    async def test_detects_flaky_stage(self):
        det = CIBottleneckDetector()
        ctx = {
            "ci_stages": [
                {
                    "name": "flaky-test",
                    "avg_duration_seconds": 60,
                    "failure_rate": 0.25,
                    "run_count": 50,
                },
            ],
            "ci_failure_threshold": 0.1,
        }
        opps = await det.detect(ctx)
        assert len(opps) == 1
        assert "flaky" in opps[0].title.lower()

    def test_score_scales_with_duration_and_failure(self):
        det = CIBottleneckDetector()
        opp_bad = Opportunity(
            metadata={"avg_duration_seconds": 900, "failure_rate": 0.4}
        )
        opp_ok = Opportunity(
            metadata={"avg_duration_seconds": 100, "failure_rate": 0.02}
        )
        assert det.score(opp_bad) > det.score(opp_ok)


# ---------------------------------------------------------------------------
# Detector 8: Documentation gap
# ---------------------------------------------------------------------------


class TestDocumentationGapDetector:
    """Tests for documentation gap detection."""

    @pytest.mark.asyncio
    async def test_detects_undocumented_files(self):
        det = DocumentationGapDetector()
        ctx = {
            "doc_coverage": {
                "src/undocumented.py": {
                    "docstring_ratio": 0.1,
                    "public_undocumented": 8,
                    "total_public": 10,
                },
                "src/documented.py": {
                    "docstring_ratio": 0.9,
                    "public_undocumented": 1,
                    "total_public": 10,
                },
            },
            "min_docstring_ratio": 0.5,
        }
        opps = await det.detect(ctx)
        paths = [o.file_path for o in opps]
        assert "src/undocumented.py" in paths
        assert "src/documented.py" not in paths

    @pytest.mark.asyncio
    async def test_zero_undocumented_no_opportunity(self):
        det = DocumentationGapDetector()
        ctx = {
            "doc_coverage": {
                "src/perfect.py": {
                    "docstring_ratio": 0.3,
                    "public_undocumented": 0,
                    "total_public": 10,
                },
            },
        }
        opps = await det.detect(ctx)
        assert len(opps) == 0

    def test_score_considers_ratio_and_count(self):
        det = DocumentationGapDetector()
        opp_bad = Opportunity(
            metadata={"docstring_ratio": 0.0, "public_undocumented": 15}
        )
        opp_ok = Opportunity(
            metadata={"docstring_ratio": 0.4, "public_undocumented": 2}
        )
        assert det.score(opp_bad) > det.score(opp_ok)


# ---------------------------------------------------------------------------
# Detector 9: Dependency vulnerability
# ---------------------------------------------------------------------------


class TestDependencyVulnerabilityDetector:
    """Tests for dependency vulnerability detection."""

    @pytest.mark.asyncio
    async def test_detects_vulnerabilities(self):
        det = DependencyVulnerabilityDetector()
        ctx = {
            "vulnerabilities": [
                {
                    "package": "requests",
                    "version": "2.25.0",
                    "cve_id": "CVE-2023-0001",
                    "severity": "HIGH",
                    "description": "SSRF vulnerability",
                },
            ]
        }
        opps = await det.detect(ctx)
        assert len(opps) == 1
        assert "requests" in opps[0].title
        assert opps[0].severity == OpportunitySeverity.HIGH

    @pytest.mark.asyncio
    async def test_maps_severity_levels(self):
        det = DependencyVulnerabilityDetector()
        ctx = {
            "vulnerabilities": [
                {
                    "package": "a",
                    "version": "1.0",
                    "cve_id": "CVE-A",
                    "severity": "CRITICAL",
                    "description": "",
                },
                {
                    "package": "b",
                    "version": "1.0",
                    "cve_id": "CVE-B",
                    "severity": "LOW",
                    "description": "",
                },
            ]
        }
        opps = await det.detect(ctx)
        by_cve = {o.metadata["cve_id"]: o.severity for o in opps}
        assert by_cve["CVE-A"] == OpportunitySeverity.CRITICAL
        assert by_cve["CVE-B"] == OpportunitySeverity.LOW

    @pytest.mark.asyncio
    async def test_empty_vulns_no_opportunities(self):
        det = DependencyVulnerabilityDetector()
        opps = await det.detect({"vulnerabilities": []})
        assert len(opps) == 0

    def test_score_by_severity(self):
        det = DependencyVulnerabilityDetector()
        opp_crit = Opportunity(metadata={"vulnerability_severity": "CRITICAL"})
        opp_low = Opportunity(metadata={"vulnerability_severity": "LOW"})
        assert det.score(opp_crit) > det.score(opp_low)


# ---------------------------------------------------------------------------
# Detector 10: Performance regression
# ---------------------------------------------------------------------------


class TestPerformanceRegressionDetector:
    """Tests for performance regression detection."""

    @pytest.mark.asyncio
    async def test_detects_lower_is_better_regression(self):
        det = PerformanceRegressionDetector()
        ctx = {
            "performance_baselines": [
                {
                    "metric_name": "api_latency_p95",
                    "baseline_value": 100,
                    "current_value": 200,
                    "unit": "ms",
                    "direction": "lower_is_better",
                },
            ],
            "regression_threshold": 0.2,
        }
        opps = await det.detect(ctx)
        assert len(opps) == 1
        assert "api_latency_p95" in opps[0].title

    @pytest.mark.asyncio
    async def test_detects_higher_is_better_regression(self):
        det = PerformanceRegressionDetector()
        ctx = {
            "performance_baselines": [
                {
                    "metric_name": "throughput_rps",
                    "baseline_value": 1000,
                    "current_value": 500,
                    "unit": "rps",
                    "direction": "higher_is_better",
                },
            ],
            "regression_threshold": 0.2,
        }
        opps = await det.detect(ctx)
        assert len(opps) == 1

    @pytest.mark.asyncio
    async def test_no_regression_when_improved(self):
        det = PerformanceRegressionDetector()
        ctx = {
            "performance_baselines": [
                {
                    "metric_name": "latency",
                    "baseline_value": 200,
                    "current_value": 100,
                    "unit": "ms",
                    "direction": "lower_is_better",
                },
            ],
        }
        opps = await det.detect(ctx)
        assert len(opps) == 0

    @pytest.mark.asyncio
    async def test_handles_zero_baseline(self):
        det = PerformanceRegressionDetector()
        ctx = {
            "performance_baselines": [
                {
                    "metric_name": "zero_base",
                    "baseline_value": 0,
                    "current_value": 100,
                    "unit": "ms",
                    "direction": "lower_is_better",
                },
            ],
        }
        opps = await det.detect(ctx)
        assert len(opps) == 0

    def test_score_scales_with_regression_pct(self):
        det = PerformanceRegressionDetector()
        opp_big = Opportunity(metadata={"regression_pct": 0.8})
        opp_small = Opportunity(metadata={"regression_pct": 0.25})
        assert det.score(opp_big) > det.score(opp_small)


# ---------------------------------------------------------------------------
# Orchestrator: OpportunityDetector
# ---------------------------------------------------------------------------


class TestOpportunityDetector:
    """Tests for the OpportunityDetector orchestrator."""

    def test_all_ten_types_registered(self, detector):
        types = detector.get_available_types()
        assert len(types) >= 10
        expected = {
            "low_test_coverage",
            "slow_api_endpoint",
            "high_error_rate",
            "unused_code",
            "configuration_drift",
            "memory_anomaly",
            "ci_bottleneck",
            "documentation_gap",
            "dependency_vulnerability",
            "performance_regression",
        }
        assert expected.issubset(set(types))

    def test_enabled_types_respects_config(self, selective_config):
        det = OpportunityDetector(selective_config)
        enabled = det.get_enabled_types()
        assert set(enabled) == {"low_test_coverage", "high_error_rate"}

    @pytest.mark.asyncio
    async def test_detect_all_returns_results(self, detector):
        ctx = {
            "coverage_data": {"src/a.py": 30.0},
            "endpoint_metrics": [
                {"path": "/slow", "method": "GET", "p95_latency_ms": 5000},
            ],
            "error_metrics": [
                {"service": "svc", "error_rate": 0.15, "error_types": ["Err"]},
            ],
            "code_references": {"DeadCode": 0},
            "config_diffs": [
                {
                    "key": "K",
                    "env_a": "stg",
                    "env_b": "prod",
                    "value_a": "a",
                    "value_b": "b",
                },
            ],
            "memory_metrics": [
                {
                    "service": "svc",
                    "current_mb": 7000,
                    "peak_mb": 7500,
                    "limit_mb": 8000,
                    "growth_rate_mb_per_hr": 0,
                },
            ],
            "ci_stages": [
                {
                    "name": "build",
                    "avg_duration_seconds": 600,
                    "failure_rate": 0.15,
                    "run_count": 50,
                },
            ],
            "doc_coverage": {
                "src/x.py": {
                    "docstring_ratio": 0.1,
                    "public_undocumented": 5,
                    "total_public": 10,
                },
            },
            "vulnerabilities": [
                {
                    "package": "pkg",
                    "version": "1.0",
                    "cve_id": "CVE-X",
                    "severity": "MEDIUM",
                    "description": "vuln",
                },
            ],
            "performance_baselines": [
                {
                    "metric_name": "latency",
                    "baseline_value": 100,
                    "current_value": 200,
                    "unit": "ms",
                    "direction": "lower_is_better",
                },
            ],
        }
        result = await detector.detect_all(ctx)
        assert len(result.opportunities) >= 10
        assert result.scan_duration_seconds > 0
        assert len(result.types_scanned) >= 10
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_detect_all_filters_by_confidence(self):
        cfg = DetectionConfig(min_confidence=0.95)
        det = OpportunityDetector(cfg)
        ctx = {
            "coverage_data": {"a.py": 30.0},
            "vulnerabilities": [
                {
                    "package": "p",
                    "version": "1",
                    "cve_id": "C",
                    "severity": "HIGH",
                    "description": "d",
                },
            ],
        }
        result = await det.detect_all(ctx)
        # Only vulnerability (0.95 confidence) should pass
        assert all(o.confidence >= 0.95 for o in result.opportunities)

    @pytest.mark.asyncio
    async def test_detect_all_respects_max_opportunities(self):
        cfg = DetectionConfig(max_opportunities_per_run=3)
        det = OpportunityDetector(cfg)
        ctx = {
            "coverage_data": {f"src/f{i}.py": 10.0 for i in range(20)},
        }
        result = await det.detect_all(ctx)
        assert len(result.opportunities) <= 3

    @pytest.mark.asyncio
    async def test_detect_all_sorted_by_score(self, detector):
        ctx = {
            "coverage_data": {"low.py": 5.0, "med.py": 50.0, "high.py": 75.0},
        }
        result = await detector.detect_all(ctx)
        scores = [o.score for o in result.opportunities]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_detect_single_known_type(self, detector):
        result = await detector.detect_single(
            "low_test_coverage",
            {"coverage_data": {"a.py": 20.0}},
        )
        assert len(result.opportunities) == 1
        assert result.types_scanned == ["low_test_coverage"]

    @pytest.mark.asyncio
    async def test_detect_single_unknown_type(self, detector):
        result = await detector.detect_single("nonexistent_type")
        assert len(result.opportunities) == 0
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_detect_single_disabled_type(self, selective_config):
        det = OpportunityDetector(selective_config)
        result = await det.detect_single(
            "ci_bottleneck",
            {
                "ci_stages": [
                    {
                        "name": "x",
                        "avg_duration_seconds": 600,
                        "failure_rate": 0,
                        "run_count": 1,
                    }
                ]
            },
        )
        # ci_bottleneck is not in enabled_types, so detector returns no opportunities
        assert len(result.opportunities) == 0
        assert result.types_scanned == ["ci_bottleneck"]

    @pytest.mark.asyncio
    async def test_empty_context_returns_no_opportunities(self, detector):
        result = await detector.detect_all({})
        assert len(result.opportunities) == 0

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Detector with very short timeout should handle timeout gracefully."""

        async def slow_detect(ctx):
            await asyncio.sleep(10)
            return []

        det = OpportunityDetector(DetectionConfig(scan_timeout_seconds=0.01))
        # Monkey-patch one detector to be slow
        original_detect = det._detectors[0].detect
        det._detectors[0].detect = slow_detect  # type: ignore[method-assign]

        result = await det.detect_all({"coverage_data": {"a.py": 10.0}})
        # The slow detector should cause an error, but others should still work
        assert len(result.errors) >= 1

    def test_summary_stats_empty(self, detector):
        result = DetectionResult(opportunities=[], scan_duration_seconds=0.1)
        stats = detector.summary_stats(result)
        assert stats["total_opportunities"] == 0
        assert stats["avg_score"] == 0.0

    def test_summary_stats_with_data(self, detector):
        opps = [
            Opportunity(
                severity=OpportunitySeverity.HIGH,
                category=OpportunityCategory.PERFORMANCE,
                score=0.8,
                confidence=0.9,
            ),
            Opportunity(
                severity=OpportunitySeverity.LOW,
                category=OpportunityCategory.PERFORMANCE,
                score=0.3,
                confidence=0.7,
            ),
        ]
        result = DetectionResult(opportunities=opps, scan_duration_seconds=1.0)
        stats = detector.summary_stats(result)
        assert stats["total_opportunities"] == 2
        assert stats["by_severity"]["HIGH"] == 1
        assert stats["by_severity"]["LOW"] == 1
        assert stats["by_category"]["performance"] == 2
        assert stats["avg_score"] == 0.55
        assert stats["avg_confidence"] == 0.8


# ---------------------------------------------------------------------------
# Cross-cutting: 10+ opportunity types verification
# ---------------------------------------------------------------------------


class TestOpportunityTypeCount:
    """Verify minimum 10 opportunity types are available."""

    def test_at_least_ten_types_registered(self):
        types = OpportunityDetector.DETECTOR_REGISTRY
        assert len(types) >= 10, (
            f"Expected at least 10 detector types, got {len(types)}: "
            f"{[t.type_name for t in types]}"
        )

    def test_all_types_have_unique_names(self):
        names = [t.type_name for t in OpportunityDetector.DETECTOR_REGISTRY]
        assert len(names) == len(set(names)), f"Duplicate type names: {names}"

    def test_all_types_have_categories(self):
        for cls in OpportunityDetector.DETECTOR_REGISTRY:
            assert (
                cls.category != OpportunityCategory.CODE_QUALITY
                or cls.type_name in ("unused_code",)
            ), (f"{cls.type_name} should have a specific category")
