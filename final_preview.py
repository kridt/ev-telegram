#!/usr/bin/env python3
"""Final preview of Telegram messages with all translations."""

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

from src.api.oddsapi import OddsApiClient, OddsApiError

API_KEY = os.environ.get("ODDSAPI_API_KEY", "")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TRANSLATIONS_FILE = os.path.join(SCRIPT_DIR, "config", "market_translations.json")
with open(TRANSLATIONS_FILE, "r", encoding="utf-8") as f:
    TRANSLATIONS = json.load(f)


def get_translated_market(market_name: str, bookmaker: str) -> str:
    markets = TRANSLATIONS.get("markets", {})
    if market_name in markets:
        book_translations = markets[market_name]
        return book_translations.get(bookmaker, book_translations.get("default", market_name))
    return market_name


def format_telegram_message(bet, market_dk: str) -> str:
    """Format Telegram message with Danish translations."""
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
    }
    book_icon = book_icons.get(bet.bookmaker.lower(), "\u26aa")

    market_lower = bet.market_name.lower()
    bet_side = (bet.bet_side or "").lower()
    line = bet.line if bet.line else 0

    # Spread markets: use team names
    if "spread" in market_lower:
        pick_arrow = "\u27a1\ufe0f"
        if bet_side == "home":
            team = bet.home_team
            pick_text = f"{team} +{line}" if line >= 0 else f"{team} {line}"
        else:
            team = bet.away_team
            opp = -line
            pick_text = f"{team} +{opp}" if opp >= 0 else f"{team} {opp}"
    # Totals markets: Over/Under
    elif bet_side == "away":
        pick_arrow = "\u2b07\ufe0f"
        pick_text = f"Under {bet.line}"
    else:
        pick_arrow = "\u2b06\ufe0f"
        pick_text = f"Over {bet.line}"

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

    print("FINAL PREVIEW - Telegram messages with Danish translations\n")

    try:
        # Get bets from Bet365 and DanskeSpil
        all_bets = []
        for book in ["Bet365", "DanskeSpil"]:
            bets = await client.get_value_bets(bookmaker=book, sport="football", min_ev=0)
            for bet in bets:
                market_lower = bet.market_name.lower()
                if any(kw in market_lower for kw in ['corner', 'booking']):
                    if bet.is_fresh:
                        all_bets.append(bet)

        # Get event details
        event_ids = set()
        for bet in all_bets:
            if bet.event_id:
                try:
                    event_ids.add(int(bet.event_id))
                except:
                    pass

        if event_ids:
            event_cache = await client.get_events_by_ids(list(event_ids))
            for bet in all_bets:
                if bet.event_id:
                    try:
                        eid = int(bet.event_id)
                        if eid in event_cache:
                            bet.enrich_with_event(event_cache[eid])
                    except:
                        pass

        # Filter football and separate by type
        spreads = [b for b in all_bets if 'spread' in b.market_name.lower() and b.sport and b.sport.lower() in ('football', 'soccer')]
        totals = [b for b in all_bets if 'totals' in b.market_name.lower() and b.sport and b.sport.lower() in ('football', 'soccer')]

        print(f"{'=' * 60}")
        print("SPREAD BETS (Handicap with team names)")
        print(f"{'=' * 60}")

        for bet in spreads[:3]:
            market_dk = get_translated_market(bet.market_name, bet.bookmaker)
            msg = format_telegram_message(bet, market_dk)
            print(msg)
            print("-" * 40)

        print(f"\n{'=' * 60}")
        print("TOTALS BETS (Over/Under)")
        print(f"{'=' * 60}")

        for bet in totals[:3]:
            market_dk = get_translated_market(bet.market_name, bet.bookmaker)
            msg = format_telegram_message(bet, market_dk)
            print(msg)
            print("-" * 40)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
