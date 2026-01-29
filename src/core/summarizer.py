"""Summarizer for generating daily channel states via LLM."""

import json
import re
from datetime import datetime
from typing import Any

from src.core.events import EventBus
from src.core.models import DailyChannelState
from src.infra.glm_client import GLMClient


class Summarizer:
    """Summarizer for generating daily channel states.

    Features:
    - Message preprocessing and formatting
    - Link extraction
    - Chunking for large message sets
    - LLM-based state generation
    """

    LINK_PATTERN = re.compile(r"https?://[^\s\]\)\"]+")

    def __init__(self, glm_client: GLMClient, event_bus: EventBus | None = None) -> None:
        """Initialize summarizer.

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

    def generate_state(
        self,
        channel_name: str,
        date: str,
        messages: list[dict[str, Any]],
    ) -> DailyChannelState:
        """Generate daily channel state from messages.

        Args:
            channel_name: Channel name
            date: Date string (YYYY-MM-DD)
            messages: List of message dicts

        Returns:
            Daily channel state

        Raises:
            ValueError: If LLM response is invalid
        """
        if not messages:
            return DailyChannelState(channel_name=channel_name, date=date)

        # Preprocess messages
        processed = self.preprocess_messages(messages)

        # Format messages for LLM
        formatted_messages = [self.format_message(m) for m in processed]
        messages_text = "\n".join(formatted_messages)

        # Build prompt
        prompt = self._build_state_prompt(channel_name, date, messages_text)

        # Call LLM
        response = self._glm_client.chat(
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes Discord channel activity."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

        # Parse response
        try:
            state_data = self._extract_json(response)
            state = DailyChannelState(**state_data)

            # Validate channel_name and date match
            if state.channel_name != channel_name:
                state.channel_name = channel_name
            if state.date != date:
                state.date = date

            return state

        except Exception as e:
            raise ValueError(f"Failed to parse LLM response as DailyChannelState: {e}") from e

    def _build_state_prompt(self, channel_name: str, date: str, messages_text: str) -> str:
        """Build prompt for generating daily channel state.

        Args:
            channel_name: Channel name
            date: Date string
            messages_text: Formatted messages

        Returns:
            Prompt for LLM
        """
        return f"""Analyze the following Discord messages from channel #{channel_name} on {date} and generate a structured daily state JSON.

Messages:
{messages_text}

Generate a JSON response with this exact schema:
{{
  "channel_name": "{channel_name}",
  "date": "{date}",
  "topics": ["topic discussed"],
  "progress": {{
    "started": ["task started"],
    "continued": ["task continued"],
    "finished": ["task completed"],
    "blocked": ["task blocked"]
  }},
  "artifacts": {{
    "links": ["https://example.com"],
    "repos": ["https://github.com/org/repo"],
    "docs": ["documentation link"]
  }},
  "questions": ["question asked"],
  "help_requests": ["help requested"],
  "next_steps": ["next action"]
}}

Requirements:
- Output ONLY valid JSON matching the schema above
- Use empty arrays [] rather than omitting fields
- Extract ALL links mentioned in messages
- Identify repos, docs, and other artifacts
- Detect blockers, questions, and help requests
- Be faithful to the actual messages - don't hallucinate
- Include all keys even if empty

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
