"""Input validation utilities for security."""

import re
import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, validator, EmailStr
from enum import Enum


class ValidationError(Exception):
    """Custom validation error."""
    pass


class ChannelName(str):
    """Validated channel name."""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            raise ValidationError("Channel name must be a string")
        if not v.startswith('#'):
            v = '#' + v

        # Channel name validation rules
        if len(v) > 100:
            raise ValidationError("Channel name too long (max 100 chars)")
        if not re.match(r'^#[a-zA-Z0-9_-]+$', v[1:]):
            raise ValidationError("Channel name can only contain letters, numbers, underscores, and hyphens")
        return v.lower()


class DateRange(str):
    """Validated date range format (YYYY-MM-DD)."""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            raise ValidationError("Date must be a string")

        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValidationError("Date must be in YYYY-MM-DD format")
        return v


class HoursRange(int):
    """Validated hours range (1-168)."""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, int):
            raise ValidationError("Hours must be an integer")
        if v < 1 or v > 168:  # 1 week max
            raise ValidationError("Hours must be between 1 and 168")
        return v


class ApiKey(str):
    """Validated API key format."""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            raise ValidationError("API key must be a string")
        if len(v) < 16:
            raise ValidationError("API key too short (min 16 chars)")
        if not re.match(r'^[a-zA-Z0-9\-_]+$', v):
            raise ValidationError("API key contains invalid characters")
        return v


class MessageContent(str):
    """Validated message content."""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            raise ValidationError("Message content must be a string")
        if len(v) > 4000:
            raise ValidationError("Message content too long (max 4000 chars)")
        return v


def _is_discord_format(item: Dict) -> bool:
    """Check if item is in Discord API format."""
    # Discord format has 'id' (not 'message_id'), nested 'author', and 'timestamp'
    return (
        "id" in item and
        isinstance(item.get("author"), dict) and
        "timestamp" in item
    )


def validate_jsonl_data(data: Any) -> List[Dict]:
    """Validate JSONL data structure.

    Supports both:
    - Standard format: author_name, created_at, content, channel_name
    - Discord format: id, author (nested), timestamp, content
    """
    if not isinstance(data, list):
        raise ValidationError("JSONL data must be a list")

    if not data:
        return []  # Empty list is valid

    # Detect format from first item
    first_item = data[0]
    is_discord = _is_discord_format(first_item)

    validated_data = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValidationError(f"Item {i} must be an object")

        if is_discord:
            # Discord format validation
            required_fields = ['id', 'author', 'timestamp', 'content']
            for field in required_fields:
                if field not in item:
                    raise ValidationError(f"Item {i} missing required field: {field}")

            # Validate nested author object
            if not isinstance(item['author'], dict):
                raise ValidationError(f"Item {i} author must be an object")

            if 'username' not in item['author'] and 'global_name' not in item['author']:
                raise ValidationError(f"Item {i} author missing username/global_name")

            # Validate timestamp format
            try:
                datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError(f"Item {i} timestamp has invalid timestamp format")

        else:
            # Standard format validation
            required_fields = ['author_name', 'created_at', 'content', 'channel_name']
            for field in required_fields:
                if field not in item:
                    raise ValidationError(f"Item {i} missing required field: {field}")

            # Validate field types
            if not isinstance(item['author_name'], str) or len(item['author_name']) > 100:
                raise ValidationError(f"Item {i} author_name invalid")

            # Validate timestamp format
            try:
                datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError(f"Item {i} created_at has invalid timestamp format")

        validated_data.append(item)

    return validated_data


def validate_channel_list(channels: Union[List[str], str]) -> List[str]:
    """Validate and normalize channel list."""
    if isinstance(channels, str):
        channels = [c.strip() for c in channels.split(',') if c.strip()]

    if not channels:
        raise ValidationError("At least one channel must be specified")

    validated_channels = []
    for channel in channels:
        try:
            validated_channel = ChannelName(channel)
            validated_channels.append(validated_channel)
        except ValidationError as e:
            raise ValidationError(f"Invalid channel '{channel}': {e}")

    return validated_channels


def validate_date_range(start: str, end: str) -> tuple:
    """Validate date range."""
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d")
        end_date = datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        raise ValidationError("Dates must be in YYYY-MM-DD format")

    if start_date > end_date:
        raise ValidationError("Start date must be before end date")

    # Max range of 30 days
    if (end_date - start_date).days > 30:
        raise ValidationError("Date range cannot exceed 30 days")

    return start, end


def validate_api_key_format(api_key: str) -> str:
    """Validate API key format."""
    try:
        return ApiKey(api_key)
    except ValidationError:
        raise ValidationError("Invalid API key format")


def sanitize_input(text: str) -> str:
    """Sanitize input text to prevent XSS and injection attacks."""
    if not isinstance(text, str):
        return ""

    # Remove control characters except common whitespace
    text = ''.join(c for c in text if ord(c) >= 32 or c in '\t\n\r')

    # Escape HTML special characters
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = text.replace('"', '&quot;').replace("'", '&#x27;')

    return text


def validate_message_content(content: str) -> str:
    """Validate and sanitize message content."""
    try:
        content = MessageContent(content)
    except ValidationError:
        raise ValidationError("Invalid message content")

    return sanitize_input(content)