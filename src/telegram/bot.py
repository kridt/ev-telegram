"""Telegram bot for sending value bet alerts."""

import logging
from datetime import datetime
from typing import List, Optional

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from ..engine.value import ValueBet
from ..utils.config import Settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Handles Telegram notifications for value bets."""

    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize the Telegram notifier.

        Args:
            bot_token: Telegram bot API token
            chat_id: Chat ID to send messages to
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._bot: Optional[Bot] = None

    @property
    def bot(self) -> Bot:
        """Get or create the bot instance."""
        if self._bot is None:
            self._bot = Bot(token=self.bot_token)
        return self._bot

    @property
    def is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return bool(self.bot_token and self.chat_id)

    async def send_message(self, text: str, parse_mode: str = ParseMode.HTML) -> bool:
        """
        Send a message to the configured chat.

        Args:
            text: Message text
            parse_mode: Telegram parse mode (HTML or Markdown)

        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            logger.warning("Telegram not configured, skipping message")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def send_value_alert(self, value_bet: ValueBet) -> bool:
        """
        Send a formatted value bet alert.

        Args:
            value_bet: The value bet to alert about

        Returns:
            True if sent successfully
        """
        message = self._format_value_alert(value_bet)
        return await self.send_message(message)

    async def send_multiple_alerts(self, value_bets: List[ValueBet]) -> int:
        """
        Send alerts for multiple value bets.

        Args:
            value_bets: List of value bets to alert about

        Returns:
            Number of successfully sent alerts
        """
        if not value_bets:
            return 0

        # If many bets, send a summary instead
        if len(value_bets) > 5:
            summary = self._format_summary(value_bets)
            success = await self.send_message(summary)
            return len(value_bets) if success else 0

        sent = 0
        for bet in value_bets:
            if await self.send_value_alert(bet):
                sent += 1

        return sent

    def _format_value_alert(self, bet: ValueBet) -> str:
        """Format a single value bet as a Telegram message."""
        # Format kickoff time
        kickoff_str = "TBD"
        if bet.kickoff:
            kickoff_str = bet.kickoff.strftime("%H:%M UTC")

        # Format hours to kickoff
        hours_str = ""
        if bet.hours_to_kickoff is not None:
            hours = bet.hours_to_kickoff
            if hours < 1:
                hours_str = f"({int(hours * 60)} min)"
            else:
                hours_str = f"({hours:.1f}h)"

        # Build message
        message = f"""<b>⚽ VALUE BET FOUND</b>

<b>Player/Market:</b> {bet.market_name}
<b>Match:</b> {bet.fixture_name}
<b>League:</b> {bet.league}
<b>Kickoff:</b> {kickoff_str} {hours_str}

<b>Selection:</b> {bet.selection}
<b>Best Odds:</b> <code>{bet.best_odds:.2f}</code> @ {bet.best_book}
<b>Fair Odds:</b> <code>{bet.fair_odds:.2f}</code>
<b>Edge:</b> <code>{bet.edge_percent:.1f}%</code>

<i>Odds comparison:</i>
"""

        # Add odds from all books
        sorted_odds = sorted(bet.all_odds.items(), key=lambda x: x[1], reverse=True)
        for book, odds in sorted_odds[:5]:  # Top 5 books
            emoji = "📈" if odds == bet.best_odds else "  "
            message += f"{emoji} {book}: {odds:.2f}\n"

        return message

    def _format_summary(self, bets: List[ValueBet]) -> str:
        """Format a summary of multiple value bets."""
        message = f"<b>⚽ {len(bets)} VALUE BETS FOUND</b>\n\n"

        for i, bet in enumerate(bets[:10], 1):  # Max 10 in summary
            kickoff_str = ""
            if bet.kickoff:
                kickoff_str = f" @ {bet.kickoff.strftime('%H:%M')}"

            message += (
                f"<b>{i}.</b> {bet.market_name}\n"
                f"   {bet.fixture_name}{kickoff_str}\n"
                f"   {bet.selection}: <code>{bet.best_odds:.2f}</code> @ {bet.best_book} "
                f"(<code>{bet.edge_percent:.1f}%</code> edge)\n\n"
            )

        if len(bets) > 10:
            message += f"<i>...and {len(bets) - 10} more</i>"

        return message

    async def send_startup_message(self) -> bool:
        """Send a startup notification."""
        message = (
            "<b>🚀 Soccer Props Value Bot Started</b>\n\n"
            f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            "Monitoring for value betting opportunities..."
        )
        return await self.send_message(message)

    async def send_error_alert(self, error: str) -> bool:
        """Send an error notification."""
        message = f"<b>⚠️ Bot Error</b>\n\n<code>{error}</code>"
        return await self.send_message(message)


def create_notifier_from_settings(settings: Settings) -> Optional[TelegramNotifier]:
    """
    Create a TelegramNotifier from settings.

    Args:
        settings: Application settings

    Returns:
        TelegramNotifier or None if not configured
    """
    if settings.telegram.bot_token and settings.telegram.chat_id:
        return TelegramNotifier(
            bot_token=settings.telegram.bot_token,
            chat_id=settings.telegram.chat_id,
        )
    return None
