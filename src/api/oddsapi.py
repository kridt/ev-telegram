"""Odds-API.io client for value betting detection.

This client integrates with the Odds-API.io API to fetch:
- Pre-calculated value bets with EV
- Events/fixtures for soccer
- Odds from multiple bookmakers

API Documentation: https://docs.odds-api.io/
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .models import (
    Fixture,
    League,
    OddsData,
    Team,
)

logger = logging.getLogger(__name__)


class OddsApiError(Exception):
    """Exception raised for Odds-API.io errors."""
    pass


class OddsApiValueBet:
    """Represents a value bet from Odds-API.io /value-bets endpoint."""

    def __init__(self, data: Dict[str, Any]):
        """Initialize from API response data."""
        self.raw = data

        # Event info - API returns eventId at top level, not nested in event object
        event = data.get("event", {})
        self.event_id = str(data.get("eventId", "") or event.get("id", ""))
        self.sport = event.get("sport", "")
        self.league = event.get("league", "")
        self.home_team = event.get("homeTeam", "")
        self.away_team = event.get("awayTeam", "")
        self.start_time = self._parse_datetime(event.get("startTime"))

        # Market info
        market = data.get("market", {})
        self.market_name = market.get("name", "")
        self.market_key = market.get("key", "")
        self.selection = market.get("selection", "")
        self.line = market.get("hdp")  # Handicap/line value
        self.bet_side = data.get("betSide", "")  # e.g., "over", "under", "home", "away"

        # Odds info
        self.bookmaker = data.get("bookmaker", "")
        odds_data = data.get("bookmakerOdds", {})
        self.betting_link = odds_data.get("href", "")

        # Get the correct odds based on bet side (home/away/over/under)
        bet_side = self.bet_side.lower() if self.bet_side else ""
        if bet_side in ("home", "over", "1"):
            self.bookmaker_odds = float(odds_data.get("home", 0) or odds_data.get("over", 0) or 0)
        elif bet_side in ("away", "under", "2"):
            self.bookmaker_odds = float(odds_data.get("away", 0) or odds_data.get("under", 0) or 0)
        else:
            # Fallback: try decimal, or first available numeric value
            self.bookmaker_odds = float(
                odds_data.get("decimal", 0) or
                odds_data.get("home", 0) or
                odds_data.get("away", 0) or 0
            )

        self.bookmaker_american = odds_data.get("american")

        # Sharp odds from market data (consensus/fair value)
        market_data = data.get("market", {})
        if bet_side in ("home", "over", "1"):
            self.sharp_odds = float(market_data.get("home", 0) or market_data.get("over", 0) or 0)
        elif bet_side in ("away", "under", "2"):
            self.sharp_odds = float(market_data.get("away", 0) or market_data.get("under", 0) or 0)
        else:
            self.sharp_odds = float(
                data.get("sharpOdds", {}).get("decimal", 0) or
                market_data.get("home", 0) or
                market_data.get("away", 0) or 0
            )
        self.sharp_american = data.get("sharpOdds", {}).get("american")

        # Expected value
        self.expected_value = float(data.get("expectedValue", 0))
        self.ev_percent = (self.expected_value - 100) if self.expected_value > 0 else 0

        # Timestamp (API uses expectedValueUpdatedAt)
        self.last_update = self._parse_datetime(
            data.get("expectedValueUpdatedAt") or data.get("lastUpdate")
        )

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    @property
    def fixture_name(self) -> str:
        """Get display name for the fixture."""
        return f"{self.home_team} vs {self.away_team}"

    @property
    def is_soccer(self) -> bool:
        """Check if this is a soccer/football bet."""
        return self.sport.lower() in ("soccer", "football")

    @property
    def is_prop_market(self) -> bool:
        """Check if this is a prop market (corners, cards, shots)."""
        prop_keywords = [
            "corner", "booking", "card", "shot", "foul",
            "throw", "offside", "tackle", "save"
        ]
        market_lower = self.market_name.lower()
        return any(kw in market_lower for kw in prop_keywords)

    @property
    def is_fresh(self) -> bool:
        """Check if odds were updated recently (< 5 minutes)."""
        if not self.last_update:
            return False
        now = datetime.now(timezone.utc)
        age = (now - self.last_update).total_seconds()
        return age < 300  # 5 minutes

    @property
    def age_seconds(self) -> Optional[float]:
        """Get age of odds in seconds."""
        if not self.last_update:
            return None
        now = datetime.now(timezone.utc)
        return (now - self.last_update).total_seconds()

    @property
    def selection_display(self) -> str:
        """Get formatted selection with line."""
        if self.bet_side:
            side = self.bet_side.capitalize()
            if self.line is not None:
                return f"{side} {self.line}"
            return side
        if self.selection:
            if self.line is not None:
                return f"{self.selection} {self.line}"
            return self.selection
        return str(self.line) if self.line is not None else "Unknown"

    def enrich_with_event(self, event_data: Dict[str, Any]) -> None:
        """Enrich this value bet with event data from /events/{id} endpoint.

        Args:
            event_data: Event object from the API containing home/away/league info
        """
        if not event_data:
            return

        self.home_team = event_data.get("home", self.home_team)
        self.away_team = event_data.get("away", self.away_team)

        # League can be nested or a string
        league_data = event_data.get("league")
        if isinstance(league_data, dict):
            self.league = league_data.get("name", self.league)
        elif isinstance(league_data, str):
            self.league = league_data

        # Sport can be nested or a string
        sport_data = event_data.get("sport")
        if isinstance(sport_data, dict):
            self.sport = sport_data.get("slug", self.sport) or sport_data.get("name", self.sport)
        elif isinstance(sport_data, str):
            self.sport = sport_data

        # Date/start time
        if not self.start_time and event_data.get("date"):
            self.start_time = self._parse_datetime(event_data.get("date"))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "fixture_name": self.fixture_name,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "league": self.league,
            "sport": self.sport,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "market_name": self.market_name,
            "market_key": self.market_key,
            "selection": self.selection,
            "line": self.line,
            "bookmaker": self.bookmaker,
            "bookmaker_odds": self.bookmaker_odds,
            "sharp_odds": self.sharp_odds,
            "ev_percent": round(self.ev_percent, 2),
            "betting_link": self.betting_link,
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }


class OddsApiClient:
    """Client for the Odds-API.io API.

    Provides access to:
    - /value-bets: Pre-calculated value betting opportunities
    - /events: Upcoming fixtures/events
    - /odds/multi: Odds from multiple bookmakers
    - /bookmakers: Available bookmakers
    """

    BASE_URL = "https://api2.odds-api.io/v3"

    # Danish bookmakers for placing bets
    DANISH_BOOKMAKERS = [
        "Bet365",
        "DanskeSpil",
        "Unibet DK",
        "Coolbet",
        "Betano DK",
        "NordicBet DK",
        "Betsson",
        "LeoVegas",
        "Betinia DK",
        "Campobet DK",
    ]

    # Sharp bookmakers for EV calculation
    SHARP_BOOKMAKERS = [
        "Pinnacle",
        "Betfair Exchange",
        "Circa",
        "Sharp Exchange",
    ]

    # Reference bookmakers for market consensus
    REFERENCE_BOOKMAKERS = [
        "888Sport",
        "Bwin",
        "Betway",
        "WilliamHill",
        "Ladbrokes",
        "Paddy Power",
    ]

    # Prop markets we're interested in
    PROP_MARKETS = [
        "Corners Totals",
        "Corners Spread",
        "Corners Totals HT",
        "Bookings Totals",
        "Bookings Spread",
        "Team Shots on Target",
        "Match Shots",
        "Player Shots",
        "Player Cards",
        "Player Fouls",
    ]

    def __init__(self, api_key: str, timeout: float = 60.0):
        """
        Initialize the Odds-API.io client.

        Args:
            api_key: Odds-API.io API key
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
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an API request.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters (apiKey added automatically)

        Returns:
            JSON response as dictionary
        """
        client = await self._get_client()

        # Add API key to params
        if params is None:
            params = {}
        params["apiKey"] = self.api_key

        try:
            response = await client.request(method, endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text[:500]}")
            raise OddsApiError(f"API error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise OddsApiError(f"Request failed: {e}") from e

    async def get_bookmakers(self) -> List[Dict[str, Any]]:
        """Get list of available bookmakers.

        Returns:
            List of bookmaker objects with id, name, active status
        """
        data = await self._request("GET", "/bookmakers")
        # API returns list directly
        return data if isinstance(data, list) else data.get("data", [])

    async def get_value_bets(
        self,
        bookmaker: Optional[str] = None,
        sport: str = "football",
        min_ev: float = 0,
    ) -> List[OddsApiValueBet]:
        """Get pre-calculated value bets.

        Args:
            bookmaker: Optional bookmaker filter (e.g., "Bet365")
            sport: Sport filter (default: "football")
            min_ev: Minimum expected value percentage

        Returns:
            List of OddsApiValueBet objects
        """
        params = {"sport": sport}
        if bookmaker:
            params["bookmaker"] = bookmaker

        data = await self._request("GET", "/value-bets", params=params)

        # API returns list directly, not wrapped in "data"
        items = data if isinstance(data, list) else data.get("data", [])

        value_bets = []
        for item in items:
            bet = OddsApiValueBet(item)
            # Filter by minimum EV
            if bet.ev_percent >= min_ev:
                value_bets.append(bet)

        logger.info(f"Fetched {len(value_bets)} value bets (min EV: {min_ev}%)")
        return value_bets

    async def get_soccer_prop_value_bets(
        self,
        bookmakers: Optional[List[str]] = None,
        min_ev: float = 5.0,
        max_ev: float = 25.0,
    ) -> List[OddsApiValueBet]:
        """Get soccer prop market value bets from Danish bookmakers.

        This is the main method for our value betting system.
        Filters for:
        - Soccer/football only
        - Prop markets (corners, cards, shots, etc.)
        - Danish bookmakers
        - EV within specified range

        Args:
            bookmakers: List of bookmakers to check (default: all Danish)
            min_ev: Minimum EV percentage (default: 5%)
            max_ev: Maximum EV percentage (default: 25%)

        Returns:
            List of filtered OddsApiValueBet objects
        """
        if bookmakers is None:
            bookmakers = self.DANISH_BOOKMAKERS

        all_bets = []

        for bookmaker in bookmakers:
            try:
                bets = await self.get_value_bets(
                    bookmaker=bookmaker,
                    sport="football",
                    min_ev=0,  # We'll filter after
                )
                all_bets.extend(bets)
            except OddsApiError as e:
                logger.warning(f"Failed to fetch value bets for {bookmaker}: {e}")
                continue

        # Filter for prop markets and EV range
        filtered = []
        for bet in all_bets:
            # Must be soccer
            if not bet.is_soccer:
                continue

            # Must be prop market
            if not bet.is_prop_market:
                continue

            # Must be within EV range
            if not (min_ev <= bet.ev_percent <= max_ev):
                continue

            filtered.append(bet)

        # Sort by EV descending
        filtered.sort(key=lambda x: x.ev_percent, reverse=True)

        logger.info(
            f"Found {len(filtered)} soccer prop value bets "
            f"(EV range: {min_ev}%-{max_ev}%)"
        )
        return filtered

    async def get_events(
        self,
        sport: str = "football",
        league: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get upcoming events/fixtures.

        Args:
            sport: Sport type (default: football)
            league: Optional league filter (e.g., "england-premier-league")

        Returns:
            List of event objects
        """
        params = {"sport": sport}
        if league:
            params["league"] = league

        data = await self._request("GET", "/events", params=params)
        # API returns list directly
        return data if isinstance(data, list) else data.get("data", [])

    async def get_event_by_id(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Get a single event by its ID.

        Args:
            event_id: The event ID from value-bets response

        Returns:
            Event object with home/away team names, or None if not found
        """
        try:
            data = await self._request("GET", f"/events/{event_id}")
            return data if isinstance(data, dict) else None
        except OddsApiError:
            return None

    async def get_events_by_ids(
        self,
        event_ids: List[int],
        batch_size: int = 10,
    ) -> Dict[int, Dict[str, Any]]:
        """Get multiple events by their IDs.

        Args:
            event_ids: List of event IDs
            batch_size: Number of concurrent requests

        Returns:
            Dict mapping event_id to event data
        """
        results = {}

        # Process in batches to avoid overwhelming the API
        for i in range(0, len(event_ids), batch_size):
            batch = event_ids[i:i + batch_size]
            tasks = [self.get_event_by_id(eid) for eid in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for eid, result in zip(batch, batch_results):
                if isinstance(result, dict):
                    results[eid] = result

        return results

    async def get_odds_multi(
        self,
        event_ids: List[str],
        bookmakers: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get odds for multiple events at once.

        Args:
            event_ids: List of event IDs (max 10 per call)
            bookmakers: List of bookmakers to fetch

        Returns:
            Dict mapping event_id to list of odds
        """
        if not event_ids:
            return {}

        # API limit: 10 events per call
        event_ids = event_ids[:10]

        params = {
            "eventIds": ",".join(event_ids),
        }
        if bookmakers:
            params["bookmakers"] = ",".join(bookmakers)

        data = await self._request("GET", "/odds/multi", params=params)

        # API returns list directly
        items = data if isinstance(data, list) else data.get("data", [])

        # Organize by event ID
        result = {}
        for item in items:
            event_id = item.get("eventId", "")
            if event_id:
                result[event_id] = item.get("odds", [])

        return result

    async def check_api_status(self) -> Dict[str, Any]:
        """Check API status and remaining quota.

        Returns:
            Dict with status info
        """
        try:
            # Make a minimal request to check status
            await self._request("GET", "/bookmakers")
            return {"status": "ok", "message": "API is reachable"}
        except OddsApiError as e:
            return {"status": "error", "message": str(e)}


# Factory function for easy creation
def create_oddsapi_client(api_key: str) -> OddsApiClient:
    """Create an Odds-API.io client.

    Args:
        api_key: Odds-API.io API key

    Returns:
        Configured OddsApiClient instance
    """
    return OddsApiClient(api_key=api_key)
