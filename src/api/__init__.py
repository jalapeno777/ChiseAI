"""API routers for ChiseAI.

Provides FastAPI routers for various API endpoints including
ECE (Expected Calibration Error) queries, pagination, and lazy loading.
"""

from src.api.ece_router import router as ece_router
from src.api.lazy_loader import (
    AsyncLazyDataLoader,
    LazyDataLoader,
    LazyDataSet,
    PanDirection,
    Resolution,
    TimeRange,
    create_lazy_loader,
)
from src.api.pagination import (
    AdaptivePaginator,
    CursorCodec,
    PageResult,
    TimeSeriesPaginator,
    create_paginator_from_data,
)
from src.api.tracing import (
    get_trace_context,
    get_current_trace_id,
    trace_api_endpoint,
    trace_api_middleware,
)

__all__ = [
    # Pagination
    "AdaptivePaginator",
    "PageResult",
    "CursorCodec",
    "create_paginator_from_data",
    # Lazy loading
    "LazyDataLoader",
    "AsyncLazyDataLoader",
    "LazyDataSet",
    "TimeRange",
    "PanDirection",
    "Resolution",
    "create_lazy_loader",
    # Tracing utilities
    "get_trace_context",
    "get_current_trace_id",
    "trace_api_endpoint",
    "trace_api_middleware",
]
