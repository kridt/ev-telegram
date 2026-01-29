#!/usr/bin/env python3
"""Automated value bet scanner with Telegram alerts - staggered sending."""

import asyncio
import json
import os
import sys
import time
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Setup logging to file
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scanner.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except:
    pass

import httpx

# Import bet manager
from bet_manager import BetManager

# Configuration - Load from environment variables
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API_KEY = os.environ.get("OPTICODDS_API_KEY", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE_URL = "https://api.opticodds.com/api/v3"

# Validate required environment variables at startup
def validate_env():
    """Check required environment variables are set."""
    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not API_KEY:
        missing.append("OPTICODDS_API_KEY")
    if not CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        print("Set these in .env file or Render environment settings.")
        sys.exit(1)
    print("[OK] All environment variables loaded")

# Bookmakers we actually bet on (Danish licensed)
BETTING_BOOKS = ["betsson", "leovegas", "unibet", "betano"]

# Additional bookmakers for calculating average (reference only, no bets sent)
REFERENCE_BOOKS = ["pinnacle", "888sport", "betway", "bwin", "william_hill", "coolbet"]

# All bookmakers combined (for API calls)
ALL_SPORTSBOOKS = BETTING_BOOKS + REFERENCE_BOOKS

LEAGUES = [
    "england_-_premier_league",
    "spain_-_la_liga",
    "germany_-_bundesliga",
    "italy_-_serie_a",
    "france_-_ligue_1",
    "netherlands_-_eredivisie",
    "portugal_-_primeira_liga",
    "uefa_-_champions_league",
    "uefa_-_europa_league",
    "usa_-_mls",
]
TARGET_MARKETS = [
    "Total Shots", "Total Shots On Target", "Total Corners",
    "Asian Handicap", "Asian Handicap Corners"
]

MIN_EDGE = 5.0
MAX_EDGE = 25.0
MIN_ODDS = 1.50
MAX_ODDS = 3.0
MIN_BOOKS = 4  # Minimum bookmakers needed for reliable average (out of 10 total)

# Stagger settings
MAX_BETS_PER_BOOKMAKER = 3  # Max bets per bookmaker per scan
BETS_PER_BATCH = 2          # Send 2-3 bets at a time
BATCH_INTERVAL_SEC = 120    # 2 minutes between batches
SCAN_INTERVAL_SEC = 300     # 5 minutes between scans

# File paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SENT_ALERTS_FILE = os.path.join(SCRIPT_DIR, 'sent_alerts.json')
PENDING_QUEUE_FILE = os.path.join(SCRIPT_DIR, 'pending_queue.json')
BET_HISTORY_FILE = os.path.join(SCRIPT_DIR, 'bet_history.json')


def load_sent_alerts():
    """Load sent alerts from file."""
    try:
        if os.path.exists(SENT_ALERTS_FILE):
            with open(SENT_ALERTS_FILE, 'r') as f:
                data = json.load(f)
                # Clean old alerts (older than 24 hours)
                cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                return {k: v for k, v in data.items() if v > cutoff}
    except:
        pass
    return {}


def save_sent_alerts(alerts: dict):
    """Save sent alerts to file."""
    try:
        with open(SENT_ALERTS_FILE, 'w') as f:
            json.dump(alerts, f)
    except:
        pass


def load_pending_queue():
    """Load pending alerts queue from file."""
    try:
        if os.path.exists(PENDING_QUEUE_FILE):
            with open(PENDING_QUEUE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return []


def save_pending_queue(queue: list):
    """Save pending alerts queue to file."""
    try:
        with open(PENDING_QUEUE_FILE, 'w') as f:
            json.dump(queue, f, default=str)
    except:
        pass


def load_bet_history():
    """Load bet history from file."""
    try:
        if os.path.exists(BET_HISTORY_FILE):
            with open(BET_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return []


def save_bet_to_history_local(bet: dict) -> None:
    """Save a sent bet to local history as backup."""
    history = load_bet_history()

    # Add metadata for tracking
    history_entry = {
        "id": len(history) + 1,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "fixture": bet["fixture"],
        "league": bet["league"],
        "kickoff": bet["kickoff"],
        "market": bet["market"],
        "selection": bet["selection"],
        "bookmaker": bet["book"],
        "odds": round(bet["odds"], 2),
        "sharp_odds": round(bet["fair"], 2),
        "edge": round(bet["edge"], 2),
        "stake": 10.0,
        "result": None,
        "profit": None
    }

    history.append(history_entry)

    try:
        with open(BET_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Failed to save local bet history: {e}")


sent_alerts = load_sent_alerts()
pending_queue = load_pending_queue()


def load_chat_id():
    """Load chat ID from environment variable or config file."""
    # First try environment variable (for Render/Docker)
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if chat_id:
        return chat_id

    # Fallback to config file (for local development)
    try:
        with open(os.path.join(SCRIPT_DIR, "config/settings.json"), "r") as f:
            config = json.load(f)
            chat_id = config.get("telegram", {}).get("chat_id", "")
            if chat_id:
                return chat_id
    except:
        pass
    return None


def send_telegram(chat_id: str, message: str, bet_id: str = None):
    """Send message to Telegram with optional buttons."""
    try:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        # Add buttons if bet_id provided (Danish labels)
        # bet_id is now a Firebase key string
        if bet_id is not None:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {"text": "Spillet", "callback_data": f"played_{bet_id}"},
                        {"text": "Droppet", "callback_data": f"skipped_{bet_id}"}
                    ]
                ]
            }

        response = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10
        )
        return response.json().get("ok", False)
    except Exception as e:
        print(f"[TELEGRAM] Error: {e}")
        return False


def american_to_decimal(am: float) -> float:
    """Convert American odds to decimal."""
    return 1 + (am / 100) if am >= 0 else 1 + (100 / abs(am))


async def get_fixtures(client: httpx.AsyncClient, league: str) -> list:
    """Get upcoming fixtures for a league."""
    r = await client.get(f"{BASE_URL}/fixtures/active", params={"sport": "soccer", "league": league})
    data = r.json()
    return [f for f in data.get("data", []) if not f.get("is_live", False)]


async def get_odds(client: httpx.AsyncClient, fixture_id: str) -> list:
    """Get odds for a fixture from all bookmakers (betting + reference).

    Note: API requires separate calls per bookmaker, can't batch them.
    """
    all_odds = []
    for book in ALL_SPORTSBOOKS:
        try:
            r = await client.get(f"{BASE_URL}/fixtures/odds",
                params={"fixture_id": fixture_id, "sportsbook": book})
            data = r.json()
            if data.get("data") and len(data["data"]) > 0:
                odds = data["data"][0].get("odds", [])
                all_odds.extend(odds)
        except:
            pass
    return all_odds


def find_value(fixture: dict, odds_list: list, now_cet: datetime, cutoff_cet: datetime) -> list:
    """Find value bets with time filtering."""
    # Check if fixture is within 6-hour window
    kickoff_str = fixture.get("start_date", "")
    if kickoff_str:
        try:
            kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
            cet_offset = timedelta(hours=1)
            kickoff_cet = kickoff + cet_offset
            if not (now_cet <= kickoff_cet <= cutoff_cet):
                return []  # Outside window
        except:
            pass

    value_bets = []
    grouped = defaultdict(dict)

    for odd in odds_list:
        if odd["market"] not in TARGET_MARKETS:
            continue
        key = f"{odd['market']}|{odd['name']}|{odd.get('points', '')}"
        grouped[key][odd["sportsbook"]] = odd

    for key, books in grouped.items():
        if len(books) < MIN_BOOKS:
            continue

        decimals = {}
        for book, odd in books.items():
            dec = american_to_decimal(odd["price"])
            if MIN_ODDS <= dec <= MAX_ODDS:
                decimals[book] = (dec, odd["price"])

        if len(decimals) < MIN_BOOKS:
            continue

        # Calculate AVERAGE odds across ALL bookmakers as fair value
        # More books = more robust consensus price
        all_odds_values = [d[0] for d in decimals.values()]
        avg_odds = sum(all_odds_values) / len(all_odds_values)

        # Only create bets for BETTING_BOOKS (Danish licensed), not reference books
        # Use lowercase comparison since API returns mixed case (e.g., "Betano" vs "betano")
        betting_books_lower = [b.lower() for b in BETTING_BOOKS]
        for book, (dec, american) in decimals.items():
            # Skip reference books - we only bet on Danish books
            if book.lower() not in betting_books_lower:
                continue

            # Edge = how much better than the average price
            edge = (dec / avg_odds - 1) * 100
            if MIN_EDGE <= edge <= MAX_EDGE:
                parts = key.split("|")
                all_odds = {b: round(d[0], 2) for b, d in decimals.items()}
                value_bets.append({
                    "fixture": f"{fixture['home_team_display']} vs {fixture['away_team_display']}",
                    "fixture_id": fixture.get("id"),  # Store for auto-settle
                    "league": fixture["league"]["name"],
                    "kickoff": fixture["start_date"],
                    "market": parts[0],
                    "selection": parts[1],
                    "book": book,
                    "odds": dec,
                    "american": american,
                    "fair": round(avg_odds, 3),
                    "edge": edge,
                    "all_odds": all_odds,
                    "books_in_avg": len(decimals)
                })

    return value_bets


def extract_line_number(selection: str) -> str:
    """Extract the line number from a selection like 'Over 24.5' -> '24.5'."""
    import re
    # Match numbers like 24.5, 10, 0.5, -0.5, +1.5, etc.
    match = re.search(r'[-+]?\d+\.?\d*', selection)
    return match.group() if match else ""


def filter_conflicting_sides(bets: list) -> list:
    """
    Filter out conflicting Over/Under bets on the SAME LINE.

    Example conflicts (same fixture, market, AND line):
    - "Over 24.5" vs "Under 24.5" on Total Shots -> CONFLICT (same line 24.5)
    - "Over 24.5" vs "Over 25.5" on Total Shots -> NO CONFLICT (different lines)
    - "Over 24.5" @ LeoVegas vs "Over 24.5" @ Unibet -> NO CONFLICT (same side, different books - keep both!)

    When Over AND Under exist on same line: keep only the best side (highest edge).
    When same side exists at multiple bookmakers: keep ALL of them.
    """
    # Group by fixture + market + line number
    market_groups = defaultdict(list)

    for bet in bets:
        fixture = bet["fixture"]
        market = bet["market"]  # e.g., "Total Shots On Target"
        line = extract_line_number(bet["selection"])  # e.g., "24.5"

        # Create key that groups Over/Under on SAME LINE together
        group_key = f"{fixture}|{market}|{line}"
        market_groups[group_key].append(bet)

    filtered = []
    for group_key, group_bets in market_groups.items():
        # Check if we have conflicting sides (Over vs Under)
        over_bets = [b for b in group_bets if "over" in b["selection"].lower()]
        under_bets = [b for b in group_bets if "under" in b["selection"].lower()]
        other_bets = [b for b in group_bets if "over" not in b["selection"].lower() and "under" not in b["selection"].lower()]

        if over_bets and under_bets:
            # CONFLICT: Have both Over and Under on same line
            # Pick the side with the highest edge bet, but keep ALL bets from that side
            best_over = max(over_bets, key=lambda x: x["edge"])
            best_under = max(under_bets, key=lambda x: x["edge"])

            if best_over["edge"] >= best_under["edge"]:
                # Keep ALL over bets (different bookmakers)
                filtered.extend(over_bets)
                print(f"  [CONFLICT] {group_key}: Kept {len(over_bets)} Over bets, removed {len(under_bets)} Under bets")
            else:
                # Keep ALL under bets (different bookmakers)
                filtered.extend(under_bets)
                print(f"  [CONFLICT] {group_key}: Kept {len(under_bets)} Under bets, removed {len(over_bets)} Over bets")

            # Also keep other bets (non Over/Under like Asian Handicap selections)
            filtered.extend(other_bets)
        else:
            # No conflict - keep ALL bets (same side at different bookmakers)
            filtered.extend(group_bets)
            if len(group_bets) > 1:
                books = [b["book"] for b in group_bets]
                print(f"  [MULTI-BOOK] {group_key}: Keeping {len(group_bets)} bets from {', '.join(books)}")

    return filtered


def limit_per_bookmaker(bets: list, max_per_book: int) -> list:
    """Limit bets to max N per bookmaker, keeping highest edge."""
    # Sort by edge descending
    sorted_bets = sorted(bets, key=lambda x: x["edge"], reverse=True)

    # Count per bookmaker
    book_counts = defaultdict(int)
    filtered = []

    for bet in sorted_bets:
        book = bet["book"]
        if book_counts[book] < max_per_book:
            filtered.append(bet)
            book_counts[book] += 1

    return filtered


def load_translations():
    """Load Danish translations from file."""
    try:
        trans_file = os.path.join(SCRIPT_DIR, 'translations.json')
        if os.path.exists(trans_file):
            with open(trans_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}


def translate_market(market: str, bookmaker: str, translations: dict) -> str:
    """Translate market name to Danish for specific bookmaker."""
    markets = translations.get('markets', {})
    if market in markets:
        book_lower = bookmaker.lower()
        return markets[market].get(book_lower, markets[market].get('default', market))
    return market


def format_telegram_alert(bet: dict) -> str:
    """Format a value bet for Telegram in Danish."""
    translations = load_translations()
    ui = translations.get('ui', {})

    kickoff_str = bet.get("kickoff", "")
    try:
        kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
        kickoff_cet = kickoff + timedelta(hours=1)
        kickoff_display = kickoff_cet.strftime("%H:%M")
        date_display = kickoff_cet.strftime("%d.%m")
    except:
        kickoff_display = "TBD"
        date_display = ""

    # Edge progress bar (10 blocks, scaled to 20% max)
    edge = bet['edge']
    filled = min(10, int(edge / 2))  # 2% per block
    bar = "▰" * filled + "░" * (10 - filled)

    # Bookmaker colors
    book_icons = {
        "betsson": "🔷",
        "leovegas": "🟡",
        "unibet": "🟢",
        "betano": "🟠"
    }
    book_icon = book_icons.get(bet['book'].lower(), "⚪")

    # Market arrow
    selection = bet['selection']
    if "under" in selection.lower():
        pick_arrow = "⬇️"
    elif "over" in selection.lower():
        pick_arrow = "⬆️"
    else:
        pick_arrow = "➡️"

    # Translate market name for this bookmaker
    market_danish = translate_market(bet['market'], bet['book'], translations)

    return f"""⚠️ <b>{ui.get('value_alert', 'EV bet fundet')}</b> ⚠️
{bar} <b>{edge:.1f}%</b>

{book_icon} <b>{bet['book'].upper()}</b>

⚽ {bet['fixture']}
🏆 {bet['league']} | {kickoff_display}

{ui.get('market', 'Marked')}: <b>{market_danish}</b>
{ui.get('pick', 'Spil')}: {pick_arrow} <b>{selection}</b>
Odds: <b>{bet['odds']:.2f}</b>"""


async def process_queue(chat_id: str, bet_manager: BetManager):
    """Process pending queue - send 2-3 bets then wait."""
    global pending_queue, sent_alerts

    if not pending_queue:
        return 0

    sent_count = 0
    to_send = min(BETS_PER_BATCH, len(pending_queue))

    for _ in range(to_send):
        if not pending_queue:
            break

        bet = pending_queue.pop(0)
        alert_key = f"{bet['fixture']}|{bet['market']}|{bet['selection']}|{bet['book']}"

        # Double check not already sent
        if alert_key in sent_alerts:
            continue

        # Use BetManager to create bet (saves to RTDB + sends Telegram)
        bet_key = await bet_manager.create_bet(bet, chat_id)

        if bet_key:
            sent_alerts[alert_key] = datetime.now(timezone.utc).isoformat()
            save_sent_alerts(sent_alerts)

            # Also save to local history for backup
            save_bet_to_history_local(bet)

            sent_count += 1
            print(f"  [SENT] {bet_key} | {bet['edge']:.1f}% | {bet['selection']} @ {bet['book']}")
            time.sleep(1)  # Small delay between messages in same batch

    # Save updated queue
    save_pending_queue(pending_queue)

    return sent_count


async def run_scan():
    """Run a single scan cycle."""
    global sent_alerts, pending_queue

    now_utc = datetime.now(timezone.utc)
    cet_offset = timedelta(hours=1)
    now_cet = now_utc + cet_offset
    cutoff_cet = now_cet + timedelta(hours=6)

    print(f"\n{'='*60}")
    print(f"SCAN: {now_cet.strftime('%Y-%m-%d %H:%M CET')}")
    print(f"Window: until {cutoff_cet.strftime('%H:%M CET')}")
    print("="*60)

    chat_id = load_chat_id()
    all_value_bets = []

    async with httpx.AsyncClient(
        headers={"x-api-key": API_KEY},
        timeout=60.0
    ) as client:
        for league in LEAGUES:
            try:
                fixtures = await get_fixtures(client, league)

                for fixture in fixtures[:5]:
                    try:
                        odds = await get_odds(client, fixture["id"])
                        if not odds:
                            continue

                        value_bets = find_value(fixture, odds, now_cet, cutoff_cet)
                        all_value_bets.extend(value_bets)

                    except Exception as e:
                        pass

            except Exception as e:
                pass

    # Sort by edge, filter conflicting sides, then limit per bookmaker
    all_value_bets.sort(key=lambda x: x["edge"], reverse=True)

    # IMPORTANT: Filter out conflicting Over/Under on same market
    # Only keep the best side per fixture+market to avoid betting both sides
    no_conflicts = filter_conflicting_sides(all_value_bets)
    print(f"After conflict filter: {len(no_conflicts)} bets (removed {len(all_value_bets) - len(no_conflicts)} conflicting sides)")

    filtered_bets = limit_per_bookmaker(no_conflicts, MAX_BETS_PER_BOOKMAKER)

    # Count per bookmaker for logging
    book_counts = defaultdict(int)
    for bet in filtered_bets:
        book_counts[bet["book"]] += 1

    print(f"\nFound {len(all_value_bets)} total value bets")
    print(f"After limit ({MAX_BETS_PER_BOOKMAKER}/book): {len(filtered_bets)} bets")
    print(f"  Per bookmaker: {dict(book_counts)}")

    # Save to JSON
    with open(os.path.join(SCRIPT_DIR, "value_bets.json"), "w") as f:
        json.dump(filtered_bets, f, indent=2, default=str)

    # Generate dashboard
    try:
        exec(open(os.path.join(SCRIPT_DIR, "generate_dashboard.py")).read())
    except:
        pass

    # Add new bets to queue (not already sent or queued)
    if chat_id:
        existing_keys = set(sent_alerts.keys())
        queued_keys = {f"{b['fixture']}|{b['market']}|{b['selection']}|{b['book']}" for b in pending_queue}

        new_bets = 0
        for bet in filtered_bets:
            alert_key = f"{bet['fixture']}|{bet['market']}|{bet['selection']}|{bet['book']}"
            if alert_key not in existing_keys and alert_key not in queued_keys:
                pending_queue.append(bet)
                new_bets += 1

        save_pending_queue(pending_queue)

        if new_bets > 0:
            print(f"\nAdded {new_bets} new bets to queue")
        print(f"Queue size: {len(pending_queue)} pending")
    else:
        print("\n[!] No Telegram chat ID configured")

    return len(filtered_bets)


async def cleanup_expired_bets(bet_manager: BetManager):
    """Background task to clean up expired bets."""
    while True:
        try:
            cleaned = await bet_manager.cleanup_expired_bets()
            if cleaned > 0:
                print(f"\n[CLEANUP] Removed {cleaned} expired bets")
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}")

        await asyncio.sleep(60)  # Check every minute


async def main():
    global pending_queue

    print("="*60)
    print("SOCCER VALUE BET SCANNER v2.0")
    print("Firebase RTDB | Auto-cleanup")
    print(f"Scan every {SCAN_INTERVAL_SEC//60}min | Send {BETS_PER_BATCH} bets every {BATCH_INTERVAL_SEC//60}min")
    print(f"Max {MAX_BETS_PER_BOOKMAKER} bets per bookmaker")
    print("="*60)

    # Validate environment variables
    validate_env()

    # Initialize bet manager
    bet_manager = BetManager()
    print("\n[OK] BetManager initialized (RTDB + Firestore)")

    chat_id = load_chat_id()
    if chat_id:
        print(f"[OK] Telegram chat ID: {chat_id}")
        send_telegram(chat_id, f"⚽ <b>Scanner v2.0 startet!</b>\n\n📊 Scanner hver {SCAN_INTERVAL_SEC//60} min\n📤 Sender {BETS_PER_BATCH} bets hver {BATCH_INTERVAL_SEC//60} min\n🗑️ Auto-oprydning aktiv\n☁️ Firebase sync aktiv")
    else:
        print("\n[!] No Telegram chat ID found")

    # Start cleanup task
    cleanup_task = asyncio.create_task(cleanup_expired_bets(bet_manager))

    last_scan_time = 0
    last_send_time = 0

    while True:
        now = time.time()

        # Run scan if enough time has passed
        if now - last_scan_time >= SCAN_INTERVAL_SEC:
            try:
                await run_scan()
                last_scan_time = now
            except Exception as e:
                print(f"[ERROR] Scan failed: {e}")

        # Process queue if enough time has passed and queue not empty
        if pending_queue and now - last_send_time >= BATCH_INTERVAL_SEC:
            chat_id = load_chat_id()
            if chat_id:
                sent = await process_queue(chat_id, bet_manager)
                if sent > 0:
                    print(f"\n[QUEUE] Sent {sent} bets, {len(pending_queue)} remaining")
                last_send_time = now

        # Status update
        queue_status = f"Queue: {len(pending_queue)}" if pending_queue else "Queue: empty"
        next_scan = max(0, SCAN_INTERVAL_SEC - (now - last_scan_time))
        next_send = max(0, BATCH_INTERVAL_SEC - (now - last_send_time)) if pending_queue else 0

        print(f"\r{queue_status} | Next scan: {int(next_scan)}s | Next send: {int(next_send)}s   ", end="", flush=True)

        await asyncio.sleep(10)  # Check every 10 seconds


if __name__ == "__main__":
    asyncio.run(main())
