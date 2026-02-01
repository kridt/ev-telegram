#!/usr/bin/env python3
"""Get bets to verify - lower thresholds."""

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.api.oddsapi import OddsApiClient

API_KEY = os.environ.get("ODDSAPI_API_KEY", "")


async def main():
    client = OddsApiClient(api_key=API_KEY)

    try:
        # Get fresh Bet365 bet - any EV
        print("=" * 60)
        print("BET365 - Verify this bet:")
        print("=" * 60)

        bet365_bets = await client.get_value_bets(bookmaker="Bet365", sport="football", min_ev=0)

        # Get event details
        event_ids = set()
        fresh_bets = []
        for bet in bet365_bets:
            if not bet.is_fresh:
                continue
            market_lower = bet.market_name.lower()
            if 'booking' not in market_lower and 'corner' not in market_lower:
                continue
            if 'totals' in market_lower and bet.line and bet.line == int(bet.line):
                continue
            fresh_bets.append(bet)
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
                        eid = int(bet.event_id)
                        if eid in event_cache:
                            bet.enrich_with_event(event_cache[eid])
                    except:
                        pass

        # Filter for football
        fresh_bets = [b for b in fresh_bets if b.sport and b.sport.lower() in ('football', 'soccer')]

        # Sort by EV
        fresh_bets.sort(key=lambda x: x.ev_percent, reverse=True)

        for bet in fresh_bets[:1]:
            age_min = bet.age_seconds / 60 if bet.age_seconds else 0
            market_lower = bet.market_name.lower()
            bet_side = (bet.bet_side or "").lower()

            if 'spread' in market_lower:
                if bet_side == "home":
                    line_display = f"+{bet.line}" if bet.line >= 0 else f"{bet.line}"
                    pick = f"{bet.home_team} {line_display}"
                else:
                    opp = -bet.line if bet.line else 0
                    line_display = f"+{opp}" if opp >= 0 else f"{opp}"
                    pick = f"{bet.away_team} {line_display}"
            elif 'totals' in market_lower:
                pick = f"Under {bet.line}" if bet_side == "away" else f"Over {bet.line}"
            else:
                pick = bet.selection_display

            print(f"""
Match: {bet.home_team} vs {bet.away_team}
Market: {bet.market_name}
Line: {bet.line}
Pick: {pick}
Odds (API): {bet.bookmaker_odds:.2f}
EV: {bet.ev_percent:.1f}%
Age: {age_min:.1f} min
Link: {bet.betting_link}
""")

        # Get fresh DanskeSpil bet
        print("=" * 60)
        print("DANSKESPIL - Verify this bet:")
        print("=" * 60)

        ds_bets = await client.get_value_bets(bookmaker="DanskeSpil", sport="football", min_ev=0)

        event_ids = set()
        fresh_ds = []
        for bet in ds_bets:
            if not bet.is_fresh:
                continue
            market_lower = bet.market_name.lower()
            if 'booking' not in market_lower and 'corner' not in market_lower:
                continue
            if 'totals' in market_lower and bet.line and bet.line == int(bet.line):
                continue
            fresh_ds.append(bet)
            if bet.event_id:
                try:
                    event_ids.add(int(bet.event_id))
                except:
                    pass

        if event_ids:
            event_cache = await client.get_events_by_ids(list(event_ids))
            for bet in fresh_ds:
                if bet.event_id:
                    try:
                        eid = int(bet.event_id)
                        if eid in event_cache:
                            bet.enrich_with_event(event_cache[eid])
                    except:
                        pass

        fresh_ds = [b for b in fresh_ds if b.sport and b.sport.lower() in ('football', 'soccer')]
        fresh_ds.sort(key=lambda x: x.ev_percent, reverse=True)

        for bet in fresh_ds[:1]:
            age_min = bet.age_seconds / 60 if bet.age_seconds else 0
            market_lower = bet.market_name.lower()
            bet_side = (bet.bet_side or "").lower()

            if 'spread' in market_lower:
                if bet_side == "home":
                    line_display = f"+{bet.line}" if bet.line >= 0 else f"{bet.line}"
                    pick = f"{bet.home_team} {line_display}"
                else:
                    opp = -bet.line if bet.line else 0
                    line_display = f"+{opp}" if opp >= 0 else f"{opp}"
                    pick = f"{bet.away_team} {line_display}"
            elif 'totals' in market_lower:
                pick = f"Under {bet.line}" if bet_side == "away" else f"Over {bet.line}"
            else:
                pick = bet.selection_display

            print(f"""
Match: {bet.home_team} vs {bet.away_team}
Market: {bet.market_name}
Line: {bet.line}
Pick: {pick}
Odds (API): {bet.bookmaker_odds:.2f}
EV: {bet.ev_percent:.1f}%
Age: {age_min:.1f} min
Link: {bet.betting_link}
""")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
