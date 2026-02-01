"""Main entry point for the Soccer Props Value Betting System.

Note: The main scanner is now oddsapi_scanner.py which uses Odds-API.io.
This module contains the base system architecture for future use.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import List, Optional

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .api import OddsApiClient
from .dashboard import create_app
from .engine import ValueCalculator, ValueBet
from .telegram import TelegramNotifier
from .telegram.bot import create_notifier_from_settings
from .tracking import BetTracker
from .utils import ConfigManager, setup_logging
from .utils.logging import get_logger

logger = get_logger(__name__)


class ValueBettingSystem:
    """Main orchestrator for the value betting system."""

    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize the system.

        Args:
            config_dir: Optional path to config directory
        """
        self.config_manager = ConfigManager(config_dir)
        self.settings = self.config_manager.get_settings()

        # Initialize components
        self.api_client: Optional[OddsApiClient] = None
        self.value_calculator = ValueCalculator(
            min_edge=self.settings.min_edge_percent,
            max_edge=getattr(self.settings, 'max_edge_percent', 50.0),
            min_books=getattr(self.settings, 'min_books', 2),
            min_odds=getattr(self.settings, 'min_odds', 1.3),
            max_odds=getattr(self.settings, 'max_odds', 15.0),
        )
        self.telegram: Optional[TelegramNotifier] = None

        # Tracking
        self.bet_tracker: Optional[BetTracker] = None

        # Shared state
        self.current_value_bets: List[ValueBet] = []
        self.sent_alerts: set = set()

        # Scheduler
        self.scheduler: Optional[AsyncIOScheduler] = None

        # Running flag
        self._running = False

    async def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing value betting system...")

        # Reload settings
        self.settings = self.config_manager.load_settings()

        # Initialize API client if Odds-API.io is configured
        if self.settings.oddsapi.enabled and self.settings.oddsapi.api_key:
            self.api_client = OddsApiClient(self.settings.oddsapi.api_key)
            logger.info("Odds-API.io client initialized")
        else:
            logger.warning("Odds-API.io not configured - use oddsapi_scanner.py instead")

        # Initialize Telegram
        self.telegram = create_notifier_from_settings(self.settings)
        if self.telegram:
            logger.info("Telegram notifier initialized")
        else:
            logger.warning("Telegram not configured")

        # Initialize tracking
        self.bet_tracker = BetTracker()
        logger.info(f"Bet tracker initialized with {len(self.bet_tracker.bets)} existing bets")

    async def shutdown(self) -> None:
        """Shutdown all components."""
        logger.info("Shutting down...")

        if self.api_client:
            await self.api_client.close()

        if self.scheduler:
            self.scheduler.shutdown()

        self._running = False


async def main():
    """Main entry point."""
    setup_logging(level="INFO")

    logger.info("Soccer Props Value Betting System")
    logger.info("Note: Use oddsapi_scanner.py for the main scanner")

    system = ValueBettingSystem()

    try:
        await system.initialize()
        logger.info("System initialized. Use oddsapi_scanner.py to run the scanner.")
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await system.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
