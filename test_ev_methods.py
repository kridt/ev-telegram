"""
EV Calculation Methods Tester
=============================
Tests many different EV calculation approaches to find the best strategy.

Methods tested:
1. Multiplicative devig (best odds)
2. Additive devig (best odds)
3. Power devig
4. Average odds devig
5. Median odds devig
6. Pinnacle as sharp line
7. Weighted average (Pinnacle weighted higher)
8. Worst-case devig
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from statistics import median, mean

DATA_FILE = os.path.join(os.path.dirname(__file__), "comprehensive_odds_data.json")

# Profitable leagues from our analysis
GOOD_LEAGUES = [
    "Jupiler Pro League",
    "Eredivisie",
    "La Liga",
    "Bundesliga",
    "Champions League",
    "Europa League",
    "Scottish Premiership",
]

# Good markets
GOOD_MARKETS = [
    "Team Total Shots On Target",
    "Team Total Shots",
    "Team Total Corners",
]

# Sharp books (their odds are more accurate)
SHARP_BOOKS = ["pinnacle", "betfair"]


def load_data():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_actual_value(results, market):
    """Get actual value from match results."""
    if not results:
        return None
    market_lower = market.lower()

    if 'team total' in market_lower:
        if 'corner' in market_lower:
            return results.get('home_corners', 0) + results.get('away_corners', 0)
        elif 'shot' in market_lower and 'target' in market_lower:
            return results.get('home_shots_on_target', 0) + results.get('away_shots_on_target', 0)
        elif 'shot' in market_lower:
            return results.get('home_shots', 0) + results.get('away_shots', 0)

    if 'corner' in market_lower:
        return results.get('total_corners')
    elif 'shot' in market_lower and 'target' in market_lower:
        return results.get('total_shots_on_target')
    elif 'shot' in market_lower:
        return results.get('total_shots')
    elif 'goal' in market_lower:
        return results.get('total_goals')
    return None


# ============================================================================
# EV CALCULATION METHODS
# ============================================================================

def method_multiplicative_best(odds_by_book, line, min_books=3):
    """Standard multiplicative devig using best odds."""
    over_odds = []
    under_odds = []

    for book, odds_list in odds_by_book.items():
        for odd in odds_list:
            if odd['line'] != line:
                continue
            if odd['selection'] == 'Over':
                over_odds.append(odd['decimal_odds'])
            else:
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

    return 1 / (imp_o / total), 1 / (imp_u / total)


def method_additive_best(odds_by_book, line, min_books=3):
    """Additive devig - removes vig equally from both sides."""
    over_odds = []
    under_odds = []

    for book, odds_list in odds_by_book.items():
        for odd in odds_list:
            if odd['line'] != line:
                continue
            if odd['selection'] == 'Over':
                over_odds.append(odd['decimal_odds'])
            else:
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
    vig = total - 1

    # Remove vig equally
    fair_imp_o = imp_o - (vig / 2)
    fair_imp_u = imp_u - (vig / 2)

    if fair_imp_o <= 0 or fair_imp_u <= 0:
        return None, None

    return 1 / fair_imp_o, 1 / fair_imp_u


def method_power_devig(odds_by_book, line, min_books=3):
    """Power method devig - better for favorites/longshots."""
    import math

    over_odds = []
    under_odds = []

    for book, odds_list in odds_by_book.items():
        for odd in odds_list:
            if odd['line'] != line:
                continue
            if odd['selection'] == 'Over':
                over_odds.append(odd['decimal_odds'])
            else:
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

    # Power method: find k such that imp_o^k + imp_u^k = 1
    if total <= 1.001:
        return None, None

    try:
        k = math.log(2) / math.log(total)
        fair_imp_o = imp_o ** k
        fair_imp_u = imp_u ** k

        if fair_imp_o <= 0 or fair_imp_u <= 0:
            return None, None

        return 1 / fair_imp_o, 1 / fair_imp_u
    except (ValueError, ZeroDivisionError):
        return None, None


def method_average_odds(odds_by_book, line, min_books=3):
    """Use average odds across books for devig."""
    over_odds = []
    under_odds = []

    for book, odds_list in odds_by_book.items():
        for odd in odds_list:
            if odd['line'] != line:
                continue
            if odd['selection'] == 'Over':
                over_odds.append(odd['decimal_odds'])
            else:
                under_odds.append(odd['decimal_odds'])

    if len(over_odds) < min_books or len(under_odds) < min_books:
        return None, None

    avg_over = mean(over_odds)
    avg_under = mean(under_odds)

    if avg_over <= 1 or avg_under <= 1:
        return None, None

    imp_o = 1 / avg_over
    imp_u = 1 / avg_under
    total = imp_o + imp_u

    return 1 / (imp_o / total), 1 / (imp_u / total)


def method_median_odds(odds_by_book, line, min_books=3):
    """Use median odds across books for devig."""
    over_odds = []
    under_odds = []

    for book, odds_list in odds_by_book.items():
        for odd in odds_list:
            if odd['line'] != line:
                continue
            if odd['selection'] == 'Over':
                over_odds.append(odd['decimal_odds'])
            else:
                under_odds.append(odd['decimal_odds'])

    if len(over_odds) < min_books or len(under_odds) < min_books:
        return None, None

    med_over = median(over_odds)
    med_under = median(under_odds)

    if med_over <= 1 or med_under <= 1:
        return None, None

    imp_o = 1 / med_over
    imp_u = 1 / med_under
    total = imp_o + imp_u

    return 1 / (imp_o / total), 1 / (imp_u / total)


def method_pinnacle_sharp(odds_by_book, line, min_books=3):
    """Use Pinnacle odds as the sharp/true line."""
    over_odds = []
    under_odds = []
    pinn_over = None
    pinn_under = None

    for book, odds_list in odds_by_book.items():
        for odd in odds_list:
            if odd['line'] != line:
                continue
            if odd['selection'] == 'Over':
                over_odds.append(odd['decimal_odds'])
                if book == 'pinnacle':
                    pinn_over = odd['decimal_odds']
            else:
                under_odds.append(odd['decimal_odds'])
                if book == 'pinnacle':
                    pinn_under = odd['decimal_odds']

    if len(over_odds) < min_books or len(under_odds) < min_books:
        return None, None

    # If no Pinnacle, use best odds
    if pinn_over is None or pinn_under is None:
        return method_multiplicative_best(odds_by_book, line, min_books)

    if pinn_over <= 1 or pinn_under <= 1:
        return None, None

    # Devig Pinnacle's odds (they have ~2% vig)
    imp_o = 1 / pinn_over
    imp_u = 1 / pinn_under
    total = imp_o + imp_u

    return 1 / (imp_o / total), 1 / (imp_u / total)


def method_weighted_sharp(odds_by_book, line, min_books=3):
    """Weight sharp books (Pinnacle, Betfair) higher in average."""
    over_odds = []
    under_odds = []
    over_weights = []
    under_weights = []

    for book, odds_list in odds_by_book.items():
        weight = 3 if book in SHARP_BOOKS else 1
        for odd in odds_list:
            if odd['line'] != line:
                continue
            if odd['selection'] == 'Over':
                over_odds.append(odd['decimal_odds'])
                over_weights.append(weight)
            else:
                under_odds.append(odd['decimal_odds'])
                under_weights.append(weight)

    if len(over_odds) < min_books or len(under_odds) < min_books:
        return None, None

    # Weighted average
    weighted_over = sum(o * w for o, w in zip(over_odds, over_weights)) / sum(over_weights)
    weighted_under = sum(o * w for o, w in zip(under_odds, under_weights)) / sum(under_weights)

    if weighted_over <= 1 or weighted_under <= 1:
        return None, None

    imp_o = 1 / weighted_over
    imp_u = 1 / weighted_under
    total = imp_o + imp_u

    return 1 / (imp_o / total), 1 / (imp_u / total)


def method_worst_case(odds_by_book, line, min_books=3):
    """Conservative: use worst odds for devig (higher fair value threshold)."""
    over_odds = []
    under_odds = []

    for book, odds_list in odds_by_book.items():
        for odd in odds_list:
            if odd['line'] != line:
                continue
            if odd['selection'] == 'Over':
                over_odds.append(odd['decimal_odds'])
            else:
                under_odds.append(odd['decimal_odds'])

    if len(over_odds) < min_books or len(under_odds) < min_books:
        return None, None

    # Use WORST (lowest) odds - more conservative
    worst_over = min(over_odds)
    worst_under = min(under_odds)

    if worst_over <= 1 or worst_under <= 1:
        return None, None

    imp_o = 1 / worst_over
    imp_u = 1 / worst_under
    total = imp_o + imp_u

    return 1 / (imp_o / total), 1 / (imp_u / total)


# All methods to test
EV_METHODS = {
    "multiplicative_best": method_multiplicative_best,
    "additive_best": method_additive_best,
    "power_devig": method_power_devig,
    "average_odds": method_average_odds,
    "median_odds": method_median_odds,
    "pinnacle_sharp": method_pinnacle_sharp,
    "weighted_sharp": method_weighted_sharp,
    "worst_case": method_worst_case,
}


def run_backtest(data, method_name, method_func, config):
    """Run backtest with a specific EV calculation method."""
    min_edge = config.get("min_edge", 5)
    max_edge = config.get("max_edge", 50)
    min_odds = config.get("min_odds", 1.5)
    max_odds = config.get("max_odds", 3.0)
    min_books = config.get("min_books", 3)
    leagues_filter = config.get("leagues", GOOD_LEAGUES)
    markets_filter = config.get("markets", GOOD_MARKETS)

    results = {
        "bets": 0, "wins": 0, "losses": 0, "profit": 0, "staked": 0,
        "by_book": defaultdict(lambda: {"bets": 0, "wins": 0, "losses": 0, "profit": 0, "staked": 0}),
        "by_date": defaultdict(lambda: defaultdict(int)),  # date -> book -> count
        "daily_bets": [],
    }

    for fixture in data.get("fixtures", []):
        league = fixture.get("league", {}).get("name", "")
        if leagues_filter and league not in leagues_filter:
            continue

        match_results = fixture.get("results", {})
        fixture_date = fixture.get("date", "")

        for market, odds_by_book in fixture.get("odds", {}).items():
            if markets_filter and market not in markets_filter:
                continue

            actual = get_actual_value(match_results, market)
            if actual is None:
                continue

            all_lines = set()
            for book, odds_list in odds_by_book.items():
                for odd in odds_list:
                    all_lines.add(odd['line'])

            for line in all_lines:
                fair_over, fair_under = method_func(odds_by_book, line, min_books)
                if fair_over is None:
                    continue

                for book, odds_list in odds_by_book.items():
                    for odd in odds_list:
                        if odd['line'] != line:
                            continue

                        decimal_odds = odd['decimal_odds']
                        fair = fair_over if odd['selection'] == 'Over' else fair_under
                        edge = ((decimal_odds / fair) - 1) * 100

                        if edge < min_edge or edge > max_edge:
                            continue
                        if decimal_odds < min_odds or decimal_odds > max_odds:
                            continue

                        stake = 10
                        if actual == line:
                            profit = 0
                        elif odd['selection'] == 'Over':
                            profit = stake * (decimal_odds - 1) if actual > line else -stake
                        else:
                            profit = stake * (decimal_odds - 1) if actual < line else -stake

                        results["bets"] += 1
                        results["staked"] += stake
                        results["profit"] += profit

                        if profit > 0:
                            results["wins"] += 1
                        elif profit < 0:
                            results["losses"] += 1

                        results["by_book"][book]["bets"] += 1
                        results["by_book"][book]["staked"] += stake
                        results["by_book"][book]["profit"] += profit
                        if profit > 0:
                            results["by_book"][book]["wins"] += 1
                        elif profit < 0:
                            results["by_book"][book]["losses"] += 1

                        results["by_date"][fixture_date][book] += 1

    # Calculate daily average bets per book
    if results["by_date"]:
        num_days = len(results["by_date"])
        for book in results["by_book"]:
            avg_daily = results["by_book"][book]["bets"] / num_days
            results["by_book"][book]["avg_daily"] = round(avg_daily, 2)

    return results


def main():
    print("Loading data...")
    data = load_data()
    print(f"Loaded {len(data.get('fixtures', []))} fixtures")
    print()

    print("=" * 80)
    print("TESTING EV CALCULATION METHODS")
    print("=" * 80)
    print(f"Leagues: {', '.join(GOOD_LEAGUES[:4])}...")
    print(f"Markets: {', '.join(GOOD_MARKETS)}")
    print()

    # Test configurations
    configs = [
        {"name": "Standard (5%+ edge)", "min_edge": 5, "max_edge": 50, "min_books": 3},
        {"name": "Moderate (7%+ edge)", "min_edge": 7, "max_edge": 50, "min_books": 3},
        {"name": "Conservative (10%+ edge)", "min_edge": 10, "max_edge": 50, "min_books": 3},
        {"name": "Aggressive (3%+ edge)", "min_edge": 3, "max_edge": 50, "min_books": 3},
        {"name": "High volume (3%+, 2 books)", "min_edge": 3, "max_edge": 50, "min_books": 2},
    ]

    all_results = []

    for config in configs:
        print(f"\n{'='*80}")
        print(f"CONFIG: {config['name']}")
        print(f"{'='*80}")

        for method_name, method_func in EV_METHODS.items():
            result = run_backtest(data, method_name, method_func, config)

            if result["bets"] == 0:
                continue

            roi = result["profit"] / result["staked"] * 100 if result["staked"] > 0 else 0
            wr = result["wins"] / (result["wins"] + result["losses"]) * 100 if (result["wins"] + result["losses"]) > 0 else 0

            # Count books with avg >= 5 bets/day
            books_5_daily = sum(1 for b, s in result["by_book"].items() if s.get("avg_daily", 0) >= 5)
            books_3_daily = sum(1 for b, s in result["by_book"].items() if s.get("avg_daily", 0) >= 3)
            total_avg_daily = sum(s.get("avg_daily", 0) for s in result["by_book"].values())

            all_results.append({
                "config": config["name"],
                "method": method_name,
                "bets": result["bets"],
                "roi": roi,
                "profit": result["profit"],
                "win_rate": wr,
                "books_5_daily": books_5_daily,
                "books_3_daily": books_3_daily,
                "total_daily": total_avg_daily,
                "by_book": dict(result["by_book"]),
            })

            print(f"\n{method_name}:")
            print(f"  Bets: {result['bets']} | ROI: {roi:+.1f}% | WR: {wr:.1f}% | Profit: {result['profit']:+.1f}")
            print(f"  Books with 5+/day: {books_5_daily} | 3+/day: {books_3_daily} | Total daily: {total_avg_daily:.1f}")

    # Find best methods
    print("\n" + "=" * 80)
    print("TOP 10 COMBINATIONS (by ROI with volume)")
    print("=" * 80)

    # Filter for methods with decent volume
    viable = [r for r in all_results if r["bets"] >= 100 and r["books_3_daily"] >= 3]
    viable.sort(key=lambda x: x["roi"], reverse=True)

    for i, r in enumerate(viable[:10], 1):
        print(f"\n{i}. {r['config']} + {r['method']}")
        print(f"   ROI: {r['roi']:+.1f}% | Profit: {r['profit']:+.1f} | Bets: {r['bets']} | WR: {r['win_rate']:.1f}%")
        print(f"   Books with 5+/day: {r['books_5_daily']} | 3+/day: {r['books_3_daily']}")

        # Show top books
        top_books = sorted(r["by_book"].items(), key=lambda x: x[1].get("avg_daily", 0), reverse=True)[:5]
        print(f"   Top books: ", end="")
        for book, stats in top_books:
            book_roi = stats["profit"] / stats["staked"] * 100 if stats["staked"] > 0 else 0
            print(f"{book}({stats.get('avg_daily', 0):.1f}/day, {book_roi:+.0f}%) ", end="")
        print()

    # Find best for volume (5+ bets daily per book)
    print("\n" + "=" * 80)
    print("BEST FOR VOLUME (targeting 5+ bets/day per book)")
    print("=" * 80)

    volume_focused = [r for r in all_results if r["books_5_daily"] >= 2]
    volume_focused.sort(key=lambda x: (x["books_5_daily"], x["roi"]), reverse=True)

    for i, r in enumerate(volume_focused[:5], 1):
        print(f"\n{i}. {r['config']} + {r['method']}")
        print(f"   ROI: {r['roi']:+.1f}% | Books with 5+/day: {r['books_5_daily']}")

        # Show books with 5+/day
        high_vol_books = [(b, s) for b, s in r["by_book"].items() if s.get("avg_daily", 0) >= 5]
        for book, stats in sorted(high_vol_books, key=lambda x: x[1].get("avg_daily", 0), reverse=True):
            book_roi = stats["profit"] / stats["staked"] * 100 if stats["staked"] > 0 else 0
            print(f"   - {book}: {stats.get('avg_daily', 0):.1f} bets/day, {stats['bets']} total, ROI: {book_roi:+.1f}%")

    # Save detailed results
    output_file = os.path.join(os.path.dirname(__file__), "ev_methods_results.json")
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
