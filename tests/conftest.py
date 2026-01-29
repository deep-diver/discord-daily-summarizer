"""Pytest fixtures for testing."""

import tempfile
import os
from pathlib import Path
from datetime import datetime
import pytest

from src.core.events import EventBus, EventType, Event
from src.core.models import (
    MessageEvent,
    DailyChannelState,
    Progress,
    Artifacts,
    Attachment,
)
from src.infra.db import Database
from src.infra.glm_client import GLMClient


@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh event bus for each test."""
    bus = EventBus()
    bus.clear_history()
    return bus


@pytest.fixture
def glm_client_mock(event_bus: EventBus) -> GLMClient:
    """Create a GLM client in mock mode."""
    client = GLMClient(event_bus=event_bus, mock=True)
    return client


@pytest.fixture
def sample_state() -> DailyChannelState:
    """Create a sample DailyChannelState for testing."""
    return DailyChannelState(
        channel_name="test-channel",
        date="2026-01-17",
        topics=["Topic A", "Topic B"],
        progress=Progress(
            started=["Task A"],
            continued=["Task B"],
            finished=["Task C"],
            blocked=["Task D"],
        ),
        artifacts=Artifacts(
            links=["https://example.com"],
            repos=["https://github.com/example/repo"],
            docs=["https://docs.example.com"],
        ),
        questions=["Question 1?"],
        help_requests=["Help needed with X"],
        next_steps=["Next step 1"],
    )


@pytest.fixture
def sample_messages() -> list[MessageEvent]:
    """Create sample message events for testing."""
    return [
        MessageEvent(
            message_id="msg1",
            channel_id="c-test",
            channel_name="test",
            author_id="u1",
            author_name="Alice",
            created_at="2026-01-17T09:00:00+09:00",
            content="Hello world",
            attachments=[],
            links=[],
        ),
        MessageEvent(
            message_id="msg2",
            channel_id="c-test",
            channel_name="test",
            author_id="u2",
            author_name="Bob",
            created_at="2026-01-17T10:00:00+09:00",
            content="Check out https://example.com",
            attachments=[],
            links=["https://example.com"],
        ),
        MessageEvent(
            message_id="msg3",
            channel_id="c-test",
            channel_name="test",
            author_id="u1",
            author_name="Alice",
            created_at="2026-01-17T11:00:00+09:00",
            content="Working on the indexing pipeline",
            attachments=[
                Attachment(
                    url="https://example.com/file.pdf",
                    filename="file.pdf",
                    content_type="application/pdf",
                )
            ],
            links=[],
        ),
    ]


@pytest.fixture
def temp_db(event_bus: EventBus) -> Database:
    """Create a temporary database for testing."""
    # Create a temporary file for the database
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Create database with temporary path (schema is created in __init__)
    db = Database(db_path=db_path, event_bus=event_bus)

    yield db

    # Cleanup
    db.close()
    os.unlink(db_path)


@pytest.fixture
def sample_previous_state() -> DailyChannelState:
    """Create a sample previous day state for delta testing."""
    return DailyChannelState(
        channel_name="test-channel",
        date="2026-01-16",
        topics=["Topic A", "Topic C"],
        progress=Progress(
            started=["Old Task A"],
            continued=["Continuing Task"],
            finished=["Old Task B"],
            blocked=["Old Blocker"],
        ),
        artifacts=Artifacts(
            links=["https://old-link.com"],
            repos=["https://github.com/old/repo"],
            docs=["https://old-docs.com"],
        ),
        questions=["Old Question?"],
        help_requests=["Old help request"],
        next_steps=["Old next step"],
    )
