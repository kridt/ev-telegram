"""
Comprehensive EV Strategy Analyzer
==================================
Analyzes the comprehensive odds data to find profitable strategies.

Usage:
  python analyze_comprehensive.py                  # Quick summary
  python analyze_comprehensive.py --efficiency     # Market efficiency analysis
  python analyze_comprehensive.py --backtest       # Full backtest with current filters
  python analyze_comprehensive.py --optimize       # Grid search for optimal strategy
"""

import json
import os
import sys
from collections import defaultdict
from itertools import product

DATA_FILE = os.path.join(os.path.dirname(__file__), "comprehensive_odds_data.json")


def load_data():
    """Load comprehensive odds data."""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_actual_value(results, market):
    """Get actual value from match results for a given market."""
    if not results:
        return None

    market_lower = market.lower()

    # Team-specific markets
    if 'team total' in market_lower:
        if 'home' in market_lower:
            if 'corner' in market_lower:
                return results.get('home_corners')
            elif 'shot' in market_lower and 'target' in market_lower:
                return results.get('home_shots_on_target')
            elif 'shot' in market_lower:
                return results.get('home_shots')
        elif 'away' in market_lower:
            if 'corner' in market_lower:
                return results.get('away_corners')
            elif 'shot' in market_lower and 'target' in market_lower:
                return results.get('away_shots_on_target')
            elif 'shot' in market_lower:
                return results.get('away_shots')

    # Total markets
    if 'corner' in market_lower:
        return results.get('total_corners')
    elif 'shot' in market_lower and 'target' in market_lower:
        return results.get('total_shots_on_target')
    elif 'shot' in market_lower:
        return results.get('total_shots')
    elif 'yellow' in market_lower:
        return results.get('total_yellow_cards')
    elif 'red' in market_lower:
        return results.get('total_red_cards')
    elif 'foul' in market_lower:
        return results.get('total_fouls')
    elif 'offside' in market_lower:
        return results.get('total_offsides')
    elif 'goal' in market_lower:
        return results.get('total_goals')

    return None


def calculate_fair_odds(odds_by_book, line, min_books=3):
    """Calculate fair odds using multiplicative devigging."""
    over_odds = []
    under_odds = []

    for book, odds_list in odds_by_book.items():
        for odd in odds_list:
            if odd['line'] != line:
                continue
            if odd['selection'] == 'Over':
                over_odds.append(odd['decimal_odds'])
            elif odd['selection'] == 'Under':
                under_odds.append(odd['decimal_odds'])

    if len(over_odds) < min_books or len(under_odds) < min_books:
        return None, None

    best_over = max(over_odds)
    best_under = max(under_odds)

    if best_over <= 1 or best_under <= 1:
        return None, None

    imp_o = 1 / best_over
    imp_u = 1 / best_under
    total = imp_o + imp_u

    if total <= 0:
        return None, None

    fair_over = 1 / (imp_o / total)
    fair_under = 1 / (imp_u / total)

    return fair_over, fair_under


def summary(data):
    """Show data summary."""
    print("=" * 70)
    print("DATA SUMMARY")
    print("=" * 70)

    meta = data.get("metadata", {})
    print(f"Collected at: {meta.get('collected_at', 'Unknown')}")
    print(f"Date range: {meta.get('date_range', {}).get('start')} to {meta.get('date_range', {}).get('end')}")
    print(f"Fixtures: {meta.get('fixture_count', len(data.get('fixtures', [])))}")
    print(f"Total odds entries: {meta.get('total_odds_entries', 'Unknown')}")
    print()

    print("Markets found:")
    for m in meta.get('markets_found', []):
        print(f"  - {m}")
    print()

    print("Sportsbooks found:")
    for s in meta.get('sportsbooks_found', []):
        print(f"  - {s}")
    print()

    # Count by league
    by_league = defaultdict(int)
    for f in data.get('fixtures', []):
        league = f.get('league', {}).get('name', 'Unknown')
        by_league[league] += 1

    print("Fixtures by league:")
    for league, count in sorted(by_league.items(), key=lambda x: x[1], reverse=True):
        print(f"  {league}: {count}")


def efficiency_analysis(data):
    """Analyze market efficiency."""
    print("=" * 70)
    print("MARKET EFFICIENCY ANALYSIS")
    print("=" * 70)
    print(f"Fixtures: {len(data.get('fixtures', []))}")
    print()

    all_edges = []
    by_league = defaultdict(list)
    by_market = defaultdict(list)
    by_book = defaultdict(list)

    for fixture in data.get("fixtures", []):
        league = fixture.get("league", {}).get("name", "Unknown")
        results = fixture.get("results", {})

        for market, odds_by_book in fixture.get("odds", {}).items():
            all_lines = set()
            for book, odds_list in odds_by_book.items():
                for odd in odds_list:
                    all_lines.add(odd['line'])

            for line in all_lines:
                fair_over, fair_under = calculate_fair_odds(odds_by_book, line, min_books=3)
                if fair_over is None:
                    continue

                for book, odds_list in odds_by_book.items():
                    for odd in odds_list:
                        if odd['line'] != line:
                            continue
                        fair = fair_over if odd['selection'] == 'Over' else fair_under
                        edge = ((odd['decimal_odds'] / fair) - 1) * 100
                        all_edges.append(edge)
                        by_league[league].append(edge)
                        by_market[market].append(edge)
                        by_book[book].append(edge)

    if not all_edges:
        print("No edges calculated - insufficient data")
        return

    all_edges.sort(reverse=True)

    print("EDGE DISTRIBUTION:")
    print(f"  Total edge calculations: {len(all_edges)}")
    print(f"  Max edge: {max(all_edges):+.2f}%")
    print(f"  Edges >= 10%: {len([e for e in all_edges if e >= 10])}")
    print(f"  Edges >= 5%: {len([e for e in all_edges if e >= 5])}")
    print(f"  Edges >= 3%: {len([e for e in all_edges if e >= 3])}")
    print()

    print("TOP 20 EDGES:")
    for i, edge in enumerate(all_edges[:20], 1):
        print(f"  {i:2}. {edge:+.2f}%")
    print()

    print("BY LEAGUE (sorted by max edge):")
    for league, edges in sorted(by_league.items(), key=lambda x: max(x[1]) if x[1] else -100, reverse=True):
        if not edges:
            continue
        max_e = max(edges)
        above_5 = len([e for e in edges if e >= 5])
        print(f"  {league}: max {max_e:+.2f}%, edges>=5%: {above_5}/{len(edges)}")
    print()

    print("BY MARKET (sorted by max edge):")
    for market, edges in sorted(by_market.items(), key=lambda x: max(x[1]) if x[1] else -100, reverse=True):
        if not edges:
            continue
        max_e = max(edges)
        above_5 = len([e for e in edges if e >= 5])
        print(f"  {market}: max {max_e:+.2f}%, edges>=5%: {above_5}/{len(edges)}")
    print()

    print("BY SPORTSBOOK (where value found, sorted by max edge):")
    for book, edges in sorted(by_book.items(), key=lambda x: max(x[1]) if x[1] else -100, reverse=True)[:10]:
        if not edges:
            continue
        max_e = max(edges)
        above_5 = len([e for e in edges if e >= 5])
        print(f"  {book}: max {max_e:+.2f}%, edges>=5%: {above_5}/{len(edges)}")


def backtest(data, config=None):
    """Run backtest with given config."""
    if config is None:
        config = {
            "min_edge": 5,
            "max_edge": 30,
            "min_odds": 1.5,
            "max_odds": 3.0,
            "min_books": 3,
        }

    print("=" * 70)
    print("BACKTEST")
    print("=" * 70)
    print(f"Config: Edge {config['min_edge']}-{config['max_edge']}% | Odds {config['min_odds']}-{config['max_odds']} | MinBooks {config['min_books']}")
    print()

    results = {
        "bets": 0, "wins": 0, "losses": 0, "push": 0,
        "staked": 0, "profit": 0,
        "by_league": defaultdict(lambda: {"bets": 0, "wins": 0, "losses": 0, "profit": 0, "staked": 0}),
        "by_market": defaultdict(lambda: {"bets": 0, "wins": 0, "losses": 0, "profit": 0, "staked": 0}),
        "by_book": defaultdict(lambda: {"bets": 0, "wins": 0, "losses": 0, "profit": 0, "staked": 0}),
    }

    leagues_filter = config.get("leagues")
    markets_filter = config.get("markets")
    books_filter = config.get("books")

    for fixture in data.get("fixtures", []):
        league = fixture.get("league", {}).get("name", "Unknown")
        if leagues_filter and league not in leagues_filter:
            continue

        match_results = fixture.get("results", {})

        for market, odds_by_book in fixture.get("odds", {}).items():
            if markets_filter and market not in markets_filter:
                continue

            if books_filter:
                odds_by_book = {k: v for k, v in odds_by_book.items() if k in books_filter}

            actual = get_actual_value(match_results, market)
            if actual is None:
                continue

            all_lines = set()
            for book, odds_list in odds_by_book.items():
                for odd in odds_list:
                    all_lines.add(odd['line'])

            for line in all_lines:
                fair_over, fair_under = calculate_fair_odds(odds_by_book, line, config['min_books'])
                if fair_over is None:
                    continue

                for book, odds_list in odds_by_book.items():
                    for odd in odds_list:
                        if odd['line'] != line:
                            continue

                        fair = fair_over if odd['selection'] == 'Over' else fair_under
                        edge = ((odd['decimal_odds'] / fair) - 1) * 100
                        decimal_odds = odd['decimal_odds']

                        if edge < config['min_edge'] or edge > config['max_edge']:
                            continue
                        if decimal_odds < config['min_odds'] or decimal_odds > config['max_odds']:
                            continue

                        # Determine result
                        stake = 10
                        if actual == line:
                            result = "push"
                            profit = 0
                        elif odd['selection'] == 'Over':
                            result = "won" if actual > line else "lost"
                        else:
                            result = "won" if actual < line else "lost"

                        if result == "won":
                            profit = stake * (decimal_odds - 1)
                        elif result == "lost":
                            profit = -stake
                        else:
                            profit = 0

                        results["bets"] += 1
                        results["staked"] += stake
                        results["profit"] += profit
                        if result == "won":
                            results["wins"] += 1
                        elif result == "lost":
                            results["losses"] += 1
                        else:
                            results["push"] += 1

                        results["by_league"][league]["bets"] += 1
                        results["by_league"][league]["staked"] += stake
                        results["by_league"][league]["profit"] += profit
                        if result == "won":
                            results["by_league"][league]["wins"] += 1
                        elif result == "lost":
                            results["by_league"][league]["losses"] += 1

                        results["by_market"][market]["bets"] += 1
                        results["by_market"][market]["staked"] += stake
                        results["by_market"][market]["profit"] += profit
                        if result == "won":
                            results["by_market"][market]["wins"] += 1
                        elif result == "lost":
                            results["by_market"][market]["losses"] += 1

                        results["by_book"][book]["bets"] += 1
                        results["by_book"][book]["staked"] += stake
                        results["by_book"][book]["profit"] += profit
                        if result == "won":
                            results["by_book"][book]["wins"] += 1
                        elif result == "lost":
                            results["by_book"][book]["losses"] += 1

    # Print results
    print(f"Total bets: {results['bets']}")
    print(f"Record: {results['wins']}W / {results['losses']}L / {results['push']}P")
    if results['wins'] + results['losses'] > 0:
        wr = results['wins'] / (results['wins'] + results['losses']) * 100
        print(f"Win rate: {wr:.1f}%")
    print(f"Profit: {results['profit']:+.2f} units")
    if results['staked'] > 0:
        roi = results['profit'] / results['staked'] * 100
        print(f"ROI: {roi:+.2f}%")
    print()

    if results["by_league"]:
        print("By League:")
        for league, stats in sorted(results["by_league"].items(), key=lambda x: x[1]["profit"], reverse=True):
            roi = stats["profit"] / stats["staked"] * 100 if stats["staked"] > 0 else 0
            print(f"  {league}: {stats['bets']} bets, {stats['wins']}W/{stats['losses']}L, {stats['profit']:+.1f} ({roi:+.1f}%)")
        print()

    if results["by_market"]:
        print("By Market:")
        for market, stats in sorted(results["by_market"].items(), key=lambda x: x[1]["profit"], reverse=True):
            roi = stats["profit"] / stats["staked"] * 100 if stats["staked"] > 0 else 0
            print(f"  {market}: {stats['bets']} bets, {stats['wins']}W/{stats['losses']}L, {stats['profit']:+.1f} ({roi:+.1f}%)")
        print()

    if results["by_book"]:
        print("By Sportsbook:")
        for book, stats in sorted(results["by_book"].items(), key=lambda x: x[1]["profit"], reverse=True)[:10]:
            roi = stats["profit"] / stats["staked"] * 100 if stats["staked"] > 0 else 0
            print(f"  {book}: {stats['bets']} bets, {stats['wins']}W/{stats['losses']}L, {stats['profit']:+.1f} ({roi:+.1f}%)")

    return results


def optimize(data):
    """Grid search for optimal strategy."""
    print("=" * 70)
    print("STRATEGY OPTIMIZER")
    print("=" * 70)
    print()

    edge_ranges = [(3, 30), (5, 30), (7, 30), (5, 20), (7, 20), (10, 30)]
    odds_ranges = [(1.5, 3.0), (1.6, 2.8), (1.7, 2.5), (1.8, 2.3)]
    min_books_options = [3, 4, 5]

    best_results = []

    total = len(edge_ranges) * len(odds_ranges) * len(min_books_options)
    print(f"Testing {total} combinations...")

    for i, (edge_range, odds_range, min_books) in enumerate(product(edge_ranges, odds_ranges, min_books_options), 1):
        config = {
            "min_edge": edge_range[0],
            "max_edge": edge_range[1],
            "min_odds": odds_range[0],
            "max_odds": odds_range[1],
            "min_books": min_books,
        }

        # Silent backtest
        result = {"bets": 0, "wins": 0, "losses": 0, "profit": 0, "staked": 0}

        for fixture in data.get("fixtures", []):
            match_results = fixture.get("results", {})

            for market, odds_by_book in fixture.get("odds", {}).items():
                actual = get_actual_value(match_results, market)
                if actual is None:
                    continue

                all_lines = set()
                for book, odds_list in odds_by_book.items():
                    for odd in odds_list:
                        all_lines.add(odd['line'])

                for line in all_lines:
                    fair_over, fair_under = calculate_fair_odds(odds_by_book, line, min_books)
                    if fair_over is None:
                        continue

                    for book, odds_list in odds_by_book.items():
                        for odd in odds_list:
                            if odd['line'] != line:
                                continue

                            fair = fair_over if odd['selection'] == 'Over' else fair_under
                            edge = ((odd['decimal_odds'] / fair) - 1) * 100

                            if edge < config['min_edge'] or edge > config['max_edge']:
                                continue
                            if odd['decimal_odds'] < config['min_odds'] or odd['decimal_odds'] > config['max_odds']:
                                continue

                            stake = 10
                            if actual == line:
                                profit = 0
                            elif odd['selection'] == 'Over':
                                profit = stake * (odd['decimal_odds'] - 1) if actual > line else -stake
                            else:
                                profit = stake * (odd['decimal_odds'] - 1) if actual < line else -stake

                            result["bets"] += 1
                            result["staked"] += stake
                            result["profit"] += profit
                            if profit > 0:
                                result["wins"] += 1
                            elif profit < 0:
                                result["losses"] += 1

        if result["bets"] >= 10:
            roi = result["profit"] / result["staked"] * 100 if result["staked"] > 0 else 0
            wr = result["wins"] / (result["wins"] + result["losses"]) * 100 if result["wins"] + result["losses"] > 0 else 0
            best_results.append({
                "config": config,
                "bets": result["bets"],
                "roi": roi,
                "profit": result["profit"],
                "win_rate": wr,
            })

        if i % 20 == 0:
            print(f"  Progress: {i}/{total}")

    best_results.sort(key=lambda x: x["roi"], reverse=True)

    print()
    print("TOP 10 STRATEGIES BY ROI:")
    print("-" * 70)
    for i, r in enumerate(best_results[:10], 1):
        c = r["config"]
        print(f"{i:2}. ROI: {r['roi']:+6.1f}% | Profit: {r['profit']:+8.1f} | Bets: {r['bets']:3} | WR: {r['win_rate']:.1f}%")
        print(f"    Edge: {c['min_edge']}-{c['max_edge']}% | Odds: {c['min_odds']}-{c['max_odds']} | MinBooks: {c['min_books']}")


if __name__ == "__main__":
    if not os.path.exists(DATA_FILE):
        print(f"Error: Data file not found: {DATA_FILE}")
        print("Run collect_comprehensive_data.py first!")
        sys.exit(1)

    print("Loading data...")
    data = load_data()
    print(f"Loaded {len(data.get('fixtures', []))} fixtures")
    print()

    if len(sys.argv) > 1:
        if sys.argv[1] == "--efficiency":
            efficiency_analysis(data)
        elif sys.argv[1] == "--backtest":
            backtest(data)
        elif sys.argv[1] == "--optimize":
            optimize(data)
        else:
            summary(data)
    else:
        summary(data)
        print()
        print("-" * 70)
        print("Options: --efficiency | --backtest | --optimize")
