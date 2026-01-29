"""Global digest aggregation across channels."""

from collections import Counter
from typing import Any

from src.core.models import DailyChannelState, DailyChannelDelta, GlobalDigest


def generate_digest(
    date: str,
    states: dict[str, DailyChannelState],
    deltas: dict[str, DailyChannelDelta],
    summaries: dict[str, str],
) -> GlobalDigest:
    """Generate global digest from all channel states and deltas.

    Args:
        date: Date string (YYYY-MM-DD)
        states: Dict mapping channel_id to DailyChannelState
        deltas: Dict mapping channel_id to DailyChannelDelta
        summaries: Dict mapping channel_id to summary markdown

    Returns:
        Global digest
    """
    # Collect highlights across channels
    highlights = _collect_highlights(states, deltas)

    # Collect help requests across channels
    help_requests = _collect_help_requests(states)

    # Collect and dedupe links
    links = _collect_links(states)

    return GlobalDigest(
        date=date,
        highlights=highlights[:5],  # Top 5
        help_requests=help_requests[:5],  # Top 5
        links=links[:10],  # Top 10
        channel_summaries=summaries,
    )


def _collect_highlights(
    states: dict[str, DailyChannelState],
    deltas: dict[str, DailyChannelDelta],
) -> list[str]:
    """Collect top highlights across channels.

    Prioritizes:
    1. Finished tasks (especially from deltas)
    2. New blockers (from deltas)
    3. Help requests (from states)
    4. Important topics (from states)

    Args:
        states: Channel states
        deltas: Channel deltas

    Returns:
        List of highlight strings
    """
    highlights: list[tuple[int, str]] = []  # (priority, highlight)

    for channel_id, delta in deltas.items():
        if delta.compared_to is None:
            continue

        channel_name = delta.channel_name

        # Finished items (high priority)
        for item in delta.progress_changes.finished_now:
            highlights.append((1, f"[#{channel_name}] Finished: {item}"))

        # New blockers (high priority)
        for item in delta.progress_changes.new_blockers:
            highlights.append((1, f"[#{channel_name}] BLOCKER: {item}"))

        # Resolved blockers (medium priority)
        for item in delta.progress_changes.resolved_blockers:
            highlights.append((2, f"[#{channel_name}] Resolved blocker: {item}"))

        # New topics (low priority)
        for topic in delta.new_topics:
            highlights.append((3, f"[#{channel_name}] New topic: {topic}"))

    # Also check states for help requests
    for channel_id, state in states.items():
        channel_name = state.channel_name

        # Help requests (medium priority)
        for request in state.help_requests:
            highlights.append((2, f"[#{channel_name}] HELP: {request}"))

        # Sort by priority (lower is better)
        highlights.sort(key=lambda x: x[0])

    return [h[1] for h in highlights]


def _collect_help_requests(states: dict[str, DailyChannelState]) -> list[str]:
    """Collect help requests across channels.

    Args:
        states: Channel states

    Returns:
        List of help request strings, sorted by frequency
    """
    requests: list[tuple[int, str]] = []

    for state in states.values():
        channel_name = state.channel_name
        for request in state.help_requests:
            requests.append((1, f"[#{channel_name}] {request}"))

    # Sort by frequency (most common first)
    if requests:
        counter = Counter([r[1] for r in requests])
        return [req for req, _ in counter.most_common()]

    return []


def _collect_links(states: dict[str, DailyChannelState]) -> list[str]:
    """Collect and dedupe links across channels.

    Args:
        states: Channel states

    Returns:
        List of unique links
    """
    all_links: set[str] = set()

    for state in states.values():
        all_links.update(state.artifacts.links)
        all_links.update(state.artifacts.repos)
        all_links.update(state.artifacts.docs)

    return sorted(list(all_links))
