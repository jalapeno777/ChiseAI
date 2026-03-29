"""Autocog job registry loader and utilities.

Loads and parses the autocog job registry from YAML, providing
dataclasses for jobs, preconditions, and retry policies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class Cadence(Enum):
    """Cadence for autocog job scheduling."""

    MIN_15 = "15m"
    HOURLY = "1h"
    HOURLY_6 = "6h"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class RiskLevel(Enum):
    """Risk level for autocog jobs."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PreconditionType(Enum):
    """Types of preconditions for autocog jobs."""

    FILE_EXISTS = "file_exists"
    DIR_EXISTS = "dir_exists"
    ENV_VAR = "env_var"
    FLAG = "flag"


@dataclass
class Precondition:
    """A precondition that must be met before an autocog job can run."""

    type: PreconditionType
    params: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | str) -> Precondition:
        """Create a Precondition from a dictionary or string.

        Handles three formats:
        - String shorthand: "file_exists:/path" or "file_exists" (path derived from context)
        - Dict shorthand: {"file_exists": "/path"} or {"file_exists": {"path": "/path"}}
        - Full format: {"type": "file_exists", "params": {"path": "/path"}}

        Args:
            data: Dictionary or string with precondition data.

        Returns:
            A Precondition instance.
        """
        # Handle string shorthand: "file_exists:/path" or just "file_exists"
        if isinstance(data, str):
            if ":" in data:
                precondition_type_str, path = data.split(":", 1)
                precondition_type = PreconditionType(precondition_type_str)
                return cls(type=precondition_type, params={"path": path})
            else:
                # Just type, no path - will fail precondition check unless path is optional
                precondition_type = PreconditionType(data)
                return cls(type=precondition_type, params={})

        # Handle dict shorthand: {"file_exists": "/path"}
        if len(data) == 1 and "type" not in data:
            for precondition_type_str, value in data.items():
                precondition_type = PreconditionType(precondition_type_str)
                # Value can be a string path or a dict with params
                if isinstance(value, str):
                    params = {"path": value}
                elif isinstance(value, dict):
                    params = value
                else:
                    params = {}
                return cls(type=precondition_type, params=params)

        # Full format: {"type": "file_exists", "params": {"path": "/path"}}
        precondition_type = PreconditionType(data.get("type", "file_exists"))
        params = data.get("params", {})
        return cls(type=precondition_type, params=params)

    def is_met(self) -> bool:
        """Check if this precondition is currently met.

        Returns:
            True if the precondition is met, False otherwise.
        """
        if self.type == PreconditionType.FILE_EXISTS:
            path = self.params.get("path")
            if not path:
                return False
            return Path(path).is_file()

        elif self.type == PreconditionType.DIR_EXISTS:
            path = self.params.get("path")
            if not path:
                return False
            return Path(path).is_dir()

        elif self.type == PreconditionType.ENV_VAR:
            var_name = self.params.get("name")
            if not var_name:
                return False
            expected_value = self.params.get("value")
            actual_value = os.environ.get(var_name)
            if expected_value is not None:
                return actual_value == expected_value
            return actual_value is not None

        elif self.type == PreconditionType.FLAG:
            flag_name = self.params.get("name")
            if not flag_name:
                return False
            # Check if flag is set to true (used as a simple boolean flag)
            return os.environ.get(flag_name, "").lower() in ("true", "1", "yes")

        return False


@dataclass
class RetryPolicy:
    """Retry policy for autocog jobs."""

    max_attempts: int = 1
    initial_delay_seconds: int = 60
    backoff_multiplier: float = 2.0
    max_delay_seconds: int = 3600

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RetryPolicy:
        """Create a RetryPolicy from a dictionary.

        Handles both formats:
        - Full format: {"max_attempts": 3, "initial_delay_seconds": 60, ...}
        - Shorthand format: {"max_retries": 3, "backoff_seconds": 60}

        Args:
            data: Dictionary with retry policy settings, or None/empty.

        Returns:
            A RetryPolicy instance with defaults if data is empty.
        """
        if not data:
            return cls()
        return cls(
            max_attempts=data.get("max_attempts", data.get("max_retries", 1)),
            initial_delay_seconds=data.get(
                "initial_delay_seconds", data.get("backoff_seconds", 60)
            ),
            backoff_multiplier=data.get("backoff_multiplier", 2.0),
            max_delay_seconds=data.get("max_delay_seconds", 3600),
        )


@dataclass
class AutocogJob:
    """An autocog job definition from the registry."""

    job_id: str
    enabled: bool
    cadence: Cadence
    timeout_seconds: int
    risk_level: RiskLevel
    idempotency_key: str
    command: list[str]
    preconditions: list[Precondition] = field(default_factory=list)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    required_approvals: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutocogJob:
        """Create an AutocogJob from a dictionary.

        Args:
            data: Dictionary with job configuration.

        Returns:
            An AutocogJob instance.
        """
        # Parse cadence
        cadence_str = data.get("cadence", "1h")
        cadence = Cadence(cadence_str)

        # Parse risk level
        risk_str = data.get("risk_level", "medium")
        risk_level = RiskLevel(risk_str)

        # Parse preconditions
        preconditions = [
            Precondition.from_dict(p) for p in data.get("preconditions", [])
        ]

        # Parse retry policy
        retry_policy = RetryPolicy.from_dict(data.get("retry_policy"))

        return cls(
            job_id=data["job_id"],
            enabled=data.get("enabled", True),
            cadence=cadence,
            timeout_seconds=data.get("timeout_seconds", 300),
            risk_level=risk_level,
            idempotency_key=data.get("idempotency_key", ""),
            command=data.get("command", []),
            preconditions=preconditions,
            retry_policy=retry_policy,
            required_approvals=data.get("required_approvals", []),
        )

    def is_ready(self) -> bool:
        """Check if this job is ready to run (all preconditions met).

        Returns:
            True if all preconditions are met or there are no preconditions.
        """
        if not self.preconditions:
            return True
        return all(p.is_met() for p in self.preconditions)


def load_registry(path: Path | None = None) -> list[AutocogJob]:
    """Load the autocog job registry from a YAML file.

    Args:
        path: Path to the registry YAML file. If None, uses the default
              location at scripts/evaluation/autocog_registry.yaml.

    Returns:
        A list of AutocogJob instances parsed from the registry.

    Raises:
        FileNotFoundError: If the registry file does not exist.
        yaml.YAMLError: If the YAML parsing fails.
    """
    if path is None:
        # Default path relative to this module
        path = Path(__file__).parent / "autocog_registry.yaml"

    with open(path) as f:
        data = yaml.safe_load(f)

    jobs = data.get("jobs", []) if data else []
    return [AutocogJob.from_dict(job) for job in jobs]


def get_autocog_jobs(jobs: list[AutocogJob]) -> list[AutocogJob]:
    """Filter to only enabled autocog jobs.

    An autocog job is defined as a job with job_id starting with "autocog_" or "autocog.".

    Args:
        jobs: List of all AutocogJob instances.

    Returns:
        List of only the enabled AutocogJob instances that are autocog jobs.
    """
    return [
        job
        for job in jobs
        if job.enabled
        and (job.job_id.startswith("autocog_") or job.job_id.startswith("autocog."))
    ]


def get_jobs_by_cadence(jobs: list[AutocogJob], cadence: Cadence) -> list[AutocogJob]:
    """Filter autocog jobs by cadence.

    Args:
        jobs: List of AutocogJob instances.
        cadence: The Cadence to filter by.

    Returns:
        List of AutocogJob instances with the specified cadence.
    """
    return [job for job in jobs if job.cadence == cadence]
