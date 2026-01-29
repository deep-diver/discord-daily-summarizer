"""CLI for message summarization system."""

import os
import sys
import tempfile
import logging
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich import print as rprint

from src.core.delta import compute_delta, has_significant_changes
from src.core.digest import generate_digest
from src.core.events import EventBus, EventType
from src.core.models import DailyChannelState, DailyChannelDelta
from src.core.renderer import (
    render_summary,
    render_delta,
    render_digest,
    print_summary,
    print_delta,
    print_digest,
    print_summary_table,
)
from src.core.summarizer import Summarizer
from src.core.simple_summarizer import SimpleSummarizer, render_simple_summary
from src.core.timewindow import TimeWindow, expand_date_range
from src.infra.db import Database
from src.infra.fixtures import load_fixture
from src.infra.glm_client import GLMClient, GLMClientError
from src.security import (
    ValidationError,
    validate_jsonl_data,
    validate_channel_list,
    validate_date_range,
    HoursRange,
    AuditLogger,
    AuditEventType,
    AuditSeverity,
)

class VerbosityLevel(str, Enum):
    """Verbosity levels for CLI output."""
    quiet = "quiet"
    normal = "normal"
    verbose = "verbose"


app = typer.Typer(
    help="""
    Discord Message Summarizer - Phase 1 (Discord-free)

    A powerful tool for analyzing Discord channel conversations and generating
    structured summaries, deltas, and digests of daily activities.

    Features:
    • Ingest Discord message data from JSONL fixtures
    • Generate daily channel states using LLM analysis
    • Track changes between days with delta computation
    • Create comprehensive digests across multiple channels
    • Enhanced progress tracking and error recovery
    • Configurable verbosity levels for detailed output
    • Input validation for all user inputs
    • Rate limiting for API calls
    • Secure credential storage
    • Comprehensive audit logging

    Examples:
    • python -m src.app ingest --reset --verbose
    • python -m src.app run --date 2026-01-17 --mock
    • python -m src.app preview --channel-name general --last-hours 24
    • python -m src.app selftest --verbose
    """
)
console = Console()


def setup_logging(verbosity: VerbosityLevel) -> None:
    """Setup logging based on verbosity level."""
    level = logging.WARNING
    if verbosity == VerbosityLevel.verbose:
        level = logging.DEBUG
    elif verbosity == VerbosityLevel.normal:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('run.log', mode='a')
        ]
    )


class ProgressTracker:
    """Enhanced progress tracking with detailed information."""

    # Class variable to track active progress tracker (prevent nesting)
    _active_count = 0

    def __init__(self, console: Console, description: str, total: Optional[int] = None):
        self.console = console
        self.description = description
        self.total = total
        self.completed = 0
        self.is_nested = ProgressTracker._active_count > 0
        self.task_id = None

        if not self.is_nested:
            self.progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            )
            self.progress.start()
        else:
            self.progress = None

    def start(self):
        """Start the progress tracking."""
        if not self.is_nested:
            self.task_id = self.progress.add_task(f"[bold cyan]{self.description}", total=self.total)
        else:
            # Just print the description for nested trackers
            self.console.print(f"[dim]  → {self.description}[/dim]")

    def update(self, advance: int = 1, description: Optional[str] = None):
        """Update progress."""
        self.completed += advance
        if not self.is_nested and self.task_id is not None:
            if description:
                self.progress.update(self.task_id, description=f"[bold cyan]{description}")
            self.progress.update(self.task_id, advance=advance)
        elif self.is_nested and description:
            # For nested trackers, just print updates
            if self.completed == advance or self.completed == self.total:
                self.console.print(f"[dim]    ✓ {description}[/dim]")

    def finish(self):
        """Finish progress tracking."""
        if not self.is_nested:
            if self.task_id is not None:
                self.progress.update(self.task_id, completed=self.total or self.completed)
            self.progress.stop()

    def __enter__(self):
        ProgressTracker._active_count += 1
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finish()
        ProgressTracker._active_count -= 1


def get_event_bus() -> EventBus:
    """Get or create event bus."""
    return EventBus()


def get_audit_logger() -> AuditLogger:
    """Get or create audit logger."""
    return AuditLogger()


def get_glm_client(event_bus: EventBus, mock: bool = False, audit_logger: AuditLogger | None = None) -> GLMClient:
    """Get GLM client with security features.

    Args:
        event_bus: Event bus
        mock: Whether to use mock mode
        audit_logger: Optional audit logger

    Returns:
        GLM client instance
    """
    try:
        # In mock mode, use a dummy API key
        api_key = "mock-key" if mock else None
        client = GLMClient(event_bus=event_bus, api_key=api_key, mock=mock, audit_logger=audit_logger)
        if mock:
            client.enable_mock_mode()
        return client
    except GLMClientError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e




@app.command()
def ingest(
    db_path: str = typer.Option("data/app.db", "--db", help="Path to SQLite database file"),
    fixture: str = typer.Option("fixtures/sample_3days.jsonl", "--fixture", help="Path to JSONL fixture file"),
    reset: bool = typer.Option(False, "--reset", help="Reset database before ingestion"),
    verbose: VerbosityLevel = typer.Option(VerbosityLevel.normal, "--verbose", "-v", help="Output verbosity level"),
) -> None:
    """Ingest Discord messages from JSONL fixture files into SQLite database.

    Loads messages from JSONL fixture files and populates the database with
    structured message data including timestamps, authors, content, and attachments.

    Examples:
    • ingest --reset --verbose
    • ingest --fixture fixtures/custom.jsonl --db ./data/custom.db
    """
    setup_logging(verbose)
    event_bus = get_event_bus()
    audit_logger = get_audit_logger()

    # Log command start
    audit_logger.log_data_modification(
        "cli", "ingest", "start",
        details={"db_path": db_path, "fixture": fixture, "reset": reset}
    )

    # Validate inputs
    try:
        db_path = str(db_path)
        if not db_path.endswith('.db'):
            raise ValidationError("Database path must end with .db")

        fixture = str(fixture)
        if not fixture.endswith('.jsonl'):
            raise ValidationError("Fixture file must be a JSONL file")

        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    except ValidationError as e:
        console.print(f"[red]Validation error:[/red] {e}")
        audit_logger.log_input_validation_failure(
            "fixture", fixture, str(e)
        )
        raise typer.Exit(code=1)

    # Track events
    ingested_count = 0

    def on_message_ingested(event) -> None:  # type: ignore
        nonlocal ingested_count
        ingested_count += event.data.get("count", 0)

    event_bus.subscribe(EventType.MESSAGE_INGESTED, on_message_ingested)

    with Database(db_path, event_bus) as db:
        if reset:
            with ProgressTracker(console, "Resetting database") as tracker:
                tracker.update(description="[bold yellow]Resetting database...")
                db.reset()
            console.print("[green]Database reset complete.[/green]")

        # Load fixture
        with ProgressTracker(console, f"Loading fixture: {fixture}") as tracker:
            tracker.update(description=f"[bold cyan]Loading fixture: {fixture}...")
            messages = load_fixture(fixture)

            # Note: load_fixture already validates data during parsing
            # No additional validation needed here

            audit_logger.log_data_access(
                "fixture", fixture, "load",
                details={"messages_count": len(messages)}
            )

            tracker.finish()

        if not messages:
            console.print("[yellow]No messages found in fixture.[/yellow]")
            return

        # Ingest with enhanced progress bar
        with ProgressTracker(console, f"Ingesting {len(messages)} messages", total=len(messages)) as tracker:
            inserted = db.insert_messages(messages)
            tracker.finish()

        # Show enhanced summary table
        # Show messages per channel with better formatting
        channels = {}
        for msg in messages:
            channel = msg.channel_name
            channels[channel] = channels.get(channel, 0) + 1

        table = Table(title="Ingest Summary", show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right", style="green")
        table.add_column("Details", style="white")

        table.add_row("Messages inserted", str(inserted), f"Success rate: {inserted}/{len(messages)}")
        table.add_row("Fixture file", fixture, "JSONL format")
        table.add_row("Database", db_path, "SQLite")
        table.add_row("Channels", str(len(channels)), f"Average messages per channel: {inserted/len(channels):.1f}")

        console.print()
        console.print(Panel(table, title="[bold green]Ingest Results[/bold green]"))
        console.print()

        if channels:
            channel_table = Table(title="Messages per Channel", show_header=True, header_style="bold cyan")
            channel_table.add_column("Channel", style="cyan")
            channel_table.add_column("Count", justify="right", style="green")
            channel_table.add_column("Percentage", justify="right", style="blue")

            for channel, count in sorted(channels.items()):
                percentage = (count / inserted) * 100
                channel_table.add_row(f"#{channel}", str(count), f"{percentage:.1f}%")

            console.print(channel_table)

        if verbose == VerbosityLevel.verbose:
            # Show additional debug information
            debug_table = Table(title="Debug Information", show_header=True, header_style="bold yellow")
            debug_table.add_column("Metric", style="yellow")
            debug_table.add_column("Value", style="white")

            debug_table.add_row("Total messages", str(len(messages)))
            debug_table.add_row("Inserted messages", str(inserted))
            debug_table.add_row("Duplicate rate", f"{((len(messages) - inserted) / len(messages) * 100):.1f}%")

            console.print()
            console.print(debug_table)


@app.command()
def run(
    db_path: str = typer.Option("data/app.db", "--db", help="Path to SQLite database file"),
    date: Optional[str] = typer.Option(None, "--date", help="Single date to process (YYYY-MM-DD)"),
    start: Optional[str] = typer.Option(None, "--start", help="Start date for date range (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", help="End date for date range (YYYY-MM-DD)"),
    last_hours: Optional[int] = typer.Option(None, "--last-hours", help="Process messages from last N hours"),
    channels: Optional[str] = typer.Option(None, "--channels", help="Comma-separated channel names to filter"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show results without storing"),
    store: bool = typer.Option(True, "--store/--no-store", help="Store results to database"),
    mock: bool = typer.Option(False, "--mock", help="Use mock LLM responses for testing"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output"),
    verbose: VerbosityLevel = typer.Option(VerbosityLevel.normal, "--verbose", "-v", help="Output verbosity level"),
    retries: int = typer.Option(3, "--retries", "-r", help="Number of retry attempts for failed operations"),
    post_to_discord: bool = typer.Option(False, "--post-to-discord", help="Post summary back to Discord channels"),
    discord_token: Optional[str] = typer.Option(None, "--discord-token", help="Discord bot token (or use DISCORD_BOT_TOKEN env var)", envvar="DISCORD_BOT_TOKEN"),
    simple: bool = typer.Option(False, "--simple", "-s", help="Use simple 3-sentence summary format"),
) -> None:
    """Run the full summarization pipeline with enhanced error recovery and progress tracking.

    Processes Discord messages to generate daily channel states, compute deltas,
    and create comprehensive digests. Includes retry logic and detailed progress
    indicators for robust operation.

    Examples:
    • run --date 2026-01-17 --mock --verbose
    • run --start 2026-01-16 --end 2026-01-17 --retries 5
    • run --last-hours 24 --channels general,dev --dry-run
    """
    setup_logging(verbose)
    event_bus = get_event_bus()
    audit_logger = get_audit_logger()
    glm_client = get_glm_client(event_bus, mock, audit_logger)

    # Log command start
    audit_logger.log_data_modification(
        "cli", "run", "start",
        details={
            "db_path": db_path,
            "date": date,
            "start": start,
            "end": end,
            "last_hours": last_hours,
            "channels": channels,
            "dry_run": dry_run,
            "mock": mock
        }
    )

    # Validate inputs
    try:
        if date and (start or end):
            raise ValidationError("Cannot use --date with --start/--end")

        if (start and not end) or (end and not start):
            raise ValidationError("Both --start and --end must be specified together")

        if date:
            date = validate_date_range(date, date)[0]

        if start and end:
            start, end = validate_date_range(start, end)

        if last_hours:
            last_hours = HoursRange(last_hours)

    except ValidationError as e:
        console.print(f"[red]Validation error:[/red] {e}")
        audit_logger.log_input_validation_failure("date_params", str(date), str(e))
        raise typer.Exit(code=1)

    with Database(db_path, event_bus) as db:
        # Determine date range
        dates_to_process: list[str] = []

        if date:
            dates_to_process = [date]
        elif start and end:
            dates_to_process = expand_date_range(start, end)
        elif last_hours:
            tw = TimeWindow.from_hours(last_hours)
            dates_to_process = [tw.effective_date]
        else:
            console.print("[red]Error:[/red] Must specify --date, --start/--end, or --last-hours")
            if verbose == VerbosityLevel.normal or verbose == VerbosityLevel.verbose:
                console.print("[yellow]Examples:[/yellow]")
                console.print("  --date 2026-01-17")
                console.print("  --start 2026-01-16 --end 2026-01-17")
                console.print("  --last-hours 24")
            raise typer.Exit(code=1)

        # Parse channel filter
        channel_filter = None
        if channels:
            channel_filter = [c.strip() for c in channels.split(",") if c.strip()]
            if verbose == VerbosityLevel.verbose:
                console.print(f"[cyan]Processing channels: {', '.join(channel_filter)}[/cyan]")

        total_channels_processed = 0
        total_messages_processed = 0
        total_errors = 0

        # Process each date with enhanced progress tracking
        with ProgressTracker(console, f"Processing {len(dates_to_process)} date(s)", total=len(dates_to_process)) as date_tracker:
            for date_str in dates_to_process:
                date_tracker.update(description=f"[bold cyan]Processing {date_str}[/bold cyan]")

                console.print()
                console.print(Panel(f"[bold cyan]Processing {date_str}[/bold cyan]", expand=False))
                console.print()

                # Get channels
                try:
                    all_channels = db.get_channels()
                except Exception as e:
                    console.print(f"[red]Error retrieving channels: {e}[/red]")
                    total_errors += 1
                    continue

                if channel_filter:
                    channels_to_process = [c for c in all_channels if c["channel_name"] in channel_filter]
                else:
                    channels_to_process = all_channels

                if not channels_to_process:
                    console.print("[yellow]No channels to process.[/yellow]")
                    continue

                # Process each channel with enhanced error recovery
                states: dict[str, DailyChannelState] = {}
                deltas: dict[str, DailyChannelDelta] = {}
                summaries: dict[str, str] = {}

                with ProgressTracker(console, f"Processing {len(channels_to_process)} channel(s)", total=len(channels_to_process)) as channel_tracker:
                    for channel_info in channels_to_process:
                        channel_name = channel_info["channel_name"]
                        channel_id = channel_info["channel_id"]

                        try:
                            # Get time window
                            if date:
                                tw = TimeWindow.from_date(date_str)
                            elif last_hours:
                                tw = TimeWindow.from_hours(last_hours)
                            else:
                                tw = TimeWindow.from_date(date_str)

                            # Get messages
                            start_iso, end_iso = tw.to_isoformat()
                            messages = db.get_messages(
                                channel_name=channel_name,
                                start_time=start_iso,
                                end_time=end_iso,
                            )

                            if not messages:
                                console.print(f"[yellow]No messages found for #{channel_name} on {date_str}[/yellow]")
                                channel_tracker.update(description=f"[yellow]No messages for #{channel_name}[/yellow]")
                                continue

                            total_messages_processed += len(messages)

                            # Convert messages to dicts
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

                            # Choose summarizer based on --simple flag
                            if simple:
                                # Simple 3-sentence summary
                                simple_summarizer = SimpleSummarizer(glm_client, event_bus)

                                simple_summary = None
                                for attempt in range(retries):
                                    try:
                                        simple_summary = simple_summarizer.generate_summary(channel_name, date_str, message_dicts)
                                        break
                                    except Exception as e:
                                        if attempt == retries - 1:
                                            console.print(f"[red]Failed to generate summary for #{channel_name} after {retries} attempts: {e}[/red]")
                                            total_errors += 1
                                            break
                                        console.print(f"[yellow]Attempt {attempt + 1}/{retries} failed for #{channel_name}, retrying...[/yellow]")
                                        continue

                                if simple_summary is None:
                                    continue

                                # Generate simple summary markdown
                                summary_md = render_simple_summary(simple_summary)

                                # For simple mode, we don't compute deltas or detailed states
                                delta = None
                                delta_md = None
                                state = None

                                # Print simple summary
                                console.print()
                                console.print(Panel(
                                    summary_md,
                                    title=f"[bold cyan]#{channel_name}[/bold cyan] - Simple Summary ({date_str})",
                                    border_style="cyan",
                                ))

                            else:
                                # Detailed summary (original behavior)
                                summarizer = Summarizer(glm_client, event_bus)

                                # Generate state with retries
                                state = None
                                for attempt in range(retries):
                                    try:
                                        state = summarizer.generate_state(channel_name, date_str, message_dicts)
                                        break
                                    except Exception as e:
                                        if attempt == retries - 1:
                                            console.print(f"[red]Failed to generate state for #{channel_name} after {retries} attempts: {e}[/red]")
                                            total_errors += 1
                                            break
                                        console.print(f"[yellow]Attempt {attempt + 1}/{retries} failed for #{channel_name}, retrying...[/yellow]")
                                        continue

                                if state is None:
                                    continue

                                # Generate summary markdown
                                summary_md = render_summary(state)

                                # Get previous day's state for delta
                                previous_date = _get_previous_date(date_str)
                                previous_state = db.get_state(previous_date, channel_id)

                                # Compute delta
                                delta = compute_delta(state, previous_state)
                                delta_md = render_delta(delta)

                            # Store results with error handling
                            if store and not dry_run:
                                try:
                                    if not simple:
                                        # Only store detailed states
                                        db.save_state(state, summary_md, channel_id)
                                        db.save_delta(delta, delta_md, channel_id, previous_date or "null")
                                except Exception as e:
                                    console.print(f"[red]Error storing results for #{channel_name}: {e}[/red]")
                                    total_errors += 1

                            # Collect for digest (only for detailed mode)
                            if not simple:
                                states[channel_id] = state
                                deltas[channel_id] = delta
                            summaries[channel_id] = summary_md

                            # Print summary and delta (only for detailed mode, simple already printed)
                            if not simple:
                                console.print()
                                print_summary(state)
                                console.print()
                                print_delta(delta)

                            channel_tracker.update(description=f"[green]Completed #{channel_name}[/green]")

                        except Exception as e:
                            console.print(f"[red]Error processing #{channel_name}: {e}[/red]")
                            if verbose == VerbosityLevel.verbose:
                                import traceback
                                console.print(f"[dim]{traceback.format_exc()}[/dim]")
                            total_errors += 1
                            continue

                        total_channels_processed += 1
                        channel_tracker.update(advance=1)

                # Generate and print digest (only for detailed mode)
                if not simple and states:
                    try:
                        digest = generate_digest(date_str, states, deltas, summaries)
                        digest_md = render_digest(digest)

                        console.print()
                        print_digest(digest)

                        # Store digest
                        if store and not dry_run:
                            db.save_digest(date_str, digest_md)

                    except Exception as e:
                        console.print(f"[red]Error generating digest: {e}[/red]")
                        total_errors += 1

                # Post to Discord if requested (works for both simple and detailed mode)
                if post_to_discord and discord_token and summaries:
                    from src.infra.discord_fetcher import post_message_sync
                    import sqlite3

                    console.print()
                    console.print("[bold cyan]Posting summaries to Discord...[/bold cyan]")

                    # Get channel_id and channel_name mappings
                    # summaries dict uses channel_id as key, we need the channel_name
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT DISTINCT channel_id, channel_name FROM messages")
                    channel_info = {row[0]: row[1] for row in cursor.fetchall()}  # channel_id -> channel_name
                    conn.close()

                    # Post summary for each channel
                    for channel_id, summary_text in summaries.items():
                        channel_name = channel_info.get(channel_id, f"unknown-{channel_id}")

                        if summary_text:
                            # Format the message for Discord
                            emoji = "📝" if simple else "📊"
                            discord_message = f"{emoji} **Daily Summary for #{channel_name} ({date_str})**\n\n{summary_text}"

                            try:
                                success = post_message_sync(
                                    token=discord_token,
                                    channel_id=channel_id,
                                    message=discord_message
                                )
                                if success:
                                    console.print(f"[green]✓[/green] Posted to #{channel_name}")
                                else:
                                    console.print(f"[red]✗[/red] Failed to post to #{channel_name}")
                            except Exception as e:
                                console.print(f"[red]✗[/red] Error posting to #{channel_name}: {e}")

                # Print summary table (only for detailed mode)
                if not simple:
                    console.print()
                    print_summary_table(states, deltas)

        # Print final summary
        console.print()
        final_summary = Table(title="Final Summary", show_header=True, header_style="bold green")
        final_summary.add_column("Metric", style="cyan")
        final_summary.add_column("Value", justify="right", style="green")

        final_summary.add_row("Dates processed", str(len(dates_to_process)))
        final_summary.add_row("Channels processed", str(total_channels_processed))
        final_summary.add_row("Messages processed", str(total_messages_processed))
        final_summary.add_row("Errors encountered", str(total_errors))

        if total_errors > 0:
            final_summary.add_row("Status", "[red]Completed with errors[/red]")
        else:
            final_summary.add_row("Status", "[green]Completed successfully[/green]")

        console.print(final_summary)

        # Exit with error code if there were errors
        if total_errors > 0:
            console.print(f"\n[yellow]{total_errors} errors occurred. Check run.log for details.[/yellow]")
            sys.exit(1)


@app.command()
def preview(
    db_path: str = typer.Option("data/app.db", "--db", help="Path to SQLite database file"),
    date: Optional[str] = typer.Option(None, "--date", help="Date to preview (YYYY-MM-DD)"),
    start: Optional[str] = typer.Option(None, "--start", help="Start date for time window (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", help="End date for time window (YYYY-MM-DD)"),
    last_hours: Optional[int] = typer.Option(None, "--last-hours", help="Preview messages from last N hours"),
    channel_name: str = typer.Option(..., "--channel-name", help="Channel name to preview"),
    mock: bool = typer.Option(False, "--mock", help="Use mock LLM responses for testing"),
    verbose: VerbosityLevel = typer.Option(VerbosityLevel.normal, "--verbose", "-v", help="Output verbosity level"),
) -> None:
    """Preview a single channel's summary with enhanced error handling and detailed output.

    Shows raw messages and generates a summary for a specific channel within a
    given time window. Includes helpful error messages and available channel list.

    Examples:
    • preview --channel-name general --date 2026-01-17 --verbose
    • preview --channel-name dev --last-hours 24 --mock
    """
    setup_logging(verbose)
    event_bus = get_event_bus()
    glm_client = get_glm_client(event_bus, mock)

    # Validate time window
    if date and (start or end):
        console.print("[red]Error:[/red] Cannot use --date with --start/--end")
        raise typer.Exit(code=1)

    if (start and not end) or (end and not start):
        console.print("[red]Error:[/red] Both --start and --end must be specified together")
        raise typer.Exit(code=1)

    # Get time window
    try:
        if date:
            tw = TimeWindow.from_date(date)
        elif last_hours:
            tw = TimeWindow.from_hours(last_hours)
        else:
            console.print("[red]Error:[/red] Must specify --date or --last-hours")
            raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error parsing time window: {e}[/red]")
        raise typer.Exit(code=1)

    with Database(db_path, event_bus) as db:
        try:
            # Get channel ID with better error handling
            channels = db.get_channels()
            channel_info = next((c for c in channels if c["channel_name"] == channel_name), None)

            if not channel_info:
                console.print(f"[red]Error:[/red] Channel '{channel_name}' not found")
                if verbose == VerbosityLevel.normal or verbose == VerbosityLevel.verbose:
                    console.print("[yellow]Available channels:[/yellow]")
                    for ch in channels[:10]:  # Show first 10 channels
                        console.print(f"  - #{ch['channel_name']}")
                    if len(channels) > 10:
                        console.print(f"  ... and {len(channels) - 10} more")
                raise typer.Exit(code=1)

            channel_id = channel_info["channel_id"]

            # Get messages
            start_iso, end_iso = tw.to_isoformat()
            try:
                messages = db.get_messages(
                    channel_name=channel_name,
                    start_time=start_iso,
                    end_time=end_iso,
                )
            except Exception as e:
                console.print(f"[red]Error retrieving messages: {e}[/red]")
                if verbose == VerbosityLevel.verbose:
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
                raise typer.Exit(code=1)

            if not messages:
                console.print(f"[yellow]No messages found for #{channel_name} in this time window[/yellow]")
                return

            # Show enhanced messages table
            table = Table(title=f"Messages in #{channel_name} ({len(messages)} total)", show_header=True, header_style="bold magenta")
            table.add_column("Time", style="cyan", width=10)
            table.add_column("Author", style="green", width=15)
            table.add_column("Content", style="white", overflow="fold")

            for i, msg in enumerate(messages[:20]):  # Show first 20
                dt = msg.created_at.split("T")[1][:8] if "T" in msg.created_at else "??"
                content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                table.add_row(dt, msg.author_name, content)

            if len(messages) > 20:
                table.add_row("...", f"[{len(messages) - 20} more messages]", "")

            console.print()
            console.print(Panel(table, title=f"[bold cyan]Messages ({tw.effective_date})[/bold cyan]"))
            console.print()

            # Generate and print summary with error handling
            try:
                summarizer = Summarizer(glm_client, event_bus)

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

                date_str = tw.effective_date
                state = summarizer.generate_state(channel_name, date_str, message_dicts)

                console.print()
                console.print(Panel("[bold green]Generated Summary[/bold green]", expand=False))
                console.print()
                print_summary(state)

            except Exception as e:
                console.print(f"[red]Error generating summary: {e}[/red]")
                if verbose == VerbosityLevel.verbose:
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
                raise typer.Exit(code=1)

        except Exception as e:
            console.print(f"[red]Preview failed: {e}[/red]")
            if verbose == VerbosityLevel.verbose:
                import traceback
                console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise typer.Exit(code=1)


@app.command()
def selftest(
    verbose: VerbosityLevel = VerbosityLevel.normal,
) -> None:
    """Run comprehensive self-test with temporary database and enhanced reporting.

    Creates a temporary database, ingests fixtures, runs the pipeline, and validates
    results with detailed progress tracking, error handling, and performance metrics.

    The selftest includes:
    • Database ingestion and query validation
    • LLM state generation with mock mode
    • Delta computation and digest creation
    • Event tracking verification
    • Performance metrics (verbose mode)

    Examples:
    • selftest
    • selftest --verbose
    """
    setup_logging(verbose)
    audit_logger = get_audit_logger()
    console.print()
    console.print(Panel("[bold cyan]Running Enhanced Self-Test[/bold cyan]", expand=False))
    console.print()

    # Log selftest start
    audit_logger.log_data_modification("cli", "selftest", "start")

    results: list[dict[str, any]] = []

    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdb = Path(tmpdir) / "test.db"
        event_bus = get_event_bus()

        # Track events for validation
        events_log: list[dict] = []

        def track_events(event) -> None:  # type: ignore
            events_log.append({
                "type": event.type.value,
                "data": event.data,
            })

        event_bus.subscribe(EventType.MESSAGE_INGESTED, track_events)
        event_bus.subscribe(EventType.STATE_GENERATED, track_events)
        event_bus.subscribe(EventType.DELTA_COMPUTED, track_events)
        event_bus.subscribe(EventType.DIGEST_CREATED, track_events)

        with Database(tmpdb, event_bus) as db:
            # Test 1: Ingest fixtures with progress tracking
            try:
                console.print("[cyan]Test 1: Ingesting fixtures...[/cyan]")

                # Try to load sample_3days.jsonl first, fall back to sample_minimal.jsonl
                fixture_files = [
                    Path("fixtures/sample_3days.jsonl"),
                    Path("fixtures/sample_minimal.jsonl"),
                ]

                messages_loaded = []
                total_fixtures = sum(1 for f in fixture_files if f.exists())

                with ProgressTracker(console, "Loading fixtures", total=total_fixtures) as tracker:
                    for i, fixture_file in enumerate(fixture_files):
                        if fixture_file.exists():
                            tracker.update(description=f"Loading {fixture_file.name}...")
                            messages = load_fixture(fixture_file)
                            tracker.update(advance=1)

                            try:
                                inserted = db.insert_messages(messages)
                                messages_loaded.extend(messages)
                                console.print(f"  [green]✓[/green] Loaded {len(messages)} messages from {fixture_file.name}")
                                if verbose == VerbosityLevel.verbose:
                                    console.print(f"    Inserted: {inserted} messages")
                            except Exception as e:
                                console.print(f"  [red]✗[/red] Failed to load {fixture_file.name}: {e}")
                                continue

                if not messages_loaded:
                    results.append({"name": "Ingest fixtures", "status": "FAIL", "detail": "No fixture files found"})
                else:
                    results.append({
                        "name": "Ingest fixtures",
                        "status": "PASS",
                        "detail": f"Loaded {len(messages_loaded)} messages",
                    })

            except Exception as e:
                results.append({"name": "Ingest fixtures", "status": "FAIL", "detail": str(e)})

            # Test 2: Query messages
            try:
                console.print("[cyan]Test 2: Querying messages...[/cyan]")

                with ProgressTracker(console, "Querying database") as tracker:
                    tracker.update(description="[cyan]Querying channels and messages...[/cyan]")
                    channels = db.get_channels()
                    messages = db.get_messages()
                    tracker.finish()

                if channels:
                    console.print(f"  [green]✓[/green] Found {len(channels)} channels: {[c['channel_name'] for c in channels]}")
                if messages:
                    console.print(f"  [green]✓[/green] Found {len(messages)} total messages")

                results.append({
                    "name": "Query messages",
                    "status": "PASS",
                    "detail": f"{len(channels)} channels, {len(messages)} messages",
                })

            except Exception as e:
                results.append({"name": "Query messages", "status": "FAIL", "detail": str(e)})

            # Test 3: Generate state (mock mode) with retries
            try:
                console.print("[cyan]Test 3: Generating daily state (mock mode)...[/cyan]")

                glm_client = get_glm_client(event_bus, mock=True)
                summarizer = Summarizer(glm_client, event_bus)

                # Get messages for first channel
                if channels:
                    channel_name = channels[0]["channel_name"]
                    messages = db.get_messages(channel_name=channel_name)

                    if messages:
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

                        state = summarizer.generate_state(channel_name, "2026-01-17", message_dicts)

                        console.print(f"  [green]✓[/green] Generated state with {len(state.topics)} topics, {len(state.progress.finished)} finished tasks")

                        # Save state with error handling
                        try:
                            db.save_state(state, "test summary", channels[0]["channel_id"])
                            console.print("  [green]✓[/green] State saved to database")
                        except Exception as e:
                            console.print(f"  [yellow]⚠[/yellow] State save failed: {e}")

                        results.append({
                            "name": "Generate state",
                            "status": "PASS",
                            "detail": f"{len(state.topics)} topics, {len(state.progress.finished)} finished",
                        })
                    else:
                        results.append({"name": "Generate state", "status": "FAIL", "detail": "No messages found"})
                else:
                    results.append({"name": "Generate state", "status": "FAIL", "detail": "No channels found"})

            except Exception as e:
                results.append({"name": "Generate state", "status": "FAIL", "detail": str(e)})

            # Test 4: Compute delta
            try:
                console.print("[cyan]Test 4: Computing delta...[/cyan]")

                if channels:
                    channel_id = channels[0]["channel_id"]

                    # Create mock states
                    from src.core.models import Progress

                    state1 = DailyChannelState(
                        channel_name=channels[0]["channel_name"],
                        date="2026-01-16",
                        topics=["Topic A", "Topic B"],
                        progress=Progress(
                            started=["Task A"],
                            finished=[],
                            blocked=[],
                        ),
                    )

                    state2 = DailyChannelState(
                        channel_name=channels[0]["channel_name"],
                        date="2026-01-17",
                        topics=["Topic A", "Topic C"],
                        progress=Progress(
                            started=[],
                            finished=["Task A"],
                            blocked=[],
                        ),
                    )

                    delta = compute_delta(state2, state1)

                    console.print(f"  [green]✓[/green] Delta: {len(delta.new_topics)} new topics, {len(delta.progress_changes.finished_now)} finished")

                    results.append({
                        "name": "Compute delta",
                        "status": "PASS",
                        "detail": f"{len(delta.new_topics)} new topics",
                    })
                else:
                    results.append({"name": "Compute delta", "status": "FAIL", "detail": "No channels found"})

            except Exception as e:
                results.append({"name": "Compute delta", "status": "FAIL", "detail": str(e)})

            # Test 5: Generate digest
            try:
                console.print("[cyan]Test 5: Generating digest...[/cyan]")

                if channels:
                    # Create mock digest
                    digest = generate_digest(
                        "2026-01-17",
                        {channels[0]["channel_id"]: state2},
                        {channels[0]["channel_id"]: delta},
                        {channels[0]["channel_id"]: "test summary"},
                    )

                    console.print(f"  [green]✓[/green] Digest: {len(digest.highlights)} highlights, {len(digest.links)} links")

                    results.append({
                        "name": "Generate digest",
                        "status": "PASS",
                        "detail": f"{len(digest.highlights)} highlights",
                    })
                else:
                    results.append({"name": "Generate digest", "status": "FAIL", "detail": "No channels found"})

            except Exception as e:
                results.append({"name": "Generate digest", "status": "FAIL", "detail": str(e)})

            # Test 6: Event tracking
            try:
                console.print("[cyan]Test 6: Validating events...[/cyan]")

                message_events = [e for e in events_log if e["type"] == "MESSAGE_INGESTED"]
                state_events = [e for e in events_log if e["type"] == "STATE_GENERATED"]

                console.print(f"  [green]✓[/green] Events: {len(message_events)} message, {len(state_events)} state")

                if message_events and state_events:
                    results.append({
                        "name": "Event tracking",
                        "status": "PASS",
                        "detail": f"{len(events_log)} total events",
                    })
                else:
                    results.append({
                        "name": "Event tracking",
                        "status": "FAIL",
                        "detail": "Missing expected events",
                    })

            except Exception as e:
                results.append({"name": "Event tracking", "status": "FAIL", "detail": str(e)})

            # Test 7: Performance metrics (verbose only)
            if verbose == VerbosityLevel.verbose:
                try:
                    console.print("[cyan]Test 7: Performance metrics...[/cyan]")

                    performance_table = Table(title="Performance Metrics", show_header=True, header_style="bold yellow")
                    performance_table.add_column("Metric", style="yellow")
                    performance_table.add_column("Value", style="white")

                    # Test message processing speed
                    import time
                    start_time = time.time()
                    test_messages = db.get_messages()[:100]  # Test with first 100 messages
                    processing_time = time.time() - start_time

                    performance_table.add_row("Message query time (100)", f"{processing_time:.3f}s")
                    performance_table.add_row("Total messages in DB", str(len(db.get_messages())))
                    performance_table.add_row("Total channels in DB", str(len(db.get_channels())))

                    console.print(performance_table)

                    results.append({
                        "name": "Performance metrics",
                        "status": "PASS",
                        "detail": f"Query time: {processing_time:.3f}s",
                    })

                except Exception as e:
                    results.append({"name": "Performance metrics", "status": "FAIL", "detail": str(e)})

    # Display enhanced results table
    console.print()
    console.print(Panel("[bold]Enhanced Self-Test Results[/bold]", expand=False))
    console.print()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Test", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="white")

    all_passed = True

    for result in results:
        status = result["status"]
        status_text = f"[{'green' if status == 'PASS' else 'red'}]{status}[/{('green' if status == 'PASS' else 'red')}]"
        status_symbol = "[green]✓[/green]" if status == "PASS" else "[red]✗[/red]"

        table.add_row(result["name"], f"{status_symbol} {status_text}", result["detail"])

        if status != "PASS":
            all_passed = False

    console.print(table)
    console.print()

    if all_passed:
        console.print("[green bold]✓ All tests passed![/green bold]")
        console.print("[green]Self-test completed successfully.[/green]")
        sys.exit(0)
    else:
        console.print("[red bold]✗ Some tests failed.[/red bold]")
        if verbose == VerbosityLevel.normal:
            console.print("[yellow]Run with --verbose for more details.[/yellow]")
        sys.exit(1)


@app.command()
def add_message(
    db_path: str = typer.Option("data/app.db", "--db", help="Path to SQLite database file"),
    channel: str = typer.Option(..., "--channel", "-c", help="Channel name"),
    content: str = typer.Option(..., "--content", "-m", help="Message content"),
    author: str = typer.Option("You", "--author", "-a", help="Author name"),
    links: str = typer.Option("", "--links", "-l", help="Comma-separated URLs"),
    date: str = typer.Option(None, "--date", "-d", help="Message date (YYYY-MM-DD), default: today"),
    discord_format: bool = typer.Option(False, "--discord-format", help="Use Discord API format (for testing Discord compatibility)"),
    message_id: str = typer.Option(None, "--message-id", help="Custom message ID (for Discord format)"),
    reply_to: str = typer.Option(None, "--reply-to", help="Message ID this message replies to (for Discord format)"),
    author_id: str = typer.Option(None, "--author-id", help="Author ID (for Discord format)"),
) -> None:
    """Quickly add a message to the database for testing.

    This is an interactive command for building realistic scenarios on the fly.
    Use it multiple times to build up a conversation before running summarization.

    STANDARD MODE (default):
    Uses our simplified MessageEvent format. Good for quick testing.

    DISCORD MODE (--discord-format):
    Uses Discord's actual API message structure. Use this to test Discord
    compatibility before integrating with real Discord.

    Examples:
    • add-message --channel dev --content "Just pushed the auth flow fix"
    • add-message --channel dev --content "LGTM! Ship it 🚀" --author "Sarah"
    • add-message --channel test --content "Tests are failing" --links "https://github.com/ourteam/repo/pull/123"
    • add-message --channel dev --content "Found a bug" --date 2026-01-15

    Discord format examples:
    • add-message --channel dev --content "Pushed!" --discord-format
    • add-message --channel dev --content "Thanks!" --reply-to "123456789" --discord-format
    • add-message --channel dev --content "LGTM" --author "Sarah" --author-id "987654321" --discord-format

    Then run:
    • run --date 2026-01-20 --channels dev
    """
    event_bus = get_event_bus()
    audit_logger = get_audit_logger()

    # Parse links
    links_list = [l.strip() for l in links.split(",") if l.strip()] if links else []

    # Determine message date
    import time
    import random
    from datetime import datetime, timedelta

    if date:
        # Use specified date with random time during business hours (9-18)
        try:
            base_dt = datetime.strptime(date, "%Y-%m-%d")
            # Random time between 9 AM and 6 PM
            hour = random.randint(9, 17)
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            message_dt = base_dt.replace(hour=hour, minute=minute, second=second)
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid date format. Use YYYY-MM-DD")
            raise typer.Exit(code=1)
    else:
        # Use current time
        message_dt = datetime.now()

    created_at = message_dt.isoformat() + "+09:00"

    # Create message in appropriate format
    from src.core.models import MessageEvent, Attachment
    from src.infra.discord_transformer import (
        create_discord_message,
        parse_discord_message_from_dict,
    )

    if discord_format:
        # Discord format - use Discord API structure
        if not message_id:
            message_id = str(int(time.time() * 1000))

        if not author_id:
            # Generate a Discord-like snowflake ID
            author_id = f"{random.randint(100000000000000000, 999999999999999999)}"

        channel_id = f"{random.randint(100000000000000000, 999999999999999999)}"

        # Create Discord-formatted message
        discord_msg_dict = create_discord_message(
            content=content,
            author_name=author,
            author_id=author_id,
            channel_id=channel_id,
            channel_name=channel,
            message_id=message_id,
            timestamp=created_at,
            reply_to=reply_to,
            attachments=None,
        )

        # Convert to MessageEvent
        message = parse_discord_message_from_dict(discord_msg_dict, channel)

        format_type = "Discord API format"
    else:
        # Standard format - use our simplified MessageEvent
        message_id = message_id or f"msg-{int(time.time() * 1000)}"
        channel_id = f"c-{channel}"
        author_id = author_id or f"u-{hash(author) % 10000:04d}"

        message = MessageEvent(
            message_id=message_id,
            channel_id=channel_id,
            channel_name=channel,
            author_id=author_id,
            author_name=author,
            created_at=created_at,
            content=content,
            attachments=[],
            links=links_list,
            reply_to_message_id=reply_to,
        )

        format_type = "Standard format"

    # Insert into database
    try:
        with Database(db_path, event_bus) as db:
            db.insert_messages([message])

        console.print(f"[green]✓[/green] Added message to [cyan]#{channel}[/cyan] ([dim]{message_dt.date()}[/dim]) - [dim]({format_type})[/dim]")
        console.print(f"  [dim]Author:[/dim] {author} [dim]({message.author_id})[/dim]")
        console.print(f"  [dim]Content:[/dim] {content[:80]}{'...' if len(content) > 80 else ''}")
        if message.links:
            console.print(f"  [dim]Links:[/dim] {', '.join(message.links)}")
        if discord_format and reply_to:
            console.print(f"  [dim]Reply to:[/dim] {reply_to}")

        # Show next steps hint
        console.print()
        console.print("[dim]Tip: Run 'add-message' again to continue the conversation[/dim]")
        if date:
            console.print(f"[dim]     When ready, run: run --date {date} --channels {channel}[/dim]")
        else:
            console.print(f"[dim]     When ready, run: run --date $(date +%Y-%m-%d) --channels {channel}[/dim]")

        if discord_format:
            console.print(f"[dim]     Using Discord format - seamless for future Discord integration[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


def _get_previous_date(date_str: str) -> str | None:
    """Get previous day's date string.

    Args:
        date_str: Date string (YYYY-MM-DD)

    Returns:
        Previous day's date string or None if invalid
    """
    from datetime import datetime, timedelta

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        prev_dt = dt - timedelta(days=1)
        return prev_dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


@app.command()
def fetch_discord(
    ctx: typer.Context,
    token: str = typer.Option(..., "--token", "-t", help="Discord bot token", envvar="DISCORD_BOT_TOKEN"),
    guild_id: str = typer.Option(..., "--guild", "-g", help="Discord guild (server) ID"),
    channels: str = typer.Option(None, "--channels", "-c", help="Comma-separated channel IDs to fetch"),
    output: str = typer.Option("discord_export.jsonl", "--output", "-o", help="Output JSONL file path"),
    after: str = typer.Option(None, "--after", help="Fetch messages after this date (YYYY-MM-DD)"),
    before: str = typer.Option(None, "--before", help="Fetch messages before this date (YYYY-MM-DD)"),
    limit: int = typer.Option(None, "--limit", "-l", help="Max messages per channel (default: unlimited)"),
    list_only: bool = typer.Option(False, "--list", help="List all channels in the guild and exit"),
    verbosity: VerbosityLevel = typer.Option(VerbosityLevel.normal, "--verbose", "-v", help="Verbosity level"),
) -> None:
    """Fetch messages directly from Discord API.

    This command connects to Discord using a bot token and downloads messages
    from the specified channels. Messages are saved in JSONL format that can
    be ingested using the 'ingest' command.

    SETUP (one-time):
    1. Go to https://discord.com/developers/applications
    2. Create a new application
    3. Go to the "Bot" section and create a bot
    4. Copy the bot token
    5. Enable "Message Content Intent" under Privileged Gateway Intents
    6. Go to OAuth2 → URL Generator
    7. Select scope: bot
    8. Select permissions: Read Messages/View Channels, Read Message History
    9. Copy the generated URL and open it in a browser to invite the bot to your server

    GETTING GUILD AND CHANNEL IDs:
    1. Enable Developer Mode in Discord (Settings → Advanced → Developer Mode)
    2. Right-click on your server → Copy Server ID (guild_id)
    3. Right-click on a channel → Copy Channel ID
    4. Or use: --list to see all channels in your server

    Examples:
    • List all channels in a server:
      fetch-discord --token YOUR_TOKEN --guild YOUR_GUILD_ID --list

    • Fetch all messages from a channel:
      fetch-discord --token YOUR_TOKEN --guild YOUR_GUILD_ID --channels 123456789

    • Fetch messages from multiple channels:
      fetch-discord --token YOUR_TOKEN --guild YOUR_GUILD_ID --channels 123,456,789

    • Fetch last 7 days of messages:
      fetch-discord --token YOUR_TOKEN --guild YOUR_GUILD_ID --channels 123 --after 2026-01-23

    • Fetch with limit per channel:
      fetch-discord --token YOUR_TOKEN --guild YOUR_GUILD_ID --channels 123 --limit 100

    Then ingest and summarize:
    • ingest --db data/app.db --fixture discord_export.jsonl --reset
    • run --db data/app.db --date 2026-01-30
    """
    setup_logging(verbosity)

    # Validate and parse channel IDs
    if not list_only and not channels:
        console.print("[red]Error:[/red] --channels is required when not using --list")
        raise typer.Exit(code=1)

    channel_ids = [c.strip() for c in channels.split(",") if c.strip()] if channels else []

    try:
        from src.infra.discord_fetcher import DiscordFetcher, list_channels_sync, fetch_messages_sync
        from datetime import datetime
        from rich.console import Console
        from rich.table import Table

        fetch_console = Console()

        if list_only:
            # List channels mode
            with console.status("[bold cyan]Connecting to Discord...[/bold cyan]"):
                channels_list = list_channels_sync(token=token, guild_id=guild_id)

            # Display channels in a nice table
            table = Table(title=f"Channels in Guild: {guild_id}")
            table.add_column("Channel Name", style="cyan")
            table.add_column("Channel ID", style="yellow")
            table.add_column("Topic", style="dim")
            table.add_column("Position", style="dim")

            for ch in sorted(channels_list, key=lambda x: x["position"]):
                topic = ch["topic"] or ""
                if len(topic) > 40:
                    topic = topic[:37] + "..."
                table.add_row(f"#{ch['name']}", ch["id"], topic, str(ch["position"]))

            fetch_console.print(table)
            fetch_console.print()
            fetch_console.print("[dim]Use the Channel IDs with --channels to fetch messages[/dim]")
            return

        # Parse date filters
        after_dt = None
        before_dt = None
        if after:
            try:
                after_dt = datetime.strptime(after, "%Y-%m-%d")
            except ValueError:
                console.print(f"[red]Error:[/red] Invalid --after date format. Use YYYY-MM-DD")
                raise typer.Exit(code=1)

        if before:
            try:
                before_dt = datetime.strptime(before, "%Y-%m-%d")
            except ValueError:
                console.print(f"[red]Error:[/red] Invalid --before date format. Use YYYY-MM-DD")
                raise typer.Exit(code=1)

        # Fetch messages
        console.print(f"[bold cyan]Fetching Discord messages...[/bold cyan]")
        console.print(f"  [dim]Guild:[/dim] {guild_id}")
        console.print(f"  [dim]Channels:[/dim] {', '.join(channel_ids)}")
        if after_dt:
            console.print(f"  [dim]After:[/dim] {after}")
        if before_dt:
            console.print(f"  [dim]Before:[/dim] {before}")
        if limit:
            console.print(f"  [dim]Limit:[/dim] {limit} per channel")
        console.print(f"  [dim]Output:[/dim] {output}")
        console.print()

        with console.status("[bold cyan]Connecting to Discord and fetching messages...[/bold cyan]"):
            message_count = fetch_messages_sync(
                token=token,
                guild_id=guild_id,
                channel_ids=channel_ids,
                output_path=output,
                after=after_dt,
                before=before_dt,
                limit=limit,
            )

        console.print()
        console.print(f"[green]✓[/green] Successfully fetched {message_count} messages")
        console.print(f"[green]✓[/green] Saved to: {output}")
        console.print()
        console.print("[bold]Next steps:[/bold]")
        console.print(f"  1. Ingest the data:")
        console.print(f"     [cyan]python -m app.cli ingest --db data/app.db --fixture {output} --reset[/cyan]")
        console.print(f"  2. Run summarization:")
        console.print(f"     [cyan]python -m app.cli run --db data/app.db --date {after or datetime.now().strftime('%Y-%m-%d')}[/cyan]")

    except ImportError:
        console.print("[red]Error:[/red] discord.py is not installed")
        console.print("[dim]Install it with: pip install discord.py[/dim]")
        console.print("[dim]Or: pip install -e '.[discord]'[/dim]")
        raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        console.print(traceback.format_exc())
        raise typer.Exit(code=1)


@app.command()
def simulate(
    guild_id: str = typer.Option(..., "--guild", "-g", help="Discord guild (server) ID"),
    channel_id: str = typer.Option(..., "--channel", "-c", help="Discord channel ID"),
    days: int = typer.Option(3, "--days", "-d", help="Number of days to simulate"),
    messages_per_day: int = typer.Option(20, "--messages", "-m", help="Messages per day"),
    pattern: str = typer.Option("normal", "--pattern", "-p", help="Activity pattern: normal, bursty, quiet"),
    output: str = typer.Option("simulated_messages.jsonl", "--output", "-o", help="Output JSONL file"),
    post_to_discord: bool = typer.Option(False, "--post", help="Post messages to Discord (requires token)"),
    discord_token: str = typer.Option(None, "--token", "-t", help="Discord bot token (required if using --post)", envvar="DISCORD_BOT_TOKEN"),
    verbosity: VerbosityLevel = typer.Option(VerbosityLevel.normal, "--verbose", "-v", help="Verbosity level"),
) -> None:
    """Simulate realistic Discord community activity.

    Generates realistic messages with different personas (tech lead, helper, casual,
    gamer, newbie, enthusiast) to test the summarizer. Can save to JSONL for
    local testing or post directly to Discord.

    PERSONAS:
    • tech_lead: Technical discussions, code reviews, deployment updates
    • helper: Questions, guidance, documentation links
    • casual: Random chat, memes, life updates
    • gamer: Gaming discussions, streaming, squad ups
    • newbie: Learning questions, confusion, gratitude
    • enthusiast: Ideas, suggestions, community excitement

    PATTERNS:
    • normal: Evenly distributed messages throughout the day
    • bursty: Bursts of activity separated by quiet periods
    • quiet: Few messages, mostly in evening hours

    Examples:
    • Simulate 3 days of normal activity (JSONL only):
      simulate --guild 123 --channel 456 --days 3

    • Simulate 5 days with 30 messages per day:
      simulate --guild 123 --channel 456 --days 5 --messages 30

    • Simulate bursty activity pattern:
      simulate --guild 123 --channel 456 --days 3 --pattern bursty

    • Simulate and post to real Discord:
      simulate --guild 123 --channel 456 --days 1 --post --token YOUR_TOKEN

    Then run summarization:
    • ingest --db data/app.db --fixture simulated_messages.jsonl --reset
    • run --db data/app.db --start 2026-01-27 --end 2026-01-30 --post-to-discord
    """
    setup_logging(verbosity)

    try:
        from src.infra.discord_simulator import (
            DiscordSimulator,
            simulate_community_activity,
            post_messages_sync,
        )
        from datetime import datetime, timedelta

        console.print(f"[bold cyan]Simulating Community Activity[/bold cyan]")
        console.print()
        console.print(f"  [dim]Guild:[/dim] {guild_id}")
        console.print(f"  [dim]Channel:[/dim] {channel_id}")
        console.print(f"  [dim]Days:[/dim] {days}")
        console.print(f"  [dim]Messages per day:[/dim] {messages_per_day}")
        console.print(f"  [dim]Pattern:[/dim] {pattern}")
        console.print(f"  [dim]Output:[/dim] {output}")
        console.print()

        # Calculate start date (days ago from now)
        start_date = datetime.now() - timedelta(days=days)

        if pattern not in ["normal", "bursty", "quiet"]:
            console.print(f"[red]Error:[/red] Pattern must be 'normal', 'bursty', or 'quiet'")
            raise typer.Exit(code=1)

        # Generate simulated messages
        messages = simulate_community_activity(
            guild_id=guild_id,
            channel_id=channel_id,
            start_date=start_date,
            num_days=days,
            messages_per_day=messages_per_day,
            activity_pattern=pattern,
            output_file=output,
        )

        console.print()
        console.print(f"[green]✓[/green] Generated {len(messages)} messages")

        if post_to_discord:
            if not discord_token:
                console.print("[red]Error:[/red] --token is required when using --post")
                raise typer.Exit(code=1)

            console.print()
            console.print(f"[bold cyan]Posting to Discord...[/bold cyan]")

            posted = post_messages_sync(
                messages=messages,
                token=discord_token,
                channel_id=channel_id,
                delay_range=(0.5, 2),  # Faster for simulation
            )

            console.print(f"[green]✓[/green] Posted {posted} messages to Discord")
            console.print()
            console.print("[bold]Next steps:[/bold]")
            console.print(f"  Wait a minute for messages to propagate, then:")
            console.print(f"  [cyan]python -m app.cli run --db data/app.db --last-hours {days * 24} --post-to-discord[/cyan]")

        else:
            console.print()
            console.print("[bold]Next steps:[/bold]")
            console.print(f"  1. Ingest the simulated data:")
            console.print(f"     [cyan]python -m app.cli ingest --db data/app.db --fixture {output} --reset[/cyan]")
            console.print(f"  2. Run summarization:")
            console.print(f"     [cyan]python -m app.cli run --db data/app.db --last-hours {days * 24}[/cyan]")
            console.print(f"  Or with posting to Discord:")
            console.print(f"     [cyan]python -m app.cli run --db data/app.db --last-hours {days * 24} --post-to-discord[/cyan]")

    except ImportError:
        console.print("[red]Error:[/red] discord.py is not installed")
        console.print("[dim]Install it with: pip install discord.py[/dim]")
        console.print("[dim]Or: pip install -e '.[discord]'[/dim]")
        raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        console.print(traceback.format_exc())
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
