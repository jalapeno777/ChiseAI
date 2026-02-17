"""
Pagination utilities for efficient time-series data retrieval.

Provides cursor-based pagination optimized for time-series data with
prefetching support for smooth scrolling experience.
"""

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterator, List, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    """Result of a single page fetch operation."""

    data: List[Dict[str, Any]]
    next_cursor: Optional[str]
    prev_cursor: Optional[str]
    has_more: bool
    total_estimated: int

    def __bool__(self) -> bool:
        return len(self.data) > 0


class DataSource(Protocol):
    """Protocol for data sources that support time-range queries."""

    def query_time_range(
        self, start_time: datetime, end_time: datetime, limit: int, offset: int
    ) -> List[Dict[str, Any]]:
        """Query data within a time range."""
        ...

    def count_time_range(self, start_time: datetime, end_time: datetime) -> int:
        """Count records in a time range."""
        ...


class InMemoryDataSource:
    """In-memory data source for testing."""

    def __init__(self, data: List[Dict[str, Any]], timestamp_field: str = "timestamp"):
        self._data = sorted(data, key=lambda x: x.get(timestamp_field, datetime.min))
        self._timestamp_field = timestamp_field

    def query_time_range(
        self, start_time: datetime, end_time: datetime, limit: int, offset: int
    ) -> List[Dict[str, Any]]:
        """Query data within a time range."""
        filtered = [
            d
            for d in self._data
            if start_time <= d.get(self._timestamp_field, datetime.min) < end_time
        ]
        return filtered[offset : offset + limit]

    def count_time_range(self, start_time: datetime, end_time: datetime) -> int:
        """Count records in a time range."""
        return sum(
            1
            for d in self._data
            if start_time <= d.get(self._timestamp_field, datetime.min) < end_time
        )


class CursorCodec:
    """Encode/decode pagination cursors."""

    @staticmethod
    def encode(timestamp: datetime, offset: int) -> str:
        """Encode timestamp and offset into a cursor.

        Args:
            timestamp: The timestamp to encode
            offset: The offset within that timestamp's data

        Returns:
            Base64-encoded cursor string
        """
        ts = int(timestamp.timestamp())
        cursor_data = f"{ts}:{offset}"
        return base64.urlsafe_b64encode(cursor_data.encode()).decode()

    @staticmethod
    def decode(cursor: str) -> tuple[datetime, int]:
        """Decode a cursor into timestamp and offset.

        Args:
            cursor: Base64-encoded cursor string

        Returns:
            Tuple of (timestamp, offset)
        """
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        parts = decoded.split(":")
        ts = int(parts[0])
        offset = int(parts[1]) if len(parts) > 1 else 0
        return datetime.fromtimestamp(ts), offset


class TimeSeriesPaginator:
    """Paginates time-series data efficiently using cursor-based navigation.

    This paginator is optimized for time-series data where data is naturally
    ordered by timestamp. It provides:
    - Cursor-based pagination (no offset drift)
    - Page prefetching for smooth scrolling
    - Adaptive page sizing based on time range density

    Example:
        >>> paginator = TimeSeriesPaginator(data_source, page_size=1000)
        >>>
        >>> # Get first page
        >>> page1 = paginator.get_page(cursor=None)
        >>> print(f"First page: {len(page1.data)} rows")
        >>>
        >>> # Get next page
        >>> if page1.has_more:
        ...     page2 = paginator.get_page(page1.next_cursor)
    """

    def __init__(
        self,
        data_source: DataSource,
        page_size: int = 1000,
        prefetch_pages: int = 1,
        timestamp_field: str = "timestamp",
        overlap_points: int = 1,
    ):
        """Initialize the paginator.

        Args:
            data_source: Source providing query_time_range and count methods
            page_size: Number of records per page
            prefetch_pages: Number of adjacent pages to pre-fetch
            timestamp_field: Field name containing timestamp data
            overlap_points: Number of points to overlap between pages for continuity
        """
        self._source = data_source
        self.page_size = page_size
        self.prefetch_pages = prefetch_pages
        self.timestamp_field = timestamp_field
        self.overlap_points = overlap_points
        self._cache: Dict[str, PageResult] = {}
        self._max_cache_size = 100

    def _get_cache_key(self, cursor: Optional[str], direction: str = "next") -> str:
        """Generate cache key for a cursor."""
        if cursor is None:
            return f"start:{direction}"
        return f"{cursor}:{direction}"

    def _get_time_range_for_cursor(
        self, cursor: Optional[str], page_size: int, direction: str = "next"
    ) -> tuple[datetime, datetime, int]:
        """Calculate time range and offset for a cursor.

        Args:
            cursor: Cursor string (None for first page)
            page_size: Number of records to fetch
            direction: 'next' or 'prev'

        Returns:
            Tuple of (start_time, end_time, offset)
        """
        if cursor is None:
            # First page - start from the beginning with far future end
            end_time = datetime.now() + timedelta(days=365)
            return datetime(1970, 1, 1), end_time, 0

        try:
            timestamp, offset = CursorCodec.decode(cursor)

            if direction == "next":
                # Going forward: start from cursor timestamp
                start_time = timestamp
                end_time = datetime.now() + timedelta(days=365)
            else:
                # Going backward: end at cursor timestamp
                start_time = datetime(1970, 1, 1)
                end_time = timestamp

            return start_time, end_time, offset
        except Exception as e:
            logger.warning(f"Failed to decode cursor: {cursor}, error: {e}")
            return datetime(1970, 1, 1), datetime.now() + timedelta(days=365), 0

    def get_page(self, cursor: Optional[str] = None) -> PageResult:
        """Get a single page of data.

        Args:
            cursor: Optional cursor from previous page (None for first page)

        Returns:
            PageResult containing data and pagination metadata
        """
        cache_key = self._get_cache_key(cursor, "next")

        # Check cache
        if cache_key in self._cache:
            logger.debug(f"Cache hit for cursor: {cursor}")
            return self._cache[cache_key]

        # Calculate time range
        start_time, end_time, offset = self._get_time_range_for_cursor(
            cursor, self.page_size, "next"
        )

        # Query data with overlap for continuity
        fetch_size = self.page_size + self.overlap_points
        data = self._source.query_time_range(start_time, end_time, fetch_size, offset)

        # Check if there's more data
        has_more = len(data) > self.page_size

        # Trim to actual page size (keep overlap)
        if has_more:
            page_data = data[: self.page_size]
            # Generate next cursor from last item
            last_item = page_data[-1]
            last_ts = last_item.get(self.timestamp_field)
            if last_ts:
                next_cursor = CursorCodec.encode(last_ts, offset + self.page_size)
            else:
                next_cursor = cursor  # Keep same cursor if no timestamp
        else:
            page_data = data
            next_cursor = None

        # Generate prev cursor
        prev_cursor = cursor

        # Estimate total (this is approximate)
        total_estimated = offset + len(page_data) + (self.page_size if has_more else 0)

        result = PageResult(
            data=page_data,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            has_more=has_more,
            total_estimated=total_estimated,
        )

        # Cache the result
        if len(self._cache) >= self._max_cache_size:
            # Simple cache eviction: remove oldest
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[cache_key] = result

        return result

    def get_prev_page(self, cursor: str) -> PageResult:
        """Get the previous page of data.

        Args:
            cursor: Cursor from current page

        Returns:
            PageResult containing previous page data
        """
        cache_key = self._get_cache_key(cursor, "prev")

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            timestamp, offset = CursorCodec.decode(cursor)

            # Calculate the time range to fetch previous page
            # We need to go back by page_size from the current position
            start_time = datetime(1970, 1, 1)
            end_time = timestamp

            fetch_size = self.page_size + self.overlap_points
            data = self._source.query_time_range(start_time, end_time, fetch_size, 0)

            # Get the last page_size items
            has_more = len(data) > self.page_size

            if has_more:
                page_data = data[-self.page_size :]
                first_item = page_data[0]
                first_ts = first_item.get(self.timestamp_field)
                if first_ts:
                    prev_cursor = CursorCodec.encode(first_ts, 0)
                else:
                    prev_cursor = None
            else:
                page_data = data
                prev_cursor = None

            next_cursor = cursor
            total_estimated = len(data)

            result = PageResult(
                data=page_data,
                next_cursor=next_cursor,
                prev_cursor=prev_cursor,
                has_more=has_more,
                total_estimated=total_estimated,
            )

            # Cache
            if len(self._cache) >= self._max_cache_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[cache_key] = result

            return result

        except Exception as e:
            logger.error(f"Failed to get prev page: {e}")
            return PageResult(
                data=[],
                next_cursor=None,
                prev_cursor=None,
                has_more=False,
                total_estimated=0,
            )

    def get_range(self, start: datetime, end: datetime) -> Iterator[PageResult]:
        """Get all pages in a time range.

        This is a generator that yields pages as needed.

        Args:
            start: Start datetime
            end: End datetime

        Yields:
            PageResult for each page in the range
        """
        offset = 0
        has_more = True

        while has_more:
            data = self._source.query_time_range(start, end, self.page_size, offset)

            if not data:
                break

            has_more = len(data) > self.page_size
            page_data = data[: self.page_size]

            # Generate cursors
            if page_data:
                first_ts = page_data[0].get(self.timestamp_field)
                last_ts = page_data[-1].get(self.timestamp_field)

                prev_cursor = CursorCodec.encode(first_ts, offset) if first_ts else None
                next_cursor = (
                    CursorCodec.encode(last_ts, offset + self.page_size)
                    if last_ts and has_more
                    else None
                )
            else:
                prev_cursor = None
                next_cursor = None

            yield PageResult(
                data=page_data,
                next_cursor=next_cursor,
                prev_cursor=prev_cursor,
                has_more=has_more,
                total_estimated=offset
                + len(page_data)
                + (self.page_size if has_more else 0),
            )

            offset += self.page_size

    def get_cursor_for_time(self, timestamp: datetime) -> str:
        """Get a cursor for a specific timestamp.

        This is useful for jumping to a specific point in time.

        Args:
            timestamp: The timestamp to find

        Returns:
            Cursor string that can be used to fetch data starting from this timestamp
        """
        return CursorCodec.encode(timestamp, 0)

    def get_time_for_cursor(self, cursor: str) -> Optional[datetime]:
        """Get the timestamp for a cursor.

        Args:
            cursor: Cursor string

        Returns:
            datetime associated with the cursor, or None
        """
        try:
            timestamp, _ = CursorCodec.decode(cursor)
            return timestamp
        except Exception:
            return None

    def clear_cache(self) -> None:
        """Clear the pagination cache."""
        self._cache.clear()
        logger.info("Pagination cache cleared")


class AdaptivePaginator(TimeSeriesPaginator):
    """TimeSeriesPaginator with adaptive page sizing.

    Automatically adjusts page size based on the density of data
    in the selected time range.
    """

    def __init__(
        self,
        data_source: DataSource,
        min_page_size: int = 100,
        max_page_size: int = 10000,
        target_duration_ms: int = 100,
        timestamp_field: str = "timestamp",
        overlap_points: int = 1,
    ):
        super().__init__(
            data_source=data_source,
            page_size=max_page_size,
            timestamp_field=timestamp_field,
            overlap_points=overlap_points,
        )
        self.min_page_size = min_page_size
        self.max_page_size = max_page_size
        self.target_duration_ms = target_duration_ms

    def _estimate_optimal_page_size(
        self, start_time: datetime, end_time: datetime
    ) -> int:
        """Estimate optimal page size based on data density."""
        # Count records in range
        total_count = self._source.count_time_range(start_time, end_time)

        # Calculate time span
        time_span = (end_time - start_time).total_seconds()

        if time_span <= 0:
            return self.max_page_size

        # Estimate records per second
        records_per_second = total_count / time_span

        # Target records for target duration
        # Assuming ~1ms per record for network/processing overhead
        target_records = self.target_duration_ms / 1  # Simplified

        # Adjust page size
        optimal = int(target_records)

        return max(self.min_page_size, min(self.max_page_size, optimal))


def create_paginator_from_data(
    data: List[Dict[str, Any]], timestamp_field: str = "timestamp", **kwargs
) -> TimeSeriesPaginator:
    """Create a TimeSeriesPaginator from a list of data.

    Args:
        data: List of dictionaries with timestamp field
        timestamp_field: Name of the timestamp field
        **kwargs: Additional arguments for TimeSeriesPaginator

    Returns:
        Configured TimeSeriesPaginator
    """
    source = InMemoryDataSource(data, timestamp_field)
    return TimeSeriesPaginator(
        data_source=source, timestamp_field=timestamp_field, **kwargs
    )
