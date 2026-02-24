"""
Lazy loading module for Grafana dashboard panels.

Provides on-demand data loading with prefetching for smooth scrolling
and zoom/pan interactions.
"""

import asyncio
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from src.api.pagination import TimeSeriesPaginator

logger = logging.getLogger(__name__)


class PanDirection(Enum):
    """Direction of pan movement."""

    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


class Resolution(Enum):
    """Data resolution levels."""

    RAW = "raw"  # Every data point
    MINUTE = "1m"  # 1 minute aggregation
    HOUR = "1h"  # 1 hour aggregation
    DAY = "1d"  # 1 day aggregation
    WEEK = "1w"  # 1 week aggregation

    @property
    def seconds(self) -> int:
        """Get duration in seconds."""
        mapping = {
            "raw": 1,
            "1m": 60,
            "1h": 3600,
            "1d": 86400,
            "1w": 604800,
        }
        return mapping.get(self.value, 3600)


@dataclass
class TimeRange:
    """Represents a time range."""

    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        """Get the duration of the range."""
        return self.end - self.start

    def contains(self, timestamp: datetime) -> bool:
        """Check if a timestamp is within the range."""
        return self.start <= timestamp < self.end

    def overlaps(self, other: "TimeRange") -> bool:
        """Check if this range overlaps with another."""
        return self.start < other.end and other.start < self.end

    def is_adjacent_to(
        self, other: "TimeRange", threshold: timedelta | None = None
    ) -> bool:
        """Check if ranges are adjacent (with optional threshold)."""
        if threshold is None:
            threshold = timedelta(hours=1)

        # Check if other starts where this ends
        if abs(self.end - other.start) <= threshold:
            return True
        # Check if this starts where other ends
        if abs(self.end - other.start) <= threshold:
            return True
        return False

    def expand(self, by: timedelta) -> "TimeRange":
        """Expand the range by a timedelta on both sides."""
        return TimeRange(start=self.start - by, end=self.end + by)


@dataclass
class LazyDataSet:
    """Dataset with lazy loading metadata."""

    visible_data: list[dict[str, Any]]
    prefetched_before: list[dict[str, Any]] = field(default_factory=list)
    prefetched_after: list[dict[str, Any]] = field(default_factory=list)
    loading: bool = False
    complete: bool = False
    resolution: str = "raw"
    time_range: TimeRange | None = None

    @property
    def all_data(self) -> list[dict[str, Any]]:
        """Get all available data including prefetched."""
        return self.prefetched_before + self.visible_data + self.prefetched_after

    @property
    def has_prefetched_before(self) -> bool:
        """Check if there's prefetched data before visible range."""
        return len(self.prefetched_before) > 0

    @property
    def has_prefetched_after(self) -> bool:
        """Check if there's prefetched data after visible range."""
        return len(self.prefetched_after) > 0


class CacheBackend(Protocol):
    """Protocol for cache backends."""

    def get(self, key: str) -> Any | None:
        """Get value from cache."""
        ...

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set value in cache with TTL in seconds."""
        ...

    def delete(self, key: str) -> None:
        """Delete value from cache."""
        ...


class InMemoryCache:
    """Simple in-memory cache implementation."""

    def __init__(self, max_size: int = 100):
        self._cache: dict[str, tuple[Any, float]] = {}
        self._max_size = max_size
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    return value
                else:
                    del self._cache[key]
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                # Remove oldest
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            self._cache[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)


class DataLoader(Protocol):
    """Protocol for data loaders."""

    def load(
        self, start_time: datetime, end_time: datetime, resolution: str
    ) -> list[dict[str, Any]]:
        """Load data for a time range."""
        ...


class TimeSeriesDataLoader:
    """Data loader that uses pagination."""

    def __init__(self, paginator: TimeSeriesPaginator):
        self._paginator = paginator

    def load(
        self, start_time: datetime, end_time: datetime, resolution: str
    ) -> list[dict[str, Any]]:
        """Load all data for a time range."""
        all_data = []

        for page in self._paginator.get_range(start_time, end_time):
            all_data.extend(page.data)

        return all_data


@dataclass
class PrefetchState:
    """Tracks prefetch state for a viewport."""

    before: TimeRange | None = None
    after: TimeRange | None = None
    loading_before: bool = False
    loading_after: bool = False
    last_update: datetime | None = None


class LazyDataLoader:
    """Lazy loads data for Grafana panels with prefetching.

    This loader manages:
    - On-demand loading for current viewport only
    - Prefetching adjacent data for smooth scrolling
    - Cache management for loaded data
    - Memory management by releasing stale data

    Example:
        >>> loader = LazyDataLoader(
        ...     paginator=paginator,
        ...     cache=cache,
        ...     prefetch_margin=timedelta(hours=1)
        ... )
        >>>
        >>> # Load data for current viewport
        >>> data = loader.load_for_viewport(
        ...     start_time=datetime(2024, 1, 1),
        ...     end_time=datetime(2024, 1, 2),
        ...     resolution="1h"
        ... )
        >>>
        >>> # Prefetch adjacent data
        >>> loader.prefetch_adjacent(data.time_range)
    """

    def __init__(
        self,
        paginator: TimeSeriesPaginator,
        cache: CacheBackend | None = None,
        prefetch_margin: timedelta = timedelta(hours=1),
        stale_timeout: timedelta = timedelta(seconds=30),
        max_memory_records: int = 50000,
    ):
        """Initialize the lazy data loader.

        Args:
            paginator: TimeSeriesPaginator for fetching data
            cache: Optional cache backend
            prefetch_margin: Time margin to prefetch beyond viewport
            stale_timeout: Time after which out-of-viewport data is released
            max_memory_records: Maximum records to keep in memory
        """
        self._paginator = paginator
        self._cache = cache or InMemoryCache()
        self._prefetch_margin = prefetch_margin
        self._stale_timeout = stale_timeout
        self._max_memory_records = max_memory_records

        self._current_data: LazyDataSet | None = None
        self._prefetch_state = PrefetchState()
        self._lock = threading.RLock()

        # Background prefetch thread
        self._prefetch_thread: threading.Thread | None = None
        self._prefetch_stop = threading.Event()

    def _make_cache_key(
        self, start_time: datetime, end: datetime, resolution: str
    ) -> str:
        """Generate cache key for a time range."""
        key_data = f"{start_time.isoformat()}:{end.isoformat()}:{resolution}"
        digest = hashlib.sha256(key_data.encode("utf-8")).hexdigest()
        return f"lazy_data:{digest}"

    def load_for_viewport(
        self, start_time: datetime, end_time: datetime, resolution: str = "raw"
    ) -> LazyDataSet:
        """Load data for the current viewport only.

        This method loads only the data needed for the current time range,
        minimizing initial load time and memory usage.

        Args:
            start_time: Start of viewport
            end_time: End of viewport
            resolution: Data resolution (raw, 1m, 1h, 1d)

        Returns:
            LazyDataSet with visible data
        """
        with self._lock:
            time_range = TimeRange(start=start_time, end=end_time)

            # Check cache first
            cache_key = self._make_cache_key(start_time, end_time, resolution)
            cached = self._cache.get(cache_key)

            if cached is not None:
                logger.debug(f"Cache hit for viewport: {start_time} - {end_time}")
                # cached is known to be LazyDataSet from cache population
                self._current_data = cached
                return cached  # type: ignore[no-any-return]

            # Load data for viewport
            logger.info(f"Loading viewport data: {start_time} - {end_time}")
            data = self._paginator.get_range(start_time, end_time)

            # Collect all data from pages
            all_records = []
            for page in data:
                all_records.extend(page.data)

            # Create lazy dataset
            lazy_data = LazyDataSet(
                visible_data=all_records,
                loading=False,
                complete=True,
                resolution=resolution,
                time_range=time_range,
            )

            # Cache it
            self._cache.set(cache_key, lazy_data)
            self._current_data = lazy_data

            # Start background prefetch
            self._trigger_prefetch(time_range)

            return lazy_data

    def prefetch_adjacent(self, current_range: TimeRange) -> LazyDataSet:
        """Pre-fetch data just outside the current viewport.

        This enables smooth scrolling by loading data before/after
        the current view before the user scrolls there.

        Args:
            current_range: Current viewport time range

        Returns:
            Updated LazyDataSet with prefetched data
        """
        with self._lock:
            if self._current_data is None:
                return LazyDataSet(visible_data=[], loading=False, complete=False)

            # Calculate adjacent ranges
            margin = self._prefetch_margin
            before_range = TimeRange(
                start=current_range.start - margin, end=current_range.start
            )
            after_range = TimeRange(
                start=current_range.end, end=current_range.end + margin
            )

            # Prefetch before
            if not self._prefetch_state.loading_before:
                self._prefetch_state.loading_before = True
                before_data = self._load_range(before_range)
                self._current_data.prefetched_before = before_data
                self._prefetch_state.loading_before = False
                self._prefetch_state.before = before_range

            # Prefetch after
            if not self._prefetch_state.loading_after:
                self._prefetch_state.loading_after = True
                after_data = self._load_range(after_range)
                self._current_data.prefetched_after = after_data
                self._prefetch_state.loading_after = False
                self._prefetch_state.after = after_range

            self._prefetch_state.last_update = datetime.now()

            return self._current_data

    def _load_range(self, time_range: TimeRange) -> list[dict[str, Any]]:
        """Load data for a time range."""
        cache_key = self._make_cache_key(time_range.start, time_range.end, "raw")

        cached = self._cache.get(cache_key)
        if cached is not None:
            if isinstance(cached, list):
                return cached
            if isinstance(cached, LazyDataSet):
                return cached.visible_data

        # Load from paginator
        data = []
        for page in self._paginator.get_range(time_range.start, time_range.end):
            data.extend(page.data)

        # Cache the result
        self._cache.set(cache_key, data)

        return data

    def _trigger_prefetch(self, current_range: TimeRange) -> None:
        """Trigger background prefetch."""
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            return

        def prefetch_worker() -> None:
            try:
                self.prefetch_adjacent(current_range)
            except Exception as e:
                logger.error(f"Prefetch failed: {e}")

        self._prefetch_thread = threading.Thread(target=prefetch_worker, daemon=True)
        self._prefetch_thread.start()

    def on_zoom(self, new_range: TimeRange) -> LazyDataSet:
        """Handle zoom events.

        When user zooms in/out, load data for the new range.

        Args:
            new_range: New viewport after zoom

        Returns:
            New LazyDataSet for the zoomed view
        """
        with self._lock:
            logger.info(f"Zoom event: {new_range.start} - {new_range.end}")

            # Check if we have prefetched data for this range
            if self._current_data:
                # Check if new range is within prefetched data
                TimeRange(
                    start=new_range.start - self._prefetch_margin,
                    end=new_range.end + self._prefetch_margin,
                )

                # Use prefetched data if available
                all_data = self._current_data.all_data
                if all_data:
                    # Filter to new range
                    visible = [
                        d
                        for d in all_data
                        if new_range.contains(d.get("timestamp", datetime.min))
                    ]

                    if len(visible) >= len(all_data) * 0.5:  # Reasonable hit rate
                        lazy_data = LazyDataSet(
                            visible_data=visible,
                            prefetched_before=self._current_data.prefetched_before,
                            prefetched_after=self._current_data.prefetched_after,
                            resolution=self._current_data.resolution,
                            time_range=new_range,
                        )
                        self._current_data = lazy_data
                        return lazy_data

            # Load fresh data for new range
            return self.load_for_viewport(
                new_range.start,
                new_range.end,
                self._current_data.resolution if self._current_data else "raw",
            )

    def on_pan(self, direction: PanDirection) -> LazyDataSet:
        """Handle pan events.

        When user pans left/right/up/down, shift the viewport
        and use prefetched data where available.

        Args:
            direction: Pan direction

        Returns:
            Updated LazyDataSet
        """
        with self._lock:
            if self._current_data is None or self._current_data.time_range is None:
                return LazyDataSet(visible_data=[], loading=False, complete=False)

            current = self._current_data.time_range
            duration = current.duration

            # Calculate new range based on direction
            if direction == PanDirection.LEFT:
                new_start = current.start - duration
                new_end = current.start
            elif direction == PanDirection.RIGHT:
                new_start = current.end
                new_end = current.end + duration
            else:
                # Vertical pans not fully supported yet
                logger.warning(f"Vertical pan not fully supported: {direction}")
                return self._current_data

            new_range = TimeRange(start=new_start, end=new_end)

            # Check prefetched data
            prefetched = (
                self._current_data.prefetched_before
                + self._current_data.visible_data
                + self._current_data.prefetched_after
            )

            if prefetched and len(prefetched) > 0:
                # Try to use prefetched data
                visible = prefetched  # Use all prefetched as visible

                lazy_data = LazyDataSet(
                    visible_data=visible[: self._max_memory_records],
                    resolution=self._current_data.resolution,
                    time_range=new_range,
                )

                self._current_data = lazy_data

                # Trigger new prefetch
                self._trigger_prefetch(new_range)

                return lazy_data

            # Load fresh data
            return self.load_for_viewport(
                new_start, new_end, self._current_data.resolution
            )

    def get_current_data(self) -> LazyDataSet | None:
        """Get the current lazy dataset."""
        with self._lock:
            return self._current_data

    def release_stale_data(self) -> None:
        """Release data that's outside the viewport and stale."""
        with self._lock:
            if self._current_data is None:
                return

            # Check if data is stale
            if self._prefetch_state.last_update:
                age = datetime.now() - self._prefetch_state.last_update
                if age > self._stale_timeout:
                    # Clear prefetched data
                    self._current_data.prefetched_before = []
                    self._current_data.prefetched_after = []
                    logger.debug("Released stale prefetched data")

    def clear_cache(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._current_data = None
            self._prefetch_state = PrefetchState()
            logger.info("Lazy loader cache cleared")


class AsyncLazyDataLoader:
    """Async version of LazyDataLoader for use with async frameworks."""

    def __init__(
        self,
        paginator: TimeSeriesPaginator,
        cache: CacheBackend | None = None,
        prefetch_margin: timedelta = timedelta(hours=1),
        **kwargs: Any,
    ) -> None:
        self._sync_loader = LazyDataLoader(
            paginator=paginator, cache=cache, prefetch_margin=prefetch_margin, **kwargs
        )
        self._executor = asyncio.get_event_loop()

    async def load_for_viewport(
        self, start_time: datetime, end_time: datetime, resolution: str = "raw"
    ) -> LazyDataSet:
        """Load data for viewport (async)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._sync_loader.load_for_viewport, start_time, end_time, resolution
        )

    async def prefetch_adjacent(self, current_range: TimeRange) -> LazyDataSet:
        """Pre-fetch adjacent data (async)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._sync_loader.prefetch_adjacent, current_range
        )

    async def on_zoom(self, new_range: TimeRange) -> LazyDataSet:
        """Handle zoom event (async)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_loader.on_zoom, new_range)

    async def on_pan(self, direction: PanDirection) -> LazyDataSet:
        """Handle pan event (async)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_loader.on_pan, direction)

    def get_current_data(self) -> LazyDataSet | None:
        """Get current data."""
        return self._sync_loader.get_current_data()

    def release_stale_data(self) -> None:
        """Release stale data."""
        self._sync_loader.release_stale_data()

    def clear_cache(self) -> None:
        """Clear cache."""
        self._sync_loader.clear_cache()


def create_lazy_loader(
    data: list[dict[str, Any]],
    timestamp_field: str = "timestamp",
    page_size: int = 1000,
    **kwargs: Any,
) -> LazyDataLoader:
    """Create a LazyDataLoader from a list of data.

    Args:
        data: List of dictionaries with timestamp field
        timestamp_field: Name of the timestamp field
        page_size: Number of records per page
        **kwargs: Additional arguments for LazyDataLoader

    Returns:
        Configured LazyDataLoader
    """
    from src.api.pagination import create_paginator_from_data

    paginator = create_paginator_from_data(data, timestamp_field, page_size=page_size)
    cache = InMemoryCache()

    return LazyDataLoader(paginator=paginator, cache=cache, **kwargs)
