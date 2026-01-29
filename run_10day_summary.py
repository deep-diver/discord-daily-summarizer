#!/usr/bin/env python3
"""Generate summaries for 10 days of messages."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.events import EventBus
from src.core.summarizer import Summarizer
from src.core.delta import compute_delta
from src.core.digest import generate_digest
from src.infra.db import Database
from src.infra.glm_client import GLMClient
from rich.console import Console
from rich.table import Table


def main():
    console = Console()
    event_bus = EventBus()

    # Setup
    api_key = "7797009ef2f64fd595decd99897b8adb.5twOwcH95GO2MEqo"
    db_path = "data/app.db"
    channels = ["dev", "test", "general"]
    start_date = "2026-01-20"

    console.print("[bold cyan]10-Day Summarization Pipeline[/bold cyan]")
    console.print()

    # Create GLM client
    glm_client = GLMClient(event_bus=event_bus, api_key=api_key)
    summarizer = Summarizer(glm_client, event_bus)

    results = []

    for day_offset in range(10):
        date = (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=day_offset)).strftime("%Y-%m-%d")

        console.print(f"[cyan]Processing {date}...[/cyan]")

        with Database(db_path, event_bus) as db:
            all_channels = db.get_channels()
            daily_summary = {
                "date": date,
                "channels": {},
                "total_topics": 0,
                "total_blockers": 0,
            }

            for channel_info in all_channels:
                channel_name = channel_info["channel_name"]
                channel_id = channel_info["channel_id"]

                # Get messages for this channel/date
                messages = db.get_messages(
                    channel_name=channel_name,
                    start_time=f"{date}T00:00:00+09:00",
                    end_time=f"{date}T23:59:59+09:00",
                )

                if not messages:
                    continue

                # Generate state
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

                try:
                    state = summarizer.generate_state(channel_name, date, message_dicts)

                    # Save state
                    db.save_state(state, "Generated via 10-day pipeline", channel_id)

                    # Store summary info
                    daily_summary["channels"][channel_name] = {
                        "messages": len(messages),
                        "topics": len(state.topics),
                        "blockers": len(state.progress.blocked),
                        "finished": len(state.progress.finished),
                    }
                    daily_summary["total_topics"] += len(state.topics)
                    daily_summary["total_blockers"] += len(state.progress.blocked)

                except Exception as e:
                    console.print(f"  [red]Error for {channel_name}: {e}[/red]")

            results.append(daily_summary)
            console.print(f"  ✓ {date}: {daily_summary['total_topics']} topics, {daily_summary['total_blockers']} blockers")

    # Display summary table
    console.print()
    console.print("[bold cyan]10-Day Summary Results[/bold cyan]")
    console.print()

    table = Table(title="Daily Summarization Results", show_header=True, header_style="bold magenta")
    table.add_column("Date", style="cyan")
    table.add_column("dev", justify="center", style="green")
    table.add_column("test", justify="center", style="yellow")
    table.add_column("general", justify="center", style="blue")
    table.add_column("Total Topics", justify="right", style="magenta")
    table.add_column("Blockers", justify="right", style="red")

    for r in results:
        dev_info = r["channels"].get("dev", {})
        test_info = r["channels"].get("test", {})
        gen_info = r["channels"].get("general", {})

        dev_text = f"{dev_info.get('messages', 0)}msg\n{dev_info.get('topics', 0)}📋" if dev_info else "—"
        test_text = f"{test_info.get('messages', 0)}msg\n{test_info.get('topics', 0)}📋" if test_info else "—"
        gen_text = f"{gen_info.get('messages', 0)}msg\n{gen_info.get('topics', 0)}📋" if gen_info else "—"

        table.add_row(
            r["date"],
            dev_text,
            test_text,
            gen_text,
            str(r["total_topics"]),
            str(r["total_blockers"])
        )

    console.print(table)
    console.print()

    # Totals
    total_messages = sum(
        sum(c.get("messages", 0) for c in r["channels"].values())
        for r in results
    )
    total_topics = sum(r["total_topics"] for r in results)
    total_blockers = sum(r["total_blockers"] for r in results)

    console.print(f"[green]Total Messages:[/green] {total_messages}")
    console.print(f"[cyan]Total Topics Extracted:[/cyan] {total_topics}")
    console.print(f"[red]Total Blockers Identified:[/red] {total_blockers}")


if __name__ == "__main__":
    main()
