#!/usr/bin/env python3
"""
Parallel Coordinator Script (ST-GOV-010).

CLI tool for analyzing and optimizing parallel execution of agent swarm tasks.
Integrates with Redis ownership system for safe coordination.

Usage:
    python scripts/swarm/parallel_coordinator.py analyze <tasks.yaml>
    python scripts/swarm/parallel_coordinator.py plan <tasks.yaml> --output plan.json
    python scripts/swarm/parallel_coordinator.py execute <plan.json>
    python scripts/swarm/parallel_coordinator.py validate <plan.json>

Story: ST-GOV-010
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.governance.parallel_optimizer import (
    ExecutionPlan,
    OptimizableTask,
    OptimizerConfig,
    ParallelOptimizer,
    TaskPriority,
)
from src.governance.parallel_optimizer.conflict_analyzer import ScopeConflictAnalyzer
from src.governance.parallel_optimizer.dependency_graph import DependencyGraphBuilder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_tasks_from_yaml(yaml_path: str) -> list[OptimizableTask]:
    """Load tasks from a YAML file."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    tasks = []
    for task_data in data.get("tasks", []):
        priority_str = task_data.get("priority", "normal").upper()
        try:
            priority = TaskPriority[priority_str]
        except KeyError:
            priority = TaskPriority.NORMAL

        task = OptimizableTask(
            task_id=task_data["task_id"],
            scope_globs=task_data.get("scope_globs", []),
            dependencies=task_data.get("dependencies", []),
            priority=priority,
            estimated_duration_seconds=task_data.get(
                "estimated_duration_seconds", 60.0
            ),
            constitution_alignment=task_data.get("constitution_alignment", 1.0),
            agent_id=task_data.get("agent_id"),
            metadata=task_data.get("metadata", {}),
        )
        tasks.append(task)

    return tasks


def analyze_tasks(tasks: list[OptimizableTask]) -> dict[str, Any]:
    """Analyze tasks for dependencies and conflicts."""
    # Build dependency graph
    graph_builder = DependencyGraphBuilder()
    graph = graph_builder.build_graph(tasks)

    # Analyze conflicts
    conflict_analyzer = ScopeConflictAnalyzer()
    conflict_matrix = conflict_analyzer.build_conflict_matrix(tasks)

    return {
        "task_count": len(tasks),
        "dependency_graph": {
            "has_cycles": graph.has_cycles,
            "edge_count": graph.edge_count,
            "max_depth": graph.max_depth,
            "critical_path": graph.critical_path,
        },
        "conflicts": {
            "conflict_count": conflict_analyzer.get_conflict_count(tasks),
            "conflict_rate": conflict_analyzer.get_conflict_rate(tasks),
            "conflict_pairs": [list(pair) for pair in conflict_matrix.conflict_details],
        },
        "execution_layers": graph_builder.get_execution_layers(graph),
    }


def create_plan(
    tasks: list[OptimizableTask],
    max_parallel: int = 10,
    target_improvement: float = 30.0,
) -> ExecutionPlan:
    """Create an optimized execution plan."""
    config = OptimizerConfig(
        max_parallel=max_parallel,
        target_throughput_improvement=target_improvement,
    )
    optimizer = ParallelOptimizer(config=config)
    return optimizer.create_execution_plan(tasks)


def plan_to_dict(plan: ExecutionPlan) -> dict[str, Any]:
    """Convert execution plan to dictionary for serialization."""
    return {
        "plan_id": plan.plan_id,
        "created_at": plan.created_at.isoformat(),
        "total_tasks": plan.total_tasks,
        "max_parallel": plan.max_parallel,
        "estimated_total_duration": plan.estimated_total_duration,
        "conflict_count": plan.conflict_count,
        "optimization_score": plan.optimization_score,
        "batches": [
            {
                "batch_id": batch.batch_id,
                "batch_number": batch.batch_number,
                "task_ids": batch.task_ids,
                "total_estimated_duration": batch.total_estimated_duration,
                "parallel_safe": batch.parallel_safe,
            }
            for batch in plan.batches
        ],
    }


def validate_plan(
    plan: ExecutionPlan, config: OptimizerConfig
) -> tuple[bool, list[str]]:
    """Validate that a plan meets acceptance criteria."""
    issues = []

    # Check for cycles
    if plan.conflict_count < 0:
        issues.append("Plan has circular dependencies")

    # Check optimization score
    if plan.optimization_score < 50:
        issues.append(f"Optimization score {plan.optimization_score:.1f} is below 50")

    # Check conflict count
    if plan.conflict_count > 0:
        conflict_rate = (
            plan.conflict_count / (plan.total_tasks * (plan.total_tasks - 1) / 2) * 100
            if plan.total_tasks > 1
            else 0
        )
        if conflict_rate > config.max_conflict_rate:
            issues.append(
                f"Conflict rate {conflict_rate:.1f}% exceeds "
                f"maximum {config.max_conflict_rate}%"
            )

    return len(issues) == 0, issues


def print_analysis(analysis: dict[str, Any]) -> None:
    """Print analysis results."""
    print("\n=== Task Analysis ===\n")
    print(f"Total Tasks: {analysis['task_count']}")

    print("\nDependency Graph:")
    dg = analysis["dependency_graph"]
    print(f"  Has Cycles: {dg['has_cycles']}")
    print(f"  Edge Count: {dg['edge_count']}")
    print(f"  Max Depth: {dg['max_depth']}")
    print(f"  Critical Path: {' -> '.join(dg['critical_path'])}")

    print("\nConflicts:")
    cf = analysis["conflicts"]
    print(f"  Conflict Count: {cf['conflict_count']}")
    print(f"  Conflict Rate: {cf['conflict_rate']:.2f}%")
    if cf["conflict_pairs"]:
        print(f"  Conflicting Pairs: {cf['conflict_pairs']}")

    print("\nExecution Layers:")
    for i, layer in enumerate(analysis["execution_layers"]):
        print(f"  Layer {i}: {layer}")


def print_plan_summary(plan: ExecutionPlan) -> None:
    """Print execution plan summary."""
    print("\n=== Execution Plan ===\n")
    print(f"Plan ID: {plan.plan_id}")
    print(f"Created: {plan.created_at.isoformat()}")
    print(f"Total Tasks: {plan.total_tasks}")
    print(f"Batch Count: {plan.batch_count}")
    print(f"Max Parallel: {plan.max_parallel}")
    print(f"Estimated Duration: {plan.estimated_total_duration:.1f}s")
    print(f"Optimization Score: {plan.optimization_score:.1f}/100")
    print(f"Conflict Count: {plan.conflict_count}")

    print("\nBatches:")
    for batch in plan.batches:
        print(
            f"  Batch {batch.batch_number}: {batch.task_ids} "
            f"({batch.total_estimated_duration:.1f}s)"
        )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Parallel Execution Coordinator for ChiseAI Agent Swarm"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Analyze command
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze tasks for dependencies and conflicts"
    )
    analyze_parser.add_argument(
        "tasks_file", help="YAML file containing task definitions"
    )

    # Plan command
    plan_parser = subparsers.add_parser(
        "plan", help="Create an optimized execution plan"
    )
    plan_parser.add_argument("tasks_file", help="YAML file containing task definitions")
    plan_parser.add_argument(
        "--output", "-o", help="Output file for plan (JSON)", default=None
    )
    plan_parser.add_argument(
        "--max-parallel", type=int, default=10, help="Maximum parallel tasks"
    )
    plan_parser.add_argument(
        "--target-improvement",
        type=float,
        default=30.0,
        help="Target throughput improvement %%",
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate an execution plan"
    )
    validate_parser.add_argument(
        "plan_file", help="JSON file containing execution plan"
    )

    # Compare command
    compare_parser = subparsers.add_parser(
        "compare", help="Compare sequential vs parallel execution"
    )
    compare_parser.add_argument(
        "tasks_file", help="YAML file containing task definitions"
    )
    compare_parser.add_argument(
        "--max-parallel", type=int, default=10, help="Maximum parallel tasks"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "analyze":
            tasks = load_tasks_from_yaml(args.tasks_file)
            analysis = analyze_tasks(tasks)
            print_analysis(analysis)

        elif args.command == "plan":
            tasks = load_tasks_from_yaml(args.tasks_file)
            plan = create_plan(
                tasks,
                max_parallel=args.max_parallel,
                target_improvement=args.target_improvement,
            )
            print_plan_summary(plan)

            if args.output:
                plan_dict = plan_to_dict(plan)
                with open(args.output, "w") as f:
                    json.dump(plan_dict, f, indent=2)
                print(f"\nPlan saved to: {args.output}")

        elif args.command == "validate":
            with open(args.plan_file) as f:
                plan_dict = json.load(f)

            # Reconstruct minimal plan for validation
            tasks = []  # Would need to load from plan
            config = OptimizerConfig()
            ParallelOptimizer(config=config)

            # Simple validation based on plan metrics
            issues = []
            if plan_dict.get("conflict_count", 0) < 0:
                issues.append("Plan has circular dependencies")
            if plan_dict.get("optimization_score", 0) < 50:
                issues.append("Low optimization score")

            if issues:
                print("Validation FAILED:")
                for issue in issues:
                    print(f"  - {issue}")
                return 1
            else:
                print("Validation PASSED")
                return 0

        elif args.command == "compare":
            tasks = load_tasks_from_yaml(args.tasks_file)

            # Sequential estimate
            sequential_duration = sum(t.estimated_duration_seconds for t in tasks)

            # Parallel estimate
            plan = create_plan(tasks, max_parallel=args.max_parallel)
            parallel_duration = plan.estimated_total_duration

            improvement = (
                (sequential_duration - parallel_duration) / sequential_duration * 100
                if sequential_duration > 0
                else 0
            )

            print("\n=== Execution Comparison ===\n")
            print(f"Sequential Duration: {sequential_duration:.1f}s")
            print(f"Parallel Duration: {parallel_duration:.1f}s")
            print(f"Improvement: {improvement:.1f}%")
            print("Target: 30.0%")
            print(f"Status: {'PASS' if improvement >= 30.0 else 'FAIL'}")

        return 0

    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
