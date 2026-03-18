#!/usr/bin/env python3
"""
Week 1 Baseline Analysis Script

Analyzes governance metrics from Week 1 baseline data to identify
bottlenecks and improvement opportunities.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class BaselineAnalyzer:
    """Analyzes Week 1 baseline metrics and identifies optimization opportunities."""

    def __init__(self, baseline_path: str | None = None):
        """Initialize analyzer with baseline data path."""
        self.baseline_path = baseline_path or self._find_baseline_file()
        self.baseline_data: dict[str, Any] = {}
        self.analysis_results: dict[str, Any] = {}

    def _find_baseline_file(self) -> str:
        """Find the Week 1 baseline file."""
        evidence_dir = Path("docs/evidence/ST-GOV-MINI-002")
        if evidence_dir.exists():
            for file in evidence_dir.glob("optimization-results-week1-*.json"):
                return str(file)
        # Fallback to the known file
        return "docs/evidence/ST-GOV-MINI-002/optimization-results-week1-20260312_022432.json"

    def load_baseline(self) -> dict[str, Any]:
        """Load Week 1 baseline data from file."""
        try:
            with open(self.baseline_path) as f:
                self.baseline_data = json.load(f)
            print(f"✓ Loaded baseline data from {self.baseline_path}")
            return self.baseline_data
        except FileNotFoundError:
            print(f"✗ Baseline file not found: {self.baseline_path}")
            return {}
        except json.JSONDecodeError as e:
            print(f"✗ Error parsing baseline file: {e}")
            return {}

    def analyze_metrics(self) -> dict[str, Any]:
        """Analyze baseline metrics and identify bottlenecks."""
        if not self.baseline_data:
            self.load_baseline()

        week1_baseline = self.baseline_data.get("week1_baseline", {})

        analysis = {
            "timestamp": datetime.now().isoformat(),
            "story_id": "ST-GOV-MINI-002",
            "analysis_version": "2.0.0",
            "metrics_summary": {},
            "bottlenecks": [],
            "improvement_opportunities": [],
            "performance_gaps": [],
        }

        # Analyze retrieval latency
        retrieval_p95 = week1_baseline.get("retrieval_p95_ms", 0)
        retrieval_mean = week1_baseline.get("retrieval_mean_ms", 0)
        analysis["metrics_summary"]["retrieval_latency"] = {
            "p95_ms": retrieval_p95,
            "mean_ms": retrieval_mean,
            "status": "good" if retrieval_p95 < 50 else "needs_improvement",
        }

        if retrieval_p95 > 50:
            analysis["bottlenecks"].append(
                {
                    "category": "retrieval",
                    "metric": "retrieval_p95_ms",
                    "current_value": retrieval_p95,
                    "threshold": 50,
                    "severity": "medium",
                    "description": f"P95 retrieval latency ({retrieval_p95}ms) exceeds threshold (50ms)",
                }
            )

        # Analyze memory hit rate
        memory_hit_rate = week1_baseline.get("memory_hit_rate", 0)
        analysis["metrics_summary"]["memory_hit_rate"] = {
            "value": memory_hit_rate,
            "status": "good" if memory_hit_rate >= 80 else "needs_improvement",
        }

        if memory_hit_rate < 80:
            analysis["performance_gaps"].append(
                {
                    "category": "memory",
                    "metric": "memory_hit_rate",
                    "current": memory_hit_rate,
                    "target": 85,
                    "gap": 85 - memory_hit_rate,
                    "impact": "High - affects agent response time",
                }
            )

        # Analyze deduplication ratio
        dedup_ratio = week1_baseline.get("deduplication_ratio", 0)
        analysis["metrics_summary"]["deduplication_ratio"] = {
            "value": dedup_ratio,
            "status": "good" if dedup_ratio >= 0.8 else "needs_improvement",
        }

        if dedup_ratio < 0.8:
            analysis["improvement_opportunities"].append(
                {
                    "category": "deduplication",
                    "metric": "deduplication_ratio",
                    "current": dedup_ratio,
                    "target": 0.85,
                    "potential_improvement": f"{((0.85 - dedup_ratio) / dedup_ratio * 100):.1f}%",
                    "effort": "medium",
                }
            )

        # Analyze relevance scores
        relevance_mean = week1_baseline.get("relevance_mean_score", 0)
        analysis["metrics_summary"]["relevance"] = {
            "mean_score": relevance_mean,
            "status": "good" if relevance_mean >= 0.8 else "needs_improvement",
        }

        if relevance_mean < 0.8:
            analysis["bottlenecks"].append(
                {
                    "category": "retrieval",
                    "metric": "relevance_mean_score",
                    "current_value": relevance_mean,
                    "threshold": 0.8,
                    "severity": "high",
                    "description": f"Mean relevance score ({relevance_mean:.3f}) below optimal threshold (0.8)",
                }
            )

        # Analyze worker efficiency
        active_locks = week1_baseline.get("active_ownership_locks", 0)
        parallel_workers = week1_baseline.get("parallel_workers", 0)
        analysis["metrics_summary"]["worker_efficiency"] = {
            "active_locks": active_locks,
            "parallel_workers": parallel_workers,
            "locks_per_worker": (
                active_locks / parallel_workers if parallel_workers > 0 else 0
            ),
        }

        # Analyze MRR and coverage
        mrr = week1_baseline.get("mrr", 0)
        coverage = week1_baseline.get("coverage_ratio", 0)
        analysis["metrics_summary"]["retrieval_quality"] = {
            "mrr": mrr,
            "coverage": coverage,
            "status": "excellent" if mrr >= 0.9 and coverage >= 0.95 else "good",
        }

        self.analysis_results = analysis
        return analysis

    def generate_summary(self) -> str:
        """Generate a human-readable summary of the analysis."""
        if not self.analysis_results:
            self.analyze_metrics()

        summary = []
        summary.append("=" * 60)
        summary.append("WEEK 1 BASELINE ANALYSIS SUMMARY")
        summary.append("=" * 60)
        summary.append(f"Analysis Time: {self.analysis_results.get('timestamp')}")
        summary.append(f"Story ID: {self.analysis_results.get('story_id')}")
        summary.append("")

        # Metrics summary
        summary.append("METRICS SUMMARY:")
        summary.append("-" * 40)
        for metric, data in self.analysis_results.get("metrics_summary", {}).items():
            summary.append(f"  {metric}:")
            for key, value in data.items():
                summary.append(f"    - {key}: {value}")
        summary.append("")

        # Bottlenecks
        bottlenecks = self.analysis_results.get("bottlenecks", [])
        summary.append(f"BOTTLENECKS IDENTIFIED: {len(bottlenecks)}")
        summary.append("-" * 40)
        for i, bottleneck in enumerate(bottlenecks, 1):
            summary.append(
                f"  {i}. [{bottleneck['severity'].upper()}] {bottleneck['category']}"
            )
            summary.append(f"     Metric: {bottleneck['metric']}")
            summary.append(
                f"     Current: {bottleneck['current_value']}, Threshold: {bottleneck['threshold']}"
            )
            summary.append(f"     {bottleneck['description']}")
        summary.append("")

        # Improvement opportunities
        opportunities = self.analysis_results.get("improvement_opportunities", [])
        summary.append(f"IMPROVEMENT OPPORTUNITIES: {len(opportunities)}")
        summary.append("-" * 40)
        for i, opp in enumerate(opportunities, 1):
            summary.append(f"  {i}. {opp['category']} ({opp['effort']} effort)")
            summary.append(f"     Current: {opp['current']}, Target: {opp['target']}")
            summary.append(f"     Potential: {opp['potential_improvement']}")
        summary.append("")

        # Performance gaps
        gaps = self.analysis_results.get("performance_gaps", [])
        summary.append(f"PERFORMANCE GAPS: {len(gaps)}")
        summary.append("-" * 40)
        for i, gap in enumerate(gaps, 1):
            summary.append(f"  {i}. {gap['category']}: {gap['gap']:.1f} points gap")
            summary.append(f"     Impact: {gap['impact']}")
        summary.append("")
        summary.append("=" * 60)

        return "\n".join(summary)

    def save_analysis(self, output_path: str | None = None) -> str:
        """Save analysis results to JSON file."""
        if not self.analysis_results:
            self.analyze_metrics()

        output_path = output_path or "docs/evidence/ST-GOV-MINI-002/week1-analysis.json"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(self.analysis_results, f, indent=2)

        print(f"✓ Analysis saved to {output_path}")
        return output_path


def main():
    """Main entry point for baseline analysis."""
    print("Starting Week 1 Baseline Analysis...")
    print("=" * 60)

    analyzer = BaselineAnalyzer()

    # Load and analyze
    analyzer.load_baseline()
    analyzer.analyze_metrics()

    # Print summary
    print(analyzer.generate_summary())

    # Save results
    output_path = analyzer.save_analysis()

    print(f"\n✓ Analysis complete. Results saved to: {output_path}")
    return 0


if __name__ == "__main__":
    exit(main())
