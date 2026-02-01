"""
EV Strategy Analyzer
====================
Reads raw odds data and tests different filter combinations to find optimal EV strategy.

Usage:
  python analyze_ev_strategies.py              # Quick analysis with current filters
  python analyze_ev_strategies.py --optimize   # Full grid search for best strategy
"""

import json
import os
import sys
from collections import defaultdict

RAW_DATA_FILE = os.path.join(os.path.dirname(__file__), "raw_odds_data.json")


def load_data():
    """Load raw odds data."""
    with open(RAW_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_actual_value(results, market):
    """Get actual value from match results."""
    if not results:
        return None
    if 'shots on target' in market.lower():
        return results.get('shots_on_target', 0)
    elif 'shot' in market.lower():
        return results.get('total_shots', 0)
    elif 'corner' in market.lower():
        return results.get('corners', 0)
    return 0


def calculate_fair_odds_for_line(odds_by_book, line, min_books=3):
    """Calculate fair odds for a specific line using multiplicative devigging."""
    over_odds = []
    under_odds = []

    for book, odds_list in odds_by_book.items():
        for odd in odds_list:
            if odd['line'] != line:
                continue
            if odd['selection'] == 'Over':
                over_odds.append(odd['odds'])
            elif odd['selection'] == 'Under':
                under_odds.append(odd['odds'])

    if len(over_odds) < min_books or len(under_odds) < min_books:
        return None, None

    # Use best odds for devig (highest odds = most favorable)
    best_over = max(over_odds)
    best_under = max(under_odds)

    if best_over <= 1 or best_under <= 1:
        return None, None

    # Multiplicative devig
    implied_over = 1 / best_over
    implied_under = 1 / best_under
    total_implied = implied_over + implied_under

    if total_implied <= 0:
        return None, None

    fair_prob_over = implied_over / total_implied
    fair_prob_under = implied_under / total_implied

    fair_over = 1 / fair_prob_over
    fair_under = 1 / fair_prob_under

    return fair_over, fair_under


def run_backtest(data, config):
    """Run backtest with given config."""
    min_edge = config.get("min_edge", 5)
    max_edge = config.get("max_edge", 25)
    min_odds = config.get("min_odds", 1.5)
    max_odds = config.get("max_odds", 3.0)
    min_books = config.get("min_books", 4)
    markets_filter = config.get("markets", None)
    leagues_filter = config.get("leagues", None)
    books_filter = config.get("books", None)

    results = {
        "total_bets": 0,
        "wins": 0,
        "losses": 0,
        "push": 0,
        "total_staked": 0,
        "total_profit": 0,
        "by_league": defaultdict(lambda: {"bets": 0, "wins": 0, "losses": 0, "profit": 0, "staked": 0}),
        "by_market": defaultdict(lambda: {"bets": 0, "wins": 0, "losses": 0, "profit": 0, "staked": 0}),
        "by_book": defaultdict(lambda: {"bets": 0, "wins": 0, "losses": 0, "profit": 0, "staked": 0}),
        "bets": []
    }

    for fixture in data.get("fixtures", []):
        league = fixture.get("league", "")
        if leagues_filter and league not in leagues_filter:
            continue

        match_results = fixture.get("results", {})

        for market, odds_by_book in fixture.get("odds_by_market", {}).items():
            if markets_filter and market not in markets_filter:
                continue

            # Filter books if specified
            if books_filter:
                odds_by_book = {k: v for k, v in odds_by_book.items() if k in books_filter}

            # Get all unique lines
            all_lines = set()
            for book, odds_list in odds_by_book.items():
                for odd in odds_list:
                    all_lines.add(odd['line'])

            actual_value = get_actual_value(match_results, market)
            if actual_value is None:
                continue

            for line in all_lines:
                fair_over, fair_under = calculate_fair_odds_for_line(odds_by_book, line, min_books)
                if fair_over is None:
                    continue

                # Find value bets on this line
                for book, odds_list in odds_by_book.items():
                    for odd in odds_list:
                        if odd['line'] != line:
                            continue

                        selection = odd['selection']
                        decimal_odds = odd['odds']
                        fair = fair_over if selection == 'Over' else fair_under

                        edge = ((decimal_odds / fair) - 1) * 100

                        # Apply filters
                        if edge < min_edge or edge > max_edge:
                            continue
                        if decimal_odds < min_odds or decimal_odds > max_odds:
                            continue

                        # Determine result
                        if actual_value == line:
                            result = "push"
                        elif selection == 'Over':
                            result = "won" if actual_value > line else "lost"
                        else:
                            result = "won" if actual_value < line else "lost"

                        # Calculate profit (flat 10 unit stake)
                        stake = 10
                        if result == "won":
                            profit = stake * (decimal_odds - 1)
                        elif result == "lost":
                            profit = -stake
                        else:
                            profit = 0

                        # Update stats
                        results["total_bets"] += 1
                        results["total_staked"] += stake
                        results["total_profit"] += profit

                        if result == "won":
                            results["wins"] += 1
                        elif result == "lost":
                            results["losses"] += 1
                        else:
                            results["push"] += 1

                        # By league
                        results["by_league"][league]["bets"] += 1
                        results["by_league"][league]["staked"] += stake
                        results["by_league"][league]["profit"] += profit
                        if result == "won":
                            results["by_league"][league]["wins"] += 1
                        elif result == "lost":
                            results["by_league"][league]["losses"] += 1

                        # By market
                        results["by_market"][market]["bets"] += 1
                        results["by_market"][market]["staked"] += stake
                        results["by_market"][market]["profit"] += profit
                        if result == "won":
                            results["by_market"][market]["wins"] += 1
                        elif result == "lost":
                            results["by_market"][market]["losses"] += 1

                        # By book
                        results["by_book"][book]["bets"] += 1
                        results["by_book"][book]["staked"] += stake
                        results["by_book"][book]["profit"] += profit
                        if result == "won":
                            results["by_book"][book]["wins"] += 1
                        elif result == "lost":
                            results["by_book"][book]["losses"] += 1

    # Calculate ROI
    if results["total_staked"] > 0:
        results["roi"] = round(results["total_profit"] / results["total_staked"] * 100, 2)
    else:
        results["roi"] = 0

    if results["wins"] + results["losses"] > 0:
        results["win_rate"] = round(results["wins"] / (results["wins"] + results["losses"]) * 100, 1)
    else:
        results["win_rate"] = 0

    return results


def grid_search(data):
    """Test many filter combinations to find optimal strategy."""
    print("=" * 70)
    print("EV STRATEGY OPTIMIZER - Grid Search")
    print("=" * 70)
    print()

    # Parameter grid
    edge_ranges = [(3, 25), (5, 25), (7, 25), (5, 15), (7, 15), (10, 25), (5, 20)]
    odds_ranges = [(1.5, 3.0), (1.7, 2.5), (1.8, 2.3), (1.5, 2.5), (1.6, 2.8)]
    min_books_options = [3, 4, 5, 6]

    # League combinations
    all_leagues = data.get("config", {}).get("leagues", [])
    profitable_hints = ["Serie A", "Eredivisie", "Primeira Liga"]
    smaller_hints = ["Eredivisie", "Primeira Liga", "Ligue 1"]

    league_combos = [
        None,  # All leagues
        [l for l in profitable_hints if l in all_leagues],
        [l for l in smaller_hints if l in all_leagues],
    ]

    # Market combinations
    all_markets = data.get("config", {}).get("markets", [])
    market_combos = [
        None,  # All markets
        ["Total Corners"] if "Total Corners" in all_markets else None,
        ["Total Shots On Target"] if "Total Shots On Target" in all_markets else None,
    ]
    market_combos = [m for m in market_combos if m is None or m]

    best_results = []

    total_combos = len(edge_ranges) * len(odds_ranges) * len(min_books_options) * len(league_combos) * len(market_combos)
    print(f"Testing {total_combos} combinations...")
    print()

    combo_num = 0
    for edge_range in edge_ranges:
        for odds_range in odds_ranges:
            for min_books in min_books_options:
                for leagues in league_combos:
                    for markets in market_combos:
                        combo_num += 1

                        config = {
                            "min_edge": edge_range[0],
                            "max_edge": edge_range[1],
                            "min_odds": odds_range[0],
                            "max_odds": odds_range[1],
                            "min_books": min_books,
                            "leagues": leagues,
                            "markets": markets,
                        }

                        result = run_backtest(data, config)

                        if result["total_bets"] >= 15:  # Minimum sample size
                            best_results.append({
                                "config": config,
                                "bets": result["total_bets"],
                                "roi": result["roi"],
                                "profit": result["total_profit"],
                                "win_rate": result["win_rate"],
                            })

                        if combo_num % 50 == 0:
                            print(f"  Progress: {combo_num}/{total_combos}...")

    # Sort by ROI
    best_results.sort(key=lambda x: x["roi"], reverse=True)

    print()
    print("=" * 70)
    print("TOP 15 STRATEGIES BY ROI (min 15 bets)")
    print("=" * 70)
    print()

    for i, r in enumerate(best_results[:15], 1):
        c = r["config"]
        leagues_str = "All" if c["leagues"] is None else ", ".join(c["leagues"][:2]) + ("..." if len(c["leagues"] or []) > 2 else "")
        markets_str = "All" if c["markets"] is None else ", ".join(c["markets"][:2])

        print(f"{i:2}. ROI: {r['roi']:+6.1f}% | Profit: {r['profit']:+8.1f} | Bets: {r['bets']:3} | WR: {r['win_rate']:.1f}%")
        print(f"    Edge: {c['min_edge']}-{c['max_edge']}% | Odds: {c['min_odds']}-{c['max_odds']} | MinBooks: {c['min_books']}")
        print(f"    Leagues: {leagues_str} | Markets: {markets_str}")
        print()

    # Save results
    output_file = os.path.join(os.path.dirname(__file__), "ev_optimization_results.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(best_results[:50], f, indent=2)
    print(f"Full results saved to: {output_file}")


def quick_analysis(data):
    """Quick analysis with current filters."""
    print("=" * 70)
    print("QUICK ANALYSIS")
    print("=" * 70)
    print(f"Fixtures loaded: {len(data.get('fixtures', []))}")
    print(f"Date range: {data.get('date_range', {}).get('start')} to {data.get('date_range', {}).get('end')}")
    print()

    config = {
        "min_edge": 5,
        "max_edge": 25,
        "min_odds": 1.5,
        "max_odds": 3.0,
        "min_books": 4,
    }

    print(f"Filters: Edge {config['min_edge']}-{config['max_edge']}% | Odds {config['min_odds']}-{config['max_odds']} | MinBooks {config['min_books']}")
    print()

    result = run_backtest(data, config)

    print(f"Total Bets: {result['total_bets']}")
    print(f"Record: {result['wins']}W / {result['losses']}L / {result['push']}P ({result['win_rate']:.1f}%)")
    print(f"Profit: {result['total_profit']:+.2f} units")
    print(f"ROI: {result['roi']:+.2f}%")
    print()

    if result["by_league"]:
        print("By League:")
        for league, stats in sorted(result["by_league"].items(), key=lambda x: x[1]["profit"], reverse=True):
            roi = stats["profit"] / stats["staked"] * 100 if stats["staked"] > 0 else 0
            print(f"  {league}: {stats['bets']} bets, {stats['wins']}W/{stats['losses']}L, {stats['profit']:+.1f} ({roi:+.1f}%)")
        print()

    if result["by_market"]:
        print("By Market:")
        for market, stats in sorted(result["by_market"].items(), key=lambda x: x[1]["profit"], reverse=True):
            roi = stats["profit"] / stats["staked"] * 100 if stats["staked"] > 0 else 0
            print(f"  {market}: {stats['bets']} bets, {stats['wins']}W/{stats['losses']}L, {stats['profit']:+.1f} ({roi:+.1f}%)")
        print()

    if result["by_book"]:
        print("By Sportsbook (where value found):")
        for book, stats in sorted(result["by_book"].items(), key=lambda x: x[1]["profit"], reverse=True):
            roi = stats["profit"] / stats["staked"] * 100 if stats["staked"] > 0 else 0
            print(f"  {book}: {stats['bets']} bets, {stats['wins']}W/{stats['losses']}L, {stats['profit']:+.1f} ({roi:+.1f}%)")


def market_efficiency_analysis(data):
    """Analyze how efficient the books are - do edges even exist?"""
    print("=" * 70)
    print("MARKET EFFICIENCY ANALYSIS")
    print("=" * 70)
    print(f"Fixtures: {len(data.get('fixtures', []))}")
    print()

    all_edges = []
    by_league = defaultdict(list)
    by_market = defaultdict(list)

    for fixture in data.get("fixtures", []):
        league = fixture.get("league", "")

        for market, odds_by_book in fixture.get("odds_by_market", {}).items():
            all_lines = set()
            for book, odds_list in odds_by_book.items():
                for odd in odds_list:
                    all_lines.add(odd['line'])

            for line in all_lines:
                fair_over, fair_under = calculate_fair_odds_for_line(odds_by_book, line, min_books=3)
                if fair_over is None:
                    continue

                for book, odds_list in odds_by_book.items():
                    for odd in odds_list:
                        if odd['line'] != line:
                            continue
                        fair = fair_over if odd['selection'] == 'Over' else fair_under
                        edge = ((odd['odds'] / fair) - 1) * 100
                        all_edges.append(edge)
                        by_league[league].append(edge)
                        by_market[market].append(edge)

    if not all_edges:
        print("No edges calculated - insufficient data")
        return

    all_edges.sort(reverse=True)

    print("EDGE DISTRIBUTION (all books, all lines):")
    print(f"  Total edge calculations: {len(all_edges)}")
    print(f"  Max edge: {max(all_edges):+.2f}%")
    print(f"  Min edge: {min(all_edges):+.2f}%")
    print(f"  Edges >= 5%: {len([e for e in all_edges if e >= 5])}")
    print(f"  Edges >= 3%: {len([e for e in all_edges if e >= 3])}")
    print(f"  Edges >= 1%: {len([e for e in all_edges if e >= 1])}")
    print(f"  Edges >= 0%: {len([e for e in all_edges if e >= 0])}")
    print()

    print("TOP 15 HIGHEST EDGES FOUND:")
    for i, edge in enumerate(all_edges[:15], 1):
        print(f"  {i:2}. {edge:+.2f}%")
    print()

    print("BY LEAGUE (max edge):")
    for league, edges in sorted(by_league.items(), key=lambda x: max(x[1]), reverse=True):
        max_e = max(edges)
        above_3 = len([e for e in edges if e >= 3])
        print(f"  {league}: max {max_e:+.2f}%, edges>=3%: {above_3}/{len(edges)}")
    print()

    print("BY MARKET (max edge):")
    for market, edges in sorted(by_market.items(), key=lambda x: max(x[1]), reverse=True):
        max_e = max(edges)
        above_3 = len([e for e in edges if e >= 3])
        print(f"  {market}: max {max_e:+.2f}%, edges>=3%: {above_3}/{len(edges)}")
    print()

    # Verdict
    max_edge = max(all_edges)
    if max_edge < 3:
        print("=" * 70)
        print("VERDICT: BOOKS ARE TOO EFFICIENT")
        print("=" * 70)
        print(f"Maximum edge found: {max_edge:+.2f}%")
        print("The European sportsbooks show very little price discrepancy.")
        print("This approach will NOT be profitable with these books/markets.")
        print()
        print("Recommendations:")
        print("  1. Try US sportsbooks (DraftKings, FanDuel, etc.)")
        print("  2. Try different markets (player props, 1st half, etc.)")
        print("  3. Use a different fair value calculation method")


if __name__ == "__main__":
    if not os.path.exists(RAW_DATA_FILE):
        print(f"Error: Raw data file not found: {RAW_DATA_FILE}")
        print("Run collect_raw_odds_data.py first!")
        sys.exit(1)

    print("Loading data...")
    data = load_data()
    print(f"Loaded {len(data.get('fixtures', []))} fixtures")
    print()

    if len(sys.argv) > 1 and sys.argv[1] == "--optimize":
        grid_search(data)
    elif len(sys.argv) > 1 and sys.argv[1] == "--efficiency":
        market_efficiency_analysis(data)
    else:
        quick_analysis(data)
        print()
        print("-" * 70)
        print("Run with --efficiency flag to analyze market efficiency")
        print("Run with --optimize flag for full grid search optimization")
