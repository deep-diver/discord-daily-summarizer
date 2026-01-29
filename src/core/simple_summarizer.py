"""Simple summarizer for brief 3-sentence summaries."""

import json
import re
from datetime import datetime
from typing import Any

from src.core.events import EventBus
from src.infra.glm_client import GLMClient


class SimpleSummarizer:
    """Simple summarizer that generates brief 3-sentence summaries.

    Features:
    - Condensed 3-sentence format
    - Quick reading time
    - Essential information only
    """

    LINK_PATTERN = re.compile(r"https?://[^\s\]\)\"]+")

    def __init__(self, glm_client: GLMClient, event_bus: EventBus | None = None) -> None:
        """Initialize simple summarizer.

        Args:
            glm_client: GLM client for LLM calls
            event_bus: Optional event bus for publishing events
        """
        self._glm_client = glm_client
        self._event_bus = event_bus or EventBus()

    def extract_links(self, content: str) -> list[str]:
        """Extract links from message content.

        Args:
            content: Message content

        Returns:
            List of URLs found in content
        """
        return self.LINK_PATTERN.findall(content)

    def format_message(self, msg: dict[str, Any]) -> str:
        """Format a message for LLM consumption.

        Args:
            msg: Message dict with author, content, time, links, attachments

        Returns:
            Formatted message string
        """
        # Parse timestamp to get time
        try:
            dt = datetime.fromisoformat(msg["created_at"])
            time_str = dt.strftime("%H:%M")
        except Exception:
            time_str = "??"

        parts = [f"[{time_str}] {msg['author_name']}:"]
        parts.append(msg['content'])

        # Add links
        if msg.get("links"):
            parts.append(f"(links: {', '.join(msg['links'])})")

        # Add attachments
        attachments = msg.get("attachments", [])
        if attachments:
            att_names = [a['filename'] for a in attachments]
            parts.append(f"(attachments: {', '.join(att_names)})")

        return " ".join(parts)

    def preprocess_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Preprocess messages for summarization.

        Args:
            messages: Raw messages from database

        Returns:
            Preprocessed messages with extracted links
        """
        processed = []

        for msg in messages:
            # Extract links from content
            content = msg.get("content", "")
            links = self.extract_links(content)

            # Parse attachments
            try:
                attachments = json.loads(msg.get("attachments_json", "[]"))
            except json.JSONDecodeError:
                attachments = []

            processed.append({
                "author_name": msg["author_name"],
                "created_at": msg["created_at"],
                "content": content.strip(),
                "links": links,
                "attachments": attachments,
            })

        return processed

    def generate_summary(
        self,
        channel_name: str,
        date: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate a simple 3-sentence summary from messages.

        Args:
            channel_name: Channel name
            date: Date string (YYYY-MM-DD)
            messages: List of message dicts

        Returns:
            Dict with simple summary data

        Raises:
            ValueError: If LLM response is invalid
        """
        if not messages:
            return {
                "channel_name": channel_name,
                "date": date,
                "summary": "No messages found for this date.",
                "key_topics": [],
                "key_links": [],
            }

        # Preprocess messages
        processed = self.preprocess_messages(messages)

        # Format messages for LLM
        formatted_messages = [self.format_message(m) for m in processed]
        messages_text = "\n".join(formatted_messages)

        # Build prompt
        prompt = self._build_simple_prompt(channel_name, date, messages_text)

        # Call LLM
        response = self._glm_client.chat(
            messages=[
                {"role": "system", "content": "You are a helpful assistant that creates brief, concise summaries of Discord conversations."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        # Parse response
        try:
            summary_data = self._extract_json(response)
            summary_data["channel_name"] = channel_name
            summary_data["date"] = date
            return summary_data

        except Exception as e:
            raise ValueError(f"Failed to parse LLM response: {e}") from e

    def _build_simple_prompt(self, channel_name: str, date: str, messages_text: str) -> str:
        """Build prompt for generating simple summary.

        Args:
            channel_name: Channel name
            date: Date string
            messages_text: Formatted messages

        Returns:
            Prompt for LLM
        """
        return f"""Analyze the following Discord messages from channel #{channel_name} on {date} and create a brief 3-sentence summary.

Messages:
{messages_text}

Generate a JSON response with this exact schema:
{{
  "summary": "Three sentences maximum: 1) What was discussed/worked on, 2) Key outcomes or decisions, 3) Any blockers or next steps. Keep it very concise.",
  "key_topics": ["topic1", "topic2"],
  "key_links": ["https://example.com"]
}}

Requirements:
- Output ONLY valid JSON matching the schema above
- The summary must be exactly 3 sentences or less
- Each sentence should be concise (under 20 words)
- Focus on the most important information only
- Extract the 2-3 most important topics discussed
- Extract any important links shared
- Be faithful to the actual messages - don't hallucinate

Respond with ONLY the JSON object, no other text."""

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from LLM response.

        Args:
            text: LLM response text

        Returns:
            Parsed JSON dict

        Raises:
            ValueError: If JSON cannot be extracted
        """
        # Try to parse the whole response as JSON
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find first JSON object
        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        if obj_match:
            try:
                return json.loads(obj_match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not extract valid JSON from response: {text[:200]}")


def render_simple_summary(summary: dict[str, Any]) -> str:
    """Render simple summary as Markdown.

    Args:
        summary: Simple summary dict

    Returns:
        Markdown summary
    """
    lines = [
        f"## #{summary['channel_name']} - Daily Summary ({summary['date']})",
        "",
    ]

    # Main summary (3 sentences)
    lines.append(f"{summary['summary']}")
    lines.append("")

    # Key topics
    if summary.get("key_topics"):
        lines.append("**Topics:** " + ", ".join(summary["key_topics"]))
        lines.append("")

    # Key links
    if summary.get("key_links"):
        lines.append("**Links:** " + ", ".join(summary["key_links"]))
        lines.append("")

    return "\n".join(lines)
