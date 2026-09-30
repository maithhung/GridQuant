"""Hourly seasonal price curves under the R1 latest-vintage assumption.

The complete D-1 price curve is assumed usable at 11:00 Berlin on D-1.
This is not verified historical availability. Targets come from the calendar,
not observed target prices. Ridge can reuse these results as its lag features.
"""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from statistics import fmean
from typing import Literal
from zoneinfo import ZoneInfo

from gridquant.data.models import PriceDataset, PriceInterval
from gridquant.data.period_quality import check_hourly_period

BERLIN = ZoneInfo("Europe/Berlin")
HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class SeasonalPrediction:
    """One target, including failed forecasts and all source dependencies."""

    model_id: Literal["previous_day", "previous_week"]
    origin_utc: datetime
    delivery_start_utc: datetime
    delivery_end_utc: datetime
    local_hour: int
    repeated_hour_occurrence: int
    prediction_eur_per_mwh: float | None
    source_delivery_date: date
    source_starts_utc: tuple[datetime, ...]
    source_document_id: str
    raw_sha256: str
    substitution: Literal["none", "same_hour", "source_day_mean"]
    failure_reason: str | None
    evidence_track: Literal["latest_vintage"] = "latest_vintage"


def _hourly_starts(day: date) -> tuple[datetime, ...]:
    start = datetime.combine(day, time.min, BERLIN).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, BERLIN).astimezone(UTC)
    return tuple(start + index * HOUR for index in range((end - start) // HOUR))


def forecast_seasonal(
    dataset: PriceDataset,
    delivery_date: date,
    *,
    lag_days: int = 1,
) -> tuple[SeasonalPrediction, ...]:
    """Forecast a complete local day using D-1 or D-7, without target prices.

    Invalid arguments or naive input timestamps raise an exception. A missing
    or invalid source-day curve returns one failed prediction for every target;
    it never silently reduces coverage. Unrelated days' prices are not read.
    Source rows must already be chronological and pass hourly validation.
    """
    if not isinstance(delivery_date, date) or isinstance(delivery_date, datetime):
        raise TypeError("delivery_date must be a date, not a datetime.")
    if isinstance(lag_days, bool) or not isinstance(lag_days, int):
        raise TypeError("lag_days must be an integer.")
    if lag_days not in (1, 7):
        raise ValueError("R1 supports only lag_days=1 or lag_days=7.")

    source_date = delivery_date - timedelta(days=lag_days)
    origin = datetime.combine(
        delivery_date - timedelta(days=1), time(11), BERLIN
    ).astimezone(UTC)
    source_rows: list[PriceInterval] = []
    for row in dataset.intervals:
        start = row.delivery_start_utc
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("Input interval starts must include a UTC offset.")
        if start.astimezone(BERLIN).date() == source_date:
            source_rows.append(row)

    source_dataset = replace(dataset, intervals=tuple(source_rows))
    failure: str | None = None
    if not source_rows:
        failure = "Missing source-day curve."
    else:
        quality = check_hourly_period(source_dataset, source_date, source_date)
        if not quality.passed:
            details = list(quality.issues)
            coverage = quality.daily_reports[0]
            if not coverage.has_complete_start_grid:
                details.append(
                    f"Invalid start grid: {len(coverage.missing_starts)} missing, "
                    f"{len(coverage.duplicate_starts)} duplicated, "
                    f"{len(coverage.unexpected_starts)} unexpected."
                )
            failure = "Invalid source-day curve. " + " ".join(details)

    by_label: dict[tuple[int, int], PriceInterval] = {}
    if failure is None:
        for row in source_rows:
            local = row.delivery_start_utc.astimezone(BERLIN)
            by_label[(local.hour, local.fold)] = row

    results: list[SeasonalPrediction] = []
    for target_start in _hourly_starts(delivery_date):
        local = target_start.astimezone(BERLIN)
        dependencies: tuple[PriceInterval, ...] = ()
        substitution: Literal["none", "same_hour", "source_day_mean"] = "none"
        prediction: float | None = None
        if failure is None:
            match = by_label.get((local.hour, local.fold))
            if match is not None:
                dependencies = (match,)
            else:
                same_hour = [
                    row for (hour, _), row in by_label.items() if hour == local.hour
                ]
                if same_hour:
                    dependencies = (same_hour[0],)
                    substitution = "same_hour"
                else:
                    dependencies = tuple(source_rows)
                    substitution = "source_day_mean"
            prediction = fmean(row.price_eur_per_mwh for row in dependencies)

        results.append(
            SeasonalPrediction(
                model_id="previous_day" if lag_days == 1 else "previous_week",
                origin_utc=origin,
                delivery_start_utc=target_start,
                delivery_end_utc=target_start + HOUR,
                local_hour=local.hour,
                repeated_hour_occurrence=local.fold,
                prediction_eur_per_mwh=prediction,
                source_delivery_date=source_date,
                source_starts_utc=tuple(
                    row.delivery_start_utc.astimezone(UTC) for row in dependencies
                ),
                source_document_id=dataset.metadata.source_document_id,
                raw_sha256=dataset.metadata.raw_sha256,
                substitution=substitution,
                failure_reason=failure,
            )
        )
    return tuple(results)
