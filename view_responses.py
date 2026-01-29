#!/usr/bin/env python3
"""View who placed/skipped each bet."""

import json
import os

RESPONSES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bet_responses.json')

def main():
    try:
        with open(RESPONSES_FILE, 'r', encoding='utf-8') as f:
            responses = json.load(f)
    except FileNotFoundError:
        print("No responses yet.")
        return

    print("\n" + "="*60)
    print("📋 WHO PLACED / SKIPPED EACH BET")
    print("="*60)

    total_placed = 0
    total_skipped = 0

    for bet_id in sorted(responses.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        data = responses[bet_id]
        placed = data.get('placed', [])
        skipped = data.get('skipped', [])

        total_placed += len(placed)
        total_skipped += len(skipped)

        print(f"\n🎯 Bet #{bet_id}")
        print(f"   ✅ Placed ({len(placed)}): {', '.join(placed) if placed else '-'}")
        print(f"   ❌ Skipped ({len(skipped)}): {', '.join(skipped) if skipped else '-'}")

    print("\n" + "="*60)
    print(f"TOTALS: {total_placed} placed, {total_skipped} skipped")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
