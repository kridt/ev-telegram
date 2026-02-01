#!/usr/bin/env python3
"""Clean up all Telegram messages and clear Firebase active bets."""

import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
RTDB_URL = "https://value-profit-system-default-rtdb.europe-west1.firebasedatabase.app"


async def cleanup():
    print("[CLEANUP] Starting cleanup...")

    # 1. Get all active bets from Firebase
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{RTDB_URL}/active_bets.json")
        active_bets = r.json() if r.status_code == 200 else {}

    if active_bets:
        print(f"[CLEANUP] Found {len(active_bets)} active bets to clean up")

        # 2. Delete each message from Telegram
        deleted = 0
        for bet_key, bet in active_bets.items():
            message_id = bet.get("message_id")
            chat_id = bet.get("chat_id", CHAT_ID)

            if message_id:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage",
                        json={"chat_id": chat_id, "message_id": message_id}
                    )
                    if r.status_code == 200:
                        deleted += 1
                        print(f"  [OK] Deleted message {message_id}")
                    else:
                        print(f"  [FAIL] Failed to delete {message_id}: {r.text}")
                await asyncio.sleep(0.3)  # Avoid rate limit

        print(f"[CLEANUP] Deleted {deleted} Telegram messages")

        # 3. Clear all active bets from Firebase
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.delete(f"{RTDB_URL}/active_bets.json")
            if r.status_code == 200:
                print("[CLEANUP] Cleared Firebase active_bets")
            else:
                print(f"[ERROR] Failed to clear Firebase: {r.text}")
    else:
        print("[CLEANUP] No active bets found in Firebase")

    # 4. Send a fresh start notification
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": "🔄 <b>Scanner genstartet</b>\n\nAlle tidligere beskeder er slettet.\nScanner kører nu og søger efter nye value bets...",
                "parse_mode": "HTML"
            }
        )

    print("[CLEANUP] Complete!")


if __name__ == "__main__":
    asyncio.run(cleanup())
