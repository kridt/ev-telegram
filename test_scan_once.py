#!/usr/bin/env python3
"""Run a single scan cycle to test the scanner."""

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Import after setting up encoding
from oddsapi_scanner import run_scan, format_telegram_alert
from src.api.oddsapi import OddsApiClient

API_KEY = os.environ.get("ODDSAPI_API_KEY", "")


async def main():
    print("Running single scan cycle...\n")

    client = OddsApiClient(api_key=API_KEY)

    try:
        value_bets = await run_scan(client)

        print(f"\n{'=' * 60}")
        print(f"SCAN COMPLETE: {len(value_bets)} value bets found")
        print(f"{'=' * 60}")

        if value_bets:
            print("\nSample Telegram messages:\n")
            for bet_dict in value_bets[:3]:
                raw_bet = bet_dict.get("_raw_bet")
                if raw_bet:
                    msg = format_telegram_alert(raw_bet)
                    print(msg)
                    print("-" * 40)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
