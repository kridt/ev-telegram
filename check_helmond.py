#!/usr/bin/env python3
"""Check raw API data for Helmond Sport fixture."""

import asyncio
import json
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
        bets = await client.get_value_bets(bookmaker="Bet365", sport="football", min_ev=0)

        # Find Helmond Sport bets
        helmond_bets = [b for b in bets if "helmond" in b.fixture_name.lower() or "helmond" in b.home_team.lower()]

        print(f"Found {len(helmond_bets)} bets for Helmond Sport\n")

        for bet in helmond_bets:
            print("=" * 60)
            print(f"Match: {bet.fixture_name}")
            print(f"Market: {bet.market_name}")
            print(f"betSide: {bet.bet_side}")
            print(f"line (hdp): {bet.line}")
            print(f"bookmaker_odds: {bet.bookmaker_odds}")
            print(f"sharp_odds: {bet.sharp_odds}")
            print(f"EV: {bet.ev_percent:.1f}%")
            print(f"\nRAW DATA:")
            print(json.dumps(bet.raw, indent=2, default=str))

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
