#!/usr/bin/env python3
"""Quick scan for value bets across multiple fixtures."""

import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

# Fix Windows encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("OPTICODDS_API_KEY", "")
BASE_URL = "https://api.opticodds.com/api/v3"

SPORTSBOOKS = ["betsson", "leovegas", "unibet"]
LEAGUES = [
    "england_-_premier_league",
    "spain_-_la_liga",
    "germany_-_bundesliga",
    "italy_-_serie_a",
    "france_-_ligue_1",
    "netherlands_-_eredivisie",
    "portugal_-_primeira_liga",
    "uefa_-_champions_league",
    "uefa_-_europa_league",
    "usa_-_mls",
]
TARGET_MARKETS = [
    "Total Shots", "Total Shots On Target", "Total Corners",
    "Asian Handicap", "Asian Handicap Corners"
]

# Filter thresholds
MIN_EDGE = 5.0      # Minimum edge to flag as value
MAX_EDGE = 25.0     # Maximum edge (higher often indicates pricing errors)
MIN_ODDS = 1.50     # Minimum decimal odds (exclude heavy favorites)
MAX_ODDS = 3.0      # Maximum decimal odds (exclude extreme longshots)
MIN_BOOKS = 3       # Minimum books pricing the market (more = more confidence)


def american_to_decimal(am: float) -> float:
    """Convert American odds to decimal."""
    return 1 + (am / 100) if am >= 0 else 1 + (100 / abs(am))


async def get_fixtures(client: httpx.AsyncClient, league: str) -> list:
    """Get upcoming fixtures for a league."""
    r = await client.get(f"{BASE_URL}/fixtures/active", params={"sport": "soccer", "league": league})
    data = r.json()
    # Filter to non-live upcoming fixtures
    return [f for f in data.get("data", []) if not f.get("is_live", False)]


async def get_odds(client: httpx.AsyncClient, fixture_id: str) -> list:
    """Get odds for a fixture from target sportsbooks."""
    # Build params with multiple sportsbook entries (API requires this format)
    params = [("fixture_id", fixture_id)]
    for book in SPORTSBOOKS:
        params.append(("sportsbook", book))

    r = await client.get(f"{BASE_URL}/fixtures/odds", params=params)
    data = r.json()
    if data.get("data"):
        return data["data"][0].get("odds", [])
    return []


def find_value(fixture: dict, odds_list: list) -> list:
    """Find value bets in odds using market average approach."""
    value_bets = []

    # Group by market+selection
    grouped = defaultdict(dict)
    for odd in odds_list:
        if odd["market"] not in TARGET_MARKETS:
            continue
        key = f"{odd['market']}|{odd['name']}|{odd.get('points', '')}"
        grouped[key][odd["sportsbook"]] = odd

    # Find value
    for key, books in grouped.items():
        if len(books) < MIN_BOOKS:
            continue

        # Convert to decimal
        decimals = {}
        for book, odd in books.items():
            dec = american_to_decimal(odd["price"])
            if MIN_ODDS <= dec <= MAX_ODDS:
                decimals[book] = (dec, odd["price"])

        if len(decimals) < MIN_BOOKS:
            continue

        avg = sum(d[0] for d in decimals.values()) / len(decimals)

        for book, (dec, american) in decimals.items():
            edge = (dec / avg - 1) * 100
            if MIN_EDGE <= edge <= MAX_EDGE:
                parts = key.split("|")
                # Build all odds display
                all_odds = {b: round(d[0], 2) for b, d in decimals.items()}
                value_bets.append({
                    "fixture": f"{fixture['home_team_display']} vs {fixture['away_team_display']}",
                    "league": fixture["league"]["name"],
                    "kickoff": fixture["start_date"],
                    "market": parts[0],
                    "selection": parts[1],
                    "book": book,
                    "odds": dec,
                    "american": american,
                    "fair": avg,
                    "edge": edge,
                    "num_books": len(decimals),
                    "all_odds": all_odds
                })

    return value_bets


async def main():
    print("=" * 60)
    print("SOCCER PLAYER PROPS VALUE SCANNER")
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    all_value_bets = []

    async with httpx.AsyncClient(
        headers={"x-api-key": API_KEY},
        timeout=60.0
    ) as client:

        for league in LEAGUES:
            print(f"\n[*] Scanning {league}...")

            try:
                fixtures = await get_fixtures(client, league)
                print(f"   Found {len(fixtures)} upcoming fixtures")

                for fixture in fixtures[:5]:  # Limit to 5 per league for speed
                    fixture_name = f"{fixture['home_team_display']} vs {fixture['away_team_display']}"

                    try:
                        odds = await get_odds(client, fixture["id"])
                        if not odds:
                            continue

                        value_bets = find_value(fixture, odds)
                        if value_bets:
                            print(f"   [+] {fixture_name}: {len(value_bets)} value bets")
                            all_value_bets.extend(value_bets)

                    except Exception as e:
                        print(f"   [!] Error for {fixture_name}: {e}")

            except Exception as e:
                print(f"   [!] Error scanning {league}: {e}")

    # Sort by edge
    all_value_bets.sort(key=lambda x: x["edge"], reverse=True)

    # Print results
    print("\n" + "=" * 60)
    print(f"RESULTS: {len(all_value_bets)} VALUE BETS FOUND")
    print("=" * 60)

    # Group by market
    by_market = defaultdict(list)
    for bet in all_value_bets:
        by_market[bet["market"]].append(bet)

    for market in TARGET_MARKETS:
        if market not in by_market:
            continue

        bets = by_market[market]
        print(f"\n[MARKET] {market} ({len(bets)} bets)")
        print("-" * 50)

        for bet in bets[:5]:  # Top 5 per market
            print(f"  {bet['edge']:.1f}% | {bet['selection']}")
            print(f"         {bet['fixture']}")
            print(f"         BEST: {bet['book']} @ {bet['odds']:.2f} (fair: {bet['fair']:.2f})")
            odds_str = " | ".join([f"{b}: {o}" for b, o in sorted(bet['all_odds'].items())])
            print(f"         All: {odds_str}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY BY SPORTSBOOK")
    print("-" * 30)
    by_book = defaultdict(int)
    for bet in all_value_bets:
        by_book[bet["book"]] += 1
    for book, count in sorted(by_book.items(), key=lambda x: -x[1]):
        print(f"  {book}: {count} value bets")

    # Save to file
    with open("value_bets.json", "w") as f:
        json.dump(all_value_bets, f, indent=2, default=str)
    print(f"\n[SAVED] Full results saved to value_bets.json")


if __name__ == "__main__":
    asyncio.run(main())
