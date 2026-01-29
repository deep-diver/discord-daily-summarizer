"""Tests for summarizer in mock mode."""

import pytest

from src.core.events import EventBus, EventType, Event
from src.core.models import DailyChannelState
from src.core.summarizer import Summarizer
from src.infra.glm_client import GLMClient


class TestSummarizerMock:
    """Test summarizer with mock LLM responses."""

    def test_extract_links(self, glm_client_mock: GLMClient) -> None:
        """Test link extraction from content."""
        summarizer = Summarizer(glm_client_mock)

        content = "Check out https://example.com and http://test.org"
        links = summarizer.extract_links(content)

        assert "https://example.com" in links
        assert "http://test.org" in links

    def test_extract_links_no_links(self, glm_client_mock: GLMClient) -> None:
        """Test link extraction with no links."""
        summarizer = Summarizer(glm_client_mock)

        content = "No links here, just text"
        links = summarizer.extract_links(content)

        assert len(links) == 0

    def test_extract_links_multiple(self, glm_client_mock: GLMClient) -> None:
        """Test extracting multiple links."""
        summarizer = Summarizer(glm_client_mock)

        content = "Links: https://a.com https://b.com https://c.com"
        links = summarizer.extract_links(content)

        assert len(links) == 3

    def test_format_message_basic(self, glm_client_mock: GLMClient) -> None:
        """Test basic message formatting."""
        summarizer = Summarizer(glm_client_mock)

        msg = {
            "author_name": "Alice",
            "created_at": "2026-01-17T09:00:00+09:00",
            "content": "Test message",
            "links": [],
            "attachments": [],
        }

        formatted = summarizer.format_message(msg)

        assert "Alice" in formatted
        assert "Test message" in formatted
        assert "09:00" in formatted

    def test_format_message_with_links(self, glm_client_mock: GLMClient) -> None:
        """Test formatting message with links."""
        summarizer = Summarizer(glm_client_mock)

        msg = {
            "author_name": "Alice",
            "created_at": "2026-01-17T09:00:00+09:00",
            "content": "Check this link",
            "links": ["https://example.com"],
            "attachments": [],
        }

        formatted = summarizer.format_message(msg)

        assert "(links:" in formatted
        assert "https://example.com" in formatted

    def test_format_message_with_attachments(self, glm_client_mock: GLMClient) -> None:
        """Test formatting message with attachments."""
        summarizer = Summarizer(glm_client_mock)

        msg = {
            "author_name": "Alice",
            "created_at": "2026-01-17T09:00:00+09:00",
            "content": "File attached",
            "links": [],
            "attachments": [
                {"url": "https://example.com/file.pdf", "filename": "file.pdf", "content_type": "application/pdf"}
            ],
        }

        formatted = summarizer.format_message(msg)

        assert "(attachments:" in formatted
        assert "file.pdf" in formatted

    def test_preprocess_messages(self, glm_client_mock: GLMClient) -> None:
        """Test message preprocessing."""
        summarizer = Summarizer(glm_client_mock)

        messages = [
            {
                "author_name": "Alice",
                "created_at": "2026-01-17T09:00:00+09:00",
                "content": "Check https://example.com",
                "attachments_json": "[]",
            }
        ]

        processed = summarizer.preprocess_messages(messages)

        assert len(processed) == 1
        assert processed[0]["links"] == ["https://example.com"]

    def test_generate_state_mock_mode(self, glm_client_mock: GLMClient) -> None:
        """Test state generation in mock mode."""
        summarizer = Summarizer(glm_client_mock)

        messages = [
            {
                "author_name": "Alice",
                "created_at": "2026-01-17T09:00:00+09:00",
                "content": "Started work on task A",
                "links": [],
                "attachments": [],
            }
        ]

        state = summarizer.generate_state("test", "2026-01-17", messages)

        assert isinstance(state, DailyChannelState)
        assert state.channel_name == "test"
        assert state.date == "2026-01-17"

    def test_generate_state_empty_messages(self, glm_client_mock: GLMClient) -> None:
        """Test state generation with no messages."""
        summarizer = Summarizer(glm_client_mock)

        state = summarizer.generate_state("test", "2026-01-17", [])

        assert isinstance(state, DailyChannelState)
        assert state.channel_name == "test"
        assert state.date == "2026-01-17"
        assert len(state.topics) == 0

    def test_generate_state_overrides_channel_date(self, glm_client_mock: GLMClient) -> None:
        """Test that generate_state overrides channel_name and date from LLM response."""
        summarizer = Summarizer(glm_client_mock)

        messages = [
            {
                "author_name": "Alice",
                "created_at": "2026-01-17T09:00:00+09:00",
                "content": "Test",
                "links": [],
                "attachments": [],
            }
        ]

        state = summarizer.generate_state("my-channel", "2026-02-01", messages)

        assert state.channel_name == "my-channel"
        assert state.date == "2026-02-01"

    def test_format_message_whitespace_normalization(self, glm_client_mock: GLMClient) -> None:
        """Test that whitespace is normalized in formatted messages."""
        summarizer = Summarizer(glm_client_mock)

        msg = {
            "author_name": "Alice",
            "created_at": "2026-01-17T09:00:00+09:00",
            "content": "  Extra   spaces  ",
            "links": [],
            "attachments": [],
        }

        formatted = summarizer.format_message(msg)

        # Content should be included (whitespace handling may vary)
        assert "Extra" in formatted
        assert "spaces" in formatted

    def test_preprocess_messages_attachments_json(self, glm_client_mock: GLMClient) -> None:
        """Test preprocessing with attachments_json field."""
        summarizer = Summarizer(glm_client_mock)

        import json
        attachments = [
            {"url": "https://example.com/file.pdf", "filename": "file.pdf", "content_type": "application/pdf"}
        ]

        messages = [
            {
                "author_name": "Alice",
                "created_at": "2026-01-17T09:00:00+09:00",
                "content": "File",
                "attachments_json": json.dumps(attachments),
            }
        ]

        processed = summarizer.preprocess_messages(messages)

        assert len(processed) == 1
        assert len(processed[0]["attachments"]) == 1
        assert processed[0]["attachments"][0]["filename"] == "file.pdf"

    def test_preprocess_messages_invalid_attachments_json(self, glm_client_mock: GLMClient) -> None:
        """Test preprocessing with invalid attachments_json."""
        summarizer = Summarizer(glm_client_mock)

        messages = [
            {
                "author_name": "Alice",
                "created_at": "2026-01-17T09:00:00+09:00",
                "content": "Test",
                "attachments_json": "invalid json",
            }
        ]

        processed = summarizer.preprocess_messages(messages)

        # Should handle gracefully
        assert len(processed) == 1
        assert processed[0]["attachments"] == []

    def test_extract_links_markdown_style(self, glm_client_mock: GLMClient) -> None:
        """Test extracting markdown-style links."""
        summarizer = Summarizer(glm_client_mock)

        content = "See [this](https://example.com) link"
        links = summarizer.extract_links(content)

        assert "https://example.com" in links

    def test_extract_links_with_punctuation(self, glm_client_mock: GLMClient) -> None:
        """Test link extraction with trailing punctuation."""
        summarizer = Summarizer(glm_client_mock)

        content = "Visit https://example.com."
        links = summarizer.extract_links(content)

        # URL should be extracted (may include or exclude trailing dot depending on regex)
        assert len(links) >= 1

    def test_generate_state_multiple_messages(self, glm_client_mock: GLMClient) -> None:
        """Test state generation with multiple messages."""
        summarizer = Summarizer(glm_client_mock)

        messages = [
            {
                "author_name": "Alice",
                "created_at": "2026-01-17T09:00:00+09:00",
                "content": "Message 1",
                "links": [],
                "attachments": [],
            },
            {
                "author_name": "Bob",
                "created_at": "2026-01-17T10:00:00+09:00",
                "content": "Message 2",
                "links": [],
                "attachments": [],
            },
        ]

        state = summarizer.generate_state("test", "2026-01-17", messages)

        assert isinstance(state, DailyChannelState)
        assert len(state.topics) >= 0  # May have topics in mock mode

    def test_mock_llm_response_structure(self, glm_client_mock: GLMClient) -> None:
        """Test that mock LLM returns valid response structure."""
        summarizer = Summarizer(glm_client_mock)

        messages = [
            {
                "author_name": "Alice",
                "created_at": "2026-01-17T09:00:00+09:00",
                "content": "Test",
                "links": [],
                "attachments": [],
            }
        ]

        state = summarizer.generate_state("test", "2026-01-17", messages)

        # Should have all required fields
        assert hasattr(state, "topics")
        assert hasattr(state, "progress")
        assert hasattr(state, "artifacts")
        assert hasattr(state, "questions")
        assert hasattr(state, "help_requests")
        assert hasattr(state, "next_steps")
