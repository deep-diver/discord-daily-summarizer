"""Discord API-compatible message models.

This module defines data structures that match Discord's actual API format.
When we integrate with real Discord, we'll be able to use these models directly.

Discord Message Object Reference:
https://discord.com/developers/docs/resources/channel#message-object
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


class DiscordAuthor(BaseModel):
    """Discord user object (nested in message).

    Discord API Reference:
    https://discord.com/developers/docs/resources/user#user-object
    """

    id: str  # Snowflake ID
    username: str  # Username (unique)
    global_name: Optional[str] = None  # Display name
    discriminator: Optional[str] = None  # 4-digit discriminator (deprecated)
    avatar: Optional[str] = None  # Avatar hash
    bot: bool = False
    system: bool = False
    public_flags: int = 0


class DiscordAttachment(BaseModel):
    """Discord attachment object.

    Discord API Reference:
    https://discord.com/developers/docs/resources/channel#attachment-object
    """

    id: str  # Attachment snowflake
    filename: str
    description: Optional[str] = None  # Alt text
    content_type: Optional[str] = None
    size: int  # File size in bytes
    url: str
    proxy_url: str
    height: Optional[int] = None  # For images
    width: Optional[int] = None
    ephemeral: bool = False


class DiscordMessageReference(BaseModel):
    """Discord message reference for replies/forwards.

    Discord API Reference:
    https://discord.com/developers/docs/resources/channel#message-reference-object
    """

    message_id: Optional[str] = None
    channel_id: Optional[str] = None
    guild_id: Optional[str] = None
    fail_if_not_exists: bool = True


class DiscordReaction(BaseModel):
    """Discord reaction object."""

    emoji: dict[str, Any]  # Simplified emoji object
    count: int
    me: bool = False


class DiscordMessage(BaseModel):
    """Discord message object matching the actual API structure.

    This is the raw format we'll receive from Discord's API.
    We'll transform these to our internal MessageEvent format.

    Discord API Reference:
    https://discord.com/developers/docs/resources/channel#message-object

    Key differences from our MessageEvent:
    - Uses 'id' instead of 'message_id'
    - Uses nested 'author' object instead of flat 'author_name'
    - Uses 'timestamp' instead of 'created_at'
    - Uses nested 'message_reference' for replies
    - Does NOT include 'channel_name' (must be fetched separately)
    - Has many additional fields we don't use yet
    """

    # Core fields
    id: str  # Message snowflake
    type: int = 0  # Message type (DEFAULT=0, REPLY=19, etc.)
    content: str
    channel_id: str  # Channel snowflake

    # Author information (nested object)
    author: DiscordAuthor

    # Timestamps
    timestamp: str  # ISO8601 timestamp
    edited_timestamp: Optional[str] = None

    # Message threading
    message_reference: Optional[DiscordMessageReference] = None

    # Attachments and embeds
    attachments: list[DiscordAttachment] = Field(default_factory=list)
    embeds: list[dict[str, Any]] = Field(default_factory=list)

    # Reactions
    reactions: list[DiscordReaction] = Field(default_factory=list)

    # Additional Discord fields (not currently used)
    guild_id: Optional[str] = None
    member: Optional[dict[str, Any]] = None  # Member object if in guild
    mentions: list[DiscordAuthor] = Field(default_factory=list)
    mention_roles: list[str] = Field(default_factory=list)
    pinned: bool = False
    webhook_id: Optional[str] = None
    components: list[dict[str, Any]] = Field(default_factory=list)
    stickers: list[dict[str, Any]] = Field(default_factory=list)
    position: Optional[int] = None
    application_id: Optional[str] = None
    application: Optional[dict[str, Any]] = None
    activity: Optional[dict[str, Any]] = None
    flags: int = 0

    # Thread fields
    thread: Optional[dict[str, Any]] = None


class DiscordChannel(BaseModel):
    """Discord channel object.

    Discord API Reference:
    https://discord.com/developers/docs/resources/channel#channel-object
    """

    id: str  # Channel snowflake
    name: str  # Channel name (without # prefix)
    type: int  # Channel type (GUILD_TEXT=0, GUILD_VOICE=2, etc.)
    guild_id: str
    position: int
    permission_overwrites: list[dict[str, Any]] = Field(default_factory=list)
    nsfw: bool = False
    parent_id: Optional[str] = None
    rate_limit_per_user: int = 0
    topic: Optional[str] = None
