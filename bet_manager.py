#!/usr/bin/env python3
"""
Complete bet management system with:
- Realtime DB for active bets (live reactions)
- Firestore for historical archive (analytics)
- Auto-cleanup of expired/non-EV bets
- Telegram message management
"""

import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
import asyncio

# Firebase URLs
RTDB_URL = "https://value-profit-system-default-rtdb.europe-west1.firebasedatabase.app"
FIRESTORE_PROJECT = "value-profit-system"
FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{FIRESTORE_PROJECT}/databases/(default)/documents"

import os
import sys
import json
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not BOT_TOKEN:
    print("[WARNING] TELEGRAM_BOT_TOKEN not set in bet_manager - some features will fail")

# Base unit size in DKK
BASE_UNIT = 10.0

# Load market translations
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSLATIONS_FILE = os.path.join(SCRIPT_DIR, "config", "market_translations.json")
try:
    with open(TRANSLATIONS_FILE, "r", encoding="utf-8") as f:
        MARKET_TRANSLATIONS = json.load(f)
except Exception as e:
    print(f"[WARNING] Could not load market translations: {e}")
    MARKET_TRANSLATIONS = {"markets": {}, "selections": {}}

# Chat ID from environment (keep secret)
THREAD_CHAT_ID = os.environ.get("TELEGRAM_THREAD_CHAT_ID", "")

# Load bookmaker thread config (for Telegram topics)
THREADS_FILE = os.path.join(SCRIPT_DIR, "config", "bookmaker_threads.json")
try:
    with open(THREADS_FILE, "r", encoding="utf-8") as f:
        BOOKMAKER_THREADS = json.load(f)
    BOOKMAKER_THREAD_IDS = BOOKMAKER_THREADS.get("bookmakers", {})
    print(f"[OK] Loaded {len(BOOKMAKER_THREAD_IDS)} bookmaker threads")
except Exception as e:
    print(f"[WARNING] Could not load bookmaker threads: {e}")
    BOOKMAKER_THREAD_IDS = {}


def get_thread_id(bookmaker: str) -> Optional[int]:
    """Get thread ID for a bookmaker. Returns None if not configured."""
    # Try exact match first
    if bookmaker in BOOKMAKER_THREAD_IDS:
        return BOOKMAKER_THREAD_IDS[bookmaker]
    # Try case-insensitive match
    for name, thread_id in BOOKMAKER_THREAD_IDS.items():
        if name.lower() == bookmaker.lower():
            return thread_id
    return None


def get_translated_market(market_name: str, bookmaker: str) -> str:
    """Translate API market name to Danish bookmaker-specific name."""
    markets = MARKET_TRANSLATIONS.get("markets", {})
    if market_name in markets:
        book_translations = markets[market_name]
        return book_translations.get(bookmaker, book_translations.get("default", market_name))
    return market_name

def calculate_stake(odds: float, base_unit: float = BASE_UNIT) -> float:
    """
    Calculate stake based on odds using Kelly-inspired risk management.

    Odds range → Unit multiplier:
    - 2.00 and below → 1.00 unit
    - 2.00 – 2.75 → 0.75 units
    - 2.75 – 4.00 → 0.50 units
    - 4.00 – 7.00 → 0.25 units
    - 7.00 and above → 0.10 units
    """
    if odds <= 2.00:
        multiplier = 1.00
    elif odds <= 2.75:
        multiplier = 0.75
    elif odds <= 4.00:
        multiplier = 0.50
    elif odds <= 7.00:
        multiplier = 0.25
    else:
        multiplier = 0.10

    return round(base_unit * multiplier, 2)


class RealtimeDB:
    """Realtime Database for active bets."""

    def __init__(self):
        self.base_url = RTDB_URL

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path}.json"

    async def push(self, path: str, data: dict) -> Optional[str]:
        """Push new data, returns key."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(self._url(path), json=data)
            if r.status_code == 200:
                return r.json().get("name")
        return None

    async def get(self, path: str) -> Optional[dict]:
        """Get data at path."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(self._url(path))
            if r.status_code == 200:
                return r.json()
        return None

    async def update(self, path: str, data: dict) -> bool:
        """Update data at path."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.patch(self._url(path), json=data)
            return r.status_code == 200

    async def delete(self, path: str) -> bool:
        """Delete data at path."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.delete(self._url(path))
            return r.status_code == 200


class ArchiveDB:
    """RTDB path for archived/settled bets (simpler than Firestore, no auth needed)."""

    def __init__(self):
        self.base_url = RTDB_URL

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path}.json"

    async def push(self, path: str, data: dict) -> Optional[str]:
        """Push new data, returns key."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(self._url(path), json=data)
            if r.status_code == 200:
                return r.json().get("name")
        return None

    async def get_all(self, path: str) -> Dict[str, dict]:
        """Get all documents from path."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(self._url(path))
            if r.status_code == 200:
                return r.json() or {}
        return {}


class TelegramManager:
    """Manage Telegram messages for bets."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.api_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_bet_alert(self, chat_id: str, message: str, bet_key: str, thread_id: int = None) -> Optional[int]:
        """Send bet alert. Returns message_id.

        Args:
            chat_id: Telegram chat ID
            message: Message text
            bet_key: Bet key (for tracking)
            thread_id: Optional thread/topic ID for supergroups with topics
        """
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        # Add thread_id for topic-based supergroups
        if thread_id is not None:
            payload["message_thread_id"] = thread_id

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{self.api_url}/sendMessage", json=payload)
            if r.status_code == 200:
                return r.json().get("result", {}).get("message_id")
            else:
                print(f"[TELEGRAM] Error sending: {r.status_code} - {r.text[:200]}")
        return None

    async def delete_message(self, chat_id: str, message_id: int) -> bool:
        """Delete a message from Telegram."""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{self.api_url}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id}
            )
            return r.status_code == 200

    async def update_message(self, chat_id: str, message_id: int, text: str,
                            show_buttons: bool = False, bet_key: str = None) -> bool:
        """Update a message."""
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML"
        }

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{self.api_url}/editMessageText", json=payload)
            return r.status_code == 200

    async def send_notification(self, chat_id: str, message: str) -> bool:
        """Send a simple notification (no buttons)."""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_notification": True
                }
            )
            return r.status_code == 200


class BetManager:
    """
    Complete bet lifecycle manager.

    Bet statuses:
    - pending: Just sent, waiting for user action
    - played: User clicked "Spillet"
    - skipped: User clicked "Droppet"
    - expired: Kickoff passed without action
    - void: Removed due to odds change / no longer EV
    - won/lost/push: Settled result
    """

    def __init__(self):
        self.rtdb = RealtimeDB()
        self.archive = ArchiveDB()
        self.telegram = TelegramManager(BOT_TOKEN)

    async def create_bet(self, bet_data: dict, chat_id: str) -> Optional[str]:
        """
        Create a new active bet.
        1. Check if bookmaker has a thread ID configured
        2. Save to Realtime DB
        3. Send Telegram message to bookmaker's thread
        4. Store message_id for later management

        Returns None if bet is invalid or bookmaker not configured.
        """
        now = datetime.now(timezone.utc)

        # Get bookmaker and check for thread ID
        bookmaker = bet_data.get("book", "")
        thread_id = get_thread_id(bookmaker)

        # SKIP if bookmaker doesn't have a thread ID configured
        if thread_id is None:
            print(f"[SKIP] No thread ID for bookmaker: {bookmaker}")
            return None

        # Use thread chat ID if configured
        actual_chat_id = THREAD_CHAT_ID if THREAD_CHAT_ID else chat_id

        # STRICT VALIDATION: Require valid selection
        selection = (bet_data.get("selection") or "").strip()
        if not selection:
            # Try market name as fallback
            market = bet_data.get("market", "")
            if market:
                selection = f"{market} (ukendt valg)"
            else:
                # REJECT bet - no selection and no market
                print(f"[REJECT] Skipping bet with no selection: {bet_data.get('fixture', 'Unknown')}")
                return None
            bet_data["selection"] = selection
            print(f"[FAILSAFE] Repaired empty selection -> '{selection}'")

        # Calculate stake based on odds (risk management)
        odds = round(bet_data.get("odds", 0), 2)
        stake = calculate_stake(odds)

        # Prepare bet record
        bet_record = {
            "fixture": bet_data.get("fixture"),
            "fixture_id": bet_data.get("fixture_id"),  # For auto-settle
            "league": bet_data.get("league"),
            "kickoff": bet_data.get("kickoff"),
            "market": bet_data.get("market"),
            "selection": bet_data.get("selection"),
            "bookmaker": bookmaker,
            "odds": odds,
            "fair_odds": round(bet_data.get("fair", 0), 3),
            "edge": round(bet_data.get("edge", 0), 2),
            "stake": stake,
            "status": "pending",
            "created_at": now.isoformat(),
            "chat_id": actual_chat_id,
            "thread_id": thread_id,
            "message_id": None,
            "user_action": None,
            "user_action_at": None,
            "result": None,
            "profit": None
        }

        # Save to Realtime DB first to get key
        bet_key = await self.rtdb.push("active_bets", bet_record)
        if not bet_key:
            return None

        # Format and send Telegram message to bookmaker's thread
        message = self._format_bet_message(bet_data)
        message_id = await self.telegram.send_bet_alert(actual_chat_id, message, bet_key, thread_id)

        if message_id:
            # Update with message_id
            await self.rtdb.update(f"active_bets/{bet_key}", {"message_id": message_id})

        print(f"[BET] Created {bet_key} | {bet_data.get('selection')} @ {bookmaker} (thread {thread_id})")
        return bet_key

    async def mark_played(self, bet_key: str, user_id: str = None, username: str = None, first_name: str = None) -> bool:
        """Mark bet as played by user. Stores user info for tracking."""
        now = datetime.now(timezone.utc)
        return await self.rtdb.update(f"active_bets/{bet_key}", {
            "status": "played",
            "user_action": "played",
            "user_action_at": now.isoformat(),
            "user_id": user_id,
            "username": username,
            "first_name": first_name
        })

    async def mark_skipped(self, bet_key: str, user_id: str = None, username: str = None, first_name: str = None) -> bool:
        """Mark bet as skipped by user. Stores user info for tracking."""
        now = datetime.now(timezone.utc)
        success = await self.rtdb.update(f"active_bets/{bet_key}", {
            "status": "skipped",
            "user_action": "skipped",
            "user_action_at": now.isoformat(),
            "user_id": user_id,
            "username": username,
            "first_name": first_name
        })

        # Delete skipped bets from Telegram after a delay
        if success:
            bet = await self.rtdb.get(f"active_bets/{bet_key}")
            if bet and bet.get("message_id") and bet.get("chat_id"):
                # Update message to show it was skipped, then delete after 30 seconds
                await self.telegram.update_message(
                    bet["chat_id"],
                    bet["message_id"],
                    "❌ <s>Bet droppet</s>",
                    show_buttons=False
                )

        return success

    async def void_bet(self, bet_key: str, reason: str = "No longer EV") -> bool:
        """Void a bet (odds changed, no longer value)."""
        bet = await self.rtdb.get(f"active_bets/{bet_key}")
        if not bet:
            return False

        # Update message to show voided
        if bet.get("message_id") and bet.get("chat_id"):
            void_message = f"🚫 <b>BET ANNULLERET</b>\n\n"
            void_message += f"<s>{bet.get('fixture', '')}\n{bet.get('selection', '')} @ {bet.get('bookmaker', '')}</s>\n\n"
            void_message += f"<i>Grund: {reason}</i>"

            await self.telegram.update_message(
                bet["chat_id"],
                bet["message_id"],
                void_message,
                show_buttons=False
            )

        # Update status
        await self.rtdb.update(f"active_bets/{bet_key}", {
            "status": "void",
            "void_reason": reason,
            "voided_at": datetime.now(timezone.utc).isoformat()
        })

        return True

    async def settle_bet(self, bet_key: str, result: str, profit: float) -> bool:
        """
        Settle a bet and archive to Firestore.
        result: won, lost, push
        """
        bet = await self.rtdb.get(f"active_bets/{bet_key}")
        if not bet:
            return False

        now = datetime.now(timezone.utc)

        # Update final status
        bet["status"] = result
        bet["result"] = result
        bet["profit"] = profit
        bet["settled_at"] = now.isoformat()

        # Archive to Firestore
        await self.archive.push("bet_history", bet)

        # Delete from Realtime DB
        await self.rtdb.delete(f"active_bets/{bet_key}")

        # Update Telegram message
        if bet.get("message_id") and bet.get("chat_id"):
            emoji = "✅" if result == "won" else "❌" if result == "lost" else "➖"
            profit_str = f"+{profit:.2f}" if profit > 0 else f"{profit:.2f}"

            settled_msg = f"{emoji} <b>AFGJORT</b>\n\n"
            settled_msg += f"{bet.get('fixture', '')}\n"
            settled_msg += f"{bet.get('selection', '')} @ {bet.get('bookmaker', '')}\n"
            settled_msg += f"Odds: {bet.get('odds', 0):.2f} | Edge: {bet.get('edge', 0):.1f}%\n\n"
            settled_msg += f"<b>Resultat: {result.upper()}</b>\n"
            settled_msg += f"<b>P&L: {profit_str} DKK</b>"

            await self.telegram.update_message(
                bet["chat_id"],
                bet["message_id"],
                settled_msg,
                show_buttons=False
            )

        print(f"[SETTLE] {bet_key} -> {result} ({profit:+.2f} DKK)")
        return True

    async def cleanup_expired_bets(self) -> int:
        """
        Clean up expired bets:
        1. Delete pending bets where kickoff has passed
        2. Archive them to Firestore as "expired"
        """
        active_bets = await self.rtdb.get("active_bets")
        if not active_bets:
            return 0

        now = datetime.now(timezone.utc)
        cleaned = 0

        for bet_key, bet in active_bets.items():
            if bet.get("status") != "pending":
                continue

            # Check if kickoff passed
            kickoff_str = bet.get("kickoff", "")
            if kickoff_str:
                try:
                    kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
                    if kickoff < now:
                        # Expired - archive and delete
                        bet["status"] = "expired"
                        bet["expired_at"] = now.isoformat()

                        # Archive to Firestore
                        await self.archive.push("bet_history", bet)

                        # Delete Telegram message
                        if bet.get("message_id") and bet.get("chat_id"):
                            await self.telegram.delete_message(bet["chat_id"], bet["message_id"])

                        # Remove from RTDB
                        await self.rtdb.delete(f"active_bets/{bet_key}")
                        cleaned += 1
                        print(f"[EXPIRED] Cleaned up {bet_key}")
                except:
                    pass

        return cleaned

    async def check_odds_validity(self, bet_key: str, current_odds: float, current_fair: float) -> bool:
        """
        Check if bet is still valid.
        If edge dropped below threshold, void it.
        """
        bet = await self.rtdb.get(f"active_bets/{bet_key}")
        if not bet or bet.get("status") != "pending":
            return True

        current_edge = (current_odds / current_fair - 1) * 100
        original_edge = bet.get("edge", 0)

        # If edge dropped by more than 50% or below 3%, void it
        if current_edge < 3.0 or current_edge < original_edge * 0.5:
            await self.void_bet(bet_key, f"Edge faldet: {original_edge:.1f}% → {current_edge:.1f}%")
            return False

        return True

    async def get_active_bets(self) -> Dict[str, dict]:
        """Get all active bets."""
        return await self.rtdb.get("active_bets") or {}

    async def get_bet_history(self, limit: int = 100) -> List[dict]:
        """Get settled bets from archive."""
        data = await self.archive.get_all("bet_history")
        return list(data.values()) if data else []

    async def get_daily_stats(self, date_str: str = None) -> dict:
        """Get statistics for a day."""
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        history = await self.get_bet_history()

        day_bets = [b for b in history if b.get("created_at", "").startswith(date_str)]

        stats = {
            "date": date_str,
            "total": len(day_bets),
            "played": len([b for b in day_bets if b.get("user_action") == "played"]),
            "skipped": len([b for b in day_bets if b.get("user_action") == "skipped"]),
            "expired": len([b for b in day_bets if b.get("status") == "expired"]),
            "won": len([b for b in day_bets if b.get("result") == "won"]),
            "lost": len([b for b in day_bets if b.get("result") == "lost"]),
            "push": len([b for b in day_bets if b.get("result") == "push"]),
            "total_profit": sum(b.get("profit", 0) or 0 for b in day_bets),
            "total_staked": sum(b.get("stake", 0) for b in day_bets if b.get("user_action") == "played")
        }

        return stats

    def _format_bet_message(self, bet: dict) -> str:
        """Format bet for Telegram message."""
        kickoff_str = bet.get("kickoff", "")
        try:
            kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
            kickoff_cet = kickoff + timedelta(hours=1)
            time_display = kickoff_cet.strftime("%H:%M")
        except:
            time_display = "TBD"

        edge = bet.get('edge', 0)
        filled = min(10, int(edge / 2))
        bar = "▓" * filled + "░" * (10 - filled)

        book_icons = {
            "betsson": "🔷", "leovegas": "🟡",
            "unibet": "🟢", "betano": "🟠"
        }
        book = bet.get('book', '').lower()
        icon = book_icons.get(book, "⚪")

        selection = bet.get('selection', '').strip()

        # FAILSAFE: Ensure selection is never empty in display
        if not selection:
            market = bet.get('market', '')
            selection = market if market else "Ukendt spil"

        if "under" in selection.lower():
            arrow = "⬇️"
        elif "over" in selection.lower():
            arrow = "⬆️"
        else:
            arrow = "➡️"

        # Calculate units for display
        odds = bet.get('odds', 0)
        stake = calculate_stake(odds)
        units = stake / BASE_UNIT  # Convert DKK to units

        # Translate market name to Danish
        market_raw = bet.get('market', '')
        bookmaker = bet.get('book', '')
        market_dk = get_translated_market(market_raw, bookmaker)

        return f"""{icon} <b>{bookmaker.upper()}</b> + {edge:.1f}%

⚽ {bet.get('fixture', '')}
🏆 {bet.get('league', '')} | {time_display}

Marked: <b>{market_dk}</b>
Spil: {arrow} <b>{selection}</b>
Odds: <b>{odds:.2f}</b>
Indsats: <b>{units:.2f} units</b>"""

    def _format_bet_message_with_timer(self, bet: dict, created_at: str) -> str:
        """Format bet for Telegram message with eligibility status."""
        kickoff_str = bet.get("kickoff", "")
        try:
            kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
            kickoff_cet = kickoff + timedelta(hours=1)
            time_display = kickoff_cet.strftime("%H:%M")
        except:
            time_display = "TBD"

        edge = bet.get('edge', 0)
        filled = min(10, int(edge / 2))
        bar = "▓" * filled + "░" * (10 - filled)

        book_icons = {
            "betsson": "🔷", "leovegas": "🟡",
            "unibet": "🟢", "betano": "🟠"
        }
        book = bet.get('bookmaker', bet.get('book', '')).lower()
        icon = book_icons.get(book, "⚪")
        bookmaker = bet.get('bookmaker', bet.get('book', ''))

        selection = bet.get('selection', '').strip()
        if not selection:
            market = bet.get('market', '')
            selection = market if market else "Ukendt spil"

        if "under" in selection.lower():
            arrow = "⬇️"
        elif "over" in selection.lower():
            arrow = "⬆️"
        else:
            arrow = "➡️"

        odds = bet.get('odds', 0)
        stake = calculate_stake(odds)
        units = stake / BASE_UNIT

        market_raw = bet.get('market', '')
        market_dk = get_translated_market(market_raw, bookmaker)

        return f"""{icon} <b>{bookmaker.upper()}</b> + {edge:.1f}%

⚽ {bet.get('fixture', '')}
🏆 {bet.get('league', '')} | {time_display}

Marked: <b>{market_dk}</b>
Spil: {arrow} <b>{selection}</b>
Odds: <b>{odds:.2f}</b>
Indsats: <b>{units:.2f} units</b>

✅ <b>Spilbar</b>"""

    def _format_expired_message(self, bet: dict) -> str:
        """Format expired bet message."""
        kickoff_str = bet.get("kickoff", "")
        try:
            kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
            kickoff_cet = kickoff + timedelta(hours=1)
            time_display = kickoff_cet.strftime("%H:%M")
        except:
            time_display = "TBD"

        edge = bet.get('edge', 0)
        filled = min(10, int(edge / 2))
        bar = "░" * 10  # Empty bar for expired

        book_icons = {
            "betsson": "🔷", "leovegas": "🟡",
            "unibet": "🟢", "betano": "🟠"
        }
        book = bet.get('bookmaker', bet.get('book', '')).lower()
        icon = book_icons.get(book, "⚪")
        bookmaker = bet.get('bookmaker', bet.get('book', ''))

        market_raw = bet.get('market', '')
        market_dk = get_translated_market(market_raw, bookmaker)
        selection = bet.get('selection', '').strip() or market_raw

        if "under" in selection.lower():
            arrow = "⬇️"
        elif "over" in selection.lower():
            arrow = "⬆️"
        else:
            arrow = "➡️"

        odds = bet.get('odds', 0)
        stake = calculate_stake(odds)
        units = stake / BASE_UNIT

        return f"""{icon} <s>{bookmaker.upper()} + {edge:.1f}%</s>

⚽ {bet.get('fixture', '')}
🏆 {bet.get('league', '')} | {time_display}

Marked: <s>{market_dk}</s>
Spil: {arrow} <s>{selection}</s>
Odds: <s>{odds:.2f}</s>
Indsats: <s>{units:.2f} units</s>

❌ <b>Ikke spilbar længere</b>"""

    async def update_bet_timers(self) -> int:
        """Update all active bet messages with current timer. Returns count of updated messages."""
        active_bets = await self.rtdb.get("active_bets")
        if not active_bets:
            return 0

        updated = 0
        expired_count = 0
        now = datetime.now(timezone.utc)

        # Process max 5 bets per cycle to avoid rate limits
        processed = 0
        MAX_PER_CYCLE = 5

        for bet_key, bet in active_bets.items():
            if processed >= MAX_PER_CYCLE:
                break

            # Skip bets that already have user action or are expired
            if bet.get("user_action") or bet.get("status") in ("expired", "void"):
                continue

            # Skip if no message_id
            message_id = bet.get("message_id")
            chat_id = bet.get("chat_id")
            if not message_id or not chat_id:
                continue

            created_at = bet.get("created_at", "")

            # Check if bet should be expired (only when match starts)
            try:
                # Check if match has started
                kickoff_str = bet.get("kickoff", "")
                if kickoff_str:
                    kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
                    match_started = now >= kickoff
                else:
                    match_started = False

                # Only expire when match starts
                if match_started:
                    await self.expire_bet(bet_key, bet, reason="match_started")
                    expired_count += 1
                    processed += 1
                    await asyncio.sleep(1.5)
                    continue

            except Exception as e:
                print(f"[TIMER] Error checking expiry for {bet_key}: {e}")
                continue

            # Update message with new timer
            try:
                new_message = self._format_bet_message_with_timer(bet, created_at)
                success = await self.telegram.update_message(
                    chat_id, message_id, new_message,
                    show_buttons=False, bet_key=bet_key
                )
                if success:
                    updated += 1
                processed += 1
                await asyncio.sleep(1.5)  # Wait 1.5 seconds between edits
            except Exception as e:
                print(f"[TIMER] Error updating message for {bet_key}: {e}")

        if expired_count > 0:
            print(f"[TIMER] Expired {expired_count} bets")

        return updated

    async def expire_bet(self, bet_key: str, bet: dict, reason: str = "timeout") -> bool:
        """Mark a bet as expired and update its Telegram message."""
        try:
            # Update status in Firebase
            await self.rtdb.update(f"active_bets/{bet_key}", {
                "status": "expired",
                "expired_at": datetime.now(timezone.utc).isoformat(),
                "expire_reason": reason
            })

            # Update Telegram message
            message_id = bet.get("message_id")
            chat_id = bet.get("chat_id")
            if message_id and chat_id:
                expired_message = self._format_expired_message(bet)
                await self.telegram.update_message(
                    chat_id, message_id, expired_message,
                    show_buttons=False
                )

            print(f"[EXPIRED] {bet_key} - {reason}")
            return True

        except Exception as e:
            print(f"[EXPIRE ERROR] {bet_key}: {e}")
            return False


# Background cleanup task
async def cleanup_loop(manager: BetManager, interval_minutes: int = 5):
    """Run cleanup every N minutes."""
    while True:
        try:
            cleaned = await manager.cleanup_expired_bets()
            if cleaned > 0:
                print(f"[CLEANUP] Removed {cleaned} expired bets")
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}")

        await asyncio.sleep(interval_minutes * 60)


# Background timer update task
async def timer_update_loop(manager: BetManager, interval_seconds: int = 60):
    """Update bet message timers every N seconds."""
    while True:
        try:
            updated = await manager.update_bet_timers()
            if updated > 0:
                print(f"[TIMER] Updated {updated} bet messages")
        except Exception as e:
            print(f"[TIMER ERROR] {e}")

        await asyncio.sleep(interval_seconds)


# Test
if __name__ == "__main__":
    async def test():
        manager = BetManager()

        # Test creating a bet
        test_bet = {
            "fixture": "Test FC vs Demo United",
            "league": "Test League",
            "kickoff": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            "market": "Total Shots",
            "selection": "Over 24.5",
            "book": "Betsson",
            "odds": 2.10,
            "fair": 1.95,
            "edge": 7.7
        }

        # This would need a real chat_id to work
        # key = await manager.create_bet(test_bet, "YOUR_CHAT_ID")

        print("BetManager ready!")
        print("- RTDB: Active bets with real-time reactions")
        print("- Firestore: Historical archive")
        print("- Telegram: Message management")

    asyncio.run(test())
