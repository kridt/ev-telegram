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
    total_staked = len(played_bets) * 10  # Assuming 10 DKK stake

    win_rate = (len(won_bets) / len(played_bets) * 100) if played_bets else 0
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0

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
            <p style="margin-bottom:20px;"><a href="/settle" style="color:#60a5fa;text-decoration:none;">⚖️ Settle Bets →</a></p>

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

    # Find unsettled bets (played but no result)
    unsettled = []
    for key, bet in bet_history.items():
        if bet.get("user_action") == "played" and not bet.get("result"):
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

    # Calculate totals
    total_bets = len(unsettled)
    total_staked = total_bets * 10
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
            book = bet.get("bookmaker", "").lower()
            book_class = book if book in ["betsson", "leovegas", "unibet", "betano"] else ""
            odds = bet.get("odds", 0)
            edge = bet.get("edge", 0)
            edge_class = "high" if edge >= 10 else "medium" if edge >= 7 else "low"
            selection = bet.get("selection", "")
            arrow = "▲" if "over" in selection.lower() else "▼" if "under" in selection.lower() else ""
            arrow_class = "over" if "over" in selection.lower() else "under" if "under" in selection.lower() else ""

            bet_rows += f'''
            <tr data-key="{key}" data-odds="{odds}" data-market="{bet.get('market', '')}" data-selection="{selection}">
                <td>{bet.get('market', 'N/A')}</td>
                <td><span class="selection"><span class="arrow {arrow_class}">{arrow}</span> {selection}</span></td>
                <td><span class="bookmaker {book_class}">{book.upper()}</span></td>
                <td>{odds:.2f}</td>
                <td><span class="edge {edge_class}">{edge:.1f}%</span></td>
                <td class="result-buttons">
                    <button class="result-btn win" onclick="setResult('{key}', 'won', {round((odds-1)*10, 2)})">Win</button>
                    <button class="result-btn loss" onclick="setResult('{key}', 'lost', -10)">Loss</button>
                    <button class="result-btn push" onclick="setResult('{key}', 'push', 0)">Push</button>
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
                    <tr><th>Market</th><th>Selection</th><th>Book</th><th>Odds</th><th>Edge</th><th>Result</th></tr>
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
                <div class="stat-value">{total_staked} DKK</div>
                <div class="stat-label">Total Staked</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="totalProfit">0 DKK</div>
                <div class="stat-label">P&L</div>
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
                        profit = result === 'won' ? (odds - 1) * STAKE : -STAKE;
                        const btn = row.querySelector(`.result-btn.${{result === 'won' ? 'win' : 'loss'}}`);
                        if (btn) btn.click();
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
            r = await client.patch(
                f"{RTDB_URL}/bet_history/{bet_key}.json",
                json=update_data
            )
            if r.status_code == 200:
                return {"success": True, "bet_key": bet_key, "result": result, "profit": profit}
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
