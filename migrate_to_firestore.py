#!/usr/bin/env python3
"""Migrate old bets from bet_history.json to Firebase RTDB archive."""

import json
import asyncio
import os
from bet_manager import ArchiveDB

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BET_HISTORY_FILE = os.path.join(SCRIPT_DIR, 'bet_history.json')


async def migrate():
    """Migrate all bets from local JSON to Firebase RTDB archive."""
    # Load local bets
    if not os.path.exists(BET_HISTORY_FILE):
        print("No bet_history.json found")
        return

    with open(BET_HISTORY_FILE, 'r', encoding='utf-8') as f:
        bets = json.load(f)

    print(f"Found {len(bets)} bets to migrate")

    archive = ArchiveDB()
    migrated = 0

    for bet in bets:
        # Convert to archive format
        doc = {
            "fixture": bet.get("fixture", ""),
            "league": bet.get("league", ""),
            "kickoff": bet.get("kickoff", ""),
            "market": bet.get("market", ""),
            "selection": bet.get("selection", ""),
            "bookmaker": bet.get("bookmaker", ""),
            "odds": bet.get("odds", 0),
            "fair_odds": bet.get("sharp_odds", 0),
            "edge": bet.get("edge", 0),
            "stake": bet.get("stake", 10),
            "status": bet.get("result") or "played",  # Assume old bets were played
            "result": bet.get("result"),
            "profit": bet.get("profit"),
            "created_at": bet.get("sent_at", ""),
            "user_action": "played",  # Assume played
            "legacy_id": bet.get("id", 0),
            "migrated": True
        }

        doc_id = await archive.push("bet_history", doc)
        if doc_id:
            migrated += 1
            print(f"  Migrated #{bet.get('id')}: {bet.get('selection')} @ {bet.get('bookmaker')}")
        else:
            print(f"  FAILED #{bet.get('id')}")

    print(f"\nMigration complete: {migrated}/{len(bets)} bets migrated to Firebase")


if __name__ == "__main__":
    asyncio.run(migrate())
