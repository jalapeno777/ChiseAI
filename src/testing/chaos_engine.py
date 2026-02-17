"""Chaos engineering engine for ChiseAI.

Provides random failure injection, recovery validation, and chaos report
generation for testing system resilience under failure conditions.

For PAPER-003-002: E2E Integration Testing with Chaos Engineering
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

from .failure_injector import (
    ErrorInjector,
    FailureInjector,
    InjectionEvent,
    LatencyInjector,
    NetworkPartitionInjector,
    ServiceFailureInjector,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ChaosPhase(Enum):
    """Phases of a chaos experiment."""

    PENDING = auto()
    SETUP = auto()
    BASELINE = auto()
    INJECTION = auto()
    VALIDATION = auto()
    RECOVERY = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class ChaosConfig:
    """Configuration for chaos experiments.

    Attributes:
        failure_probability: Probability of failure (0-100)
        max_concurrent_failures: Maximum simultaneous failures
        recovery_timeout_seconds: Timeout for recovery validation
        baseline_duration_seconds: Duration of baseline measurement
        injection_duration_seconds: Duration of failure injection
        random_seed: Seed for reproducibility
    """

    failure_probability: float = 50.0
    max_concurrent_failures: int = 3
    recovery_timeout_seconds: float = 30.0
    baseline_duration_seconds: float = 10.0
    injection_duration_seconds: float = 30.0
    random_seed: int | None = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0 <= self.failure_probability <= 100:
            raise ValueError("failure_probability must be between 0 and 100")
        if self.max_concurrent_failures < 1:
            raise ValueError("max_concurrent_failures must be at least 1")


@dataclass
class RecoveryResult:
    """Result of a recovery validation.

    Attributes:
        success: Whether recovery was successful
        duration_seconds: Time taken to recover
        validation_checks: Number of validation checks performed
        failed_checks: Number of failed validation checks
        details: Additional details about recovery
    """

    success: bool
    duration_seconds: float
    validation_checks: int = 0
    failed_checks: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "duration_seconds": round(self.duration_seconds, 3),
            "validation_checks": self.validation_checks,
            "failed_checks": self.failed_checks,
            "details": self.details,
        }


@dataclass
class ChaosReport:
    """Report generated from a chaos experiment.

    Attributes:
        experiment_id: Unique identifier
        start_time: When experiment started
        end_time: When experiment ended
        config: Chaos configuration used
        phases: List of phases executed
        injections: List of failure injections
        recovery_results: Results of recovery validations
        metrics: Experiment metrics
        summary: Human-readable summary
    """

    experiment_id: str
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    config: ChaosConfig = field(default_factory=ChaosConfig)
    phases: list[dict[str, Any]] = field(default_factory=list)
    injections: list[InjectionEvent] = field(default_factory=list)
    recovery_results: list[RecoveryResult] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def add_phase(
        self, phase: ChaosPhase, details: dict[str, Any] | None = None
    ) -> None:
        """Add a phase to the report.

        Args:
            phase: Phase that was executed
            details: Additional phase details
        """
        self.phases.append(
            {
                "phase": phase.name,
                "timestamp": datetime.now(UTC).isoformat(),
                "details": details or {},
            }
        )

    def add_injection(self, event: InjectionEvent) -> None:
        """Add an injection event to the report.

        Args:
            event: Injection event to add
        """
        self.injections.append(event)

    def add_recovery_result(self, result: RecoveryResult) -> None:
        """Add a recovery result to the report.

        Args:
            result: Recovery result to add
        """
        self.recovery_results.append(result)

    def finalize(self, success: bool = True) -> None:
        """Finalize the report.

        Args:
            success: Whether experiment was successful
        """
        self.end_time = datetime.now(UTC)
        self._calculate_metrics()
        self._generate_summary(success)

    def _calculate_metrics(self) -> None:
        """Calculate experiment metrics."""
        total_injections = len(self.injections)
        recovered = sum(1 for i in self.injections if i.recovered)
        recovery_rate = recovered / total_injections if total_injections > 0 else 0

        total_recoveries = len(self.recovery_results)
        successful_recoveries = sum(1 for r in self.recovery_results if r.success)
        recovery_success_rate = (
            successful_recoveries / total_recoveries if total_recoveries > 0 else 0
        )

        avg_recovery_time = (
            sum(r.duration_seconds for r in self.recovery_results) / total_recoveries
            if total_recoveries > 0
            else 0
        )

        duration = 0.0
        if self.end_time and self.start_time:
            duration = (self.end_time - self.start_time).total_seconds()

        self.metrics = {
            "total_injections": total_injections,
            "recovered_injections": recovered,
            "injection_recovery_rate": round(recovery_rate, 3),
            "total_recovery_validations": total_recoveries,
            "successful_recoveries": successful_recoveries,
            "recovery_success_rate": round(recovery_success_rate, 3),
            "average_recovery_time_seconds": round(avg_recovery_time, 3),
            "experiment_duration_seconds": round(duration, 3),
        }

    def _generate_summary(self, success: bool) -> None:
        """Generate human-readable summary."""
        status = "SUCCESS" if success else "FAILED"
        lines = [
            f"Chaos Experiment Report: {self.experiment_id}",
            f"Status: {status}",
            f"Duration: {self.metrics.get('experiment_duration_seconds', 0):.1f}s",
            "",
            "Injections:",
            f"  Total: {self.metrics.get('total_injections', 0)}",
            f"  Recovery Rate: {self.metrics.get('injection_recovery_rate', 0) * 100:.1f}%",  # noqa: E501
            "",
            "Recovery Validations:",
            f"  Total: {self.metrics.get('total_recovery_validations', 0)}",
            f"  Success Rate: {self.metrics.get('recovery_success_rate', 0) * 100:.1f}%",  # noqa: E501
            f"  Avg Time: {self.metrics.get('average_recovery_time_seconds', 0):.2f}s",
        ]
        self.summary = "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "config": {
                "failure_probability": self.config.failure_probability,
                "max_concurrent_failures": self.config.max_concurrent_failures,
                "recovery_timeout_seconds": self.config.recovery_timeout_seconds,
            },
            "phases": self.phases,
            "injections": [i.to_dict() for i in self.injections],
            "recovery_results": [r.to_dict() for r in self.recovery_results],
            "metrics": self.metrics,
            "summary": self.summary,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert report to JSON string.

        Args:
            indent: JSON indentation

        Returns:
            JSON string
        """
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: Path | str) -> None:
        """Save report to file.

        Args:
            path: Path to save report
        """
        path = Path(path)
        path.write_text(self.to_json())
        logger.info(f"Chaos report saved to {path}")


@runtime_checkable
class RecoveryValidator(Protocol):
    """Protocol for validating system recovery."""

    async def check_recovery(self) -> bool:
        """Check if system has recovered.

        Returns:
            True if system is recovered
        """
        ...

    async def get_system_state(self) -> dict[str, Any]:
        """Get current system state.

        Returns:
            Dictionary of system state
        """
        ...


class ChaosEngine:
    """Engine for running chaos engineering experiments.

        Orchestrates failure injection, recovery validation, and report
    generation for testing system resilience.

        Attributes:
            config: Chaos experiment configuration
            injectors: Available failure injectors
            report: Generated chaos report
    """

    def __init__(
        self,
        config: ChaosConfig | None = None,
        injectors: list[FailureInjector] | None = None,
        experiment_id: str | None = None,
    ) -> None:
        """Initialize chaos engine.

        Args:
            config: Chaos configuration
            injectors: Failure injectors to use
            experiment_id: Unique experiment identifier
        """
        self.config = config or ChaosConfig()
        self._injectors = injectors or self._create_default_injectors()
        self._experiment_id = experiment_id or self._generate_experiment_id()
        self._report = ChaosReport(
            experiment_id=self._experiment_id,
            config=self.config,
        )
        self._phase = ChaosPhase.PENDING
        self._recovery_validator: RecoveryValidator | None = None
        self._stop_event = asyncio.Event()

        if self.config.random_seed:
            random.seed(self.config.random_seed)

        logger.info(f"ChaosEngine initialized: {self._experiment_id}")

    def _create_default_injectors(self) -> list[FailureInjector]:
        """Create default set of failure injectors."""
        return [
            NetworkPartitionInjector(),
            ServiceFailureInjector(),
            LatencyInjector(),
            ErrorInjector(),
        ]

    def _generate_experiment_id(self) -> str:
        """Generate unique experiment ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        random_suffix = random.randint(1000, 9999)
        return f"chaos-{timestamp}-{random_suffix}"

    @property
    def report(self) -> ChaosReport:
        """Get the current chaos report."""
        return self._report

    @property
    def phase(self) -> ChaosPhase:
        """Get current experiment phase."""
        return self._phase

    def set_recovery_validator(self, validator: RecoveryValidator) -> None:
        """Set the recovery validator.

        Args:
            validator: Validator to use for recovery checks
        """
        self._recovery_validator = validator

    async def run(
        self,
        targets: list[str] | None = None,
        custom_injections: list[dict[str, Any]] | None = None,
    ) -> ChaosReport:
        """Run a complete chaos experiment.

        Args:
            targets: List of targets to inject failures into
            custom_injections: Custom injection configurations

        Returns:
            ChaosReport with experiment results
        """
        try:
            await self._run_setup()
            await self._run_baseline()
            await self._run_injection(targets, custom_injections)
            await self._run_validation()
            await self._run_recovery()
            self._phase = ChaosPhase.COMPLETED
            self._report.finalize(success=True)
        except Exception as e:
            logger.error(f"Chaos experiment failed: {e}")
            self._phase = ChaosPhase.FAILED
            self._report.finalize(success=False)
            raise

        return self._report

    async def _run_setup(self) -> None:
        """Run setup phase."""
        self._phase = ChaosPhase.SETUP
        self._report.add_phase(
            ChaosPhase.SETUP,
            {
                "injectors": [i.name for i in self._injectors],
                "config": {
                    "failure_probability": self.config.failure_probability,
                    "max_concurrent_failures": self.config.max_concurrent_failures,
                },
            },
        )
        logger.info("Chaos experiment setup complete")

    async def _run_baseline(self) -> None:
        """Run baseline measurement phase."""
        self._phase = ChaosPhase.BASELINE
        start_time = datetime.now(UTC)

        logger.info(f"Running baseline for {self.config.baseline_duration_seconds}s...")
        await asyncio.sleep(self.config.baseline_duration_seconds)

        self._report.add_phase(
            ChaosPhase.BASELINE,
            {
                "duration_seconds": self.config.baseline_duration_seconds,
                "start_time": start_time.isoformat(),
            },
        )

    async def _run_injection(
        self,
        targets: list[str] | None = None,
        custom_injections: list[dict[str, Any]] | None = None,
    ) -> None:
        """Run failure injection phase."""
        self._phase = ChaosPhase.INJECTION
        start_time = datetime.now(UTC)

        injection_tasks = []

        if custom_injections:
            for injection_config in custom_injections:
                task = self._execute_custom_injection(injection_config)
                injection_tasks.append(task)
        elif targets:
            for target in targets:
                if random.random() * 100 < self.config.failure_probability:
                    task = self._execute_random_injection(target)
                    injection_tasks.append(task)

                    if len(injection_tasks) >= self.config.max_concurrent_failures:
                        break

        if injection_tasks:
            await asyncio.gather(*injection_tasks, return_exceptions=True)

        # Continue injection for the configured duration
        elapsed = (datetime.now(UTC) - start_time).total_seconds()
        remaining = self.config.injection_duration_seconds - elapsed
        if remaining > 0:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=remaining,
            )

        self._report.add_phase(
            ChaosPhase.INJECTION,
            {
                "duration_seconds": self.config.injection_duration_seconds,
                "injections_count": len(self._report.injections),
                "start_time": start_time.isoformat(),
            },
        )

    async def _execute_random_injection(self, target: str) -> None:
        """Execute a random injection on target."""
        injector = random.choice(self._injectors)

        try:
            if isinstance(injector, NetworkPartitionInjector):
                event = await injector.inject(target, partition_type="complete")
            elif isinstance(injector, ServiceFailureInjector):
                event = await injector.inject(target, failure_type="crash")
            elif isinstance(injector, LatencyInjector):
                event = await injector.inject(target, delay_type="random", delay_ms=500)
            elif isinstance(injector, ErrorInjector):
                event = await injector.inject(target, error_type="exception")
            else:
                return

            self._report.add_injection(event)
        except Exception as e:
            logger.error(f"Injection failed for {target}: {e}")

    async def _execute_custom_injection(self, config: dict[str, Any]) -> None:
        """Execute a custom injection."""
        injector_type = config.get("injector")
        target = config.get("target", "unknown")

        for injector in self._injectors:
            if injector.name == injector_type or (
                injector_type == "network"
                and isinstance(injector, NetworkPartitionInjector)
            ):
                try:
                    event = await injector.inject(target, **config.get("params", {}))
                    self._report.add_injection(event)
                except Exception as e:
                    logger.error(f"Custom injection failed: {e}")
                break

    async def _run_validation(self) -> None:
        """Run recovery validation phase."""
        self._phase = ChaosPhase.VALIDATION
        start_time = datetime.now(UTC)

        if self._recovery_validator:
            is_recovered = await self._validate_recovery()

            self._report.add_phase(
                ChaosPhase.VALIDATION,
                {
                    "recovered": is_recovered,
                    "duration_seconds": (
                        datetime.now(UTC) - start_time
                    ).total_seconds(),
                },
            )

    async def _validate_recovery(self) -> bool:
        """Validate system recovery.

        Returns:
            True if system has recovered
        """
        if not self._recovery_validator:
            return True

        start_time = datetime.now(UTC)
        check_interval = 1.0
        max_checks = int(self.config.recovery_timeout_seconds / check_interval)

        for check_num in range(max_checks):
            if await self._recovery_validator.check_recovery():
                duration = (datetime.now(UTC) - start_time).total_seconds()
                result = RecoveryResult(
                    success=True,
                    duration_seconds=duration,
                    validation_checks=check_num + 1,
                )
                self._report.add_recovery_result(result)
                logger.info(f"Recovery validated after {duration:.2f}s")
                return True

            await asyncio.sleep(check_interval)

        # Recovery timeout
        duration = (datetime.now(UTC) - start_time).total_seconds()
        result = RecoveryResult(
            success=False,
            duration_seconds=duration,
            validation_checks=max_checks,
            details={"error": "Recovery timeout"},
        )
        self._report.add_recovery_result(result)
        logger.warning(f"Recovery validation failed after {duration:.2f}s")
        return False

    async def _run_recovery(self) -> None:
        """Run recovery phase - clean up all injections."""
        self._phase = ChaosPhase.RECOVERY
        start_time = datetime.now(UTC)

        recovery_tasks = []
        for event in self._report.injections:
            for injector in self._injectors:
                task = injector.recover(event)
                recovery_tasks.append(task)

        if recovery_tasks:
            results = await asyncio.gather(*recovery_tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)

            self._report.add_phase(
                ChaosPhase.RECOVERY,
                {
                    "duration_seconds": (
                        datetime.now(UTC) - start_time
                    ).total_seconds(),
                    "successful_recoveries": success_count,
                    "total_recoveries": len(recovery_tasks),
                },
            )

        self._stop_event.set()

    def stop(self) -> None:
        """Stop the chaos experiment."""
        self._stop_event.set()
        logger.info("Chaos experiment stop requested")

    async def inject_single_failure(
        self,
        injector_name: str,
        target: str,
        **kwargs: Any,
    ) -> InjectionEvent | None:
        """Inject a single failure.

        Args:
            injector_name: Name of injector to use
            target: Target to inject failure into
            **kwargs: Injection parameters

        Returns:
            InjectionEvent if successful, None otherwise
        """
        for injector in self._injectors:
            if injector.name == injector_name:
                try:
                    event = await injector.inject(target, **kwargs)
                    self._report.add_injection(event)
                    return event
                except Exception as e:
                    logger.error(f"Single injection failed: {e}")
                    return None
        return None

    async def recover_all(self) -> list[InjectionEvent]:
        """Recover all injected failures.

        Returns:
            List of recovered events
        """
        recovered = []
        for event in self._report.injections:
            for injector in self._injectors:
                if await injector.recover(event):
                    recovered.append(event)
                    break
        return recovered
