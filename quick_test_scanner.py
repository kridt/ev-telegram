#!/usr/bin/env python3
"""Quick test of the scanner with Telegram preview."""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.api.oddsapi import OddsApiClient, OddsApiValueBet, OddsApiError

API_KEY = os.environ.get("ODDSAPI_API_KEY", "")

# Same filters as scanner
MIN_EV = 5.0
MAX_EV = 25.0
MIN_ODDS = 1.50
MAX_ODDS = 3.00
MAX_AGE = 600

PROP_KEYWORDS = ['corner', 'booking', 'card', 'shot', 'foul', 'throw', 'offside']


def format_telegram_alert(bet: OddsApiValueBet) -> str:
    """Format a value bet for Telegram in Danish."""
    kickoff_display = "TBD"
    if bet.start_time:
        kickoff_cet = bet.start_time + timedelta(hours=1)
        kickoff_display = kickoff_cet.strftime("%H:%M")

    ev = bet.ev_percent
    filled = min(10, int(ev / 2))
    bar = "\u25b0" * filled + "\u2591" * (10 - filled)

    selection_lower = bet.selection.lower() if bet.selection else ""
    bet_side_lower = bet.bet_side.lower() if bet.bet_side else ""

    if "under" in selection_lower or bet_side_lower == "away":
        pick_arrow = "\u2b07\ufe0f"
        pick_text = f"Under {bet.line}" if bet.line else "Under"
    elif "over" in selection_lower or bet_side_lower == "home":
        pick_arrow = "\u2b06\ufe0f"
        pick_text = f"Over {bet.line}" if bet.line else "Over"
    else:
        pick_arrow = "\u27a1\ufe0f"
        pick_text = bet.selection_display

    return f"""\u26a0\ufe0f <b>EV bet fundet</b> \u26a0\ufe0f
{bar} <b>{ev:.1f}%</b>

\U0001f537 <b>{bet.bookmaker.upper()}</b>

\u26bd {bet.fixture_name}
\U0001f3c6 {bet.league} | {kickoff_display}

Marked: <b>{bet.market_name}</b>
Spil: {pick_arrow} <b>{pick_text}</b>
Odds: <b>{bet.bookmaker_odds:.2f}</b>
Fair: <b>{bet.sharp_odds:.2f}</b>"""


async def main():
    client = OddsApiClient(api_key=API_KEY)

    print("Testing scanner with Telegram preview...\n")

    try:
        # Test with Bet365
        bets = await client.get_value_bets(bookmaker="Bet365", sport="football", min_ev=0)
        print(f"Got {len(bets)} total bets from Bet365")

        # Filter for prop markets
        prop_bets = []
        event_ids = set()

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

            prop_bets.append(bet)
            if bet.event_id:
                try:
                    event_ids.add(int(bet.event_id))
                except (ValueError, TypeError):
                    pass

        print(f"Found {len(prop_bets)} qualifying prop bets")

        # Fetch event details
        if event_ids:
            event_cache = await client.get_events_by_ids(list(event_ids))
            print(f"Fetched {len(event_cache)} event details")

            # Enrich and display Telegram previews
            print("\n" + "=" * 60)
            print("TELEGRAM MESSAGE PREVIEWS")
            print("=" * 60)

            shown = 0
            for bet in prop_bets:
                if bet.event_id:
                    try:
                        event_id = int(bet.event_id)
                        if event_id in event_cache:
                            event_data = event_cache[event_id]
                            bet.enrich_with_event(event_data)

                            # Skip non-football
                            if bet.sport and bet.sport.lower() not in ("football", "soccer"):
                                continue

                            msg = format_telegram_alert(bet)
                            print(f"\n{msg}")
                            print("-" * 40)
                            shown += 1

                            if shown >= 3:
                                break
                    except (ValueError, TypeError):
                        pass

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
