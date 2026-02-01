#!/usr/bin/env python3
"""Send test bets to Telegram - find best EV bets."""

import asyncio
import json
import os
import sys
from datetime import timedelta
from dotenv import load_dotenv
import httpx

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.api.oddsapi import OddsApiClient

API_KEY = os.environ.get("ODDSAPI_API_KEY", "")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

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


def format_telegram_alert(bet, market_dk: str) -> str:
    """Format a value bet for Telegram in Danish."""
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
    }
    book_icon = book_icons.get(bet.bookmaker.lower(), "\u26aa")

    market_lower = bet.market_name.lower()
    bet_side = (bet.bet_side or "").lower()
    line = bet.line if bet.line else 0

    # Spread markets: use team names
    if "spread" in market_lower:
        pick_arrow = "\u27a1\ufe0f"
        if bet_side == "home":
            team = bet.home_team or "Hjemmehold"
            if line >= 0:
                pick_text = f"{team} +{line}"
            else:
                pick_text = f"{team} {line}"
        else:
            team = bet.away_team or "Udehold"
            opp = -line if line else 0
            if opp >= 0:
                pick_text = f"{team} +{opp}"
            else:
                pick_text = f"{team} {opp}"
    # Totals: Over/Under
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


def send_telegram(message: str) -> bool:
    """Send message to Telegram."""
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        result = response.json()
        if result.get("ok"):
            print("✓ Sent to Telegram")
            return True
        else:
            print(f"✗ Telegram error: {result}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


async def main():
    client = OddsApiClient(api_key=API_KEY)

    try:
        print("Fetching fresh bets from both bookmakers...\n")

        all_bets = []

        # Get Bet365 bets
        bet365_bets = await client.get_value_bets(bookmaker="Bet365", sport="football", min_ev=0)
        for bet in bet365_bets:
            if not bet.is_fresh:
                continue
            market_lower = bet.market_name.lower()
            if 'booking' not in market_lower and 'corner' not in market_lower:
                continue
            if 'totals' in market_lower and bet.line and bet.line == int(bet.line):
                continue
            all_bets.append(bet)

        # Get DanskeSpil bets
        ds_bets = await client.get_value_bets(bookmaker="DanskeSpil", sport="football", min_ev=0)
        for bet in ds_bets:
            if not bet.is_fresh:
                continue
            market_lower = bet.market_name.lower()
            if 'booking' not in market_lower and 'corner' not in market_lower:
                continue
            if 'totals' in market_lower and bet.line and bet.line == int(bet.line):
                continue
            all_bets.append(bet)

        print(f"Found {len(all_bets)} fresh prop bets total")

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

        # Filter for football
        all_bets = [b for b in all_bets if b.sport and b.sport.lower() in ('football', 'soccer')]

        # Sort by EV
        all_bets.sort(key=lambda x: x.ev_percent, reverse=True)

        print(f"After filtering: {len(all_bets)} football prop bets\n")

        # Find best Bet365 and best DanskeSpil
        bet365_best = None
        ds_best = None

        for bet in all_bets:
            if bet.bookmaker == "Bet365" and bet365_best is None:
                bet365_best = bet
            elif bet.bookmaker == "DanskeSpil" and ds_best is None:
                ds_best = bet
            if bet365_best and ds_best:
                break

        # Send Bet365 bet
        if bet365_best:
            print("=" * 50)
            print(f"Sending Bet365 bet (EV: {bet365_best.ev_percent:.1f}%):")
            market_dk = get_translated_market(bet365_best.market_name, bet365_best.bookmaker)
            msg = format_telegram_alert(bet365_best, market_dk)
            print(msg)
            print()
            send_telegram(msg)
        else:
            print("No fresh Bet365 prop bet found")

        print()

        # Send DanskeSpil bet
        if ds_best:
            print("=" * 50)
            print(f"Sending DanskeSpil bet (EV: {ds_best.ev_percent:.1f}%):")
            market_dk = get_translated_market(ds_best.market_name, ds_best.bookmaker)
            msg = format_telegram_alert(ds_best, market_dk)
            print(msg)
            print()
            send_telegram(msg)
        else:
            print("No fresh DanskeSpil prop bet found")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
