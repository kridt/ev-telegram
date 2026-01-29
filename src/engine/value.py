"""Value bet detection logic - Updated for market average approach."""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..api.models import Fixture, OddsData
from .devig import devig_multiplicative

logger = logging.getLogger(__name__)


@dataclass
class ValueBet:
    """Represents a detected value betting opportunity."""
    fixture_id: str
    fixture_name: str
    league: str
    kickoff: Optional[datetime]
    market: str
    selection: str
    line: Optional[float]

    best_odds: float  # Decimal odds
    best_odds_american: float  # American odds
    best_book: str
    fair_odds: float  # Market average devigged
    edge_percent: float

    all_odds: Dict[str, float] = field(default_factory=dict)  # book -> decimal odds
    is_player_prop: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def edge_display(self) -> str:
        """Format edge for display."""
        return f"{self.edge_percent:.1f}%"

    @property
    def hours_to_kickoff(self) -> Optional[float]:
        """Calculate hours until kickoff."""
        if not self.kickoff:
            return None
        now = datetime.now(timezone.utc)
        if self.kickoff.tzinfo is None:
            # Assume UTC if no timezone
            kickoff = self.kickoff.replace(tzinfo=timezone.utc)
        else:
            kickoff = self.kickoff
        delta = kickoff - now
        return delta.total_seconds() / 3600

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "fixture_id": self.fixture_id,
            "fixture_name": self.fixture_name,
            "league": self.league,
            "kickoff": self.kickoff.isoformat() if self.kickoff else None,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "best_odds": round(self.best_odds, 3),
            "best_odds_american": self.best_odds_american,
            "best_book": self.best_book,
            "fair_odds": round(self.fair_odds, 3),
            "edge_percent": round(self.edge_percent, 2),
            "all_odds": {k: round(v, 3) for k, v in self.all_odds.items()},
            "is_player_prop": self.is_player_prop,
            "timestamp": self.timestamp.isoformat(),
        }


def american_to_decimal(american: float) -> float:
    """Convert American odds to decimal."""
    if american >= 0:
        return 1 + (american / 100)
    else:
        return 1 + (100 / abs(american))


def calculate_edge(book_odds: float, fair_odds: float) -> float:
    """
    Calculate edge percentage.

    Edge = (book_odds / fair_odds - 1) * 100

    A positive edge means the bookmaker's odds are higher than fair value,
    representing a +EV betting opportunity.

    Args:
        book_odds: Decimal odds offered by bookmaker
        fair_odds: Calculated fair decimal odds

    Returns:
        Edge as a percentage (e.g., 5.0 for 5% edge)
    """
    if fair_odds <= 0:
        return 0.0
    return (book_odds / fair_odds - 1) * 100


class ValueCalculator:
    """Calculator for finding value betting opportunities using market average."""

    def __init__(
        self,
        min_edge: float = 5.0,
        min_books: int = 2,
        max_edge: float = 50.0,
        min_odds: float = 1.3,
        max_odds: float = 15.0,
    ):
        """
        Initialize the value calculator.

        Args:
            min_edge: Minimum edge percentage to flag as value
            min_books: Minimum number of bookmakers needed for fair odds calculation
            max_edge: Maximum edge (filter outliers/errors)
            min_odds: Minimum decimal odds to consider
            max_odds: Maximum decimal odds to consider
        """
        self.min_edge = min_edge
        self.min_books = min_books
        self.max_edge = max_edge
        self.min_odds = min_odds
        self.max_odds = max_odds

    def find_value_bets(
        self,
        fixture: Fixture,
        odds_list: List[OddsData],
        target_markets: Optional[List[str]] = None,
    ) -> List[ValueBet]:
        """
        Find value bets for a fixture using market average approach.

        Args:
            fixture: The fixture information
            odds_list: List of all odds data
            target_markets: Optional list of market names to analyze

        Returns:
            List of detected value bets
        """
        value_bets = []

        # Group odds by market+selection key
        grouped = self._group_odds(odds_list, target_markets)

        for key, book_odds in grouped.items():
            if len(book_odds) < self.min_books:
                continue

            bets = self._analyze_market(fixture, key, book_odds)
            value_bets.extend(bets)

        # Sort by edge, highest first
        value_bets.sort(key=lambda x: x.edge_percent, reverse=True)

        logger.info(f"Found {len(value_bets)} value bets for {fixture.display_name}")
        return value_bets

    def _group_odds(
        self,
        odds_list: List[OddsData],
        target_markets: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, OddsData]]:
        """
        Group odds by market+selection key.

        Returns:
            Dict mapping key to dict of {sportsbook: OddsData}
        """
        grouped: Dict[str, Dict[str, OddsData]] = defaultdict(dict)

        for odd in odds_list:
            # Filter by target markets if specified
            if target_markets and odd.market not in target_markets:
                continue

            # Create unique key for this selection
            # Include points for O/U markets
            key = f"{odd.market}|{odd.name}|{odd.points or ''}"
            grouped[key][odd.sportsbook] = odd

        return grouped

    def _analyze_market(
        self,
        fixture: Fixture,
        key: str,
        book_odds: Dict[str, OddsData],
    ) -> List[ValueBet]:
        """
        Analyze a single market for value.

        Uses market average approach:
        1. Calculate average decimal odds across all books
        2. Compare each book's odds to the average
        3. Flag books with odds significantly above average
        """
        value_bets = []

        # Convert all to decimal odds
        decimal_odds: Dict[str, float] = {}
        for book, odd in book_odds.items():
            dec = american_to_decimal(odd.price)
            # Filter extreme odds
            if self.min_odds <= dec <= self.max_odds:
                decimal_odds[book] = dec

        if len(decimal_odds) < self.min_books:
            return value_bets

        # Calculate market average (this is our "fair" estimate)
        avg_odds = sum(decimal_odds.values()) / len(decimal_odds)

        # Parse key parts
        parts = key.split("|")
        market = parts[0]
        selection = parts[1] if len(parts) > 1 else ""
        line_str = parts[2] if len(parts) > 2 else ""
        line = float(line_str) if line_str else None

        # Find value opportunities
        for book, dec in decimal_odds.items():
            edge = calculate_edge(dec, avg_odds)

            if self.min_edge <= edge <= self.max_edge:
                odd = book_odds[book]

                value_bets.append(ValueBet(
                    fixture_id=fixture.id,
                    fixture_name=fixture.display_name,
                    league=fixture.league.name,
                    kickoff=fixture.start_date,
                    market=market,
                    selection=selection,
                    line=line,
                    best_odds=dec,
                    best_odds_american=odd.price,
                    best_book=book,
                    fair_odds=avg_odds,
                    edge_percent=edge,
                    all_odds=decimal_odds,
                    is_player_prop=odd.is_player_prop,
                ))

        return value_bets

    def find_value_two_way(
        self,
        fixture: Fixture,
        odds_list: List[OddsData],
        target_markets: Optional[List[str]] = None,
    ) -> List[ValueBet]:
        """
        Find value in two-way markets using proper devigging.

        For markets with Over/Under, calculates fair odds by:
        1. Finding matching Over/Under pairs
        2. Averaging each side across books
        3. Devigging the average to get true probabilities
        4. Comparing individual book odds to devigged fair odds
        """
        value_bets = []

        # Group by market + line (for O/U matching)
        grouped = self._group_two_way_odds(odds_list, target_markets)

        for market_key, sides in grouped.items():
            over_odds = sides.get("over", {})
            under_odds = sides.get("under", {})

            if len(over_odds) < self.min_books or len(under_odds) < self.min_books:
                continue

            bets = self._analyze_two_way_market(fixture, market_key, over_odds, under_odds)
            value_bets.extend(bets)

        value_bets.sort(key=lambda x: x.edge_percent, reverse=True)
        return value_bets

    def _group_two_way_odds(
        self,
        odds_list: List[OddsData],
        target_markets: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Dict[str, OddsData]]]:
        """
        Group O/U odds by market+line.

        Returns:
            Dict[market_key, {"over": {book: odds}, "under": {book: odds}}]
        """
        grouped: Dict[str, Dict[str, Dict[str, OddsData]]] = defaultdict(
            lambda: {"over": {}, "under": {}}
        )

        for odd in odds_list:
            if target_markets and odd.market not in target_markets:
                continue

            # Detect Over/Under from name
            name_lower = odd.name.lower()
            if "over" in name_lower:
                side = "over"
            elif "under" in name_lower:
                side = "under"
            else:
                continue

            # Create key without the Over/Under part
            key = f"{odd.market}|{odd.points or ''}"
            grouped[key][side][odd.sportsbook] = odd

        return grouped

    def _analyze_two_way_market(
        self,
        fixture: Fixture,
        market_key: str,
        over_odds: Dict[str, OddsData],
        under_odds: Dict[str, OddsData],
    ) -> List[ValueBet]:
        """Analyze a two-way O/U market using devigging."""
        value_bets = []

        # Convert to decimal
        over_dec = {b: american_to_decimal(o.price) for b, o in over_odds.items()
                    if self.min_odds <= american_to_decimal(o.price) <= self.max_odds}
        under_dec = {b: american_to_decimal(o.price) for b, o in under_odds.items()
                     if self.min_odds <= american_to_decimal(o.price) <= self.max_odds}

        if len(over_dec) < self.min_books or len(under_dec) < self.min_books:
            return value_bets

        # Calculate average for each side
        avg_over = sum(over_dec.values()) / len(over_dec)
        avg_under = sum(under_dec.values()) / len(under_dec)

        # Devig to get fair odds
        try:
            fair_over, fair_under = devig_multiplicative([avg_over, avg_under])
        except ValueError:
            return value_bets

        # Parse market key
        parts = market_key.split("|")
        market = parts[0]
        line = float(parts[1]) if len(parts) > 1 and parts[1] else None

        # Check Over side for value
        for book, dec in over_dec.items():
            edge = calculate_edge(dec, fair_over)
            if self.min_edge <= edge <= self.max_edge:
                odd = over_odds[book]
                value_bets.append(ValueBet(
                    fixture_id=fixture.id,
                    fixture_name=fixture.display_name,
                    league=fixture.league.name,
                    kickoff=fixture.start_date,
                    market=market,
                    selection=f"Over {line}" if line else "Over",
                    line=line,
                    best_odds=dec,
                    best_odds_american=odd.price,
                    best_book=book,
                    fair_odds=fair_over,
                    edge_percent=edge,
                    all_odds=over_dec,
                    is_player_prop=odd.is_player_prop,
                ))

        # Check Under side for value
        for book, dec in under_dec.items():
            edge = calculate_edge(dec, fair_under)
            if self.min_edge <= edge <= self.max_edge:
                odd = under_odds[book]
                value_bets.append(ValueBet(
                    fixture_id=fixture.id,
                    fixture_name=fixture.display_name,
                    league=fixture.league.name,
                    kickoff=fixture.start_date,
                    market=market,
                    selection=f"Under {line}" if line else "Under",
                    line=line,
                    best_odds=dec,
                    best_odds_american=odd.price,
                    best_book=book,
                    fair_odds=fair_under,
                    edge_percent=edge,
                    all_odds=under_dec,
                    is_player_prop=odd.is_player_prop,
                ))

        return value_bets
