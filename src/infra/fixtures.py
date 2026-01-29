"""Fixture loader for reading JSONL test data.

Supports two formats:
1. Standard format: Our simplified MessageEvent structure
2. Discord format: Discord's actual API message structure

Auto-detects format based on field names and handles both seamlessly.
"""

import json
from pathlib import Path

from src.core.models import Attachment, MessageEvent


def _is_discord_format(data: dict) -> bool:
    """Detect if data is in Discord API format.

    Discord messages use 'id' instead of 'message_id', 'timestamp' instead
    of 'created_at', and have a nested 'author' object.

    Args:
        data: Parsed JSON data

    Returns:
        True if Discord format, False if standard format
    """
    # Discord format has 'id' field, standard format has 'message_id'
    has_id = "id" in data
    has_message_id = "message_id" in data

    # Discord format has nested 'author' object, standard has flat 'author_name'
    has_nested_author = isinstance(data.get("author"), dict)

    # Discord format has 'timestamp', standard has 'created_at'
    has_timestamp = "timestamp" in data
    has_created_at = "created_at" in data

    # If it has Discord signature fields, treat as Discord format
    if has_id and has_nested_author and has_timestamp:
        return True

    # If it has our standard fields, treat as standard format
    if has_message_id and has_created_at:
        return False

    # Default to standard format for backward compatibility
    return False


def _load_standard_format(data: dict, line_num: int) -> MessageEvent:
    """Load a message in our standard MessageEvent format.

    Args:
        data: Parsed JSON data
        line_num: Line number for error reporting

    Returns:
        MessageEvent instance
    """
    # Parse attachments
    attachments = []
    if "attachments" in data and data["attachments"]:
        for att in data["attachments"]:
            attachments.append(
                Attachment(
                    url=att["url"],
                    filename=att["filename"],
                    content_type=att["content_type"],
                )
            )

    # Parse links (may be extracted later or provided)
    links = data.get("links", [])

    return MessageEvent(
        message_id=data["message_id"],
        channel_id=data["channel_id"],
        channel_name=data["channel_name"],
        author_id=data["author_id"],
        author_name=data["author_name"],
        created_at=data["created_at"],
        content=data.get("content", ""),
        attachments=attachments,
        links=links,
        reply_to_message_id=data.get("reply_to_message_id"),
    )


def _load_discord_format(data: dict, channel_name: str, line_num: int) -> MessageEvent:
    """Load a message in Discord API format.

    Args:
        data: Parsed JSON data in Discord format
        channel_name: Channel name (not in Discord message, must be provided)
        line_num: Line number for error reporting

    Returns:
        MessageEvent instance
    """
    from src.infra.discord_transformer import parse_discord_message_from_dict

    try:
        return parse_discord_message_from_dict(data, channel_name)
    except Exception as e:
        raise ValueError(f"Error parsing Discord message on line {line_num}: {e}") from e


def _extract_channel_name_from_path(fixture_path: Path) -> str:
    """Extract channel name from fixture file path.

    Looks for patterns like:
    - discord_format_dev_2026-01-20.jsonl -> "dev"
    - fixtures/discord_format_2026-01-20.jsonl -> "general" (default)

    Args:
        fixture_path: Path to fixture file

    Returns:
        Extracted channel name or default "general"
    """
    stem = fixture_path.stem  # Filename without extension

    # Try to extract channel name from filename
    # Pattern: discord_format_<channel>_<date> or discord_format_<date>
    parts = stem.split("_")

    if len(parts) >= 4 and parts[0] == "discord" and parts[1] == "format":
        # discord_format_<channel>_<date>
        potential_channel = parts[2]
        if potential_channel not in ["2026", "2025", "2024"]:  # Not a year
            return potential_channel

    return "general"  # Default channel name


def load_fixture(fixture_path: str | Path, default_channel_name: str = "general") -> list[MessageEvent]:
    """Load messages from a JSONL fixture file.

    Auto-detects format (standard vs Discord) and handles both seamlessly.

    Args:
        fixture_path: Path to JSONL file
        default_channel_name: Default channel name for Discord format (if not in filename)

    Returns:
        List of message events

    Raises:
        FileNotFoundError: If fixture file doesn't exist
        ValueError: If fixture file has invalid format

    Examples:
        >>> # Standard format fixture
        >>> messages = load_fixture("fixtures/sample_3days.jsonl")
        >>> # Discord format fixture
        >>> messages = load_fixture("fixtures/discord_format_2026-01-20.jsonl")
    """
    path = Path(fixture_path)

    if not path.exists():
        raise FileNotFoundError(f"Fixture file not found: {fixture_path}")

    messages = []

    # For Discord format, we need a channel name
    # Try to extract from filename, otherwise use default
    discord_channel_name = _extract_channel_name_from_path(path)
    if discord_channel_name == "general":
        discord_channel_name = default_channel_name

    # Auto-detect format from first message
    detected_format = None

    with open(path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_num}: {e}") from e

            try:
                # Auto-detect format on first message
                if detected_format is None:
                    detected_format = "discord" if _is_discord_format(data) else "standard"

                if detected_format == "discord":
                    # Discord format - need to handle channel name per message
                    # Check if _channel_name was added by our fetcher
                    if "_channel_name" in data:
                        channel_name_for_message = data["_channel_name"]
                        # Remove the temporary field
                        del data["_channel_name"]
                    else:
                        channel_name_for_message = discord_channel_name

                    message = _load_discord_format(data, channel_name_for_message, line_num)
                else:
                    # Standard format
                    message = _load_standard_format(data, line_num)

                messages.append(message)

            except ValueError:
                raise
            except Exception as e:
                format_hint = f" (detected format: {detected_format})" if detected_format else ""
                raise ValueError(f"Error parsing message on line {line_num}{format_hint}: {e}") from e

    return messages
