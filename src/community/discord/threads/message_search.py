"""Message search functionality for Discord community."""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SearchSortOrder(Enum):
    """Sort order for search results."""

    RELEVANCE = "relevance"
    DATE_NEWEST = "date_newest"
    DATE_OLDEST = "date_oldest"


@dataclass
class SearchResult:
    """A single search result."""

    message_id: str
    channel_id: str
    thread_id: str | None
    author_id: str
    author_name: str
    content: str
    timestamp: datetime
    relevance_score: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "thread_id": self.thread_id,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "relevance_score": self.relevance_score,
            "matched_keywords": self.matched_keywords,
        }


@dataclass
class SearchResponse:
    """Response from a search query."""

    results: list[SearchResult]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    query: str
    filters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "results": [r.to_dict() for r in self.results],
            "total_count": self.total_count,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "query": self.query,
            "filters": self.filters,
        }


class MessageSearcher:
    """Search messages in Discord channels and threads.

    Supports searching by keyword, user, date range, and within specific
    threads or channels. Results are ranked by relevance and paginated.
    """

    def __init__(
        self,
        redis_client: Any = None,
        default_page_size: int = 25,
        max_page_size: int = 100,
    ):
        """Initialize MessageSearcher.

        Args:
            redis_client: Redis client for storing search index
            default_page_size: Default number of results per page
            max_page_size: Maximum results per page
        """
        self._redis = redis_client
        self._default_page_size = default_page_size
        self._max_page_size = max_page_size
        self._message_cache: dict[str, dict[str, Any]] = {}

    def _get_message_key(self, channel_id: str, message_id: str) -> str:
        """Get Redis key for a message."""
        return f"community:discord:message:{channel_id}:{message_id}"

    def _get_channel_messages_key(self, channel_id: str) -> str:
        """Get Redis key for channel's message index."""
        return f"community:discord:channel:{channel_id}:messages"

    def _get_user_messages_key(self, user_id: str) -> str:
        """Get Redis key for user's messages index."""
        return f"community:discord:user:{user_id}:messages"

    def _calculate_relevance(
        self,
        content: str,
        keywords: list[str],
        author_id: str | None = None,
        target_author: str | None = None,
    ) -> float:
        """Calculate relevance score for a message.

        Args:
            content: Message content
            keywords: Search keywords
            author_id: Message author ID
            target_author: Target author filter

        Returns:
            Relevance score (0.0 to 1.0)
        """
        if not keywords and not target_author:
            return 1.0

        score = 0.0
        content_lower = content.lower()

        # Author match is high relevance
        if target_author and author_id == target_author:
            score += 0.5

        # Keyword matches
        if keywords:
            matched = 0
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in content_lower:
                    matched += 1
                    # Exact match bonus
                    if re.search(rf"\b{re.escape(keyword_lower)}\b", content_lower):
                        score += 0.2
                    else:
                        score += 0.1

            if keywords:
                score += (matched / len(keywords)) * 0.4

        return min(score, 1.0)

    def _matches_filters(
        self,
        message: dict[str, Any],
        filters: dict[str, Any],
    ) -> bool:
        """Check if message matches all filters.

        Args:
            message: Message data
            filters: Filter criteria

        Returns:
            True if message matches all filters
        """
        # Date range filter
        if "start_date" in filters or "end_date" in filters:
            msg_time = message.get("timestamp")
            if msg_time:
                if isinstance(msg_time, str):
                    msg_time = datetime.fromisoformat(msg_time)
                if "start_date" in filters:
                    start = filters["start_date"]
                    if isinstance(start, str):
                        start = datetime.fromisoformat(start)
                    if msg_time < start:
                        return False
                if "end_date" in filters:
                    end = filters["end_date"]
                    if isinstance(end, str):
                        end = datetime.fromisoformat(end)
                    if msg_time > end:
                        return False

        # Author filter
        if "author_id" in filters:
            if message.get("author_id") != filters["author_id"]:
                return False

        # Channel filter
        if "channel_id" in filters:
            if message.get("channel_id") != filters["channel_id"]:
                return False

        # Thread filter
        if "thread_id" in filters:
            if message.get("thread_id") != filters["thread_id"]:
                return False

        # Has link filter
        if filters.get("has_link") is not None:
            has_link = bool(re.search(r"https?://", message.get("content", "")))
            if has_link != filters["has_link"]:
                return False

        return True

    async def index_message(
        self,
        message_id: str,
        channel_id: str,
        author_id: str,
        author_name: str,
        content: str,
        thread_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Index a message for searching.

        Args:
            message_id: Discord message ID
            channel_id: Discord channel ID
            author_id: Discord user ID
            author_name: Discord username
            content: Message content
            thread_id: Thread ID if message is in a thread
            timestamp: Message timestamp
        """
        import json

        if timestamp is None:
            timestamp = datetime.now()

        message_data = {
            "message_id": message_id,
            "channel_id": channel_id,
            "author_id": author_id,
            "author_name": author_name,
            "content": content,
            "thread_id": thread_id,
            "timestamp": timestamp.isoformat(),
        }

        # Cache locally
        cache_key = f"{channel_id}:{message_id}"
        self._message_cache[cache_key] = message_data

        # Store in Redis if available
        if self._redis:
            try:
                from tools.redis_state import redis_state_set

                key = self._get_message_key(channel_id, message_id)
                redis_state_set(key, json.dumps(message_data))

                # Add to channel index
                self._get_channel_messages_key(channel_id)
                # Store as sorted set with timestamp as score
                # Note: In real implementation, would use redis_state_zadd
            except Exception as e:
                logger.warning(f"Failed to index message in Redis: {e}")

    async def search(
        self,
        query: str,
        keywords: list[str] | None = None,
        author_id: str | None = None,
        channel_id: str | None = None,
        thread_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        has_link: bool | None = None,
        sort_order: SearchSortOrder = SearchSortOrder.RELEVANCE,
        page: int = 1,
        page_size: int | None = None,
    ) -> SearchResponse:
        """Search messages.

        Args:
            query: Search query string
            keywords: List of keywords to search for
            author_id: Filter by author Discord ID
            channel_id: Filter by channel Discord ID
            thread_id: Filter by thread Discord ID
            start_date: Filter messages after this date
            end_date: Filter messages before this date
            has_link: Filter for messages with/without links
            sort_order: How to sort results
            page: Page number (1-indexed)
            page_size: Results per page

        Returns:
            SearchResponse with paginated results
        """
        if keywords is None:
            keywords = []

        # Parse keywords from query if not provided
        if keywords and not query:
            query = " ".join(keywords)
        elif not keywords and query:
            # Split query into keywords
            keywords = query.split()

        page_size = min(page_size or self._default_page_size, self._max_page_size)
        offset = (page - 1) * page_size

        filters = {
            "author_id": author_id,
            "channel_id": channel_id,
            "thread_id": thread_id,
            "start_date": start_date,
            "end_date": end_date,
            "has_link": has_link,
        }

        # Search in cache first
        results: list[SearchResult] = []

        for _cache_key, message in self._message_cache.items():
            if not self._matches_filters(message, filters):
                continue

            # Calculate relevance
            relevance = self._calculate_relevance(
                content=message.get("content", ""),
                keywords=keywords,
                author_id=message.get("author_id"),
                target_author=author_id,
            )

            if relevance > 0:
                timestamp = message.get("timestamp")
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp)

                matched_kw = [
                    kw
                    for kw in keywords
                    if kw.lower() in message.get("content", "").lower()
                ]

                result = SearchResult(
                    message_id=message["message_id"],
                    channel_id=message["channel_id"],
                    thread_id=message.get("thread_id"),
                    author_id=message["author_id"],
                    author_name=message["author_name"],
                    content=message["content"],
                    timestamp=timestamp or datetime.now(),
                    relevance_score=relevance,
                    matched_keywords=matched_kw,
                )
                results.append(result)

        # Search in Redis if available
        if self._redis:
            try:
                import json

                from tools.redis_state import redis_state_get, redis_state_scan_keys

                pattern = "community:discord:message:*"
                keys = redis_state_scan_keys(pattern, count=1000)

                for key in keys:
                    # Parse channel and message ID from key
                    parts = key.split(":")
                    if len(parts) >= 4:
                        ch_id = parts[3]
                        parts[4] if len(parts) > 4 else ""  # msg_id for future use

                        # Apply channel filter
                        if channel_id and ch_id != channel_id:
                            continue

                        data = redis_state_get(key)
                        if data:
                            message = json.loads(data)

                            if not self._matches_filters(message, filters):
                                continue

                            relevance = self._calculate_relevance(
                                content=message.get("content", ""),
                                keywords=keywords,
                                author_id=message.get("author_id"),
                                target_author=author_id,
                            )

                            if relevance > 0:
                                timestamp = message.get("timestamp")
                                if isinstance(timestamp, str):
                                    timestamp = datetime.fromisoformat(timestamp)

                                matched_kw = [
                                    kw
                                    for kw in keywords
                                    if kw.lower() in message.get("content", "").lower()
                                ]

                                result = SearchResult(
                                    message_id=message["message_id"],
                                    channel_id=message["channel_id"],
                                    thread_id=message.get("thread_id"),
                                    author_id=message["author_id"],
                                    author_name=message["author_name"],
                                    content=message["content"],
                                    timestamp=timestamp or datetime.now(),
                                    relevance_score=relevance,
                                    matched_keywords=matched_kw,
                                )
                                results.append(result)

            except Exception as e:
                logger.warning(f"Failed to search in Redis: {e}")

        # Sort results
        if sort_order == SearchSortOrder.DATE_NEWEST:
            results.sort(key=lambda x: x.timestamp, reverse=True)
        elif sort_order == SearchSortOrder.DATE_OLDEST:
            results.sort(key=lambda x: x.timestamp)
        else:
            results.sort(key=lambda x: x.relevance_score, reverse=True)

        total_count = len(results)
        total_pages = (total_count + page_size - 1) // page_size

        # Paginate
        paginated_results = results[offset : offset + page_size]

        return SearchResponse(
            results=paginated_results,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            query=query,
            filters=filters,
        )

    async def export_results(
        self,
        response: SearchResponse,
        format: str = "json",
    ) -> str:
        """Export search results.

        Args:
            response: SearchResponse to export
            format: Export format ('json' or 'csv')

        Returns:
            Exported data as string
        """
        if format == "json":
            import json

            return json.dumps(response.to_dict(), indent=2)
        elif format == "csv":
            lines = [
                "message_id,channel_id,thread_id,author_id,author_name,content,timestamp,relevance"
            ]

            for result in response.results:
                # Escape content for CSV
                content = result.content.replace('"', '""')
                lines.append(
                    f"{result.message_id},{result.channel_id},"
                    f"{result.thread_id or ''},{result.author_id},"
                    f'"{result.author_name}","{content}",'
                    f"{result.timestamp.isoformat()},{result.relevance_score}"
                )

            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Remove a message from search index.

        Args:
            channel_id: Discord channel ID
            message_id: Discord message ID

        Returns:
            True if deleted successfully
        """
        cache_key = f"{channel_id}:{message_id}"

        if cache_key in self._message_cache:
            del self._message_cache[cache_key]

        if self._redis:
            try:
                from tools.redis_state import redis_state_delete

                key = self._get_message_key(channel_id, message_id)
                redis_state_delete(key)
            except Exception as e:
                logger.warning(f"Failed to delete message from Redis: {e}")
                return False

        return True
