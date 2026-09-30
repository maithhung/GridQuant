from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from gridquant.data.models import DatasetMetadata, PriceDataset, PriceInterval
from gridquant.models.seasonal import forecast_seasonal


def source_curve(start: datetime, count: int) -> PriceDataset:
    """Explicit UTC fixtures, with distinct prices so alignment is observable."""
    return PriceDataset(
        series_id="day_ahead_price",
        metadata=DatasetMetadata(
            source="synthetic",
            source_document_id="seasonal-fixture",
            raw_sha256="0" * 64,
            retrieved_at_utc=datetime(2026, 9, 30, tzinfo=UTC),
        ),
        intervals=tuple(
            PriceInterval(
                start + timedelta(hours=index),
                start + timedelta(hours=index + 1),
                float(index - 10),
                "DE-LU",
            )
            for index in range(count)
        ),
    )


@pytest.mark.parametrize(
    "lag_days,target", [(1, date(2023, 2, 16)), (7, date(2023, 2, 22))]
)
def test_ordinary_curve_and_provenance(lag_days: int, target: date) -> None:
    dataset = source_curve(datetime(2023, 2, 14, 23, tzinfo=UTC), 24)
    before = dataset.intervals
    result = forecast_seasonal(dataset, target, lag_days=lag_days)
    assert len(result) == 24
    assert [row.prediction_eur_per_mwh for row in result] == list(range(-10, 14))
    assert result[14].prediction_eur_per_mwh == 4.0
    assert result[14].source_starts_utc == (datetime(2023, 2, 15, 13, tzinfo=UTC),)
    assert result[0].origin_utc == datetime.combine(
        target - timedelta(days=1), datetime.min.time(), UTC
    ) + timedelta(hours=10)
    assert result[0].model_id == ("previous_day" if lag_days == 1 else "previous_week")
    assert result[0].source_document_id == "seasonal-fixture"
    assert result[0].raw_sha256 == "0" * 64
    assert all(
        row.failure_reason is None and row.substitution == "none" for row in result
    )
    assert dataset.intervals == before


@pytest.mark.parametrize(
    "lag_days,target", [(1, date(2023, 3, 27)), (7, date(2023, 4, 2))]
)
def test_missing_spring_hour_uses_complete_source_mean(
    lag_days: int, target: date
) -> None:
    dataset = source_curve(datetime(2023, 3, 25, 23, tzinfo=UTC), 23)
    result = forecast_seasonal(dataset, target, lag_days=lag_days)
    assert len(result) == 24
    assert result[2].substitution == "source_day_mean"
    assert result[2].prediction_eur_per_mwh == 1.0  # mean of -10 through 12
    assert len(result[2].source_starts_utc) == 23
    assert result[3].prediction_eur_per_mwh == -8.0
    assert result[3].substitution == "none"


def test_spring_target_has_no_invented_hour_and_correct_origin() -> None:
    dataset = source_curve(datetime(2023, 3, 24, 23, tzinfo=UTC), 24)
    result = forecast_seasonal(dataset, date(2023, 3, 26))
    assert len(result) == 23
    assert 2 not in [row.local_hour for row in result]
    assert result[2].prediction_eur_per_mwh == -7.0  # local 03:00, not row 2
    assert result[0].origin_utc == datetime(2023, 3, 25, 10, tzinfo=UTC)
    assert result[-1].delivery_end_utc == datetime(2023, 3, 26, 22, tzinfo=UTC)


@pytest.mark.parametrize(
    "lag_days,start",
    [
        (1, datetime(2023, 10, 27, 22, tzinfo=UTC)),
        (7, datetime(2023, 10, 21, 22, tzinfo=UTC)),
    ],
)
def test_autumn_target_reuses_available_occurrence(
    lag_days: int, start: datetime
) -> None:
    result = forecast_seasonal(
        source_curve(start, 24), date(2023, 10, 29), lag_days=lag_days
    )
    assert len(result) == 25
    first, second = result[2:4]
    assert (first.local_hour, first.repeated_hour_occurrence) == (2, 0)
    assert (second.local_hour, second.repeated_hour_occurrence) == (2, 1)
    assert first.prediction_eur_per_mwh == second.prediction_eur_per_mwh == -8.0
    assert first.substitution == "none"
    assert second.substitution == "same_hour"
    assert first.source_starts_utc == second.source_starts_utc
    assert second.delivery_start_utc - first.delivery_start_utc == timedelta(hours=1)
    assert first.origin_utc == datetime(2023, 10, 28, 9, tzinfo=UTC)


def test_autumn_source_uses_first_occurrence_for_ordinary_target() -> None:
    dataset = source_curve(datetime(2023, 10, 28, 22, tzinfo=UTC), 25)
    result = forecast_seasonal(dataset, date(2023, 10, 30))
    assert len(result) == 24
    assert result[2].prediction_eur_per_mwh == -8.0
    assert result[3].prediction_eur_per_mwh == -6.0
    assert result[0].origin_utc == datetime(2023, 10, 29, 10, tzinfo=UTC)


@pytest.mark.parametrize(
    "damage",
    ["missing", "duplicate", "conflict", "duration", "zone", "nan", "order", "empty"],
)
def test_invalid_source_fails_every_target(damage: str) -> None:
    dataset = source_curve(datetime(2023, 2, 14, 23, tzinfo=UTC), 24)
    rows = list(dataset.intervals)
    if damage == "missing":
        rows.pop(2)
    elif damage == "duplicate":
        rows[2] = rows[1]
    elif damage == "conflict":
        rows.insert(1, replace(rows[0], price_eur_per_mwh=999.0))
    elif damage == "duration":
        rows[2] = replace(rows[2], delivery_end_utc=rows[2].delivery_start_utc)
    elif damage == "zone":
        rows[2] = replace(rows[2], bidding_zone="FR")
    elif damage == "nan":
        rows[2] = replace(rows[2], price_eur_per_mwh=float("nan"))
    elif damage == "order":
        rows.reverse()
    else:
        rows.clear()
    result = forecast_seasonal(
        replace(dataset, intervals=tuple(rows)), date(2023, 2, 16)
    )
    assert len(result) == 24
    assert all(
        row.prediction_eur_per_mwh is None and row.failure_reason for row in result
    )
    assert all(
        row.substitution == "none" and not row.source_starts_utc for row in result
    )


def test_target_and_future_prices_cannot_change_predictions() -> None:
    source = source_curve(datetime(2023, 2, 14, 23, tzinfo=UTC), 24)
    future = source_curve(datetime(2023, 2, 15, 23, tzinfo=UTC), 48)
    with_future = replace(source, intervals=source.intervals + future.intervals)
    corrupted = replace(
        source,
        intervals=source.intervals
        + tuple(
            replace(row, price_eur_per_mwh=float("nan")) for row in future.intervals
        ),
    )
    expected = forecast_seasonal(source, date(2023, 2, 16))
    assert forecast_seasonal(with_future, date(2023, 2, 16)) == expected
    assert forecast_seasonal(corrupted, date(2023, 2, 16)) == expected


@pytest.mark.parametrize("lag", [0, -1, 2, 8])
def test_unsupported_lag_is_rejected(lag: int) -> None:
    with pytest.raises(ValueError, match="supports only"):
        forecast_seasonal(
            source_curve(datetime(2023, 2, 14, 23, tzinfo=UTC), 24),
            date(2023, 2, 16),
            lag_days=lag,
        )


def test_boolean_lag_and_datetime_target_are_rejected() -> None:
    dataset = source_curve(datetime(2023, 2, 14, 23, tzinfo=UTC), 24)
    with pytest.raises(TypeError, match="integer"):
        forecast_seasonal(dataset, date(2023, 2, 16), lag_days=True)
    with pytest.raises(TypeError, match="date, not a datetime"):
        forecast_seasonal(dataset, datetime(2023, 2, 16, tzinfo=UTC))
