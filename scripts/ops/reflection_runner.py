#!/usr/bin/env python3
"""
Reflection Runner - CLI for executing reflection loops.

This script provides command-line interface for running micro, meso,
and macro reflection loops with artifact generation and storage.

Usage:
    python3 scripts/ops/reflection_runner.py --story-id=ST-XXX-001 --type=meso
    python3 scripts/ops/reflection_runner.py --type=macro --period=daily
    python3 scripts/ops/reflection_runner.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Ensure src is in path for imports
project_root = Path(__file__).parent.parent.parent
src_path = str(project_root / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Create mock src module to satisfy 'from src.xxx' imports in governance package
# This must be done BEFORE importing any governance modules
if "src" not in sys.modules:
    src_module = types.ModuleType("src")
    sys.modules["src"] = src_module

# Import governance and link to src.governance
# This populates the src.governance namespace to satisfy imports like 'from src.governance.xxx'
import governance as _real_governance

if "src.governance" not in sys.modules:
    sys.modules["src.governance"] = _real_governance
    if hasattr(sys.modules["src"], "governance"):
        sys.modules["src"].governance = _real_governance
    else:
        setattr(sys.modules["src"], "governance", _real_governance)

# Import reflection modules
from governance.reflection.artifacts import (
    AutomationTarget,
    FailureObservation,
    FailureType,
    KPISnapshot,
    Priority,
    PromotionCandidate,
    ReflectionArtifact,
    ReflectionType,
    ReflectionValidator,
    RootCause,
    RootCauseCategory,
    Severity,
)
from governance.reflection.loops import ReflectionLoops


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("reflection_runner")


def get_redis_client() -> Optional[Any]:
    """Get Redis client from environment or return None."""
    try:
        import redis

        import os

        host = os.getenv("REDIS_HOST", "host.docker.internal")
        port = int(os.getenv("REDIS_PORT", "6380"))
        db = int(os.getenv("REDIS_DB", "0"))

        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
        )

        client.ping()
        logger.info(f"Connected to Redis at {host}:{port}")
        return client
    except Exception as e:
        logger.warning(f"Could not connect to Redis: {e}")
        return None


def get_qdrant_client() -> Optional[Any]:
    """Get Qdrant client from environment or return None."""
    try:
        from qdrant_client import QdrantClient

        import os

        host = os.getenv("QDRANT_HOST", "host.docker.internal")
        port = int(os.getenv("QDRANT_PORT", "6334"))

        client = QdrantClient(host=host, port=port)
        logger.info(f"Connected to Qdrant at {host}:{port}")
        return client
    except Exception as e:
        logger.warning(f"Could not connect to Qdrant: {e}")
        return None


def create_mock_redis() -> Any:
    """Create a mock Redis client for testing/dry-run."""

    class MockRedis:
        def __init__(self):
            self.data = {}

        def lpush(self, key, value):
            if key not in self.data:
                self.data[key] = []
            self.data[key].insert(0, value)
            logger.debug(f"MockRedis: LPUSH {key}")

        def set(self, key, value):
            self.data[key] = value
            logger.debug(f"MockRedis: SET {key}")

        def get(self, key):
            return self.data.get(key)

        def lrange(self, key, start, end):
            if key not in self.data:
                return []
            lst = self.data[key]
            if end == -1:
                return lst[start:]
            return lst[start : end + 1]

        def expire(self, key, seconds):
            logger.debug(f"MockRedis: EXPIRE {key} {seconds}s")

        def ping(self):
            return True

    return MockRedis()


def create_mock_qdrant() -> Any:
    """Create a mock Qdrant client for testing/dry-run."""

    class MockQdrant:
        def __init__(self):
            self.collections = {}

        def upsert(self, collection_name, points):
            if collection_name not in self.collections:
                self.collections[collection_name] = []
            self.collections[collection_name].extend(points)
            logger.debug(
                f"MockQdrant: UPSERT {len(points)} points to {collection_name}"
            )

    return MockQdrant()


def run_micro_reflection(
    loops: ReflectionLoops,
    story_id: str,
    action: str,
    result: str,
    duration_ms: Optional[int] = None,
    error: Optional[str] = None,
) -> ReflectionArtifact:
    """Run a micro-reflection loop."""
    logger.info(f"Running micro-reflection for {story_id}")

    artifact = loops.micro_loop(
        story_id=story_id,
        action=action,
        result=result,
        duration_ms=duration_ms,
        error=error,
    )

    return artifact


def run_meso_reflection(
    loops: ReflectionLoops,
    story_id: str,
    what_changed: str,
    kpi_file: Optional[str] = None,
    failures_file: Optional[str] = None,
    root_causes_file: Optional[str] = None,
    automation_file: Optional[str] = None,
    promotion_file: Optional[str] = None,
) -> ReflectionArtifact:
    """Run a meso-reflection loop."""
    logger.info(f"Running meso-reflection for {story_id}")

    kpi_snapshot = None
    if kpi_file:
        with open(kpi_file) as f:
            data = json.load(f)
            kpi_snapshot = KPISnapshot.from_dict(data)

    failures_observed = None
    if failures_file:
        with open(failures_file) as f:
            data = json.load(f)
            failures_observed = [FailureObservation.from_dict(d) for d in data]

    root_causes = None
    if root_causes_file:
        with open(root_causes_file) as f:
            data = json.load(f)
            root_causes = [RootCause.from_dict(d) for d in data]

    next_automation_targets = None
    if automation_file:
        with open(automation_file) as f:
            data = json.load(f)
            next_automation_targets = [AutomationTarget.from_dict(d) for d in data]

    promotion_candidates = None
    if promotion_file:
        with open(promotion_file) as f:
            data = json.load(f)
            promotion_candidates = [PromotionCandidate.from_dict(d) for d in data]

    artifact = loops.meso_loop(
        story_id=story_id,
        what_changed=what_changed,
        kpi_snapshot=kpi_snapshot,
        failures_observed=failures_observed,
        root_causes=root_causes,
        next_automation_targets=next_automation_targets,
        promotion_candidates=promotion_candidates,
    )

    return artifact


def run_macro_reflection(
    loops: ReflectionLoops,
    period: str,
    stories_file: str,
    kpi_file: Optional[str] = None,
) -> ReflectionArtifact:
    """Run a macro-reflection loop."""
    logger.info(f"Running macro-reflection for {period}")

    with open(stories_file) as f:
        stories_completed = json.load(f)

    aggregate_kpis = None
    if kpi_file:
        with open(kpi_file) as f:
            data = json.load(f)
            aggregate_kpis = KPISnapshot.from_dict(data)

    artifact = loops.macro_loop(
        period=period,
        stories_completed=stories_completed,
        aggregate_kpis=aggregate_kpis,
    )

    return artifact


def validate_schema(json_file: str) -> bool:
    """Validate a reflection artifact JSON file against schema."""
    logger.info(f"Validating schema for {json_file}")

    with open(json_file) as f:
        data = json.load(f)

    is_valid, errors = ReflectionValidator.validate_artifact(data)

    if is_valid:
        logger.info("✓ Schema validation passed")
        return True
    else:
        logger.error("✗ Schema validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reflection Runner - Execute reflection loops",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run micro-reflection
  %(prog)s --story-id ST-TEST-001 --type micro --action "tool_call" --result "success"
  
  # Run meso-reflection
  %(prog)s --story-id ST-TEST-001 --type meso --what-changed "Implemented feature X"
  
  # Run macro-reflection
  %(prog)s --type macro --period daily --stories-file stories.json
  
  # Validate artifact schema
  %(prog)s --validate artifact.json
  
  # Dry run (no external storage)
  %(prog)s --story-id ST-TEST-001 --type meso --what-changed "Test" --dry-run
        """,
    )

    parser.add_argument(
        "--story-id",
        type=str,
        help="Story identifier (e.g., ST-XXX-001)",
    )
    parser.add_argument(
        "--type",
        type=str,
        choices=["micro", "meso", "macro"],
        help="Type of reflection loop",
    )
    parser.add_argument(
        "--period",
        type=str,
        choices=["daily", "weekly"],
        help="Period for macro-reflection",
    )
    parser.add_argument(
        "--action",
        type=str,
        help="Action performed (for micro-reflection)",
    )
    parser.add_argument(
        "--result",
        type=str,
        help="Result of action (for micro-reflection)",
    )
    parser.add_argument(
        "--duration-ms",
        type=int,
        help="Duration in milliseconds (for micro-reflection)",
    )
    parser.add_argument(
        "--error",
        type=str,
        help="Error message if action failed (for micro-reflection)",
    )
    parser.add_argument(
        "--what-changed",
        type=str,
        help="Summary of changes (for meso-reflection)",
    )
    parser.add_argument(
        "--kpi-file",
        type=str,
        help="JSON file with KPI snapshot data",
    )
    parser.add_argument(
        "--failures-file",
        type=str,
        help="JSON file with failures observed data",
    )
    parser.add_argument(
        "--root-causes-file",
        type=str,
        help="JSON file with root causes data",
    )
    parser.add_argument(
        "--automation-file",
        type=str,
        help="JSON file with automation targets data",
    )
    parser.add_argument(
        "--promotion-file",
        type=str,
        help="JSON file with promotion candidates data",
    )
    parser.add_argument(
        "--stories-file",
        type=str,
        help="JSON file with list of story IDs (for macro-reflection)",
    )
    parser.add_argument(
        "--validate",
        type=str,
        metavar="JSON_FILE",
        help="Validate a reflection artifact JSON file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no external storage)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file for reflection artifact JSON",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.validate:
        success = validate_schema(args.validate)
        sys.exit(0 if success else 1)

    if not args.type:
        parser.error("--type is required (unless using --validate)")

    if args.type == "micro":
        if not args.story_id:
            parser.error("--story-id is required for micro-reflection")
        if not args.action:
            parser.error("--action is required for micro-reflection")
        if not args.result:
            parser.error("--result is required for micro-reflection")

    elif args.type == "meso":
        if not args.story_id:
            parser.error("--story-id is required for meso-reflection")
        if not args.what_changed:
            parser.error("--what-changed is required for meso-reflection")

    elif args.type == "macro":
        if not args.period:
            parser.error("--period is required for macro-reflection")
        if not args.stories_file:
            parser.error("--stories-file is required for macro-reflection")

    if args.dry_run:
        logger.info("Running in dry-run mode (using mock storage)")
        redis_client = create_mock_redis()
        qdrant_client = create_mock_qdrant()
    else:
        redis_client = get_redis_client()
        qdrant_client = get_qdrant_client()

        if redis_client is None:
            logger.error("Redis connection failed. Use --dry-run for testing.")
            sys.exit(1)

    loops = ReflectionLoops(redis_client=redis_client, qdrant_client=qdrant_client)

    artifact = None
    try:
        if args.type == "micro":
            artifact = run_micro_reflection(
                loops=loops,
                story_id=args.story_id,
                action=args.action,
                result=args.result,
                duration_ms=args.duration_ms,
                error=args.error,
            )

        elif args.type == "meso":
            artifact = run_meso_reflection(
                loops=loops,
                story_id=args.story_id,
                what_changed=args.what_changed,
                kpi_file=args.kpi_file,
                failures_file=args.failures_file,
                root_causes_file=args.root_causes_file,
                automation_file=args.automation_file,
                promotion_file=args.promotion_file,
            )

        elif args.type == "macro":
            artifact = run_macro_reflection(
                loops=loops,
                period=args.period,
                stories_file=args.stories_file,
                kpi_file=args.kpi_file,
            )

    except Exception as e:
        logger.error(f"Reflection loop failed: {e}")
        sys.exit(1)

    if artifact:
        artifact_json = artifact.to_json()

        if args.output:
            with open(args.output, "w") as f:
                f.write(artifact_json)
            logger.info(f"Reflection artifact written to {args.output}")
        else:
            print(artifact_json)

        logger.info("Reflection loop completed successfully")


if __name__ == "__main__":
    main()
