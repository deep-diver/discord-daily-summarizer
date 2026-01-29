"""SQLite database layer for storing messages, states, deltas, and digests."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.core.events import EventBus, Event, EventType
from src.core.models import (
    Attachment,
    DailyChannelState,
    DailyChannelDelta,
    GlobalDigest,
    MessageEvent,
)


class Database:
    """SQLite database for message summarization system.

    Features:
    - Schema management with migrations
    - Event publishing for observability
    - Proper indexing for performance
    """

    def __init__(self, db_path: str | Path, event_bus: EventBus | None = None) -> None:
        """Initialize database connection and create schema.

        Args:
            db_path: Path to SQLite database file
            event_bus: Optional event bus for publishing events
        """
        self._db_path = Path(db_path)
        self._event_bus = event_bus or EventBus()
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection.

        Returns:
            SQLite connection
        """
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Create messages table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                author_id TEXT NOT NULL,
                author_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                content TEXT NOT NULL,
                attachments_json TEXT NOT NULL DEFAULT '[]',
                links_json TEXT NOT NULL DEFAULT '[]'
            )
        """
        )

        # Create indexes for messages
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_channel_id_created
            ON messages (channel_id, created_at)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_channel_name_created
            ON messages (channel_name, created_at)
        """
        )

        # Create daily_channel_state table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_channel_state (
                date TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                state_json TEXT NOT NULL,
                summary_md TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (date, channel_id)
            )
        """
        )

        # Create daily_channel_delta table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_channel_delta (
                date TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                compared_to TEXT NOT NULL,
                delta_json TEXT NOT NULL,
                delta_md TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (date, channel_id)
            )
        """
        )

        # Create global_digest table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS global_digest (
                date TEXT PRIMARY KEY,
                digest_md TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """
        )

        conn.commit()

    def reset(self) -> None:
        """Drop and recreate all tables."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS messages")
        cursor.execute("DROP TABLE IF EXISTS daily_channel_state")
        cursor.execute("DROP TABLE IF EXISTS daily_channel_delta")
        cursor.execute("DROP TABLE IF EXISTS global_digest")

        conn.commit()
        self._ensure_schema()

    def insert_messages(self, messages: list[MessageEvent]) -> int:
        """Insert messages into the database.

        Uses INSERT OR REPLACE for idempotence.

        Args:
            messages: List of message events to insert

        Returns:
            Number of messages inserted
        """
        if not messages:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        inserted = 0
        for msg in messages:
            attachments_json = json.dumps([a.model_dump() for a in msg.attachments])
            links_json = json.dumps(msg.links)

            cursor.execute(
                """
                INSERT OR REPLACE INTO messages
                (message_id, channel_id, channel_name, author_id, author_name,
                 created_at, content, attachments_json, links_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    msg.message_id,
                    msg.channel_id,
                    msg.channel_name,
                    msg.author_id,
                    msg.author_name,
                    msg.created_at,
                    msg.content,
                    attachments_json,
                    links_json,
                ),
            )
            inserted += 1

        conn.commit()

        # Publish event
        self._event_bus.publish(
            Event(
                type=EventType.MESSAGE_INGESTED,
                data={
                    "count": inserted,
                    "channel_name": messages[0].channel_name if messages else "unknown",
                },
            )
        )

        return inserted

    def get_messages(
        self,
        channel_name: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[MessageEvent]:
        """Query messages from the database.

        Args:
            channel_name: Optional channel name filter
            start_time: Optional start time (ISO format)
            end_time: Optional end time (ISO format)

        Returns:
            List of message events
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM messages WHERE 1=1"
        params: list[Any] = []

        if channel_name:
            query += " AND channel_name = ?"
            params.append(channel_name)

        if start_time:
            query += " AND created_at >= ?"
            params.append(start_time)

        if end_time:
            query += " AND created_at <= ?"
            params.append(end_time)

        query += " ORDER BY created_at ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        messages = []
        for row in rows:
            attachments = [Attachment(**a) for a in json.loads(row["attachments_json"])]
            links = json.loads(row["links_json"])

            messages.append(
                MessageEvent(
                    message_id=row["message_id"],
                    channel_id=row["channel_id"],
                    channel_name=row["channel_name"],
                    author_id=row["author_id"],
                    author_name=row["author_name"],
                    created_at=row["created_at"],
                    content=row["content"],
                    attachments=attachments,
                    links=links,
                )
            )

        return messages

    def save_state(self, state: DailyChannelState, summary_md: str, channel_id: str) -> None:
        """Save a daily channel state to the database.

        Args:
            state: Daily channel state to save
            summary_md: Markdown summary
            channel_id: Channel ID
        """
        from datetime import datetime, timezone

        conn = self._get_connection()
        cursor = conn.cursor()

        state_json = state.model_dump_json()
        created_at = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            INSERT OR REPLACE INTO daily_channel_state
            (date, channel_id, channel_name, state_json, summary_md, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (state.date, channel_id, state.channel_name, state_json, summary_md, created_at),
        )

        conn.commit()

        # Publish event
        self._event_bus.publish(
            Event(
                type=EventType.STATE_GENERATED,
                data={
                    "channel_name": state.channel_name,
                    "date": state.date,
                    "topics_count": len(state.topics),
                    "has_blockers": len(state.progress.blocked) > 0,
                },
            )
        )

    def get_state(self, date: str, channel_id: str) -> DailyChannelState | None:
        """Get a daily channel state from the database.

        Args:
            date: Date string (YYYY-MM-DD)
            channel_id: Channel ID

        Returns:
            Daily channel state or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT state_json FROM daily_channel_state WHERE date = ? AND channel_id = ?",
            (date, channel_id),
        )

        row = cursor.fetchone()
        if row:
            return DailyChannelState.model_validate_json(row["state_json"])
        return None

    def save_delta(
        self, delta: DailyChannelDelta, delta_md: str, channel_id: str, compared_to: str
    ) -> None:
        """Save a daily channel delta to the database.

        Args:
            delta: Daily channel delta to save
            delta_md: Markdown delta
            channel_id: Channel ID
            compared_to: Date to compare against (YYYY-MM-DD or "null")
        """
        from datetime import datetime, timezone

        conn = self._get_connection()
        cursor = conn.cursor()

        delta_json = delta.model_dump_json()
        created_at = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            INSERT OR REPLACE INTO daily_channel_delta
            (date, channel_id, channel_name, compared_to, delta_json, delta_md, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (delta.date, channel_id, delta.channel_name, compared_to, delta_json, delta_md, created_at),
        )

        conn.commit()

        # Publish event
        self._event_bus.publish(
            Event(
                type=EventType.DELTA_COMPUTED,
                data={
                    "channel_name": delta.channel_name,
                    "date": delta.date,
                    "compared_to": compared_to,
                    "new_items_count": len(delta.new_topics) + len(delta.progress_changes.finished_now),
                    "resolved_items_count": len(delta.resolved_topics),
                },
            )
        )

    def get_delta(self, date: str, channel_id: str) -> DailyChannelDelta | None:
        """Get a daily channel delta from the database.

        Args:
            date: Date string (YYYY-MM-DD)
            channel_id: Channel ID

        Returns:
            Daily channel delta or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT delta_json FROM daily_channel_delta WHERE date = ? AND channel_id = ?",
            (date, channel_id),
        )

        row = cursor.fetchone()
        if row:
            return DailyChannelDelta.model_validate_json(row["delta_json"])
        return None

    def save_digest(self, date: str, digest_md: str) -> None:
        """Save a global digest to the database.

        Args:
            date: Date string (YYYY-MM-DD)
            digest_md: Markdown digest
        """
        from datetime import datetime, timezone

        conn = self._get_connection()
        cursor = conn.cursor()

        created_at = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            INSERT OR REPLACE INTO global_digest (date, digest_md, created_at)
            VALUES (?, ?, ?)
        """,
            (date, digest_md, created_at),
        )

        conn.commit()

        # Publish event
        self._event_bus.publish(
            Event(
                type=EventType.DIGEST_CREATED,
                data={
                    "date": date,
                    "digest_md_length": len(digest_md),
                },
            )
        )

    def get_digest(self, date: str) -> str | None:
        """Get a global digest from the database.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            Markdown digest or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT digest_md FROM global_digest WHERE date = ?", (date,))

        row = cursor.fetchone()
        if row:
            return row["digest_md"]
        return None

    def get_channels(self) -> list[dict[str, str]]:
        """Get all unique channels in the database.

        Returns:
            List of dicts with channel_id and channel_name
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT channel_id, channel_name
            FROM messages
            ORDER BY channel_name
        """
        )

        return [{"channel_id": row["channel_id"], "channel_name": row["channel_name"]} for row in cursor.fetchall()]

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Database":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Context manager exit."""
        self.close()
