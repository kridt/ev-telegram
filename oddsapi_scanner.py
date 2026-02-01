#!/usr/bin/env python3
"""
Odds-API.io Value Bet Scanner

Uses the Odds-API.io /value-bets endpoint to find pre-calculated
value betting opportunities on soccer prop markets from Danish bookmakers.

Features:
- Built-in EV calculation from the API
- Soccer prop markets (corners, cards, shots)
- Danish bookmakers (Bet365, DanskeSpil, Unibet DK, Coolbet)
- Telegram alerts with action buttons
- Firebase integration for bet tracking
- Staggered alert sending to avoid spam

Usage:
    python oddsapi_scanner.py

Environment Variables:
    ODDSAPI_API_KEY     - Odds-API.io API key (required)
    TELEGRAM_BOT_TOKEN  - Telegram bot token
    TELEGRAM_CHAT_ID    - Telegram chat ID for alerts
"""

import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

# Setup logging
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oddsapi_scanner.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import httpx

# Import our Odds-API.io client
from src.api.oddsapi import OddsApiClient, OddsApiValueBet, OddsApiError

# Import bet manager for Firebase integration
try:
    from bet_manager import BetManager
    BET_MANAGER_ENABLED = True
    logger.info("[OK] BetManager loaded")
except ImportError:
    BET_MANAGER_ENABLED = False
    logger.warning("[!] BetManager not available - bets won't be tracked in Firebase")

# Configuration from environment
API_KEY = os.environ.get("ODDSAPI_API_KEY", "")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Danish bookmakers to monitor for VALUE BETS (place bets here)
DANISH_BOOKMAKERS = [
    "Bet365",
    "DanskeSpil",
    "Unibet DK",
    "Coolbet",
    "Betano DK",
    "NordicBet DK",
    "Betsson",
    "LeoVegas",
    "Betinia DK",
    "Campobet DK",
]

# Sharp/Reference bookmakers (for EV calculation, don't bet here)
SHARP_BOOKMAKERS = [
    "Pinnacle",
    "Betfair Exchange",
    "Circa",
    "Sharp Exchange",
]

# Major European bookmakers (additional market reference)
REFERENCE_BOOKMAKERS = [
    "888Sport",
    "Bwin",
    "Betway",
    "WilliamHill",
    "Ladbrokes",
    "Paddy Power",
]

# Value bet filters
MIN_EV_PERCENT = 5.0      # Minimum expected value
MAX_EV_PERCENT = 25.0     # Maximum EV (filter outliers)
MIN_ODDS = 1.50           # Minimum decimal odds
MAX_ODDS = 3.00           # Maximum decimal odds
MAX_ODDS_AGE_SECONDS = 300  # Only use odds updated in last 5 minutes

# Rate limiting
SCAN_INTERVAL_SEC = 300   # 5 minutes between scans
BATCH_INTERVAL_SEC = 120  # 2 minutes between alert batches
BETS_PER_BATCH = 2        # Send 2 bets at a time
MAX_BETS_PER_BOOK = 3     # Max bets per bookmaker per scan

# File paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SENT_ALERTS_FILE = os.path.join(SCRIPT_DIR, "oddsapi_sent_alerts.json")
PENDING_QUEUE_FILE = os.path.join(SCRIPT_DIR, "oddsapi_pending_queue.json")
VALUE_BETS_FILE = os.path.join(SCRIPT_DIR, "oddsapi_value_bets.json")
TRANSLATIONS_FILE = os.path.join(SCRIPT_DIR, "config", "market_translations.json")

# Load market translations
try:
    with open(TRANSLATIONS_FILE, "r", encoding="utf-8") as f:
        TRANSLATIONS = json.load(f)
except Exception as e:
    logger.warning(f"Failed to load translations: {e}")
    TRANSLATIONS = {"markets": {}, "selections": {}}


def get_translated_market(market_name: str, bookmaker: str) -> str:
    """Get Danish translation for market name."""
    markets = TRANSLATIONS.get("markets", {})
    if market_name in markets:
        book_translations = markets[market_name]
        return book_translations.get(bookmaker, book_translations.get("default", market_name))
    return market_name


def validate_env() -> bool:
    """Check required environment variables."""
    missing = []
    if not API_KEY:
        missing.append("ODDSAPI_API_KEY")
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        logger.error("Set these in .env file or environment settings.")
        return False

    logger.info("[OK] All environment variables loaded")
    return True


def load_sent_alerts() -> Dict[str, str]:
    """Load sent alerts from file."""
    try:
        if os.path.exists(SENT_ALERTS_FILE):
            with open(SENT_ALERTS_FILE, "r") as f:
                data = json.load(f)
                # Clean old alerts (older than 24 hours)
                cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                return {k: v for k, v in data.items() if v > cutoff}
    except Exception as e:
        logger.warning(f"Failed to load sent alerts: {e}")
    return {}


def save_sent_alerts(alerts: Dict[str, str]) -> None:
    """Save sent alerts to file."""
    try:
        with open(SENT_ALERTS_FILE, "w") as f:
            json.dump(alerts, f)
    except Exception as e:
        logger.warning(f"Failed to save sent alerts: {e}")


def load_pending_queue() -> List[Dict]:
    """Load pending alerts queue from file."""
    try:
        if os.path.exists(PENDING_QUEUE_FILE):
            with open(PENDING_QUEUE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load pending queue: {e}")
    return []


def save_pending_queue(queue: List[Dict]) -> None:
    """Save pending alerts queue to file."""
    try:
        with open(PENDING_QUEUE_FILE, "w") as f:
            json.dump(queue, f, default=str)
    except Exception as e:
        logger.warning(f"Failed to save pending queue: {e}")


def send_telegram(chat_id: str, message: str, bet_id: Optional[str] = None) -> bool:
    """Send message to Telegram."""
    try:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        response = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10,
        )
        return response.json().get("ok", False)
    except Exception as e:
        logger.error(f"[TELEGRAM] Error: {e}")
        return False


def format_telegram_alert(bet: OddsApiValueBet) -> str:
    """Format a value bet for Telegram in Danish."""
    # Format kickoff time
    kickoff_display = "TBD"
    if bet.start_time:
        kickoff_cet = bet.start_time + timedelta(hours=1)  # UTC to CET
        kickoff_display = kickoff_cet.strftime("%H:%M")

    # EV progress bar (10 blocks, scaled to 20% max)
    ev = bet.ev_percent
    filled = min(10, int(ev / 2))
    bar = "\u25b0" * filled + "\u2591" * (10 - filled)

    # Bookmaker colors
    book_icons = {
        "bet365": "\U0001f537",       # Blue diamond
        "danskespil": "\U0001f7e2",   # Green circle
        "unibet dk": "\U0001f7e2",    # Green circle
        "coolbet": "\U0001f535",      # Blue circle
        "betano dk": "\U0001f7e0",    # Orange circle
        "leovegas": "\U0001f7e1",     # Yellow circle
        "betsson": "\U0001f537",      # Blue diamond
        "nordicbet dk": "\U0001f535", # Blue circle
        "betinia dk": "\U0001f7e3",   # Purple circle
        "campobet dk": "\U0001f7e0",  # Orange circle
    }
    book_key = bet.bookmaker.lower()
    book_icon = book_icons.get(book_key, "\u26aa")

    # Determine pick text based on market type and betSide
    market_lower = bet.market_name.lower()
    bet_side_lower = (bet.bet_side or "").lower()
    line = bet.line if bet.line else 0

    # Check if this is a spread/handicap market (use team names)
    if "spread" in market_lower:
        pick_arrow = "\u27a1\ufe0f"
        if bet_side_lower == "home":
            team_name = bet.home_team or "Hjemmehold"
            if line >= 0:
                pick_text = f"{team_name} +{line}"
            else:
                pick_text = f"{team_name} {line}"
        elif bet_side_lower == "away":
            team_name = bet.away_team or "Udehold"
            opposite = -line if line else 0
            if opposite >= 0:
                pick_text = f"{team_name} +{opposite}"
            else:
                pick_text = f"{team_name} {opposite}"
        else:
            pick_text = bet.selection_display
    # For totals markets: "home" = over, "away" = under (API convention)
    elif bet_side_lower == "away" or "under" in (bet.selection or "").lower():
        pick_arrow = "\u2b07\ufe0f"
        pick_text = f"Under {bet.line}" if bet.line else "Under"
    elif bet_side_lower == "home" or "over" in (bet.selection or "").lower():
        pick_arrow = "\u2b06\ufe0f"
        pick_text = f"Over {bet.line}" if bet.line else "Over"
    else:
        pick_arrow = "\u27a1\ufe0f"
        pick_text = bet.selection_display

    # Get Danish translation for market name
    market_dk = get_translated_market(bet.market_name, bet.bookmaker)

    return f"""\u26a0\ufe0f <b>EV bet fundet</b> \u26a0\ufe0f
{bar} <b>{ev:.1f}%</b>

{book_icon} <b>{bet.bookmaker.upper()}</b>

\u26bd {bet.fixture_name}
\U0001f3c6 {bet.league} | {kickoff_display}

Marked: <b>{market_dk}</b>
Spil: {pick_arrow} <b>{pick_text}</b>
Odds: <b>{bet.bookmaker_odds:.2f}</b>
Fair: <b>{bet.sharp_odds:.2f}</b>"""


def build_selection_text(bet: OddsApiValueBet) -> str:
    """
    Build proper selection text for display.

    FAIL-SAFE: This function ALWAYS returns a meaningful string, never crashes.
    Priority chain: Calculated > selection_display > selection > market+side > "Ukendt spil"
    """
    try:
        # Safe extraction of all fields with defaults
        market_name = getattr(bet, 'market_name', None) or ""
        market_lower = market_name.lower()
        bet_side = (getattr(bet, 'bet_side', None) or "").lower().strip()
        line = getattr(bet, 'line', None)
        home_team = getattr(bet, 'home_team', None) or ""
        away_team = getattr(bet, 'away_team', None) or ""
        selection = getattr(bet, 'selection', None) or ""
        selection_display = getattr(bet, 'selection_display', None) or ""

        # Format line with +/- sign (handles floats and ints)
        def format_line(val) -> str:
            if val is None:
                return ""
            try:
                val = float(val)
                # Format nicely: 9.5 stays 9.5, 9.0 becomes 9
                if val == int(val):
                    val = int(val)
                if val > 0:
                    return f"+{val}"
                elif val == 0:
                    return "0"
                else:
                    return str(val)
            except (ValueError, TypeError):
                return ""

        # ============================================================
        # STRATEGY 1: Calculate based on market type
        # ============================================================

        # --- SPREAD / HANDICAP markets ---
        if any(kw in market_lower for kw in ["spread", "handicap", "asian"]):
            if bet_side in ("home", "1"):
                team = home_team if home_team else "Hjemme"
                line_str = format_line(line)
                return f"{team} {line_str}".strip() if line_str else team
            elif bet_side in ("away", "2"):
                team = away_team if away_team else "Ude"
                # Away handicap is opposite sign of the line shown
                try:
                    opposite = -float(line) if line is not None else None
                    line_str = format_line(opposite)
                except (ValueError, TypeError):
                    line_str = ""
                return f"{team} {line_str}".strip() if line_str else team
            elif bet_side == "draw":
                return "Uafgjort"

        # --- TOTALS / OVER-UNDER markets ---
        elif any(kw in market_lower for kw in ["total", "over", "under", "o/u"]):
            line_str = str(line) if line is not None else ""
            if bet_side in ("home", "over", "o"):
                return f"Over {line_str}".strip() if line_str else "Over"
            elif bet_side in ("away", "under", "u"):
                return f"Under {line_str}".strip() if line_str else "Under"

        # --- 1X2 / MONEYLINE markets ---
        elif any(kw in market_lower for kw in ["1x2", "moneyline", "match winner", "fulltime result"]):
            if bet_side in ("home", "1", "h"):
                return home_team if home_team else "Hjemme sejr"
            elif bet_side in ("away", "2", "a"):
                return away_team if away_team else "Ude sejr"
            elif bet_side in ("draw", "x"):
                return "Uafgjort"

        # --- DOUBLE CHANCE markets ---
        elif "double chance" in market_lower:
            if bet_side in ("1x", "home_draw"):
                home = home_team if home_team else "Hjemme"
                return f"{home} eller Uafgjort"
            elif bet_side in ("x2", "draw_away"):
                away = away_team if away_team else "Ude"
                return f"Uafgjort eller {away}"
            elif bet_side in ("12", "home_away"):
                return "Hjemme eller Ude"

        # --- DRAW NO BET markets ---
        elif "draw no bet" in market_lower or "dnb" in market_lower:
            if bet_side in ("home", "1"):
                return home_team if home_team else "Hjemme (DNB)"
            elif bet_side in ("away", "2"):
                return away_team if away_team else "Ude (DNB)"

        # --- BOTH TEAMS TO SCORE ---
        elif any(kw in market_lower for kw in ["btts", "both teams", "gg/ng"]):
            if bet_side in ("yes", "gg", "over"):
                return "Begge hold scorer: Ja"
            elif bet_side in ("no", "ng", "under"):
                return "Begge hold scorer: Nej"

        # --- CORNERS markets ---
        elif "corner" in market_lower:
            line_str = str(line) if line is not None else ""
            if "spread" in market_lower or "handicap" in market_lower:
                if bet_side in ("home", "1"):
                    team = home_team if home_team else "Hjemme"
                    return f"{team} Hjørnespark {format_line(line)}".strip()
                elif bet_side in ("away", "2"):
                    team = away_team if away_team else "Ude"
                    try:
                        opposite = -float(line) if line is not None else None
                        line_str = format_line(opposite)
                    except (ValueError, TypeError):
                        line_str = ""
                    return f"{team} Hjørnespark {line_str}".strip()
            else:  # Totals
                if bet_side in ("home", "over", "o"):
                    return f"Hjørnespark Over {line_str}".strip()
                elif bet_side in ("away", "under", "u"):
                    return f"Hjørnespark Under {line_str}".strip()

        # --- CARDS / BOOKINGS markets ---
        elif any(kw in market_lower for kw in ["card", "booking"]):
            line_str = str(line) if line is not None else ""
            if "spread" in market_lower or "handicap" in market_lower:
                if bet_side in ("home", "1"):
                    team = home_team if home_team else "Hjemme"
                    return f"{team} Kort {format_line(line)}".strip()
                elif bet_side in ("away", "2"):
                    team = away_team if away_team else "Ude"
                    try:
                        opposite = -float(line) if line is not None else None
                        line_str = format_line(opposite)
                    except (ValueError, TypeError):
                        line_str = ""
                    return f"{team} Kort {line_str}".strip()
            else:  # Totals
                if bet_side in ("home", "over", "o"):
                    return f"Kort Over {line_str}".strip()
                elif bet_side in ("away", "under", "u"):
                    return f"Kort Under {line_str}".strip()

        # ============================================================
        # STRATEGY 2: Use API-provided selection_display
        # ============================================================
        if selection_display and selection_display.strip():
            return selection_display.strip()

        # ============================================================
        # STRATEGY 3: Use API-provided selection
        # ============================================================
        if selection and selection.strip():
            return selection.strip()

        # ============================================================
        # STRATEGY 4: Build from market name + bet_side
        # ============================================================
        if market_name and bet_side:
            # Clean up market name for display
            clean_market = market_name.replace("_", " ").title()
            side_display = bet_side.replace("_", " ").title()
            line_str = f" {line}" if line is not None else ""
            return f"{clean_market}: {side_display}{line_str}"

        # ============================================================
        # STRATEGY 5: Last resort fallbacks
        # ============================================================
        if market_name:
            return f"{market_name} (ukendt)"

        if bet_side:
            return bet_side.title()

        # Absolute last resort
        return "Ukendt spil"

    except Exception as e:
        # CRITICAL: Never crash, always return something
        logger.warning(f"[FAILSAFE] Error building selection text: {e}")
        try:
            # Emergency fallbacks
            if hasattr(bet, 'selection_display') and bet.selection_display:
                return str(bet.selection_display)
            if hasattr(bet, 'selection') and bet.selection:
                return str(bet.selection)
            if hasattr(bet, 'market_name') and bet.market_name:
                return f"{bet.market_name} (fejl)"
        except:
            pass
        return "Ukendt spil"


def convert_to_bet_dict(bet: OddsApiValueBet) -> Dict:
    """Convert OddsApiValueBet to dict format compatible with BetManager."""
    return {
        "fixture": bet.fixture_name,
        "fixture_id": bet.event_id,
        "league": bet.league,
        "kickoff": bet.start_time.isoformat() if bet.start_time else None,
        "market": bet.market_name,
        "selection": build_selection_text(bet),
        "book": bet.bookmaker,
        "odds": bet.bookmaker_odds,
        "american": bet.bookmaker_american,
        "fair": bet.sharp_odds,
        "edge": bet.ev_percent,
        "betting_link": bet.betting_link,
        "source": "oddsapi",
    }


def filter_conflicting_sides(bets: List[Dict]) -> List[Dict]:
    """Filter out conflicting Over/Under bets on the same line."""
    import re

    def extract_line(selection: str) -> str:
        match = re.search(r"[-+]?\d+\.?\d*", selection)
        return match.group() if match else ""

    # Group by fixture + market + line
    groups = defaultdict(list)
    for bet in bets:
        key = f"{bet['fixture']}|{bet['market']}|{extract_line(bet['selection'])}"
        groups[key].append(bet)

    filtered = []
    for key, group_bets in groups.items():
        over_bets = [b for b in group_bets if "over" in b["selection"].lower()]
        under_bets = [b for b in group_bets if "under" in b["selection"].lower()]
        other_bets = [
            b for b in group_bets
            if "over" not in b["selection"].lower() and "under" not in b["selection"].lower()
        ]

        if over_bets and under_bets:
            # Conflict: keep only the best side
            best_over = max(over_bets, key=lambda x: x["edge"])
            best_under = max(under_bets, key=lambda x: x["edge"])

            if best_over["edge"] >= best_under["edge"]:
                filtered.extend(over_bets)
                logger.info(f"[CONFLICT] {key}: Kept Over, removed Under")
            else:
                filtered.extend(under_bets)
                logger.info(f"[CONFLICT] {key}: Kept Under, removed Over")

            filtered.extend(other_bets)
        else:
            filtered.extend(group_bets)

    return filtered


def limit_per_bookmaker(bets: List[Dict], max_per_book: int) -> List[Dict]:
    """Limit bets to max N per bookmaker, keeping highest EV."""
    sorted_bets = sorted(bets, key=lambda x: x["edge"], reverse=True)
    book_counts = defaultdict(int)
    filtered = []

    for bet in sorted_bets:
        book = bet["book"]
        if book_counts[book] < max_per_book:
            filtered.append(bet)
            book_counts[book] += 1

    return filtered


async def run_scan(client: OddsApiClient) -> List[Dict]:
    """Run a single scan cycle using Odds-API.io."""
    now_utc = datetime.now(timezone.utc)
    now_cet = now_utc + timedelta(hours=1)

    logger.info("=" * 60)
    logger.info(f"SCAN: {now_cet.strftime('%Y-%m-%d %H:%M CET')}")
    logger.info("=" * 60)

    all_value_bets = []
    stale_count = 0
    total_fetched = 0
    event_ids_to_fetch = set()

    try:
        # Fetch value bets from each Danish bookmaker
        for bookmaker in DANISH_BOOKMAKERS:
            try:
                bets = await client.get_value_bets(
                    bookmaker=bookmaker,
                    sport="football",
                    min_ev=0,  # Get all, filter later
                )
                total_fetched += len(bets)

                for bet in bets:
                    # Filter criteria - skip non-prop markets early
                    if not bet.is_prop_market:
                        continue

                    if not (MIN_EV_PERCENT <= bet.ev_percent <= MAX_EV_PERCENT):
                        continue

                    if not (MIN_ODDS <= bet.bookmaker_odds <= MAX_ODDS):
                        continue

                    # IMPORTANT: Only use fresh odds (< 5 min old)
                    if not bet.is_fresh:
                        stale_count += 1
                        continue

                    # Double-check age
                    if bet.age_seconds and bet.age_seconds > MAX_ODDS_AGE_SECONDS:
                        stale_count += 1
                        continue

                    # Skip whole number lines for totals (these are 3-way markets)
                    if "totals" in bet.market_name.lower() and bet.line is not None:
                        if bet.line == int(bet.line):  # Whole number like 11, not 10.5
                            continue

                    # Track eventId for fetching event details
                    if bet.event_id:
                        try:
                            event_ids_to_fetch.add(int(bet.event_id))
                        except (ValueError, TypeError):
                            pass

                    # Convert to dict format
                    bet_dict = convert_to_bet_dict(bet)
                    bet_dict["_raw_bet"] = bet  # Keep reference for formatting
                    all_value_bets.append(bet_dict)

                logger.info(f"  {bookmaker}: found {len([b for b in all_value_bets if b['book'] == bookmaker])} qualifying bets")

            except OddsApiError as e:
                logger.warning(f"  {bookmaker}: API error - {e}")
                continue

        # Fetch event details to get match names
        if event_ids_to_fetch:
            logger.info(f"Fetching event details for {len(event_ids_to_fetch)} events...")
            event_cache = await client.get_events_by_ids(list(event_ids_to_fetch))
            logger.info(f"  Retrieved {len(event_cache)} event details")

            # Enrich value bets with event info
            for bet_dict in all_value_bets:
                raw_bet = bet_dict.get("_raw_bet")
                if raw_bet and raw_bet.event_id:
                    try:
                        event_id = int(raw_bet.event_id)
                        if event_id in event_cache:
                            event_data = event_cache[event_id]
                            raw_bet.enrich_with_event(event_data)

                            # Update the dict with enriched data
                            bet_dict["fixture"] = raw_bet.fixture_name
                            bet_dict["league"] = raw_bet.league
                            # Rebuild selection with real team names
                            bet_dict["selection"] = build_selection_text(raw_bet)

                            # Filter out non-football events
                            if raw_bet.sport and raw_bet.sport.lower() not in ("football", "soccer"):
                                bet_dict["_skip"] = True
                    except (ValueError, TypeError):
                        pass

            # Remove non-football bets
            all_value_bets = [b for b in all_value_bets if not b.get("_skip")]

    except Exception as e:
        logger.error(f"Scan error: {e}")
        return []

    # Sort by EV descending
    all_value_bets.sort(key=lambda x: x["edge"], reverse=True)

    # Filter conflicting sides
    no_conflicts = filter_conflicting_sides(all_value_bets)
    logger.info(f"After conflict filter: {len(no_conflicts)} bets")

    # Limit per bookmaker
    filtered = limit_per_bookmaker(no_conflicts, MAX_BETS_PER_BOOK)

    # Count per bookmaker
    book_counts = defaultdict(int)
    for bet in filtered:
        book_counts[bet["book"]] += 1

    logger.info(f"\nFetched {total_fetched} bets, {stale_count} stale (>{MAX_ODDS_AGE_SECONDS}s old)")
    logger.info(f"Found {len(all_value_bets)} fresh value bets")
    logger.info(f"After limit ({MAX_BETS_PER_BOOK}/book): {len(filtered)} bets")
    logger.info(f"  Per bookmaker: {dict(book_counts)}")

    # Save to JSON (without _raw_bet which isn't serializable)
    save_data = [{k: v for k, v in b.items() if k != "_raw_bet"} for b in filtered]
    with open(VALUE_BETS_FILE, "w") as f:
        json.dump(save_data, f, indent=2, default=str)

    return filtered


async def process_queue(
    sent_alerts: Dict[str, str],
    pending_queue: List[Dict],
    bet_manager: Optional["BetManager"] = None,
) -> int:
    """Process pending queue - send bets in batches."""
    if not pending_queue:
        return 0

    sent_count = 0
    to_send = min(BETS_PER_BATCH, len(pending_queue))

    for _ in range(to_send):
        if not pending_queue:
            break

        bet = pending_queue.pop(0)

        # Get the raw bet object for formatting
        raw_bet = bet.pop("_raw_bet", None)

        # FAILSAFE: Validate and repair empty selection
        selection = bet.get("selection", "").strip()
        if not selection:
            # Try to rebuild from raw_bet if available
            if raw_bet:
                try:
                    selection = build_selection_text(raw_bet)
                    bet["selection"] = selection
                    logger.warning(f"[FAILSAFE] Repaired empty selection -> '{selection}'")
                except Exception as e:
                    logger.warning(f"[FAILSAFE] Could not repair selection: {e}")

            # If still empty, use market name as last resort
            if not bet.get("selection", "").strip():
                fallback = bet.get("market", "Ukendt marked")
                bet["selection"] = fallback
                logger.warning(f"[FAILSAFE] Using market as selection: '{fallback}'")

        alert_key = f"{bet['fixture']}|{bet['market']}|{bet['selection']}|{bet['book']}"

        if alert_key in sent_alerts:
            continue

        # Create bet in Firebase and send to Telegram thread
        bet_key = None
        if bet_manager:
            bet_key = await bet_manager.create_bet(bet, CHAT_ID)

        # Skip if no thread ID configured for this bookmaker (no fallback)
        if bet_key is None:
            logger.info(f"  [SKIP] No thread for {bet['book']} - {bet['selection']}")
            continue

        sent_alerts[alert_key] = datetime.now(timezone.utc).isoformat()
        save_sent_alerts(sent_alerts)

        sent_count += 1
        logger.info(f"  [SENT] {bet_key} | {bet['edge']:.1f}% | {bet['selection']} @ {bet['book']}")
        time.sleep(1)

    save_pending_queue(pending_queue)
    return sent_count


async def main():
    """Main scanner loop."""
    logger.info("=" * 60)
    logger.info("ODDS-API.IO VALUE BET SCANNER v1.0")
    logger.info(f"Scan every {SCAN_INTERVAL_SEC // 60}min")
    logger.info(f"Send {BETS_PER_BATCH} bets every {BATCH_INTERVAL_SEC // 60}min")
    logger.info(f"EV range: {MIN_EV_PERCENT}% - {MAX_EV_PERCENT}%")
    logger.info(f"Odds range: {MIN_ODDS} - {MAX_ODDS}")
    logger.info("=" * 60)

    if not validate_env():
        sys.exit(1)

    # Initialize bet manager
    bet_manager = None
    if BET_MANAGER_ENABLED:
        bet_manager = BetManager()
        logger.info("[OK] BetManager initialized")

    # Initialize Odds-API.io client
    client = OddsApiClient(api_key=API_KEY)

    # Check API status
    status = await client.check_api_status()
    if status["status"] != "ok":
        logger.error(f"API check failed: {status['message']}")
        sys.exit(1)
    logger.info("[OK] Odds-API.io connection verified")

    # Silent startup - no Telegram message (runs passively)
    # Load state
    sent_alerts = load_sent_alerts()
    pending_queue = load_pending_queue()

    last_scan_time = 0
    last_send_time = 0
    last_timer_time = 0
    TIMER_INTERVAL_SEC = 60  # Update timers every 60 seconds

    try:
        while True:
            now = time.time()

            # Run scan if enough time has passed
            if now - last_scan_time >= SCAN_INTERVAL_SEC:
                try:
                    value_bets = await run_scan(client)

                    # Add new bets to queue
                    existing_keys = set(sent_alerts.keys())
                    queued_keys = {
                        f"{b['fixture']}|{b['market']}|{b['selection']}|{b['book']}"
                        for b in pending_queue
                    }

                    new_bets = 0
                    skipped_empty = 0
                    for bet in value_bets:
                        # STRICT: Skip bets with empty selection
                        selection = (bet.get('selection') or '').strip()
                        if not selection:
                            skipped_empty += 1
                            logger.warning(f"[SKIP] Empty selection: {bet.get('fixture', 'Unknown')} | {bet.get('market', 'Unknown')}")
                            continue

                        key = f"{bet['fixture']}|{bet['market']}|{bet['selection']}|{bet['book']}"
                        if key not in existing_keys and key not in queued_keys:
                            pending_queue.append(bet)
                            new_bets += 1

                    if skipped_empty > 0:
                        logger.warning(f"[SKIP] Skipped {skipped_empty} bets with empty selection")

                    save_pending_queue(pending_queue)

                    if new_bets > 0:
                        logger.info(f"\nAdded {new_bets} new bets to queue")
                    logger.info(f"Queue size: {len(pending_queue)} pending")

                    last_scan_time = now

                except Exception as e:
                    logger.error(f"[ERROR] Scan failed: {e}")

            # Process queue if enough time has passed
            if pending_queue and now - last_send_time >= BATCH_INTERVAL_SEC:
                sent = await process_queue(sent_alerts, pending_queue, bet_manager)
                if sent > 0:
                    logger.info(f"\n[QUEUE] Sent {sent} bets, {len(pending_queue)} remaining")
                last_send_time = now

            # Update bet timers every 60 seconds
            if bet_manager and now - last_timer_time >= TIMER_INTERVAL_SEC:
                try:
                    updated = await bet_manager.update_bet_timers()
                    if updated > 0:
                        logger.info(f"\n[TIMER] Updated {updated} bet timers")
                except Exception as e:
                    logger.warning(f"[TIMER] Error: {e}")
                last_timer_time = now

            # Status update
            queue_status = f"Queue: {len(pending_queue)}" if pending_queue else "Queue: empty"
            next_scan = max(0, SCAN_INTERVAL_SEC - (now - last_scan_time))
            next_send = max(0, BATCH_INTERVAL_SEC - (now - last_send_time)) if pending_queue else 0

            print(
                f"\r{queue_status} | Next scan: {int(next_scan)}s | Next send: {int(next_send)}s   ",
                end="",
                flush=True,
            )

            await asyncio.sleep(10)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
