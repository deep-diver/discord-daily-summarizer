"""Tests for database layer."""

import tempfile
from pathlib import Path

import pytest

from src.core.events import EventBus, EventType, Event
from src.core.models import (
    Attachment,
    DailyChannelState,
    DailyChannelDelta,
    MessageEvent,
    Progress,
    ProgressChanges,
    Artifacts,
)
from src.infra.db import Database


class TestDatabase:
    """Test database operations."""

    def test_database_creation(self, event_bus: EventBus) -> None:
        """Test that database and tables are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path, event_bus)

            # Check that tables exist
            conn = db._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
            )
            assert cursor.fetchone() is not None

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_channel_state'"
            )
            assert cursor.fetchone() is not None

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_channel_delta'"
            )
            assert cursor.fetchone() is not None

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='global_digest'"
            )
            assert cursor.fetchone() is not None

            db.close()

    def test_insert_messages(self, temp_db: Database, sample_messages: list[MessageEvent]) -> None:
        """Test inserting messages."""
        inserted = temp_db.insert_messages(sample_messages)
        assert inserted == len(sample_messages)

    def test_insert_empty_messages(self, temp_db: Database) -> None:
        """Test inserting empty message list."""
        inserted = temp_db.insert_messages([])
        assert inserted == 0

    def test_get_messages(self, temp_db: Database, sample_messages: list[MessageEvent]) -> None:
        """Test retrieving messages."""
        temp_db.insert_messages(sample_messages)

        messages = temp_db.get_messages()
        assert len(messages) == len(sample_messages)

    def test_get_messages_by_channel(self, temp_db: Database, sample_messages: list[MessageEvent]) -> None:
        """Test retrieving messages by channel."""
        temp_db.insert_messages(sample_messages)

        messages = temp_db.get_messages(channel_name="test")
        assert len(messages) == len(sample_messages)

        messages = temp_db.get_messages(channel_name="nonexistent")
        assert len(messages) == 0

    def test_get_messages_by_time_range(self, temp_db: Database, sample_messages: list[MessageEvent]) -> None:
        """Test retrieving messages by time range."""
        temp_db.insert_messages(sample_messages)

        messages = temp_db.get_messages(
            start_time="2026-01-17T09:30:00+09:00",
            end_time="2026-01-17T11:30:00+09:00",
        )
        assert len(messages) == 2  # m2 and m3

    def test_message_event_published(self, temp_db: Database, sample_messages: list[MessageEvent]) -> None:
        """Test that MESSAGE_INGESTED event is published."""
        events = []

        def on_message_ingested(event: Event) -> None:
            events.append(event)

        temp_db._event_bus.subscribe(EventType.MESSAGE_INGESTED, on_message_ingested)

        temp_db.insert_messages(sample_messages)

        assert len(events) == 1
        assert events[0].data["count"] == len(sample_messages)

    def test_save_and_get_state(self, temp_db: Database, sample_state: DailyChannelState) -> None:
        """Test saving and retrieving a daily channel state."""
        summary_md = "# Test Summary\n\nThis is a test."

        temp_db.save_state(sample_state, summary_md, "c-test")

        retrieved = temp_db.get_state("2026-01-17", "c-test")
        assert retrieved is not None
        assert retrieved.channel_name == sample_state.channel_name
        assert retrieved.date == sample_state.date
        assert len(retrieved.topics) == len(sample_state.topics)

    def test_get_state_not_found(self, temp_db: Database) -> None:
        """Test retrieving a non-existent state."""
        retrieved = temp_db.get_state("2026-01-17", "c-test")
        assert retrieved is None

    def test_save_state_event_published(self, temp_db: Database, sample_state: DailyChannelState) -> None:
        """Test that STATE_GENERATED event is published."""
        events = []

        def on_state_generated(event: Event) -> None:
            events.append(event)

        temp_db._event_bus.subscribe(EventType.STATE_GENERATED, on_state_generated)

        temp_db.save_state(sample_state, "summary", "c-test")

        assert len(events) == 1
        assert events[0].data["channel_name"] == sample_state.channel_name
        assert events[0].data["date"] == sample_state.date

    def test_save_and_get_delta(self, temp_db: Database) -> None:
        """Test saving and retrieving a daily channel delta."""
        delta = DailyChannelDelta(
            channel_name="test",
            date="2026-01-17",
            compared_to="2026-01-16",
            new_topics=["New Topic"],
            progress_changes=ProgressChanges(
                finished_now=["Task A"],
            ),
        )
        delta_md = "# Delta\n\nChanges here."

        temp_db.save_delta(delta, delta_md, "c-test", "2026-01-16")

        retrieved = temp_db.get_delta("2026-01-17", "c-test")
        assert retrieved is not None
        assert retrieved.channel_name == delta.channel_name
        assert retrieved.date == delta.date
        assert len(retrieved.new_topics) == 1

    def test_save_delta_event_published(self, temp_db: Database) -> None:
        """Test that DELTA_COMPUTED event is published."""
        events = []

        def on_delta_computed(event: Event) -> None:
            events.append(event)

        temp_db._event_bus.subscribe(EventType.DELTA_COMPUTED, on_delta_computed)

        delta = DailyChannelDelta(
            channel_name="test",
            date="2026-01-17",
            compared_to="2026-01-16",
        )
        temp_db.save_delta(delta, "delta", "c-test", "2026-01-16")

        assert len(events) == 1
        assert events[0].data["channel_name"] == delta.channel_name

    def test_save_and_get_digest(self, temp_db: Database) -> None:
        """Test saving and retrieving a global digest."""
        digest_md = "# Digest\n\nDaily digest content."

        temp_db.save_digest("2026-01-17", digest_md)

        retrieved = temp_db.get_digest("2026-01-17")
        assert retrieved == digest_md

    def test_get_digest_not_found(self, temp_db: Database) -> None:
        """Test retrieving a non-existent digest."""
        retrieved = temp_db.get_digest("2026-01-17")
        assert retrieved is None

    def test_save_digest_event_published(self, temp_db: Database) -> None:
        """Test that DIGEST_CREATED event is published."""
        events = []

        def on_digest_created(event: Event) -> None:
            events.append(event)

        temp_db._event_bus.subscribe(EventType.DIGEST_CREATED, on_digest_created)

        temp_db.save_digest("2026-01-17", "digest content")

        assert len(events) == 1
        assert events[0].data["date"] == "2026-01-17"

    def test_get_channels(self, temp_db: Database, sample_messages: list[MessageEvent]) -> None:
        """Test retrieving all channels."""
        temp_db.insert_messages(sample_messages)

        channels = temp_db.get_channels()
        assert len(channels) == 1
        assert channels[0]["channel_id"] == "c-test"
        assert channels[0]["channel_name"] == "test"

    def test_reset_database(self, temp_db: Database, sample_messages: list[MessageEvent]) -> None:
        """Test resetting the database."""
        temp_db.insert_messages(sample_messages)

        # Save some data
        state = DailyChannelState(channel_name="test", date="2026-01-17")
        temp_db.save_state(state, "summary", "c-test")

        # Reset
        temp_db.reset()

        # Check data is gone
        messages = temp_db.get_messages()
        assert len(messages) == 0

        state = temp_db.get_state("2026-01-17", "c-test")
        assert state is None

    def test_context_manager(self, event_bus: EventBus) -> None:
        """Test database as context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            with Database(db_path, event_bus) as db:
                db.insert_messages([])

            # Connection should be closed now

    def test_insert_or_replace(self, temp_db: Database) -> None:
        """Test INSERT OR REPLACE behavior."""
        msg1 = MessageEvent(
            message_id="m1",
            channel_id="c-test",
            channel_name="test",
            author_id="u1",
            author_name="Alice",
            created_at="2026-01-17T09:00:00+09:00",
            content="Original",
        )

        msg2 = MessageEvent(
            message_id="m1",  # Same ID
            channel_id="c-test",
            channel_name="test",
            author_id="u2",
            author_name="Bob",
            created_at="2026-01-17T10:00:00+09:00",
            content="Updated",
        )

        temp_db.insert_messages([msg1])
        temp_db.insert_messages([msg2])

        messages = temp_db.get_messages()
        assert len(messages) == 1
        assert messages[0].author_name == "Bob"
        assert messages[0].content == "Updated"

    def test_state_primary_key(self, temp_db: Database) -> None:
        """Test that (date, channel_id) is primary key for states."""
        state1 = DailyChannelState(channel_name="test", date="2026-01-17", topics=["A"])
        state2 = DailyChannelState(channel_name="test", date="2026-01-17", topics=["B"])

        temp_db.save_state(state1, "summary1", "c-test")
        temp_db.save_state(state2, "summary2", "c-test")  # Should replace

        retrieved = temp_db.get_state("2026-01-17", "c-test")
        assert retrieved is not None
        assert retrieved.topics == ["B"]  # Second save replaced first

    def test_delta_primary_key(self, temp_db: Database) -> None:
        """Test that (date, channel_id) is primary key for deltas."""
        delta1 = DailyChannelDelta(
            channel_name="test",
            date="2026-01-17",
            compared_to="2026-01-16",
            new_topics=["A"],
        )
        delta2 = DailyChannelDelta(
            channel_name="test",
            date="2026-01-17",
            compared_to="2026-01-16",
            new_topics=["B"],
        )

        temp_db.save_delta(delta1, "delta1", "c-test", "2026-01-16")
        temp_db.save_delta(delta2, "delta2", "c-test", "2026-01-16")  # Should replace

        retrieved = temp_db.get_delta("2026-01-17", "c-test")
        assert retrieved is not None
        assert retrieved.new_topics == ["B"]  # Second save replaced first
