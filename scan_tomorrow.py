#!/usr/bin/env python3
"""One-time scan for all matches tomorrow."""

import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except:
    pass

import httpx
from dotenv import load_dotenv

load_dotenv()

# Configuration
API_KEY = os.environ.get("OPTICODDS_API_KEY", "")
BASE_URL = "https://api.opticodds.com/api/v3"

# Bookmakers we actually bet on (Danish licensed)
BETTING_BOOKS = ["betsson", "leovegas", "unibet", "betano"]

# Additional bookmakers for calculating average (reference only)
REFERENCE_BOOKS = ["pinnacle", "888sport", "betway", "bwin", "william_hill", "coolbet"]

# All bookmakers combined
ALL_SPORTSBOOKS = BETTING_BOOKS + REFERENCE_BOOKS

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

MIN_EDGE = 5.0
MAX_EDGE = 25.0
MIN_ODDS = 1.50
MAX_ODDS = 3.0
MIN_BOOKS = 4

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def american_to_decimal(am: float) -> float:
    return 1 + (am / 100) if am >= 0 else 1 + (100 / abs(am))


async def get_fixtures(client: httpx.AsyncClient, league: str) -> list:
    r = await client.get(f"{BASE_URL}/fixtures/active", params={"sport": "soccer", "league": league})
    data = r.json()
    return [f for f in data.get("data", []) if not f.get("is_live", False)]


async def get_odds(client: httpx.AsyncClient, fixture_id: str) -> list:
    """Query each bookmaker separately (API doesn't support batching)."""
    all_odds = []
    for book in ALL_SPORTSBOOKS:
        try:
            r = await client.get(f"{BASE_URL}/fixtures/odds",
                params={"fixture_id": fixture_id, "sportsbook": book})
            data = r.json()
            if data.get("data") and len(data["data"]) > 0:
                all_odds.extend(data["data"][0].get("odds", []))
        except:
            pass
    return all_odds


def find_value(fixture: dict, odds_list: list, start_cet: datetime, end_cet: datetime) -> list:
    """Find value bets within time window."""
    kickoff_str = fixture.get("start_date", "")
    if kickoff_str:
        try:
            kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
            cet_offset = timedelta(hours=1)
            kickoff_cet = kickoff + cet_offset
            if not (start_cet <= kickoff_cet <= end_cet):
                return []
        except:
            pass

    value_bets = []
    grouped = defaultdict(dict)

    for odd in odds_list:
        if odd["market"] not in TARGET_MARKETS:
            continue
        key = f"{odd['market']}|{odd['name']}|{odd.get('points', '')}"
        grouped[key][odd["sportsbook"]] = odd

    for key, books in grouped.items():
        if len(books) < MIN_BOOKS:
            continue

        decimals = {}
        for book, odd in books.items():
            dec = american_to_decimal(odd["price"])
            if MIN_ODDS <= dec <= MAX_ODDS:
                decimals[book] = (dec, odd["price"])

        if len(decimals) < MIN_BOOKS:
            continue

        # Calculate AVERAGE odds across ALL bookmakers
        all_odds_values = [d[0] for d in decimals.values()]
        avg_odds = sum(all_odds_values) / len(all_odds_values)

        # Only create bets for BETTING_BOOKS (Danish licensed)
        # Case-insensitive comparison (API returns "Betano" not "betano")
        betting_books_lower = [b.lower() for b in BETTING_BOOKS]
        for book, (dec, american) in decimals.items():
            if book.lower() not in betting_books_lower:
                continue

            edge = (dec / avg_odds - 1) * 100
            if MIN_EDGE <= edge <= MAX_EDGE:
                parts = key.split("|")
                all_odds = {b: round(d[0], 2) for b, d in decimals.items()}

                # Get kickoff time
                kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
                kickoff_cet = kickoff + timedelta(hours=1)

                value_bets.append({
                    "fixture": f"{fixture['home_team_display']} vs {fixture['away_team_display']}",
                    "league": fixture["league"]["name"],
                    "kickoff": fixture["start_date"],
                    "kickoff_cet": kickoff_cet.strftime("%Y-%m-%d %H:%M"),
                    "market": parts[0],
                    "selection": parts[1],
                    "book": book,
                    "odds": round(dec, 2),
                    "fair": round(avg_odds, 3),
                    "edge": round(edge, 1),
                    "all_odds": all_odds,
                    "books_in_avg": len(decimals)
                })

    return value_bets


def filter_conflicting_sides(bets: list) -> list:
    """Filter out conflicting Over/Under bets on the same market."""
    market_groups = defaultdict(list)
    for bet in bets:
        group_key = f"{bet['fixture']}|{bet['market']}"
        market_groups[group_key].append(bet)

    filtered = []
    for group_key, group_bets in market_groups.items():
        best_bet = max(group_bets, key=lambda x: x["edge"])
        filtered.append(best_bet)
    return filtered


async def scan_tomorrow():
    """Scan for all matches tomorrow."""
    now_utc = datetime.now(timezone.utc)
    cet_offset = timedelta(hours=1)
    now_cet = now_utc + cet_offset

    # Tomorrow's window (00:00 to 23:59 CET)
    tomorrow = now_cet.date() + timedelta(days=1)
    start_cet = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, tzinfo=timezone.utc)
    end_cet = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 23, 59, tzinfo=timezone.utc)

    print("=" * 70)
    print("SCANNING ALL MATCHES TOMORROW")
    print(f"Date: {tomorrow.strftime('%A %Y-%m-%d')}")
    print(f"Window: {start_cet.strftime('%H:%M')} - {end_cet.strftime('%H:%M')} CET")
    print(f"Bookmakers for betting: {', '.join(BETTING_BOOKS)}")
    print(f"Reference bookmakers: {', '.join(REFERENCE_BOOKS)}")
    print("=" * 70)

    all_value_bets = []
    fixtures_found = []

    async with httpx.AsyncClient(
        headers={"x-api-key": API_KEY},
        timeout=60.0
    ) as client:
        for league in LEAGUES:
            try:
                fixtures = await get_fixtures(client, league)
                print(f"\n{league}: {len(fixtures)} fixtures")

                for fixture in fixtures:
                    # Check if fixture is tomorrow
                    kickoff_str = fixture.get("start_date", "")
                    if kickoff_str:
                        kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
                        kickoff_cet = kickoff + cet_offset
                        if start_cet <= kickoff_cet <= end_cet:
                            fixtures_found.append({
                                "match": f"{fixture['home_team_display']} vs {fixture['away_team_display']}",
                                "league": fixture["league"]["name"],
                                "kickoff": kickoff_cet.strftime("%H:%M")
                            })

                            try:
                                odds = await get_odds(client, fixture["id"])
                                if odds:
                                    value_bets = find_value(fixture, odds, start_cet, end_cet)
                                    all_value_bets.extend(value_bets)
                                    if value_bets:
                                        print(f"  + {fixture['home_team_display']} vs {fixture['away_team_display']}: {len(value_bets)} value bets")
                            except Exception as e:
                                print(f"  ! Error getting odds: {e}")

            except Exception as e:
                print(f"  ! Error: {e}")

    # Filter conflicting sides
    filtered_bets = filter_conflicting_sides(all_value_bets)

    # Sort by edge
    filtered_bets.sort(key=lambda x: x["edge"], reverse=True)

    print("\n" + "=" * 70)
    print(f"FIXTURES TOMORROW: {len(fixtures_found)}")
    print("=" * 70)
    for f in sorted(fixtures_found, key=lambda x: x["kickoff"]):
        print(f"  {f['kickoff']} | {f['match']} ({f['league']})")

    print("\n" + "=" * 70)
    print(f"VALUE BETS FOUND: {len(filtered_bets)}")
    print("=" * 70)

    if filtered_bets:
        for bet in filtered_bets:
            print(f"\n  {bet['edge']:.1f}% | {bet['book'].upper()}")
            print(f"  {bet['fixture']}")
            print(f"  {bet['market']}: {bet['selection']} @ {bet['odds']}")
            print(f"  Avg: {bet['fair']} from {bet['books_in_avg']} books | Kickoff: {bet['kickoff_cet']}")
    else:
        print("\n  No value bets found for tomorrow yet.")
        print("  (Odds may not be available until closer to match time)")

    # Save to file
    output = {
        "scan_time": now_cet.strftime("%Y-%m-%d %H:%M CET"),
        "scan_date": str(tomorrow),
        "fixtures_count": len(fixtures_found),
        "fixtures": fixtures_found,
        "value_bets_count": len(filtered_bets),
        "value_bets": filtered_bets
    }

    output_file = os.path.join(SCRIPT_DIR, "tomorrow_scan.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n\nResults saved to: {output_file}")

    return filtered_bets


if __name__ == "__main__":
    asyncio.run(scan_tomorrow())
