"""Pydantic models for API responses."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Team(BaseModel):
    """Team information."""
    id: str = ""
    name: str = ""


class League(BaseModel):
    """League/competition information."""
    id: str = ""
    name: str = ""


class Fixture(BaseModel):
    """A sports fixture/match."""
    id: str
    sport: str = "soccer"
    league: League = Field(default_factory=League)
    home_team: Team = Field(default_factory=Team)
    away_team: Team = Field(default_factory=Team)
    start_date: Optional[datetime] = None
    status: str = "scheduled"
    is_live: bool = False

    class Config:
        populate_by_name = True

    @property
    def display_name(self) -> str:
        """Get display name for the fixture."""
        return f"{self.home_team.name} vs {self.away_team.name}"


class OddsData(BaseModel):
    """Individual odds from the API."""
    id: str = ""
    fixture_id: str = ""
    sportsbook: str = ""
    market: str = ""
    name: str = ""  # Full selection name, e.g., "Mohamed Salah Over 0.5"
    selection: str = ""  # Selection part, e.g., "Mohamed Salah"
    price: float = 0  # American odds format
    points: Optional[float] = None  # Line value for O/U markets
    player_id: Optional[str] = None
    team_id: Optional[str] = None
    is_main: bool = True
    timestamp: Optional[float] = None

    @property
    def decimal_odds(self) -> float:
        """Convert American odds to decimal."""
        if self.price >= 0:
            return 1 + (self.price / 100)
        else:
            return 1 + (100 / abs(self.price))

    @property
    def implied_probability(self) -> float:
        """Get implied probability from decimal odds."""
        return 1 / self.decimal_odds

    @property
    def is_player_prop(self) -> bool:
        """Check if this is a player prop."""
        return self.player_id is not None


class Sportsbook(BaseModel):
    """Sportsbook/bookmaker information."""
    id: str
    name: str
    is_active: bool = True


class Market(BaseModel):
    """Market type information."""
    id: str
    name: str
    description: str = ""
    sport: str = "soccer"


class APIResponse(BaseModel):
    """Generic API response wrapper."""
    success: bool = True
    data: Any = None
    error: Optional[str] = None
