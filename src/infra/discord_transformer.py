"""Transformation utilities for Discord API compatibility.

This module provides functions to convert between Discord's API format
and our internal MessageEvent format. This allows us to:

1. Use real Discord data structures in simulation
2. Seamlessly transition to real Discord integration later
3. Maintain backward compatibility with existing fixtures
"""

import re
from typing import Optional

from src.core.models import MessageEvent, Attachment
from src.infra.discord_models import DiscordMessage, DiscordAttachment


def extract_links(content: str) -> list[str]:
    """Extract URLs from message content.

    Args:
        content: Message text content

    Returns:
        List of URLs found in the content
    """
    # URL pattern matching http://, https://, and www.
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    return re.findall(url_pattern, content)


def discord_to_message_event(
    discord_msg: DiscordMessage,
    channel_name: str,
) -> MessageEvent:
    """Convert a Discord message to our internal MessageEvent format.

    This function transforms Discord's API structure into our normalized
    MessageEvent format. It handles all the field mappings and nested
    object flattening.

    Args:
        discord_msg: Discord message object from API
        channel_name: Channel name (not included in Discord message object)

    Returns:
        Normalized MessageEvent

    Example:
        discord_msg = DiscordMessage(**discord_api_data)
        event = discord_to_message_event(discord_msg, "dev")
        # Now 'event' can be used in our pipeline
    """
    # Extract reply information from message_reference
    reply_to_message_id: Optional[str] = None
    if discord_msg.message_reference and discord_msg.message_reference.message_id:
        reply_to_message_id = discord_msg.message_reference.message_id

    # Convert Discord attachments to our Attachment format
    attachments = [
        Attachment(
            url=att.url,
            filename=att.filename,
            content_type=att.content_type or "application/octet-stream",
        )
        for att in discord_msg.attachments
    ]

    # Extract links from content
    links = extract_links(discord_msg.content)

    # Add attachment URLs to links
    for att in discord_msg.attachments:
        if att.url not in links:
            links.append(att.url)

    return MessageEvent(
        # Field mappings
        message_id=discord_msg.id,  # Discord's 'id' -> our 'message_id'
        channel_id=discord_msg.channel_id,
        channel_name=channel_name,  # Not in Discord message, must be provided
        author_id=discord_msg.author.id,
        author_name=discord_msg.author.global_name or discord_msg.author.username,
        created_at=discord_msg.timestamp,  # Discord's 'timestamp' -> our 'created_at'

        # Direct mappings
        content=discord_msg.content,
        attachments=attachments,
        links=links,

        # Nested object flattening
        reply_to_message_id=reply_to_message_id,
    )


def message_event_to_discord(
    event: MessageEvent,
    guild_id: str,
) -> DiscordMessage:
    """Convert our MessageEvent back to Discord message format.

    This is useful for:
    - Testing Discord API calls with our data
    - Creating Discord-compatible fixtures
    - Exporting data in Discord format

    Args:
        event: Our internal MessageEvent
        guild_id: Guild ID (required for Discord format)

    Returns:
        Discord message object

    Example:
        discord_msg = message_event_to_discord(event, "123456789")
        # Can now be serialized and sent to Discord API
    """
    from src.infra.discord_models import (
        DiscordAuthor,
        DiscordAttachment,
        DiscordMessageReference,
    )

    # Create Discord author object
    author = DiscordAuthor(
        id=event.author_id,
        username=event.author_name,
        global_name=event.author_name,
        discriminator="0000",  # Default discriminator
    )

    # Create Discord attachment objects
    attachments = [
        DiscordAttachment(
            id=f"att_{i}",
            filename=att.filename,
            description=None,
            content_type=att.content_type,
            size=0,  # Unknown
            url=att.url,
            proxy_url=att.url,
            height=None,
            width=None,
            ephemeral=False,
        )
        for i, att in enumerate(event.attachments)
    ]

    # Create message reference if this is a reply
    message_reference = None
    if event.reply_to_message_id:
        message_reference = DiscordMessageReference(
            message_id=event.reply_to_message_id,
            channel_id=event.channel_id,
            guild_id=guild_id,
        )

    return DiscordMessage(
        id=event.message_id,
        content=event.content,
        channel_id=event.channel_id,
        author=author,
        timestamp=event.created_at,
        edited_timestamp=None,
        message_reference=message_reference,
        attachments=attachments,
        embeds=[],
        reactions=[],
        guild_id=guild_id,
    )


def create_discord_message(
    content: str,
    author_name: str,
    author_id: str,
    channel_id: str,
    channel_name: str,
    message_id: str,
    timestamp: str,
    reply_to: Optional[str] = None,
    attachments: Optional[list[dict]] = None,
) -> dict:
    """Create a Discord-formatted message dict for simulation.

    This function creates a dict matching Discord's API structure,
    which can be used in our simulation fixtures. When we eventually
    connect to real Discord, these will work seamlessly.

    Args:
        content: Message content
        author_name: Author's display name
        author_id: Author's snowflake ID
        channel_id: Channel snowflake ID
        channel_name: Channel name (for our internal use)
        message_id: Message snowflake ID
        timestamp: ISO8601 timestamp
        reply_to: Optional message ID this replies to
        attachments: Optional list of attachment dicts

    Returns:
        Dict matching Discord message API structure

    Example:
        msg = create_discord_message(
            content="Just pushed the fix!",
            author_name="Sarah Chen",
            author_id="123456789",
            channel_id="987654321",
            channel_name="dev",
            message_id="111111111",
            timestamp="2026-01-20T09:15:00+09:00",
        )
        # Can be used in fixtures or directly transformed
    """
    from src.infra.discord_models import DiscordAuthor, DiscordAttachment

    # Create author object
    author_data = DiscordAuthor(
        id=author_id,
        username=author_name.lower().replace(" ", "_"),
        global_name=author_name,
        discriminator="0000",
    ).model_dump()

    # Create attachment objects
    attachment_data = []
    if attachments:
        for att in attachments:
            discord_att = DiscordAttachment(
                id=att.get("id", "att_000"),
                filename=att["filename"],
                description=att.get("description"),
                content_type=att.get("content_type"),
                size=att.get("size", 0),
                url=att["url"],
                proxy_url=att["url"],
            ).model_dump()
            attachment_data.append(discord_att)

    # Create message reference if this is a reply
    message_reference = None
    if reply_to:
        message_reference = {
            "message_id": reply_to,
            "channel_id": channel_id,
            "guild_id": "guild_placeholder",  # Not used in our pipeline
        }

    # Build Discord message structure
    discord_msg = {
        "id": message_id,
        "type": 0,  # DEFAULT message type
        "content": content,
        "channel_id": channel_id,
        "author": author_data,
        "timestamp": timestamp,
        "edited_timestamp": None,
        "attachments": attachment_data,
        "embeds": [],
        "reactions": [],
        "message_reference": message_reference,
        "guild_id": "guild_placeholder",  # Not used in our pipeline
        "mentions": [],
        "mention_roles": [],
        "pinned": False,
    }

    return discord_msg


def parse_discord_message_from_dict(data: dict, channel_name: str) -> MessageEvent:
    """Parse a Discord message dict and convert to MessageEvent.

    This is a convenience function that handles the common pattern of
    loading JSON data and converting it to our internal format.

    Args:
        data: Dict matching Discord message API structure
        channel_name: Channel name (not in Discord message object)

    Returns:
        MessageEvent instance

    Example:
        data = json.loads(json_line)
        event = parse_discord_message_from_dict(data, "dev")
        db.insert_messages([event])
    """
    discord_msg = DiscordMessage(**data)
    return discord_to_message_event(discord_msg, channel_name)
