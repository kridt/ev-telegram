"""OpticOdds API client - Updated with real API structure."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from .models import (
    Fixture,
    OddsData,
    Team,
    League,
)

logger = logging.getLogger(__name__)


class OpticOddsError(Exception):
    """Exception raised for OpticOdds API errors."""
    pass


class OpticOddsClient:
    """Client for the OpticOdds API."""

    BASE_URL = "https://api.opticodds.com/api/v3"

    def __init__(self, api_key: str, timeout: float = 60.0):
        """
        Initialize the OpticOdds client.

        Args:
            api_key: OpticOdds API key
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "x-api-key": self.api_key,
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an API request."""
        client = await self._get_client()

        try:
            response = await client.request(method, endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text[:500]}")
            raise OpticOddsError(f"API error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise OpticOddsError(f"Request failed: {e}") from e

    async def get_sportsbooks(self) -> List[Dict[str, Any]]:
        """Get list of available sportsbooks."""
        data = await self._request("GET", "/sportsbooks")
        return data.get("data", [])

    async def get_markets(self, sport: str = "soccer") -> List[Dict[str, Any]]:
        """Get available market types for a sport."""
        data = await self._request("GET", "/markets", params={"sport": sport})
        return data.get("data", [])

    async def get_leagues(self, sport: str = "soccer") -> List[Dict[str, Any]]:
        """Get available leagues for a sport."""
        data = await self._request("GET", "/leagues", params={"sport": sport})
        return data.get("data", [])

    async def get_fixtures(
        self,
        sport: str = "soccer",
        league: Optional[str] = None,
        hours_ahead: int = 24,
        include_live: bool = False,
    ) -> List[Fixture]:
        """
        Get upcoming fixtures.

        Args:
            sport: Sport type (default: soccer)
            league: Optional league filter (e.g., "england_-_premier_league")
            hours_ahead: How many hours ahead to look
            include_live: Whether to include live matches

        Returns:
            List of upcoming fixtures
        """
        params = {"sport": sport}

        if league:
            params["league"] = league

        data = await self._request("GET", "/fixtures/active", params=params)

        fixtures = []
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours_ahead)

        for item in data.get("data", []):
            # Skip live matches if not wanted
            if not include_live and item.get("is_live", False):
                continue

            # Parse start date
            start_date = None
            if item.get("start_date"):
                try:
                    start_date = datetime.fromisoformat(
                        item["start_date"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Filter by time window
            if start_date and start_date > cutoff:
                continue

            # Extract team info
            home_competitors = item.get("home_competitors", [])
            away_competitors = item.get("away_competitors", [])

            home_team = Team(
                id=home_competitors[0].get("id", "") if home_competitors else "",
                name=item.get("home_team_display", ""),
            )
            away_team = Team(
                id=away_competitors[0].get("id", "") if away_competitors else "",
                name=item.get("away_team_display", ""),
            )

            league_info = item.get("league", {})

            fixture = Fixture(
                id=item.get("id", ""),
                sport=sport,
                league=League(
                    id=league_info.get("id", ""),
                    name=league_info.get("name", ""),
                ),
                home_team=home_team,
                away_team=away_team,
                start_date=start_date,
                status=item.get("status", "scheduled"),
                is_live=item.get("is_live", False),
            )
            fixtures.append(fixture)

        logger.info(f"Fetched {len(fixtures)} fixtures for {league or 'all leagues'}")
        return fixtures

    async def get_odds(
        self,
        fixture_id: str,
        sportsbooks: List[str],
        markets: Optional[List[str]] = None,
    ) -> List[OddsData]:
        """
        Get odds for a fixture.

        Args:
            fixture_id: Fixture ID
            sportsbooks: List of sportsbook IDs to fetch
            markets: Optional list of market types to filter

        Returns:
            List of odds data
        """
        if not sportsbooks:
            raise ValueError("At least one sportsbook is required")

        # Build params with multiple sportsbook entries (API requires this format)
        params = [("fixture_id", fixture_id)]
        for book in sportsbooks:
            params.append(("sportsbook", book))

        if markets:
            for market in markets:
                params.append(("market", market))

        data = await self._request("GET", "/fixtures/odds", params=params)

        odds_list = []
        for fixture_data in data.get("data", []):
            for odd in fixture_data.get("odds", []):
                odds_list.append(OddsData(
                    id=odd.get("id", ""),
                    fixture_id=fixture_id,
                    sportsbook=odd.get("sportsbook", ""),
                    market=odd.get("market", ""),
                    name=odd.get("name", ""),
                    selection=odd.get("selection", ""),
                    price=odd.get("price", 0),
                    points=odd.get("points"),
                    player_id=odd.get("player_id"),
                    team_id=odd.get("team_id"),
                    is_main=odd.get("is_main", True),
                    timestamp=odd.get("timestamp"),
                ))

        logger.debug(f"Fetched {len(odds_list)} odds for fixture {fixture_id}")
        return odds_list

    async def get_fixture_with_odds(
        self,
        fixture: Fixture,
        sportsbooks: List[str],
        markets: Optional[List[str]] = None,
    ) -> tuple[Fixture, List[OddsData]]:
        """
        Get a fixture with all its odds.

        Args:
            fixture: The fixture
            sportsbooks: List of sportsbooks
            markets: Optional market filter

        Returns:
            Tuple of (fixture, odds_list)
        """
        odds = await self.get_odds(fixture.id, sportsbooks, markets)
        return fixture, odds
