"""
Firebase Realtime Database integration for bet tracking.
Uses REST API for simplicity - no SDK needed.
"""

import os
import json
import httpx
from datetime import datetime
from typing import Optional, Dict, List, Any

# Firebase configuration
FIREBASE_PROJECT_ID = "value-profit-system"
DATABASE_URL = "https://value-profit-system-default-rtdb.europe-west1.firebasedatabase.app"

# For authenticated writes, you can add an API key or use service account
# For now, using open rules for simplicity (configured in database.rules.json)


class FirebaseDB:
    """Firebase Realtime Database client."""

    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url.rstrip("/")
        self.client = httpx.Client(timeout=30.0)

    def _url(self, path: str) -> str:
        """Build full URL for a database path."""
        return f"{self.database_url}/{path}.json"

    def get(self, path: str) -> Optional[Any]:
        """Get data from a path."""
        try:
            response = self.client.get(self._url(path))
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Firebase GET error: {e}")
            return None

    def set(self, path: str, data: Any) -> bool:
        """Set data at a path (overwrites)."""
        try:
            response = self.client.put(self._url(path), json=data)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Firebase SET error: {e}")
            return False

    def push(self, path: str, data: Any) -> Optional[str]:
        """Push data to a list (generates unique key)."""
        try:
            response = self.client.post(self._url(path), json=data)
            response.raise_for_status()
            result = response.json()
            return result.get("name")  # Returns the generated key
        except Exception as e:
            print(f"Firebase PUSH error: {e}")
            return None

    def update(self, path: str, data: Dict) -> bool:
        """Update specific fields at a path."""
        try:
            response = self.client.patch(self._url(path), json=data)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Firebase UPDATE error: {e}")
            return False

    def delete(self, path: str) -> bool:
        """Delete data at a path."""
        try:
            response = self.client.delete(self._url(path))
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Firebase DELETE error: {e}")
            return False


class BetTracker:
    """High-level bet tracking using Firebase."""

    def __init__(self):
        self.db = FirebaseDB()

    def add_bet(self, bet_data: Dict) -> Optional[str]:
        """
        Add a new bet to Firebase.
        Returns the Firebase key for the bet.
        """
        # Add timestamp
        bet_data["created_at"] = datetime.utcnow().isoformat() + "Z"
        bet_data["status"] = "pending"  # pending, played, skipped, won, lost, push

        # Push to bets collection
        key = self.db.push("bets", bet_data)
        if key:
            print(f"Bet saved to Firebase: {key}")
        return key

    def get_bet(self, bet_key: str) -> Optional[Dict]:
        """Get a specific bet by its Firebase key."""
        return self.db.get(f"bets/{bet_key}")

    def get_all_bets(self) -> Dict[str, Dict]:
        """Get all bets."""
        result = self.db.get("bets")
        return result or {}

    def get_bets_by_date(self, date_str: str) -> Dict[str, Dict]:
        """Get bets for a specific date (YYYY-MM-DD)."""
        all_bets = self.get_all_bets()
        filtered = {}
        for key, bet in all_bets.items():
            kickoff = bet.get("kickoff", "")
            if kickoff.startswith(date_str):
                filtered[key] = bet
        return filtered

    def update_bet_status(self, bet_key: str, status: str, profit: float = None) -> bool:
        """
        Update bet status.
        Status: pending, played, skipped, won, lost, push
        """
        update_data = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }
        if profit is not None:
            update_data["profit"] = profit
        return self.db.update(f"bets/{bet_key}", update_data)

    def mark_played(self, bet_key: str) -> bool:
        """Mark a bet as played by user."""
        return self.update_bet_status(bet_key, "played")

    def mark_skipped(self, bet_key: str) -> bool:
        """Mark a bet as skipped by user."""
        return self.update_bet_status(bet_key, "skipped")

    def settle_bet(self, bet_key: str, result: str, profit: float) -> bool:
        """
        Settle a bet with result.
        result: won, lost, push
        """
        return self.update_bet_status(bet_key, result, profit)

    def record_user_action(self, bet_key: str, action: str, user_id: str = None) -> Optional[str]:
        """Record a user action (played/skipped) for analytics."""
        action_data = {
            "bet_key": bet_key,
            "action": action,
            "user_id": user_id or "default",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        return self.db.push("user_actions", action_data)

    def get_stats(self, date_str: str = None) -> Dict:
        """Get betting statistics."""
        bets = self.get_bets_by_date(date_str) if date_str else self.get_all_bets()

        stats = {
            "total": len(bets),
            "played": 0,
            "skipped": 0,
            "won": 0,
            "lost": 0,
            "push": 0,
            "pending": 0,
            "total_profit": 0.0,
            "total_staked": 0.0
        }

        for bet in bets.values():
            status = bet.get("status", "pending")
            stats[status] = stats.get(status, 0) + 1

            if status in ["won", "lost", "push"]:
                stats["total_profit"] += bet.get("profit", 0)

            if status in ["played", "won", "lost", "push"]:
                stats["total_staked"] += bet.get("stake", 10)

        return stats


# Async version for use with async scanner
class AsyncFirebaseDB:
    """Async Firebase Realtime Database client."""

    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.database_url}/{path}.json"

    async def get(self, path: str) -> Optional[Any]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self._url(path))
                response.raise_for_status()
                return response.json()
        except Exception as e:
            print(f"Firebase GET error: {e}")
            return None

    async def push(self, path: str, data: Any) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self._url(path), json=data)
                response.raise_for_status()
                result = response.json()
                return result.get("name")
        except Exception as e:
            print(f"Firebase PUSH error: {e}")
            return None

    async def update(self, path: str, data: Dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(self._url(path), json=data)
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"Firebase UPDATE error: {e}")
            return False


class AsyncBetTracker:
    """Async bet tracker for use with async scanner."""

    def __init__(self):
        self.db = AsyncFirebaseDB()

    async def add_bet(self, bet_data: Dict) -> Optional[str]:
        bet_data["created_at"] = datetime.utcnow().isoformat() + "Z"
        bet_data["status"] = "pending"
        key = await self.db.push("bets", bet_data)
        if key:
            print(f"Bet saved to Firebase: {key}")
        return key

    async def update_bet_status(self, bet_key: str, status: str, profit: float = None) -> bool:
        update_data = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }
        if profit is not None:
            update_data["profit"] = profit
        return await self.db.update(f"bets/{bet_key}", update_data)

    async def mark_played(self, bet_key: str) -> bool:
        return await self.update_bet_status(bet_key, "played")

    async def mark_skipped(self, bet_key: str) -> bool:
        return await self.update_bet_status(bet_key, "skipped")


# Test connection
if __name__ == "__main__":
    print("Testing Firebase connection...")
    tracker = BetTracker()

    # Test push
    test_bet = {
        "fixture": "Test Match",
        "market": "Total Goals",
        "selection": "Over 2.5",
        "bookmaker": "TestBook",
        "odds": 1.95,
        "edge": 5.5,
        "stake": 10
    }

    key = tracker.add_bet(test_bet)
    if key:
        print(f"Test bet created with key: {key}")

        # Test get
        bet = tracker.get_bet(key)
        print(f"Retrieved bet: {bet}")

        # Test update
        tracker.mark_played(key)
        bet = tracker.get_bet(key)
        print(f"After marking played: {bet.get('status')}")

        # Clean up test
        tracker.db.delete(f"bets/{key}")
        print("Test bet deleted")
    else:
        print("Failed to create test bet - check database URL and rules")
