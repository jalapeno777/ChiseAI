"""
Pattern Library for managing known patterns.

Provides database of known patterns with similarity matching and
historical performance tracking.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.neuro_symbolic.pattern_recognition.engine import PatternType


@dataclass
class PatternTemplate:
    """Template for a known pattern."""

    pattern_id: str
    pattern_type: PatternType
    template_data: np.ndarray
    description: str = ""
    tags: list[str] = field(default_factory=list)
    min_occurrences: int = 5
    confidence_weight: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excludes template_data)."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type.value,
            "description": self.description,
            "tags": self.tags,
            "min_occurrences": self.min_occurrences,
            "confidence_weight": self.confidence_weight,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], template_data: np.ndarray
    ) -> "PatternTemplate":
        """Create from dictionary."""
        return cls(
            pattern_id=data["pattern_id"],
            pattern_type=PatternType(data["pattern_type"]),
            template_data=template_data,
            description=data.get("description", ""),
            tags=data.get("tags", []),
            min_occurrences=data.get("min_occurrences", 5),
            confidence_weight=data.get("confidence_weight", 1.0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )


@dataclass
class PatternOccurrence:
    """Record of a pattern occurrence."""

    occurrence_id: str
    pattern_type: PatternType
    timestamp: str
    data: np.ndarray
    confidence: float
    outcome: str | None = None  # "success", "failure", None
    price_change_pct: float | None = None
    duration_bars: int | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "occurrence_id": self.occurrence_id,
            "pattern_type": self.pattern_type.value,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "outcome": self.outcome,
            "price_change_pct": self.price_change_pct,
            "duration_bars": self.duration_bars,
            "notes": self.notes,
        }


@dataclass
class PatternPerformance:
    """Performance metrics for a pattern type."""

    pattern_type: PatternType
    total_occurrences: int = 0
    successful_occurrences: int = 0
    failed_occurrences: int = 0
    avg_confidence: float = 0.0
    avg_price_change: float = 0.0
    win_rate: float = 0.0
    avg_duration: float = 0.0
    last_occurrence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pattern_type": self.pattern_type.value,
            "total_occurrences": self.total_occurrences,
            "successful_occurrences": self.successful_occurrences,
            "failed_occurrences": self.failed_occurrences,
            "avg_confidence": self.avg_confidence,
            "avg_price_change": self.avg_price_change,
            "win_rate": self.win_rate,
            "avg_duration": self.avg_duration,
            "last_occurrence": self.last_occurrence,
        }

    def update_with_occurrence(self, occurrence: PatternOccurrence) -> None:
        """Update metrics with new occurrence.

        Args:
            occurrence: New pattern occurrence
        """
        self.total_occurrences += 1
        self.last_occurrence = occurrence.timestamp

        # Update running averages
        n = self.total_occurrences
        self.avg_confidence = (
            (self.avg_confidence * (n - 1)) + occurrence.confidence
        ) / n

        if occurrence.price_change_pct is not None:
            self.avg_price_change = (
                (self.avg_price_change * (n - 1)) + occurrence.price_change_pct
            ) / n

        if occurrence.duration_bars is not None:
            self.avg_duration = (
                (self.avg_duration * (n - 1)) + occurrence.duration_bars
            ) / n

        if occurrence.outcome == "success":
            self.successful_occurrences += 1
        elif occurrence.outcome == "failure":
            self.failed_occurrences += 1

        # Update win rate
        total_with_outcome = self.successful_occurrences + self.failed_occurrences
        if total_with_outcome > 0:
            self.win_rate = self.successful_occurrences / total_with_outcome


class PatternLibrary:
    """Database of known patterns with similarity matching and performance tracking.

    Provides:
    - Pattern template storage and retrieval
    - Similarity-based pattern matching
    - Historical performance tracking
    - Pattern occurrence logging
    """

    def __init__(self, storage_path: str | Path | None = None):
        """Initialize pattern library.

        Args:
            storage_path: Optional path for persistent storage
        """
        self.storage_path = Path(storage_path) if storage_path else None

        # In-memory storage
        self._templates: dict[str, PatternTemplate] = {}
        self._occurrences: list[PatternOccurrence] = []
        self._performance: dict[PatternType, PatternPerformance] = {}

        # Initialize default patterns
        self._initialize_default_patterns()

        # Load from storage if available
        if self.storage_path and self.storage_path.exists():
            self.load()

    def _initialize_default_patterns(self) -> None:
        """Initialize library with default pattern templates."""
        default_patterns = {
            PatternType.DOUBLE_TOP: self._create_double_top_template(),
            PatternType.DOUBLE_BOTTOM: self._create_double_bottom_template(),
            PatternType.HEAD_AND_SHOULDERS: self._create_head_shoulders_template(),
            PatternType.ASCENDING_TRIANGLE: self._create_ascending_triangle_template(),
            PatternType.DESCENDING_TRIANGLE: self._create_descending_triangle_template(),
            PatternType.BULL_FLAG: self._create_bull_flag_template(),
            PatternType.BEAR_FLAG: self._create_bear_flag_template(),
            PatternType.CUP_AND_HANDLE: self._create_cup_handle_template(),
        }

        for pattern_type, template_data in default_patterns.items():
            template = PatternTemplate(
                pattern_id=f"default_{pattern_type.value}",
                pattern_type=pattern_type,
                template_data=template_data,
                description=f"Default {pattern_type.value} template",
                tags=["default", "synthetic"],
            )
            self._templates[template.pattern_id] = template

        # Initialize performance tracking
        for pattern_type in PatternType:
            if pattern_type != PatternType.UNKNOWN:
                self._performance[pattern_type] = PatternPerformance(
                    pattern_type=pattern_type
                )

    def _create_double_top_template(self) -> np.ndarray:
        """Create double top template."""
        x = np.linspace(0, 2 * np.pi, 50)
        return (-np.abs(np.sin(x)) + 1) / np.max(np.abs(np.sin(x)))

    def _create_double_bottom_template(self) -> np.ndarray:
        """Create double bottom template."""
        x = np.linspace(0, 2 * np.pi, 50)
        return (np.abs(np.sin(x)) - 1) / np.max(np.abs(np.sin(x)))

    def _create_head_shoulders_template(self) -> np.ndarray:
        """Create head and shoulders template."""
        x = np.linspace(0, 3 * np.pi, 50)
        template = np.sin(x)
        return template / np.max(np.abs(template))

    def _create_ascending_triangle_template(self) -> np.ndarray:
        """Create ascending triangle template."""
        seq_len = 50
        template = np.zeros(seq_len)
        for i in range(seq_len):
            template[i] = 0.3 + (i / seq_len) * 0.4
            if i > seq_len // 2:
                template[i] = min(template[i], 0.7)
        return template / np.max(np.abs(template))

    def _create_descending_triangle_template(self) -> np.ndarray:
        """Create descending triangle template."""
        seq_len = 50
        template = np.zeros(seq_len)
        for i in range(seq_len):
            template[i] = 0.7 - (i / seq_len) * 0.4
            if i > seq_len // 2:
                template[i] = max(template[i], 0.3)
        return template / np.max(np.abs(template))

    def _create_bull_flag_template(self) -> np.ndarray:
        """Create bull flag template."""
        seq_len = 50
        template = np.zeros(seq_len)
        for i in range(seq_len):
            if i < seq_len // 4:
                template[i] = (i / (seq_len // 4)) * 0.8
            else:
                template[i] = 0.8 - (i - seq_len // 4) * 0.01
        return (
            template / np.max(np.abs(template))
            if np.max(np.abs(template)) > 0
            else template
        )

    def _create_bear_flag_template(self) -> np.ndarray:
        """Create bear flag template."""
        seq_len = 50
        template = np.zeros(seq_len)
        for i in range(seq_len):
            if i < seq_len // 4:
                template[i] = 0.8 - (i / (seq_len // 4)) * 0.8
            else:
                template[i] = 0.0 + (i - seq_len // 4) * 0.01
        return (
            template / np.max(np.abs(template))
            if np.max(np.abs(template)) > 0
            else template
        )

    def _create_cup_handle_template(self) -> np.ndarray:
        """Create cup and handle template."""
        seq_len = 50
        template = np.zeros(seq_len)
        for i in range(seq_len):
            if i < seq_len * 0.8:
                x = (i / (seq_len * 0.8)) * np.pi
                template[i] = -np.sin(x) * 0.5 + 0.5
            else:
                handle_pos = (i - seq_len * 0.8) / (seq_len * 0.2)
                template[i] = 0.5 - handle_pos * 0.1
        return (
            template / np.max(np.abs(template))
            if np.max(np.abs(template)) > 0
            else template
        )

    def add_template(self, template: PatternTemplate) -> None:
        """Add a pattern template to the library.

        Args:
            template: Pattern template to add
        """
        self._templates[template.pattern_id] = template

    def get_template(self, pattern_id: str) -> PatternTemplate | None:
        """Get a pattern template by ID.

        Args:
            pattern_id: Template ID

        Returns:
            PatternTemplate or None
        """
        return self._templates.get(pattern_id)

    def get_templates_by_type(self, pattern_type: PatternType) -> list[PatternTemplate]:
        """Get all templates of a specific type.

        Args:
            pattern_type: Pattern type to filter

        Returns:
            List of matching templates
        """
        return [t for t in self._templates.values() if t.pattern_type == pattern_type]

    def list_templates(self) -> list[str]:
        """List all template IDs.

        Returns:
            List of template IDs
        """
        return list(self._templates.keys())

    def find_similar_patterns(
        self,
        data: np.ndarray,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
    ) -> list[tuple[PatternTemplate, float]]:
        """Find patterns similar to the input data.

        Args:
            data: Input data to match
            top_k: Number of top matches to return
            similarity_threshold: Minimum similarity score

        Returns:
            List of (template, similarity) tuples
        """
        if isinstance(data, list):
            data = np.array(data)

        similarities = []

        for template in self._templates.values():
            similarity = self._compute_similarity(data, template.template_data)

            if similarity >= similarity_threshold:
                similarities.append((template, similarity))

        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities[:top_k]

    def _compute_similarity(self, data1: np.ndarray, data2: np.ndarray) -> float:
        """Compute similarity between two data sequences.

        Args:
            data1: First data sequence
            data2: Second data sequence

        Returns:
            Similarity score (0-1)
        """
        # Normalize both sequences
        d1 = np.array(data1).flatten()
        d2 = np.array(data2).flatten()

        # Resample to same length if needed
        if len(d1) != len(d2):
            x1 = np.linspace(0, 1, len(d1))
            x2 = np.linspace(0, 1, len(d2))
            d2 = np.interp(x1, x2, d2)

        # Normalize
        d1 = (d1 - np.mean(d1)) / (np.std(d1) + 1e-8)
        d2 = (d2 - np.mean(d2)) / (np.std(d2) + 1e-8)

        # Pearson correlation
        correlation = np.corrcoef(d1, d2)[0, 1]

        # Convert to 0-1 scale
        return (correlation + 1) / 2

    def log_occurrence(self, occurrence: PatternOccurrence) -> None:
        """Log a pattern occurrence.

        Args:
            occurrence: Pattern occurrence to log
        """
        self._occurrences.append(occurrence)

        # Update performance metrics
        if occurrence.pattern_type in self._performance:
            self._performance[occurrence.pattern_type].update_with_occurrence(
                occurrence
            )

    def get_occurrences(
        self,
        pattern_type: PatternType | None = None,
        limit: int = 100,
    ) -> list[PatternOccurrence]:
        """Get pattern occurrences.

        Args:
            pattern_type: Filter by pattern type
            limit: Maximum number to return

        Returns:
            List of occurrences
        """
        occurrences = self._occurrences

        if pattern_type is not None:
            occurrences = [o for o in occurrences if o.pattern_type == pattern_type]

        return occurrences[-limit:]

    def get_performance(self, pattern_type: PatternType) -> PatternPerformance | None:
        """Get performance metrics for a pattern type.

        Args:
            pattern_type: Pattern type

        Returns:
            PatternPerformance or None
        """
        return self._performance.get(pattern_type)

    def get_all_performance(self) -> dict[PatternType, PatternPerformance]:
        """Get performance metrics for all pattern types.

        Returns:
            Dictionary of pattern type to performance
        """
        return self._performance.copy()

    def get_best_performing_patterns(
        self, min_occurrences: int = 5, top_k: int = 5
    ) -> list[tuple[PatternType, PatternPerformance]]:
        """Get patterns with best historical performance.

        Args:
            min_occurrences: Minimum occurrences to consider
            top_k: Number to return

        Returns:
            List of (pattern_type, performance) tuples
        """
        valid_performance = [
            (pt, perf)
            for pt, perf in self._performance.items()
            if perf.total_occurrences >= min_occurrences
        ]

        # Sort by win rate
        valid_performance.sort(key=lambda x: x[1].win_rate, reverse=True)

        return valid_performance[:top_k]

    def remove_template(self, pattern_id: str) -> bool:
        """Remove a pattern template.

        Args:
            pattern_id: Template ID to remove

        Returns:
            True if removed, False if not found
        """
        if pattern_id in self._templates:
            del self._templates[pattern_id]
            return True
        return False

    def save(self, path: str | Path | None = None) -> None:
        """Save library to disk.

        Args:
            path: Optional override path
        """
        save_path = Path(path) if path else self.storage_path
        if save_path is None:
            return

        save_path.mkdir(parents=True, exist_ok=True)

        # Save templates
        templates_data = {}
        template_arrays = {}

        for pattern_id, template in self._templates.items():
            templates_data[pattern_id] = template.to_dict()
            template_arrays[pattern_id] = template.template_data.tolist()

        with open(save_path / "templates.json", "w") as f:
            json.dump(templates_data, f, indent=2)

        with open(save_path / "template_arrays.json", "w") as f:
            json.dump(template_arrays, f)

        # Save performance
        performance_data = {
            pt.value: perf.to_dict() for pt, perf in self._performance.items()
        }
        with open(save_path / "performance.json", "w") as f:
            json.dump(performance_data, f, indent=2)

        # Save occurrences (last 1000)
        occurrences_data = [occ.to_dict() for occ in self._occurrences[-1000:]]
        with open(save_path / "occurrences.json", "w") as f:
            json.dump(occurrences_data, f, indent=2)

    def load(self, path: str | Path | None = None) -> None:
        """Load library from disk.

        Args:
            path: Optional override path
        """
        load_path = Path(path) if path else self.storage_path
        if load_path is None or not load_path.exists():
            return

        # Load templates
        templates_path = load_path / "templates.json"
        arrays_path = load_path / "template_arrays.json"

        if templates_path.exists() and arrays_path.exists():
            with open(templates_path) as f:
                templates_data = json.load(f)

            with open(arrays_path) as f:
                template_arrays = json.load(f)

            for pattern_id, data in templates_data.items():
                if pattern_id in template_arrays:
                    template = PatternTemplate.from_dict(
                        data, np.array(template_arrays[pattern_id])
                    )
                    self._templates[pattern_id] = template

        # Load performance
        performance_path = load_path / "performance.json"
        if performance_path.exists():
            with open(performance_path) as f:
                performance_data = json.load(f)

            for pattern_value, data in performance_data.items():
                try:
                    pattern_type = PatternType(pattern_value)
                    self._performance[pattern_type] = PatternPerformance(
                        pattern_type=pattern_type,
                        **{k: v for k, v in data.items() if k != "pattern_type"},
                    )
                except ValueError:
                    continue

        # Load occurrences
        occurrences_path = load_path / "occurrences.json"
        if occurrences_path.exists():
            with open(occurrences_path) as f:
                occurrences_data = json.load(f)

            for data in occurrences_data:
                try:
                    occurrence = PatternOccurrence(
                        occurrence_id=data["occurrence_id"],
                        pattern_type=PatternType(data["pattern_type"]),
                        timestamp=data["timestamp"],
                        data=np.array([]),  # Don't store full data
                        confidence=data["confidence"],
                        outcome=data.get("outcome"),
                        price_change_pct=data.get("price_change_pct"),
                        duration_bars=data.get("duration_bars"),
                        notes=data.get("notes", ""),
                    )
                    self._occurrences.append(occurrence)
                except (KeyError, ValueError):
                    continue

    def get_statistics(self) -> dict[str, Any]:
        """Get library statistics.

        Returns:
            Dictionary of statistics
        """
        total_occurrences = len(self._occurrences)
        successful = sum(1 for o in self._occurrences if o.outcome == "success")
        failed = sum(1 for o in self._occurrences if o.outcome == "failure")

        return {
            "total_templates": len(self._templates),
            "total_occurrences": total_occurrences,
            "successful_occurrences": successful,
            "failed_occurrences": failed,
            "patterns_with_data": len(
                [p for p in self._performance.values() if p.total_occurrences > 0]
            ),
        }
