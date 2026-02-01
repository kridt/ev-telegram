#!/usr/bin/env python3
"""Find spread bet examples with team names."""

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


async def main():
    client = OddsApiClient(api_key=API_KEY)

    print("Finding Corners Spread examples with team names...\n")

    try:
        bets = await client.get_value_bets(bookmaker="Bet365", sport="football", min_ev=0)

        # Filter for corners spread only
        spread_bets = [b for b in bets if 'corners spread' in b.market_name.lower()]
        print(f"Found {len(spread_bets)} Corners Spread bets")

        # Get event details
        event_ids = set()
        for bet in spread_bets[:10]:
            if bet.event_id:
                try:
                    event_ids.add(int(bet.event_id))
                except:
                    pass

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

        # Filter for football
        spread_bets = [b for b in spread_bets if b.sport and b.sport.lower() in ("football", "soccer")]

        print(f"\n{'=' * 60}")
        print("CORNERS SPREAD EXAMPLES (with team names)")
        print(f"{'=' * 60}")

        for bet in spread_bets[:6]:
            kickoff = bet.start_time
            if kickoff:
                kickoff_cet = kickoff + timedelta(hours=1)
                kickoff_str = kickoff_cet.strftime("%H:%M CET")
            else:
                kickoff_str = "TBD"

            market_dk = get_translated_market(bet.market_name, bet.bookmaker)

            # Use team names
            bet_side = (bet.bet_side or "").lower()
            line = bet.line if bet.line else 0

            if bet_side == "home":
                team_name = bet.home_team
                if line >= 0:
                    pick = f"{team_name} +{line}"
                else:
                    pick = f"{team_name} {line}"
            elif bet_side == "away":
                team_name = bet.away_team
                opposite = -line if line else 0
                if opposite >= 0:
                    pick = f"{team_name} +{opposite}"
                else:
                    pick = f"{team_name} {opposite}"
            else:
                pick = "?"

            print(f"""
⚽ {bet.fixture_name}
🏆 {bet.league} | {kickoff_str}

Market (DK): {market_dk}
Spil: ➡️ {pick}
Odds: {bet.bookmaker_odds:.2f}
""")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
