#!/usr/bin/env python3
"""Run brain evaluation with full metrics storage in Redis."""

import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import redis
from brain.evaluation import BrainEvaluator


def main():
    # Connect to Redis
    redis_client = redis.Redis(
        host="host.docker.internal", port=6380, decode_responses=True
    )

    # Create BrainEvaluator with Redis client
    evaluator = BrainEvaluator(redis_client=redis_client)

    # Generate deterministic test data for version 1.0.0-current
    version = "1.0.0-current"
    version_hash = hash(version)
    num_cases = 10 + (version_hash % 20)

    test_data = []
    expected_outputs = []

    for i in range(num_cases):
        case_hash = version_hash ^ (i * 31)
        output = (case_hash % 2) == 0
        expected = ((case_hash >> 1) % 2) == 0
        test_data.append({"output": output, "case_index": i})
        expected_outputs.append({"expected": expected})

    # Run evaluation
    print(f"Running evaluation for {version} with {len(test_data)} test cases...")
    result = evaluator.evaluate_version(
        version=version, test_data=test_data, expected_outputs=expected_outputs
    )

    # Print results
    print(f"\nEvaluation Status: {result.status.value}")
    print(f"Duration: {result.duration_seconds:.4f}s")
    print(f"\nMetrics:")
    print(f"  Accuracy: {result.metrics.accuracy:.4f}")
    print(f"  Precision: {result.metrics.precision:.4f}")
    print(f"  Recall: {result.metrics.recall:.4f}")
    print(f"  F1 Score: {result.metrics.f1_score:.4f}")
    print(f"\nBrainEval KPIs:")
    print(f"  1. paper_carryover_rate: {result.metrics.paper_carryover_rate:.4f}")
    print(f"  2. false_positive_rate: {result.metrics.false_positive_rate:.4f}")
    print(f"  3. time_to_improvement: {result.metrics.time_to_improvement:.4f}")
    print(f"  4. turnover_bias_alignment: {result.metrics.turnover_bias_alignment:.4f}")
    print(f"  5. compute_cost: {result.metrics.compute_cost:.4f}")
    print(f"  6. safety_compliance: {result.metrics.safety_compliance:.4f}")

    # Verify Redis storage
    redis_key = f"brain:evaluation:{version}"
    stored = redis_client.get(redis_key)
    if stored:
        print(f"\n✓ Results stored in Redis: {redis_key}")
        stored_data = json.loads(stored)
        print(f"✓ Redis contains all metrics: {list(stored_data['metrics'].keys())}")
    else:
        print(f"\n✗ Results NOT stored in Redis")
        sys.exit(1)

    # Save to JSON file
    output_path = Path("_bmad-output/brain/eval-vcurrent-full.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(result.to_dict(), f, indent=2)

    print(f"✓ Full results saved to: {output_path}")


if __name__ == "__main__":
    main()
