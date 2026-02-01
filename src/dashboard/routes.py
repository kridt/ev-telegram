"""API routes for the dashboard."""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..utils.config import ConfigManager, Settings

logger = logging.getLogger(__name__)


class SettingsUpdate(BaseModel):
    """Model for settings update requests."""
    min_edge_percent: float | None = None
    refresh_interval_minutes: int | None = None
    hours_ahead: int | None = None
    telegram: Dict[str, str] | None = None
    leagues: List[str] | None = None
    markets: List[str] | None = None


def get_config_manager(request: Request) -> ConfigManager:
    """Get the config manager from app state."""
    return request.app.state.config_manager


def get_value_bets(request: Request) -> list:
    """Get the value bets store from app state."""
    return request.app.state.value_bets


def get_fixtures(request: Request) -> list:
    """Get the fixtures store from app state."""
    return request.app.state.fixtures


def create_router() -> APIRouter:
    """Create the API router with all endpoints."""
    router = APIRouter()

    @router.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    @router.get("/value-bets")
    async def list_value_bets(
        min_edge: float | None = None,
        league: str | None = None,
        value_bets: list = Depends(get_value_bets),
    ) -> List[Dict[str, Any]]:
        """
        Get current value bets.

        Args:
            min_edge: Optional minimum edge filter
            league: Optional league filter

        Returns:
            List of value bets
        """
        result = []

        for bet in value_bets:
            # Convert ValueBet to dict if needed
            bet_dict = bet.to_dict() if hasattr(bet, "to_dict") else bet

            # Apply filters
            if min_edge is not None and bet_dict.get("edge_percent", 0) < min_edge:
                continue
            if league is not None and bet_dict.get("league", "").lower() != league.lower():
                continue

            result.append(bet_dict)

        # Sort by edge, highest first
        result.sort(key=lambda x: x.get("edge_percent", 0), reverse=True)

        return result

    @router.get("/fixtures")
    async def list_fixtures(
        league: str | None = None,
        fixtures: list = Depends(get_fixtures),
    ) -> List[Dict[str, Any]]:
        """
        Get current fixtures being monitored.

        Args:
            league: Optional league filter

        Returns:
            List of fixtures
        """
        result = []

        for fixture in fixtures:
            # Convert Fixture to dict if needed
            if hasattr(fixture, "model_dump"):
                fixture_dict = fixture.model_dump()
            elif hasattr(fixture, "dict"):
                fixture_dict = fixture.dict()
            else:
                fixture_dict = fixture

            # Apply league filter
            if league is not None:
                fixture_league = fixture_dict.get("league", {}).get("name", "")
                if fixture_league.lower() != league.lower():
                    continue

            result.append(fixture_dict)

        return result

    @router.get("/settings")
    async def get_settings(
        config_manager: ConfigManager = Depends(get_config_manager),
    ) -> Dict[str, Any]:
        """Get current settings."""
        settings = config_manager.get_settings()
        return settings.model_dump()

    @router.post("/settings")
    async def update_settings(
        updates: SettingsUpdate,
        config_manager: ConfigManager = Depends(get_config_manager),
    ) -> Dict[str, Any]:
        """
        Update settings.

        Args:
            updates: Settings to update

        Returns:
            Updated settings
        """
        try:
            # Convert to dict, excluding None values
            update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}

            new_settings = config_manager.update_settings(update_dict)
            logger.info(f"Settings updated: {update_dict.keys()}")

            return new_settings.model_dump()
        except Exception as e:
            logger.error(f"Failed to update settings: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/bookmakers")
    async def list_bookmakers(
        config_manager: ConfigManager = Depends(get_config_manager),
    ) -> Dict[str, Any]:
        """Get configured bookmakers."""
        bookmakers = config_manager.get_bookmakers()
        return bookmakers.model_dump()

    @router.get("/leagues")
    async def list_leagues() -> List[Dict[str, str]]:
        """Get available leagues."""
        # This could be expanded to fetch from Odds-API.io
        return [
            {"id": "premier-league", "name": "Premier League"},
            {"id": "la-liga", "name": "La Liga"},
            {"id": "bundesliga", "name": "Bundesliga"},
            {"id": "serie-a", "name": "Serie A"},
            {"id": "ligue-1", "name": "Ligue 1"},
            {"id": "champions-league", "name": "Champions League"},
            {"id": "europa-league", "name": "Europa League"},
            {"id": "mls", "name": "MLS"},
            {"id": "eredivisie", "name": "Eredivisie"},
            {"id": "primeira-liga", "name": "Primeira Liga"},
        ]

    @router.get("/markets")
    async def list_markets() -> List[Dict[str, str]]:
        """Get available market types."""
        return [
            {"id": "player_shots", "name": "Player Shots"},
            {"id": "player_shots_on_target", "name": "Player Shots on Target"},
            {"id": "player_goals", "name": "Player Goals"},
            {"id": "player_assists", "name": "Player Assists"},
            {"id": "player_tackles", "name": "Player Tackles"},
            {"id": "player_passes", "name": "Player Passes"},
            {"id": "player_fouls", "name": "Player Fouls"},
            {"id": "player_cards", "name": "Player Cards"},
            {"id": "total_goals", "name": "Total Goals"},
            {"id": "btts", "name": "Both Teams to Score"},
        ]

    @router.get("/stats")
    async def get_stats(
        value_bets: list = Depends(get_value_bets),
        fixtures: list = Depends(get_fixtures),
    ) -> Dict[str, Any]:
        """Get system statistics."""
        return {
            "total_value_bets": len(value_bets),
            "total_fixtures": len(fixtures),
            "avg_edge": (
                sum(b.edge_percent if hasattr(b, "edge_percent") else b.get("edge_percent", 0)
                    for b in value_bets) / len(value_bets)
                if value_bets else 0
            ),
        }

    @router.get("/tracking/stats")
    async def get_tracking_stats(request: Request) -> Dict[str, Any]:
        """Get bet tracking performance statistics."""
        tracker = getattr(request.app.state, "bet_tracker", None)
        if not tracker:
            return {"error": "Tracking not enabled"}
        return tracker.get_stats()

    @router.get("/tracking/bets")
    async def get_tracked_bets(
        request: Request,
        status: str | None = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get tracked bets."""
        tracker = getattr(request.app.state, "bet_tracker", None)
        if not tracker:
            return []

        bets = list(tracker.bets.values())

        # Filter by status
        if status:
            bets = [b for b in bets if b.status.value == status]

        # Sort by logged_at descending
        bets.sort(key=lambda b: b.logged_at, reverse=True)

        return [b.to_dict() for b in bets[:limit]]

    @router.post("/tracking/log")
    async def log_bets_for_tracking(
        request: Request,
        min_edge: float = 10.0,
        max_bets: int = 20,
    ) -> Dict[str, Any]:
        """Log current value bets for tracking."""
        tracker = getattr(request.app.state, "bet_tracker", None)
        value_bets = getattr(request.app.state, "value_bets", [])

        if not tracker:
            return {"error": "Tracking not enabled"}

        # Filter by min edge
        filtered = [b for b in value_bets if b.edge_percent >= min_edge]

        # Log bets
        logged = tracker.log_multiple(filtered, stake=10.0, max_bets=max_bets)

        return {
            "logged": logged,
            "filtered_count": len(filtered),
            "total_tracked": len(tracker.bets),
        }

    @router.post("/tracking/check-results")
    async def check_results(request: Request) -> Dict[str, Any]:
        """Check results and settle pending bets."""
        results_checker = getattr(request.app.state, "results_checker", None)
        if not results_checker:
            return {"error": "Results checker not enabled"}

        result = await results_checker.check_and_settle()
        return result

    return router
