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
    """Settlement page for marking bet results."""
    bet_history = await fetch_firebase("bet_history") or {}

    # Find unsettled bets (played but no result)
    unsettled = []
    for key, bet in bet_history.items():
        if bet.get("user_action") == "played" and not bet.get("result"):
            unsettled.append((key, bet))

    # Sort by kickoff (oldest first - should be settled first)
    unsettled.sort(key=lambda x: x[1].get("kickoff", ""))

    # Build table rows
    rows = ""
    for key, bet in unsettled:
        book_icon = get_book_icon(bet.get("bookmaker", ""))
        odds = bet.get("odds", 0)
        stake = bet.get("stake", 10)
        potential_win = round((odds - 1) * stake, 2)

        # Format kickoff
        kickoff_str = bet.get("kickoff", "")
        try:
            kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
            kickoff_cet = kickoff + timedelta(hours=1)
            kickoff_display = kickoff_cet.strftime("%d/%m %H:%M")
        except:
            kickoff_display = "TBD"

        rows += f"""
        <tr>
            <td>{book_icon} {bet.get('bookmaker', 'N/A').upper()}</td>
            <td>{bet.get('fixture', 'N/A')[:35]}</td>
            <td><strong>{bet.get('selection', 'N/A')}</strong></td>
            <td>{odds:.2f}</td>
            <td>{bet.get('edge', 0):.1f}%</td>
            <td>{kickoff_display}</td>
            <td>
                <button onclick="settle('{key}', 'won', {potential_win})" style="background:#22c55e;color:white;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;margin:2px;">
                    ✅ Won (+{potential_win})
                </button>
                <button onclick="settle('{key}', 'lost', -{stake})" style="background:#ef4444;color:white;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;margin:2px;">
                    ❌ Lost (-{stake})
                </button>
                <button onclick="settle('{key}', 'push', 0)" style="background:#3b82f6;color:white;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;margin:2px;">
                    ➖ Push
                </button>
            </td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="7" style="text-align:center;color:#666;padding:40px;">No unsettled bets! All caught up.</td></tr>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Settle Bets - EV Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
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
            h1 {{ color: #f8fafc; margin-bottom: 10px; font-size: 24px; }}
            .subtitle {{ color: #94a3b8; margin-bottom: 30px; }}
            a {{ color: #60a5fa; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}

            .stats {{
                display: flex;
                gap: 20px;
                margin-bottom: 30px;
            }}
            .stat {{
                background: #1e293b;
                padding: 15px 25px;
                border-radius: 8px;
            }}
            .stat-num {{ font-size: 24px; font-weight: bold; }}
            .stat-label {{ color: #94a3b8; font-size: 12px; }}

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
        <div class="container">
            <h1>⚖️ Settle Bets</h1>
            <p class="subtitle"><a href="/">← Back to Dashboard</a> | {len(unsettled)} bets to settle</p>

            <div class="stats">
                <div class="stat">
                    <div class="stat-num">{len(unsettled)}</div>
                    <div class="stat-label">Pending Settlement</div>
                </div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>Book</th>
                        <th>Match</th>
                        <th>Pick</th>
                        <th>Odds</th>
                        <th>Edge</th>
                        <th>Kickoff</th>
                        <th>Result</th>
                    </tr>
                </thead>
                <tbody id="bets-table">
                    {rows}
                </tbody>
            </table>
        </div>

        <div id="toast" class="toast"></div>

        <script>
            async function settle(betKey, result, profit) {{
                const row = event.target.closest('tr');

                try {{
                    const response = await fetch('/api/settle', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ bet_key: betKey, result: result, profit: profit }})
                    }});

                    if (response.ok) {{
                        // Remove row with animation
                        row.style.background = result === 'won' ? '#22c55e33' : result === 'lost' ? '#ef444433' : '#3b82f633';
                        setTimeout(() => {{
                            row.remove();
                            // Check if table is empty
                            const tbody = document.getElementById('bets-table');
                            if (tbody.children.length === 0) {{
                                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#666;padding:40px;">No unsettled bets! All caught up.</td></tr>';
                            }}
                        }}, 300);

                        // Show toast
                        const toast = document.getElementById('toast');
                        toast.textContent = `Bet marked as ${{result.toUpperCase()}} (${{profit >= 0 ? '+' : ''}}${{profit}} DKK)`;
                        toast.style.background = result === 'won' ? '#22c55e' : result === 'lost' ? '#ef4444' : '#3b82f6';
                        toast.style.display = 'block';
                        setTimeout(() => toast.style.display = 'none', 3000);
                    }}
                }} catch (e) {{
                    alert('Error settling bet: ' + e);
                }}
            }}
        </script>
    </body>
    </html>
    """
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
