"""Devigging calculations for removing bookmaker margin."""

from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


def implied_probability(odds: float) -> float:
    """
    Convert decimal odds to implied probability.

    Args:
        odds: Decimal odds (e.g., 2.0)

    Returns:
        Implied probability (e.g., 0.5)
    """
    if odds <= 0:
        raise ValueError(f"Odds must be positive, got {odds}")
    return 1.0 / odds


def odds_from_probability(probability: float) -> float:
    """
    Convert probability to decimal odds.

    Args:
        probability: Probability (e.g., 0.5)

    Returns:
        Decimal odds (e.g., 2.0)
    """
    if probability <= 0 or probability >= 1:
        raise ValueError(f"Probability must be between 0 and 1, got {probability}")
    return 1.0 / probability


def calculate_vig(odds: List[float]) -> float:
    """
    Calculate the total vig/margin in a set of odds.

    Args:
        odds: List of decimal odds for all outcomes

    Returns:
        Vig as a percentage (e.g., 5.0 for 5% margin)
    """
    total_implied = sum(implied_probability(o) for o in odds)
    return (total_implied - 1.0) * 100


def devig_multiplicative(odds: List[float]) -> List[float]:
    """
    Remove bookmaker margin using the multiplicative (proportional) method.

    This method assumes the bookmaker has applied their margin proportionally
    to all outcomes. It's the most common and generally fair method.

    Steps:
    1. Convert odds to implied probabilities
    2. Sum probabilities (will be > 1 due to vig)
    3. Divide each probability by the sum to normalize to 1
    4. Convert back to fair odds

    Args:
        odds: List of decimal odds for all outcomes in a market

    Returns:
        List of fair (devigged) decimal odds

    Example:
        >>> devig_multiplicative([1.90, 1.90])  # 50/50 with ~5% vig
        [2.0, 2.0]  # Fair odds
    """
    if not odds:
        raise ValueError("Odds list cannot be empty")

    if any(o <= 1.0 for o in odds):
        raise ValueError(f"All odds must be greater than 1.0, got {odds}")

    # Convert to implied probabilities
    implied_probs = [implied_probability(o) for o in odds]

    # Calculate total (should be > 1 due to vig)
    total = sum(implied_probs)

    if total <= 0:
        raise ValueError("Sum of implied probabilities must be positive")

    # Normalize probabilities to sum to 1
    fair_probs = [p / total for p in implied_probs]

    # Convert back to odds
    fair_odds = [odds_from_probability(p) for p in fair_probs]

    return fair_odds


def devig_additive(odds: List[float]) -> List[float]:
    """
    Remove bookmaker margin using the additive method.

    This method subtracts an equal amount from each implied probability.
    Less common but can be useful for certain market types.

    Args:
        odds: List of decimal odds for all outcomes

    Returns:
        List of fair decimal odds
    """
    if not odds:
        raise ValueError("Odds list cannot be empty")

    implied_probs = [implied_probability(o) for o in odds]
    total = sum(implied_probs)
    vig = total - 1.0

    # Subtract equal portion of vig from each probability
    vig_per_outcome = vig / len(implied_probs)
    fair_probs = [p - vig_per_outcome for p in implied_probs]

    # Ensure all probabilities are valid
    fair_probs = [max(0.001, min(0.999, p)) for p in fair_probs]

    return [odds_from_probability(p) for p in fair_probs]


def devig_power(odds: List[float]) -> List[float]:
    """
    Remove bookmaker margin using the power method.

    This method assumes longer odds have proportionally more vig applied.
    Useful for markets with heavy favorites.

    Args:
        odds: List of decimal odds for all outcomes

    Returns:
        List of fair decimal odds
    """
    if not odds:
        raise ValueError("Odds list cannot be empty")

    implied_probs = [implied_probability(o) for o in odds]
    total = sum(implied_probs)

    # Find the power 'k' such that sum(p^k) = 1
    # Use binary search
    k_low, k_high = 0.5, 2.0

    for _ in range(50):  # Binary search iterations
        k = (k_low + k_high) / 2
        adjusted_sum = sum(p ** k for p in implied_probs)

        if abs(adjusted_sum - 1.0) < 0.0001:
            break
        elif adjusted_sum > 1.0:
            k_high = k
        else:
            k_low = k

    fair_probs = [p ** k for p in implied_probs]
    # Normalize to ensure sum = 1
    total_fair = sum(fair_probs)
    fair_probs = [p / total_fair for p in fair_probs]

    return [odds_from_probability(p) for p in fair_probs]


def calculate_average_odds(all_book_odds: List[Tuple[str, float]]) -> float:
    """
    Calculate the simple average of odds across bookmakers.

    Args:
        all_book_odds: List of (bookmaker_name, odds) tuples

    Returns:
        Average odds value
    """
    if not all_book_odds:
        raise ValueError("No odds provided")

    odds_values = [odds for _, odds in all_book_odds]
    return sum(odds_values) / len(odds_values)


def calculate_weighted_average_odds(
    all_book_odds: List[Tuple[str, float]],
    weights: dict[str, float] = None,
) -> float:
    """
    Calculate weighted average of odds.

    Args:
        all_book_odds: List of (bookmaker_name, odds) tuples
        weights: Optional dict of bookmaker -> weight

    Returns:
        Weighted average odds
    """
    if not all_book_odds:
        raise ValueError("No odds provided")

    if weights is None:
        return calculate_average_odds(all_book_odds)

    total_weight = 0.0
    weighted_sum = 0.0

    for book, odds in all_book_odds:
        w = weights.get(book, 1.0)
        weighted_sum += odds * w
        total_weight += w

    return weighted_sum / total_weight if total_weight > 0 else 0


def calculate_fair_odds_from_market(
    over_odds: List[Tuple[str, float]],
    under_odds: List[Tuple[str, float]],
) -> Tuple[float, float]:
    """
    Calculate fair odds for an over/under market using average devigging.

    Args:
        over_odds: List of (bookmaker, odds) for the over
        under_odds: List of (bookmaker, odds) for the under

    Returns:
        Tuple of (fair_over_odds, fair_under_odds)
    """
    # Calculate average odds for each side
    avg_over = calculate_average_odds(over_odds)
    avg_under = calculate_average_odds(under_odds)

    # Devig the average
    fair_odds = devig_multiplicative([avg_over, avg_under])

    return fair_odds[0], fair_odds[1]
