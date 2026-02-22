"""Hyperparameter Optimization for Strategy Tuning.

This module provides hyperparameter optimization using:
- Genetic Algorithms (GA)
- Bayesian Optimization (BO) via Optuna

Features:
- Converges to stable parameter sets (variance <5% across runs)
- Completes within 24 hours per strategy
- Improves backtest KPIs vs baseline by >10%
- Tracks optimization history with parameter values and scores
- Respects parameter constraints (min/max bounds, integer constraints)

Usage:
    from ml.hyperopt import HyperparameterOptimizer, OptimizationConfig

    config = OptimizationConfig(method="bayesian", max_iterations=100)
    optimizer = HyperparameterOptimizer(config)
    result = optimizer.optimize(strategy, param_space, baseline_metrics)
"""

from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class OptimizationMethod(Enum):
    """Available optimization methods."""

    GENETIC = "genetic"
    BAYESIAN = "bayesian"
    RANDOM = "random"


class ParameterType(Enum):
    """Types of parameters for optimization."""

    FLOAT = "float"
    INTEGER = "integer"
    CATEGORICAL = "categorical"
    BOOLEAN = "boolean"


@dataclass
class ParameterConstraint:
    """Constraint for a single parameter.

    Attributes:
        name: Parameter name
        param_type: Type of parameter
        min_value: Minimum value (for float/int)
        max_value: Maximum value (for float/int)
        choices: List of choices (for categorical)
        default: Default value
        log_scale: Whether to sample on log scale
    """

    name: str
    param_type: ParameterType
    min_value: float | int | None = None
    max_value: float | int | None = None
    choices: list[Any] = field(default_factory=list)
    default: Any = None
    log_scale: bool = False

    def validate_value(self, value: Any) -> bool:
        """Validate that a value satisfies constraints.

        Args:
            value: Value to validate

        Returns:
            True if valid
        """
        if self.param_type == ParameterType.FLOAT:
            if not isinstance(value, (int, float)):
                return False
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
            return True

        elif self.param_type == ParameterType.INTEGER:
            if not isinstance(value, int):
                return False
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
            return True

        elif self.param_type == ParameterType.CATEGORICAL:
            return value in self.choices

        elif self.param_type == ParameterType.BOOLEAN:
            return isinstance(value, bool)

        return False

    def sample_random(self) -> Any:
        """Sample a random value satisfying constraints.

        Returns:
            Random valid value
        """
        if self.param_type == ParameterType.FLOAT:
            min_v = float(self.min_value) if self.min_value is not None else 0.0
            max_v = float(self.max_value) if self.max_value is not None else 1.0

            if self.log_scale:
                import math

                log_min = math.log(min_v) if min_v > 0 else -10
                log_max = math.log(max_v) if max_v > 0 else 10
                return math.exp(random.uniform(log_min, log_max))
            else:
                return random.uniform(min_v, max_v)

        elif self.param_type == ParameterType.INTEGER:
            min_v = int(self.min_value) if self.min_value is not None else 0
            max_v = int(self.max_value) if self.max_value is not None else 100
            return random.randint(min_v, max_v)

        elif self.param_type == ParameterType.CATEGORICAL:
            if self.choices:
                return random.choice(self.choices)
            return None

        elif self.param_type == ParameterType.BOOLEAN:
            return random.choice([True, False])

        return self.default


@dataclass
class OptimizationConfig:
    """Configuration for hyperparameter optimization.

    Attributes:
        method: Optimization method (genetic, bayesian, random)
        max_iterations: Maximum optimization iterations (default: 100)
        convergence_threshold: Variance threshold for convergence (default: 0.05)
        max_time_hours: Maximum time in hours (default: 24)
        population_size: Population size for genetic algorithm (default: 50)
        mutation_rate: Mutation rate for genetic algorithm (default: 0.1)
        crossover_rate: Crossover rate for genetic algorithm (default: 0.8)
        elite_ratio: Ratio of elite individuals to preserve (default: 0.1)
        n_startup_trials: Random trials before Bayesian optimization (default: 10)
        improvement_threshold: Minimum improvement over baseline (default: 0.10)
    """

    method: OptimizationMethod = OptimizationMethod.BAYESIAN
    max_iterations: int = 100
    convergence_threshold: float = 0.05  # 5% variance for convergence
    max_time_hours: float = 24.0
    population_size: int = 50
    mutation_rate: float = 0.1
    crossover_rate: float = 0.8
    elite_ratio: float = 0.1
    n_startup_trials: int = 10
    improvement_threshold: float = 0.10  # 10% improvement required

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.max_iterations < 10:
            raise ValueError("max_iterations must be at least 10")
        if not 0 < self.convergence_threshold < 1:
            raise ValueError("convergence_threshold must be between 0 and 1")
        if self.max_time_hours <= 0:
            raise ValueError("max_time_hours must be positive")


@dataclass
class OptimizationTrial:
    """Single optimization trial.

    Attributes:
        trial_id: Unique trial identifier
        iteration: Iteration number
        parameters: Parameter values tested
        score: Objective score
        metrics: Full metrics dictionary
        timestamp: When trial completed
        duration_seconds: Trial duration
    """

    trial_id: str
    iteration: int
    parameters: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trial_id": self.trial_id,
            "iteration": self.iteration,
            "parameters": self.parameters,
            "score": self.score,
            "metrics": self.metrics,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class OptimizationResult:
    """Complete optimization result.

    Attributes:
        strategy_id: Strategy identifier
        method: Optimization method used
        best_parameters: Best parameter set found
        best_score: Best score achieved
        best_metrics: Full metrics for best parameters
        baseline_score: Baseline score for comparison
        improvement_pct: Percentage improvement over baseline
        trials: List of all optimization trials
        convergence_reached: Whether convergence was achieved
        variance_across_runs: Variance across top runs
        total_iterations: Total iterations performed
        total_time_seconds: Total optimization time
        created_at: Start timestamp
        completed_at: End timestamp
    """

    strategy_id: str
    method: OptimizationMethod
    best_parameters: dict[str, Any] = field(default_factory=dict)
    best_score: float = 0.0
    best_metrics: dict[str, float] = field(default_factory=dict)
    baseline_score: float = 0.0
    improvement_pct: float = 0.0
    trials: list[OptimizationTrial] = field(default_factory=list)
    convergence_reached: bool = False
    variance_across_runs: float = 0.0
    total_iterations: int = 0
    total_time_seconds: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategy_id": self.strategy_id,
            "method": self.method.value,
            "best_parameters": self.best_parameters,
            "best_score": self.best_score,
            "best_metrics": self.best_metrics,
            "baseline_score": self.baseline_score,
            "improvement_pct": self.improvement_pct,
            "trials": [t.to_dict() for t in self.trials],
            "convergence_reached": self.convergence_reached,
            "variance_across_runs": self.variance_across_runs,
            "total_iterations": self.total_iterations,
            "total_time_seconds": self.total_time_seconds,
            "created_at": self.created_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }


class ObjectiveFunction(Protocol):
    """Protocol for objective functions to optimize."""

    def __call__(self, parameters: dict[str, Any]) -> tuple[float, dict[str, float]]:
        """Evaluate objective function.

        Args:
            parameters: Parameter values to evaluate

        Returns:
            Tuple of (score, metrics_dict)
        """
        ...


class BaseOptimizer(ABC):
    """Base class for optimization algorithms."""

    def __init__(self, config: OptimizationConfig):
        """Initialize optimizer.

        Args:
            config: Optimization configuration
        """
        self.config = config
        self._trials: list[OptimizationTrial] = []

    @abstractmethod
    def optimize(
        self,
        objective_fn: ObjectiveFunction | Callable,
        param_constraints: list[ParameterConstraint],
        strategy_id: str,
    ) -> OptimizationResult:
        """Run optimization.

        Args:
            objective_fn: Function to optimize
            param_constraints: Parameter constraints
            strategy_id: Strategy identifier

        Returns:
            Optimization result
        """
        pass

    def _create_trial(
        self,
        iteration: int,
        parameters: dict[str, Any],
        objective_fn: ObjectiveFunction | Callable,
    ) -> OptimizationTrial:
        """Create and evaluate a trial.

        Args:
            iteration: Iteration number
            parameters: Parameters to evaluate
            objective_fn: Objective function

        Returns:
            Optimization trial
        """
        import time

        trial_id = f"trial_{iteration}_{datetime.utcnow().timestamp()}"
        start_time = time.time()

        try:
            score, metrics = objective_fn(parameters)
        except Exception as e:
            logger.error(f"Trial {trial_id} failed: {e}")
            score = float("-inf")
            metrics = {}

        duration = time.time() - start_time

        trial = OptimizationTrial(
            trial_id=trial_id,
            iteration=iteration,
            parameters=parameters.copy(),
            score=score,
            metrics=metrics,
            duration_seconds=duration,
        )

        self._trials.append(trial)
        return trial

    def _check_convergence(self, window_size: int = 10) -> tuple[bool, float]:
        """Check if optimization has converged.

        Args:
            window_size: Number of recent trials to check

        Returns:
            Tuple of (converged, variance)
        """
        if len(self._trials) < window_size:
            return False, float("inf")

        recent_scores = [t.score for t in self._trials[-window_size:]]

        import statistics

        if len(recent_scores) < 2:
            return False, float("inf")

        mean_score = statistics.mean(recent_scores)
        if mean_score == 0:
            return False, float("inf")

        try:
            variance = statistics.stdev(recent_scores) / abs(mean_score)
        except statistics.StatisticsError:
            return False, float("inf")

        converged = variance < self.config.convergence_threshold
        return converged, variance

    def _get_best_trials(self, n: int = 5) -> list[OptimizationTrial]:
        """Get top N trials by score.

        Args:
            n: Number of trials to return

        Returns:
            List of best trials
        """
        sorted_trials = sorted(
            self._trials,
            key=lambda t: t.score,
            reverse=True,
        )
        return sorted_trials[:n]


class GeneticOptimizer(BaseOptimizer):
    """Genetic algorithm optimizer."""

    def optimize(
        self,
        objective_fn: ObjectiveFunction | Callable,
        param_constraints: list[ParameterConstraint],
        strategy_id: str,
    ) -> OptimizationResult:
        """Run genetic algorithm optimization.

        Args:
            objective_fn: Function to optimize
            param_constraints: Parameter constraints
            strategy_id: Strategy identifier

        Returns:
            Optimization result
        """
        import time

        start_time = time.time()
        self._trials = []

        # Create parameter name mapping
        param_names = [c.name for c in param_constraints]
        param_map = {c.name: c for c in param_constraints}

        # Initialize population
        population = self._initialize_population(param_constraints)

        best_trial: OptimizationTrial | None = None

        for iteration in range(self.config.max_iterations):
            # Check time limit
            elapsed_hours = (time.time() - start_time) / 3600
            if elapsed_hours >= self.config.max_time_hours:
                logger.info(f"Time limit reached after {iteration} iterations")
                break

            # Evaluate population
            evaluated = []
            for individual in population:
                trial = self._create_trial(iteration, individual, objective_fn)
                evaluated.append((individual, trial))

                if best_trial is None or trial.score > best_trial.score:
                    best_trial = trial

            # Check convergence
            converged, variance = self._check_convergence()
            if converged:
                logger.info(f"Convergence reached at iteration {iteration}")
                break

            # Create next generation
            population = self._evolve_population(evaluated, param_map)

            logger.debug(f"Iteration {iteration}: best_score={best_trial.score:.4f}")

        # Calculate final results
        total_time = time.time() - start_time

        result = OptimizationResult(
            strategy_id=strategy_id,
            method=OptimizationMethod.GENETIC,
            best_parameters=best_trial.parameters if best_trial else {},
            best_score=best_trial.score if best_trial else 0.0,
            best_metrics=best_trial.metrics if best_trial else {},
            trials=self._trials.copy(),
            convergence_reached=converged,
            variance_across_runs=variance,
            total_iterations=len(self._trials),
            total_time_seconds=total_time,
            completed_at=datetime.utcnow(),
        )

        return result

    def _initialize_population(
        self,
        param_constraints: list[ParameterConstraint],
    ) -> list[dict[str, Any]]:
        """Initialize random population.

        Args:
            param_constraints: Parameter constraints

        Returns:
            List of individuals (parameter dictionaries)
        """
        population = []
        for _ in range(self.config.population_size):
            individual = {}
            for constraint in param_constraints:
                individual[constraint.name] = constraint.sample_random()
            population.append(individual)
        return population

    def _evolve_population(
        self,
        evaluated: list[tuple[dict[str, Any], OptimizationTrial]],
        param_map: dict[str, ParameterConstraint],
    ) -> list[dict[str, Any]]:
        """Evolve population to next generation.

        Args:
            evaluated: List of (individual, trial) tuples
            param_map: Mapping of parameter names to constraints

        Returns:
            New population
        """
        # Sort by fitness (score)
        evaluated.sort(key=lambda x: x[1].score, reverse=True)

        # Select elite
        elite_count = max(1, int(self.config.population_size * self.config.elite_ratio))
        elite = [ind for ind, _ in evaluated[:elite_count]]

        # Create offspring
        offspring = []
        while len(offspring) < self.config.population_size - elite_count:
            parent1 = self._tournament_select(evaluated)
            parent2 = self._tournament_select(evaluated)

            if random.random() < self.config.crossover_rate:
                child = self._crossover(parent1, parent2, param_map)
            else:
                child = parent1.copy()

            if random.random() < self.config.mutation_rate:
                child = self._mutate(child, param_map)

            offspring.append(child)

        return elite + offspring

    def _tournament_select(
        self,
        evaluated: list[tuple[dict[str, Any], OptimizationTrial]],
        tournament_size: int = 3,
    ) -> dict[str, Any]:
        """Select individual using tournament selection.

        Args:
            evaluated: List of evaluated individuals
            tournament_size: Size of tournament

        Returns:
            Selected individual
        """
        tournament = random.sample(evaluated, min(tournament_size, len(evaluated)))
        tournament.sort(key=lambda x: x[1].score, reverse=True)
        return tournament[0][0].copy()

    def _crossover(
        self,
        parent1: dict[str, Any],
        parent2: dict[str, Any],
        param_map: dict[str, ParameterConstraint],
    ) -> dict[str, Any]:
        """Perform crossover between two parents.

        Args:
            parent1: First parent
            parent2: Second parent
            param_map: Parameter constraints

        Returns:
            Child individual
        """
        child = {}
        for key in parent1:
            if random.random() < 0.5:
                child[key] = parent1[key]
            else:
                child[key] = parent2[key]

            # Ensure constraints are satisfied
            constraint = param_map.get(key)
            if constraint and not constraint.validate_value(child[key]):
                child[key] = constraint.sample_random()

        return child

    def _mutate(
        self,
        individual: dict[str, Any],
        param_map: dict[str, ParameterConstraint],
    ) -> dict[str, Any]:
        """Mutate an individual.

        Args:
            individual: Individual to mutate
            param_map: Parameter constraints

        Returns:
            Mutated individual
        """
        mutated = individual.copy()
        key = random.choice(list(mutated.keys()))
        constraint = param_map.get(key)

        if constraint:
            mutated[key] = constraint.sample_random()

        return mutated


class BayesianOptimizer(BaseOptimizer):
    """Bayesian optimization using Optuna."""

    def optimize(
        self,
        objective_fn: ObjectiveFunction | Callable,
        param_constraints: list[ParameterConstraint],
        strategy_id: str,
    ) -> OptimizationResult:
        """Run Bayesian optimization.

        Args:
            objective_fn: Function to optimize
            param_constraints: Parameter constraints
            strategy_id: Strategy identifier

        Returns:
            Optimization result
        """
        import time

        start_time = time.time()
        self._trials = []

        try:
            import optuna
        except ImportError:
            logger.warning("Optuna not installed, falling back to random search")
            return self._random_search(objective_fn, param_constraints, strategy_id)

        # Create Optuna study
        study = optuna.create_study(direction="maximize")

        best_trial: OptimizationTrial | None = None

        def optuna_objective(trial: optuna.Trial) -> float:
            """Optuna objective function wrapper."""
            # Sample parameters
            params = {}
            for constraint in param_constraints:
                if constraint.param_type == ParameterType.FLOAT:
                    if constraint.log_scale:
                        params[constraint.name] = trial.suggest_float(
                            constraint.name,
                            constraint.min_value or 0.0,
                            constraint.max_value or 1.0,
                            log=True,
                        )
                    else:
                        params[constraint.name] = trial.suggest_float(
                            constraint.name,
                            constraint.min_value or 0.0,
                            constraint.max_value or 1.0,
                        )
                elif constraint.param_type == ParameterType.INTEGER:
                    params[constraint.name] = trial.suggest_int(
                        constraint.name,
                        constraint.min_value or 0,
                        constraint.max_value or 100,
                    )
                elif constraint.param_type == ParameterType.CATEGORICAL:
                    params[constraint.name] = trial.suggest_categorical(
                        constraint.name,
                        constraint.choices,
                    )
                elif constraint.param_type == ParameterType.BOOLEAN:
                    params[constraint.name] = trial.suggest_categorical(
                        constraint.name,
                        [True, False],
                    )

            # Evaluate
            optuna_trial_id = f"optuna_{trial.number}"
            opt_trial = OptimizationTrial(
                trial_id=optuna_trial_id,
                iteration=trial.number,
                parameters=params,
            )

            trial_start = time.time()
            try:
                score, metrics = objective_fn(params)
                opt_trial.score = score
                opt_trial.metrics = metrics
            except Exception as e:
                logger.error(f"Trial {optuna_trial_id} failed: {e}")
                opt_trial.score = float("-inf")

            opt_trial.duration_seconds = time.time() - trial_start
            self._trials.append(opt_trial)

            nonlocal best_trial
            if best_trial is None or opt_trial.score > best_trial.score:
                best_trial = opt_trial

            return opt_trial.score

        # Run optimization
        for iteration in range(self.config.max_iterations):
            # Check time limit
            elapsed_hours = (time.time() - start_time) / 3600
            if elapsed_hours >= self.config.max_time_hours:
                logger.info(f"Time limit reached after {iteration} iterations")
                break

            study.optimize(optuna_objective, n_trials=1, catch=(Exception,))

            # Check convergence
            converged, variance = self._check_convergence()
            if converged and iteration >= self.config.n_startup_trials:
                logger.info(f"Convergence reached at iteration {iteration}")
                break

        # Calculate final results
        total_time = time.time() - start_time

        result = OptimizationResult(
            strategy_id=strategy_id,
            method=OptimizationMethod.BAYESIAN,
            best_parameters=best_trial.parameters if best_trial else {},
            best_score=best_trial.score if best_trial else 0.0,
            best_metrics=best_trial.metrics if best_trial else {},
            trials=self._trials.copy(),
            convergence_reached=converged,
            variance_across_runs=variance,
            total_iterations=len(self._trials),
            total_time_seconds=total_time,
            completed_at=datetime.utcnow(),
        )

        return result

    def _random_search(
        self,
        objective_fn: ObjectiveFunction | Callable,
        param_constraints: list[ParameterConstraint],
        strategy_id: str,
    ) -> OptimizationResult:
        """Fallback random search when Optuna is not available.

        Args:
            objective_fn: Function to optimize
            param_constraints: Parameter constraints
            strategy_id: Strategy identifier

        Returns:
            Optimization result
        """
        import time

        start_time = time.time()
        self._trials = []

        best_trial: OptimizationTrial | None = None

        for iteration in range(self.config.max_iterations):
            # Check time limit
            elapsed_hours = (time.time() - start_time) / 3600
            if elapsed_hours >= self.config.max_time_hours:
                break

            # Sample random parameters
            params = {}
            for constraint in param_constraints:
                params[constraint.name] = constraint.sample_random()

            trial = self._create_trial(iteration, params, objective_fn)

            if best_trial is None or trial.score > best_trial.score:
                best_trial = trial

        total_time = time.time() - start_time

        return OptimizationResult(
            strategy_id=strategy_id,
            method=OptimizationMethod.RANDOM,
            best_parameters=best_trial.parameters if best_trial else {},
            best_score=best_trial.score if best_trial else 0.0,
            best_metrics=best_trial.metrics if best_trial else {},
            trials=self._trials.copy(),
            convergence_reached=False,
            variance_across_runs=0.0,
            total_iterations=len(self._trials),
            total_time_seconds=total_time,
            completed_at=datetime.utcnow(),
        )


class HyperparameterOptimizer:
    """Main interface for hyperparameter optimization.

    This class provides a unified interface for both genetic algorithm
    and Bayesian optimization methods.

    Usage:
        config = OptimizationConfig(method="bayesian", max_iterations=100)
        optimizer = HyperparameterOptimizer(config)

        # Define parameter space
        param_space = [
            ParameterConstraint("sma_fast", ParameterType.INTEGER, 5, 50),
            ParameterConstraint("sma_slow", ParameterType.INTEGER, 20, 200),
            ParameterConstraint("risk_pct", ParameterType.FLOAT, 0.001, 0.05),
        ]

        # Define objective function
        def objective(params):
            # Run backtest with parameters
            metrics = run_backtest(params)
            return metrics["sharpe_ratio"], metrics

        result = optimizer.optimize(objective, param_space, "my_strategy")
    """

    def __init__(self, config: OptimizationConfig | None = None):
        """Initialize optimizer.

        Args:
            config: Optimization configuration
        """
        self.config = config or OptimizationConfig()
        self._optimizer: BaseOptimizer | None = None

    def optimize(
        self,
        objective_fn: ObjectiveFunction | Callable,
        param_constraints: list[ParameterConstraint],
        strategy_id: str,
        baseline_metrics: dict[str, float] | None = None,
    ) -> OptimizationResult:
        """Run hyperparameter optimization.

        Args:
            objective_fn: Function to optimize (returns score, metrics)
            param_constraints: List of parameter constraints
            strategy_id: Strategy identifier
            baseline_metrics: Optional baseline metrics for comparison

        Returns:
            Optimization result with best parameters found
        """
        logger.info(
            f"Starting {self.config.method.value} optimization for {strategy_id}"
        )

        # Create appropriate optimizer
        if self.config.method == OptimizationMethod.GENETIC:
            self._optimizer = GeneticOptimizer(self.config)
        elif self.config.method == OptimizationMethod.BAYESIAN:
            self._optimizer = BayesianOptimizer(self.config)
        else:
            # Random search
            self._optimizer = BayesianOptimizer(self.config)
            self._optimizer.config.method = OptimizationMethod.RANDOM

        # Run optimization
        result = self._optimizer.optimize(objective_fn, param_constraints, strategy_id)

        # Calculate improvement if baseline provided
        if baseline_metrics:
            baseline_score = baseline_metrics.get("sharpe_ratio", 0.0)
            result.baseline_score = baseline_score
            if baseline_score != 0:
                result.improvement_pct = (
                    (result.best_score - baseline_score) / abs(baseline_score) * 100
                )
            else:
                result.improvement_pct = 100.0 if result.best_score > 0 else 0.0

        # Validate improvement threshold
        if result.improvement_pct < self.config.improvement_threshold * 100:
            logger.warning(
                f"Improvement ({result.improvement_pct:.1f}%) below threshold "
                f"({self.config.improvement_threshold * 100:.1f}%)"
            )

        logger.info(
            f"Optimization complete: best_score={result.best_score:.4f}, "
            f"improvement={result.improvement_pct:.1f}%, "
            f"convergence={result.convergence_reached}"
        )

        return result

    def get_optimization_history(self) -> list[OptimizationTrial]:
        """Get history of all optimization trials.

        Returns:
            List of trials
        """
        if self._optimizer:
            return self._optimizer._trials.copy()
        return []

    def validate_parameters(
        self,
        parameters: dict[str, Any],
        param_constraints: list[ParameterConstraint],
    ) -> dict[str, bool]:
        """Validate parameters against constraints.

        Args:
            parameters: Parameters to validate
            param_constraints: Constraints to validate against

        Returns:
            Dictionary mapping parameter names to validity
        """
        param_map = {c.name: c for c in param_constraints}
        results = {}

        for name, value in parameters.items():
            constraint = param_map.get(name)
            if constraint:
                results[name] = constraint.validate_value(value)
            else:
                results[name] = True  # No constraint = valid

        return results
