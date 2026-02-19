#!/usr/bin/env python3
"""
Standalone test script for discord.py-self.

Usage:
    1. Get your Discord user token (browser DevTools → Network tab → any request → Authorization header)
    2. Run: DISCORD_TOKEN=your_token python scripts/test_discord_selfbot.py

Optional env vars:
    DISCORD_CHANNEL_ID  — specific channel to read history from
    DISCORD_SERVER_ID   — specific server to list channels from
"""

from __future__ import annotations

import asyncio
import os
import sys


async def main():
    try:
        import discord
    except ImportError:
        print("discord.py-self not installed. Install with:")
        print("  uv pip install discord.py-self")
        sys.exit(1)

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("Set DISCORD_TOKEN env var to your Discord user token.")
        print()
        print("To get your token:")
        print("  1. Open Discord in a browser (discord.com/app)")
        print("  2. Open DevTools (F12) → Network tab")
        print("  3. Do anything (switch channels, send a message)")
        print("  4. Find any request to discord.com/api → Headers → Authorization")
        print("  5. Copy that value")
        sys.exit(1)

    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    server_id = os.environ.get("DISCORD_SERVER_ID")

    client = discord.Client()

    @client.event
    async def on_ready():
        print(f"Logged in as: {client.user} (id: {client.user.id})")
        print(f"Servers: {len(client.guilds)}")
        print()

        # List servers
        for guild in client.guilds:
            print(f"  [{guild.id}] {guild.name} ({guild.member_count} members)")
        print()

        # If server_id given, list its channels
        if server_id:
            guild = client.get_guild(int(server_id))
            if guild:
                print(f"Channels in {guild.name}:")
                for ch in guild.text_channels:
                    print(f"  [{ch.id}] #{ch.name} (category: {ch.category})")
                print()
            else:
                print(f"Server {server_id} not found (not a member?)")

        # If channel_id given, read recent messages
        if channel_id:
            channel = client.get_channel(int(channel_id))
            if channel:
                print(f"Last 10 messages in #{channel.name}:")
                print("-" * 60)
                messages = []
                async for msg in channel.history(limit=10):
                    messages.append(msg)

                # Print oldest first
                for msg in reversed(messages):
                    reactions = ""
                    if msg.reactions:
                        reactions = " " + " ".join(
                            f"[{r.emoji} x{r.count}]" for r in msg.reactions
                        )
                    print(f"  {msg.created_at:%H:%M} {msg.author.display_name}: {msg.content[:200]}{reactions}")
                    # Show the message URL format
                    if msg.guild:
                        print(f"         -> https://discord.com/channels/{msg.guild.id}/{msg.channel.id}/{msg.id}")
                print("-" * 60)
            else:
                print(f"Channel {channel_id} not found (no access?)")

        print()
        print("Done. Closing connection.")
        await client.close()

    try:
        await client.start(token)
    except discord.LoginFailure:
        print("ERROR: Invalid token. Check your DISCORD_TOKEN value.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
