"""Market type definitions and utilities."""

from enum import Enum
from typing import Optional


class MarketType(Enum):
    """Types of betting markets."""
    # Match markets
    MATCH_WINNER = "match_winner"
    DOUBLE_CHANCE = "double_chance"
    DRAW_NO_BET = "draw_no_bet"

    # Goals markets
    TOTAL_GOALS = "total_goals"
    TEAM_TOTAL_GOALS = "team_total_goals"
    BOTH_TEAMS_TO_SCORE = "btts"
    CORRECT_SCORE = "correct_score"

    # Player props
    PLAYER_GOALS = "player_goals"
    PLAYER_ASSISTS = "player_assists"
    PLAYER_SHOTS = "player_shots"
    PLAYER_SHOTS_ON_TARGET = "player_shots_on_target"
    PLAYER_TACKLES = "player_tackles"
    PLAYER_PASSES = "player_passes"
    PLAYER_FOULS = "player_fouls"
    PLAYER_CARDS = "player_cards"

    # Other
    CORNERS = "corners"
    CARDS = "cards"
    UNKNOWN = "unknown"


class MarketCategory(Enum):
    """Categories of markets."""
    MATCH = "match"
    GOALS = "goals"
    PLAYER_PROPS = "player_props"
    SPECIALS = "specials"


# Mapping from API market IDs to our market types
MARKET_ID_MAP = {
    "1x2": MarketType.MATCH_WINNER,
    "moneyline": MarketType.MATCH_WINNER,
    "double_chance": MarketType.DOUBLE_CHANCE,
    "draw_no_bet": MarketType.DRAW_NO_BET,
    "over_under": MarketType.TOTAL_GOALS,
    "total_goals": MarketType.TOTAL_GOALS,
    "btts": MarketType.BOTH_TEAMS_TO_SCORE,
    "both_teams_to_score": MarketType.BOTH_TEAMS_TO_SCORE,
    "correct_score": MarketType.CORRECT_SCORE,
    "player_goals": MarketType.PLAYER_GOALS,
    "player_assists": MarketType.PLAYER_ASSISTS,
    "player_shots": MarketType.PLAYER_SHOTS,
    "player_shots_on_target": MarketType.PLAYER_SHOTS_ON_TARGET,
    "player_tackles": MarketType.PLAYER_TACKLES,
    "player_passes": MarketType.PLAYER_PASSES,
    "player_fouls": MarketType.PLAYER_FOULS,
    "player_cards": MarketType.PLAYER_CARDS,
    "corners": MarketType.CORNERS,
    "cards": MarketType.CARDS,
}

# Category mapping
MARKET_CATEGORIES = {
    MarketType.MATCH_WINNER: MarketCategory.MATCH,
    MarketType.DOUBLE_CHANCE: MarketCategory.MATCH,
    MarketType.DRAW_NO_BET: MarketCategory.MATCH,
    MarketType.TOTAL_GOALS: MarketCategory.GOALS,
    MarketType.TEAM_TOTAL_GOALS: MarketCategory.GOALS,
    MarketType.BOTH_TEAMS_TO_SCORE: MarketCategory.GOALS,
    MarketType.CORRECT_SCORE: MarketCategory.GOALS,
    MarketType.PLAYER_GOALS: MarketCategory.PLAYER_PROPS,
    MarketType.PLAYER_ASSISTS: MarketCategory.PLAYER_PROPS,
    MarketType.PLAYER_SHOTS: MarketCategory.PLAYER_PROPS,
    MarketType.PLAYER_SHOTS_ON_TARGET: MarketCategory.PLAYER_PROPS,
    MarketType.PLAYER_TACKLES: MarketCategory.PLAYER_PROPS,
    MarketType.PLAYER_PASSES: MarketCategory.PLAYER_PROPS,
    MarketType.PLAYER_FOULS: MarketCategory.PLAYER_PROPS,
    MarketType.PLAYER_CARDS: MarketCategory.PLAYER_PROPS,
    MarketType.CORNERS: MarketCategory.SPECIALS,
    MarketType.CARDS: MarketCategory.SPECIALS,
    MarketType.UNKNOWN: MarketCategory.SPECIALS,
}

# Player prop market types for filtering
PLAYER_PROP_MARKETS = [
    MarketType.PLAYER_GOALS,
    MarketType.PLAYER_ASSISTS,
    MarketType.PLAYER_SHOTS,
    MarketType.PLAYER_SHOTS_ON_TARGET,
    MarketType.PLAYER_TACKLES,
    MarketType.PLAYER_PASSES,
    MarketType.PLAYER_FOULS,
    MarketType.PLAYER_CARDS,
]


def get_market_type(market_id: str) -> MarketType:
    """
    Get the market type from a market ID.

    Args:
        market_id: Market ID string

    Returns:
        MarketType enum value
    """
    market_id_lower = market_id.lower().replace("-", "_").replace(" ", "_")
    return MARKET_ID_MAP.get(market_id_lower, MarketType.UNKNOWN)


def get_market_category(market_type: MarketType) -> MarketCategory:
    """
    Get the category for a market type.

    Args:
        market_type: MarketType enum value

    Returns:
        MarketCategory enum value
    """
    return MARKET_CATEGORIES.get(market_type, MarketCategory.SPECIALS)


def is_player_prop(market_type: MarketType) -> bool:
    """Check if a market type is a player prop."""
    return market_type in PLAYER_PROP_MARKETS


def is_two_way_market(market_type: MarketType) -> bool:
    """Check if a market is a two-way (over/under, yes/no) market."""
    two_way_markets = [
        MarketType.BOTH_TEAMS_TO_SCORE,
        MarketType.TOTAL_GOALS,
        MarketType.TEAM_TOTAL_GOALS,
        MarketType.PLAYER_GOALS,
        MarketType.PLAYER_ASSISTS,
        MarketType.PLAYER_SHOTS,
        MarketType.PLAYER_SHOTS_ON_TARGET,
        MarketType.PLAYER_TACKLES,
        MarketType.PLAYER_PASSES,
        MarketType.PLAYER_FOULS,
        MarketType.PLAYER_CARDS,
        MarketType.CORNERS,
        MarketType.CARDS,
    ]
    return market_type in two_way_markets


def parse_line_from_outcome(outcome_name: str) -> Optional[float]:
    """
    Extract the line value from an outcome name.

    Examples:
        "Over 2.5" -> 2.5
        "Under 1.5" -> 1.5
        "O 3.5" -> 3.5

    Args:
        outcome_name: Outcome name string

    Returns:
        Line value or None if not found
    """
    import re

    # Match patterns like "Over 2.5", "Under 1.5", "O 3.5", "U 2.5"
    pattern = r"(?:over|under|o|u)\s*(\d+\.?\d*)"
    match = re.search(pattern, outcome_name.lower())

    if match:
        return float(match.group(1))
    return None
