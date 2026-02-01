#!/usr/bin/env python3
"""Preview prop spread bets (corners spread, bookings spread)."""

import asyncio
import json
import os
import sys
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.api.oddsapi import OddsApiClient, OddsApiValueBet, OddsApiError

API_KEY = os.environ.get("ODDSAPI_API_KEY", "")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TRANSLATIONS_FILE = os.path.join(SCRIPT_DIR, "config", "market_translations.json")
with open(TRANSLATIONS_FILE, "r", encoding="utf-8") as f:
    TRANSLATIONS = json.load(f)

DANISH_BOOKMAKERS = ["Bet365", "DanskeSpil"]

PROP_SPREAD_KEYWORDS = ['corners spread', 'bookings spread', 'cards spread', 'shots spread']


def get_translated_market(market_name: str, bookmaker: str) -> str:
    markets = TRANSLATIONS.get("markets", {})
    if market_name in markets:
        book_translations = markets[market_name]
        return book_translations.get(bookmaker, book_translations.get("default", market_name))
    return market_name


async def main():
    client = OddsApiClient(api_key=API_KEY)

    print("Looking for PROP spread bets (corners spread, bookings spread)...\n")

    prop_spread_bets = []
    event_ids = set()

    try:
        for bookmaker in DANISH_BOOKMAKERS:
            try:
                bets = await client.get_value_bets(bookmaker=bookmaker, sport="football", min_ev=0)

                for bet in bets:
                    market_lower = bet.market_name.lower()

                    # Look for prop spread markets specifically
                    if any(kw in market_lower for kw in PROP_SPREAD_KEYWORDS):
                        prop_spread_bets.append(bet)
                        if bet.event_id:
                            try:
                                event_ids.add(int(bet.event_id))
                            except:
                                pass

                print(f"  {bookmaker}: {len([b for b in prop_spread_bets if b.bookmaker == bookmaker])} prop spread bets")

            except OddsApiError as e:
                print(f"  {bookmaker}: Error - {e}")

        print(f"\nTotal: {len(prop_spread_bets)} prop spread bets")

        # Fetch event details
        if event_ids:
            event_cache = await client.get_events_by_ids(list(event_ids))

            football_bets = []
            for bet in prop_spread_bets:
                if bet.event_id:
                    try:
                        event_id = int(bet.event_id)
                        if event_id in event_cache:
                            bet.enrich_with_event(event_cache[event_id])
                            if bet.sport and bet.sport.lower() in ("football", "soccer"):
                                football_bets.append(bet)
                    except:
                        pass

            prop_spread_bets = football_bets

        print(f"After filtering for football: {len(prop_spread_bets)} bets")

        # Show with formatting
        print(f"\n{'=' * 60}")
        print("PROP SPREAD BETS (Corners/Bookings Handicap)")
        print(f"{'=' * 60}")

        for i, bet in enumerate(prop_spread_bets[:10], 1):
            print(f"\n--- Bet {i} ---")
            print(f"Match: {bet.fixture_name}")
            print(f"League: {bet.league}")
            print(f"Market (EN): {bet.market_name}")
            print(f"Market (DK): {get_translated_market(bet.market_name, bet.bookmaker)}")
            print(f"Bookmaker: {bet.bookmaker}")
            print(f"betSide: '{bet.bet_side}'")
            print(f"line (hdp): {bet.line}")
            print(f"Odds: {bet.bookmaker_odds:.2f}")
            print(f"Fair: {bet.sharp_odds:.2f}")
            print(f"EV: {bet.ev_percent:.1f}%")

            # Format the pick properly for spread markets
            bet_side = (bet.bet_side or "").lower()
            line = bet.line if bet.line else 0

            if bet_side == "home":
                # Home team gets the handicap shown
                if line >= 0:
                    pick = f"Hjemmehold +{line}"
                else:
                    pick = f"Hjemmehold {line}"
            elif bet_side == "away":
                # Away team - opposite sign of the line shown
                opposite = -line if line else 0
                if opposite >= 0:
                    pick = f"Udehold +{opposite}"
                else:
                    pick = f"Udehold {opposite}"
            else:
                pick = bet.selection_display

            print(f"\n>>> Formatted pick: {pick}")

            # Show full Telegram preview
            kickoff = bet.start_time.strftime("%H:%M") if bet.start_time else "TBD"
            market_dk = get_translated_market(bet.market_name, bet.bookmaker)

            book_icons = {
                "bet365": "🔷",
                "danskespil": "🟢",
            }
            icon = book_icons.get(bet.bookmaker.lower(), "⚪")

            print(f"""
{icon} <b>{bet.bookmaker.upper()}</b>
⚽ {bet.fixture_name}
🏆 {bet.league} | {kickoff}
Marked: <b>{market_dk}</b>
Spil: ➡️ <b>{pick}</b>
Odds: <b>{bet.bookmaker_odds:.2f}</b>
Fair: <b>{bet.sharp_odds:.2f}</b>
EV: <b>{bet.ev_percent:.1f}%</b>
""")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
