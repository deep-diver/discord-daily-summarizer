"""Delta computation for comparing daily channel states."""

from typing import Any

from src.core.models import DailyChannelState, DailyChannelDelta, ProgressChanges


def compute_delta(
    today_state: DailyChannelState,
    yesterday_state: DailyChannelState | None,
) -> DailyChannelDelta:
    """Compute delta between today's state and previous day's state.

    Primarily code-based (set differences), not LLM-based.

    Args:
        today_state: Today's daily channel state
        yesterday_state: Previous day's state (or None if first day)

    Returns:
        Daily channel delta
    """
    if yesterday_state is None:
        # No previous day - return empty delta with null comparison
        return DailyChannelDelta(
            channel_name=today_state.channel_name,
            date=today_state.date,
            compared_to=None,
            new_topics=[],
            resolved_topics=[],
            progress_changes=ProgressChanges(),
            new_links=[],
            new_help_requests=[],
        )

    # Compute set differences
    new_topics = _set_diff(today_state.topics, yesterday_state.topics)
    resolved_topics = _set_diff(yesterday_state.topics, today_state.topics)

    # Progress changes
    progress_changes = ProgressChanges(
        started_now=_set_diff(today_state.progress.started, yesterday_state.progress.started),
        finished_now=_set_diff(today_state.progress.finished, yesterday_state.progress.finished),
        new_blockers=_set_diff(today_state.progress.blocked, yesterday_state.progress.blocked),
        resolved_blockers=_set_diff(yesterday_state.progress.blocked, today_state.progress.blocked),
    )

    # New links
    new_links = _set_diff(today_state.artifacts.links, yesterday_state.artifacts.links)

    # New help requests
    new_help_requests = _set_diff(today_state.help_requests, yesterday_state.help_requests)

    return DailyChannelDelta(
        channel_name=today_state.channel_name,
        date=today_state.date,
        compared_to=yesterday_state.date,
        new_topics=list(new_topics),
        resolved_topics=list(resolved_topics),
        progress_changes=progress_changes,
        new_links=list(new_links),
        new_help_requests=list(new_help_requests),
    )


def _set_diff(today: list[str], yesterday: list[str]) -> set[str]:
    """Compute set difference: items in today but not in yesterday.

    Args:
        today: Today's list
        yesterday: Yesterday's list

    Returns:
        Set of items in today but not in yesterday
    """
    return set(today) - set(yesterday)


def has_significant_changes(delta: DailyChannelDelta) -> bool:
    """Check if delta has any significant changes.

    Args:
        delta: Daily channel delta

    Returns:
        True if delta has any changes
    """
    if delta.compared_to is None:
        return False

    # Check all list fields for non-empty lists
    return (
        bool(delta.new_topics)
        or bool(delta.resolved_topics)
        or bool(delta.progress_changes.started_now)
        or bool(delta.progress_changes.finished_now)
        or bool(delta.progress_changes.new_blockers)
        or bool(delta.progress_changes.resolved_blockers)
        or bool(delta.new_links)
        or bool(delta.new_help_requests)
    )
