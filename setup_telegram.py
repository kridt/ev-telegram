#!/usr/bin/env python3
"""Setup Telegram bot and get chat ID."""

import time
import json
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

def get_updates():
    """Poll for updates from Telegram."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    response = httpx.get(url, timeout=30)
    return response.json()

def main():
    print("=" * 50)
    print("TELEGRAM SETUP")
    print("=" * 50)
    print("\nWaiting for a message in your Telegram group...")
    print("Please send any message in the group now.\n")

    chat_id = None
    attempts = 0
    max_attempts = 60  # 5 minutes max

    while chat_id is None and attempts < max_attempts:
        attempts += 1
        print(f"Polling for messages... (attempt {attempts}/{max_attempts})", end="\r")

        data = get_updates()

        if data.get("ok") and data.get("result"):
            for update in data["result"]:
                message = update.get("message") or update.get("channel_post")
                if message and "chat" in message:
                    chat = message["chat"]
                    chat_id = chat["id"]
                    chat_title = chat.get("title", "Unknown")
                    print(f"\n\nFound chat!")
                    print(f"  Title: {chat_title}")
                    print(f"  Chat ID: {chat_id}")
                    break

        if chat_id is None:
            time.sleep(5)

    if chat_id:
        # Update config
        config_path = "config/settings.json"
        try:
            with open(config_path, "r") as f:
                config = json.load(f)

            config["telegram"]["bot_token"] = BOT_TOKEN
            config["telegram"]["chat_id"] = str(chat_id)

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            print(f"\nConfig updated: {config_path}")
            print("\nTelegram setup complete!")

            # Test message
            test_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            test_response = httpx.post(test_url, json={
                "chat_id": chat_id,
                "text": "Soccer Value Bot connected successfully!",
                "parse_mode": "HTML"
            })

            if test_response.json().get("ok"):
                print("Test message sent to group!")

        except Exception as e:
            print(f"Error updating config: {e}")
            print(f"\nManually add to config/settings.json:")
            print(f'  "bot_token": "{BOT_TOKEN}"')
            print(f'  "chat_id": "{chat_id}"')
    else:
        print("\n\nTimeout waiting for messages.")
        print("Make sure:")
        print("1. Group Privacy Mode is OFF in BotFather")
        print("2. Bot is admin in the group")
        print("3. Send a message in the group")

if __name__ == "__main__":
    main()
