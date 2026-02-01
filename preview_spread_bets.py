#!/usr/bin/env python3
"""Preview spread/handicap bets (not over/under)."""

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


def get_translated_market(market_name: str, bookmaker: str) -> str:
    markets = TRANSLATIONS.get("markets", {})
    if market_name in markets:
        book_translations = markets[market_name]
        return book_translations.get(bookmaker, book_translations.get("default", market_name))
    return market_name


async def main():
    client = OddsApiClient(api_key=API_KEY)

    print("Looking for spread/handicap bets (not Over/Under)...\n")

    spread_bets = []
    event_ids = set()

    try:
        for bookmaker in DANISH_BOOKMAKERS:
            try:
                bets = await client.get_value_bets(bookmaker=bookmaker, sport="football", min_ev=0)

                for bet in bets:
                    market_lower = bet.market_name.lower()

                    # Look for spread/handicap markets
                    if "spread" in market_lower or "handicap" in market_lower:
                        spread_bets.append(bet)
                        if bet.event_id:
                            try:
                                event_ids.add(int(bet.event_id))
                            except:
                                pass

            except OddsApiError as e:
                print(f"  {bookmaker}: Error - {e}")

        print(f"Found {len(spread_bets)} spread/handicap bets total")

        # Fetch event details
        if event_ids:
            event_cache = await client.get_events_by_ids(list(event_ids))

            for bet in spread_bets:
                if bet.event_id:
                    try:
                        event_id = int(bet.event_id)
                        if event_id in event_cache:
                            bet.enrich_with_event(event_cache[event_id])
                    except:
                        pass

        # Show first 5 with raw data
        print(f"\n{'=' * 60}")
        print("RAW DATA FOR SPREAD BETS")
        print(f"{'=' * 60}")

        for i, bet in enumerate(spread_bets[:5], 1):
            print(f"\n--- Bet {i} ---")
            print(f"Match: {bet.fixture_name}")
            print(f"Market: {bet.market_name}")
            print(f"Market (DK): {get_translated_market(bet.market_name, bet.bookmaker)}")
            print(f"Bookmaker: {bet.bookmaker}")
            print(f"betSide: '{bet.bet_side}'")
            print(f"selection: '{bet.selection}'")
            print(f"line (hdp): {bet.line}")
            print(f"Odds: {bet.bookmaker_odds:.2f}")
            print(f"EV: {bet.ev_percent:.1f}%")

            # Show how it would be formatted
            bet_side = (bet.bet_side or "").lower()
            if bet_side == "home":
                pick = f"Hjemmehold {bet.line:+.1f}" if bet.line else "Hjemmehold"
            elif bet_side == "away":
                pick = f"Udehold {bet.line:+.1f}" if bet.line else "Udehold"
            else:
                pick = bet.selection_display

            print(f"\nFormatted pick: {pick}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
