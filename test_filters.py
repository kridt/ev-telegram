#!/usr/bin/env python3
"""Test with new filters."""

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from oddsapi_scanner import run_scan, format_telegram_alert
from src.api.oddsapi import OddsApiClient

API_KEY = os.environ.get("ODDSAPI_API_KEY", "")


async def main():
    print("Testing with new filters:")
    print("- Max age: 5 minutes")
    print("- No whole number lines for totals\n")

    client = OddsApiClient(api_key=API_KEY)

    try:
        value_bets = await run_scan(client)

        print(f"\n{'=' * 60}")
        print(f"FOUND {len(value_bets)} VALUE BETS")
        print(f"{'=' * 60}")

        if value_bets:
            for bet_dict in value_bets:
                raw_bet = bet_dict.get("_raw_bet")
                if raw_bet:
                    age_min = raw_bet.age_seconds / 60 if raw_bet.age_seconds else 0
                    print(f"\n{raw_bet.fixture_name}")
                    print(f"  {raw_bet.market_name}: Line {raw_bet.line}")
                    print(f"  {raw_bet.bookmaker} @ {raw_bet.bookmaker_odds:.2f}")
                    print(f"  EV: {raw_bet.ev_percent:.1f}% | Age: {age_min:.1f} min")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
