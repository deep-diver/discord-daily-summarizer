"""Tests for delta computation."""

import pytest

from src.core.delta import compute_delta, has_significant_changes, _set_diff
from src.core.models import DailyChannelState, DailyChannelDelta, Progress, ProgressChanges


class TestDeltaComputation:
    """Test delta computation between states."""

    def test_compute_delta_no_previous(self, sample_state: DailyChannelState) -> None:
        """Test computing delta when no previous state exists."""
        delta = compute_delta(sample_state, None)

        assert delta.channel_name == sample_state.channel_name
        assert delta.date == sample_state.date
        assert delta.compared_to is None
        assert delta.new_topics == []
        assert delta.resolved_topics == []

    def test_compute_delta_with_previous(
        self, sample_state: DailyChannelState, sample_previous_state: DailyChannelState
    ) -> None:
        """Test computing delta with previous state."""
        delta = compute_delta(sample_state, sample_previous_state)

        assert delta.compared_to == sample_previous_state.date
        assert "Topic B" in delta.new_topics
        assert "Topic C" in delta.resolved_topics

    def test_compute_delta_new_topics(self) -> None:
        """Test detecting new topics."""
        state1 = DailyChannelState(channel_name="test", date="2026-01-16", topics=["A", "B"])
        state2 = DailyChannelState(channel_name="test", date="2026-01-17", topics=["A", "C"])

        delta = compute_delta(state2, state1)

        assert "C" in delta.new_topics
        assert "A" not in delta.new_topics

    def test_compute_delta_resolved_topics(self) -> None:
        """Test detecting resolved topics."""
        state1 = DailyChannelState(channel_name="test", date="2026-01-16", topics=["A", "B"])
        state2 = DailyChannelState(channel_name="test", date="2026-01-17", topics=["A"])

        delta = compute_delta(state2, state1)

        assert "B" in delta.resolved_topics

    def test_compute_delta_progress_started(self) -> None:
        """Test detecting newly started tasks."""
        state1 = DailyChannelState(
            channel_name="test",
            date="2026-01-16",
            progress=Progress(started=["Task A"]),
        )
        state2 = DailyChannelState(
            channel_name="test",
            date="2026-01-17",
            progress=Progress(started=["Task A", "Task B"]),
        )

        delta = compute_delta(state2, state1)

        assert "Task B" in delta.progress_changes.started_now
        assert "Task A" not in delta.progress_changes.started_now

    def test_compute_delta_progress_finished(self) -> None:
        """Test detecting finished tasks."""
        state1 = DailyChannelState(
            channel_name="test",
            date="2026-01-16",
            progress=Progress(finished=[]),
        )
        state2 = DailyChannelState(
            channel_name="test",
            date="2026-01-17",
            progress=Progress(finished=["Task A", "Task B"]),
        )

        delta = compute_delta(state2, state1)

        assert "Task A" in delta.progress_changes.finished_now
        assert "Task B" in delta.progress_changes.finished_now

    def test_compute_delta_new_blockers(self) -> None:
        """Test detecting new blockers."""
        state1 = DailyChannelState(
            channel_name="test",
            date="2026-01-16",
            progress=Progress(blocked=["Blocker A"]),
        )
        state2 = DailyChannelState(
            channel_name="test",
            date="2026-01-17",
            progress=Progress(blocked=["Blocker A", "Blocker B"]),
        )

        delta = compute_delta(state2, state1)

        assert "Blocker B" in delta.progress_changes.new_blockers
        assert "Blocker A" not in delta.progress_changes.new_blockers

    def test_compute_delta_resolved_blockers(self) -> None:
        """Test detecting resolved blockers."""
        state1 = DailyChannelState(
            channel_name="test",
            date="2026-01-16",
            progress=Progress(blocked=["Blocker A", "Blocker B"]),
        )
        state2 = DailyChannelState(
            channel_name="test",
            date="2026-01-17",
            progress=Progress(blocked=["Blocker A"]),
        )

        delta = compute_delta(state2, state1)

        assert "Blocker B" in delta.progress_changes.resolved_blockers
        assert "Blocker A" not in delta.progress_changes.resolved_blockers

    def test_compute_delta_new_links(self) -> None:
        """Test detecting new links."""
        from src.core.models import Artifacts

        state1 = DailyChannelState(
            channel_name="test",
            date="2026-01-16",
            artifacts=Artifacts(links=["https://old.com"]),
        )
        state2 = DailyChannelState(
            channel_name="test",
            date="2026-01-17",
            artifacts=Artifacts(links=["https://old.com", "https://new.com"]),
        )

        delta = compute_delta(state2, state1)

        assert "https://new.com" in delta.new_links
        assert "https://old.com" not in delta.new_links

    def test_compute_delta_new_help_requests(self) -> None:
        """Test detecting new help requests."""
        state1 = DailyChannelState(
            channel_name="test",
            date="2026-01-16",
            help_requests=[],
        )
        state2 = DailyChannelState(
            channel_name="test",
            date="2026-01-17",
            help_requests=["Help with task A"],
        )

        delta = compute_delta(state2, state1)

        assert "Help with task A" in delta.new_help_requests

    def test_has_significant_changes_no_previous(self) -> None:
        """Test has_significant_changes with no previous day."""
        delta = DailyChannelDelta(
            channel_name="test",
            date="2026-01-17",
            compared_to=None,
        )

        assert not has_significant_changes(delta)

    def test_has_significant_changes_with_changes(self) -> None:
        """Test has_significant_changes detects changes."""
        delta = DailyChannelDelta(
            channel_name="test",
            date="2026-01-17",
            compared_to="2026-01-16",
            new_topics=["New Topic"],
        )

        assert has_significant_changes(delta)

    def test_has_significant_changes_no_changes(self) -> None:
        """Test has_significant_changes with no changes."""
        delta = DailyChannelDelta(
            channel_name="test",
            date="2026-01-17",
            compared_to="2026-01-16",
        )

        assert not has_significant_changes(delta)

    def test_set_diff(self) -> None:
        """Test set difference function."""
        today = ["A", "B", "C"]
        yesterday = ["A", "B", "D"]

        diff = _set_diff(today, yesterday)

        assert "C" in diff
        assert "D" not in diff
        assert "A" not in diff
        assert "B" not in diff

    def test_set_diff_empty_yesterday(self) -> None:
        """Test set diff with empty yesterday."""
        today = ["A", "B", "C"]
        yesterday = []

        diff = _set_diff(today, yesterday)

        assert diff == {"A", "B", "C"}

    def test_set_diff_empty_today(self) -> None:
        """Test set diff with empty today."""
        today = []
        yesterday = ["A", "B", "C"]

        diff = _set_diff(today, yesterday)

        assert diff == set()

    def test_set_diff_duplicates(self) -> None:
        """Test set diff handles duplicates correctly."""
        today = ["A", "A", "B", "B"]
        yesterday = ["A", "C"]

        diff = _set_diff(today, yesterday)

        assert "B" in diff
        assert "C" not in diff

    def test_compute_delta_channel_name_preserved(
        self, sample_state: DailyChannelState, sample_previous_state: DailyChannelState
    ) -> None:
        """Test that channel name is preserved in delta."""
        delta = compute_delta(sample_state, sample_previous_state)

        assert delta.channel_name == sample_state.channel_name

    def test_compute_delta_date_preserved(
        self, sample_state: DailyChannelState, sample_previous_state: DailyChannelState
    ) -> None:
        """Test that date is preserved in delta."""
        delta = compute_delta(sample_state, sample_previous_state)

        assert delta.date == sample_state.date

    def test_compute_delta_all_progress_changes(self) -> None:
        """Test all progress change types are computed."""
        state1 = DailyChannelState(
            channel_name="test",
            date="2026-01-16",
            progress=Progress(
                started=["Task A"],
                finished=["Task B"],
                blocked=["Blocker A"],
            ),
        )
        state2 = DailyChannelState(
            channel_name="test",
            date="2026-01-17",
            progress=Progress(
                started=["Task A", "Task C"],
                finished=["Task B", "Task D"],
                blocked=["Blocker A", "Blocker B"],
            ),
        )

        delta = compute_delta(state2, state1)

        assert "Task C" in delta.progress_changes.started_now
        assert "Task D" in delta.progress_changes.finished_now
        assert "Blocker B" in delta.progress_changes.new_blockers

    def test_compute_delta_empty_states(self) -> None:
        """Test delta computation with empty states."""
        state1 = DailyChannelState(channel_name="test", date="2026-01-16")
        state2 = DailyChannelState(channel_name="test", date="2026-01-17")

        delta = compute_delta(state2, state1)

        assert delta.new_topics == []
        assert delta.resolved_topics == []
        assert delta.new_links == []
        assert delta.new_help_requests == []
