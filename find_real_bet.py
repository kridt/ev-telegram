#!/usr/bin/env python3
"""Find fresh bets that exist right now on Bet365."""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
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
    now = datetime.now(timezone.utc)

    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("Finding FRESH bets from Bet365 (updated in last 5 minutes)...\n")

    try:
        bets = await client.get_value_bets(bookmaker="Bet365", sport="football", min_ev=0)

        # Filter for very fresh bets and prop markets
        fresh_bets = []
        for bet in bets:
            # Must be fresh (< 5 minutes old)
            if bet.age_seconds and bet.age_seconds < 300:
                market_lower = bet.market_name.lower()
                # Prop markets
                if any(kw in market_lower for kw in ['corner', 'booking', 'card']):
                    fresh_bets.append(bet)

        print(f"Found {len(fresh_bets)} fresh prop bets (< 5 min old)")

        # Get event details
        event_ids = set()
        for bet in fresh_bets:
            if bet.event_id:
                try:
                    event_ids.add(int(bet.event_id))
                except:
                    pass

        if event_ids:
            event_cache = await client.get_events_by_ids(list(event_ids))
            for bet in fresh_bets:
                if bet.event_id:
                    try:
                        event_id = int(bet.event_id)
                        if event_id in event_cache:
                            bet.enrich_with_event(event_cache[event_id])
                    except:
                        pass

        # Filter for football only
        fresh_bets = [b for b in fresh_bets if b.sport and b.sport.lower() in ("football", "soccer")]

        # Group by market type
        totals = [b for b in fresh_bets if 'totals' in b.market_name.lower()]
        spreads = [b for b in fresh_bets if 'spread' in b.market_name.lower()]

        print(f"\nTotals (Over/Under): {len(totals)}")
        print(f"Spreads (Handicap): {len(spreads)}")

        # Show freshest spread bets
        if spreads:
            spreads.sort(key=lambda x: x.age_seconds or 9999)
            print(f"\n{'=' * 60}")
            print("FRESHEST SPREAD BETS (with team names)")
            print(f"{'=' * 60}")

            for bet in spreads[:5]:
                kickoff = bet.start_time
                if kickoff:
                    kickoff_cet = kickoff + timedelta(hours=1)
                    kickoff_str = kickoff_cet.strftime("%H:%M CET")
                else:
                    kickoff_str = "TBD"

                age_min = bet.age_seconds / 60 if bet.age_seconds else 0
                market_dk = get_translated_market(bet.market_name, bet.bookmaker)

                # Use team names instead of Hjemmehold/Udehold
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
                    # For away, show the opposite handicap (their perspective)
                    opposite = -line if line else 0
                    if opposite >= 0:
                        pick = f"{team_name} +{opposite}"
                    else:
                        pick = f"{team_name} {opposite}"
                else:
                    pick = "?"

                print(f"""
⚽ {bet.fixture_name}
🏆 {bet.league}
⏰ Kickoff: {kickoff_str}
📊 Updated: {age_min:.1f} min ago

Market (DK): {market_dk}
Spil: ➡️ {pick}
Odds: {bet.bookmaker_odds:.2f}
Link: {bet.betting_link}
""")

        # Show freshest totals bets
        if totals:
            totals.sort(key=lambda x: x.age_seconds or 9999)
            print(f"\n{'=' * 60}")
            print("FRESHEST TOTALS BETS")
            print(f"{'=' * 60}")

            for bet in totals[:5]:
                kickoff = bet.start_time
                if kickoff:
                    kickoff_cet = kickoff + timedelta(hours=1)
                    kickoff_str = kickoff_cet.strftime("%H:%M CET")
                else:
                    kickoff_str = "TBD"

                age_min = bet.age_seconds / 60 if bet.age_seconds else 0
                market_dk = get_translated_market(bet.market_name, bet.bookmaker)

                bet_side = (bet.bet_side or "").lower()
                if bet_side == "away":
                    pick = f"Under {bet.line}"
                else:
                    pick = f"Over {bet.line}"

                print(f"""
⚽ {bet.fixture_name}
🏆 {bet.league}
⏰ Kickoff: {kickoff_str}
📊 Updated: {age_min:.1f} min ago

Market (DK): {market_dk}
Spil: {pick}
Odds: {bet.bookmaker_odds:.2f}
Link: {bet.betting_link}
""")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
