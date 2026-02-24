"""
Pattern Inference for real-time pattern detection.

Provides real-time pattern detection with confidence scoring and classification.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Callable, Tuple
from collections import deque
import numpy as np
import time

from src.neuro_symbolic.pattern_recognition.engine import (
    PatternRecognitionEngine,
    PatternMatch,
    PatternType,
    PatternRecognitionConfig,
)


@dataclass
class InferenceConfig:
    """Configuration for pattern inference."""

    buffer_size: int = 200
    min_confidence: float = 0.6
    smoothing_alpha: float = 0.3
    batch_size: int = 1
    max_latency_ms: float = 100.0
    enable_caching: bool = True
    cache_ttl_seconds: int = 60


@dataclass
class InferenceResult:
    """Result from pattern inference."""

    pattern_type: PatternType
    confidence: float
    timestamp: float
    inference_time_ms: float
    features: Dict[str, float] = field(default_factory=dict)
    probabilities: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pattern_type": self.pattern_type.value,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "inference_time_ms": self.inference_time_ms,
            "features": self.features,
            "probabilities": self.probabilities,
            "metadata": self.metadata,
        }


class PatternInference:
    """Real-time pattern detection and inference.

    Provides efficient pattern detection with confidence scoring,
    caching, and streaming capabilities.
    """

    def __init__(
        self,
        engine: Optional[PatternRecognitionEngine] = None,
        config: Optional[InferenceConfig] = None,
    ):
        """Initialize pattern inference.

        Args:
            engine: Pattern recognition engine
            config: Inference configuration
        """
        self.engine = engine or PatternRecognitionEngine()
        self.config = config or InferenceConfig()

        # Data buffer for streaming
        self._buffer: deque = deque(maxlen=self.config.buffer_size)

        # Cache for results
        self._cache: Dict[str, InferenceResult] = {}
        self._cache_timestamps: Dict[str, float] = {}

        # Smoothing state
        self._smoothed_probabilities: Optional[Dict[str, float]] = None

        # Performance metrics
        self._inference_times: deque = deque(maxlen=100)
        self._total_inferences = 0

    def add_data_point(self, value: float, timestamp: Optional[float] = None) -> None:
        """Add a single data point to the buffer.

        Args:
            value: Data value
            timestamp: Optional timestamp (uses current time if None)
        """
        ts = timestamp if timestamp is not None else time.time()
        self._buffer.append((ts, value))

    def add_batch(
        self, values: List[float], timestamps: Optional[List[float]] = None
    ) -> None:
        """Add a batch of data points.

        Args:
            values: List of data values
            timestamps: Optional list of timestamps
        """
        if timestamps is None:
            timestamps = [time.time()] * len(values)

        for ts, val in zip(timestamps, values):
            self.add_data_point(val, ts)

    def get_buffer_data(self) -> np.ndarray:
        """Get data from buffer as numpy array.

        Returns:
            Array of values from buffer
        """
        if not self._buffer:
            return np.array([])
        return np.array([v for _, v in self._buffer])

    def detect(
        self,
        data: Optional[Union[List[float], np.ndarray]] = None,
        use_buffer: bool = False,
    ) -> Optional[InferenceResult]:
        """Detect patterns in data.

        Args:
            data: Data to analyze (uses buffer if None and use_buffer=True)
            use_buffer: Use buffered data

        Returns:
            InferenceResult or None if no pattern detected
        """
        start_time = time.time()

        # Get data
        if data is None:
            if use_buffer:
                data = self.get_buffer_data()
            else:
                return None

        if len(data) < self.engine.config.sequence_length:
            return None

        # Check cache
        if self.config.enable_caching:
            cache_key = self._compute_cache_key(data)
            cached = self._get_cached_result(cache_key)
            if cached is not None:
                return cached

        # Run inference
        pattern_match = self.engine.detect_patterns(data)

        if pattern_match is None:
            return None

        # Get probabilities
        probabilities = self.engine.get_pattern_probabilities(data)

        # Apply smoothing
        probabilities = self._smooth_probabilities(probabilities)

        # Compute features
        features = self.engine.compute_features(data)

        # Compute inference time
        inference_time_ms = (time.time() - start_time) * 1000
        self._inference_times.append(inference_time_ms)
        self._total_inferences += 1

        result = InferenceResult(
            pattern_type=pattern_match.pattern_type,
            confidence=pattern_match.confidence,
            timestamp=time.time(),
            inference_time_ms=inference_time_ms,
            features=features,
            probabilities=probabilities,
            metadata={
                "buffer_size": len(self._buffer),
                "data_length": len(data),
            },
        )

        # Cache result
        if self.config.enable_caching:
            self._cache_result(cache_key, result)

        return result

    def detect_all(
        self,
        data: Optional[Union[List[float], np.ndarray]] = None,
        min_confidence: Optional[float] = None,
    ) -> List[InferenceResult]:
        """Detect all patterns above confidence threshold.

        Args:
            data: Data to analyze
            min_confidence: Override minimum confidence

        Returns:
            List of InferenceResult objects
        """
        min_conf = min_confidence or self.config.min_confidence

        if data is None:
            data = self.get_buffer_data()

        if len(data) < self.engine.config.sequence_length:
            return []

        # Get all pattern matches
        matches = self.engine.detect_patterns(data, return_all=True)

        if matches is None:
            return []

        # Filter by confidence
        results = []
        probabilities = self.engine.get_pattern_probabilities(data)
        features = self.engine.compute_features(data)

        for match in matches:
            if match.confidence >= min_conf:
                results.append(
                    InferenceResult(
                        pattern_type=match.pattern_type,
                        confidence=match.confidence,
                        timestamp=time.time(),
                        inference_time_ms=0.0,
                        features=features,
                        probabilities=probabilities,
                    )
                )

        return results

    def stream_detect(
        self,
        data_stream: Any,
        callback: Callable[[InferenceResult], None],
        interval: float = 1.0,
    ) -> None:
        """Stream pattern detection from data source.

        Args:
            data_stream: Iterable data source
            callback: Callback for each detection
            interval: Detection interval in seconds
        """
        last_detection = time.time()

        for value in data_stream:
            self.add_data_point(float(value))

            current_time = time.time()
            if current_time - last_detection >= interval:
                result = self.detect(use_buffer=True)
                if (
                    result is not None
                    and result.confidence >= self.config.min_confidence
                ):
                    callback(result)
                last_detection = current_time

    def get_confidence_score(
        self, data: Union[List[float], np.ndarray], pattern_type: PatternType
    ) -> float:
        """Get confidence score for a specific pattern type.

        Args:
            data: Data to analyze
            pattern_type: Pattern type to score

        Returns:
            Confidence score for the pattern
        """
        probabilities = self.engine.get_pattern_probabilities(data)
        return probabilities.get(pattern_type.value, 0.0)

    def classify_pattern(
        self, data: Union[List[float], np.ndarray]
    ) -> Tuple[PatternType, float]:
        """Classify the most likely pattern in data.

        Args:
            data: Data to classify

        Returns:
            Tuple of (pattern_type, confidence)
        """
        probabilities = self.engine.get_pattern_probabilities(data)

        if not probabilities:
            return PatternType.UNKNOWN, 0.0

        best_pattern = max(probabilities.items(), key=lambda x: x[1])

        try:
            pattern_type = PatternType(best_pattern[0])
        except ValueError:
            pattern_type = PatternType.UNKNOWN

        return pattern_type, best_pattern[1]

    def _smooth_probabilities(
        self, probabilities: Dict[str, float]
    ) -> Dict[str, float]:
        """Apply exponential smoothing to probabilities.

        Args:
            probabilities: Raw probabilities

        Returns:
            Smoothed probabilities
        """
        if self._smoothed_probabilities is None:
            self._smoothed_probabilities = probabilities.copy()
            return probabilities

        alpha = self.config.smoothing_alpha
        smoothed = {}

        for pattern, prob in probabilities.items():
            prev = self._smoothed_probabilities.get(pattern, prob)
            smoothed[pattern] = alpha * prob + (1 - alpha) * prev

        self._smoothed_probabilities = smoothed
        return smoothed

    def _compute_cache_key(self, data: Union[List[float], np.ndarray]) -> str:
        """Compute cache key for data.

        Args:
            data: Data array

        Returns:
            Cache key string
        """
        if isinstance(data, list):
            data = np.array(data)

        # Use hash of last N values for cache key
        key_data = data[-20:] if len(data) > 20 else data
        return f"pattern_{hash(key_data.tobytes())}"

    def _get_cached_result(self, cache_key: str) -> Optional[InferenceResult]:
        """Get cached result if valid.

        Args:
            cache_key: Cache key

        Returns:
            Cached InferenceResult or None
        """
        if cache_key not in self._cache:
            return None

        timestamp = self._cache_timestamps.get(cache_key, 0)
        if time.time() - timestamp > self.config.cache_ttl_seconds:
            del self._cache[cache_key]
            del self._cache_timestamps[cache_key]
            return None

        return self._cache[cache_key]

    def _cache_result(self, cache_key: str, result: InferenceResult) -> None:
        """Cache inference result.

        Args:
            cache_key: Cache key
            result: Result to cache
        """
        self._cache[cache_key] = result
        self._cache_timestamps[cache_key] = time.time()

        # Clean old cache entries
        if len(self._cache) > 1000:
            current_time = time.time()
            keys_to_remove = [
                k
                for k, ts in self._cache_timestamps.items()
                if current_time - ts > self.config.cache_ttl_seconds
            ]
            for k in keys_to_remove:
                del self._cache[k]
                del self._cache_timestamps[k]

    def get_performance_metrics(self) -> Dict[str, float]:
        """Get inference performance metrics.

        Returns:
            Dictionary of performance metrics
        """
        if not self._inference_times:
            return {
                "avg_inference_time_ms": 0.0,
                "max_inference_time_ms": 0.0,
                "p95_inference_time_ms": 0.0,
                "total_inferences": 0,
            }

        times = list(self._inference_times)
        return {
            "avg_inference_time_ms": np.mean(times),
            "max_inference_time_ms": np.max(times),
            "p95_inference_time_ms": np.percentile(times, 95),
            "total_inferences": self._total_inferences,
        }

    def reset(self) -> None:
        """Reset inference state."""
        self._buffer.clear()
        self._cache.clear()
        self._cache_timestamps.clear()
        self._smoothed_probabilities = None
        self._inference_times.clear()
        self._total_inferences = 0

    def set_engine(self, engine: PatternRecognitionEngine) -> None:
        """Set the pattern recognition engine.

        Args:
            engine: New engine to use
        """
        self.engine = engine
        self.reset()
