#!/usr/bin/env python3
"""Verify the scanner and Telegram connection work."""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
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


def send_telegram(message: str) -> bool:
    """Send message to Telegram."""
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        return response.json().get("ok", False)
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


async def main():
    print("=" * 50)
    print("VERIFYING DEPLOYMENT")
    print("=" * 50)

    # 1. Check environment variables
    print("\n1. Environment variables:")
    print(f"   ODDSAPI_API_KEY: {'✓ Set' if API_KEY else '✗ Missing'}")
    print(f"   TELEGRAM_BOT_TOKEN: {'✓ Set' if BOT_TOKEN else '✗ Missing'}")
    print(f"   TELEGRAM_CHAT_ID: {'✓ Set' if CHAT_ID else '✗ Missing'}")

    if not all([API_KEY, BOT_TOKEN, CHAT_ID]):
        print("\n✗ Missing environment variables!")
        return

    # 2. Test Odds-API.io connection
    print("\n2. Testing Odds-API.io connection...")
    client = OddsApiClient(api_key=API_KEY)

    try:
        status = await client.check_api_status()
        if status["status"] == "ok":
            print("   ✓ Odds-API.io connection OK")
        else:
            print(f"   ✗ Odds-API.io error: {status['message']}")
            return

        # 3. Fetch some value bets
        print("\n3. Fetching value bets...")
        bets = await client.get_value_bets(bookmaker="Bet365", sport="football", min_ev=0)
        fresh_bets = [b for b in bets if b.is_fresh]
        print(f"   ✓ Got {len(bets)} total bets, {len(fresh_bets)} fresh (<5min)")

    finally:
        await client.close()

    # 4. Test Telegram connection
    print("\n4. Testing Telegram connection...")
    now = datetime.now(timezone.utc) + timedelta(hours=1)
    test_msg = f"""✅ <b>Scanner Deployment Verified</b>

🕐 {now.strftime('%Y-%m-%d %H:%M CET')}
📡 Odds-API.io: Connected
📊 Fresh bets available: {len(fresh_bets)}

Scanner is running on Render!"""

    if send_telegram(test_msg):
        print("   ✓ Telegram message sent!")
    else:
        print("   ✗ Failed to send Telegram message")

    print("\n" + "=" * 50)
    print("VERIFICATION COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
