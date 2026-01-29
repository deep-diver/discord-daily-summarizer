"""Tests for event system."""

import time
from datetime import datetime, timezone

import pytest

from src.core.events import EventBus, EventType, Event


class TestEventBus:
    """Test event bus functionality."""

    def test_event_creation(self) -> None:
        """Test creating an event."""
        event = Event(
            type=EventType.MESSAGE_INGESTED,
            data={"count": 10},
        )

        assert event.type == EventType.MESSAGE_INGESTED
        assert event.data["count"] == 10
        assert isinstance(event.timestamp, datetime)

    def test_event_default_timestamp(self) -> None:
        """Test that event has default timestamp."""
        event = Event(type=EventType.MESSAGE_INGESTED)

        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)

    def test_event_custom_timestamp(self) -> None:
        """Test event with custom timestamp."""
        custom_time = datetime(2026, 1, 17, 12, 0, 0, tzinfo=timezone.utc)
        event = Event(
            type=EventType.MESSAGE_INGESTED,
            timestamp=custom_time,
        )

        assert event.timestamp == custom_time

    def test_subscribe_and_publish(self, event_bus: EventBus) -> None:
        """Test subscribing to and publishing events."""
        received = []

        def callback(event: Event) -> None:
            received.append(event)

        event_bus.subscribe(EventType.MESSAGE_INGESTED, callback)

        event = Event(type=EventType.MESSAGE_INGESTED, data={"count": 5})
        event_bus.publish(event)

        assert len(received) == 1
        assert received[0].data["count"] == 5

    def test_subscribe_multiple_callbacks(self, event_bus: EventBus) -> None:
        """Test multiple subscribers to same event type."""
        received1 = []
        received2 = []

        def callback1(event: Event) -> None:
            received1.append(event)

        def callback2(event: Event) -> None:
            received2.append(event)

        event_bus.subscribe(EventType.MESSAGE_INGESTED, callback1)
        event_bus.subscribe(EventType.MESSAGE_INGESTED, callback2)

        event = Event(type=EventType.MESSAGE_INGESTED)
        event_bus.publish(event)

        assert len(received1) == 1
        assert len(received2) == 1

    def test_subscribe_different_event_types(self, event_bus: EventBus) -> None:
        """Test subscribing to different event types."""
        message_events = []
        state_events = []

        event_bus.subscribe(EventType.MESSAGE_INGESTED, lambda e: message_events.append(e))
        event_bus.subscribe(EventType.STATE_GENERATED, lambda e: state_events.append(e))

        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))
        event_bus.publish(Event(type=EventType.STATE_GENERATED))

        assert len(message_events) == 1
        assert len(state_events) == 1

    def test_unsubscribe(self, event_bus: EventBus) -> None:
        """Test unsubscribing from events."""
        received = []

        def callback(event: Event) -> None:
            received.append(event)

        event_bus.subscribe(EventType.MESSAGE_INGESTED, callback)
        event_bus.unsubscribe(EventType.MESSAGE_INGESTED, callback)

        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))

        assert len(received) == 0

    def test_get_history(self, event_bus: EventBus) -> None:
        """Test getting event history."""
        event1 = Event(type=EventType.MESSAGE_INGESTED, data={"count": 1})
        event2 = Event(type=EventType.STATE_GENERATED, data={"count": 2})

        event_bus.publish(event1)
        event_bus.publish(event2)

        history = event_bus.get_history()

        assert len(history) == 2
        assert history[0] == event1
        assert history[1] == event2

    def test_get_history_filtered(self, event_bus: EventBus) -> None:
        """Test getting filtered event history."""
        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))
        event_bus.publish(Event(type=EventType.STATE_GENERATED))
        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))

        message_events = event_bus.get_history(EventType.MESSAGE_INGESTED)

        assert len(message_events) == 2
        assert all(e.type == EventType.MESSAGE_INGESTED for e in message_events)

    def test_clear_history(self, event_bus: EventBus) -> None:
        """Test clearing event history."""
        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))
        event_bus.publish(Event(type=EventType.STATE_GENERATED))

        assert event_bus.history_count == 2

        event_bus.clear_history()

        assert event_bus.history_count == 0
        assert len(event_bus.get_history()) == 0

    def test_enable_disable(self, event_bus: EventBus) -> None:
        """Test enabling and disabling event publishing."""
        received = []

        def callback(event: Event) -> None:
            received.append(event)

        event_bus.subscribe(EventType.MESSAGE_INGESTED, callback)

        # Disabled - should not receive events
        event_bus.disable()
        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))
        assert len(received) == 0

        # Enabled - should receive events
        event_bus.enable()
        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))
        assert len(received) == 1

    def test_subscriber_error_isolation(self, event_bus: EventBus) -> None:
        """Test that one failing subscriber doesn't break others."""
        received = []

        def failing_callback(event: Event) -> None:
            raise ValueError("Intentional error")

        def working_callback(event: Event) -> None:
            received.append(event)

        event_bus.subscribe(EventType.MESSAGE_INGESTED, failing_callback)
        event_bus.subscribe(EventType.MESSAGE_INGESTED, working_callback)

        # Should not raise exception
        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))

        # Working callback should still be called
        assert len(received) == 1

        # Error event should be published
        error_events = event_bus.get_history(EventType.ERROR)
        assert len(error_events) == 1
        assert "Intentional error" in error_events[0].data["error_message"]

    def test_subscriber_error_isolation_multiple(self, event_bus: EventBus) -> None:
        """Test error isolation with multiple failing subscribers."""
        received = []

        def failing_callback1(event: Event) -> None:
            raise ValueError("Error 1")

        def failing_callback2(event: Event) -> None:
            raise RuntimeError("Error 2")

        def working_callback(event: Event) -> None:
            received.append(event)

        event_bus.subscribe(EventType.MESSAGE_INGESTED, failing_callback1)
        event_bus.subscribe(EventType.MESSAGE_INGESTED, failing_callback2)
        event_bus.subscribe(EventType.MESSAGE_INGESTED, working_callback)

        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))

        # Working callback should still be called
        assert len(received) == 1

        # Two error events should be published
        error_events = event_bus.get_history(EventType.ERROR)
        assert len(error_events) == 2

    def test_event_history_not_affected_by_disable(self, event_bus: EventBus) -> None:
        """Test that event history is recorded even when disabled."""
        event_bus.disable()
        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))

        # History should be empty when disabled
        assert event_bus.history_count == 0

    def test_multiple_event_types_in_history(self, event_bus: EventBus) -> None:
        """Test that all event types are recorded in history."""
        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))
        event_bus.publish(Event(type=EventType.STATE_GENERATED))
        event_bus.publish(Event(type=EventType.DELTA_COMPUTED))
        event_bus.publish(Event(type=EventType.DIGEST_CREATED))

        history = event_bus.get_history()

        assert len(history) == 4
        assert history[0].type == EventType.MESSAGE_INGESTED
        assert history[1].type == EventType.STATE_GENERATED
        assert history[2].type == EventType.DELTA_COMPUTED
        assert history[3].type == EventType.DIGEST_CREATED

    def test_unsubscribe_nonexistent_callback(self, event_bus: EventBus) -> None:
        """Test unsubscribing a callback that wasn't subscribed."""
        def callback(event: Event) -> None:
            pass

        # Should not raise exception
        event_bus.unsubscribe(EventType.MESSAGE_INGESTED, callback)

    def test_event_data_mutation(self, event_bus: EventBus) -> None:
        """Test that event data is not mutated by subscribers."""
        original_data = {"count": 5}

        def mutating_callback(event: Event) -> None:
            event.data["count"] = 999

        def reading_callback(event: Event) -> None:
            # Should see the mutated data
            assert event.data["count"] == 999

        event_bus.subscribe(EventType.MESSAGE_INGESTED, mutating_callback)
        event_bus.subscribe(EventType.MESSAGE_INGESTED, reading_callback)

        event = Event(type=EventType.MESSAGE_INGESTED, data=original_data)
        event_bus.publish(event)

    def test_thread_safety(self, event_bus: EventBus) -> None:
        """Test basic thread safety of event bus."""
        import threading

        received = []

        def callback(event: Event) -> None:
            received.append(event)

        event_bus.subscribe(EventType.MESSAGE_INGESTED, callback)

        def publish_events():
            for i in range(10):
                event_bus.publish(Event(type=EventType.MESSAGE_INGESTED, data={"count": i}))

        threads = [threading.Thread(target=publish_events) for _ in range(2)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Should have received 20 events (10 from each thread)
        assert len(received) == 20

    def test_event_repr(self) -> None:
        """Test event string representation."""
        event = Event(type=EventType.MESSAGE_INGESTED, data={"count": 5})

        repr_str = repr(event)

        assert "MESSAGE_INGESTED" in repr_str
        assert "count" in repr_str

    def test_event_bus_history_count(self, event_bus: EventBus) -> None:
        """Test history_count property."""
        assert event_bus.history_count == 0

        event_bus.publish(Event(type=EventType.MESSAGE_INGESTED))
        assert event_bus.history_count == 1

        event_bus.publish(Event(type=EventType.STATE_GENERATED))
        assert event_bus.history_count == 2

        event_bus.clear_history()
        assert event_bus.history_count == 0
