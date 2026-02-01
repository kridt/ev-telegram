#!/usr/bin/env python3
"""Admin dashboard for EV Telegram Bot."""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import httpx
from dotenv import load_dotenv

load_dotenv()

# Firebase config
RTDB_URL = "https://value-profit-system-default-rtdb.europe-west1.firebasedatabase.app"

# Load market translations
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSLATIONS_FILE = os.path.join(SCRIPT_DIR, "config", "market_translations.json")
try:
    with open(TRANSLATIONS_FILE, "r", encoding="utf-8") as f:
        MARKET_TRANSLATIONS = json.load(f)
except Exception as e:
    print(f"[WARNING] Could not load market translations: {e}")
    MARKET_TRANSLATIONS = {"markets": {}, "selections": {}}


def get_translated_market(market_name: str, bookmaker: str) -> str:
    """Translate API market name to Danish bookmaker-specific name."""
    markets = MARKET_TRANSLATIONS.get("markets", {})
    if market_name in markets:
        book_translations = markets[market_name]
        return book_translations.get(bookmaker, book_translations.get("default", market_name))
    return market_name


app = FastAPI(title="EV Bot Admin Dashboard")


async def fetch_firebase(path: str) -> Optional[dict]:
    """Fetch data from Firebase RTDB."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{RTDB_URL}/{path}.json")
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        print(f"Firebase error: {e}")
    return None


def format_time_ago(iso_str: str) -> str:
    """Format time as 'X ago'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        diff = now - dt

        if diff.days > 0:
            return f"{diff.days}d ago"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours}h ago"
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    except:
        return iso_str


def get_status_badge(status: str) -> str:
    """Get colored badge for status."""
    colors = {
        "pending": "#fbbf24",  # yellow
        "played": "#22c55e",   # green
        "skipped": "#ef4444",  # red
        "expired": "#6b7280",  # gray
        "void": "#8b5cf6",     # purple
        "won": "#22c55e",      # green
        "lost": "#ef4444",     # red
        "push": "#3b82f6",     # blue
    }
    color = colors.get(status, "#6b7280")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:12px;">{status.upper()}</span>'


def get_book_icon(book: str) -> str:
    """Get emoji for bookmaker."""
    icons = {
        "betsson": "🔷",
        "leovegas": "🟡",
        "unibet": "🟢",
        "betano": "🟠"
    }
    return icons.get(book.lower(), "⚪")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    # Fetch data from Firebase
    active_bets = await fetch_firebase("active_bets") or {}
    bet_history = await fetch_firebase("bet_history") or {}

    # Calculate stats
    total_active = len(active_bets)
    total_history = len(bet_history)

    # Stats from history
    played_bets = [b for b in bet_history.values() if b.get("user_action") == "played"]
    skipped_bets = [b for b in bet_history.values() if b.get("user_action") == "skipped"]
    won_bets = [b for b in bet_history.values() if b.get("result") == "won"]
    lost_bets = [b for b in bet_history.values() if b.get("result") == "lost"]

    total_profit = sum(b.get("profit", 0) or 0 for b in bet_history.values())
    # Calculate total staked from actual stake values (with fallback to calculated stake)
    def calc_stake(odds):
        if odds <= 2.00: return 10.0
        elif odds <= 2.75: return 7.5
        elif odds <= 4.00: return 5.0
        elif odds <= 7.00: return 2.5
        else: return 1.0
    total_staked = sum(b.get("stake", calc_stake(b.get("odds", 2.0))) for b in played_bets)

    win_rate = (len(won_bets) / len(played_bets) * 100) if played_bets else 0
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0

    # Calculate average odds and edge from played bets
    avg_odds = sum(b.get("odds", 0) for b in played_bets) / len(played_bets) if played_bets else 0
    avg_edge = sum(b.get("edge", 0) for b in played_bets) / len(played_bets) if played_bets else 0

    # Build active bets table
    active_rows = ""
    for key, bet in sorted(active_bets.items(), key=lambda x: x[1].get("created_at", ""), reverse=True):
        book_icon = get_book_icon(bet.get("bookmaker", ""))
        status_badge = get_status_badge(bet.get("status", "pending"))
        created = format_time_ago(bet.get("created_at", ""))

        # Format kickoff
        kickoff_str = bet.get("kickoff", "")
        try:
            kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
            kickoff_cet = kickoff + timedelta(hours=1)
            kickoff_display = kickoff_cet.strftime("%d/%m %H:%M")
        except:
            kickoff_display = "TBD"

        active_rows += f"""
        <tr>
            <td>{book_icon} {bet.get('bookmaker', 'N/A').upper()}</td>
            <td>{bet.get('fixture', 'N/A')}</td>
            <td>{bet.get('market', 'N/A')}</td>
            <td><strong>{bet.get('selection', 'N/A')}</strong></td>
            <td><strong>{bet.get('odds', 0):.2f}</strong></td>
            <td>{bet.get('edge', 0):.1f}%</td>
            <td>{kickoff_display}</td>
            <td>{status_badge}</td>
            <td>{created}</td>
        </tr>
        """

    if not active_rows:
        active_rows = '<tr><td colspan="9" style="text-align:center;color:#666;">No active bets</td></tr>'

    # Build history table (last 20)
    history_items = sorted(bet_history.items(), key=lambda x: x[1].get("created_at", ""), reverse=True)[:20]
    history_rows = ""
    for key, bet in history_items:
        book_icon = get_book_icon(bet.get("bookmaker", ""))
        status_badge = get_status_badge(bet.get("status", "pending"))
        profit = bet.get("profit", 0) or 0
        profit_str = f"+{profit:.0f}" if profit > 0 else f"{profit:.0f}" if profit < 0 else "-"
        profit_color = "#22c55e" if profit > 0 else "#ef4444" if profit < 0 else "#666"

        history_rows += f"""
        <tr>
            <td>{book_icon} {bet.get('bookmaker', 'N/A').upper()}</td>
            <td>{bet.get('fixture', 'N/A')[:30]}...</td>
            <td><strong>{bet.get('selection', 'N/A')}</strong></td>
            <td>{bet.get('odds', 0):.2f}</td>
            <td>{bet.get('edge', 0):.1f}%</td>
            <td>{status_badge}</td>
            <td style="color:{profit_color};font-weight:bold;">{profit_str}</td>
        </tr>
        """

    if not history_rows:
        history_rows = '<tr><td colspan="7" style="text-align:center;color:#666;">No bet history</td></tr>'

    # Build bookmaker stats
    book_stats = {}
    for bet in bet_history.values():
        book = bet.get("bookmaker", "unknown").lower()
        if book not in book_stats:
            book_stats[book] = {"total": 0, "played": 0, "won": 0, "profit": 0}
        book_stats[book]["total"] += 1
        if bet.get("user_action") == "played":
            book_stats[book]["played"] += 1
        if bet.get("result") == "won":
            book_stats[book]["won"] += 1
        book_stats[book]["profit"] += bet.get("profit", 0) or 0

    book_rows = ""
    for book, stats in sorted(book_stats.items(), key=lambda x: x[1]["profit"], reverse=True):
        icon = get_book_icon(book)
        wr = (stats["won"] / stats["played"] * 100) if stats["played"] > 0 else 0
        profit_color = "#22c55e" if stats["profit"] > 0 else "#ef4444" if stats["profit"] < 0 else "#666"
        book_rows += f"""
        <tr>
            <td>{icon} {book.upper()}</td>
            <td>{stats['total']}</td>
            <td>{stats['played']}</td>
            <td>{wr:.0f}%</td>
            <td style="color:{profit_color};font-weight:bold;">{stats['profit']:+.0f} DKK</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>EV Bot Dashboard</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta http-equiv="refresh" content="60">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0f172a;
                color: #e2e8f0;
                padding: 20px;
                line-height: 1.5;
            }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            h1 {{ color: #f8fafc; margin-bottom: 20px; font-size: 24px; }}
            h2 {{ color: #94a3b8; margin: 30px 0 15px; font-size: 18px; }}

            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px;
                margin-bottom: 30px;
            }}
            .stat-card {{
                background: #1e293b;
                border-radius: 10px;
                padding: 20px;
                text-align: center;
            }}
            .stat-value {{
                font-size: 32px;
                font-weight: bold;
                color: #f8fafc;
            }}
            .stat-label {{
                color: #94a3b8;
                font-size: 12px;
                text-transform: uppercase;
                margin-top: 5px;
            }}
            .stat-positive {{ color: #22c55e; }}
            .stat-negative {{ color: #ef4444; }}

            table {{
                width: 100%;
                border-collapse: collapse;
                background: #1e293b;
                border-radius: 10px;
                overflow: hidden;
                font-size: 14px;
            }}
            th {{
                background: #334155;
                color: #94a3b8;
                padding: 12px;
                text-align: left;
                font-weight: 500;
                font-size: 12px;
                text-transform: uppercase;
            }}
            td {{
                padding: 12px;
                border-bottom: 1px solid #334155;
            }}
            tr:hover {{ background: #334155; }}

            .two-col {{
                display: grid;
                grid-template-columns: 2fr 1fr;
                gap: 20px;
            }}
            @media (max-width: 900px) {{
                .two-col {{ grid-template-columns: 1fr; }}
            }}

            .refresh-note {{
                color: #64748b;
                font-size: 12px;
                margin-top: 20px;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚽ EV Telegram Bot Dashboard</h1>
            <p style="margin-bottom:20px;">
                <a href="/settle" style="color:#60a5fa;text-decoration:none;margin-right:20px;">⚖️ Settle Bets</a>
                <a href="/backtest" style="color:#60a5fa;text-decoration:none;margin-right:20px;">📊 Backtest</a>
                <a href="/data-collection" style="color:#22c55e;text-decoration:none;">📦 Data Collection</a>
            </p>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{total_active}</div>
                    <div class="stat-label">Active Bets</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_history}</div>
                    <div class="stat-label">Total Bets</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{len(played_bets)}</div>
                    <div class="stat-label">Played</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{win_rate:.0f}%</div>
                    <div class="stat-label">Win Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{avg_odds:.2f}</div>
                    <div class="stat-label">Avg Odds</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{avg_edge:.1f}%</div>
                    <div class="stat-label">Avg Edge</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value {'stat-positive' if total_profit >= 0 else 'stat-negative'}">{total_profit:+.0f}</div>
                    <div class="stat-label">Profit (DKK)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value {'stat-positive' if roi >= 0 else 'stat-negative'}">{roi:+.1f}%</div>
                    <div class="stat-label">ROI</div>
                </div>
            </div>

            <h2>📊 Active Bets</h2>
            <table>
                <thead>
                    <tr>
                        <th>Book</th>
                        <th>Match</th>
                        <th>Market</th>
                        <th>Pick</th>
                        <th>Odds</th>
                        <th>Edge</th>
                        <th>Kickoff</th>
                        <th>Status</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody>
                    {active_rows}
                </tbody>
            </table>

            <div class="two-col">
                <div>
                    <h2>📜 Recent History</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Book</th>
                                <th>Match</th>
                                <th>Pick</th>
                                <th>Odds</th>
                                <th>Edge</th>
                                <th>Status</th>
                                <th>P&L</th>
                            </tr>
                        </thead>
                        <tbody>
                            {history_rows}
                        </tbody>
                    </table>
                </div>

                <div>
                    <h2>📈 By Bookmaker</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Book</th>
                                <th>Total</th>
                                <th>Played</th>
                                <th>Win%</th>
                                <th>Profit</th>
                            </tr>
                        </thead>
                        <tbody>
                            {book_rows if book_rows else '<tr><td colspan="5" style="text-align:center;color:#666;">No data</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>

            <p class="refresh-note">Auto-refreshes every 60 seconds</p>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


@app.get("/settle", response_class=HTMLResponse)
async def settle_page(request: Request):
    """Settlement page for marking bet results - grouped by match with auto-settle."""
    bet_history = await fetch_firebase("bet_history") or {}
    active_bets = await fetch_firebase("active_bets") or {}

    # Find unsettled bets (played but no result) from bet_history
    unsettled = []
    for key, bet in bet_history.items():
        if bet.get("user_action") == "played" and not bet.get("result"):
            unsettled.append((key, bet))

    # Also include pending/played/expired bets from active_bets (not yet settled)
    for key, bet in active_bets.items():
        if bet.get("status") in ("pending", "played", "expired") and not bet.get("result"):
            # Mark source for display
            bet["_source"] = "active"
            unsettled.append((key, bet))

    # Group by fixture
    matches = {}
    for key, bet in unsettled:
        fixture = bet.get("fixture", "Unknown")
        if fixture not in matches:
            matches[fixture] = []
        matches[fixture].append((key, bet))

    # Sort matches by kickoff
    sorted_matches = sorted(matches.items(), key=lambda x: x[1][0][1].get("kickoff", ""))

    # Stake calculation based on odds (risk management)
    def calc_stake(odds):
        if odds <= 2.00: return 10.0
        elif odds <= 2.75: return 7.5
        elif odds <= 4.00: return 5.0
        elif odds <= 7.00: return 2.5
        else: return 1.0

    # Calculate totals
    total_bets = len(unsettled)
    total_staked = sum(bet.get("stake", calc_stake(bet.get("odds", 2.0))) for _, bet in unsettled)
    avg_edge = sum(bet.get("edge", 0) for _, bet in unsettled) / total_bets if total_bets > 0 else 0

    # Build match cards
    match_cards = ""
    for fixture, bets in sorted_matches:
        match_id = fixture.lower().replace(" ", "_").replace(".", "")[:20]

        # Determine what input fields we need based on markets
        markets = set(bet.get("market", "") for _, bet in bets)
        needs_shots = any("Shot" in m for m in markets)
        needs_sot = any("Shots On Target" in m or "SOT" in m.upper() for m in markets)
        needs_corners = any("Corner" in m for m in markets)
        needs_goals = any("Handicap" in m for m in markets)

        # Input fields
        inputs = ""
        if needs_shots:
            inputs += f'<div class="input-group"><label>Shots:</label><input type="number" id="{match_id}-shots" placeholder="0"></div>'
        if needs_sot:
            inputs += f'<div class="input-group"><label>SOT:</label><input type="number" id="{match_id}-sot" placeholder="0"></div>'
        if needs_corners:
            inputs += f'<div class="input-group"><label>Corners:</label><input type="number" id="{match_id}-corners" placeholder="0"></div>'
        if needs_goals:
            inputs += f'<div class="input-group"><label>Home:</label><input type="number" id="{match_id}-home" placeholder="0"></div>'
            inputs += f'<div class="input-group"><label>Away:</label><input type="number" id="{match_id}-away" placeholder="0"></div>'

        # Build bet rows
        bet_rows = ""
        for key, bet in bets:
            book = bet.get("bookmaker", "")
            book_lower = book.lower()
            book_class = book_lower if book_lower in ["betsson", "leovegas", "unibet", "betano"] else ""
            odds = bet.get("odds", 0)
            edge = bet.get("edge", 0)
            edge_class = "high" if edge >= 10 else "medium" if edge >= 7 else "low"
            selection = bet.get("selection", "")
            arrow = "▲" if "over" in selection.lower() else "▼" if "under" in selection.lower() else ""
            arrow_class = "over" if "over" in selection.lower() else "under" if "under" in selection.lower() else ""
            stake = bet.get("stake", calc_stake(odds))
            market_raw = bet.get("market", "")
            market_dk = get_translated_market(market_raw, book)

            bet_rows += f'''
            <tr data-key="{key}" data-odds="{odds}" data-stake="{stake}" data-market="{market_raw}" data-selection="{selection}">
                <td>{market_dk}</td>
                <td><span class="selection"><span class="arrow {arrow_class}">{arrow}</span> {selection}</span></td>
                <td><span class="bookmaker {book_class}">{book.upper() if book else 'N/A'}</span></td>
                <td>{odds:.2f}</td>
                <td><span class="edge {edge_class}">{edge:.1f}%</span></td>
                <td><input type="number" class="stake-input" id="stake-{key}" value="{stake}" step="0.5" min="0.5" max="50"></td>
                <td class="result-buttons">
                    <button class="result-btn win" onclick="setResultWithStake('{key}', 'won')">Win</button>
                    <button class="result-btn loss" onclick="setResultWithStake('{key}', 'lost')">Loss</button>
                    <button class="result-btn push" onclick="setResultWithStake('{key}', 'push')">Push</button>
                </td>
            </tr>
            '''

        match_cards += f'''
        <div class="match-card" data-match="{match_id}">
            <div class="match-header">
                <span class="match-title">⚽ {fixture}</span>
                <span class="match-count">{len(bets)} bets</span>
            </div>
            <div class="input-row">
                {inputs}
                <button class="settle-all-btn" onclick="settleMatch('{match_id}')">Settle All</button>
            </div>
            <table class="bets-table">
                <thead>
                    <tr><th>Market</th><th>Selection</th><th>Book</th><th>Odds</th><th>Edge</th><th>Stake</th><th>Result</th></tr>
                </thead>
                <tbody>{bet_rows}</tbody>
            </table>
        </div>
        '''

    if not match_cards:
        match_cards = '<div class="empty-state">No unsettled bets! All caught up. 🎉</div>'

    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Settle Bets - EV Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0f0f0f;
                color: #fff;
                padding: 20px;
                max-width: 1200px;
                margin: 0 auto;
            }}
            h1 {{ text-align: center; margin-bottom: 10px; }}
            .subtitle {{ text-align: center; color: #888; margin-bottom: 30px; }}
            .subtitle a {{ color: #60a5fa; text-decoration: none; }}

            .stats-bar {{
                display: flex;
                justify-content: center;
                gap: 30px;
                margin-bottom: 30px;
                flex-wrap: wrap;
            }}
            .stat {{
                background: #1a1a1a;
                padding: 15px 25px;
                border-radius: 10px;
                text-align: center;
            }}
            .stat-value {{ font-size: 24px; font-weight: bold; color: #4ade80; }}
            .stat-value.negative {{ color: #f87171; }}
            .stat-label {{ font-size: 12px; color: #888; margin-top: 5px; }}

            .match-card {{
                background: #1a1a1a;
                border-radius: 12px;
                margin-bottom: 20px;
                overflow: hidden;
            }}
            .match-header {{
                background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
                padding: 15px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .match-header.settled {{ background: linear-gradient(135deg, #16a34a 0%, #15803d 100%); }}
            .match-title {{ font-size: 18px; font-weight: 600; }}
            .match-count {{ background: rgba(255,255,255,0.2); padding: 5px 12px; border-radius: 20px; font-size: 14px; }}

            .input-row {{
                background: #252525;
                padding: 15px 20px;
                display: flex;
                gap: 20px;
                align-items: center;
                flex-wrap: wrap;
            }}
            .input-group {{ display: flex; align-items: center; gap: 10px; }}
            .input-group label {{ color: #888; font-size: 13px; }}
            .input-group input {{
                background: #1a1a1a;
                border: 1px solid #333;
                padding: 8px 12px;
                border-radius: 6px;
                color: #fff;
                width: 70px;
                font-size: 14px;
            }}
            .settle-all-btn {{
                background: #2563eb;
                color: #fff;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 500;
                margin-left: auto;
            }}
            .settle-all-btn:hover {{ background: #1d4ed8; }}

            .bets-table {{ width: 100%; border-collapse: collapse; }}
            .bets-table th {{
                background: #252525;
                padding: 12px 15px;
                text-align: left;
                font-weight: 500;
                color: #888;
                font-size: 12px;
                text-transform: uppercase;
            }}
            .bets-table td {{ padding: 12px 15px; border-bottom: 1px solid #252525; }}
            .bets-table tr:hover {{ background: #252525; }}
            .bets-table tr.settled {{ opacity: 0.5; }}

            .bookmaker {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
            .bookmaker.betsson {{ background: #3b82f6; }}
            .bookmaker.leovegas {{ background: #eab308; color: #000; }}
            .bookmaker.unibet {{ background: #22c55e; }}
            .bookmaker.betano {{ background: #f97316; }}

            .edge {{ font-weight: 600; }}
            .edge.high {{ color: #4ade80; }}
            .edge.medium {{ color: #fbbf24; }}
            .edge.low {{ color: #888; }}

            .selection {{ display: flex; align-items: center; gap: 8px; }}
            .arrow {{ font-size: 14px; }}
            .arrow.over {{ color: #4ade80; }}
            .arrow.under {{ color: #f87171; }}

            .result-buttons {{ display: flex; gap: 5px; }}
            .result-btn {{
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 500;
                transition: all 0.2s;
            }}
            .result-btn.win {{ background: #166534; color: #4ade80; }}
            .result-btn.win:hover, .result-btn.win.active {{ background: #22c55e; color: #fff; }}
            .result-btn.loss {{ background: #7f1d1d; color: #f87171; }}
            .result-btn.loss:hover, .result-btn.loss.active {{ background: #ef4444; color: #fff; }}
            .result-btn.push {{ background: #374151; color: #9ca3af; }}
            .result-btn.push:hover, .result-btn.push.active {{ background: #6b7280; color: #fff; }}

            .empty-state {{ text-align: center; padding: 60px; color: #888; font-size: 18px; }}

            .toast {{
                position: fixed;
                bottom: 20px;
                right: 20px;
                background: #22c55e;
                color: white;
                padding: 15px 25px;
                border-radius: 8px;
                display: none;
                z-index: 1000;
            }}

            .stake-input {{
                background: #1a1a1a;
                border: 1px solid #333;
                padding: 6px 8px;
                border-radius: 4px;
                color: #fff;
                width: 60px;
                font-size: 13px;
                text-align: center;
            }}
            .stake-input:focus {{
                border-color: #2563eb;
                outline: none;
            }}

            .auto-settle-section {{
                background: linear-gradient(135deg, #1e3a5f 0%, #1a2744 100%);
                border: 1px solid #2563eb;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 25px;
                text-align: center;
            }}
            .auto-settle-section h3 {{
                color: #60a5fa;
                margin-bottom: 10px;
                font-size: 16px;
            }}
            .auto-settle-section p {{
                color: #94a3b8;
                font-size: 13px;
                margin-bottom: 15px;
            }}
            .auto-settle-btn {{
                background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
                color: #fff;
                border: none;
                padding: 12px 30px;
                border-radius: 8px;
                font-size: 15px;
                font-weight: 600;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 10px;
            }}
            .auto-settle-btn:hover {{ background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%); }}
            .auto-settle-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
            .auto-settle-btn .spinner {{
                width: 18px;
                height: 18px;
                border: 2px solid #fff;
                border-top-color: transparent;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                display: none;
            }}
            @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

            .auto-settle-progress {{
                display: none;
                margin-top: 20px;
                text-align: left;
            }}
            .auto-settle-progress.show {{ display: block; }}
            .auto-settle-progress .progress-bar {{
                background: #1a1a1a;
                border-radius: 6px;
                height: 10px;
                overflow: hidden;
                margin-bottom: 10px;
            }}
            .auto-settle-progress .progress-fill {{
                background: linear-gradient(90deg, #2563eb, #4ade80);
                height: 100%;
                width: 0%;
                transition: width 0.3s;
            }}
            .auto-settle-progress .status {{
                font-size: 13px;
                color: #94a3b8;
            }}
            .auto-settle-progress .results-log {{
                background: #0f0f0f;
                border-radius: 6px;
                padding: 10px;
                max-height: 200px;
                overflow-y: auto;
                font-family: monospace;
                font-size: 12px;
                margin-top: 10px;
            }}
            .auto-settle-progress .log-entry {{
                padding: 4px 0;
                border-bottom: 1px solid #222;
            }}
            .auto-settle-progress .log-entry.won {{ color: #4ade80; }}
            .auto-settle-progress .log-entry.lost {{ color: #f87171; }}
            .auto-settle-progress .log-entry.push {{ color: #60a5fa; }}
            .auto-settle-progress .log-entry.skip {{ color: #6b7280; }}
        </style>
    </head>
    <body>
        <h1>⚖️ Settle Bets</h1>
        <p class="subtitle"><a href="/">← Back to Dashboard</a></p>

        <div class="stats-bar">
            <div class="stat">
                <div class="stat-value">{total_bets}</div>
                <div class="stat-label">Total Bets</div>
            </div>
            <div class="stat">
                <div class="stat-value">{avg_edge:.1f}%</div>
                <div class="stat-label">Avg Edge</div>
            </div>
            <div class="stat">
                <div class="stat-value">{total_staked:.1f} DKK</div>
                <div class="stat-label">Total Staked</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="totalProfit">0 DKK</div>
                <div class="stat-label">P&L</div>
            </div>
        </div>

        <div class="auto-settle-section">
            <h3>🤖 Auto-Settle with Live Scores</h3>
            <p>Automatically fetch match results from Odds-API and settle all bets. Only works for bets with fixture_id stored.</p>
            <button class="auto-settle-btn" onclick="runAutoSettle()">
                <span class="spinner" id="autoSettleSpinner"></span>
                <span id="autoSettleBtnText">⚡ Auto-Settle All</span>
            </button>
            <div class="auto-settle-progress" id="autoSettleProgress">
                <div class="progress-bar"><div class="progress-fill" id="autoSettleProgressBar"></div></div>
                <div class="status" id="autoSettleStatus">Starting...</div>
                <div class="results-log" id="autoSettleLog"></div>
            </div>
        </div>

        {match_cards}

        <div id="toast" class="toast"></div>

        <script>
            const STAKE = 10;
            let totalProfit = 0;
            const settledBets = new Set();

            async function setResult(betKey, result, profit) {{
                if (settledBets.has(betKey)) return;

                const row = document.querySelector(`tr[data-key="${{betKey}}"]`);
                const buttons = row.querySelectorAll('.result-btn');
                buttons.forEach(btn => btn.classList.remove('active'));
                event.target.classList.add('active');

                // Update Firebase
                try {{
                    const response = await fetch('/api/settle', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ bet_key: betKey, result: result, profit: profit }})
                    }});

                    if (response.ok) {{
                        settledBets.add(betKey);
                        row.classList.add('settled');
                        totalProfit += profit;
                        updateProfitDisplay();
                        showToast(`${{result.toUpperCase()}}: ${{profit >= 0 ? '+' : ''}}${{profit}} DKK`);
                    }}
                }} catch (e) {{
                    alert('Error: ' + e);
                }}
            }}

            function setResultWithStake(betKey, result) {{
                // Read stake from input field
                const stakeInput = document.getElementById(`stake-${{betKey}}`);
                const stake = parseFloat(stakeInput?.value) || 10;

                // Get odds from row data
                const row = document.querySelector(`tr[data-key="${{betKey}}"]`);
                const odds = parseFloat(row.dataset.odds) || 2.0;

                // Calculate profit based on result
                let profit = 0;
                if (result === 'won') {{
                    profit = (odds - 1) * stake;
                }} else if (result === 'lost') {{
                    profit = -stake;
                }} else if (result === 'push') {{
                    profit = 0;
                }}

                // Round to 2 decimals
                profit = Math.round(profit * 100) / 100;

                // Call the main setResult function
                setResult(betKey, result, profit);
            }}

            function updateProfitDisplay() {{
                const el = document.getElementById('totalProfit');
                el.textContent = `${{totalProfit >= 0 ? '+' : ''}}${{totalProfit.toFixed(0)}} DKK`;
                el.className = 'stat-value ' + (totalProfit >= 0 ? '' : 'negative');
            }}

            function settleMatch(matchId) {{
                const card = document.querySelector(`[data-match="${{matchId}}"]`);
                const rows = card.querySelectorAll('tbody tr');

                const shots = parseInt(document.getElementById(`${{matchId}}-shots`)?.value) || 0;
                const sot = parseInt(document.getElementById(`${{matchId}}-sot`)?.value) || 0;
                const corners = parseInt(document.getElementById(`${{matchId}}-corners`)?.value) || 0;
                const homeGoals = parseInt(document.getElementById(`${{matchId}}-home`)?.value) || 0;
                const awayGoals = parseInt(document.getElementById(`${{matchId}}-away`)?.value) || 0;

                rows.forEach(row => {{
                    const betKey = row.dataset.key;
                    if (settledBets.has(betKey)) return;

                    const market = row.dataset.market.toLowerCase();
                    const selection = row.dataset.selection;
                    const odds = parseFloat(row.dataset.odds);

                    const lineMatch = selection.match(/[\\d.]+/);
                    const line = lineMatch ? parseFloat(lineMatch[0]) : 0;
                    const isOver = selection.toLowerCase().includes('over');
                    const isUnder = selection.toLowerCase().includes('under');

                    let result = null;
                    let profit = 0;

                    if (market.includes('shots on target') || market.includes('sot')) {{
                        if (isOver) result = sot > line ? 'won' : 'lost';
                        else if (isUnder) result = sot < line ? 'won' : 'lost';
                    }} else if (market.includes('shot')) {{
                        if (isOver) result = shots > line ? 'won' : 'lost';
                        else if (isUnder) result = shots < line ? 'won' : 'lost';
                    }} else if (market.includes('corner')) {{
                        if (isOver) result = corners > line ? 'won' : 'lost';
                        else if (isUnder) result = corners < line ? 'won' : 'lost';
                    }} else if (market.includes('handicap')) {{
                        if (selection.includes('+')) {{
                            const team = selection.includes('Away') || selection.match(/[A-Z][a-z]+.*\\+/);
                            result = (awayGoals + line) > homeGoals ? 'won' : 'lost';
                        }} else if (selection.includes('-')) {{
                            result = (homeGoals - line) > awayGoals ? 'won' : 'lost';
                        }}
                    }}

                    if (result) {{
                        // Get stake from input field
                        const stakeInput = document.getElementById(`stake-${{betKey}}`);
                        const stake = parseFloat(stakeInput?.value) || 10;
                        profit = result === 'won' ? (odds - 1) * stake : -stake;
                        profit = Math.round(profit * 100) / 100;

                        // Call setResult directly instead of simulating click
                        setResult(betKey, result, profit);
                        const btn = row.querySelector(`.result-btn.${{result === 'won' ? 'win' : 'loss'}}`);
                        if (btn) btn.classList.add('active');
                    }}
                }});

                card.querySelector('.match-header').classList.add('settled');
            }}

            function showToast(message) {{
                const toast = document.getElementById('toast');
                toast.textContent = message;
                toast.style.display = 'block';
                setTimeout(() => toast.style.display = 'none', 2000);
            }}

            // Auto-settle functionality
            let autoSettleEventSource = null;

            function runAutoSettle() {{
                const btn = document.querySelector('.auto-settle-btn');
                const spinner = document.getElementById('autoSettleSpinner');
                const btnText = document.getElementById('autoSettleBtnText');
                const progressDiv = document.getElementById('autoSettleProgress');
                const progressBar = document.getElementById('autoSettleProgressBar');
                const status = document.getElementById('autoSettleStatus');
                const log = document.getElementById('autoSettleLog');

                // Reset and show UI
                btn.disabled = true;
                spinner.style.display = 'block';
                btnText.textContent = 'Processing...';
                progressDiv.classList.add('show');
                progressBar.style.width = '0%';
                log.innerHTML = '';
                status.textContent = 'Connecting to Odds-API...';

                // Close existing connection
                if (autoSettleEventSource) autoSettleEventSource.close();

                autoSettleEventSource = new EventSource('/api/auto-settle/stream');

                autoSettleEventSource.onmessage = function(event) {{
                    const data = JSON.parse(event.data);

                    switch(data.type) {{
                        case 'init':
                            status.textContent = `Found ${{data.total_bets}} unsettled bets to process...`;
                            break;

                        case 'progress':
                            const pct = Math.round((data.current / data.total) * 100);
                            progressBar.style.width = pct + '%';
                            status.textContent = `Processing ${{data.current}}/${{data.total}}: ${{data.fixture}} (Settled: ${{data.settled}}, Skipped: ${{data.skipped}})`;
                            break;

                        case 'settled':
                            const profitStr = data.profit >= 0 ? '+' + data.profit.toFixed(1) : data.profit.toFixed(1);
                            log.innerHTML += `<div class="log-entry ${{data.result}}">✓ ${{data.fixture}} | ${{data.selection}} | Actual: ${{data.actual}} | ${{data.result.toUpperCase()}} ${{profitStr}} DKK</div>`;
                            log.scrollTop = log.scrollHeight;

                            // Update the row in the table if visible
                            const row = document.querySelector(`tr[data-key="${{data.bet_key}}"]`);
                            if (row) {{
                                row.classList.add('settled');
                                settledBets.add(data.bet_key);
                                totalProfit += data.profit;
                                updateProfitDisplay();
                            }}
                            break;

                        case 'skip':
                            log.innerHTML += `<div class="log-entry skip">⊘ Skipped: ${{data.reason}}</div>`;
                            log.scrollTop = log.scrollHeight;
                            break;

                        case 'complete':
                            autoSettleEventSource.close();
                            progressBar.style.width = '100%';
                            const summaryProfit = data.total_profit >= 0 ? '+' + data.total_profit.toFixed(1) : data.total_profit.toFixed(1);
                            status.textContent = `✅ Complete! Settled: ${{data.settled}} | Won: ${{data.won}} | Lost: ${{data.lost}} | Push: ${{data.push}} | P&L: ${{summaryProfit}} DKK`;

                            btn.disabled = false;
                            spinner.style.display = 'none';
                            btnText.textContent = '⚡ Auto-Settle All';

                            if (data.settled > 0) {{
                                showToast(`Auto-settled ${{data.settled}} bets!`);
                            }}
                            break;

                        case 'error':
                            autoSettleEventSource.close();
                            status.textContent = '❌ Error: ' + data.message;
                            btn.disabled = false;
                            spinner.style.display = 'none';
                            btnText.textContent = '⚡ Auto-Settle All';
                            break;
                    }}
                }};

                autoSettleEventSource.onerror = function(err) {{
                    console.error('SSE Error:', err);
                    autoSettleEventSource.close();
                    status.textContent = '❌ Connection lost. Try again.';
                    btn.disabled = false;
                    spinner.style.display = 'none';
                    btnText.textContent = '⚡ Auto-Settle All';
                }};
            }}
        </script>
    </body>
    </html>
    '''
    return HTMLResponse(content=html)


@app.post("/api/settle")
async def api_settle(request: Request):
    """API endpoint to settle a bet."""
    data = await request.json()
    bet_key = data.get("bet_key")
    result = data.get("result")  # won, lost, push
    profit = data.get("profit", 0)

    if not bet_key or not result:
        return {"error": "Missing bet_key or result"}

    # Update bet in Firebase
    update_data = {
        "result": result,
        "status": result,
        "profit": profit,
        "settled_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Try active_bets first (for pending/played bets)
            r = await client.get(f"{RTDB_URL}/active_bets/{bet_key}.json")
            if r.status_code == 200 and r.json():
                # Bet is in active_bets - update it there
                r = await client.patch(
                    f"{RTDB_URL}/active_bets/{bet_key}.json",
                    json=update_data
                )
                if r.status_code == 200:
                    return {"success": True, "bet_key": bet_key, "result": result, "profit": profit, "source": "active_bets"}
            else:
                # Try bet_history
                r = await client.patch(
                    f"{RTDB_URL}/bet_history/{bet_key}.json",
                    json=update_data
                )
                if r.status_code == 200:
                    return {"success": True, "bet_key": bet_key, "result": result, "profit": profit, "source": "bet_history"}
    except Exception as e:
        return {"error": str(e)}

    return {"error": "Failed to update Firebase"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "admin-dashboard"}


@app.get("/api/active")
async def api_active():
    """API endpoint for active bets."""
    return await fetch_firebase("active_bets") or {}


@app.get("/api/history")
async def api_history():
    """API endpoint for bet history."""
    return await fetch_firebase("bet_history") or {}


@app.get("/api/stats")
async def api_stats():
    """API endpoint for statistics."""
    history = await fetch_firebase("bet_history") or {}

    played = [b for b in history.values() if b.get("user_action") == "played"]
    won = [b for b in history.values() if b.get("result") == "won"]
    total_profit = sum(b.get("profit", 0) or 0 for b in history.values())

    return {
        "total_bets": len(history),
        "played": len(played),
        "won": len(won),
        "win_rate": (len(won) / len(played) * 100) if played else 0,
        "total_profit": total_profit,
        "roi": (total_profit / (len(played) * 10) * 100) if played else 0
    }


from fastapi.responses import StreamingResponse
import uuid

# Store for backtest jobs
backtest_jobs = {}


@app.get("/api/data-collection/stats")
async def data_collection_stats():
    """Get statistics about collected odds data for backtesting."""
    try:
        from src.odds_history import get_collector
        collector = get_collector()
        stats = collector.get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/data-collection", response_class=HTMLResponse)
async def data_collection_page(request: Request):
    """Page showing data collection status for backtesting."""

    # Try to get stats
    try:
        from src.odds_history import get_collector
        collector = get_collector()
        stats = collector.get_stats()
        enabled = True
    except Exception as e:
        stats = {"error": str(e)}
        enabled = False

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Data Collection | EV Bot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
            min-height: 100vh;
            color: #e2e8f0;
            padding: 20px;
        }}

        .container {{ max-width: 900px; margin: 0 auto; }}

        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}

        .header h1 {{ font-size: 28px; }}
        .header nav a {{
            color: #94a3b8;
            text-decoration: none;
            margin-left: 20px;
            transition: color 0.2s;
        }}
        .header nav a:hover {{ color: #22c55e; }}

        .status-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        .status-badge {{
            display: inline-block;
            padding: 6px 16px;
            border-radius: 20px;
            font-weight: 600;
            margin-bottom: 20px;
        }}
        .status-enabled {{ background: #22c55e; color: white; }}
        .status-disabled {{ background: #ef4444; color: white; }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}

        .stat-box {{
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }}
        .stat-box .value {{
            font-size: 36px;
            font-weight: 700;
            color: #22c55e;
            margin-bottom: 5px;
        }}
        .stat-box .label {{ color: #94a3b8; font-size: 14px; }}

        .info-section {{
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid rgba(34, 197, 94, 0.3);
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
        }}
        .info-section h3 {{ color: #22c55e; margin-bottom: 10px; }}
        .info-section p {{ color: #94a3b8; line-height: 1.6; }}

        .date-range {{
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 8px;
            padding: 15px;
            display: inline-block;
            margin-top: 10px;
        }}
        .date-range span {{ color: #60a5fa; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Data Collection</h1>
            <nav>
                <a href="/">Dashboard</a>
                <a href="/settle">Settle</a>
                <a href="/backtest">Backtest</a>
            </nav>
        </div>

        <div class="status-card">
            <div class="status-badge {'status-enabled' if enabled else 'status-disabled'}">
                {'ACTIVE' if enabled else 'DISABLED'}
            </div>

            <h2>Odds History Collection</h2>
            <p style="color: #94a3b8; margin-top: 10px;">
                The scanner automatically saves odds snapshots for every fixture it analyzes.
                This data will be used for future backtesting once enough history is collected.
            </p>

            {'<div class="stats-grid">' if enabled else ''}
            {'<div class="stat-box"><div class="value">' + str(stats.get("total_days", 0)) + '</div><div class="label">Days Collected</div></div>' if enabled else ''}
            {'<div class="stat-box"><div class="value">' + str(stats.get("total_snapshots", 0)) + '</div><div class="label">Odds Snapshots</div></div>' if enabled else ''}
            {'<div class="stat-box"><div class="value">' + str(stats.get("total_fixtures", 0)) + '</div><div class="label">Unique Fixtures</div></div>' if enabled else ''}
            {'<div class="stat-box"><div class="value">' + str(stats.get("total_value_bets_logged", 0)) + '</div><div class="label">Value Bets Found</div></div>' if enabled else ''}
            {'<div class="stat-box"><div class="value">' + str(stats.get("total_results_saved", 0)) + '</div><div class="label">Results Saved</div></div>' if enabled else ''}
            {'</div>' if enabled else ''}

            {('<div class="date-range">Data from <span>' + (stats.get("date_range", {}) or {}).get("start", "N/A") + '</span> to <span>' + (stats.get("date_range", {}) or {}).get("end", "N/A") + '</span></div>') if enabled and stats.get("date_range") else ''}
        </div>

        <div class="info-section">
            <h3>How It Works</h3>
            <p>
                Every time the scanner runs (every 5 minutes), it saves odds from all bookmakers
                for every fixture and market it analyzes. This includes:
            </p>
            <ul style="margin-top: 10px; margin-left: 20px; color: #94a3b8;">
                <li>Odds from 10 bookmakers (4 betting + 6 reference)</li>
                <li>All target markets (Shots, SOT, Corners, Asian Handicap)</li>
                <li>Value bets detected at each snapshot</li>
                <li>Match results when available</li>
            </ul>
            <p style="margin-top: 15px;">
                After collecting 1-3 months of data, you'll be able to run comprehensive
                backtests using real historical odds from your scanner.
            </p>
        </div>

        <div class="info-section" style="background: rgba(251, 191, 36, 0.1); border-color: rgba(251, 191, 36, 0.3);">
            <h3 style="color: #fbbf24;">Recommendation</h3>
            <p>
                Keep the scanner running consistently. The more data collected, the more
                statistically significant your backtest results will be. Aim for at least
                30 days of data before running a backtest.
            </p>
        </div>
    </div>

    <script>
        // Auto-refresh stats every 60 seconds
        setTimeout(() => location.reload(), 60000);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html)

@app.get("/backtest", response_class=HTMLResponse)
async def backtest_page(request: Request):
    """Backtesting page to analyze historical EV opportunities."""

    # Get available leagues from Odds-API
    leagues = [
        ("england_-_premier_league", "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League"),
        ("spain_-_la_liga", "🇪🇸 La Liga"),
        ("germany_-_bundesliga", "🇩🇪 Bundesliga"),
        ("italy_-_serie_a", "🇮🇹 Serie A"),
        ("france_-_ligue_1", "🇫🇷 Ligue 1"),
        ("uefa_-_champions_league", "🏆 Champions League"),
        ("uefa_-_europa_league", "🏆 Europa League"),
    ]

    league_options = "".join([
        f'<option value="{lid}">{name}</option>' for lid, name in leagues
    ])

    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Backtest - EV Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}

            /* Animated background */
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(-45deg, #0a0a0a, #1a1a2e, #0f0f1a, #0a1628);
                background-size: 400% 400%;
                animation: gradientBG 15s ease infinite;
                color: #fff;
                padding: 20px;
                max-width: 1400px;
                margin: 0 auto;
                min-height: 100vh;
            }}
            @keyframes gradientBG {{
                0% {{ background-position: 0% 50%; }}
                50% {{ background-position: 100% 50%; }}
                100% {{ background-position: 0% 50%; }}
            }}

            h1 {{
                text-align: center;
                margin-bottom: 10px;
                font-size: 32px;
                background: linear-gradient(135deg, #fff 0%, #60a5fa 50%, #4ade80 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                animation: titleGlow 3s ease-in-out infinite;
            }}
            @keyframes titleGlow {{
                0%, 100% {{ filter: brightness(1); }}
                50% {{ filter: brightness(1.2); }}
            }}

            .subtitle {{ text-align: center; color: #888; margin-bottom: 30px; }}
            .subtitle a {{
                color: #60a5fa;
                text-decoration: none;
                transition: all 0.3s ease;
            }}
            .subtitle a:hover {{
                color: #93c5fd;
                text-shadow: 0 0 10px rgba(96, 165, 250, 0.5);
            }}

            .form-card {{
                background: rgba(26, 26, 26, 0.8);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 16px;
                padding: 30px;
                margin-bottom: 30px;
                animation: slideUp 0.5s ease-out;
            }}
            @keyframes slideUp {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}

            .form-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 25px;
            }}
            .form-group {{
                display: flex;
                flex-direction: column;
                gap: 8px;
            }}
            .form-group label {{
                color: #94a3b8;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .form-group input, .form-group select {{
                background: rgba(37, 37, 37, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 14px;
                border-radius: 10px;
                color: #fff;
                font-size: 14px;
                transition: all 0.3s ease;
            }}
            .form-group input:focus, .form-group select:focus {{
                border-color: #2563eb;
                outline: none;
                box-shadow: 0 0 20px rgba(37, 99, 235, 0.3);
            }}

            .run-btn {{
                background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
                color: #fff;
                border: none;
                padding: 16px 50px;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 12px;
                margin: 0 auto;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4);
                position: relative;
                overflow: hidden;
            }}
            .run-btn::before {{
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
                transition: left 0.5s;
            }}
            .run-btn:hover::before {{ left: 100%; }}
            .run-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 25px rgba(37, 99, 235, 0.5);
            }}
            .run-btn:disabled {{
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }}
            .run-btn .spinner {{
                width: 20px;
                height: 20px;
                border: 2px solid #fff;
                border-top-color: transparent;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
                display: none;
            }}
            @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

            .results-card {{
                background: rgba(26, 26, 26, 0.8);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 16px;
                padding: 30px;
                display: none;
                animation: fadeIn 0.5s ease-out;
            }}
            .results-card.show {{ display: block; }}
            @keyframes fadeIn {{
                from {{ opacity: 0; }}
                to {{ opacity: 1; }}
            }}

            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 15px;
                margin-bottom: 25px;
            }}
            .stat {{
                background: linear-gradient(135deg, rgba(37, 37, 37, 0.9) 0%, rgba(30, 30, 40, 0.9) 100%);
                padding: 20px;
                border-radius: 12px;
                text-align: center;
                border: 1px solid rgba(255, 255, 255, 0.05);
                transition: all 0.3s ease;
                animation: statPop 0.5s ease-out backwards;
            }}
            .stat:nth-child(1) {{ animation-delay: 0.1s; }}
            .stat:nth-child(2) {{ animation-delay: 0.2s; }}
            .stat:nth-child(3) {{ animation-delay: 0.3s; }}
            .stat:nth-child(4) {{ animation-delay: 0.4s; }}
            .stat:nth-child(5) {{ animation-delay: 0.5s; }}
            .stat:nth-child(6) {{ animation-delay: 0.6s; }}
            @keyframes statPop {{
                from {{ opacity: 0; transform: scale(0.8); }}
                to {{ opacity: 1; transform: scale(1); }}
            }}
            .stat:hover {{
                transform: translateY(-5px);
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            }}
            .stat-value {{
                font-size: 32px;
                font-weight: bold;
                background: linear-gradient(135deg, #fff 0%, #94a3b8 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            .stat-value.positive {{
                background: linear-gradient(135deg, #4ade80 0%, #22c55e 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                text-shadow: 0 0 30px rgba(74, 222, 128, 0.3);
            }}
            .stat-value.negative {{
                background: linear-gradient(135deg, #f87171 0%, #ef4444 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            .stat-label {{
                color: #64748b;
                font-size: 11px;
                margin-top: 8px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}

            .bets-table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 14px;
            }}
            .bets-table th {{
                background: rgba(37, 37, 37, 0.8);
                padding: 14px;
                text-align: left;
                font-weight: 500;
                color: #64748b;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .bets-table td {{
                padding: 14px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }}
            .bets-table tr {{
                transition: all 0.2s ease;
                animation: rowSlide 0.3s ease-out backwards;
            }}
            @keyframes rowSlide {{
                from {{ opacity: 0; transform: translateX(-10px); }}
                to {{ opacity: 1; transform: translateX(0); }}
            }}
            .bets-table tbody tr:hover {{
                background: rgba(37, 99, 235, 0.1);
                transform: scale(1.01);
            }}

            .badge {{
                display: inline-block;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .badge.win {{
                background: linear-gradient(135deg, #166534 0%, #15803d 100%);
                color: #4ade80;
                box-shadow: 0 0 15px rgba(74, 222, 128, 0.3);
            }}
            .badge.loss {{
                background: linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%);
                color: #f87171;
            }}
            .badge.push {{
                background: linear-gradient(135deg, #374151 0%, #4b5563 100%);
                color: #9ca3af;
            }}
            .badge.pending {{
                background: linear-gradient(135deg, #1e3a5f 0%, #1e40af 100%);
                color: #60a5fa;
            }}

            .edge {{
                font-weight: 600;
                color: #4ade80;
                text-shadow: 0 0 10px rgba(74, 222, 128, 0.3);
            }}

            .progress-bar {{
                background: rgba(37, 37, 37, 0.8);
                border-radius: 12px;
                height: 16px;
                overflow: hidden;
                margin-bottom: 15px;
                position: relative;
                box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.3);
            }}
            .progress-fill {{
                background: linear-gradient(90deg, #2563eb, #7c3aed, #4ade80, #2563eb);
                background-size: 300% 100%;
                height: 100%;
                width: 0%;
                transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
                animation: shimmer 2s linear infinite;
                box-shadow: 0 0 20px rgba(37, 99, 235, 0.5);
            }}
            @keyframes shimmer {{
                0% {{ background-position: 300% 0; }}
                100% {{ background-position: -300% 0; }}
            }}
            .progress-bar .progress-text {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-size: 11px;
                font-weight: bold;
                color: #fff;
                text-shadow: 0 1px 3px rgba(0,0,0,0.8);
                z-index: 1;
            }}

            .status-text {{
                text-align: center;
                color: #94a3b8;
                margin-bottom: 20px;
                min-height: 24px;
                font-size: 14px;
                transition: all 0.3s ease;
            }}

            .live-stats {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 12px;
                margin-bottom: 20px;
                padding: 20px;
                background: linear-gradient(135deg, rgba(37, 37, 37, 0.9) 0%, rgba(20, 20, 30, 0.9) 100%);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.05);
                animation: fadeIn 0.5s ease-out;
            }}
            .live-stat {{
                text-align: center;
                padding: 10px;
                border-radius: 8px;
                background: rgba(0, 0, 0, 0.2);
                transition: all 0.3s ease;
            }}
            .live-stat:hover {{
                transform: scale(1.05);
                background: rgba(37, 99, 235, 0.1);
            }}
            .live-stat-value {{
                font-size: 24px;
                font-weight: bold;
                color: #4ade80;
                animation: countUp 0.3s ease-out;
            }}
            @keyframes countUp {{
                from {{ transform: scale(1.2); opacity: 0.5; }}
                to {{ transform: scale(1); opacity: 1; }}
            }}
            .live-stat-value.loss {{ color: #f87171; }}
            .live-stat-label {{
                font-size: 10px;
                color: #64748b;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-top: 4px;
            }}

            .fixture-ticker {{
                background: linear-gradient(135deg, rgba(30, 58, 95, 0.5) 0%, rgba(30, 41, 59, 0.5) 100%);
                border: 1px solid rgba(96, 165, 250, 0.3);
                border-radius: 12px;
                padding: 14px 20px;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 12px;
                overflow: hidden;
                animation: slideIn 0.3s ease-out;
            }}
            @keyframes slideIn {{
                from {{ opacity: 0; transform: translateX(-20px); }}
                to {{ opacity: 1; transform: translateX(0); }}
            }}
            .ticker-icon {{
                font-size: 24px;
                animation: bounce 1s ease-in-out infinite;
            }}
            @keyframes bounce {{
                0%, 100% {{ transform: translateY(0); }}
                50% {{ transform: translateY(-5px); }}
            }}
            .ticker-text {{
                flex: 1;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                color: #94a3b8;
                font-size: 14px;
            }}
            .ticker-text strong {{
                color: #fff;
                text-shadow: 0 0 10px rgba(255, 255, 255, 0.3);
            }}

            .warning-box {{
                background: linear-gradient(135deg, rgba(66, 32, 6, 0.9) 0%, rgba(55, 28, 8, 0.9) 100%);
                border: 1px solid rgba(249, 115, 22, 0.5);
                border-radius: 12px;
                padding: 18px;
                margin-bottom: 20px;
                display: flex;
                align-items: flex-start;
                gap: 14px;
                animation: pulseGlow 2s ease-in-out infinite;
            }}
            @keyframes pulseGlow {{
                0%, 100% {{ box-shadow: 0 0 5px rgba(249, 115, 22, 0.3); }}
                50% {{ box-shadow: 0 0 20px rgba(249, 115, 22, 0.5); }}
            }}
            .warning-box .icon {{
                font-size: 24px;
                animation: shake 0.5s ease-in-out infinite;
            }}
            @keyframes shake {{
                0%, 100% {{ transform: rotate(0deg); }}
                25% {{ transform: rotate(-5deg); }}
                75% {{ transform: rotate(5deg); }}
            }}
            .warning-box .text {{ color: #fed7aa; font-size: 14px; line-height: 1.5; }}
            .warning-box .text strong {{ color: #fff; }}

            .filter-row {{
                display: flex;
                gap: 12px;
                margin-bottom: 20px;
                flex-wrap: wrap;
                animation: fadeIn 0.5s ease-out;
            }}
            .filter-btn {{
                background: rgba(37, 37, 37, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #94a3b8;
                padding: 10px 20px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 13px;
                font-weight: 500;
                transition: all 0.3s ease;
            }}
            .filter-btn:hover {{
                background: rgba(37, 99, 235, 0.2);
                border-color: rgba(37, 99, 235, 0.5);
                color: #fff;
                transform: translateY(-2px);
            }}
            .filter-btn.active {{
                background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
                border-color: transparent;
                color: #fff;
                box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4);
            }}

            /* Confetti animation for wins */
            .confetti {{
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 9999;
            }}

            /* Scrollbar styling */
            ::-webkit-scrollbar {{
                width: 8px;
                height: 8px;
            }}
            ::-webkit-scrollbar-track {{
                background: rgba(0, 0, 0, 0.3);
                border-radius: 4px;
            }}
            ::-webkit-scrollbar-thumb {{
                background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
                border-radius: 4px;
            }}
            ::-webkit-scrollbar-thumb:hover {{
                background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
            }}
        </style>
    </head>
    <body>
        <h1>📊 Backtest EV Strategy</h1>
        <p class="subtitle"><a href="/">← Back to Dashboard</a></p>

        <div class="form-card">
            <div class="form-grid">
                <div class="form-group">
                    <label>Start Date</label>
                    <input type="date" id="startDate" value="">
                </div>
                <div class="form-group">
                    <label>End Date</label>
                    <input type="date" id="endDate" value="">
                </div>
                <div class="form-group">
                    <label>League</label>
                    <select id="league">
                        {league_options}
                    </select>
                </div>
                <div class="form-group">
                    <label>Min Edge %</label>
                    <input type="number" id="minEdge" value="5" min="1" max="50" step="0.5">
                </div>
                <div class="form-group">
                    <label>Min Odds</label>
                    <input type="number" id="minOdds" value="1.50" min="1.01" max="10" step="0.05">
                </div>
                <div class="form-group">
                    <label>Max Odds</label>
                    <input type="number" id="maxOdds" value="5.00" min="1.5" max="20" step="0.1">
                </div>
            </div>
            <button class="run-btn" onclick="runBacktest()">
                <span class="spinner"></span>
                <span class="btn-text">🚀 Run Backtest</span>
            </button>
        </div>

        <div class="results-card" id="results">
            <div class="warning-box" id="warningBox" style="display:none;">
                <span class="icon">⚠️</span>
                <div class="text">
                    <strong>Large backtest running</strong><br>
                    Processing up to 100 fixtures. This may take 2-5 minutes.
                    Do not close this tab. Progress is saved as we go.
                </div>
            </div>

            <div class="progress-bar">
                <div class="progress-fill" id="progress"></div>
                <span class="progress-text" id="progressText">0%</span>
            </div>
            <p class="status-text" id="status">Ready to run backtest...</p>

            <div class="fixture-ticker" id="ticker" style="display:none;">
                <span class="ticker-icon">⚽</span>
                <span class="ticker-text" id="tickerText">Analyzing fixture...</span>
            </div>

            <div class="live-stats" id="liveStats" style="display:none;">
                <div class="live-stat">
                    <div class="live-stat-value" id="liveFixtures">0</div>
                    <div class="live-stat-label">Fixtures</div>
                </div>
                <div class="live-stat">
                    <div class="live-stat-value" id="liveBets">0</div>
                    <div class="live-stat-label">Bets Found</div>
                </div>
                <div class="live-stat">
                    <div class="live-stat-value" id="liveWins">0</div>
                    <div class="live-stat-label">Wins</div>
                </div>
                <div class="live-stat">
                    <div class="live-stat-value loss" id="liveLosses">0</div>
                    <div class="live-stat-label">Losses</div>
                </div>
            </div>

            <div class="stats-grid" id="statsGrid" style="display:none;">
                <div class="stat">
                    <div class="stat-value" id="totalBets">0</div>
                    <div class="stat-label">Total Bets</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="winRate">0%</div>
                    <div class="stat-label">Win Rate</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="avgEdge">0%</div>
                    <div class="stat-label">Avg Edge</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="avgOdds">0</div>
                    <div class="stat-label">Avg Odds</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="totalProfit">0</div>
                    <div class="stat-label">Profit (DKK)</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="roi">0%</div>
                    <div class="stat-label">ROI</div>
                </div>
            </div>

            <div class="filter-row" id="filterRow" style="display:none;">
                <button class="filter-btn active" onclick="filterBets('all')">All</button>
                <button class="filter-btn" onclick="filterBets('won')">Wins</button>
                <button class="filter-btn" onclick="filterBets('lost')">Losses</button>
                <button class="filter-btn" onclick="filterBets('push')">Push</button>
            </div>

            <table class="bets-table" id="betsTable" style="display:none;">
                <thead>
                    <tr>
                        <th>Match</th>
                        <th>Market</th>
                        <th>Selection</th>
                        <th>Book</th>
                        <th>Odds</th>
                        <th>Edge</th>
                        <th>Result</th>
                        <th>Actual</th>
                        <th>P&L</th>
                    </tr>
                </thead>
                <tbody id="betsBody"></tbody>
            </table>
        </div>

        <script>
            // Set default dates (last 30 days for more data)
            const today = new Date();
            const monthAgo = new Date(today - 30 * 24 * 60 * 60 * 1000);
            document.getElementById('endDate').value = today.toISOString().split('T')[0];
            document.getElementById('startDate').value = monthAgo.toISOString().split('T')[0];

            let allBets = [];
            let eventSource = null;

            function resetUI() {{
                document.getElementById('warningBox').style.display = 'none';
                document.getElementById('ticker').style.display = 'none';
                document.getElementById('liveStats').style.display = 'none';
                document.getElementById('statsGrid').style.display = 'none';
                document.getElementById('filterRow').style.display = 'none';
                document.getElementById('betsTable').style.display = 'none';
                document.getElementById('progress').style.width = '0%';
                document.getElementById('progressText').textContent = '0%';
                document.getElementById('liveFixtures').textContent = '0';
                document.getElementById('liveBets').textContent = '0';
                document.getElementById('liveWins').textContent = '0';
                document.getElementById('liveLosses').textContent = '0';
                allBets = [];
            }}

            async function runBacktest() {{
                const btn = document.querySelector('.run-btn');
                const spinner = btn.querySelector('.spinner');
                const btnText = btn.querySelector('.btn-text');
                const results = document.getElementById('results');

                // Reset and show UI
                resetUI();
                btn.disabled = true;
                spinner.style.display = 'block';
                btnText.textContent = 'Running...';
                results.classList.add('show');

                // Get form values
                const params = new URLSearchParams({{
                    start_date: document.getElementById('startDate').value,
                    end_date: document.getElementById('endDate').value,
                    league: document.getElementById('league').value,
                    min_edge: document.getElementById('minEdge').value,
                    min_odds: document.getElementById('minOdds').value,
                    max_odds: document.getElementById('maxOdds').value
                }});

                document.getElementById('status').textContent = 'Connecting to backtest server...';

                // Use SSE for streaming progress
                if (eventSource) eventSource.close();

                eventSource = new EventSource(`/api/backtest/stream?${{params}}`);

                eventSource.onmessage = function(event) {{
                    const data = JSON.parse(event.data);
                    handleBacktestUpdate(data);
                }};

                eventSource.onerror = function(err) {{
                    console.error('SSE Error:', err);
                    eventSource.close();
                    btn.disabled = false;
                    spinner.style.display = 'none';
                    btnText.textContent = '🚀 Run Backtest';

                    const status = document.getElementById('status');
                    if (!status.textContent.includes('✅')) {{
                        status.textContent = '❌ Connection lost. Try again.';
                    }}
                }};
            }}

            function handleBacktestUpdate(data) {{
                const progress = document.getElementById('progress');
                const progressText = document.getElementById('progressText');
                const status = document.getElementById('status');

                switch(data.type) {{
                    case 'init':
                        // Show warning for large backtests
                        if (data.total_fixtures > 20) {{
                            document.getElementById('warningBox').style.display = 'flex';
                        }}
                        document.getElementById('ticker').style.display = 'flex';
                        document.getElementById('liveStats').style.display = 'grid';
                        status.textContent = `Found ${{data.total_fixtures}} fixtures to analyze...`;
                        break;

                    case 'progress':
                        const pct = Math.round((data.current / data.total) * 100);
                        progress.style.width = pct + '%';
                        progressText.textContent = pct + '%';
                        document.getElementById('tickerText').innerHTML = `Analyzing: <strong>${{data.fixture_name}}</strong>`;
                        document.getElementById('liveFixtures').textContent = data.current;
                        document.getElementById('liveBets').textContent = data.bets_found;
                        document.getElementById('liveWins').textContent = data.wins;
                        document.getElementById('liveLosses').textContent = data.losses;
                        status.textContent = `Processing fixture ${{data.current}} of ${{data.total}}...`;
                        break;

                    case 'bet':
                        // Add bet to list in real-time
                        allBets.push(data.bet);
                        break;

                    case 'complete':
                        eventSource.close();
                        progress.style.width = '100%';
                        progressText.textContent = '100%';
                        document.getElementById('warningBox').style.display = 'none';
                        document.getElementById('ticker').style.display = 'none';

                        status.textContent = `✅ Complete! Found ${{data.total_bets}} value bets across ${{data.fixtures_analyzed}} fixtures`;

                        // Update final stats
                        document.getElementById('totalBets').textContent = data.total_bets;
                        document.getElementById('winRate').textContent = data.win_rate.toFixed(1) + '%';
                        document.getElementById('avgEdge').textContent = data.avg_edge.toFixed(1) + '%';
                        document.getElementById('avgOdds').textContent = data.avg_odds.toFixed(2);

                        const profitEl = document.getElementById('totalProfit');
                        profitEl.textContent = (data.total_profit >= 0 ? '+' : '') + data.total_profit.toFixed(0) + ' DKK';
                        profitEl.className = 'stat-value ' + (data.total_profit >= 0 ? 'positive' : 'negative');

                        const roiEl = document.getElementById('roi');
                        roiEl.textContent = (data.roi >= 0 ? '+' : '') + data.roi.toFixed(1) + '%';
                        roiEl.className = 'stat-value ' + (data.roi >= 0 ? 'positive' : 'negative');

                        allBets = data.bets || allBets;
                        renderBets(allBets);

                        document.getElementById('liveStats').style.display = 'none';
                        document.getElementById('statsGrid').style.display = 'grid';
                        document.getElementById('filterRow').style.display = 'flex';
                        document.getElementById('betsTable').style.display = 'table';

                        // Reset button
                        const btn = document.querySelector('.run-btn');
                        btn.disabled = false;
                        btn.querySelector('.spinner').style.display = 'none';
                        btn.querySelector('.btn-text').textContent = '🚀 Run Backtest';
                        break;

                    case 'error':
                        eventSource.close();
                        status.textContent = '❌ Error: ' + data.message;
                        const errBtn = document.querySelector('.run-btn');
                        errBtn.disabled = false;
                        errBtn.querySelector('.spinner').style.display = 'none';
                        errBtn.querySelector('.btn-text').textContent = '🚀 Run Backtest';
                        break;
                }}
            }}

            function renderBets(bets) {{
                const tbody = document.getElementById('betsBody');
                tbody.innerHTML = '';

                bets.forEach(bet => {{
                    const resultClass = bet.won === true ? 'win' : bet.won === false ? 'loss' : 'push';
                    const resultText = bet.won === true ? 'WIN' : bet.won === false ? 'LOSS' : 'PUSH';
                    const profitText = bet.profit !== null ? (bet.profit >= 0 ? '+' : '') + bet.profit.toFixed(1) : '-';
                    const profitColor = bet.profit > 0 ? '#4ade80' : bet.profit < 0 ? '#f87171' : '#888';

                    tbody.innerHTML += `
                        <tr data-result="${{resultClass}}">
                            <td>${{bet.fixture_name || 'N/A'}}</td>
                            <td>${{bet.market || 'N/A'}}</td>
                            <td>${{bet.selection || 'N/A'}}</td>
                            <td>${{bet.book_name || 'N/A'}}</td>
                            <td>${{bet.book_odds?.toFixed(2) || 'N/A'}}</td>
                            <td class="edge">${{bet.edge_percent?.toFixed(1) || 0}}%</td>
                            <td><span class="badge ${{resultClass}}">${{resultText}}</span></td>
                            <td>${{bet.actual_result !== null ? bet.actual_result : '-'}}</td>
                            <td style="color:${{profitColor}};font-weight:bold;">${{profitText}}</td>
                        </tr>
                    `;
                }});
            }}

            function filterBets(filter) {{
                // Update active button
                document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
                event.target.classList.add('active');

                // Filter bets
                let filtered = allBets;
                if (filter === 'won') filtered = allBets.filter(b => b.won === true);
                else if (filter === 'lost') filtered = allBets.filter(b => b.won === false);
                else if (filter === 'push') filtered = allBets.filter(b => b.won === null && b.profit === 0);

                renderBets(filtered);
            }}
        </script>
    </body>
    </html>
    '''
    return HTMLResponse(content=html)


@app.get("/api/backtest/stream")
async def api_backtest_stream(
    start_date: str,
    end_date: str,
    league: str = "england_-_premier_league",
    min_edge: float = 5.0,
    min_odds: float = 1.5,
    max_odds: float = 5.0
):
    """Run backtest with SSE streaming for progress updates."""
    import sys
    import os

    # Add src to path for imports
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

    async def generate():
        try:
            from src.api import OddsApiClient
            from src.backtesting.backtest import Backtester
        except ImportError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Import error: {e}'})}\n\n"
            return

        api_key = os.environ.get("ODDSAPI_API_KEY", "")
        if not api_key:
            yield f"data: {json.dumps({'type': 'error', 'message': 'ODDSAPI_API_KEY not configured'})}\n\n"
            return

        client = None
        try:
            client = OddsApiClient(api_key, timeout=120.0)

            # Fetch completed fixtures in date range
            response = await client._request('GET', '/fixtures', params={
                'sport': 'soccer',
                'league': league,
                'status': 'completed',
                'start_date': start_date,
                'end_date': end_date
            })

            fixtures = response.get('data', [])

            if not fixtures:
                yield f"data: {json.dumps({'type': 'error', 'message': f'No completed fixtures found for {league} between {start_date} and {end_date}'})}\n\n"
                return

            # Limit to 100 fixtures max
            fixtures = fixtures[:100]
            total_fixtures = len(fixtures)

            # Send init message
            yield f"data: {json.dumps({'type': 'init', 'total_fixtures': total_fixtures})}\n\n"

            # Risk management stake function
            def calc_stake(odds):
                if odds <= 2.00: return 10.0
                elif odds <= 2.75: return 7.5
                elif odds <= 4.00: return 5.0
                elif odds <= 7.00: return 2.5
                else: return 1.0

            backtester = Backtester(client)
            all_bets = []
            wins = 0
            losses = 0
            pushes = 0
            total_staked = 0
            total_profit = 0

            # Process fixtures one by one
            for i, fixture in enumerate(fixtures):
                fixture_id = fixture.get('id')
                fixture_name = f"{fixture.get('home_team_display', 'Home')} vs {fixture.get('away_team_display', 'Away')}"

                # Send progress update
                yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': total_fixtures, 'fixture_name': fixture_name, 'bets_found': len(all_bets), 'wins': wins, 'losses': losses})}\n\n"

                # Process this fixture
                try:
                    results = await backtester.run_backtest(
                        fixtures=[fixture],
                        min_edge=min_edge,
                        min_odds=min_odds,
                        max_odds=max_odds,
                        stake=10.0
                    )

                    # Process bets from this fixture
                    for bet in results.bets:
                        stake = calc_stake(bet.book_odds)
                        if bet.won is True:
                            bet.profit = (bet.book_odds - 1) * stake
                            wins += 1
                        elif bet.won is False:
                            bet.profit = -stake
                            losses += 1
                        else:
                            bet.profit = 0
                            pushes += 1
                        total_staked += stake
                        total_profit += bet.profit or 0

                        bet_dict = {
                            "fixture_id": bet.fixture_id,
                            "fixture_name": bet.fixture_name,
                            "market": bet.market,
                            "selection": bet.selection,
                            "line": bet.line,
                            "book_odds": bet.book_odds,
                            "book_name": bet.book_name,
                            "fair_odds": bet.fair_odds,
                            "edge_percent": bet.edge_percent,
                            "actual_result": bet.actual_result,
                            "won": bet.won,
                            "profit": bet.profit
                        }
                        all_bets.append(bet_dict)

                        # Send bet found
                        yield f"data: {json.dumps({'type': 'bet', 'bet': bet_dict})}\n\n"

                except Exception as fixture_error:
                    # Log but continue with other fixtures
                    print(f"[BACKTEST] Error on fixture {fixture_id}: {fixture_error}")
                    continue

                # Small delay to prevent overwhelming the API
                await asyncio.sleep(0.1)

            # Calculate final stats
            settled_bets = [b for b in all_bets if b['won'] is not None]
            avg_edge = sum(b['edge_percent'] for b in all_bets) / len(all_bets) if all_bets else 0
            avg_odds = sum(b['book_odds'] for b in all_bets) / len(all_bets) if all_bets else 0
            win_rate = (wins / len(settled_bets) * 100) if settled_bets else 0
            roi = (total_profit / total_staked * 100) if total_staked > 0 else 0

            # Send complete message
            yield f"data: {json.dumps({'type': 'complete', 'total_bets': len(all_bets), 'wins': wins, 'losses': losses, 'pushes': pushes, 'total_staked': total_staked, 'total_profit': total_profit, 'roi': roi, 'win_rate': win_rate, 'avg_edge': avg_edge, 'avg_odds': avg_odds, 'bets': all_bets, 'fixtures_analyzed': total_fixtures})}\n\n"

        except Exception as e:
            import traceback
            yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'trace': traceback.format_exc()})}\n\n"
        finally:
            if client:
                await client.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/auto-settle/stream")
async def api_auto_settle_stream():
    """Auto-settle bets using Odds-API match results with SSE streaming."""
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

    async def generate():
        try:
            from src.api import OddsApiClient
        except ImportError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Import error: {e}'})}\n\n"
            return

        api_key = os.environ.get("ODDSAPI_API_KEY", "")
        if not api_key:
            yield f"data: {json.dumps({'type': 'error', 'message': 'ODDSAPI_API_KEY not configured'})}\n\n"
            return

        # Fetch unsettled bets from Firebase
        bet_history = await fetch_firebase("bet_history") or {}

        unsettled = []
        for key, bet in bet_history.items():
            if bet.get("user_action") == "played" and not bet.get("result"):
                unsettled.append((key, bet))

        if not unsettled:
            yield f"data: {json.dumps({'type': 'complete', 'message': 'No unsettled bets found', 'settled': 0})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'init', 'total_bets': len(unsettled)})}\n\n"

        client = None
        try:
            client = OddsApiClient(api_key, timeout=60.0)

            # Risk management stake function
            def calc_stake(odds):
                if odds <= 2.00: return 10.0
                elif odds <= 2.75: return 7.5
                elif odds <= 4.00: return 5.0
                elif odds <= 7.00: return 2.5
                else: return 1.0

            settled_count = 0
            skipped_count = 0
            results_summary = {"won": 0, "lost": 0, "push": 0}
            total_profit = 0

            for i, (bet_key, bet) in enumerate(unsettled):
                fixture_id = bet.get("fixture_id")
                fixture_name = bet.get("fixture", "Unknown")
                market = bet.get("market", "")
                selection = bet.get("selection", "")
                odds = bet.get("odds", 2.0)
                stake = bet.get("stake", calc_stake(odds))

                yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': len(unsettled), 'fixture': fixture_name, 'settled': settled_count, 'skipped': skipped_count})}\n\n"

                if not fixture_id:
                    skipped_count += 1
                    yield f"data: {json.dumps({'type': 'skip', 'bet_key': bet_key, 'reason': 'No fixture_id stored'})}\n\n"
                    continue

                try:
                    # Fetch match results from Odds-API
                    response = await client._request('GET', '/fixtures/results', params={
                        'fixture_id': fixture_id
                    })

                    if not response or not response.get('data'):
                        skipped_count += 1
                        yield f"data: {json.dumps({'type': 'skip', 'bet_key': bet_key, 'reason': 'No results available yet'})}\n\n"
                        continue

                    data = response['data'][0]
                    stats = data.get('stats', {})

                    # Extract home and away stats
                    home_stats = {}
                    away_stats = {}

                    for entry in stats.get('home', []):
                        if entry.get('period') == 'all':
                            home_stats = entry.get('stats', {})
                            break

                    for entry in stats.get('away', []):
                        if entry.get('period') == 'all':
                            away_stats = entry.get('stats', {})
                            break

                    # Determine actual stat value based on market
                    actual_value = None
                    market_lower = market.lower()

                    if 'shots on target' in market_lower or 'sot' in market_lower:
                        home = home_stats.get('ontarget_scoring_att', 0) or 0
                        away = away_stats.get('ontarget_scoring_att', 0) or 0
                        actual_value = home + away

                    elif 'shot' in market_lower:
                        home = home_stats.get('total_scoring_att', 0) or 0
                        away = away_stats.get('total_scoring_att', 0) or 0
                        actual_value = home + away

                    elif 'corner' in market_lower:
                        home = home_stats.get('won_corners', 0) or 0
                        away = away_stats.get('won_corners', 0) or 0
                        actual_value = home + away

                    elif 'card' in market_lower:
                        home = home_stats.get('total_yellow_card', 0) or 0
                        away = away_stats.get('total_yellow_card', 0) or 0
                        actual_value = home + away

                    elif 'goal' in market_lower or 'handicap' in market_lower:
                        home = home_stats.get('goals', 0) or 0
                        away = away_stats.get('goals', 0) or 0
                        actual_value = home + away

                    if actual_value is None:
                        skipped_count += 1
                        yield f"data: {json.dumps({'type': 'skip', 'bet_key': bet_key, 'reason': f'Unknown market type: {market}'})}\n\n"
                        continue

                    # Extract line from selection (e.g., "Over 24.5" -> 24.5)
                    import re
                    line_match = re.search(r'[\d.]+', selection)
                    if not line_match:
                        skipped_count += 1
                        yield f"data: {json.dumps({'type': 'skip', 'bet_key': bet_key, 'reason': f'Could not parse line from: {selection}'})}\n\n"
                        continue

                    line = float(line_match.group())
                    selection_lower = selection.lower()

                    # Determine result
                    result = None
                    profit = 0

                    if 'over' in selection_lower:
                        if actual_value > line:
                            result = 'won'
                            profit = (odds - 1) * stake
                        elif actual_value < line:
                            result = 'lost'
                            profit = -stake
                        else:
                            result = 'push'
                            profit = 0

                    elif 'under' in selection_lower:
                        if actual_value < line:
                            result = 'won'
                            profit = (odds - 1) * stake
                        elif actual_value > line:
                            result = 'lost'
                            profit = -stake
                        else:
                            result = 'push'
                            profit = 0

                    if result is None:
                        skipped_count += 1
                        yield f"data: {json.dumps({'type': 'skip', 'bet_key': bet_key, 'reason': f'Could not determine over/under from: {selection}'})}\n\n"
                        continue

                    # Update Firebase
                    profit = round(profit, 2)
                    update_data = {
                        "result": result,
                        "status": result,
                        "profit": profit,
                        "actual_value": actual_value,
                        "settled_at": datetime.now(timezone.utc).isoformat(),
                        "auto_settled": True
                    }

                    async with httpx.AsyncClient(timeout=30) as http_client:
                        r = await http_client.patch(
                            f"{RTDB_URL}/bet_history/{bet_key}.json",
                            json=update_data
                        )
                        if r.status_code == 200:
                            settled_count += 1
                            results_summary[result] += 1
                            total_profit += profit

                            yield f"data: {json.dumps({'type': 'settled', 'bet_key': bet_key, 'fixture': fixture_name, 'selection': selection, 'line': line, 'actual': actual_value, 'result': result, 'profit': profit})}\n\n"
                        else:
                            skipped_count += 1
                            yield f"data: {json.dumps({'type': 'skip', 'bet_key': bet_key, 'reason': 'Failed to update Firebase'})}\n\n"

                except Exception as bet_error:
                    skipped_count += 1
                    yield f"data: {json.dumps({'type': 'skip', 'bet_key': bet_key, 'reason': str(bet_error)})}\n\n"

                await asyncio.sleep(0.2)  # Rate limiting

            # Send completion
            yield f"data: {json.dumps({'type': 'complete', 'settled': settled_count, 'skipped': skipped_count, 'won': results_summary['won'], 'lost': results_summary['lost'], 'push': results_summary['push'], 'total_profit': round(total_profit, 2)})}\n\n"

        except Exception as e:
            import traceback
            yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'trace': traceback.format_exc()})}\n\n"
        finally:
            if client:
                await client.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


# Backtest Live Results Path
BACKTEST_RESULTS_FILE = os.path.join(os.path.dirname(__file__), "backtest_live_results.json")


@app.get("/backtest-live", response_class=HTMLResponse)
async def backtest_live_page(request: Request):
    """Live backtest results page - reads from JSON file updated by run_live_backtest.py."""

    # Load results from JSON file
    results = None
    if os.path.exists(BACKTEST_RESULTS_FILE):
        try:
            with open(BACKTEST_RESULTS_FILE, 'r', encoding='utf-8') as f:
                results = json.load(f)
        except:
            pass

    if not results:
        results = {
            "status": "not_started",
            "summary": {"total_bets": 0, "wins": 0, "losses": 0, "push": 0, "total_profit": 0, "roi": 0},
            "progress": {"leagues_done": 0, "leagues_total": 9, "fixtures_processed": 0, "current_league": ""},
            "by_league": {},
            "by_market": {},
            "by_book": {},
            "recent_bets": [],
            "config": {}
        }

    status = results.get("status", "unknown")
    summary = results.get("summary", {})
    progress = results.get("progress", {})
    config = results.get("config", {})
    by_league = results.get("by_league", {})
    by_market = results.get("by_market", {})
    by_book = results.get("by_book", {})
    recent_bets = results.get("recent_bets", [])

    # Status badge
    status_colors = {"running": "#f59e0b", "completed": "#22c55e", "not_started": "#6b7280", "error": "#ef4444"}
    status_color = status_colors.get(status, "#6b7280")
    status_badge = f'<span style="background:{status_color};color:white;padding:5px 15px;border-radius:20px;font-weight:500;">{status.upper()}</span>'

    # Progress bar
    leagues_done = progress.get("leagues_done", 0)
    leagues_total = progress.get("leagues_total", 9)
    progress_pct = (leagues_done / leagues_total * 100) if leagues_total > 0 else 0
    current_league = progress.get("current_league", "")

    # Summary stats
    total_bets = summary.get("total_bets", 0)
    wins = summary.get("wins", 0)
    losses = summary.get("losses", 0)
    push = summary.get("push", 0)
    total_profit = summary.get("total_profit", 0)
    roi = summary.get("roi", 0)
    win_rate = summary.get("win_rate", 0)
    avg_edge = summary.get("avg_edge", 0)
    avg_odds = summary.get("avg_odds", 0)
    total_staked = summary.get("total_staked", 0)

    profit_class = "positive" if total_profit >= 0 else "negative"
    roi_class = "positive" if roi >= 0 else "negative"

    # League breakdown table
    league_rows = ""
    for league_name, stats in sorted(by_league.items(), key=lambda x: x[1].get("profit", 0), reverse=True):
        l_bets = stats.get("bets", 0)
        l_wins = stats.get("wins", 0)
        l_losses = stats.get("losses", 0)
        l_profit = stats.get("profit", 0)
        l_staked = stats.get("staked", 0)
        l_roi = (l_profit / l_staked * 100) if l_staked > 0 else 0
        l_wr = (l_wins / (l_wins + l_losses) * 100) if (l_wins + l_losses) > 0 else 0
        l_profit_class = "positive" if l_profit >= 0 else "negative"
        league_rows += f'''
        <tr>
            <td>{league_name}</td>
            <td>{l_bets}</td>
            <td>{l_wins}W / {l_losses}L</td>
            <td>{l_wr:.1f}%</td>
            <td class="{l_profit_class}">{l_profit:+.2f}</td>
            <td class="{l_profit_class}">{l_roi:+.1f}%</td>
        </tr>
        '''

    # Market breakdown table
    market_rows = ""
    for market_name, stats in sorted(by_market.items(), key=lambda x: x[1].get("profit", 0), reverse=True):
        m_bets = stats.get("bets", 0)
        m_wins = stats.get("wins", 0)
        m_losses = stats.get("losses", 0)
        m_profit = stats.get("profit", 0)
        m_staked = stats.get("staked", 0)
        m_roi = (m_profit / m_staked * 100) if m_staked > 0 else 0
        m_wr = (m_wins / (m_wins + m_losses) * 100) if (m_wins + m_losses) > 0 else 0
        m_profit_class = "positive" if m_profit >= 0 else "negative"
        market_rows += f'''
        <tr>
            <td>{market_name}</td>
            <td>{m_bets}</td>
            <td>{m_wins}W / {m_losses}L</td>
            <td>{m_wr:.1f}%</td>
            <td class="{m_profit_class}">{m_profit:+.2f}</td>
            <td class="{m_profit_class}">{m_roi:+.1f}%</td>
        </tr>
        '''

    # Book breakdown table
    book_rows = ""
    for book_name, stats in sorted(by_book.items(), key=lambda x: x[1].get("profit", 0), reverse=True):
        b_bets = stats.get("bets", 0)
        b_wins = stats.get("wins", 0)
        b_losses = stats.get("losses", 0)
        b_profit = stats.get("profit", 0)
        b_staked = stats.get("staked", 0)
        b_roi = (b_profit / b_staked * 100) if b_staked > 0 else 0
        b_wr = (b_wins / (b_wins + b_losses) * 100) if (b_wins + b_losses) > 0 else 0
        b_profit_class = "positive" if b_profit >= 0 else "negative"
        book_rows += f'''
        <tr>
            <td style="text-transform: capitalize;">{book_name}</td>
            <td>{b_bets}</td>
            <td>{b_wins}W / {b_losses}L</td>
            <td>{b_wr:.1f}%</td>
            <td class="{b_profit_class}">{b_profit:+.2f}</td>
            <td class="{b_profit_class}">{b_roi:+.1f}%</td>
        </tr>
        '''

    # Recent bets table (show last 25)
    recent_rows = ""
    for bet in reversed(recent_bets[-25:]):
        result = bet.get("result", "pending")
        result_colors = {"won": "#22c55e", "lost": "#ef4444", "push": "#3b82f6"}
        result_color = result_colors.get(result, "#6b7280")
        bet_profit = bet.get("profit", 0)
        profit_class = "positive" if bet_profit >= 0 else "negative"
        recent_rows += f'''
        <tr>
            <td>{bet.get("date", "")}</td>
            <td>{bet.get("fixture", "")[:30]}</td>
            <td>{bet.get("league", "")}</td>
            <td>{bet.get("market", "")}</td>
            <td>{bet.get("selection", "")}</td>
            <td style="text-transform: capitalize;">{bet.get("book", "")}</td>
            <td>{bet.get("odds", 0):.2f}</td>
            <td>{bet.get("edge", 0):.1f}%</td>
            <td>{bet.get("actual", "")}</td>
            <td><span style="background:{result_color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">{result.upper()}</span></td>
            <td class="{profit_class}">{bet_profit:+.2f}</td>
        </tr>
        '''

    # Config info
    config_info = ""
    if config:
        config_info = f'''
        <div class="config-info">
            <span>Date Range: {config.get("date_range", "N/A")}</span>
            <span>Edge: {config.get("min_edge", 5)}% - {config.get("max_edge", 25)}%</span>
            <span>Odds: {config.get("min_odds", 1.5)} - {config.get("max_odds", 3.0)}</span>
            <span>Min Books: {config.get("min_books", 4)}</span>
        </div>
        '''

    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live Backtest - EV Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(-45deg, #0a0a0a, #1a1a2e, #0f0f1a, #0a1628);
                background-size: 400% 400%;
                animation: gradientBG 15s ease infinite;
                color: #fff;
                padding: 20px;
                max-width: 1600px;
                margin: 0 auto;
                min-height: 100vh;
            }}
            @keyframes gradientBG {{
                0% {{ background-position: 0% 50%; }}
                50% {{ background-position: 100% 50%; }}
                100% {{ background-position: 0% 50%; }}
            }}

            h1 {{
                text-align: center;
                margin-bottom: 10px;
                font-size: 32px;
                background: linear-gradient(135deg, #fff 0%, #f59e0b 50%, #22c55e 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            .subtitle {{ text-align: center; color: #888; margin-bottom: 20px; }}
            .subtitle a {{ color: #60a5fa; text-decoration: none; }}

            .status-bar {{
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 20px;
                margin-bottom: 20px;
                flex-wrap: wrap;
            }}

            .progress-section {{
                background: rgba(26, 26, 26, 0.8);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
            }}
            .progress-bar {{
                background: #1a1a1a;
                border-radius: 10px;
                height: 20px;
                overflow: hidden;
                margin: 10px 0;
            }}
            .progress-fill {{
                background: linear-gradient(90deg, #f59e0b, #22c55e);
                height: 100%;
                transition: width 0.5s ease;
            }}
            .progress-text {{ text-align: center; color: #888; font-size: 14px; }}

            .config-info {{
                display: flex;
                justify-content: center;
                gap: 20px;
                flex-wrap: wrap;
                margin-bottom: 20px;
                font-size: 13px;
                color: #888;
            }}
            .config-info span {{
                background: rgba(255,255,255,0.05);
                padding: 5px 12px;
                border-radius: 6px;
            }}

            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px;
                margin-bottom: 30px;
            }}
            .stat-card {{
                background: rgba(26, 26, 26, 0.8);
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                border: 1px solid rgba(255,255,255,0.1);
            }}
            .stat-value {{
                font-size: 28px;
                font-weight: bold;
                margin-bottom: 5px;
            }}
            .stat-value.positive {{ color: #4ade80; }}
            .stat-value.negative {{ color: #f87171; }}
            .stat-label {{ font-size: 12px; color: #888; text-transform: uppercase; }}

            .section-title {{
                font-size: 20px;
                margin: 30px 0 15px 0;
                padding-bottom: 10px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }}

            .breakdown-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .breakdown-card {{
                background: rgba(26, 26, 26, 0.8);
                border-radius: 12px;
                padding: 20px;
                border: 1px solid rgba(255,255,255,0.1);
            }}
            .breakdown-card h3 {{
                margin-bottom: 15px;
                color: #60a5fa;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 13px;
            }}
            th {{
                background: rgba(255,255,255,0.05);
                padding: 10px;
                text-align: left;
                font-weight: 500;
                color: #888;
            }}
            td {{
                padding: 10px;
                border-bottom: 1px solid rgba(255,255,255,0.05);
            }}
            .positive {{ color: #4ade80; }}
            .negative {{ color: #f87171; }}

            .recent-bets {{
                background: rgba(26, 26, 26, 0.8);
                border-radius: 12px;
                padding: 20px;
                overflow-x: auto;
            }}
            .recent-bets table {{ min-width: 1000px; }}

            .refresh-info {{
                text-align: center;
                color: #666;
                font-size: 12px;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <h1>Live Backtest Results</h1>
        <p class="subtitle"><a href="/">Dashboard</a> | <a href="/backtest">Run Backtest</a> | <a href="/settle">Settle</a></p>

        <div class="status-bar">
            {status_badge}
            <span style="color:#888;">Last Updated: {results.get("last_updated", "Never")}</span>
        </div>

        {config_info}

        <div class="progress-section">
            <div class="progress-text">
                Processing: <strong>{current_league or "Waiting..."}</strong>
                ({leagues_done}/{leagues_total} leagues, {progress.get("fixtures_processed", 0)} fixtures)
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {progress_pct:.1f}%"></div>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total_bets}</div>
                <div class="stat-label">Total Bets</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{wins}W / {losses}L</div>
                <div class="stat-label">Record</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{win_rate:.1f}%</div>
                <div class="stat-label">Win Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_staked:.0f}</div>
                <div class="stat-label">Total Staked</div>
            </div>
            <div class="stat-card">
                <div class="stat-value {profit_class}">{total_profit:+.2f}</div>
                <div class="stat-label">Profit</div>
            </div>
            <div class="stat-card">
                <div class="stat-value {roi_class}">{roi:+.1f}%</div>
                <div class="stat-label">ROI</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{avg_edge:.1f}%</div>
                <div class="stat-label">Avg Edge</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{avg_odds:.2f}</div>
                <div class="stat-label">Avg Odds</div>
            </div>
        </div>

        <div class="breakdown-grid">
            <div class="breakdown-card">
                <h3>By League</h3>
                <table>
                    <thead><tr><th>League</th><th>Bets</th><th>Record</th><th>Win%</th><th>Profit</th><th>ROI</th></tr></thead>
                    <tbody>{league_rows if league_rows else '<tr><td colspan="6" style="text-align:center;color:#666;">No data yet</td></tr>'}</tbody>
                </table>
            </div>
            <div class="breakdown-card">
                <h3>By Market</h3>
                <table>
                    <thead><tr><th>Market</th><th>Bets</th><th>Record</th><th>Win%</th><th>Profit</th><th>ROI</th></tr></thead>
                    <tbody>{market_rows if market_rows else '<tr><td colspan="6" style="text-align:center;color:#666;">No data yet</td></tr>'}</tbody>
                </table>
            </div>
            <div class="breakdown-card">
                <h3>By Bookmaker</h3>
                <table>
                    <thead><tr><th>Book</th><th>Bets</th><th>Record</th><th>Win%</th><th>Profit</th><th>ROI</th></tr></thead>
                    <tbody>{book_rows if book_rows else '<tr><td colspan="6" style="text-align:center;color:#666;">No data yet</td></tr>'}</tbody>
                </table>
            </div>
        </div>

        <h2 class="section-title">Recent Bets ({len(recent_bets)})</h2>
        <div class="recent-bets">
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Fixture</th>
                        <th>League</th>
                        <th>Market</th>
                        <th>Selection</th>
                        <th>Book</th>
                        <th>Odds</th>
                        <th>Edge</th>
                        <th>Actual</th>
                        <th>Result</th>
                        <th>Profit</th>
                    </tr>
                </thead>
                <tbody>
                    {recent_rows if recent_rows else '<tr><td colspan="11" style="text-align:center;color:#666;">No bets yet</td></tr>'}
                </tbody>
            </table>
        </div>

        <p class="refresh-info">Auto-refreshes every 10 seconds | Started: {results.get("started_at", "N/A")}</p>

        <script>
            // Auto-refresh every 10 seconds
            setTimeout(() => location.reload(), 10000);
        </script>
    </body>
    </html>
    '''

    return HTMLResponse(content=html)
