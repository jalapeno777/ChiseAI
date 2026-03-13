"""
Trades API Router

TEMPO-2026-001: Instrumented with OpenTelemetry custom spans
"""

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

# Import trace module to get tracer
from opentelemetry import trace

# Get tracer for this module
tracer = trace.get_tracer(__name__)

router = APIRouter(prefix="/api/v1/trades", tags=["trades"])


class TradeCreate(BaseModel):
    """Trade creation request model."""

    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    price: Optional[float] = None
    order_type: str = "market"  # "market" or "limit"
    user_id: str


class TradeResult(BaseModel):
    """Trade result model."""

    trade_id: str
    status: str
    symbol: str
    side: str
    quantity: float
    filled_price: Optional[float] = None
    message: Optional[str] = None


@router.post("/", response_model=TradeResult)
async def create_trade(trade: TradeCreate):
    """
    Create a new trade.

    TEMPO-2026-001: Custom span with ChiseAI-specific attributes
    """
    with tracer.start_as_current_span("create_trade") as span:
        # Set ChiseAI-specific attributes
        span.set_attribute("chiseai.trade.symbol", trade.symbol)
        span.set_attribute("chiseai.trade.side", trade.side)
        span.set_attribute("chiseai.trade.quantity", trade.quantity)
        span.set_attribute("chiseai.trade.order_type", trade.order_type)
        span.set_attribute("chiseai.user.id", trade.user_id)
        span.set_attribute("chiseai.endpoint", "/api/v1/trades/")

        try:
            # Simulate trade processing
            # In production, this would call the actual trade engine
            import uuid

            trade_id = str(uuid.uuid4())

            # Set additional attributes after processing
            span.set_attribute("chiseai.trade.id", trade_id)
            span.set_attribute("chiseai.trade.status", "created")

            result = TradeResult(
                trade_id=trade_id,
                status="created",
                symbol=trade.symbol,
                side=trade.side,
                quantity=trade.quantity,
                filled_price=None,
                message="Trade created successfully",
            )

            return result

        except Exception as e:
            span.set_attribute("chiseai.trade.error", str(e))
            span.set_attribute("error", True)
            raise HTTPException(
                status_code=500, detail=f"Failed to create trade: {str(e)}"
            )


@router.get("/{trade_id}")
async def get_trade(trade_id: str):
    """
    Get trade by ID.

    TEMPO-2026-001: Custom span for trade retrieval
    """
    with tracer.start_as_current_span("get_trade") as span:
        span.set_attribute("chiseai.trade.id", trade_id)
        span.set_attribute("chiseai.endpoint", f"/api/v1/trades/{trade_id}")

        # Simulate trade lookup
        # In production, this would query the database
        return {
            "trade_id": trade_id,
            "status": "filled",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100.0,
            "filled_price": 150.0,
        }


@router.get("/")
async def list_trades(
    symbol: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 100,
):
    """
    List trades with optional filtering.

    TEMPO-2026-001: Custom span for trade listing
    """
    with tracer.start_as_current_span("list_trades") as span:
        span.set_attribute("chiseai.endpoint", "/api/v1/trades/")
        span.set_attribute("chiseai.trade.list.limit", limit)

        if symbol:
            span.set_attribute("chiseai.trade.symbol", symbol)
        if user_id:
            span.set_attribute("chiseai.user.id", user_id)

        # Simulate trade listing
        # In production, this would query the database
        return {
            "trades": [],
            "count": 0,
            "symbol_filter": symbol,
            "user_filter": user_id,
        }


@router.post("/{trade_id}/cancel")
async def cancel_trade(trade_id: str):
    """
    Cancel a pending trade.

    TEMPO-2026-001: Custom span for trade cancellation
    """
    with tracer.start_as_current_span("cancel_trade") as span:
        span.set_attribute("chiseai.trade.id", trade_id)
        span.set_attribute("chiseai.endpoint", f"/api/v1/trades/{trade_id}/cancel")
        span.set_attribute("chiseai.trade.action", "cancel")

        # Simulate trade cancellation
        # In production, this would call the trade engine
        return {
            "trade_id": trade_id,
            "status": "cancelled",
            "message": "Trade cancelled successfully",
        }
