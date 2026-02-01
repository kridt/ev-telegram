#!/usr/bin/env python3
"""Preview value bets with Danish translations before sending."""

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

# Load translations
TRANSLATIONS_FILE = os.path.join(SCRIPT_DIR, "config", "market_translations.json")
with open(TRANSLATIONS_FILE, "r", encoding="utf-8") as f:
    TRANSLATIONS = json.load(f)

# Filters
MIN_EV = 5.0
MAX_EV = 25.0
MIN_ODDS = 1.50
MAX_ODDS = 3.00

PROP_KEYWORDS = ['corner', 'booking', 'card', 'shot', 'foul', 'throw', 'offside']

DANISH_BOOKMAKERS = [
    "Bet365",
    "DanskeSpil",
    "Unibet DK",
    "Coolbet",
    "Betano DK",
    "NordicBet DK",
    "Betsson",
    "LeoVegas",
    "Betinia DK",
    "Campobet DK",
]


def get_translated_market(market_name: str, bookmaker: str) -> str:
    """Get Danish translation for market name."""
    markets = TRANSLATIONS.get("markets", {})
    if market_name in markets:
        book_translations = markets[market_name]
        # Try bookmaker-specific first, then default
        return book_translations.get(bookmaker, book_translations.get("default", market_name))
    return market_name


def get_translated_selection(selection: str, bookmaker: str) -> str:
    """Get Danish translation for selection."""
    selections = TRANSLATIONS.get("selections", {})
    if selection in selections:
        book_translations = selections[selection]
        return book_translations.get(bookmaker, book_translations.get("default", selection))
    return selection


def format_telegram_alert(bet: OddsApiValueBet) -> str:
    """Format a value bet for Telegram in Danish with translations."""
    kickoff_display = "TBD"
    if bet.start_time:
        kickoff_cet = bet.start_time + timedelta(hours=1)
        kickoff_display = kickoff_cet.strftime("%H:%M")

    ev = bet.ev_percent
    filled = min(10, int(ev / 2))
    bar = "\u25b0" * filled + "\u2591" * (10 - filled)

    book_icons = {
        "bet365": "\U0001f537",
        "danskespil": "\U0001f7e2",
        "unibet dk": "\U0001f7e2",
        "coolbet": "\U0001f535",
        "betano dk": "\U0001f7e0",
        "leovegas": "\U0001f7e1",
        "betsson": "\U0001f537",
        "nordicbet dk": "\U0001f535",
        "betinia dk": "\U0001f7e3",
        "campobet dk": "\U0001f7e0",
    }
    book_key = bet.bookmaker.lower()
    book_icon = book_icons.get(book_key, "\u26aa")

    # Get Danish translation for market
    market_dk = get_translated_market(bet.market_name, bet.bookmaker)

    # Determine pick text based on betSide
    bet_side_lower = (bet.bet_side or "").lower()
    selection_lower = (bet.selection or "").lower()

    if bet_side_lower == "away" or "under" in selection_lower:
        pick_arrow = "\u2b07\ufe0f"
        pick_text = f"Under {bet.line}" if bet.line else "Under"
    elif bet_side_lower == "home" or "over" in selection_lower:
        pick_arrow = "\u2b06\ufe0f"
        pick_text = f"Over {bet.line}" if bet.line else "Over"
    else:
        pick_arrow = "\u27a1\ufe0f"
        pick_text = bet.selection_display

    return f"""\u26a0\ufe0f <b>EV bet fundet</b> \u26a0\ufe0f
{bar} <b>{ev:.1f}%</b>

{book_icon} <b>{bet.bookmaker.upper()}</b>

\u26bd {bet.fixture_name}
\U0001f3c6 {bet.league} | {kickoff_display}

Marked: <b>{market_dk}</b>
Spil: {pick_arrow} <b>{pick_text}</b>
Odds: <b>{bet.bookmaker_odds:.2f}</b>
Fair: <b>{bet.sharp_odds:.2f}</b>"""


async def main():
    client = OddsApiClient(api_key=API_KEY)

    print("Fetching value bets from all Danish bookmakers...\n")

    all_bets = []
    event_ids = set()

    try:
        for bookmaker in DANISH_BOOKMAKERS:
            try:
                bets = await client.get_value_bets(bookmaker=bookmaker, sport="football", min_ev=0)

                for bet in bets:
                    market_lower = bet.market_name.lower()
                    if not any(kw in market_lower for kw in PROP_KEYWORDS):
                        continue
                    if not (MIN_EV <= bet.ev_percent <= MAX_EV):
                        continue
                    if not (MIN_ODDS <= bet.bookmaker_odds <= MAX_ODDS):
                        continue
                    if not bet.is_fresh:
                        continue

                    all_bets.append(bet)
                    if bet.event_id:
                        try:
                            event_ids.add(int(bet.event_id))
                        except (ValueError, TypeError):
                            pass

                print(f"  {bookmaker}: {len([b for b in all_bets if b.bookmaker == bookmaker])} prop bets")

            except OddsApiError as e:
                print(f"  {bookmaker}: Error - {e}")

        # Fetch event details
        if event_ids:
            print(f"\nFetching event details for {len(event_ids)} events...")
            event_cache = await client.get_events_by_ids(list(event_ids))

            # Enrich bets
            football_bets = []
            for bet in all_bets:
                if bet.event_id:
                    try:
                        event_id = int(bet.event_id)
                        if event_id in event_cache:
                            bet.enrich_with_event(event_cache[event_id])
                            if bet.sport and bet.sport.lower() in ("football", "soccer"):
                                football_bets.append(bet)
                    except (ValueError, TypeError):
                        pass

            all_bets = football_bets

        # Sort by EV
        all_bets.sort(key=lambda x: x.ev_percent, reverse=True)

        print(f"\n{'=' * 60}")
        print(f"FOUND {len(all_bets)} PROP VALUE BETS")
        print(f"{'=' * 60}")

        for i, bet in enumerate(all_bets, 1):
            print(f"\n--- Bet {i}/{len(all_bets)} ---")
            print(f"Original market: {bet.market_name}")
            print(f"Translated for {bet.bookmaker}: {get_translated_market(bet.market_name, bet.bookmaker)}")
            print()
            msg = format_telegram_alert(bet)
            print(msg)
            print()

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
