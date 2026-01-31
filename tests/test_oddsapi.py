"""Tests for the Odds-API.io client."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from src.api.oddsapi import (
    OddsApiClient,
    OddsApiValueBet,
    OddsApiError,
    create_oddsapi_client,
)


class TestOddsApiValueBet:
    """Tests for OddsApiValueBet class."""

    def test_init_basic(self):
        """Test basic initialization from API data."""
        data = {
            "event": {
                "id": "evt_123",
                "sport": "football",
                "league": "Premier League",
                "homeTeam": "Arsenal",
                "awayTeam": "Chelsea",
                "startTime": "2024-01-15T15:00:00Z",
            },
            "market": {
                "name": "Corners Totals",
                "key": "corners_totals",
                "selection": "Over",
                "hdp": 9.5,
            },
            "bookmaker": "Bet365",
            "bookmakerOdds": {
                "decimal": 2.00,
                "american": 100,
                "href": "https://bet365.com/...",
            },
            "sharpOdds": {
                "decimal": 1.85,
                "american": -118,
            },
            "expectedValue": 108.11,
            "lastUpdate": "2024-01-15T14:53:00Z",
        }

        bet = OddsApiValueBet(data)

        assert bet.event_id == "evt_123"
        assert bet.sport == "football"
        assert bet.league == "Premier League"
        assert bet.home_team == "Arsenal"
        assert bet.away_team == "Chelsea"
        assert bet.market_name == "Corners Totals"
        assert bet.selection == "Over"
        assert bet.line == 9.5
        assert bet.bookmaker == "Bet365"
        assert bet.bookmaker_odds == 2.00
        assert bet.sharp_odds == 1.85
        assert bet.ev_percent == pytest.approx(8.11, abs=0.01)
        assert bet.betting_link == "https://bet365.com/..."

    def test_fixture_name(self):
        """Test fixture_name property."""
        data = {
            "event": {
                "homeTeam": "Arsenal",
                "awayTeam": "Chelsea",
            },
            "market": {},
            "bookmakerOdds": {},
            "sharpOdds": {},
        }
        bet = OddsApiValueBet(data)
        assert bet.fixture_name == "Arsenal vs Chelsea"

    def test_is_soccer(self):
        """Test is_soccer property."""
        soccer_data = {"event": {"sport": "football"}, "market": {}, "bookmakerOdds": {}, "sharpOdds": {}}
        bet = OddsApiValueBet(soccer_data)
        assert bet.is_soccer is True

        basketball_data = {"event": {"sport": "basketball"}, "market": {}, "bookmakerOdds": {}, "sharpOdds": {}}
        bet = OddsApiValueBet(basketball_data)
        assert bet.is_soccer is False

    def test_is_prop_market(self):
        """Test is_prop_market detection."""
        prop_markets = [
            "Corners Totals",
            "Bookings Spread",
            "Player Shots",
            "Team Cards",
            "Match Fouls",
        ]

        for market_name in prop_markets:
            data = {"event": {}, "market": {"name": market_name}, "bookmakerOdds": {}, "sharpOdds": {}}
            bet = OddsApiValueBet(data)
            assert bet.is_prop_market is True, f"Expected {market_name} to be prop market"

        # Non-prop markets
        non_prop_markets = ["Match Result", "Over Under Goals", "Asian Handicap"]
        for market_name in non_prop_markets:
            data = {"event": {}, "market": {"name": market_name}, "bookmakerOdds": {}, "sharpOdds": {}}
            bet = OddsApiValueBet(data)
            assert bet.is_prop_market is False, f"Expected {market_name} to NOT be prop market"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        data = {
            "event": {
                "id": "evt_123",
                "sport": "football",
                "league": "Premier League",
                "homeTeam": "Arsenal",
                "awayTeam": "Chelsea",
                "startTime": "2024-01-15T15:00:00Z",
            },
            "market": {
                "name": "Corners Totals",
                "key": "corners_totals",
                "selection": "Over 9.5",
                "hdp": 9.5,
            },
            "bookmaker": "Bet365",
            "bookmakerOdds": {"decimal": 2.00},
            "sharpOdds": {"decimal": 1.85},
            "expectedValue": 108.11,
        }

        bet = OddsApiValueBet(data)
        result = bet.to_dict()

        assert result["event_id"] == "evt_123"
        assert result["fixture_name"] == "Arsenal vs Chelsea"
        assert result["bookmaker"] == "Bet365"
        assert result["ev_percent"] == pytest.approx(8.11, abs=0.01)

    def test_missing_data_handling(self):
        """Test graceful handling of missing data."""
        minimal_data = {
            "event": {},
            "market": {},
            "bookmakerOdds": {},
            "sharpOdds": {},
        }

        bet = OddsApiValueBet(minimal_data)

        assert bet.event_id == ""
        assert bet.sport == ""
        assert bet.home_team == ""
        assert bet.bookmaker_odds == 0
        assert bet.ev_percent == 0


class TestOddsApiClient:
    """Tests for OddsApiClient class."""

    @pytest.fixture
    def client(self):
        """Create a client instance for testing."""
        return OddsApiClient(api_key="test_api_key")

    @pytest.mark.asyncio
    async def test_context_manager(self, client):
        """Test async context manager usage."""
        async with client as c:
            assert c.api_key == "test_api_key"
        # Client should be closed after exiting context

    @pytest.mark.asyncio
    async def test_request_adds_api_key(self, client):
        """Test that API key is added to all requests."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": []}
            mock_response.raise_for_status = MagicMock()

            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            await client._request("GET", "/test")

            # Verify API key was added to params
            call_args = mock_http_client.request.call_args
            assert call_args[1]["params"]["apiKey"] == "test_api_key"

    @pytest.mark.asyncio
    async def test_get_bookmakers(self, client):
        """Test fetching bookmakers list."""
        mock_response = {
            "data": [
                {"id": "bet365", "name": "Bet365", "active": True},
                {"id": "danskespil", "name": "DanskeSpil", "active": True},
            ]
        }

        with patch.object(client, "_request", return_value=mock_response) as mock_req:
            result = await client.get_bookmakers()

            mock_req.assert_called_once_with("GET", "/bookmakers")
            assert len(result) == 2
            assert result[0]["id"] == "bet365"

    @pytest.mark.asyncio
    async def test_get_value_bets_basic(self, client):
        """Test fetching value bets."""
        mock_response = {
            "data": [
                {
                    "event": {
                        "id": "evt_1",
                        "sport": "football",
                        "homeTeam": "Team A",
                        "awayTeam": "Team B",
                    },
                    "market": {"name": "Corners Totals"},
                    "bookmaker": "Bet365",
                    "bookmakerOdds": {"decimal": 2.00},
                    "sharpOdds": {"decimal": 1.85},
                    "expectedValue": 108.0,
                },
            ]
        }

        with patch.object(client, "_request", return_value=mock_response) as mock_req:
            result = await client.get_value_bets(bookmaker="Bet365", sport="football")

            mock_req.assert_called_once()
            call_params = mock_req.call_args[1]["params"]
            assert call_params["sport"] == "football"
            assert call_params["bookmaker"] == "Bet365"

            assert len(result) == 1
            assert isinstance(result[0], OddsApiValueBet)
            assert result[0].bookmaker == "Bet365"

    @pytest.mark.asyncio
    async def test_get_value_bets_with_min_ev_filter(self, client):
        """Test that min_ev filter is applied."""
        mock_response = {
            "data": [
                {
                    "event": {"sport": "football"},
                    "market": {},
                    "bookmakerOdds": {"decimal": 2.00},
                    "sharpOdds": {"decimal": 1.90},
                    "expectedValue": 105.0,  # 5% EV
                },
                {
                    "event": {"sport": "football"},
                    "market": {},
                    "bookmakerOdds": {"decimal": 2.00},
                    "sharpOdds": {"decimal": 1.85},
                    "expectedValue": 108.0,  # 8% EV
                },
            ]
        }

        with patch.object(client, "_request", return_value=mock_response):
            # Filter for min 6% EV
            result = await client.get_value_bets(min_ev=6.0)

            # Should only return the 8% EV bet
            assert len(result) == 1
            assert result[0].ev_percent >= 6.0

    @pytest.mark.asyncio
    async def test_get_soccer_prop_value_bets(self, client):
        """Test fetching soccer prop value bets with all filters."""
        mock_response = {
            "data": [
                {
                    "event": {"sport": "football"},
                    "market": {"name": "Corners Totals"},
                    "bookmaker": "Bet365",
                    "bookmakerOdds": {"decimal": 2.00},
                    "sharpOdds": {"decimal": 1.85},
                    "expectedValue": 108.0,
                },
                {
                    "event": {"sport": "football"},
                    "market": {"name": "Match Result"},  # Not a prop
                    "bookmaker": "Bet365",
                    "bookmakerOdds": {"decimal": 2.00},
                    "sharpOdds": {"decimal": 1.85},
                    "expectedValue": 108.0,
                },
                {
                    "event": {"sport": "basketball"},  # Not soccer
                    "market": {"name": "Corners Totals"},
                    "bookmakerOdds": {"decimal": 2.00},
                    "sharpOdds": {"decimal": 1.85},
                    "expectedValue": 108.0,
                },
            ]
        }

        with patch.object(client, "get_value_bets", return_value=[
            OddsApiValueBet(d) for d in mock_response["data"]
        ]):
            result = await client.get_soccer_prop_value_bets(
                bookmakers=["Bet365"],
                min_ev=5.0,
                max_ev=25.0,
            )

            # Should only return soccer prop bets
            assert all(b.is_soccer for b in result)
            assert all(b.is_prop_market for b in result)

    @pytest.mark.asyncio
    async def test_get_events(self, client):
        """Test fetching events."""
        mock_response = {
            "data": [
                {"id": "evt_1", "homeTeam": "Arsenal", "awayTeam": "Chelsea"},
                {"id": "evt_2", "homeTeam": "Liverpool", "awayTeam": "Man United"},
            ]
        }

        with patch.object(client, "_request", return_value=mock_response) as mock_req:
            result = await client.get_events(sport="football", league="premier-league")

            mock_req.assert_called_once()
            call_params = mock_req.call_args[1]["params"]
            assert call_params["sport"] == "football"
            assert call_params["league"] == "premier-league"

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_odds_multi(self, client):
        """Test fetching odds for multiple events."""
        mock_response = {
            "data": [
                {"eventId": "evt_1", "odds": [{"market": "corners", "price": 2.00}]},
                {"eventId": "evt_2", "odds": [{"market": "corners", "price": 1.90}]},
            ]
        }

        with patch.object(client, "_request", return_value=mock_response) as mock_req:
            result = await client.get_odds_multi(
                event_ids=["evt_1", "evt_2"],
                bookmakers=["bet365"],
            )

            mock_req.assert_called_once()
            call_params = mock_req.call_args[1]["params"]
            assert call_params["eventIds"] == "evt_1,evt_2"
            assert call_params["bookmakers"] == "bet365"

            assert "evt_1" in result
            assert "evt_2" in result

    @pytest.mark.asyncio
    async def test_get_odds_multi_limits_to_10(self, client):
        """Test that get_odds_multi limits to 10 events."""
        event_ids = [f"evt_{i}" for i in range(15)]

        with patch.object(client, "_request", return_value={"data": []}) as mock_req:
            await client.get_odds_multi(event_ids=event_ids)

            call_params = mock_req.call_args[1]["params"]
            requested_ids = call_params["eventIds"].split(",")
            assert len(requested_ids) == 10

    @pytest.mark.asyncio
    async def test_api_error_handling(self, client):
        """Test error handling for API errors."""
        import httpx

        with patch.object(client, "_get_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                message="401",
                request=MagicMock(),
                response=mock_response,
            )

            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            with pytest.raises(OddsApiError):
                await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_check_api_status_success(self, client):
        """Test API status check - success case."""
        with patch.object(client, "_request", return_value={"data": []}):
            result = await client.check_api_status()
            assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_check_api_status_failure(self, client):
        """Test API status check - failure case."""
        with patch.object(client, "_request", side_effect=OddsApiError("Connection failed")):
            result = await client.check_api_status()
            assert result["status"] == "error"
            assert "Connection failed" in result["message"]


class TestCreateOddsApiClient:
    """Tests for factory function."""

    def test_create_client(self):
        """Test factory function creates client correctly."""
        client = create_oddsapi_client("my_api_key")

        assert isinstance(client, OddsApiClient)
        assert client.api_key == "my_api_key"


class TestDanishBookmakers:
    """Tests for Danish bookmaker configuration."""

    def test_danish_bookmakers_defined(self):
        """Test that Danish bookmakers are defined."""
        assert len(OddsApiClient.DANISH_BOOKMAKERS) > 0
        assert "bet365" in OddsApiClient.DANISH_BOOKMAKERS
        assert "danskespil" in OddsApiClient.DANISH_BOOKMAKERS

    def test_prop_markets_defined(self):
        """Test that prop markets are defined."""
        assert len(OddsApiClient.PROP_MARKETS) > 0
        assert any("corner" in m.lower() for m in OddsApiClient.PROP_MARKETS)
        assert any("booking" in m.lower() or "card" in m.lower() for m in OddsApiClient.PROP_MARKETS)
