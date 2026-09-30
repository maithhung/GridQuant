"""Check price interval starts against a Berlin delivery-day calendar.

This checks coverage only, not interval ends, prices, zones, or record order.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from gridquant.data.models import PriceDataset


@dataclass(frozen=True)
class CoverageReport:
    """Counts and unique diagnostic starts, all normalized to UTC."""

    delivery_date: date
    interval_minutes: int
    expected_count: int
    observed_count: int
    matched_count: int
    missing_starts: tuple[datetime, ...]
    duplicate_starts: tuple[datetime, ...]
    unexpected_starts: tuple[datetime, ...]

    @property
    def coverage_percent(self) -> float:
        """Duplicates and unexpected starts never increase coverage."""
        return 100.0 * self.matched_count / self.expected_count

    @property
    def has_complete_start_grid(self) -> bool:
        """Every expected start occurs exactly once, with no extra starts."""
        return not (
            self.missing_starts or self.duplicate_starts or self.unexpected_starts
        )


def check_daily_coverage(
    dataset: PriceDataset,
    delivery_date: date,
    interval_minutes: int,
) -> CoverageReport:
    """Compare all dataset starts with one Europe/Berlin delivery day.

    The caller supplies the expected resolution independently of the data.
    Both local midnights are converted to UTC before stepping through the day,
    preserving spring's shorter day and autumn's repeated hour. Starts outside
    the day or off the expected grid are unexpected; inputs are never changed.

    Reject naive starts and invalid calendar arguments. A successful coverage
    result does not establish valid interval ends or forecast-time availability.
    """
    if not isinstance(delivery_date, date) or isinstance(delivery_date, datetime):
        raise TypeError("delivery_date must be a date, not a datetime.")
    if isinstance(interval_minutes, bool) or not isinstance(interval_minutes, int):
        raise TypeError("interval_minutes must be an integer.")
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive.")

    berlin = ZoneInfo("Europe/Berlin")
    start_utc = datetime.combine(delivery_date, time.min, berlin).astimezone(UTC)
    end_utc = datetime.combine(
        delivery_date + timedelta(days=1), time.min, berlin
    ).astimezone(UTC)
    step = timedelta(minutes=interval_minutes)
    count, remainder = divmod(end_utc - start_utc, step)
    if remainder:
        raise ValueError("interval_minutes must divide the delivery day exactly.")
    expected = {start_utc + index * step for index in range(count)}

    observed: Counter[datetime] = Counter()
    for interval in dataset.intervals:
        start = interval.delivery_start_utc
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("Interval starts must include a UTC offset.")
        # Normalize before comparing: repeated local hours have distinct UTC starts.
        observed[start.astimezone(UTC)] += 1

    observed_starts = set(observed)
    return CoverageReport(
        delivery_date=delivery_date,
        interval_minutes=interval_minutes,
        expected_count=count,
        observed_count=len(dataset.intervals),
        matched_count=len(expected & observed_starts),
        missing_starts=tuple(sorted(expected - observed_starts)),
        duplicate_starts=tuple(
            sorted(start for start, occurrences in observed.items() if occurrences > 1)
        ),
        unexpected_starts=tuple(sorted(observed_starts - expected)),
    )
