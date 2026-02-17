"""API routers for ChiseAI.

Provides FastAPI routers for various API endpoints including
ECE (Expected Calibration Error) queries, pagination, and lazy loading.
"""

from src.api.ece_router import router as ece_router
from src.api.pagination import (
    TimeSeriesPaginator,
    AdaptivePaginator,
    PageResult,
    CursorCodec,
    create_paginator_from_data,
)
from src.api.lazy_loader import (
    LazyDataLoader,
    AsyncLazyDataLoader,
    LazyDataSet,
    TimeRange,
    PanDirection,
    Resolution,
    create_lazy_loader,
)

__all__ = [
    "ece_router",
    # Pagination
    "TimeSeriesPaginator",
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
]
