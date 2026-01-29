"""Results checker for settling bets automatically."""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from ..api import OpticOddsClient
from .bet_tracker import BetTracker, TrackedBet, BetStatus

logger = logging.getLogger(__name__)


class ResultsChecker:
    """Checks match results and settles bets."""

    def __init__(self, api_client: OpticOddsClient, bet_tracker: BetTracker):
        """Initialize with API client and bet tracker."""
        self.api = api_client
        self.tracker = bet_tracker

    async def check_and_settle(self) -> Dict[str, Any]:
        """Check for completed matches and settle pending bets."""
        pending = self.tracker.get_pending_bets()
        if not pending:
            return {"checked": 0, "settled": 0}

        # Group by fixture
        fixtures = {}
        for bet in pending:
            if bet.fixture_id not in fixtures:
                fixtures[bet.fixture_id] = []
            fixtures[bet.fixture_id].append(bet)

        logger.info(f"Checking results for {len(fixtures)} fixtures with {len(pending)} pending bets")

        settled_count = 0
        for fixture_id, bets in fixtures.items():
            try:
                results = await self._get_fixture_results(fixture_id)
                if results:
                    settled_count += self._settle_fixture_bets(bets, results)
            except Exception as e:
                logger.error(f"Error checking fixture {fixture_id}: {e}")

        return {
            "checked": len(fixtures),
            "settled": settled_count,
            "stats": self.tracker.get_stats(),
        }

    async def _get_fixture_results(self, fixture_id: str) -> Optional[Dict[str, Any]]:
        """Get results for a fixture."""
        try:
            # Use the API to get results
            results = await self.api._request(
                "GET",
                "/fixtures/results",
                params={"fixture_id": fixture_id}
            )

            if results and results.get("data"):
                data = results["data"][0]
                fixture_status = data.get("fixture", {}).get("status", "")

                if fixture_status == "completed":
                    return data

            return None

        except Exception as e:
            logger.debug(f"No results for {fixture_id}: {e}")
            return None

    def _settle_fixture_bets(self, bets: List[TrackedBet], results: Dict[str, Any]) -> int:
        """Settle all bets for a fixture given results."""
        # Extract stats from the API response structure
        # Stats are in results["stats"]["home"] and results["stats"]["away"] arrays
        # Each array has periods, we want the "all" period stats
        home_stats = {}
        away_stats = {}

        stats_data = results.get("stats", {})
        for stat_entry in stats_data.get("home", []):
            if stat_entry.get("period") == "all":
                home_stats = stat_entry.get("stats", {})
                break
        for stat_entry in stats_data.get("away", []):
            if stat_entry.get("period") == "all":
                away_stats = stat_entry.get("stats", {})
                break

        settled = 0

        for bet in bets:
            try:
                result_value = self._get_result_value(bet, home_stats, away_stats, results)

                if result_value is not None:
                    self.tracker.settle_bet(bet.id, result_value)
                    settled += 1
                    logger.info(f"Settled: {bet.selection} = {result_value}")
                else:
                    logger.warning(f"Could not find result for: {bet.market} - {bet.selection}")

            except Exception as e:
                logger.error(f"Error settling bet {bet.id}: {e}")

        return settled

    def _get_result_value(
        self,
        bet: TrackedBet,
        home_stats: Dict[str, float],
        away_stats: Dict[str, float],
        results: Dict[str, Any]
    ) -> Optional[float]:
        """Extract the result value for a bet from match stats.

        OpticOdds API field names:
        - total_scoring_att = Total shots
        - ontarget_scoring_att = Shots on target
        - fouls = Total fouls
        - won_corners = Corners won
        - goals = Total goals
        """
        market = bet.market.lower()
        selection = bet.selection.lower()

        # Team total shots markets
        if "total shots" in market and "on target" not in market:
            if "home" in selection or self._is_home_team(bet, results):
                return home_stats.get("total_scoring_att")
            elif "away" in selection or self._is_away_team(bet, results):
                return away_stats.get("total_scoring_att")
            else:
                # Combined total
                home = home_stats.get("total_scoring_att", 0)
                away = away_stats.get("total_scoring_att", 0)
                return home + away if home or away else None

        # Team shots on target markets
        elif "shots on target" in market or "total shots on target" in market:
            if "home" in selection or self._is_home_team(bet, results):
                return home_stats.get("ontarget_scoring_att")
            elif "away" in selection or self._is_away_team(bet, results):
                return away_stats.get("ontarget_scoring_att")
            else:
                home = home_stats.get("ontarget_scoring_att", 0)
                away = away_stats.get("ontarget_scoring_att", 0)
                return home + away if home or away else None

        # Corner markets
        elif "corner" in market:
            if "home" in selection or self._is_home_team(bet, results):
                return home_stats.get("won_corners")
            elif "away" in selection or self._is_away_team(bet, results):
                return away_stats.get("won_corners")
            else:
                home = home_stats.get("won_corners", 0)
                away = away_stats.get("won_corners", 0)
                return home + away if home or away else None

        # Card markets (yellow + red cards)
        elif "card" in market:
            if "home" in selection or self._is_home_team(bet, results):
                return home_stats.get("total_yellow_card", 0) or 0
            elif "away" in selection or self._is_away_team(bet, results):
                return away_stats.get("total_yellow_card", 0) or 0
            else:
                home_cards = home_stats.get("total_yellow_card", 0) or 0
                away_cards = away_stats.get("total_yellow_card", 0) or 0
                return home_cards + away_cards

        # Foul markets
        elif "foul" in market:
            if "home" in selection or self._is_home_team(bet, results):
                return home_stats.get("fouls")
            elif "away" in selection or self._is_away_team(bet, results):
                return away_stats.get("fouls")
            else:
                home = home_stats.get("fouls", 0)
                away = away_stats.get("fouls", 0)
                return home + away if home or away else None

        # Total goals markets
        elif "total goals" in market or "goals" in market and "player" not in market:
            if "home" in selection or self._is_home_team(bet, results):
                return home_stats.get("goals")
            elif "away" in selection or self._is_away_team(bet, results):
                return away_stats.get("goals")
            else:
                home = home_stats.get("goals", 0)
                away = away_stats.get("goals", 0)
                return home + away if home or away else None

        # Asian handicap markets
        elif "asian handicap" in market or "handicap" in market:
            scores = results.get("scores", {})
            home_goals = scores.get("home", {}).get("total", 0)
            away_goals = scores.get("away", {}).get("total", 0)

            # For handicap, return the goal difference
            if self._is_home_team(bet, results):
                return home_goals - away_goals
            else:
                return away_goals - home_goals

        # Player props - OpticOdds doesn't provide player-level stats
        # These need manual verification
        if "player" in market:
            logger.info(f"Player prop needs manual verification: {bet.selection}")
            return None

        return None

    def _is_home_team(self, bet: TrackedBet, results: Dict[str, Any]) -> bool:
        """Check if bet selection is for home team."""
        fixture = results.get("fixture", {})
        home_name = fixture.get("home_team_display", "").lower()
        return home_name in bet.selection.lower()

    def _is_away_team(self, bet: TrackedBet, results: Dict[str, Any]) -> bool:
        """Check if bet selection is for away team."""
        fixture = results.get("fixture", {})
        away_name = fixture.get("away_team_display", "").lower()
        return away_name in bet.selection.lower()

    def _extract_line(self, selection: str) -> Optional[float]:
        """Extract the line from a selection string like 'Over 2.5'."""
        match = re.search(r"([\d.]+)", selection)
        if match:
            return float(match.group(1))
        return None
