#!/usr/bin/env python3
"""Handle Telegram button clicks and track who placed/skipped bets."""

import json
import os
import time
import asyncio
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# Import bet manager
from bet_manager import BetManager

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESPONSES_FILE = os.path.join(SCRIPT_DIR, 'bet_responses.json')

# Validate bot token at startup
if not BOT_TOKEN:
    print("[ERROR] TELEGRAM_BOT_TOKEN not set!")
    print("Set it in .env file or Render environment settings.")
    import sys
    sys.exit(1)

# Initialize bet manager
bet_manager = BetManager()


def load_responses():
    """Load bet responses from file."""
    try:
        if os.path.exists(RESPONSES_FILE):
            with open(RESPONSES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}


def save_responses(responses):
    """Save bet responses to file."""
    with open(RESPONSES_FILE, 'w', encoding='utf-8') as f:
        json.dump(responses, f, indent=2, ensure_ascii=False)


def get_user_display(user):
    """Get display name for user."""
    if user.get('username'):
        return f"@{user['username']}"
    elif user.get('first_name'):
        return user['first_name']
    else:
        return f"User {user['id']}"


def update_message_with_responses(chat_id, message_id, original_text, bet_id, responses):
    """Update the message to show who responded (Danish)."""
    bet_responses = responses.get(str(bet_id), {'placed': [], 'skipped': []})

    placed = bet_responses.get('placed', [])
    skipped = bet_responses.get('skipped', [])

    # Build response summary (Danish)
    summary = "\n\n─────────────────"
    if placed:
        summary += f"\n✅ Spillet ({len(placed)}): " + ", ".join(placed)
    if skipped:
        summary += f"\n❌ Droppet ({len(skipped)}): " + ", ".join(skipped)
    if not placed and not skipped:
        summary += "\n⏳ Ingen svar endnu"

    # Keyboard (Danish)
    keyboard = {
        'inline_keyboard': [
            [
                {'text': f'✅ Spillet ({len(placed)})', 'callback_data': f'placed_{bet_id}'},
                {'text': f'❌ Droppet ({len(skipped)})', 'callback_data': f'skipped_{bet_id}'}
            ]
        ]
    }

    # Update message
    try:
        httpx.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/editMessageText',
            json={
                'chat_id': chat_id,
                'message_id': message_id,
                'text': original_text + summary,
                'parse_mode': 'HTML',
                'reply_markup': keyboard
            },
            timeout=10
        )
    except Exception as e:
        print(f"[ERROR] Failed to update message: {e}")


def handle_callback(callback_query, responses):
    """Handle a button click callback."""
    callback_id = callback_query['id']
    data = callback_query.get('data', '')
    user = callback_query['from']
    message = callback_query.get('message', {})
    chat_id = message.get('chat', {}).get('id')
    message_id = message.get('message_id')
    original_text = message.get('text', '')

    # Remove old response summary from text
    if "─────────────────" in original_text:
        original_text = original_text.split("─────────────────")[0].strip()

    user_display = get_user_display(user)

    # Parse callback data
    if data.startswith('placed_'):
        bet_id = data.replace('placed_', '')
        action = 'placed'
    elif data.startswith('skipped_'):
        bet_id = data.replace('skipped_', '')
        action = 'skipped'
    else:
        # Answer callback and return
        httpx.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery',
            json={'callback_query_id': callback_id, 'text': 'Unknown action'}
        )
        return

    # Initialize bet in responses
    if bet_id not in responses:
        responses[bet_id] = {'placed': [], 'skipped': [], 'bet_info': original_text[:100]}

    bet_data = responses[bet_id]

    # Remove user from other list if present
    if user_display in bet_data['placed']:
        bet_data['placed'].remove(user_display)
    if user_display in bet_data['skipped']:
        bet_data['skipped'].remove(user_display)

    # Add to new list
    bet_data[action].append(user_display)

    # Save locally
    save_responses(responses)

    # Update Firebase via BetManager if this is a Firebase key (starts with -)
    if bet_id.startswith('-'):
        try:
            if action == 'placed':
                asyncio.run(bet_manager.mark_played(bet_id, str(user.get('id', ''))))
                print(f"  [FIREBASE] Marked {bet_id} as played")
            else:
                asyncio.run(bet_manager.mark_skipped(bet_id, str(user.get('id', ''))))
                print(f"  [FIREBASE] Marked {bet_id} as skipped")
        except Exception as e:
            print(f"  [FIREBASE ERROR] {e}")

    # Answer callback (Danish)
    if action == "placed":
        response_text = "✅ Markeret som spillet!"
    else:
        response_text = "❌ Markeret som droppet!"
    httpx.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery',
        json={
            'callback_query_id': callback_id,
            'text': response_text
        }
    )

    # Update message
    update_message_with_responses(chat_id, message_id, original_text, bet_id, responses)

    print(f"[CLICK] {user_display} {action} bet #{bet_id}")


def main():
    print("="*50)
    print("TELEGRAM BUTTON HANDLER")
    print("Listening for button clicks...")
    print("="*50)

    responses = load_responses()
    last_update_id = 0

    while True:
        try:
            # Long poll for updates
            r = httpx.get(
                f'https://api.telegram.org/bot{BOT_TOKEN}/getUpdates',
                params={
                    'offset': last_update_id + 1,
                    'timeout': 30,
                    'allowed_updates': ['callback_query']
                },
                timeout=35
            )

            data = r.json()

            if data.get('ok') and data.get('result'):
                for update in data['result']:
                    last_update_id = update['update_id']

                    if 'callback_query' in update:
                        handle_callback(update['callback_query'], responses)

        except httpx.TimeoutException:
            pass  # Normal timeout, continue polling
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
