"""Fast backtesting with progress output and bet limits per bookmaker."""

import asyncio
import re
import sys
from collections import defaultdict
from datetime import datetime
from src.api import OpticOddsClient
from src.utils import ConfigManager

# Configuration
MIN_BETS_PER_BOOK_PER_DAY = 3
MAX_BETS_PER_BOOK_PER_DAY = 15


def american_to_decimal(american_odds):
    """Convert American odds to decimal odds."""
    if american_odds >= 100:
        return (american_odds / 100) + 1
    else:
        return (100 / abs(american_odds)) + 1


async def backtest_fixture(client, fixture, min_edge=5.0, min_odds=1.5, max_odds=3.0):
    """Backtest a single fixture."""
    fixture_id = fixture['id']
    fixture_name = f"{fixture.get('home_team_display')} vs {fixture.get('away_team_display')}"

    # Extract date from fixture
    start_date = fixture.get('start_date', '')
    fixture_date = start_date[:10] if start_date else 'unknown'

    bets = []
    sportsbooks = [
        'Pinnacle',      # Sharp book for reference
        'Betsson',       # Value Profits
        'LeoVegas',      # Value Profits
        'Unibet',        # Value Profits
    ]
    markets = ['Total Corners', 'Total Shots', 'Total Shots On Target']

    for market in markets:
        all_odds = {}

        for book in sportsbooks:
            try:
                await asyncio.sleep(0.3)  # Rate limit
                response = await client._request('GET', '/fixtures/odds/historical', params={
                    'fixture_id': fixture_id,
                    'sportsbook': book,
                    'market': market,
                    'include_timeseries': 'true'
                })

                if response.get('data'):
                    for fd in response['data']:
                        for odd in fd.get('odds', []):
                            entries = odd.get('entries', [])
                            if not entries:
                                continue

                            last = entries[-1]
                            price = last.get('price')
                            line = last.get('points')
                            name = odd.get('name', '').lower()

                            if 'over' in name:
                                sel = 'over'
                            elif 'under' in name:
                                sel = 'under'
                            else:
                                continue

                            if line is None:
                                match = re.search(r'[\d.]+', name)
                                if match:
                                    line = float(match.group())
                                else:
                                    continue

                            if price is None:
                                continue

                            dec = american_to_decimal(price)
                            key = (sel, float(line))
                            if key not in all_odds:
                                all_odds[key] = {}
                            all_odds[key][book] = dec

            except Exception:
                pass

        # Find value bets
        for (selection, line), book_odds in all_odds.items():
            if len(book_odds) < 2:
                continue

            opposite = 'under' if selection == 'over' else 'over'
            opposite_key = (opposite, line)

            if opposite_key not in all_odds:
                continue

            avg_sel = sum(book_odds.values()) / len(book_odds)
            avg_opp = sum(all_odds[opposite_key].values()) / len(all_odds[opposite_key])

            if avg_sel <= 0 or avg_opp <= 0:
                continue

            sel_prob = 1/avg_sel
            opp_prob = 1/avg_opp
            total = sel_prob + opp_prob
            fair_odds = 1 / (sel_prob / total)

            for book, odds in book_odds.items():
                if not (min_odds <= odds <= max_odds):
                    continue

                edge = ((odds / fair_odds) - 1) * 100

                if edge >= min_edge:
                    bets.append({
                        'fixture_id': fixture_id,
                        'fixture_name': fixture_name,
                        'fixture_date': fixture_date,
                        'market': market,
                        'selection': f"{selection.title()} {line}",
                        'line': line,
                        'book': book,
                        'odds': odds,
                        'fair_odds': fair_odds,
                        'edge': edge
                    })

    # Get results
    try:
        await asyncio.sleep(0.3)
        results = await client._request('GET', '/fixtures/results', params={
            'fixture_id': fixture_id
        })

        if results.get('data'):
            data = results['data'][0]
            stats = data.get('stats', {})

            home_stats = {}
            away_stats = {}
            for entry in stats.get('home', []):
                if entry.get('period') == 'all':
                    home_stats = entry.get('stats', {})
            for entry in stats.get('away', []):
                if entry.get('period') == 'all':
                    away_stats = entry.get('stats', {})

            # Settle bets
            for bet in bets:
                market = bet['market'].lower()
                actual = None

                if 'shots on target' in market:
                    home = home_stats.get('ontarget_scoring_att', 0) or 0
                    away = away_stats.get('ontarget_scoring_att', 0) or 0
                    actual = home + away
                elif 'shots' in market:
                    home = home_stats.get('total_scoring_att', 0) or 0
                    away = away_stats.get('total_scoring_att', 0) or 0
                    actual = home + away
                elif 'corner' in market:
                    home = home_stats.get('won_corners', 0) or 0
                    away = away_stats.get('won_corners', 0) or 0
                    actual = home + away

                bet['actual'] = actual

                if actual is not None:
                    sel = bet['selection'].lower()
                    line = bet['line']

                    if 'over' in sel:
                        bet['won'] = actual > line
                    else:
                        bet['won'] = actual < line

                    if actual == line:
                        bet['profit'] = 0  # Push
                    elif bet['won']:
                        bet['profit'] = (bet['odds'] - 1) * 10
                    else:
                        bet['profit'] = -10
    except Exception:
        pass

    return bets


def filter_bets_per_bookmaker(all_bets, min_per_day=3, max_per_day=15):
    """
    Filter bets to have between min and max bets per bookmaker per day.
    Prioritizes highest edge bets when limiting.
    """
    # Group bets by (date, bookmaker)
    bets_by_date_book = defaultdict(list)
    for bet in all_bets:
        key = (bet.get('fixture_date', 'unknown'), bet['book'])
        bets_by_date_book[key].append(bet)

    filtered_bets = []

    for (date, book), bets in bets_by_date_book.items():
        # Sort by edge (highest first)
        sorted_bets = sorted(bets, key=lambda x: x['edge'], reverse=True)

        # Take between min and max bets
        # If we have fewer than min, skip this day/book (not enough value)
        # If we have more than max, take only top max by edge
        if len(sorted_bets) >= min_per_day:
            selected = sorted_bets[:max_per_day]
            filtered_bets.extend(selected)

    return filtered_bets


async def main():
    config = ConfigManager()
    settings = config.get_settings()
    client = OpticOddsClient(settings.opticodds_api_key)

    leagues = [
        # Top 5 leagues
        'spain_-_la_liga',
        'germany_-_bundesliga',
        'italy_-_serie_a',
        'france_-_ligue_1',
        'england_-_premier_league',
        # Other major leagues
        'netherlands_-_eredivisie',
        'portugal_-_primeira_liga',
        'belgium_-_first_division_a',
        'turkey_-_super_lig',
        'scotland_-_premiership',
        # Cup competitions
        'england_-_fa_cup',
        'spain_-_copa_del_rey',
        'germany_-_dfb_pokal',
        'italy_-_coppa_italia',
        'france_-_coupe_de_france',
        # European competitions
        'europe_-_champions_league',
        'europe_-_europa_league',
        'europe_-_conference_league',
    ]

    # Calculate date range for last 30 days
    from datetime import datetime, timedelta
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    start_date_str = start_date.strftime('%Y-%m-%dT00:00:00Z')
    end_date_str = end_date.strftime('%Y-%m-%dT23:59:59Z')

    print(f"Backtesting from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (30 days)", flush=True)

    all_bets = []

    for league in leagues:
        print(f"\n{'='*60}", flush=True)
        print(f"Processing {league}", flush=True)
        print('='*60, flush=True)

        try:
            response = await client._request('GET', '/fixtures', params={
                'sport': 'soccer',
                'league': league,
                'status': 'completed',
                'start_date_after': start_date_str,
                'start_date_before': end_date_str,
            })

            fixtures = response.get('data', [])
            print(f"Found {len(fixtures)} completed fixtures", flush=True)

            for i, fixture in enumerate(fixtures):
                name = f"{fixture.get('home_team_display')} vs {fixture.get('away_team_display')}"
                print(f"  [{i+1}/{len(fixtures)}] {name[:50]}...", end='', flush=True)

                bets = await backtest_fixture(client, fixture)
                all_bets.extend(bets)

                wins = sum(1 for b in bets if b.get('won') == True)
                losses = sum(1 for b in bets if b.get('won') == False)
                print(f" {len(bets)} bets ({wins}W/{losses}L)", flush=True)

        except Exception as e:
            print(f"Error: {e}", flush=True)

    await client.close()

    # Apply bookmaker limit filter
    print("\n" + "="*70, flush=True)
    print(f"APPLYING FILTER: {MIN_BETS_PER_BOOK_PER_DAY}-{MAX_BETS_PER_BOOK_PER_DAY} bets per bookmaker per day", flush=True)
    print("="*70, flush=True)

    filtered_bets = filter_bets_per_bookmaker(
        all_bets,
        min_per_day=MIN_BETS_PER_BOOK_PER_DAY,
        max_per_day=MAX_BETS_PER_BOOK_PER_DAY
    )

    # Show distribution by date/book
    bets_by_date_book = defaultdict(list)
    for bet in filtered_bets:
        key = (bet.get('fixture_date', 'unknown'), bet['book'])
        bets_by_date_book[key].append(bet)

    print(f"\nBets per bookmaker per day:", flush=True)
    for (date, book), bets in sorted(bets_by_date_book.items()):
        print(f"  {date} @ {book:10}: {len(bets)} bets", flush=True)

    # Summary - Unfiltered
    print("\n" + "="*70, flush=True)
    print("UNFILTERED RESULTS (all value bets)", flush=True)
    print("="*70, flush=True)

    settled_all = [b for b in all_bets if 'won' in b]
    wins_all = sum(1 for b in settled_all if b['won'] == True)
    losses_all = sum(1 for b in settled_all if b['won'] == False)
    profit_all = sum(b.get('profit', 0) for b in settled_all)
    staked_all = len(settled_all) * 10

    print(f"Total Bets: {len(settled_all)}", flush=True)
    print(f"Wins: {wins_all} | Losses: {losses_all}", flush=True)
    if settled_all:
        print(f"Win Rate: {(wins_all/len(settled_all))*100:.1f}%", flush=True)
        print(f"Avg Edge: {sum(b['edge'] for b in settled_all)/len(settled_all):.1f}%", flush=True)
    print(f"Total Staked: ${staked_all:.2f} | Profit: ${profit_all:.2f}", flush=True)
    if staked_all > 0:
        print(f"ROI: {(profit_all/staked_all)*100:.1f}%", flush=True)

    # Summary - Filtered
    print("\n" + "="*70, flush=True)
    print(f"FILTERED RESULTS ({MIN_BETS_PER_BOOK_PER_DAY}-{MAX_BETS_PER_BOOK_PER_DAY} bets/book/day)", flush=True)
    print("="*70, flush=True)

    settled = [b for b in filtered_bets if 'won' in b]
    wins = sum(1 for b in settled if b['won'] == True)
    losses = sum(1 for b in settled if b['won'] == False)
    pushes = sum(1 for b in settled if b.get('profit') == 0)
    profit = sum(b.get('profit', 0) for b in settled)
    staked = len(settled) * 10

    print(f"\nTotal Bets: {len(filtered_bets)}", flush=True)
    print(f"Settled: {len(settled)}", flush=True)
    print(f"Wins: {wins} | Losses: {losses} | Pushes: {pushes}", flush=True)

    if settled:
        print(f"Win Rate: {(wins/len(settled))*100:.1f}%", flush=True)
        print(f"Avg Edge: {sum(b['edge'] for b in settled)/len(settled):.1f}%", flush=True)
        print(f"Avg Odds: {sum(b['odds'] for b in settled)/len(settled):.2f}", flush=True)

    print(f"\nTotal Staked: ${staked:.2f}", flush=True)
    print(f"Total Profit: ${profit:.2f}", flush=True)
    if staked > 0:
        print(f"ROI: {(profit/staked)*100:.1f}%", flush=True)

    # Show all filtered bets
    print("\n" + "="*70, flush=True)
    print("FILTERED BETS (sorted by profit)", flush=True)
    print("="*70, flush=True)

    for bet in sorted(settled, key=lambda x: x.get('profit', 0), reverse=True):
        status = 'WIN ' if bet['won'] else 'LOSS'
        pnl = f"+${bet['profit']:.2f}" if bet['profit'] > 0 else f"-${abs(bet['profit']):.2f}" if bet['profit'] < 0 else "$0"
        print(f"[{status}] {bet['edge']:5.1f}% | {bet['odds']:.2f} @ {bet['book']:10} | {bet['selection']:15} | {bet['market']:25} | {bet['fixture_date']} | {pnl}", flush=True)


if __name__ == '__main__':
    asyncio.run(main())
