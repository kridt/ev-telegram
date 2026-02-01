#!/usr/bin/env python3
"""Test script to verify match names are included in value bets."""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

# Fix encoding for Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.api.oddsapi import OddsApiClient, OddsApiValueBet, OddsApiError

API_KEY = os.environ.get("ODDSAPI_API_KEY", "")

# Filters
MIN_EV = 5.0
MAX_EV = 25.0
MIN_ODDS = 1.50
MAX_ODDS = 3.00
MAX_AGE = 600

PROP_KEYWORDS = ['corner', 'booking', 'card', 'shot', 'foul', 'throw', 'offside']


async def main():
    client = OddsApiClient(api_key=API_KEY)

    print("Fetching value bets from Bet365...")

    try:
        bets = await client.get_value_bets(
            bookmaker="Bet365",
            sport="football",
            min_ev=0,
        )
        print(f"Got {len(bets)} total bets")

        # Filter for prop markets
        prop_bets = []
        event_ids = set()

        for bet in bets:
            # Check if prop market
            market_lower = bet.market_name.lower()
            if not any(kw in market_lower for kw in PROP_KEYWORDS):
                continue

            # Check EV range
            if not (MIN_EV <= bet.ev_percent <= MAX_EV):
                continue

            # Check odds range
            if not (MIN_ODDS <= bet.bookmaker_odds <= MAX_ODDS):
                continue

            # Check freshness
            if not bet.is_fresh:
                continue

            prop_bets.append(bet)
            if bet.event_id:
                try:
                    event_ids.add(int(bet.event_id))
                except (ValueError, TypeError):
                    pass

        print(f"\nFound {len(prop_bets)} prop bets matching criteria")
        print(f"Need to fetch {len(event_ids)} event details")

        # Fetch event details
        if event_ids:
            print("\nFetching event details...")
            event_cache = await client.get_events_by_ids(list(event_ids)[:20])  # Limit for testing
            print(f"Retrieved {len(event_cache)} events")

            # Enrich and display
            print("\n" + "=" * 60)
            print("SAMPLE VALUE BETS WITH MATCH NAMES")
            print("=" * 60)

            shown = 0
            for bet in prop_bets[:10]:
                if bet.event_id:
                    try:
                        event_id = int(bet.event_id)
                        if event_id in event_cache:
                            event_data = event_cache[event_id]
                            bet.enrich_with_event(event_data)

                            # Skip non-football
                            if bet.sport and bet.sport.lower() not in ("football", "soccer"):
                                continue

                            print(f"\n{bet.fixture_name}")
                            print(f"  League: {bet.league}")
                            print(f"  Market: {bet.market_name}")
                            print(f"  Selection: {bet.selection_display}")
                            print(f"  Odds: {bet.bookmaker_odds:.2f} @ {bet.bookmaker}")
                            print(f"  Fair: {bet.sharp_odds:.2f}")
                            print(f"  EV: {bet.ev_percent:.1f}%")
                            print(f"  Kickoff: {bet.start_time.strftime('%Y-%m-%d %H:%M') if bet.start_time else 'TBD'}")
                            shown += 1

                            if shown >= 5:
                                break
                    except (ValueError, TypeError):
                        pass

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
