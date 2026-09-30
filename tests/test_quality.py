from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from gridquant.data.models import DatasetMetadata, PriceDataset, PriceInterval
from gridquant.data.quality import check_daily_coverage


def make_dataset(start: datetime, count: int, minutes: int) -> PriceDataset:
    """Build fixtures from explicit UTC boundaries, independent of the checker."""
    step = timedelta(minutes=minutes)
    return PriceDataset(
        series_id="day_ahead_price",
        metadata=DatasetMetadata(
            source="synthetic",
            source_document_id="test-quality",
            raw_sha256="0" * 64,
            retrieved_at_utc=datetime(2026, 9, 30, tzinfo=UTC),
        ),
        intervals=tuple(
            PriceInterval(start + i * step, start + (i + 1) * step, -10.0, "DE-LU")
            for i in range(count)
        ),
    )


@pytest.mark.parametrize(
    "day,utc_start,hours",
    [
        (date(2023, 2, 15), datetime(2023, 2, 14, 23, tzinfo=UTC), 24),
        (date(2023, 3, 26), datetime(2023, 3, 25, 23, tzinfo=UTC), 23),
        (date(2023, 10, 29), datetime(2023, 10, 28, 22, tzinfo=UTC), 25),
    ],
)
@pytest.mark.parametrize("minutes", [15, 60])
def test_ordinary_and_dst_coverage(
    day: date, utc_start: datetime, hours: int, minutes: int
) -> None:
    count = hours * 60 // minutes
    dataset = make_dataset(utc_start, count, minutes)

    report = check_daily_coverage(dataset, day, minutes)

    assert report.expected_count == report.observed_count == count
    assert report.matched_count == count
    assert report.coverage_percent == 100.0
    assert report.has_complete_start_grid


def test_missing_and_duplicate_with_unchanged_row_count() -> None:
    dataset = make_dataset(datetime(2026, 9, 25, 22, tzinfo=UTC), 96, 15)
    original_intervals = dataset.intervals
    broken = replace(dataset, intervals=dataset.intervals[1:] + (dataset.intervals[1],))

    report = check_daily_coverage(broken, date(2026, 9, 26), 15)

    assert report.expected_count == report.observed_count == 96
    assert report.matched_count == 95
    assert report.coverage_percent == pytest.approx(95 / 96 * 100)
    assert report.missing_starts == (dataset.intervals[0].delivery_start_utc,)
    assert report.duplicate_starts == (dataset.intervals[1].delivery_start_utc,)
    assert report.unexpected_starts == ()
    assert not report.has_complete_start_grid
    assert dataset.intervals == original_intervals


def test_out_of_range_and_off_grid_starts() -> None:
    start = datetime(2026, 9, 25, 22, tzinfo=UTC)
    dataset = make_dataset(start, 96, 15)
    extra_starts = (
        start - timedelta(minutes=15),
        start + timedelta(minutes=1),
        start + timedelta(days=1),
    )
    extras = tuple(
        PriceInterval(value, value + timedelta(minutes=15), 20.0, "DE-LU")
        for value in extra_starts
    )

    report = check_daily_coverage(
        replace(dataset, intervals=dataset.intervals + extras), date(2026, 9, 26), 15
    )

    assert report.unexpected_starts == extra_starts
    assert report.coverage_percent == 100.0
    assert report.observed_count == 99
    assert not report.has_complete_start_grid


def test_empty_dataset_reports_all_starts_missing() -> None:
    dataset = make_dataset(datetime(2026, 9, 25, 22, tzinfo=UTC), 0, 15)
    report = check_daily_coverage(dataset, date(2026, 9, 26), 15)
    assert report.expected_count == len(report.missing_starts) == 96
    assert report.observed_count == report.matched_count == 0
    assert report.coverage_percent == 0.0
    assert not report.has_complete_start_grid


def test_repeated_local_hour_is_not_a_duplicate() -> None:
    dataset = make_dataset(datetime(2023, 10, 28, 22, tzinfo=UTC), 25, 60)
    berlin = ZoneInfo("Europe/Berlin")
    local_intervals = tuple(
        replace(
            interval, delivery_start_utc=interval.delivery_start_utc.astimezone(berlin)
        )
        for interval in dataset.intervals
    )
    report = check_daily_coverage(
        replace(dataset, intervals=local_intervals), date(2023, 10, 29), 60
    )
    assert report.has_complete_start_grid
    assert report.duplicate_starts == ()


def test_naive_start_is_rejected() -> None:
    dataset = make_dataset(datetime(2026, 9, 26, tzinfo=None), 1, 15)  # noqa: DTZ001
    with pytest.raises(ValueError, match="UTC offset"):
        check_daily_coverage(dataset, date(2026, 9, 26), 15)


@pytest.mark.parametrize("minutes", [0, -15, 7, 1500])
def test_invalid_resolution(minutes: int) -> None:
    dataset = make_dataset(datetime(2026, 9, 25, 22, tzinfo=UTC), 0, 15)
    with pytest.raises(ValueError, match="positive|divide"):
        check_daily_coverage(dataset, date(2026, 9, 26), minutes)


def test_boolean_resolution_is_rejected() -> None:
    dataset = make_dataset(datetime(2026, 9, 25, 22, tzinfo=UTC), 0, 15)
    with pytest.raises(TypeError, match="integer"):
        check_daily_coverage(dataset, date(2026, 9, 26), True)
