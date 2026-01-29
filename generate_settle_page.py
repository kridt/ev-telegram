#!/usr/bin/env python3
"""
Generate daily bet settling pages from bet_history.json.
Creates an interactive HTML page for each day's bets.
"""

import json
import os
from datetime import datetime
from collections import defaultdict
from pathlib import Path

def load_bet_history():
    """Load bet history from JSON file."""
    history_path = Path(__file__).parent / "bet_history.json"
    if not history_path.exists():
        return []
    with open(history_path, "r", encoding="utf-8") as f:
        return json.load(f)

def group_bets_by_date(bets):
    """Group bets by kickoff date."""
    date_groups = defaultdict(list)
    for bet in bets:
        kickoff = bet.get("kickoff", "")
        if kickoff:
            date_str = kickoff[:10]  # YYYY-MM-DD
            date_groups[date_str].append(bet)
    return date_groups

def group_bets_by_match(bets):
    """Group bets by fixture for a single day."""
    match_groups = defaultdict(list)
    for bet in bets:
        fixture = bet.get("fixture", "Unknown")
        match_groups[fixture].append(bet)
    return match_groups

def generate_html(date_str, bets):
    """Generate HTML page for a single day's bets."""
    match_groups = group_bets_by_match(bets)

    # Format date for display
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        display_date = date_obj.strftime("%A, %B %d, %Y")
    except:
        display_date = date_str

    total_stake = sum(bet.get("stake", 10) for bet in bets)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Settle Bets - {date_str}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
        }}
        h1 {{
            color: #00d4ff;
            margin-bottom: 10px;
            font-size: 2em;
        }}
        .date {{
            color: #888;
            font-size: 1.1em;
        }}
        .summary {{
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-top: 15px;
            flex-wrap: wrap;
        }}
        .summary-item {{
            text-align: center;
        }}
        .summary-value {{
            font-size: 1.5em;
            font-weight: bold;
            color: #00d4ff;
        }}
        .summary-label {{
            color: #888;
            font-size: 0.9em;
        }}
        .pnl {{
            font-size: 2em;
            font-weight: bold;
            margin-top: 15px;
        }}
        .pnl.positive {{ color: #00ff88; }}
        .pnl.negative {{ color: #ff4466; }}
        .pnl.neutral {{ color: #888; }}

        .match-section {{
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            margin-bottom: 25px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .match-header {{
            background: rgba(0,212,255,0.1);
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }}
        .match-title {{
            font-size: 1.3em;
            color: #00d4ff;
        }}
        .match-info {{
            color: #888;
            font-size: 0.9em;
        }}
        .stats-input {{
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }}
        .stat-group {{
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .stat-group label {{
            font-size: 0.75em;
            color: #888;
            margin-bottom: 3px;
        }}
        .stat-group input {{
            width: 60px;
            padding: 8px;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 6px;
            background: rgba(0,0,0,0.3);
            color: #fff;
            text-align: center;
            font-size: 1em;
        }}
        .settle-match-btn {{
            padding: 10px 20px;
            background: linear-gradient(135deg, #00d4ff, #0099cc);
            border: none;
            border-radius: 6px;
            color: #fff;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        .settle-match-btn:hover {{
            transform: scale(1.05);
        }}

        .bets-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .bets-table th {{
            background: rgba(0,0,0,0.3);
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #888;
            font-size: 0.85em;
            text-transform: uppercase;
        }}
        .bets-table td {{
            padding: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .bets-table tr:hover {{
            background: rgba(255,255,255,0.02);
        }}

        .bookmaker {{
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        .bookmaker.betsson {{ background: #1a472a; color: #4ade80; }}
        .bookmaker.leovegas {{ background: #4a2c1a; color: #fb923c; }}
        .bookmaker.betano {{ background: #1a2a4a; color: #60a5fa; }}
        .bookmaker.unibet {{ background: #3a1a4a; color: #c084fc; }}

        .edge {{
            color: #00ff88;
            font-weight: bold;
        }}

        .result-btns {{
            display: flex;
            gap: 8px;
        }}
        .result-btn {{
            padding: 6px 14px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.85em;
            transition: all 0.2s;
        }}
        .result-btn.win {{
            background: rgba(0,255,136,0.2);
            color: #00ff88;
            border: 1px solid #00ff88;
        }}
        .result-btn.win:hover, .result-btn.win.active {{
            background: #00ff88;
            color: #000;
        }}
        .result-btn.loss {{
            background: rgba(255,68,102,0.2);
            color: #ff4466;
            border: 1px solid #ff4466;
        }}
        .result-btn.loss:hover, .result-btn.loss.active {{
            background: #ff4466;
            color: #fff;
        }}
        .result-btn.push {{
            background: rgba(136,136,136,0.2);
            color: #888;
            border: 1px solid #888;
        }}
        .result-btn.push:hover, .result-btn.push.active {{
            background: #888;
            color: #000;
        }}

        .profit-cell {{
            font-weight: bold;
        }}
        .profit-cell.positive {{ color: #00ff88; }}
        .profit-cell.negative {{ color: #ff4466; }}
        .profit-cell.neutral {{ color: #888; }}

        .footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            margin-top: 30px;
        }}

        @media (max-width: 768px) {{
            .bets-table th, .bets-table td {{
                padding: 8px 6px;
                font-size: 0.85em;
            }}
            .stats-input {{
                width: 100%;
                justify-content: center;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Bet Settling</h1>
            <div class="date">{display_date}</div>
            <div class="summary">
                <div class="summary-item">
                    <div class="summary-value" id="total-bets">{len(bets)}</div>
                    <div class="summary-label">Total Bets</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value" id="settled-count">0</div>
                    <div class="summary-label">Settled</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{total_stake:.0f} DKK</div>
                    <div class="summary-label">Total Staked</div>
                </div>
            </div>
            <div class="pnl neutral" id="total-pnl">P&L: 0.00 DKK</div>
        </header>
'''

    # Generate match sections
    for fixture, match_bets in sorted(match_groups.items()):
        # Get kickoff time
        kickoff = match_bets[0].get("kickoff", "")
        try:
            ko_time = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).strftime("%H:%M")
        except:
            ko_time = ""

        league = match_bets[0].get("league", "")
        match_id = fixture.replace(" ", "_").replace(".", "")[:30]

        html += f'''
        <div class="match-section" data-match="{match_id}">
            <div class="match-header">
                <div>
                    <div class="match-title">{fixture}</div>
                    <div class="match-info">{league} | KO: {ko_time}</div>
                </div>
                <div class="stats-input">
                    <div class="stat-group">
                        <label>Shots</label>
                        <input type="number" id="{match_id}_shots" placeholder="0">
                    </div>
                    <div class="stat-group">
                        <label>SOT</label>
                        <input type="number" id="{match_id}_sot" placeholder="0">
                    </div>
                    <div class="stat-group">
                        <label>Corners</label>
                        <input type="number" id="{match_id}_corners" placeholder="0">
                    </div>
                    <div class="stat-group">
                        <label>Home</label>
                        <input type="number" id="{match_id}_home" placeholder="0">
                    </div>
                    <div class="stat-group">
                        <label>Away</label>
                        <input type="number" id="{match_id}_away" placeholder="0">
                    </div>
                    <button class="settle-match-btn" onclick="settleMatch('{match_id}')">Settle All</button>
                </div>
            </div>
            <table class="bets-table">
                <thead>
                    <tr>
                        <th>Market</th>
                        <th>Selection</th>
                        <th>Bookmaker</th>
                        <th>Odds</th>
                        <th>Edge</th>
                        <th>Stake</th>
                        <th>Result</th>
                        <th>Profit</th>
                    </tr>
                </thead>
                <tbody>
'''

        for bet in sorted(match_bets, key=lambda x: (x.get("market", ""), x.get("selection", ""))):
            bet_id = bet.get("id", 0)
            bookmaker = bet.get("bookmaker", "Unknown").lower()
            bookmaker_class = bookmaker.replace(" ", "")

            html += f'''
                    <tr data-bet-id="{bet_id}" data-match="{match_id}">
                        <td>{bet.get("market", "")}</td>
                        <td>{bet.get("selection", "")}</td>
                        <td><span class="bookmaker {bookmaker_class}">{bet.get("bookmaker", "")}</span></td>
                        <td>{bet.get("odds", 0):.2f}</td>
                        <td class="edge">{bet.get("edge", 0):.1f}%</td>
                        <td>{bet.get("stake", 10):.0f} DKK</td>
                        <td class="result-btns">
                            <button class="result-btn win" onclick="setBetResult({bet_id}, 'win', {bet.get('odds', 0)}, {bet.get('stake', 10)})">Win</button>
                            <button class="result-btn loss" onclick="setBetResult({bet_id}, 'loss', {bet.get('odds', 0)}, {bet.get('stake', 10)})">Loss</button>
                            <button class="result-btn push" onclick="setBetResult({bet_id}, 'push', {bet.get('odds', 0)}, {bet.get('stake', 10)})">Push</button>
                        </td>
                        <td class="profit-cell neutral" id="profit-{bet_id}">-</td>
                    </tr>
'''

        html += '''
                </tbody>
            </table>
        </div>
'''

    # Add JavaScript
    html += '''
        <div class="footer">
            Generated by Soccer Props Value Scanner
        </div>
    </div>

    <script>
        const betResults = {};

        function setBetResult(betId, result, odds, stake) {
            const row = document.querySelector(`tr[data-bet-id="${betId}"]`);
            const profitCell = document.getElementById(`profit-${betId}`);

            // Clear previous selection
            row.querySelectorAll('.result-btn').forEach(btn => btn.classList.remove('active'));

            // Set new selection
            row.querySelector(`.result-btn.${result}`).classList.add('active');

            let profit = 0;
            if (result === 'win') {
                profit = (odds - 1) * stake;
                profitCell.textContent = `+${profit.toFixed(2)} DKK`;
                profitCell.className = 'profit-cell positive';
            } else if (result === 'loss') {
                profit = -stake;
                profitCell.textContent = `${profit.toFixed(2)} DKK`;
                profitCell.className = 'profit-cell negative';
            } else {
                profit = 0;
                profitCell.textContent = '0.00 DKK';
                profitCell.className = 'profit-cell neutral';
            }

            betResults[betId] = { result, profit };
            updateTotals();
        }

        function updateTotals() {
            let totalPnL = 0;
            let settledCount = 0;

            for (const betId in betResults) {
                totalPnL += betResults[betId].profit;
                settledCount++;
            }

            document.getElementById('settled-count').textContent = settledCount;

            const pnlEl = document.getElementById('total-pnl');
            if (totalPnL > 0) {
                pnlEl.textContent = `P&L: +${totalPnL.toFixed(2)} DKK`;
                pnlEl.className = 'pnl positive';
            } else if (totalPnL < 0) {
                pnlEl.textContent = `P&L: ${totalPnL.toFixed(2)} DKK`;
                pnlEl.className = 'pnl negative';
            } else {
                pnlEl.textContent = `P&L: 0.00 DKK`;
                pnlEl.className = 'pnl neutral';
            }
        }

        function settleMatch(matchId) {
            const shots = parseInt(document.getElementById(`${matchId}_shots`).value) || 0;
            const sot = parseInt(document.getElementById(`${matchId}_sot`).value) || 0;
            const corners = parseInt(document.getElementById(`${matchId}_corners`).value) || 0;
            const homeGoals = parseInt(document.getElementById(`${matchId}_home`).value) || 0;
            const awayGoals = parseInt(document.getElementById(`${matchId}_away`).value) || 0;

            const rows = document.querySelectorAll(`tr[data-match="${matchId}"]`);

            rows.forEach(row => {
                const betId = row.dataset.betId;
                const market = row.cells[0].textContent;
                const selection = row.cells[1].textContent;
                const odds = parseFloat(row.cells[3].textContent);
                const stake = parseFloat(row.cells[5].textContent);

                let result = null;

                // Parse selection
                const isOver = selection.toLowerCase().includes('over');
                const isUnder = selection.toLowerCase().includes('under');
                const lineMatch = selection.match(/[\\d.]+/);
                const line = lineMatch ? parseFloat(lineMatch[0]) : 0;

                // Determine result based on market
                if (market.includes('Total Shots') && !market.includes('On Target')) {
                    if (shots > 0) {
                        if (isOver) result = shots > line ? 'win' : 'loss';
                        else if (isUnder) result = shots < line ? 'win' : 'loss';
                    }
                } else if (market.includes('Shots On Target') || market.includes('Total Shots On Target')) {
                    if (sot > 0) {
                        if (isOver) result = sot > line ? 'win' : 'loss';
                        else if (isUnder) result = sot < line ? 'win' : 'loss';
                    }
                } else if (market.includes('Corners') || market.includes('Total Corners')) {
                    if (corners > 0) {
                        if (isOver) result = corners > line ? 'win' : 'loss';
                        else if (isUnder) result = corners < line ? 'win' : 'loss';
                    }
                } else if (market.includes('Asian Handicap')) {
                    // AH settlement is more complex, skip auto-settle
                    result = null;
                }

                if (result) {
                    setBetResult(parseInt(betId), result, odds, stake);
                }
            });
        }
    </script>
</body>
</html>
'''

    return html

def generate_index(output_dir, date_groups):
    """Generate index.html listing all settle pages."""
    pages_data = []

    for date_str, day_bets in sorted(date_groups.items(), reverse=True):
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            display_date = date_obj.strftime("%A, %B %d, %Y")
        except:
            display_date = date_str

        match_groups = group_bets_by_match(day_bets)

        pages_data.append({
            "file": f"settle_{date_str}.html",
            "date": date_str,
            "display_date": display_date,
            "bet_count": len(day_bets),
            "match_count": len(match_groups)
        })

    index_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bet Settling - Index</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 40px 20px;
        }
        .container { max-width: 600px; margin: 0 auto; }
        h1 {
            text-align: center;
            color: #00d4ff;
            margin-bottom: 40px;
            font-size: 2em;
        }
        .days-list { display: flex; flex-direction: column; gap: 15px; }
        .day-link {
            display: block;
            background: rgba(255,255,255,0.05);
            padding: 20px 25px;
            border-radius: 12px;
            text-decoration: none;
            color: #e0e0e0;
            border: 1px solid rgba(255,255,255,0.1);
            transition: all 0.2s;
        }
        .day-link:hover {
            background: rgba(0,212,255,0.1);
            border-color: #00d4ff;
            transform: translateX(5px);
        }
        .day-date {
            font-size: 1.3em;
            font-weight: 600;
            color: #00d4ff;
            margin-bottom: 5px;
        }
        .day-info { color: #888; font-size: 0.9em; }
        .no-pages { text-align: center; color: #888; padding: 40px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Bet Settling Pages</h1>
        <div class="days-list">
'''

    if not pages_data:
        index_html += '<div class="no-pages">No settle pages found.</div>'
    else:
        for page in pages_data:
            index_html += f'''
            <a href="{page['file']}" class="day-link">
                <div class="day-date">{page['display_date']}</div>
                <div class="day-info">{page['bet_count']} bets | {page['match_count']} matches</div>
            </a>
'''

    index_html += '''
        </div>
    </div>
</body>
</html>
'''

    with open(output_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"Generated: {output_dir / 'index.html'}")


def generate_all_pages():
    """Generate settle pages for all dates in bet history."""
    bets = load_bet_history()
    if not bets:
        print("No bets found in bet_history.json")
        return []

    date_groups = group_bets_by_date(bets)

    # Create output directory
    output_dir = Path(__file__).parent / "settle_pages"
    output_dir.mkdir(exist_ok=True)

    generated_files = []

    for date_str, day_bets in sorted(date_groups.items(), reverse=True):
        html = generate_html(date_str, day_bets)
        output_file = output_dir / f"settle_{date_str}.html"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"Generated: {output_file} ({len(day_bets)} bets)")
        generated_files.append(output_file)

    # Generate index page
    generate_index(output_dir, date_groups)

    return generated_files

def generate_today():
    """Generate settle page for today's bets only."""
    today = datetime.now().strftime("%Y-%m-%d")
    bets = load_bet_history()

    date_groups = group_bets_by_date(bets)

    if today not in date_groups:
        print(f"No bets found for {today}")
        return None

    day_bets = date_groups[today]
    html = generate_html(today, day_bets)

    output_dir = Path(__file__).parent / "settle_pages"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"settle_{today}.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Generated: {output_file} ({len(day_bets)} bets)")
    return output_file

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--today":
        generate_today()
    else:
        generate_all_pages()
