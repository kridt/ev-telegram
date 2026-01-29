"""Tests for value bet detection."""

from datetime import datetime, timedelta

import pytest

from src.api.models import Fixture, Odds, BookOdds, OddsOutcome, League, Team, PlayerProp
from src.engine.value import ValueCalculator, ValueBet, calculate_edge


class TestCalculateEdge:
    """Tests for edge calculation."""

    def test_positive_edge(self):
        """Test positive edge calculation."""
        # Book offers 2.10, fair is 2.00 = 5% edge
        edge = calculate_edge(2.10, 2.00)
        assert edge == pytest.approx(5.0, rel=0.01)

    def test_negative_edge(self):
        """Test negative edge (no value)."""
        # Book offers 1.90, fair is 2.00 = -5% edge
        edge = calculate_edge(1.90, 2.00)
        assert edge == pytest.approx(-5.0, rel=0.01)

    def test_zero_edge(self):
        """Test zero edge (fair value)."""
        edge = calculate_edge(2.00, 2.00)
        assert edge == pytest.approx(0.0, abs=0.01)

    def test_large_edge(self):
        """Test large edge calculation."""
        # Book offers 2.50, fair is 2.00 = 25% edge
        edge = calculate_edge(2.50, 2.00)
        assert edge == pytest.approx(25.0, rel=0.01)


class TestValueCalculator:
    """Tests for ValueCalculator class."""

    @pytest.fixture
    def calculator(self):
        """Create a value calculator instance."""
        return ValueCalculator(min_edge=5.0, min_books=2)

    @pytest.fixture
    def sample_fixture(self):
        """Create a sample fixture."""
        return Fixture(
            id="fixture_123",
            sport="soccer",
            league=League(id="premier-league", name="Premier League"),
            home_team=Team(id="mci", name="Manchester City"),
            away_team=Team(id="ars", name="Arsenal"),
            start_date=datetime.utcnow() + timedelta(hours=5),
            status="scheduled",
        )

    def test_find_value_two_way_market(self, calculator, sample_fixture):
        """Test finding value in a two-way over/under market."""
        # Create odds with Book3 offering +7% value on Over
        odds = Odds(
            fixture_id=sample_fixture.id,
            market_id="total_goals",
            market_name="Total Goals O/U 2.5",
            bookmaker_odds=[
                BookOdds(
                    sportsbook_id="book1",
                    sportsbook_name="Book1",
                    outcomes=[
                        OddsOutcome(name="Over 2.5", odds=1.90, line=2.5),
                        OddsOutcome(name="Under 2.5", odds=1.90, line=2.5),
                    ],
                ),
                BookOdds(
                    sportsbook_id="book2",
                    sportsbook_name="Book2",
                    outcomes=[
                        OddsOutcome(name="Over 2.5", odds=1.91, line=2.5),
                        OddsOutcome(name="Under 2.5", odds=1.89, line=2.5),
                    ],
                ),
                BookOdds(
                    sportsbook_id="book3",
                    sportsbook_name="Book3",
                    outcomes=[
                        OddsOutcome(name="Over 2.5", odds=2.15, line=2.5),  # +7% value!
                        OddsOutcome(name="Under 2.5", odds=1.85, line=2.5),
                    ],
                ),
            ],
        )

        value_bets = calculator.find_value_bets(sample_fixture, [odds])

        # Should find value on Book3's Over
        assert len(value_bets) >= 1

        over_bet = next(
            (b for b in value_bets if "Over" in b.selection and b.best_book == "Book3"),
            None,
        )
        assert over_bet is not None
        assert over_bet.edge_percent >= 5.0
        assert over_bet.best_odds == 2.15

    def test_no_value_when_below_threshold(self, sample_fixture):
        """Test that small edges are not flagged."""
        calculator = ValueCalculator(min_edge=10.0, min_books=2)

        # Create odds with only 5% edge (below 10% threshold)
        odds = Odds(
            fixture_id=sample_fixture.id,
            market_id="total_goals",
            market_name="Total Goals O/U 2.5",
            bookmaker_odds=[
                BookOdds(
                    sportsbook_id="book1",
                    sportsbook_name="Book1",
                    outcomes=[
                        OddsOutcome(name="Over 2.5", odds=1.90, line=2.5),
                        OddsOutcome(name="Under 2.5", odds=1.90, line=2.5),
                    ],
                ),
                BookOdds(
                    sportsbook_id="book2",
                    sportsbook_name="Book2",
                    outcomes=[
                        OddsOutcome(name="Over 2.5", odds=2.05, line=2.5),  # ~2.5% edge
                        OddsOutcome(name="Under 2.5", odds=1.95, line=2.5),
                    ],
                ),
            ],
        )

        value_bets = calculator.find_value_bets(sample_fixture, [odds])
        assert len(value_bets) == 0

    def test_insufficient_books(self, sample_fixture):
        """Test that markets with too few books are skipped."""
        calculator = ValueCalculator(min_edge=5.0, min_books=3)

        # Only 2 books, but calculator requires 3
        odds = Odds(
            fixture_id=sample_fixture.id,
            market_id="total_goals",
            market_name="Total Goals O/U 2.5",
            bookmaker_odds=[
                BookOdds(
                    sportsbook_id="book1",
                    sportsbook_name="Book1",
                    outcomes=[
                        OddsOutcome(name="Over 2.5", odds=1.90, line=2.5),
                        OddsOutcome(name="Under 2.5", odds=1.90, line=2.5),
                    ],
                ),
                BookOdds(
                    sportsbook_id="book2",
                    sportsbook_name="Book2",
                    outcomes=[
                        OddsOutcome(name="Over 2.5", odds=2.20, line=2.5),
                        OddsOutcome(name="Under 2.5", odds=1.80, line=2.5),
                    ],
                ),
            ],
        )

        value_bets = calculator.find_value_bets(sample_fixture, [odds])
        assert len(value_bets) == 0

    def test_find_value_player_props(self, calculator, sample_fixture):
        """Test finding value in player prop markets."""
        props = [
            PlayerProp(
                fixture_id=sample_fixture.id,
                player_name="Haaland",
                market_type="Shots on Target",
                line=2.5,
                over_odds={
                    "Book1": 1.90,
                    "Book2": 1.91,
                    "Book3": 2.15,  # +7% value
                },
                under_odds={
                    "Book1": 1.90,
                    "Book2": 1.89,
                    "Book3": 1.75,
                },
            ),
        ]

        value_bets = calculator.find_value_from_player_props(sample_fixture, props)

        assert len(value_bets) >= 1

        haaland_bet = next(
            (b for b in value_bets if "Haaland" in b.market_name),
            None,
        )
        assert haaland_bet is not None
        assert haaland_bet.edge_percent >= 5.0


class TestValueBet:
    """Tests for ValueBet dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        bet = ValueBet(
            fixture_id="123",
            fixture_name="Man City vs Arsenal",
            league="Premier League",
            kickoff=datetime(2024, 1, 15, 15, 0),
            market_type="player_shots",
            market_name="Haaland Shots on Target",
            selection="Over 2.5",
            line=2.5,
            best_odds=2.15,
            best_book="Book3",
            fair_odds=2.00,
            edge_percent=7.5,
            all_odds={"Book1": 1.90, "Book2": 1.91, "Book3": 2.15},
        )

        data = bet.to_dict()

        assert data["fixture_id"] == "123"
        assert data["edge_percent"] == 7.5
        assert data["best_odds"] == 2.15
        assert "Book3" in data["all_odds"]

    def test_hours_to_kickoff(self):
        """Test hours to kickoff calculation."""
        future = datetime.utcnow() + timedelta(hours=3)
        bet = ValueBet(
            fixture_id="123",
            fixture_name="Test",
            league="Test",
            kickoff=future,
            market_type="test",
            market_name="Test",
            selection="Test",
            line=None,
            best_odds=2.0,
            best_book="Book",
            fair_odds=1.9,
            edge_percent=5.0,
        )

        assert bet.hours_to_kickoff is not None
        assert 2.9 < bet.hours_to_kickoff < 3.1

    def test_edge_display(self):
        """Test edge display formatting."""
        bet = ValueBet(
            fixture_id="123",
            fixture_name="Test",
            league="Test",
            kickoff=None,
            market_type="test",
            market_name="Test",
            selection="Test",
            line=None,
            best_odds=2.0,
            best_book="Book",
            fair_odds=1.9,
            edge_percent=7.56,
        )

        assert bet.edge_display == "7.6%"
