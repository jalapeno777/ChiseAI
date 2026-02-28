"""Nightly trade history recap for #trading channel.

Posts a daily summary of trade history to the Discord #trading channel.
This complements the daily summary to #summaries by providing a more
focused view of individual trades.

For RECON-001: Trade Schema Reconciliation
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from src.ml.models.signal_outcome import SignalOutcome

logger = logging.getLogger(__name__)


class TradeHistoryRecap:
    """Generate and send nightly trade history recap to #trading.

    Queries persisted trade outcomes and posts a summary to Discord #trading
    channel with key metrics and highlights from the day's trading activity.

    Attributes:
        trading_webhook_url: Discord webhook URL for #trading channel
        trading_channel_id: Discord channel ID for #trading
    """

    def __init__(
        self,
        trading_webhook_url: str | None = None,
        trading_channel_id: str = "1444447985378398459",
    ) -> None:
        """Initialize trade history recap.

        Args:
            trading_webhook_url: Discord webhook URL for #trading
                (reads from DISCORD_TRADING_WEBHOOK_URL env if None)
            trading_channel_id: Discord channel ID for #trading
        """
        self.trading_webhook_url = (
            trading_webhook_url
            or os.getenv("DISCORD_TRADING_WEBHOOK_URL")
            or os.getenv("DISCORD_WEBHOOK_URL")
        )
        self.trading_channel_id = trading_channel_id
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30.0)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def generate_and_send_recap(
        self,
        date: datetime | None = None,
        trades: list[SignalOutcome] | None = None,
    ) -> dict[str, Any]:
        """Generate and send trade history recap.

        Args:
            date: Date for the recap (default: yesterday)
            trades: List of trades to include (if None, queries database)

        Returns:
            Dictionary with result status
        """
        if date is None:
            date = datetime.now(UTC) - timedelta(days=1)

        # Normalize to start of day
        date = date.replace(hour=0, minute=0, second=0, microsecond=0)

        logger.info(f"Generating trade history recap for {date.strftime('%Y-%m-%d')}")

        # If no trades provided, we would query from database
        # For now, this is a placeholder - actual implementation would
        # query the SignalOutcome records from PostgreSQL
        if trades is None:
            trades = await self._query_trades_for_date(date)

        if not trades:
            logger.info("No trades found for recap date")
            return {
                "success": True,
                "message": "No trades to report",
                "trades_count": 0,
            }

        # Generate recap content
        content = self._format_recap_message(date, trades)

        # Send to Discord
        if not self.trading_webhook_url:
            logger.warning("No trading webhook URL configured")
            return {
                "success": False,
                "error": "No trading webhook URL configured",
                "trades_count": len(trades),
            }

        result = await self._send_to_discord(content)
        result["trades_count"] = len(trades)
        return result

    async def _query_trades_for_date(
        self,
        date: datetime,
    ) -> list[SignalOutcome]:
        """Query trades from database for a specific date.

        Args:
            date: Date to query

        Returns:
            List of SignalOutcome records
        """
        trades = []

        try:
            # This would query PostgreSQL for SignalOutcome records
            # Implementation depends on the database client available
            import asyncpg

            db_host = os.getenv("DB_HOST", "host.docker.internal")
            db_port = int(os.getenv("DB_PORT", "5434"))
            db_name = os.getenv("DB_NAME", "chiseai")
            db_user = os.getenv("DB_USER", "chiseai")
            db_pass = os.getenv("DB_PASSWORD", "chiseai")

            dsn = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

            conn = await asyncpg.connect(dsn)
            try:
                start_time = date
                end_time = date + timedelta(days=1)

                rows = await conn.fetch(
                    """
                    SELECT * FROM signal_outcomes
                    WHERE entry_time >= $1 AND entry_time < $2
                    ORDER BY entry_time DESC
                    """,
                    start_time,
                    end_time,
                )

                from src.ml.models.signal_outcome import SignalOutcome

                for row in rows:
                    # Convert asyncpg Record to dict, handling native types
                    row_dict = {}
                    for key, value in row.items():
                        if hasattr(value, "int") and not hasattr(value, "timestamp"):
                            # asyncpg UUID object - convert to string
                            row_dict[key] = str(value)
                        elif hasattr(value, "isoformat"):
                            # datetime object - convert to ISO string
                            row_dict[key] = value.isoformat()
                        else:
                            row_dict[key] = value
                    trade = SignalOutcome.from_dict(row_dict)
                    trades.append(trade)

            finally:
                await conn.close()

        except Exception as e:
            logger.error(f"Failed to query trades: {e}")

        return trades

    def _format_recap_message(
        self,
        date: datetime,
        trades: list[SignalOutcome],
    ) -> str:
        """Format trade recap as Discord message.

        Args:
            date: Date of the recap
            trades: List of trades to include

        Returns:
            Formatted message string
        """
        from decimal import Decimal

        # Calculate metrics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl and t.pnl < 0]

        total_pnl = sum((t.pnl or Decimal("0")) for t in trades)

        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

        # Find best and worst trades
        best_trade = (
            max(winning_trades, key=lambda t: t.pnl or Decimal("0"))
            if winning_trades
            else None
        )
        worst_trade = (
            min(losing_trades, key=lambda t: t.pnl or Decimal("0"))
            if losing_trades
            else None
        )

        # Format message
        lines = [
            "📊 **Daily Trade History Recap**",
            f"**Date:** {date.strftime('%Y-%m-%d')}",
            "",
            "📈 **Summary**",
            f"```",
            f"Total Trades:   {total_trades}",
            f"Winning:        {win_count}",
            f"Losing:         {loss_count}",
            f"Win Rate:       {win_rate:.1f}%",
            f"Total PnL:      ${float(total_pnl):,.2f}",
            f"```",
        ]

        # Add best trade
        if best_trade:
            token = best_trade.token or best_trade.symbol.replace("USDT", "")
            lines.extend(
                [
                    "",
                    "🏆 **Best Trade**",
                    f"```",
                    f"Token:     {token}",
                    f"Direction: {best_trade.direction}",
                    f"PnL:       +${float(best_trade.pnl):,.2f}",
                    f"```",
                ]
            )

        # Add worst trade
        if worst_trade:
            token = worst_trade.token or worst_trade.symbol.replace("USDT", "")
            lines.extend(
                [
                    "",
                    "💔 **Worst Trade**",
                    f"```",
                    f"Token:     {token}",
                    f"Direction: {worst_trade.direction}",
                    f"PnL:       ${float(worst_trade.pnl):,.2f}",
                    f"```",
                ]
            )

        # Add recent trades (last 5)
        if trades:
            lines.extend(
                [
                    "",
                    "📝 **Recent Trades**",
                ]
            )
            for trade in trades[:5]:
                token = trade.token or trade.symbol.replace("USDT", "")
                pnl_str = ""
                if trade.pnl is not None:
                    pnl_prefix = "+" if trade.pnl > 0 else ""
                    pnl_str = f" ({pnl_prefix}${float(trade.pnl):,.2f})"

                status_emoji = "🔒" if trade.is_closed else "⏳"
                lines.append(f"{status_emoji} {token} {trade.direction}{pnl_str}")

        lines.extend(
            [
                "",
                "---",
                "*Trade history recap generated by ChiseAI*",
            ]
        )

        return "\n".join(lines)

    async def _send_to_discord(self, content: str) -> dict[str, Any]:
        """Send message to Discord webhook.

        Args:
            content: Message content

        Returns:
            Dictionary with success status
        """
        try:
            session = await self._get_session()

            # Discord has a 2000 character limit for content
            chunks = self._split_message(content, 1900)
            message_ids = []

            for i, chunk in enumerate(chunks):
                payload = {"content": chunk}

                async with session.post(
                    self.trading_webhook_url,  # type: ignore[arg-type]
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 204:
                        message_ids.append(f"part_{i + 1}")
                        logger.debug(f"Discord message sent (part {i + 1})")
                    elif response.status == 429:
                        retry_after = float(response.headers.get("Retry-After", "5"))
                        logger.warning(f"Rate limited, retry after {retry_after}s")
                        return {
                            "success": False,
                            "error": f"Rate limited. Retry after {retry_after}s",
                            "retry_after": retry_after,
                        }
                    else:
                        body = await response.text()
                        error_msg = (
                            f"Discord webhook returned {response.status}: {body}"
                        )
                        logger.error(error_msg)
                        return {"success": False, "error": error_msg}

            return {
                "success": True,
                "message_ids": message_ids,
                "parts": len(chunks),
            }

        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return {"success": False, "error": str(e)}

    def _split_message(self, content: str, max_length: int) -> list[str]:
        """Split message into chunks.

        Args:
            content: Message content
            max_length: Maximum chunk length

        Returns:
            List of message chunks
        """
        if len(content) <= max_length:
            return [content]

        chunks = []
        lines = content.split("\n")
        current_chunk = ""

        for line in lines:
            if len(current_chunk) + len(line) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    async def schedule_daily_recap(
        self,
        hour: int = 0,
        minute: int = 0,
    ) -> None:
        """Schedule daily recap at specified time.

        This is a simple scheduling method. For production, use a proper
        scheduler like APScheduler or integrate with the existing
        DailySummaryScheduler.

        Args:
            hour: Hour to run (0-23)
            minute: Minute to run (0-59)
        """
        import asyncio

        while True:
            now = datetime.now(UTC)
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if target <= now:
                # Target time has passed, schedule for tomorrow
                target = target + timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            logger.info(f"Next trade history recap scheduled for {target.isoformat()}")

            await asyncio.sleep(wait_seconds)

            # Generate and send recap for yesterday
            yesterday = target - timedelta(days=1)
            await self.generate_and_send_recap(date=yesterday)


async def run_nightly_recap() -> dict[str, Any]:
    """Run the nightly trade history recap.

    This function can be called from a scheduler or cron job.

    Returns:
        Dictionary with result status
    """
    recap = TradeHistoryRecap()
    try:
        result = await recap.generate_and_send_recap()
        return result
    finally:
        await recap.close()
