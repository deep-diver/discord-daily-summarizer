"""Time window handling for date/range/last-hours modes."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


# Default timezone as per spec
DEFAULT_TIMEZONE = ZoneInfo("Asia/Seoul")


@dataclass
class TimeWindow:
    """A time window for querying messages."""

    start: datetime
    end: datetime
    effective_date: str  # YYYY-MM-DD format for storing results

    @classmethod
    def from_date(cls, date_str: str, tz: ZoneInfo = DEFAULT_TIMEZONE) -> "TimeWindow":
        """Create a time window from a date string (YYYY-MM-DD).

        Window: [YYYY-MM-DD 00:00:00, YYYY-MM-DD 23:59:59] in the specified timezone.

        Args:
            date_str: Date string in YYYY-MM-DD format
            tz: Timezone to use (default: Asia/Seoul)

        Returns:
            TimeWindow instance

        Raises:
            ValueError: If date_str is not in YYYY-MM-DD format
        """
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
        except ValueError as e:
            raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD") from e

        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date.replace(hour=23, minute=59, second=59, microsecond=999999)

        return cls(start=start, end=end, effective_date=date_str)

    @classmethod
    def from_hours(cls, hours: int, tz: ZoneInfo = DEFAULT_TIMEZONE) -> "TimeWindow":
        """Create a rolling time window for the last N hours.

        Window: [now - N hours, now] in the specified timezone.
        The effective date is set to the current date.

        Args:
            hours: Number of hours to look back
            tz: Timezone to use (default: Asia/Seoul)

        Returns:
            TimeWindow instance
        """
        now = datetime.now(tz)
        start = now - timedelta(hours=hours)
        end = now
        effective_date = now.strftime("%Y-%m-%d")

        return cls(start=start, end=end, effective_date=effective_date)

    def to_isoformat(self) -> tuple[str, str]:
        """Convert start and end to ISO format strings for database queries.

        Returns:
            Tuple of (start_iso, end_iso) strings
        """
        return self.start.isoformat(), self.end.isoformat()

    def __repr__(self) -> str:
        return f"TimeWindow(start={self.start.isoformat()}, end={self.end.isoformat()}, effective_date={self.effective_date})"


def expand_date_range(start_str: str, end_str: str, tz: ZoneInfo = DEFAULT_TIMEZONE) -> list[str]:
    """Expand a date range into individual date strings.

    Args:
        start_str: Start date in YYYY-MM-DD format (inclusive)
        end_str: End date in YYYY-MM-DD format (inclusive)
        tz: Timezone to use (default: Asia/Seoul)

    Returns:
        List of date strings in YYYY-MM-DD format

    Raises:
        ValueError: If dates are invalid or end is before start
    """
    try:
        start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=tz)
        end = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=tz)
    except ValueError as e:
        raise ValueError(f"Invalid date format. Expected YYYY-MM-DD: {e}") from e

    if end < start:
        raise ValueError(f"End date {end_str} is before start date {start_str}")

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    return dates
