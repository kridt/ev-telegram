"""Main entry point for the Soccer Props Value Betting System."""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import List, Optional

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .api import OpticOddsClient, Fixture, OddsData
from .dashboard import create_app
from .engine import ValueCalculator, ValueBet
from .telegram import TelegramNotifier
from .telegram.bot import create_notifier_from_settings
from .tracking import BetTracker, ResultsChecker
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
        self.api_client: Optional[OpticOddsClient] = None
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
        self.results_checker: Optional[ResultsChecker] = None

        # Shared state
        self.current_fixtures: List[Fixture] = []
        self.current_value_bets: List[ValueBet] = []
        self.sent_alerts: set = set()  # Track sent alerts to avoid duplicates

        # Scheduler
        self.scheduler: Optional[AsyncIOScheduler] = None

        # Running flag
        self._running = False

    async def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing value betting system...")

        # Reload settings
        self.settings = self.config_manager.load_settings()

        # Initialize API client
        if self.settings.opticodds_api_key:
            self.api_client = OpticOddsClient(self.settings.opticodds_api_key)
            logger.info("OpticOdds API client initialized")
        else:
            logger.warning("OpticOdds API key not configured")

        # Initialize Telegram
        self.telegram = create_notifier_from_settings(self.settings)
        if self.telegram:
            logger.info("Telegram notifier initialized")
        else:
            logger.warning("Telegram not configured")

        # Initialize tracking
        self.bet_tracker = BetTracker()
        if self.api_client:
            self.results_checker = ResultsChecker(self.api_client, self.bet_tracker)
        logger.info(f"Bet tracker initialized with {len(self.bet_tracker.bets)} existing bets")

    async def shutdown(self) -> None:
        """Shutdown all components."""
        logger.info("Shutting down...")

        if self.api_client:
            await self.api_client.close()

        if self.scheduler:
            self.scheduler.shutdown()

        self._running = False

    async def fetch_and_analyze(self) -> List[ValueBet]:
        """
        Fetch odds and find value bets.

        Returns:
            List of found value bets
        """
        if not self.api_client:
            logger.warning("API client not initialized, skipping fetch")
            return []

        try:
            all_value_bets = []
            self.current_fixtures.clear()  # Clear old fixtures
            sportsbooks = self.settings.sportsbooks or ["betsson", "leovegas", "unibet", "betway"]
            target_markets = self.settings.target_markets if hasattr(self.settings, 'target_markets') else None

            # Fetch fixtures for each configured league
            leagues = self.settings.leagues or []
            if not leagues or "all" in [l.lower() for l in leagues]:
                # If "all" or empty, fetch without league filter
                leagues = [None]

            for league in leagues:
                try:
                    logger.info(f"Fetching fixtures for {league or 'all leagues'}...")
                    fixtures = await self.api_client.get_fixtures(
                        sport="soccer",
                        league=league,
                        hours_ahead=self.settings.hours_ahead,
                    )

                    if not fixtures:
                        continue

                    logger.info(f"Found {len(fixtures)} fixtures for {league or 'all'}")

                    # Process each fixture
                    for fixture in fixtures[:10]:  # Limit per league for performance
                        try:
                            odds = await self.api_client.get_odds(
                                fixture.id,
                                sportsbooks=sportsbooks,
                            )

                            if not odds:
                                continue

                            value_bets = self.value_calculator.find_value_bets(
                                fixture, odds, target_markets=target_markets
                            )
                            all_value_bets.extend(value_bets)
                            self.current_fixtures.append(fixture)

                        except Exception as e:
                            logger.error(f"Error processing fixture {fixture.id}: {e}")

                except Exception as e:
                    logger.error(f"Error fetching fixtures for {league}: {e}")

            # Filter by minimum edge
            min_edge = self.settings.min_edge_percent
            all_value_bets = [b for b in all_value_bets if b.edge_percent >= min_edge]

            # Sort by edge
            all_value_bets.sort(key=lambda x: x.edge_percent, reverse=True)

            # Update the shared list (don't replace reference - dashboard uses same list)
            self.current_value_bets.clear()
            self.current_value_bets.extend(all_value_bets)
            logger.info(f"Found {len(all_value_bets)} value bets with edge >= {min_edge}%")

            return all_value_bets

        except Exception as e:
            logger.error(f"Error in fetch_and_analyze: {e}")
            return []

    async def send_alerts(self, value_bets: List[ValueBet]) -> None:
        """
        Send Telegram alerts for new value bets.

        Args:
            value_bets: List of value bets to alert about
        """
        if not self.telegram or not self.telegram.is_configured:
            return

        # Filter out already-sent alerts
        new_bets = []
        for bet in value_bets:
            alert_key = f"{bet.fixture_id}_{bet.market}_{bet.selection}_{bet.best_book}"
            if alert_key not in self.sent_alerts:
                new_bets.append(bet)
                self.sent_alerts.add(alert_key)

        if not new_bets:
            return

        logger.info(f"Sending {len(new_bets)} new alerts")
        sent = await self.telegram.send_multiple_alerts(new_bets)
        logger.info(f"Sent {sent} alerts successfully")

    async def run_cycle(self) -> None:
        """Run a single fetch-analyze-alert cycle."""
        logger.info("Starting analysis cycle...")
        start = datetime.utcnow()

        try:
            value_bets = await self.fetch_and_analyze()
            await self.send_alerts(value_bets)
        except Exception as e:
            logger.error(f"Error in cycle: {e}")
            if self.telegram:
                await self.telegram.send_error_alert(str(e))

        elapsed = (datetime.utcnow() - start).total_seconds()
        logger.info(f"Cycle completed in {elapsed:.1f}s")

    def start_scheduler(self) -> None:
        """Start the background scheduler."""
        self.scheduler = AsyncIOScheduler()

        # Schedule the main job
        interval = self.settings.refresh_interval_minutes
        self.scheduler.add_job(
            self.run_cycle,
            IntervalTrigger(minutes=interval),
            id="main_cycle",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(f"Scheduler started, running every {interval} minutes")

    async def run(self) -> None:
        """Run the complete system with web dashboard."""
        await self.initialize()

        # Create FastAPI app with shared state
        app = create_app(
            config_manager=self.config_manager,
            value_bets_store=self.current_value_bets,
            fixtures_store=self.current_fixtures,
        )

        # The app state references our lists, so updates will be reflected
        app.state.value_bets = self.current_value_bets
        app.state.fixtures = self.current_fixtures
        app.state.bet_tracker = self.bet_tracker
        app.state.results_checker = self.results_checker

        # Send startup message
        if self.telegram and self.telegram.is_configured:
            await self.telegram.send_startup_message()

        # Run initial cycle
        await self.run_cycle()

        # Start scheduler
        self.start_scheduler()

        # Run web server
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
        )
        server = uvicorn.Server(config)

        self._running = True

        # Handle shutdown signals
        loop = asyncio.get_event_loop()

        def signal_handler():
            logger.info("Received shutdown signal")
            asyncio.create_task(self.shutdown())

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig, lambda s, f: signal_handler())

        await server.serve()


async def main():
    """Main entry point."""
    # Setup logging
    setup_logging(level="INFO")

    logger.info("Soccer Props Value Betting System starting...")

    system = ValueBettingSystem()

    try:
        await system.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await system.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
