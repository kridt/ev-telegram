#!/usr/bin/env python3
"""Server for live dashboard with admin controls."""

import http.server
import json
import os
import httpx
from urllib.parse import urlparse, parse_qs

PORT = 8888
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
API_KEY = os.environ.get("OPTICODDS_API_KEY", "")
API_BASE = "https://api.opticodds.com/api/v3"


def load_json(filename):
    """Load JSON file."""
    try:
        path = os.path.join(SCRIPT_DIR, filename)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return [] if 'history' in filename or 'queue' in filename else {}


def save_json(filename, data):
    """Save JSON file."""
    path = os.path.join(SCRIPT_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def send_telegram_message(text, reply_markup=None):
    """Send a new Telegram message."""
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10
        )
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def update_bet_result(bet_id, result):
    """Update a bet's result and notify Telegram."""
    history = load_json('bet_history.json')

    for bet in history:
        if bet['id'] == bet_id:
            bet['result'] = result
            stake = bet.get('stake', 10)
            odds = bet.get('odds', 1)

            if result == 'win':
                bet['profit'] = round(stake * (odds - 1), 2)
                emoji = "✅"
                result_text = "WON"
            elif result == 'loss':
                bet['profit'] = -stake
                emoji = "❌"
                result_text = "LOST"
            elif result == 'push':
                bet['profit'] = 0
                emoji = "🔄"
                result_text = "PUSH"
            elif result == 'void':
                bet['profit'] = 0
                emoji = "⚪"
                result_text = "VOID"
            else:
                bet['profit'] = None
                emoji = "⏳"
                result_text = "PENDING"

            save_json('bet_history.json', history)

            # Send result notification to Telegram
            profit_str = f"+${bet['profit']:.2f}" if bet['profit'] and bet['profit'] > 0 else f"${bet['profit']:.2f}" if bet['profit'] else ""

            msg = f"""{emoji} <b>BET #{bet_id} {result_text}</b> {emoji}

⚽ {bet['fixture']}
🎯 {bet['market']} - {bet['selection']}
💰 Odds: {bet['odds']:.2f} @ {bet['bookmaker']}

{f"Profit: <b>{profit_str}</b>" if profit_str else ""}"""

            send_telegram_message(msg)

            return {"ok": True, "bet": bet}

    return {"ok": False, "error": "Bet not found"}


def send_custom_message(text):
    """Send a custom message to Telegram."""
    return send_telegram_message(text)


def get_fixture_results(fixture_name):
    """Try to get fixture results from API."""
    try:
        # Extract team names from fixture
        teams = fixture_name.split(' vs ')
        if len(teams) != 2:
            return None

        home_team = teams[0].strip().lower()
        away_team = teams[1].strip().lower()

        # Get completed fixtures from API
        r = httpx.get(
            f"{API_BASE}/fixtures",
            params={"sport": "soccer", "status": "completed"},
            headers={"x-api-key": API_KEY},
            timeout=15
        )

        if r.status_code == 200:
            data = r.json()
            fixtures = data.get("data", [])

            for fix in fixtures:
                # Check if this is the right fixture
                fix_home = (fix.get("home_team_display") or "").lower()
                fix_away = (fix.get("away_team_display") or "").lower()

                # Match if team names are contained in fixture names
                home_match = home_team in fix_home or fix_home in home_team
                away_match = away_team in fix_away or fix_away in away_team

                if home_match and away_match:
                    print(f"[INFO] Found fixture: {fix.get('home_team_display')} vs {fix.get('away_team_display')}")
                    return fix

        return None
    except Exception as e:
        print(f"[ERROR] Failed to get fixture results: {e}")
        return None


def get_fixture_stats(fixture_id):
    """Get detailed stats for a fixture."""
    try:
        r = httpx.get(
            f"{API_BASE}/fixtures/{fixture_id}/stats",
            headers={"x-api-key": API_KEY},
            timeout=15
        )

        if r.status_code == 200:
            return r.json().get("data", {})
        return None
    except Exception as e:
        print(f"[ERROR] Failed to get fixture stats: {e}")
        return None


def check_bet_result(bet, fixture_data, stats_data):
    """Check if a bet won or lost based on fixture data."""
    try:
        market = bet.get("market", "").lower()
        selection = bet.get("selection", "").lower()

        # Parse the selection to get over/under and the line
        is_over = "over" in selection
        is_under = "under" in selection

        # Extract the number from selection (e.g., "Over 9.5" -> 9.5)
        import re
        numbers = re.findall(r'[\d.]+', selection)
        if not numbers:
            return None
        line = float(numbers[0])

        # Get the actual stat value based on market
        actual_value = None

        if stats_data:
            stats = stats_data

            if "corner" in market:
                # Total corners
                home_corners = stats.get("home", {}).get("corners", 0) or 0
                away_corners = stats.get("away", {}).get("corners", 0) or 0
                actual_value = home_corners + away_corners

            elif "shot" in market and "target" in market:
                # Shots on target
                home_sot = stats.get("home", {}).get("shots_on_target", 0) or 0
                away_sot = stats.get("away", {}).get("shots_on_target", 0) or 0
                actual_value = home_sot + away_sot

            elif "shot" in market:
                # Total shots
                home_shots = stats.get("home", {}).get("shots", 0) or 0
                away_shots = stats.get("away", {}).get("shots", 0) or 0
                actual_value = home_shots + away_shots

        # If we couldn't get stats, try from fixture scores
        if actual_value is None and fixture_data:
            # For goals markets
            if "goal" in market or "handicap" in market.lower():
                home_score = fixture_data.get("home_score", 0) or 0
                away_score = fixture_data.get("away_score", 0) or 0
                actual_value = home_score + away_score

        if actual_value is None:
            return None

        # Determine win/loss
        if is_over:
            if actual_value > line:
                return "win"
            elif actual_value < line:
                return "loss"
            else:
                return "push"
        elif is_under:
            if actual_value < line:
                return "win"
            elif actual_value > line:
                return "loss"
            else:
                return "push"

        return None

    except Exception as e:
        print(f"[ERROR] Failed to check bet result: {e}")
        return None


def auto_settle_bets():
    """Auto-settle pending bets by checking results."""
    history = load_json('bet_history.json')
    results = {
        "settled": [],
        "manual_needed": [],
        "not_finished": []
    }

    for bet in history:
        if bet.get("result") is not None:
            continue  # Already settled

        # Check if match should be finished (kickoff + 3 hours)
        kickoff = bet.get("kickoff", "")
        if kickoff:
            try:
                from datetime import datetime, timezone, timedelta
                kick_dt = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)

                if now < kick_dt + timedelta(hours=2.5):
                    results["not_finished"].append({
                        "id": bet["id"],
                        "fixture": bet["fixture"],
                        "reason": "Match not finished yet"
                    })
                    continue
            except:
                pass

        # Try to get fixture results
        fixture_data = get_fixture_results(bet.get("fixture", ""))

        if not fixture_data:
            results["manual_needed"].append({
                "id": bet["id"],
                "fixture": bet["fixture"],
                "reason": "Could not find fixture results"
            })
            continue

        # Get stats
        stats_data = get_fixture_stats(fixture_data.get("id")) if fixture_data else None

        # Check bet result
        result = check_bet_result(bet, fixture_data, stats_data)

        if result:
            # Auto-settle
            update_bet_result(bet["id"], result)
            results["settled"].append({
                "id": bet["id"],
                "fixture": bet["fixture"],
                "result": result
            })
        else:
            results["manual_needed"].append({
                "id": bet["id"],
                "fixture": bet["fixture"],
                "market": bet.get("market"),
                "selection": bet.get("selection"),
                "reason": "Could not determine result from stats"
            })

    return results


def get_stats():
    """Calculate detailed stats."""
    history = load_json('bet_history.json')
    responses = load_json('bet_responses.json')

    total = len(history)
    wins = sum(1 for b in history if b.get('result') == 'win')
    losses = sum(1 for b in history if b.get('result') == 'loss')
    pending = sum(1 for b in history if b.get('result') is None)
    total_profit = sum(b.get('profit', 0) or 0 for b in history)
    total_staked = sum(b.get('stake', 10) for b in history if b.get('result') in ['win', 'loss'])

    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0

    # By bookmaker
    by_bookmaker = {}
    for bet in history:
        book = bet.get('bookmaker', 'Unknown')
        if book not in by_bookmaker:
            by_bookmaker[book] = {'bets': 0, 'wins': 0, 'profit': 0}
        by_bookmaker[book]['bets'] += 1
        if bet.get('result') == 'win':
            by_bookmaker[book]['wins'] += 1
        by_bookmaker[book]['profit'] += bet.get('profit', 0) or 0

    total_placed = sum(len(r.get('placed', [])) for r in responses.values())
    total_skipped = sum(len(r.get('skipped', [])) for r in responses.values())

    return {
        'total_bets': total,
        'wins': wins,
        'losses': losses,
        'pending': pending,
        'win_rate': round(win_rate, 1),
        'total_profit': round(total_profit, 2),
        'roi': round(roi, 1),
        'by_bookmaker': by_bookmaker,
        'total_placed': total_placed,
        'total_skipped': total_skipped,
        'pending_in_queue': len(load_json('pending_queue.json'))
    }


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SCRIPT_DIR, **kwargs)

    def send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == '/api/data':
            data = {
                'bets': load_json('bet_history.json'),
                'responses': load_json('bet_responses.json'),
                'pending_queue': load_json('pending_queue.json'),
                'stats': get_stats()
            }
            self.send_json_response(data)
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length else '{}'

        try:
            data = json.loads(body) if body else {}
        except:
            data = {}

        if parsed.path == '/api/result':
            # Mark bet as win/loss/push/void
            bet_id = data.get('bet_id')
            result = data.get('result')  # win, loss, push, void, null (to clear)

            if bet_id is None:
                self.send_json_response({'ok': False, 'error': 'bet_id required'}, 400)
                return

            response = update_bet_result(int(bet_id), result)
            self.send_json_response(response)
            return

        elif parsed.path == '/api/message':
            # Send custom message
            text = data.get('text', '')
            if not text:
                self.send_json_response({'ok': False, 'error': 'text required'}, 400)
                return

            response = send_telegram_message(text)
            self.send_json_response(response)
            return

        elif parsed.path == '/api/broadcast':
            # Broadcast stats summary
            stats = get_stats()
            msg = f"""📊 <b>DAILY STATS</b> 📊

Total bets: {stats['total_bets']}
✅ Wins: {stats['wins']} | ❌ Losses: {stats['losses']}
📈 Win rate: {stats['win_rate']}%

💰 Profit: <b>${stats['total_profit']:.2f}</b>
📊 ROI: {stats['roi']}%"""

            response = send_telegram_message(msg)
            self.send_json_response(response)
            return

        elif parsed.path == '/api/auto-settle':
            # Auto-settle pending bets
            results = auto_settle_bets()
            self.send_json_response({
                "ok": True,
                "settled": results["settled"],
                "manual_needed": results["manual_needed"],
                "not_finished": results["not_finished"]
            })
            return

        elif parsed.path == '/api/auto-settle-single':
            # Auto-settle a single bet
            bet_id = data.get('bet_id')
            if bet_id is None:
                self.send_json_response({'ok': False, 'error': 'bet_id required'}, 400)
                return

            history = load_json('bet_history.json')
            bet = next((b for b in history if b['id'] == int(bet_id)), None)

            if not bet:
                self.send_json_response({'ok': False, 'error': 'Bet not found'}, 404)
                return

            if bet.get('result') is not None:
                self.send_json_response({'ok': False, 'error': 'Bet already settled', 'result': bet['result']})
                return

            # Check if match should be finished (kickoff + 2 hours)
            kickoff = bet.get("kickoff", "")
            if kickoff:
                try:
                    from datetime import datetime, timezone, timedelta
                    kick_dt = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    if now < kick_dt + timedelta(hours=2):
                        time_left = kick_dt + timedelta(hours=2) - now
                        hours_left = time_left.total_seconds() / 3600
                        self.send_json_response({
                            'ok': False,
                            'error': f'Match not finished yet (~{hours_left:.1f}h remaining)',
                            'not_finished': True
                        })
                        return
                except Exception as e:
                    print(f"[WARN] Could not parse kickoff: {e}")

            # Try to get fixture results
            fixture_data = get_fixture_results(bet.get("fixture", ""))

            if not fixture_data:
                self.send_json_response({
                    'ok': False,
                    'error': 'Could not find fixture results',
                    'manual': True
                })
                return

            # Get stats
            stats_data = get_fixture_stats(fixture_data.get("id")) if fixture_data else None

            # Check bet result
            result = check_bet_result(bet, fixture_data, stats_data)

            if result:
                update_bet_result(int(bet_id), result)
                self.send_json_response({
                    'ok': True,
                    'result': result,
                    'message': f'Bet #{bet_id} settled as {result.upper()}'
                })
            else:
                self.send_json_response({
                    'ok': False,
                    'error': 'Could not determine result from stats',
                    'manual': True
                })
            return

        self.send_json_response({'ok': False, 'error': 'Unknown endpoint'}, 404)


def main():
    print(f"🌐 Dashboard running at http://localhost:{PORT}/live_dashboard.html")
    print("Press Ctrl+C to stop")

    with http.server.HTTPServer(('', PORT), DashboardHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
