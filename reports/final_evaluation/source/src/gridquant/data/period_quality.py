"""Validate an hourly DE-LU price snapshot over local delivery dates."""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from gridquant.data.models import PriceDataset
from gridquant.data.quality import CoverageReport, check_daily_coverage


@dataclass(frozen=True)
class PeriodQualityReport:
    start_date: date
    end_date: date
    expected_count: int
    observed_count: int
    daily_reports: tuple[CoverageReport, ...]
    issues: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.issues and all(
            report.has_complete_start_grid for report in self.daily_reports
        )


def check_hourly_period(
    dataset: PriceDataset,
    start_date: date,
    end_date: date,
) -> PeriodQualityReport:
    """Check inclusive Berlin delivery dates without modifying input rows."""
    for value in (start_date, end_date):
        if not isinstance(value, date) or isinstance(value, datetime):
            raise TypeError("Period boundaries must be dates.")

    if end_date < start_date:
        raise ValueError("end_date must not precede start_date.")

    berlin = ZoneInfo("Europe/Berlin")
    hour = timedelta(hours=1)

    period_start = datetime.combine(start_date, time.min, berlin).astimezone(UTC)

    period_end = datetime.combine(
        end_date + timedelta(days=1), time.min, berlin
    ).astimezone(UTC)

    issues: list[str] = []
    spans: list[tuple[datetime, datetime]] = []
    prices_by_interval: dict[tuple[datetime, datetime], float] = {}

    if dataset.series_id != "day_ahead_price":
        issues.append("Unexpected series_id.")

    for index, row in enumerate(dataset.intervals):
        start = row.delivery_start_utc
        end = row.delivery_end_utc

        # Naive timestamps cannot be assigned to a delivery day safely.
        for timestamp in (start, end):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError(f"Row {index}: timestamp has no UTC offset.")

        start = start.astimezone(UTC)
        end = end.astimezone(UTC)

        if end - start != hour:
            issues.append(f"Row {index}: duration is not one hour.")

        if not (period_start <= start < end <= period_end):
            issues.append(f"Row {index}: invalid or out-of-period interval.")

        if row.bidding_zone != "DE-LU":
            issues.append(f"Row {index}: unexpected bidding zone.")

        price = row.price_eur_per_mwh
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            issues.append(f"Row {index}: price is not numeric.")
        elif not isfinite(price):
            issues.append(f"Row {index}: price is not finite.")
        else:
            key = (start, end)
            if key in prices_by_interval:
                if prices_by_interval[key] != price:
                    issues.append(f"Row {index}: conflicting price.")
            else:
                prices_by_interval[key] = price

        spans.append((start, end))

    starts = [start for start, _ in spans]
    if starts != sorted(starts):
        issues.append("Records are not in chronological order.")

    # Sort a separate list for continuity checks; preserve original rows.
    furthest_end: datetime | None = None
    for start, end in sorted(spans):
        if furthest_end is not None:
            if start < furthest_end:
                issues.append(f"Overlap at {start.isoformat()}.")
            elif start > furthest_end:
                issues.append(f"Gap before {start.isoformat()}.")

        furthest_end = end if furthest_end is None else max(furthest_end, end)

    daily_reports: list[CoverageReport] = []
    delivery_date = start_date

    while delivery_date <= end_date:
        daily_rows = tuple(
            row
            for row in dataset.intervals
            if row.delivery_start_utc.astimezone(berlin).date() == delivery_date
        )

        daily_dataset = replace(dataset, intervals=daily_rows)

        daily_reports.append(
            check_daily_coverage(
                daily_dataset,
                delivery_date,
                interval_minutes=60,
            )
        )
        delivery_date += timedelta(days=1)

    return PeriodQualityReport(
        start_date=start_date,
        end_date=end_date,
        expected_count=sum(report.expected_count for report in daily_reports),
        observed_count=len(dataset.intervals),
        daily_reports=tuple(daily_reports),
        issues=tuple(issues),
    )
