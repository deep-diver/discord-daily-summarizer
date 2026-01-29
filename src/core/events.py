"""Event-driven architecture for loose coupling and observability."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from threading import Lock


class EventType(str, Enum):
    """Event types in the system."""

    MESSAGE_INGESTED = "MESSAGE_INGESTED"
    STATE_GENERATED = "STATE_GENERATED"
    DELTA_COMPUTED = "DELTA_COMPUTED"
    DIGEST_CREATED = "DIGEST_CREATED"
    ERROR = "ERROR"


@dataclass
class Event:
    """Base event class.

    All events have a type, timestamp, and optional data payload.
    """

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"Event(type={self.type.value}, timestamp={self.timestamp.isoformat()}, data={self.data})"


class EventBus:
    """Event bus for pub/sub communication.

    Provides:
    - Loose coupling between components
    - Observability through event history
    - Testability through event tracking
    - Error isolation (one subscriber error doesn't break others)
    """

    def __init__(self) -> None:
        """Initialize event bus."""
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._history: list[Event] = []
        self._lock = Lock()
        self._enabled = True

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """Subscribe to an event type.

        Args:
            event_type: The event type to subscribe to
            callback: Function to call when event is published
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """Unsubscribe from an event type.

        Args:
            event_type: The event type to unsubscribe from
            callback: The callback to remove
        """
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass  # Callback not in list

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers.

        Subscriber errors are isolated - one failing subscriber doesn't break others.

        Args:
            event: The event to publish
        """
        if not self._enabled:
            return

        with self._lock:
            self._history.append(event)

        # Publish outside lock to prevent deadlocks
        if event.type in self._subscribers:
            for callback in self._subscribers[event.type]:
                try:
                    callback(event)
                except Exception as e:
                    # Don't let subscriber errors break the bus
                    # Log and continue with other subscribers
                    error_event = Event(
                        type=EventType.ERROR,
                        data={
                            "original_event": event.type.value,
                            "error_message": str(e),
                            "context": "event_bus_subscriber",
                        },
                    )
                    with self._lock:
                        self._history.append(error_event)

    def get_history(self, event_type: EventType | None = None) -> list[Event]:
        """Get event history, optionally filtered by type.

        Args:
            event_type: Optional event type to filter by

        Returns:
            List of events (most recent last)
        """
        with self._lock:
            if event_type is None:
                return list(self._history)
            return [e for e in self._history if e.type == event_type]

    def clear_history(self) -> None:
        """Clear event history."""
        with self._lock:
            self._history.clear()

    def enable(self) -> None:
        """Enable event publishing."""
        self._enabled = True

    def disable(self) -> None:
        """Disable event publishing."""
        self._enabled = False

    @property
    def history_count(self) -> int:
        """Get number of events in history."""
        with self._lock:
            return len(self._history)
