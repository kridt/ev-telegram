"""
Odds History Collector
Saves odds snapshots for future backtesting.
Data is stored in Firebase Realtime Database using HTTP API.
"""

import os
import json
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

# Firebase Realtime Database URL
RTDB_URL = "https://value-profit-system-default-rtdb.europe-west1.firebasedatabase.app"


class OddsHistoryCollector:
    """Collects and stores odds data for backtesting using HTTP API."""

    def __init__(self):
        self.base_url = RTDB_URL

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path}.json"

    async def _async_set(self, path: str, data: dict) -> bool:
        """Set data at path asynchronously."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.put(self._url(path), json=data)
                return r.status_code == 200
        except Exception as e:
            print(f"[OddsHistory] Async set error: {e}")
            return False

    async def _async_get(self, path: str) -> Optional[dict]:
        """Get data at path asynchronously."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(self._url(path))
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            print(f"[OddsHistory] Async get error: {e}")
        return None

    def _sync_set(self, path: str, data: dict) -> bool:
        """Set data at path synchronously."""
        try:
            with httpx.Client(timeout=30) as client:
                r = client.put(self._url(path), json=data)
                return r.status_code == 200
        except Exception as e:
            print(f"[OddsHistory] Sync set error: {e}")
            return False

    def _sync_get(self, path: str) -> Optional[dict]:
        """Get data at path synchronously."""
        try:
            with httpx.Client(timeout=30) as client:
                r = client.get(self._url(path))
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            print(f"[OddsHistory] Sync get error: {e}")
        return None

    def save_odds_snapshot(
        self,
        fixture_id: str,
        fixture_info: Dict[str, Any],
        market: str,
        odds_data: Dict[str, Any],
        value_bets: List[Dict[str, Any]] = None
    ) -> bool:
        """
        Save an odds snapshot for a fixture/market.

        Args:
            fixture_id: Unique fixture identifier
            fixture_info: Fixture details (teams, league, kickoff time)
            market: Market type (e.g., "Total Shots")
            odds_data: All odds from all bookmakers
            value_bets: Any value bets detected (optional)

        Returns:
            True if saved successfully
        """
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Get league name safely
            league = fixture_info.get("league", "")
            if isinstance(league, dict):
                league = league.get("name", "")
            else:
                league = str(league) if league else ""

            # Simplify odds data - just keep decimal values, replace invalid keys
            simplified_odds = {}
            for key, books in odds_data.items():
                # Replace special characters in keys that Firebase doesn't like
                safe_key = str(key).replace("|", "_").replace(".", "_").replace("#", "_").replace("$", "_").replace("[", "_").replace("]", "_")
                if isinstance(books, dict):
                    simplified_odds[safe_key] = {
                        b: v.get("decimal") if isinstance(v, dict) else v
                        for b, v in books.items()
                    }
                else:
                    simplified_odds[safe_key] = books

            # Simplify value bets - only keep essential fields
            simplified_vb = []
            if value_bets:
                for vb in value_bets[:5]:  # Limit to 5 per snapshot
                    simplified_vb.append({
                        "selection": str(vb.get("selection", "")),
                        "book": str(vb.get("book", "")),
                        "odds": float(vb.get("odds", 0)),
                        "edge": float(vb.get("edge", 0))
                    })

            # Create snapshot record
            snapshot = {
                "ts": timestamp,
                "fid": fixture_id,
                "home": str(fixture_info.get("home_team_display", "")),
                "away": str(fixture_info.get("away_team_display", "")),
                "league": league,
                "start": str(fixture_info.get("start_date", "")),
                "market": market,
                "odds": simplified_odds,
                "vb_count": len(value_bets) if value_bets else 0,
                "vb": simplified_vb
            }

            # Save to Firebase: /odds_history/{date}/{fixture_id}/{market}/{timestamp}
            safe_market = market.replace(" ", "_").replace("/", "_")
            # Use a simpler timestamp format for path
            ts_key = datetime.now(timezone.utc).strftime("%H%M%S")

            path = f"odds_history/{date_key}/{fixture_id}/{safe_market}/{ts_key}"
            return self._sync_set(path, snapshot)

        except Exception as e:
            print(f"[OddsHistory] Error saving snapshot: {e}")
            import traceback
            traceback.print_exc()
            return False

    def save_fixture_result(
        self,
        fixture_id: str,
        results: Dict[str, Any]
    ) -> bool:
        """
        Save the actual match results for a fixture.

        Args:
            fixture_id: Unique fixture identifier
            results: Match statistics (shots, corners, etc.)

        Returns:
            True if saved successfully
        """
        try:
            timestamp = datetime.now(timezone.utc).isoformat()

            result_record = {
                "timestamp": timestamp,
                "fixture_id": fixture_id,
                "results": results
            }

            path = f"fixture_results/{fixture_id}"
            return self._sync_set(path, result_record)

        except Exception as e:
            print(f"[OddsHistory] Error saving result: {e}")
            return False

    def get_odds_history(
        self,
        start_date: str,
        end_date: str,
        league: str = None,
        market: str = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve historical odds data for backtesting.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            league: Filter by league (optional)
            market: Filter by market (optional)

        Returns:
            List of odds snapshots
        """
        try:
            snapshots = []

            # Parse dates
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")

            # Iterate through each day
            current = start
            while current <= end:
                date_key = current.strftime("%Y-%m-%d")

                day_data = self._sync_get(f"odds_history/{date_key}")

                if day_data:
                    for fixture_id, markets in day_data.items():
                        if not isinstance(markets, dict):
                            continue
                        for market_name, timestamps in markets.items():
                            if not isinstance(timestamps, dict):
                                continue
                            # Apply market filter
                            if market and market.replace(" ", "_") != market_name:
                                continue

                            for ts, snapshot in timestamps.items():
                                if not isinstance(snapshot, dict):
                                    continue
                                # Apply league filter
                                if league:
                                    fixture_league = snapshot.get("fixture", {}).get("league", "")
                                    if league.lower() not in fixture_league.lower():
                                        continue

                                snapshots.append(snapshot)

                current += timedelta(days=1)

            return snapshots

        except Exception as e:
            print(f"[OddsHistory] Error retrieving history: {e}")
            return []

    def get_fixture_result(self, fixture_id: str) -> Optional[Dict[str, Any]]:
        """Get the saved result for a fixture."""
        try:
            return self._sync_get(f"fixture_results/{fixture_id}")
        except Exception as e:
            print(f"[OddsHistory] Error getting result: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about collected data."""
        try:
            # Get all odds history dates (shallow query)
            all_history = self._sync_get("odds_history")

            if not all_history:
                return {
                    "total_days": 0,
                    "date_range": None,
                    "total_snapshots": 0,
                    "total_fixtures": 0,
                    "total_value_bets_logged": 0,
                    "total_results_saved": 0
                }

            dates = sorted(all_history.keys())

            # Count stats
            total_snapshots = 0
            total_fixtures = set()
            total_value_bets = 0

            for date_key, fixtures in all_history.items():
                if not isinstance(fixtures, dict):
                    continue
                for fixture_id, markets in fixtures.items():
                    total_fixtures.add(fixture_id)
                    if not isinstance(markets, dict):
                        continue
                    for market_name, timestamps in markets.items():
                        if not isinstance(timestamps, dict):
                            continue
                        total_snapshots += len(timestamps)
                        for ts, snapshot in timestamps.items():
                            if isinstance(snapshot, dict):
                                total_value_bets += snapshot.get("value_bets_found", 0)

            # Count results
            results = self._sync_get("fixture_results")
            total_results = len(results) if results else 0

            return {
                "total_days": len(dates),
                "date_range": {
                    "start": dates[0] if dates else None,
                    "end": dates[-1] if dates else None
                },
                "total_snapshots": total_snapshots,
                "total_fixtures": len(total_fixtures),
                "total_value_bets_logged": total_value_bets,
                "total_results_saved": total_results
            }

        except Exception as e:
            print(f"[OddsHistory] Error getting stats: {e}")
            return {"error": str(e)}


async def collect_results_for_pending_fixtures():
    """
    Background task to collect results for fixtures that have odds data but no results.
    Should be run periodically (e.g., every hour).
    """
    collector = get_collector()
    api_key = os.environ.get("ODDSAPI_API_KEY", "")

    if not api_key:
        print("[OddsHistory] No API key for results collection")
        return 0

    try:
        # Get all fixture IDs we have odds for (from recent dates)
        all_history = collector._sync_get("odds_history")

        if not all_history:
            return 0

        # Get fixture IDs from recent dates (last 7 days)
        dates = sorted(all_history.keys())[-7:]

        fixture_ids = set()
        for date_key in dates:
            if date_key in all_history and isinstance(all_history[date_key], dict):
                fixture_ids.update(all_history[date_key].keys())

        # Check which fixtures don't have results yet
        existing_results = collector._sync_get("fixture_results") or {}

        pending_fixtures = [fid for fid in fixture_ids if fid not in existing_results]

        if not pending_fixtures:
            return 0

        print(f"[OddsHistory] Collecting results for {len(pending_fixtures)} fixtures...")

        collected = 0
        async with httpx.AsyncClient(timeout=30) as client:
            for fixture_id in pending_fixtures[:20]:  # Limit to 20 per run
                try:
                    response = await client.get(
                        "https://api2.odds-api.io/v3/events",
                        params={"apiKey": api_key, "eventId": fixture_id},
                    )

                    if response.status_code == 200:
                        data = response.json()
                        if data.get("data"):
                            result_data = data["data"][0]
                            stats = result_data.get("stats", {})

                            # Extract relevant stats
                            home_stats = {}
                            away_stats = {}

                            for entry in stats.get("home", []):
                                if entry.get("period") == "all":
                                    home_stats = entry.get("stats", {})
                                    break

                            for entry in stats.get("away", []):
                                if entry.get("period") == "all":
                                    away_stats = entry.get("stats", {})
                                    break

                            results = {
                                "fixture_id": fixture_id,
                                "status": result_data.get("status"),
                                "home_team": result_data.get("home_team_display"),
                                "away_team": result_data.get("away_team_display"),
                                "home_score": result_data.get("home_score"),
                                "away_score": result_data.get("away_score"),
                                "stats": {
                                    "total_shots": (home_stats.get("total_scoring_att", 0) or 0) +
                                                   (away_stats.get("total_scoring_att", 0) or 0),
                                    "shots_on_target": (home_stats.get("ontarget_scoring_att", 0) or 0) +
                                                       (away_stats.get("ontarget_scoring_att", 0) or 0),
                                    "corners": (home_stats.get("won_corners", 0) or 0) +
                                               (away_stats.get("won_corners", 0) or 0),
                                    "home": home_stats,
                                    "away": away_stats
                                }
                            }

                            if collector.save_fixture_result(fixture_id, results):
                                collected += 1

                except Exception as e:
                    pass  # Skip failed fixtures

                await asyncio.sleep(0.5)  # Rate limiting

        print(f"[OddsHistory] Collected {collected} results")
        return collected

    except Exception as e:
        print(f"[OddsHistory] Error collecting results: {e}")
        return 0


# Singleton instance
_collector = None

def get_collector() -> OddsHistoryCollector:
    """Get the singleton collector instance."""
    global _collector
    if _collector is None:
        _collector = OddsHistoryCollector()
    return _collector
