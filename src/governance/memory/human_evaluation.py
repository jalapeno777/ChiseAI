"""
Human Evaluation Interface for Observation Quality Metrics.

Stores human evaluation results for observations scored on:
- accuracy: factually correct?
- completeness: captures all key facts?
- actionability: usable for future decisions?
- non_redundancy: not repeating prior observations?

Ref: memory-audit-framework-20260409.md Section 3a
"""

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Redis key prefix for human evaluation results
HUMAN_EVAL_PREFIX = "bmad:chiseai:memory:human_eval"


def _get_redis_client() -> object | None:
    """Get or create Redis client.

    Returns:
        Redis client instance or None if connection fails.
    """
    try:
        import redis as redis_lib

        client = redis_lib.Redis(
            host="host.docker.internal",
            port=6380,
            db=1,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        return None


@dataclass
class HumanEvaluationResult:
    """
    Result of human evaluation of observation quality.

    From memory-audit-framework-20260409.md Section 3a:
    Scoring rubric (1-5 each dimension):
    - accuracy: factually correct?
    - completeness: captures all key facts?
    - actionability: usable for future decisions?
    - non_redundancy: not repeating prior observations?
    """

    accuracy: float  # 1-5 scale
    completeness: float  # 1-5 scale
    actionability: float  # 1-5 scale
    non_redundancy: float  # 1-5 scale
    evaluator_id: str
    story_id: str
    observation_id: str
    evaluated_at: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for Redis hash storage."""
        return {
            "accuracy": str(self.accuracy),
            "completeness": str(self.completeness),
            "actionability": str(self.actionability),
            "non_redundancy": str(self.non_redundancy),
            "evaluator_id": self.evaluator_id,
            "story_id": self.story_id,
            "observation_id": self.observation_id,
            "evaluated_at": self.evaluated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HumanEvaluationResult":
        """Create from Redis hash data."""
        return cls(
            accuracy=float(data["accuracy"]),
            completeness=float(data["completeness"]),
            actionability=float(data["actionability"]),
            non_redundancy=float(data["non_redundancy"]),
            evaluator_id=data["evaluator_id"],
            story_id=data["story_id"],
            observation_id=data["observation_id"],
            evaluated_at=datetime.fromisoformat(data["evaluated_at"]),
        )


def _build_key(story_id: str, observation_id: str) -> str:
    """Build Redis key for human evaluation."""
    return f"{HUMAN_EVAL_PREFIX}:{story_id}:{observation_id}"


def store_human_evaluation(result: HumanEvaluationResult) -> str:
    """
    Store human evaluation result to Redis.

    Redis key: bmad:chiseai:memory:human_eval:{story_id}:{observation_id}
    Hash fields: evaluator_id, evaluated_at, accuracy, completeness, actionability, non_redundancy

    Args:
        result: HumanEvaluationResult to store

    Returns:
        Redis key
    """
    redis_client = _get_redis_client()
    if redis_client is None:
        raise RuntimeError("Redis connection unavailable")

    key = _build_key(result.story_id, result.observation_id)
    redis_client.hset(key, mapping=result.to_dict())
    logger.debug(f"Stored human evaluation at key: {key}")
    return key


def get_latest_evaluation(story_id: str) -> HumanEvaluationResult | None:
    """
    Get latest human evaluation for a story.

    Note: This returns the most recent evaluation for a given story_id.
    If multiple observations exist, it returns the most recently evaluated one.

    Args:
        story_id: Story identifier

    Returns:
        HumanEvaluationResult or None if not found.
    """
    redis_client = _get_redis_client()
    if redis_client is None:
        logger.warning("Redis connection unavailable")
        return None

    # Scan for all evaluations matching this story
    pattern = f"{HUMAN_EVAL_PREFIX}:{story_id}:*"
    keys = list(redis_client.scan_iter(match=pattern))

    if not keys:
        return None

    # Sort by evaluated_at timestamp to get the latest
    latest_key = None
    latest_time = None

    for key in keys:
        data = redis_client.hgetall(key)
        if data and "evaluated_at" in data:
            eval_time = datetime.fromisoformat(data["evaluated_at"])
            if latest_time is None or eval_time > latest_time:
                latest_time = eval_time
                latest_key = key

    if latest_key is None:
        return None

    data = redis_client.hgetall(latest_key)
    return HumanEvaluationResult.from_dict(data) if data else None


def get_evaluation_summary(story_id: str) -> dict:
    """
    Get summary stats for all evaluations of a story.

    Args:
        story_id: Story identifier

    Returns:
        {
            'count': N,
            'mean_accuracy': float,
            'mean_completeness': float,
            'mean_actionability': float,
            'mean_non_redundancy': float
        }
    """
    redis_client = _get_redis_client()
    if redis_client is None:
        logger.warning("Redis connection unavailable")
        return {
            "count": 0,
            "mean_accuracy": 0.0,
            "mean_completeness": 0.0,
            "mean_actionability": 0.0,
            "mean_non_redundancy": 0.0,
        }

    # Scan for all evaluations matching this story
    pattern = f"{HUMAN_EVAL_PREFIX}:{story_id}:*"
    keys = list(redis_client.scan_iter(match=pattern))

    if not keys:
        return {
            "count": 0,
            "mean_accuracy": 0.0,
            "mean_completeness": 0.0,
            "mean_actionability": 0.0,
            "mean_non_redundancy": 0.0,
        }

    total_accuracy = 0.0
    total_completeness = 0.0
    total_actionability = 0.0
    total_non_redundancy = 0.0
    count = 0

    for key in keys:
        data = redis_client.hgetall(key)
        if data and all(
            k in data
            for k in ["accuracy", "completeness", "actionability", "non_redundancy"]
        ):
            total_accuracy += float(data["accuracy"])
            total_completeness += float(data["completeness"])
            total_actionability += float(data["actionability"])
            total_non_redundancy += float(data["non_redundancy"])
            count += 1

    if count == 0:
        return {
            "count": 0,
            "mean_accuracy": 0.0,
            "mean_completeness": 0.0,
            "mean_actionability": 0.0,
            "mean_non_redundancy": 0.0,
        }

    return {
        "count": count,
        "mean_accuracy": total_accuracy / count,
        "mean_completeness": total_completeness / count,
        "mean_actionability": total_actionability / count,
        "mean_non_redundancy": total_non_redundancy / count,
    }
