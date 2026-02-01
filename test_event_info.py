#!/usr/bin/env python3
"""Test script to check how to get event/match names from Odds-API.io."""

import asyncio
import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("ODDSAPI_API_KEY", "")
BASE_URL = "https://api2.odds-api.io/v3"


async def main():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Get a sample value bet to see the response structure
        print("=" * 60)
        print("1. Fetching value bets from Bet365...")
        print("=" * 60)

        resp = await client.get(
            f"{BASE_URL}/value-bets",
            params={"apiKey": API_KEY, "bookmaker": "Bet365", "sport": "football"}
        )

        if resp.status_code != 200:
            print(f"Error: {resp.status_code}")
            print(resp.text[:500])
            return

        bets = resp.json()
        print(f"Got {len(bets)} value bets")

        if bets:
            # Show first bet's full structure
            print("\nFirst bet structure:")
            print(json.dumps(bets[0], indent=2, default=str))

            # Check if event info is included
            first_bet = bets[0]
            event = first_bet.get("event", {})
            event_id = first_bet.get("eventId") or event.get("id")

            print(f"\neventId field: {first_bet.get('eventId')}")
            print(f"event object: {event}")
            print(f"event.id: {event.get('id')}")
            print(f"event.homeTeam: {event.get('homeTeam')}")
            print(f"event.awayTeam: {event.get('awayTeam')}")

            # 2. Try to get event details if we have an eventId
            if event_id:
                print("\n" + "=" * 60)
                print(f"2. Trying to fetch event details for eventId: {event_id}")
                print("=" * 60)

                # Try different endpoint patterns
                endpoints_to_try = [
                    (f"/events/{event_id}", {}),
                    ("/events", {"eventId": event_id}),
                    ("/events", {"eventIds": str(event_id)}),
                    ("/events", {"id": event_id}),
                    (f"/odds/{event_id}", {}),
                ]

                for endpoint, params in endpoints_to_try:
                    params["apiKey"] = API_KEY
                    params["sport"] = "football"

                    try:
                        resp = await client.get(f"{BASE_URL}{endpoint}", params=params)
                        print(f"\n{endpoint} with params {params}:")
                        print(f"  Status: {resp.status_code}")
                        if resp.status_code == 200:
                            data = resp.json()
                            if data:
                                print(f"  Response: {json.dumps(data[:2] if isinstance(data, list) else data, indent=2, default=str)[:500]}...")
                            else:
                                print("  Empty response")
                    except Exception as e:
                        print(f"  Error: {e}")

        # 3. Get all events to see the format
        print("\n" + "=" * 60)
        print("3. Fetching football events (first 3)...")
        print("=" * 60)

        resp = await client.get(
            f"{BASE_URL}/events",
            params={"apiKey": API_KEY, "sport": "football"}
        )

        if resp.status_code == 200:
            events = resp.json()
            print(f"Got {len(events)} events")

            if events:
                for event in events[:3]:
                    print(f"\nEvent: {json.dumps(event, indent=2, default=str)[:400]}...")


if __name__ == "__main__":
    asyncio.run(main())
