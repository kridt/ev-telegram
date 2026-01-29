"""Tests for OpticOdds API client."""

from datetime import datetime, timedelta, timezone

import pytest
import httpx
from pytest_httpx import HTTPXMock

from src.api.opticodds import OpticOddsClient, OpticOddsError
from src.api.models import Fixture, Odds, Market, Sportsbook


class TestOpticOddsClient:
    """Tests for the OpticOdds API client."""

    @pytest.fixture
    def client(self):
        """Create a client instance."""
        return OpticOddsClient(api_key="test_api_key")

    @pytest.fixture
    def mock_fixtures_response(self):
        """Sample fixtures response."""
        return {
            "data": [
                {
                    "id": "fixture_1",
                    "league": {"id": "premier-league", "name": "Premier League"},
                    "home_team": {"id": "mci", "name": "Manchester City"},
                    "away_team": {"id": "ars", "name": "Arsenal"},
                    "start_date": (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat(),
                    "status": "scheduled",
                },
                {
                    "id": "fixture_2",
                    "league": {"id": "la-liga", "name": "La Liga"},
                    "home_team": {"id": "rma", "name": "Real Madrid"},
                    "away_team": {"id": "bar", "name": "Barcelona"},
                    "start_date": (datetime.now(timezone.utc) + timedelta(hours=10)).isoformat(),
                    "status": "scheduled",
                },
            ]
        }

    @pytest.fixture
    def mock_odds_response(self):
        """Sample odds response."""
        return {
            "data": [
                {
                    "market": {"id": "total_goals", "name": "Total Goals O/U 2.5"},
                    "sportsbook": {"id": "bet365", "name": "Bet365"},
                    "outcomes": [
                        {"name": "Over 2.5", "odds": 1.90, "line": 2.5},
                        {"name": "Under 2.5", "odds": 1.90, "line": 2.5},
                    ],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "market": {"id": "total_goals", "name": "Total Goals O/U 2.5"},
                    "sportsbook": {"id": "draftkings", "name": "DraftKings"},
                    "outcomes": [
                        {"name": "Over 2.5", "odds": 1.95, "line": 2.5},
                        {"name": "Under 2.5", "odds": 1.87, "line": 2.5},
                    ],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            ]
        }

    @pytest.mark.asyncio
    async def test_get_fixtures(self, client, httpx_mock: HTTPXMock, mock_fixtures_response):
        """Test fetching fixtures."""
        httpx_mock.add_response(
            url="https://api.opticodds.com/api/v3/fixtures/active",
            json=mock_fixtures_response,
        )

        fixtures = await client.get_fixtures(sport="soccer", hours_ahead=24)
        await client.close()

        assert len(fixtures) == 2
        assert fixtures[0].id == "fixture_1"
        assert fixtures[0].home_team.name == "Manchester City"
        assert fixtures[1].league.name == "La Liga"

    @pytest.mark.asyncio
    async def test_get_fixtures_filters_by_time(self, client, httpx_mock: HTTPXMock):
        """Test that fixtures beyond time window are filtered."""
        far_future = datetime.now(timezone.utc) + timedelta(hours=48)
        response = {
            "data": [
                {
                    "id": "fixture_1",
                    "league": {"id": "pl", "name": "Premier League"},
                    "home_team": {"id": "a", "name": "Team A"},
                    "away_team": {"id": "b", "name": "Team B"},
                    "start_date": far_future.isoformat(),
                    "status": "scheduled",
                },
            ]
        }

        httpx_mock.add_response(json=response)

        fixtures = await client.get_fixtures(hours_ahead=24)  # Only 24 hours
        await client.close()

        assert len(fixtures) == 0  # Fixture is beyond window

    @pytest.mark.asyncio
    async def test_get_odds(self, client, httpx_mock: HTTPXMock, mock_odds_response):
        """Test fetching odds for a fixture."""
        httpx_mock.add_response(
            url="https://api.opticodds.com/api/v3/fixtures/odds",
            json=mock_odds_response,
        )

        odds = await client.get_odds("fixture_1")
        await client.close()

        assert len(odds) == 1  # Grouped by market
        assert odds[0].market_id == "total_goals"
        assert len(odds[0].bookmaker_odds) == 2

        bet365 = next(b for b in odds[0].bookmaker_odds if b.sportsbook_name == "Bet365")
        assert len(bet365.outcomes) == 2
        assert bet365.outcomes[0].odds == 1.90

    @pytest.mark.asyncio
    async def test_get_sportsbooks(self, client, httpx_mock: HTTPXMock):
        """Test fetching sportsbooks."""
        httpx_mock.add_response(
            json={
                "data": [
                    {"id": "bet365", "name": "Bet365"},
                    {"id": "draftkings", "name": "DraftKings"},
                ]
            }
        )

        sportsbooks = await client.get_sportsbooks()
        await client.close()

        assert len(sportsbooks) == 2
        assert sportsbooks[0].id == "bet365"

    @pytest.mark.asyncio
    async def test_get_markets(self, client, httpx_mock: HTTPXMock):
        """Test fetching markets."""
        httpx_mock.add_response(
            json={
                "data": [
                    {"id": "total_goals", "name": "Total Goals", "description": "Over/Under"},
                    {"id": "player_shots", "name": "Player Shots", "description": "Shots props"},
                ]
            }
        )

        markets = await client.get_markets(sport="soccer")
        await client.close()

        assert len(markets) == 2
        assert markets[0].id == "total_goals"
        assert markets[1].name == "Player Shots"

    @pytest.mark.asyncio
    async def test_api_error_handling(self, client, httpx_mock: HTTPXMock):
        """Test handling of API errors."""
        httpx_mock.add_response(status_code=401, json={"error": "Unauthorized"})

        with pytest.raises(OpticOddsError):
            await client.get_fixtures()

        await client.close()

    @pytest.mark.asyncio
    async def test_request_timeout(self, client, httpx_mock: HTTPXMock):
        """Test handling of request timeouts."""
        httpx_mock.add_exception(httpx.TimeoutException("Timeout"))

        with pytest.raises(OpticOddsError):
            await client.get_fixtures()

        await client.close()

    @pytest.mark.asyncio
    async def test_headers_include_api_key(self, client, httpx_mock: HTTPXMock):
        """Test that API key is included in headers."""
        httpx_mock.add_response(json={"data": []})

        await client.get_fixtures()
        await client.close()

        request = httpx_mock.get_requests()[0]
        assert request.headers["X-Api-Key"] == "test_api_key"


class TestOddsModel:
    """Tests for Odds model."""

    def test_get_all_odds_for_outcome(self):
        """Test getting all odds for a specific outcome."""
        from src.api.models import Odds, BookOdds, OddsOutcome

        odds = Odds(
            fixture_id="123",
            market_id="total_goals",
            market_name="Total Goals",
            bookmaker_odds=[
                BookOdds(
                    sportsbook_id="book1",
                    sportsbook_name="Book1",
                    outcomes=[
                        OddsOutcome(name="Over 2.5", odds=1.90),
                        OddsOutcome(name="Under 2.5", odds=1.90),
                    ],
                ),
                BookOdds(
                    sportsbook_id="book2",
                    sportsbook_name="Book2",
                    outcomes=[
                        OddsOutcome(name="Over 2.5", odds=1.95),
                        OddsOutcome(name="Under 2.5", odds=1.85),
                    ],
                ),
            ],
        )

        over_odds = odds.get_all_odds_for_outcome("Over 2.5")

        assert len(over_odds) == 2
        assert ("Book1", 1.90) in over_odds
        assert ("Book2", 1.95) in over_odds


class TestFixtureModel:
    """Tests for Fixture model."""

    def test_display_name(self):
        """Test fixture display name."""
        from src.api.models import Fixture, Team, League

        fixture = Fixture(
            id="123",
            league=League(id="pl", name="Premier League"),
            home_team=Team(id="mci", name="Man City"),
            away_team=Team(id="ars", name="Arsenal"),
        )

        assert fixture.display_name == "Man City vs Arsenal"
