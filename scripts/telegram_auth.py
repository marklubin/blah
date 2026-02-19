#!/usr/bin/env python3
"""One-time Telegram StringSession generator.

Run this script to authenticate with Telegram and get a session string.
Store the session string in your ~/.blah/config.yaml under:

platforms:
  telegram:
    enabled: true
    telegram_api_id: <your_api_id>
    telegram_api_hash: <your_api_hash>
    telegram_session_string: <paste_session_string_here>

Get your api_id and api_hash from https://my.telegram.org/apps
"""
import sys

from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def main():
    print("Telegram Session Generator")
    print("=" * 40)
    print()
    print("Get your api_id and api_hash from https://my.telegram.org/apps")
    print()

    api_id = input("Enter your api_id: ").strip()
    api_hash = input("Enter your api_hash: ").strip()

    if not api_id or not api_hash:
        print("Error: api_id and api_hash are required")
        sys.exit(1)

    try:
        api_id = int(api_id)
    except ValueError:
        print("Error: api_id must be a number")
        sys.exit(1)

    client = TelegramClient(StringSession(), api_id, api_hash)
    client.start()

    session_string = client.session.save()
    client.disconnect()

    print()
    print("Session string generated successfully!")
    print()
    print("Add this to your ~/.blah/config.yaml:")
    print()
    print("platforms:")
    print("  telegram:")
    print("    enabled: true")
    print(f"    telegram_api_id: {api_id}")
    print(f"    telegram_api_hash: {api_hash}")
    print(f"    telegram_session_string: {session_string}")


if __name__ == "__main__":
    main()
