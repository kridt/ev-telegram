"""Tests for devigging calculations."""

import pytest
from src.engine.devig import (
    implied_probability,
    odds_from_probability,
    calculate_vig,
    devig_multiplicative,
    devig_additive,
    calculate_average_odds,
    calculate_fair_odds_from_market,
)


class TestImpliedProbability:
    """Tests for implied probability calculations."""

    def test_even_odds(self):
        """Test conversion of 2.0 odds (50% implied)."""
        assert implied_probability(2.0) == 0.5

    def test_favorite_odds(self):
        """Test conversion of favorite odds."""
        assert implied_probability(1.5) == pytest.approx(0.6667, rel=0.01)

    def test_underdog_odds(self):
        """Test conversion of underdog odds."""
        assert implied_probability(4.0) == 0.25

    def test_invalid_odds(self):
        """Test that non-positive odds raise error."""
        with pytest.raises(ValueError):
            implied_probability(0)
        with pytest.raises(ValueError):
            implied_probability(-1.5)


class TestOddsFromProbability:
    """Tests for odds conversion from probability."""

    def test_fifty_percent(self):
        """Test 50% probability converts to 2.0 odds."""
        assert odds_from_probability(0.5) == 2.0

    def test_high_probability(self):
        """Test high probability conversion."""
        assert odds_from_probability(0.8) == pytest.approx(1.25, rel=0.01)

    def test_low_probability(self):
        """Test low probability conversion."""
        assert odds_from_probability(0.25) == 4.0

    def test_invalid_probability(self):
        """Test that invalid probabilities raise error."""
        with pytest.raises(ValueError):
            odds_from_probability(0)
        with pytest.raises(ValueError):
            odds_from_probability(1)
        with pytest.raises(ValueError):
            odds_from_probability(1.5)


class TestCalculateVig:
    """Tests for vig calculation."""

    def test_no_vig(self):
        """Test fair odds have no vig."""
        vig = calculate_vig([2.0, 2.0])
        assert vig == pytest.approx(0, abs=0.01)

    def test_typical_vig(self):
        """Test typical bookmaker vig (~5%)."""
        # 1.90 / 1.90 is a common vigorous line
        vig = calculate_vig([1.90, 1.90])
        assert vig == pytest.approx(5.26, rel=0.1)

    def test_high_vig(self):
        """Test high vig market."""
        vig = calculate_vig([1.80, 1.80])
        assert vig == pytest.approx(11.1, rel=0.1)


class TestDevigMultiplicative:
    """Tests for multiplicative devigging."""

    def test_symmetric_odds(self):
        """Test devigging symmetric vigorous odds."""
        fair = devig_multiplicative([1.90, 1.90])
        assert len(fair) == 2
        assert fair[0] == pytest.approx(2.0, rel=0.01)
        assert fair[1] == pytest.approx(2.0, rel=0.01)

    def test_asymmetric_odds(self):
        """Test devigging asymmetric odds."""
        # Favorite at 1.50 (-200), underdog at 2.50 (+150) with vig
        fair = devig_multiplicative([1.50, 2.50])

        # Sum of implied should be 1.0
        sum_implied = sum(1/o for o in fair)
        assert sum_implied == pytest.approx(1.0, rel=0.01)

    def test_three_way_market(self):
        """Test devigging 3-way market (1X2)."""
        # Typical 1X2 odds with vig
        fair = devig_multiplicative([2.10, 3.40, 3.50])

        sum_implied = sum(1/o for o in fair)
        assert sum_implied == pytest.approx(1.0, rel=0.01)

    def test_empty_list(self):
        """Test empty odds list raises error."""
        with pytest.raises(ValueError):
            devig_multiplicative([])

    def test_invalid_odds(self):
        """Test odds <= 1.0 raise error."""
        with pytest.raises(ValueError):
            devig_multiplicative([1.0, 2.0])
        with pytest.raises(ValueError):
            devig_multiplicative([0.5, 2.0])


class TestDevigAdditive:
    """Tests for additive devigging."""

    def test_symmetric_odds(self):
        """Test devigging symmetric vigorous odds."""
        fair = devig_additive([1.90, 1.90])
        assert len(fair) == 2
        # Should be close to 2.0 each
        assert fair[0] == pytest.approx(2.0, rel=0.05)
        assert fair[1] == pytest.approx(2.0, rel=0.05)

    def test_sum_to_one(self):
        """Test fair probabilities sum to 1."""
        fair = devig_additive([1.90, 1.90])
        sum_implied = sum(1/o for o in fair)
        assert sum_implied == pytest.approx(1.0, rel=0.01)


class TestAverageOdds:
    """Tests for average odds calculation."""

    def test_simple_average(self):
        """Test simple average of odds."""
        odds = [("Book1", 2.0), ("Book2", 2.2), ("Book3", 2.1)]
        avg = calculate_average_odds(odds)
        assert avg == pytest.approx(2.1, rel=0.01)

    def test_single_book(self):
        """Test average with single book."""
        odds = [("Book1", 2.5)]
        avg = calculate_average_odds(odds)
        assert avg == 2.5

    def test_empty_list(self):
        """Test empty list raises error."""
        with pytest.raises(ValueError):
            calculate_average_odds([])


class TestFairOddsFromMarket:
    """Tests for fair odds calculation from market data."""

    def test_balanced_market(self):
        """Test fair odds from balanced market."""
        over_odds = [("Book1", 1.90), ("Book2", 1.91), ("Book3", 1.89)]
        under_odds = [("Book1", 1.90), ("Book2", 1.89), ("Book3", 1.91)]

        fair_over, fair_under = calculate_fair_odds_from_market(over_odds, under_odds)

        # Both should be close to 2.0
        assert fair_over == pytest.approx(2.0, rel=0.05)
        assert fair_under == pytest.approx(2.0, rel=0.05)

    def test_skewed_market(self):
        """Test fair odds from skewed market."""
        over_odds = [("Book1", 2.10), ("Book2", 2.15)]
        under_odds = [("Book1", 1.75), ("Book2", 1.72)]

        fair_over, fair_under = calculate_fair_odds_from_market(over_odds, under_odds)

        # Fair odds should be higher than vigged odds
        assert fair_over > 2.1
        assert fair_under > 1.75
