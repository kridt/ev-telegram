#!/usr/bin/env python3
"""View and update bet results from history."""

import json
import os
from datetime import datetime

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bet_history.json')


def load_history():
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []


def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def show_stats(history):
    """Show overall statistics."""
    total = len(history)
    pending = sum(1 for b in history if b['result'] is None)
    wins = sum(1 for b in history if b['result'] == 'win')
    losses = sum(1 for b in history if b['result'] == 'loss')

    if wins + losses > 0:
        win_rate = wins / (wins + losses) * 100
        total_profit = sum(b['profit'] or 0 for b in history)
        total_staked = sum(b['stake'] for b in history if b['result'] in ['win', 'loss'])
        roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
    else:
        win_rate = 0
        total_profit = 0
        roi = 0

    print("\n" + "="*50)
    print("📊 BET HISTORY STATS")
    print("="*50)
    print(f"Total bets:     {total}")
    print(f"Pending:        {pending}")
    print(f"Wins:           {wins}")
    print(f"Losses:         {losses}")
    print(f"Win rate:       {win_rate:.1f}%")
    print(f"Total profit:   ${total_profit:.2f}")
    print(f"ROI:            {roi:.1f}%")
    print("="*50)


def show_pending(history):
    """Show bets awaiting results."""
    pending = [b for b in history if b['result'] is None]

    if not pending:
        print("\n✅ No pending bets!")
        return

    print(f"\n📋 PENDING BETS ({len(pending)})")
    print("-"*70)

    for bet in pending:
        kickoff = bet['kickoff'][:16].replace('T', ' ') if bet['kickoff'] else 'TBD'
        print(f"#{bet['id']:3} | {bet['bookmaker']:10} | {bet['odds']:.2f} | {bet['selection'][:20]:20} | {kickoff}")

    print("-"*70)


def show_all(history):
    """Show all bets."""
    print(f"\n📋 ALL BETS ({len(history)})")
    print("-"*80)

    for bet in history[-20:]:  # Last 20
        result_icon = {"win": "✅", "loss": "❌", "push": "🔄", "void": "⚪"}.get(bet['result'], "⏳")
        profit_str = f"${bet['profit']:+.2f}" if bet['profit'] is not None else "---"
        print(f"#{bet['id']:3} {result_icon} | {bet['bookmaker']:10} | {bet['odds']:.2f} | {bet['selection'][:20]:20} | {profit_str}")

    print("-"*80)


def update_result(history, bet_id, result):
    """Update a bet's result."""
    for bet in history:
        if bet['id'] == bet_id:
            bet['result'] = result
            stake = bet['stake']
            odds = bet['odds']

            if result == 'win':
                bet['profit'] = round(stake * (odds - 1), 2)
            elif result == 'loss':
                bet['profit'] = -stake
            elif result in ['push', 'void']:
                bet['profit'] = 0

            save_history(history)
            print(f"✅ Updated bet #{bet_id}: {result} (profit: ${bet['profit']:.2f})")
            return

    print(f"❌ Bet #{bet_id} not found")


def main():
    history = load_history()

    if not history:
        print("No bet history yet.")
        return

    print("\n🎰 BET HISTORY MANAGER")
    print("Commands: stats, pending, all, win <id>, loss <id>, push <id>, quit")

    show_stats(history)
    show_pending(history)

    while True:
        try:
            cmd = input("\n> ").strip().lower()

            if cmd == 'quit' or cmd == 'q':
                break
            elif cmd == 'stats':
                show_stats(history)
            elif cmd == 'pending':
                show_pending(history)
            elif cmd == 'all':
                show_all(history)
            elif cmd.startswith('win '):
                bet_id = int(cmd.split()[1])
                update_result(history, bet_id, 'win')
            elif cmd.startswith('loss '):
                bet_id = int(cmd.split()[1])
                update_result(history, bet_id, 'loss')
            elif cmd.startswith('push '):
                bet_id = int(cmd.split()[1])
                update_result(history, bet_id, 'push')
            else:
                print("Unknown command. Try: stats, pending, all, win <id>, loss <id>")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
