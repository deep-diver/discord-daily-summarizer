"""Core data models using Pydantic."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Attachment(BaseModel):
    """Attachment metadata."""

    url: str
    filename: str
    content_type: str


class MessageEvent(BaseModel):
    """Normalized message event from Discord or fixtures."""

    message_id: str
    channel_id: str
    channel_name: str
    author_id: str
    author_name: str
    created_at: str  # ISO8601 string
    content: str
    attachments: list[Attachment] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    reply_to_message_id: Optional[str] = None


class Progress(BaseModel):
    """Progress tracking for tasks."""

    started: list[str] = Field(default_factory=list)
    continued: list[str] = Field(default_factory=list)
    finished: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)


class Artifacts(BaseModel):
    """Artifacts mentioned in channel."""

    links: list[str] = Field(default_factory=list)
    repos: list[str] = Field(default_factory=list)
    docs: list[str] = Field(default_factory=list)


class DailyChannelState(BaseModel):
    """Structured JSON state for a channel on a given date.

    This MUST be stable because deltas depend on it.
    """

    channel_name: str
    date: str  # YYYY-MM-DD
    topics: list[str] = Field(default_factory=list)
    progress: Progress = Field(default_factory=Progress)
    artifacts: Artifacts = Field(default_factory=Artifacts)
    questions: list[str] = Field(default_factory=list)
    help_requests: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ProgressChanges(BaseModel):
    """Progress changes in delta."""

    started_now: list[str] = Field(default_factory=list)
    finished_now: list[str] = Field(default_factory=list)
    new_blockers: list[str] = Field(default_factory=list)
    resolved_blockers: list[str] = Field(default_factory=list)


class DailyChannelDelta(BaseModel):
    """Structured JSON delta comparing today vs. previous day.

    Derived via JSON-to-JSON comparison (NOT message-to-message diff).
    """

    channel_name: str
    date: str  # YYYY-MM-DD
    compared_to: Optional[str]  # YYYY-MM-DD or null if no previous day
    new_topics: list[str] = Field(default_factory=list)
    resolved_topics: list[str] = Field(default_factory=list)
    progress_changes: ProgressChanges = Field(default_factory=ProgressChanges)
    new_links: list[str] = Field(default_factory=list)
    new_help_requests: list[str] = Field(default_factory=list)


class GlobalDigest(BaseModel):
    """Global digest rolling up all channels.

    A Markdown text (and optionally a small JSON) that rolls up:
    - Top highlights across channels (top 5)
    - Help requests across channels (top 5)
    - New links across channels (top 10)
    """

    date: str  # YYYY-MM-DD
    highlights: list[str] = Field(default_factory=list)
    help_requests: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    channel_summaries: dict[str, str] = Field(default_factory=dict)  # channel_name -> summary_md
