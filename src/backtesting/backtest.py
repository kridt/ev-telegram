"""Backtesting module for value betting strategy."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import json

from ..api import OpticOddsClient

logger = logging.getLogger(__name__)


def american_to_decimal(american_odds: float) -> float:
    """Convert American odds to decimal odds."""
    if american_odds >= 100:
        return (american_odds / 100) + 1
    else:
        return (100 / abs(american_odds)) + 1


def decimal_to_implied_prob(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability."""
    return 1 / decimal_odds if decimal_odds > 0 else 0


def devig_multiplicative(odds_dict: Dict[str, float]) -> Dict[str, float]:
    """
    Remove vig using multiplicative method.
    Returns fair decimal odds for each selection.
    """
    if not odds_dict:
        return {}

    # Calculate implied probabilities
    implied_probs = {k: decimal_to_implied_prob(v) for k, v in odds_dict.items()}
    total_prob = sum(implied_probs.values())

    if total_prob <= 0:
        return {}

    # Remove vig by normalizing
    fair_probs = {k: v / total_prob for k, v in implied_probs.items()}

    # Convert back to decimal odds
    fair_odds = {k: 1 / v if v > 0 else 0 for k, v in fair_probs.items()}

    return fair_odds


@dataclass
class BacktestBet:
    """A bet identified during backtesting."""
    fixture_id: str
    fixture_name: str
    market: str
    selection: str
    line: float
    book_odds: float
    book_name: str
    fair_odds: float
    edge_percent: float
    actual_result: Optional[float] = None
    won: Optional[bool] = None
    profit: Optional[float] = None


@dataclass
class BacktestResults:
    """Results from backtesting."""
    total_bets: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    total_staked: float = 0
    total_profit: float = 0
    roi: float = 0
    win_rate: float = 0
    avg_edge: float = 0
    avg_odds: float = 0
    bets: List[BacktestBet] = field(default_factory=list)


class Backtester:
    """Backtesting engine for value betting strategy."""

    SPORTSBOOKS = ['Pinnacle', 'Betsson', 'Unibet', 'bet365', 'Betway', 'DraftKings', 'FanDuel']
    MARKETS = ['Total Corners', 'Total Shots', 'Total Shots On Target']

    def __init__(self, api_client: OpticOddsClient):
        self.api = api_client

    async def run_backtest(
        self,
        fixtures: List[Dict[str, Any]],
        min_edge: float = 10.0,
        min_odds: float = 1.5,
        max_odds: float = 4.0,
        stake: float = 10.0
    ) -> BacktestResults:
        """
        Run backtest on completed fixtures.

        Args:
            fixtures: List of completed fixture data
            min_edge: Minimum edge % to consider a value bet
            min_odds: Minimum odds to consider
            max_odds: Maximum odds to consider
            stake: Stake amount per bet
        """
        results = BacktestResults()
        all_bets = []

        for fixture in fixtures:
            fixture_id = fixture.get('id')
            fixture_name = f"{fixture.get('home_team_display')} vs {fixture.get('away_team_display')}"

            logger.info(f"Backtesting: {fixture_name}")

            # Get historical odds for each market
            for market in self.MARKETS:
                try:
                    value_bets = await self._find_value_bets_for_market(
                        fixture_id, fixture_name, market, min_edge, min_odds, max_odds
                    )

                    # Get actual results and settle bets
                    if value_bets:
                        actual_result = await self._get_actual_result(fixture_id, market)

                        for bet in value_bets:
                            bet.actual_result = actual_result
                            if actual_result is not None:
                                self._settle_bet(bet, actual_result, stake)
                            all_bets.append(bet)

                except Exception as e:
                    logger.debug(f"Error processing {market} for {fixture_id}: {e}")

        # Calculate results
        results.bets = all_bets
        results.total_bets = len(all_bets)

        settled_bets = [b for b in all_bets if b.won is not None]
        results.wins = sum(1 for b in settled_bets if b.won == True)
        results.losses = sum(1 for b in settled_bets if b.won == False)
        results.pushes = sum(1 for b in settled_bets if b.profit == 0 and b.won is not None)

        results.total_staked = len(settled_bets) * stake
        results.total_profit = sum(b.profit or 0 for b in settled_bets)

        if results.total_staked > 0:
            results.roi = (results.total_profit / results.total_staked) * 100

        if settled_bets:
            results.win_rate = (results.wins / len(settled_bets)) * 100
            results.avg_edge = sum(b.edge_percent for b in settled_bets) / len(settled_bets)
            results.avg_odds = sum(b.book_odds for b in settled_bets) / len(settled_bets)

        return results

    async def _find_value_bets_for_market(
        self,
        fixture_id: str,
        fixture_name: str,
        market: str,
        min_edge: float,
        min_odds: float,
        max_odds: float
    ) -> List[BacktestBet]:
        """Find value bets for a specific market."""
        value_bets = []

        # Collect odds from all sportsbooks
        all_odds = {}  # {(selection, line): {book: decimal_odds}}

        for book in self.SPORTSBOOKS:
            try:
                # Add delay to avoid rate limiting
                await asyncio.sleep(0.5)

                # Retry logic
                for attempt in range(3):
                    try:
                        response = await self.api._request('GET', '/fixtures/odds/historical', params={
                            'fixture_id': fixture_id,
                            'sportsbook': book,
                            'market': market,
                            'include_timeseries': 'true'
                        })
                        break
                    except Exception as retry_err:
                        if attempt < 2:
                            await asyncio.sleep(2)
                        else:
                            raise retry_err

                if response and response.get('data'):
                    for fixture_data in response['data']:
                        for odd in fixture_data.get('odds', []):
                            # Get the last (most recent) entry
                            entries = odd.get('entries', [])
                            if not entries:
                                continue

                            last_entry = entries[-1]
                            american_price = last_entry.get('price')
                            line = last_entry.get('points')

                            # Parse selection from name
                            name = odd.get('name', '').lower()
                            if 'over' in name:
                                selection = 'over'
                            elif 'under' in name:
                                selection = 'under'
                            else:
                                continue

                            # Extract line from name if not in points (e.g., "Over 9.5" -> 9.5)
                            if line is None:
                                import re
                                match = re.search(r'[\d.]+', name)
                                if match:
                                    line = float(match.group())
                                else:
                                    continue

                            if american_price is None:
                                continue

                            decimal_odds = american_to_decimal(american_price)

                            key = (selection, float(line))
                            if key not in all_odds:
                                all_odds[key] = {}
                            all_odds[key][book] = decimal_odds

            except Exception as e:
                logger.debug(f"Error fetching {book} odds for {market}: {e}")

        # Calculate fair odds and find value
        for (selection, line), book_odds in all_odds.items():
            if len(book_odds) < 2:
                continue  # Need at least 2 books for comparison

            # Get opposite selection odds for devigging
            opposite_selection = 'under' if selection == 'over' else 'over'
            opposite_key = (opposite_selection, line)

            if opposite_key not in all_odds:
                continue

            # Calculate fair odds using average market
            avg_over = sum(all_odds.get(('over', line), {}).values()) / len(all_odds.get(('over', line), {})) if all_odds.get(('over', line)) else 0
            avg_under = sum(all_odds.get(('under', line), {}).values()) / len(all_odds.get(('under', line), {})) if all_odds.get(('under', line)) else 0

            if avg_over <= 0 or avg_under <= 0:
                continue

            fair_odds_dict = devig_multiplicative({'over': avg_over, 'under': avg_under})
            fair_odds = fair_odds_dict.get(selection, 0)

            if fair_odds <= 0:
                continue

            # Find best odds and check for value
            for book, odds in book_odds.items():
                if not (min_odds <= odds <= max_odds):
                    continue

                edge = ((odds / fair_odds) - 1) * 100

                if edge >= min_edge:
                    bet = BacktestBet(
                        fixture_id=fixture_id,
                        fixture_name=fixture_name,
                        market=market,
                        selection=f"{selection.title()} {line}",
                        line=line,
                        book_odds=odds,
                        book_name=book,
                        fair_odds=fair_odds,
                        edge_percent=edge
                    )
                    value_bets.append(bet)

        return value_bets

    async def _get_actual_result(self, fixture_id: str, market: str) -> Optional[float]:
        """Get the actual result for a market."""
        try:
            response = await self.api._request('GET', '/fixtures/results', params={
                'fixture_id': fixture_id
            })

            if not response or not response.get('data'):
                return None

            data = response['data'][0]
            stats = data.get('stats', {})

            # Extract home and away stats
            home_stats = {}
            away_stats = {}

            for entry in stats.get('home', []):
                if entry.get('period') == 'all':
                    home_stats = entry.get('stats', {})
                    break

            for entry in stats.get('away', []):
                if entry.get('period') == 'all':
                    away_stats = entry.get('stats', {})
                    break

            market_lower = market.lower()

            if 'shots on target' in market_lower:
                home = home_stats.get('ontarget_scoring_att', 0) or 0
                away = away_stats.get('ontarget_scoring_att', 0) or 0
                return home + away

            elif 'shots' in market_lower:
                home = home_stats.get('total_scoring_att', 0) or 0
                away = away_stats.get('total_scoring_att', 0) or 0
                return home + away

            elif 'corner' in market_lower:
                home = home_stats.get('won_corners', 0) or 0
                away = away_stats.get('won_corners', 0) or 0
                return home + away

            elif 'card' in market_lower:
                home = home_stats.get('total_yellow_card', 0) or 0
                away = away_stats.get('total_yellow_card', 0) or 0
                return home + away

            return None

        except Exception as e:
            logger.debug(f"Error getting results for {fixture_id}: {e}")
            return None

    def _settle_bet(self, bet: BacktestBet, actual_result: float, stake: float):
        """Settle a bet based on actual result."""
        selection_lower = bet.selection.lower()

        if 'over' in selection_lower:
            if actual_result > bet.line:
                bet.won = True
                bet.profit = (bet.book_odds - 1) * stake
            elif actual_result < bet.line:
                bet.won = False
                bet.profit = -stake
            else:
                # Push
                bet.won = None
                bet.profit = 0

        elif 'under' in selection_lower:
            if actual_result < bet.line:
                bet.won = True
                bet.profit = (bet.book_odds - 1) * stake
            elif actual_result > bet.line:
                bet.won = False
                bet.profit = -stake
            else:
                # Push
                bet.won = None
                bet.profit = 0


async def run_full_backtest(
    api_key: str,
    league: str = 'england_-_premier_league',
    min_edge: float = 10.0,
    min_odds: float = 1.5,
    max_odds: float = 4.0
) -> BacktestResults:
    """Run a full backtest on completed fixtures."""

    client = OpticOddsClient(api_key)
    backtester = Backtester(client)

    try:
        # Get completed fixtures
        response = await client._request('GET', '/fixtures', params={
            'sport': 'soccer',
            'league': league,
            'status': 'completed'
        })

        fixtures = response.get('data', [])  # All fixtures
        logger.info(f"Found {len(fixtures)} completed fixtures to backtest")

        # Run backtest
        results = await backtester.run_backtest(
            fixtures=fixtures,
            min_edge=min_edge,
            min_odds=min_odds,
            max_odds=max_odds
        )

        return results

    finally:
        await client.close()
