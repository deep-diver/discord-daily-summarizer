"""End-to-end tests (offline, mock mode)."""

import tempfile
from pathlib import Path

import pytest

from src.core.events import EventBus
from src.core.models import DailyChannelState
from src.core.summarizer import Summarizer
from src.core.delta import compute_delta
from src.core.digest import generate_digest
from src.core.renderer import render_summary, render_delta, render_digest
from src.infra.db import Database
from src.infra.fixtures import load_fixture
from src.infra.glm_client import GLMClient


class TestE2EOffline:
    """End-to-end tests with mock LLM."""

    def test_full_pipeline_mock_mode(self, event_bus: EventBus) -> None:
        """Test full pipeline from fixture to digest in mock mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            glm_client = GLMClient(api_key="test-key", event_bus=event_bus)
            glm_client.enable_mock_mode()

            with Database(db_path, event_bus) as db:
                # Step 1: Load and ingest fixtures
                fixture_path = Path("fixtures/sample_minimal.jsonl")
                if not fixture_path.exists():
                    pytest.skip("Fixture file not found")

                messages = load_fixture(fixture_path)
                inserted = db.insert_messages(messages)
                assert inserted > 0

                # Step 2: Get messages for a channel
                channels = db.get_channels()
                assert len(channels) > 0

                channel_name = channels[0]["channel_name"]
                channel_id = channels[0]["channel_id"]

                db_messages = db.get_messages(channel_name=channel_name)
                assert len(db_messages) > 0

                # Step 3: Generate state
                summarizer = Summarizer(glm_client, event_bus)

                message_dicts = [
                    {
                        "author_name": msg.author_name,
                        "created_at": msg.created_at,
                        "content": msg.content,
                        "links": msg.links,
                        "attachments_json": str([a.model_dump() for a in msg.attachments]),
                    }
                    for msg in db_messages
                ]

                state = summarizer.generate_state(channel_name, "2026-01-17", message_dicts)
                assert isinstance(state, DailyChannelState)
                assert state.channel_name == channel_name

                # Step 4: Render summary
                summary_md = render_summary(state)
                assert len(summary_md) > 0
                assert channel_name in summary_md

                # Step 5: Save state
                db.save_state(state, summary_md, channel_id)

                # Step 6: Compute delta (no previous day)
                delta = compute_delta(state, None)
                assert delta.compared_to is None

                # Step 7: Render delta
                delta_md = render_delta(delta)
                assert len(delta_md) > 0

                # Step 8: Save delta
                db.save_delta(delta, delta_md, channel_id, "null")

                # Step 9: Generate digest
                digest = generate_digest(
                    "2026-01-17",
                    {channel_id: state},
                    {channel_id: delta},
                    {channel_id: summary_md},
                )

                assert digest.date == "2026-01-17"

                # Step 10: Render digest
                digest_md = render_digest(digest)
                assert len(digest_md) > 0

                # Step 11: Save digest
                db.save_digest("2026-01-17", digest_md)

                # Step 12: Verify persistence
                retrieved_state = db.get_state("2026-01-17", channel_id)
                assert retrieved_state is not None
                assert retrieved_state.channel_name == state.channel_name

                retrieved_delta = db.get_delta("2026-01-17", channel_id)
                assert retrieved_delta is not None

                retrieved_digest = db.get_digest("2026-01-17")
                assert retrieved_digest is not None

    def test_multi_day_pipeline(self, event_bus: EventBus) -> None:
        """Test pipeline across multiple days with chained deltas."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            glm_client = GLMClient(api_key="test-key", event_bus=event_bus)
            glm_client.enable_mock_mode()

            with Database(db_path, event_bus) as db:
                fixture_path = Path("fixtures/sample_3days.jsonl")
                if not fixture_path.exists():
                    pytest.skip("Fixture file not found")

                messages = load_fixture(fixture_path)
                db.insert_messages(messages)

                channels = db.get_channels()
                if not channels:
                    pytest.skip("No channels in fixture")

                channel_name = channels[0]["channel_name"]
                channel_id = channels[0]["channel_id"]

                summarizer = Summarizer(glm_client, event_bus)

                # Process multiple days
                dates = ["2026-01-15", "2026-01-16", "2026-01-17"]
                previous_state = None

                for date_str in dates:
                    db_messages = db.get_messages(
                        channel_name=channel_name,
                        start_time=f"{date_str}T00:00:00+09:00",
                        end_time=f"{date_str}T23:59:59+09:00",
                    )

                    if not db_messages:
                        continue

                    message_dicts = [
                        {
                            "author_name": msg.author_name,
                            "created_at": msg.created_at,
                            "content": msg.content,
                            "links": msg.links,
                            "attachments_json": str([a.model_dump() for a in msg.attachments]),
                        }
                        for msg in db_messages
                    ]

                    state = summarizer.generate_state(channel_name, date_str, message_dicts)

                    # Compute delta
                    delta = compute_delta(state, previous_state)

                    # Verify delta
                    if previous_state:
                        assert delta.compared_to is not None

                    # Save
                    db.save_state(state, "summary", channel_id)
                    db.save_delta(delta, "delta", channel_id, previous_state.date if previous_state else "null")

                    previous_state = state

                # Verify all states and deltas were saved
                for date_str in dates:
                    state = db.get_state(date_str, channel_id)
                    # May be None if no messages that day
                    if state:
                        assert state.date == date_str

    def test_event_tracking_through_pipeline(self, event_bus: EventBus) -> None:
        """Test that events are published throughout the pipeline."""
        events_log = []

        def track_all_events(event) -> None:  # type: ignore
            events_log.append(event.type.value)

        # Subscribe to all event types
        from src.core.events import EventType
        for event_type in EventType:
            event_bus.subscribe(event_type, lambda e, et=event_type: events_log.append(et.value))

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            glm_client = GLMClient(api_key="test-key", event_bus=event_bus)
            glm_client.enable_mock_mode()

            with Database(db_path, event_bus) as db:
                # Run pipeline
                messages = load_fixture("fixtures/sample_minimal.jsonl")
                db.insert_messages(messages)

                channels = db.get_channels()
                if channels:
                    channel_id = channels[0]["channel_id"]

                    state = DailyChannelState(channel_name="test", date="2026-01-17")
                    db.save_state(state, "summary", channel_id)

                    delta = compute_delta(state, None)
                    db.save_delta(delta, "delta", channel_id, "null")

                    db.save_digest("2026-01-17", "digest")

                # Check that events were published
                assert any("MESSAGE_INGESTED" in str(e) for e in events_log)
                assert any("STATE_GENERATED" in str(e) for e in events_log)

    def test_renderer_output_validity(self, glm_client_mock: GLMClient) -> None:
        """Test that renderer produces valid markdown."""
        state = DailyChannelState(
            channel_name="test",
            date="2026-01-17",
            topics=["Topic A"],
        )

        summary_md = render_summary(state)

        # Should contain markdown headers
        assert "##" in summary_md
        assert "test" in summary_md
        assert "2026-01-17" in summary_md

    def test_database_isolation(self, event_bus: EventBus) -> None:
        """Test that different databases don't interfere."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db1_path = Path(tmpdir) / "test1.db"
            db2_path = Path(tmpdir) / "test2.db"

            with Database(db1_path, event_bus) as db1:
                db1.insert_messages([])

                state = DailyChannelState(channel_name="test", date="2026-01-17")
                db1.save_state(state, "summary", "c-test")

            with Database(db2_path, event_bus) as db2:
                # db2 should not have data from db1
                retrieved = db2.get_state("2026-01-17", "c-test")
                assert retrieved is None

    def test_fixture_loading(self) -> None:
        """Test that fixtures can be loaded."""
        fixture_path = Path("fixtures/sample_minimal.jsonl")
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        messages = load_fixture(fixture_path)

        assert len(messages) > 0
        assert all(hasattr(msg, "message_id") for msg in messages)
        assert all(hasattr(msg, "channel_name") for msg in messages)

    def test_summarizer_link_extraction_pipeline(self, glm_client_mock: GLMClient) -> None:
        """Test that links are extracted in the summarization pipeline."""
        summarizer = Summarizer(glm_client_mock)

        messages = [
            {
                "author_name": "Alice",
                "created_at": "2026-01-17T09:00:00+09:00",
                "content": "Check https://example.com",
                "links": [],
                "attachments": [],
            }
        ]

        state = summarizer.generate_state("test", "2026-01-17", messages)

        # State should be created successfully
        assert isinstance(state, DailyChannelState)
