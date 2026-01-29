"""Discord API message fetcher for importing real Discord messages.

This module provides functionality to fetch messages directly from Discord's API
and save them in JSONL format for ingestion by the summarizer.

Requirements:
    pip install discord.py

Usage:
    fetcher = DiscordFetcher(token="your_bot_token")
    await fetcher.fetch_to_jsonl(
        guild_id="123456789",
        channel_ids=["987654321"],
        output_path="discord_export.jsonl",
    )
"""

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import discord
except ImportError:
    raise ImportError(
        "discord.py is required for Discord integration. "
        "Install it with: pip install discord.py"
    )

from src.core.events import EventBus


async def _fetch_messages_task(
    token: str,
    guild_id: str,
    channel_ids: list[str],
    output_path: str | Path,
    after: Optional[datetime] = None,
    before: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> int:
    """Internal async task to fetch messages from Discord.

    Args:
        token: Discord bot token
        guild_id: Discord server (guild) ID
        channel_ids: List of channel IDs to fetch from
        output_path: Path to output JSONL file
        after: Only fetch messages after this datetime
        before: Only fetch messages before this datetime
        limit: Maximum number of messages per channel (None = no limit)

    Returns:
        Number of messages fetched

    Raises:
        ValueError: If guild_id or channel_ids is empty
        discord.DiscordException: If Discord API call fails
    """
    if not guild_id:
        raise ValueError("guild_id cannot be empty")
    if not channel_ids:
        raise ValueError("channel_ids cannot be empty")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Use a mutable list to track messages fetched
    messages_counter = [0]

    # Define intents
    intents = discord.Intents(
        guilds=True,
        messages=True,
        message_content=True,
    )

    # Create client
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        """Called when the bot is ready."""
        try:
            # Get the guild
            guild = client.get_guild(int(guild_id))
            if not guild:
                print(f"Error: Guild not found: {guild_id}")
                await client.close()
                return

            # Fetch messages from channels
            with open(output_path, "w", encoding="utf-8") as f:
                for channel_id in channel_ids:
                    # Get the channel
                    channel = guild.get_channel(int(channel_id))
                    if not channel:
                        print(f"Warning: Channel {channel_id} not found, skipping...")
                        continue

                    if not isinstance(channel, discord.abc.Messageable):
                        print(f"Warning: Channel {channel_id} is not messageable, skipping...")
                        continue

                    channel_name = channel.name
                    msg_count = 0

                    # Fetch messages
                    async for message in channel.history(
                        after=after,
                        before=before,
                        limit=limit,
                    ):
                        # Skip messages without content (e.g., join/leave notifications)
                        if not message.content and not message.attachments:
                            continue

                        # Convert to dict
                        msg_dict = {
                            "id": str(message.id),
                            "type": message.type.value,
                            "content": message.content,
                            "channel_id": str(message.channel.id),
                            "author": {
                                "id": str(message.author.id),
                                "username": message.author.name,
                                "global_name": message.author.global_name,
                                "discriminator": message.author.discriminator,
                                "bot": message.author.bot,
                                "avatar": str(message.author.avatar) if message.author.avatar else None,
                            },
                            "timestamp": message.created_at.isoformat(),
                            "edited_timestamp": message.edited_at.isoformat() if message.edited_at else None,
                            "attachments": [
                                {
                                    "id": str(att.id),
                                    "filename": att.filename,
                                    "description": att.description,
                                    "content_type": att.content_type,
                                    "size": att.size,
                                    "url": att.url,
                                    "proxy_url": att.proxy_url,
                                    "height": att.height,
                                    "width": att.width,
                                    "ephemeral": att.ephemeral,
                                }
                                for att in message.attachments
                            ],
                            "embeds": [],
                            "reactions": [
                                {
                                    "emoji": {"name": str(r.emoji), "id": str(r.emoji.id) if hasattr(r.emoji, 'id') and r.emoji.id else None},
                                    "count": r.count,
                                    "me": r.me,
                                }
                                for r in message.reactions
                            ],
                            "message_reference": {
                                "message_id": str(message.reference.message_id) if message.reference and message.reference.message_id else None,
                                "channel_id": str(message.reference.channel_id) if message.reference and message.reference.channel_id else None,
                                "guild_id": str(message.reference.guild_id) if message.reference and message.reference.guild_id else None,
                            } if message.reference else None,
                            "guild_id": str(message.guild.id) if message.guild else None,
                            "mentions": [],
                            "mention_roles": [],
                            "pinned": message.pinned,
                        }

                        # Add channel_name to the dict for our use
                        msg_dict["_channel_name"] = channel_name

                        f.write(json.dumps(msg_dict, ensure_ascii=False) + "\n")
                        msg_count += 1
                        messages_counter[0] += 1

                print(f"✓ Fetched {messages_counter[0]} messages from #{channel_name}")

        finally:
            await client.close()

    # Start the bot
    await client.start(token)

    return messages_counter[0]


async def _list_channels_task(token: str, guild_id: str) -> list[dict]:
    """Internal async task to list channels in a guild.

    Args:
        token: Discord bot token
        guild_id: Discord server (guild) ID

    Returns:
        List of dicts with channel info: {id, name, topic, position}
    """
    if not guild_id:
        raise ValueError("guild_id cannot be empty")

    # Define intents
    intents = discord.Intents(
        guilds=True,
        messages=True,
        message_content=True,
    )

    # Create client
    client = discord.Client(intents=intents)

    channels_result = []

    @client.event
    async def on_ready():
        """Called when the bot is ready."""
        try:
            # Get the guild
            guild = client.get_guild(int(guild_id))
            if not guild:
                print(f"Error: Guild not found: {guild_id}")
                await client.close()
                return

            # List all text channels
            for channel in guild.text_channels:
                channels_result.append({
                    "id": str(channel.id),
                    "name": channel.name,
                    "topic": channel.topic,
                    "position": channel.position,
                    "nsfw": channel.is_nsfw(),
                })

        finally:
            await client.close()

    # Start the bot
    await client.start(token)

    return channels_result


async def _post_message_task(token: str, channel_id: str, message: str) -> bool:
    """Internal async task to post a message to Discord.

    Args:
        token: Discord bot token
        channel_id: Channel ID to post to
        message: Message content to post

    Returns:
        True if successful, False otherwise
    """
    if not channel_id:
        raise ValueError("channel_id cannot be empty")
    if not message:
        raise ValueError("message cannot be empty")

    # Define intents
    intents = discord.Intents(
        guilds=True,
        messages=True,
        message_content=True,
    )

    # Create client
    client = discord.Client(intents=intents)

    result = {"success": False, "error": None}

    @client.event
    async def on_ready():
        """Called when the bot is ready."""
        try:
            # Get the channel
            channel = client.get_channel(int(channel_id))
            if not channel:
                result["error"] = f"Channel {channel_id} not found"
                await client.close()
                return

            if not isinstance(channel, discord.abc.Messageable):
                result["error"] = f"Channel {channel_id} is not messageable"
                await client.close()
                return

            # Send the message
            await channel.send(message)
            result["success"] = True
            print(f"✓ Posted summary to #{channel.name}")

        except Exception as e:
            result["error"] = str(e)
            print(f"✗ Error posting message: {e}")

        finally:
            await client.close()

    # Start the bot
    await client.start(token)

    return result["success"]


def fetch_messages_sync(
    token: str,
    guild_id: str,
    channel_ids: list[str],
    output_path: str | Path,
    after: Optional[datetime] = None,
    before: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> int:
    """Synchronous wrapper for fetching Discord messages.

    This is a convenience function that runs the async fetch_to_jsonl
    in an event loop, making it easier to call from synchronous code.

    Args:
        token: Discord bot token
        guild_id: Discord server (guild) ID
        channel_ids: List of channel IDs to fetch from
        output_path: Path to output JSONL file
        after: Only fetch messages after this datetime
        before: Only fetch messages before this datetime
        limit: Maximum number of messages per channel (None = no limit)

    Returns:
        Number of messages fetched

    Example:
        >>> from datetime import datetime, timedelta
        >>> messages = fetch_messages_sync(
        ...     token="your_bot_token",
        ...     guild_id="123456789",
        ...     channel_ids=["987654321"],
        ...     output_path="export.jsonl",
        ...     after=datetime.now() - timedelta(days=7),
        ... )
        >>> print(f"Fetched {messages} messages")
    """
    return asyncio.run(_fetch_messages_task(
        token=token,
        guild_id=guild_id,
        channel_ids=channel_ids,
        output_path=output_path,
        after=after,
        before=before,
        limit=limit,
    ))


def list_channels_sync(token: str, guild_id: str) -> list[dict]:
    """Synchronous wrapper for listing Discord channels.

    Args:
        token: Discord bot token
        guild_id: Discord server (guild) ID

    Returns:
        List of dicts with channel info

    Example:
        >>> channels = list_channels_sync(
        ...     token="your_bot_token",
        ...     guild_id="123456789",
        ... )
        >>> for ch in channels:
        ...     print(f"#{ch['name']} ({ch['id']})")
    """
    return asyncio.run(_list_channels_task(
        token=token,
        guild_id=guild_id,
    ))


def post_message_sync(token: str, channel_id: str, message: str) -> bool:
    """Synchronous wrapper for posting a message to Discord.

    Args:
        token: Discord bot token
        channel_id: Channel ID to post to
        message: Message content to post

    Returns:
        True if successful, False otherwise

    Example:
        >>> success = post_message_sync(
        ...     token="your_bot_token",
        ...     channel_id="123456789",
        ...     message="Hello from the summarizer!"
        ... )
        >>> print(f"Posted: {success}")
    """
    return asyncio.run(_post_message_task(
        token=token,
        channel_id=channel_id,
        message=message,
    ))
