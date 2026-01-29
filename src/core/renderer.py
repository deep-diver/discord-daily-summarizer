"""Renderer for converting states and deltas to Markdown."""

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.core.models import DailyChannelState, DailyChannelDelta, GlobalDigest


console = Console()


def render_summary(state: DailyChannelState) -> str:
    """Render daily channel state as Markdown.

    Args:
        state: Daily channel state

    Returns:
        Markdown summary
    """
    lines = [
        f"## #{state.channel_name} - Daily Summary ({state.date})",
        "",
    ]

    # Highlights section
    highlights = []

    # Progress items
    if state.progress.finished:
        highlights.extend([f"- Finished: {item}" for item in state.progress.finished])

    if state.progress.started:
        highlights.extend([f"- Started: {item}" for item in state.progress.started])

    if state.progress.blocked:
        highlights.extend([f"- BLOCKED: {item}" for item in state.progress.blocked])

    if state.progress.continued:
        highlights.extend([f"- Continued: {item}" for item in state.progress.continued])

    # Topics
    if state.topics:
        highlights.extend([f"- Topic: {topic}" for topic in state.topics])

    if highlights:
        lines.append("### Highlights")
        lines.extend(highlights)
        lines.append("")

    # Blockers
    if state.progress.blocked:
        lines.append("### Blockers")
        for blocker in state.progress.blocked:
            lines.append(f"- {blocker}")
        lines.append("")

    # Help Requests
    if state.help_requests:
        lines.append("### Help Requests")
        for request in state.help_requests:
            lines.append(f"- {request}")
        lines.append("")

    # Links
    all_links = []
    if state.artifacts.links:
        all_links.extend(state.artifacts.links)
    if state.artifacts.repos:
        all_links.extend(state.artifacts.repos)
    if state.artifacts.docs:
        all_links.extend(state.artifacts.docs)

    if all_links:
        lines.append("### Links")
        for link in all_links:
            lines.append(f"- {link}")
        lines.append("")

    # Next Steps
    if state.next_steps:
        lines.append("### Next Steps")
        for step in state.next_steps:
            lines.append(f"- {step}")
        lines.append("")

    return "\n".join(lines)


def render_delta(delta: DailyChannelDelta) -> str:
    """Render daily channel delta as Markdown.

    Args:
        delta: Daily channel delta

    Returns:
        Markdown delta
    """
    lines = [
        f"### Delta vs. {delta.compared_to if delta.compared_to else 'N/A'}",
        "",
    ]

    if delta.compared_to is None:
        lines.append("No previous day data available.")
        lines.append("")
        return "\n".join(lines)

    # New Topics
    if delta.new_topics:
        lines.append("#### New Topics")
        for topic in delta.new_topics:
            lines.append(f"- {topic}")
        lines.append("")

    # Resolved Topics
    if delta.resolved_topics:
        lines.append("#### Resolved Topics")
        for topic in delta.resolved_topics:
            lines.append(f"- {topic}")
        lines.append("")

    # Progress Changes
    has_progress = any([
        delta.progress_changes.started_now,
        delta.progress_changes.finished_now,
        delta.progress_changes.new_blockers,
        delta.progress_changes.resolved_blockers,
    ])

    if has_progress:
        lines.append("#### Progress Changes")

        if delta.progress_changes.finished_now:
            lines.append("- Finished now:")
            for item in delta.progress_changes.finished_now:
                lines.append(f"  - {item}")

        if delta.progress_changes.new_blockers:
            lines.append("- New blockers:")
            for item in delta.progress_changes.new_blockers:
                lines.append(f"  - {item}")

        if delta.progress_changes.resolved_blockers:
            lines.append("- Resolved blockers:")
            for item in delta.progress_changes.resolved_blockers:
                lines.append(f"  - {item}")

        if delta.progress_changes.started_now:
            lines.append("- Started now:")
            for item in delta.progress_changes.started_now:
                lines.append(f"  - {item}")

        lines.append("")

    # New Links
    if delta.new_links:
        lines.append("#### New Links")
        for link in delta.new_links:
            lines.append(f"- {link}")
        lines.append("")

    # New Help Requests
    if delta.new_help_requests:
        lines.append("#### New Help Requests")
        for request in delta.new_help_requests:
            lines.append(f"- {request}")
        lines.append("")

    return "\n".join(lines)


def render_digest(digest: GlobalDigest) -> str:
    """Render global digest as Markdown.

    Args:
        digest: Global digest

    Returns:
        Markdown digest
    """
    lines = [
        f"# Daily Digest ({digest.date})",
        "",
    ]

    # Top Highlights
    if digest.highlights:
        lines.append("## Top Highlights")
        for highlight in digest.highlights:
            lines.append(f"- {highlight}")
        lines.append("")

    # Help Requests
    if digest.help_requests:
        lines.append("## Help Requests")
        for request in digest.help_requests:
            lines.append(f"- {request}")
        lines.append("")

    # New Links
    if digest.links:
        lines.append("## New Links")
        for link in digest.links:
            lines.append(f"- {link}")
        lines.append("")

    # Per-Channel Summaries (optional in Phase 1)
    if digest.channel_summaries:
        lines.append("## Per-Channel Summaries")
        lines.append("")
        for channel_name, summary_md in digest.channel_summaries.items():
            lines.append(f"### #{channel_name}")
            lines.append(summary_md)
            lines.append("")

    return "\n".join(lines)


def render_summary_panel(state: DailyChannelState) -> Panel:
    """Render daily channel state as a rich Panel.

    Args:
        state: Daily channel state

    Returns:
        Rich Panel with formatted content
    """
    summary_md = render_summary(state)

    # Convert Markdown to rich text (basic formatting)
    text = Text()
    text.append(summary_md, style="cyan")

    return Panel(
        text,
        title=f"[bold blue]#{state.channel_name}[/bold blue] - Daily Summary ({state.date})",
        border_style="blue",
    )


def render_delta_panel(delta: DailyChannelDelta) -> Panel:
    """Render daily channel delta as a rich Panel.

    Args:
        delta: Daily channel delta

    Returns:
        Rich Panel with formatted content
    """
    delta_md = render_delta(delta)

    text = Text()
    text.append(delta_md, style="yellow")

    compared_to = delta.compared_to if delta.compared_to else "N/A"
    return Panel(
        text,
        title=f"[bold yellow]Delta vs. {compared_to}[/bold yellow]",
        border_style="yellow",
    )


def render_digest_panel(digest: GlobalDigest) -> Panel:
    """Render global digest as a rich Panel.

    Args:
        digest: Global digest

    Returns:
        Rich Panel with formatted content
    """
    digest_md = render_digest(digest)

    text = Text()
    text.append(digest_md, style="green")

    return Panel(
        text,
        title=f"[bold green]Daily Digest ({digest.date})[/bold green]",
        border_style="green",
    )


def create_summary_table(
    states: dict[str, DailyChannelState],
    deltas: dict[str, DailyChannelDelta] | None = None,
) -> Table:
    """Create a rich table summarizing channel states.

    Args:
        states: Dict mapping channel_id to DailyChannelState
        deltas: Optional dict mapping channel_id to DailyChannelDelta

    Returns:
        Rich Table with summary data
    """
    table = Table(title="Channel Summary", show_header=True, header_style="bold magenta")

    table.add_column("Channel", style="cyan")
    table.add_column("Date", style="white")
    table.add_column("Topics", justify="right", style="green")
    table.add_column("Blockers", justify="right", style="red")
    table.add_column("Help Requests", justify="right", style="yellow")

    if deltas:
        table.add_column("New Topics", justify="right", style="blue")
        table.add_column("Finished", justify="right", style="green")

    for channel_id, state in states.items():
        row = [
            f"#{state.channel_name}",
            state.date,
            str(len(state.topics)),
            str(len(state.progress.blocked)),
            str(len(state.help_requests)),
        ]

        if deltas and channel_id in deltas:
            delta = deltas[channel_id]
            row.extend([
                str(len(delta.new_topics)),
                str(len(delta.progress_changes.finished_now)),
            ])
        elif deltas:
            row.extend(["-", "-"])

        table.add_row(*row)

    return table


def print_summary(state: DailyChannelState) -> None:
    """Print daily channel state summary to console.

    Args:
        state: Daily channel state
    """
    panel = render_summary_panel(state)
    console.print(panel)


def print_delta(delta: DailyChannelDelta) -> None:
    """Print daily channel delta to console.

    Args:
        delta: Daily channel delta
    """
    panel = render_delta_panel(delta)
    console.print(panel)


def print_digest(digest: GlobalDigest) -> None:
    """Print global digest to console.

    Args:
        digest: Global digest
    """
    panel = render_digest_panel(digest)
    console.print(panel)


def print_summary_table(
    states: dict[str, DailyChannelState],
    deltas: dict[str, DailyChannelDelta] | None = None,
) -> None:
    """Print summary table to console.

    Args:
        states: Dict mapping channel_id to DailyChannelState
        deltas: Optional dict mapping channel_id to DailyChannelDelta
    """
    table = create_summary_table(states, deltas)
    console.print(table)
