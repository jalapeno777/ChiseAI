"""Signals command for Discord bot.

Provides !signals command to list active trading signals.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from discord import Embed

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Represents a trading signal.

    Attributes:
        signal_id: Unique signal identifier.
        symbol: Trading symbol (e.g., BTC/USD).
        direction: 'long' or 'short'.
        entry_price: Entry price.
        current_price: Current market price.
        confidence: Confidence score (0-100).
        status: 'active', 'closed', 'cancelled'.
        created_at: When signal was created.
        expires_at: When signal expires.
        pnl: Profit/loss if closed.
        description: Signal description.
    """

    signal_id: str
    symbol: str
    direction: str
    entry_price: float
    current_price: float
    confidence: float
    status: str = "active"
    created_at: datetime | None = None
    expires_at: datetime | None = None
    pnl: float | None = None
    description: str = ""

    @property
    def emoji(self) -> str:
        """Get emoji for direction."""
        return "🟢" if self.direction == "long" else "🔴"

    @property
    def price_change_pct(self) -> float:
        """Calculate price change percentage."""
        if self.entry_price == 0:
            return 0.0
        change = self.current_price - self.entry_price
        return (change / self.entry_price) * 100

    @property
    def pnl_emoji(self) -> str:
        """Get emoji for PnL."""
        if self.pnl is None:
            return "⏳"
        return "🟢" if self.pnl >= 0 else "🔴"


class SignalsCommand:
    """Handler for !signals command.

    Features:
    - List active signals
    - Filter by symbol, direction, confidence
    - Pagination for long lists
    - Embedded Discord messages
    """

    DEFAULT_PAGE_SIZE = 5
    MAX_EMBED_FIELDS = 25

    def __init__(
        self,
        signals_provider: Any | None = None,
        max_results: int = 50,
    ):
        """Initialize SignalsCommand.

        Args:
            signals_provider: Provider for signal data (mock or real).
            max_results: Maximum signals to return.
        """
        self._signals_provider = signals_provider
        self._max_results = max_results

    async def get_signals(
        self,
        symbol: str | None = None,
        direction: str | None = None,
        min_confidence: float | None = None,
        status: str | None = "active",
    ) -> list[Signal]:
        """Get signals with optional filters.

        Args:
            symbol: Filter by symbol (e.g., "BTC/USD").
            direction: Filter by direction ("long" or "short").
            min_confidence: Minimum confidence score (0-100).
            status: Filter by status ("active", "closed", etc).

        Returns:
            List of Signal objects.
        """
        # Use provider if available, otherwise return mock data
        if self._signals_provider:
            try:
                return await self._signals_provider.get_signals(
                    symbol=symbol,
                    direction=direction,
                    min_confidence=min_confidence,
                    status=status,
                )
            except Exception as e:
                logger.error("Signals provider error: %s", str(e))

        # Return mock data for testing
        return self._get_mock_signals(symbol, direction, min_confidence, status)

    def _get_mock_signals(
        self,
        symbol: str | None,
        direction: str | None,
        min_confidence: float | None,
        status: str | None,
    ) -> list[Signal]:
        """Generate mock signals for testing.

        Args:
            symbol: Filter by symbol.
            direction: Filter by direction.
            min_confidence: Minimum confidence.
            status: Filter by status.

        Returns:
            List of mock Signal objects.
        """
        mock_signals = [
            Signal(
                signal_id="SIG-001",
                symbol="BTC/USD",
                direction="long",
                entry_price=67234.50,
                current_price=68102.30,
                confidence=87.5,
                status="active",
                created_at=datetime.now(UTC) - timedelta(hours=2),
                description="BTC breakout above resistance",
            ),
            Signal(
                signal_id="SIG-002",
                symbol="ETH/USD",
                direction="short",
                entry_price=3521.20,
                current_price=3489.45,
                confidence=72.3,
                status="active",
                created_at=datetime.now(UTC) - timedelta(hours=5),
                description="ETH approaching key support",
            ),
            Signal(
                signal_id="SIG-003",
                symbol="SOL/USD",
                direction="long",
                entry_price=142.80,
                current_price=145.60,
                confidence=65.0,
                status="active",
                created_at=datetime.now(UTC) - timedelta(minutes=30),
                description="SOL momentum play",
            ),
            Signal(
                signal_id="SIG-004",
                symbol="BTC/USD",
                direction="short",
                entry_price=68500.00,
                current_price=68102.30,
                confidence=91.2,
                status="active",
                created_at=datetime.now(UTC) - timedelta(hours=1),
                description="BTC short on overbought",
            ),
            Signal(
                signal_id="SIG-005",
                symbol="AVAX/USD",
                direction="long",
                entry_price=35.40,
                current_price=36.12,
                confidence=58.7,
                status="closed",
                created_at=datetime.now(UTC) - timedelta(days=1),
                expires_at=datetime.now(UTC) - timedelta(hours=12),
                pnl=2.03,
                description="AVAX swing trade",
            ),
        ]

        # Apply filters
        filtered = mock_signals

        if symbol:
            filtered = [s for s in filtered if symbol.upper() in s.symbol.upper()]

        if direction:
            filtered = [s for s in filtered if s.direction == direction.lower()]

        if min_confidence is not None:
            filtered = [s for s in filtered if s.confidence >= min_confidence]

        if status:
            filtered = [s for s in filtered if s.status == status.lower()]

        return filtered[: self._max_results]

    def format_signal_embed(
        self, signal: Signal, page: int = 1, total_pages: int = 1
    ) -> Embed:
        """Format a signal as Discord embed.

        Args:
            signal: Signal to format.
            page: Current page number.
            total_pages: Total pages.

        Returns:
            Discord Embed object.
        """
        color = 0x43B581 if signal.direction == "long" else 0xFF4444

        embed = Embed(
            title=f"{signal.emoji} {signal.signal_id}: {signal.symbol} {signal.direction.upper()}",
            color=color,
            timestamp=signal.created_at or datetime.now(UTC),
        )

        # Add fields
        embed.add_field(
            name="Entry Price",
            value=f"${signal.entry_price:,.2f}",
            inline=True,
        )
        embed.add_field(
            name="Current Price",
            value=f"${signal.current_price:,.2f}",
            inline=True,
        )
        embed.add_field(
            name="Change",
            value=f"{signal.price_change_pct:+.2f}%",
            inline=True,
        )

        embed.add_field(
            name="Confidence",
            value=f"{signal.confidence:.1f}%",
            inline=True,
        )
        embed.add_field(
            name="Status",
            value=signal.status.upper(),
            inline=True,
        )

        if signal.pnl is not None:
            embed.add_field(
                name="PnL",
                value=f"{signal.pnl_emoji} {signal.pnl:+.2f}%",
                inline=True,
            )

        if signal.description:
            embed.add_field(
                name="Description",
                value=signal.description,
                inline=False,
            )

        # Footer with pagination
        if total_pages > 1:
            embed.set_footer(text=f"Page {page}/{total_pages}")

        return embed

    def format_signals_list_embed(
        self,
        signals: list[Signal],
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Embed:
        """Format a list of signals as a single embed.

        Args:
            signals: List of signals.
            page: Current page.
            page_size: Signals per page.

        Returns:
            Discord Embed object.
        """
        total_pages = max(1, (len(signals) + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_signals = signals[start_idx:end_idx]

        # Calculate aggregate stats
        active_signals = [s for s in signals if s.status == "active"]
        long_signals = [s for s in active_signals if s.direction == "long"]
        short_signals = [s for s in active_signals if s.direction == "short"]
        avg_confidence = (
            sum(s.confidence for s in active_signals) / len(active_signals)
            if active_signals
            else 0
        )

        embed = Embed(
            title="📊 Active Trading Signals",
            color=0x7289DA,
            timestamp=datetime.now(UTC),
        )

        # Summary stats
        embed.add_field(
            name="Total Active",
            value=str(len(active_signals)),
            inline=True,
        )
        embed.add_field(
            name="Long",
            value=str(len(long_signals)),
            inline=True,
        )
        embed.add_field(
            name="Short",
            value=str(len(short_signals)),
            inline=True,
        )
        embed.add_field(
            name="Avg Confidence",
            value=f"{avg_confidence:.1f}%",
            inline=True,
        )

        # Signal list
        signal_lines = []
        for s in page_signals:
            pnl_str = f" | PnL: {s.pnl:+.2f}%" if s.pnl is not None else ""
            signal_lines.append(
                f"{s.emoji} `{s.signal_id}` {s.symbol} "
                f"{s.direction.upper()} "
                f"${s.current_price:,.0f} "
                f"(C: {s.confidence:.0f}%){pnl_str}"
            )

        embed.add_field(
            name=f"Signals ({len(signals)} total)",
            value="\n".join(signal_lines) if signal_lines else "No signals",
            inline=False,
        )

        if total_pages > 1:
            embed.set_footer(
                text=f"Page {page}/{total_pages} | Use !signals page N for more"
            )

        return embed

    async def execute(self, ctx: Any, args: dict[str, Any]) -> bool:
        """Execute !signals command.

        Args:
            ctx: Discord context.
            args: Parsed command arguments.

        Returns:
            True if successful.
        """
        # Parse filters from args
        symbol = args.get("symbol")
        direction = args.get("direction")
        min_confidence = args.get("confidence")
        page = args.get("page", 1)
        page_size = args.get("limit", self.DEFAULT_PAGE_SIZE)

        # Validate direction
        if direction and direction.lower() not in ("long", "short"):
            if hasattr(ctx, "send"):
                await ctx.send("❌ Direction must be 'long' or 'short'")
            return False

        # Validate confidence
        if min_confidence is not None:
            try:
                min_confidence = float(min_confidence)
                if min_confidence < 0 or min_confidence > 100:
                    raise ValueError()
            except (TypeError, ValueError):
                if hasattr(ctx, "send"):
                    await ctx.send("❌ Confidence must be 0-100")
                return False

        # Get signals
        try:
            signals = await self.get_signals(
                symbol=symbol,
                direction=direction,
                min_confidence=min_confidence,
                status="active",
            )
        except Exception as e:
            logger.error("Failed to get signals: %s", str(e))
            if hasattr(ctx, "send"):
                await ctx.send("❌ Failed to fetch signals. Please try again later.")
            return False

        if not signals:
            if hasattr(ctx, "send"):
                await ctx.send("📭 No active signals match your criteria.")
            return True

        # Handle single signal detail request
        if args.get("detail") and len(signals) == 1:
            embed = self.format_signal_embed(signals[0])
            if hasattr(ctx, "send"):
                await ctx.send(embed=embed)
            return True

        # Format as list
        try:
            page = int(page)
            page_size = min(int(page_size), self.DEFAULT_PAGE_SIZE)
        except (TypeError, ValueError):
            page = 1
            page_size = self.DEFAULT_PAGE_SIZE

        total_pages = max(1, (len(signals) + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))

        embed = self.format_signals_list_embed(signals, page, page_size)

        if hasattr(ctx, "send"):
            await ctx.send(embed=embed)

        return True
