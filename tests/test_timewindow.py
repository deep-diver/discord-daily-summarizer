"""Tests for time window functionality."""

import pytest
from zoneinfo import ZoneInfo

from src.core.timewindow import TimeWindow, expand_date_range


class TestTimeWindow:
    """Test time window creation and manipulation."""

    def test_from_date(self) -> None:
        """Test creating time window from date string."""
        tw = TimeWindow.from_date("2026-01-17")

        assert tw.effective_date == "2026-01-17"
        assert tw.start.hour == 0
        assert tw.start.minute == 0
        assert tw.end.hour == 23
        assert tw.end.minute == 59

    def test_from_date_invalid_format(self) -> None:
        """Test that invalid date format raises error."""
        with pytest.raises(ValueError, match="Invalid date format"):
            TimeWindow.from_date("2026/01/17")

    def test_from_date_timezone(self) -> None:
        """Test that time window uses correct timezone."""
        tz = ZoneInfo("Asia/Seoul")
        tw = TimeWindow.from_date("2026-01-17", tz=tz)

        assert tw.start.tzinfo == tz
        assert tw.end.tzinfo == tz

    def test_from_hours(self) -> None:
        """Test creating rolling time window."""
        tw = TimeWindow.from_hours(24)

        assert len(str(tw.effective_date)) == 10  # YYYY-MM-DD format
        assert tw.end >= tw.start

    def test_from_hours_timezone(self) -> None:
        """Test that hours window uses correct timezone."""
        tz = ZoneInfo("Asia/Seoul")
        tw = TimeWindow.from_hours(1, tz=tz)

        assert tw.start.tzinfo == tz
        assert tw.end.tzinfo == tz

    def test_to_isoformat(self) -> None:
        """Test converting time window to ISO format."""
        tw = TimeWindow.from_date("2026-01-17")
        start_iso, end_iso = tw.to_isoformat()

        assert "2026-01-17" in start_iso
        assert "2026-01-17" in end_iso

    def test_expand_date_range_single_day(self) -> None:
        """Test expanding single day range."""
        dates = expand_date_range("2026-01-17", "2026-01-17")

        assert dates == ["2026-01-17"]

    def test_expand_date_range_multiple_days(self) -> None:
        """Test expanding multi-day range."""
        dates = expand_date_range("2026-01-15", "2026-01-17")

        assert dates == ["2026-01-15", "2026-01-16", "2026-01-17"]

    def test_expand_date_range_invalid_format(self) -> None:
        """Test that invalid date format raises error."""
        with pytest.raises(ValueError, match="Invalid date format"):
            expand_date_range("2026/01/15", "2026/01/17")

    def test_expand_date_range_end_before_start(self) -> None:
        """Test that end before start raises error."""
        with pytest.raises(ValueError, match="End date.*is before start date"):
            expand_date_range("2026-01-17", "2026-01-15")

    def test_expand_date_range_timezone(self) -> None:
        """Test expanding date range with timezone."""
        tz = ZoneInfo("Asia/Seoul")
        dates = expand_date_range("2026-01-15", "2026-01-17", tz=tz)

        assert len(dates) == 3
        assert dates[0] == "2026-01-15"

    def test_time_window_repr(self) -> None:
        """Test time window string representation."""
        tw = TimeWindow.from_date("2026-01-17")
        repr_str = repr(tw)

        assert "TimeWindow" in repr_str
        assert "2026-01-17" in repr_str

    def test_from_date_preserves_date(self) -> None:
        """Test that from_date preserves the original date."""
        tw = TimeWindow.from_date("2026-01-17")

        # Check that start and end are on the same day
        assert tw.start.date() == tw.end.date()

    def test_from_hours_window_size(self) -> None:
        """Test that from_hours creates correct window size."""
        tw = TimeWindow.from_hours(24)

        # Window should be approximately 24 hours
        window_hours = (tw.end - tw.start).total_seconds() / 3600
        assert 23 <= window_hours <= 24

    def test_from_hours_zero(self) -> None:
        """Test that from_hours with 0 works."""
        tw = TimeWindow.from_hours(0)

        assert tw.start <= tw.end

    def test_multiple_date_ranges(self) -> None:
        """Test expanding various date ranges."""
        # 1 week
        dates = expand_date_range("2026-01-01", "2026-01-07")
        assert len(dates) == 7

        # 1 month (approx)
        dates = expand_date_range("2026-01-01", "2026-01-31")
        assert len(dates) == 31

    def test_leap_year_date(self) -> None:
        """Test date range that includes leap day."""
        dates = expand_date_range("2024-02-28", "2024-03-01")
        assert dates == ["2024-02-28", "2024-02-29", "2024-03-01"]

    def test_time_window_effective_date_format(self) -> None:
        """Test that effective_date is in correct format."""
        tw = TimeWindow.from_date("2026-01-17")
        assert len(tw.effective_date.split("-")) == 3

        tw = TimeWindow.from_hours(24)
        assert len(tw.effective_date.split("-")) == 3

    def test_cross_month_boundary(self) -> None:
        """Test date range crossing month boundary."""
        dates = expand_date_range("2026-01-31", "2026-02-02")
        assert dates == ["2026-01-31", "2026-02-01", "2026-02-02"]

    def test_cross_year_boundary(self) -> None:
        """Test date range crossing year boundary."""
        dates = expand_date_range("2025-12-31", "2026-01-02")
        assert dates == ["2025-12-31", "2026-01-01", "2026-01-02"]
