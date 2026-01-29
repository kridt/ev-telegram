#!/usr/bin/env python3
"""Generate HTML dashboard from value_bets.json"""

import json
from datetime import datetime, timedelta, timezone

# Load value bets
with open('value_bets.json', 'r', encoding='utf-8') as f:
    all_bets = json.load(f)

now_utc = datetime.now(timezone.utc)
cet_offset = timedelta(hours=1)
now_cet = now_utc + cet_offset
cutoff_cet = now_cet + timedelta(hours=6)

# Filter bets to only include fixtures in the next 6 hours
bets = []
for bet in all_bets:
    kickoff_str = bet.get('kickoff', '')
    if kickoff_str:
        try:
            kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
            kickoff_cet = kickoff + cet_offset
            if now_cet <= kickoff_cet <= cutoff_cet:
                bets.append(bet)
        except:
            pass

# Sort by edge
bets.sort(key=lambda x: -x['edge'])

# Count by market
market_counts = {}
for bet in bets:
    m = bet['market']
    market_counts[m] = market_counts.get(m, 0) + 1

def format_kickoff(kickoff_str):
    try:
        kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
        kickoff_cet = kickoff + cet_offset
        return kickoff_cet.strftime('%b %d - %H:%M CET')
    except:
        return 'TBD'

def format_kickoff_short(kickoff_str):
    try:
        kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
        kickoff_cet = kickoff + cet_offset
        return kickoff_cet.strftime('%b %d %H:%M')
    except:
        return 'TBD'

# Check if we have bets in the next 6 hours
no_bets_message = ""
next_bets_html = ""

if len(bets) == 0:
    # Find next available bets
    upcoming = []
    for bet in all_bets:
        kickoff_str = bet.get('kickoff', '')
        if kickoff_str:
            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
                kickoff_cet = kickoff + cet_offset
                if kickoff_cet > now_cet:
                    bet['_kickoff_cet'] = kickoff_cet
                    upcoming.append(bet)
            except:
                pass
    upcoming.sort(key=lambda x: x['_kickoff_cet'])

    no_bets_message = f'''
        <div style="text-align: center; padding: 60px 20px; background: rgba(255,255,255,0.03); border-radius: 12px; margin: 30px 0;">
            <h2 style="color: #00d4ff; margin-bottom: 15px;">No Matches in Next 6 Hours</h2>
            <p style="color: rgba(255,255,255,0.6); margin-bottom: 30px;">
                Current time: {now_cet.strftime('%H:%M CET')} | No fixtures with value until {cutoff_cet.strftime('%H:%M CET')}
            </p>
            <h3 style="color: #00ff88; margin-bottom: 20px;">Next Available Value Bets:</h3>
    '''

    seen_fixtures = set()
    for bet in upcoming[:6]:
        if bet['fixture'] not in seen_fixtures:
            seen_fixtures.add(bet['fixture'])
            kickoff_str = bet['_kickoff_cet'].strftime('%b %d, %H:%M CET')
            no_bets_message += f'''
            <div style="background: rgba(0,212,255,0.1); padding: 15px 20px; border-radius: 8px; margin: 10px auto; max-width: 600px; text-align: left;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-weight: 600;">{bet['fixture'][:50]}</div>
                        <div style="font-size: 0.85rem; color: rgba(255,255,255,0.5);">{kickoff_str} | {bet['league'][:20]}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="color: #00ff88; font-weight: 700;">+{bet['edge']:.1f}%</div>
                        <div style="font-size: 0.85rem;">{bet['selection']}</div>
                    </div>
                </div>
            </div>
            '''

    no_bets_message += '''
        </div>
    '''

# Generate bet cards HTML
cards_html = ""
for bet in bets[:8]:
    kickoff_str = format_kickoff(bet['kickoff'])
    high_class = 'high-value' if bet['edge'] >= 10 else ''
    league_short = bet['league'][:20]

    all_odds_html = ''
    for book, odd in sorted(bet['all_odds'].items()):
        chip_class = 'best' if book == bet['book'] else ''
        all_odds_html += f'<span class="odds-chip {chip_class}">{book}: {odd}</span>'

    cards_html += f'''
            <div class="bet-card {high_class}">
                <div class="bet-header">
                    <div class="bet-edge">+{bet['edge']:.1f}%</div>
                    <div class="bet-league">{league_short}</div>
                </div>
                <div class="bet-fixture">{bet['fixture'][:45]}</div>
                <div class="bet-kickoff">{kickoff_str}</div>
                <div class="bet-selection">
                    <div class="bet-market">{bet['market']}</div>
                    <div class="bet-pick">{bet['selection']}</div>
                </div>
                <div class="bet-odds-row">
                    <span class="bet-book">{bet['book']}</span>
                    <span class="bet-odds">{bet['odds']:.2f}</span>
                    <span class="bet-fair">Fair: {bet['fair']:.2f}</span>
                </div>
                <div class="all-odds">{all_odds_html}</div>
            </div>
'''

# Generate table rows
table_rows = ""
for bet in bets:
    kickoff_str = format_kickoff_short(bet['kickoff'])
    edge_class = 'edge-high' if bet['edge'] >= 10 else 'edge-medium'
    league_short = bet['league'][:15]

    table_rows += f'''                    <tr>
                        <td><span class="edge-badge {edge_class}">{bet['edge']:.1f}%</span></td>
                        <td>{kickoff_str}</td>
                        <td>{bet['fixture'][:35]}</td>
                        <td>{league_short}</td>
                        <td>{bet['market']}</td>
                        <td>{bet['selection']}</td>
                        <td><strong>{bet['odds']:.2f}</strong></td>
                        <td>{bet['fair']:.2f}</td>
                    </tr>
'''

html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Value Bets - Soccer Props</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            text-align: center;
            margin-bottom: 10px;
            font-size: 2.5rem;
            background: linear-gradient(90deg, #00d4ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .timestamp {{ text-align: center; color: rgba(255,255,255,0.5); margin-bottom: 20px; }}
        .config-info {{
            text-align: center;
            margin-bottom: 20px;
            display: flex;
            justify-content: center;
            gap: 15px;
            flex-wrap: wrap;
        }}
        .config-tag {{
            background: rgba(255,255,255,0.1);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.85rem;
        }}
        .config-tag.highlight {{
            background: rgba(0, 212, 255, 0.2);
            border: 1px solid rgba(0, 212, 255, 0.3);
        }}
        .summary-bar {{
            display: flex;
            justify-content: center;
            gap: 40px;
            padding: 20px;
            background: rgba(0, 255, 136, 0.1);
            border-radius: 12px;
            margin-bottom: 30px;
            border: 1px solid rgba(0, 255, 136, 0.2);
            flex-wrap: wrap;
        }}
        .summary-item {{ text-align: center; }}
        .summary-item .value {{ font-size: 1.8rem; font-weight: 700; color: #00ff88; }}
        .summary-item .label {{ font-size: 0.8rem; color: rgba(255,255,255,0.6); text-transform: uppercase; }}
        .section-title {{
            font-size: 1.5rem;
            margin: 40px 0 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(255,255,255,0.1);
        }}
        .bets-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .bet-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 18px;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .bet-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0, 212, 255, 0.15);
        }}
        .bet-card.high-value {{
            border-color: rgba(0, 255, 136, 0.3);
            background: linear-gradient(135deg, rgba(0, 255, 136, 0.05), rgba(0, 212, 255, 0.05));
        }}
        .bet-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 10px;
        }}
        .bet-edge {{ font-size: 1.4rem; font-weight: 700; color: #00ff88; }}
        .bet-league {{
            font-size: 0.7rem;
            color: rgba(255,255,255,0.5);
            text-transform: uppercase;
            background: rgba(255,255,255,0.1);
            padding: 4px 8px;
            border-radius: 4px;
        }}
        .bet-fixture {{ font-size: 1.05rem; font-weight: 600; margin-bottom: 6px; }}
        .bet-kickoff {{ font-size: 0.8rem; color: rgba(255,255,255,0.5); margin-bottom: 10px; }}
        .bet-selection {{
            background: rgba(0, 212, 255, 0.15);
            padding: 10px 12px;
            border-radius: 8px;
            margin-bottom: 10px;
        }}
        .bet-market {{ font-size: 0.75rem; color: rgba(255,255,255,0.5); text-transform: uppercase; }}
        .bet-pick {{ font-size: 1rem; font-weight: 600; color: #00d4ff; margin-top: 3px; }}
        .bet-odds-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-top: 8px;
            border-top: 1px solid rgba(255,255,255,0.05);
        }}
        .bet-book {{ font-weight: 600; color: #00ff88; }}
        .bet-odds {{ font-size: 1.2rem; font-weight: 700; }}
        .bet-fair {{ color: rgba(255,255,255,0.5); font-size: 0.85rem; }}
        .all-odds {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }}
        .odds-chip {{
            background: rgba(255,255,255,0.08);
            padding: 3px 7px;
            border-radius: 4px;
            font-size: 0.7rem;
        }}
        .odds-chip.best {{ background: rgba(0, 255, 136, 0.2); color: #00ff88; }}
        .table-container {{
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.1);
            overflow: hidden;
            max-height: 600px;
            overflow-y: auto;
        }}
        .bets-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        .bets-table th {{
            background: rgba(0, 212, 255, 0.15);
            padding: 12px 10px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.7rem;
            position: sticky;
            top: 0;
        }}
        .bets-table td {{ padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        .bets-table tr:hover {{ background: rgba(255,255,255,0.03); }}
        .edge-badge {{ display: inline-block; padding: 3px 7px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }}
        .edge-high {{ background: rgba(0, 255, 136, 0.2); color: #00ff88; }}
        .edge-medium {{ background: rgba(0, 212, 255, 0.2); color: #00d4ff; }}
        .footer {{ text-align: center; margin-top: 40px; color: rgba(255,255,255,0.4); font-size: 0.85rem; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Value Bets - Next 6 Hours</h1>
        <p class="timestamp">Scanned: {now_cet.strftime('%B %d, %Y %H:%M CET')} | Window: until {cutoff_cet.strftime('%H:%M CET')}</p>

        <div class="config-info">
            <span class="config-tag">Total Shots, Corners, Asian Handicap</span>
            <span class="config-tag">Betsson, LeoVegas, Unibet</span>
            <span class="config-tag highlight">Odds: 1.50 - 3.00</span>
            <span class="config-tag">Min Edge: 5%</span>
        </div>

        <div class="summary-bar">
            <div class="summary-item">
                <div class="value">{len(bets)}</div>
                <div class="label">Value Bets</div>
            </div>
            <div class="summary-item">
                <div class="value">{market_counts.get('Total Shots', 0)}</div>
                <div class="label">Total Shots</div>
            </div>
            <div class="summary-item">
                <div class="value">{market_counts.get('Total Shots On Target', 0)}</div>
                <div class="label">Shots On Target</div>
            </div>
            <div class="summary-item">
                <div class="value">{market_counts.get('Total Corners', 0)}</div>
                <div class="label">Total Corners</div>
            </div>
            <div class="summary-item">
                <div class="value">{market_counts.get('Asian Handicap', 0) + market_counts.get('Asian Handicap Corners', 0)}</div>
                <div class="label">Asian Handicap</div>
            </div>
        </div>

        {no_bets_message if len(bets) == 0 else f'''
        <h2 class="section-title">Top Value Bets</h2>
        <div class="bets-grid">
{cards_html}
        </div>

        <h2 class="section-title">All {len(bets)} Value Bets</h2>
        <div class="table-container">
            <table class="bets-table">
                <thead>
                    <tr>
                        <th>Edge</th>
                        <th>Kickoff</th>
                        <th>Match</th>
                        <th>League</th>
                        <th>Market</th>
                        <th>Selection</th>
                        <th>Odds</th>
                        <th>Fair</th>
                    </tr>
                </thead>
                <tbody>
{table_rows}
                </tbody>
            </table>
        </div>
'''}

        <div class="footer">
            Generated on {now_cet.strftime('%B %d, %Y %H:%M CET')} | Soccer Props Value Betting System<br>
            <small>All bets at Betsson | Odds range: 1.50 - 3.00</small>
        </div>
    </div>
</body>
</html>
'''

with open('upcoming_value.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Dashboard updated: {len(bets)} value bets')
