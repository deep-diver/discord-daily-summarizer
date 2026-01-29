#!/usr/bin/env python3
"""Generate one-liner daily digests for 10 days."""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.events import EventBus
from src.core.summarizer import Summarizer
from src.core.digest import generate_digest
from src.infra.db import Database
from src.infra.glm_client import GLMClient
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def generate_one_liner_summary(glm_client: GLMClient, channel_name: str, date: str, messages: list) -> str:
    """Generate a one-line summary for a channel.

    Args:
        glm_client: GLM client instance
        channel_name: Channel name
        date: Date string
        messages: List of message dicts

    Returns:
        One-line summary string
    """
    if not messages:
        return f"No activity in #{channel_name}"

    # Build a simpler prompt for one-liner summary
    message_contents = [f"{m['author_name']}: {m['content']}" for m in messages[:15]]
    messages_text = "\n".join(message_contents)

    prompt = f"""You are a tech lead writing a DAILY STATUS HEADLINE for #{channel_name} on {date}.

Write ONE eye-catching, specific sentence (max 25 words) that captures WHAT the team actually worked on.

❌ BAD (too generic):
- "Activity focused on bug fixes, testing"
- "Team worked on API and authentication"

✅ GOOD (specific & action-oriented):
- "Debugging API rate limit issues blocking production deployment"
- "Refactored authentication flow to improve login reliability"
- "Added comprehensive unit tests for payment processing"
- "Deployed hotfix for critical memory leak in worker"
- "Optimizing database queries slowing down dashboard"

Messages to analyze:
{messages_text}

Headline:"""

    try:
        response = glm_client.chat(
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.8,
        )
        # Small delay to avoid rate limiting
        time.sleep(1)
        # Clean up the response
        summary = response.strip().strip('."')
        # Remove common prefixes
        for prefix in ["Summary: ", "In #", "On " + date, "On " + channel_name, "The channel discussed ", "Headline: "]:
            if summary.startswith(prefix):
                summary = summary[len(prefix):].strip()

        # Fallback if empty
        if not summary or len(summary) < 10:
            # More intelligent fallback that extracts specifics
            actions = []
            blockers = []

            for m in messages[:15]:
                content = m.get('content', '').lower()
                if any(word in content for word in ['fixed', 'resolved', 'finished', 'completed', 'deployed']):
                    if 'bug' in content or 'fix' in content:
                        actions.append('Fixed bugs')
                    elif 'test' in content:
                        actions.append('Completed testing')
                    elif 'api' in content:
                        actions.append('API work completed')
                elif any(word in content for word in ['blocked', 'stuck', 'waiting', 'issue', 'error']):
                    if 'api' in content:
                        blockers.append('API issues')
                    elif 'auth' in content or 'login' in content:
                        blockers.append('Auth problems')
                    elif 'deploy' in content:
                        blockers.append('Deployment blocked')
                elif 'working on' in content or 'implementing' in content or 'adding' in content:
                    if 'auth' in content or 'login' in content:
                        actions.append('Building auth features')
                    elif 'test' in content:
                        actions.append('Writing tests')
                    elif 'api' in content:
                        actions.append('Developing API')

            if actions:
                summary = ', '.join(actions[:2])
                if blockers:
                    summary += f' (blocked by {blockers[0]})'
                return summary
            else:
                return f"{len(messages)} messages from {len(set(m['author_name'] for m in messages))} team members"

        return summary
    except Exception as e:
        # Fallback: return simple summary
        return f"{len(messages)} messages from {len(set(m['author_name'] for m in messages))} team members"


def main():
    console = Console()
    event_bus = EventBus()

    # Setup
    api_key = "7797009ef2f64fd595decd99897b8adb.5twOwcH95GO2MEqo"
    db_path = "data/app.db"
    channels = ["dev", "test", "general"]
    start_date = "2026-01-20"

    console.print("[bold cyan]One-Liner Daily Digest Pipeline[/bold cyan]")
    console.print()

    # Create GLM client and summarizer
    glm_client = GLMClient(event_bus=event_bus, api_key=api_key)
    summarizer = Summarizer(glm_client, event_bus)

    digest_channel_name = "daily-digest"
    digest_channel_id = "c-daily-digest"

    results = []

    for day_offset in range(10):
        date = (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=day_offset)).strftime("%Y-%m-%d")

        console.print(f"[cyan]Processing {date}...[/cyan]")

        with Database(db_path, event_bus) as db:
            channel_summaries = {}

            for channel_name in channels:
                # Get messages for this channel/date
                messages = db.get_messages(
                    channel_name=channel_name,
                    start_time=f"{date}T00:00:00+09:00",
                    end_time=f"{date}T23:59:59+09:00",
                )

                # Convert to message dicts
                message_dicts = [
                    {
                        "author_name": msg.author_name,
                        "created_at": msg.created_at,
                        "content": msg.content,
                        "links": msg.links,
                        "attachments_json": str([a.model_dump() for a in msg.attachments]),
                    }
                    for msg in messages
                ]

                # Generate one-liner summary
                one_liner = generate_one_liner_summary(glm_client, channel_name, date, message_dicts)
                channel_summaries[channel_name] = one_liner

                # Skip full state generation - we only need one-liners for digest
                # This reduces API calls from 60 to 30 for 10-day pipeline

            # Create digest content
            digest_lines = []
            digest_lines.append(f"# Daily Digest for {date}")
            digest_lines.append("")

            for channel_name in channels:
                summary = channel_summaries.get(channel_name, "No activity")
                digest_lines.append(f"**#{channel_name}**: {summary}")

            digest_lines.append("")
            digest_lines.append("*Generated by Discord Daily Summarizer*")

            digest_content = "\n".join(digest_lines)

            # Create digest message and insert it
            from src.core.models import MessageEvent
            digest_message = MessageEvent(
                message_id=f"digest-{date}",
                channel_id=digest_channel_id,
                channel_name=digest_channel_name,
                author_id="bot-daily-digest",
                author_name="Daily Digest Bot",
                created_at=f"{date}T20:00:00+09:00",
                content=digest_content,
                attachments=[],
                links=[],
            )
            db.insert_messages([digest_message])

            results.append({
                "date": date,
                "summaries": channel_summaries,
            })

            # Show the digest
            console.print()
            console.print(Panel(
                Text.from_markup(digest_content),
                title=f"[bold green]Daily Digest - {date}[/bold green]",
                border_style="green",
            ))
            console.print()

    # Display summary table
    console.print()
    console.print("[bold cyan]10-Day One-Liner Digest Results[/bold cyan]")
    console.print()

    table = Table(title="Daily One-Liner Summaries", show_header=True, header_style="bold magenta")
    table.add_column("Date", style="cyan", width=12)
    table.add_column("dev", style="green", width=50)
    table.add_column("test", style="yellow", width=50)
    table.add_column("general", style="blue", width=50)

    for r in results:
        table.add_row(
            r["date"],
            r["summaries"].get("dev", "—"),
            r["summaries"].get("test", "—"),
            r["summaries"].get("general", "—"),
        )

    console.print(table)
    console.print()
    console.print(f"[green]✓ All digests posted to #{digest_channel_name}[/green]")


if __name__ == "__main__":
    main()
